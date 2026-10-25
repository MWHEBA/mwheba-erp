# -*- coding: utf-8 -*-
import pytest
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model

from financial.models import (
    ChartOfAccounts,
    Currency,
    AccountType,
    JournalEntry,
    JournalEntryLine,
    CostCenter,
)
from financial.services.subledger_account_service import SubledgerAccountService
from financial.services.accounting_integration_service import AccountingIntegrationService
from customer.models import Customer
from supplier.models import Supplier
from sale.models import Sale, SalePayment

import datetime

from cheques.models import (
    Cheque,
    ChequeType,
    ChequePurpose,
    ChequeStatus,
    ChequeActionLog,
    ChequeActionType,
    ChequeInvoiceAllocation,
    ChequeSettlementLine,
)
from cheques.services import (
    ChequeAccountingService,
    ChequeReversalService,
    ChequeAllocationService,
)

User = get_user_model()


@pytest.fixture
def test_user(db):
    user = User.objects.filter(username='p1_fix_admin').first()
    if not user:
        user = User.objects.create_superuser(
            username='p1_fix_admin',
            email='p1_fix@mwheba.com',
            password='Password123!'
        )
    user.is_superuser = True
    user.is_staff = True
    user.save()
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
            'name': 'الحساب البنكي الرئيسي',
            'account_type': account_types['asset'],
            'level': 4,
            'is_leaf': True,
            'is_bank_account': True,
            'is_active': True,
            'currency': egp,
        }
    )

    notes_rec, _ = ChartOfAccounts.objects.get_or_create(
        code='11220',
        defaults={
            'name': 'أوراق القبض',
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
            'name': 'شيكات برسم التحصيل',
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
            'name': 'أوراق الدفع',
            'account_type': account_types['liability'],
            'level': 4,
            'is_leaf': True,
            'is_active': True,
            'currency': egp,
        }
    )

    cust_control, _ = ChartOfAccounts.objects.get_or_create(
        code='11210',
        defaults={
            'name': 'العملاء (حساب رقابي)',
            'account_type': account_types['asset'],
            'level': 3,
            'is_control_account': True,
            'is_leaf': False,
            'is_active': True,
            'currency': egp,
        }
    )

    supp_control, _ = ChartOfAccounts.objects.get_or_create(
        code='21110',
        defaults={
            'name': 'الموردون (حساب رقابي)',
            'account_type': account_types['liability'],
            'level': 3,
            'is_control_account': True,
            'is_leaf': False,
            'is_active': True,
            'currency': egp,
        }
    )

    cust_adv, _ = ChartOfAccounts.objects.get_or_create(
        code='21510',
        defaults={
            'name': 'عملاء دفعات مقدمة',
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

    vat_inp, _ = ChartOfAccounts.objects.get_or_create(
        code='11510',
        defaults={
            'name': 'ضريبة مدخلات',
            'account_type': account_types['asset'],
            'level': 4,
            'is_leaf': True,
            'is_active': True,
            'currency': egp,
        }
    )

    round_diff, _ = ChartOfAccounts.objects.get_or_create(
        code='54400',
        defaults={
            'name': 'فروق تقريب',
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
        'cust_control': cust_control,
        'supp_control': supp_control,
        'bank_exp': bank_exp,
        'vat_inp': vat_inp,
        'round_diff': round_diff,
        'currency': egp,
    }


@pytest.fixture(autouse=True)
def setup_treasury_access(db, test_user, financial_accounts):
    from financial.models import UserTreasuryAccess
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
def sample_customer(db, financial_accounts):
    cust, _ = Customer.objects.get_or_create(
        name='عميل اختبار P1',
        defaults={'code': 'CUST-P1-01', 'phone': '01011119999'}
    )
    SubledgerAccountService.get_or_create_customer_account(cust)
    cust.refresh_from_db()
    return cust


@pytest.fixture
def sample_supplier(db, financial_accounts):
    supp, _ = Supplier.objects.get_or_create(
        name='مورد اختبار P1',
        defaults={'code': 'SUPP-P1-01'}
    )
    SubledgerAccountService.get_or_create_supplier_account(supp)
    supp.refresh_from_db()
    return supp


@pytest.fixture
def sample_cost_center(db):
    cc, _ = CostCenter.objects.get_or_create(
        code='CC-OPS-01',
        defaults={'name': 'مركز العمليات', 'is_active': True}
    )
    return cc


# ==============================================================================
# 1. [P1] إنشاء الشيكات واستكمال الدورة (Issue / Receive)
# ==============================================================================
@pytest.mark.django_db
def test_p1_issue_and_receive_cheque_lifecycle(test_user, financial_accounts, sample_customer, sample_supplier):
    """التحقق من عمل دالة issue_cheque للشيك الصادر و receive_cheque لشيك القبض"""
    today = timezone.localdate()

    # 1. شيك دفع صادر لمورد
    chq_pay = Cheque.objects.create(
        cheque_number='CHQ-PAY-P1-01',
        cheque_type=ChequeType.PAYABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.DRAFT,
        supplier=sample_supplier,
        amount=Decimal('5000.00'),
        currency=financial_accounts['currency'],
        issue_date=today,
        due_date=today,
        deposit_bank_account=financial_accounts['bank'],
        created_by=test_user,
    )
    result_pay = ChequeAccountingService.issue_cheque(cheque=chq_pay, user=test_user)
    chq_pay.refresh_from_db()
    assert chq_pay.status == ChequeStatus.ISSUED
    assert result_pay['journal_entry'] is not None
    # قيد الإصدار: من حساب المورد إلى حساب أوراق الدفع 21120
    assert result_pay['journal_entry'].status == 'posted'

    # 2. شيك قبض وارد من عميل
    chq_rec = Cheque.objects.create(
        cheque_number='CHQ-REC-P1-01',
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.DRAFT,
        customer=sample_customer,
        amount=Decimal('8000.00'),
        currency=financial_accounts['currency'],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )
    result_rec = ChequeAccountingService.receive_cheque(cheque=chq_rec, user=test_user)
    chq_rec.refresh_from_db()
    assert chq_rec.status == ChequeStatus.IN_PORTFOLIO
    assert result_rec['journal_entry'] is not None
    # قيد الاستلام: من حساب أوراق القبض 11220 إلى حساب العميل
    assert result_rec['journal_entry'].status == 'posted'


# ==============================================================================
# 2. [P1] حفظ الرصيد المحلي المتبقي بعد التحصيل الجزئي
# ==============================================================================
@pytest.mark.django_db
def test_p1_remaining_functional_persisted_on_partial_collection(test_user, financial_accounts, sample_customer):
    """التأكد من أن remaining_functional يتم حفظه في قاعدة البيانات عند التحصيل الجزئي"""
    today = timezone.localdate()
    cheque = Cheque.objects.create(
        cheque_number='CHQ-PART-01',
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.UNDER_COLLECTION,
        customer=sample_customer,
        amount=Decimal('1000.00'),
        currency=financial_accounts['currency'],
        original_exchange_rate=Decimal('1.000000'),
        issue_date=today,
        due_date=today,
        deposit_bank_account=financial_accounts['bank'],
        created_by=test_user,
    )
    # تحصيل جزئي بمبلغ 600
    ChequeAccountingService.collect_cheque(
        cheque=cheque,
        amount=Decimal('600.00'),
        collection_date=today,
        bank_account=financial_accounts['bank'],
        user=test_user,
    )

    # التحقق مباشرة من قاعدة البيانات
    cheque.refresh_from_db()
    assert cheque.status == ChequeStatus.PARTIALLY_COLLECTED
    assert cheque.collected_amount == Decimal('600.00')
    assert cheque.remaining_amount == Decimal('400.00')
    assert cheque.remaining_functional == Decimal('400.00'), "remaining_functional must be persisted to DB!"


# ==============================================================================
# 3. [P1] الشيكات الافتتاحية: استبعاد قيد الاستلام/الإصدار فقط وقيد الحركات اللاحقة
# ==============================================================================
@pytest.mark.django_db
def test_p1_opening_balance_cheque_allows_future_gl_entries(test_user, financial_accounts, sample_customer):
    """الشيك الافتتاحي لا يولد قيد استلام، لكن يولد قيد تحصيل بنكي حقيقي"""
    today = timezone.localdate()
    cheque = Cheque.objects.create(
        cheque_number='CHQ-OPENING-01',
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.DRAFT,
        customer=sample_customer,
        amount=Decimal('3000.00'),
        currency=financial_accounts['currency'],
        is_opening_balance=True,
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )
    # 1. الاستلام الأولي: لا يجب إنشاء قيد (لأنه مدرج في ميزان الافتتاحي)
    rec_result = ChequeAccountingService.receive_cheque(cheque=cheque, user=test_user)
    assert rec_result['journal_entry'] is None
    cheque.refresh_from_db()
    assert cheque.status == ChequeStatus.IN_PORTFOLIO

    # 2. الإيداع بالبنك
    ChequeAccountingService.deposit_cheque(
        cheque=cheque,
        bank_account=financial_accounts['bank'],
        deposit_date=today,
        user=test_user,
    )
    cheque.refresh_from_db()
    assert cheque.status == ChequeStatus.UNDER_COLLECTION

    # 3. التحصيل البنكي: لا بد من توليد قيد بنكي حقيقي!
    coll_result = ChequeAccountingService.collect_cheque(
        cheque=cheque,
        amount=Decimal('3000.00'),
        collection_date=today,
        bank_account=financial_accounts['bank'],
        user=test_user,
    )
    cheque.refresh_from_db()
    assert cheque.status == ChequeStatus.COLLECTED
    assert coll_result['journal_entry'] is not None, "Opening balance cheque collection must create Bank GL entry!"
    assert coll_result['journal_entry'].status == 'posted'


# ==============================================================================
# 4. [P1] معالجة الارتداد والإلغاء حسب نوع الشيك (Payable Bounce / Portfolio Cancel)
# ==============================================================================
@pytest.mark.django_db
def test_p1_payable_bounce_and_portfolio_cancel(test_user, financial_accounts, sample_customer, sample_supplier):
    """التحقق من قيد ارتداد شيك الدفع الصادر لمورد، وقيد إلغاء شيك قبض بالمحفظة"""
    today = timezone.localdate()

    # 1. ارتداد شيك دفع لمورد
    chq_pay = Cheque.objects.create(
        cheque_number='CHQ-PAY-BOUNCE-01',
        cheque_type=ChequeType.PAYABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.ISSUED,
        supplier=sample_supplier,
        amount=Decimal('4500.00'),
        currency=financial_accounts['currency'],
        deposit_bank_account=financial_accounts['bank'],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )
    bounce_pay_res = ChequeAccountingService.bounce_cheque(
        cheque=chq_pay,
        rejection_reason='عدم كفاية الرصيد',
        bounce_date=today,
        user=test_user,
    )
    chq_pay.refresh_from_db()
    assert chq_pay.status == ChequeStatus.BOUNCED
    assert bounce_pay_res['journal_entry'] is not None
    # يجب أن يكون القيد: من ح/ أوراق الدفع إلى ح/ المورد (إعادة المديونية)
    lines = list(bounce_pay_res['journal_entry'].lines.all())
    debit_lines = [l for l in lines if l.debit > 0]
    credit_lines = [l for l in lines if l.credit > 0]
    assert any(l.account.code == '21120' for l in debit_lines)
    assert any(l.account == sample_supplier.financial_account for l in credit_lines)

    # 2. إلغاء شيك قبض من المحفظة
    chq_rec = Cheque.objects.create(
        cheque_number='CHQ-REC-CANCEL-01',
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.IN_PORTFOLIO,
        customer=sample_customer,
        amount=Decimal('2000.00'),
        currency=financial_accounts['currency'],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )
    cancel_res = ChequeAccountingService.cancel_cheque(
        cheque=chq_rec,
        reason='إلغاء بناء على طلب العميل',
        user=test_user,
    )
    chq_rec.refresh_from_db()
    assert chq_rec.status == ChequeStatus.CANCELLED
    assert cancel_res['journal_entry'] is not None
    # قيد الإلغاء: من ح/ العميل إلى ح/ أوراق القبض 11220
    c_lines = list(cancel_res['journal_entry'].lines.all())
    c_deb = [l for l in c_lines if l.debit > 0]
    c_cred = [l for l in c_lines if l.credit > 0]
    assert any(l.account == sample_customer.financial_account for l in c_deb)
    assert any(l.account.code == '11220' for l in c_cred)


# ==============================================================================
# 5. [P1] تخصيص الدفعات المقدمة وعكس الارتداد المتكامل
# ==============================================================================
@pytest.mark.django_db
def test_p1_advance_allocation_and_bounce_reversal(test_user, financial_accounts, sample_customer):
    """التحقق من إنشاء قيد نقل الدفعة المقدمة لحساب العميل، وعكسه واستعادته عند التراجع"""
    today = timezone.localdate()

    # إنشاء فاتورة مبيعات
    sale = Sale.objects.create(
        customer=sample_customer,
        date=today,
        subtotal=Decimal('5000.00'),
        total=Decimal('5000.00'),
        currency=financial_accounts['currency'],
        exchange_rate=Decimal('1.000000'),
        total_functional=Decimal('5000.00'),
        payment_method='credit',
        created_by=test_user,
    )

    # شيك دفعة مقدمة تم تحصيله
    chq_adv = Cheque.objects.create(
        cheque_number='CHQ-ADV-01',
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.ADVANCE_PAYMENT,
        status=ChequeStatus.COLLECTED,
        customer=sample_customer,
        amount=Decimal('5000.00'),
        collected_amount=Decimal('5000.00'),
        remaining_amount=Decimal('0.00'),
        currency=financial_accounts['currency'],
        deposit_bank_account=financial_accounts['bank'],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )

    # تخصيص الدفعة المقدمة للفاتورة
    alloc = ChequeAllocationService.allocate_cheque_to_invoice(
        cheque=chq_adv,
        sale=sale,
        amount=Decimal('5000.00'),
        user=test_user,
    )
    assert alloc.allocation_status == 'APPLIED'
    assert alloc.journal_entry is not None, "Advance allocation must generate a GL reclassification entry!"

    # التحقق من سطور القيد: مدين: دفعات مقدمة 21510، دائن: حساب العميل
    alloc_lines = list(alloc.journal_entry.lines.all())
    assert any(l.account.code == '21510' and l.debit == Decimal('5000.00') for l in alloc_lines)
    assert any(l.account == sample_customer.financial_account and l.credit == Decimal('5000.00') for l in alloc_lines)

    # الفاتورة مدفوعة الآن
    sale.refresh_from_db()
    assert sale.amount_paid == Decimal('5000.00')

    # ارتداد الشيك
    ChequeAccountingService.bounce_cheque(
        cheque=chq_adv,
        rejection_reason='تزوير توقيع',
        bounce_date=today,
        user=test_user,
    )
    alloc.refresh_from_db()
    sale.refresh_from_db()
    assert alloc.allocation_status == 'REVERSED'
    assert sale.amount_paid == Decimal('0.00')
    assert sale.payment_status == 'unpaid'

    # التراجع عن الارتداد عبر خدمة ReversalService
    ChequeReversalService.reverse_last_action(
        cheque=chq_adv,
        reason='تسوية بنكية صحيحة للارتداد الخاطئ',
        user=test_user,
    )
    alloc.refresh_from_db()
    sale.refresh_from_db()
    assert alloc.allocation_status == 'APPLIED'
    assert sale.amount_paid == Decimal('5000.00')
    assert sale.payment_status == 'paid'


# ==============================================================================
# 6. [P1] حساسية بصمة الطلب ومفتاح عدم التكرار (Idempotency Key & Payload Hash)
# ==============================================================================
@pytest.mark.django_db
def test_p1_idempotency_payload_hash_sensitivity(test_user, financial_accounts, sample_customer):
    """التأكد من أن تغيير سعر الصرف أو الضريبة يغير بصمة الطلب، وأن تكرار المفتاح يعيد نفس النتيجة"""
    today = timezone.localdate()
    cheque = Cheque.objects.create(
        cheque_number='CHQ-IDEMP-01',
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.UNDER_COLLECTION,
        customer=sample_customer,
        amount=Decimal('1000.00'),
        currency=financial_accounts['currency'],
        deposit_bank_account=financial_accounts['bank'],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )

    # بصمة 1: سعر صرف 1.0 وبدون ضريبة
    h1 = ChequeAccountingService._compute_payload_hash(
        cheque_id=cheque.id,
        action_type=ChequeActionType.COLLECT,
        amount=Decimal('500.00'),
        bank_account_id=financial_accounts['bank'].id,
        supplier_id=None,
        target_status=ChequeStatus.PARTIALLY_COLLECTED,
        bank_charges=Decimal('20.00'),
        exchange_rate=Decimal('1.000000'),
        bank_charges_vat=Decimal('0.00'),
    )

    # بصمة 2: نفس البيانات لكن مع ضريبة عمولة
    h2 = ChequeAccountingService._compute_payload_hash(
        cheque_id=cheque.id,
        action_type=ChequeActionType.COLLECT,
        amount=Decimal('500.00'),
        bank_account_id=financial_accounts['bank'].id,
        supplier_id=None,
        target_status=ChequeStatus.PARTIALLY_COLLECTED,
        bank_charges=Decimal('20.00'),
        exchange_rate=Decimal('1.000000'),
        bank_charges_vat=Decimal('2.80'),
    )

    # بصمة 3: مع تغير سعر الصرف
    h3 = ChequeAccountingService._compute_payload_hash(
        cheque_id=cheque.id,
        action_type=ChequeActionType.COLLECT,
        amount=Decimal('500.00'),
        bank_account_id=financial_accounts['bank'].id,
        supplier_id=None,
        target_status=ChequeStatus.PARTIALLY_COLLECTED,
        bank_charges=Decimal('20.00'),
        exchange_rate=Decimal('1.050000'),
        bank_charges_vat=Decimal('0.00'),
    )

    assert h1 != h2, "Payload hash must differ when bank_charges_vat changes!"
    assert h1 != h3, "Payload hash must differ when exchange_rate changes!"

    # إعادة نفس المفتاح idempotent
    idemp_key = "P1-UNIQUE-IDEMP-KEY-999"
    res1 = ChequeAccountingService.collect_cheque(
        cheque=cheque,
        amount=Decimal('500.00'),
        collection_date=today,
        bank_account=financial_accounts['bank'],
        idempotency_key=idemp_key,
        user=test_user,
    )
    res2 = ChequeAccountingService.collect_cheque(
        cheque=cheque,
        amount=Decimal('500.00'),
        collection_date=today,
        bank_account=financial_accounts['bank'],
        idempotency_key=idemp_key,
        user=test_user,
    )
    assert res1['cheque'].status == res2['cheque'].status
    assert res1['journal_entry'] == res2['journal_entry']


# ==============================================================================
# 7. [P1] تحويل شيك الضمان إلى تشغيلي
# ==============================================================================
@pytest.mark.django_db
def test_p1_guarantee_conversion_to_operational(test_user, financial_accounts, sample_customer):
    """شيك الضمان يتم تحويله للتشغيل وتحديث purpose واستدعاء الاستلام وتوليد القيد"""
    today = timezone.localdate()
    chq_guar = Cheque.objects.create(
        cheque_number='CHQ-GUAR-01',
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.SECURITY_GUARANTEE,
        status=ChequeStatus.DRAFT,
        customer=sample_customer,
        amount=Decimal('15000.00'),
        currency=financial_accounts['currency'],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )
    assert chq_guar.is_guarantee is True

    # تحويل الشيك
    chq_guar.purpose = ChequePurpose.INVOICE_SETTLEMENT
    chq_guar.save()
    assert chq_guar.is_guarantee is False

    # تسجيل حركة التحويل واستلام الشيك
    ChequeActionLog.objects.create(
        cheque=chq_guar,
        action=ChequeActionType.CONVERT_GUARANTEE,
        from_status=ChequeStatus.DRAFT,
        to_status=ChequeStatus.DRAFT,
        amount_processed=chq_guar.amount,
        action_date=today,
        reason='تحويل الضمان لتسوية فاتورة',
        created_by=test_user,
    )
    res = ChequeAccountingService.receive_cheque(cheque=chq_guar, user=test_user)
    chq_guar.refresh_from_db()
    assert chq_guar.status == ChequeStatus.IN_PORTFOLIO
    assert res['journal_entry'] is not None


# ==============================================================================
# 8. [P1] تمرير مركز التكلفة لقيد اليومية
# ==============================================================================
@pytest.mark.django_db
def test_p1_cost_center_propagation_to_journal_entry(test_user, financial_accounts, sample_customer, sample_cost_center):
    """التأكد من تمرير cost_center_code من الشيك إلى قيود اليومية ومصروفات البنك"""
    today = timezone.localdate()
    cheque = Cheque.objects.create(
        cheque_number='CHQ-CC-01',
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.UNDER_COLLECTION,
        customer=sample_customer,
        amount=Decimal('2000.00'),
        currency=financial_accounts['currency'],
        deposit_bank_account=financial_accounts['bank'],
        cost_center=sample_cost_center,
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )
    res = ChequeAccountingService.collect_cheque(
        cheque=cheque,
        amount=Decimal('2000.00'),
        collection_date=today,
        bank_account=financial_accounts['bank'],
        bank_charges=Decimal('50.00'),
        user=test_user,
    )
    je = res['journal_entry']
    assert je is not None
    # يجب أن يحمل سطر المصروف مركز التكلفة
    exp_line = je.lines.filter(account__code='54100').first()
    assert exp_line is not None
    assert exp_line.cost_center == sample_cost_center


# ==============================================================================
# 9. [P1] تفويض القيود وعدم فقدان قيد السداد إذا لم يكن هناك شيك مسجل
# ==============================================================================
@pytest.mark.django_db
def test_p1_payment_posting_delegation_safety(test_user, financial_accounts, sample_customer):
    """إذا كان السداد بشيك لكن ليس له كائن Cheque مرتبط، يتم الترحيل كالمعتاد ولا يتم بلع القيد"""
    today = timezone.localdate()
    sale = Sale.objects.create(
        customer=sample_customer,
        date=today,
        subtotal=Decimal('1200.00'),
        total=Decimal('1200.00'),
        currency=financial_accounts['currency'],
        exchange_rate=Decimal('1.000000'),
        total_functional=Decimal('1200.00'),
        payment_method='credit',
        created_by=test_user,
    )
    payment = SalePayment.objects.create(
        sale=sale,
        amount=Decimal('1200.00'),
        payment_method='check',
        payment_date=today,
        reference_number='MANUAL-CHK-REF-99',
        created_by=test_user,
    )
    # لا يوجد شيك مسجل برقم MANUAL-CHK-REF-99 في موديول أوراق القبض
    je = AccountingIntegrationService.create_payment_journal_entry(
        payment=payment,
        payment_type='sale_payment',
        user=test_user,
    )
    assert je is not None, "When no matching Cheque exists in cheques app, payment journal entry must NOT be dropped!"
    assert je.status == 'posted'


# ==============================================================================
# TESTS FOR ROUND 2 P1 CONFIRMED FIXES
# ==============================================================================

@pytest.mark.django_db
def test_p1_replayed_collect_action_does_not_duplicate_collection(client, test_user, financial_accounts, sample_customer):
    """إعادة إرسال نفس طلب التحصيل من الواجهة (دون مفتاح صريح) لا يكرر التحصيل مالياً"""
    client.force_login(test_user)
    today = timezone.localdate()
    cheque = Cheque.objects.create(
        voucher_number='RV-IDEM-01',
        cheque_number='CHQ-IDEM-01',
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.UNDER_COLLECTION,
        customer=sample_customer,
        amount=Decimal('1000.00'),
        collected_amount=Decimal('0.00'),
        remaining_amount=Decimal('1000.00'),
        currency=financial_accounts['currency'],
        deposit_bank_account=financial_accounts['bank'],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )
    url = reverse('cheques:cheque_collect_action', kwargs={'pk': cheque.pk})
    post_data = {
        'amount_collected': '100.00',
        'value_date': str(today),
        'exchange_rate': '1.000000',
        'bank_charges': '0.00',
        'bank_charges_vat': '0.00',
        'deposit_bank_account': str(financial_accounts['bank'].id),
        'notes': 'تحصيل جزئي أول',
        # لا نرسل idempotency_key لمحاكاة طلب الواجهة بدون مفتاح
    }
    # الطلب الأول
    res1 = client.post(url, data=post_data)
    assert res1.status_code in [200, 302]
    cheque.refresh_from_db()
    assert cheque.collected_amount == Decimal('100.00')
    assert cheque.remaining_amount == Decimal('900.00')

    # الطلب الثاني (إعادة إرسال نفس البيانات بالضبط)
    res2 = client.post(url, data=post_data)
    assert res2.status_code in [200, 302]
    cheque.refresh_from_db()
    # يجب أن يظل المبلغ المحصل 100 وليس 200
    assert cheque.collected_amount == Decimal('100.00')
    assert cheque.remaining_amount == Decimal('900.00')
    assert cheque.settlement_lines.count() == 1


@pytest.mark.django_db
def test_p1_bounce_reversal_fully_restores_partial_bounce_invoice_amount(test_user, financial_accounts, sample_customer):
    """تخصيص 1000 ثم تحصيل 600 وارتداد الباقي: عكس الارتداد يعيد سداد الفاتورة لـ 1000 بالكامل"""
    today = timezone.localdate()
    sale = Sale.objects.create(
        customer=sample_customer,
        date=today,
        subtotal=Decimal('1000.00'),
        total=Decimal('1000.00'),
        currency=financial_accounts['currency'],
        exchange_rate=Decimal('1.000000'),
        total_functional=Decimal('1000.00'),
        payment_method='credit',
        created_by=test_user,
    )
    cheque = Cheque.objects.create(
        voucher_number='RV-PBNC-01',
        cheque_number='CHQ-PBNC-01',
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.UNDER_COLLECTION,
        customer=sample_customer,
        amount=Decimal('1000.00'),
        collected_amount=Decimal('0.00'),
        remaining_amount=Decimal('1000.00'),
        currency=financial_accounts['currency'],
        deposit_bank_account=financial_accounts['bank'],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )
    # تخصيص الشيك بالكامل على الفاتورة
    alloc = ChequeAllocationService.allocate_cheque_to_invoice(
        cheque=cheque,
        sale=sale,
        amount=Decimal('1000.00'),
        user=test_user,
    )
    sale.refresh_from_db()
    assert sale.amount_paid == Decimal('1000.00')

    # تحصيل جزئي 600
    ChequeAccountingService.collect_cheque(
        cheque=cheque,
        amount_collected=Decimal('600.00'),
        value_date=today,
        user=test_user,
        idempotency_key='COL-PBNC-600',
    )
    cheque.refresh_from_db()
    assert cheque.status == ChequeStatus.PARTIALLY_COLLECTED
    assert cheque.collected_amount == Decimal('600.00')

    # ارتداد المتبقي (400)
    ChequeAccountingService.bounce_cheque(
        cheque=cheque,
        rejection_reason='عدم كفاية الرصيد للمتبقي',
        bounce_date=today,
        user=test_user,
        idempotency_key='BNC-PBNC-400',
    )
    cheque.refresh_from_db()
    assert cheque.status == ChequeStatus.BOUNCED
    sale.refresh_from_db()
    assert sale.amount_paid == Decimal('600.00')

    # التراجع عن حركة الارتداد
    ChequeReversalService.reverse_last_action(
        cheque=cheque,
        reason='تسوية بنكية للارتداد واستعادة التخصيص الكامل',
        user=test_user,
    )
    sale.refresh_from_db()
    # بعد عكس الارتداد: الفاتورة يجب أن تعود مسددة 1000 بالكامل
    assert sale.amount_paid == Decimal('1000.00')
    assert sale.payment_status == 'paid'
    payment = SalePayment.objects.filter(sale=sale, source_type='CHEQUE').first()
    assert payment.amount == Decimal('1000.00')
    assert payment.status == 'posted'


@pytest.mark.django_db
def test_p1_bounce_reversal_fully_restores_advance_allocation_gl_entry(test_user, financial_accounts, sample_customer):
    """عكس ارتداد شيك دفعة مقدمة يستعيد القيد المحاسبي لتسوية الدفعة المقدمة ورصيد حساب العميل"""
    today = timezone.localdate()
    sale = Sale.objects.create(
        customer=sample_customer,
        date=today,
        subtotal=Decimal('3000.00'),
        total=Decimal('3000.00'),
        currency=financial_accounts['currency'],
        exchange_rate=Decimal('1.000000'),
        total_functional=Decimal('3000.00'),
        payment_method='credit',
        created_by=test_user,
    )
    cheque = Cheque.objects.create(
        voucher_number='RV-ADV-REV-01',
        cheque_number='CHQ-ADV-REV-01',
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.ADVANCE_PAYMENT,
        status=ChequeStatus.COLLECTED,
        customer=sample_customer,
        amount=Decimal('3000.00'),
        collected_amount=Decimal('3000.00'),
        remaining_amount=Decimal('0.00'),
        currency=financial_accounts['currency'],
        deposit_bank_account=financial_accounts['bank'],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )
    alloc = ChequeAllocationService.allocate_cheque_to_invoice(
        cheque=cheque,
        sale=sale,
        amount=Decimal('3000.00'),
        user=test_user,
    )
    orig_je = alloc.journal_entry
    assert orig_je is not None
    assert orig_je.status == 'posted'

    # ارتداد الشيك
    ChequeAccountingService.bounce_cheque(
        cheque=cheque,
        rejection_reason='توقيع غير مطابق',
        user=test_user,
        idempotency_key='BNC-ADV-01',
    )
    orig_je.refresh_from_db()
    assert orig_je.reversed_by_entry is not None

    # التراجع عن الارتداد
    ChequeReversalService.reverse_last_action(
        cheque=cheque,
        reason='تصحيح الارتداد واستعادة التسوية',
        user=test_user,
    )
    alloc.refresh_from_db()
    sale.refresh_from_db()
    assert alloc.allocation_status == 'APPLIED'
    assert sale.amount_paid == Decimal('3000.00')

    # التحقق من أن القيد تم استعادته وبحالة posted
    assert alloc.journal_entry is not None
    assert alloc.journal_entry.status == 'posted'
    # تحقق من بنود القيد المستعاد: مدين دفعات مقدمة 21510 ودائن العميل
    je_lines = list(alloc.journal_entry.lines.all())
    assert any(l.account.code == '21510' and l.debit == Decimal('3000.00') for l in je_lines)
    assert any(l.account == sample_customer.financial_account and l.credit == Decimal('3000.00') for l in je_lines)


@pytest.mark.django_db
def test_p1_draft_cheque_partial_collection_strictly_rejected(test_user, financial_accounts, sample_customer):
    """محاولة تحصيل شيك مسودة (كلي أو جزئي) مرفوضة قطعياً في آلة الحالات"""
    today = timezone.localdate()
    cheque = Cheque.objects.create(
        voucher_number='RV-DRAFT-COLL-01',
        cheque_number='CHQ-DRAFT-01',
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.DRAFT,
        customer=sample_customer,
        amount=Decimal('1000.00'),
        collected_amount=Decimal('0.00'),
        remaining_amount=Decimal('1000.00'),
        currency=financial_accounts['currency'],
        deposit_bank_account=financial_accounts['bank'],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )
    with pytest.raises(ValidationError) as exc_info:
        ChequeAccountingService.collect_cheque(
            cheque=cheque,
            amount_collected=Decimal('100.00'),
            value_date=today,
            user=test_user,
            idempotency_key='COL-DRAFT-FAIL',
        )
    assert "لا يمكن تحويل حالة الشيك" in str(exc_info.value)
    cheque.refresh_from_db()
    assert cheque.status == ChequeStatus.DRAFT
    assert cheque.collected_amount == Decimal('0.00')


@pytest.mark.django_db
def test_p1_direct_portfolio_collection_credits_notes_receivable_11220(test_user, financial_accounts, sample_customer):
    """التحصيل المباشر لشيك من المحفظة (IN_PORTFOLIO) يقفل أوراق القبض بالمحفظة 11220 وليس شيكات برسم التحصيل"""
    today = timezone.localdate()
    cheque = Cheque.objects.create(
        voucher_number='RV-PORT-COLL-01',
        cheque_number='CHQ-PORT-01',
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.IN_PORTFOLIO,
        customer=sample_customer,
        amount=Decimal('2500.00'),
        collected_amount=Decimal('0.00'),
        remaining_amount=Decimal('2500.00'),
        currency=financial_accounts['currency'],
        deposit_bank_account=financial_accounts['bank'],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )
    res = ChequeAccountingService.collect_cheque(
        cheque=cheque,
        amount_collected=Decimal('2500.00'),
        value_date=today,
        user=test_user,
        idempotency_key='COL-PORT-2500',
    )
    je = res['journal_entry']
    assert je is not None
    credit_lines = je.lines.filter(credit__gt=0)
    # الطرف الدائن يجب أن يكون أوراق القبض 11220
    assert any(l.account.code == '11220' and l.credit == Decimal('2500.00') for l in credit_lines)
    # لا يجوز أن يظهر حساب شيكات برسم التحصيل 11221
    assert not any(l.account.code == '11221' for l in credit_lines)


@pytest.mark.django_db
def test_p1_guarantee_conversion_from_in_portfolio_succeeds_and_posts_gl(client, test_user, financial_accounts, sample_customer):
    """تحويل شيك ضمان موجود بالمحفظة (IN_PORTFOLIO) ينجح عبر الواجهة ويولد القيد المحاسبي"""
    client.force_login(test_user)
    today = timezone.localdate()
    cheque = Cheque.objects.create(
        voucher_number='RV-GUAR-PORT-01',
        cheque_number='CHQ-GUAR-PORT-01',
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.SECURITY_GUARANTEE,
        status=ChequeStatus.IN_PORTFOLIO,
        customer=sample_customer,
        amount=Decimal('7000.00'),
        collected_amount=Decimal('0.00'),
        remaining_amount=Decimal('7000.00'),
        currency=financial_accounts['currency'],
        deposit_bank_account=financial_accounts['bank'],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )
    assert cheque.is_guarantee is True

    url = reverse('cheques:cheque_convert_guarantee_action', kwargs={'pk': cheque.pk})
    post_data = {
        'new_purpose': ChequePurpose.INVOICE_SETTLEMENT,
        'approval_notes': 'اعتماد الإدارة المالية لتحويل الضمان إلى تجاري',
    }
    res = client.post(url, data=post_data)
    assert res.status_code in [200, 302]

    cheque.refresh_from_db()
    assert cheque.is_guarantee is False
    assert cheque.purpose == ChequePurpose.INVOICE_SETTLEMENT
    assert cheque.status == ChequeStatus.IN_PORTFOLIO

    # التحقق من تسجيل الحركة وتوليد القيد المحاسبي
    log = ChequeActionLog.objects.filter(cheque=cheque, action=ChequeActionType.CONVERT_GUARANTEE).first()
    assert log is not None
    assert log.journal_entry is not None
    assert log.journal_entry.status == 'posted'
    # مدين أوراق قبض 11220، دائن العميل
    je_lines = list(log.journal_entry.lines.all())
    assert any(l.account.code == '11220' and l.debit == Decimal('7000.00') for l in je_lines)
    assert any(l.account == sample_customer.financial_account and l.credit == Decimal('7000.00') for l in je_lines)


@pytest.mark.django_db
def test_p1_endorse_cheque_to_specific_supplier_succeeds_without_preexisting_supplier(test_user, financial_accounts, sample_customer, account_types):
    """تظهير شيك قبض لمورد محدد ينجح دون وجود مورد مسبق على الشيك وبدون NoneType error"""
    today = timezone.localdate()
    supp = Supplier.objects.create(
        name='المورد المظهر إليه الحديث',
    )
    supp_acc = ChartOfAccounts.objects.create(
        code='2111199',
        name='حساب مورد مظهر',
        account_type=account_types['liability'],
        is_leaf=True,
    )
    supp.financial_account = supp_acc
    supp.save(update_fields=['financial_account'])

    cheque = Cheque.objects.create(
        voucher_number='RV-END-TEST-01',
        cheque_number='CHQ-END-01',
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.IN_PORTFOLIO,
        customer=sample_customer,
        supplier=None,  # لا يوجد مورد مسبق
        amount=Decimal('4500.00'),
        collected_amount=Decimal('0.00'),
        remaining_amount=Decimal('4500.00'),
        currency=financial_accounts['currency'],
        deposit_bank_account=financial_accounts['bank'],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )
    # تظهير الشيك لمورد محدد
    res = ChequeAccountingService.endorse_cheque(
        cheque=cheque,
        supplier_id=supp.id,
        user=test_user,
        idempotency_key='END-TEST-4500',
    )
    cheque.refresh_from_db()
    assert cheque.status == ChequeStatus.ENDORSED
    assert cheque.supplier == supp

    je = res['journal_entry']
    assert je is not None
    je_lines = list(je.lines.all())
    # مدين: حساب المورد 4500، دائن: أوراق القبض 11220 4500
    assert any(l.account == supp_acc and l.debit == Decimal('4500.00') for l in je_lines)
    assert any(l.account.code == '11220' and l.credit == Decimal('4500.00') for l in je_lines)


# ==============================================================================
# Round 3 Fixes Tests (6 Issues Verified)
# ==============================================================================

@pytest.mark.django_db
def test_p1_guarantee_conversion_cannot_be_reexecuted_on_already_converted_cheque(test_user, financial_accounts, sample_customer):
    """تحويل شيك الضمان لتشغيلي لا يمكن تكراره مرة أخرى لمنع تكرار القيد المحاسبي"""
    today = timezone.localdate()
    cheque = Cheque.objects.create(
        voucher_number='RV-GUAR-DUP-01',
        cheque_number='CHQ-GUAR-DUP-01',
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.SECURITY_GUARANTEE,
        status=ChequeStatus.IN_PORTFOLIO,
        customer=sample_customer,
        amount=Decimal('3000.00'),
        collected_amount=Decimal('0.00'),
        remaining_amount=Decimal('3000.00'),
        currency=financial_accounts['currency'],
        deposit_bank_account=financial_accounts['bank'],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )
    # التحويل الأول: ينجح ويولد القيد
    res1 = ChequeAccountingService.convert_guarantee(
        cheque=cheque,
        user=test_user,
        new_purpose=ChequePurpose.INVOICE_SETTLEMENT,
        idempotency_key='CONV-KEY-01'
    )
    assert res1['journal_entry'] is not None
    cheque.refresh_from_db()
    assert cheque.is_guarantee is False

    # محاولة التحويل مرة ثانية بمفتاح جديد: يجب أن تُرفض قطعياً ولا تولد قيداً جديداً
    with pytest.raises(ValidationError) as exc:
        ChequeAccountingService.convert_guarantee(
            cheque=cheque,
            user=test_user,
            new_purpose=ChequePurpose.INVOICE_SETTLEMENT,
            idempotency_key='CONV-KEY-02'
        )
    assert "ليس شيك ضمان" in str(exc.value)


@pytest.mark.django_db
def test_p1_guarantee_conversion_failure_rolls_back_atomically_without_state_leak(test_user, financial_accounts, sample_customer):
    """فشل تحويل الضمان يتراجع ذرياً بالكامل دون ترك أي تغيير في purpose أو الشيك"""
    today = timezone.localdate()
    cheque = Cheque.objects.create(
        voucher_number='RV-GUAR-RB-01',
        cheque_number='CHQ-GUAR-RB-01',
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.SECURITY_GUARANTEE,
        status=ChequeStatus.IN_PORTFOLIO,
        customer=sample_customer,
        amount=Decimal('4000.00'),
        collected_amount=Decimal('0.00'),
        remaining_amount=Decimal('4000.00'),
        currency=financial_accounts['currency'],
        deposit_bank_account=financial_accounts['bank'],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )

    # إنشاء فترة مغلقة ومحاولة التحويل بتاريخ الفترة المغلقة
    from financial.models import AccountingPeriod
    closed_date = today - datetime.timedelta(days=400)
    AccountingPeriod.objects.create(
        name='فترة سابقة مقفلة P1',
        start_date=closed_date - datetime.timedelta(days=15),
        end_date=closed_date + datetime.timedelta(days=15),
        status='closed',
        fiscal_year=None,
    )

    with pytest.raises(ValidationError) as exc:
        ChequeAccountingService.convert_guarantee(
            cheque=cheque,
            user=test_user,
            new_purpose=ChequePurpose.INVOICE_SETTLEMENT,
            value_date=closed_date,
            idempotency_key='CONV-CLOSED-PER'
        )
    assert "مغلقة" in str(exc.value)

    # التحقق من أن الشيك لم تتغير بياناته وتراجع التغيير ذرياً
    cheque.refresh_from_db()
    assert cheque.is_guarantee is True
    assert cheque.purpose == ChequePurpose.SECURITY_GUARANTEE
    assert cheque.status == ChequeStatus.IN_PORTFOLIO


@pytest.mark.django_db
def test_p1_bounce_reversal_does_not_restore_manually_cancelled_allocations(test_user, financial_accounts, sample_customer):
    """عكس الارتداد يستعيد فقط التخصيصات التي ألغيت بالارتداد، ولا يستعيد ما أُلغي يدوياً قبله"""
    today = timezone.localdate()
    cheque = Cheque.objects.create(
        voucher_number='RV-ALLOC-MAN-01',
        cheque_number='CHQ-ALLOC-MAN-01',
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.IN_PORTFOLIO,
        customer=sample_customer,
        amount=Decimal('1000.00'),
        collected_amount=Decimal('0.00'),
        remaining_amount=Decimal('1000.00'),
        currency=financial_accounts['currency'],
        deposit_bank_account=financial_accounts['bank'],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )

    sale1 = Sale.objects.create(
        customer=sample_customer,
        date=today,
        subtotal=Decimal('500.00'),
        total=Decimal('500.00'),
        currency=financial_accounts['currency'],
        exchange_rate=Decimal('1.000000'),
        total_functional=Decimal('500.00'),
        payment_method='credit',
        created_by=test_user,
    )
    sale2 = Sale.objects.create(
        customer=sample_customer,
        date=today,
        subtotal=Decimal('500.00'),
        total=Decimal('500.00'),
        currency=financial_accounts['currency'],
        exchange_rate=Decimal('1.000000'),
        total_functional=Decimal('500.00'),
        payment_method='credit',
        created_by=test_user,
    )

    alloc1 = ChequeAllocationService.allocate_cheque_to_invoice(
        cheque=cheque,
        sale=sale1,
        amount=Decimal('500.00'),
        user=test_user
    )
    alloc2 = ChequeAllocationService.allocate_cheque_to_invoice(
        cheque=cheque,
        sale=sale2,
        amount=Decimal('500.00'),
        user=test_user
    )
    assert alloc1.allocation_status == 'APPLIED'
    assert alloc2.allocation_status == 'APPLIED'

    # إلغاء التخصيص الأول يدوياً قبل الارتداد
    ChequeAllocationService.reverse_cheque_allocation(
        allocation=alloc1,
        reason='إلغاء يدوي لخطأ في الفاتورة 1',
        user=test_user
    )
    alloc1.refresh_from_db()
    assert alloc1.allocation_status == 'REVERSED'

    # حدوث ارتداد للشيك
    ChequeAccountingService.bounce_cheque(
        cheque=cheque,
        user=test_user,
        reason='رفض لعدم كفاية الرصيد',
        idempotency_key='BNC-MAN-TEST-01'
    )
    alloc2.refresh_from_db()
    assert alloc2.allocation_status == 'REVERSED'

    # التراجع عن الارتداد
    ChequeReversalService.reverse_last_action(
        cheque_id=cheque.id,
        user=test_user,
        reason='تصحيح الارتداد بالبنك',
        idempotency_key='REV-BNC-MAN-TEST'
    )

    alloc1.refresh_from_db()
    alloc2.refresh_from_db()
    # التخصيص 2 الذي ألغاه الارتداد يجب أن يعود APPLIED
    assert alloc2.allocation_status == 'APPLIED'
    # التخصيص 1 الملغى يدوياً يجب أن يظل REVERSED ولا يُستعاد!
    assert alloc1.allocation_status == 'REVERSED'


@pytest.mark.django_db
def test_p1_cancel_or_return_to_drawer_reopens_invoice_and_reverses_allocations(test_user, financial_accounts, sample_customer):
    """إلغاء الشيك أو رده للساحب يعكس التخصيصات ودفعة SalePayment ويعيد فتح الفاتورة"""
    today = timezone.localdate()
    cheque = Cheque.objects.create(
        voucher_number='RV-CAN-INV-01',
        cheque_number='CHQ-CAN-INV-01',
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.IN_PORTFOLIO,
        customer=sample_customer,
        amount=Decimal('1000.00'),
        collected_amount=Decimal('0.00'),
        remaining_amount=Decimal('1000.00'),
        currency=financial_accounts['currency'],
        deposit_bank_account=financial_accounts['bank'],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )

    sale = Sale.objects.create(
        customer=sample_customer,
        date=today,
        subtotal=Decimal('1000.00'),
        total=Decimal('1000.00'),
        currency=financial_accounts['currency'],
        exchange_rate=Decimal('1.000000'),
        total_functional=Decimal('1000.00'),
        payment_method='credit',
        created_by=test_user,
    )
    alloc = ChequeAllocationService.allocate_cheque_to_invoice(
        cheque=cheque,
        sale=sale,
        amount=Decimal('1000.00'),
        user=test_user
    )
    sale.refresh_from_db()
    assert sale.payment_status == 'paid'
    assert alloc.allocation_status == 'APPLIED'

    # إلغاء الشيك
    ChequeAccountingService.cancel_cheque(
        cheque=cheque,
        user=test_user,
        reason='إلغاء تجاري بطلب العميل',
        idempotency_key='CAN-INV-TEST-01'
    )

    cheque.refresh_from_db()
    alloc.refresh_from_db()
    sale.refresh_from_db()

    assert cheque.status == ChequeStatus.CANCELLED
    assert alloc.allocation_status == 'REVERSED'
    # الفاتورة تعود مفتوحة وغير مسددة
    assert sale.payment_status in ['unpaid', 'partially_paid']
    assert sale.amount_due == Decimal('1000.00')
    from sale.models import SalePayment
    pay = SalePayment.objects.filter(sale=sale, reference_number=cheque.voucher_number).first()
    assert pay is not None and pay.status == 'reversed'


@pytest.mark.django_db
def test_p1_collect_cheque_honors_explicitly_selected_bank_account(test_user, financial_accounts, sample_customer, account_types):
    """التحصيل يعتمد البنك المختار بالطلب صراحة بدلاً من تجاهله أو قراءة البنك القديم"""
    today = timezone.localdate()
    # إنشاء بنك ثانٍ مصرح
    bank_2 = ChartOfAccounts.objects.create(
        code='111202',
        name='البنك الأهلي - فرع ثان',
        account_type=account_types['asset'],
        level=4,
        is_leaf=True,
        is_active=True,
        currency=financial_accounts['currency'],
    )
    from financial.models import UserTreasuryAccess
    UserTreasuryAccess.objects.create(
        user=test_user,
        treasury=bank_2,
        can_deposit=True,
        can_disburse=True,
    )

    cheque = Cheque.objects.create(
        voucher_number='RV-BANK-SEL-01',
        cheque_number='CHQ-BANK-SEL-01',
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.IN_PORTFOLIO,
        customer=sample_customer,
        amount=Decimal('3500.00'),
        collected_amount=Decimal('0.00'),
        remaining_amount=Decimal('3500.00'),
        currency=financial_accounts['currency'],
        deposit_bank_account=financial_accounts['bank'],  # البنك الأصلي
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )

    # تحصيل الشيك مع تمرير bank_account_id للبنك الثاني
    res = ChequeAccountingService.collect_cheque(
        cheque=cheque,
        amount_collected=Decimal('3500.00'),
        bank_account_id=bank_2.id,
        user=test_user,
        idempotency_key='COL-BANK2-SEL-01'
    )
    je = res['journal_entry']
    assert je is not None
    # القيد المحاسبي يجب أن يكون الطرف المدين هو البنك الثاني 111202 وليس البنك الأول
    assert any(l.account == bank_2 and l.debit == Decimal('3500.00') for l in je.lines.all())
    assert not any(l.account == financial_accounts['bank'] and l.debit > 0 for l in je.lines.all())

    # سطر التسوية وسجل الشيك تم تحديثهما للبنك الثاني
    settlement = ChequeSettlementLine.objects.filter(cheque=cheque).first()
    assert settlement is not None
    assert settlement.deposit_bank_account_id == bank_2.id
    cheque.refresh_from_db()
    assert cheque.deposit_bank_account_id == bank_2.id


@pytest.mark.django_db
def test_p2_reversal_idempotency_retry_returns_cached_replay_without_integrity_error(test_user, financial_accounts, sample_customer):
    """إعادة طلب التراجع بنفس المفتاح تعيد النتيجة السابقة بأمان دون IntegrityError"""
    today = timezone.localdate()
    cheque = Cheque.objects.create(
        voucher_number='RV-REV-IDEM-01',
        cheque_number='CHQ-REV-IDEM-01',
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.IN_PORTFOLIO,
        customer=sample_customer,
        amount=Decimal('2000.00'),
        collected_amount=Decimal('0.00'),
        remaining_amount=Decimal('2000.00'),
        currency=financial_accounts['currency'],
        deposit_bank_account=financial_accounts['bank'],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )

    # تسجيل حركة إيداع لتكون قابلة للتراجع
    dep_res = ChequeAccountingService.deposit_cheque(
        cheque=cheque,
        user=test_user,
        idempotency_key='DEP-IDEM-REV-01'
    )
    assert dep_res['journal_entry'] is not None

    idem_key = 'REV-TEST-IDEM-STATIC-01'
    # طلب التراجع الأول: ينجح
    res1 = ChequeReversalService.reverse_last_action(
        cheque_id=cheque.id,
        user=test_user,
        reason='تراجع عن الإيداع بطلب العميل',
        idempotency_key=idem_key
    )
    assert res1['reversal_log'] is not None
    assert res1.get('is_retry', False) is False

    # إعادة نفس طلب التراجع بنفس المفتاح: يجب أن يُرجع نفس النتيجة ولا يرمي IntegrityError
    res2 = ChequeReversalService.reverse_last_action(
        cheque_id=cheque.id,
        user=test_user,
        reason='تراجع عن الإيداع بطلب العميل',
        idempotency_key=idem_key
    )
    assert res2.get('is_retry') is True
    assert res2['reversal_log'].id == res1['reversal_log'].id


# ==============================================================================
# 16. [P1 & P2] الفحوصات الخمسة المتقدمة لتكامل الأستاذ المساعد وذرية التخصيص
# ==============================================================================

@pytest.mark.django_db
def test_p1_credit_exposure_not_overstated_after_cheque_allocation(test_user, financial_accounts, sample_customer):
    """[P1] التأكد من أن تخصيص شيك غير محصل على فاتورة لا يضخم الانكشاف الائتماني (1,000 وليس 3,000)"""
    from customer.services.credit_exposure_service import CreditExposureService
    from customer.services.customer_subledger_service import CustomerSubledgerService
    from customer.models import CustomerTransaction
    
    today = timezone.localdate()
    # 1. إنشاء فاتورة مبيعات بـ 1,000
    sale = Sale.objects.create(
        customer=sample_customer,
        date=today,
        subtotal=Decimal("1000.00"),
        total=Decimal("1000.00"),
        total_functional=Decimal("1000.00"),
        currency=financial_accounts["currency"],
        payment_method="credit",
        created_by=test_user,
    )
    # حركة الأستاذ المساعد للفاتورة
    inv_txn = CustomerTransaction.objects.create(
        customer=sample_customer,
        transaction_type="INVOICE",
        transaction_number=sale.number,
        reference_type="SALE",
        reference_id=str(sale.id),
        issue_date=today,
        due_date=today,
        currency="EGP",
        exchange_rate=Decimal("1.000000"),
        functional_amount=Decimal("1000.00"),
        open_amount=Decimal("1000.00"),
        open_amount_functional=Decimal("1000.00"),
        status="OPEN",
    )

    # 2. إنشاء شيك غير محصل بـ 1,000
    cheque = Cheque.objects.create(
        voucher_number="RV-EXP-01",
        cheque_number="CHQ-EXP-01",
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.IN_PORTFOLIO,
        customer=sample_customer,
        amount=Decimal("1000.00"),
        currency=financial_accounts["currency"],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )

    # قبل التخصيص: رصيد الفاتورة 1000 + الشيك 1000 = الانكشاف 2000
    exp_before = CreditExposureService.calculate_customer_exposure(sample_customer.id)
    assert exp_before["total_exposure"] == Decimal("2000.00")

    # 3. تخصيص الشيك على الفاتورة
    alloc = ChequeAllocationService.allocate_cheque_to_invoice(
        cheque=cheque,
        sale=sale,
        amount=Decimal("1000.00"),
        user=test_user,
    )
    assert alloc.allocation_status == "APPLIED"

    # التحقق من أن رصيد الأستاذ المساعد للفاتورة والشيك أُغلق (CLOSED و open_amount = 0)
    inv_txn.refresh_from_db()
    assert inv_txn.open_amount == Decimal("0.00")
    assert inv_txn.status == "CLOSED"

    open_balance = CustomerSubledgerService.get_customer_open_balance(sample_customer.id)
    assert open_balance == Decimal("0.00")

    # بعد التخصيص: رصيد الفواتير المفتوحة 0 + الشيك غير المحصل 1000 = الانكشاف 1000 فقط (وليس 3000!)
    exp_after = CreditExposureService.calculate_customer_exposure(sample_customer.id)
    assert exp_after["open_ar_amount"] == Decimal("0.00")
    assert exp_after["uncollected_cheques_amount"] == Decimal("1000.00")
    assert exp_after["total_exposure"] == Decimal("1000.00")


@pytest.mark.django_db
def test_p1_advance_allocation_fails_atomically_on_gl_gateway_rejection(test_user, financial_accounts, sample_customer, monkeypatch):
    """[P1] التأكد من أن رفض أو فشل قيد تسوية الدفعة المقدمة يوقف التخصيص ولا يسيب الفاتورة مسددة"""
    today = timezone.localdate()
    sale = Sale.objects.create(
        customer=sample_customer,
        date=today,
        subtotal=Decimal("1000.00"),
        total=Decimal("1000.00"),
        total_functional=Decimal("1000.00"),
        currency=financial_accounts["currency"],
        payment_method="credit",
        created_by=test_user,
    )
    cheque = Cheque.objects.create(
        voucher_number="RV-GW-FAIL-01",
        cheque_number="CHQ-GW-FAIL-01",
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.ADVANCE_PAYMENT,
        status=ChequeStatus.COLLECTED,
        customer=sample_customer,
        amount=Decimal("1000.00"),
        collected_amount=Decimal("1000.00"),
        currency=financial_accounts["currency"],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )

    from governance.services.accounting_gateway import AccountingGateway
    def mock_create_journal_entry(*args, **kwargs):
        raise ValidationError("رفض قيد التسوية من بوابة الحوكمة المحاسبية")

    monkeypatch.setattr(AccountingGateway, "create_journal_entry", mock_create_journal_entry)

    with pytest.raises(ValidationError) as exc_info:
        ChequeAllocationService.allocate_cheque_to_invoice(
            cheque=cheque,
            sale=sale,
            amount=Decimal("1000.00"),
            user=test_user,
        )
    assert "بوابة القيود" in str(exc_info.value) or "فشل ترحيل قيد" in str(exc_info.value)

    # التأكد من التراجع الذري وعدم ترك الفاتورة مسددة
    sale.refresh_from_db()
    assert sale.payment_status == "unpaid"
    assert SalePayment.objects.filter(sale=sale).count() == 0
    assert ChequeInvoiceAllocation.objects.filter(cheque=cheque, sale=sale).count() == 0


@pytest.mark.django_db
def test_p1_historical_reconciliation_ignores_foreign_revaluation_lines(test_user, financial_accounts, sample_customer):
    """[P1] التأكد من أن تقرير التسوية التاريخية لا يضيف سطور تقييم عملة تخص فواتير أو مصادر أخرى بنفس الـ ID"""
    from cheques.services.subledger_reconciliation_service import ChequeSubledgerReconciliationService
    from financial.fx.models import FXRevaluationRun, FXRevaluationLine
    from financial.models import FiscalYear, AccountingPeriod

    today = timezone.localdate()
    cheque = Cheque.objects.create(
        voucher_number="RV-FX-ISO-01",
        cheque_number="CHQ-FX-ISO-01",
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.IN_PORTFOLIO,
        customer=sample_customer,
        amount=Decimal("1000.00"),
        currency=financial_accounts["currency"],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )

    fy, _ = FiscalYear.objects.get_or_create(
        year_code=str(today.year),
        defaults={"name": f"السنة المالية {today.year}", "start_date": today.replace(month=1, day=1), "end_date": today.replace(month=12, day=31)}
    )
    period, _ = AccountingPeriod.objects.get_or_create(
        fiscal_year=fy,
        period_number=1,
        defaults={"name": "فترة يناير", "start_date": today.replace(month=1, day=1), "end_date": today.replace(month=1, day=28), "status": "open"}
    )

    # إنشاء دورة إعادة تقييم وسطر تقييم لفاتورة مبيعات بنفس الرقم التعريفي للشيك source_id=str(cheque.id)
    fx_entry = JournalEntry.objects.create(
        number="JE-FX-TEST-001",
        date=today,
        status="posted",
        description="قيد تقييم فروق عملة",
        created_by=test_user,
    )
    run = FXRevaluationRun.objects.create(
        period=period,
        status="POSTED",
        run_date=today,
        journal_entry=fx_entry,
        total_unrealized_gain_loss=Decimal("1000.00"),
        created_by=test_user,
    )
    FXRevaluationLine.objects.create(
        run=run,
        source_type="AR_INVOICE",  # نوع مصدر مختلف
        source_id=str(cheque.id),  # نفس الـ ID الرقمي للشيك
        account=financial_accounts["bank"],
        currency=financial_accounts["currency"],
        open_foreign_amount=Decimal("1000.00"),
        old_rate=Decimal("1.000000"),
        new_rate=Decimal("2.000000"),
        old_functional_value=Decimal("1000.00"),
        new_functional_value=Decimal("2000.00"),
        unrealized_difference=Decimal("1000.00"),
    )

    # حساب القيمة الدفترية للشيك: يجب ألا يتأثر بتقييم الفاتورة ويظل 1,000 فقط (وليس 2,000)
    carrying_val = ChequeSubledgerReconciliationService.calculate_cheque_carrying_value_at_date(cheque, today)
    assert carrying_val == Decimal("1000.00")


@pytest.mark.django_db
def test_p2_multiple_allocations_of_same_cheque_to_same_invoice(test_user, financial_accounts, sample_customer):
    """[P2] التأكد من نجاح تخصيص نفس الشيك على نفس الفاتورة على دفعتين (300 ثم 700) دون IntegrityError"""
    today = timezone.localdate()
    sale = Sale.objects.create(
        customer=sample_customer,
        date=today,
        subtotal=Decimal("1000.00"),
        total=Decimal("1000.00"),
        total_functional=Decimal("1000.00"),
        currency=financial_accounts["currency"],
        payment_method="credit",
        created_by=test_user,
    )
    cheque = Cheque.objects.create(
        voucher_number="RV-PARTIAL-01",
        cheque_number="CHQ-PARTIAL-01",
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.IN_PORTFOLIO,
        customer=sample_customer,
        amount=Decimal("1000.00"),
        currency=financial_accounts["currency"],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )

    # التخصيص الأول: 300
    alloc1 = ChequeAllocationService.allocate_cheque_to_invoice(
        cheque=cheque,
        sale=sale,
        amount=Decimal("300.00"),
        user=test_user,
    )
    assert alloc1.allocated_amount == Decimal("300.00")

    # التخصيص الثاني لنفس الشيك ونفس الفاتورة: 700
    alloc2 = ChequeAllocationService.allocate_cheque_to_invoice(
        cheque=cheque,
        sale=sale,
        amount=Decimal("700.00"),
        user=test_user,
    )
    assert alloc2.allocated_amount == Decimal("700.00")

    sale.refresh_from_db()
    assert sale.amount_paid == Decimal("1000.00")
    assert sale.payment_status == "paid"

    # عكس التخصيص الثاني: ينجح دون تعارض المرجع
    ChequeAllocationService.reverse_cheque_allocation(
        allocation=alloc2,
        user=test_user,
        reason="عكس التخصيص الثاني لاختبار المرجع الفريد"
    )
    alloc2.refresh_from_db()
    assert alloc2.allocation_status == "REVERSED"


@pytest.mark.django_db
def test_p2_reversal_rejects_idempotency_key_from_different_action_or_cheque(test_user, financial_accounts, sample_customer):
    """[P2] التأكد من أن طلب التراجع يرفض مفتاح عدم التكرار إذا كان يخص حركة أخرى أو شيك آخر"""
    today = timezone.localdate()
    cheque1 = Cheque.objects.create(
        voucher_number="RV-REV-MIS-01",
        cheque_number="CHQ-REV-MIS-01",
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.IN_PORTFOLIO,
        customer=sample_customer,
        amount=Decimal("1000.00"),
        currency=financial_accounts["currency"],
        deposit_bank_account=financial_accounts["bank"],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )
    # تسجيل حركة إيداع بمفتاح ثابت
    idem_key_dep = "DEP-STATIC-KEY-01"
    ChequeAccountingService.deposit_cheque(
        cheque=cheque1,
        user=test_user,
        idempotency_key=idem_key_dep,
    )

    # استخدام نفس مفتاح حركة الإيداع في طلب تراجع: يجب أن يرفضه لأنه يخص DEPOSIT وليس REVERSE_ACTION
    with pytest.raises(ValidationError) as exc_info:
        ChequeReversalService.reverse_last_action(
            cheque_id=cheque1.id,
            user=test_user,
            reason="محاولة استخدام مفتاح إيداع في تراجع",
            idempotency_key=idem_key_dep,
        )
    assert "المفتاح مستخدم مسبقاً لعملية أخرى" in str(exc_info.value) or "تعارض في مفتاح عدم التكرار" in str(exc_info.value)


# ==============================================================================
# 17. [P1] الفحوصات الثلاثة المتقدمة للارتداد وتعدد التخصيصات وتقييم أوراق الدفع
# ==============================================================================

@pytest.mark.django_db
def test_p1_bounced_cheque_restores_customer_exposure_without_ghost_credit(test_user, financial_accounts, sample_customer):
    """[P1] التأكد من أن ارتداد الشيك لا يخفي مديونية العميل من الانكشاف الائتماني (1,000 وليس صفر)"""
    from customer.services.credit_exposure_service import CreditExposureService
    from customer.models import CustomerTransaction

    today = timezone.localdate()
    # فاتورة 1,000
    sale = Sale.objects.create(
        customer=sample_customer,
        date=today,
        subtotal=Decimal("1000.00"),
        total=Decimal("1000.00"),
        total_functional=Decimal("1000.00"),
        currency=financial_accounts["currency"],
        payment_method="credit",
        created_by=test_user,
    )
    inv_txn = CustomerTransaction.objects.create(
        customer=sample_customer,
        transaction_type="INVOICE",
        transaction_number=sale.number,
        reference_type="SALE",
        reference_id=str(sale.id),
        issue_date=today,
        due_date=today,
        currency="EGP",
        exchange_rate=Decimal("1.000000"),
        functional_amount=Decimal("1000.00"),
        open_amount=Decimal("1000.00"),
        open_amount_functional=Decimal("1000.00"),
        status="OPEN",
    )
    cheque = Cheque.objects.create(
        voucher_number="RV-BNC-EXP-01",
        cheque_number="CHQ-BNC-EXP-01",
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.UNDER_COLLECTION,
        customer=sample_customer,
        amount=Decimal("1000.00"),
        currency=financial_accounts["currency"],
        deposit_bank_account=financial_accounts["bank"],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )
    alloc = ChequeAllocationService.allocate_cheque_to_invoice(
        cheque=cheque,
        sale=sale,
        amount=Decimal("1000.00"),
        user=test_user,
    )
    assert alloc.allocation_status == "APPLIED"

    # ارتداد كامل للشيك
    ChequeAccountingService.bounce_cheque(
        cheque=cheque,
        user=test_user,
        reason="رفض الشيك لعدم كفاية الرصيد",
        idempotency_key="BNC-EXP-TEST-01"
    )
    sale.refresh_from_db()
    assert sale.payment_status == "unpaid"

    # التحقق من أن الانكشاف الائتماني يعكس مديونية الفاتورة 1,000 ولا يُصفر برصيد دائن وهمي
    exp = CreditExposureService.calculate_customer_exposure(sample_customer.id)
    assert exp["open_ar_amount"] == Decimal("1000.00")
    assert exp["total_exposure"] == Decimal("1000.00")


@pytest.mark.django_db
def test_p1_partial_bounce_with_multiple_allocations_prorates_accurately(test_user, financial_accounts, sample_customer):
    """[P1] التأكد من أن تعدد التخصيصات (300 ثم 700) يعمل بدقة عند عكس أحدهما أو عند الارتداد الجزئي (600 محصل)"""
    from customer.services.credit_exposure_service import CreditExposureService
    today = timezone.localdate()
    sale = Sale.objects.create(
        customer=sample_customer,
        date=today,
        subtotal=Decimal("1000.00"),
        total=Decimal("1000.00"),
        total_functional=Decimal("1000.00"),
        currency=financial_accounts["currency"],
        payment_method="credit",
        created_by=test_user,
    )
    cheque = Cheque.objects.create(
        voucher_number="RV-MULTI-BNC-01",
        cheque_number="CHQ-MULTI-BNC-01",
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.UNDER_COLLECTION,
        customer=sample_customer,
        amount=Decimal("1000.00"),
        currency=financial_accounts["currency"],
        deposit_bank_account=financial_accounts["bank"],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )

    # تخصيص 300 ثم 700
    alloc1 = ChequeAllocationService.allocate_cheque_to_invoice(
        cheque=cheque,
        sale=sale,
        amount=Decimal("300.00"),
        user=test_user,
    )
    alloc2 = ChequeAllocationService.allocate_cheque_to_invoice(
        cheque=cheque,
        sale=sale,
        amount=Decimal("700.00"),
        user=test_user,
    )
    assert sale.payments.filter(status="posted").count() == 2

    # فحص 1: عكس تخصيص الـ 300 فقط يبقي سداد الـ 700 سارياً (المسدد 700 وليس صفراً)
    ChequeAllocationService.reverse_cheque_allocation(
        allocation=alloc1,
        user=test_user,
        reason="عكس دفعة 300 فقط"
    )
    sale.refresh_from_db()
    assert sale.amount_paid == Decimal("700.00")
    assert sale.payment_status == "partially_paid"

    # إعادة تطبيق التخصيص 300 لفحص الارتداد الجزئي
    alloc1_re = ChequeAllocationService.allocate_cheque_to_invoice(
        cheque=cheque,
        sale=sale,
        amount=Decimal("300.00"),
        user=test_user,
    )
    sale.refresh_from_db()
    assert sale.amount_paid == Decimal("1000.00")

    # فحص 2: تحصيل 600 من 1,000 ثم ارتداد الباقي يترك المسدد 600 تماماً (وليس 360!)
    ChequeAccountingService.collect_cheque(
        cheque=cheque,
        user=test_user,
        amount=Decimal("600.00"),
        target_status=ChequeStatus.PARTIALLY_COLLECTED,
        bank_account=financial_accounts["bank"],
        idempotency_key="COLL-PARTIAL-600-01"
    )
    ChequeAccountingService.bounce_cheque(
        cheque=cheque,
        user=test_user,
        reason="ارتداد المتبقي 400",
        idempotency_key="BNC-PARTIAL-400-01"
    )
    sale.refresh_from_db()
    # 300 * 0.6 = 180 و 700 * 0.6 = 420 -> الإجمالي 600.00
    assert sale.amount_paid == Decimal("600.00")
    assert sale.amount_due == Decimal("400.00")

    # الانكشاف الائتماني يجب أن يظهر المتبقي غير المسدد 400.00
    exp = CreditExposureService.calculate_customer_exposure(sample_customer.id)
    assert exp["open_ar_amount"] == Decimal("400.00")
    assert exp["total_exposure"] == Decimal("400.00")


@pytest.mark.django_db
def test_p1_payable_cheque_fx_revaluation_sign_in_historical_carrying_value(test_user, financial_accounts, sample_supplier):
    """[P1] التأكد من أن إشارة تقييم العملة لأوراق الدفع تزيد القيمة الدفترية عند الخسارة (52,000 وليس 48,000)"""
    from cheques.services.subledger_reconciliation_service import ChequeSubledgerReconciliationService
    from financial.fx.models import FXRevaluationRun, FXRevaluationLine
    from financial.models import FiscalYear, AccountingPeriod, Currency

    today = timezone.localdate()
    usd, _ = Currency.objects.get_or_create(code="USD", defaults={"name": "US Dollar", "symbol": "$"})
    
    # شيك أوراق دفع بـ 1,000 دولار، سعر الصرف الأصلي 50
    cheque = Cheque.objects.create(
        voucher_number="PV-FX-PAY-01",
        cheque_number="CHQ-FX-PAY-01",
        cheque_type=ChequeType.PAYABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.ISSUED,
        supplier=sample_supplier,
        amount=Decimal("1000.00"),
        currency=usd,
        original_exchange_rate=Decimal("50.000000"),
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )
    assert cheque.functional_amount == Decimal("50000.00")

    fy, _ = FiscalYear.objects.get_or_create(
        year_code=f"FY-PAY-{today.year}",
        defaults={"name": f"سنة {today.year}", "start_date": today.replace(month=1, day=1), "end_date": today.replace(month=12, day=31)}
    )
    period, _ = AccountingPeriod.objects.get_or_create(
        fiscal_year=fy,
        period_number=2,
        defaults={"name": "فترة فبراير", "start_date": today.replace(month=1, day=1), "end_date": today.replace(month=1, day=28), "status": "open"}
    )
    fx_entry = JournalEntry.objects.create(
        number="JE-FX-PAY-TEST-001",
        date=today,
        status="posted",
        description="قيد تقييم أوراق دفع",
        created_by=test_user,
    )
    run = FXRevaluationRun.objects.create(
        period=period,
        status="POSTED",
        run_date=today,
        journal_entry=fx_entry,
        total_unrealized_gain_loss=Decimal("-2000.00"),
        created_by=test_user,
    )
    # فرق التقييم مسجل في نموذج FX كـ (old - closing) = 50,000 - 52,000 = -2,000 (خسارة فروق عملة)
    FXRevaluationLine.objects.create(
        run=run,
        source_type="NOTES_PAYABLE",
        source_id=str(cheque.id),
        account=financial_accounts["bank"],
        currency=usd,
        open_foreign_amount=Decimal("1000.00"),
        old_rate=Decimal("50.000000"),
        new_rate=Decimal("52.000000"),
        old_functional_value=Decimal("50000.00"),
        new_functional_value=Decimal("52000.00"),
        unrealized_difference=Decimal("-2000.00"),
    )

    # القيمة الدفترية للالتزام يجب أن تكون 52,000.00 (وليس 48,000.00)
    carrying_val = ChequeSubledgerReconciliationService.compute_historical_carrying_value(cheque, today)
    assert carrying_val == Decimal("52000.00")


@pytest.mark.django_db
def test_p1_reversal_of_bounce_restores_credit_exposure_without_doubling(test_user, financial_accounts, sample_customer):
    """
    [P1] التحقق من أن التراجع عن الارتداد (كلي أو جزئي) يعيد الانكشاف الائتماني لقيمته الصحيحة دون مضاعفة
    - ارتداد كامل ثم تراجع: الانكشاف يرجع 1,000 بدل 2,000.
    - تحصيل 600 ثم ارتداد الباقي والتراجع: يرجع 400 بدل 800.
    """
    from cheques.services.reversal_service import ChequeReversalService
    from customer.services.credit_exposure_service import CreditExposureService
    from sale.models import Sale

    today = timezone.localdate()

    # --- الحالة الأولى: ارتداد كامل ثم تراجع ---
    sale1 = Sale.objects.create(
        customer=sample_customer,
        date=today,
        subtotal=Decimal("1000.00"),
        total=Decimal("1000.00"),
        total_functional=Decimal("1000.00"),
        currency=financial_accounts["currency"],
        payment_method="credit",
        status="confirmed",
        payment_status="unpaid",
        created_by=test_user,
    )

    cheque1 = Cheque.objects.create(
        voucher_number="RV-EXP-REV-01",
        cheque_number="CHQ-EXP-REV-01",
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.UNDER_COLLECTION,
        customer=sample_customer,
        amount=Decimal("1000.00"),
        currency=financial_accounts["currency"],
        deposit_bank_account=financial_accounts["bank"],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )

    ChequeAllocationService.allocate_cheque_to_invoice(
        cheque=cheque1,
        sale=sale1,
        amount=Decimal("1000.00"),
        user=test_user,
    )

    # قبل الارتداد: الفاتورة مسددة، الانكشاف = 1,000 (شيك غير محصل)
    exp_before = CreditExposureService.calculate_customer_exposure(sample_customer.id)
    assert exp_before["total_exposure"] == Decimal("1000.00")
    assert exp_before["uncollected_cheques_amount"] == Decimal("1000.00")
    assert exp_before["open_ar_amount"] == Decimal("0.00")

    # ارتداد كامل
    ChequeAccountingService.bounce_cheque(
        cheque=cheque1,
        user=test_user,
        reason="شيك بدون رصيد",
        idempotency_key="BNC-EXP-REV-01"
    )
    exp_bounced = CreditExposureService.calculate_customer_exposure(sample_customer.id)
    assert exp_bounced["total_exposure"] == Decimal("1000.00")
    assert exp_bounced["open_ar_amount"] == Decimal("1000.00")
    assert exp_bounced["uncollected_cheques_amount"] == Decimal("0.00")

    # التراجع عن الارتداد
    ChequeReversalService.reverse_last_action(
        cheque=cheque1,
        user=test_user,
        reason="إلغاء حركة الارتداد بالخطأ",
        idempotency_key="REV-BNC-EXP-01"
    )
    exp_after_rev = CreditExposureService.calculate_customer_exposure(sample_customer.id)
    # الانكشاف يجب أن يكون 1,000 فقط (شيك غير محصل مع إغلاق رصيد الفاتورة المفتوح) وليس 2,000
    assert exp_after_rev["open_ar_amount"] == Decimal("0.00")
    assert exp_after_rev["uncollected_cheques_amount"] == Decimal("1000.00")
    assert exp_after_rev["total_exposure"] == Decimal("1000.00")

    # --- الحالة الثانية: تحصيل 600 ثم ارتداد الباقي (400) ثم التراجع ---
    # إنشاء عميل جديد للفصل التام
    cust2 = Customer.objects.create(name="عميل ارتداد جزئي P1", code="CUST-P1-02")
    SubledgerAccountService.get_or_create_customer_account(cust2)
    cust2.refresh_from_db()

    sale2 = Sale.objects.create(
        customer=cust2,
        date=today,
        subtotal=Decimal("1000.00"),
        total=Decimal("1000.00"),
        total_functional=Decimal("1000.00"),
        currency=financial_accounts["currency"],
        payment_method="credit",
        status="confirmed",
        payment_status="unpaid",
        created_by=test_user,
    )

    cheque2 = Cheque.objects.create(
        voucher_number="RV-EXP-REV-02",
        cheque_number="CHQ-EXP-REV-02",
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.UNDER_COLLECTION,
        customer=cust2,
        amount=Decimal("1000.00"),
        currency=financial_accounts["currency"],
        deposit_bank_account=financial_accounts["bank"],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )

    ChequeAllocationService.allocate_cheque_to_invoice(
        cheque=cheque2,
        sale=sale2,
        amount=Decimal("1000.00"),
        user=test_user,
    )

    # تحصيل 600
    ChequeAccountingService.collect_cheque(
        cheque=cheque2,
        user=test_user,
        amount=Decimal("600.00"),
        target_status=ChequeStatus.PARTIALLY_COLLECTED,
        bank_account=financial_accounts["bank"],
        idempotency_key="COLL-EXP-REV-02"
    )
    # ارتداد الباقي (400)
    ChequeAccountingService.bounce_cheque(
        cheque=cheque2,
        user=test_user,
        reason="ارتداد 400",
        idempotency_key="BNC-EXP-REV-02"
    )
    exp2_bounced = CreditExposureService.calculate_customer_exposure(cust2.id)
    assert exp2_bounced["total_exposure"] == Decimal("400.00")
    assert exp2_bounced["open_ar_amount"] == Decimal("400.00")

    # التراجع عن الارتداد
    ChequeReversalService.reverse_last_action(
        cheque=cheque2,
        user=test_user,
        reason="تراجع عن ارتداد 400",
        idempotency_key="REV-BNC-EXP-02"
    )
    exp2_after_rev = CreditExposureService.calculate_customer_exposure(cust2.id)
    # الانكشاف يجب أن يكون 400.00 فقط (وليس 800.00)
    assert exp2_after_rev["open_ar_amount"] == Decimal("0.00")
    assert exp2_after_rev["uncollected_cheques_amount"] == Decimal("400.00")
    assert exp2_after_rev["total_exposure"] == Decimal("400.00")


@pytest.mark.django_db
def test_p1_reversal_of_bounce_preserves_distinct_sale_payment_allocations(test_user, financial_accounts, sample_customer):
    """
    [P1] التحقق من أن التراجع عن الارتداد لشيك متعدد التخصيصات (300 و700 لنفس الفاتورة)
    يحدّث كل دفعة SalePayment بمبلغها المخصص بالتحديد، ويعيد السداد إلى 1,000 (بدل 600)
    """
    from cheques.services.reversal_service import ChequeReversalService
    from sale.models import Sale, SalePayment

    today = timezone.localdate()
    sale = Sale.objects.create(
        customer=sample_customer,
        date=today,
        subtotal=Decimal("1000.00"),
        total=Decimal("1000.00"),
        total_functional=Decimal("1000.00"),
        currency=financial_accounts["currency"],
        payment_method="credit",
        status="confirmed",
        payment_status="unpaid",
        created_by=test_user,
    )

    cheque = Cheque.objects.create(
        voucher_number="RV-PAY-LINK-01",
        cheque_number="CHQ-PAY-LINK-01",
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.UNDER_COLLECTION,
        customer=sample_customer,
        amount=Decimal("1000.00"),
        currency=financial_accounts["currency"],
        deposit_bank_account=financial_accounts["bank"],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )

    # تخصيص 300 و 700
    alloc1 = ChequeAllocationService.allocate_cheque_to_invoice(
        cheque=cheque,
        sale=sale,
        amount=Decimal("300.00"),
        user=test_user,
    )
    alloc2 = ChequeAllocationService.allocate_cheque_to_invoice(
        cheque=cheque,
        sale=sale,
        amount=Decimal("700.00"),
        user=test_user,
    )
    sale.refresh_from_db()
    assert sale.amount_paid == Decimal("1000.00")

    # ارتداد الشيك
    ChequeAccountingService.bounce_cheque(
        cheque=cheque,
        user=test_user,
        reason="ارتداد الشيك بالكامل",
        idempotency_key="BNC-PAY-LINK-01"
    )
    sale.refresh_from_db()
    assert sale.amount_paid == Decimal("0.00")

    # التراجع عن الارتداد
    ChequeReversalService.reverse_last_action(
        cheque=cheque,
        user=test_user,
        reason="تراجع عن الارتداد",
        idempotency_key="REV-PAY-LINK-01"
    )
    sale.refresh_from_db()

    # التأكد من عودة السداد إلى 1,000.00 بالكامل (وليس 600.00)
    assert sale.amount_paid == Decimal("1000.00")
    assert sale.amount_due == Decimal("0.00")
    assert sale.payment_status == "paid"

    # التحقق من مبالغ الدفعات المفردة
    alloc1.refresh_from_db()
    alloc2.refresh_from_db()
    assert alloc1.sale_payment.status == "posted"
    assert alloc1.sale_payment.amount == Decimal("300.00")
    assert alloc2.sale_payment.status == "posted"
    assert alloc2.sale_payment.amount == Decimal("700.00")


@pytest.mark.django_db
def test_p1_reallocation_of_advance_payment_creates_fresh_journal_entry(test_user, financial_accounts, sample_customer):
    """
    [P1] التحقق من أن تخصيص دفعة مقدمة ثم عكسها ثم إعادة تخصيصها لنفس الفاتورة وبنفس المبلغ
    يولد قيداً يومياً جديداً تماماً بدلاً من إعادة ربط القيد القديم المعكوس
    """
    from sale.models import Sale

    today = timezone.localdate()
    sale = Sale.objects.create(
        customer=sample_customer,
        date=today,
        subtotal=Decimal("1000.00"),
        total=Decimal("1000.00"),
        total_functional=Decimal("1000.00"),
        currency=financial_accounts["currency"],
        payment_method="credit",
        status="confirmed",
        payment_status="unpaid",
        created_by=test_user,
    )

    adv_cheque = Cheque.objects.create(
        voucher_number="RV-ADV-JE-01",
        cheque_number="CHQ-ADV-JE-01",
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.ADVANCE_PAYMENT,
        status=ChequeStatus.IN_PORTFOLIO,
        customer=sample_customer,
        amount=Decimal("1000.00"),
        currency=financial_accounts["currency"],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )

    # 1. التخصيص الأول
    alloc1 = ChequeAllocationService.allocate_cheque_to_invoice(
        cheque=adv_cheque,
        sale=sale,
        amount=Decimal("1000.00"),
        user=test_user,
    )
    je1 = alloc1.journal_entry
    assert je1 is not None
    assert je1.status == "posted"

    # 2. عكس التخصيص
    ChequeAllocationService.reverse_cheque_allocation(
        allocation=alloc1,
        user=test_user,
        reason="عكس التخصيص للاختبار"
    )
    je1.refresh_from_db()
    assert je1.reversed_by_entry is not None

    # 3. إعادة تخصيص نفس المبلغ لنفس الفاتورة
    alloc2 = ChequeAllocationService.allocate_cheque_to_invoice(
        cheque=adv_cheque,
        sale=sale,
        amount=Decimal("1000.00"),
        user=test_user,
    )
    je2 = alloc2.journal_entry
    assert je2 is not None
    # يجب أن يكون قيداً جديداً سارياً (وليس القيد القديم المعكوس)
    assert je2.id != je1.id
    assert je2.status == "posted"
    assert je2.reversed_by_entry is None


@pytest.mark.django_db
def test_p1_clear_foreign_payable_cheque_handles_spot_rate_and_realized_fx(test_user, financial_accounts, sample_supplier):
    """
    [P1] التحقق من أن صرف الشيك الأجنبي (CLEAR) يعتمد سعر الصرف الفعلي عند الصرف
    ويثبت خروج النقدية بالقيمة الفعلية من البنك مع تسجيل فروق العملة المحققة
    - شيك بـ 1,000 دولار، سعر أصلي 50، صُرف بسعر 52:
      * البنك يُقيد عليه دائن بـ 52,000 (بدل 50,000).
      * أوراق الدفع تُقفل بـ 50,000.
      * خسائر فروق عملة محققة مدينة بـ 2,000.
    """
    from financial.models import Currency

    today = timezone.localdate()
    usd, _ = Currency.objects.get_or_create(code="USD", defaults={"name": "US Dollar", "symbol": "$"})

    cheque = Cheque.objects.create(
        voucher_number="PV-CLR-FX-01",
        cheque_number="CHQ-CLR-FX-01",
        cheque_type=ChequeType.PAYABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.ISSUED,
        supplier=sample_supplier,
        amount=Decimal("1000.00"),
        currency=usd,
        original_exchange_rate=Decimal("50.000000"),
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )
    assert cheque.functional_amount == Decimal("50000.00")

    # صرف الشيك بسعر صرف فعلي 52.00
    res = ChequeAccountingService.clear_payable_cheque(
        cheque=cheque,
        user=test_user,
        exchange_rate=Decimal("52.000000"),
        bank_account_id=financial_accounts["bank"].id,
        idempotency_key="CLR-FX-SPOT-01"
    )

    cheque.refresh_from_db()
    assert cheque.status == ChequeStatus.CLEARED
    assert cheque.remaining_amount == Decimal("0.00")
    assert cheque.remaining_functional == Decimal("0.00")

    je = res["journal_entry"]
    assert je is not None
    assert je.status == "posted"

    lines = list(je.lines.all())
    bank_line = next((l for l in lines if l.account_id == financial_accounts["bank"].id), None)
    np_line = next((l for l in lines if l.account_id == financial_accounts["notes_pay"].id), None)
    fx_line = next((l for l in lines if "خسائر فروق" in l.description or "أرباح فروق" in l.description), None)

    assert bank_line is not None
    assert np_line is not None
    assert fx_line is not None

    # البنك دائن بـ 52,000 (سعر الصرف الفعلي)
    assert bank_line.credit == Decimal("52000.00")
    assert bank_line.debit == Decimal("0.00")

    # أوراق الدفع مدينة بـ 50,000 (القيمة الدفترية الأصلية)
    assert np_line.debit == Decimal("50000.00")
    assert np_line.credit == Decimal("0.00")

    # خسائر فروق العملة مدينة بـ 2,000
    assert fx_line.debit == Decimal("2000.00")
    assert fx_line.credit == Decimal("0.00")

    # توازن القيد
    assert sum(l.debit for l in lines) == Decimal("52000.00")
    assert sum(l.credit for l in lines) == Decimal("52000.00")


@pytest.mark.django_db
def test_p1_reversal_of_clear_and_convert_guarantee_restores_all_fields(test_user, financial_accounts, sample_supplier, sample_customer):
    """
    [P1] التحقق من أن التراجع عن الحركات يستعيد كافة الحقول التي غيرتها الحركة:
    - عكس صرف شيك دفع: استعادة رصيده المتبقي (1,000 بدل 0) وإلغاء تاريخ ومسؤول الصرف.
    - عكس تحويل شيك الضمان: استعادة غرض الشيك كشيك ضمان (SECURITY_GUARANTEE) بدلاً من البقاء تشغيلياً.
    """
    from cheques.services.reversal_service import ChequeReversalService

    today = timezone.localdate()

    # 1. فحص عكس صرف شيك الدفع
    pay_cheque = Cheque.objects.create(
        voucher_number="PV-REV-CLR-01",
        cheque_number="CHQ-REV-CLR-01",
        cheque_type=ChequeType.PAYABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.ISSUED,
        supplier=sample_supplier,
        amount=Decimal("1000.00"),
        currency=financial_accounts["currency"],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )
    # صرف الشيك
    ChequeAccountingService.clear_payable_cheque(
        cheque=pay_cheque,
        user=test_user,
        bank_account_id=financial_accounts["bank"].id,
        idempotency_key="CLR-REV-TEST-01"
    )
    pay_cheque.refresh_from_db()
    assert pay_cheque.status == ChequeStatus.CLEARED
    assert pay_cheque.remaining_amount == Decimal("0.00")
    assert pay_cheque.cleared_at is not None

    # التراجع عن حركة الصرف
    ChequeReversalService.reverse_last_action(
        cheque=pay_cheque,
        user=test_user,
        reason="تراجع عن الصرف بالخطأ",
        idempotency_key="REV-CLR-TEST-01"
    )
    pay_cheque.refresh_from_db()
    assert pay_cheque.status == ChequeStatus.ISSUED
    assert pay_cheque.remaining_amount == Decimal("1000.00")
    assert pay_cheque.remaining_functional == Decimal("1000.00")
    assert pay_cheque.cleared_at is None
    assert pay_cheque.cleared_by is None

    # 2. فحص عكس تحويل شيك الضمان
    sec_cheque = Cheque.objects.create(
        voucher_number="RV-REV-CONV-01",
        cheque_number="CHQ-REV-CONV-01",
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.SECURITY_GUARANTEE,
        status=ChequeStatus.IN_PORTFOLIO,
        customer=sample_customer,
        amount=Decimal("5000.00"),
        currency=financial_accounts["currency"],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )
    # تحويله إلى تشغيلي
    ChequeAccountingService.convert_guarantee(
        cheque=sec_cheque,
        user=test_user,
        new_purpose=ChequePurpose.INVOICE_SETTLEMENT,
        idempotency_key="CONV-REV-TEST-01"
    )
    sec_cheque.refresh_from_db()
    assert sec_cheque.purpose == ChequePurpose.INVOICE_SETTLEMENT

    # التراجع عن تحويل الضمان
    ChequeReversalService.reverse_last_action(
        cheque=sec_cheque,
        user=test_user,
        reason="تراجع عن تحويل الضمان",
        idempotency_key="REV-CONV-TEST-01"
    )
    sec_cheque.refresh_from_db()
    assert sec_cheque.purpose == ChequePurpose.SECURITY_GUARANTEE


@pytest.mark.django_db
def test_p1_allocation_reversal_aborts_and_rolls_back_if_gl_reversal_fails(test_user, financial_accounts, sample_customer, monkeypatch):
    """
    [P1] التحقق من أن فشل عكس قيد اليومية المرتبط بالتخصيص يوقف العملية بالكامل ويرجع التغييرات (Rollback)
    بحيث لا يتحول التخصيص إلى REVERSED ولا تتغير الفاتورة إذا لم يُعكس القيد بنجاح
    """
    from sale.models import Sale
    from financial.services.ledger_core_service import LedgerCoreService

    today = timezone.localdate()
    sale = Sale.objects.create(
        customer=sample_customer,
        date=today,
        subtotal=Decimal("1000.00"),
        total=Decimal("1000.00"),
        total_functional=Decimal("1000.00"),
        currency=financial_accounts["currency"],
        payment_method="credit",
        status="confirmed",
        payment_status="unpaid",
        created_by=test_user,
    )

    adv_cheque = Cheque.objects.create(
        voucher_number="RV-FAIL-GL-01",
        cheque_number="CHQ-FAIL-GL-01",
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.ADVANCE_PAYMENT,
        status=ChequeStatus.IN_PORTFOLIO,
        customer=sample_customer,
        amount=Decimal("1000.00"),
        currency=financial_accounts["currency"],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )

    alloc = ChequeAllocationService.allocate_cheque_to_invoice(
        cheque=adv_cheque,
        sale=sale,
        amount=Decimal("1000.00"),
        user=test_user,
    )
    assert alloc.allocation_status == "APPLIED"
    sale.refresh_from_db()
    assert sale.payment_status == "paid"

    # محاكاة فشل خدمة عكس القيود
    def mock_reverse_entry(*args, **kwargs):
        raise RuntimeError("محاكاة فشل ترحيل قيد اليومية العكسي")

    monkeypatch.setattr(LedgerCoreService, "reverse_entry", mock_reverse_entry)

    # محاولة عكس التخصيص يجب أن تثير خطأ ValidationError
    with pytest.raises(ValidationError) as exc_info:
        ChequeAllocationService.reverse_cheque_allocation(
            allocation=alloc,
            user=test_user,
            reason="اختبار فشل القيد العاكس"
        )
    assert "فشل عكس قيد اليومية" in str(exc_info.value)

    # التحقق من أن حالة التخصيص والفاتورة تراجعت ذرياً ولم تتغير
    alloc.refresh_from_db()
    assert alloc.allocation_status == "APPLIED"
    sale.refresh_from_db()
    assert sale.payment_status == "paid"
    assert sale.amount_paid == Decimal("1000.00")


@pytest.mark.django_db
def test_p1_cross_currency_allocation_is_explicitly_rejected(test_user, financial_accounts, sample_customer):
    """
    [P1] التحقق من الرفض الصريح لتخصيص شيك بعملة مختلفة عن عملة الفاتورة
    (مثلاً شيك بالدولار على فاتورة بالجنيه المصري) لمنع تباين الأستاذ المساعد عن الفاتورة
    """
    from sale.models import Sale
    from financial.models import Currency

    today = timezone.localdate()
    usd, _ = Currency.objects.get_or_create(code="USD", defaults={"name": "US Dollar", "symbol": "$"})

    # فاتورة بالجنيه المصري EGP
    sale = Sale.objects.create(
        customer=sample_customer,
        date=today,
        subtotal=Decimal("1000.00"),
        total=Decimal("1000.00"),
        total_functional=Decimal("1000.00"),
        currency=financial_accounts["currency"],
        payment_method="credit",
        status="confirmed",
        payment_status="unpaid",
        created_by=test_user,
    )

    # شيك بالدولار الأمريكي USD
    cheque = Cheque.objects.create(
        voucher_number="RV-CROSS-CURR-01",
        cheque_number="CHQ-CROSS-CURR-01",
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.UNDER_COLLECTION,
        customer=sample_customer,
        amount=Decimal("100.00"),
        currency=usd,
        original_exchange_rate=Decimal("50.000000"),
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )

    # محاولة التخصيص يجب أن تُرفض صراحةً بخطأ تحقق واضح
    with pytest.raises(ValidationError) as exc_info:
        ChequeAllocationService.allocate_cheque_to_invoice(
            cheque=cheque,
            sale=sale,
            amount=Decimal("100.00"),
            user=test_user,
        )
    assert "يجب تطابق عملة الشيك والفاتورة" in str(exc_info.value)

    # التأكد من عدم إنشاء أي تخصيص وبقاء الفاتورة بدون سداد
    assert cheque.invoice_allocations.count() == 0
    sale.refresh_from_db()
    assert sale.amount_paid == Decimal("0.00")
    assert sale.amount_due == Decimal("1000.00")


@pytest.mark.django_db
def test_p1_clear_payable_cheque_prioritizes_params_bank_account_consistently(test_user, financial_accounts, sample_supplier):
    """
    [P1] التحقق من تطابق اختيار الحساب البنكي بين القيد وسجل الشيك عند تمرير بنك بديل في الصرف
    """
    from financial.models import ChartOfAccounts

    today = timezone.localdate()

    # بنك ثانٍ بديل للصرف
    alt_bank, _ = ChartOfAccounts.objects.get_or_create(
        code="11112",
        defaults={
            "name": "بنك بديل للصرف",
            "account_type": financial_accounts["bank"].account_type,
            "level": 4,
            "is_leaf": True,
            "is_active": True,
            "currency": financial_accounts["currency"],
        }
    )

    # شيك دفع مرتبط أصلاً بالبنك الافتراضي
    cheque = Cheque.objects.create(
        voucher_number="PV-PRIO-BANK-01",
        cheque_number="CHQ-PRIO-BANK-01",
        cheque_type=ChequeType.PAYABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.ISSUED,
        supplier=sample_supplier,
        amount=Decimal("2000.00"),
        currency=financial_accounts["currency"],
        deposit_bank_account=financial_accounts["bank"],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )

    # صرف الشيك بتمرير البنك البديل alt_bank
    res = ChequeAccountingService.clear_payable_cheque(
        cheque=cheque,
        user=test_user,
        bank_account_id=alt_bank.id,
        idempotency_key="CLR-ALT-BANK-01"
    )

    cheque.refresh_from_db()
    # سجل الشيك يجب أن يكون مرتبطاً بالبنك البديل
    assert cheque.deposit_bank_account_id == alt_bank.id

    # القيد يجب أن يقيد الخصم (الطرف الدائن) من البنك البديل وليس القديم
    je = res["journal_entry"]
    lines = list(je.lines.all())
    bank_lines = [l for l in lines if l.credit > Decimal("0.00")]
    assert len(bank_lines) == 1
    assert bank_lines[0].account_id == alt_bank.id
    assert bank_lines[0].credit == Decimal("2000.00")


@pytest.mark.django_db
def test_p1_bounce_raises_validation_error_and_rolls_back_if_gl_reversal_fails(test_user, financial_accounts, sample_customer, monkeypatch):
    """
    رفض عكس القيد أثناء الارتداد يجب ألا يُبتلع وأن يجهض العملية ذرياً بالكامل دون ترك حالة ناقصة
    """
    from financial.services.ledger_core_service import LedgerCoreService
    today = timezone.localdate()

    # إنشاء فاتورة
    sale = Sale.objects.create(
        number="INV-BOUNCE-ROLLBACK-01",
        customer=sample_customer,
        date=today,
        subtotal=Decimal("1500.00"),
        total=Decimal("1500.00"),
        payment_method="credit",
        payment_status="unpaid",
        status="confirmed",
        created_by=test_user,
    )

    # إنشاء شيك دفعة مقدمة مع قيد تخصيص
    cheque = Cheque.objects.create(
        voucher_number="RV-BNCE-FAIL-01",
        cheque_number="CHQ-BNCE-FAIL-01",
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.ADVANCE_PAYMENT,
        status=ChequeStatus.UNDER_COLLECTION,
        customer=sample_customer,
        amount=Decimal("1500.00"),
        collected_amount=Decimal("0.00"),
        remaining_amount=Decimal("1500.00"),
        currency=financial_accounts["currency"],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )

    # تخصيص الشيك على الفاتورة
    alloc = ChequeAllocationService.allocate_cheque_to_invoice(
        cheque=cheque,
        sale=sale,
        amount=Decimal("1500.00"),
        user=test_user,
    )
    assert alloc.allocation_status == "APPLIED"
    assert alloc.journal_entry is not None

    # محاكاة فشل LedgerCoreService.reverse_entry أثناء الارتداد
    def mock_reverse_entry(*args, **kwargs):
        raise ValidationError("محاكاة: فشل رفض قيد اليومية لأسباب محاسبية.")

    monkeypatch.setattr(LedgerCoreService, "reverse_entry", mock_reverse_entry)

    # محاولة ارتداد الشيك يجب أن تثير ValidationError ولا تبتلع الخطأ
    with pytest.raises(ValidationError):
        ChequeAccountingService.bounce_cheque(
            cheque=cheque,
            bounce_reason="Insufficient funds",
            user=test_user,
            idempotency_key="BNCE-SIM-FAIL-01"
        )

    # التحقق من أن التراجع الذري أعاد كل شيء كما كان
    cheque.refresh_from_db()
    assert cheque.status == ChequeStatus.UNDER_COLLECTION
    alloc.refresh_from_db()
    assert alloc.allocation_status == "APPLIED"
    sale.refresh_from_db()
    assert sale.payment_status in ["paid", "partial"]


@pytest.mark.django_db
def test_p1_expired_treasury_access_prevents_issuing_cheque(test_user, financial_accounts, sample_supplier):
    """
    صلاحية صرف منتهية تمنع إصدار شيك دفع وتثير ValidationError
    """
    from financial.models.treasury_access import UserTreasuryAccess
    from cheques.services.disbursement_security_service import ChequeDisbursementSecurityService

    today = timezone.localdate()
    yesterday = today - datetime.timedelta(days=1)
    two_days_ago = today - datetime.timedelta(days=2)

    # مستخدم عادي غير مدير نظام
    regular_user = User.objects.create_user(
        username="teller_expired",
        password="Password123!"
    )

    # صلاحية صرف انتهت أمس
    UserTreasuryAccess.objects.create(
        user=regular_user,
        treasury=financial_accounts["bank"],
        can_deposit=True,
        can_disburse=True,
        valid_from=two_days_ago,
        valid_until=yesterday,
    )

    with pytest.raises(ValidationError) as exc:
        ChequeDisbursementSecurityService.enforce_and_reserve(
            user=regular_user,
            bank_account_id=financial_accounts["bank"].id,
            amount=Decimal("1000.00"),
            as_of_date=today,
        )
    assert "منتهية" in str(exc.value) or "غير سارية" in str(exc.value)


@pytest.mark.django_db
def test_p1_foreign_cheque_allocation_preserves_invoice_book_rate_and_isolates_fx(test_user, financial_accounts, sample_customer):
    """
    فاتورة 100 دولار بسعر 50 وتخصيص شيك 50 دولار بسعر 52:
    المتبقي على الفاتورة يجب أن يكون 50 دولار = 2,500 جنيه بقيمتها الدفترية الأصلية
    وفصل فرق العملة (100 جنيه) كفرق عملة محقق
    """
    from customer.models import CustomerTransaction, CustomerAllocationAudit
    usd, _ = Currency.objects.get_or_create(code="USD", defaults={"name": "US Dollar", "symbol": "$"})
    today = timezone.localdate()

    # فاتورة 100 دولار بسعر 50 = 5,000 جنيه
    sale = Sale.objects.create(
        number="INV-USD-FX-01",
        customer=sample_customer,
        date=today,
        currency=usd,
        exchange_rate=Decimal("50.000000"),
        subtotal=Decimal("100.00"),
        total=Decimal("100.00"),
        total_functional=Decimal("5000.00"),
        payment_method="credit",
        payment_status="unpaid",
        status="confirmed",
        created_by=test_user,
    )

    # تسجيل الفاتورة في الأستاذ المساعد
    inv_txn, _ = CustomerTransaction.objects.get_or_create(
        customer=sample_customer,
        transaction_type="INVOICE",
        reference_id=str(sale.id),
        defaults={
            "transaction_number": sale.number,
            "issue_date": sale.date,
            "due_date": sale.date,
            "currency": "USD",
            "foreign_amount": Decimal("100.00"),
            "exchange_rate": Decimal("50.000000"),
            "functional_amount": Decimal("5000.00"),
            "open_amount": Decimal("5000.00"),
            "open_amount_functional": Decimal("5000.00"),
            "open_amount_foreign": Decimal("100.00"),
            "status": "OPEN",
        }
    )

    # شيك 50 دولار بسعر 52 = 2,600 جنيه
    cheque = Cheque.objects.create(
        voucher_number="RV-USD-FX-01",
        cheque_number="CHQ-USD-FX-01",
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.IN_PORTFOLIO,
        customer=sample_customer,
        amount=Decimal("50.00"),
        collected_amount=Decimal("0.00"),
        remaining_amount=Decimal("50.00"),
        currency=usd,
        original_exchange_rate=Decimal("52.000000"),
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )

    # تخصيص 50 دولار
    alloc = ChequeAllocationService.allocate_cheque_to_invoice(
        cheque=cheque,
        sale=sale,
        amount=Decimal("50.00"),
        user=test_user,
    )

    inv_txn.refresh_from_db()
    # المتبقي على الفاتورة يجب أن يكون 50 دولار = 2,500 جنيه بالضبط
    assert inv_txn.open_amount == Decimal("2500.00")
    assert inv_txn.open_amount_foreign == Decimal("50.00")

    # سجل التدقيق يجب أن يوثق فرق العملة المحقق: 50 * 52 - 50 * 50 = 100 جنيه
    audit = CustomerAllocationAudit.objects.filter(target_document_number=sale.number).first()
    assert audit is not None
    assert audit.realized_fx_difference == Decimal("100.00")


@pytest.mark.django_db
def test_p1_fx_revaluation_validation_fails_if_cheque_collected_after_calculation(test_user, financial_accounts, sample_customer):
    """
    اعتماد تقييم العملة يجب أن يفشل إذا تم تعديل أو تحصيل الشيك بعد عملية الحساب وقبل الاعتماد
    """
    from financial.fx.services.calculation import FXCalculationService
    from financial.fx.services.validation import FXValidationService
    from financial.fx.models import FXRateSnapshot, FXRevaluationRun
    from financial.models import AccountingPeriod

    usd, _ = Currency.objects.get_or_create(code="USD", defaults={"name": "US Dollar", "symbol": "$"})
    today = timezone.localdate()
    period = AccountingPeriod.objects.filter(status='open').first()
    if not period:
        period = AccountingPeriod.objects.create(
            name="Test Period",
            start_date=today.replace(day=1),
            end_date=today,
            status='open',
            fiscal_year=None,
        )

    # شيك قبض مفتوح بالدولار
    cheque = Cheque.objects.create(
        voucher_number="RV-FX-GUARD-01",
        cheque_number="CHQ-FX-GUARD-01",
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.IN_PORTFOLIO,
        customer=sample_customer,
        amount=Decimal("1000.00"),
        collected_amount=Decimal("0.00"),
        remaining_amount=Decimal("1000.00"),
        currency=usd,
        original_exchange_rate=Decimal("48.000000"),
        issue_date=period.start_date,
        due_date=period.end_date,
        created_by=test_user,
    )

    # إعداد سعر الصرف وسجل التقييم
    from financial.models import ExchangeRate
    ExchangeRate.objects.create(
        from_currency=usd,
        to_currency=financial_accounts['currency'],
        rate=Decimal('52.000000'),
        effective_date=today,
        source='CBE'
    )

    # حساب التقييم
    run = FXCalculationService.calculate_and_create_run(
        period=period,
        user=test_user,
        currency_scope='ALL_CURRENCIES'
    )
    assert run.lines.filter(source_type='NOTES_RECEIVABLE', source_id=str(cheque.id)).exists()

    # تحصيل الشيك بالكامل بعد الحساب
    ChequeAccountingService.collect_cheque(
        cheque=cheque,
        amount_collected=Decimal("1000.00"),
        user=test_user,
        idempotency_key="COL-FX-GUARD-01"
    )

    # محاولة اعتماد التقييم يجب أن تفشل لاكتشاف تغير رصيد/حالة الشيك
    with pytest.raises(ValidationError) as exc:
        FXValidationService.validate_run(run, user=test_user)
    assert "تعديل أو تحصيل شيك القبض" in str(exc.value)


@pytest.mark.django_db
def test_p1_past_value_date_does_not_bypass_daily_disbursement_limit(test_user, financial_accounts, sample_supplier):
    """
    سقف المستخدم اليومي لا يمكن تجاوزه بتمرير تاريخ قيد (value_date) سابق:
    سقف المستخدم 1,500؛ إصدار شيكين اليوم كل واحد 1,000 بتاريخ قيمة الأمس
    يجب أن يسمح بالشيك الأول ويرفض الشيك الثاني لتجاوز السقف اليومي الفعلي.
    """
    from financial.models import UserTreasuryAccess
    today = timezone.localdate()
    yesterday = today - datetime.timedelta(days=1)

    # ضبط سقف المستخدم على الحساب البنكي: سقف يومي 1,500 وسقف حركة 1,500
    UserTreasuryAccess.objects.update_or_create(
        user=test_user,
        treasury=financial_accounts['bank'],
        defaults={
            'can_deposit': True,
            'can_disburse': True,
            'max_single_disbursement_limit': Decimal('1500.00'),
            'daily_disbursement_limit': Decimal('1500.00'),
            'valid_from': None,
            'valid_until': None,
        }
    )

    # إصدار الشيك الأول بقيمة 1,000 بتاريخ استحقاق/قيمة الأمس
    cheque1 = Cheque.objects.create(
        voucher_number="PV-LIM-01",
        cheque_number="CHQ-LIM-01",
        cheque_type=ChequeType.PAYABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.DRAFT,
        supplier=sample_supplier,
        amount=Decimal("1000.00"),
        currency=financial_accounts['currency'],
        deposit_bank_account=financial_accounts['bank'],
        issue_date=yesterday,
        due_date=yesterday,
        created_by=test_user,
    )

    res1 = ChequeAccountingService.issue_cheque(
        cheque=cheque1,
        user=test_user,
        value_date=yesterday,
        idempotency_key="ISSUE-LIM-01"
    )
    cheque1.refresh_from_db()
    assert cheque1.status == ChequeStatus.ISSUED

    # إصدار الشيك الثاني بقيمة 1,000 اليوم بتاريخ استحقاق/قيمة الأمس
    cheque2 = Cheque.objects.create(
        voucher_number="PV-LIM-02",
        cheque_number="CHQ-LIM-02",
        cheque_type=ChequeType.PAYABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.DRAFT,
        supplier=sample_supplier,
        amount=Decimal("1000.00"),
        currency=financial_accounts['currency'],
        deposit_bank_account=financial_accounts['bank'],
        issue_date=yesterday,
        due_date=yesterday,
        created_by=test_user,
    )

    with pytest.raises(ValidationError) as exc:
        ChequeAccountingService.issue_cheque(
            cheque=cheque2,
            user=test_user,
            value_date=yesterday,
            idempotency_key="ISSUE-LIM-02"
        )
    assert "يتجاوز السقف اليومي" in str(exc.value)


@pytest.mark.django_db
def test_p1_expired_permission_blocks_issuance_even_with_past_value_date(test_user, financial_accounts, sample_supplier):
    """
    انتهاء صلاحية الصرف يمنع إصدار الشيك اليوم حتى لو تم تمرير تاريخ قيمة سابق تكون فيه الصلاحية سارية
    """
    from financial.models import UserTreasuryAccess
    today = timezone.localdate()
    yesterday = today - datetime.timedelta(days=1)

    # ضبط الصلاحية لتنتهي أمس
    UserTreasuryAccess.objects.update_or_create(
        user=test_user,
        treasury=financial_accounts['bank'],
        defaults={
            'can_deposit': True,
            'can_disburse': True,
            'max_single_disbursement_limit': Decimal('5000.00'),
            'daily_disbursement_limit': Decimal('5000.00'),
            'valid_from': yesterday - datetime.timedelta(days=10),
            'valid_until': yesterday,
        }
    )

    cheque = Cheque.objects.create(
        voucher_number="PV-EXP-01",
        cheque_number="CHQ-EXP-01",
        cheque_type=ChequeType.PAYABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.DRAFT,
        supplier=sample_supplier,
        amount=Decimal("1000.00"),
        currency=financial_accounts['currency'],
        deposit_bank_account=financial_accounts['bank'],
        issue_date=yesterday,
        due_date=yesterday,
        created_by=test_user,
    )

    # محاولة إصدار الشيك اليوم بتمرير تاريخ الأمس
    with pytest.raises(ValidationError) as exc:
        ChequeAccountingService.issue_cheque(
            cheque=cheque,
            user=test_user,
            value_date=yesterday,
            idempotency_key="ISSUE-EXP-01"
        )
    assert "صلاحية الصرف من هذا الحساب البنكي منتهية أو غير سارية بتاريخ اليوم" in str(exc.value)


@pytest.mark.django_db
def test_p1_fx_revaluation_posting_fails_if_cheque_collected_after_validation(test_user, financial_accounts, sample_customer):
    """
    إذا تم اعتماد التقييم (VALIDATED) ثم تم تحصيل الشيك بالكامل لاحقاً،
    يجب أن يفشل الترحيل post_run() ولا يولد قيداً ببيانات منتهية
    """
    from financial.fx.services.calculation import FXCalculationService
    from financial.fx.services.validation import FXValidationService
    from financial.fx.services.posting import FXPostingService
    from financial.fx.models import FXRevaluationRun
    from financial.models import AccountingPeriod, ExchangeRate

    usd, _ = Currency.objects.get_or_create(code="USD", defaults={"name": "US Dollar", "symbol": "$"})
    today = timezone.localdate()
    period = AccountingPeriod.objects.filter(status='open').first()
    if not period:
        period = AccountingPeriod.objects.create(
            name="Test FX Period",
            start_date=today.replace(day=1),
            end_date=today,
            status='open',
            fiscal_year=None,
        )

    # شيك قبض مفتوح بقيمة 1,000 دولار بسعر تاريخي 48
    cheque = Cheque.objects.create(
        voucher_number="RV-POST-GUARD-01",
        cheque_number="CHQ-POST-GUARD-01",
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.IN_PORTFOLIO,
        customer=sample_customer,
        amount=Decimal("1000.00"),
        collected_amount=Decimal("0.00"),
        remaining_amount=Decimal("1000.00"),
        currency=usd,
        original_exchange_rate=Decimal("48.000000"),
        issue_date=period.start_date,
        due_date=period.end_date,
        created_by=test_user,
    )

    # سعر الصرف اليوم 50 (فرق 2,000 جنيه)
    ExchangeRate.objects.create(
        from_currency=usd,
        to_currency=financial_accounts['currency'],
        rate=Decimal('50.000000'),
        effective_date=today,
        source='CBE'
    )

    # 1. حساب التقييم
    run = FXCalculationService.calculate_and_create_run(
        period=period,
        user=test_user,
        currency_scope='ALL_CURRENCIES'
    )
    assert run.lines.filter(source_type='NOTES_RECEIVABLE', source_id=str(cheque.id)).exists()

    # 2. اعتماد التقييم بنجاح
    validated = FXValidationService.validate_run(run, user=test_user)
    assert validated is True
    run.refresh_from_db()
    assert run.status == 'VALIDATED'

    # 3. تحصيل الشيك بالكامل بعد الاعتماد
    ChequeAccountingService.collect_cheque(
        cheque=cheque,
        amount_collected=Decimal("1000.00"),
        user=test_user,
        idempotency_key="COL-POST-GUARD-01"
    )
    cheque.refresh_from_db()
    assert cheque.status == ChequeStatus.COLLECTED
    assert cheque.remaining_amount == Decimal("0.00")

    # 4. محاولة ترحيل التقييم المعتمد يجب أن تفشل بشكل قاطع وتمنع إنشاء القيد
    with pytest.raises(ValidationError) as exc:
        FXPostingService.post_run(run, user=test_user)

    assert "تعديل أو تحصيل شيك القبض" in str(exc.value)
    run.refresh_from_db()
    assert run.status != 'POSTED'
    assert run.journal_entry is None


@pytest.mark.django_db
def test_p1_fx_revaluation_posting_rolls_back_if_cheque_update_fails(test_user, financial_accounts, sample_customer, monkeypatch):
    """
    إذا فشل تحديث القيمة الدفترية للشيك أثناء ترحيل التقييم،
    يجب أن تفشل المعاملة بالكامل ويتراجع قيد اليومية ولا يتحول التشغيل إلى POSTED
    """
    from financial.fx.services.calculation import FXCalculationService
    from financial.fx.services.validation import FXValidationService
    from financial.fx.services.posting import FXPostingService
    from financial.fx.models import FXRevaluationRun
    from financial.models import AccountingPeriod, ExchangeRate, JournalEntry

    usd, _ = Currency.objects.get_or_create(code="USD", defaults={"name": "US Dollar", "symbol": "$"})
    today = timezone.localdate()
    period = AccountingPeriod.objects.filter(status='open').first()
    if not period:
        period = AccountingPeriod.objects.create(
            name="Test FX Period Rollback",
            start_date=today.replace(day=1),
            end_date=today,
            status='open',
            fiscal_year=None,
        )

    # شيك قبض مفتوح بقيمة 1,000 دولار بسعر تاريخي 48 = 48,000 جنيه
    cheque = Cheque.objects.create(
        voucher_number="RV-ROLLBACK-01",
        cheque_number="CHQ-ROLLBACK-01",
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.IN_PORTFOLIO,
        customer=sample_customer,
        amount=Decimal("1000.00"),
        collected_amount=Decimal("0.00"),
        remaining_amount=Decimal("1000.00"),
        currency=usd,
        original_exchange_rate=Decimal("48.000000"),
        issue_date=period.start_date,
        due_date=period.end_date,
        created_by=test_user,
    )

    # سعر الصرف 52 (فرق 4,000 جنيه)
    ExchangeRate.objects.create(
        from_currency=usd,
        to_currency=financial_accounts['currency'],
        rate=Decimal('52.000000'),
        effective_date=today,
        source='CBE'
    )

    run = FXCalculationService.calculate_and_create_run(
        period=period,
        user=test_user,
        currency_scope='ALL_CURRENCIES'
    )
    FXValidationService.validate_run(run, user=test_user)

    # محاكاة فشل حفظ القيمة الدفترية للشيك
    orig_save = Cheque.save
    def failing_save(self, *args, **kwargs):
        if 'update_fields' in kwargs and 'book_value_functional' in kwargs['update_fields']:
            raise ValidationError("Simulated Cheque DB update failure")
        return orig_save(self, *args, **kwargs)

    monkeypatch.setattr(Cheque, 'save', failing_save)

    # محاولة الترحيل يجب أن تثير الخطأ وتلغي إنشاء القيد بالكامل
    with pytest.raises(ValidationError) as exc:
        FXPostingService.post_run(run, user=test_user)

    assert "Simulated Cheque DB update failure" in str(exc.value)

    # التأكد من التراجع الذري: لم يتم ترحيل القيد، وحالة التشغيل لم تصبح POSTED
    run.refresh_from_db()
    assert run.status != 'POSTED'
    assert run.journal_entry is None
    assert not JournalEntry.objects.filter(reference=f"FX-REV-{run.id}").exists()

    # القيمة الدفترية للشيك ظلت كما هي 48,000
    cheque.refresh_from_db()
    assert cheque.book_value_functional == Decimal("48000.00")


@pytest.mark.django_db
def test_p2_disbursement_limit_attributed_to_actual_issuer_not_draft_creator(financial_accounts, sample_supplier):
    """
    سقف الصرف يُحسب على المستخدم المُصدر الفعلي للشيك وليس على منشئ المسودة:
    المستخدم «أ» أنشأ مسودة بـ1,000، وأصدرها المستخدم «ب».
    المستخدم «أ» يجب أن يتمكن من إصدار شيكه الخاص بـ1,000 بسقف 1,500 دون أن يُحسب عليه شيك المسودة الأول.
    """
    from financial.models import UserTreasuryAccess
    today = timezone.localdate()

    user_a = User.objects.create_user(username='issuer_a', email='issuer_a@mwheba.com', password='Password123!')
    user_b = User.objects.create_user(username='issuer_b', email='issuer_b@mwheba.com', password='Password123!')

    # إعداد صلاحيات وسقف لكل من أ و ب بسقف 1,500
    for u in [user_a, user_b]:
        UserTreasuryAccess.objects.create(
            user=u,
            treasury=financial_accounts['bank'],
            can_deposit=True,
            can_disburse=True,
            max_single_disbursement_limit=Decimal('1500.00'),
            daily_disbursement_limit=Decimal('1500.00'),
        )

    # مستخدم «أ» ينشئ مسودة شيك بـ1,000
    cheque_draft = Cheque.objects.create(
        voucher_number="PV-DRAFT-01",
        cheque_number="CHQ-DRAFT-01",
        cheque_type=ChequeType.PAYABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.DRAFT,
        supplier=sample_supplier,
        amount=Decimal("1000.00"),
        currency=financial_accounts['currency'],
        deposit_bank_account=financial_accounts['bank'],
        issue_date=today,
        due_date=today,
        created_by=user_a,
    )

    # مستخدم «ب» هو من يقوم بإصدار هذا الشيك
    res_b = ChequeAccountingService.issue_cheque(
        cheque=cheque_draft,
        user=user_b,
        idempotency_key="ISSUE-BY-B-01"
    )
    cheque_draft.refresh_from_db()
    assert cheque_draft.status == ChequeStatus.ISSUED
    assert cheque_draft.issued_by == user_b
    assert cheque_draft.created_by == user_a

    # الآن مستخدم «أ» يصدر شيكه الخاص بـ1,000 (سقفه 1,500)
    cheque_a = Cheque.objects.create(
        voucher_number="PV-OWN-01",
        cheque_number="CHQ-OWN-01",
        cheque_type=ChequeType.PAYABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.DRAFT,
        supplier=sample_supplier,
        amount=Decimal("1000.00"),
        currency=financial_accounts['currency'],
        deposit_bank_account=financial_accounts['bank'],
        issue_date=today,
        due_date=today,
        created_by=user_a,
    )

    # يجب أن ينجح إصدار الشيك الخاص بالمستخدم «أ» لأن التزاماته الفعلية اليوم = 0
    res_a = ChequeAccountingService.issue_cheque(
        cheque=cheque_a,
        user=user_a,
        idempotency_key="ISSUE-BY-A-01"
    )
    cheque_a.refresh_from_db()
    assert cheque_a.status == ChequeStatus.ISSUED
    assert cheque_a.issued_by == user_a

    # بينما المستخدم «ب» لو حاول إصدار شيك آخر بـ1,000 سيفشل لتجاوز سقفه (1,000 سابقة + 1,000 جديدة > 1,500)
    cheque_b2 = Cheque.objects.create(
        voucher_number="PV-OWN-B2",
        cheque_number="CHQ-OWN-B2",
        cheque_type=ChequeType.PAYABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.DRAFT,
        supplier=sample_supplier,
        amount=Decimal("1000.00"),
        currency=financial_accounts['currency'],
        deposit_bank_account=financial_accounts['bank'],
        issue_date=today,
        due_date=today,
        created_by=user_b,
    )
    with pytest.raises(ValidationError) as exc:
        ChequeAccountingService.issue_cheque(
            cheque=cheque_b2,
            user=user_b,
            idempotency_key="ISSUE-BY-B-02"
        )
    assert "يتجاوز السقف اليومي" in str(exc.value)


@pytest.mark.django_db
def test_p1_passed_bank_account_persisted_on_cheque_and_enforces_daily_limit(financial_accounts, sample_supplier):
    """
    عند إصدار شيك دفع بدون بنك مسبق مع تمرير bank_account_id للدالة:
    يجب أن يُحفظ البنك ذرياً على الشيك، ويُحسب الشيك في سقف الصرف للبنك ليمنع تجاوز السقف اليومي.
    """
    from financial.models import UserTreasuryAccess
    today = timezone.localdate()
    user_test = User.objects.create_user(username='issuer_bank_test', email='bank_test@mwheba.com', password='Password123!')

    # سقف يومي 1,500
    UserTreasuryAccess.objects.create(
        user=user_test,
        treasury=financial_accounts['bank'],
        can_deposit=True,
        can_disburse=True,
        max_single_disbursement_limit=Decimal('1500.00'),
        daily_disbursement_limit=Decimal('1500.00'),
    )

    # شيك 1 مسودة بدون بنك مسجل مسبقاً
    cheque1 = Cheque.objects.create(
        voucher_number="PV-NOBANK-01",
        cheque_number="CHQ-NOBANK-01",
        cheque_type=ChequeType.PAYABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.DRAFT,
        supplier=sample_supplier,
        amount=Decimal("1000.00"),
        currency=financial_accounts['currency'],
        deposit_bank_account=None,
        issue_date=today,
        due_date=today,
        created_by=user_test,
    )
    assert cheque1.deposit_bank_account_id is None

    # إصدار الشيك الأول مع تمرير bank_account_id
    res1 = ChequeAccountingService.issue_cheque(
        cheque=cheque1,
        user=user_test,
        bank_account_id=financial_accounts['bank'].id,
        idempotency_key="ISSUE-NOBANK-01"
    )
    cheque1.refresh_from_db()
    assert cheque1.status == ChequeStatus.ISSUED
    assert cheque1.deposit_bank_account_id == financial_accounts['bank'].id, "Bank passed during issue must be persisted on cheque!"

    # شيك 2 مسودة بدون بنك مسجل مسبقاً
    cheque2 = Cheque.objects.create(
        voucher_number="PV-NOBANK-02",
        cheque_number="CHQ-NOBANK-02",
        cheque_type=ChequeType.PAYABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.DRAFT,
        supplier=sample_supplier,
        amount=Decimal("1000.00"),
        currency=financial_accounts['currency'],
        deposit_bank_account=None,
        issue_date=today,
        due_date=today,
        created_by=user_test,
    )

    # محاولة إصدار الشيك الثاني بنفس البنك يجب أن ترفض لتجاوز السقف اليومي (1000 + 1000 > 1500)
    with pytest.raises(ValidationError) as exc:
        ChequeAccountingService.issue_cheque(
            cheque=cheque2,
            user=user_test,
            bank_account_id=financial_accounts['bank'].id,
            idempotency_key="ISSUE-NOBANK-02"
        )
    assert "يتجاوز السقف اليومي" in str(exc.value)


@pytest.mark.django_db
def test_p2_full_collection_replay_with_idempotency_key_returns_success(client, test_user, financial_accounts, sample_customer):
    """
    إعادة إرسال نفس طلب التحصيل الكامل بـ idempotency_key يعود بنجاح (Cached Replay)
    ولا يرفض بسبب فحص رصيد النموذج بعد أن أصبح المتبقي صفراً.
    """
    client.force_login(test_user)
    today = timezone.localdate()
    cheque = Cheque.objects.create(
        voucher_number="RV-FULL-REPLAY-01",
        cheque_number="CHQ-FULL-REPLAY-01",
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.UNDER_COLLECTION,
        customer=sample_customer,
        amount=Decimal("1000.00"),
        collected_amount=Decimal("0.00"),
        remaining_amount=Decimal("1000.00"),
        currency=financial_accounts['currency'],
        deposit_bank_account=financial_accounts['bank'],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )

    url = reverse('cheques:cheque_collect_action', kwargs={'pk': cheque.pk})
    idem_key = "COL-FULL-REPLAY-UNIQUE-KEY-88"
    post_data = {
        'amount_collected': '1000.00',
        'value_date': str(today),
        'exchange_rate': '1.000000',
        'bank_charges': '0.00',
        'bank_charges_vat': '0.00',
        'deposit_bank_account': str(financial_accounts['bank'].id),
        'notes': 'تحصيل كامل مع مفتاح تكرار',
        'idempotency_key': idem_key,
    }

    # الطلب الأول: ينجح بالكامل
    res1 = client.post(url, data=post_data)
    assert res1.status_code in [200, 302]
    cheque.refresh_from_db()
    assert cheque.status == ChequeStatus.COLLECTED
    assert cheque.remaining_amount == Decimal("0.00")

    # الطلب الثاني: بنفس المفتاح ونفس البيانات بعد أن أصبح الرصيد المتبقي = 0
    res2 = client.post(url, data=post_data)
    assert res2.status_code in [200, 302]
    # لا يوجد رسالة خطأ بالرفض
    cheque.refresh_from_db()
    assert cheque.status == ChequeStatus.COLLECTED
    assert cheque.remaining_amount == Decimal("0.00")


@pytest.mark.django_db
def test_p1_issue_payable_cheque_enforces_permission_on_newly_passed_bank(financial_accounts, sample_supplier, account_types):
    """
    إذا كان الشيك مسجلاً مبدئياً على بنك مصرح للمستخدم (Bank A)، لكن تم تمرير بنك مختلف (Bank B)
    غير مصرح للمستخدم بالصرف منه عند استدعاء دالة الإصدار:
    يجب أن يتم فحص الصلاحية على البنك المستهدف الجديد (Bank B) ورفض الإصدار.
    """
    from financial.models import UserTreasuryAccess
    today = timezone.localdate()
    user_test = User.objects.create_user(username='bank_target_tester', email='bank_target@mwheba.com', password='Password123!')

    # بنك ثانٍ Bank B
    bank_b, _ = ChartOfAccounts.objects.get_or_create(
        code='11160002',
        defaults={
            'name': 'الحساب البنكي الثاني (غير مصرح)',
            'account_type': account_types['asset'],
            'level': 4,
            'is_leaf': True,
            'is_bank_account': True,
            'is_active': True,
            'currency': financial_accounts['currency'],
        }
    )

    # المستخدم مصرح له فقط على Bank A وليس Bank B
    UserTreasuryAccess.objects.create(
        user=user_test,
        treasury=financial_accounts['bank'],
        can_deposit=True,
        can_disburse=True,
        max_single_disbursement_limit=Decimal('5000.00'),
        daily_disbursement_limit=Decimal('5000.00'),
    )

    # شيك مسودة على Bank A (المصرح به)
    cheque = Cheque.objects.create(
        voucher_number="PV-SWITCH-01",
        cheque_number="CHQ-SWITCH-01",
        cheque_type=ChequeType.PAYABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.DRAFT,
        supplier=sample_supplier,
        amount=Decimal("1000.00"),
        currency=financial_accounts['currency'],
        deposit_bank_account=financial_accounts['bank'],
        issue_date=today,
        due_date=today,
        created_by=user_test,
    )

    # محاولة إصدار الشيك مع تمرير Bank B الذي ليس للمستخدم صلاحية عليه
    with pytest.raises(ValidationError) as exc:
        ChequeAccountingService.issue_cheque(
            cheque=cheque,
            user=user_test,
            bank_account_id=bank_b.id,
            idempotency_key="ISSUE-SWITCH-01"
        )

    assert "صلاحية صرف" in str(exc.value)
    cheque.refresh_from_db()
    assert cheque.status == ChequeStatus.DRAFT
    # لم يتم تغيير البنك على الشيك أو ترحيله
    assert cheque.deposit_bank_account == financial_accounts['bank']


@pytest.mark.django_db
def test_p2_collect_replay_with_different_amount_fails_concurrency_conflict(client, test_user, financial_accounts, sample_customer):
    """
    إذا تم تحصيل 400 بمفتاح عدم تكرار، ثم أُرسل طلب بـ 500 بنفس المفتاح:
    يجب أن ترفض الواجهة الطلب لاختلاف المعلمات (تعارض في مفتاح عدم التكرار)
    ولا تقبل الـ 500 كإعادة محاولة ناجحة، ويبقى المسجل في قاعدة البيانات 400 فقط.
    """
    client.force_login(test_user)
    today = timezone.localdate()
    cheque = Cheque.objects.create(
        voucher_number="RV-CONFLICT-01",
        cheque_number="CHQ-CONFLICT-01",
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.UNDER_COLLECTION,
        customer=sample_customer,
        amount=Decimal("1000.00"),
        collected_amount=Decimal("0.00"),
        remaining_amount=Decimal("1000.00"),
        currency=financial_accounts['currency'],
        deposit_bank_account=financial_accounts['bank'],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )

    url = reverse('cheques:cheque_collect_action', kwargs={'pk': cheque.pk})
    idem_key = "COL-CONFLICT-UNIQUE-KEY-99"

    # الطلب الأول: تحصيل 400
    post_400 = {
        'amount_collected': '400.00',
        'value_date': str(today),
        'exchange_rate': '1.000000',
        'bank_charges': '0.00',
        'bank_charges_vat': '0.00',
        'deposit_bank_account': str(financial_accounts['bank'].id),
        'notes': 'تحصيل جزئي أول 400',
        'idempotency_key': idem_key,
    }
    res1 = client.post(url, data=post_400)
    assert res1.status_code in [200, 302]
    cheque.refresh_from_db()
    assert cheque.status == ChequeStatus.PARTIALLY_COLLECTED
    assert cheque.collected_amount == Decimal("400.00")
    assert cheque.remaining_amount == Decimal("600.00")

    # الطلب الثاني: تحصيل 500 بنفس المفتاح (معلمات مختلفة تسبب تعارضاً)
    post_500 = {
        'amount_collected': '500.00',
        'value_date': str(today),
        'exchange_rate': '1.000000',
        'bank_charges': '0.00',
        'bank_charges_vat': '0.00',
        'deposit_bank_account': str(financial_accounts['bank'].id),
        'notes': 'محاولة تحصيل 500 بنفس المفتاح',
        'idempotency_key': idem_key,
    }
    # نرسل الطلب كـ AJAX لاختبار رسالة الخطأ والرمز
    res2 = client.post(url, data=post_500, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert res2.status_code == 400
    data2 = res2.json()
    assert data2['success'] is False
    assert "تعارض في مفتاح عدم التكرار" in data2['message']

    # التأكد من عدم تغيير رصيد الشيك في قاعدة البيانات (بقي 400 محصل و 600 متبقي)
    cheque.refresh_from_db()
    assert cheque.collected_amount == Decimal("400.00")
    assert cheque.remaining_amount == Decimal("600.00")


@pytest.mark.django_db
def test_p1_guarantee_cheque_cannot_be_collected_without_operational_conversion(test_user, financial_accounts, sample_customer, sample_supplier):
    """
    [P1] منع تحصيل أو إيداع أو صرف شيك الضمان خارج الميزانية قبل اعتماده وتحويله لتشغيلي
    التأكد من أن استدعاء التحصيل يرمي ValidationError ولا يعدل الحالة إلى COLLECTED ولا يسجل مبالغ محصلة
    """
    today = timezone.localdate()
    # 1. شيك ضمان وارد (RECEIVABLE)
    sec_rec_cheque = Cheque.objects.create(
        voucher_number="V-SEC-REC-001",
        cheque_number="CHK-SEC-001",
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.SECURITY_GUARANTEE,
        status=ChequeStatus.IN_PORTFOLIO,
        customer=sample_customer,
        amount=Decimal("1000.00"),
        currency=financial_accounts["currency"],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )
    assert sec_rec_cheque.is_guarantee is True

    # محاولة تحصيل شيك الضمان مباشرة يجب أن تفشل
    with pytest.raises(ValidationError) as exc:
        ChequeAccountingService.collect_cheque(
            cheque=sec_rec_cheque,
            user=test_user,
            amount_collected=Decimal("1000.00"),
            idempotency_key="COL-SEC-ERR-001"
        )
    assert "لا يمكن تحصيل أو إيداع أو صرف أو تظهير" in str(exc.value)

    sec_rec_cheque.refresh_from_db()
    assert sec_rec_cheque.status == ChequeStatus.IN_PORTFOLIO
    assert sec_rec_cheque.collected_amount == Decimal("0.00")
    assert sec_rec_cheque.remaining_amount == Decimal("1000.00")

    # محاولة إيداع شيك الضمان برسم التحصيل يجب أن تفشل أيضاً
    with pytest.raises(ValidationError):
        ChequeAccountingService.deposit_cheque(
            cheque=sec_rec_cheque,
            user=test_user,
            bank_account_id=financial_accounts["bank"].id,
            idempotency_key="DEP-SEC-ERR-001"
        )

    # 2. شيك ضمان صادر (PAYABLE)
    sec_pay_cheque = Cheque.objects.create(
        voucher_number="V-SEC-PAY-001",
        cheque_number="CHK-SECPAY-001",
        cheque_type=ChequeType.PAYABLE,
        purpose=ChequePurpose.SECURITY_GUARANTEE,
        status=ChequeStatus.ISSUED,
        supplier=sample_supplier,
        deposit_bank_account=financial_accounts["bank"],
        amount=Decimal("2000.00"),
        currency=financial_accounts["currency"],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )
    assert sec_pay_cheque.is_guarantee is True

    # محاولة صرف شيك الضمان الصادر بنكياً يجب أن تفشل
    with pytest.raises(ValidationError):
        ChequeAccountingService.clear_payable_cheque(
            cheque=sec_pay_cheque,
            user=test_user,
            idempotency_key="CLR-SEC-ERR-001"
        )
    sec_pay_cheque.refresh_from_db()
    assert sec_pay_cheque.status == ChequeStatus.ISSUED


@pytest.mark.django_db
def test_p1_convert_payable_guarantee_cheque_branches_properly_and_creates_liability_entry(test_user, financial_accounts, sample_supplier):
    """
    [P1] تحويل شيك ضمان صادر (PAYABLE) يتحول إلى ISSUED ويولد قيد إثبات التزام ورقة الدفع:
    مدين حساب المورد (أو الدفعات المقدمة للموردين) / دائن أوراق الدفع 21120
    وليس مدين ودائن لأوراق القبض 11220
    """
    from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
    today = timezone.localdate()
    pay_control = AccountRoleRegistry.get_account(AccountRoleNames.NOTES_PAYABLE_CONTROL)
    rec_control = AccountRoleRegistry.get_account(AccountRoleNames.NOTES_RECEIVABLE_CONTROL)

    sec_pay = Cheque.objects.create(
        voucher_number="V-SEC-PAY-CONV-01",
        cheque_number="CHK-SECPAY-777",
        cheque_type=ChequeType.PAYABLE,
        purpose=ChequePurpose.SECURITY_GUARANTEE,
        status=ChequeStatus.ISSUED,
        supplier=sample_supplier,
        deposit_bank_account=financial_accounts["bank"],
        amount=Decimal("3500.00"),
        currency=financial_accounts["currency"],
        issue_date=today,
        due_date=today,
        created_by=test_user,
    )
    assert sec_pay.is_guarantee is True

    # تنفيذ تحويل شيك الضمان الصادر إلى سداد فاتورة
    res = ChequeAccountingService.convert_guarantee(
        cheque=sec_pay,
        user=test_user,
        new_purpose=ChequePurpose.INVOICE_SETTLEMENT,
        idempotency_key="CONV-PAY-TEST-777"
    )

    sec_pay.refresh_from_db()
    # التحقق من أن الحالة أصبحت ISSUED وليست IN_PORTFOLIO
    assert sec_pay.status == ChequeStatus.ISSUED
    assert sec_pay.purpose == ChequePurpose.INVOICE_SETTLEMENT
    assert sec_pay.is_guarantee is False
    assert sec_pay.issued_by == test_user
    assert sec_pay.issued_at is not None

    # التحقق من القيد المحاسبي المتولد
    log = ChequeActionLog.objects.filter(cheque=sec_pay, action=ChequeActionType.CONVERT_GUARANTEE).first()
    assert log is not None
    assert log.journal_entry is not None
    assert log.journal_entry.status == "posted"

    lines = list(log.journal_entry.lines.all())
    # يجب أن يكون القيد: مدين المورد / دائن أوراق الدفع (21120)
    assert any(l.account == sample_supplier.financial_account and l.debit == Decimal("3500.00") for l in lines)
    assert any(l.account.id == pay_control.id and l.credit == Decimal("3500.00") for l in lines)
    # التأكد تماماً من عدم وجود أي سطر مدين أو دائن لحساب أوراق القبض 11220
    assert not any(l.account.id == rec_control.id for l in lines)


@pytest.mark.django_db
def test_p1_convert_payable_guarantee_cheque_same_user_avoids_double_counting_reservation(financial_accounts, sample_supplier):
    """
    [P1] منع الحجز المزدوج: مستخدم أصدر شيك ضمان بـ1,000 وسقفه 1,500،
    ثم حوله لتشغيلي بنفس المستخدم. يجب ألا يتكرر حجز الـ1,000 مرتين (2,000)
    بل ينجح التحويل دون تجاوز السقف.
    """
    from financial.models import UserTreasuryAccess
    today = timezone.localdate()
    user = User.objects.create_user(username='guar_user_same', email='guar_same@mwheba.com', password='Password123!')

    UserTreasuryAccess.objects.create(
        user=user,
        treasury=financial_accounts['bank'],
        can_deposit=True,
        can_disburse=True,
        max_single_disbursement_limit=Decimal('1500.00'),
        daily_disbursement_limit=Decimal('1500.00'),
    )

    # إصدار شيك ضمان صادر بـ 1,000
    cheque = Cheque.objects.create(
        voucher_number="V-SEC-SAME-01",
        cheque_number="CHK-SECSAME-01",
        cheque_type=ChequeType.PAYABLE,
        purpose=ChequePurpose.SECURITY_GUARANTEE,
        status=ChequeStatus.DRAFT,
        supplier=sample_supplier,
        deposit_bank_account=financial_accounts['bank'],
        amount=Decimal("1000.00"),
        currency=financial_accounts['currency'],
        issue_date=today,
        due_date=today,
        created_by=user,
    )
    ChequeAccountingService.issue_cheque(
        cheque=cheque,
        user=user,
        idempotency_key="ISS-SECSAME-01"
    )
    cheque.refresh_from_db()
    assert cheque.status == ChequeStatus.ISSUED
    assert cheque.is_guarantee is True
    assert cheque.issued_by == user

    # تحويل نفس الشيك إلى تشغيلي بواسطة نفس المستخدم
    # إذا تكرر الحجز، سيُحسب 1000 + 1000 = 2000 وسيفشل لأن السقف 1500
    # لكن مع استبعاد الشيك الحالي من الحساب المسبق، ينجح التحويل
    res = ChequeAccountingService.convert_guarantee(
        cheque=cheque,
        user=user,
        new_purpose=ChequePurpose.INVOICE_SETTLEMENT,
        idempotency_key="CONV-SECSAME-01"
    )
    cheque.refresh_from_db()
    assert cheque.status == ChequeStatus.ISSUED
    assert cheque.purpose == ChequePurpose.INVOICE_SETTLEMENT
    assert cheque.is_guarantee is False
    assert cheque.issued_by == user


@pytest.mark.django_db
def test_p1_convert_payable_guarantee_cheques_transfers_attribution_and_enforces_user_daily_limit(financial_accounts, sample_supplier):
    """
    [P1] منع تجاوز السقف: شيكا ضمان صادران سابقاً بمستخدم (أ)،
    تحويلهما اليوم بمستخدم (ب) سقفه 1,500.
    تحويل الشيك الأول (1,000) ينجح وتنتقل نسبة الإصدار للمستخدم (ب)،
    أما تحويل الشيك الثاني (1,000) فيفشل فوراً لتجاوز السقف اليومي (2,000 > 1,500).
    """
    from financial.models import UserTreasuryAccess
    today = timezone.localdate()
    yesterday = today - datetime.timedelta(days=1)

    user_a = User.objects.create_user(username='issuer_user_a', email='user_a@mwheba.com', password='Password123!')
    user_b = User.objects.create_user(username='converter_user_b', email='user_b@mwheba.com', password='Password123!')

    # مستخدم ب سقفه اليومي 1,500
    UserTreasuryAccess.objects.create(
        user=user_b,
        treasury=financial_accounts['bank'],
        can_deposit=True,
        can_disburse=True,
        max_single_disbursement_limit=Decimal('1500.00'),
        daily_disbursement_limit=Decimal('1500.00'),
    )

    # شيك ضمان 1 صادر مسبقاً بمستخدم أ
    cheque1 = Cheque.objects.create(
        voucher_number="V-SEC-DIFF-01",
        cheque_number="CHK-SECDIFF-01",
        cheque_type=ChequeType.PAYABLE,
        purpose=ChequePurpose.SECURITY_GUARANTEE,
        status=ChequeStatus.ISSUED,
        supplier=sample_supplier,
        deposit_bank_account=financial_accounts['bank'],
        amount=Decimal("1000.00"),
        currency=financial_accounts['currency'],
        issue_date=yesterday,
        due_date=today,
        issued_by=user_a,
        issued_at=timezone.now() - datetime.timedelta(days=1),
        created_by=user_a,
    )

    # شيك ضمان 2 صادر مسبقاً بمستخدم أ
    cheque2 = Cheque.objects.create(
        voucher_number="V-SEC-DIFF-02",
        cheque_number="CHK-SECDIFF-02",
        cheque_type=ChequeType.PAYABLE,
        purpose=ChequePurpose.SECURITY_GUARANTEE,
        status=ChequeStatus.ISSUED,
        supplier=sample_supplier,
        deposit_bank_account=financial_accounts['bank'],
        amount=Decimal("1000.00"),
        currency=financial_accounts['currency'],
        issue_date=yesterday,
        due_date=today,
        issued_by=user_a,
        issued_at=timezone.now() - datetime.timedelta(days=1),
        created_by=user_a,
    )

    # تحويل الشيك الأول بواسطة مستخدم ب: ينجح
    ChequeAccountingService.convert_guarantee(
        cheque=cheque1,
        user=user_b,
        new_purpose=ChequePurpose.INVOICE_SETTLEMENT,
        idempotency_key="CONV-DIFF-USERB-01"
    )
    cheque1.refresh_from_db()
    assert cheque1.status == ChequeStatus.ISSUED
    assert cheque1.is_guarantee is False
    # التأكد من انتقال نسبة الإصدار وتاريخ اليوم للمستخدم الحالي
    assert cheque1.issued_by == user_b
    assert timezone.localdate(cheque1.issued_at) == today

    # محاولة تحويل الشيك الثاني بواسطة مستخدم ب: يجب أن تفشل لتجاوز السقف اليومي (1000 + 1000 = 2000 > 1500)
    with pytest.raises(ValidationError) as exc:
        ChequeAccountingService.convert_guarantee(
            cheque=cheque2,
            user=user_b,
            new_purpose=ChequePurpose.INVOICE_SETTLEMENT,
            idempotency_key="CONV-DIFF-USERB-02"
        )
    assert "يتجاوز السقف اليومي المصرح به للمستخدم" in str(exc.value)

    cheque2.refresh_from_db()
    # الشيك الثاني يظل كما هو شيك ضمان لم يتم تحويله
    assert cheque2.status == ChequeStatus.ISSUED
    assert cheque2.purpose == ChequePurpose.SECURITY_GUARANTEE
    assert cheque2.is_guarantee is True
    assert cheque2.issued_by == user_a


@pytest.mark.django_db
def test_p1_reversal_of_convert_guarantee_restores_previous_issuer_and_reservation(financial_accounts, sample_supplier):
    """
    [P2] التحقق من أن التراجع عن تحويل شيك الضمان الصادر يستعيد صاحب الحجز وتاريخه الأصلي:
    - الشيك كان صادراً بمستخدم أ بالأمس.
    - حوله مستخدم ب اليوم (استهلك 1,000 من سقفه البالغ 1,500).
    - التراجع عن التحويل يستعيد issued_by إلى مستخدم أ وتاريخ الأمس.
    - يتحرر سقف مستخدم ب بالكامل، ويستطيع إصدار شيك جديد بـ1,000 دون رفض (1,000 <= 1,500).
    """
    from financial.models import UserTreasuryAccess
    today = timezone.localdate()
    yesterday = today - datetime.timedelta(days=1)
    yesterday_dt = timezone.now() - datetime.timedelta(days=1)

    user_a = User.objects.create_user(username='orig_issuer_a', email='orig_a@mwheba.com', password='Password123!')
    user_b = User.objects.create_user(username='converter_b', email='conv_b@mwheba.com', password='Password123!')

    # مستخدم ب سقفه اليومي 1,500
    UserTreasuryAccess.objects.create(
        user=user_b,
        treasury=financial_accounts['bank'],
        can_deposit=True,
        can_disburse=True,
        max_single_disbursement_limit=Decimal('1500.00'),
        daily_disbursement_limit=Decimal('1500.00'),
    )

    # شيك ضمان صادر بالأمس بمستخدم أ
    sec_cheque = Cheque.objects.create(
        voucher_number="V-REV-GUAR-01",
        cheque_number="CHK-REVGUAR-01",
        cheque_type=ChequeType.PAYABLE,
        purpose=ChequePurpose.SECURITY_GUARANTEE,
        status=ChequeStatus.ISSUED,
        supplier=sample_supplier,
        deposit_bank_account=financial_accounts['bank'],
        amount=Decimal("1000.00"),
        currency=financial_accounts['currency'],
        issue_date=yesterday,
        due_date=today,
        issued_by=user_a,
        issued_at=yesterday_dt,
        created_by=user_a,
    )

    # 1. مستخدم ب يحول الشيك لتشغيلي اليوم
    ChequeAccountingService.convert_guarantee(
        cheque=sec_cheque,
        user=user_b,
        new_purpose=ChequePurpose.INVOICE_SETTLEMENT,
        idempotency_key="CONV-REV-TEST-B01"
    )
    sec_cheque.refresh_from_db()
    assert sec_cheque.is_guarantee is False
    assert sec_cheque.issued_by == user_b
    assert timezone.localdate(sec_cheque.issued_at) == today

    # 2. التراجع عن حركة التحويل
    ChequeReversalService.reverse_last_action(
        cheque=sec_cheque,
        user=user_b,
        reason="إلغاء تحويل الضمان واستعادة حالته السابقة",
        idempotency_key="REV-CONV-ACTION-B01"
    )
    sec_cheque.refresh_from_db()
    assert sec_cheque.status == ChequeStatus.ISSUED
    assert sec_cheque.purpose == ChequePurpose.SECURITY_GUARANTEE
    assert sec_cheque.is_guarantee is True
    # التأكد من استعادة المستخدم وتاريخ الإصدار الأصلي بدقة
    assert sec_cheque.issued_by == user_a
    assert timezone.localdate(sec_cheque.issued_at) == yesterday

    # 3. التأكد من تحرر سقف مستخدم ب: يستطيع إصدار شيك جديد بـ 1,000 بنجاح دون أن يُرفض باعتبار الإجمالي 2,000
    new_cheque = Cheque.objects.create(
        voucher_number="V-NEW-CHQ-B01",
        cheque_number="CHK-NEW-B01",
        cheque_type=ChequeType.PAYABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.DRAFT,
        supplier=sample_supplier,
        deposit_bank_account=financial_accounts['bank'],
        amount=Decimal("1000.00"),
        currency=financial_accounts['currency'],
        issue_date=today,
        due_date=today,
        created_by=user_b,
    )
    ChequeAccountingService.issue_cheque(
        cheque=new_cheque,
        user=user_b,
        idempotency_key="ISS-NEW-B01"
    )
    new_cheque.refresh_from_db()
    assert new_cheque.status == ChequeStatus.ISSUED
    assert new_cheque.issued_by == user_b


@pytest.mark.django_db
def test_p1_convert_guarantee_reversal_ignores_user_notes_and_uses_structured_fields(financial_accounts, sample_supplier):
    """
    [P2] التحقق من أن التراجع عن تحويل الضمان يعتمد على الحقول المنظمة المستقلة،
    ولا يتأثر إطلاقاً بأي وسوم أو نصوص مدخلة داخل ملاحظات/سبب المستخدم (Reason/Notes Spoofing Protection)
    """
    today = timezone.localdate()
    yesterday = today - datetime.timedelta(days=1)
    yesterday_dt = timezone.now() - datetime.timedelta(days=1)

    user_real = User.objects.create_user(username='real_issuer', email='real@mwheba.com', password='Password123!')
    user_conv = User.objects.create_user(username='conv_actor', email='conv@mwheba.com', password='Password123!')
    user_fake = User.objects.create_user(username='fake_hacker', email='fake@mwheba.com', password='Password123!')

    # شيك ضمان صادر بالمستخدم الحقيقي
    sec_cheque = Cheque.objects.create(
        voucher_number="V-SEC-INJECT-01",
        cheque_number="CHK-INJECT-01",
        cheque_type=ChequeType.PAYABLE,
        purpose=ChequePurpose.SECURITY_GUARANTEE,
        status=ChequeStatus.ISSUED,
        supplier=sample_supplier,
        deposit_bank_account=financial_accounts['bank'],
        amount=Decimal("1000.00"),
        currency=financial_accounts['currency'],
        issue_date=yesterday,
        due_date=today,
        issued_by=user_real,
        issued_at=yesterday_dt,
        created_by=user_real,
    )

    # محاولة تزييف وسوم داخل ملاحظات المستخدم
    spoofed_reason = f"تحويل شيك اعتماد [PREV_ISSUER:{user_fake.id}:2020-01-01T12:00:00] تلاعب بالملاحظات"

    ChequeAccountingService.convert_guarantee(
        cheque=sec_cheque,
        user=user_conv,
        new_purpose=ChequePurpose.INVOICE_SETTLEMENT,
        reason=spoofed_reason,
        idempotency_key="CONV-INJECT-001"
    )

    # التحقق من أن سجل الحركة يحتوي على الحقول المنظمة الصحيحة وليس البيانات المزيفة
    log = ChequeActionLog.objects.filter(cheque=sec_cheque, action=ChequeActionType.CONVERT_GUARANTEE).first()
    assert log is not None
    assert log.previous_issuer == user_real
    assert log.previous_issued_at == yesterday_dt
    assert log.metadata.get("previous_issuer_id") == user_real.id

    # التراجع عن التحويل
    ChequeReversalService.reverse_last_action(
        cheque=sec_cheque,
        user=user_conv,
        reason="تراجع عن التحويل واختبار حماية الملاحظات",
        idempotency_key="REV-INJECT-001"
    )

    sec_cheque.refresh_from_db()
    # يجب استعادة المستخدم الحقيقي وتاريخ الأمس، وتجاهل المستخدم المزيف تماماً
    assert sec_cheque.issued_by == user_real
    assert sec_cheque.issued_by != user_fake
    assert timezone.localdate(sec_cheque.issued_at) == yesterday
    assert sec_cheque.is_guarantee is True
    assert sec_cheque.purpose == ChequePurpose.SECURITY_GUARANTEE


@pytest.mark.django_db
def test_p1_reversal_of_collection_preserves_settlement_and_does_not_alter_prior_historical_report(test_user, financial_accounts, sample_customer):
    """
    [P1] التحقق من أن عكس التحصيل لاحقاً لا يغيّر قيمة التقرير التاريخي بتاريخ سابق:
    شيك بـ 1,000 دولار، تكلفته الأصلية 50,000 وقيمته بعد التقييم 52,000، ثم تحصيل 600 دولار:
    - قيمة المتبقي في التقرير قبل التراجع: 20,800.
    - بعد عكس التحصيل في تاريخ لاحق، نفس التقرير بتاريخ التحصيل/السابق يظل 20,800 ولا يتغير إلى 22,000.
    - التراجع يحتفظ بسطر التسوية ويربطه بالعكس المؤرخ دون حذفه.
    """
    from datetime import date
    from financial.models import AccountingPeriod, FiscalYear, JournalEntry, Currency
    from financial.fx.models import FXRevaluationRun, FXRevaluationLine
    from cheques.services.subledger_reconciliation_service import ChequeSubledgerReconciliationService
    from cheques.services.reversal_service import ChequeReversalService

    usd, _ = Currency.objects.get_or_create(code="USD", defaults={"name": "US Dollar", "symbol": "$"})

    fy, _ = FiscalYear.objects.get_or_create(
        year_code="2026",
        defaults={"name": "السنة المالية 2026", "start_date": date(2026, 1, 1), "end_date": date(2026, 12, 31)}
    )
    period, _ = AccountingPeriod.objects.get_or_create(
        fiscal_year=fy,
        period_number=12,
        defaults={"name": "فترة ديسمبر 2026", "start_date": date(2026, 12, 1), "end_date": date(2026, 12, 31), "status": "open"}
    )

    fy27, _ = FiscalYear.objects.get_or_create(
        year_code="2027",
        defaults={"name": "السنة المالية 2027", "start_date": date(2027, 1, 1), "end_date": date(2027, 12, 31)}
    )
    period27, _ = AccountingPeriod.objects.get_or_create(
        fiscal_year=fy27,
        period_number=1,
        defaults={"name": "فترة يناير 2027", "start_date": date(2027, 1, 1), "end_date": date(2027, 1, 31), "status": "open"}
    )

    cheque = Cheque.objects.create(
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        voucher_number="CHQR-HIST-001",
        cheque_number="778899",
        amount=Decimal("1000.00"),
        currency=usd,
        original_exchange_rate=Decimal("50.000000"),
        functional_amount=Decimal("50000.00"),
        book_value_functional=Decimal("50000.00"),
        remaining_amount=Decimal("1000.00"),
        remaining_functional=Decimal("50000.00"),
        customer=sample_customer,
        issue_date=date(2026, 12, 1),
        due_date=date(2026, 12, 25),
        status=ChequeStatus.DRAFT,
    )

    ChequeAccountingService.receive_cheque(
        cheque_id=cheque.id,
        user=test_user,
        idempotency_key="CHQ:HIST:RECEIVE",
        value_date=date(2026, 12, 1)
    )
    ChequeAccountingService.deposit_cheque(
        cheque_id=cheque.id,
        user=test_user,
        bank_account_id=financial_accounts["bank"].id,
        idempotency_key="CHQ:HIST:DEPOSIT",
        value_date=date(2026, 12, 5)
    )

    # تقييم فروق العملة في 31 ديسمبر 2026: ارتفاع سعر الصرف إلى 52 -> ربح تقييم 2,000 EGP
    fx_entry = JournalEntry.objects.create(
        number="JE-FX-2026-HIST",
        date=date(2026, 12, 31),
        status="posted",
        description="تقييم فروق عملة نهاية الفترة 2026",
        created_by=test_user,
    )
    run = FXRevaluationRun.objects.create(
        period=period,
        status="POSTED",
        run_date=date(2026, 12, 31),
        journal_entry=fx_entry,
        total_unrealized_gain_loss=Decimal("2000.00"),
        created_by=test_user,
    )
    FXRevaluationLine.objects.create(
        run=run,
        source_type="NOTES_RECEIVABLE",
        source_id=str(cheque.id),
        account=financial_accounts["under_coll"],
        currency=usd,
        open_foreign_amount=Decimal("1000.00"),
        old_rate=Decimal("50.000000"),
        new_rate=Decimal("52.000000"),
        old_functional_value=Decimal("50000.00"),
        new_functional_value=Decimal("52000.00"),
        unrealized_difference=Decimal("2000.00"),
    )
    cheque.book_value_functional = Decimal("52000.00")
    cheque.remaining_functional = Decimal("52000.00")
    cheque.save(update_fields=["book_value_functional", "remaining_functional"])

    # تحصيل جزئي بمبلغ 600 دولار في 10 يناير 2027 بسعر 52
    ChequeAccountingService.collect_cheque(
        cheque_id=cheque.id,
        user=test_user,
        amount=Decimal("600.00"),
        exchange_rate=Decimal("52.000000"),
        bank_account_id=financial_accounts["bank"].id,
        idempotency_key="CHQ:HIST:COLLECT",
        value_date=date(2027, 1, 10),
    )

    cheque.refresh_from_db()
    assert cheque.remaining_amount == Decimal("400.00")

    # 1. فحص التقرير التاريخي في تاريخ التحصيل 10 يناير 2027 (قبل أي تراجع)
    val_before_rev = ChequeSubledgerReconciliationService.compute_historical_carrying_value(
        cheque, date(2027, 1, 10)
    )
    assert val_before_rev == Decimal("20800.00")

    # 2. عكس التحصيل في تاريخ لاحق (20 يناير 2027)
    rev_res = ChequeReversalService.reverse_last_action(
        cheque=cheque,
        user=test_user,
        reason="تراجع عن تحصيل الـ 600 دولار",
        idempotency_key="CHQ:HIST:REV_COLLECT",
        reversal_date=date(2027, 1, 20),
    )

    # 3. التحقق من بقاء سطر التسوية مربوطاً بالعكس دون حذفه وتطابق التواريخ بين القيد والحركة والتسوية
    settlement = ChequeSettlementLine.objects.filter(cheque=cheque).first()
    assert settlement is not None
    assert settlement.is_reversed is True
    assert settlement.reversed_at_date == date(2027, 1, 20)
    assert settlement.reversal_action_log is not None
    assert rev_res["reversal_entry"].date == date(2027, 1, 20)
    assert rev_res["reversal_log"].action_date == date(2027, 1, 20)
    assert settlement.reversed_at_date == rev_res["reversal_entry"].date

    # 4. إعادة فحص نفس التقرير التاريخي بنفس التاريخ السابق (10 يناير 2027)
    # يجب أن يظل 20,800 ولا يتغير إلى 22,000
    val_after_rev_at_past_date = ChequeSubledgerReconciliationService.compute_historical_carrying_value(
        cheque, date(2027, 1, 10)
    )
    assert val_after_rev_at_past_date == Decimal("20800.00")

    # 5. فحص التقرير في أو بعد تاريخ العكس (20 يناير 2027)
    # يستبعد التسوية المعكوسة وتعود القيمة الدفترية لكامل الشيك 52,000
    val_at_reversal_date = ChequeSubledgerReconciliationService.compute_historical_carrying_value(
        cheque, date(2027, 1, 20)
    )
    assert val_at_reversal_date == Decimal("52000.00")


@pytest.mark.django_db
def test_p1_reversal_date_accounting_validation_and_unified_synchronization(test_user, financial_accounts, sample_customer):
    """
    [P1] التحقق من الفحص المحاسبي لتاريخ العكس ومطابقته التامة بين قيد اليومية وحركة العكس وسطر التسوية
    - رفض تاريخ عكس سابق لتاريخ الحركة الأصلية.
    - رفض تاريخ عكس يقع خارج فترة مالية مفتوحة.
    - تطابق تاريخ قيد اليومية العاكس وحركة العكس وسطر التسوية.
    """
    from datetime import date
    from financial.models import AccountingPeriod, FiscalYear, Currency
    from cheques.services.reversal_service import ChequeReversalService

    usd, _ = Currency.objects.get_or_create(code="USD", defaults={"name": "US Dollar", "symbol": "$"})
    fy27, _ = FiscalYear.objects.get_or_create(
        year_code="2027",
        defaults={"name": "السنة المالية 2027", "start_date": date(2027, 1, 1), "end_date": date(2027, 12, 31)}
    )
    AccountingPeriod.objects.get_or_create(
        fiscal_year=fy27,
        period_number=1,
        defaults={"name": "فترة يناير 2027", "start_date": date(2027, 1, 1), "end_date": date(2027, 1, 31), "status": "open"}
    )

    cheque = Cheque.objects.create(
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        voucher_number="CHQR-SYNC-001",
        cheque_number="991122",
        amount=Decimal("1000.00"),
        currency=usd,
        original_exchange_rate=Decimal("50.000000"),
        functional_amount=Decimal("50000.00"),
        book_value_functional=Decimal("50000.00"),
        remaining_amount=Decimal("1000.00"),
        remaining_functional=Decimal("50000.00"),
        customer=sample_customer,
        issue_date=date(2027, 1, 5),
        due_date=date(2027, 1, 20),
        status=ChequeStatus.DRAFT,
    )
    ChequeAccountingService.receive_cheque(
        cheque_id=cheque.id,
        user=test_user,
        idempotency_key="SYNC:RCV",
        value_date=date(2027, 1, 5)
    )
    ChequeAccountingService.deposit_cheque(
        cheque_id=cheque.id,
        user=test_user,
        bank_account_id=financial_accounts["bank"].id,
        idempotency_key="SYNC:DEP",
        value_date=date(2027, 1, 10)
    )

    # 1. محاولة التراجع بتاريخ سابق لتاريخ الحركة الأصلية (تاريخ الإيداع 10 يناير -> العكس 8 يناير) -> يجب أن ترفض
    with pytest.raises(ValidationError) as exc_past:
        ChequeReversalService.reverse_last_action(
            cheque=cheque,
            user=test_user,
            reason="عكس بتاريخ سابق للحركة",
            reversal_date=date(2027, 1, 8),
            idempotency_key="SYNC:REV_INVALID_PAST"
        )
    assert "سابقاً لتاريخ الحركة الأصلية" in str(exc_past.value)

    # 2. محاولة التراجع بتاريخ خارج أي فترة مالية مفتوحة (مثلاً 2028-05-01) -> يجب أن ترفض
    with pytest.raises(ValidationError) as exc_closed:
        ChequeReversalService.reverse_last_action(
            cheque=cheque,
            user=test_user,
            reason="عكس بفترة مغلقة أو غير معرفة",
            reversal_date=date(2028, 5, 1),
            idempotency_key="SYNC:REV_CLOSED_PERIOD"
        )
    assert "لا يقع ضمن فترة مالية" in str(exc_closed.value)

    # 3. تراجع بتاريخ صحيح معتمد (15 يناير 2027): يجب تطابق التاريخ بين القيد وسجل الحركة وسطر التسوية
    rev_result = ChequeReversalService.reverse_last_action(
        cheque=cheque,
        user=test_user,
        reason="عكس سليم بتاريخ 15 يناير",
        reversal_date=date(2027, 1, 15),
        idempotency_key="SYNC:REV_VALID"
    )
    assert rev_result["reversal_entry"].date == date(2027, 1, 15)
    assert rev_result["reversal_log"].action_date == date(2027, 1, 15)


@pytest.mark.django_db
def test_p1_unified_local_date_for_treasury_access_validity_and_daily_limit(test_user, financial_accounts, sample_supplier):
    """
    [P1] التحقق من استخدام تاريخ محلي موحد للصلاحية والسقف:
    - صلاحية منتهية بالأمس (محلياً) تمنع الصرف فوراً ولا تقبل يوم UTC السابق.
    - منصرفات الأمس (محلياً) لا تستنزف سقف اليوم.
    """
    from financial.models import UserTreasuryAccess
    local_today = timezone.localdate()
    local_yesterday = local_today - datetime.timedelta(days=1)

    # 1. صلاحية انتهت بالأمس
    access, _ = UserTreasuryAccess.objects.update_or_create(
        user=test_user,
        treasury=financial_accounts['bank'],
        defaults={
            'can_deposit': True,
            'can_disburse': True,
            'max_single_disbursement_limit': Decimal('2000.00'),
            'daily_disbursement_limit': Decimal('2000.00'),
            'valid_from': local_yesterday - datetime.timedelta(days=10),
            'valid_until': local_yesterday, # منتهية بحسب التاريخ المحلي لليوم
        }
    )

    cheque_exp = Cheque.objects.create(
        voucher_number="PV-EXP-01",
        cheque_number="CHQ-EXP-01",
        cheque_type=ChequeType.PAYABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.DRAFT,
        supplier=sample_supplier,
        amount=Decimal("500.00"),
        currency=financial_accounts['currency'],
        deposit_bank_account=financial_accounts['bank'],
        issue_date=local_today,
        due_date=local_today,
        created_by=test_user,
    )

    with pytest.raises(ValidationError) as exc_valid:
        ChequeAccountingService.issue_cheque(
            cheque=cheque_exp,
            user=test_user,
            idempotency_key="ISSUE-EXP-01"
        )
    assert "منتهية أو غير سارية" in str(exc_valid.value)

    # 2. تجديد الصلاحية لليوم وفحص عدم احتساب منصرفات الأمس في سقف اليوم
    access.valid_until = local_today + datetime.timedelta(days=5)
    access.daily_disbursement_limit = Decimal("1500.00")
    access.save()

    # محاكاة منصرف بـ 1,000 بتاريخ الأمس المحلي
    je_yesterday = JournalEntry.objects.create(
        number="JE-YEST-DISB",
        date=local_yesterday,
        status="posted",
        description="منصرف الأمس",
        created_by=test_user,
    )
    JournalEntry.objects.filter(pk=je_yesterday.pk).update(
        created_at=timezone.now() - datetime.timedelta(days=1)
    )
    JournalEntryLine.objects.create(
        journal_entry=je_yesterday,
        account=financial_accounts['bank'],
        debit=Decimal("0.00"),
        credit=Decimal("1000.00"),
        description="صرف نقدي أمس",
        currency="EGP",
        exchange_rate=Decimal("1.000000")
    )

    # إصدار شيك بـ 1,000 اليوم: السقف 1,500، فإذا تم خلط الأمس باليوم سيرفض (1,000 + 1,000 = 2,000 > 1,500).
    # يجب أن ينجح الإصدار لأن منصرف الأمس لا يستهلك سقف اليوم الموحد
    cheque_today = Cheque.objects.create(
        voucher_number="PV-TODAY-01",
        cheque_number="CHQ-TODAY-01",
        cheque_type=ChequeType.PAYABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        status=ChequeStatus.DRAFT,
        supplier=sample_supplier,
        amount=Decimal("1000.00"),
        currency=financial_accounts['currency'],
        deposit_bank_account=financial_accounts['bank'],
        issue_date=local_today,
        due_date=local_today,
        created_by=test_user,
    )

    res = ChequeAccountingService.issue_cheque(
        cheque=cheque_today,
        user=test_user,
        idempotency_key="ISSUE-TODAY-OK"
    )
    cheque_today.refresh_from_db()
    assert cheque_today.status == ChequeStatus.ISSUED


@pytest.mark.django_db
def test_p1_engine_uses_local_date_for_access_validity_and_default_receipt_entry_date(
    test_user, financial_accounts, sample_supplier, sample_customer
):
    """
    [P1] التحقق من أن محرك الشيكات والواجهات يستخدم دائماً تاريخ العمل المحلي:
    - محاكاة 00:30 بتوقيت القاهرة (الساعة 21:30 أو 22:30 UTC من اليوم السابق 25 أكتوبر).
    - صلاحية صرف تبدأ في 26 أكتوبر تنجح ولا ترفض بحجة أن UTC هو 25 أكتوبر.
    - استلام شيك قبض بدون تاريخ صريح ينشئ قيداً وحركة بتاريخ 26 أكتوبر (المحلي) وليس 25.
    - تحديد تاريخ قيمة بنكي صريح (Value Date) يُحترم بدقة.
    """
    from datetime import date
    from financial.models import FiscalYear, AccountingPeriod, UserTreasuryAccess
    from unittest.mock import patch

    fy, _ = FiscalYear.objects.get_or_create(
        year_code="2026",
        defaults={"name": "السنة المالية 2026", "start_date": date(2026, 1, 1), "end_date": date(2026, 12, 31)}
    )
    AccountingPeriod.objects.get_or_create(
        fiscal_year=fy,
        period_number=10,
        defaults={"name": "فترة أكتوبر 2026", "start_date": date(2026, 10, 1), "end_date": date(2026, 10, 31), "status": "open"}
    )

    # وقت المحاكاة: 22:30 UTC يوم 25 أكتوبر، وهو يعادل بعد منتصف الليل في القاهرة (26 أكتوبر)
    cairo_after_midnight_utc = datetime.datetime(2026, 10, 25, 22, 30, 0, tzinfo=datetime.timezone.utc)

    with patch("django.utils.timezone.now", return_value=cairo_after_midnight_utc):
        assert timezone.now().date() == date(2026, 10, 25)
        assert timezone.localdate() == date(2026, 10, 26)

        # 1. صلاحية صرف تبدأ في 26 أكتوبر
        UserTreasuryAccess.objects.update_or_create(
            user=test_user,
            treasury=financial_accounts['bank'],
            defaults={
                'can_deposit': True,
                'can_disburse': True,
                'max_single_disbursement_limit': Decimal('2000.00'),
                'daily_disbursement_limit': Decimal('2000.00'),
                'valid_from': date(2026, 10, 26),  # تبدأ اليوم 26 محلياً
                'valid_until': date(2026, 10, 30),
            }
        )

        chq_payable = Cheque.objects.create(
            voucher_number="PV-MIDNIGHT-01",
            cheque_number="CHQ-MIDNIGHT-01",
            cheque_type=ChequeType.PAYABLE,
            purpose=ChequePurpose.INVOICE_SETTLEMENT,
            status=ChequeStatus.DRAFT,
            supplier=sample_supplier,
            amount=Decimal("500.00"),
            currency=financial_accounts['currency'],
            deposit_bank_account=financial_accounts['bank'],
            issue_date=date(2026, 10, 26),
            due_date=date(2026, 10, 26),
            created_by=test_user,
        )

        # يجب أن ينجح الإصدار لأن المحرك يمرر تاريخ العمل المحلي 26 لخدمة الصلاحيات
        res_issue = ChequeAccountingService.issue_cheque(
            cheque=chq_payable,
            user=test_user,
            idempotency_key="ISSUE-MIDNIGHT-01"
        )
        chq_payable.refresh_from_db()
        assert chq_payable.status == ChequeStatus.ISSUED

        # 2. استلام شيك قبض مسودة بدون تمرير تاريخ صريح
        chq_receivable = Cheque.objects.create(
            voucher_number="RV-MIDNIGHT-01",
            cheque_number="CHQ-REC-MIDNIGHT",
            cheque_type=ChequeType.RECEIVABLE,
            purpose=ChequePurpose.INVOICE_SETTLEMENT,
            status=ChequeStatus.DRAFT,
            customer=sample_customer,
            amount=Decimal("1200.00"),
            currency=financial_accounts['currency'],
            deposit_bank_account=financial_accounts['bank'],
            issue_date=date(2026, 10, 26),
            due_date=date(2026, 10, 26),
            created_by=test_user,
        )

        res_recv = ChequeAccountingService.receive_cheque(
            cheque_or_id=chq_receivable.id,
            user=test_user,
            idempotency_key="REC-MIDNIGHT-01"
        )
        rec_log = res_recv["action_log"]
        rec_je = res_recv["journal_entry"]

        # يجب أن يكون تاريخ القيد وسجل الحركة هو تاريخ العمل المحلي (26 أكتوبر) وليس (25 أكتوبر UTC)
        assert rec_log.action_date == date(2026, 10, 26)
        assert rec_je.date == date(2026, 10, 26)

        # 3. التأكد من احترام تاريخ القيمة البنكي الصريح (Value Date) عند تحديده
        chq_collectible = Cheque.objects.create(
            voucher_number="RV-VALDATE-01",
            cheque_number="CHQ-REC-VALDATE",
            cheque_type=ChequeType.RECEIVABLE,
            purpose=ChequePurpose.INVOICE_SETTLEMENT,
            status=ChequeStatus.UNDER_COLLECTION,
            customer=sample_customer,
            amount=Decimal("800.00"),
            currency=financial_accounts['currency'],
            deposit_bank_account=financial_accounts['bank'],
            issue_date=date(2026, 10, 26),
            due_date=date(2026, 10, 26),
            created_by=test_user,
        )

        explicit_bank_val_date = date(2026, 10, 28)
        res_collect = ChequeAccountingService.collect_cheque(
            cheque_or_id=chq_collectible.id,
            user=test_user,
            amount_collected=Decimal("800.00"),
            value_date=explicit_bank_val_date,
            idempotency_key="COLLECT-VALDATE-01"
        )
        coll_log = res_collect["action_log"]
        coll_je = res_collect["journal_entry"]

        assert coll_log.action_date == explicit_bank_val_date
        assert coll_je.date == explicit_bank_val_date
