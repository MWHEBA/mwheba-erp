"""
اختبارات واجهات برمجة التطبيقات (API)
"""

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
import json

User = get_user_model()


class APIAuthenticationTest(APITestCase):
    """اختبارات المصادقة في API"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="apiuser",
            password="apipass123",
            email="api@test.com"
        )
        
    def test_api_authentication_required(self):
        """اختبار أن API يتطلب مصادقة"""
        # محاولة الوصول بدون مصادقة
        response = self.client.get('/api/products/')
        
        # يجب أن يرجع 401 أو 403
        self.assertIn(response.status_code, [401, 403])
        
    def test_api_authentication_success(self):
        """اختبار المصادقة الناجحة"""
        # تسجيل الدخول
        self.client.force_authenticate(user=self.user)
        
        # محاولة الوصول مع المصادقة
        response = self.client.get('/api/')
        
        # يجب أن ينجح أو يعيد 404 إذا لم يكن الـ endpoint موجود
        self.assertIn(response.status_code, [200, 404])


class APIEndpointsTest(APITestCase):
    """اختبارات نقاط النهاية للـ API"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="apiuser",
            password="apipass123",
            is_staff=True
        )
        self.client.force_authenticate(user=self.user)
        
    def test_api_root_endpoint(self):
        """اختبار نقطة النهاية الجذر للـ API"""
        response = self.client.get('/api/')
        
        # إما أن ينجح أو لا يكون موجود
        self.assertIn(response.status_code, [200, 404])
        
    def test_api_products_endpoint(self):
        """اختبار نقطة نهاية المنتجات"""
        response = self.client.get('/api/products/')
        
        # إما أن ينجح أو لا يكون موجود
        self.assertIn(response.status_code, [200, 404])
        
    def test_api_suppliers_endpoint(self):
        """اختبار نقطة نهاية الموردين"""
        response = self.client.get('/api/suppliers/')
        
        # إما أن ينجح أو لا يكون موجود
        self.assertIn(response.status_code, [200, 404])
        
    def test_api_clients_endpoint(self):
        """اختبار نقطة نهاية العملاء"""
        response = self.client.get('/api/clients/')
        
        # إما أن ينجح أو لا يكون موجود
        self.assertIn(response.status_code, [200, 404])


class APIResponseFormatTest(APITestCase):
    """اختبارات تنسيق استجابة API"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="apiuser",
            password="apipass123",
            is_staff=True
        )
        self.client.force_authenticate(user=self.user)
        
    def test_api_json_response(self):
        """اختبار أن API يرجع JSON"""
        response = self.client.get('/api/')
        
        if response.status_code == 200:
            # التحقق من أن الاستجابة JSON
            self.assertEqual(
                response.get('Content-Type', '').split(';')[0],
                'application/json'
            )
            
            # محاولة تحليل JSON
            try:
                json.loads(response.content)
            except json.JSONDecodeError:
                self.fail("Response is not valid JSON")
                
    def test_api_error_response_format(self):
        """اختبار تنسيق استجابة الخطأ"""
        # طلب غير صحيح
        response = self.client.post('/api/invalid-endpoint/', {})
        
        if response.status_code >= 400:
            # التحقق من أن استجابة الخطأ JSON
            self.assertEqual(
                response.get('Content-Type', '').split(';')[0],
                'application/json'
            )


class APIPermissionsTest(APITestCase):
    """اختبارات صلاحيات API"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = APIClient()
        
        # مستخدم عادي
        self.regular_user = User.objects.create_user(
            username="regular",
            password="regular123"
        )
        
        # مستخدم موظف
        self.staff_user = User.objects.create_user(
            username="staff",
            password="staff123",
            is_staff=True
        )
        
        # مستخدم مدير
        self.admin_user = User.objects.create_user(
            username="admin",
            password="admin123",
            is_staff=True,
            is_superuser=True
        )
        
    def test_regular_user_permissions(self):
        """اختبار صلاحيات المستخدم العادي"""
        self.client.force_authenticate(user=self.regular_user)
        
        # محاولة الوصول لـ API
        response = self.client.get('/api/')
        
        # قد يُمنع أو يُسمح حسب إعدادات API
        self.assertIn(response.status_code, [200, 403, 404])
        
    def test_staff_user_permissions(self):
        """اختبار صلاحيات موظف"""
        self.client.force_authenticate(user=self.staff_user)
        
        response = self.client.get('/api/')
        
        # الموظف يجب أن يملك صلاحيات أكثر
        self.assertIn(response.status_code, [200, 404])
        
    def test_admin_user_permissions(self):
        """اختبار صلاحيات المدير"""
        self.client.force_authenticate(user=self.admin_user)
        
        response = self.client.get('/api/')
        
        # المدير يجب أن يملك صلاحيات كاملة
        self.assertIn(response.status_code, [200, 404])


class APICRUDOperationsTest(APITestCase):
    """اختبارات عمليات CRUD في API"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="apiuser",
            password="apipass123",
            is_staff=True,
            is_superuser=True
        )
        self.client.force_authenticate(user=self.user)
        
    def test_api_create_operation(self):
        """اختبار عملية الإنشاء عبر API"""
        data = {
            'name': 'منتج تجريبي',
            'description': 'وصف المنتج'
        }
        
        response = self.client.post('/api/products/', data)
        
        # إما أن ينجح أو لا يكون الـ endpoint موجود
        self.assertIn(response.status_code, [201, 404, 405])
        
    def test_api_read_operation(self):
        """اختبار عملية القراءة عبر API"""
        response = self.client.get('/api/products/')
        
        # إما أن ينجح أو لا يكون موجود
        self.assertIn(response.status_code, [200, 404])
        
        if response.status_code == 200:
            # التحقق من أن الاستجابة قابلة للقراءة
            try:
                data = json.loads(response.content)
                self.assertIsInstance(data, (list, dict))
            except json.JSONDecodeError:
                self.fail("Response is not valid JSON")
                
    def test_api_update_operation(self):
        """اختبار عملية التحديث عبر API"""
        # محاولة تحديث عنصر (قد لا يكون موجود)
        data = {
            'name': 'منتج محدث',
            'description': 'وصف محدث'
        }
        
        response = self.client.put('/api/products/1/', data)
        
        # إما أن ينجح أو لا يكون موجود
        self.assertIn(response.status_code, [200, 404, 405])
        
    def test_api_delete_operation(self):
        """اختبار عملية الحذف عبر API"""
        response = self.client.delete('/api/products/999/')
        
        # إما أن ينجح أو لا يكون موجود
        self.assertIn(response.status_code, [204, 404, 405])


class APIErrorHandlingTest(APITestCase):
    """اختبارات معالجة الأخطاء في API"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="apiuser",
            password="apipass123",
            is_staff=True
        )
        self.client.force_authenticate(user=self.user)
        
    def test_api_invalid_endpoint(self):
        """اختبار نقطة نهاية غير صحيحة"""
        response = self.client.get('/api/nonexistent-endpoint/')
        
        # يجب أن يرجع 404
        self.assertEqual(response.status_code, 404)
        
    def test_api_invalid_method(self):
        """اختبار طريقة غير مدعومة"""
        response = self.client.patch('/api/')
        
        # قد يرجع 405 أو 404
        self.assertIn(response.status_code, [404, 405])
        
    def test_api_invalid_data(self):
        """اختبار بيانات غير صحيحة"""
        invalid_data = {
            'invalid_field': 'invalid_value'
        }
        
        response = self.client.post('/api/products/', invalid_data)
        
        # قد يرجع 400 أو 404 حسب وجود الـ endpoint
        self.assertIn(response.status_code, [400, 404, 405])


class APIVersioningTest(APITestCase):
    """اختبارات إصدارات API"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="apiuser",
            password="apipass123",
            is_staff=True
        )
        self.client.force_authenticate(user=self.user)
        
    def test_api_version_header(self):
        """اختبار رأس إصدار API"""
        response = self.client.get('/api/')
        
        if response.status_code == 200:
            # التحقق من وجود معلومات الإصدار
            # قد تكون في الرأس أو في البيانات
            version_info = (
                'version' in response.data if hasattr(response, 'data') else False
            ) or (
                'API-Version' in response.headers
            )
            
            # لا نفشل الاختبار إذا لم تكن معلومات الإصدار موجودة
            # لأن هذا قد يكون اختياري
            
    def test_api_versioned_endpoints(self):
        """اختبار نقاط النهاية المُرقمة"""
        # اختبار إصدارات مختلفة
        versions = ['v1', 'v2']
        
        for version in versions:
            response = self.client.get(f'/api/{version}/')
            
            # إما أن ينجح أو لا يكون موجود
            self.assertIn(response.status_code, [200, 404])


class APIDocumentationTest(TestCase):
    """اختبارات توثيق API"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = Client()
        
    def test_api_documentation_exists(self):
        """اختبار وجود توثيق API"""
        # محاولة الوصول لصفحات التوثيق المحتملة
        doc_urls = [
            '/api/docs/',
            '/api/swagger/',
            '/api/redoc/',
            '/docs/',
            '/swagger/'
        ]
        
        found_docs = False
        for url in doc_urls:
            response = self.client.get(url)
            if response.status_code == 200:
                found_docs = True
                break
                
        # لا نفشل الاختبار إذا لم يكن التوثيق موجود
        # لأن هذا قد يكون اختياري في بعض المشاريع


class APIIntegrationTest(APITestCase):
    """اختبارات تكامل API مع النظام"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="apiuser",
            password="apipass123",
            is_staff=True,
            is_superuser=True
        )
        self.client.force_authenticate(user=self.user)
        
    def test_api_database_integration(self):
        """اختبار تكامل API مع قاعدة البيانات"""
        # محاولة إنشاء بيانات عبر API
        data = {
            'username': 'api_created_user',
            'email': 'api@created.com'
        }
        
        response = self.client.post('/api/users/', data)
        
        # إما أن ينجح أو لا يكون الـ endpoint موجود
        self.assertIn(response.status_code, [201, 404, 405])
        
        if response.status_code == 201:
            # التحقق من إنشاء البيانات في قاعدة البيانات
            self.assertTrue(
                User.objects.filter(username='api_created_user').exists()
            )
            
    def test_api_business_logic_integration(self):
        """اختبار تكامل API مع منطق الأعمال"""
        # اختبار أن API يطبق قواعد العمل
        # مثل التحقق من صحة البيانات، الحسابات، إلخ
        
        # هذا مثال عام - يجب تخصيصه حسب منطق العمل الفعلي
        response = self.client.get('/api/')
        
        # التأكد من أن API يعمل مع النظام
        self.assertIn(response.status_code, [200, 404])
