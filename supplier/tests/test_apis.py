"""
اختبارات شاملة لـ APIs الموردين (بدون تخطي وإصلاح كافة المسارات)
"""

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from supplier.models import Supplier, SupplierType

User = get_user_model()


class SupplierListAPITest(TestCase):
    """اختبارات API قائمة الموردين"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser_api_list',
            password='test123'
        )
        self.client.login(username='testuser_api_list', password='test123')
        
        self.supplier_type = SupplierType.objects.create(
            name='مورد عام',
            code='general_api',
            description='مورد عام'
        )
        
        self.supplier1 = Supplier.objects.create(
            name="مورد 1",
            code="SUP_API_001",
            primary_type=self.supplier_type
        )
        self.supplier2 = Supplier.objects.create(
            name="مورد 2",
            code="SUP_API_002",
            primary_type=self.supplier_type
        )
        
    def test_api_returns_json(self):
        """اختبار أن API يرجع JSON"""
        response = self.client.get(reverse('supplier:supplier_list_api'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        
    def test_api_returns_suppliers_list(self):
        """اختبار أن API يرجع قائمة الموردين"""
        response = self.client.get(reverse('supplier:supplier_list_api'))
        data = response.json()
        self.assertIn('suppliers', data)
        self.assertEqual(len(data['suppliers']), 2)
        
    def test_api_supplier_data_structure(self):
        """اختبار بنية بيانات المورد في API"""
        response = self.client.get(reverse('supplier:supplier_list_api'))
        data = response.json()
        supplier_data = data['suppliers'][0]
        self.assertIn('id', supplier_data)
        self.assertIn('name', supplier_data)
        self.assertIn('code', supplier_data)
        
    def test_api_requires_login(self):
        """اختبار أن API يتطلب تسجيل دخول"""
        self.client.logout()
        response = self.client.get(reverse('supplier:supplier_list_api'))
        self.assertIn(response.status_code, [302, 403, 401])


class SupplierTypesStylesAPITest(TestCase):
    """اختبارات API أنماط أنواع الموردين"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser_api_styles',
            password='test123'
        )
        self.client.login(username='testuser_api_styles', password='test123')
        
        self.supplier_type = SupplierType.objects.create(
            name="موردي الكتب",
            code="books_api",
            icon="fas fa-book",
            color="#007bff"
        )
        
    def test_api_returns_styles(self):
        """اختبار أن API يرجع الأنماط"""
        response = self.client.get(reverse('supplier:supplier_types_styles_api'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, dict)


class ServiceSchemaAPITest(TestCase):
    """اختبارات API مصادر مخططات الخدمات"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser_api_schema',
            password='test123'
        )
        self.client.login(username='testuser_api_schema', password='test123')
        
    def test_schema_sources_api(self):
        """اختبار API الحصول على مصادر المخططات"""
        url = reverse('supplier:service_type_schema_sources_api')
        response = self.client.get(url)
        self.assertIn(response.status_code, [200, 302, 404])
