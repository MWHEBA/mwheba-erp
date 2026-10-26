import pytest
from decimal import Decimal
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission

from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.currency import Currency
from financial.models.fiscal_year import FiscalYear
from financial.models.journal_entry import AccountingPeriod, JournalEntry
from financial.models.custody import (
    EmployeeCustodyAdvance,
    PettyCashSettlement,
    PettyCashSettlementLine,
    CustodyAdvanceStatus,
    SettlementStatus,
    SettlementLineType,
)
from hr.models import Employee, Department, JobTitle
from purchase.models.payment import PurchasePayment
from purchase.models.purchase import Purchase
from supplier.models import Supplier

User = get_user_model()


@pytest.mark.django_db
class TestPhase2CustodyHardening:
    """
    مجموعة اختبارات التحقق الصارم من متطلبات المرحلة 2:
    2.1 حقول EmployeeCustodyAdvance الجديدة
    2.2 حقول PettyCashSettlement الجديدة وملفات المرفقات
    2.3 حقول PurchasePayment وخيار CUSTODY
    2.4 الصلاحيات المخصصة Meta.permissions
    2.5 معادلة update_balance() الصامدة واستثناء العهدة المستديمة
    2.6 حراس الحذف الصارمة وتجميد الحقول المالية في clean()
    """

    def setup_method(self):
        self.user = User.objects.create_user(username="test_custody_officer", password="password123")
        self.egp, _ = Currency.objects.get_or_create(code="EGP", defaults={"name": "Egyptian Pound", "symbol": "EGP"})
        self.usd, _ = Currency.objects.get_or_create(code="USD", defaults={"name": "US Dollar", "symbol": "$"})

        self.asset_type, _ = AccountType.objects.get_or_create(name="Current Asset", category="asset", code="CA")
        self.expense_type, _ = AccountType.objects.get_or_create(name="Expense", category="expense", code="EXP")

        self.treasury_acc, _ = ChartOfAccounts.objects.get_or_create(
            code="11110",
            defaults={"name": "الخزينة الرئيسية", "account_type": self.asset_type, "is_cash_account": True, "is_active": True}
        )
        self.custody_acc, _ = ChartOfAccounts.objects.get_or_create(
            code="11130",
            defaults={"name": "العهد النقدية المؤقتة", "account_type": self.asset_type, "is_custody_account": True, "is_active": True}
        )
        self.imprest_acc, _ = ChartOfAccounts.objects.get_or_create(
            code="11230",
            defaults={"name": "العهد المستديمة", "account_type": self.asset_type, "is_custody_account": True, "is_active": True}
        )

        dept, _ = Department.objects.get_or_create(code="FIN", defaults={"name_ar": "المالية", "name_en": "Finance"})
        job, _ = JobTitle.objects.get_or_create(code="ACC", defaults={"title_ar": "محاسب", "title_en": "Accountant", "department": dept})
        self.employee = Employee.objects.create(
            name="Ahmed Ali",
            employee_number="EMP-7001",
            national_id="29001010101011",
            birth_date=date(1990, 1, 1),
            gender="male",
            marital_status="single",
            hire_date=date(2023, 1, 1),
            department=dept,
            job_title=job,
            created_by=self.user,
        )

        self.fy, _ = FiscalYear.objects.get_or_create(
            year_code="FY2026",
            defaults={"name": "Fiscal Year 2026", "start_date": date(2026, 1, 1), "end_date": date(2026, 12, 31), "status": "open"}
        )
        self.period, _ = AccountingPeriod.objects.get_or_create(
            fiscal_year=self.fy,
            period_number=1,
            defaults={"name": "January 2026", "start_date": date(2026, 1, 1), "end_date": date(2026, 1, 31), "status": "open"}
        )

    def test_2_1_and_2_4_advance_fields_and_permissions(self):
        """اختبار الحقول الجديدة والصلاحيات المخصصة لنموذج EmployeeCustodyAdvance"""
        advance = EmployeeCustodyAdvance.objects.create(
            advance_number="ADV-TEST-001",
            employee=self.employee,
            user=self.user,
            source_treasury=self.treasury_acc,
            amount=Decimal("5000.00"),
            currency=self.egp,
            issue_date=date(2026, 1, 10),
            due_date=date(2026, 1, 25),
            purpose="اختبار المرحلة 2",
            status=CustodyAdvanceStatus.DRAFT,
            custody_type="temporary",
            settlement_principal_amount=Decimal("4500.00"),
            refunds_collected_amount=Decimal("200.00"),
            shortage_amount=Decimal("100.00"),
            transferred_out_amount=Decimal("300.00"),
            transferred_in_amount=Decimal("500.00"),
            custody_account=self.custody_acc,
            imprest_ceiling=Decimal("10000.00"),
        )
        advance.refresh_from_db()
        assert advance.settlement_principal_amount == Decimal("4500.00")
        assert advance.refunds_collected_amount == Decimal("200.00")
        assert advance.shortage_amount == Decimal("100.00")
        assert advance.transferred_out_amount == Decimal("300.00")
        assert advance.transferred_in_amount == Decimal("500.00")
        assert advance.custody_type == "temporary"
        assert advance.custody_account == self.custody_acc
        assert advance.imprest_ceiling == Decimal("10000.00")

        # التحقق من الصلاحيات المخصصة في Meta
        perms = [p[0] for p in EmployeeCustodyAdvance._meta.permissions]
        assert "can_disburse_custody" in perms
        assert "can_transfer_custody" in perms

    def test_2_2_and_2_4_settlement_fields_and_permissions(self):
        """اختبار الحقول الجديدة والصلاحيات المخصصة لنموذج PettyCashSettlement وسطورها"""
        settlement = PettyCashSettlement.objects.create(
            settlement_number="SET-TEST-001",
            employee=self.employee,
            settlement_date=date(2026, 1, 15),
            currency=self.egp,
            expenses_absorbed=Decimal("1200.00"),
            refunds_collected=Decimal("300.00"),
            overrun_amount=Decimal("150.00"),
            eligible_replenishment_amount=Decimal("900.00"),
            is_replenished=False,
            rejection_reason="تحت المراجعة",
            status=SettlementStatus.DRAFT,
        )
        settlement.refresh_from_db()
        assert settlement.currency == self.egp
        assert settlement.expenses_absorbed == Decimal("1200.00")
        assert settlement.refunds_collected == Decimal("300.00")
        assert settlement.overrun_amount == Decimal("150.00")
        assert settlement.eligible_replenishment_amount == Decimal("900.00")
        assert settlement.is_replenished is False
        assert settlement.rejection_reason == "تحت المراجعة"

        # فحص حقل receipt_file في السطور
        line = PettyCashSettlementLine.objects.create(
            settlement=settlement,
            line_number=1,
            line_type=SettlementLineType.DIRECT_EXPENSE,
            amount=Decimal("500.00"),
            currency=self.egp,
            expense_account=self.treasury_acc,
            description="نثريات موقع",
        )
        assert hasattr(line, "receipt_file")

        # التحقق من الصلاحيات المخصصة في Meta
        perms = [p[0] for p in PettyCashSettlement._meta.permissions]
        assert "can_post_settlement" in perms
        assert "can_reverse_settlement" in perms
        assert "can_audit_custody" in perms

    def test_2_3_purchase_payment_custody_fields_and_choices(self):
        """اختبار إضافة الخصم وضريبة المنبع وخيار CUSTODY في PurchasePayment"""
        supplier = Supplier.objects.create(name="Supplier XYZ", code="SUP-XYZ")
        purchase = Purchase.objects.create(
            number="INV-2026-XYZ",
            supplier=supplier,
            date=date(2026, 1, 10),
            subtotal=Decimal("1000.00"),
            total=Decimal("1000.00"),
            currency=self.egp,
            payment_status="unpaid",
            created_by=self.user,
        )

        payment = PurchasePayment.objects.create(
            purchase=purchase,
            amount=Decimal("850.00"),
            payment_date=date(2026, 1, 12),
            source_type="CUSTODY",
            financial_account=self.custody_acc,
            payment_currency=self.egp,
            discount_amount=Decimal("100.00"),
            withholding_tax_amount=Decimal("50.00"),
            amount_paid_currency=Decimal("850.00"),
            amount_settled_invoice_currency=Decimal("1000.00"),
            amount_functional=Decimal("850.00"),
            created_by=self.user,
        )
        payment.refresh_from_db()
        assert payment.source_type == "CUSTODY"
        assert payment.discount_amount == Decimal("100.00")
        assert payment.withholding_tax_amount == Decimal("50.00")
        assert payment.is_custody_payment is True

        choices_dict = dict(PurchasePayment.SOURCE_TYPE_CHOICES)
        assert "CUSTODY" in choices_dict

    def test_2_5_update_balance_formula_and_permanent_custody(self):
        """
        اختبار معادلة update_balance() الصامدة:
        - اعتماد settlement_principal_amount (بدل السفر المقطوع)
        - إضافة refunds_collected_amount (زيادة النقدية بيد الموظف)
        - طرح shortage_amount (عجز محمل على ذمة الموظف)
        - استثناء العهدة المستديمة من التحول التلقائي لحالة SETTLED
        """
        # حالة 1: سلفة مؤقتة مع بدل مقطوع ومرتجع
        adv = EmployeeCustodyAdvance.objects.create(
            advance_number="ADV-MATH-001",
            employee=self.employee,
            source_treasury=self.treasury_acc,
            amount=Decimal("1000.00"),
            settlement_principal_amount=Decimal("800.00"),  # 1000 - 200 بدل مقطوع
            currency=self.egp,
            issue_date=date(2026, 1, 10),
            due_date=date(2026, 12, 31),
            status=CustodyAdvanceStatus.ACTIVE,
            custody_type="temporary",
        )
        adv.update_balance()
        assert adv.current_balance == Decimal("800.00")
        assert adv.status == CustodyAdvanceStatus.ACTIVE

        # تحصيل مرتجع نقدي 200 ج.م -> يزيد الرصيد إلى 1000 ج.م
        adv.refunds_collected_amount = Decimal("200.00")
        adv.update_balance()
        assert adv.current_balance == Decimal("1000.00")

        # تسوية منصرفات 700 ج.م + عجز محمل 100 ج.م + توريد نقدية 200 ج.م -> الرصيد يصبح صفر
        adv.settled_amount = Decimal("700.00")
        adv.shortage_amount = Decimal("100.00")
        adv.returned_cash_amount = Decimal("200.00")
        adv.update_balance()
        assert adv.current_balance == Decimal("0.00")
        assert adv.status == CustodyAdvanceStatus.SETTLED

        # حالة 2: عهدة مستديمة وصلت إلى صفر لا تتحول إلى SETTLED
        perm_adv = EmployeeCustodyAdvance.objects.create(
            advance_number="ADV-PERM-001",
            employee=self.employee,
            source_treasury=self.treasury_acc,
            amount=Decimal("5000.00"),
            currency=self.egp,
            issue_date=date(2026, 1, 1),
            due_date=date(2026, 12, 31),
            status=CustodyAdvanceStatus.ACTIVE,
            custody_type="permanent",
            custody_account=self.imprest_acc,
        )
        perm_adv.settled_amount = Decimal("5000.00")
        perm_adv.update_balance()
        assert perm_adv.current_balance == Decimal("0.00")
        # العهدة المستديمة تظل نشطة ولا تُقفل كـ SETTLED تلقائياً
        assert perm_adv.status != CustodyAdvanceStatus.SETTLED
        assert perm_adv.status == CustodyAdvanceStatus.ACTIVE

    def test_2_6_deletion_guards_and_immutability(self):
        """
        اختبار حراس الحذف الصارمة وتجميد الحقول في clean()
        """
        # 1. حارس حذف العهدة النشطة أو التي لها قيد
        adv = EmployeeCustodyAdvance.objects.create(
            advance_number="ADV-DEL-001",
            employee=self.employee,
            source_treasury=self.treasury_acc,
            amount=Decimal("2000.00"),
            currency=self.egp,
            issue_date=date(2026, 1, 10),
            due_date=date(2026, 1, 20),
            status=CustodyAdvanceStatus.ACTIVE,
        )
        with pytest.raises(ValidationError) as exc:
            adv.delete()
        assert "لا يجوز حذف عهدة نشطة" in str(exc.value)

        # يمكن حذفها إذا كانت مسودة وبدون قيد
        adv.status = CustodyAdvanceStatus.DRAFT
        adv.save()
        adv_id = adv.id
        adv.delete()
        assert not EmployeeCustodyAdvance.objects.filter(id=adv_id).exists()

        # 2. تجميد الحقول في EmployeeCustodyAdvance بعد مغادرة المسودة
        adv2 = EmployeeCustodyAdvance.objects.create(
            advance_number="ADV-IMM-002",
            employee=self.employee,
            source_treasury=self.treasury_acc,
            amount=Decimal("3000.00"),
            currency=self.egp,
            issue_date=date(2026, 1, 10),
            due_date=date(2026, 1, 20),
            status=CustodyAdvanceStatus.ACTIVE,
        )
        adv2.amount = Decimal("4000.00")
        with pytest.raises(ValidationError) as exc:
            adv2.clean()
        assert "لا يجوز تعديل مبلغ العهدة" in str(exc.value)

        # 3. حارس حذف وتجميد تسوية العهدة المرحّلة محاسبياً
        settlement = PettyCashSettlement.objects.create(
            settlement_number="SET-POSTED-001",
            employee=self.employee,
            settlement_date=date(2026, 1, 15),
            currency=self.egp,
            total_settled_amount=Decimal("1500.00"),
            status=SettlementStatus.APPROVED,
        )
        line = PettyCashSettlementLine.objects.create(
            settlement=settlement,
            line_number=1,
            line_type=SettlementLineType.DIRECT_EXPENSE,
            amount=Decimal("1500.00"),
            currency=self.egp,
            expense_account=self.treasury_acc,
            description="بند مرحل",
        )
        settlement.status = SettlementStatus.POSTED
        settlement.save(update_fields=["status"])

        with pytest.raises(ValidationError) as exc:
            settlement.delete()
        assert "لا يجوز حذف تسوية مرحلة محاسبياً" in str(exc.value)

        # تجميد حقول التسوية المرحلة
        settlement.total_settled_amount = Decimal("2000.00")
        with pytest.raises(ValidationError) as exc:
            settlement.clean()
        assert "لا يمكن تعديل هذا الحقل المالي بعد ترحيل" in str(exc.value)

        # 4. حارس حذف بنود تسوية مرحلة
        with pytest.raises(ValidationError) as exc:
            line.delete()
        assert "لا يمكن حذف بند من تسوية مرحلة محاسبياً" in str(exc.value)
