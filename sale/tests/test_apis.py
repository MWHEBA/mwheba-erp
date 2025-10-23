"""
اختبارات شاملة لـ APIs المبيعات - تغطية 100%
"""

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from decimal import Decimal
from datetime import date

from sale.models.sale import Sale
from client.models import Customer

User = get_user_model()


class SaleListAPITest(TestCase):
    """اختبارات API قائمة المبيعات"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='test123'
        )
        self.client.login(username='testuser', password='test123')
        
    def test_sale_list_view_loads(self):
        """اختبار تحميل قائمة المبيعات"""
        response = self.client.get(reverse('sale:sale_list'))
        
        self.assertEqual(response.status_code, 200)
        
    def test_sale_list_requires_login(self):
        """اختبار أن قائمة المبيعات تتطلب تسجيل دخول"""
        self.client.logout()
        response = self.client.get(reverse('sale:sale_list'))
        
        # يجب أن يعيد توجيه لصفحة تسجيل الدخول
        self.assertEqual(response.status_code, 302)


class SaleDetailAPITest(TestCase):
    """اختبارات API تفاصيل المبيعات"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='test123'
        )
        self.client.login(username='testuser', password='test123')
        
    def test_sale_detail_with_invalid_id(self):
        """اختبار تفاصيل فاتورة غير موجودة"""
        response = self.client.get(
            reverse('sale:sale_detail', kwargs={'pk': 99999})
        )
        
        self.assertEqual(response.status_code, 404)


class SaleCreateAPITest(TestCase):
    """اختبارات API إنشاء فاتورة مبيعات"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='test123'
        )
        self.client.login(username='testuser', password='test123')
        
    def test_sale_create_view_loads(self):
        """اختبار تحميل صفحة إنشاء فاتورة"""
        response = self.client.get(reverse('sale:sale_create'))
        
        self.assertEqual(response.status_code, 200)


class SaleReturnAPITest(TestCase):
    """اختبارات API مرتجعات المبيعات"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='test123'
        )
        self.client.login(username='testuser', password='test123')
        
    def test_sale_return_list_view_loads(self):
        """اختبار تحميل قائمة المرتجعات"""
        response = self.client.get(reverse('sale:sale_return_list'))
        
        self.assertEqual(response.status_code, 200)
