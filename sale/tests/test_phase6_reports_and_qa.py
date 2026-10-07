import pytest
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import Sum, Q

from product.models import Product, Warehouse, Stock, Category, Unit
from customer.models import Customer
from customer.services import CustomerService
from sale.models import Sale, SaleItem, SaleReturn, SaleReturnItem
from sale.services.sale_service import SaleService
from financial.models import AccountType, AccountingPeriod, ChartOfAccounts
from core.models import SystemSetting

User = get_user_model()


@pytest.mark.django_db
class TestPhase6ReportsAndQA(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="phase6_admin",
            email="admin@phase6.com",
            password="password123"
        )
        self.client = Client()
        self.client.force_login(self.user)

        # إعدادات النظام الأساسية
        SystemSetting.objects.update_or_create(key="enable_quotations", defaults={"value": "true"})
        SystemSetting.objects.update_or_create(key="AUTO_CREATE_CUSTOMER_ACCOUNTS", defaults={"value": "true"})

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
        ChartOfAccounts.objects.get_or_create(code='10300', defaults={'name': 'حسابات العملاء', 'account_type': asset_type, 'is_active': True})
        ChartOfAccounts.objects.get_or_create(code='11210', defaults={'name': 'حسابات العملاء', 'account_type': asset_type, 'is_active': True})
        ChartOfAccounts.objects.get_or_create(code='11310', defaults={'name': 'المخزون', 'account_type': asset_type, 'is_active': True})
        ChartOfAccounts.objects.get_or_create(code='41100', defaults={'name': 'إيرادات المبيعات', 'account_type': revenue_type, 'is_active': True})
        ChartOfAccounts.objects.get_or_create(code='51100', defaults={'name': 'تكلفة البضاعة المباعة', 'account_type': expense_type, 'is_active': True})

        # إنشاء 3 مخازن
        self.wh_alex = Warehouse.objects.create(name="مخزن الإسكندرية", is_active=True)
        self.wh_cairo = Warehouse.objects.create(name="مخزن القاهرة", is_active=True)
        self.wh_tanta = Warehouse.objects.create(name="مخزن طنطا", is_active=True)

        self.category = Category.objects.create(name="تصنيف عام")
        self.unit = Unit.objects.create(name="قطعة", symbol="PCS")

        self.prod_a = Product.objects.create(
            name="منتج أ",
            sku="P6-A",
            unit=self.unit,
            selling_price=Decimal("100.00"),
            cost_price=Decimal("60.00"),
            category=self.category,
            is_service=False,
            is_active=True,
            created_by=self.user,
        )
        self.prod_b = Product.objects.create(
            name="منتج ب",
            sku="P6-B",
            unit=self.unit,
            selling_price=Decimal("200.00"),
            cost_price=Decimal("120.00"),
            category=self.category,
            is_service=False,
            is_active=True,
            created_by=self.user,
        )
        self.prod_c = Product.objects.create(
            name="منتج ج",
            sku="P6-C",
            unit=self.unit,
            selling_price=Decimal("300.00"),
            cost_price=Decimal("180.00"),
            category=self.category,
            is_service=False,
            is_active=True,
            created_by=self.user,
        )

        Stock.objects.create(product=self.prod_a, warehouse=self.wh_alex, quantity=Decimal("100.00"), average_cost=Decimal("60.00"))
        Stock.objects.create(product=self.prod_b, warehouse=self.wh_cairo, quantity=Decimal("100.00"), average_cost=Decimal("120.00"))
        Stock.objects.create(product=self.prod_c, warehouse=self.wh_tanta, quantity=Decimal("100.00"), average_cost=Decimal("180.00"))

        customer_service = CustomerService()
        self.customer = customer_service.create_customer(
            name="عميل تقارير المرحلة 6", code="CUST-P6", phone="0123456789", user=self.user
        )

    def test_sale_list_filtering_by_line_warehouses(self):
        """
        اختبار فلترة قائمة الفواتير بالمخزن:
        فاتورة تحتوي على أصناف من (الإسكندرية + القاهرة) فقط،
        يجب أن تظهر عند الفلترة بمخزن الإسكندرية أو مخزن القاهرة،
        ويجب ألا تظهر عند الفلترة بمخزن طنطا.
        """
        sale_data = {
            "date": timezone.now().date(),
            "customer_id": self.customer.id,
            "payment_method": "credit",
            "items": [
                {
                    "product_id": self.prod_a.id,
                    "warehouse_id": self.wh_alex.id,
                    "quantity": Decimal("2.00"),
                    "unit_price": Decimal("100.00"),
                },
                {
                    "product_id": self.prod_b.id,
                    "warehouse_id": self.wh_cairo.id,
                    "quantity": Decimal("3.00"),
                    "unit_price": Decimal("200.00"),
                }
            ]
        }
        sale = SaleService.create_sale(data=sale_data, user=self.user)

        # 1. الفلترة بمخزن الإسكندرية -> يجب ظهور الفاتورة
        url_alex = f"{reverse('sale:sale_list')}?warehouse={self.wh_alex.id}"
        resp_alex = self.client.get(url_alex)
        self.assertEqual(resp_alex.status_code, 200)
        self.assertContains(resp_alex, sale.number)

        # 2. الفلترة بمخزن القاهرة -> يجب ظهور الفاتورة
        url_cairo = f"{reverse('sale:sale_list')}?warehouse={self.wh_cairo.id}"
        resp_cairo = self.client.get(url_cairo)
        self.assertEqual(resp_cairo.status_code, 200)
        self.assertContains(resp_cairo, sale.number)

        # 3. الفلترة بمخزن طنطا -> يجب ألا تظهر الفاتورة
        url_tanta = f"{reverse('sale:sale_list')}?warehouse={self.wh_tanta.id}"
        resp_tanta = self.client.get(url_tanta)
        self.assertEqual(resp_tanta.status_code, 200)
        self.assertNotContains(resp_tanta, sale.number)

    def test_line_level_warehouse_reporting_and_aggregations(self):
        """
        اختبار صحة استعلامات وتقارير المبيعات حسب المخزن على مستوى البنود
        """
        sale_data = {
            "date": timezone.now().date(),
            "customer_id": self.customer.id,
            "payment_method": "credit",
            "items": [
                {
                    "product_id": self.prod_a.id,
                    "warehouse_id": self.wh_alex.id,
                    "quantity": Decimal("10.00"),
                    "unit_price": Decimal("100.00"),
                },
                {
                    "product_id": self.prod_b.id,
                    "warehouse_id": self.wh_cairo.id,
                    "quantity": Decimal("5.00"),
                    "unit_price": Decimal("200.00"),
                }
            ]
        }
        SaleService.create_sale(data=sale_data, user=self.user)

        # إجمالي كمية وقيمة مبيعات مخزن الإسكندرية
        alex_sales = SaleItem.objects.filter(warehouse=self.wh_alex).aggregate(
            total_qty=Sum('quantity'),
            total_revenue=Sum('total')
        )
        self.assertEqual(alex_sales['total_qty'], Decimal("10.00"))
        self.assertEqual(alex_sales['total_revenue'], Decimal("1000.00"))

        # إجمالي كمية وقيمة مبيعات مخزن القاهرة
        cairo_sales = SaleItem.objects.filter(warehouse=self.wh_cairo).aggregate(
            total_qty=Sum('quantity'),
            total_revenue=Sum('total')
        )
        self.assertEqual(cairo_sales['total_qty'], Decimal("5.00"))
        self.assertEqual(cairo_sales['total_revenue'], Decimal("1000.00"))

        # مخزن طنطا لم تتم عليه أي مبيعات
        tanta_sales = SaleItem.objects.filter(warehouse=self.wh_tanta).aggregate(
            total_qty=Sum('quantity'),
            total_revenue=Sum('total')
        )
        self.assertIsNone(tanta_sales['total_qty'])
        self.assertIsNone(tanta_sales['total_revenue'])
