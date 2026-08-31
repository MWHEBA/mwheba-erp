"""
اختبارات العروض الشاملة للمبيعات (بدون تخطي وإصلاح كافة الاستدعاءات)
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal

from sale.models import Sale, SaleItem
from customer.models import Customer
from product.models import Product, Category, Unit, Warehouse

User = get_user_model()


class SaleViewsTestCase(TestCase):
    """الفئة الأساسية لاختبارات عروض المبيعات"""
    
    def setUp(self):
        self.client = Client()
        
        self.user = User.objects.create_user(
            username='testuser_views',
            password='testpass123',
            email='views@example.com'
        )
        self.client.login(username='testuser_views', password='testpass123')
        
        self.customer = Customer.objects.create(
            name='عميل اختبار العروض',
            code='CUST_VIEWS_01',
            phone='01234567890',
            email='customer_views@test.com'
        )
        
        self.warehouse = Warehouse.objects.create(
            name='المخزن الرئيسي',
            code='WH_VIEWS_01'
        )
        
        self.category = Category.objects.create(
            name='فئة اختبار'
        )
        
        self.unit = Unit.objects.create(
            name='قطعة',
            symbol='قطعة'
        )
        
        self.product = Product.objects.create(
            name='منتج اختبار',
            sku='PROD_VIEWS_01',
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('50.00'),
            selling_price=Decimal('100.00'),
            created_by=self.user
        )
        
        self.sale = Sale.objects.create(
            number='SAL_VIEWS_001',
            date=timezone.now().date(),
            customer=self.customer,
            warehouse=self.warehouse,
            subtotal=Decimal('1000.00'),
            discount=Decimal('0.00'),
            tax=Decimal('0.00'),
            total=Decimal('1000.00'),
            payment_method='cash',
            payment_status='unpaid',
            status='draft',
            created_by=self.user
        )


class SaleListViewTest(SaleViewsTestCase):
    """اختبارات عرض قائمة المبيعات"""
    
    def test_sale_list_view_accessible(self):
        """اختبار إمكانية الوصول لقائمة المبيعات"""
        url = reverse('sale:sale_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.sale.number)


class SaleCreateViewTest(SaleViewsTestCase):
    """اختبارات عرض إنشاء فاتورة مبيعات"""
    
    def test_sale_create_view_accessible(self):
        """اختبار الوصول لصفحة إنشاء فاتورة"""
        url = reverse('sale:sale_create')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class SaleDetailViewTest(SaleViewsTestCase):
    """اختبارات عرض تفاصيل فاتورة المبيعات"""
    
    def test_sale_detail_view_accessible(self):
        """اختبار الوصول لصفحة تفاصيل الفاتورة"""
        url = reverse('sale:sale_detail', kwargs={'pk': self.sale.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.sale.number)
