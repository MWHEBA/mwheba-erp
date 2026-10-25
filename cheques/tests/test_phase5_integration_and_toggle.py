# -*- coding: utf-8 -*-
"""
FIN-CHQ-PHASE5: Comprehensive Test Suite for Phase 5 Integration and Toggle
- SCN-06 & SCN-32: Invoice Allocation & SHA-256 Audit Trail
- SCN-17 & SCN-22: Full Bounce Reversal & Invoice Reopening
- SCN-18: Partial Collection & Bounce Proration
- SCN-23: Manual Allocation Reversal
- Posting Delegation: Zero GL Double-Posting for Cheques
- Opening Balance Cheques: Zero GL Entries & Portfolio Tracking
- SCN-38 & SCN-45: Feature Toggle & Draining Mode Governance
"""
import pytest
import hashlib
from decimal import Decimal
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from core.models import SystemModule, SystemSetting
from financial.models import (
    ChartOfAccounts,
    Currency,
    AccountType,
    JournalEntry,
    UserTreasuryAccess,
    OpeningBalanceBatch,
    FiscalYear,
)
from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
from financial.services.subledger_account_service import SubledgerAccountService
from financial.services.accounting_integration_service import AccountingIntegrationService
from customer.models import Customer, CustomerTransaction, CustomerAllocationAudit
from customer.services.customer_allocation_audit_service import CustomerAllocationAuditService
from sale.models import Sale, SalePayment

from cheques.models import (
    Checkbook,
    CheckbookLeaf,
    Cheque,
    ChequeType,
    ChequePurpose,
    ChequeStatus,
    ChequeInvoiceAllocation,
    AllocationStatus,
)
from cheques.services.accounting_service import ChequeAccountingService
from cheques.services.allocation_service import ChequeAllocationService
from cheques.services.toggle_service import ChequeToggleService

User = get_user_model()


@pytest.fixture
def test_user(db):
    user = User.objects.filter(username='phase5_admin').first()
    if not user:
        user = User.objects.create_user(
            username='phase5_admin',
            email='phase5_admin@mwheba.com',
            password='Password123!'
        )
    return user


@pytest.fixture
def account_types(db):
    asset_type, _ = AccountType.objects.get_or_create(
        code='asset', defaults={'name': 'أصول', 'category': 'asset', 'nature': 'debit'}
    )
    liability_type, _ = AccountType.objects.get_or_create(
        code='liability', defaults={'name': 'خصوم', 'category': 'liability', 'nature': 'credit'}
    )
    expense_type, _ = AccountType.objects.get_or_create(
        code='expense', defaults={'name': 'مصروفات', 'category': 'expense', 'nature': 'debit'}
    )
    revenue_type, _ = AccountType.objects.get_or_create(
        code='revenue', defaults={'name': 'إيرادات', 'category': 'revenue', 'nature': 'credit'}
    )
    return {
        'asset': asset_type,
        'liability': liability_type,
        'expense': expense_type,
        'revenue': revenue_type,
    }


@pytest.fixture
def financial_accounts(db, account_types):
    egp, _ = Currency.objects.get_or_create(
        code='EGP',
        defaults={'name': 'جنيه مصري', 'symbol': 'ج.م', 'is_functional': True, 'is_active': True}
    )

    bank, _ = ChartOfAccounts.objects.get_or_create(
        code='11160001',
        defaults={
            'name': 'البنك الأهلي المصري',
            'account_type': account_types['asset'],
            'level': 4,
            'is_leaf': True,
            'is_active': True,
            'currency': egp,
        }
    )

    notes_rec, _ = ChartOfAccounts.objects.get_or_create(
        code='11220',
        defaults={
            'name': 'أوراق القبض (شيكات برسم التحصيل)',
            'account_type': account_types['asset'],
            'level': 4,
            'is_leaf': True,
            'is_active': True,
            'currency': egp,
        }
    )

    under_coll, _ = ChartOfAccounts.objects.get_or_create(
        code='11190',
        defaults={
            'name': 'نقدية في الطريق وشيكات برسم التحصيل',
            'account_type': account_types['asset'],
            'level': 4,
            'is_leaf': True,
            'is_active': True,
            'currency': egp,
        }
    )

    notes_pay, _ = ChartOfAccounts.objects.get_or_create(
        code='21120',
        defaults={
            'name': 'أوراق الدفع (شيكات صادرة)',
            'account_type': account_types['liability'],
            'level': 4,
            'is_leaf': True,
            'is_active': True,
            'currency': egp,
        }
    )

    cust_adv, _ = ChartOfAccounts.objects.get_or_create(
        code='21510',
        defaults={
            'name': 'دفعات مقدمة من العملاء',
            'account_type': account_types['liability'],
            'level': 4,
            'is_leaf': True,
            'is_active': True,
            'currency': egp,
        }
    )

    bank_exp, _ = ChartOfAccounts.objects.get_or_create(
        code='54100',
        defaults={
            'name': 'عمولات ومصاريف بنكية',
            'account_type': account_types['expense'],
            'level': 4,
            'is_leaf': True,
            'is_active': True,
            'currency': egp,
        }
    )

    round_diff, _ = ChartOfAccounts.objects.get_or_create(
        code='54400',
        defaults={
            'name': 'فروق تقريب العملات',
            'account_type': account_types['expense'],
            'level': 4,
            'is_leaf': True,
            'is_active': True,
            'currency': egp,
        }
    )

    return {
        'bank': bank,
        'notes_rec': notes_rec,
        'under_coll': under_coll,
        'notes_pay': notes_pay,
        'cust_adv': cust_adv,
        'bank_exp': bank_exp,
        'round_diff': round_diff,
        'currency': egp,
    }


@pytest.fixture
def sample_customer(db, financial_accounts):
    cust, _ = Customer.objects.get_or_create(
        name='شركة النور الهندسية للتجارة',
        defaults={'code': 'CUST-NOOR-01', 'phone': '01099887766'}
    )
    SubledgerAccountService.get_or_create_customer_account(cust)
    cust.refresh_from_db()
    return cust


@pytest.fixture(autouse=True)
def setup_treasury_access(db, test_user, financial_accounts):
    access, _ = UserTreasuryAccess.objects.get_or_create(
        user=test_user,
        treasury=financial_accounts['bank'],
        defaults={
            'can_deposit': True,
            'can_disburse': True,
            'max_single_disbursement_limit': Decimal('1000000.00'),
            'daily_disbursement_limit': Decimal('2000000.00'),
        }
    )
    return access


@pytest.fixture
def sample_sale(db, sample_customer, test_user, financial_accounts):
    sale = Sale.objects.create(
        customer=sample_customer,
        date=timezone.now().date(),
        subtotal=Decimal('1000.00'),
        total=Decimal('1000.00'),
        currency=financial_accounts['currency'],
        exchange_rate=Decimal('1.000000'),
        total_functional=Decimal('1000.00'),
        payment_method='credit',
        created_by=test_user,
    )
    sale.update_payment_status()
    return sale


# ==============================================================================
# TESTS FOR PHASE 5
# ==============================================================================

@pytest.mark.django_db
class TestPhase5InvoiceIntegration:
    """
    اختبارات تكامل فواتير المبيعات مع أوراق القبض وتوثيق سجلات التدقيق المشفرة
    """

    def test_sale_invoice_allocation_with_cheque(self, sample_sale, sample_customer, test_user, financial_accounts):
        """
        SCN-06 & SCN-32: تخصيص ورقة قبض على فاتورة مبيعات:
        - التحقق من إنشاء ChequeInvoiceAllocation بحالة APPLIED
        - التحقق من إنشاء SalePayment مفوضة الترحيل (financial_account=None, source_type='CHEQUE')
        - التحقق من إنشاء CustomerAllocationAudit مع توقيع إثبات مشفر سليم SHA-256
        - التحقق من تحديث Sale.amount_paid و Sale.payment_status دون أي احتساب مزدوج
        """
        cheque = Cheque.objects.create(
            voucher_number='RV-P5-001',
            cheque_number='CHQ-77881',
            cheque_type=ChequeType.RECEIVABLE,
            purpose=ChequePurpose.INVOICE_SETTLEMENT,
            status=ChequeStatus.IN_PORTFOLIO,
            amount=Decimal('1000.00'),
            remaining_amount=Decimal('1000.00'),
            collected_amount=Decimal('0.00'),
            currency=financial_accounts['currency'],
            original_exchange_rate=Decimal('1.000000'),
            functional_amount=Decimal('1000.00'),
            book_value_functional=Decimal('1000.00'),
            customer=sample_customer,
            issue_date=timezone.now().date(),
            due_date=timezone.now().date() + timezone.timedelta(days=15),
            created_by=test_user
        )

        assert sample_sale.amount_paid == Decimal('0.00')
        assert sample_sale.payment_status == 'unpaid'

        # تنفيذ التخصيص
        alloc = ChequeAllocationService.allocate_cheque_to_invoice(
            cheque=cheque,
            sale=sample_sale,
            amount=Decimal('1000.00'),
            user=test_user,
            notes="سداد فاتورة المبيعات بالكامل بموجب شيك قبض"
        )

        # 1. التحقق من سجل التخصيص
        assert alloc.id is not None
        assert alloc.allocation_status == AllocationStatus.APPLIED
        assert alloc.allocated_amount == Decimal('1000.00')

        # 2. التحقق من سجل السداد SalePayment
        payment = SalePayment.objects.filter(sale=sample_sale, source_type='CHEQUE').first()
        assert payment is not None
        assert payment.amount == Decimal('1000.00')
        assert payment.financial_account is None  # لا ازدواج في قيود الخزينة/البنك العامة
        assert payment.status == 'posted'
        assert payment.reference_number == cheque.voucher_number
        assert "شيك رقم: RV-P5-001" in payment.source_display_info

        # 3. التحقق من سجل التدقيق CustomerAllocationAudit والتوقيع المشفر
        audit = CustomerAllocationAudit.objects.filter(
            target_document_number=sample_sale.number,
            source_document_number=cheque.voucher_number,
            allocation_status='APPLIED'
        ).first()
        assert audit is not None
        assert audit.allocated_amount == Decimal('1000.00')
        assert audit.evidence_hash is not None
        assert len(audit.evidence_hash) == 64  # SHA-256 hash
        assert CustomerAllocationAuditService.verify_audit_integrity(audit.id) is True

        # 4. التحقق من تحديث الفاتورة والمبلغ المدفوع
        sample_sale.refresh_from_db()
        assert sample_sale.amount_paid == Decimal('1000.00')
        assert sample_sale.amount_due == Decimal('0.00')
        assert sample_sale.payment_status == 'paid'

    def test_full_bounce_reverses_sale_allocation_and_reopens_invoice(
        self, sample_sale, sample_customer, test_user, financial_accounts
    ):
        """
        SCN-17 & SCN-22: ارتداد الشيك بالكامل يعكس تخصيص الفاتورة وسجل السداد ويعيد فتح الفاتورة:
        - تحويل ChequeInvoiceAllocation إلى REVERSED
        - تسجيل سجل تدقيق عكسي في CustomerAllocationAudit
        - تحويل SalePayment إلى reversed
        - إعادة فتح الفاتورة لتصبح unpaid
        """
        cheque = Cheque.objects.create(
            voucher_number='RV-P5-002',
            cheque_number='CHQ-77882',
            cheque_type=ChequeType.RECEIVABLE,
            purpose=ChequePurpose.INVOICE_SETTLEMENT,
            status=ChequeStatus.UNDER_COLLECTION,
            deposit_bank_account=financial_accounts['bank'],
            amount=Decimal('1000.00'),
            remaining_amount=Decimal('1000.00'),
            collected_amount=Decimal('0.00'),
            currency=financial_accounts['currency'],
            original_exchange_rate=Decimal('1.000000'),
            functional_amount=Decimal('1000.00'),
            book_value_functional=Decimal('1000.00'),
            customer=sample_customer,
            issue_date=timezone.now().date(),
            due_date=timezone.now().date(),
            created_by=test_user
        )

        # تخصيص الشيك على الفاتورة
        alloc = ChequeAllocationService.allocate_cheque_to_invoice(
            cheque=cheque,
            sale=sample_sale,
            amount=Decimal('1000.00'),
            user=test_user
        )
        sample_sale.refresh_from_db()
        assert sample_sale.amount_paid == Decimal('1000.00')
        assert sample_sale.payment_status == 'paid'

        # تنفيذ ارتداد الشيك
        res = ChequeAccountingService.bounce_cheque(
            cheque_id=cheque.id,
            user=test_user,
            idempotency_key='IDEM:P5:BOUNCE:002',
            bounce_reason='NO_FUNDS',
            rejection_advice_number='REJ-9988'
        )
        cheque.refresh_from_db()
        assert cheque.status == ChequeStatus.BOUNCED

        # التحقق من عكس التخصيص
        alloc.refresh_from_db()
        assert alloc.allocation_status == AllocationStatus.REVERSED

        # التحقق من تحويل SalePayment إلى reversed
        payment = SalePayment.objects.filter(sale=sample_sale, source_type='CHEQUE').first()
        assert payment.status == 'reversed'

        # التحقق من إنشاء سجل التدقيق العكسي
        rev_audit = CustomerAllocationAudit.objects.filter(
            target_document_number=sample_sale.number,
            allocation_status='REVERSED'
        ).first()
        assert rev_audit is not None
        assert rev_audit.reversed_audit is not None

        # التحقق من إعادة فتح الفاتورة
        sample_sale.refresh_from_db()
        assert sample_sale.amount_paid == Decimal('0.00')
        assert sample_sale.amount_due == Decimal('1000.00')
        assert sample_sale.payment_status == 'unpaid'

    def test_partial_collection_and_bounce_prorates_sale_allocation(
        self, sample_sale, sample_customer, test_user, financial_accounts
    ):
        """
        SCN-18: تحصيل جزئي ثم ارتداد المتبقي:
        - تخصيص 1000 ج.م
        - تحصيل جزئي 600 ج.م
        - ارتداد المتبقي 400 ج.م
        - تعديل مبلغ SalePayment ليقتصر على 600 ج.م وتحديث الفاتورة إلى partially_paid
        """
        cheque = Cheque.objects.create(
            voucher_number='RV-P5-003',
            cheque_number='CHQ-77883',
            cheque_type=ChequeType.RECEIVABLE,
            purpose=ChequePurpose.INVOICE_SETTLEMENT,
            status=ChequeStatus.UNDER_COLLECTION,
            deposit_bank_account=financial_accounts['bank'],
            amount=Decimal('1000.00'),
            remaining_amount=Decimal('1000.00'),
            collected_amount=Decimal('0.00'),
            currency=financial_accounts['currency'],
            original_exchange_rate=Decimal('1.000000'),
            functional_amount=Decimal('1000.00'),
            book_value_functional=Decimal('1000.00'),
            customer=sample_customer,
            issue_date=timezone.now().date(),
            due_date=timezone.now().date(),
            created_by=test_user
        )

        ChequeAllocationService.allocate_cheque_to_invoice(
            cheque=cheque,
            sale=sample_sale,
            amount=Decimal('1000.00'),
            user=test_user
        )

        # 1. تحصيل جزئي 600
        ChequeAccountingService.collect_cheque(
            cheque_id=cheque.id,
            user=test_user,
            idempotency_key='IDEM:P5:COLL:PARTIAL',
            collection_mode='PARTIAL',
            amount_collected=Decimal('600.00'),
            bank_account_id=financial_accounts['bank'].id
        )
        cheque.refresh_from_db()
        assert cheque.status == ChequeStatus.PARTIALLY_COLLECTED
        assert cheque.collected_amount == Decimal('600.00')

        # 2. ارتداد المتبقي (400)
        ChequeAccountingService.bounce_cheque(
            cheque_id=cheque.id,
            user=test_user,
            idempotency_key='IDEM:P5:BOUNCE:PARTIAL',
            bounce_reason='SIGNATURE_MISMATCH'
        )

        # التحقق من تعديل SalePayment إلى 600
        payment = SalePayment.objects.filter(sale=sample_sale, source_type='CHEQUE').first()
        assert payment.amount == Decimal('600.00')
        assert payment.status == 'posted'

        # التحقق من أن حالة الفاتورة مسددة جزئياً
        sample_sale.refresh_from_db()
        assert sample_sale.amount_paid == Decimal('600.00')
        assert sample_sale.amount_due == Decimal('400.00')
        assert sample_sale.payment_status == 'partially_paid'

    def test_manual_allocation_reversal(self, sample_sale, sample_customer, test_user, financial_accounts):
        """
        SCN-23: عكس التخصيص يدوياً:
        - التحقق من استدعاء ChequeAllocationService.reverse_cheque_allocation
        - التحقق من إعادة فتح الفاتورة وتحديث سجلات التدقيق
        """
        cheque = Cheque.objects.create(
            voucher_number='RV-P5-004',
            cheque_number='CHQ-77884',
            cheque_type=ChequeType.RECEIVABLE,
            purpose=ChequePurpose.INVOICE_SETTLEMENT,
            status=ChequeStatus.IN_PORTFOLIO,
            amount=Decimal('1000.00'),
            remaining_amount=Decimal('1000.00'),
            collected_amount=Decimal('0.00'),
            currency=financial_accounts['currency'],
            original_exchange_rate=Decimal('1.000000'),
            functional_amount=Decimal('1000.00'),
            book_value_functional=Decimal('1000.00'),
            customer=sample_customer,
            issue_date=timezone.now().date(),
            due_date=timezone.now().date(),
            created_by=test_user
        )

        alloc = ChequeAllocationService.allocate_cheque_to_invoice(
            cheque=cheque,
            sale=sample_sale,
            amount=Decimal('1000.00'),
            user=test_user
        )
        sample_sale.refresh_from_db()
        assert sample_sale.amount_paid == Decimal('1000.00')

        # عكس التخصيص يدوياً
        ChequeAllocationService.reverse_cheque_allocation(
            allocation=alloc,
            reason="طلب العميل استبدال طريقة السداد بنقدي",
            user=test_user
        )

        alloc.refresh_from_db()
        assert alloc.allocation_status == AllocationStatus.REVERSED

        payment = SalePayment.objects.filter(sale=sample_sale, source_type='CHEQUE').first()
        assert payment.status == 'reversed'

        sample_sale.refresh_from_db()
        assert sample_sale.amount_paid == Decimal('0.00')
        assert sample_sale.payment_status == 'unpaid'


@pytest.mark.django_db
class TestPhase5PostingDelegationAndOpeningBalance:
    """
    اختبارات تفويض الترحيل وشيكات الأرصدة الافتتاحية
    """

    def test_accounting_integration_posting_delegation(self, sample_sale, test_user, financial_accounts):
        """
        تفويض الترحيل المحاسبي لمنظومة الشيكات ومنع الازدواج في قيود الخزينة/البنك العامة
        عند استدعاء AccountingIntegrationService.create_payment_journal_entry مع طريقة الدفع check
        يجب أن تُرجع الخدمة None وتفوض الترحيل لـ cheques
        """
        # ضمان تفعيل موديول الشيكات
        SystemModule.objects.update_or_create(
            code='cheques',
            defaults={'name_ar': 'أوراق القبض والدفع', 'name_en': 'Cheques', 'is_enabled': True}
        )

        payment = SalePayment.objects.create(
            sale=sample_sale,
            amount=Decimal('500.00'),
            payment_date=timezone.now().date(),
            payment_method='check',
            source_type='CHEQUE',
            financial_account=None,
            reference_number='CHQ-DELEGATE-01',
            created_by=test_user,
            status='posted'
        )

        entry = AccountingIntegrationService.create_payment_journal_entry(
            payment=payment,
            payment_type='sale_payment',
            user=test_user
        )

        assert entry is None  # تم التفويض بالكامل لموديول cheques دون إنشاء قيود نقدية مكررة

    def test_opening_balance_cheque_zero_gl_entries(self, sample_customer, test_user, financial_accounts):
        """
        شيكات الأرصدة الافتتاحية المرتبطة بـ OpeningBalanceBatch لا تولد أي قيود أستاذ عام جديدة
        مع إتاحتها في الحافظة وإدارتها كأوراق قبض معتمدة
        """
        fy, _ = FiscalYear.objects.get_or_create(
            year_code='FY2026',
            defaults={
                'name': '2026',
                'start_date': timezone.now().date().replace(month=1, day=1),
                'end_date': timezone.now().date().replace(month=12, day=31),
                'status': 'open'
            }
        )
        batch = OpeningBalanceBatch.objects.create(
            fiscal_year=fy,
            batch_number='OB-2026-001',
            opening_date=timezone.now().date(),
            description="دفعة الأرصدة الافتتاحية للسنة المالية الجديدة",
            created_by=test_user,
            status='posted'
        )

        cheque = Cheque.objects.create(
            voucher_number='OB-CHQ-001',
            cheque_number='CHQ-OB-999',
            cheque_type=ChequeType.RECEIVABLE,
            purpose=ChequePurpose.INVOICE_SETTLEMENT,
            status=ChequeStatus.DRAFT,
            amount=Decimal('50000.00'),
            remaining_amount=Decimal('50000.00'),
            collected_amount=Decimal('0.00'),
            currency=financial_accounts['currency'],
            original_exchange_rate=Decimal('1.000000'),
            functional_amount=Decimal('50000.00'),
            book_value_functional=Decimal('50000.00'),
            customer=sample_customer,
            is_opening_balance=True,
            opening_batch=batch,
            issue_date=timezone.now().date(),
            due_date=timezone.now().date() + timezone.timedelta(days=30),
            created_by=test_user
        )

        # استلام الشيك
        res = ChequeAccountingService.receive_cheque(
            cheque_id=cheque.id,
            user=test_user,
            idempotency_key='IDEM:OB:RCV:001'
        )

        # التحقق من عدم توليد أي قيد أستاذ عام جديد
        assert res['journal_entry'] is None
        assert res['cheque'].status == ChequeStatus.IN_PORTFOLIO

        cheque.refresh_from_db()
        assert cheque.status == ChequeStatus.IN_PORTFOLIO
        assert cheque.is_opening_balance is True
        assert cheque.opening_batch == batch


@pytest.mark.django_db
class TestPhase5FeatureToggleAndDrainingMode:
    """
    SCN-38 & SCN-45: اختبارات حوكمة تفعيل وتعطيل موديول الشيكات ووضع التصفية التدريجي (Draining Mode)
    """

    def test_system_module_can_disable_blocked_by_active_cheques(self, sample_customer, test_user, financial_accounts):
        """
        SCN-38: لا يمكن تعطيل موديول الشيكات عبر SystemModule.can_disable() إذا كانت هناك شيكات نشطة
        """
        module, _ = SystemModule.objects.update_or_create(
            code='cheques',
            defaults={'name_ar': 'الشيكات وأوراق القبض', 'name_en': 'Cheques', 'is_enabled': True}
        )

        # إنشاء شيك نشط في الحافظة
        cheque = Cheque.objects.create(
            voucher_number='RV-TOGGLE-001',
            cheque_number='CHQ-ACT-1',
            cheque_type=ChequeType.RECEIVABLE,
            purpose=ChequePurpose.INVOICE_SETTLEMENT,
            status=ChequeStatus.IN_PORTFOLIO,
            amount=Decimal('5000.00'),
            remaining_amount=Decimal('5000.00'),
            collected_amount=Decimal('0.00'),
            currency=financial_accounts['currency'],
            original_exchange_rate=Decimal('1.000000'),
            functional_amount=Decimal('5000.00'),
            book_value_functional=Decimal('5000.00'),
            customer=sample_customer,
            issue_date=timezone.now().date(),
            due_date=timezone.now().date(),
            created_by=test_user
        )

        assert ChequeToggleService.get_active_cheques_count() > 0
        assert ChequeToggleService.can_disable_module() is False
        assert module.can_disable() is False

    def test_draining_mode_workflow_and_terminal_deactivation(self, sample_customer, test_user, financial_accounts):
        """
        SCN-45: دورة حياة وضع التصفية التدريجي (Draining Mode):
        1. طلب التعطيل مع وجود شيك نشط يؤدي إلى تفعيل وضع التصفية (Draining Mode)
        2. منع إنشاء شيكات جديدة أثناء وضع التصفية
        3. السماح بتحصيل أو تسوية الشيك القائم
        4. عند وصول عدد الشيكات النشطة إلى 0، ينجح التعطيل الكامل للموديول
        """
        module, _ = SystemModule.objects.update_or_create(
            code='cheques',
            defaults={'name_ar': 'الشيكات وأوراق القبض', 'name_en': 'Cheques', 'is_enabled': True}
        )

        cheque = Cheque.objects.create(
            voucher_number='RV-DRAIN-001',
            cheque_number='CHQ-DRN-1',
            cheque_type=ChequeType.RECEIVABLE,
            purpose=ChequePurpose.INVOICE_SETTLEMENT,
            status=ChequeStatus.UNDER_COLLECTION,
            deposit_bank_account=financial_accounts['bank'],
            amount=Decimal('2000.00'),
            remaining_amount=Decimal('2000.00'),
            collected_amount=Decimal('0.00'),
            currency=financial_accounts['currency'],
            original_exchange_rate=Decimal('1.000000'),
            functional_amount=Decimal('2000.00'),
            book_value_functional=Decimal('2000.00'),
            customer=sample_customer,
            issue_date=timezone.now().date(),
            due_date=timezone.now().date(),
            created_by=test_user
        )

        # 1. طلب تعطيل الموديول
        req_res = ChequeToggleService.request_disable(user=test_user)
        assert req_res['success'] is False
        assert req_res['draining'] is True
        assert req_res['active_count'] >= 1
        assert ChequeToggleService.is_draining() is True

        # 2. التحقق من منع إنشاء شيكات جديدة
        assert ChequeToggleService.can_create_new_cheques() is False

        # 3. استكمال دورة الشيك القائم بالتحصيل الكامل
        ChequeAccountingService.collect_cheque(
            cheque_id=cheque.id,
            user=test_user,
            idempotency_key='IDEM:P5:COLL:DRAIN',
            collection_mode='FULL',
            bank_account_id=financial_accounts['bank'].id
        )
        cheque.refresh_from_db()
        assert cheque.status == ChequeStatus.COLLECTED

        # 4. بعد وصول خط الأنابيب إلى صفر شيكات نشطة
        assert ChequeToggleService.get_active_cheques_count() == 0
        assert ChequeToggleService.can_disable_module() is True
        assert module.can_disable() is True

        # تنفيذ طلب التعطيل مجدداً
        final_res = ChequeToggleService.request_disable(user=test_user)
        assert final_res['success'] is True
        assert final_res['draining'] is False

        module.refresh_from_db()
        assert module.is_enabled is False
        assert ChequeToggleService.is_enabled() is False
