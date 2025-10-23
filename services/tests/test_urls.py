from django.test import TestCase
from django.urls import reverse, resolve
from django.contrib.auth import get_user_model
from services import views

User = get_user_model()


class ServicesUrlsTest(TestCase):
    """اختبارات URLs الخدمات"""
    
    def setUp(self):
        """إعداد البيانات الأساسية للاختبار"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
    
    def test_services_home_url(self):
        """اختبار URL الصفحة الرئيسية للخدمات"""
        url = reverse('services:services_home')
        self.assertEqual(url, '/services/')
        
        # اختبار resolve
        resolver = resolve('/services/')
        self.assertEqual(resolver.view_name, 'services:services_home')
        self.assertEqual(resolver.func, views.services_home)
    
    def test_category_detail_url(self):
        """اختبار URL تفاصيل الفئة"""
        slug = 'test-category'
        url = reverse('services:category_detail', kwargs={'slug': slug})
        self.assertEqual(url, f'/services/{slug}/')
        
        # اختبار resolve
        resolver = resolve(f'/services/{slug}/')
        self.assertEqual(resolver.view_name, 'services:category_detail')
        self.assertEqual(resolver.func, views.category_detail)
        self.assertEqual(resolver.kwargs['slug'], slug)
    
    def test_url_patterns_count(self):
        """اختبار عدد أنماط URLs"""
        from services.urls import urlpatterns
        
        # يجب أن يكون هناك نمطان
        self.assertEqual(len(urlpatterns), 2)
    
    def test_app_name(self):
        """اختبار اسم التطبيق في URLs"""
        from services.urls import app_name
        
        self.assertEqual(app_name, 'services')
    
    def test_url_names(self):
        """اختبار أسماء URLs"""
        # اختبار أن جميع الأسماء صحيحة
        url_names = ['services_home', 'category_detail']
        
        for name in url_names:
            try:
                url = reverse(f'services:{name}', kwargs={'slug': 'test'} if name == 'category_detail' else {})
                self.assertIsNotNone(url)
            except Exception as e:
                if name != 'category_detail':  # category_detail يحتاج slug
                    self.fail(f"فشل في إنشاء URL لـ {name}: {e}")
    
    def test_category_detail_with_special_characters(self):
        """اختبار URL مع أحرف خاصة في slug"""
        special_slugs = [
            'test-category-123',
            'category_with_underscore',
            'arabic-slug',
            'multi-word-category'
        ]
        
        for slug in special_slugs:
            url = reverse('services:category_detail', kwargs={'slug': slug})
            self.assertEqual(url, f'/services/{slug}/')
            
            # اختبار resolve
            resolver = resolve(f'/services/{slug}/')
            self.assertEqual(resolver.kwargs['slug'], slug)
    
    def test_url_accessibility(self):
        """اختبار إمكانية الوصول للـ URLs"""
        self.client.login(username='testuser', password='testpass123')
        
        # اختبار الصفحة الرئيسية
        home_url = reverse('services:services_home')
        response = self.client.get(home_url)
        self.assertEqual(response.status_code, 200)
        
        # اختبار صفحة تفاصيل الفئة (404 متوقع لعدم وجود الفئة)
        detail_url = reverse('services:category_detail', kwargs={'slug': 'nonexistent'})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 404)
    
    def test_url_without_login(self):
        """اختبار URLs بدون تسجيل دخول"""
        # اختبار الصفحة الرئيسية
        home_url = reverse('services:services_home')
        response = self.client.get(home_url)
        self.assertEqual(response.status_code, 302)  # إعادة توجيه لصفحة تسجيل الدخول
        
        # اختبار صفحة تفاصيل الفئة
        detail_url = reverse('services:category_detail', kwargs={'slug': 'test'})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 302)  # إعادة توجيه لصفحة تسجيل الدخول
