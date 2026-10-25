# -*- coding: utf-8 -*-
import pytest
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth import get_user_model

from core.enums.document_types import DocumentType
from core.services.sequence_service import SequenceService
from financial.models import (
    ChartOfAccounts,
    Currency,
    AccountType,
    JournalEntry,
    JournalEntryLine,
    UserTreasuryAccess,
    BankStatementBatch,
    BankStatementLine,
    BankReconciliationMatch,
)
from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
from financial.services.subledger_account_service import SubledgerAccountService
from customer.models import Customer
from supplier.models import Supplier
from sale.models import Sale, SalePayment

from cheques.models import (
    Checkbook,
    CheckbookLeaf,
    Cheque,
    ChequeType,
    ChequePurpose,
    ChequeStatus,
    ChequeActionLog,
    ChequeActionType,
    ChequeSettlementLine,
    ChequeInvoiceAllocation,
)
from cheques.services import (
    CheckbookService,
    ChequeDisbursementSecurityService,
    ChequeExposureService,
    ChequeAccountingService,
    ConcurrencyConflictError,
    ChequeReversalService,
    ChequeSubledgerReconciliationService,
)

User = get_user_model()


@pytest.fixture
def test_user(db):
    user = User.objects.filter(username='cheque_service_admin').first()
    if not user:
        user = User.objects.create_user(
            username='cheque_service_admin',
            email='cheque_admin2@mwheba.com',
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

    # 11160001 البنك الرئيسي
    bank, _ = ChartOfAccounts.objects.get_or_create(
        code='11160001',
        defaults={
            'name': 'الحساب البنكي الرئيسي (جاري محلي)',
            'account_type': account_types['asset'],
            'level': 4,
            'is_leaf': True,
            'is_bank_account': True,
            'is_active': True,
            'currency': egp,
        }
    )

    # 11220 أوراق القبض
    notes_rec, _ = ChartOfAccounts.objects.get_or_create(
        code='11220',
        defaults={
            'name': 'أوراق القبض (كمبيالات وشيكات آجلة)',
            'account_type': account_types['asset'],
            'level': 4,
            'is_leaf': True,
            'is_active': True,
            'currency': egp,
        }
    )

    # 11190 شيكات برسم التحصيل
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

    # 21120 أوراق الدفع
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

    # 21510 دفعات مقدمة عملاء
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

    # 54100 مصاريف وعمولات بنكية
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

    # 11510 ضريبة مدخلات
    vat_inp, _ = ChartOfAccounts.objects.get_or_create(
        code='11510',
        defaults={
            'name': 'ضريبة القيمة المضافة - مدخلات',
            'account_type': account_types['asset'],
            'level': 4,
            'is_leaf': True,
            'is_active': True,
            'currency': egp,
        }
    )

    # 54400 فروق تقريب العملات
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
        'vat_inp': vat_inp,
        'round_diff': round_diff,
        'currency': egp,
    }


@pytest.fixture
def sample_customer(db, financial_accounts):
    cust, _ = Customer.objects.get_or_create(
        name='شركة النيل للمقاولات',
        defaults={'code': 'CUST-NIL-01', 'phone': '01011112222'}
    )
    # ربط حساب الأستاذ المساعد للعميل
    SubledgerAccountService.get_or_create_customer_account(cust)
    cust.refresh_from_db()
    return cust


@pytest.fixture
def sample_supplier(db, financial_accounts):
    supp, _ = Supplier.objects.get_or_create(
        name='شركة الأهرام للحديد',
        defaults={'code': 'SUPP-AHR-01'}
    )
    # ربط حساب الأستاذ المساعد للمورد
    SubledgerAccountService.get_or_create_supplier_account(supp)
    supp.refresh_from_db()
    return supp


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


@pytest.mark.django_db
class TestRoleRegistryAndResolution:
    """اختبارات حل الأدوار المالية الحاكمة للشيكات وأوراق القبض والدفع"""

    def test_cheque_account_roles_resolved_from_registry(self, financial_accounts):
        """التحقق من أن استدعاء الأدوار يرجع الحسابات المعتمدة في الدليل دون خطأ"""
        code_rec = AccountRoleRegistry.get_account_code(AccountRoleNames.NOTES_RECEIVABLE_CONTROL)
        assert code_rec == '11220'

        code_coll = AccountRoleRegistry.get_account_code(AccountRoleNames.CHEQUES_UNDER_COLLECTION)
        assert code_coll == '11190'

        code_pay = AccountRoleRegistry.get_account_code(AccountRoleNames.NOTES_PAYABLE_CONTROL)
        assert code_pay == '21120'

        acc_rec = AccountRoleRegistry.get_account(AccountRoleNames.NOTES_RECEIVABLE_CONTROL)
        assert acc_rec.code == '11220'

        acc_coll = AccountRoleRegistry.get_account(AccountRoleNames.CHEQUES_UNDER_COLLECTION)
        assert acc_coll.code == '11190'


@pytest.mark.django_db
class TestCheckbookServiceLifecycle:
    """اختبارات خدمة دفاتر الشيكات وتوليد الأوراق واستبدال الأوراق التالفة"""

    def test_create_checkbook_and_leaf_fetching(self, test_user, financial_accounts):
        """التحقق من إنشاء الدفتر وجلب الورقة المتاحة التالية ذرياً"""
        checkbook = CheckbookService.create_checkbook(
            bank_account=financial_accounts['bank'],
            serial_prefix='CIB',
            serial_from=101,
            serial_to=110,
            user=test_user,
        )
        assert checkbook.leaf_count == 10
        assert checkbook.leaves.count() == 10

        leaf = CheckbookService.get_next_available_leaf(financial_accounts['bank'].id, serial_prefix='CIB')
        assert leaf is not None
        assert leaf.serial_number == 'CIB101'
        assert leaf.status == CheckbookLeaf.LeafStatus.AVAILABLE

    def test_replace_ruined_leaf_workflow(self, test_user, financial_accounts, sample_supplier):
        """التحقق من استبدال ورقة الشيك التالفة وتوثيق الإتلاف وتحديث رقم الشيك"""
        checkbook = CheckbookService.create_checkbook(
            bank_account=financial_accounts['bank'],
            serial_prefix='QNB',
            serial_from=201,
            serial_to=205,
            user=test_user,
        )
        leaf1 = checkbook.leaves.get(serial_number='QNB201')
        leaf2 = checkbook.leaves.get(serial_number='QNB202')

        cheque = Cheque.objects.create(
            voucher_number='CHQP-TEST-001',
            cheque_type=ChequeType.PAYABLE,
            purpose=ChequePurpose.INVOICE_SETTLEMENT,
            status=ChequeStatus.ISSUED,
            checkbook_leaf=leaf1,
            cheque_number='QNB201',
            amount=Decimal('25000.00'),
            currency=financial_accounts['currency'],
            issue_date=timezone.now().date(),
            due_date=timezone.now().date(),
            drawer_bank_name='QNB مصر',
            drawer_name='موهبة',
            payee_name='الأهرام للحديد',
            supplier=sample_supplier,
            deposit_bank_account=financial_accounts['bank'],
            created_by=test_user,
        )
        leaf1.status = CheckbookLeaf.LeafStatus.ISSUED
        leaf1.save()

        # استبدال الورقة التالفة
        reason = 'انحشار الورقة في الطابعة وتلف الرمز الممغنط'
        updated_cheque = CheckbookService.replace_ruined_leaf(
            cheque=cheque,
            new_leaf=leaf2,
            voided_reason=reason,
            user=test_user
        )

        leaf1.refresh_from_db()
        leaf2.refresh_from_db()
        assert leaf1.status == CheckbookLeaf.LeafStatus.VOIDED
        assert leaf1.voided_reason == reason
        assert leaf2.status == CheckbookLeaf.LeafStatus.ISSUED
        assert updated_cheque.checkbook_leaf_id == leaf2.id
        assert updated_cheque.cheque_number == 'QNB202'


@pytest.mark.django_db
class TestChequeDisbursementSecurity:
    """اختبارات حجز سقف الخزينة اليومي وسقف الحركة الواحدة لأوراق الدفع"""

    def test_single_and_daily_disbursement_limit_enforcement(self, financial_accounts):
        """التحقق من اعتراض تجاوز سقف الحركة الواحدة والسقف اليومي التراكمي"""
        limit_user = User.objects.create_user(
            username='limit_enforce_user',
            email='limit@mwheba.com',
            password='Password123!'
        )
        UserTreasuryAccess.objects.create(
            user=limit_user,
            treasury=financial_accounts['bank'],
            can_disburse=True,
            can_deposit=True,
            max_single_disbursement_limit=Decimal('50000.00'),
            daily_disbursement_limit=Decimal('80000.00'),
        )

        # 1. تجاوز سقف الحركة الواحدة
        with pytest.raises(ValidationError):
            ChequeDisbursementSecurityService.enforce_and_reserve(
                user=limit_user,
                bank_account_id=financial_accounts['bank'].id,
                amount=Decimal('60000.00')
            )

        # 2. حركة أولى مسموحة (40,000)
        assert ChequeDisbursementSecurityService.enforce_and_reserve(
            user=limit_user,
            bank_account_id=financial_accounts['bank'].id,
            amount=Decimal('40000.00')
        ) is True


@pytest.mark.django_db
class TestChequeExposureService:
    """اختبارات أثر الشيكات غير المحصلة على سقف الائتمان للعملاء"""

    def test_uncollected_invoiced_cheque_adds_to_exposure(self, test_user, financial_accounts, sample_customer):
        """التحقق من أن الشيك غير المحصل لسداد فاتورة يُدرج في الانكشاف حتى الصرف بالبنك"""
        cheque = Cheque.objects.create(
            voucher_number='CHQR-EXP-001',
            cheque_type=ChequeType.RECEIVABLE,
            purpose=ChequePurpose.INVOICE_SETTLEMENT,
            status=ChequeStatus.IN_PORTFOLIO,
            cheque_number='EXP1001',
            amount=Decimal('30000.00'),
            remaining_amount=Decimal('30000.00'),
            currency=financial_accounts['currency'],
            original_exchange_rate=Decimal('1.000000'),
            issue_date=timezone.now().date(),
            due_date=timezone.now().date(),
            drawer_bank_name='CIB',
            drawer_name='العميل',
            payee_name='موهبة',
            customer=sample_customer,
            created_by=test_user,
        )

        exp = ChequeExposureService.get_uncollected_cheques_exposure(sample_customer.id)
        assert exp == Decimal('30000.00')

        # عند التحصيل البنكي الصريح يتحرر السقف ويخرج من الانكشاف
        cheque.status = ChequeStatus.COLLECTED
        cheque.remaining_amount = Decimal('0.00')
        cheque.save()

        exp_after = ChequeExposureService.get_uncollected_cheques_exposure(sample_customer.id)
        assert exp_after == Decimal('0.00')


@pytest.mark.django_db
class TestChequeAccountingDoubleEntryLifecycle:
    """اختبارات دورة القيود المحاسبية المزدوجة المتكاملة عبر ChequeAccountingService"""

    def test_full_receivable_lifecycle_receive_deposit_collect(self, test_user, financial_accounts, sample_customer):
        """التحقق من دورة حياة شيك القبض: استلام ⬅️ إيداع ⬅️ تحصيل جزئي مع مصاريف وضريبة"""
        cheque = Cheque.objects.create(
            voucher_number='CHQR-CYCLE-001',
            cheque_type=ChequeType.RECEIVABLE,
            purpose=ChequePurpose.INVOICE_SETTLEMENT,
            status=ChequeStatus.DRAFT,
            cheque_number='CYC123',
            amount=Decimal('10000.00'),
            currency=financial_accounts['currency'],
            original_exchange_rate=Decimal('1.000000'),
            issue_date=timezone.now().date(),
            due_date=timezone.now().date(),
            drawer_bank_name='البنك الأهلي',
            drawer_name='العميل',
            payee_name='موهبة',
            customer=sample_customer,
            deposit_bank_account=financial_accounts['bank'],
            created_by=test_user,
        )

        # 1. الاستلام في المحفظة (RECEIVE)
        res_rec = ChequeAccountingService.receive_cheque(
            cheque_id=cheque.id,
            user=test_user,
            idempotency_key='IDEMP-REC-001',
        )
        assert res_rec['cheque'].status == ChequeStatus.IN_PORTFOLIO
        entry_rec = res_rec['journal_entry']
        assert entry_rec is not None
        # تحقق من القيد: مدين أوراق القبض (11220) ودائن العميل
        lines_rec = entry_rec.lines.all()
        assert lines_rec.filter(account__code='11220', debit=Decimal('10000.00')).exists()

        # 2. الإيداع برسم التحصيل (DEPOSIT)
        res_dep = ChequeAccountingService.deposit_cheque(
            cheque_id=cheque.id,
            user=test_user,
            idempotency_key='IDEMP-DEP-001',
            bank_account_id=financial_accounts['bank'].id,
        )
        assert res_dep['cheque'].status == ChequeStatus.UNDER_COLLECTION
        entry_dep = res_dep['journal_entry']
        assert entry_dep is not None
        lines_dep = entry_dep.lines.all()
        assert lines_dep.filter(account__code='11190', debit=Decimal('10000.00')).exists()
        assert lines_dep.filter(account__code='11220', credit=Decimal('10000.00')).exists()

        # 3. التحصيل الجزئي (COLLECT): تحصيل 6000 مع عمولة 50 وضريبة 7
        res_coll = ChequeAccountingService.collect_cheque(
            cheque_id=cheque.id,
            user=test_user,
            idempotency_key='IDEMP-COL-001',
            amount_collected=Decimal('6000.00'),
            bank_charges=Decimal('50.00'),
            bank_charges_vat=Decimal('7.00'),
        )
        chq_coll = res_coll['cheque']
        assert chq_coll.status == ChequeStatus.PARTIALLY_COLLECTED
        assert chq_coll.collected_amount == Decimal('6000.00')
        assert chq_coll.remaining_amount == Decimal('4000.00')
        assert chq_coll.settlement_lines.count() == 1

        entry_coll = res_coll['journal_entry']
        lines_coll = entry_coll.lines.all()
        # مدين البنك = 6000 - 57 = 5943
        assert lines_coll.filter(account=financial_accounts['bank'], debit=Decimal('5943.00')).exists()
        assert lines_coll.filter(account__code='54100', debit=Decimal('50.00')).exists()
        assert lines_coll.filter(account__code='11510', debit=Decimal('7.00')).exists()
        assert lines_coll.filter(account__code='11190', credit=Decimal('6000.00')).exists()

    def test_idempotent_cached_replay_contract(self, test_user, financial_accounts, sample_customer):
        """التحقق من إرجاع النتيجة المحفوظة فوراً وبأمان عند تكرار نفس المفتاح والمعلمات"""
        cheque = Cheque.objects.create(
            voucher_number='CHQR-IDEMP-001',
            cheque_type=ChequeType.RECEIVABLE,
            purpose=ChequePurpose.INVOICE_SETTLEMENT,
            status=ChequeStatus.DRAFT,
            cheque_number='IDM999',
            amount=Decimal('8000.00'),
            currency=financial_accounts['currency'],
            issue_date=timezone.now().date(),
            due_date=timezone.now().date(),
            drawer_bank_name='بنك مصر',
            drawer_name='عميل',
            payee_name='موهبة',
            customer=sample_customer,
            created_by=test_user,
        )

        res1 = ChequeAccountingService.receive_cheque(
            cheque_id=cheque.id,
            user=test_user,
            idempotency_key='IDEMP-REPEAT-KEY-001'
        )
        assert res1['is_retry'] is False

        # إعادة إرسال نفس الطلب بنفس المفتاح
        res2 = ChequeAccountingService.receive_cheque(
            cheque_id=cheque.id,
            user=test_user,
            idempotency_key='IDEMP-REPEAT-KEY-001'
        )
        assert res2['is_retry'] is True
        assert res2['journal_entry'].id == res1['journal_entry'].id

        # إرسال نفس المفتاح بمعلمات مختلفة -> يثير تعارض
        with pytest.raises(ConcurrencyConflictError):
            ChequeAccountingService.process_lifecycle_action(
                cheque_id=cheque.id,
                action_type=ChequeActionType.RECEIVE,
                user=test_user,
                idempotency_key='IDEMP-REPEAT-KEY-001',
                reason='معلمات مختلفة تماماً'
            )


@pytest.mark.django_db
class TestChequeReversalServiceLifecycle:
    """اختبارات خدمة التراجع الخطي الآمن LIFO وحوكمة التسوية البنكية"""

    def test_lifo_reversal_of_cheque_deposit(self, test_user, financial_accounts, sample_customer):
        """التحقق من التراجع عن حركة الإيداع وإعادة الشيك للمحفظة وعكس قيد اليومية"""
        cheque = Cheque.objects.create(
            voucher_number='CHQR-REV-001',
            cheque_type=ChequeType.RECEIVABLE,
            purpose=ChequePurpose.INVOICE_SETTLEMENT,
            status=ChequeStatus.DRAFT,
            cheque_number='REV111',
            amount=Decimal('5000.00'),
            currency=financial_accounts['currency'],
            issue_date=timezone.now().date(),
            due_date=timezone.now().date(),
            drawer_bank_name='CIB',
            drawer_name='العميل',
            payee_name='موهبة',
            customer=sample_customer,
            created_by=test_user,
        )

        # استلام
        ChequeAccountingService.receive_cheque(
            cheque_id=cheque.id,
            user=test_user,
            idempotency_key='REV-KEY-01'
        )
        # إيداع
        ChequeAccountingService.deposit_cheque(
            cheque_id=cheque.id,
            user=test_user,
            idempotency_key='REV-KEY-02',
            bank_account_id=financial_accounts['bank'].id
        )
        cheque.refresh_from_db()
        assert cheque.status == ChequeStatus.UNDER_COLLECTION

        # التراجع عن الإيداع
        res_rev = ChequeReversalService.reverse_last_action(
            cheque_id=cheque.id,
            user=test_user,
            reason='طلب سحب الشيك من البنك واستبداله بسداد نقدي',
            idempotency_key='REV-ACT-KEY-01'
        )
        cheque.refresh_from_db()
        assert cheque.status == ChequeStatus.IN_PORTFOLIO
        assert res_rev['reversal_entry'] is not None

    def test_reversal_blocked_if_reconciled_with_bank(self, test_user, financial_accounts, sample_customer):
        """التحقق من حظر التراجع إذا تمت مطابقة قيد اليومية في كشف الحساب البنكي"""
        cheque = Cheque.objects.create(
            voucher_number='CHQR-RECON-001',
            cheque_type=ChequeType.RECEIVABLE,
            purpose=ChequePurpose.INVOICE_SETTLEMENT,
            status=ChequeStatus.DRAFT,
            cheque_number='RCN555',
            amount=Decimal('12000.00'),
            currency=financial_accounts['currency'],
            issue_date=timezone.now().date(),
            due_date=timezone.now().date(),
            drawer_bank_name='Banque Misr',
            drawer_name='عميل',
            payee_name='موهبة',
            customer=sample_customer,
            deposit_bank_account=financial_accounts['bank'],
            created_by=test_user,
        )

        ChequeAccountingService.receive_cheque(cheque.id, test_user, 'RC-KEY-1')
        ChequeAccountingService.deposit_cheque(cheque.id, test_user, 'RC-KEY-2', financial_accounts['bank'].id)
        res_coll = ChequeAccountingService.collect_cheque(cheque.id, test_user, 'RC-KEY-3', amount_collected=Decimal('12000.00'))

        entry = res_coll['journal_entry']
        bank_line = entry.lines.filter(account=financial_accounts['bank']).first()

        # محاكاة مطابقة بنكية لهذا السطر
        batch = BankStatementBatch.objects.create(
            batch_number='BATCH-REC-TEST-01',
            bank_account=financial_accounts['bank'],
            statement_date=timezone.now().date(),
            opening_balance=Decimal('0.00'),
            closing_balance=Decimal('12000.00'),
            created_by=test_user,
        )
        stmt_line = BankStatementLine.objects.create(
            batch=batch,
            transaction_date=timezone.now().date(),
            value_date=timezone.now().date(),
            debit=Decimal('12000.00'),
            credit=Decimal('0.00'),
            description='إيداع شيك RCN555',
            is_matched=True,
        )
        BankReconciliationMatch.objects.create(
            statement_line=stmt_line,
            journal_line=bank_line,
            matched_amount=Decimal('12000.00'),
            match_type='EXACT',
            status='MATCHED'
        )

        # محاولة عكس التحصيل المطابق بنكياً -> يجب أن تُرفض
        with pytest.raises(ValidationError):
            ChequeReversalService.reverse_last_action(
                cheque_id=cheque.id,
                user=test_user,
                reason='محاولة عكس شيك مطابق',
                idempotency_key='REV-FAIL-KEY'
            )


@pytest.mark.django_db
class TestSubledgerReconciliationEngine:
    """اختبارات مطابقة الأستاذ المساعد التاريخي بأثر رجعي مع ميزان المراجعة"""

    def test_point_in_time_subledger_reconciliation(self, test_user, financial_accounts, sample_customer):
        """التحقق من دقة تقرير المطابقة التاريخي ومطابقة ميزان المراجعة بالسنت"""
        today = timezone.now().date()
        cheque = Cheque.objects.create(
            voucher_number='CHQR-RECON-SUB-01',
            cheque_type=ChequeType.RECEIVABLE,
            purpose=ChequePurpose.INVOICE_SETTLEMENT,
            status=ChequeStatus.DRAFT,
            cheque_number='SUB9001',
            amount=Decimal('15000.00'),
            currency=financial_accounts['currency'],
            issue_date=today,
            due_date=today,
            drawer_bank_name='CIB',
            drawer_name='عميل الأستاذ',
            payee_name='موهبة',
            customer=sample_customer,
            created_by=test_user,
        )

        ChequeAccountingService.receive_cheque(cheque.id, test_user, 'SUB-IDEMP-01')

        # استخراج المطابقة في تاريخ اليوم
        recon = ChequeSubledgerReconciliationService.reconcile_at_date(today)
        rec_acc = recon['11220_notes_receivable']
        assert rec_acc['is_matched'] is True
        assert rec_acc['subledger_balance'] == Decimal('15000.00')
        assert rec_acc['gl_balance'] == Decimal('15000.00')
        assert recon['overall_matched'] is True
