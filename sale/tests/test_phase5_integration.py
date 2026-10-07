import pytest
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from product.models import Product, Warehouse, Stock, Category
from customer.models import Customer
from sale.models import Sale, SaleItem, SaleReturn, SaleReturnItem, Quotation, QuotationItem
from sale.services.sale_service import SaleService
from financial.models import ChartOfAccounts
from financial.services.role_registry import AccountRoleRegistry

User = get_user_model()


@pytest.mark.django_db
class TestPhase5Integration(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="phase5_admin",
            email="admin@phase5.com",
            password="password123"
        )
        self.client = Client()
        self.client.force_login(self.user)
        from core.models import SystemSetting
        SystemSetting.objects.update_or_create(key="enable_quotations", defaults={"value": "true"})
        SystemSetting.objects.update_or_create(key="AUTO_CREATE_CUSTOMER_ACCOUNTS", defaults={"value": "true"})

        self.category = Category.objects.create(name="Phase 5 Category")

        # إنشاء مخزنين منفصلين
        self.wh_alex = Warehouse.objects.create(name="مخزن الإسكندرية", is_active=True)
        self.wh_cairo = Warehouse.objects.create(name="مخزن القاهرة", is_active=True)

        from product.models import Unit
        self.unit = Unit.objects.create(name="قطعة", symbol="PCS")

        # إنشاء منتجين ماديين
        self.prod_a = Product.objects.create(
            name="منتج أ - إسكندرية",
            sku="PROD-ALX-01",
            unit=self.unit,
            selling_price=Decimal("100.00"),
            cost_price=Decimal("60.00"),
            category=self.category,
            is_service=False,
            is_active=True,
            created_by=self.user,
        )
        self.prod_b = Product.objects.create(
            name="منتج ب - قاهرة",
            sku="PROD-CAI-01",
            unit=self.unit,
            selling_price=Decimal("200.00"),
            cost_price=Decimal("120.00"),
            category=self.category,
            is_service=False,
            is_active=True,
            created_by=self.user,
        )

        # إضافة رصيد لكل منتج في مخزنه المخصص فقط
        Stock.objects.create(
            product=self.prod_a,
            warehouse=self.wh_alex,
            quantity=Decimal("50.00"),
            average_cost=Decimal("60.00")
        )
        Stock.objects.create(
            product=self.prod_b,
            warehouse=self.wh_cairo,
            quantity=Decimal("30.00"),
            average_cost=Decimal("120.00")
        )

        # إعداد الحسابات المالية اللازمة
        from financial.models import AccountType, AccountingPeriod
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
        ChartOfAccounts.objects.get_or_create(code='10300', defaults={'name': 'حسابات العملاء', 'account_type': asset_type, 'is_active': True})
        ChartOfAccounts.objects.get_or_create(code='11210', defaults={'name': 'حسابات العملاء', 'account_type': asset_type, 'is_active': True})
        ChartOfAccounts.objects.get_or_create(code='11310', defaults={'name': 'المخزون', 'account_type': asset_type, 'is_active': True})
        ChartOfAccounts.objects.get_or_create(code='41100', defaults={'name': 'إيرادات المبيعات', 'account_type': revenue_type, 'is_active': True})
        ChartOfAccounts.objects.get_or_create(code='51100', defaults={'name': 'تكلفة البضاعة المباعة', 'account_type': expense_type, 'is_active': True})

        from customer.services import CustomerService
        customer_service = CustomerService()
        self.customer = customer_service.create_customer(
            name="شركة الأمل للتجارة", code="CUST_PHASE5_01", phone="01011112222", user=self.user
        )

    def test_quotation_convert_to_multi_warehouse_sale(self):
        """
        اختبار تحويل عرض سعر يحتوي على منتجات من مخازن مختلفة إلى فاتورة مبيعات
        تخصص تلقائياً كل منتج لمخزنه الذي يتوفر فيه الرصيد
        """
        quotation = Quotation.objects.create(
            customer=self.customer,
            date=timezone.now().date(),
            status="approved",
            subtotal=Decimal("700.00"),
            total=Decimal("700.00"),
            tax=Decimal("0.00"),
            discount=Decimal("0.00"),
            created_by=self.user,
        )
        QuotationItem.objects.create(
            quotation=quotation,
            product=self.prod_a,
            quantity=Decimal("3.00"),
            unit_price=Decimal("100.00"),
            total=Decimal("300.00")
        )
        QuotationItem.objects.create(
            quotation=quotation,
            product=self.prod_b,
            quantity=Decimal("2.00"),
            unit_price=Decimal("200.00"),
            total=Decimal("400.00")
        )

        # التحويل عبر View مع اختيار 'auto' أو بدون مخزن محدد
        url = reverse("sale:quotation_convert_to_sale", kwargs={"pk": quotation.pk})
        response = self.client.post(url, {"warehouse": "auto"}, follow=True)

        self.assertEqual(response.status_code, 200)
        quotation.refresh_from_db()
        self.assertIsNotNone(quotation.converted_to_sale)

        sale = quotation.converted_to_sale
        items = list(sale.items.all().order_by("id"))
        self.assertEqual(len(items), 2)

        # التحقق من أن بند منتج أ تم تخصيصه لمخزن الإسكندرية
        item_a = items[0]
        self.assertEqual(item_a.product_id, self.prod_a.id)
        self.assertEqual(item_a.warehouse_id, self.wh_alex.id)

        # التحقق من أن بند منتج ب تم تخصيصه لمخزن القاهرة
        item_b = items[1]
        self.assertEqual(item_b.product_id, self.prod_b.id)
        self.assertEqual(item_b.warehouse_id, self.wh_cairo.id)

        # التحقق من خصم الأرصدة بدقة من كل مخزن
        stock_a = Stock.objects.get(product=self.prod_a, warehouse=self.wh_alex)
        self.assertEqual(stock_a.quantity, Decimal("47.00"))  # 50 - 3

        stock_b = Stock.objects.get(product=self.prod_b, warehouse=self.wh_cairo)
        self.assertEqual(stock_b.quantity, Decimal("28.00"))  # 30 - 2

    def test_multi_warehouse_sales_return_restores_stock_to_correct_warehouses(self):
        """
        اختبار إنشاء مرتجع مبيعات لفاتورة ذات أسطر من مخازن متعددة
        والتأكد من إرجاع كل منتج لمخزنه الأصلي وتسجيل بند المرتجع والمخزن بدقة
        """
        sale_data = {
            "date": timezone.now().date(),
            "customer_id": self.customer.id,
            "payment_method": "credit",
            "items": [
                {
                    "product_id": self.prod_a.id,
                    "warehouse_id": self.wh_alex.id,
                    "quantity": Decimal("5.00"),
                    "unit_price": Decimal("100.00"),
                    "discount": Decimal("0.00"),
                    "tax_rate": Decimal("0.00"),
                },
                {
                    "product_id": self.prod_b.id,
                    "warehouse_id": self.wh_cairo.id,
                    "quantity": Decimal("4.00"),
                    "unit_price": Decimal("200.00"),
                    "discount": Decimal("0.00"),
                    "tax_rate": Decimal("0.00"),
                }
            ]
        }
        sale = SaleService.create_sale(data=sale_data, user=self.user)

        # التحقق من الأرصدة بعد البيع
        self.assertEqual(Stock.objects.get(product=self.prod_a, warehouse=self.wh_alex).quantity, Decimal("45.00"))
        self.assertEqual(Stock.objects.get(product=self.prod_b, warehouse=self.wh_cairo).quantity, Decimal("26.00"))

        item_a = sale.items.get(product=self.prod_a)
        item_b = sale.items.get(product=self.prod_b)

        # إرجاع وحدتين من منتج أ ووحدة من منتج ب
        return_data = {
            "date": timezone.now().date(),
            "notes": "مرتجع تجريبي متعدد المخازن",
            "items": [
                {
                    "sale_item_id": item_a.id,
                    "quantity": Decimal("2.00"),
                    "unit_price": item_a.unit_price,
                },
                {
                    "sale_item_id": item_b.id,
                    "quantity": Decimal("1.00"),
                    "unit_price": item_b.unit_price,
                }
            ]
        }
        sale_return = SaleService.create_return(sale=sale, return_data=return_data, user=self.user)

        self.assertIsNotNone(sale_return)
        self.assertEqual(sale_return.status, "confirmed")

        # التحقق من بنود المرتجع وربط المخازن
        ret_items = list(sale_return.items.all().order_by("id"))
        self.assertEqual(len(ret_items), 2)
        self.assertEqual(ret_items[0].warehouse_id, self.wh_alex.id)
        self.assertEqual(ret_items[1].warehouse_id, self.wh_cairo.id)

        # التحقق من زيادة الأرصدة المخزنية في المخازن الصحيحة
        stock_a_after = Stock.objects.get(product=self.prod_a, warehouse=self.wh_alex)
        self.assertEqual(stock_a_after.quantity, Decimal("47.00"))  # 45 + 2

        stock_b_after = Stock.objects.get(product=self.prod_b, warehouse=self.wh_cairo)
        self.assertEqual(stock_b_after.quantity, Decimal("27.00"))  # 26 + 1

    def test_detail_and_print_views_render_cleanly(self):
        """
        اختبار عرض تفاصيل الفاتورة والمرتجع وصفحات الطباعة بدون أخطاء
        """
        sale_data = {
            "date": timezone.now().date(),
            "customer_id": self.customer.id,
            "payment_method": "credit",
            "items": [
                {
                    "product_id": self.prod_a.id,
                    "warehouse_id": self.wh_alex.id,
                    "quantity": Decimal("1.00"),
                    "unit_price": Decimal("100.00"),
                },
                {
                    "product_id": self.prod_b.id,
                    "warehouse_id": self.wh_cairo.id,
                    "quantity": Decimal("1.00"),
                    "unit_price": Decimal("200.00"),
                }
            ]
        }
        sale = SaleService.create_sale(data=sale_data, user=self.user)

        # صفحة تفاصيل الفاتورة
        detail_url = reverse("sale:sale_detail", kwargs={"pk": sale.pk})
        resp = self.client.get(detail_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "مخزن الإسكندرية")
        self.assertContains(resp, "مخزن القاهرة")

        # صفحة طباعة الفاتورة
        print_url = reverse("sale:sale_print", kwargs={"pk": sale.pk})
        resp_print = self.client.get(print_url)
        self.assertEqual(resp_print.status_code, 200)

        # إنشاء مرتجع وعرض تفاصيله
        item_a = sale.items.get(product=self.prod_a)
        return_data = {
            "date": timezone.now().date(),
            "items": [
                {
                    "sale_item_id": item_a.id,
                    "quantity": Decimal("1.00"),
                    "unit_price": item_a.unit_price,
                }
            ]
        }
        ret = SaleService.create_return(sale=sale, return_data=return_data, user=self.user)
        ret_url = reverse("sale:sale_return_detail", kwargs={"pk": ret.pk})
        resp_ret = self.client.get(ret_url)
        self.assertEqual(resp_ret.status_code, 200)
        self.assertContains(resp_ret, "مخزن الإسكندرية")
