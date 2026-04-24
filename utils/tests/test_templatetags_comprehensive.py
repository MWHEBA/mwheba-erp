from django.test import TestCase
from django.template import Context, Template
from django.contrib.auth import get_user_model
from decimal import Decimal
import datetime

User = get_user_model()


class UtilsExtrasTemplateTagsTest(TestCase):
    """اختبارات template tags في utils_extras - مبسطة"""
    
    def test_remove_trailing_zeros_filter(self):
        """اختبار فلتر إزالة الأصفار الزائدة"""
        template = Template('{% load utils_extras %}{{ value|remove_trailing_zeros }}')
        
        # اختبارات أساسية فقط
        test_cases = [
            (Decimal('10.00'), '10'),
            (Decimal('10.50'), '10.5'),
            (1000, '1,000'),
        ]
        
        for input_value, expected in test_cases:
            context = Context({'value': input_value})
            rendered = template.render(context)
            self.assertEqual(rendered.strip(), expected)
    
    def test_currency_filter(self):
        """اختبار فلتر تنسيق العملة"""
        template = Template('{% load utils_extras %}{{ value|currency }}')
        
        context = Context({'value': Decimal('1234.56')})
        rendered = template.render(context)
        self.assertIn(',', rendered)
    
    def test_multiply_filter(self):
        """اختبار فلتر الضرب"""
        template = Template('{% load utils_extras %}{{ value|multiply:factor }}')
        
        context = Context({'value': 10, 'factor': 5})
        rendered = template.render(context)
        self.assertEqual(rendered.strip(), '50')


class AppTagsTemplateTagsTest(TestCase):
    """اختبارات template tags في app_tags - مبسطة"""
    
    def test_getattr_filter(self):
        """اختبار فلتر الحصول على خاصية من كائن"""
        template = Template('{% load app_tags %}{{ obj|get_attr:"name" }}')
        
        class TestObj:
            name = "اختبار"
            
        context = Context({'obj': TestObj()})
        rendered = template.render(context)
        self.assertEqual(rendered.strip(), "اختبار")
    
    def test_currency_filter_app_tags(self):
        """اختبار فلتر تنسيق العملة في app_tags"""
        template = Template('{% load app_tags %}{{ value|currency }}')
        
        context = Context({'value': 1234})
        rendered = template.render(context)
        self.assertIn(',', rendered)
            (100, 0, 0),  # قسمة على صفر
            (0, 5, 0.0),
            ('invalid', 5, 0),  # قيمة غير صحيحة
        ]
        
        for value, divisor, expected in test_cases:
            with self.subTest(value=value, divisor=divisor):
                context = Context({'value': value, 'divisor': divisor})
                rendered = template.render(context)
                self.assertEqual(float(rendered.strip()), expected)
    
    def test_percentage_filter(self):
        """اختبار فلتر حساب النسبة المئوية"""
        template = Template('{% load utils_extras %}{{ part|percentage:total }}')
        
        test_cases = [
            (25, 100, '25.00'),
            (50, 200, '25.00'),
            (0, 100, '0.00'),
            (25, 0, '0.00'),  # قسمة على صفر
        ]
        
        for part, total, expected in test_cases:
            with self.subTest(part=part, total=total):
                context = Context({'part': part, 'total': total})
                rendered = template.render(context)
                self.assertEqual(rendered.strip(), expected)
    
    def test_status_badge_filter(self):
        """اختبار فلتر عرض الحالة كـ badge"""
        template = Template('{% load utils_extras %}{{ status|status_badge }}')
        
        test_cases = [

