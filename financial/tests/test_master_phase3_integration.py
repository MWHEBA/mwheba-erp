"""
FIN-CORE-PHASE3: Master End-to-End System Integration Test Suite
مصفوفة الاختبارات التكاملية الشاملة لـ Phase 3 (End-to-End Cross-Module Workflows)
تغطي التدفق التكاملي الكامل من عروض الأسعار، فواتير المبيعات، المشتريات، الاستلامات، وإعادة التقييم.
"""

import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from financial.models.currency import Currency, ExchangeRate
from financial.services.exchange_rate_service import ExchangeRateService
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.bridges.sales_bridge import SalesAccountingBridge
from financial.bridges.purchase_bridge import PurchaseAccountingBridge
from financial.bridges.inventory_bridge import InventoryAccountingBridge
from financial.bridges.payroll_bridge import PayrollAccountingBridge
from financial.services.fx_revaluation_service import FXRevaluationService
from purchase.services.landed_cost_allocation_service import LandedCostAllocationService
from sale.models.sale import Sale
from purchase.models.purchase import Purchase
from client.models import Customer
from supplier.models import Supplier
from product.models.stock_management import Warehouse

User = get_user_model()


@pytest.mark.django_db
class TestMasterPhase3Integration:

    @pytest.fixture(autouse=True)
    def setup_integration_data(self):
        self.user, _ = User.objects.get_or_create(username="phase3_tester", defaults={"email": "test3@mwheba.com"})
        self.egp, _ = Currency.objects.get_or_create(code="EGP", defaults={"name": "جنيه مصري", "symbol": "ج.م", "is_functional": True})
        self.usd, _ = Currency.objects.get_or_create(code="USD", defaults={"name": "دولار أمريكي", "symbol": "$", "is_functional": False})
        self.today = timezone.now().date()

        # Account Types
        ast_type, _ = AccountType.objects.get_or_create(code="AST_TEST3", defaults={"name": "Asset Test3", "category": "asset", "nature": "debit"})
        liab_type, _ = AccountType.objects.get_or_create(code="LIAB_TEST3", defaults={"name": "Liability Test3", "category": "liability", "nature": "credit"})
        rev_type, _ = AccountType.objects.get_or_create(code="REV_TEST3", defaults={"name": "Revenue Test3", "category": "revenue", "nature": "credit"})

        # Chart of Accounts
        ChartOfAccounts.objects.get_or_create(code="11210", defaults={"name": "حساب العملاء", "account_type": ast_type})
        ChartOfAccounts.objects.get_or_create(code="21110", defaults={"name": "حساب الموردين", "account_type": liab_type})
        ChartOfAccounts.objects.get_or_create(code="41100", defaults={"name": "إيراد المبيعات", "account_type": rev_type})
        ChartOfAccounts.objects.get_or_create(code="21210", defaults={"name": "حساب الاستلامات غير المفوترة", "account_type": liab_type})
        ChartOfAccounts.objects.get_or_create(code="21310", defaults={"name": "ضريبة القيمة المضافة", "account_type": liab_type})

        # Entities
        self.customer, _ = Customer.objects.get_or_create(name="عميل تجريبي دولي", defaults={"code": "CUST-INT-99"})
        self.supplier, _ = Supplier.objects.get_or_create(name="مورد تجريبي دولي", defaults={"code": "SUP-INT-99"})
        self.warehouse, _ = Warehouse.objects.get_or_create(name="المخزن الرئيسي", defaults={"code": "WH0001"})

        # Spot rate
        ExchangeRateService.set_rate(from_code="USD", to_code="EGP", rate=Decimal("50.000000"), date=self.today, user=self.user)

    def test_e2e_sales_workflow_posting(self):
        """اختبار التكتل التكاملي لفاتورة مبيعات بالدولار والترحيل عبر الجسر المحاسبي"""
        sale = Sale.objects.create(
            number="INV-2026-USD01",
            customer=self.customer,
            warehouse=self.warehouse,
            date=self.today,
            currency=self.usd,
            exchange_rate=Decimal("50.000000"),
            subtotal=Decimal("1000.00"),
            discount=Decimal("0.00"),
            tax=Decimal("140.00"),
            total=Decimal("1140.00"),
            created_by=self.user
        )

        res = SalesAccountingBridge.post_sale_invoice(sale.id, user=self.user)
        assert res["status"] == "POSTED"
        assert res["journal_entry_id"] is not None

        sale.refresh_from_db()
        assert sale.journal_entry is not None
        assert sale.journal_entry.status == "posted"

    def test_e2e_purchase_workflow_posting(self):
        """اختبار التكتل التكاملي لفاتورة مشتريات بالدولار والترحيل عبر الجسر المحاسبي"""
        purchase = Purchase.objects.create(
            number="PINV-2026-USD01",
            supplier=self.supplier,
            warehouse=self.warehouse,
            date=self.today,
            currency=self.usd,
            exchange_rate=Decimal("50.000000"),
            subtotal=Decimal("2000.00"),
            discount=Decimal("0.00"),
            tax=Decimal("0.00"),
            total=Decimal("2000.00"),
            created_by=self.user
        )

        res = PurchaseAccountingBridge.post_purchase_invoice(purchase.id, user=self.user)
        assert res["status"] == "POSTED"
        assert res["journal_entry_id"] is not None

        purchase.refresh_from_db()
        assert purchase.journal_entry is not None
        assert purchase.journal_entry.status == "posted"
