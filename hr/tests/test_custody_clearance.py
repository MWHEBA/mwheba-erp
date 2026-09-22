import pytest
from decimal import Decimal
from datetime import date
from django.utils import timezone
from django.contrib.auth import get_user_model

from hr.models import (
    Employee,
    Department,
    JobTitle,
    WorkLocation,
    EmployeeAssetCustody,
    AssetCustodyStatus,
    AssetCategory,
)
from financial.models.currency import Currency
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.custody import EmployeeCustodyAdvance, CustodyAdvanceStatus
from hr.services.employee_service import EmployeeService

User = get_user_model()


@pytest.mark.django_db
class TestEmployeeCustodyClearance:
    @pytest.fixture(autouse=True)
    def setup_data(self):
        self.user = User.objects.create_user(
            username="hr_manager",
            email="hr@test.com",
            password="Password123!",
            is_staff=True,
        )

        self.dept = Department.objects.create(name_ar="الموارد البشرية", code="HR")
        self.job = JobTitle.objects.create(title_ar="أخصائي شؤون موظفين", department=self.dept, code="HRA")
        self.work_location = WorkLocation.objects.create(name_ar="المقر الرئيسي", latitude=30.0, longitude=31.0)

        self.employee = Employee.objects.create(
            employee_number="EMP-099",
            name="طارق يحيى إبراهيم",
            national_id="29012120102030",
            birth_date=date(1990, 12, 12),
            gender="male",
            marital_status="married",
            hire_date=date(2022, 1, 1),
            department=self.dept,
            job_title=self.job,
            work_location=self.work_location,
            created_by=self.user,
        )

        self.currency, _ = Currency.objects.get_or_create(
            code="EGP",
            defaults={"name": "جنيه مصري", "symbol": "ج.م", "is_functional": True}
        )

        self.asset_type = AccountType.objects.create(
            code="1000",
            name="أصول متداولة",
            category="asset",
            nature="debit",
        )

        self.treasury = ChartOfAccounts.objects.create(
            code="101001",
            name="الخزينة الرئيسية",
            account_type=self.asset_type,
            currency=self.currency,
        )

    def test_clearance_when_no_custodies(self):
        """اختبار إخلاء طرف موظف ليس في ذمته أي عهد نقدية أو أجهزة"""
        res = EmployeeService.check_custody_clearance(self.employee)
        assert res['is_cleared'] is True
        assert res['pending_cash_balance'] == Decimal("0.00")
        assert res['active_assets_count'] == 0

    def test_clearance_blocked_by_active_cash_advance(self):
        """اختبار تعليق إخلاء الطرف عند وجود عهدة نقدية غير مسواة"""
        advance = EmployeeCustodyAdvance.objects.create(
            advance_number="CADV-2026-0099",
            employee=self.employee,
            source_treasury=self.treasury,
            amount=Decimal("5000.00"),
            current_balance=Decimal("5000.00"),
            currency=self.currency,
            due_date=date(2026, 3, 1),
            purpose="عهدة موقع",
            status=CustodyAdvanceStatus.ACTIVE,
        )

        res = EmployeeService.check_custody_clearance(self.employee)
        assert res['is_cleared'] is False
        assert res['pending_cash_balance'] == Decimal("5000.00")
        assert res['unsettled_advances_count'] == 1

    def test_clearance_blocked_by_active_asset(self):
        """اختبار تعليق إخلاء الطرف عند وجود لابتوب أو جهاز في ذمة الموظف"""
        asset = EmployeeAssetCustody.objects.create(
            custody_code="CASR-2026-0099",
            employee=self.employee,
            item_name="Dell Precision 5560",
            category=AssetCategory.LAPTOP_PC,
            serial_number="DELL-PREC-776655",
            status=AssetCustodyStatus.ACTIVE,
        )

        res = EmployeeService.check_custody_clearance(self.employee)
        assert res['is_cleared'] is False
        assert res['active_assets_count'] == 1
        assert len(res['active_assets']) == 1
