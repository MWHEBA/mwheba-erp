# -*- coding: utf-8 -*-
"""
Tests for Budgeted WIP COGS Allocation & Project Completion True-Up Reconciliation
MWHEBA ERP — Real Estate Wave 3 (Phase 10)
"""
from decimal import Decimal
from datetime import date
import pytest

from django.contrib.auth import get_user_model

from customer.models import Customer
from financial.models import Currency, ChartOfAccounts, AccountType
from financial.services.role_registry import AccountRoleNames

from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    PropertyContract,
    PropertyHandoverReceipt,
)
from real_estate.services.handover_service import HandoverExecutionService
from real_estate.services.true_up_service import ProjectCostTrueUpService

User = get_user_model()


@pytest.fixture
def true_up_setup(db):
    user, _ = User.objects.get_or_create(
        username="cost_accountant",
        defaults={"email": "cost_accountant@test.com", "is_staff": True}
    )
    engineer, _ = User.objects.get_or_create(
        username="project_director",
        defaults={"email": "director@test.com", "is_staff": True}
    )
    currency, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={"name": "جنيه مصري", "symbol": "ج.م"}
    )

    asset_type, _ = AccountType.objects.get_or_create(code='asset', defaults={'name': 'أصول', 'category': 'asset', 'nature': 'debit'})
    liability_type, _ = AccountType.objects.get_or_create(code='liability', defaults={'name': 'خصوم', 'category': 'liability', 'nature': 'credit'})
    revenue_type, _ = AccountType.objects.get_or_create(code='revenue', defaults={'name': 'إيرادات', 'category': 'revenue', 'nature': 'credit'})
    expense_type, _ = AccountType.objects.get_or_create(code='expense', defaults={'name': 'مصروفات', 'category': 'expense', 'nature': 'debit'})

    contract_liability_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="21102",
        defaults={
            "name": "التزامات عقود التطوير العقاري",
            "account_type": liability_type,
            "is_active": True
        }
    )
    revenue_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="41101",
        defaults={
            "name": "إيرادات بيع وتطوير عقاري محققة",
            "account_type": revenue_type,
            "is_active": True
        }
    )
    cogs_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="51100",
        defaults={
            "name": "تكلفة مبيعات التطوير العقاري",
            "account_type": expense_type,
            "is_active": True
        }
    )
    wip_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="12101",
        defaults={
            "name": "مشروعات تحت التنفيذ - أعمال إنشائية",
            "account_type": asset_type,
            "is_active": True
        }
    )

    customer, _ = Customer.objects.get_or_create(
        code="CUST-TRUP-01",
        defaults={"name": "شركة التطوير الاستثماري", "default_currency": currency}
    )

    project = RealEstateProject.objects.create(
        code="PRJ-TRUP-01",
        name="مجمع بيفرلي جيتس السكني",
        start_date=date(2024, 1, 1),
        expected_completion_date=date(2026, 6, 30),
        total_land_area=Decimal("20000.00"),
        gross_built_area=Decimal("80000.00"),
        created_by=user
    )
    block = PropertyBlock.objects.create(project=project, code="B-01", name="عمارة 1")
    floor = PropertyFloor.objects.create(block=block, floor_number=1, name="الدور الأول")

    # إنشاء 3 وحدات تم تسليمها
    unit1 = PropertyUnit.objects.create(
        project=project,
        floor=floor,
        unit_code="BG-U101",
        gross_area=Decimal("100.00"),
        net_area=Decimal("85.00"),
        meter_price=Decimal("20000.00"),
        total_price=Decimal("2000000.00"),
        status=PropertyUnit.UnitStatus.AVAILABLE
    )
    unit2 = PropertyUnit.objects.create(
        project=project,
        floor=floor,
        unit_code="BG-U102",
        gross_area=Decimal("150.00"),
        net_area=Decimal("130.00"),
        meter_price=Decimal("20000.00"),
        total_price=Decimal("3000000.00"),
        status=PropertyUnit.UnitStatus.AVAILABLE
    )

    contract1 = PropertyContract.objects.create(
        contract_number="CTR-TRUP-01",
        project=project,
        unit=unit1,
        customer=customer,
        final_contract_price=Decimal("2000000.00"),
        down_payment=Decimal("400000.00"),
        currency=currency,
        contract_date=date(2024, 6, 1),
        delivery_date=date(2026, 6, 30),
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=user
    )
    contract2 = PropertyContract.objects.create(
        contract_number="CTR-TRUP-02",
        project=project,
        unit=unit2,
        customer=customer,
        final_contract_price=Decimal("3000000.00"),
        down_payment=Decimal("600000.00"),
        currency=currency,
        contract_date=date(2024, 6, 1),
        delivery_date=date(2026, 6, 30),
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=user
    )

    # تسليم الوحدتين بتكلفة تقديرية 10,000 ج.م للمتر
    budgeted_meter_cost = Decimal("10000.00")

    receipt1 = HandoverExecutionService.create_handover_receipt(
        contract=contract1,
        created_by=user,
        site_engineer=engineer,
        client_signatory_name="ممثل الشركة 1"
    )
    HandoverExecutionService.execute_physical_handover(
        receipt=receipt1,
        executed_by=engineer,
        budgeted_cost_per_meter=budgeted_meter_cost  # 100 * 10,000 = 1,000,000 EGP
    )

    receipt2 = HandoverExecutionService.create_handover_receipt(
        contract=contract2,
        created_by=user,
        site_engineer=engineer,
        client_signatory_name="ممثل الشركة 2"
    )
    HandoverExecutionService.execute_physical_handover(
        receipt=receipt2,
        executed_by=engineer,
        budgeted_cost_per_meter=budgeted_meter_cost  # 150 * 10,000 = 1,500,000 EGP
    )

    # إجمالي تكلفة المبيعات التقديرية المحملة = 1,000,000 + 1,500,000 = 2,500,000 EGP
    return {
        "user": user,
        "director": engineer,
        "project": project,
        "total_recognized_interim_cogs": Decimal("2500000.00")
    }


@pytest.mark.django_db
class TestBudgetedWipCogsAndTrueUpReconciliation:
    """اختبارات احتساب تكلفة المبيعات التقديرية وتسوية فروق التكلفة الختامية للمشروع"""

    def test_interim_cogs_aggregation_across_multiple_unit_handovers(self, true_up_setup):
        """التحقق من تجميع إجمالي تكلفة المبيعات المرحلية لكافة الوحدات المسلمة بدقة"""
        setup = true_up_setup
        project = setup["project"]
        expected_total = setup["total_recognized_interim_cogs"]

        analysis = ProjectCostTrueUpService.calculate_project_cost_variance(
            project=project,
            actual_wip_incurred=Decimal("2500000.00")
        )

        assert analysis["delivered_units_count"] == 2
        assert analysis["total_interim_cogs_recognized"] == expected_total
        assert analysis["is_balanced"] is True
        assert analysis["variance_amount"] == Decimal("0.00")

    def test_project_completion_cost_true_up_with_cost_overrun(self, true_up_setup):
        """التحقق من ترحيل قيد التسوية عند تجاوز التكاليف الفعلية للتكلفة التقديرية (Cost Overrun)"""
        setup = true_up_setup
        project = setup["project"]
        user = setup["user"]

        # التكاليف الفعلية المنفذة في WIP بلغت 2,850,000 ج.م بينما المعترف به مرحلياً 2,500,000 ج.م
        # فرق التكلفة = +350,000 ج.م (تجاوز تكلفة يجب تحميله على تكلفة المبيعات وإقفال الـ WIP)
        actual_wip = Decimal("2850000.00")
        expected_variance = Decimal("350000.00")

        result = ProjectCostTrueUpService.execute_project_cost_true_up(
            project=project,
            actual_wip_incurred=actual_wip,
            user=user
        )

        assert result["is_overrun"] is True
        assert result["variance_amount"] == expected_variance

        entry = result["journal_entry"]
        assert entry is not None
        assert entry.is_balanced is True

        lines = list(entry.lines.all())
        assert len(lines) == 2

        # طرف مدين: تحميل الفارق على تكلفة المبيعات 51100
        dr = [l for l in lines if l.debit > 0][0]
        assert dr.account.code == "51100"
        assert dr.debit == expected_variance

        # طرف دائن: إقفال رصيد مشروعات تحت التنفيذ 12101
        cr = [l for l in lines if l.credit > 0][0]
        assert cr.account.code == "12101"
        assert cr.credit == expected_variance

    def test_project_completion_cost_true_up_with_cost_saving(self, true_up_setup):
        """التحقق من ترحيل قيد التسوية عند وجود وفر وتوفير في تكاليف الإنشاء الفعلية (Cost Saving)"""
        setup = true_up_setup
        project = setup["project"]
        user = setup["user"]

        # التكاليف الفعلية المنفذة في WIP بلغت 2,300,000 ج.م بينما المعترف به مرحلياً 2,500,000 ج.م
        # فرق التكلفة = -200,000 ج.م (وفر في التكلفة يعود لصالح تكلفة المبيعات)
        actual_wip = Decimal("2300000.00")
        expected_variance = Decimal("-200000.00")

        result = ProjectCostTrueUpService.execute_project_cost_true_up(
            project=project,
            actual_wip_incurred=actual_wip,
            user=user
        )

        assert result["is_saving"] is True
        assert result["variance_amount"] == expected_variance

        entry = result["journal_entry"]
        assert entry is not None
        assert entry.is_balanced is True

        lines = list(entry.lines.all())
        assert len(lines) == 2

        # طرف مدين: تسوية مشروعات تحت التنفيذ 12101
        dr = [l for l in lines if l.debit > 0][0]
        assert dr.account.code == "12101"
        assert dr.debit == abs(expected_variance)

        # طرف دائن: تخفيض تكلفة المبيعات 51100
        cr = [l for l in lines if l.credit > 0][0]
        assert cr.account.code == "51100"
        assert cr.credit == abs(expected_variance)

    def test_project_cost_true_up_zero_variance_creates_no_entry(self, true_up_setup):
        """التحقق من عدم إنشاء أي قيد تسوية عند تطابق التكلفة الفعلية تماماً مع التكلفة المرحلية المحملة"""
        setup = true_up_setup
        project = setup["project"]

        actual_wip = Decimal("2500000.00")  # متطابق تماماً
        result = ProjectCostTrueUpService.execute_project_cost_true_up(
            project=project,
            actual_wip_incurred=actual_wip,
            user=setup["user"]
        )

        assert result["is_balanced"] is True
        assert result["variance_amount"] == Decimal("0.00")
        assert result["journal_entry"] is None
