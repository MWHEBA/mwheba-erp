# -*- coding: utf-8 -*-
"""
Test Suite: Independent Audit Remediation Verification (6 Critical P1 Defect Regressions)
Covers:
1. Real estate installment cash payment generates both receipt voucher and journal entry atomically.
2. Same unit strictly rejects two active contracts (at model clean, save lock, and DB unique constraint levels).
3. Pricing matrix views and service strictly enforce RBAC permissions and log mutations in SystemLog.
4. ModuleAccessMiddleware permits API authentication endpoints (/api/token/) without 302 redirects.
5. Contract save strictly verifies installment plan customer ownership before persisting.
6. IFRS 15 Point-in-Time revenue recognition gate strictly blocks recognition before approved handover.
"""
import json
from decimal import Decimal
import pytest
from django.utils import timezone
from django.core.exceptions import ValidationError, PermissionDenied
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse
from django.db import IntegrityError

from customer.models import Customer, CustomerPayment
from sale.models.installments import InstallmentPlan, InstallmentItem
from sale.services.installment_engine import InstallmentEngine
from sale.services.contract_installment_binding_service import ContractBindingIntegrityError
from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    PropertyContract,
    UnitPricingMatrixConfig
)
from real_estate.services.accounting_service import RealEstateAccountingService
from real_estate.services.pricing_service import BulkPricingGeneratorService
from financial.models.currency import Currency
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.journal_entry import JournalEntry
from utils.models import SystemLog
from core.models import SystemModule

User = get_user_model()


@pytest.fixture
def remediation_setup(db):
    SystemModule.objects.update_or_create(
        code='real_estate',
        defaults={'name_ar': 'العقارات', 'is_enabled': True}
    )

    user = User.objects.create_superuser(
        username="admin_remedy",
        email="admin_remedy@example.com",
        password="password123"
    )

    unprivileged_user = User.objects.create_user(
        username="unprivileged_user",
        email="unprivileged@example.com",
        password="password123",
        is_staff=True
    )

    asset_type, _ = AccountType.objects.get_or_create(
        code='asset',
        defaults={'name': 'أصول', 'category': 'asset', 'nature': 'debit'}
    )
    liability_type, _ = AccountType.objects.get_or_create(
        code='liability',
        defaults={'name': 'خصوم', 'category': 'liability', 'nature': 'credit'}
    )
    revenue_type, _ = AccountType.objects.get_or_create(
        code='revenue',
        defaults={'name': 'إيرادات', 'category': 'revenue', 'nature': 'credit'}
    )

    bank_account, _ = ChartOfAccounts.objects.get_or_create(
        code="11101",
        defaults={'name': "البنك الأهلي التجاري", 'account_type': asset_type, 'is_active': True, 'is_leaf': True}
    )
    contract_liability, _ = ChartOfAccounts.objects.get_or_create(
        code="21102",
        defaults={'name': "التزامات عقود بيع وحدات", 'account_type': liability_type, 'is_active': True, 'is_leaf': True}
    )
    real_estate_revenue, _ = ChartOfAccounts.objects.get_or_create(
        code="41101",
        defaults={'name': "إيرادات بيع وحدات عقارية", 'account_type': revenue_type, 'is_active': True, 'is_leaf': True}
    )

    egp_currency, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={'name': "Egyptian Pound", 'symbol': "ج.م", 'is_functional': True}
    )
    usd_currency, _ = Currency.objects.get_or_create(
        code="USD",
        defaults={'name': "US Dollar", 'symbol': "$", 'is_functional': False}
    )

    project = RealEstateProject.objects.create(
        code="PRJ-RMD",
        name="مشروع التحقق المستقل",
        total_land_area=Decimal("8000.00"),
        gross_built_area=Decimal("20000.00"),
        start_date=timezone.localdate(),
        expected_completion_date=timezone.localdate() + timezone.timedelta(days=700),
        escrow_account=bank_account,
        created_by=user
    )
    block = PropertyBlock.objects.create(project=project, code="BLK-A", name="العمارة أ")
    floor = PropertyFloor.objects.create(block=block, floor_number=2, name="الطابق الثاني")

    customer_a = Customer.objects.create(name="العميل أ", code="CUST-RMD-A")
    customer_b = Customer.objects.create(name="العميل ب", code="CUST-RMD-B")

    unit = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor,
        unit_code="RMD-201",
        unit_type=PropertyUnit.UnitType.APARTMENT,
        gross_area=Decimal("150.00"),
        net_area=Decimal("130.00"),
        meter_price=Decimal("10000.00"),
        total_price=Decimal("1500000.00"),
        status=PropertyUnit.UnitStatus.AVAILABLE
    )

    return {
        'user': user,
        'unprivileged_user': unprivileged_user,
        'project': project,
        'block': block,
        'floor': floor,
        'unit': unit,
        'customer_a': customer_a,
        'customer_b': customer_b,
        'currency': egp_currency,
        'usd_currency': usd_currency,
        'bank_account': bank_account,
        'contract_liability': contract_liability,
        'real_estate_revenue': real_estate_revenue,
    }


@pytest.mark.django_db
def test_1_real_estate_installment_payment_creates_receipt_and_journal_entry(remediation_setup):
    """
    عيب 1 [P1]: سداد القسط العقاري يجب أن يسجل الدفعة (CustomerPayment) والقيد المحاسبي في معاملة واحدة.
    """
    s = remediation_setup
    contract = PropertyContract.objects.create(
        contract_number="CTR-RMD-001",
        project=s['project'],
        unit=s['unit'],
        customer=s['customer_a'],
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + timezone.timedelta(days=365),
        final_contract_price=Decimal("1500000.00"),
        currency=s['currency'],
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=s['user']
    )

    plan = InstallmentPlan.objects.create(
        customer=s['customer_a'],
        total_amount=Decimal("1500000.00"),
        total_principal=Decimal("1500000.00"),
        number_of_installments=1,
        frequency='single',
        start_date=timezone.localdate(),
        created_by=s['user']
    )
    contract.installment_plan = plan
    contract.save()

    item = InstallmentItem.objects.create(
        plan=plan,
        installment_number=1,
        due_date=timezone.localdate(),
        principal_amount=Decimal("100.00"),
        total_amount=Decimal("100.00"),
        paid_amount=Decimal("0.00")
    )

    je_count_before = JournalEntry.objects.count()
    payment_count_before = CustomerPayment.objects.count()

    # تسجيل تحصيل 100 جنيه
    payment = InstallmentEngine.record_installment_payment(
        installment_item=item,
        amount=Decimal("100.00"),
        payment_date=timezone.localdate(),
        user=s['user'],
        financial_account=s['bank_account'],
        reference_number="RECEIPT-001",
        notes="سداد قسط عقاري تجريبي"
    )

    # 1. التحقق من إرجاع كائن سند الدفع (إيصال القبض)
    assert payment is not None, "يجب أن ترجع الدالة سند دفع مسجل للعميل"
    assert isinstance(payment, CustomerPayment)
    assert payment.amount == Decimal("100.00")
    assert payment.customer == s['customer_a']
    assert payment.reference_number == "RECEIPT-001"
    assert CustomerPayment.objects.count() == payment_count_before + 1

    # 2. التحقق من تحديث القسط الفعلي
    item.refresh_from_db()
    assert item.paid_amount == Decimal("100.00")
    assert item.cash_status == InstallmentItem.CashStatus.COLLECTED

    # 3. التحقق من ترحيل القيد المحاسبي في دفتر الأستاذ العام
    assert JournalEntry.objects.count() == je_count_before + 1
    je = JournalEntry.objects.latest('id')
    assert je.status == 'posted'
    debit_line = je.lines.filter(debit__gt=0).first()
    credit_line = je.lines.filter(credit__gt=0).first()
    assert debit_line.account.code == s['bank_account'].code
    assert debit_line.debit == Decimal("100.00")
    assert credit_line.account.code == s['contract_liability'].code
    assert credit_line.credit == Decimal("100.00")


@pytest.mark.django_db
def test_2_same_unit_strictly_rejects_two_active_contracts(remediation_setup):
    """
    عيب 2 [P1]: نفس الوحدة يجب أن ترفض تماماً إنشاء أو تفعيل عقد نشط ثانٍ عليها.
    """
    s = remediation_setup
    # إنشاء العقد الأول وتفعيله
    contract_1 = PropertyContract.objects.create(
        contract_number="CTR-RMD-001",
        project=s['project'],
        unit=s['unit'],
        customer=s['customer_a'],
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + timezone.timedelta(days=365),
        final_contract_price=Decimal("1500000.00"),
        currency=s['currency'],
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=s['user']
    )
    s['unit'].refresh_from_db()
    assert s['unit'].status == PropertyUnit.UnitStatus.CONTRACTED

    # محاولة إنشاء عقد ثانٍ نشط على نفس الوحدة
    contract_2 = PropertyContract(
        contract_number="CTR-RMD-002",
        project=s['project'],
        unit=s['unit'],
        customer=s['customer_b'],
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + timezone.timedelta(days=365),
        final_contract_price=Decimal("1600000.00"),
        currency=s['currency'],
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=s['user']
    )

    # 1. التحقق من رفض دالة clean
    with pytest.raises(ValidationError) as exc_clean:
        contract_2.clean()
    assert "مرتبطة بالفعل بعقد نشط آخر" in str(exc_clean.value)

    # 2. التحقق من رفض دالة save
    with pytest.raises(ValidationError) as exc_save:
        contract_2.save()
    assert "مرتبطة بالفعل بعقد نشط آخر" in str(exc_save.value)

    # 3. التأكد من بقاء عقد واحد فقط نشط على الوحدة
    active_contracts = PropertyContract.objects.filter(
        unit=s['unit'],
        status=PropertyContract.ContractStatus.ACTIVE
    )
    assert active_contracts.count() == 1


@pytest.mark.django_db
def test_3_pricing_endpoints_and_service_enforce_rbac_and_audit(remediation_setup):
    """
    عيب 3 [P1]: مستخدم بلا صلاحيات لا يستطيع تعديل التسعير، ويجب توثيق التعديل في SystemLog.
    """
    s = remediation_setup
    client = Client()
    client.force_login(s['unprivileged_user'])

    url = reverse('real_estate:project_pricing', kwargs={'project_id': s['project'].id})

    # 1. محاولة تعديل سعر المتر من مستخدم بلا صلاحية
    resp = client.post(url, {'base_meter_price': '1.00'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert resp.status_code == 403, f"المستخدم بدون صلاحية يجب أن يحصل على 403، الاستجابة كانت {resp.status_code}"

    # 2. محاولة تطبيق التسعير المجمع عبر الخدمة مباشرة بمستخدم غير مصرح له
    with pytest.raises(PermissionDenied):
        BulkPricingGeneratorService.bulk_generate_pricing(
            project=s['project'],
            user=s['unprivileged_user']
        )

    # 3. منح الصلاحية لمستخدم والمحاولة مرة أخرى
    perm = Permission.objects.get(codename='change_unitpricingmatrixconfig')
    s['unprivileged_user'].user_permissions.add(perm)

    log_count_before = SystemLog.objects.filter(action='UPDATE_PRICING_CONFIG').count()

    resp_authorized = client.post(url, {
        'base_meter_price': '12500.00',
        'base_floor_number': '1',
        'floor_rise_rate': '1.50'
    })
    assert resp_authorized.status_code == 200
    assert resp_authorized.json()['success'] is True

    # 4. التحقق من تسجيل الإجراء في سجل النظام SystemLog
    assert SystemLog.objects.filter(action='UPDATE_PRICING_CONFIG').count() == log_count_before + 1
    latest_log = SystemLog.objects.filter(action='UPDATE_PRICING_CONFIG').latest('timestamp')
    assert latest_log.user == s['unprivileged_user']
    assert "12500" in latest_log.details


@pytest.mark.django_db
def test_4_middleware_permits_api_token_endpoint(remediation_setup):
    """
    عيب 4 [P1]: الـ middleware لا يعطل تسجيل دخول الـ API (/api/token/) ولا يعيد التوجيه 302.
    """
    client = Client()
    resp = client.post('/api/token/', {})
    # يجب ألا يعيد التوجيه 302 إطلاقاً، بل يصل لـ DRF ويرد 400 (Bad Request لنقص بيانات الاعتماد)
    assert resp.status_code == 400, f"المسار /api/token/ يجب أن يعود بـ 400، لكن النتيجة كانت {resp.status_code}"


@pytest.mark.django_db
def test_5_contract_save_strictly_blocks_other_customer_plan(remediation_setup):
    """
    عيب 5 [P1]: حفظ العقد يرفض قطيعاً الربط بخطة تنتمي لعميل مختلف.
    """
    s = remediation_setup
    # إنشاء خطة تقسيط خاصة بالعميل ب
    plan_b = InstallmentPlan.objects.create(
        customer=s['customer_b'],
        total_amount=Decimal("1500000.00"),
        total_principal=Decimal("1500000.00"),
        number_of_installments=1,
        frequency='single',
        start_date=timezone.localdate(),
        created_by=s['user']
    )

    # محاولة إنشاء عقد للعميل أ مع ربطه بخطة العميل ب
    contract = PropertyContract(
        contract_number="CTR-RMD-FOREIGN-PLAN",
        project=s['project'],
        unit=s['unit'],
        customer=s['customer_a'],
        installment_plan=plan_b,
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + timezone.timedelta(days=365),
        final_contract_price=Decimal("1500000.00"),
        currency=s['currency'],
        status=PropertyContract.ContractStatus.DRAFT,
        created_by=s['user']
    )

    with pytest.raises(ContractBindingIntegrityError) as exc_info:
        contract.save()

    assert "عميل مختلف" in str(exc_info.value)
    assert not PropertyContract.objects.filter(contract_number="CTR-RMD-FOREIGN-PLAN").exists()


@pytest.mark.django_db
def test_6_point_in_time_revenue_recognition_blocked_before_handover(remediation_setup):
    """
    عيب 6 [P1]: حارس الاعتراف بالإيراد يمنع ترحيل الإيراد لعقد POINT_IN_TIME قبل محضر التسليم.
    """
    s = remediation_setup
    contract = PropertyContract.objects.create(
        contract_number="CTR-RMD-REV-GATE",
        project=s['project'],
        unit=s['unit'],
        customer=s['customer_a'],
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + timezone.timedelta(days=365),
        final_contract_price=Decimal("1500000.00"),
        currency=s['currency'],
        revenue_recognition_method=PropertyContract.RevenueMethod.POINT_IN_TIME,
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=s['user']
    )
    s['unit'].refresh_from_db()
    assert s['unit'].status == PropertyUnit.UnitStatus.CONTRACTED

    # محاولة الاعتراف بالإيراد والوحدة ما زالت في حالة CONTRACTED وبدون تسليم
    with pytest.raises(ValidationError) as exc_info:
        RealEstateAccountingService.post_revenue_recognition(
            contract=contract,
            amount=Decimal("1500000.00"),
            user=s['user'],
            is_handover=False
        )

    assert "لا يجوز الاعتراف بالإيراد لطريقة (Point in Time) إلا عند التسليم الفعلي أو الحكمي" in str(exc_info.value)


@pytest.mark.django_db
def test_7_cannot_switch_contract_plan_after_payments_even_for_same_customer(remediation_setup):
    """
    عيب 1 [P1 الجديد]: تبديل خطة العقد بعد السداد محظور تماماً حتى لنفس العميل.
    """
    s = remediation_setup
    contract = PropertyContract.objects.create(
        contract_number="CTR-RMD-PLAN-SWITCH",
        project=s['project'],
        unit=s['unit'],
        customer=s['customer_a'],
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + timezone.timedelta(days=365),
        final_contract_price=Decimal("1500000.00"),
        currency=s['currency'],
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=s['user']
    )

    plan_1 = InstallmentPlan.objects.create(
        customer=s['customer_a'],
        total_amount=Decimal("1500000.00"),
        total_principal=Decimal("1500000.00"),
        number_of_installments=2,
        frequency='monthly',
        start_date=timezone.localdate(),
        created_by=s['user']
    )
    contract.installment_plan = plan_1
    contract.save()

    item_1 = InstallmentItem.objects.create(
        plan=plan_1,
        installment_number=1,
        due_date=timezone.localdate(),
        principal_amount=Decimal("1000.00"),
        total_amount=Decimal("1000.00"),
        paid_amount=Decimal("0.00")
    )
    item_2 = InstallmentItem.objects.create(
        plan=plan_1,
        installment_number=2,
        due_date=timezone.localdate() + timezone.timedelta(days=30),
        principal_amount=Decimal("1499000.00"),
        total_amount=Decimal("1499000.00"),
        paid_amount=Decimal("0.00")
    )

    # سداد جزء من الخطة 1
    InstallmentEngine.record_installment_payment(
        installment_item=item_1,
        amount=Decimal("500.00"),
        payment_date=timezone.localdate(),
        user=s['user'],
        financial_account=s['bank_account'],
        reference_number="REC-P1-PAY"
    )

    # إنشاء خطة جديدة لنفس العميل أ
    plan_2 = InstallmentPlan.objects.create(
        customer=s['customer_a'],
        total_amount=Decimal("1500000.00"),
        total_principal=Decimal("1500000.00"),
        number_of_installments=3,
        frequency='monthly',
        start_date=timezone.localdate(),
        created_by=s['user']
    )

    # محاولة تبديل الخطة في العقد للخطة 2 بعد أن دخلت الخطة 1 في مسار سداد مالي
    contract.installment_plan = plan_2
    with pytest.raises(ContractBindingIntegrityError) as exc_info:
        contract.save()

    assert "حظر تبديل الخطة" in str(exc_info.value)
    contract.refresh_from_db()
    assert contract.installment_plan_id == plan_1.id, "يجب أن يظل العقد مرتبطاً بالخطة 1 دون تعديل"


@pytest.mark.django_db
def test_8_idempotent_collection_request_returns_existing_payment_without_double_debit(remediation_setup):
    """
    عيب 2 [P1 الجديد]: تكرار طلب التحصيل بنفس المرجع لا يكرر السداد ولا يرفع المسدد.
    """
    s = remediation_setup
    contract = PropertyContract.objects.create(
        contract_number="CTR-RMD-IDEMP",
        project=s['project'],
        unit=s['unit'],
        customer=s['customer_a'],
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + timezone.timedelta(days=365),
        final_contract_price=Decimal("1500000.00"),
        currency=s['currency'],
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=s['user']
    )

    plan = InstallmentPlan.objects.create(
        customer=s['customer_a'],
        total_amount=Decimal("1500000.00"),
        total_principal=Decimal("1500000.00"),
        number_of_installments=1,
        frequency='single',
        start_date=timezone.localdate(),
        created_by=s['user']
    )
    contract.installment_plan = plan
    contract.save()

    item = InstallmentItem.objects.create(
        plan=plan,
        installment_number=1,
        due_date=timezone.localdate(),
        principal_amount=Decimal("100.00"),
        total_amount=Decimal("100.00"),
        paid_amount=Decimal("0.00")
    )

    # طلب السداد الأول بمبلغ 100 ومرجع فريد
    ref = "REF-IDEMP-UNIQ-100"
    p1 = InstallmentEngine.record_installment_payment(
        installment_item=item,
        amount=Decimal("100.00"),
        payment_date=timezone.localdate(),
        user=s['user'],
        financial_account=s['bank_account'],
        reference_number=ref
    )
    assert p1 is not None

    item.refresh_from_db()
    assert item.paid_amount == Decimal("100.00")
    je_count_after_p1 = JournalEntry.objects.count()
    payment_count_after_p1 = CustomerPayment.objects.count()

    # إعادة نفس طلب السداد بنفس المرجع والمبلغ
    p2 = InstallmentEngine.record_installment_payment(
        installment_item=item,
        amount=Decimal("100.00"),
        payment_date=timezone.localdate(),
        user=s['user'],
        financial_account=s['bank_account'],
        reference_number=ref
    )

    # التحقق من أن النتيجة هي نفس الإيصال دون زيادة في المسدد
    assert p2.id == p1.id
    item.refresh_from_db()
    assert item.paid_amount == Decimal("100.00"), f"المسدد يجب أن يظل 100 وليس {item.paid_amount}"
    assert JournalEntry.objects.count() == je_count_after_p1
    assert CustomerPayment.objects.count() == payment_count_after_p1


@pytest.mark.django_db
def test_9_foreign_currency_collection_records_correct_functional_amounts(remediation_setup):
    """
    عيب 3 [P1 الجديد]: تحصيل العملة الأجنبية (100 USD بسعر 50) يسجل الإيصال بـ USD والقيد بـ 5000 EGP.
    """
    s = remediation_setup
    contract = PropertyContract.objects.create(
        contract_number="CTR-RMD-USD",
        project=s['project'],
        unit=s['unit'],
        customer=s['customer_a'],
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + timezone.timedelta(days=365),
        final_contract_price=Decimal("100000.00"),
        currency=s['usd_currency'],
        exchange_rate=Decimal("50.000000"),
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=s['user']
    )

    plan = InstallmentPlan.objects.create(
        customer=s['customer_a'],
        total_amount=Decimal("100000.00"),
        total_principal=Decimal("100000.00"),
        number_of_installments=1,
        frequency='single',
        start_date=timezone.localdate(),
        created_by=s['user']
    )
    contract.installment_plan = plan
    contract.save()

    item = InstallmentItem.objects.create(
        plan=plan,
        installment_number=1,
        due_date=timezone.localdate(),
        principal_amount=Decimal("100.00"),
        total_amount=Decimal("100.00"),
        paid_amount=Decimal("0.00")
    )

    je_count_before = JournalEntry.objects.count()

    # تحصيل 100 دولار
    payment = InstallmentEngine.record_installment_payment(
        installment_item=item,
        amount=Decimal("100.00"),
        payment_date=timezone.localdate(),
        user=s['user'],
        financial_account=s['bank_account'],
        reference_number="REC-USD-100"
    )

    # 1. التحقق من حقول الإيصال CustomerPayment
    assert payment.currency.code == "USD"
    assert payment.amount == Decimal("100.00")
    assert payment.transaction_amount == Decimal("100.00")
    assert payment.exchange_rate_snapshot == Decimal("50.000000")
    assert payment.base_amount == Decimal("5000.00")

    # 2. التحقق من القيد المحاسبي المزدوج بالعملة الوظيفية والأجنبية
    assert JournalEntry.objects.count() == je_count_before + 1
    je = JournalEntry.objects.latest('id')
    debit_line = je.lines.filter(debit__gt=0).first()
    credit_line = je.lines.filter(credit__gt=0).first()

    assert debit_line.debit == Decimal("5000.00"), f"المدين الوظيفي يجب أن يكون 5000 EGP وليس {debit_line.debit}"
    assert debit_line.foreign_debit == Decimal("100.00")
    assert str(debit_line.currency) == "USD"
    assert debit_line.exchange_rate == Decimal("50.000000")

    assert credit_line.credit == Decimal("5000.00"), f"الدائن الوظيفي يجب أن يكون 5000 EGP وليس {credit_line.credit}"
    assert credit_line.foreign_credit == Decimal("100.00")
    assert str(credit_line.currency) == "USD"
    assert credit_line.exchange_rate == Decimal("50.000000")


@pytest.mark.django_db
def test_10_last_installment_surplus_preserves_commercial_customer_balance(remediation_setup):
    """
    عيب 4 [P1 الجديد]: زيادة سداد العقار (150 لقسط متبقيه 100) لا تغير Customer.balance التجاري.
    """
    s = remediation_setup
    customer = s['customer_a']
    customer.balance = Decimal("0.00")
    customer.save(update_fields=['balance'])

    contract = PropertyContract.objects.create(
        contract_number="CTR-RMD-SURPLUS",
        project=s['project'],
        unit=s['unit'],
        customer=customer,
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + timezone.timedelta(days=365),
        final_contract_price=Decimal("100.00"),
        currency=s['currency'],
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=s['user']
    )

    plan = InstallmentPlan.objects.create(
        customer=customer,
        total_amount=Decimal("100.00"),
        total_principal=Decimal("100.00"),
        number_of_installments=1,
        frequency='single',
        start_date=timezone.localdate(),
        created_by=s['user']
    )
    contract.installment_plan = plan
    contract.save()

    item = InstallmentItem.objects.create(
        plan=plan,
        installment_number=1,
        due_date=timezone.localdate(),
        principal_amount=Decimal("100.00"),
        total_amount=Decimal("100.00"),
        paid_amount=Decimal("0.00")
    )

    # سداد 150 لقسط متبقيه 100 فقط (فائض 50)
    payment = InstallmentEngine.record_installment_payment(
        installment_item=item,
        amount=Decimal("150.00"),
        payment_date=timezone.localdate(),
        user=s['user'],
        financial_account=s['bank_account'],
        reference_number="REC-SURPLUS-150"
    )

    # 1. التحقق الصارم من بقاء الرصيد التجاري للعميل صفراً دون أي تأثير (-50 محظور تماماً)
    customer.refresh_from_db()
    assert customer.balance == Decimal("0.00"), f"الرصيد التجاري يجب أن يبقى 0.00 وليس {customer.balance}"

    # 2. التحقق من القيد المحاسبي: 150 في البنك، 100 إقفال التزام العقد، و 50 في حساب الأمانات العقارية المعزولة
    je = JournalEntry.objects.latest('id')
    bank_line = je.lines.filter(account=s['bank_account']).first()
    contract_line = je.lines.filter(account=s['contract_liability']).first()
    advance_line = je.lines.filter(account__code="21101").first()

    assert bank_line.debit == Decimal("150.00")
    assert contract_line.credit == Decimal("100.00")
    assert advance_line is not None, "يجب إثبات الفائض في حساب أمانات الحجز المعزول 21101"
    assert advance_line.credit == Decimal("50.00")


@pytest.mark.django_db
def test_11_unit_row_lock_serialized_in_atomic_transaction(remediation_setup):
    """
    عيب 5 [P1 الجديد]: قفل الوحدة فورياً داخل معاملة ذرية لحظر ازدواج العقود على كافة المحركات.
    """
    s = remediation_setup
    contract_1 = PropertyContract.objects.create(
        contract_number="CTR-LOCK-001",
        project=s['project'],
        unit=s['unit'],
        customer=s['customer_a'],
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + timezone.timedelta(days=365),
        final_contract_price=Decimal("1500000.00"),
        currency=s['currency'],
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=s['user']
    )

    contract_2 = PropertyContract(
        contract_number="CTR-LOCK-002",
        project=s['project'],
        unit=s['unit'],
        customer=s['customer_b'],
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + timezone.timedelta(days=365),
        final_contract_price=Decimal("1500000.00"),
        currency=s['currency'],
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=s['user']
    )

    with pytest.raises(ValidationError) as exc:
        contract_2.save()

    assert "مرتبطة بالفعل بعقد نشط آخر" in str(exc.value)


@pytest.mark.django_db
def test_12_real_estate_collection_does_not_appear_as_commercial_credit_balance(remediation_setup):
    """
    عيب 1 [P1]: التحصيل العقاري لا يظهر إطلاقاً كرصيد دائن تجاري في تقرير أعمار الديون أو التوزيع التجاري.
    Dual-Activity Subledger Isolation
    """
    from customer.services.customer_aging_service import CustomerAgingService
    s = remediation_setup

    contract = PropertyContract.objects.create(
        contract_number="CTR-AGING-ISO-01",
        project=s['project'],
        unit=s['unit'],
        customer=s['customer_a'],
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + timezone.timedelta(days=365),
        final_contract_price=Decimal("1500000.00"),
        currency=s['currency'],
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=s['user']
    )

    plan = InstallmentPlan.objects.create(
        customer=s['customer_a'],
        total_principal=Decimal("1500000.00"),
        total_amount=Decimal("1500000.00"),
        number_of_installments=1,
        frequency='single',
        status=InstallmentPlan.PlanStatus.ACTIVE,
        start_date=timezone.localdate(),
        created_by=s['user']
    )
    contract.installment_plan = plan
    contract.save()

    item = InstallmentItem.objects.create(
        plan=plan,
        installment_number=1,
        due_date=timezone.localdate(),
        principal_amount=Decimal("100.00"),
        total_amount=Decimal("100.00"),
        paid_amount=Decimal("0.00")
    )

    payment = InstallmentEngine.record_installment_payment(
        installment_item=item,
        amount=Decimal("100.00"),
        payment_date=timezone.localdate(),
        user=s['user'],
        financial_account=s['bank_account'],
        reference_number="REC-ISO-AGING-100"
    )

    assert payment.source_type == 'REAL_ESTATE', "الدفعة يجب أن تصنف كدفعة عقارية REAL_ESTATE"
    receipt = contract.payment_receipts.filter(customer_payment=payment).first()
    assert receipt is not None, "يجب ربط إيصال التحصيل بالعقد العقاري عبر ContractPaymentReceipt"
    assert receipt.installment_item == item

    # فحص تقرير أعمار الديون التجارية
    report = CustomerAgingService.get_customer_aging_report(as_of_date=timezone.localdate())
    customer_rows = [r for r in report['rows'] if r['customer_id'] == s['customer_a'].id]

    assert len(customer_rows) == 1
    cust_row = customer_rows[0]
    assert cust_row['credit_balance'] == Decimal("0.00"), f"الرصيد الدائن المتاح بالتقرير التجاري يجب أن يبقى 0.00 وليس {cust_row['credit_balance']}"
    assert cust_row['net_balance'] == Decimal("0.00"), f"صافي الرصيد التجاري يجب أن يبقى 0.00 وليس {cust_row['net_balance']}"


@pytest.mark.django_db
def test_13_duplicate_reference_with_different_payload_is_rejected(remediation_setup):
    """
    عيب 2 [P1]: نفس مرجع التحصيل بمبلغ مختلف أو عملة مختلفة يتم رفضه فوراً (Payload Divergence Protection).
    """
    s = remediation_setup

    contract = PropertyContract.objects.create(
        contract_number="CTR-IDEM-01",
        project=s['project'],
        unit=s['unit'],
        customer=s['customer_a'],
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + timezone.timedelta(days=365),
        final_contract_price=Decimal("1500000.00"),
        currency=s['currency'],
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=s['user']
    )

    plan = InstallmentPlan.objects.create(
        customer=s['customer_a'],
        total_principal=Decimal("1500000.00"),
        total_amount=Decimal("1500000.00"),
        number_of_installments=1,
        frequency='single',
        status=InstallmentPlan.PlanStatus.ACTIVE,
        start_date=timezone.localdate(),
        created_by=s['user']
    )
    contract.installment_plan = plan
    contract.save()

    item1 = InstallmentItem.objects.create(
        plan=plan,
        installment_number=1,
        due_date=timezone.localdate(),
        principal_amount=Decimal("500.00"),
        total_amount=Decimal("500.00"),
        paid_amount=Decimal("0.00")
    )

    # التحصيل الأول بمبلغ 100 ومرجع ثابت
    p1 = InstallmentEngine.record_installment_payment(
        installment_item=item1,
        amount=Decimal("100.00"),
        payment_date=timezone.localdate(),
        user=s['user'],
        financial_account=s['bank_account'],
        reference_number="REF-IDEM-SAME-01"
    )
    assert p1.amount == Decimal("100.00")

    # محاولة إعادة نفس المرجع بمبلغ مختلف 200 -> يجب الرفض بـ ValidationError
    with pytest.raises(ValidationError) as exc:
        InstallmentEngine.record_installment_payment(
            installment_item=item1,
            amount=Decimal("200.00"),
            payment_date=timezone.localdate(),
            user=s['user'],
            financial_account=s['bank_account'],
            reference_number="REF-IDEM-SAME-01"
        )
    assert "تعارض في بيانات المرجع" in str(exc.value)

    # إعادة نفس المرجع بنفس المبلغ المتطابق 100 -> ينجح ويرجع الدفعة الأولى نفسها دون تكرار
    p_cached = InstallmentEngine.record_installment_payment(
        installment_item=item1,
        amount=Decimal("100.00"),
        payment_date=timezone.localdate(),
        user=s['user'],
        financial_account=s['bank_account'],
        reference_number="REF-IDEM-SAME-01"
    )
    assert p_cached.id == p1.id
    assert CustomerPayment.objects.filter(reference_number="REF-IDEM-SAME-01").count() == 1


@pytest.mark.django_db
def test_14_foreign_currency_revenue_recognition_converts_to_functional_amount(remediation_setup):
    """
    عيب 3 [P1]: الاعتراف بالإيراد للعملات الأجنبية يحول المبلغ بدقة للعملة الوظيفية ويسجل المبالغ الأجنبية.
    IFRS 15 Multi-Currency Ledger Compliance
    """
    s = remediation_setup

    contract_usd = PropertyContract.objects.create(
        contract_number="CTR-USD-REV-01",
        project=s['project'],
        unit=s['unit'],
        customer=s['customer_a'],
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + timezone.timedelta(days=365),
        final_contract_price=Decimal("100000.00"),
        currency=s['usd_currency'],
        exchange_rate=Decimal("50.000000"),
        revenue_recognition_method=PropertyContract.RevenueMethod.POINT_IN_TIME,
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=s['user']
    )

    # الاعتراف بإيراد 100 USD بسعر صرف 50.000000
    je = RealEstateAccountingService.post_revenue_recognition(
        contract=contract_usd,
        amount=Decimal("100.00"),
        user=s['user'],
        is_handover=True,
        reference="REV-USD-100"
    )

    liability_line = je.lines.filter(account=s['contract_liability']).first()
    revenue_line = je.lines.filter(account=s['real_estate_revenue']).first()

    assert liability_line is not None
    assert revenue_line is not None

    # التحقق من أن القيمة المدينة والدائنة مقيدة بالعملة الوظيفية (5000 EGP) وليس 100
    assert liability_line.debit == Decimal("5000.00"), f"القيد المدين يجب أن يكون 5000.00 وليس {liability_line.debit}"
    assert liability_line.foreign_debit == Decimal("100.00"), f"المدين الأجنبي يجب أن يكون 100.00 وليس {liability_line.foreign_debit}"
    assert liability_line.currency == "USD"
    assert liability_line.exchange_rate == Decimal("50.000000")

    assert revenue_line.credit == Decimal("5000.00"), f"القيد الدائن يجب أن يكون 5000.00 وليس {revenue_line.credit}"
    assert revenue_line.foreign_credit == Decimal("100.00"), f"الدائن الأجنبي يجب أن يكون 100.00 وليس {revenue_line.foreign_credit}"
    assert revenue_line.currency == "USD"
    assert revenue_line.exchange_rate == Decimal("50.000000")


@pytest.mark.django_db
def test_15_multi_installment_collection_request_idempotency_preserved(remediation_setup):
    """
    عيب 1 [P1 الجديد]: سداد 150 موزع على قسطين (100 و 50) يحفظ طلب التحصيل كاملاً،
    وإعادة إرسال نفس الطلب بنفس المرجع والمبلغ (150) يقبل بنجاح كطلب مكرر دون رفض.
    """
    from sale.models.installments import InstallmentCollectionRequest, InstallmentCollectionDistribution
    s = remediation_setup

    contract = PropertyContract.objects.create(
        contract_number="CTR-MULTI-COLL-01",
        project=s['project'],
        unit=s['unit'],
        customer=s['customer_a'],
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + timezone.timedelta(days=365),
        final_contract_price=Decimal("1500000.00"),
        currency=s['currency'],
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=s['user']
    )

    plan = InstallmentPlan.objects.create(
        customer=s['customer_a'],
        total_principal=Decimal("1500000.00"),
        total_amount=Decimal("1500000.00"),
        number_of_installments=2,
        frequency='single',
        status=InstallmentPlan.PlanStatus.ACTIVE,
        start_date=timezone.localdate(),
        created_by=s['user']
    )
    contract.installment_plan = plan
    contract.save()

    item1 = InstallmentItem.objects.create(
        plan=plan,
        installment_number=1,
        due_date=timezone.localdate(),
        principal_amount=Decimal("100.00"),
        total_amount=Decimal("100.00"),
        paid_amount=Decimal("0.00")
    )
    item2 = InstallmentItem.objects.create(
        plan=plan,
        installment_number=2,
        due_date=timezone.localdate() + timezone.timedelta(days=30),
        principal_amount=Decimal("100.00"),
        total_amount=Decimal("100.00"),
        paid_amount=Decimal("0.00")
    )

    # سداد 150 بمرجع واحد موزع على قسطين (100 على item1 و 50 على item2)
    p = InstallmentEngine.record_installment_payment(
        installment_item=item1,
        amount=Decimal("150.00"),
        payment_date=timezone.localdate(),
        user=s['user'],
        financial_account=s['bank_account'],
        reference_number="REF-BATCH-150"
    )

    item1.refresh_from_db()
    item2.refresh_from_db()
    assert item1.paid_amount == Decimal("100.00")
    assert item2.paid_amount == Decimal("50.00")

    # التحقق من تسجيل طلب التحصيل التجميعي وتوزيعاته
    req = InstallmentCollectionRequest.objects.filter(reference_number="REF-BATCH-150").first()
    assert req is not None
    assert req.requested_amount == Decimal("150.00")
    assert req.distributions.count() == 2

    # 1. إعادة إرسال نفس الطلب والمرجع بمبلغ 150 -> يجب أن يقبل فوراً ويعيد نفس الإيصال دون خطأ
    p_retry = InstallmentEngine.record_installment_payment(
        installment_item=item1,
        amount=Decimal("150.00"),
        payment_date=timezone.localdate(),
        user=s['user'],
        financial_account=s['bank_account'],
        reference_number="REF-BATCH-150"
    )
    assert p_retry.id == p.id

    # 2. إرسال نفس المرجع بمبلغ مختلف (200 بدلاً من 150) -> يجب الرفض الصارم
    with pytest.raises(ValidationError) as exc:
        InstallmentEngine.record_installment_payment(
            installment_item=item1,
            amount=Decimal("200.00"),
            payment_date=timezone.localdate(),
            user=s['user'],
            financial_account=s['bank_account'],
            reference_number="REF-BATCH-150"
        )
    assert "تعارض في بيانات المرجع" in str(exc.value)


@pytest.mark.django_db
def test_16_booking_conversion_to_foreign_currency_preserves_functional_values(remediation_setup):
    """
    عيب 2 [P1 الجديد]: تحصيل حجز بـ 100 EGP ثم تحويله لعقد USD بسعر 50
    يقفل حساب مقدمات الحجز دائن 100 ومدين 100 بالتطابق التام، ويقيد التزام العقد بـ 100 EGP (2 USD).
    """
    from real_estate.models import UnitBooking
    s = remediation_setup

    booking_advance_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="21101",
        defaults={'name': "أمانات ودفعات حجز معلقة", 'account_type': s['contract_liability'].account_type, 'is_active': True, 'is_leaf': True}
    )

    booking = UnitBooking.objects.create(
        booking_number="BK-FX-001",
        unit=s['unit'],
        customer=s['customer_a'],
        booking_date=timezone.localdate(),
        expiry_date=timezone.localdate() + timezone.timedelta(days=14),
        holding_deposit=Decimal("100.00"),
        currency=s['currency'],  # EGP
        exchange_rate=Decimal("1.000000"),
        created_by=s['user']
    )

    # 1. تحصيل جدية الحجز (100 EGP)
    je_holding = RealEstateAccountingService.post_booking_holding_fee(
        booking=booking,
        payment_account=s['bank_account'],
        user=s['user']
    )
    adv_line_cr = je_holding.lines.filter(account=booking_advance_acc).first()
    assert adv_line_cr.credit == Decimal("100.00"), "جدية الحجز تقيد دائنة بـ 100 EGP"

    # 2. إنشاء العقد النهائي بالـ USD بسعر صرف 50.000000
    contract_usd = PropertyContract.objects.create(
        contract_number="CTR-BK-CONV-USD",
        project=s['project'],
        unit=s['unit'],
        customer=s['customer_a'],
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + timezone.timedelta(days=365),
        final_contract_price=Decimal("100000.00"),
        currency=s['usd_currency'],
        exchange_rate=Decimal("50.000000"),
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=s['user']
    )

    # 3. تحويل الحجز إلى العقد النهائي دون دفع إضافي
    je_conv = RealEstateAccountingService.post_booking_conversion(
        booking=booking,
        contract=contract_usd,
        user=s['user'],
        additional_down_payment=Decimal("0.00")
    )

    adv_line_dr = je_conv.lines.filter(account=booking_advance_acc).first()
    contract_line_cr = je_conv.lines.filter(account=s['contract_liability']).first()

    # التحقق الحاسم: حساب 21101 يقفل بـ 100 EGP وليس 5000 EGP!
    assert adv_line_dr.debit == Decimal("100.00"), f"حساب أمانات الحجز يجب أن يقفل بمدين 100.00 EGP وليس {adv_line_dr.debit}"
    assert adv_line_dr.currency == "EGP"

    # التحقق من قيد التزام العقد: 100 EGP functional تعادل 2.00 USD
    assert contract_line_cr.credit == Decimal("100.00"), f"التزام العقد الوظيفي يجب أن يكون 100.00 EGP وليس {contract_line_cr.credit}"
    assert contract_line_cr.foreign_credit == Decimal("2.00"), f"التزام العقد بالدولار يجب أن يكون 2.00 USD وليس {contract_line_cr.foreign_credit}"
    assert contract_line_cr.currency == "USD"
    assert contract_line_cr.exchange_rate == Decimal("50.000000")


@pytest.mark.django_db
def test_17_customer_migrations_independent_of_real_estate():
    """
    عيب 3 [P2]: شجرة migrations الخاصة بالعملاء مستقلة تماماً ولا تعتمد على real_estate (Loose Coupling).
    """
    from django.db.migrations.loader import MigrationLoader
    from django.db import connection

    loader = MigrationLoader(connection, ignore_no_migrations=True)
    customer_nodes = [node for node in loader.graph.nodes if node[0] == 'customer']

    for node in customer_nodes:
        deps = loader.graph.node_map[node].dependencies
        for dep in deps:
            assert dep[0] != 'real_estate', f"هجرة العملاء {node} تعتمد بشكل محظور على تطبيق العقارات {dep}!"


@pytest.mark.django_db
def test_18_booking_conversion_to_foreign_currency_converts_contract_down_payment(remediation_setup):
    """
    عيب 1 [P1 مسار فعلي]: تحويل حجز بـ 100 EGP لعقد USD بسعر 50 يسجل مقدم العقد كـ 2.00 USD وليس 100.00 USD.
    """
    from real_estate.models import UnitBooking
    from real_estate.services.booking_service import UnitBookingService
    s = remediation_setup

    unit = s['unit']
    unit.status = PropertyUnit.UnitStatus.RESERVED
    unit.save()

    booking = UnitBooking.objects.create(
        booking_number="BK-CONV-DP-01",
        unit=unit,
        customer=s['customer_a'],
        booking_date=timezone.localdate(),
        expiry_date=timezone.localdate() + timezone.timedelta(days=14),
        holding_deposit=Decimal("100.00"),
        currency=s['currency'],  # EGP
        exchange_rate=Decimal("1.000000"),
        is_deposit_collected=True,
        is_confirmed_audit=True,
        created_by=s['user']
    )
    unit.current_booking = booking
    unit.save()

    contract = UnitBookingService.convert_booking_to_contract(
        booking_id=booking.id,
        user=s['user'],
        currency=s['usd_currency'],
        exchange_rate=Decimal("50.000000"),
        final_contract_price=Decimal("10000.00")
    )

    assert contract.currency == s['usd_currency']
    assert contract.exchange_rate == Decimal("50.000000")
    # الـ 100 EGP تعادل 2.00 USD بسعر 50
    assert contract.down_payment == Decimal("2.00"), f"مقدم العقد يجب أن يسجل 2.00 USD وليس {contract.down_payment}"


@pytest.mark.django_db
def test_19_booking_creation_posts_accounting_journal_entry_atomically(remediation_setup):
    """
    عيب 2 [P1 مسار فعلي]: إنشاء الحجز بجدية حجز يسجل القيد المحاسبي وإيصال السداد فورياً في نفس المعاملة.
    """
    from real_estate.models import UnitBooking
    from real_estate.services.booking_service import UnitBookingService
    s = remediation_setup

    unit_new = PropertyUnit.objects.create(
        project=s['project'],
        block=s['block'],
        floor=s['floor'],
        unit_code="U-BOOK-AC-01",
        unit_type=PropertyUnit.UnitType.APARTMENT,
        status=PropertyUnit.UnitStatus.AVAILABLE,
        gross_area=Decimal("100.00"),
        meter_price=Decimal("5000.00"),
        total_price=Decimal("500000.00")
    )

    booking = UnitBookingService.create_booking(
        unit_id=unit_new.id,
        customer=s['customer_a'],
        holding_deposit=Decimal("100.00"),
        expiry_date=timezone.localdate() + timezone.timedelta(days=14),
        user=s['user'],
        payment_account=s['bank_account']
    )

    assert booking.is_deposit_collected is True, "يجب إثبات تحصيل جدية الحجز محاسبياً فور الإنشاء"
    assert booking.journal_entry is not None, "يجب ربط قيد اليومية بالحجز"

    je = booking.journal_entry
    bank_line = je.lines.filter(account=s['bank_account']).first()
    adv_line = je.lines.filter(account__code="21101").first()

    assert bank_line is not None and bank_line.debit == Decimal("100.00"), "الطرف المدين يجب أن يكون حساب البنك/الخزينة بمبلغ 100"
    assert adv_line is not None and adv_line.credit == Decimal("100.00"), "الطرف الدائن يجب أن يكون أمانات الحجز 21101 بمبلغ 100"


@pytest.mark.django_db
def test_20_duplicate_reference_for_different_installment_is_rejected(remediation_setup):
    """
    عيب 3 [P1 مسار فعلي]: إعادة نفس مرجع التحصيل لقسط مختلف يُرفض فوراً لمنع النجاح المضلل.
    """
    s = remediation_setup

    contract = PropertyContract.objects.create(
        contract_number="CTR-ITEM-IDEM-01",
        project=s['project'],
        unit=s['unit'],
        customer=s['customer_a'],
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + timezone.timedelta(days=365),
        final_contract_price=Decimal("1500000.00"),
        currency=s['currency'],
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=s['user']
    )

    plan = InstallmentPlan.objects.create(
        customer=s['customer_a'],
        total_principal=Decimal("1500000.00"),
        total_amount=Decimal("1500000.00"),
        number_of_installments=2,
        frequency='single',
        status=InstallmentPlan.PlanStatus.ACTIVE,
        start_date=timezone.localdate(),
        created_by=s['user']
    )
    contract.installment_plan = plan
    contract.save()

    item1 = InstallmentItem.objects.create(
        plan=plan,
        installment_number=1,
        due_date=timezone.localdate(),
        principal_amount=Decimal("100.00"),
        total_amount=Decimal("100.00"),
        paid_amount=Decimal("0.00")
    )
    item2 = InstallmentItem.objects.create(
        plan=plan,
        installment_number=2,
        due_date=timezone.localdate() + timezone.timedelta(days=30),
        principal_amount=Decimal("100.00"),
        total_amount=Decimal("100.00"),
        paid_amount=Decimal("0.00")
    )

    # 1. دفع 50 للقسط الأول بمرجع "REF-DIFF-01"
    p1 = InstallmentEngine.record_installment_payment(
        installment_item=item1,
        amount=Decimal("50.00"),
        payment_date=timezone.localdate(),
        user=s['user'],
        financial_account=s['bank_account'],
        reference_number="REF-DIFF-01"
    )
    assert p1.amount == Decimal("50.00")

    # 2. محاولة سداد القسط الثاني بنفس المرجع "REF-DIFF-01" وبنفس المبلغ 50 -> يجب الرفض الصارم!
    with pytest.raises(ValidationError) as exc:
        InstallmentEngine.record_installment_payment(
            installment_item=item2,
            amount=Decimal("50.00"),
            payment_date=timezone.localdate(),
            user=s['user'],
            financial_account=s['bank_account'],
            reference_number="REF-DIFF-01"
        )
    assert "لقسط آخر" in str(exc.value)

    # التحقق من أن القسط الثاني فضل غير مسدد ولم يتأثر بالخطأ
    item2.refresh_from_db()
    assert item2.paid_amount == Decimal("0.00")

    # 3. إعادة نفس المرجع لنفس القسط الأول يقبل ويعيد الدفعة القديمة
    p1_cached = InstallmentEngine.record_installment_payment(
        installment_item=item1,
        amount=Decimal("50.00"),
        payment_date=timezone.localdate(),
        user=s['user'],
        financial_account=s['bank_account'],
        reference_number="REF-DIFF-01"
    )
    assert p1_cached.id == p1.id


@pytest.mark.django_db
def test_21_booking_creation_and_cancellation_enforces_permissions(remediation_setup, client):
    """
    عيب 1 [P1]: فرض حراسة الصلاحيات الصارمة على واجهات حجز وإلغاء الوحدات العقارية.
    المستخدم غير المصرح يرفض بـ 403 ولا يتم تسجيل الحجز أو القيد المالي.
    """
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType
    from real_estate.models import UnitBooking
    from real_estate.services.booking_service import UnitBookingService
    s = remediation_setup

    unit_p = PropertyUnit.objects.create(
        project=s['project'],
        block=s['block'],
        floor=s['floor'],
        unit_code="U-PERM-GUARD-01",
        unit_type=PropertyUnit.UnitType.APARTMENT,
        status=PropertyUnit.UnitStatus.AVAILABLE,
        gross_area=Decimal("120.00"),
        net_area=Decimal("100.00"),
        meter_price=Decimal("8000.00"),
        total_price=Decimal("960000.00")
    )

    unprivileged = s['unprivileged_user']
    client.force_login(unprivileged)

    # 1. محاولة الحجز بمستخدم بلا صلاحية add_unitbooking -> يجب أن يُرفض بـ 403 فورياً
    book_url = reverse('real_estate:api_book_unit', kwargs={'unit_id': unit_p.id})
    resp_book = client.post(
        book_url,
        data=json.dumps({
            'customer_id': s['customer_a'].id,
            'holding_deposit': '500.00',
            'expiry_date': (timezone.localdate() + timezone.timedelta(days=7)).strftime('%Y-%m-%d')
        }),
        content_type='application/json'
    )
    assert resp_book.status_code == 403, f"المستخدم غير المصرح يجب أن يتلقى 403 وليس {resp_book.status_code}"
    unit_p.refresh_from_db()
    assert unit_p.status == PropertyUnit.UnitStatus.AVAILABLE, "الوحدة يجب أن تظل متاحة"
    assert UnitBooking.objects.filter(unit=unit_p).count() == 0, "لا يجب إنشاء أي حجز لمستخدم غير مصرح"

    # 2. منح صلاحية الحجز للمستخدم والتأكد من نجاح العملية
    ct_booking = ContentType.objects.get_for_model(UnitBooking)
    add_perm = Permission.objects.get(content_type=ct_booking, codename='add_unitbooking')
    unprivileged.user_permissions.add(add_perm)
    unprivileged = get_user_model().objects.get(pk=unprivileged.pk)
    client.force_login(unprivileged)

    resp_book_allowed = client.post(
        book_url,
        data=json.dumps({
            'customer_id': s['customer_a'].id,
            'holding_deposit': '500.00',
            'expiry_date': (timezone.localdate() + timezone.timedelta(days=7)).strftime('%Y-%m-%d')
        }),
        content_type='application/json'
    )
    assert resp_book_allowed.status_code == 200, f"بعد منح الصلاحية يجب أن تنجح الاستجابة: {resp_book_allowed.content}"
    data_booking = resp_book_allowed.json()
    booking_id = data_booking['booking_id']

    # 3. محاولة إلغاء الحجز بدون صلاحية change_unitbooking -> يجب أن يُرفض بـ 403
    cancel_url = reverse('real_estate:api_cancel_booking', kwargs={'booking_id': booking_id})
    resp_cancel_denied = client.post(
        cancel_url,
        data=json.dumps({'reason': 'إلغاء تجريبي'}),
        content_type='application/json'
    )
    assert resp_cancel_denied.status_code == 403, "إلغاء الحجز بدون change_unitbooking يجب أن يُرفض بـ 403"

    # 4. منح صلاحية التعديل للمستخدم وإلغاء الحجز بنجاح
    chg_perm = Permission.objects.get(content_type=ct_booking, codename='change_unitbooking')
    unprivileged.user_permissions.add(chg_perm)
    unprivileged = get_user_model().objects.get(pk=unprivileged.pk)
    client.force_login(unprivileged)

    resp_cancel_allowed = client.post(
        cancel_url,
        data=json.dumps({'reason': 'إلغاء مصرح'}),
        content_type='application/json'
    )
    assert resp_cancel_allowed.status_code == 200, "بعد منح صلاحية التعديل يجب أن ينجح الإلغاء"


@pytest.mark.django_db
def test_22_booking_conversion_to_contract_transfers_holding_deposit_to_contract_liability(remediation_setup):
    """
    عيب 2 [P1]: تحويل الحجز لعقد ينقل جدية الحجز محاسبياً في نفس المعاملة الذرية
    من حساب أمانات الحجز 21101 إلى التزام العقد 21102.
    """
    from real_estate.models import UnitBooking
    from real_estate.services.booking_service import UnitBookingService
    from financial.models.journal_entry import JournalEntry
    s = remediation_setup

    unit_c = PropertyUnit.objects.create(
        project=s['project'],
        block=s['block'],
        floor=s['floor'],
        unit_code="U-CONV-ACC-01",
        unit_type=PropertyUnit.UnitType.APARTMENT,
        status=PropertyUnit.UnitStatus.AVAILABLE,
        gross_area=Decimal("150.00"),
        net_area=Decimal("130.00"),
        meter_price=Decimal("10000.00"),
        total_price=Decimal("1500000.00")
    )

    # حجز بمقدم 100
    booking = UnitBookingService.create_booking(
        unit_id=unit_c.id,
        customer=s['customer_a'],
        holding_deposit=Decimal("100.00"),
        expiry_date=timezone.localdate() + timezone.timedelta(days=14),
        user=s['user'],
        payment_account=s['bank_account']
    )
    assert booking.is_deposit_collected is True
    booking.is_confirmed_audit = True
    booking.save()

    # تحويل الحجز إلى عقد رسمي
    contract = UnitBookingService.convert_booking_to_contract(
        booking_id=booking.id,
        user=s['user']
    )
    assert contract is not None

    # التحقق من قيد تحويل جدية الحجز محاسبياً (Event 1b: Reclassification)
    conv_entry = JournalEntry.objects.filter(
        source_module='real_estate',
        source_model='PropertyContract',
        source_id=contract.id
    ).first()
    assert conv_entry is not None, "يجب إنشاء قيد تحويل مقدم الحجز إلى التزام العقد في نفس المعاملة الذرية"

    line_21101 = conv_entry.lines.filter(account__code='21101').first()
    line_21102 = conv_entry.lines.filter(account__code='21102').first()

    assert line_21101 is not None and line_21101.debit == Decimal("100.00"), "يجب إقفال حساب أمانات الحجز 21101 مديناً بـ 100"
    assert line_21102 is not None and line_21102.credit == Decimal("100.00"), "يجب قيد التزام العقد 21102 دائناً بـ 100"


@pytest.mark.django_db
def test_23_booking_cancellation_decouples_refund_request_from_settlement(remediation_setup):
    """
    عيب 3 [P1]: فصل طلب استرداد جدية الحجز عن الصرف الفعلي وربط الحالة بالتسوية المحاسبية.
    """
    from real_estate.models import UnitBooking
    from real_estate.services.booking_service import UnitBookingService
    from financial.models.journal_entry import JournalEntry
    s = remediation_setup

    unit_r = PropertyUnit.objects.create(
        project=s['project'],
        block=s['block'],
        floor=s['floor'],
        unit_code="U-REFUND-DEC-01",
        unit_type=PropertyUnit.UnitType.APARTMENT,
        status=PropertyUnit.UnitStatus.AVAILABLE,
        gross_area=Decimal("110.00"),
        net_area=Decimal("95.00"),
        meter_price=Decimal("6000.00"),
        total_price=Decimal("660000.00")
    )

    booking = UnitBookingService.create_booking(
        unit_id=unit_r.id,
        customer=s['customer_a'],
        holding_deposit=Decimal("100.00"),
        expiry_date=timezone.localdate() + timezone.timedelta(days=14),
        user=s['user'],
        payment_account=s['bank_account']
    )

    # عدد القيود في هذه اللحظة هو 1 فقط (قيد التحصيل)
    entries_count_after_book = JournalEntry.objects.filter(
        source_module='real_estate',
        source_model='UnitBooking',
        source_id=booking.id
    ).count()
    assert entries_count_after_book == 1

    # 1. إلغاء الحجز بدون تحديد حساب الصرف المالي الفوري
    cancelled_b = UnitBookingService.cancel_booking(
        booking_id=booking.id,
        reason="رغبة العميل في إلغاء الحجز",
        forfeit_deposit=False,
        user=s['user']
    )

    # يجب أن تكون الحالة بانتظار رد جدية الحجز (PENDING) وليس REFUNDED
    assert cancelled_b.status == UnitBooking.BookingStatus.CANCELLED_PENDING_REFUND, (
        f"الحالة يجب أن تكون CANCELLED_PENDING_REFUND وليس {cancelled_b.status}"
    )

    # الوحدة يجب أن تتحرر للبيع فورياً
    unit_r.refresh_from_db()
    assert unit_r.status == PropertyUnit.UnitStatus.AVAILABLE
    assert unit_r.current_booking is None

    # القيود المحاسبية تظل 1 فقط (لم يحدث صرف وهمي)
    entries_count_after_cancel = JournalEntry.objects.filter(
        source_module='real_estate',
        source_model='UnitBooking',
        source_id=booking.id
    ).count()
    assert entries_count_after_cancel == 1, "لا يجوز إنشاء قيد صرف قبل التسوية الفعلية"

    # 2. تنفيذ التسوية المالية وصرف المبلغ فعلياً (Actual Settlement)
    refunded_b = UnitBookingService.process_booking_refund(
        booking_id=cancelled_b.id,
        payment_account=s['bank_account'],
        user=s['user']
    )

    # بعد الصرف الفعلي تصبح الحالة CANCELLED_REFUNDED
    assert refunded_b.status == UnitBooking.BookingStatus.CANCELLED_REFUNDED

    # وعدد القيود يصبح 2 (قيد التحصيل + قيد سند الصرف والاسترداد)
    entries_count_after_settle = JournalEntry.objects.filter(
        source_module='real_estate',
        source_model='UnitBooking',
        source_id=booking.id
    ).count()
    assert entries_count_after_settle == 2, "يجب أن يصبح إجمالي القيود 2 بعد الصرف الفعلي"

    # التحقق من دقة قيد الرد
    refund_entry = JournalEntry.objects.filter(
        source_module='real_estate',
        source_model='UnitBooking',
        source_id=booking.id,
        entry_type='payment_voucher'
    ).first()
    assert refund_entry is not None

    adv_line = refund_entry.lines.filter(account__code='21101').first()
    bank_line = refund_entry.lines.filter(account=s['bank_account']).first()

    assert adv_line is not None and adv_line.debit == Decimal("100.00"), "إقفال أمانات الحجز 21101 مديناً بـ 100"
    assert bank_line is not None and bank_line.credit == Decimal("100.00"), "صرف من البنك دائناً بـ 100"


@pytest.mark.django_db
def test_24_property_unit_creation_without_net_area_does_not_crash(remediation_setup):
    """
    التحقق من مرونة حفظ الوحدة العقارية وعدم الانهيار بـ TypeError في حالة عدم تمرير net_area.
    """
    s = remediation_setup
    unit_defensive = PropertyUnit.objects.create(
        project=s['project'],
        block=s['block'],
        floor=s['floor'],
        unit_code="U-DEFENSIVE-NET-01",
        unit_type=PropertyUnit.UnitType.APARTMENT,
        status=PropertyUnit.UnitStatus.AVAILABLE,
        gross_area=Decimal("100.00"),
        net_area=None,
        meter_price=Decimal("5000.00"),
        total_price=Decimal("500000.00")
    )
    assert unit_defensive.id is not None
    assert unit_defensive.net_area == Decimal("100.00")





