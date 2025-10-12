"""
اختبارات JavaScript لنظام التسعير
JavaScript Tests for Pricing System
"""
import pytest
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import os

from pricing.models import PricingOrder, PaperType, PaperSize
from client.models import Client as ClientModel


class PricingJavaScriptTestCase(StaticLiveServerTestCase):
    """اختبارات JavaScript لنظام التسعير باستخدام Selenium"""
    
    @classmethod
    def setUpClass(cls):
        """إعداد Selenium WebDriver"""
        super().setUpClass()
        
        # إعداد Chrome options
        chrome_options = Options()
        chrome_options.add_argument('--headless')  # تشغيل بدون واجهة
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        
        try:
            cls.selenium = webdriver.Chrome(options=chrome_options)
            cls.selenium.implicitly_wait(10)
        except Exception as e:
            # إذا لم يكن Chrome متاحاً، استخدم Firefox
            try:
                from selenium.webdriver.firefox.options import Options as FirefoxOptions
                firefox_options = FirefoxOptions()
                firefox_options.add_argument('--headless')
                cls.selenium = webdriver.Firefox(options=firefox_options)
                cls.selenium.implicitly_wait(10)
            except Exception:
                cls.selenium = None
                print("تحذير: لا يمكن تشغيل اختبارات Selenium - المتصفح غير متاح")
    
    @classmethod
    def tearDownClass(cls):
        """تنظيف Selenium WebDriver"""
        if cls.selenium:
            cls.selenium.quit()
        super().tearDownClass()
    
    def setUp(self):
        """إعداد البيانات للاختبارات"""
        if not self.selenium:
            self.skipTest("Selenium WebDriver غير متاح")
            
        # إنشاء مستخدم للاختبار
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # إنشاء عميل للاختبار
        self.client_obj = ClientModel.objects.create(
            name='عميل تجريبي',
            email='client@test.com',
            phone='01234567890'
        )
        
        # إنشاء البيانات المرجعية
        self.paper_type = PaperType.objects.create(
            name='ورق أبيض',
            weight=80,
            price_per_kg=15.00
        )
        
        self.paper_size = PaperSize.objects.create(
            name='A4',
            width=21.0,
            height=29.7
        )
        
        # تسجيل دخول المستخدم
        self.login_user()
    
    def login_user(self):
        """تسجيل دخول المستخدم"""
        self.selenium.get(f'{self.live_server_url}/login/')
        
        username_input = self.selenium.find_element(By.NAME, "username")
        password_input = self.selenium.find_element(By.NAME, "password")
        
        username_input.send_keys('testuser')
        password_input.send_keys('testpass123')
        
        self.selenium.find_element(By.XPATH, '//button[@type="submit"]').click()
        
        # انتظار تحميل الصفحة
        WebDriverWait(self.selenium, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
    
    def test_pricing_form_javascript_loading(self):
        """اختبار تحميل JavaScript في صفحة التسعير"""
        self.selenium.get(f'{self.live_server_url}/pricing/orders/create/')
        
        # انتظار تحميل JavaScript
        WebDriverWait(self.selenium, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "script"))
        )
        
        # التحقق من تحميل ملفات JavaScript الأساسية
        scripts = self.selenium.find_elements(By.TAG_NAME, "script")
        script_sources = [script.get_attribute('src') for script in scripts if script.get_attribute('src')]
        
        # التحقق من وجود ملفات JavaScript المطلوبة
        js_files = ['core.js', 'main.js', 'api-services.js', 'pricing-calculator.js']
        for js_file in js_files:
            found = any(js_file in src for src in script_sources if src)
            self.assertTrue(found, f"ملف {js_file} غير محمل")
    
    def test_pricing_system_initialization(self):
        """اختبار تهيئة نظام التسعير JavaScript"""
        self.selenium.get(f'{self.live_server_url}/pricing/orders/create/')
        
        # انتظار تحميل النظام
        WebDriverWait(self.selenium, 10).until(
            EC.presence_of_element_located((By.ID, "pricing-form"))
        )
        
        # التحقق من تهيئة كائن PricingSystem
        pricing_system_exists = self.selenium.execute_script(
            "return typeof window.PricingSystem !== 'undefined';"
        )
        self.assertTrue(pricing_system_exists, "كائن PricingSystem غير مهيأ")
        
        # التحقق من تهيئة EventBus
        event_bus_exists = self.selenium.execute_script(
            "return typeof window.EventBus !== 'undefined';"
        )
        self.assertTrue(event_bus_exists, "كائن EventBus غير مهيأ")
    
    def test_paper_type_selection_triggers_calculation(self):
        """اختبار أن اختيار نوع الورق يؤدي لحساب تلقائي"""
        self.selenium.get(f'{self.live_server_url}/pricing/orders/create/')
        
        # انتظار تحميل النموذج
        WebDriverWait(self.selenium, 10).until(
            EC.presence_of_element_located((By.ID, "id_paper_type"))
        )
        
        # اختيار نوع الورق
        paper_type_select = self.selenium.find_element(By.ID, "id_paper_type")
        paper_type_select.send_keys(str(self.paper_type.id))
        
        # اختيار مقاس الورق
        paper_size_select = self.selenium.find_element(By.ID, "id_paper_size")
        paper_size_select.send_keys(str(self.paper_size.id))
        
        # إدخال الكمية
        quantity_input = self.selenium.find_element(By.ID, "id_quantity")
        quantity_input.clear()
        quantity_input.send_keys("1000")
        
        # انتظار الحساب التلقائي
        time.sleep(2)
        
        # التحقق من تحديث حقل تكلفة الورق
        paper_cost_field = self.selenium.find_element(By.ID, "id_paper_cost")
        paper_cost_value = paper_cost_field.get_attribute('value')
        
        # يجب أن تكون التكلفة أكبر من صفر
        self.assertNotEqual(paper_cost_value, '0')
        self.assertNotEqual(paper_cost_value, '')
    
    def test_step_indicator_functionality(self):
        """اختبار وظائف مؤشر الخطوات"""
        self.selenium.get(f'{self.live_server_url}/pricing/orders/create/')
        
        # انتظار تحميل مؤشر الخطوات
        WebDriverWait(self.selenium, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "step-indicator"))
        )
        
        # التحقق من وجود الخطوات
        steps = self.selenium.find_elements(By.CLASS_NAME, "step")
        self.assertGreaterEqual(len(steps), 4, "عدد الخطوات أقل من المطلوب")
        
        # التحقق من الخطوة النشطة
        active_steps = self.selenium.find_elements(By.CLASS_NAME, "step.active")
        self.assertEqual(len(active_steps), 1, "يجب أن تكون خطوة واحدة نشطة")
    
    def test_section_toggle_functionality(self):
        """اختبار وظائف إظهار/إخفاء الأقسام"""
        self.selenium.get(f'{self.live_server_url}/pricing/orders/create/')
        
        # انتظار تحميل الأقسام
        WebDriverWait(self.selenium, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "pricing-section"))
        )
        
        # البحث عن أزرار التبديل
        toggle_buttons = self.selenium.find_elements(By.CLASS_NAME, "section-toggle")
        
        if toggle_buttons:
            # النقر على زر التبديل
            toggle_buttons[0].click()
            time.sleep(1)
            
            # التحقق من تغيير حالة القسم
            section = self.selenium.find_element(By.CLASS_NAME, "pricing-section")
            section_classes = section.get_attribute('class')
            
            # يجب أن يحتوي على class للحالة المتغيرة
            self.assertTrue('collapsed' in section_classes or 'expanded' in section_classes)
    
    def test_api_calls_from_javascript(self):
        """اختبار استدعاءات API من JavaScript"""
        self.selenium.get(f'{self.live_server_url}/pricing/orders/create/')
        
        # انتظار تحميل النموذج
        WebDriverWait(self.selenium, 10).until(
            EC.presence_of_element_located((By.ID, "pricing-form"))
        )
        
        # تنفيذ استدعاء API من JavaScript
        api_response = self.selenium.execute_script("""
            return new Promise((resolve) => {
                fetch('/pricing/api/paper-types/')
                    .then(response => response.json())
                    .then(data => resolve(data))
                    .catch(error => resolve({error: error.message}));
            });
        """)
        
        # التحقق من نجاح الاستدعاء
        self.assertNotIn('error', api_response)
        self.assertIn('success', api_response)
    
    def test_form_validation_javascript(self):
        """اختبار التحقق من النموذج بـ JavaScript"""
        self.selenium.get(f'{self.live_server_url}/pricing/orders/create/')
        
        # انتظار تحميل النموذج
        WebDriverWait(self.selenium, 10).until(
            EC.presence_of_element_located((By.ID, "pricing-form"))
        )
        
        # محاولة إرسال النموذج بدون بيانات
        submit_button = self.selenium.find_element(By.XPATH, '//button[@type="submit"]')
        submit_button.click()
        
        # انتظار ظهور رسائل الخطأ
        time.sleep(2)
        
        # التحقق من ظهور رسائل التحقق
        error_messages = self.selenium.find_elements(By.CLASS_NAME, "error-message")
        validation_errors = self.selenium.find_elements(By.CLASS_NAME, "field-error")
        
        # يجب أن تظهر رسائل خطأ
        self.assertTrue(len(error_messages) > 0 or len(validation_errors) > 0)
    
    def test_session_handlers_functionality(self):
        """اختبار وظائف معالجة الجلسة"""
        self.selenium.get(f'{self.live_server_url}/pricing/orders/create/')
        
        # انتظار تحميل النموذج
        WebDriverWait(self.selenium, 10).until(
            EC.presence_of_element_located((By.ID, "pricing-form"))
        )
        
        # ملء بعض البيانات
        product_name_input = self.selenium.find_element(By.ID, "id_product_name")
        product_name_input.send_keys("كتالوج تجريبي")
        
        quantity_input = self.selenium.find_element(By.ID, "id_quantity")
        quantity_input.send_keys("1000")
        
        # انتظار الحفظ التلقائي
        time.sleep(3)
        
        # إعادة تحميل الصفحة
        self.selenium.refresh()
        
        # انتظار تحميل النموذج مرة أخرى
        WebDriverWait(self.selenium, 10).until(
            EC.presence_of_element_located((By.ID, "pricing-form"))
        )
        
        # التحقق من استرجاع البيانات
        product_name_value = self.selenium.find_element(By.ID, "id_product_name").get_attribute('value')
        quantity_value = self.selenium.find_element(By.ID, "id_quantity").get_attribute('value')
        
        # يجب أن تكون البيانات محفوظة
        self.assertEqual(product_name_value, "كتالوج تجريبي")
        self.assertEqual(quantity_value, "1000")


class PricingJavaScriptUnitTestCase(TestCase):
    """اختبارات وحدة JavaScript (بدون Selenium)"""
    
    def setUp(self):
        """إعداد البيانات للاختبارات"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')
    
    def test_javascript_files_exist(self):
        """اختبار وجود ملفات JavaScript"""
        from django.conf import settings
        import os
        
        js_files = [
            'core.js', 'main.js', 'api-services.js', 'event-bus.js',
            'paper-handlers.js', 'print-handlers.js', 'finishing-handlers.js',
            'pricing-calculator.js', 'session-handlers.js', 'ui-handlers.js'
        ]
        
        static_js_path = os.path.join(settings.BASE_DIR, 'static', 'js', 'pricing')
        
        for js_file in js_files:
            file_path = os.path.join(static_js_path, js_file)
            self.assertTrue(os.path.exists(file_path), f"ملف {js_file} غير موجود")
    
    def test_pricing_form_template_includes_javascript(self):
        """اختبار أن قالب نموذج التسعير يتضمن JavaScript"""
        url = reverse('pricing:pricing_order_create')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # التحقق من تضمين ملفات JavaScript
        js_files = ['core.js', 'main.js', 'api-services.js']
        for js_file in js_files:
            self.assertContains(response, js_file)
    
    def test_pricing_apis_return_json(self):
        """اختبار أن APIs التسعير ترجع JSON"""
        # إنشاء البيانات المرجعية
        paper_type = PaperType.objects.create(
            name='ورق أبيض',
            weight=80
        )
        
        # اختبار API أنواع الورق
        url = reverse('pricing:get_paper_types')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        
        # التحقق من صحة JSON
        import json
        try:
            json.loads(response.content)
        except json.JSONDecodeError:
            self.fail("الاستجابة ليست JSON صحيح")


class PricingJavaScriptPerformanceTestCase(TestCase):
    """اختبارات أداء JavaScript"""
    
    def setUp(self):
        """إعداد البيانات للاختبارات"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')
    
    def test_javascript_file_sizes(self):
        """اختبار أحجام ملفات JavaScript"""
        from django.conf import settings
        import os
        
        js_files = [
            'core.js', 'main.js', 'api-services.js', 'pricing-calculator.js'
        ]
        
        static_js_path = os.path.join(settings.BASE_DIR, 'static', 'js', 'pricing')
        
        for js_file in js_files:
            file_path = os.path.join(static_js_path, js_file)
            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                # يجب أن يكون حجم الملف معقول (أقل من 100KB)
                self.assertLess(file_size, 100 * 1024, f"ملف {js_file} كبير جداً")
    
    def test_api_response_time(self):
        """اختبار زمن استجابة APIs"""
        import time
        
        # إنشاء البيانات المرجعية
        paper_type = PaperType.objects.create(
            name='ورق أبيض',
            weight=80
        )
        
        url = reverse('pricing:get_paper_types')
        
        start_time = time.time()
        response = self.client.get(url)
        end_time = time.time()
        
        response_time = end_time - start_time
        
        self.assertEqual(response.status_code, 200)
        # يجب أن يكون زمن الاستجابة أقل من ثانية واحدة
        self.assertLess(response_time, 1.0, "زمن استجابة API بطيء")


if __name__ == '__main__':
    pytest.main([__file__])
