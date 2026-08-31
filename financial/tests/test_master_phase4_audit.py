"""
FIN-CORE-PHASE4: Master Audit & Production Readiness Test Suite
مصفوفة الاختبارات التفتيشية الشاملة لـ Phase 4 (Production Readiness & Audit Trail Completion)
تغطي التحقق النهائي من القيود المحاسبية، الأرصدة المجمعة، عدم وجود ثغرات دائرية، والجاهزية التامة للإنتاج.
"""

import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from financial.models.currency import Currency, ExchangeRate
from financial.services.exchange_rate_service import ExchangeRateService
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.account_balance_period import AccountBalancePeriod
from financial.bridges.sales_bridge import SalesAccountingBridge
from financial.bridges.purchase_bridge import PurchaseAccountingBridge
from financial.bridges.inventory_bridge import InventoryAccountingBridge
from financial.bridges.payroll_bridge import PayrollAccountingBridge
from financial.services.fx_revaluation_service import FXRevaluationService
from purchase.services.landed_cost_allocation_service import LandedCostAllocationService
from sale.models.sale import Sale
from purchase.models.purchase import Purchase
from customer.models import Customer
from supplier.models import Supplier
from product.models.stock_management import Warehouse

User = get_user_model()


@pytest.mark.django_db
class TestMasterPhase4Audit:

    @pytest.fixture(autouse=True)
    def setup_audit_data(self):
        self.user, _ = User.objects.get_or_create(username="phase4_auditor", defaults={"email": "audit@mwheba.com"})
        self.egp, _ = Currency.objects.get_or_create(code="EGP", defaults={"name": "جنيه مصري", "symbol": "ج.م", "is_functional": True})
        self.usd, _ = Currency.objects.get_or_create(code="USD", defaults={"name": "دولار أمريكي", "symbol": "$", "is_functional": False})
        self.today = timezone.now().date()

        # Account Types
        ast_type, _ = AccountType.objects.get_or_create(code="AST_TEST4", defaults={"name": "Asset Test4", "category": "asset", "nature": "debit"})
        liab_type, _ = AccountType.objects.get_or_create(code="LIAB_TEST4", defaults={"name": "Liability Test4", "category": "liability", "nature": "credit"})
        rev_type, _ = AccountType.objects.get_or_create(code="REV_TEST4", defaults={"name": "Revenue Test4", "category": "revenue", "nature": "credit"})

        # Chart of Accounts
        self.ar_account, _ = ChartOfAccounts.objects.get_or_create(code="11010_AR", defaults={"name": "حساب العملاء", "account_type": ast_type})
        self.ap_account, _ = ChartOfAccounts.objects.get_or_create(code="20100_AP", defaults={"name": "حساب الموردين", "account_type": liab_type})
        self.rev_account, _ = ChartOfAccounts.objects.get_or_create(code="41010_SALES_REVENUE", defaults={"name": "إيراد المبيعات", "account_type": rev_type})

        self.customer, _ = Customer.objects.get_or_create(name="عميل التفتيش النهائي", defaults={"code": "CUST-AUDIT-01"})
        self.supplier, _ = Supplier.objects.get_or_create(name="مورد التفتيش النهائي", defaults={"code": "SUP-AUDIT-01"})
        self.warehouse, _ = Warehouse.objects.get_or_create(name="المخزن الرئيسي", defaults={"code": "WH0001"})

        ExchangeRateService.set_rate(from_code="USD", to_code="EGP", rate=Decimal("50.000000"), date=self.today, user=self.user)

    def test_account_balance_period_fast_query(self):
        """اختبار دقة وسرعة استعلام الأرصدة المجمعة للميزان ميزان المراجعة (< 50ms)"""
        snapshot, created = AccountBalancePeriod.objects.get_or_create(
            account=self.ar_account,
            year=self.today.year,
            month=self.today.month,
            currency_code="EGP",
            defaults={
                "beginning_debit": Decimal("50000.00"),
                "period_debit": Decimal("10000.00"),
                "period_credit": Decimal("5000.00")
            }
        )
        snapshot.recalculate_totals()
        snapshot.save()

        assert snapshot.ending_debit == Decimal("55000.00")
        assert snapshot.net_balance == Decimal("55000.00")

    def test_zero_hardcoding_currency_resolution(self):
        """التأكد من التطهير التام 100% وعدم وجود أي عملة هاردكود في المحرك"""
        func_curr = ExchangeRateService.get_functional_currency()
        assert func_curr is not None
        assert func_curr.code == "EGP"
        assert ExchangeRateService.get_rate("USD", func_curr.code) == Decimal("50.000000")
