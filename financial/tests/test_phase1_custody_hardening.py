import pytest
from decimal import Decimal
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth import get_user_model

from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.currency import Currency
from financial.models.fiscal_year import FiscalYear
from financial.models.journal_entry import AccountingPeriod, JournalEntry
from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
from financial.services.custody_service import CustodyManagementService
from financial.services.partner_balance_service import PartnerBalanceService
from purchase.models.payment import PurchasePayment
from purchase.models.purchase import Purchase
from supplier.models import Supplier

User = get_user_model()


@pytest.mark.django_db
class TestPhase1CustodyHardening:
    """
    مجموعة اختبارات التحقق الصارم من متطلبات المرحلة 1:
    1.1 تسجيل الأدوار الجديدة واستئصال DEFAULT_SYS_ACCOUNTS
    1.2 حوكمة _get_open_period الصارمة
    1.3 تحصين PurchasePayment ضد التعديل أو الحذف أو فك الارتباط
    1.4 حوكمة PartnerBalanceService وإلزامية invoice_rate ومنع ابتلاع الاستثناءات
    """

    def setup_method(self):
        self.user = User.objects.create_user(username="test_accountant", password="password123")
        self.egp, _ = Currency.objects.get_or_create(code="EGP", defaults={"name": "Egyptian Pound", "symbol": "EGP"})
        self.usd, _ = Currency.objects.get_or_create(code="USD", defaults={"name": "US Dollar", "symbol": "$"})

        self.asset_type, _ = AccountType.objects.get_or_create(name="Current Asset", category="asset", code="CA")
        self.expense_type, _ = AccountType.objects.get_or_create(name="Expense", category="expense", code="EXP")
        self.liability_type, _ = AccountType.objects.get_or_create(name="Liability", category="liability", code="LIA")

        # إنشاء الحسابات المعيارية
        self.acc_11440, _ = ChartOfAccounts.objects.get_or_create(
            code="11440",
            defaults={"name": "تأمينات مستردة لدى الغير", "account_type": self.asset_type, "is_active": True}
        )
        self.acc_54900, _ = ChartOfAccounts.objects.get_or_create(
            code="54900",
            defaults={"name": "عجز العهد المعتمد وخسائر متنوعة", "account_type": self.expense_type, "is_active": True}
        )
        self.acc_11130, _ = ChartOfAccounts.objects.get_or_create(
            code="11130",
            defaults={"name": "العهد النقدية المؤقتة", "account_type": self.asset_type, "is_active": True}
        )

        # السنة المالية والفترات
        self.fy, _ = FiscalYear.objects.get_or_create(
            year_code="FY2026",
            defaults={"name": "Fiscal Year 2026", "start_date": date(2026, 1, 1), "end_date": date(2026, 12, 31), "status": "open"}
        )
        self.open_period, _ = AccountingPeriod.objects.get_or_create(
            fiscal_year=self.fy,
            period_number=1,
            defaults={
                "name": "January 2026",
                "start_date": date(2026, 1, 1),
                "end_date": date(2026, 1, 31),
                "status": "open",
            }
        )

    def test_1_1_role_registry_new_roles_resolution(self):
        """التحقق من حل الأدوار الجديدة refundable_deposits_asset و custody_shortage_loss"""
        acc_dep = AccountRoleRegistry.get_account(AccountRoleNames.REFUNDABLE_DEPOSITS_ASSET)
        assert acc_dep is not None
        assert acc_dep.code == "11440"

        acc_short = AccountRoleRegistry.get_account(AccountRoleNames.CUSTODY_SHORTAGE_LOSS)
        assert acc_short is not None
        assert acc_short.code == "54900"

        # التحقق من استئصال DEFAULT_SYS_ACCOUNTS
        assert not hasattr(CustodyManagementService, "DEFAULT_SYS_ACCOUNTS")

    def test_1_2_get_open_period_strict_validation(self):
        """التحقق من رفض أي تاريخ يقع خارج الفترات المحاسبية المفتوحة وعدم التراجع لفترة أخرى"""
        valid_date = date(2026, 1, 15)
        period = CustodyManagementService._get_open_period(valid_date)
        assert period.id == self.open_period.id

        # تاريخ في شهر فبراير غير المفتوح
        invalid_date = date(2026, 2, 15)
        with pytest.raises(ValidationError) as exc_info:
            CustodyManagementService._get_open_period(invalid_date)
        assert "يقع خارج أي فترة محاسبية مفتوحة" in str(exc_info.value)

    def test_1_3_purchase_payment_custody_clean_accounts(self):
        """التحقق من قبول حسابات العهد في PurchasePayment.clean()"""
        supplier = Supplier.objects.create(name="Vendor A", code="SUP-001")
        purchase = Purchase.objects.create(
            supplier=supplier,
            number="PUR-001",
            date=date(2026, 1, 10),
            subtotal=Decimal("1000.00"),
            total=Decimal("1000.00"),
            currency=self.egp,
            payment_method="credit",
            created_by=self.user,
        )

        # حساب عهدة معتمد 11130
        payment = PurchasePayment(
            purchase=purchase,
            amount=Decimal("500.00"),
            payment_date=date(2026, 1, 10),
            payment_method="cash",
            financial_account=self.acc_11130,
            source_type="CUSTODY",
            created_by=self.user,
        )
        # يجب أن تمر الفحوصات دون ValidationError
        payment.clean()

    def test_1_3_purchase_payment_custody_governance_shield(self):
        """التحقق من تحصين دفعة العهدة ضد التعديل أو الـ unpost أو الحذف"""
        supplier = Supplier.objects.create(name="Vendor B", code="SUP-002")
        purchase = Purchase.objects.create(
            supplier=supplier,
            number="PUR-002",
            date=date(2026, 1, 10),
            subtotal=Decimal("2000.00"),
            total=Decimal("2000.00"),
            currency=self.egp,
            payment_method="credit",
            created_by=self.user,
        )

        entry = JournalEntry.objects.create(
            number="CSET-001",
            date=date(2026, 1, 10),
            accounting_period=self.open_period,
            entry_type="settlement",
            status="posted",
            source_model="PettyCashSettlement",
            source_id=999,
        )

        payment = PurchasePayment.objects.create(
            purchase=purchase,
            amount=Decimal("1000.00"),
            payment_date=date(2026, 1, 10),
            payment_method="cash",
            financial_account=self.acc_11130,
            source_type="CUSTODY",
            financial_transaction=entry,
            status="posted",
            created_by=self.user,
        )

        # 1. منع إلغاء الترحيل (unpost)
        unpost_res = payment.unpost(user=self.user)
        assert unpost_res["success"] is False
        assert "حظر حوكمة" in unpost_res["message"]

        # 2. منع تعديل الحقول المالية المحمية
        payment.amount = Decimal("1500.00")
        with pytest.raises(ValidationError) as exc:
            payment.clean()
        assert "حظر حوكمة" in str(exc.value)

        # 3. منع تغيير الحالة إلى draft
        payment.refresh_from_db()
        payment.status = "draft"
        with pytest.raises(ValidationError) as exc:
            payment.clean()
        assert "حظر حوكمة" in str(exc.value)

        # 4. منع الحذف
        payment.refresh_from_db()
        with pytest.raises(ValidationError) as exc:
            payment.delete()
        assert "حظر حوكمة" in str(exc.value)

        # 5. السماح بالحذف إذا تم تفعيل راية العكس المعتمدة _allow_custody_reversal
        payment._allow_custody_reversal = True
        payment.delete()
        assert PurchasePayment.objects.filter(pk=payment.pk).count() == 0

    def test_1_4_partner_balance_service_hardening(self):
        """التحقق من إلزامية invoice_rate الموجب ومنع ابتلاع الاستثناءات"""
        supplier = Supplier.objects.create(name="Vendor C", code="SUP-003", balance=Decimal("1000.00"))

        # 1. رفض invoice_rate None أو <= 0
        with pytest.raises(ValueError) as exc:
            PartnerBalanceService.apply_settlement_delta(
                partner_type="supplier",
                partner_id=supplier.id,
                settled_invoice_amount=Decimal("500.00"),
                invoice_rate=None
            )
        assert "إلزامي وموجب" in str(exc.value)

        with pytest.raises(ValueError) as exc:
            PartnerBalanceService.apply_settlement_delta(
                partner_type="supplier",
                partner_id=supplier.id,
                settled_invoice_amount=Decimal("500.00"),
                invoice_rate=Decimal("0.00")
            )
        assert "إلزامي وموجب" in str(exc.value)

        # 2. التحقق من السداد الناجح وتخفيض الرصيد
        PartnerBalanceService.apply_settlement_delta(
            partner_type="supplier",
            partner_id=supplier.id,
            settled_invoice_amount=Decimal("500.00"),
            invoice_rate=Decimal("1.000000")
        )
        supplier.refresh_from_db()
        assert supplier.balance == Decimal("500.00")

        # 3. التحقق من إعادة رمي الاستثناء وعدم ابتلاعه عند فشل التحديث
        with patch("supplier.models.Supplier.objects.filter", side_effect=RuntimeError("Database failure")):
            with pytest.raises(RuntimeError):
                PartnerBalanceService._update_partner_balance_field(
                    partner_type="supplier",
                    partner_id=supplier.id,
                    delta=Decimal("100.00")
                )
