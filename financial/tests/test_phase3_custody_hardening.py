import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from financial.models.fiscal_year import FiscalYear
from financial.models.currency import Currency
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.journal_entry import AccountingPeriod, JournalEntry, JournalEntryLine
from financial.models.cost_center import CostCenter
from financial.models.cost_center_budget import CostCenterBudget, CostCenterBudgetLine
from financial.models.custody import (
    EmployeeCustodyAdvance,
    CustodyAdvanceStatus,
    SettlementLineType,
    PettyCashSettlement,
    SettlementStatus,
    PettyCashSettlementLine,
    SettlementLineStatus,
    CustodyTransfer,
)
from financial.models.custody_history import CustodyAssignmentHistory
from financial.services.custody_service import CustodyManagementService
from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
from hr.models import Employee, Department, JobTitle, WorkLocation
from purchase.models.purchase import Purchase
from purchase.models.payment import PurchasePayment
from supplier.models import Supplier

User = get_user_model()


@pytest.mark.django_db
class TestPhase3CustodyHardening:
    """
    مجموعة اختبارات التحقق الصارم من متطلبات المرحلة 3:
    3.1 & 3.9 & 3.2: دورة صرف العهدة، المعالجة المحاسبية لبدل السفر، تثبيت أصل التمويل، وقفل القيد
    3.6: فحص كفاية الخزينة بحالات العملات الأربع (EGP/EGP, USD/USD, EGP/USD, Cross-Foreign) والرفض الصارم لسعر 1.0
    3.10: خدمة التعزيز النقدي top_up_advance وإغلاق سجل المسؤول السابق في assign_custody_account_employee
    3.3 & 3.8: محرك حسابات التسوية، التمييز للشيكات، المرتجع، والقفل الذري In-Lock Revalidation
    3.4: تسوية فواتير المشتريات متعددة العملات عبر المحرك المركزي وتحديث الأستاذ المساعد للمورد
    3.5: الفحص التجميعي المسبق للموازنة المشتق مباشرة من بنود القيد المقترح
    3.7: مناقلة العهد بين الموظفين transfer_custody وتحديث سجلات المسلّم والمستلم
    """

    def setup_method(self):
        self.user = User.objects.create_user(
            username="test_cfo",
            email="cfo@example.com",
            password="password123",
            is_staff=True,
            is_superuser=True,
        )

        self.egp, _ = Currency.objects.get_or_create(
            code="EGP",
            defaults={"name": "Egyptian Pound", "symbol": "ج.م", "is_functional": True}
        )
        self.usd, _ = Currency.objects.get_or_create(
            code="USD",
            defaults={"name": "US Dollar", "symbol": "$", "is_functional": False}
        )
        self.eur, _ = Currency.objects.get_or_create(
            code="EUR",
            defaults={"name": "Euro", "symbol": "€", "is_functional": False}
        )

        self.fiscal_year, _ = FiscalYear.objects.get_or_create(
            year_code="FY2026",
            defaults={
                "name": "السنة المالية 2026",
                "start_date": date(2026, 1, 1),
                "end_date": date(2026, 12, 31),
                "status": "open",
            }
        )

        self.period = AccountingPeriod.objects.create(
            name="2026-P3",
            fiscal_year=self.fiscal_year,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            status="open",
            created_by=self.user,
        )

        self.asset_type, _ = AccountType.objects.get_or_create(
            code="AT_ASSET",
            defaults={"name": "أصول", "category": "asset", "nature": "debit"}
        )
        self.liability_type, _ = AccountType.objects.get_or_create(
            code="AT_LIAB",
            defaults={"name": "التزامات", "category": "liability", "nature": "credit"}
        )
        self.expense_type, _ = AccountType.objects.get_or_create(
            code="AT_EXP",
            defaults={"name": "مصروفات", "category": "expense", "nature": "debit"}
        )
        self.revenue_type, _ = AccountType.objects.get_or_create(
            code="AT_REV",
            defaults={"name": "إيرادات", "category": "revenue", "nature": "credit"}
        )

        # حسابات الأستاذ العام
        self.treasury_egp, _ = ChartOfAccounts.objects.get_or_create(
            code="11110",
            defaults={
                "name": "الخزينة الرئيسية EGP",
                "account_type": self.asset_type,
                "currency": self.egp,
                "is_cash_account": True,
                "is_active": True,
            }
        )
        self.treasury_usd, _ = ChartOfAccounts.objects.get_or_create(
            code="11115",
            defaults={
                "name": "خزينة الدولار USD",
                "account_type": self.asset_type,
                "currency": self.usd,
                "is_cash_account": True,
                "is_active": True,
            }
        )
        self.treasury_eur, _ = ChartOfAccounts.objects.get_or_create(
            code="11118",
            defaults={
                "name": "خزينة اليورو EUR",
                "account_type": self.asset_type,
                "currency": self.eur,
                "is_cash_account": True,
                "is_active": True,
            }
        )

        self.custody_acc, _ = ChartOfAccounts.objects.get_or_create(
            code="11130",
            defaults={
                "name": "العهد النقدية المؤقتة",
                "account_type": self.asset_type,
                "currency": self.egp,
                "is_custody_account": True,
                "is_active": True,
            }
        )
        self.imprest_acc, _ = ChartOfAccounts.objects.get_or_create(
            code="11230",
            defaults={
                "name": "صناديق العهد المستديمة / سلف الموظفين",
                "account_type": self.asset_type,
                "currency": self.egp,
                "is_custody_account": True,
                "is_active": True,
            }
        )
        self.travel_expense_acc, _ = ChartOfAccounts.objects.get_or_create(
            code="51100",
            defaults={
                "name": "مصاريف السفر والانتقالات",
                "account_type": self.expense_type,
                "currency": self.egp,
                "is_active": True,
            }
        )
        self.supplier_payable_acc, _ = ChartOfAccounts.objects.get_or_create(
            code="21110",
            defaults={
                "name": "الموردون - حساب مراقبة",
                "account_type": self.liability_type,
                "currency": self.egp,
                "is_active": True,
            }
        )
        self.vat_acc, _ = ChartOfAccounts.objects.get_or_create(
            code="11510",
            defaults={
                "name": "ضريبة مدخلات مشتريات",
                "account_type": self.asset_type,
                "currency": self.egp,
                "is_active": True,
            }
        )
        self.overrun_payable_acc, _ = ChartOfAccounts.objects.get_or_create(
            code="21230",
            defaults={
                "name": "مستحقات عهد الموظفين",
                "account_type": self.liability_type,
                "currency": self.egp,
                "is_active": True,
            }
        )
        self.fx_loss_acc, _ = ChartOfAccounts.objects.get_or_create(
            code="54300",
            defaults={
                "name": "خسائر فروق أسعار الصرف",
                "account_type": self.expense_type,
                "currency": self.egp,
                "is_active": True,
            }
        )
        self.fx_gain_acc, _ = ChartOfAccounts.objects.get_or_create(
            code="43100",
            defaults={
                "name": "أرباح فروق أسعار الصرف",
                "account_type": self.revenue_type,
                "currency": self.egp,
                "is_active": True,
            }
        )

        # الموظفون
        self.department, _ = Department.objects.get_or_create(
            code="PRJ",
            defaults={"name_ar": "المشاريع", "name_en": "Projects"}
        )
        self.job_title, _ = JobTitle.objects.get_or_create(
            code="ENG",
            defaults={"title_ar": "مهندس", "department": self.department}
        )
        self.location, _ = WorkLocation.objects.get_or_create(
            name_ar="الموقع الرئيسي",
            defaults={"latitude": 30.0, "longitude": 31.0}
        )

        self.emp1, _ = Employee.objects.get_or_create(
            employee_number="EMP-01",
            defaults={
                "name": "أحمد عادل",
                "national_id": "29001010101011",
                "birth_date": date(1990, 1, 1),
                "gender": "male",
                "marital_status": "single",
                "hire_date": date(2023, 1, 1),
                "department": self.department,
                "job_title": self.job_title,
                "work_location": self.location,
                "created_by": self.user,
            }
        )
        self.emp2, _ = Employee.objects.get_or_create(
            employee_number="EMP-02",
            defaults={
                "name": "محمود سمير",
                "national_id": "29001010101022",
                "birth_date": date(1992, 5, 5),
                "gender": "male",
                "marital_status": "married",
                "hire_date": date(2023, 2, 1),
                "department": self.department,
                "job_title": self.job_title,
                "work_location": self.location,
                "created_by": self.user,
            }
        )

        # تغذية رصيد الخزائن لتمكين عمليات الصرف المالي
        self._fund_account(self.treasury_egp, Decimal("200000.00"), self.egp)
        self._fund_account(self.treasury_usd, Decimal("10000.00"), self.usd, is_foreign=True, rate=Decimal("50.000000"))

    def _fund_account(self, account, amount, currency, is_foreign=False, rate=Decimal("1.000000")):
        """مساعدة إيداع رصيد مثبت في الأستاذ العام"""
        entry = JournalEntry.objects.create(
            number=f"FUND-{account.code}-{timezone.now().strftime('%f')}",
            date=date(2026, 1, 1),
            accounting_period=self.period,
            entry_type="opening",
            status="posted",
            description=f"تغذية رصيد {account.name}",
        )
        eq_acc, _ = ChartOfAccounts.objects.get_or_create(
            code="31010",
            defaults={"name": "رأس المال / الأرصدة الافتتاحية", "account_type": self.asset_type, "is_active": True}
        )
        func_amount = (amount if not is_foreign else (amount * rate)).quantize(Decimal("0.01"))
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=account,
            debit=func_amount,
            credit=Decimal("0.00"),
            foreign_debit=amount if is_foreign else Decimal("0.00"),
            transaction_debit=amount,
            currency=currency.code,
            exchange_rate=rate,
        )
        JournalEntryLine.objects.create(
            journal_entry=entry,
            account=eq_acc,
            debit=Decimal("0.00"),
            credit=func_amount,
            foreign_credit=amount if is_foreign else Decimal("0.00"),
            transaction_credit=amount,
            currency=currency.code,
            exchange_rate=rate,
        )

    # =========================================================================
    # 1. اختبارات صرف العهدة وبدل السفر المقطوع وحظر الصرف المتكرر (3.1 & 3.9 & 3.2)
    # =========================================================================
    def test_disburse_advance_with_per_diem_split_and_locking(self):
        """اختبار صرف عهدة ببدل سفر مقطوع وتثبيت settlement_principal_amount وقفل القيد"""
        advance = EmployeeCustodyAdvance.objects.create(
            advance_number="ADV-TEST-001",
            employee=self.emp1,
            user=self.user,
            source_treasury=self.treasury_egp,
            amount=Decimal("10000.00"),
            settlement_principal_amount=Decimal("8000.00"),
            current_balance=Decimal("8000.00"),
            currency=self.egp,
            issue_date=date(2026, 3, 1),
            due_date=date(2026, 3, 31),
            is_per_diem_split=True,
            per_diem_amount=Decimal("2000.00"),
            status=CustodyAdvanceStatus.PENDING_APPROVAL,
        )

        journal_entry = CustodyManagementService.disburse_advance(
            advance=advance,
            disbursed_by_user=self.user,
        )

        advance.refresh_from_db()
        assert advance.status == CustodyAdvanceStatus.ACTIVE
        assert advance.settlement_principal_amount == Decimal("8000.00")
        assert advance.current_balance == Decimal("8000.00")
        assert journal_entry.status == "posted"
        assert journal_entry.is_locked is True

        # التحقق من سطور القيد: مصروف السفر 2000، العهدة 8000، والخزينة 10000
        assert journal_entry.lines.count() == 3
        travel_line = journal_entry.lines.filter(account=self.travel_expense_acc).first()
        custody_line = journal_entry.lines.filter(account=self.custody_acc).first()
        treasury_line = journal_entry.lines.filter(account=self.treasury_egp).first()

        assert travel_line.debit == Decimal("2000.00")
        assert custody_line.debit == Decimal("8000.00")
        assert treasury_line.credit == Decimal("10000.00")

        # حظر الصرف المتكرر لعهدة نشطة
        with pytest.raises(ValidationError, match="لا يمكن إعادة صرف عهدة"):
            CustodyManagementService.disburse_advance(advance=advance, disbursed_by_user=self.user)

    # =========================================================================
    # 2. اختبارات كفاية الخزينة وحالات العملات الأربع وسعر 1.0 (3.6 & 3.9)
    # =========================================================================
    def test_treasury_sufficiency_scenarios(self):
        """اختبار حالات كفاية الخزينة الأربع والرفض الصارم لسعر 1.0 للعملة الأجنبية"""
        # الحالة 1: عهدة محلية بمبلغ يتجاوز رصيد الخزينة المتاح
        adv_huge = EmployeeCustodyAdvance.objects.create(
            advance_number="ADV-HUGE-EGP",
            employee=self.emp1,
            source_treasury=self.treasury_egp,
            amount=Decimal("500000.00"),
            currency=self.egp,
            issue_date=date(2026, 3, 1),
            due_date=date(2026, 3, 31),
            status=CustodyAdvanceStatus.PENDING_APPROVAL,
        )
        with pytest.raises(ValidationError, match="غير كافٍ لصرف العهدة"):
            CustodyManagementService.disburse_advance(advance=adv_huge, disbursed_by_user=self.user)

        # الحالة 3: سلفة USD من خزينة EGP بسعر 1.000000 -> رفض فوري (Fail-Fast)
        adv_usd_egp = EmployeeCustodyAdvance.objects.create(
            advance_number="ADV-USD-EGP-1",
            employee=self.emp1,
            source_treasury=self.treasury_egp,
            amount=Decimal("100.00"),
            currency=self.usd,
            exchange_rate=Decimal("1.000000"),
            issue_date=date(2026, 3, 1),
            due_date=date(2026, 3, 31),
            status=CustodyAdvanceStatus.PENDING_APPROVAL,
        )
        with pytest.raises(ValidationError, match="بسعر صرف 1.000000"):
            CustodyManagementService.disburse_advance(advance=adv_usd_egp, disbursed_by_user=self.user)

        # الحالة 4: تقاطع عملتين أجنبيتين (سلفة USD من خزينة EUR) -> حظر صريح
        adv_cross = EmployeeCustodyAdvance.objects.create(
            advance_number="ADV-CROSS-EUR",
            employee=self.emp1,
            source_treasury=self.treasury_eur,
            amount=Decimal("100.00"),
            currency=self.usd,
            exchange_rate=Decimal("50.000000"),
            issue_date=date(2026, 3, 1),
            due_date=date(2026, 3, 31),
            status=CustodyAdvanceStatus.PENDING_APPROVAL,
        )
        with pytest.raises(ValidationError, match="CashTransferService"):
            CustodyManagementService.disburse_advance(advance=adv_cross, disbursed_by_user=self.user)

    # =========================================================================
    # 3. اختبارات التعزيز النقدي top_up_advance وإغلاق سجل الإسناد (3.10)
    # =========================================================================
    def test_top_up_advance_and_assignment_history(self):
        """اختبار تعزيز العهدة top_up_advance وإغلاق سجل الإسناد السابق في account_views"""
        advance = EmployeeCustodyAdvance.objects.create(
            advance_number="ADV-TOP-01",
            employee=self.emp1,
            source_treasury=self.treasury_egp,
            amount=Decimal("5000.00"),
            settlement_principal_amount=Decimal("5000.00"),
            current_balance=Decimal("5000.00"),
            currency=self.egp,
            issue_date=date(2026, 3, 1),
            due_date=date(2026, 3, 31),
            status=CustodyAdvanceStatus.ACTIVE,
        )

        entry = CustodyManagementService.top_up_advance(
            advance=advance,
            amount=Decimal("3000.00"),
            treasury_account=self.treasury_egp,
            user=self.user,
        )
        advance.refresh_from_db()
        assert advance.top_up_amount == Decimal("3000.00")
        assert advance.current_balance == Decimal("8000.00")
        assert entry.is_locked is True

        # اختبار إغلاق سجل المسؤول السابق في CustodyAssignmentHistory
        CustodyAssignmentHistory.objects.create(
            account=self.imprest_acc,
            employee=self.emp1,
            assigned_by=self.user,
            is_active=True,
            opening_balance_on_handover=Decimal("5000.00"),
        )
        from django.test import RequestFactory
        from financial.views.account_views import assign_custody_account_employee

        rf = RequestFactory()
        req = rf.post("/financial/cash-accounts/assign-custody-employee/", {
            "account_id": self.imprest_acc.id,
            "employee_id": self.emp2.id,
        })
        req.user = self.user

        res = assign_custody_account_employee(req)
        assert res.status_code == 200

        old_hist = CustodyAssignmentHistory.objects.filter(account=self.imprest_acc, employee=self.emp1).first()
        new_hist = CustodyAssignmentHistory.objects.filter(account=self.imprest_acc, employee=self.emp2).first()

        assert old_hist.is_active is False
        assert old_hist.end_date == timezone.localdate()
        assert new_hist.is_active is True

    # =========================================================================
    # 4. اختبارات محرك التسوية والشيكات والمرتجعات والقفل الذري (3.3 & 3.8)
    # =========================================================================
    def test_settlement_totals_and_in_lock_revalidation(self):
        """اختبار محرك التسوية: الشيكات لا تصرف نقدية، المرتجع يزيد الرصيد، وفحص التدفق تحت القفل"""
        advance = EmployeeCustodyAdvance.objects.create(
            advance_number="ADV-SETT-01",
            employee=self.emp1,
            source_treasury=self.treasury_egp,
            amount=Decimal("5000.00"),
            settlement_principal_amount=Decimal("5000.00"),
            current_balance=Decimal("5000.00"),
            currency=self.egp,
            issue_date=date(2026, 3, 1),
            due_date=date(2026, 3, 31),
            status=CustodyAdvanceStatus.ACTIVE,
        )

        settlement = PettyCashSettlement.objects.create(
            settlement_number="SETT-TEST-001",
            custody_advance=advance,
            employee=self.emp1,
            settlement_date=date(2026, 3, 15),
            total_settled_amount=Decimal("4000.00"),
            cash_returned_to_treasury=Decimal("1500.00"),
            status=SettlementStatus.SUBMITTED,
        )

        # 1. سطر تسليم شيك (Handover Milestone) -> لا يسحب نقدية من العهدة
        PettyCashSettlementLine.objects.create(
            settlement=settlement,
            line_number=1,
            line_type=SettlementLineType.CHECK_DELIVERY,
            status=SettlementLineStatus.APPROVED,
            currency=self.egp,
            amount=Decimal("50000.00"),
            description="تسليم شيك بنكي لمقاول",
        )

        # 2. سطر مرتجع نقدي مقبوض من مورد -> يزيد نقدية العهدة بـ 500
        PettyCashSettlementLine.objects.create(
            settlement=settlement,
            line_number=2,
            line_type=SettlementLineType.PURCHASE_REFUND,
            status=SettlementLineStatus.APPROVED,
            currency=self.egp,
            amount=Decimal("500.00"),
            description="استرداد نقدي من مورد خامات",
        )

        # 3. سطر مصروف معتمد بـ 4000
        PettyCashSettlementLine.objects.create(
            settlement=settlement,
            line_number=3,
            line_type=SettlementLineType.DIRECT_EXPENSE,
            status=SettlementLineStatus.APPROVED,
            currency=self.egp,
            expense_account=self.travel_expense_acc,
            amount=Decimal("4000.00"),
            description="مصروفات تشغيل",
        )

        totals = CustodyManagementService.calculate_settlement_totals(settlement)
        # الرصيد المتاح = 5000 + 500 مرتجع = 5500
        # التدفق الخارج = 4000 مصروف + 1500 نقدية موردة = 5500
        assert totals["refunds_collected"] == Decimal("500.00")
        assert totals["gross_net_expenses"] == Decimal("4000.00")
        assert totals["expenses_absorbed"] == Decimal("4000.00")
        assert totals["cash_returned"] == Decimal("1500.00")
        assert totals["total_cash_in_hand"] == Decimal("5500.00")

        # ترحيل التسوية بنجاح
        entry = CustodyManagementService.post_settlement(settlement=settlement, approved_by_user=self.user)
        assert entry.status == "posted"
        assert entry.is_locked is True

        advance.refresh_from_db()
        assert advance.status == CustodyAdvanceStatus.SETTLED
        assert advance.current_balance == Decimal("0.00")
        assert advance.refunds_collected_amount == Decimal("500.00")
        assert advance.returned_cash_amount == Decimal("1500.00")

    def test_in_lock_revalidation_blocks_outflow_exceeding_available(self):
        """اختبار القفل الذري: رفض ترحيل تسوية إذا تجاوز التدفق الخارج الرصيد المتاح"""
        advance = EmployeeCustodyAdvance.objects.create(
            advance_number="ADV-SETT-ERR",
            employee=self.emp1,
            source_treasury=self.treasury_egp,
            amount=Decimal("2000.00"),
            settlement_principal_amount=Decimal("2000.00"),
            current_balance=Decimal("2000.00"),
            currency=self.egp,
            issue_date=date(2026, 3, 1),
            due_date=date(2026, 3, 31),
            status=CustodyAdvanceStatus.ACTIVE,
        )

        settlement = PettyCashSettlement.objects.create(
            settlement_number="SETT-ERR-001",
            custody_advance=advance,
            employee=self.emp1,
            settlement_date=date(2026, 3, 15),
            total_settled_amount=Decimal("1500.00"),
            cash_returned_to_treasury=Decimal("1000.00"),  # 1500 + 1000 = 2500 > 2000
            status=SettlementStatus.SUBMITTED,
        )
        PettyCashSettlementLine.objects.create(
            settlement=settlement,
            line_number=1,
            line_type=SettlementLineType.DIRECT_EXPENSE,
            status=SettlementLineStatus.APPROVED,
            currency=self.egp,
            expense_account=self.travel_expense_acc,
            amount=Decimal("1500.00"),
            description="نفقات موقع",
        )

        # تعديل الحقول لمحاكاة تدفق غير مغطى تحت القفل
        settlement.expenses_absorbed = Decimal("1500.00")
        settlement.cash_returned_to_treasury = Decimal("1000.00")
        settlement.refunds_collected = Decimal("0.00")

        with pytest.raises(ValidationError, match="تعارض تزامن: إجمالي التدفقات النقدية الخارجة"):
            CustodyManagementService.post_settlement(settlement=settlement, approved_by_user=self.user)

    # =========================================================================
    # 5. اختبارات تسوية فواتير المشتريات متعددة العملات (3.4)
    # =========================================================================
    def test_multi_currency_purchase_settlement(self):
        """اختبار تسوية فاتورة مشتريات متعددة العملات وإنشاء PurchasePayment وتحديث الأستاذ المساعد"""
        supplier = Supplier.objects.create(
            name="شركة التوريدات العالمية",
            tax_number="123456789",
        )

        purchase = Purchase.objects.create(
            number="PO-USD-101",
            supplier=supplier,
            date=date(2026, 3, 1),
            currency=self.usd,
            exchange_rate=Decimal("50.000000"),
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
            status="confirmed",
            created_by=self.user,
        )

        advance = EmployeeCustodyAdvance.objects.create(
            advance_number="ADV-PURCH-01",
            employee=self.emp1,
            source_treasury=self.treasury_egp,
            amount=Decimal("10000.00"),
            settlement_principal_amount=Decimal("10000.00"),
            current_balance=Decimal("10000.00"),
            currency=self.egp,
            issue_date=date(2026, 3, 1),
            due_date=date(2026, 3, 31),
            status=CustodyAdvanceStatus.ACTIVE,
        )

        settlement = PettyCashSettlement.objects.create(
            settlement_number="SETT-PURCH-01",
            custody_advance=advance,
            employee=self.emp1,
            settlement_date=date(2026, 3, 10),
            status=SettlementStatus.SUBMITTED,
        )

        PettyCashSettlementLine.objects.create(
            settlement=settlement,
            line_number=1,
            line_type=SettlementLineType.SUPPLIER_INVOICE,
            purchase_invoice=purchase,
            supplier=supplier,
            status=SettlementLineStatus.APPROVED,
            currency=self.usd,
            amount=Decimal("100.00"),
            exchange_rate=Decimal("55.000000"),  # سعر صرف معتمد للسداد
            description="سداد فاتورة دولار من عهدة جنيه",
        )

        entry = CustodyManagementService.post_settlement(settlement=settlement, approved_by_user=self.user)
        assert entry.is_locked is True

        # التحقق من إنشاء دفعة المشتريات
        pmt = PurchasePayment.objects.filter(purchase=purchase, source_type="CUSTODY").first()
        assert pmt is not None
        assert pmt.amount == Decimal("100.00")
        assert pmt.amount_settled_invoice_currency == Decimal("100.00")
        assert pmt.amount_paid_currency == Decimal("5500.00")  # 100 * 55
        assert pmt.status == "posted"
        assert pmt.financial_status == "synced"

        # التحقق من تحديث رصيد المورد
        supplier.refresh_from_db()
        assert supplier.balance == Decimal("-5000.00")  # انخفض رصيد ذمة المورد بمبلغ الفاتورة الدفتري (100 * 50)

    # =========================================================================
    # 6. اختبارات مناقلة العهد بين الموظفين transfer_custody (3.7)
    # =========================================================================
    def test_inter_employee_custody_transfer(self):
        """اختبار مناقلة عهدة بين موظفين وتحديث الأرصدة وقفل القيد"""
        from_adv = EmployeeCustodyAdvance.objects.create(
            advance_number="ADV-TRF-FROM",
            employee=self.emp1,
            source_treasury=self.treasury_egp,
            amount=Decimal("5000.00"),
            settlement_principal_amount=Decimal("5000.00"),
            current_balance=Decimal("5000.00"),
            currency=self.egp,
            issue_date=date(2026, 3, 1),
            due_date=date(2026, 3, 31),
            status=CustodyAdvanceStatus.ACTIVE,
        )

        transfer = CustodyTransfer.objects.create(
            transfer_number="TRF-00101",
            from_employee=self.emp1,
            to_employee=self.emp2,
            from_advance=from_adv,
            amount=Decimal("2000.00"),
            currency=self.egp,
            transfer_date=date(2026, 3, 5),
            notes="مناقلة نقدية عهدة للمهندس البديل",
        )

        entry = CustodyManagementService.transfer_custody(transfer=transfer, approved_by_user=self.user)
        assert entry.is_locked is True

        from_adv.refresh_from_db()
        assert from_adv.transferred_out_amount == Decimal("2000.00")
        assert from_adv.current_balance == Decimal("3000.00")

        transfer.refresh_from_db()
        to_adv = transfer.to_advance
        assert to_adv is not None
        assert to_adv.employee == self.emp2
        assert to_adv.current_balance == Decimal("2000.00")
        assert to_adv.status == CustodyAdvanceStatus.ACTIVE

        # محاولة مناقلة بمبلغ أكبر من الرصيد المتبقي (3000)
        transfer_excess = CustodyTransfer.objects.create(
            transfer_number="TRF-00102",
            from_employee=self.emp1,
            to_employee=self.emp2,
            from_advance=from_adv,
            amount=Decimal("4000.00"),
            currency=self.egp,
            transfer_date=date(2026, 3, 6),
        )
        with pytest.raises(ValidationError, match="غير كافٍ لتحويل"):
            CustodyManagementService.transfer_custody(transfer=transfer_excess, approved_by_user=self.user)

    # =========================================================================
    # 7. اختبارات الفحص التجميعي المسبق للموازنة (3.5)
    # =========================================================================
    def test_pre_budget_validation_blocks_exceeded_expense(self):
        """اختبار الفحص التجميعي المسبق للموازنة وحظر ترحيل التسوية عند تجاوز سقف الموازنة المعتمدة (3.5)"""
        cost_center = CostCenter.objects.create(
            code="CC-SITE-1",
            name="مشروع العاصمة",
        )
        budget = CostCenterBudget.objects.create(
            cost_center=cost_center,
            fiscal_year=self.fiscal_year,
            version=1,
            budget_amount=Decimal("1000.00"),
            status="APPROVED",
            approved_by=self.user,
        )
        CostCenterBudgetLine.objects.create(
            budget=budget,
            account=self.travel_expense_acc,
            allocated_amount=Decimal("1000.00"),
            control_policy="BLOCK",
        )

        advance = EmployeeCustodyAdvance.objects.create(
            advance_number="ADV-BUDGET-01",
            employee=self.emp1,
            source_treasury=self.treasury_egp,
            amount=Decimal("5000.00"),
            settlement_principal_amount=Decimal("5000.00"),
            current_balance=Decimal("5000.00"),
            currency=self.egp,
            issue_date=date(2026, 3, 1),
            due_date=date(2026, 3, 31),
            status=CustodyAdvanceStatus.ACTIVE,
        )

        settlement = PettyCashSettlement.objects.create(
            settlement_number="SETT-BUDGET-01",
            custody_advance=advance,
            employee=self.emp1,
            settlement_date=date(2026, 3, 15),
            total_settled_amount=Decimal("2500.00"),
            status=SettlementStatus.SUBMITTED,
        )
        PettyCashSettlementLine.objects.create(
            settlement=settlement,
            line_number=1,
            line_type=SettlementLineType.DIRECT_EXPENSE,
            status=SettlementLineStatus.APPROVED,
            currency=self.egp,
            expense_account=self.travel_expense_acc,
            cost_center=cost_center,
            amount=Decimal("2500.00"),
            description="نفقات موقع تتجاوز سقف الموازنة المعتمدة",
        )

        from financial.services.budget_control_service import BudgetExceededError
        with pytest.raises(BudgetExceededError):
            CustodyManagementService.post_settlement(settlement=settlement, approved_by_user=self.user)

