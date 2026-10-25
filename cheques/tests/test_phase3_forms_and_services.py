# -*- coding: utf-8 -*-
from decimal import Decimal
import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.enums.document_types import DocumentType
from core.services.sequence_service import SequenceService
from financial.models import (
    ChartOfAccounts,
    AccountType,
    Currency,
    AccountingPeriod,
    FiscalYear,
    UserTreasuryAccess,
)
from customer.models import Customer
from supplier.models import Supplier
from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
from financial.services.subledger_account_service import SubledgerAccountService
from financial.fx.models import FXRevaluationRun, FXRevaluationLine
from financial.fx.services.calculation import FXCalculationService
from financial.fx.services.posting import FXPostingService
from financial.fx.services.reversal import FXReversalService

from cheques.models import (
    Cheque,
    ChequeType,
    ChequePurpose,
    ChequeStatus,
    Checkbook,
    CheckbookLeaf,
    CheckbookLeafStatus,
    ChequeBatchDeposit,
    BatchDepositStatus,
    BankChequeLayout,
)
from cheques.services.batch_deposit_service import ChequeBatchDepositService
from cheques.services.accounting_service import ChequeAccountingService
from cheques.forms import (
    ChequeReceivableForm,
    ChequePayableForm,
    CheckbookForm,
    RuinedLeafReplacementForm,
    ChequeDepositActionForm,
    ChequeCollectActionForm,
    ChequeBounceActionForm,
    ChequeEndorseActionForm,
    ChequeReversalActionForm,
    ChequeConvertGuaranteeActionForm,
    ChequeBatchDepositForm,
    BankChequeLayoutForm,
)

User = get_user_model()


@pytest.fixture
def test_user(db):
    user = User.objects.filter(username='form_service_admin').first()
    if not user:
        user = User.objects.create_user(
            username='form_service_admin',
            email='form_admin@mwheba.com',
            password='Password123!',
            is_staff=True,
            is_superuser=True,
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
    usd, _ = Currency.objects.get_or_create(
        code='USD',
        defaults={'name': 'دولار أمريكي', 'symbol': '$', 'is_functional': False, 'is_active': True}
    )

    bank, _ = ChartOfAccounts.objects.get_or_create(
        code='11110',
        defaults={
            'name': 'البنك التجاري الدولي CIB',
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
            'name': 'أوراق القبض (شيكات بالخزينة)',
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
            'name': 'شيكات برسم التحصيل بالبنك',
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
    bank_exp, _ = ChartOfAccounts.objects.get_or_create(
        code='54100',
        defaults={
            'name': 'مصاريف وعمولات بنكية',
            'account_type': account_types['expense'],
            'level': 4,
            'is_leaf': True,
            'is_active': True,
            'currency': egp,
        }
    )
    vat_inp, _ = ChartOfAccounts.objects.get_or_create(
        code='11510',
        defaults={
            'name': 'ضريبة القيمة المضافة على المدخلات',
            'account_type': account_types['asset'],
            'level': 4,
            'is_leaf': True,
            'is_active': True,
            'currency': egp,
        }
    )
    fx_gain_loss, _ = ChartOfAccounts.objects.get_or_create(
        code='71020',
        defaults={
            'name': 'أرباح وخسائر فروق تقييم العملة غير المحققة',
            'account_type': account_types['revenue'],
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
        'bank_exp': bank_exp,
        'vat_inp': vat_inp,
        'fx_gain_loss': fx_gain_loss,
        'currency': egp,
        'usd': usd,
    }


@pytest.fixture
def sample_customer(db, financial_accounts):
    cust, _ = Customer.objects.get_or_create(
        name='مؤسسة الفجر للمقاولات',
        defaults={'code': 'CUST-FAJR-01', 'phone': '01099998888'}
    )
    SubledgerAccountService.get_or_create_customer_account(cust)
    cust.refresh_from_db()
    return cust


@pytest.fixture
def sample_supplier(db, financial_accounts):
    supp, _ = Supplier.objects.get_or_create(
        name='شركة السويس للأسمنت',
        defaults={'code': 'SUPP-SWZ-01'}
    )
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
class TestChequeReceivableFormValidation:
    """اختبارات نموذج استلام شيك قبض وقواعد التحقق والترقيم التلقائي"""

    def test_receivable_form_valid_and_auto_assigns_voucher(self, test_user, financial_accounts, sample_customer):
        """التحقق من صحة النموذج وتوليد رقم الإيصال الآلي عبر SequenceService"""
        today = timezone.localdate()
        data = {
            'cheque_number': 'RCV-99901',
            'purpose': ChequePurpose.INVOICE_SETTLEMENT,
            'amount': '25000.00',
            'currency': financial_accounts['currency'].id,
            'original_exchange_rate': '1.000000',
            'issue_date': str(today),
            'due_date': str(today),
            'drawer_bank_name': 'Banque Misr',
            'drawer_name': 'العميل محمد',
            'payee_name': 'موهبة',
            'customer': sample_customer.id,
        }
        form = ChequeReceivableForm(data=data, user=test_user)
        assert form.is_valid(), form.errors
        cheque = form.save()
        assert cheque.pk is not None
        assert cheque.cheque_type == ChequeType.RECEIVABLE
        assert cheque.status == ChequeStatus.DRAFT
        assert cheque.voucher_number.startswith('CHQR')

    def test_receivable_form_due_date_before_issue_date_rejected(self, test_user, financial_accounts, sample_customer):
        """رفض الشيك إذا كان تاريخ الاستحقاق سابقاً لتاريخ التحرير"""
        today = timezone.localdate()
        past = today - timezone.timedelta(days=5)
        data = {
            'cheque_number': 'RCV-99902',
            'purpose': ChequePurpose.INVOICE_SETTLEMENT,
            'amount': '15000.00',
            'currency': financial_accounts['currency'].id,
            'original_exchange_rate': '1.000000',
            'issue_date': str(today),
            'due_date': str(past),
            'drawer_bank_name': 'CIB',
            'drawer_name': 'العميل',
            'payee_name': 'موهبة',
            'customer': sample_customer.id,
        }
        form = ChequeReceivableForm(data=data, user=test_user)
        assert not form.is_valid()
        assert 'due_date' in form.errors

    def test_receivable_guarantee_requires_contract_reference(self, test_user, financial_accounts, sample_customer):
        """شيك الضمان يلزم وجود رقم العقد المرجعي"""
        today = timezone.localdate()
        data = {
            'cheque_number': 'RCV-GUAR-01',
            'purpose': ChequePurpose.SECURITY_GUARANTEE,
            'amount': '50000.00',
            'currency': financial_accounts['currency'].id,
            'original_exchange_rate': '1.000000',
            'issue_date': str(today),
            'due_date': str(today),
            'drawer_bank_name': 'NBE',
            'drawer_name': 'المقاول',
            'payee_name': 'موهبة',
            'customer': sample_customer.id,
            'is_guarantee': True,
            'notes': '',  # فارغ
        }
        form = ChequeReceivableForm(data=data, user=test_user)
        assert not form.is_valid()
        assert 'notes' in form.errors


@pytest.mark.django_db
class TestChequePayableFormValidation:
    """اختبارات نموذج إصدار شيك دفع وسحب الورقة من الدفتر وحدود الصرف"""

    def test_payable_form_valid_with_checkbook_leaf(self, test_user, financial_accounts, sample_supplier):
        """إصدار شيك دفع بسحب ورقة من دفتر متاح وتوليد رقم الإذن CHQP"""
        book = Checkbook.objects.create(
            bank_account=financial_accounts['bank'],
            name='BOOK-PAY-01',
            serial_prefix='EG',
            serial_from=1001,
            serial_to=1005,
            current_serial=1001,
            leaf_count=5,
            created_by=test_user,
        )
        leaf1 = book.leaves.get(serial_number='EG1001')

        today = timezone.localdate()
        data = {
            'checkbook': book.id,
            'checkbook_leaf': leaf1.id,
            'purpose': ChequePurpose.INVOICE_SETTLEMENT,
            'amount': '18000.00',
            'currency': financial_accounts['currency'].id,
            'original_exchange_rate': '1.000000',
            'issue_date': str(today),
            'due_date': str(today),
            'deposit_bank_account': financial_accounts['bank'].id,
            'drawer_bank_name': 'CIB',
            'payee_name': sample_supplier.name,
            'supplier': sample_supplier.id,
        }
        form = ChequePayableForm(data=data, user=test_user)
        assert form.is_valid(), form.errors
        cheque = form.save()
        assert cheque.cheque_type == ChequeType.PAYABLE
        assert cheque.cheque_number == 'EG1001'
        assert cheque.voucher_number.startswith('CHQP')

    def test_payable_form_exceeding_user_disbursement_limit_fails(self, financial_accounts, sample_supplier):
        """رفض إصدار شيك دفع يتجاوز السقف المصرح به للمستخدم"""
        limited_user = User.objects.create_user(
            username='limited_cashier',
            email='cashier@mwheba.com',
            password='Password123!'
        )
        UserTreasuryAccess.objects.create(
            user=limited_user,
            treasury=financial_accounts['bank'],
            can_disburse=True,
            max_single_disbursement_limit=Decimal('20000.00'),
            daily_disbursement_limit=Decimal('30000.00'),
        )

        today = timezone.localdate()
        data = {
            'cheque_number': 'MANUAL-555',
            'purpose': ChequePurpose.INVOICE_SETTLEMENT,
            'amount': '25000.00',  # يتجاوز سقف الـ 20,000
            'currency': financial_accounts['currency'].id,
            'original_exchange_rate': '1.000000',
            'issue_date': str(today),
            'due_date': str(today),
            'deposit_bank_account': financial_accounts['bank'].id,
            'drawer_bank_name': 'CIB',
            'payee_name': sample_supplier.name,
            'supplier': sample_supplier.id,
        }
        form = ChequePayableForm(data=data, user=limited_user)
        assert not form.is_valid()
        assert 'amount' in form.errors


@pytest.mark.django_db
class TestCheckbookFormValidation:
    """اختبارات نموذج إنشاء دفتر شيكات ومنع تداخل الأرقام"""

    def test_checkbook_create_form_atomic_leaf_generation(self, test_user, financial_accounts):
        """إنشاء الدفتر بنجاح وتوليد الأوراق"""
        data = {
            'bank_account': financial_accounts['bank'].id,
            'name': 'BK-CIB-2026-01',
            'serial_prefix': 'CB',
            'serial_from': 501,
            'serial_to': 510,
        }
        form = CheckbookForm(data=data, user=test_user)
        assert form.is_valid(), form.errors
        book = form.save()
        assert book.pk is not None
        assert book.leaves.count() == 10
        assert book.leaves.first().serial_number == 'CB501'

    def test_checkbook_overlapping_serial_rejected(self, test_user, financial_accounts):
        """رفض إنشاء دفتر يتداخل في السيريال لنفس الحساب والبادئة"""
        Checkbook.objects.create(
            bank_account=financial_accounts['bank'],
            name='BK-EX-01',
            serial_prefix='CB',
            serial_from=100,
            serial_to=200,
            current_serial=100,
            leaf_count=101,
            is_active=True,
            created_by=test_user,
        )

        data = {
            'bank_account': financial_accounts['bank'].id,
            'name': 'BK-EX-02',
            'serial_prefix': 'CB',
            'serial_from': 150,  # تداخل
            'serial_to': 250,
        }
        form = CheckbookForm(data=data, user=test_user)
        assert not form.is_valid()
        assert any('تداخل' in str(err) or 'overlap' in str(err).lower() for err in form.non_field_errors())


@pytest.mark.django_db
class TestChequeBatchDepositServiceAndForm:
    """اختبارات حافظة إيداع الشيكات المجمعة ChequeBatchDepositService و ChequeBatchDepositForm"""

    def test_create_and_deposit_batch_service_lifecycle(self, test_user, financial_accounts, sample_customer):
        """إنشاء الحافظة وإيداع شيكين ذرياً وتغيير حالتهما إلى برسم التحصيل"""
        today = timezone.localdate()
        chq1 = Cheque.objects.create(
            voucher_number='CHQR-B1-01',
            cheque_type=ChequeType.RECEIVABLE,
            purpose=ChequePurpose.INVOICE_SETTLEMENT,
            status=ChequeStatus.IN_PORTFOLIO,
            cheque_number='BATCH-CHQ-1',
            amount=Decimal('10000.00'),
            currency=financial_accounts['currency'],
            original_exchange_rate=Decimal('1.000000'),
            issue_date=today,
            due_date=today,
            drawer_bank_name='CIB',
            drawer_name='العميل 1',
            payee_name='موهبة',
            customer=sample_customer,
            created_by=test_user,
        )
        chq2 = Cheque.objects.create(
            voucher_number='CHQR-B1-02',
            cheque_type=ChequeType.RECEIVABLE,
            purpose=ChequePurpose.INVOICE_SETTLEMENT,
            status=ChequeStatus.IN_PORTFOLIO,
            cheque_number='BATCH-CHQ-2',
            amount=Decimal('15000.00'),
            currency=financial_accounts['currency'],
            original_exchange_rate=Decimal('1.000000'),
            issue_date=today,
            due_date=today,
            drawer_bank_name='NBE',
            drawer_name='العميل 2',
            payee_name='موهبة',
            customer=sample_customer,
            created_by=test_user,
        )

        batch = ChequeBatchDepositService.create_and_deposit_batch(
            bank_account_id=financial_accounts['bank'].id,
            cheque_ids=[chq1.id, chq2.id],
            user=test_user,
            deposit_date=today,
            notes='حافظة إيداع اليوم'
        )

        assert batch.batch_number.startswith('CHQB')
        assert batch.status == BatchDepositStatus.DEPOSITED
        assert batch.total_amount == Decimal('25000.00')

        # التحقق من أن الشيكات انتقلت لحالة برسم التحصيل وتولد لها قيود إيداع
        chq1.refresh_from_db()
        chq2.refresh_from_db()
        assert chq1.status == ChequeStatus.UNDER_COLLECTION
        assert chq2.status == ChequeStatus.UNDER_COLLECTION

        # تحصيل شيك 1 ومزامنة حالة الحافظة
        ChequeAccountingService.collect_cheque(
            cheque_id=chq1.id,
            user=test_user,
            idempotency_key='COLLECT-B1-01',
            amount_collected=Decimal('10000.00')
        )
        st = ChequeBatchDepositService.sync_batch_status(batch)
        assert st == BatchDepositStatus.PARTIALLY_CLEARED

        # تحصيل شيك 2 -> يجب أن تصبح الحافظة مغلقة بالكامل CLOSED
        ChequeAccountingService.collect_cheque(
            cheque_id=chq2.id,
            user=test_user,
            idempotency_key='COLLECT-B1-02',
            amount_collected=Decimal('15000.00')
        )
        st2 = ChequeBatchDepositService.sync_batch_status(batch)
        assert st2 == BatchDepositStatus.CLOSED


@pytest.mark.django_db
class TestFXRevaluationChequeIntegration:
    """اختبارات تقييم أوراق القبض والدفع بالعملات الأجنبية كـ Monetary Items وتحديث القيمة الدفترية وفق IAS 21"""

    def test_foreign_cheque_evaluated_in_fx_run_and_book_value_updated(self, test_user, financial_accounts, sample_customer):
        """تقييم شيك قبض بالدولار وترحيل القيد وتحديث book_value_functional ثم إعادة ضبطها عند العكس"""
        today = timezone.localdate()
        usd = financial_accounts['usd']

        # 1. إنشاء سنة وفترة مالية مفتوحة
        year, _ = FiscalYear.objects.get_or_create(
            name='FY-2026',
            defaults={'start_date': today, 'end_date': today, 'status': 'open'}
        )
        period, _ = AccountingPeriod.objects.get_or_create(
            name='Period-10-2026',
            defaults={
                'fiscal_year': year,
                'period_number': 10,
                'start_date': today,
                'end_date': today,
                'status': 'open',
            }
        )

        # 2. إنشاء شيك قبض بـ 1,000 USD بسعر صرف 48.00
        cheque = Cheque.objects.create(
            voucher_number='CHQR-USD-001',
            cheque_type=ChequeType.RECEIVABLE,
            purpose=ChequePurpose.INVOICE_SETTLEMENT,
            status=ChequeStatus.IN_PORTFOLIO,
            cheque_number='US-CHQ-101',
            amount=Decimal('1000.00'),
            currency=usd,
            original_exchange_rate=Decimal('48.000000'),
            functional_amount=Decimal('48000.00'),
            book_value_functional=Decimal('48000.00'),
            remaining_amount=Decimal('1000.00'),
            remaining_functional=Decimal('48000.00'),
            issue_date=today,
            due_date=today,
            drawer_bank_name='Chase Bank',
            drawer_name='عميل أمريكي',
            payee_name='موهبة',
            customer=sample_customer,
            created_by=test_user,
        )

        # 3. إعداد سعر الصرف الجديد (50.00)
        from financial.models import ExchangeRate
        ExchangeRate.objects.create(
            from_currency=usd,
            to_currency=financial_accounts['currency'],
            rate=Decimal('50.000000'),
            effective_date=today,
            source='CBE'
        )

        # 4. تشغيل حساب تقييم فروق العملة
        run = FXCalculationService.calculate_and_create_run(
            period=period,
            user=test_user,
            currency_scope='ALL_CURRENCIES'
        )
        assert run.status == 'CALCULATED'

        # التحقق من وجود سطر التقييم لشيك القبض
        line = run.lines.filter(source_type='NOTES_RECEIVABLE', source_id=str(cheque.id)).first()
        assert line is not None
        assert line.open_foreign_amount == Decimal('1000.0000')
        assert line.old_rate == Decimal('48.000000')
        assert line.new_rate == Decimal('50.000000')
        # فرق موجب (أرباح غير محققة) = 2,000 ج.م
        assert line.unrealized_difference == Decimal('2000.00')

        # 5. ترحيل تشغيل التقييم -> يجب تحديث القيمة الدفترية للشيك
        FXPostingService.post_run(run, user=test_user)
        cheque.refresh_from_db()
        assert cheque.book_value_functional == Decimal('50000.00')
        assert cheque.remaining_functional == Decimal('50000.00')

        # 6. عكس تشغيل التقييم (Day-1 Reversal) -> يجب إعادة ضبط القيمة الدفترية للشيك لتكلفتها التاريخية (48,000)
        FXReversalService.reverse_run(run, user=test_user, reason='عكس دوري بداية الفترة التالية')
        cheque.refresh_from_db()
        assert cheque.book_value_functional == Decimal('48000.00')
        assert cheque.remaining_functional == Decimal('48000.00')
