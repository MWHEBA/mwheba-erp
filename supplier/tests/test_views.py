from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from supplier.models import Supplier, SupplierType

User = get_user_model()

class SupplierCreateModalViewTest(TestCase):
    """اختبارات إضافة مورد عبر المودال AJAX"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='test123'
        )
        self.client.login(username='testuser', password='test123')
        
        # إنشاء نوع مورد مطلوب لإنشاء مورد جديد
        self.supplier_type = SupplierType.objects.create(
            name='مورد عام',
            code='general',
            description='مورد عام'
        )
        
    def test_get_supplier_create_modal(self):
        """اختبار جلب صفحة المودال بـ GET"""
        url = reverse('supplier:supplier_create_modal')
        response = self.client.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        
        data = response.json()
        self.assertIn('html', data)
        self.assertIn('إضافة مورد جديد', data['html'])
        
    def test_post_supplier_create_modal_success(self):
        """اختبار إنشاء مورد بنجاح عبر POST AJAX"""
        url = reverse('supplier:supplier_create_modal')
        post_data = {
            'name': 'مورد تجربة جديد',
            'code': 'SUPNEW123',
            'primary_type': self.supplier_type.id,
            'phone': '01234567890',
            'is_active': 'on'
        }
        response = self.client.post(url, post_data, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('supplier_id', data)
        self.assertEqual(data['supplier_name'], 'مورد تجربة جديد')
        
        # التحقق من الحفظ في قاعدة البيانات
        self.assertTrue(Supplier.objects.filter(name='مورد تجربة جديد').exists())

    def test_post_supplier_create_modal_validation_error(self):
        """اختبار إرسال بيانات غير صالحة والتحقق من رجوع الأخطاء"""
        url = reverse('supplier:supplier_create_modal')
        post_data = {
            'name': '', # اسم فارغ
            'primary_type': self.supplier_type.id,
            'phone': '', # رقم هاتف فارغ
        }
        response = self.client.post(url, post_data, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('errors', data)
        self.assertIn('name', data['errors'])


class ServiceTypeSettingsViewsTest(TestCase):
    """اختبارات صفحة خدمات وقدرات التسعير المستقلة"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_superuser(
            username='adminuser',
            password='password123',
            email='admin@example.com'
        )
        self.client.login(username='adminuser', password='password123')

        from core.models import SystemModule
        SystemModule.objects.get_or_create(code='printing_pricing', defaults={'is_enabled': True, 'name': 'تسعير المطبوعات'})
        SystemModule.objects.filter(code='printing_pricing').update(is_enabled=True)

        from supplier.models import ServiceType
        self.st1 = ServiceType.objects.create(
            name='طباعة سلك سكرين',
            code='silkscreen',
            category='printing',
            is_active=True
        )

    def test_service_type_list_standalone_page(self):
        """التحقق من أن صفحة خدمات التسعير أصبحت مستقلة وتعرض البيانات والإحصائيات"""
        url = reverse('supplier:service_type_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'supplier/settings/service_types/list.html')
        self.assertIn('service_types', response.context)
        self.assertIn('stats', response.context)
        self.assertEqual(response.context['stats']['total'], 1)
        self.assertContains(response, 'طباعة سلك سكرين')

    def test_printing_pricing_service_type_list_alias(self):
        """التحقق من إمكانية الوصول من خلال namespace الخاص بتسعير المطبوعات"""
        url = reverse('printing_pricing:service_type_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'supplier/settings/service_types/list.html')

    def test_supplier_types_settings_list(self):
        """التحقق من صفحة أنواع الموردين النظيفة"""
        url = reverse('supplier:supplier_type_settings_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'supplier/settings/supplier_types/list.html')

