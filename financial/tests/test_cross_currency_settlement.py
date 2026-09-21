import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from financial.models.currency import Currency
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.services.exchange_rate_service import ExchangeRateService

User = get_user_model()


@pytest.mark.django_db
class TestCrossCurrencySettlementEngine:
    """
    اختبارات معمارية ومحاسبية لمحرك السداد المتقاطع والعملات المتعددة
    """

    def setup_method(self):
        # 1. إعداد العملات
        self.egp, _ = Currency.objects.get_or_create(
            code="EGP",
            defaults={"name": "جنيه مصري", "symbol": "ج.م", "is_functional": True, "decimal_places": 2}
        )
        self.usd, _ = Currency.objects.get_or_create(
            code="USD",
            defaults={"name": "دولار أمريكي", "symbol": "$", "is_functional": False, "decimal_places": 2}
        )
        self.eur, _ = Currency.objects.get_or_create(
            code="EUR",
            defaults={"name": "يورو", "symbol": "€", "is_functional": False, "decimal_places": 2}
        )

        # 2. إعداد المستخدم
        self.user, _ = User.objects.get_or_create(
            username="test_accountant",
            defaults={"email": "acc@mwheba.com"}
        )

        # 3. إعداد الحسابات المالية (خزينة ج.م وبنك دولار)
        acc_type_asset, _ = AccountType.objects.get_or_create(
            name="أصول متداولة",
            defaults={"code": "10", "nature": "DEBIT", "category": "ASSET"}
        )
        
        self.cash_acc, _ = ChartOfAccounts.objects.get_or_create(
            code="10100",
            defaults={"name": "الخزينة الرئيسية (EGP)", "account_type": acc_type_asset, "currency": self.egp}
        )
        self.bank_usd_acc, _ = ChartOfAccounts.objects.get_or_create(
            code="10200",
            defaults={"name": "حساب بنكي دولاري (USD)", "account_type": acc_type_asset, "currency": self.usd}
        )

    def test_scenario_1_egp_invoice_from_egp_cash(self):
        """سيناريو 1: فاتورة محلية (500 EGP) مسددة من خزينة محلية (EGP)"""
        res = ExchangeRateService.calculate_payment_settlement(
            invoice_amount=Decimal("500.00"),
            invoice_currency_code="EGP",
            invoice_rate=Decimal("1.000000"),
            payment_currency_code="EGP",
            settlement_rate=Decimal("1.000000"),
        )
        assert res["amount_paid_currency"] == Decimal("500.00")
        assert res["amount_functional"] == Decimal("500.00")
        assert res["invoice_book_functional"] == Decimal("500.00")
        assert res["realized_fx_difference"] == Decimal("0.00")
        assert res["fx_type"] == "NONE"

    def test_scenario_2_egp_invoice_from_usd_bank(self):
        """سيناريو 2 (حل الكارثة): فاتورة محلية (500 EGP) مسددة من حساب دولاري (USD) بسعر صرف 50.00"""
        res = ExchangeRateService.calculate_payment_settlement(
            invoice_amount=Decimal("500.00"),
            invoice_currency_code="EGP",
            invoice_rate=Decimal("1.000000"),
            payment_currency_code="USD",
            settlement_rate=Decimal("50.000000"),
        )
        # يجب أن يكون المبلغ بالدولار 10$ بالضبط (وليس 25 ألف دولار!)
        assert res["amount_paid_currency"] == Decimal("10.00")
        assert res["amount_functional"] == Decimal("500.00")
        assert res["invoice_book_functional"] == Decimal("500.00")
        assert res["realized_fx_difference"] == Decimal("0.00")
        assert res["fx_type"] == "NONE"

    def test_scenario_3_usd_invoice_from_egp_cash(self):
        """سيناريو 3: فاتورة أجنبية (100 USD) مسددة من خزينة محلية (EGP) بسعر صرف 52.00 (سعر الفاتورة 50.00)"""
        res = ExchangeRateService.calculate_payment_settlement(
            invoice_amount=Decimal("100.00"),
            invoice_currency_code="USD",
            invoice_rate=Decimal("50.000000"),
            payment_currency_code="EGP",
            settlement_rate=Decimal("52.000000"),
        )
        # خروج 5,200 ج.م لسداد فاتورة دفترية بـ 5,000 ج.م -> خسارة فروق صرف 200 ج.م
        assert res["amount_paid_currency"] == Decimal("5200.00")
        assert res["amount_functional"] == Decimal("5200.00")
        assert res["invoice_book_functional"] == Decimal("5000.00")
        assert res["realized_fx_difference"] == Decimal("200.00")
        assert res["fx_type"] == "LOSS"

    def test_scenario_4_usd_invoice_from_usd_bank(self):
        """سيناريو 4: فاتورة أجنبية (100 USD) مسددة من بنك دولاري بسعر صرف لحظي 52.00 (سعر الفاتورة 50.00)"""
        res = ExchangeRateService.calculate_payment_settlement(
            invoice_amount=Decimal("100.00"),
            invoice_currency_code="USD",
            invoice_rate=Decimal("50.000000"),
            payment_currency_code="USD",
            settlement_rate=Decimal("52.000000"),
        )
        # خصم 100$ من البنك، المعادل اللحظي 5,200 ج.م، الدفتري 5,000 ج.م -> فروق صرف 200 ج.م
        assert res["amount_paid_currency"] == Decimal("100.00")
        assert res["amount_functional"] == Decimal("5200.00")
        assert res["invoice_book_functional"] == Decimal("5000.00")
        assert res["realized_fx_difference"] == Decimal("200.00")
        assert res["fx_type"] == "LOSS"

    def test_scenario_5_eur_invoice_from_usd_bank(self):
        """سيناريو 5: فاتورة يورو (100 EUR - سعر 55) مسددة من بنك دولار (سعر 50)"""
        res = ExchangeRateService.calculate_payment_settlement(
            invoice_amount=Decimal("100.00"),
            invoice_currency_code="EUR",
            invoice_rate=Decimal("55.000000"),
            payment_currency_code="USD",
            settlement_rate=Decimal("50.000000"),
        )
        # 100 * 55 = 5,500 ج.م -> بالدولار: 5,500 / 50 = 110.00 USD
        assert res["amount_paid_currency"] == Decimal("110.00")
        assert res["amount_functional"] == Decimal("5500.00")
        assert res["invoice_book_functional"] == Decimal("5500.00")
        assert res["realized_fx_difference"] == Decimal("0.00")

    def test_fail_fast_guard_validation(self):
        """اختبار صمام الأمان والرفض الصارم للانحرافات المشوهة"""
        # إذا حاول مستخدم إرسال 26 ألف دولار لسداد 500 جنيه بسعر 50:
        with pytest.raises(ValidationError):
            ExchangeRateService.validate_payment_invariants(
                invoice_amount=Decimal("500.00"),
                invoice_currency_code="EGP",
                invoice_rate=Decimal("1.000000"),
                payment_currency_code="USD",
                settlement_rate=Decimal("50.000000"),
                submitted_paid_amt=Decimal("26021.32"), # قيمة مشوهة جداً
            )
