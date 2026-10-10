"""
Multi-Warehouse Sales Views Tests - Phase 4
اختبارات إنشاء وتعديل فواتير مبيعات متعددة المخازن على مستوى البنود عبر الـ Views
"""
import pytest
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from sale.models import Sale, SaleItem
from customer.models import Customer
from customer.services import CustomerService
from product.models import Category, Unit, Product, Warehouse, Stock
from financial.models import AccountType, AccountingPeriod, ChartOfAccounts

User = get_user_model()


class MultiWarehouseSalesViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_superuser(
            username="test_wh_views_admin", password="password123", email="admin@mwheba.test"
        )
        self.client.login(username="test_wh_views_admin", password="password123")

        # إعداد الحسابات المالية اللازمة
        current_year = timezone.now().year
        AccountingPeriod.objects.get_or_create(
            start_date=timezone.datetime(current_year, 1, 1).date(),
            end_date=timezone.datetime(current_year, 12, 31).date(),
            defaults={'name': f'السنة المالية {current_year}', 'status': 'open'}
        )

        cash_type, _ = AccountType.objects.get_or_create(code='CASH', defaults={'name': 'نقدية', 'nature': 'debit'})
        asset_type, _ = AccountType.objects.get_or_create(code='ASSET', defaults={'name': 'أصول', 'nature': 'debit'})
        revenue_type, _ = AccountType.objects.get_or_create(code='REVENUE', defaults={'name': 'إيرادات', 'nature': 'credit'})
        expense_type, _ = AccountType.objects.get_or_create(code='EXPENSE', defaults={'name': 'مصروفات', 'nature': 'debit'})

        ChartOfAccounts.objects.get_or_create(code='11110', defaults={'name': 'الخزينة', 'account_type': cash_type, 'is_active': True})
        ChartOfAccounts.objects.get_or_create(code='11210', defaults={'name': 'حسابات العملاء', 'account_type': asset_type, 'is_active': True})
        ChartOfAccounts.objects.get_or_create(code='11310', defaults={'name': 'المخزون', 'account_type': asset_type, 'is_active': True})
        ChartOfAccounts.objects.get_or_create(code='41100', defaults={'name': 'إيرادات المبيعات', 'account_type': revenue_type, 'is_active': True})
        ChartOfAccounts.objects.get_or_create(code='51100', defaults={'name': 'تكلفة البضاعة المباعة', 'account_type': expense_type, 'is_active': True})

        customer_service = CustomerService()
        self.customer = customer_service.create_customer(
            name="عميل اختبار المخازن", code="CUST_WH_01", phone="01011112222", user=self.user
        )

        self.wh_elec = Warehouse.objects.create(name="مخزن الإلكترونيات", code="WH_ELEC", is_active=True)
        self.wh_acc = Warehouse.objects.create(name="مخزن الإكسسوارات", code="WH_ACC", is_active=True)

        self.cat = Category.objects.create(name="إلكترونيات")
        self.unit = Unit.objects.create(name="قطعة", symbol="قطعة")

        self.prod_tv = Product.objects.create(
            name="شاشة سامسونج",
            sku="SAM_TV_55",
            category=self.cat,
            unit=self.unit,
            cost_price=Decimal("10000.00"),
            selling_price=Decimal("15000.00"),
            created_by=self.user,
        )
        self.prod_cable = Product.objects.create(
            name="كابل HDMI",
            sku="HDMI_CABLE",
            category=self.cat,
            unit=self.unit,
            cost_price=Decimal("50.00"),
            selling_price=Decimal("100.00"),
            created_by=self.user,
        )

        Stock.objects.create(
            product=self.prod_tv,
            warehouse=self.wh_elec,
            quantity=Decimal("20.00"),
            average_cost=Decimal("10000.00"),
        )
        Stock.objects.create(
            product=self.prod_cable,
            warehouse=self.wh_acc,
            quantity=Decimal("100.00"),
            average_cost=Decimal("50.00"),
        )

    def test_sale_create_get_contains_warehouses_data(self):
        """التحقق من أن صفحة إنشاء الفاتورة تحتوي على بيانات المخازن للواجهة"""
        url = reverse("sale:sale_create")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("warehouses", response.context)
        self.assertContains(response, "warehouses-data-json")

    def test_sale_create_post_with_line_level_warehouses(self):
        """إنشاء فاتورة مبيعات ببندين من مخزنين مختلفين بدون اختيار مخزن رئيسي في الهيدر"""
        url = reverse("sale:sale_create")
        post_data = {
            "date": timezone.now().date().strftime("%Y-%m-%d"),
            "customer": self.customer.id,
            "invoice_type": "credit",
            "currency": "",
            "exchange_rate": "1.0",
            "discount": "0",
            "discount_type": "fixed",
            "adjustment_amount": "0",
            "adjustment_type": "add",
            "tax": "0",
            "product[]": [str(self.prod_tv.id), str(self.prod_cable.id)],
            "warehouse[]": [str(self.wh_elec.id), str(self.wh_acc.id)],
            "quantity[]": ["2", "5"],
            "unit_price[]": ["15000.00", "100.00"],
            "discount[]": ["0", "0"],
        }

        response = self.client.post(url, post_data)
        self.assertEqual(response.status_code, 302)

        sale = Sale.objects.order_by("-id").first()
        self.assertIsNotNone(sale)
        self.assertEqual(sale.customer_id, self.customer.id)

        items = list(sale.items.order_by("id"))
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].product_id, self.prod_tv.id)
        self.assertEqual(items[0].warehouse_id, self.wh_elec.id)
        self.assertEqual(items[0].quantity, Decimal("2"))

        self.assertEqual(items[1].product_id, self.prod_cable.id)
        self.assertEqual(items[1].warehouse_id, self.wh_acc.id)
        self.assertEqual(items[1].quantity, Decimal("5"))

        # التحقق من خصم المخزون بدقة من كل مخزن
        stock_tv = Stock.objects.get(product=self.prod_tv, warehouse=self.wh_elec)
        stock_cable = Stock.objects.get(product=self.prod_cable, warehouse=self.wh_acc)
        self.assertEqual(stock_tv.quantity, Decimal("18.00"))
        self.assertEqual(stock_cable.quantity, Decimal("95.00"))

    def test_invoice_product_lookup_returns_products_with_warehouse_stocks(self):
        """التحقق من أن استعلام المنتجات يُرجع المنتجات الأساسية وتفاصيل أرصدة المخازن بدقة"""
        url = reverse("product:invoice_product_lookup")
        response = self.client.get(f"{url}?product_ids={self.prod_tv.id},{self.prod_cable.id}&show_all=true")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("products", data)
        self.assertEqual(len(data["products"]), 2)

        tv_data = next((p for p in data["products"] if p["id"] == self.prod_tv.id), None)
        self.assertIsNotNone(tv_data)
        self.assertIn("warehouse_stocks", tv_data)
        self.assertTrue(len(tv_data["warehouse_stocks"]) >= 2)
        
        # التأكد من رصيد الشاشة في مخزن الإلكترونيات
        wh_elec_stock = next((w for w in tv_data["warehouse_stocks"] if w["warehouse_id"] == self.wh_elec.id), None)
        self.assertIsNotNone(wh_elec_stock)
        self.assertEqual(wh_elec_stock["available_quantity"], 20.0)

        # التأكد من خاصية stock على مستوى Product
        self.assertEqual(self.prod_tv.stock, Decimal("20.00"))
        self.assertEqual(self.prod_cable.stock, Decimal("100.00"))

    def test_sale_edit_get_contains_id_warehouse(self):
        """التحقق من أن صفحة تعديل الفاتورة تشتمل على حقل id_warehouse لضمان قراءة الواجهة للمخزن"""
        # إنشاء فاتورة تجريبية أولاً
        sale = Sale.objects.create(
            number="SL-TEST-WH",
            customer=self.customer,
            date=timezone.now().date(),
            warehouse=self.wh_elec,
            payment_method="credit",
            payment_status="unpaid",
            status="draft",
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
            created_by=self.user,
        )
        url = reverse("sale:sale_edit", kwargs={"pk": sale.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="id_warehouse"')
