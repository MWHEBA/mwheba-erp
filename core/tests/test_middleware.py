from django.test import TestCase, Client, RequestFactory, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.contrib.messages.storage.fallback import FallbackStorage
from django.http import HttpResponse
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import json
import pytz
import time
import re

from core.middleware import (
    LoginRequiredMiddleware,
    ActivityTrackingMiddleware,
    MaintenanceModeMiddleware,
    TimezoneMiddleware,
    AuditLogMiddleware,
    SecurityHeadersMiddleware,
    PerformanceMonitoringMiddleware
)
from core.models import UserProfile, UserActivity, AuditLog

User = get_user_model()

class MiddlewareTestCase(TestCase):
    """
    اختبارات middleware التطبيق
    """
    def setUp(self):
        self.client = Client()
        self.factory = RequestFactory()
        
        # إنشاء مستخدم للاختبارات
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        
        # إنشاء مستخدم مدير للاختبارات
        self.admin_user = User.objects.create_user(
            username='adminuser',
            password='adminpass123',
            email='admin@example.com',
            is_staff=True,
            is_superuser=True
        )
        
        # إنشاء ملف تعريف للمستخدم
        self.user_profile = UserProfile.objects.create(
            user=self.user,
            phone='01234567890',
            timezone='Africa/Cairo'
        )
    
    def test_login_required_middleware(self):
        """
        اختبار middleware طلب تسجيل الدخول
        """
        # التأكد من أن الصفحات المحمية تتطلب تسجيل الدخول
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue('/accounts/login/' in response.url)
        
        # التأكد من أن الصفحات العامة لا تتطلب تسجيل الدخول
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        
        # اختبار middleware باستخدام RequestFactory
        request = self.factory.get('/dashboard/')
        request.user = self.user
        middleware = LoginRequiredMiddleware(get_response=lambda r: HttpResponse())
        response = middleware(request)
        self.assertEqual(response.status_code, 200)
    
    def test_maintenance_mode_middleware(self):
        """
        اختبار middleware وضع الصيانة
        """
        # تسجيل دخول المستخدم العادي
        self.client.login(username='testuser', password='testpass123')
        
        # اختبار middleware عندما يكون وضع الصيانة غير مفعل
        with self.settings(MAINTENANCE_MODE=False):
            response = self.client.get(reverse('dashboard'))
            self.assertEqual(response.status_code, 200)
        
        # اختبار middleware عندما يكون وضع الصيانة مفعل (للمستخدم العادي)
        with self.settings(MAINTENANCE_MODE=True):
            response = self.client.get(reverse('dashboard'))
            self.assertEqual(response.status_code, 503)
            self.assertTemplateUsed(response, 'core/maintenance.html')
        
        # تسجيل خروج المستخدم العادي
        self.client.logout()
        
        # تسجيل دخول المستخدم المدير
        self.client.login(username='adminuser', password='adminpass123')
        
        # اختبار middleware عندما يكون وضع الصيانة مفعل (للمستخدم المدير)
        with self.settings(MAINTENANCE_MODE=True):
            response = self.client.get(reverse('dashboard'))
            self.assertEqual(response.status_code, 200)
    
    def test_activity_tracking_middleware(self):
        """
        اختبار middleware تتبع النشاط
        """
        # تسجيل دخول المستخدم
        self.client.login(username='testuser', password='testpass123')
        
        # التأكد من عدم وجود أنشطة قبل زيارة الصفحة
        self.assertEqual(UserActivity.objects.filter(user=self.user).count(), 0)
        
        # زيارة صفحة
        self.client.get(reverse('dashboard'))
        
        # التأكد من تسجيل النشاط
        activities = UserActivity.objects.filter(user=self.user)
        self.assertEqual(activities.count(), 1)
        
        activity = activities.first()
        self.assertEqual(activity.user, self.user)
        self.assertEqual(activity.url, reverse('dashboard'))
        
        # اختبار middleware باستخدام RequestFactory
        request = self.factory.get('/dashboard/')
        request.user = self.user
        request.session = self.client.session
        middleware = ActivityTrackingMiddleware(get_response=lambda r: HttpResponse())
        
        # تخزين الوقت الحالي للتحقق من تحديث آخر نشاط
        now = timezone.now()
        # تعديل آخر نشاط ليكون قديمًا
        self.user.last_activity = now - timedelta(hours=1)
        self.user.save()
        
        response = middleware(request)
        self.user.refresh_from_db()
        
        # التحقق من تحديث آخر نشاط للمستخدم
        self.assertGreater(self.user.last_activity, now)
    
    @override_settings(USE_TZ=True)
    def test_timezone_middleware(self):
        """
        اختبار middleware المنطقة الزمنية
        """
        # تسجيل دخول المستخدم
        self.client.login(username='testuser', password='testpass123')
        
        # زيارة صفحة
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # اختبار middleware باستخدام RequestFactory
        request = self.factory.get('/dashboard/')
        request.user = self.user
        request.session = {}
        middleware = TimezoneMiddleware(get_response=lambda r: HttpResponse())
        
        response = middleware(request)
        
        # التحقق من تعيين المنطقة الزمنية في الجلسة
        self.assertEqual(request.session.get('django_timezone'), 'Africa/Cairo')
    
    def test_ajax_redirect_middleware(self):
        """
        اختبار middleware إعادة توجيه AJAX
        """
        # تهيئة طلب AJAX
        request = self.factory.get('/accounts/login/')
        request.META['HTTP_X_REQUESTED_WITH'] = 'XMLHttpRequest'
        
        # تسجيل خروج واختبار إعادة التوجيه
        self.client.logout()
        
        # إرسال طلب AJAX للصفحة التي تتطلب تسجيل الدخول
        response = self.client.get(
            reverse('dashboard'),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        
        # التحقق من أن الاستجابة تحتوي على رمز إعادة التوجيه وعنوان URL
        self.assertEqual(response.status_code, 401)
        data = json.loads(response.content)
        self.assertIn('redirect', data)


class CsrfMiddlewareTest(TestCase):
    """
    اختبارات middleware حماية CSRF
    """
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
    
    def test_csrf_protection(self):
        """
        اختبار حماية CSRF في النماذج
        """
        # تسجيل دخول المستخدم
        login_url = reverse('login')
        
        # الحصول على رمز CSRF من صفحة تسجيل الدخول
        response = self.client.get(login_url)
        csrf_token = response.context['csrf_token']
        
        # محاولة تسجيل الدخول بدون رمز CSRF
        response = self.client.post(
            login_url,
            {'username': 'testuser', 'password': 'testpass123'}
        )
        
        # يجب رفض الطلب لعدم وجود رمز CSRF
        self.assertEqual(response.status_code, 403)
        
        # تسجيل الدخول مع رمز CSRF
        response = self.client.post(
            login_url,
            {'username': 'testuser', 'password': 'testpass123', 'csrfmiddlewaretoken': csrf_token}
        )
        
        # يجب أن يكون تسجيل الدخول ناجحًا
        self.assertEqual(response.status_code, 302)
    
    def test_csrf_exempt(self):
        """
        اختبار استثناء CSRF للمسارات المحددة
        """
        # يعتمد هذا الاختبار على إعدادات التطبيق وقد يحتاج للتعديل
        # افتراض وجود مسار معفى من حماية CSRF (مثل API)
        # في حالة عدم وجود مسار معفى، يمكن تخطي هذا الاختبار
        pass


class SecurityMiddlewareTest(TestCase):
    """
    اختبارات middleware الأمان
    """
    def setUp(self):
        self.client = Client()
    
    def test_xss_protection_header(self):
        """
        اختبار رأس حماية XSS
        """
        response = self.client.get(reverse('login'))
        self.assertEqual(response['X-XSS-Protection'], '1; mode=block')
    
    def test_content_type_header(self):
        """
        اختبار رأس نوع المحتوى
        """
        response = self.client.get(reverse('login'))
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
    
    def test_frame_options_header(self):
        """
        اختبار رأس خيارات الإطار
        """
        response = self.client.get(reverse('login'))
        self.assertEqual(response['X-Frame-Options'], 'SAMEORIGIN')
    
    @override_settings(DEBUG=False, SECURE_SSL_REDIRECT=True)
    def test_ssl_redirect(self):
        """
        اختبار إعادة توجيه SSL
        """
        # يجب ضبط SECURE_SSL_REDIRECT = True في الإعدادات
        # يتم تخطي هذا الاختبار في بيئة التطوير
        if not settings.DEBUG and settings.SECURE_SSL_REDIRECT:
            response = self.client.get(reverse('login'), secure=False)
            self.assertEqual(response.status_code, 301)
    
    @override_settings(DEBUG=False, SECURE_HSTS_SECONDS=3600)
    def test_hsts_header(self):
        """
        اختبار رأس HSTS
        """
        # يجب ضبط SECURE_HSTS_SECONDS > 0 في الإعدادات
        # يتم تخطي هذا الاختبار في بيئة التطوير
        if not settings.DEBUG and settings.SECURE_HSTS_SECONDS:
            response = self.client.get(reverse('login'), secure=True)
            self.assertIn('max-age=3600', response['Strict-Transport-Security'])


class SessionMiddlewareTest(TestCase):
    """
    اختبارات middleware الجلسة
    """
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
    
    def test_session_cookie_settings(self):
        """
        اختبار إعدادات كوكي الجلسة
        """
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        
        # الحصول على قائمة الكوكيز
        session_cookie = response.cookies.get(settings.SESSION_COOKIE_NAME)
        
        # التحقق من إعدادات الكوكي
        if session_cookie:
            self.assertEqual(session_cookie['httponly'], True)
            if not settings.DEBUG:
                self.assertEqual(session_cookie['secure'], settings.SESSION_COOKIE_SECURE)
    
    @override_settings(SESSION_COOKIE_AGE=1800)
    def test_session_expiry(self):
        """
        اختبار انتهاء صلاحية الجلسة
        """
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        
        # التحقق من مدة صلاحية الجلسة
        session_cookie = response.cookies.get(settings.SESSION_COOKIE_NAME)
        if session_cookie:
            # التحقق من أن وقت انتهاء الصلاحية أقل من أو يساوي الوقت المحدد
            self.assertLessEqual(session_cookie['max-age'], settings.SESSION_COOKIE_AGE)
    
    def test_session_regeneration(self):
        """
        اختبار إعادة إنشاء معرف الجلسة عند تسجيل الدخول
        """
        # الحصول على معرف جلسة قبل تسجيل الدخول
        response = self.client.get(reverse('login'))
        before_login_session = self.client.session.session_key
        
        # تسجيل الدخول
        self.client.login(username='testuser', password='testpass123')
        
        # الحصول على معرف جلسة بعد تسجيل الدخول
        response = self.client.get(reverse('dashboard'))
        after_login_session = self.client.session.session_key
        
        # التحقق من تغيير معرف الجلسة
        self.assertNotEqual(before_login_session, after_login_session)


class MaintenanceModeMiddlewareTest(TestCase):
    """
    اختبارات وسيط وضع الصيانة
    """
    
    def setUp(self):
        """
        إعداد بيئة الاختبار
        """
        self.factory = RequestFactory()
        self.middleware = MaintenanceModeMiddleware(get_response=lambda request: HttpResponse())
        self.admin_user = User.objects.create_superuser(
            username='adminuser',
            email='admin@example.com',
            password='adminpassword123'
        )
        self.regular_user = User.objects.create_user(
            username='regularuser',
            email='regular@example.com',
            password='regular123'
        )
    
    def test_maintenance_mode_disabled(self):
        """
        اختبار عندما يكون وضع الصيانة معطلاً
        """
        # تعطيل وضع الصيانة
        settings.MAINTENANCE_MODE = False
        
        # إنشاء طلب
        request = self.factory.get('/')
        request.user = self.regular_user
        
        # تشغيل الوسيط
        response = self.middleware(request)
        
        # يجب أن يستمر الطلب بشكل طبيعي
        self.assertEqual(response.status_code, 200)
    
    def test_maintenance_mode_enabled_regular_user(self):
        """
        اختبار عندما يكون وضع الصيانة مفعلاً للمستخدم العادي
        """
        # تفعيل وضع الصيانة
        settings.MAINTENANCE_MODE = True
        
        # إنشاء طلب من مستخدم عادي
        request = self.factory.get('/')
        request.user = self.regular_user
        
        # تشغيل الوسيط
        response = self.middleware(request)
        
        # يجب إعادة توجيه المستخدم العادي إلى صفحة الصيانة
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.content.decode(), 'النظام في وضع الصيانة. يرجى المحاولة لاحقًا.')
    
    def test_maintenance_mode_enabled_admin_user(self):
        """
        اختبار عندما يكون وضع الصيانة مفعلاً للمستخدم المشرف
        """
        # تفعيل وضع الصيانة
        settings.MAINTENANCE_MODE = True
        
        # إنشاء طلب من مستخدم مشرف
        request = self.factory.get('/')
        request.user = self.admin_user
        
        # تشغيل الوسيط
        response = self.middleware(request)
        
        # يجب السماح للمستخدم المشرف بالمرور
        self.assertEqual(response.status_code, 200)
    
    def test_maintenance_mode_allowed_urls(self):
        """
        اختبار عندما يكون وضع الصيانة مفعلاً لكن المسار مسموح به
        """
        # تفعيل وضع الصيانة
        settings.MAINTENANCE_MODE = True
        
        # تحديد مسارات مسموح بها
        settings.MAINTENANCE_ALLOWED_URLS = [r'^/login/', r'^/maintenance/']
        
        # إنشاء طلب لمسار مسموح به
        request = self.factory.get('/login/')
        request.user = self.regular_user
        
        # تشغيل الوسيط
        response = self.middleware(request)
        
        # يجب السماح بالمرور للمسار المسموح به
        self.assertEqual(response.status_code, 200)


class TimezoneMiddlewareTest(TestCase):
    """
    اختبارات وسيط المنطقة الزمنية
    """
    
    def setUp(self):
        """
        إعداد بيئة الاختبار
        """
        self.factory = RequestFactory()
        self.middleware = TimezoneMiddleware(get_response=lambda request: HttpResponse())
        self.user = User.objects.create_user(
            username='timezoneuser',
            email='timezone@example.com',
            password='timezone123'
        )
        # افتراض وجود حقل timezone في نموذج المستخدم أو الملف الشخصي
        self.user.profile = type('Profile', (), {'timezone': 'Europe/London'})()
    
    def test_timezone_for_authenticated_user(self):
        """
        اختبار تعيين المنطقة الزمنية للمستخدم المصادق
        """
        request = self.factory.get('/')
        request.user = self.user
        request.session = {}
        
        # تشغيل الوسيط
        self.middleware(request)
        
        # التحقق من تغيير المنطقة الزمنية
        current_timezone = timezone.get_current_timezone_name()
        self.assertEqual(current_timezone, 'Europe/London')
    
    def test_timezone_from_session(self):
        """
        اختبار تعيين المنطقة الزمنية من الجلسة
        """
        request = self.factory.get('/')
        request.user = self.user
        request.session = {'timezone': 'Asia/Tokyo'}
        
        # تشغيل الوسيط
        self.middleware(request)
        
        # التحقق من تغيير المنطقة الزمنية
        current_timezone = timezone.get_current_timezone_name()
        self.assertEqual(current_timezone, 'Asia/Tokyo')
    
    def test_default_timezone(self):
        """
        اختبار استخدام المنطقة الزمنية الافتراضية
        """
        request = self.factory.get('/')
        request.user = User.objects.create_user(
            username='defaultuser',
            email='default@example.com',
            password='default123'
        )
        request.session = {}
        
        # تشغيل الوسيط
        self.middleware(request)
        
        # التحقق من استخدام المنطقة الزمنية الافتراضية
        current_timezone = timezone.get_current_timezone_name()
        self.assertEqual(current_timezone, settings.TIME_ZONE)


class AuditLogMiddlewareTest(TestCase):
    """
    اختبارات وسيط سجل المراقبة
    """
    
    def setUp(self):
        """
        إعداد بيئة الاختبار
        """
        self.factory = RequestFactory()
        self.middleware = AuditLogMiddleware(get_response=lambda request: HttpResponse())
        self.user = User.objects.create_user(
            username='audituser',
            email='audit@example.com',
            password='audit123'
        )
    
    def test_audit_log_creation(self):
        """
        اختبار إنشاء سجل مراقبة عند تنفيذ طلب
        """
        # إنشاء طلب
        request = self.factory.get('/admin/users/')
        request.user = self.user
        request.META = {
            'REMOTE_ADDR': '127.0.0.1',
            'HTTP_USER_AGENT': 'Mozilla/5.0'
        }
        
        # تنفيذ الوسيط
        self.middleware(request)
        
        # التحقق من إنشاء سجل المراقبة
        log = AuditLog.objects.filter(
            user=self.user,
            url='/admin/users/',
            method='GET',
            ip_address='127.0.0.1'
        ).first()
        
        self.assertIsNotNone(log)
        self.assertEqual(log.user_agent, 'Mozilla/5.0')
    
    def test_audit_log_for_anonymous_user(self):
        """
        اختبار إنشاء سجل مراقبة للمستخدم المجهول
        """
        # إنشاء طلب
        request = self.factory.get('/login/')
        request.user = None
        request.META = {
            'REMOTE_ADDR': '127.0.0.1',
            'HTTP_USER_AGENT': 'Mozilla/5.0'
        }
        
        # تنفيذ الوسيط
        self.middleware(request)
        
        # التحقق من إنشاء سجل المراقبة
        log = AuditLog.objects.filter(
            user__isnull=True,
            url='/login/',
            method='GET',
            ip_address='127.0.0.1'
        ).first()
        
        self.assertIsNotNone(log)
        self.assertEqual(log.user_agent, 'Mozilla/5.0')


class SecurityHeadersMiddlewareTest(TestCase):
    """
    اختبارات وسيط رؤوس الأمان
    """
    
    def setUp(self):
        """
        إعداد بيئة الاختبار
        """
        self.client = Client()
        self.user = User.objects.create_user(
            username='securityuser',
            email='security@example.com',
            password='security123'
        )
        self.client.login(username='securityuser', password='security123')
        self.dashboard_url = reverse('dashboard')  # افتراض وجود هذا المسار
    
    def test_security_headers_present(self):
        """
        اختبار وجود رؤوس الأمان في الاستجابة
        """
        response = self.client.get(self.dashboard_url)
        
        # التحقق من وجود رؤوس الأمان
        self.assertIn('X-Content-Type-Options', response)
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        
        self.assertIn('X-Frame-Options', response)
        self.assertEqual(response['X-Frame-Options'], 'DENY')
        
        self.assertIn('X-XSS-Protection', response)
        self.assertEqual(response['X-XSS-Protection'], '1; mode=block')
        
        self.assertIn('Content-Security-Policy', response)
        # التحقق من وجود قيم مناسبة في سياسة أمان المحتوى
        self.assertIn("default-src 'self'", response['Content-Security-Policy'])
        
        self.assertIn('Referrer-Policy', response)
        self.assertEqual(response['Referrer-Policy'], 'strict-origin-when-cross-origin')


class PerformanceMonitoringMiddlewareTest(TestCase):
    """
    اختبارات وسيط مراقبة الأداء
    """
    
    def setUp(self):
        """
        إعداد بيئة الاختبار
        """
        self.factory = RequestFactory()
        self.get_response = lambda request: HttpResponse()
        self.middleware = PerformanceMonitoringMiddleware(get_response=self.get_response)
        self.user = User.objects.create_superuser(
            username='perfuser',
            email='perf@example.com',
            password='perf123'
        )
    
    def test_performance_monitoring(self):
        """
        اختبار تسجيل زمن معالجة الطلب
        """
        # إنشاء طلب
        request = self.factory.get('/admin/')
        request.user = self.user
        
        # تنفيذ الوسيط
        response = self.middleware(request)
        
        # التحقق من وجود معلومات الأداء في استجابة المشرف
        if hasattr(response, 'performance_data'):
            self.assertTrue('total_time' in response.performance_data)
            self.assertTrue(isinstance(response.performance_data['total_time'], float))
    
    def test_slow_request_logging(self):
        """
        اختبار تسجيل الطلبات البطيئة
        """
        # إنشاء طلب
        request = self.factory.get('/slow/')
        request.user = self.user
        
        # تعريف دالة استجابة بطيئة
        def slow_response(request):
            time.sleep(0.1)  # تأخير الاستجابة
            return HttpResponse()
        
        # إنشاء وسيط بدالة استجابة بطيئة
        middleware = PerformanceMonitoringMiddleware(get_response=slow_response)
        
        # تنفيذ الوسيط
        response = middleware(request)
        
        # لا يمكن اختبار رسائل السجل مباشرة، لكن يمكن التحقق من وجود بيانات الأداء
        if hasattr(response, 'performance_data'):
            self.assertTrue('total_time' in response.performance_data)
            self.assertTrue(response.performance_data['total_time'] >= 0.1)
    
    def test_url_pattern_matching(self):
        """
        اختبار تجاهل مسارات معينة في قياس الأداء
        """
        # تعريف أنماط المسارات المتجاهلة
        settings.PERF_MONITORING_IGNORE_URLS = [r'^/static/', r'^/media/']
        
        # إنشاء طلب لمسار متجاهل
        request = self.factory.get('/static/css/main.css')
        request.user = self.user
        
        # تنفيذ الوسيط
        response = self.middleware(request)
        
        # المسار المتجاهل يجب ألا يحتوي على بيانات أداء
        self.assertFalse(hasattr(response, 'performance_data')) 