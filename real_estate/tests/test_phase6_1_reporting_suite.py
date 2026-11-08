# -*- coding: utf-8 -*-
"""
Tests for Phase 6.1 - Real Estate Analytics & Financial Reporting Suite
MWHEBA ERP — Real Estate Wave 6 (Dual-Perspective Subledger, Cash Flow Radar, WIP & IFRS 15, Broker Commissions)
"""
import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone

from core.models import SystemModule
from core.middleware.module_control import ModuleAccessMiddleware
from customer.models import Customer, CustomerPayment
from supplier.models import Supplier
from financial.models import Currency, ChartOfAccounts, AccountType
from sale.models.installments import InstallmentPlan, InstallmentItem
from cheques.models.cheque import Cheque, ChequeType, ChequeStatus
from cheques.models.allocation import ChequeInvoiceAllocation, AllocationStatus

from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    PropertyContract,
    ContractPaymentReceipt,
    PropertyHandoverReceipt,
    ContractorProgressCertificate,
    RealEstateBroker,
    BrokerCommission,
    SharedInfrastructureAsset,
    SharedInfrastructureApportionment,
    InfrastructureApportionmentLine,
)
from real_estate.services.reporting_service import RealEstateReportingService

User = get_user_model()


@pytest.fixture
def reporting_setup(db):
    cache.delete('enabled_modules_set')
    cache.delete('module_namespace_map')

    mod, _ = SystemModule.objects.get_or_create(
        code='real_estate',
        defaults={'name_ar': 'العقارات', 'is_enabled': True}
    )
    mod.is_enabled = True
    mod.save()
    ModuleAccessMiddleware.invalidate_cache()

    user = User.objects.create_superuser(
        username="reporting_cfo",
        email="cfo_reports@test.com",
        password="password123"
    )

    currency, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={"name": "جنيه مصري", "symbol": "ج.م", "is_functional": True}
    )

    asset_type, _ = AccountType.objects.get_or_create(
        code='asset',
        defaults={'name': 'أصول', 'category': 'asset', 'nature': 'debit'}
    )
    liability_type, _ = AccountType.objects.get_or_create(
        code='liability',
        defaults={'name': 'خصوم', 'category': 'liability', 'nature': 'credit'}
    )

    ChartOfAccounts.objects.get_or_create(
        code="21102",
        defaults={"name": "التزامات عقود عملاء عقاري", "account_type": liability_type, "is_active": True}
    )
    ChartOfAccounts.objects.get_or_create(
        code="12101",
        defaults={"name": "مشروعات تحت التنفيذ WIP", "account_type": asset_type, "is_active": True}
    )

    project = RealEstateProject.objects.create(
        code="PRJ-REP-01",
        name="أبراج الماسة الإدارية",
        project_type=RealEstateProject.ProjectType.ADMINISTRATIVE,
        status=RealEstateProject.ProjectStatus.UNDER_CONSTRUCTION,
        start_date=date(2025, 1, 1),
        expected_completion_date=date(2027, 12, 31),
        total_land_area=Decimal("5000.00"),
        gross_built_area=Decimal("20000.00"),
        created_by=user
    )

    block = PropertyBlock.objects.create(project=project, code="BLK-REP-A", name="البرج الشمالي")
    floor = PropertyFloor.objects.create(block=block, floor_number=3, name="الدور الثالث")

    # إنشاء 3 وحدات: واحدة مسلمة، واحدة مباعة قيد الإنشاء، وواحدة متاحة
    unit_delivered = PropertyUnit.objects.create(
        project=project,
        floor=floor,
        unit_code="MASA-301",
        gross_area=Decimal("150.00"),
        net_area=Decimal("130.00"),
        meter_price=Decimal("20000.00"),
        base_price=Decimal("3000000.00"),
        total_price=Decimal("3000000.00"),
        progress_percentage=Decimal("100.00"),
        status=PropertyUnit.UnitStatus.DELIVERED
    )
    unit_active = PropertyUnit.objects.create(
        project=project,
        floor=floor,
        unit_code="MASA-302",
        gross_area=Decimal("200.00"),
        net_area=Decimal("175.00"),
        meter_price=Decimal("20000.00"),
        base_price=Decimal("4000000.00"),
        total_price=Decimal("4000000.00"),
        status=PropertyUnit.UnitStatus.CONTRACTED
    )
    unit_available = PropertyUnit.objects.create(
        project=project,
        floor=floor,
        unit_code="MASA-303",
        gross_area=Decimal("120.00"),
        net_area=Decimal("100.00"),
        meter_price=Decimal("20000.00"),
        base_price=Decimal("2400000.00"),
        total_price=Decimal("2400000.00"),
        status=PropertyUnit.UnitStatus.AVAILABLE
    )

    customer_1 = Customer.objects.create(
        code="CUST-REP-01",
        name="شركة النيل للاستشارات",
        default_currency=currency
    )
    customer_2 = Customer.objects.create(
        code="CUST-REP-02",
        name="المهندس سامح فهمي",
        default_currency=currency
    )

    # العقد الأول: مسدد بالكامل ومسلم (إيراد محقق IFRS 15 = 3,000,000)
    contract_1 = PropertyContract.objects.create(
        contract_number="CTR-REP-101",
        project=project,
        unit=unit_delivered,
        customer=customer_1,
        final_contract_price=Decimal("3000000.00"),
        down_payment=Decimal("1000000.00"),
        currency=currency,
        contract_date=date(2026, 1, 10),
        delivery_date=date(2026, 6, 1),
        status=PropertyContract.ContractStatus.COMPLETED,
        created_by=user
    )
    dp_pay_1 = CustomerPayment.objects.create(
        customer=customer_1,
        amount=Decimal("1000000.00"),
        payment_date=date(2026, 1, 10),
        payment_method="CASH",
        created_by=user
    )
    ContractPaymentReceipt.objects.create(
        contract=contract_1,
        customer_payment=dp_pay_1,
        installment_item=None
    )
    plan_1 = InstallmentPlan.objects.create(
        customer=customer_1,
        total_principal=Decimal("2000000.00"),
        total_amount=Decimal("2000000.00"),
        number_of_installments=1,
        start_date=date(2026, 3, 1),
        status=InstallmentPlan.PlanStatus.COMPLETED,
        created_by=user
    )
    contract_1.installment_plan = plan_1
    contract_1.save(update_fields=['installment_plan'])
    InstallmentItem.objects.create(
        plan=plan_1,
        installment_number=1,
        due_date=date(2026, 5, 1),
        principal_amount=Decimal("2000000.00"),
        total_amount=Decimal("2000000.00"),
        paid_amount=Decimal("2000000.00"),
        cash_status=InstallmentItem.CashStatus.COLLECTED
    )
    # محضر تسليم منفذ للعقد الأول بتكلفة مبيعات مرحلية 1,800,000
    PropertyHandoverReceipt.objects.create(
        receipt_number="HND-REP-101",
        contract=contract_1,
        unit=unit_delivered,
        handover_type=PropertyHandoverReceipt.HandoverType.PHYSICAL,
        status=PropertyHandoverReceipt.HandoverStatus.EXECUTED,
        handover_date=date(2026, 6, 1),
        client_signatory_name="مستلم معتمد",
        interim_cogs_amount=Decimal("1800000.00"),
        recognized_revenue_amount=Decimal("3000000.00"),
        created_by=user
    )

    # العقد الثاني: نشط غير مسلم (إيراد مؤجل) به قسطان وشيك بالحافظة
    contract_2 = PropertyContract.objects.create(
        contract_number="CTR-REP-102",
        project=project,
        unit=unit_active,
        customer=customer_2,
        final_contract_price=Decimal("4000000.00"),
        down_payment=Decimal("800000.00"),
        currency=currency,
        contract_date=date(2026, 2, 15),
        delivery_date=date(2027, 12, 31),
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=user
    )
    dp_pay_2 = CustomerPayment.objects.create(
        customer=customer_2,
        amount=Decimal("800000.00"),
        payment_date=date(2026, 2, 15),
        payment_method="CASH",
        created_by=user
    )
    ContractPaymentReceipt.objects.create(
        contract=contract_2,
        customer_payment=dp_pay_2,
        installment_item=None
    )
    plan_2 = InstallmentPlan.objects.create(
        customer=customer_2,
        total_principal=Decimal("3200000.00"),
        total_amount=Decimal("3200000.00"),
        number_of_installments=2,
        start_date=date(2026, 6, 1),
        status=InstallmentPlan.PlanStatus.ACTIVE,
        created_by=user
    )
    contract_2.installment_plan = plan_2
    contract_2.save(update_fields=['installment_plan'])

    item_2_1 = InstallmentItem.objects.create(
        plan=plan_2,
        installment_number=1,
        due_date=date(2026, 5, 15),
        principal_amount=Decimal("1600000.00"),
        total_amount=Decimal("1600000.00"),
        paid_amount=Decimal("0.00"),
        cash_status=InstallmentItem.CashStatus.PENDING
    )
    item_2_2 = InstallmentItem.objects.create(
        plan=plan_2,
        installment_number=2,
        due_date=timezone.localdate() + timedelta(days=60),
        principal_amount=Decimal("1600000.00"),
        total_amount=Decimal("1600000.00"),
        paid_amount=Decimal("0.00"),
        cash_status=InstallmentItem.CashStatus.PENDING
    )

    # شيك في الخزينة يغطي القسط الأول من العقد الثاني
    cheque_in_safe = Cheque.objects.create(
        cheque_number="CHQ-REP-SAFE-01",
        amount=Decimal("1600000.00"),
        currency=currency,
        issue_date=date(2026, 2, 15),
        due_date=date(2026, 5, 15),
        cheque_type=ChequeType.RECEIVABLE,
        status=ChequeStatus.IN_PORTFOLIO,
        customer=customer_2,
        created_by=user
    )
    ChequeInvoiceAllocation.objects.create(
        cheque=cheque_in_safe,
        installment_item=item_2_1,
        allocated_amount=Decimal("1600000.00"),
        allocated_amount_functional=Decimal("1600000.00"),
        allocation_date=date(2026, 2, 15),
        allocation_status=AllocationStatus.APPLIED
    )

    # مستخلص مقاول معتمد للمشروع بقيمة أعمال 2,500,000 وصافي مستحق 2,350,000
    contractor = Supplier.objects.create(
        code="SUP-REP-01",
        name="شركة المقاولون المتحدون للإنشاءات"
    )
    cert = ContractorProgressCertificate.objects.create(
        certificate_number="IPC-REP-001",
        project=project,
        contractor=contractor,
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        gross_certified_work=Decimal("2500000.00"),
        previous_certified_work=Decimal("0.00"),
        current_period_work=Decimal("2500000.00"),
        materials_on_site=Decimal("0.00"),
        retention_rate=Decimal("5.00"),
        retention_amount=Decimal("125000.00"),
        wht_rate=Decimal("1.00"),
        wht_amount=Decimal("25000.00"),
        net_amount=Decimal("2350000.00"),
        currency=currency,
        status=ContractorProgressCertificate.CertificateStatus.APPROVED,
        created_by=user
    )

    # توزيع تكاليف بنية تحتية مشتركة مرحل للمشروع بقيمة 500,000
    infra_asset = SharedInfrastructureAsset.objects.create(
        code="INF-REP-01",
        name="محطة التكييف المركزي الموحدة",
        accumulated_wip_cost=Decimal("1000000.00"),
        apportioned_wip_cost=Decimal("500000.00"),
        created_by=user
    )
    apportionment = SharedInfrastructureApportionment.objects.create(
        apportionment_number="APP-REP-001",
        infrastructure_asset=infra_asset,
        total_apportioned_amount=Decimal("500000.00"),
        status=SharedInfrastructureApportionment.ApportionmentStatus.POSTED,
        created_by=user
    )
    InfrastructureApportionmentLine.objects.create(
        apportionment=apportionment,
        beneficiary_project=project,
        metric_value=Decimal("20000.00"),
        allocation_percentage=Decimal("100.0000"),
        allocated_amount=Decimal("500000.00")
    )

    # وسيط عقاري وعمولة على العقد الثاني (2.5% من 4,000,000 = 100,000)
    broker = RealEstateBroker.objects.create(
        code="BRK-REP-01",
        name="دار الخبرة للتسويق العقاري",
        default_commission_rate=Decimal("2.50"),
        created_by=user
    )
    commission = BrokerCommission.objects.create(
        contract=contract_2,
        broker=broker,
        commission_rate=Decimal("2.50"),
        total_commission_amount=Decimal("100000.00"),
        staged_tranche_1_amount=Decimal("50000.00"),
        tranche_1_status=BrokerCommission.TrancheStatus.PAID,
        staged_tranche_2_amount=Decimal("50000.00"),
        tranche_2_status=BrokerCommission.TrancheStatus.PENDING
    )

    return {
        "user": user,
        "project": project,
        "customer_1": customer_1,
        "customer_2": customer_2,
        "contract_1": contract_1,
        "contract_2": contract_2,
        "broker": broker,
        "commission": commission,
        "cert": cert,
    }


# ==============================================================================
# 1. اختبارات كشف الحساب المزدوج (Dual-Perspective Subledger Report)
# ==============================================================================

@pytest.mark.django_db
def test_dual_subledger_report_service_and_view(client, reporting_setup):
    client.force_login(reporting_setup["user"])

    report = RealEstateReportingService.get_dual_subledger_report(
        project_id=reporting_setup["project"].id
    )
    assert report["total_contracts_count"] == 2
    assert report["total_contractual_value"] == Decimal("7000000.00")
    # العقد الأول محصل بالكامل 3,000,000 + العقد الثاني محصل المقدم 800,000 = 3,800,000
    assert report["total_verified_collected"] == Decimal("3800000.00")
    # شيكات بالحافظة = 1,600,000
    assert report["total_cheques_in_vault"] == Decimal("1600000.00")
    # المتبقي التعاقدي = 3,200,000
    assert report["total_remaining_contractual"] == Decimal("3200000.00")
    # الإيراد المحقق IFRS 15 (العقد المسلم فقط) = 3,000,000
    assert report["total_recognized_revenue"] == Decimal("3000000.00")
    # التزام العقد المؤجل 21102 (المتحصل من العقد غير المسلم) = 800,000
    assert report["total_deferred_liability"] == Decimal("800000.00")

    # اختبار الفيو وقالب العرض
    url = reverse("real_estate:report_dual_subledger")
    resp = client.get(url, {"project": reporting_setup["project"].id})
    assert resp.status_code == 200
    assert "real_estate/reports/dual_subledger_report.html" in [t.name for t in resp.templates]
    assert resp.context["total_contractual_value"] == Decimal("7000000.00")

    # اختبار فلتر العقود خالصة الذمة فقط
    resp_cleared = client.get(url, {"clearance": "CLEARED"})
    assert resp_cleared.status_code == 200
    assert len(resp_cleared.context["contract_rows"]) == 1
    assert resp_cleared.context["contract_rows"][0]["contract"] == reporting_setup["contract_1"]


# ==============================================================================
# 2. اختبارات رادار التدفقات النقدية ومطابقة السيولة (Cash Flow & Liquidity Radar)
# ==============================================================================

@pytest.mark.django_db
def test_cash_flow_liquidity_report_service_and_view(client, reporting_setup):
    client.force_login(reporting_setup["user"])

    report = RealEstateReportingService.get_cash_flow_liquidity_report(
        project_id=reporting_setup["project"].id
    )
    # إجمالي الأقساط المجدولة (2,000,000 + 3,200,000 = 5,200,000)
    assert report["total_scheduled_inflows"] == Decimal("5200000.00")
    assert report["total_collected_inflows"] == Decimal("2000000.00")
    assert report["total_expected_remaining"] == Decimal("3200000.00")
    assert report["total_cheque_backed"] == Decimal("1600000.00")
    assert report["total_contractor_outflows"] == Decimal("2350000.00")
    # صافي السيولة = 5,200,000 - 2,350,000 = 2,850,000
    assert report["net_liquidity_gap"] == Decimal("2850000.00")

    url = reverse("real_estate:report_cash_flow")
    resp = client.get(url, {"project": reporting_setup["project"].id})
    assert resp.status_code == 200
    assert "real_estate/reports/cash_flow_report.html" in [t.name for t in resp.templates]
    assert len(resp.context["monthly_summary"]) >= 2


# ==============================================================================
# 3. اختبارات تكاليف المشروعات وإيرادات IFRS 15 (WIP Costing & IFRS 15 Revenue)
# ==============================================================================

@pytest.mark.django_db
def test_project_wip_revenue_report_service_and_view(client, reporting_setup):
    client.force_login(reporting_setup["user"])

    report = RealEstateReportingService.get_project_wip_revenue_report(
        project_id=reporting_setup["project"].id
    )
    assert len(report["project_rows"]) == 1
    p_row = report["project_rows"][0]

    assert p_row["total_units"] == 3
    assert p_row["sold_units"] == 2
    assert p_row["delivered_units_count"] == 1
    assert p_row["contracted_sales"] == Decimal("7000000.00")
    assert p_row["recognized_revenue"] == Decimal("3000000.00")
    assert p_row["deferred_revenue"] == Decimal("4000000.00")
    # إجمالي WIP = 2,500,000 مستخلصات + 500,000 بنية تحتية = 3,000,000
    assert p_row["direct_contractor_wip"] == Decimal("2500000.00")
    assert p_row["infra_wip"] == Decimal("500000.00")
    assert p_row["total_wip_cost"] == Decimal("3000000.00")
    assert p_row["interim_cogs"] == Decimal("1800000.00")
    assert p_row["remaining_wip_inventory"] == Decimal("1200000.00")
    # تكلفة المتر البنائي = 3,000,000 / 20,000 م² = 150.00 ج.م/م²
    assert p_row["cost_per_sqm"] == Decimal("150.00")

    url = reverse("real_estate:report_wip_revenue")
    resp = client.get(url)
    assert resp.status_code == 200
    assert "real_estate/reports/wip_revenue_report.html" in [t.name for t in resp.templates]


# ==============================================================================
# 4. اختبارات تقرير أداء الوسطاء والعمولات (Broker Commission Radar)
# ==============================================================================

@pytest.mark.django_db
def test_broker_commission_report_service_and_view(client, reporting_setup):
    client.force_login(reporting_setup["user"])

    report = RealEstateReportingService.get_broker_commission_report(
        broker_id=reporting_setup["broker"].id
    )
    assert report["total_brokered_sales"] == Decimal("4000000.00")
    assert report["total_commissions_amount"] == Decimal("100000.00")
    assert report["total_released_commissions"] == Decimal("50000.00")
    assert report["total_retained_commissions"] == Decimal("50000.00")
    assert len(report["broker_summaries"]) == 1

    url = reverse("real_estate:report_broker_commissions")
    resp = client.get(url, {"broker": reporting_setup["broker"].id})
    assert resp.status_code == 200
    assert "real_estate/reports/broker_commission_report.html" in [t.name for t in resp.templates]
    assert resp.context["total_released_commissions"] == Decimal("50000.00")


@pytest.mark.django_db
def test_dual_subledger_bounced_cheque_filter(client, reporting_setup):
    client.force_login(reporting_setup["user"])
    chq = Cheque.objects.get(cheque_number="CHQ-REP-SAFE-01")
    chq.status = ChequeStatus.BOUNCED
    chq.save(update_fields=['status'])

    url = reverse("real_estate:report_dual_subledger")
    resp = client.get(url, {"clearance": "BOUNCED"})
    assert resp.status_code == 200
    rows = resp.context["contract_rows"]
    assert len(rows) == 1
    assert rows[0]["contract"] == reporting_setup["contract_2"]
    assert rows[0]["bounced_count"] == 1
    assert rows[0]["cheques_bounced"] == Decimal("1600000.00")


@pytest.mark.django_db
def test_all_report_endpoints_guarded_by_module_toggle(client, reporting_setup):
    client.force_login(reporting_setup["user"])
    mod = SystemModule.objects.get(code='real_estate')
    mod.is_enabled = False
    mod.save()
    ModuleAccessMiddleware.invalidate_cache()

    report_urls = [
        reverse("real_estate:report_dual_subledger"),
        reverse("real_estate:report_cash_flow"),
        reverse("real_estate:report_wip_revenue"),
        reverse("real_estate:report_broker_commissions"),
    ]
    for url in report_urls:
        resp = client.get(url)
        assert resp.status_code == 302

