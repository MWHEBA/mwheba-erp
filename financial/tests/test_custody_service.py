import pytest
from decimal import Decimal
from datetime import date
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from core.enums.document_types import DocumentType
from core.services.sequence_service import SequenceService
from financial.models.currency import Currency
from financial.models.chart_of_accounts import (
    ChartOfAccounts,
    AccountType,
)
from financial.models.journal_entry import AccountingPeriod, JournalEntry
from financial.models.custody import (
    EmployeeCustodyAdvance,
    CustodyAdvanceStatus,
    SettlementLineType,
    PettyCashSettlement,
    SettlementStatus,
    PettyCashSettlementLine,
    SettlementLineStatus,
    CustodyTransfer,
    PettyCashCount,
)
from financial.services.custody_service import CustodyManagementService
from hr.models import (
    Employee,
    Department,
    JobTitle,
    WorkLocation,
)

User = get_user_model()


@pytest.mark.django_db
class TestCustodyService:
    @pytest.fixture(autouse=True)
    def setup_data(self):
        self.user = User.objects.create_user(
            username="test_accountant",
            email="accountant@example.com",
            password="password123",
            is_staff=True,
            is_superuser=True,
        )

        self.currency, _ = Currency.objects.get_or_create(
            code="EGP",
            defaults={
                "name": "جنيه مصري",
                "symbol": "ج.م",
                "is_functional": True,
            }
        )

        self.period = AccountingPeriod.objects.create(
            name="2026-Q1",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            status="open",
            created_by=self.user,
        )

        self.asset_type = AccountType.objects.create(
            code="1000",
            name="أصول متداولة",
            category="asset",
            nature="debit",
        )
        self.liability_type = AccountType.objects.create(
            code="2000",
            name="التزامات متداولة",
            category="liability",
            nature="credit",
        )
        self.revenue_type = AccountType.objects.create(
            code="4000",
            name="إيرادات أخرى",
            category="revenue",
            nature="credit",
        )
        self.expense_type = AccountType.objects.create(
            code="5000",
            name="مصروفات تشغيلية",
            category="expense",
            nature="debit",
        )

        self.custody_acc = ChartOfAccounts.objects.create(
            code="11240",
            name="مراقبة عهد الموظفين النقدية",
            account_type=self.asset_type,
            currency=self.currency,
            is_custody_account=True,
            custody_type="temporary",
            is_active=True,
            created_by=self.user,
        )

        self.treasury_acc = ChartOfAccounts.objects.create(
            code="11110",
            name="الخزينة الرئيسية",
            account_type=self.asset_type,
            currency=self.currency,
            is_active=True,
            created_by=self.user,
        )

        self.expense_acc = ChartOfAccounts.objects.create(
            code="51100",
            name="مصروفات تشغيلية وعمومية",
            account_type=self.expense_type,
            currency=self.currency,
            is_active=True,
            created_by=self.user,
        )

        self.vat_acc = ChartOfAccounts.objects.create(
            code="11410",
            name="ضريبة القيمة المضافة على المدخلات",
            account_type=self.asset_type,
            currency=self.currency,
            is_active=True,
            created_by=self.user,
        )

        self.wht_acc = ChartOfAccounts.objects.create(
            code="21320",
            name="ضريبة الخصم والتحصيل من المنبع",
            account_type=self.liability_type,
            currency=self.currency,
            is_active=True,
            created_by=self.user,
        )

        self.discount_acc = ChartOfAccounts.objects.create(
            code="42200",
            name="خصم مكتسب",
            account_type=self.revenue_type,
            currency=self.currency,
            is_active=True,
            created_by=self.user,
        )

        self.department = Department.objects.create(name_ar="إدارة المشاريع", code="PRJ")
        self.job_title = JobTitle.objects.create(title_ar="مهندس موقع", department=self.department, code="ENG")
        self.work_location = WorkLocation.objects.create(name_ar="موقع العاصمة الإدارية", latitude=30.0, longitude=31.0)

        self.employee1 = Employee.objects.create(
            name="م. أحمد الشناوي",
            employee_number="EMP-00101",
            national_id="29001010101011",
            birth_date=date(1990, 1, 1),
            gender="male",
            marital_status="single",
            hire_date=date(2023, 1, 1),
            department=self.department,
            job_title=self.job_title,
            work_location=self.work_location,
            created_by=self.user,
        )

        self.employee2 = Employee.objects.create(
            name="م. كريم عبد العزيز",
            employee_number="EMP-00102",
            national_id="29001010101022",
            birth_date=date(1992, 5, 5),
            gender="male",
            marital_status="married",
            hire_date=date(2023, 2, 1),
            department=self.department,
            job_title=self.job_title,
            work_location=self.work_location,
            created_by=self.user,
        )

    def test_disburse_advance_success(self):
        """اختبار صرف العهدة النقدية وتوليد القيد المحاسبي المتزن"""
        adv_num = SequenceService.get_next_number(DocumentType.CUSTODY_ADVANCE)
        advance = EmployeeCustodyAdvance.objects.create(
            advance_number=adv_num,
            employee=self.employee1,
            user=self.user,
            source_treasury=self.treasury_acc,
            amount=Decimal("15000.00"),
            currency=self.currency,
            issue_date=date(2026, 2, 1),
            due_date=date(2026, 2, 28),
            purpose="شراء مواد صيانة طارئة ومستلزمات موقع",
            status=CustodyAdvanceStatus.PENDING_APPROVAL,
        )

        journal_entry = CustodyManagementService.disburse_advance(
            advance=advance,
            disbursed_by_user=self.user,
        )

        assert journal_entry is not None
        assert journal_entry.is_posted is True
        assert advance.status == CustodyAdvanceStatus.ACTIVE
        assert advance.current_balance == Decimal("15000.00")
        assert journal_entry.lines.count() == 2

        debit_line = journal_entry.lines.filter(account=self.custody_acc).first()
        credit_line = journal_entry.lines.filter(account=self.treasury_acc).first()

        assert debit_line.debit == Decimal("15000.00")
        assert credit_line.credit == Decimal("15000.00")

    def test_post_settlement_compound_entry(self):
        """اختبار ترحيل تسوية مركبة تشمل مصروفات وضريبة VAT وضريبة WHT وخصم مكتسب"""
        adv_num = SequenceService.get_next_number(DocumentType.CUSTODY_ADVANCE)
        advance = EmployeeCustodyAdvance.objects.create(
            advance_number=adv_num,
            employee=self.employee1,
            user=self.user,
            source_treasury=self.treasury_acc,
            amount=Decimal("10000.00"),
            current_balance=Decimal("10000.00"),
            currency=self.currency,
            issue_date=date(2026, 2, 1),
            due_date=date(2026, 2, 28),
            purpose="شراء مستلزمات",
            status=CustodyAdvanceStatus.ACTIVE,
        )

        set_num = SequenceService.get_next_number(DocumentType.CUSTODY_SETTLEMENT)
        settlement = PettyCashSettlement.objects.create(
            settlement_number=set_num,
            custody_advance=advance,
            employee=self.employee1,
            settlement_date=date(2026, 2, 10),
            total_expenses=Decimal("10000.00"),
            total_settled_amount=Decimal("10000.00"),
            status=SettlementStatus.SUBMITTED,
            submitted_by=self.user,
        )

        PettyCashSettlementLine.objects.create(
            settlement=settlement,
            line_number=1,
            line_type=SettlementLineType.DIRECT_EXPENSE,
            status=SettlementLineStatus.APPROVED,
            expense_account=self.expense_acc,
            currency=self.currency,
            amount=Decimal("10000.00"),
            tax_amount=Decimal("1228.07"),
            wht_rate=Decimal("1.00"),
            wht_amount=Decimal("87.72"),
            discount_amount=Decimal("100.00"),
            invoice_number="INV-2026-9901",
            invoice_date=date(2026, 2, 9),
            description="قطع غيار وصيانة كهرباء",
        )

        journal_entry = CustodyManagementService.post_settlement(
            settlement=settlement,
            approved_by_user=self.user,
        )

        assert journal_entry is not None
        assert journal_entry.is_posted is True
        assert settlement.status == SettlementStatus.POSTED
        advance.refresh_from_db()
        assert advance.status == CustodyAdvanceStatus.SETTLED
        assert advance.current_balance == Decimal("0.00")

        total_deb = sum(l.debit for l in journal_entry.lines.all())
        total_crd = sum(l.credit for l in journal_entry.lines.all())
        assert total_deb == total_crd

    def test_custody_transfer_success(self):
        """اختبار مناقلة العهدة بين موظفين وتحديث سجل الإسناد"""
        trf_num = SequenceService.get_next_number(DocumentType.CUSTODY_TRANSFER)
        transfer = CustodyTransfer.objects.create(
            transfer_number=trf_num,
            from_employee=self.employee1,
            to_employee=self.employee2,
            amount=Decimal("5000.00"),
            currency=self.currency,
            transfer_date=date(2026, 2, 15),
            notes="نقل مسؤولية العهدة للمهندس البديل قبل الإجازة",
            status=CustodyAdvanceStatus.PENDING_APPROVAL,
        )

        journal_entry = CustodyManagementService.transfer_custody(
            transfer=transfer,
            approved_by_user=self.user,
        )

        assert journal_entry is not None
        assert transfer.status == CustodyAdvanceStatus.ACTIVE
        assert journal_entry.lines.count() == 2

    def test_petty_cash_count_denominations(self):
        """اختبار محضر جرد العهدة النقدية وتفصيل فئات النقدية وحساب الفارق"""
        count_num = SequenceService.get_next_number(DocumentType.CUSTODY_COUNT)
        count_obj = PettyCashCount.objects.create(
            count_number=count_num,
            employee=self.employee1,
            count_date=timezone.now(),
            auditor=self.user,
            gl_balance=Decimal("10000.00"),
            actual_cash_amount=Decimal("0.00"),
            pending_vouchers_amount=Decimal("2000.00"),
        )

        denoms = {
            "200": 35,  # 7000
            "100": 10,  # 1000
        }

        result = CustodyManagementService.record_petty_cash_count(
            count_obj=count_obj,
            denominations_data=denoms,
        )

        assert result.actual_cash_amount == Decimal("8000.00")
        assert result.variance_amount == Decimal("0.00")
        assert result.variance_type == "matched"
        assert result.denomination_breakdown == denoms
