# -*- coding: utf-8 -*-
"""
Tests for Maintenance Escrow Banking Yields - Tax-Free Balance Sheet Only Posting
MWHEBA ERP — Real Estate Wave 3 (Phase 11)
"""
from decimal import Decimal
from datetime import date
import pytest

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

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
)
from real_estate.services.facility_service import BuildingFacilityService

User = get_user_model()


@pytest.fixture
def facility_setup(db):
    user, _ = User.objects.get_or_create(
        username="escrow_manager",
        defaults={"email": "escrow_mgr@test.com", "is_staff": True}
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
            "name": "حساب البنك المقيد لوديعة صيانة المشروعات (Restricted Cash)",
            "account_type": asset_type,
            "is_active": True
        }
    )
    escrow_liability_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="21520",
        defaults={
            "name": "أمانات صندوق صيانة اتحاد الشاغلين (Escrow Liability)",
            "account_type": liability_type,
            "is_active": True
        }
    )

    customer, _ = Customer.objects.get_or_create(
        code="CUST-FAC-01",
        defaults={"name": "المهندس شريف الشناوي", "default_currency": currency}
    )

    project = RealEstateProject.objects.create(
        code="PRJ-FAC-01",
        name="كمبوند سيلفر تاورز",
        start_date=date(2025, 1, 1),
        expected_completion_date=date(2027, 12, 31),
        total_land_area=Decimal("10000.00"),
        gross_built_area=Decimal("40000.00"),
        created_by=user
    )
    block = PropertyBlock.objects.create(project=project, code="T-01", name="برج الفيروز")
    floor = PropertyFloor.objects.create(block=block, floor_number=3, name="الدور الثالث")

    unit = PropertyUnit.objects.create(
        project=project,
        floor=floor,
        unit_code="ST-U301",
        gross_area=Decimal("160.00"),
        net_area=Decimal("135.00"),
        meter_price=Decimal("30000.00"),
        total_price=Decimal("4800000.00"),
        status=PropertyUnit.UnitStatus.AVAILABLE
    )

    contract = PropertyContract.objects.create(
        contract_number="CTR-FAC-2026-001",
        project=project,
        unit=unit,
        customer=customer,
        final_contract_price=Decimal("4800000.00"),
        down_payment=Decimal("960000.00"),
        currency=currency,
        contract_date=date(2025, 3, 1),
        delivery_date=date(2027, 12, 31),
        status=PropertyContract.ContractStatus.ACTIVE,
        created_by=user
    )

    subledger = BuildingFacilityService.get_or_create_subledger(
        project=project,
        user=user,
        restricted_cash_account=restricted_cash_acc,
        maintenance_escrow_account=escrow_liability_acc
    )

    return {
        "user": user,
        "project": project,
        "unit": unit,
        "contract": contract,
        "subledger": subledger,
        "restricted_cash": restricted_cash_acc,
        "escrow_liability": escrow_liability_acc
    }


@pytest.mark.django_db
class TestMaintenanceEscrowYieldTaxFreeBalanceSheetEntry:
    """اختبارات إثبات عوائد شهادات ودائع الصيانة كقيد ميزانية بحت دون أي أثر على قائمة الدخل"""

    def test_bank_certificate_yield_posts_balance_sheet_only_entry(self, facility_setup):
        """التحقق من إثبات عائد الشهادة البنكية بحسابات الميزانية فقط دون أي أثر ضريبي على الأرباح والخسائر"""
        setup = facility_setup
        subledger = setup["subledger"]
        user = setup["user"]

        # إثبات عائد ربع سنوي لشهادة بنكية بقيمة 150,000 ج.م
        yield_amount = Decimal("150000.00")
        op = BuildingFacilityService.post_bank_yield(
            subledger=subledger,
            yield_amount=yield_amount,
            certificate_number="CD-NBE-99420",
            yield_rate=Decimal("19.50"),
            period_start=date(2026, 1, 1),
            period_end=date(2026, 3, 31),
            user=user
        )

        assert op.operation_type == MaintenanceFundOperation.OperationType.BANK_YIELD
        assert op.amount == yield_amount
        assert op.journal_entry is not None

        # 1. التحقق من توازن القيد المحاسبي بالقرش
        entry = op.journal_entry
        assert entry.is_balanced is True

        lines = list(entry.lines.all())
        assert len(lines) == 2

        # 2. التحقق الصارم من الحسابات: حساب أصول مقيدة وحساب التزامات أمانات
        debit_line = [l for l in lines if l.debit > 0][0]
        credit_line = [l for l in lines if l.credit > 0][0]

        # طرف مدين: البنك المقيد لوديعة الصيانة 11170 (أصل)
        assert debit_line.account.code == "11170"
        assert debit_line.account.account_type.category == "asset"
        assert debit_line.debit == yield_amount

        # طرف دائن: التزامات أمانات صندوق الصيانة 21520 (خصم / التزام)
        assert credit_line.account.code == "21520"
        assert credit_line.account.account_type.category == "liability"
        assert credit_line.credit == yield_amount

        # 3. التحقق القاطع: لا يوجد أي حساب إيراد أو مصروف (Zero P&L Impact)
        for line in lines:
            assert line.account.account_type.category not in ["revenue", "expense"]

        # 4. التحقق من تحديث رصيد الصندوق بدفتر الأستاذ المساعد
        subledger.refresh_from_db()
        assert subledger.total_yield_accumulated == yield_amount
        assert subledger.current_fund_balance == yield_amount

    def test_record_contractual_deposit_collection(self, facility_setup):
        """التحقق من تحصيل وديعة الصيانة التعاقدية (Deposit Collection) وترحيل قيدها وتحديث الرصيد"""
        setup = facility_setup
        subledger = setup["subledger"]
        contract = setup["contract"]
        user = setup["user"]

        deposit_amount = Decimal("240000.00")  # 5% من سعر الوحدة
        op = BuildingFacilityService.record_deposit_collection(
            subledger=subledger,
            contract=contract,
            amount=deposit_amount,
            user=user
        )

        assert op.operation_type == MaintenanceFundOperation.OperationType.DEPOSIT_COLLECTION
        assert op.amount == deposit_amount
        assert op.journal_entry is not None
        assert op.journal_entry.is_balanced is True

        lines = list(op.journal_entry.lines.all())
        dr = [l for l in lines if l.debit > 0][0]
        cr = [l for l in lines if l.credit > 0][0]

        assert dr.account.code == "11170"
        assert dr.debit == deposit_amount
        assert cr.account.code == "21520"
        assert cr.credit == deposit_amount

        subledger.refresh_from_db()
        assert subledger.total_collected_deposits == deposit_amount
        assert subledger.current_fund_balance == deposit_amount

    def test_facility_expense_disbursement(self, facility_setup):
        """التحقق من صرف مصروفات الصيانة الدورية خصماً من أمانات الصيانة والبنك المقيد"""
        setup = facility_setup
        subledger = setup["subledger"]
        user = setup["user"]

        # إيداع مبدئي في الصندوق
        BuildingFacilityService.post_bank_yield(
            subledger=subledger,
            yield_amount=Decimal("100000.00"),
            user=user
        )

        # صرف مصروف صيانة مصاعد بقيمة 25,000 ج.م
        expense_amount = Decimal("25000.00")
        op = BuildingFacilityService.record_facility_expense(
            subledger=subledger,
            expense_amount=expense_amount,
            expense_category=MaintenanceFundOperation.ExpenseCategory.ELEVATOR,
            description="عقد الصيانة الدورية لمصاعد البرج مع شركة شندلر",
            user=user
        )

        assert op.operation_type == MaintenanceFundOperation.OperationType.FACILITY_EXPENSE
        assert op.amount == expense_amount
        assert op.journal_entry is not None
        assert op.journal_entry.is_balanced is True

        lines = list(op.journal_entry.lines.all())
        dr = [l for l in lines if l.debit > 0][0]
        cr = [l for l in lines if l.credit > 0][0]

        # مدين: تخفيض أمانات الصيانة 21520
        assert dr.account.code == "21520"
        assert dr.debit == expense_amount
        # دائن: صرف من البنك المقيد 11170
        assert cr.account.code == "11170"
        assert cr.credit == expense_amount

        # التحقق من رصيد الصندوق الصافي المتبقي
        subledger.refresh_from_db()
        assert subledger.total_expenses_disbursed == expense_amount
        assert subledger.current_fund_balance == Decimal("75000.00")
