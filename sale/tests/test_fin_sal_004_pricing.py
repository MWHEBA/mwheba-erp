import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone

from product.models.product_core import Product, Category, Unit
from customer.models import Customer
from sale.models.pricing import PriceList, PriceListItem, DiscountRule, PricingAuditLog
from sale.services.pricing_service import PricingService

User = get_user_model()


@pytest.mark.django_db(transaction=True)
class TestFINSAL004SalesPricingEngine:

    @pytest.fixture
    def setup_pricing_data(self):
        user = User.objects.create_user(username="price_user4_v2", password="password123")
        category = Category.objects.create(name="Electronics")
        unit = Unit.objects.create(name="PCS")

        product = Product.objects.create(
            name="Smart Display 10",
            category=category,
            unit=unit,
            cost_price=Decimal("400.00"),
            selling_price=Decimal("600.00"),
            created_by=user
        )
        customer = Customer.objects.create(
            name="VIP Tech Retail",
            code="CUST-PR-001",
            credit_limit=Decimal("50000.00")
        )

        price_list = PriceList.objects.create(name="Wholesale EGP", currency="EGP", is_active=True)
        PriceListItem.objects.create(price_list=price_list, product=product, unit_price=Decimal("520.00"), min_quantity=Decimal("1.0000"))
        PriceListItem.objects.create(price_list=price_list, product=product, unit_price=Decimal("490.00"), min_quantity=Decimal("10.0000"))

        DiscountRule.objects.create(
            rule_name="Bulk Electronics Discount",
            customer=customer,
            category=category,
            discount_percentage=Decimal("5.00"),
            min_order_amount=Decimal("1000.00"),
            priority=10
        )

        return user, product, customer, price_list

    def test_get_product_price_with_tier(self, setup_pricing_data):
        user, product, customer, price_list = setup_pricing_data

        p1 = PricingService.get_sales_price(product_id=product.id, customer_id=customer.id, quantity=Decimal("1.0000"), price_list_id=price_list.id)
        assert p1["base_price"] == Decimal("520.00")
        assert p1["discount_percentage"] == Decimal("5.00")
        assert p1["final_price"] == Decimal("494.00")

        p10 = PricingService.get_sales_price(product_id=product.id, customer_id=customer.id, quantity=Decimal("10.0000"), price_list_id=price_list.id)
        assert p10["base_price"] == Decimal("490.00")
        assert p10["discount_percentage"] == Decimal("5.00")

    def test_pricing_update_audit_log(self, setup_pricing_data):
        user, product, customer, price_list = setup_pricing_data

        audit = PricingService.update_product_price(
            product_id=product.id,
            new_price=Decimal("650.00"),
            user=user,
            reason="Market inflation adjustment"
        )

        assert audit.old_price == Decimal("600.00")
        assert audit.new_price == Decimal("650.00")
        assert audit.reason == "Market inflation adjustment"
        assert PricingAuditLog.objects.filter(product=product).count() == 1

    def test_product_specific_discount_rule_override(self, setup_pricing_data):
        user, product, customer, price_list = setup_pricing_data

        # إضافة قاعدة خصم خاصة بالمنتج نفسه بأولوية أعلى
        DiscountRule.objects.create(
            rule_name="Product Specific Super Discount",
            product=product,
            customer=customer,
            discount_percentage=Decimal("12.00"),
            priority=20
        )

        p = PricingService.get_sales_price(product_id=product.id, customer_id=customer.id, quantity=Decimal("1.0000"), price_list_id=price_list.id)
        assert p["discount_percentage"] == Decimal("12.00")
        assert p["rule_name"] == "Product Specific Super Discount"
        assert p["final_price"] == Decimal("457.60")

    def test_cart_evaluation_and_eta_vat(self, setup_pricing_data):
        user, product, customer, price_list = setup_pricing_data

        items = [
            {"product_id": product.id, "quantity": "2", "unit_id": product.unit_id}
        ]

        cart = PricingService.evaluate_cart_pricing(
            items=items,
            customer_id=customer.id,
            price_list_id=price_list.id,
            header_discount=Decimal("50.00"),
            header_discount_type="fixed",
            vat_active=True,
            vat_rate=Decimal("14.00")
        )

        # subtotal: 520 * 2 = 1040.00
        assert cart["subtotal"] == Decimal("1040.00")
        # line discount: 5% of 520 = 26 * 2 = 52.00
        assert cart["total_line_discounts"] == Decimal("52.00")
        # taxable base after line discount (988) and header discount (50): 938.00
        assert cart["taxable_base"] == Decimal("938.00")
        # VAT: 938 * 14% = 131.32
        assert cart["vat_amount"] == Decimal("131.32")
        # Total: 938 + 131.32 = 1069.32
        assert cart["total"] == Decimal("1069.32")

    def test_cost_floor_warning(self, setup_pricing_data):
        user, product, customer, price_list = setup_pricing_data

        # إنشاء قاعدة خصم ضخمة تجعل السعر أقل من سعر التكلفة (400)
        DiscountRule.objects.create(
            rule_name="Huge Discount Below Cost",
            product=product,
            discount_percentage=Decimal("50.00"),
            priority=50
        )

        p = PricingService.get_sales_price(product_id=product.id, quantity=Decimal("1.0000"))
        # Base: 600, 50% disc -> 300 < cost_price (400)
        assert p["final_price"] == Decimal("300.00")
        assert p["is_below_cost"] is True
