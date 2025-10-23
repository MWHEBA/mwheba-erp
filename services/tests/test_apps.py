from django.test import TestCase
from django.apps import apps
from services.apps import ServicesConfig


class ServicesConfigTest(TestCase):
    """اختبارات تكوين تطبيق الخدمات"""
    
    def test_app_config(self):
        """اختبار إعدادات التطبيق"""
        app_config = apps.get_app_config('services')
        
        # التحقق من أن التطبيق مسجل بشكل صحيح
        self.assertIsInstance(app_config, ServicesConfig)
        self.assertEqual(app_config.name, 'services')
        self.assertEqual(app_config.verbose_name, 'الخدمات المتخصصة')
        self.assertEqual(app_config.default_auto_field, 'django.db.models.BigAutoField')
    
    def test_app_ready(self):
        """اختبار أن التطبيق جاهز للاستخدام"""
        app_config = apps.get_app_config('services')
        
        # التحقق من أن التطبيق في حالة جاهزة
        self.assertTrue(apps.ready)
        self.assertIn('services', [app.name for app in apps.get_app_configs()])
    
    def test_app_models(self):
        """اختبار نماذج التطبيق"""
        app_config = apps.get_app_config('services')
        
        # التطبيق لا يحتوي على نماذج خاصة به
        models = app_config.get_models()
        self.assertEqual(len(models), 0)
    
    def test_app_label(self):
        """اختبار تسمية التطبيق"""
        app_config = apps.get_app_config('services')
        
        self.assertEqual(app_config.label, 'services')
    
    def test_app_path(self):
        """اختبار مسار التطبيق"""
        app_config = apps.get_app_config('services')
        
        # التحقق من أن المسار صحيح
        self.assertTrue(app_config.path.endswith('services'))
    
    def test_verbose_name_translation(self):
        """اختبار ترجمة الاسم المعروض"""
        app_config = apps.get_app_config('services')
        
        # التحقق من أن الاسم باللغة العربية
        self.assertEqual(app_config.verbose_name, 'الخدمات المتخصصة')
        self.assertIn('خدمات', app_config.verbose_name)
        self.assertIn('متخصصة', app_config.verbose_name)
