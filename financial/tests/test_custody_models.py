# -*- coding: utf-8 -*-
"""
اختبارات النماذج والترقيم للعهد المالية والعينية
Tests for Custody Models, Sequences, and Lifecycle
"""

from decimal import Decimal
import pytest
from django.utils import timezone
from django.contrib.auth import get_user_model

from core.enums.document_types import DocumentType
from core.services.sequence_service import SequenceService
from financial.models import (
    AccountType,
    ChartOfAccounts,
    Currency,
    UserTreasuryAccess,
    CustodyAssignmentHistory,
    EmployeeCustodyAdvance,
    PettyCashSettlement,
    PettyCashSettlementLine,
    CustodyTransfer,
    PettyCashCount,
    CustodyAdvanceStatus,
    SettlementStatus,
    SettlementLineType,
    PaymentChannel,
)
from hr.models import (
    Employee,
    Department,
    JobTitle,
    WorkLocation,
    EmployeeAssetCustody,
    EmployeeAssetTransfer,
    AssetCustodyStatus,
    AssetCategory,
)

User = get_user_model()


@pytest.mark.django_db
class TestCustodyModelsAndSequences:
    """اختبارات بنية نماذج العهد والترقيم المركزي"""

    @pytest.fixture(autouse=True)
    def setup_fixtures(self):
        self.user = User.objects.create_user(
            username="test_auditor",
            email="auditor@test.com",
            password="Password123!",
        )
        self.dept = Department.objects.create(code="FIN", name_ar="الشؤون المالية")
        self.job = JobTitle.objects.create(code="ACC", title_ar="محاسب عهد", department=self.dept)
        self.work_location = WorkLocation.objects.create(
            name_ar="المقر الرئيسي - القاهرة",
            latitude=Decimal("30.0444000"),
            longitude=Decimal("31.2357000"),
        )

        self.employee1 = Employee.objects.create(
            employee_number="EMP001",
            name="أحمد علي حسن",
            national_id="29001011234567",
            birth_date="1990-01-01",
            gender="male",
            marital_status="married",
            department=self.dept,
            job_title=self.job,
            work_location=self.work_location,
            hire_date=timezone.now().date(),
            created_by=self.user,
        )
        self.employee2 = Employee.objects.create(
            employee_number="EMP002",
            name="محمود حسن علي",
            national_id="29101011234568",
            birth_date="1991-01-01",
            gender="male",
            marital_status="single",
            department=self.dept,
            job_title=self.job,
            work_location=self.work_location,
            hire_date=timezone.now().date(),
            created_by=self.user,
        )

        self.currency, _ = Currency.objects.get_or_create(
            code="EGP",
            defaults={
                "name": "جنيه مصري",
                "symbol": "ج.م",
                "is_functional": True,
            },
        )
        self.usd_currency, _ = Currency.objects.get_or_create(
            code="USD",
            defaults={
                "name": "دولار أمريكي",
                "symbol": "$",
                "is_functional": False,
            },
        )

        self.asset_type = AccountType.objects.create(
            code="1000",
            name="أصول متداولة",
            category="asset",
            nature="debit",
        )
        self.expense_type = AccountType.objects.create(
            code="5000",
            name="مصروفات تشغيلية",
            category="expense",
            nature="debit",
        )

        self.main_treasury = ChartOfAccounts.objects.create(
            code="101001",
            name="الخزينة الرئيسية",
            account_type=self.asset_type,
            is_cash_account=True,
            currency=self.currency,
        )
        self.custody_account = ChartOfAccounts.objects.create(
            code="101005",
            name="عهدة أحمد علي المستديمة",
            account_type=self.asset_type,
            is_custody_account=True,
            custody_type="permanent",
            assigned_employee=self.employee1,
            work_location=self.work_location,
            currency=self.currency,
        )
        self.expense_account = ChartOfAccounts.objects.create(
            code="501001",
            name="مصروفات بوفية وضيافة",
            account_type=self.expense_type,
            currency=self.currency,
        )

    def test_chart_of_accounts_custody_properties(self):
        """التحقق من حقول العهد في شجرة الحسابات"""
        assert self.custody_account.is_custody_account is True
        assert self.custody_account.custody_type == "permanent"
        assert self.custody_account.assigned_employee == self.employee1
        assert self.custody_account.work_location == self.work_location

    def test_user_treasury_access_employee_link(self):
        """التحقق من ربط إسناد الخزينة بالموظف"""
        access = UserTreasuryAccess.objects.create(
            user=self.user,
            employee=self.employee1,
            treasury=self.custody_account,
            can_deposit=True,
            can_disburse=True,
        )
        assert access.employee == self.employee1
        assert access.treasury.is_custody_account is True

    def test_custody_assignment_history(self):
        """التحقق من تسجيل السجل التاريخي لإسناد العهدة"""
        history = CustodyAssignmentHistory.objects.create(
            account=self.custody_account,
            employee=self.employee1,
            assigned_by=self.user,
            start_date=timezone.now().date(),
            is_active=True,
            opening_balance_on_handover=Decimal("5000.00"),
        )
        assert history.id is not None
        assert history.account == self.custody_account
        assert history.employee == self.employee1
        assert history.is_active is True

    def test_employee_custody_advance_lifecycle(self):
        """التحقق من دورة حياة العهدة المؤقتة وحساب الرصيد"""
        adv_num = SequenceService.get_next_number(DocumentType.CUSTODY_ADVANCE)
        assert adv_num.startswith("CADV")

        advance = EmployeeCustodyAdvance.objects.create(
            advance_number=adv_num,
            employee=self.employee1,
            user=self.user,
            source_treasury=self.main_treasury,
            work_location=self.work_location,
            amount=Decimal("3000.00"),
            currency=self.currency,
            due_date=timezone.now().date() + timezone.timedelta(days=7),
            purpose="مأمورية شراء مستلزمات مكتبية",
            status=CustodyAdvanceStatus.ACTIVE,
        )
        advance.update_balance()
        assert advance.current_balance == Decimal("3000.00")
        assert advance.status == CustodyAdvanceStatus.ACTIVE

        # إضافة تغذية إضافية وتسوية جزئية
        advance.top_up_amount = Decimal("1000.00")
        advance.settled_amount = Decimal("2500.00")
        advance.returned_cash_amount = Decimal("500.00")
        advance.update_balance()
        assert advance.current_balance == Decimal("1000.00")
        assert advance.status == CustodyAdvanceStatus.PARTIALLY_SETTLED

        # إكمال التسوية
        advance.settled_amount = Decimal("3500.00")
        advance.update_balance()
        assert advance.current_balance == Decimal("0.00")
        assert advance.status == CustodyAdvanceStatus.SETTLED

    def test_petty_cash_settlement_and_lines(self):
        """التحقق من إنشاء سند التسوية وأسطر المصروفات والضرائب"""
        set_num = SequenceService.get_next_number(DocumentType.CUSTODY_SETTLEMENT)
        assert set_num.startswith("CSET")

        settlement = PettyCashSettlement.objects.create(
            settlement_number=set_num,
            custody_account=self.custody_account,
            employee=self.employee1,
            settlement_date=timezone.now().date(),
            work_location=self.work_location,
            total_expenses=Decimal("1500.00"),
            total_tax=Decimal("210.00"),
            total_settled_amount=Decimal("1710.00"),
            status=SettlementStatus.SUBMITTED,
        )
        assert settlement.id is not None

        line1 = PettyCashSettlementLine.objects.create(
            settlement=settlement,
            line_number=1,
            line_type=SettlementLineType.DIRECT_EXPENSE,
            payment_channel=PaymentChannel.CASH,
            expense_account=self.expense_account,
            target_work_location=self.work_location,
            invoice_number="INV-9988",
            supplier_name="شركة الأمل للضيافة",
            supplier_tax_id="123456789",
            currency=self.currency,
            amount=Decimal("1710.00"),
            tax_amount=Decimal("210.00"),
            description="مستلزمات ضيافة وبوفيه للمقر",
        )
        assert line1.id is not None
        assert line1.settlement == settlement

    def test_custody_transfer_and_count(self):
        """التحقق من سند التحويل ومحضر الجرد الفعلي"""
        trf_num = SequenceService.get_next_number(DocumentType.CUSTODY_TRANSFER)
        assert trf_num.startswith("CTRF")

        transfer = CustodyTransfer.objects.create(
            transfer_number=trf_num,
            from_employee=self.employee1,
            to_employee=self.employee2,
            amount=Decimal("500.00"),
            currency=self.currency,
            notes="تحويل عهدة لمهندس الموقع البديل",
        )
        assert transfer.id is not None

        cnt_num = SequenceService.get_next_number(DocumentType.CUSTODY_COUNT)
        assert cnt_num.startswith("CCNT")

        count = PettyCashCount.objects.create(
            count_number=cnt_num,
            custody_account=self.custody_account,
            employee=self.employee1,
            auditor=self.user,
            gl_balance=Decimal("2000.00"),
            actual_cash_amount=Decimal("1950.00"),
            pending_vouchers_amount=Decimal("0.00"),
            variance_amount=Decimal("-50.00"),
            variance_type="shortage",
            denomination_breakdown={"100": 19, "50": 1},
        )
        assert count.id is not None
        assert count.variance_type == "shortage"

    def test_employee_asset_custody_and_transfer(self):
        """التحقق من العهد العينية ومحضر المناقلة الميداني"""
        code = SequenceService.get_next_number(DocumentType.CUSTODY_ASSET_RECEIPT)
        assert code.startswith("CASR")

        asset = EmployeeAssetCustody.objects.create(
            custody_code=code,
            employee=self.employee1,
            work_location=self.work_location,
            item_name="لابتوب Dell Latitude 5420",
            category=AssetCategory.LAPTOP_PC,
            serial_number="DELL-LAT-998822",
            is_consumable=False,
            estimated_value=Decimal("25000.00"),
            status=AssetCustodyStatus.ACTIVE,
        )
        assert asset.id is not None
        assert asset.status == AssetCustodyStatus.ACTIVE

        trf_code = SequenceService.get_next_number(DocumentType.CUSTODY_ASSET_TRANSFER)
        assert trf_code.startswith("CAST")

        asset_transfer = EmployeeAssetTransfer.objects.create(
            transfer_code=trf_code,
            asset_custody=asset,
            from_employee=self.employee1,
            to_employee=self.employee2,
            approved_by=self.user,
            notes="مناقلة الجهاز في موقع العمل لمهندس المشروع",
        )
        assert asset_transfer.id is not None
        assert asset_transfer.to_employee == self.employee2
