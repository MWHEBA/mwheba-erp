# -*- coding: utf-8 -*-
"""
Tests for Building Facility Ledger & Supplemental Maintenance Levy Apportionment
MWHEBA ERP — Real Estate Wave 3 (Phase 11)
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
    BuildingFacilitySubledger,
    MaintenanceFundOperation,
    SupplementalLevyApportionment,
)
from real_estate.services.facility_service import BuildingFacilityService

User = get_user_model()


@pytest.fixture
def multi_unit_facility_setup(db):
    user, _ = User.objects.get_or_create(
        username="facility_director",
        defaults={"email": "facility_director@test.com", "is_staff": True}
    )
    currency, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={"name": "جنيه مصري", "symbol": "ج.م"}
    )

    asset_type, _ = AccountType.objects.get_or_create(
        code='asset',
        defaults={'name': 'أصول', 'category': 'asset', 'nature': 'debit'}
    )
    liability_type, _ = AccountType.objects.get_or_create(
        code='liability',
        defaults={'name': 'خصوم', 'category': 'liability', 'nature': 'credit'}
    )

    restricted_cash_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="11170",
        defaults={
            "name": "حساب البنك المقيد لوديعة صيانة المشروعات",
            "account_type": asset_type,
            "is_active": True
        }
    )
    escrow_liability_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="21520",
        defaults={
            "name": "أمانات صندوق صيانة اتحاد الشاغلين",
            "account_type": liability_type,
            "is_active": True
        }
    )
    levy_receivable_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="11240",
        defaults={
            "name": "مدينو فروق صيانة اتحاد الشاغلين (Levy Receivable)",
            "account_type": asset_type,
            "is_active": True
        }
    )

    project = RealEstateProject.objects.create(
        code="PRJ-LEVY-01",
        name="كمبوند صن رايز كينجدوم",
        start_date=date(2024, 1, 1),
        expected_completion_date=date(2026, 12, 31),
        total_land_area=Decimal("15000.00"),
        gross_built_area=Decimal("50000.00"),
        created_by=user
    )
    block = PropertyBlock.objects.create(project=project, code="B-01", name="المبنى الرئيسي")
    floor = PropertyFloor.objects.create(block=block, floor_number=1, name="الدور الأول")

    # إنشاء 3 عملاء و3 وحدات بمساحات مختلفة
    # الوحدة 1: 100 م² (20%)
    # الوحدة 2: 150 م² (30%)
    # الوحدة 3: 250 م² (50%)
    # الإجمالي = 500 م²
    customers = []
    units = []
    contracts = []
    areas = [Decimal("100.00"), Decimal("150.00"), Decimal("250.00")]

    for i, area in enumerate(areas, start=1):
        cust = Customer.objects.create(
            code=f"CUST-LVY-0{i}",
            name=f"مالك الوحدة {i}",
            default_currency=currency
        )
        customers.append(cust)

        u = PropertyUnit.objects.create(
            project=project,
            floor=floor,
            unit_code=f"SR-U10{i}",
            gross_area=area,
            net_area=area - Decimal("15.00"),
            meter_price=Decimal("20000.00"),
            total_price=area * Decimal("20000.00"),
            status=PropertyUnit.UnitStatus.DELIVERED
        )
        units.append(u)

        ctr = PropertyContract.objects.create(
            contract_number=f"CTR-LVY-2026-00{i}",
            project=project,
            unit=u,
            customer=cust,
            final_contract_price=area * Decimal("20000.00"),
            down_payment=Decimal("200000.00"),
            currency=currency,
            contract_date=date(2024, 6, 1),
            delivery_date=date(2025, 12, 31),
            status=PropertyContract.ContractStatus.ACTIVE,
            created_by=user
        )
        contracts.append(ctr)

    subledger = BuildingFacilityService.get_or_create_subledger(
        project=project,
        user=user,
        restricted_cash_account=restricted_cash_acc,
        maintenance_escrow_account=escrow_liability_acc
    )

    return {
        "user": user,
        "project": project,
        "units": units,
        "contracts": contracts,
        "customers": customers,
        "subledger": subledger,
        "levy_receivable_account": levy_receivable_acc
    }


@pytest.mark.django_db
class TestMaintenanceEscrowOperations:
    """اختبارات تشغيل صندوق الصيانة وتوزيع عجز الصيانة السنوي (Supplemental Levy) على الملاك"""

    def test_supplemental_levy_apportionment_by_gross_area_when_deficit_exists(self, multi_unit_facility_setup):
        """التحقق من توزيع عجز الصيانة السنوي على ملاك الوحدات بنسبة المساحة الإجمالية (Gross Area %) بدقة تامة"""
        setup = multi_unit_facility_setup
        subledger = setup["subledger"]
        user = setup["user"]

        period_start = date(2026, 1, 1)
        period_end = date(2026, 12, 31)

        # 1. تسجيل عوائد بنكية للفترة بقيمة 100,000 ج.م
        BuildingFacilityService.post_bank_yield(
            subledger=subledger,
            yield_amount=Decimal("100000.00"),
            period_start=period_start,
            period_end=period_end,
            user=user
        )

        # 2. تسجيل مصروفات تشغيلية للفترة بقيمة 180,000 ج.م (مصاعد، أمن، نظافة)
        BuildingFacilityService.record_facility_expense(
            subledger=subledger,
            expense_amount=Decimal("80000.00"),
            expense_category=MaintenanceFundOperation.ExpenseCategory.ELEVATOR,
            operation_date=date(2026, 4, 1),
            user=user
        )
        BuildingFacilityService.record_facility_expense(
            subledger=subledger,
            expense_amount=Decimal("60000.00"),
            expense_category=MaintenanceFundOperation.ExpenseCategory.SECURITY,
            operation_date=date(2026, 8, 1),
            user=user
        )
        BuildingFacilityService.record_facility_expense(
            subledger=subledger,
            expense_amount=Decimal("40000.00"),
            expense_category=MaintenanceFundOperation.ExpenseCategory.CLEANING,
            operation_date=date(2026, 11, 1),
            user=user
        )

        # إجمالي المصروفات = 180,000 ج.م
        # إجمالي العوائد = 100,000 ج.م
        # العجز الصافي الواجب توزيعه = 80,000 ج.م

        result = BuildingFacilityService.calculate_and_apportion_annual_levy(
            subledger=subledger,
            period_start=period_start,
            period_end=period_end,
            user=user
        )

        assert result["has_deficit"] is True
        assert result["deficit_amount"] == Decimal("80000.00")
        assert result["units_count"] == 3

        # التحقق من دقة التوزيع لكل وحدة وفق المساحة:
        # إجمالي المساحة = 100 + 150 + 250 = 500 م²
        # الوحدة 1 (100 م² / 500 م² = 20%): 80,000 × 20% = 16,000 ج.م
        # الوحدة 2 (150 م² / 500 م² = 30%): 80,000 × 30% = 24,000 ج.م
        # الوحدة 3 (250 م² / 500 م² = 50%): 80,000 × 50% = 40,000 ج.م
        apportionments = {app.unit.unit_code: app for app in result["apportionments"]}

        app1 = apportionments["SR-U101"]
        assert app1.unit_gross_area == Decimal("100.00")
        assert app1.share_percentage == Decimal("20.0000")
        assert app1.apportioned_amount == Decimal("16000.00")

        app2 = apportionments["SR-U102"]
        assert app2.unit_gross_area == Decimal("150.00")
        assert app2.share_percentage == Decimal("30.0000")
        assert app2.apportioned_amount == Decimal("24000.00")

        app3 = apportionments["SR-U103"]
        assert app3.unit_gross_area == Decimal("250.00")
        assert app3.share_percentage == Decimal("50.0000")
        assert app3.apportioned_amount == Decimal("40000.00")

        # مجموع المطالبات يطابق بالمليم العجز الإجمالي
        total_levied = sum(a.apportioned_amount for a in result["apportionments"])
        assert total_levied == Decimal("80000.00")

        # 3. التحقق من القيد المحاسبي المتوازن لإثبات استحقاق الفروق
        op = MaintenanceFundOperation.objects.get(operation_number=result["operation_number"])
        assert op.journal_entry is not None
        assert op.journal_entry.is_balanced is True

        lines = list(op.journal_entry.lines.all())
        dr = [l for l in lines if l.debit > 0][0]
        cr = [l for l in lines if l.credit > 0][0]

        # مدين: مدينو فروق صيانة اتحاد الشاغلين 11240
        assert dr.account.code == "11240"
        assert dr.debit == Decimal("80000.00")

        # دائن: التزامات أمانات صندوق الصيانة 21520
        assert cr.account.code == "21520"
        assert cr.credit == Decimal("80000.00")

    def test_no_levy_apportioned_when_yields_cover_expenses(self, multi_unit_facility_setup):
        """التحقق من عدم إنشاء أي مطالبة فروق صيانة إذا كانت العوائد البنكية تغطي المصروفات بالكامل (فائض)"""
        setup = multi_unit_facility_setup
        subledger = setup["subledger"]
        user = setup["user"]

        period_start = date(2026, 1, 1)
        period_end = date(2026, 12, 31)

        # عوائد 90,000 ج.م ومصروفات 50,000 ج.م -> فائض 40,000 ج.م
        BuildingFacilityService.post_bank_yield(
            subledger=subledger,
            yield_amount=Decimal("90000.00"),
            period_start=period_start,
            period_end=period_end,
            user=user
        )
        BuildingFacilityService.record_facility_expense(
            subledger=subledger,
            expense_amount=Decimal("50000.00"),
            expense_category=MaintenanceFundOperation.ExpenseCategory.CLEANING,
            operation_date=date(2026, 6, 1),
            user=user
        )

        result = BuildingFacilityService.calculate_and_apportion_annual_levy(
            subledger=subledger,
            period_start=period_start,
            period_end=period_end,
            user=user
        )

        assert result["has_deficit"] is False
        assert result["deficit_amount"] == Decimal("0.00")
        assert "لا يوجد عجز مالي" in result["message"]
        assert SupplementalLevyApportionment.objects.count() == 0

    def test_levy_apportionment_penny_rounding_integrity(self, multi_unit_facility_setup):
        """التحقق من سلامة معالجة كسور القروش (Penny Rounding Difference Guarantee) لضمان تطابق الإجمالي تماماً"""
        setup = multi_unit_facility_setup
        subledger = setup["subledger"]
        user = setup["user"]

        # عجز بقيمة 10,000 ج.م موزع على مساحات 100، 150، 250 (نسب منتظمة)
        # لنجرب عجز ينتج كسوراً: 10,000.55 ج.م
        period_start = date(2027, 1, 1)
        period_end = date(2027, 12, 31)

        BuildingFacilityService.record_facility_expense(
            subledger=subledger,
            expense_amount=Decimal("10000.55"),
            expense_category=MaintenanceFundOperation.ExpenseCategory.OTHER,
            operation_date=date(2027, 2, 1),
            user=user
        )

        result = BuildingFacilityService.calculate_and_apportion_annual_levy(
            subledger=subledger,
            period_start=period_start,
            period_end=period_end,
            user=user
        )

        total_apportioned = sum(a.apportioned_amount for a in result["apportionments"])
        assert total_apportioned == Decimal("10000.55")
