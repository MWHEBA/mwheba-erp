# -*- coding: utf-8 -*-
"""
Tests for Phase 5: Broker Management, Staged 50/50 Commission Releases,
Lead Attribution Lock, and Automated Commission Clawback.
"""
from decimal import Decimal
import pytest
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    PropertyContract,
    RealEstateBroker,
    BrokerCommission,
    BrokerAttributionAudit,
)
from customer.models import Customer
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.currency import Currency
from financial.models.journal_entry import JournalEntry
from financial.services.role_registry import AccountRoleNames
from sale.models.installments import InstallmentPlan, InstallmentItem
from real_estate.services.broker_service import BrokerCommissionService
from real_estate.services.accounting_service import RealEstateAccountingService

User = get_user_model()


@pytest.fixture
def phase5_setup(db):
    user = User.objects.create_superuser(
        username="broker_admin",
        email="broker_admin@example.com",
        password="password123"
    )

    # 1. Account Types Setup
    asset_type, _ = AccountType.objects.get_or_create(
        code='asset',
        defaults={'name': 'أصول', 'category': 'asset', 'nature': 'debit'}
    )
    liability_type, _ = AccountType.objects.get_or_create(
        code='liability',
        defaults={'name': 'خصوم', 'category': 'liability', 'nature': 'credit'}
    )
    expense_type, _ = AccountType.objects.get_or_create(
        code='expense',
        defaults={'name': 'مصروفات', 'category': 'expense', 'nature': 'debit'}
    )
    revenue_type, _ = AccountType.objects.get_or_create(
        code='revenue',
        defaults={'name': 'إيرادات', 'category': 'revenue', 'nature': 'credit'}
    )

    # 2. Accounts Setup
    bank_account, _ = ChartOfAccounts.objects.get_or_create(
        code="11101",
        defaults={
            'name': "البنك الأهلي التجاري",
            'account_type': asset_type,
            'is_active': True,
            'is_leaf': True
        }
    )
    clawback_account, _ = ChartOfAccounts.objects.get_or_create(
        code="11450",
        defaults={
            'name': "مستحقات استرداد عمولات الوسطاء (Clawback)",
            'account_type': asset_type,
            'is_active': True,
            'is_leaf': True
        }
    )
    contract_liability, _ = ChartOfAccounts.objects.get_or_create(
        code="21102",
        defaults={
            'name': "التزامات عقود عقارية",
            'account_type': liability_type,
            'is_active': True,
            'is_leaf': True
        }
    )
    vault_cheques, _ = ChartOfAccounts.objects.get_or_create(
        code="11220",
        defaults={
            'name': "شيكات أوراق قبض بالخزينة",
            'account_type': asset_type,
            'is_active': True,
            'is_leaf': True
        }
    )
    commission_expense, _ = ChartOfAccounts.objects.get_or_create(
        code="52510",
        defaults={
            'name': "مصروف عمولات التسويق والوسطاء العقاريين",
            'account_type': expense_type,
            'is_active': True,
            'is_leaf': True
        }
    )
    forfeited_income, _ = ChartOfAccounts.objects.get_or_create(
        code="42201",
        defaults={
            'name': "إيرادات غرامات الفسخ",
            'account_type': revenue_type,
            'is_active': True,
            'is_leaf': True
        }
    )

    # 3. Project, Unit, Contract Setup
    project = RealEstateProject.objects.create(
        name="برج الموهبة 5",
        code="MWH-P5",
        project_type=RealEstateProject.ProjectType.RESIDENTIAL,
        status=RealEstateProject.ProjectStatus.UNDER_CONSTRUCTION,
        start_date=timezone.localdate(),
        expected_completion_date=timezone.localdate() + timezone.timedelta(days=365),
        created_by=user
    )
    block = PropertyBlock.objects.create(project=project, name="Block A", code="MWH-P5-A")
    floor = PropertyFloor.objects.create(block=block, name="الدور الأول", floor_number=1)
    unit = PropertyUnit.objects.create(
        project=project,
        block=block,
        floor=floor,
        unit_code="501",
        gross_area=Decimal("150.00"),
        net_area=Decimal("130.00"),
        meter_price=Decimal("13333.33"),
        base_price=Decimal("2000000.00"),
        total_price=Decimal("2000000.00"),
        status=PropertyUnit.UnitStatus.AVAILABLE
    )

    direct_customer = Customer.objects.create(
        code="CUST-P5-DIR",
        name="عميل مباشر إعلانات فيسبوك",
        customer_type="INDIVIDUAL",
        tax_number="TX-111"
    )
    BrokerAttributionAudit.objects.create(
        customer=direct_customer,
        first_touch_source=BrokerAttributionAudit.LeadSource.COMPANY_CAMPAIGN,
        is_locked=True
    )

    broker_customer = Customer.objects.create(
        code="CUST-P5-BRK",
        name="عميل محال من وسيط خارجي",
        customer_type="INDIVIDUAL",
        tax_number="TX-222"
    )

    broker = RealEstateBroker.objects.create(
        code="BRK-001",
        name="شركة ريماكس للتسويق العقاري",
        broker_type=RealEstateBroker.BrokerType.AGENCY,
        default_commission_rate=Decimal("2.50"),
        financial_account=clawback_account,
        created_by=user
    )

    egp_currency, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={'name': "Egyptian Pound", 'symbol': "ج.م", 'is_functional': True}
    )

    contract = PropertyContract.objects.create(
        contract_number="CNT-P5-001",
        project=project,
        unit=unit,
        customer=direct_customer,
        final_contract_price=Decimal("2000000.00"),
        down_payment=Decimal("200000.00"),  # 10%
        currency=egp_currency,
        contract_date=timezone.localdate(),
        delivery_date=timezone.localdate() + timezone.timedelta(days=720),
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=user
    )

    return {
        "user": user,
        "project": project,
        "unit": unit,
        "contract": contract,
        "direct_customer": direct_customer,
        "broker_customer": broker_customer,
        "broker": broker,
        "bank_account": bank_account,
        "commission_expense": commission_expense,
        "clawback_account": clawback_account
    }


@pytest.mark.django_db
def test_lead_attribution_lock_blocks_direct_campaign_without_ceo_override(phase5_setup):
    """
    اختبار قفل أسبقية المصدر (Lead Attribution Lock):
    محاولة ربط وسيط بعميل قادم من حملة إعلانية مباشرة للشركة ترفع خطأ وتمنع التواطؤ الداخلي
    """
    contract = phase5_setup["contract"]
    broker = phase5_setup["broker"]
    user = phase5_setup["user"]

    with pytest.raises(ValidationError) as exc_info:
        BrokerCommissionService.assign_broker_to_contract(
            contract=contract,
            broker=broker,
            user=user
        )

    assert "حماية تضارب المصالح: العميل مسجل كعميل مباشر للشركة" in str(exc_info.value)


@pytest.mark.django_db
def test_lead_attribution_ceo_override_unlocks_and_creates_audit_record(phase5_setup):
    """
    اختبار تفويض العضو المنتدب (CEO Override):
    يسمح بالربط استثنائياً ويوثق البصمة الرقمية ومبرر التفويض
    """
    contract = phase5_setup["contract"]
    broker = phase5_setup["broker"]
    user = phase5_setup["user"]

    token = BrokerCommissionService.generate_ceo_override_token(contract.id, broker.id)
    commission = BrokerCommissionService.assign_broker_to_contract(
        contract=contract,
        broker=broker,
        user=user,
        ceo_override_token=token,
        ceo_override_reason="استثناء استراتيجي بقرار مجلس الإدارة"
    )

    assert commission is not None
    assert commission.total_commission_amount == Decimal("50000.00")  # 2.5% of 2M
    assert commission.staged_tranche_1_amount == Decimal("25000.00")
    assert commission.staged_tranche_2_amount == Decimal("25000.00")

    # تدقيق توثيق التفويض
    attr = BrokerAttributionAudit.objects.get(customer=contract.customer)
    assert attr.ceo_override_used is True
    assert attr.ceo_override_reason == "استثناء استراتيجي بقرار مجلس الإدارة"
    assert attr.ceo_override_hash != ""


@pytest.mark.django_db
def test_staged_50_50_commission_eligibility_and_milestones(phase5_setup):
    """
    اختبار الإفراج المرحلي للعمولة 50/50:
    - الشريحة 1: دفعة مقدمة >= 10%
    - الشريحة 2: سداد أول قسطين دوريين
    """
    contract = phase5_setup["contract"]
    broker = phase5_setup["broker"]
    user = phase5_setup["user"]
    broker_customer = phase5_setup["broker_customer"]

    contract.customer = broker_customer
    contract.down_payment = Decimal("150000.00")  # 7.5% (< 10%)
    contract.save()

    commission = BrokerCommissionService.assign_broker_to_contract(
        contract=contract,
        broker=broker,
        user=user
    )

    # الشريحة 1 معلقة لأن المقدم أقل من 10%
    assert commission.tranche_1_status == BrokerCommission.TrancheStatus.PENDING
    assert commission.tranche_2_status == BrokerCommission.TrancheStatus.PENDING

    # العميل سدد المقدم بالكامل (250,000 ج.م > 10%)
    contract.down_payment = Decimal("250000.00")
    contract.save()

    BrokerCommissionService.evaluate_milestones_and_release(commission)
    commission.refresh_from_db()
    assert commission.tranche_1_status == BrokerCommission.TrancheStatus.ELIGIBLE
    assert commission.tranche_2_status == BrokerCommission.TrancheStatus.PENDING

    # إنشاء خطة أقساط وسداد قسطين دوريين
    plan = InstallmentPlan.objects.create(
        customer=contract.customer,
        plan_type=InstallmentPlan.PlanType.ASSET_FINANCING,
        total_principal=Decimal("1750000.00"),
        total_amount=Decimal("1750000.00"),
        down_payment=Decimal("250000.00"),
        number_of_installments=10,
        start_date=timezone.localdate(),
        status=InstallmentPlan.PlanStatus.ACTIVE,
        created_by=user
    )
    contract.installment_plan = plan
    contract.save()

    # قسط 1
    InstallmentItem.objects.create(
        plan=plan,
        installment_number=1,
        principal_amount=Decimal("175000.00"),
        total_amount=Decimal("175000.00"),
        interest_amount=Decimal("0.00"),
        paid_amount=Decimal("175000.00"),  # مسدد
        paid_principal=Decimal("175000.00"),
        due_date=timezone.localdate(),
        cash_status=InstallmentItem.CashStatus.COLLECTED
    )
    # قسط 2
    InstallmentItem.objects.create(
        plan=plan,
        installment_number=2,
        principal_amount=Decimal("175000.00"),
        total_amount=Decimal("175000.00"),
        interest_amount=Decimal("0.00"),
        paid_amount=Decimal("175000.00"),  # مسدد
        paid_principal=Decimal("175000.00"),
        due_date=timezone.localdate(),
        cash_status=InstallmentItem.CashStatus.COLLECTED
    )

    BrokerCommissionService.evaluate_milestones_and_release(commission)
    commission.refresh_from_db()
    assert commission.tranche_2_status == BrokerCommission.TrancheStatus.ELIGIBLE


@pytest.mark.django_db
def test_commission_payout_journal_entry_generation(phase5_setup):
    """
    اختبار صرف الشريحة المستحقة وتسجيل القيد المحاسبي
    """
    contract = phase5_setup["contract"]
    broker = phase5_setup["broker"]
    user = phase5_setup["user"]
    bank_account = phase5_setup["bank_account"]

    token = BrokerCommissionService.generate_ceo_override_token(contract.id, broker.id)
    commission = BrokerCommissionService.assign_broker_to_contract(
        contract=contract,
        broker=broker,
        user=user,
        ceo_override_token=token
    )

    assert commission.tranche_1_status == BrokerCommission.TrancheStatus.ELIGIBLE

    # محاولة صرف الشريحة 2 وهي PENDING ترفع خطأ
    with pytest.raises(ValidationError):
        BrokerCommissionService.payout_commission_tranche(
            broker_commission=commission,
            tranche_number=2,
            payment_account=bank_account,
            user=user
        )

    # صرف الشريحة 1
    journal_entry = BrokerCommissionService.payout_commission_tranche(
        broker_commission=commission,
        tranche_number=1,
        payment_account=bank_account,
        user=user
    )

    commission.refresh_from_db()
    assert commission.tranche_1_status == BrokerCommission.TrancheStatus.PAID
    assert commission.tranche_1_journal_entry == journal_entry
    assert journal_entry.status.lower() == 'posted'

    lines = list(journal_entry.lines.all())
    assert len(lines) == 2
    debit_line = [l for l in lines if l.debit > 0][0]
    credit_line = [l for l in lines if l.credit > 0][0]

    assert debit_line.account.code == "52510"
    assert debit_line.debit == Decimal("25000.00")
    assert credit_line.account.code == "11101"
    assert credit_line.credit == Decimal("25000.00")


@pytest.mark.django_db
def test_automated_commission_clawback_on_contract_cancellation(phase5_setup):
    """
    اختبار استرداد العمولات الآلي (Clawback) عند فسخ العقد
    """
    contract = phase5_setup["contract"]
    broker = phase5_setup["broker"]
    user = phase5_setup["user"]
    bank_account = phase5_setup["bank_account"]

    token = BrokerCommissionService.generate_ceo_override_token(contract.id, broker.id)
    commission = BrokerCommissionService.assign_broker_to_contract(
        contract=contract,
        broker=broker,
        user=user,
        ceo_override_token=token
    )

    # صرف الشريحة 1
    BrokerCommissionService.payout_commission_tranche(
        broker_commission=commission,
        tranche_number=1,
        payment_account=bank_account,
        user=user
    )

    commission.refresh_from_db()
    assert commission.tranche_1_status == BrokerCommission.TrancheStatus.PAID
    assert commission.tranche_2_status == BrokerCommission.TrancheStatus.PENDING

    # فسخ العقد
    cancel_entry = RealEstateAccountingService.post_contract_cancellation(
        contract=contract,
        penalty_amount=Decimal("50000.00"),
        refund_amount=Decimal("150000.00"),
        uncashed_cheques_amount=Decimal("0.00"),
        refund_account=bank_account,
        user=user
    )

    commission.refresh_from_db()
    # الشريحة 2 يتم إلغاؤها
    assert commission.tranche_2_status == BrokerCommission.TrancheStatus.CANCELLED
    # الشريحة 1 المصروفة يتم استردادها Clawback
    assert commission.clawback_status == BrokerCommission.ClawbackStatus.CLAWED_BACK
    assert commission.clawback_amount == Decimal("25000.00")
    assert commission.clawback_journal_entry is not None

    claw_lines = list(commission.clawback_journal_entry.lines.all())
    debit_claw = [l for l in claw_lines if l.debit > 0][0]
    credit_claw = [l for l in claw_lines if l.credit > 0][0]

    assert debit_claw.account.code == "11450"  # Clawback asset
    assert debit_claw.debit == Decimal("25000.00")
    assert credit_claw.account.code == "52510"  # Commission expense reversed
    assert credit_claw.credit == Decimal("25000.00")
