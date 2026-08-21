"""
FIN-CORE-PHASE2: Master Test Suite for Phase 2 Enterprise Multi-Currency Workflows
مصفوفة الاختبارات التلقائية لـ Phase 2 (FX Revaluation Engine IAS 21 & Landed Cost Allocation Engine IAS 2)
"""

import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from financial.models.currency import Currency, ExchangeRate
from financial.services.exchange_rate_service import ExchangeRateService
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.services.fx_revaluation_service import FXRevaluationService
from purchase.services.landed_cost_allocation_service import LandedCostAllocationService
from purchase.models.procurement_models import GoodsReceivedNote, GoodsReceivedNoteItem, PurchaseOrder, PurchaseOrderItem
from supplier.models import Supplier
from product.models.product_core import Product, Category, Unit
from product.models.stock_management import Warehouse

User = get_user_model()


@pytest.mark.django_db
class TestMasterPhase2Workflows:

    @pytest.fixture(autouse=True)
    def setup_base_data(self):
        self.user, _ = User.objects.get_or_create(username="phase2_tester", defaults={"email": "test2@mwheba.com"})
        self.egp, _ = Currency.objects.get_or_create(code="EGP", defaults={"name": "جنيه مصري", "symbol": "ج.م", "is_functional": True})
        self.usd, _ = Currency.objects.get_or_create(code="USD", defaults={"name": "دولار أمريكي", "symbol": "$", "is_functional": False})
        self.today = timezone.now().date()

        # Account Types
        ast_type, _ = AccountType.objects.get_or_create(code="AST_TEST2", defaults={"name": "Asset Test", "category": "asset", "nature": "debit"})
        liab_type, _ = AccountType.objects.get_or_create(code="LIAB_TEST2", defaults={"name": "Liability Test", "category": "liability", "nature": "credit"})
        rev_type, _ = AccountType.objects.get_or_create(code="REV_TEST2", defaults={"name": "Revenue Test", "category": "revenue", "nature": "credit"})

        # Chart of Accounts for tests
        ChartOfAccounts.objects.get_or_create(code="11010_AR", defaults={"name": "حساب العملاء", "account_type": ast_type})
        ChartOfAccounts.objects.get_or_create(code="11040_INVENTORY", defaults={"name": "حساب المخزون", "account_type": ast_type})
        ChartOfAccounts.objects.get_or_create(code="20160_LANDED_COST_CLEARING", defaults={"name": "حساب تسوية المصاريف المضافة", "account_type": liab_type})
        ChartOfAccounts.objects.get_or_create(code="71020_UNREALIZED_FX_GAIN_LOSS", defaults={"name": "حساب فروق تقييم غير محققة", "account_type": rev_type})

        # Base Master Entities
        self.unit, _ = Unit.objects.get_or_create(name="قطعة")
        self.category, _ = Category.objects.get_or_create(name="تصنيف المشتريات التجريبي")
        self.supplier, _ = Supplier.objects.get_or_create(name="شركة التوريدات الدولية التجريبية", defaults={"code": "SUP-PHASE2-99"})
        self.warehouse, _ = Warehouse.objects.get_or_create(name="المخزن الرئيسي", defaults={"code": "WH0001"})
        self.product, _ = Product.objects.get_or_create(
            name="منتج تجريبي أجنبي",
            category=self.category,
            unit=self.unit,
            created_by=self.user,
            defaults={"sku": "PROD-FX-999", "cost_price": Decimal("10.00"), "selling_price": Decimal("15.00")}
        )

        # Purchase Order
        self.po, _ = PurchaseOrder.objects.get_or_create(
            order_number="PO-PHASE2-001",
            defaults={
                "supplier": self.supplier,
                "warehouse": self.warehouse,
                "order_date": self.today,
                "created_by": self.user
            }
        )
        self.po_item, _ = PurchaseOrderItem.objects.get_or_create(
            purchase_order=self.po,
            product=self.product,
            defaults={
                "ordered_qty": Decimal("100.0000"),
                "unit_price": Decimal("10.0000"),
                "total_price": Decimal("1000.00")
            }
        )

    def test_fx_revaluation_calculation_and_posting(self):
        """اختبار محرك حساب وإعادة التقييم الدوري لفروق أسعار الصرف غير المحققة (IAS 21)"""
        # Set spot rate for USD
        ExchangeRateService.set_rate(from_code="USD", to_code="EGP", rate=Decimal("50.000000"), date=self.today, user=self.user)

        # Execute calculation
        res = FXRevaluationService.calculate_open_items_revaluation(as_of_date=self.today)
        assert res["functional_currency"] == "EGP"
        assert "customer_items" in res

    def test_landed_cost_allocation_engine(self):
        """اختبار محرك توزيع المصاريف المضافة على طبقات المخزون (IAS 2)"""
        grn = GoodsReceivedNote.objects.create(
            grn_number="GRN-2026-TEST01",
            supplier=self.supplier,
            warehouse=self.warehouse,
            purchase_order=self.po,
            currency="USD",
            exchange_rate=Decimal("50.000000")
        )
        item = GoodsReceivedNoteItem.objects.create(
            grn=grn,
            po_item=self.po_item,
            product=self.product,
            received_qty=Decimal("100.0000"),
            unit_price=Decimal("10.0000"),
            total_cost=Decimal("1000.00")
        )

        res = LandedCostAllocationService.allocate_landed_costs(
            grn_id=grn.id,
            freight_amount=Decimal("5000.00"),
            customs_amount=Decimal("3000.00"),
            other_fees=Decimal("2000.00"),
            allocation_method="VALUE",
            user=self.user
        )

        assert res["status"] == "POSTED"
        assert res["total_landed_cost"] == Decimal("10000.00")
        assert res["journal_entry_id"] is not None
        assert res["allocations"][0]["final_unit_cost"] == Decimal("110.0000")
