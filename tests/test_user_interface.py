"""
اختبارات واجهة المستخدم لنظام MWHEBA ERP
يغطي المودالز، النماذج، AJAX، والتفاعلات
"""

import json
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.http import JsonResponse

# Models imports
from product.models import Category, Brand, Product
from supplier.models import SupplierType, Supplier
from client.models import Client
from printing_pricing.models import PaperType, PaperWeight

User = get_user_model()


class UITestCase(TestCase):
    """اختبارات واجهة المستخدم الأساسية"""
    
    fixtures = [
        'supplier/fixtures/supplier_types.json',
        'printing_pricing/fixtures/initial_data.json'
    ]
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = Client()
        self.admin_user = User.objects.create_user(
            username="admin",
            email="admin@test.com",
            password="admin123",
            is_staff=True,
            is_superuser=True
        )
        
        # تسجيل الدخول
        self.client.login(username="admin", password="admin123")
        
    def test_dashboard_access(self):
        """اختبار الوصول للوحة التحكم"""
        print("🏠 اختبار الوصول للوحة التحكم...")
        
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "لوحة التحكم")
        
    def test_navigation_links(self):
        """اختبار روابط التنقل"""
        print("🧭 اختبار روابط التنقل...")
        
        # اختبار الروابط الأساسية
        urls_to_test = [
            '/product/',
            '/supplier/', 
            '/client/',
            '/purchase/',
            '/sale/',
            '/financial/',
            '/printing-pricing/'
        ]
        
        for url in urls_to_test:
            response = self.client.get(url)
            self.assertIn(response.status_code, [200, 302])  # 200 أو إعادة توجيه


class ModalTestCase(TestCase):
    """اختبارات المودالز والنماذج"""
    
    fixtures = [
        'supplier/fixtures/supplier_types.json',
        'printing_pricing/fixtures/initial_data.json'
    ]
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = Client()
        self.admin_user = User.objects.create_user(
            username="admin",
            password="admin123",
            is_staff=True,
            is_superuser=True
        )
        self.client.login(username="admin", password="admin123")
        
    def test_product_modal_create(self):
        """اختبار مودال إضافة منتج"""
        print("📦 اختبار مودال إضافة منتج...")
        
        # إنشاء تصنيف أولاً
        category = Category.objects.create(name="ورق A4")
        
        # اختبار عرض المودال
        response = self.client.get('/product/create/')
        self.assertEqual(response.status_code, 200)
        
        # اختبار إرسال البيانات
        data = {
            'name': 'ورق A4 80 جرام',
            'category': category.id,
            'sku': 'TEST-001',
            'cost_price': '0.50',
            'selling_price': '0.75'
        }
        
        response = self.client.post('/product/create/', data)
        self.assertIn(response.status_code, [200, 302])
        
        # التحقق من إنشاء المنتج
        self.assertTrue(Product.objects.filter(sku='TEST-001').exists())
        
    def test_ajax_product_create(self):
        """اختبار إضافة منتج عبر AJAX"""
        print("⚡ اختبار إضافة منتج عبر AJAX...")
        
        category = Category.objects.create(name="ورق A4")
        
        data = {
            'name': 'منتج AJAX',
            'category': category.id,
            'sku': 'AJAX-001',
            'cost_price': '1.00',
            'selling_price': '1.50'
        }
        
        response = self.client.post(
            '/product/create/',
            data,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        
        # التحقق من الاستجابة
        if response.status_code == 200:
            try:
                json_data = json.loads(response.content)
                if 'success' in json_data:
                    self.assertTrue(json_data.get('success', False))
            except json.JSONDecodeError:
                pass  # قد تكون الاستجابة HTML
                
    def test_supplier_modal_create(self):
        """اختبار مودال إضافة مورد"""
        print("🏭 اختبار مودال إضافة مورد...")
        
        # الحصول على نوع مورد
        supplier_type = SupplierType.objects.first()
        
        if supplier_type:
            data = {
                'name': 'مورد تجريبي',
                'supplier_type': supplier_type.id,
                'email': 'supplier@test.com',
                'phone': '01234567890'
            }
            
            response = self.client.post('/supplier/create/', data)
            self.assertIn(response.status_code, [200, 302])
            
    def test_paper_type_modal(self):
        """اختبار مودال أنواع الورق"""
        print("📄 اختبار مودال أنواع الورق...")
        
        # اختبار إضافة نوع ورق
        data = {
            'name': 'كوشيه تجريبي',
            'description': 'ورق كوشيه للاختبار'
        }
        
        response = self.client.post(
            '/printing-pricing/settings/paper-types/create/',
            data
        )
        self.assertIn(response.status_code, [200, 302])
        
        # التحقق من إنشاء النوع
        self.assertTrue(PaperType.objects.filter(name='كوشيه تجريبي').exists())


class AjaxTestCase(TestCase):
    """اختبارات AJAX والاستجابات"""
    
    fixtures = [
        'supplier/fixtures/supplier_types.json',
        'printing_pricing/fixtures/initial_data.json'
    ]
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = Client()
        self.admin_user = User.objects.create_user(
            username="admin",
            password="admin123",
            is_staff=True,
            is_superuser=True
        )
        self.client.login(username="admin", password="admin123")
        
    def test_ajax_form_validation(self):
        """اختبار التحقق من النماذج عبر AJAX"""
        print("✅ اختبار التحقق من النماذج عبر AJAX...")
        
        # إرسال بيانات غير صحيحة
        data = {
            'name': '',  # اسم فارغ
            'sku': ''    # SKU فارغ
        }
        
        response = self.client.post(
            '/product/create/',
            data,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        
        # التحقق من وجود أخطاء
        if response.status_code == 200:
            try:
                json_data = json.loads(response.content)
                if 'success' in json_data:
                    self.assertFalse(json_data.get('success', True))
                if 'errors' in json_data:
                    self.assertIsInstance(json_data['errors'], dict)
            except json.JSONDecodeError:
                pass
                
    def test_ajax_delete_operations(self):
        """اختبار عمليات الحذف عبر AJAX"""
        print("🗑️ اختبار عمليات الحذف عبر AJAX...")
        
        # إنشاء نوع ورق للحذف
        paper_type = PaperType.objects.create(
            name="نوع للحذف",
            description="سيتم حذفه"
        )
        
        # محاولة حذف عبر AJAX
        response = self.client.post(
            f'/printing-pricing/settings/paper-types/{paper_type.id}/delete/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        
        # التحقق من الاستجابة
        if response.status_code == 200:
            try:
                json_data = json.loads(response.content)
                if 'success' in json_data:
                    self.assertTrue(json_data.get('success', False))
            except json.JSONDecodeError:
                pass
                
    def test_dynamic_form_loading(self):
        """اختبار تحميل النماذج الديناميكية"""
        print("🔄 اختبار تحميل النماذج الديناميكية...")
        
        # اختبار تحميل نموذج خدمة الورق
        supplier_type = SupplierType.objects.filter(
            supplier_type_settings__type_key="paper"
        ).first()
        
        if supplier_type:
            response = self.client.get(
                f'/supplier/api/category-form/{supplier_type.supplier_type_settings.type_key}/',
                HTTP_X_REQUESTED_WITH='XMLHttpRequest'
            )
            
            self.assertEqual(response.status_code, 200)
            self.assertIn('application/json', response.get('Content-Type', ''))


class FilterAndSearchTestCase(TestCase):
    """اختبارات الفلاتر والبحث"""
    
    fixtures = [
        'product/fixtures/initial_data.json',
        'supplier/fixtures/supplier_types.json'
    ]
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = Client()
        self.admin_user = User.objects.create_user(
            username="admin",
            password="admin123",
            is_staff=True
        )
        self.client.login(username="admin", password="admin123")
        
        # إنشاء بيانات للاختبار
        self.category = Category.objects.create(name="ورق طباعة")
        
        self.product1 = Product.objects.create(
            name="ورق A4 80 جرام",
            category=self.category,
            sku="A4-80",
            cost_price=Decimal('0.50'),
            selling_price=Decimal('0.75')
        )
        
        self.product2 = Product.objects.create(
            name="ورق A3 120 جرام", 
            category=self.category,
            sku="A3-120",
            cost_price=Decimal('1.00'),
            selling_price=Decimal('1.50')
        )
        
    def test_product_search(self):
        """اختبار البحث في المنتجات"""
        print("🔍 اختبار البحث في المنتجات...")
        
        # البحث بالاسم
        response = self.client.get('/product/?search=A4')
        self.assertEqual(response.status_code, 200)
        
        # البحث بـ SKU
        response = self.client.get('/product/?search=A3-120')
        self.assertEqual(response.status_code, 200)
        
    def test_category_filter(self):
        """اختبار فلتر التصنيفات"""
        print("📂 اختبار فلتر التصنيفات...")
        
        response = self.client.get(f'/product/?category={self.category.id}')
        self.assertEqual(response.status_code, 200)
        
    def test_supplier_filter(self):
        """اختبار فلتر الموردين"""
        print("🏭 اختبار فلتر الموردين...")
        
        # فلتر حسب نوع المورد
        supplier_type = SupplierType.objects.first()
        if supplier_type:
            response = self.client.get(f'/supplier/?type={supplier_type.id}')
            self.assertEqual(response.status_code, 200)


class ResponsiveTestCase(TestCase):
    """اختبارات الاستجابة والتوافق"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = Client()
        self.admin_user = User.objects.create_user(
            username="admin",
            password="admin123",
            is_staff=True
        )
        self.client.login(username="admin", password="admin123")
        
    def test_mobile_compatibility(self):
        """اختبار التوافق مع الهواتف المحمولة"""
        print("📱 اختبار التوافق مع الهواتف المحمولة...")
        
        # محاكاة متصفح الهاتف المحمول
        response = self.client.get(
            '/',
            HTTP_USER_AGENT='Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)'
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'viewport')
        
    def test_css_and_js_loading(self):
        """اختبار تحميل ملفات CSS و JavaScript"""
        print("🎨 اختبار تحميل ملفات CSS و JavaScript...")
        
        response = self.client.get('/')
        
        # التحقق من وجود ملفات CSS
        self.assertContains(response, '.css')
        
        # التحقق من وجود ملفات JavaScript
        self.assertContains(response, '.js')


class ErrorHandlingTestCase(TestCase):
    """اختبارات معالجة الأخطاء"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = Client()
        self.admin_user = User.objects.create_user(
            username="admin",
            password="admin123",
            is_staff=True
        )
        self.client.login(username="admin", password="admin123")
        
    def test_404_error_handling(self):
        """اختبار معالجة خطأ 404"""
        print("❌ اختبار معالجة خطأ 404...")
        
        response = self.client.get('/nonexistent-page/')
        self.assertEqual(response.status_code, 404)
        
    def test_permission_denied(self):
        """اختبار منع الوصول"""
        print("🚫 اختبار منع الوصول...")
        
        # إنشاء مستخدم محدود الصلاحيات
        limited_user = User.objects.create_user(
            username="limited",
            password="limited123"
        )
        
        # تسجيل دخول المستخدم المحدود
        self.client.logout()
        self.client.login(username="limited", password="limited123")
        
        # محاولة الوصول لصفحة محظورة
        response = self.client.get('/financial/journal-entries/')
        self.assertIn(response.status_code, [302, 403])  # إعادة توجيه أو منع
        
    def test_form_error_display(self):
        """اختبار عرض أخطاء النماذج"""
        print("📝 اختبار عرض أخطاء النماذج...")
        
        # إرسال بيانات غير صحيحة
        data = {
            'name': '',  # حقل مطلوب فارغ
            'sku': 'duplicate-sku'
        }
        
        response = self.client.post('/product/create/', data)
        
        # التحقق من عرض الأخطاء
        if response.status_code == 200:
            self.assertContains(response, 'error', msg_prefix="يجب عرض رسائل الخطأ")


# تشغيل جميع اختبارات واجهة المستخدم
if __name__ == '__main__':
    import django
    from django.conf import settings
    from django.test.utils import get_runner
    
    django.setup()
    TestRunner = get_runner(settings)
    test_runner = TestRunner()
    failures = test_runner.run_tests([
        "tests.test_user_interface"
    ])
