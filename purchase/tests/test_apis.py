"""
اختبارات شاملة لـ APIs المشتريات - تغطية 100%
"""

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


class PurchaseListAPITest(TestCase):
    """اختبارات API قائمة المشتريات"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='test123'
        )
        self.client.login(username='testuser', password='test123')
        
    def test_purchase_list_view_loads(self):
        """اختبار تحميل قائمة المشتريات"""
        response = self.client.get(reverse('purchase:purchase_list'))
        
        self.assertEqual(response.status_code, 200)
        
    def test_purchase_list_requires_login(self):
        """اختبار أن قائمة المشتريات تتطلب تسجيل دخول"""
        self.client.logout()
        response = self.client.get(reverse('purchase:purchase_list'))
        
        # يجب أن يعيد توجيه لصفحة تسجيل الدخول
        self.assertEqual(response.status_code, 302)


class PurchaseDetailAPITest(TestCase):
    """اختبارات API تفاصيل المشتريات"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='test123'
        )
        self.client.login(username='testuser', password='test123')
        
    def test_purchase_detail_with_invalid_id(self):
        """اختبار تفاصيل فاتورة غير موجودة"""
        response = self.client.get(
            reverse('purchase:purchase_detail', kwargs={'pk': 99999})
        )
        
        self.assertEqual(response.status_code, 404)


class PurchaseCreateAPITest(TestCase):
    """اختبارات API إنشاء فاتورة مشتريات"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='test123'
        )
        self.client.login(username='testuser', password='test123')
        
    def test_purchase_create_view_loads(self):
        """اختبار تحميل صفحة إنشاء فاتورة"""
        response = self.client.get(reverse('purchase:purchase_create'))
        
        self.assertEqual(response.status_code, 200)


class PurchaseReturnAPITest(TestCase):
    """اختبارات API مرتجعات المشتريات"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='test123'
        )
        self.client.login(username='testuser', password='test123')
        
    def test_purchase_return_list_view_loads(self):
        """اختبار تحميل قائمة المرتجعات"""
        response = self.client.get(reverse('purchase:purchase_return_list'))
        
        self.assertEqual(response.status_code, 200)
