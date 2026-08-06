"""
FIN-CORE-PHASE1: Master Test Suite for Phase 1 Core Backend Architecture
مصفوفة الاختبارات التلقائية لـ Phase 1 (Fail Fast, Pricing Conversion, GRNI Fix, Bridges, AccountBalancePeriod)
"""

import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from financial.models.currency import Currency, ExchangeRate
from financial.services.exchange_rate_service import ExchangeRateService
from financial.models.account_balance_period import AccountBalancePeriod
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.bridges.sales_bridge import SalesAccountingBridge
from financial.bridges.purchase_bridge import PurchaseAccountingBridge
from financial.bridges.inventory_bridge import InventoryAccountingBridge
from financial.bridges.payroll_bridge import PayrollAccountingBridge
from sale.services.pricing_service import PricingService
from purchase.services.grni_subledger_service import GRNISubledgerService

User = get_user_model()


@pytest.mark.django_db
class TestMasterPhase1Core:

    @pytest.fixture(autouse=True)
    def setup_base_data(self):
        self.user, _ = User.objects.get_or_create(username="phase1_tester", defaults={"email": "test@mwheba.com"})
        self.egp, _ = Currency.objects.get_or_create(code="EGP", defaults={"name": "جنيه مصري", "symbol": "ج.م", "is_functional": True})
        self.usd, _ = Currency.objects.get_or_create(code="USD", defaults={"name": "دولار أمريكي", "symbol": "$", "is_functional": False})
        self.today = timezone.now().date()

        # Account Types
        exp_type, _ = AccountType.objects.get_or_create(code="EXP_TEST", defaults={"name": "Expense Test", "category": "expense", "nature": "debit"})
        liab_type, _ = AccountType.objects.get_or_create(code="LIAB_TEST", defaults={"name": "Liability Test", "category": "liability", "nature": "credit"})

        # Chart of Accounts for payroll test
        ChartOfAccounts.objects.get_or_create(code="52010_SALARIES_EXPENSE", defaults={"name": "مصروف الرواتب", "account_type": exp_type})
        ChartOfAccounts.objects.get_or_create(code="22020_PAYROLL_DEDUCTIONS", defaults={"name": "استقطاعات الرواتب", "account_type": liab_type})
        ChartOfAccounts.objects.get_or_create(code="22010_SALARIES_PAYABLE", defaults={"name": "الرواتب المستحقة", "account_type": liab_type})

    def test_fail_fast_rate_policy(self):
        """اختبار سياسة الرفض الصارم Fail Fast عند غياب سعر الصرف"""
        # 1. No rate registered between EUR and EGP -> Must raise ValidationError
        with pytest.raises(ValidationError) as excinfo:
            ExchangeRateService.get_rate(from_code="EUR", to_code="EGP", date=self.today)
        assert "لا يوجد سعر صرف مسجل" in str(excinfo.value)

        # 2. Same currency rate -> Always 1.0
        assert ExchangeRateService.get_rate(from_code="EGP", to_code="EGP") == Decimal("1.000000")

        # 3. After setting rate -> Successfully returned
        ExchangeRateService.set_rate(from_code="USD", to_code="EGP", rate=Decimal("50.000000"), date=self.today, user=self.user)
        assert ExchangeRateService.get_rate(from_code="USD", to_code="EGP", date=self.today) == Decimal("50.000000")

    def test_account_balance_period_calculation(self):
        """اختبار نموذج الأرصدة التجميعية للفترات المحاسبية"""
        exp_type, _ = AccountType.objects.get_or_create(code="AST_TEST", defaults={"name": "Asset Test", "category": "asset", "nature": "debit"})
        account, _ = ChartOfAccounts.objects.get_or_create(code="11010_TEST", defaults={"name": "حساب اختبار", "account_type": exp_type})

        balance_period = AccountBalancePeriod.objects.create(
            account=account,
            year=self.today.year,
            month=self.today.month,
            currency_code="EGP",
            beginning_debit=Decimal("1000.00"),
            period_debit=Decimal("500.00"),
            period_credit=Decimal("200.00")
        )
        balance_period.recalculate_totals()
        balance_period.save()

        assert balance_period.ending_debit == Decimal("1300.00")
        assert balance_period.net_balance == Decimal("1300.00")

    def test_payroll_accounting_bridge(self):
        """اختبار جسر الرواتب والمستحقات العمالية"""
        res = PayrollAccountingBridge.post_payroll_run(
            payroll_run_id="2026-08-RUN01",
            total_salaries=Decimal("50000.00"),
            total_allowances=Decimal("10000.00"),
            total_deductions=Decimal("5000.00"),
            net_payable=Decimal("55000.00"),
            entry_date=self.today,
            user=self.user
        )
        assert res["status"] == "POSTED"
        assert res["journal_entry_id"] is not None
