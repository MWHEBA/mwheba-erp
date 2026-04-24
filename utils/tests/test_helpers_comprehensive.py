from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from decimal import Decimal
import datetime
import json

# استيراد المساعدات المتاحة فعلياً
from utils.helpers import (
    arabic_slugify, generate_random_code, format_currency,
    calculate_vat, arabic_date_format, get_current_fiscal_year,
    arabic_text_to_html, validate_egyptian_phone, is_arabic_text,
    calculate_age, format_age_in_years_months
)

User = get_user_model()


class HelpersTest(TestCase):
    """اختبارات الدوال المساعدة العامة"""
    
    def test_generate_random_code(self):
        """اختبار إنشاء كود عشوائي"""
        # اختبار كود بدون بادئة
        code1 = generate_random_code()
        self.assertIsInstance(code1, str)
        self.assertEqual(len(code1), 8)  # الطول الافتراضي
        
        # اختبار كود مع بادئة
        code2 = generate_random_code(prefix='INV')
        self.assertTrue(code2.startswith('INV'))
        
        # اختبار طول مخصص
        code3 = generate_random_code(length=10)
        self.assertEqual(len(code3), 10)
        
        # اختبار أرقام فقط
        code4 = generate_random_code(digits_only=True)
        self.assertTrue(code4.isdigit())
        
        # التحقق من الفرادة
        code5 = generate_random_code()
        self.assertNotEqual(code1, code5)
    
    def test_validate_egyptian_phone(self):
        """اختبار التحقق من رقم الهاتف المصري"""
        valid_phones = [
            '01234567890',
            '01012345678',
            '01112345678',
            '01212345678',
        ]
        
        invalid_phones = [
            '123456789',  # قصير جداً
            '012345678901',  # طويل جداً
            '02123456789',  # لا يبدأ بـ 01
            'abc1234567890',  # يحتوي على أحرف
            '',  # فارغ
            None,  # None
        ]
        
        for phone in valid_phones:
            self.assertTrue(validate_egyptian_phone(phone), f"Phone {phone} should be valid")
        
        for phone in invalid_phones:
            self.assertFalse(validate_egyptian_phone(phone), f"Phone {phone} should be invalid")
    
    def test_format_currency(self):
        """اختبار تنسيق العملة"""
        from decimal import Decimal
        
        test_cases = [
            (Decimal('1234.56'), '1,234.56'),
            (Decimal('1000.00'), '1,000'),
            (Decimal('500.50'), '500.50'),
            (1000, '1,000'),
            (1500.75, '1,500.75'),
            (0, '0'),
        ]
        
        for amount, expected_pattern in test_cases:
            formatted = format_currency(amount)
            # التحقق من وجود الفواصل للأرقام الكبيرة
            if float(amount) >= 1000:
                self.assertIn(',', formatted)
    
    def test_calculate_vat(self):
        """اختبار حساب ضريبة القيمة المضافة"""
        # حالات عادية
        self.assertEqual(calculate_vat(100, 15), 15.0)
        self.assertEqual(calculate_vat(200, 10), 20.0)
        
        # حالة معدل افتراضي (15%)
        self.assertEqual(calculate_vat(100), 15.0)
        
        # حالة مبلغ صفر
        self.assertEqual(calculate_vat(0), 0)
    
    def test_arabic_date_format(self):
        """اختبار تنسيق التاريخ بالعربية"""
        import datetime
        
        test_date = datetime.date(2024, 1, 15)
        
        # تنسيق بدون وقت
        formatted = arabic_date_format(test_date)
        self.assertIn('يناير', formatted)
        self.assertIn('2024', formatted)
        self.assertIn('15', formatted)
        
        # تنسيق مع الوقت
        test_datetime = datetime.datetime(2024, 1, 15, 14, 30)
        formatted_with_time = arabic_date_format(test_datetime, with_time=True)
        self.assertIn('يناير', formatted_with_time)
        self.assertIn('14:30', formatted_with_time)
    
    def test_is_arabic_text(self):
        """اختبار التحقق من النص العربي"""
        arabic_texts = [
            'النص العربي',
            'مرحبا بك',
            'Mixed نص عربي',
        ]
        
        non_arabic_texts = [
            'English text',
            '123456',
            '',
            None,
        ]
        
        for text in arabic_texts:
            self.assertTrue(is_arabic_text(text))
        
        for text in non_arabic_texts:
            self.assertFalse(is_arabic_text(text))
    
    def test_calculate_age(self):
        """اختبار حساب العمر"""
        import datetime
        from django.utils import timezone
        
        # تاريخ ميلاد قبل 25 سنة
        birth_date = timezone.now().date() - datetime.timedelta(days=25*365)
        age = calculate_age(birth_date)
        self.assertGreaterEqual(age, 24)
        self.assertLessEqual(age, 26)
        
        # تاريخ ميلاد فارغ
        self.assertEqual(calculate_age(None), 0)
    
    def test_arabic_slugify(self):
        """اختبار إنشاء slug للنص العربي"""
        test_cases = [
            ('النص العربي', 'النص-العربي'),
            ('المنتج الجديد', 'المنتج-الجديد'),
            ('English Text', 'english-text'),
            ('', ''),
        ]
        
        for input_text, expected_pattern in test_cases:
            slug = arabic_slugify(input_text)
            if input_text and ' ' in input_text:
                self.assertIn('-', slug)
            # التحقق من عدم وجود مسافات
            self.assertNotIn(' ', slug)
    
    def test_format_age_in_years_months(self):
        """اختبار تنسيق العمر بالسنين والشهور"""
        test_cases = [
            (0, '0 شهر'),
            (1, '1 شهر'),
            (12, 'سنة واحدة'),
            (24, 'سنتان'),
            (25, 'سنتان و شهر واحد'),
            (36, '3 سنوات'),
        ]
        
        for age_months, expected_pattern in test_cases:
            result = format_age_in_years_months(age_months)
            # التحقق من وجود كلمات عربية مناسبة
            if age_months == 0:
                self.assertIn('شهر', result)
            elif age_months >= 12:
                self.assertTrue('سنة' in result or 'سنوات' in result or 'سنتان' in result)
    
    def test_get_current_fiscal_year(self):
        """اختبار الحصول على السنة المالية الحالية"""
        start_date, end_date = get_current_fiscal_year()
        
        # التحقق من أن التواريخ صحيحة
        self.assertIsInstance(start_date, datetime.date)
        self.assertIsInstance(end_date, datetime.date)
        self.assertLess(start_date, end_date)
        
        # التحقق من أن الفترة سنة كاملة تقريباً
        diff = end_date - start_date
        self.assertGreaterEqual(diff.days, 364)
        self.assertLessEqual(diff.days, 366)


class RequestHelpersTest(TestCase):
    """اختبارات مساعدات الطلبات"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
    
    def test_arabic_text_to_html(self):
        """اختبار تحويل النص العربي إلى HTML"""
        text = "هذا نص عربي\nسطر جديد"
        html = arabic_text_to_html(text)
        
        # التحقق من وجود اتجاه النص
        self.assertIn('dir="rtl"', html)
        # التحقق من تحويل السطور الجديدة
        self.assertIn('<br>', html)
        # التحقق من وجود النص الأصلي
        self.assertIn('هذا نص عربي', html)


class DataHelpersTest(TestCase):
    """اختبارات مساعدات البيانات"""
    
    def test_format_currency_advanced(self):
        """اختبار تنسيق العملة المتقدم"""
        from decimal import Decimal
        
        # اختبار مع رمز العملة
        formatted = format_currency(1000, currency="ج.م")
        self.assertIn("1,000", formatted)
        self.assertIn("ج.م", formatted)
        
        # اختبار مع عملة دولارية
        formatted_usd = format_currency(1500.50, currency="$")
        self.assertIn("$1,500.50", formatted_usd)
        
        # اختبار مع منازل عشرية مخصصة
        formatted_custom = format_currency(1234.5678, decimal_places=3)
        self.assertIn("1,234.568", formatted_custom)


class ValidationHelpersTest(TestCase):
    """اختبارات مساعدات التحقق"""
    
    def test_validate_egyptian_phone_comprehensive(self):
        """اختبار شامل للتحقق من رقم الهاتف المصري"""
        # أرقام صحيحة
        valid_phones = [
            '01234567890',
            '01012345678',
            '01112345678',
            '01212345678',
            '01512345678',
        ]
        
        # أرقام غير صحيحة
        invalid_phones = [
            '123456789',      # قصير جداً
            '012345678901',   # طويل جداً
            '02123456789',    # لا يبدأ بـ 01
            'abc1234567890',  # يحتوي على أحرف
            '00123456789',    # يبدأ بـ 00
            '',               # فارغ
            None,             # None
        ]
        
        for phone in valid_phones:
            self.assertTrue(validate_egyptian_phone(phone), f"Phone {phone} should be valid")
        
        for phone in invalid_phones:
            self.assertFalse(validate_egyptian_phone(phone), f"Phone {phone} should be invalid")


class FileHelpersTest(TestCase):
    """اختبارات مساعدات الملفات"""
    
    def test_arabic_text_to_html_advanced(self):
        """اختبار متقدم لتحويل النص العربي إلى HTML"""
        # نص فارغ
        self.assertEqual(arabic_text_to_html(""), "")
        self.assertEqual(arabic_text_to_html(None), "")
        
        # نص بسيط
        simple_text = "مرحبا"
        html = arabic_text_to_html(simple_text)
        self.assertIn('dir="rtl"', html)
        self.assertIn('مرحبا', html)
        
        # نص متعدد الأسطر
        multiline_text = "السطر الأول\nالسطر الثاني"
        html_multiline = arabic_text_to_html(multiline_text)
        self.assertIn('<br>', html_multiline)


class CacheHelpersTest(TestCase):
    """اختبارات مساعدات التخزين المؤقت"""
    
    def test_format_currency_edge_cases(self):
        """اختبار حالات حدية لتنسيق العملة"""
        # قيم غير صالحة
        self.assertEqual(format_currency("invalid"), "0")
        self.assertEqual(format_currency(None), "0")
        
        # قيم صفر
        self.assertEqual(format_currency(0), "0")
        self.assertEqual(format_currency("0"), "0")
        
        # أرقام سالبة
        negative_result = format_currency(-1000)
        self.assertIn("-1,000", negative_result)


class SecurityHelpersTest(TestCase):
    """اختبارات مساعدات الأمان"""
    
    def test_is_arabic_text_comprehensive(self):
        """اختبار شامل للتحقق من النص العربي"""
        # نصوص عربية
        arabic_texts = [
            'النص العربي',
            'مرحبا بك في النظام',
            'Mixed نص عربي and English',
            'أ',  # حرف واحد
        ]
        
        # نصوص غير عربية
        non_arabic_texts = [
            'English text only',
            '123456789',
            '!@#$%^&*()',
            '',
            None,
            'français',
            'русский',
        ]
        
        for text in arabic_texts:
            self.assertTrue(is_arabic_text(text), f"Text '{text}' should be detected as Arabic")
        
        for text in non_arabic_texts:
            self.assertFalse(is_arabic_text(text), f"Text '{text}' should not be detected as Arabic")


class PerformanceHelpersTest(TestCase):
    """اختبارات مساعدات الأداء"""
    
    def test_calculate_age_edge_cases(self):
        """اختبار حالات حدية لحساب العمر"""
        import datetime
        from django.utils import timezone
        
        today = timezone.now().date()
        
        # تاريخ ميلاد اليوم (عمر 0)
        age_today = calculate_age(today)
        self.assertEqual(age_today, 0)
        
        # تاريخ ميلاد بالأمس (عمر 0)
        yesterday = today - datetime.timedelta(days=1)
        age_yesterday = calculate_age(yesterday)
        self.assertEqual(age_yesterday, 0)
        
        # تاريخ ميلاد قبل سنة بالضبط
        one_year_ago = today.replace(year=today.year - 1)
        age_one_year = calculate_age(one_year_ago)
        self.assertEqual(age_one_year, 1)
        
        # تاريخ ميلاد في المستقبل (يجب أن يعطي عمر سالب أو صفر)
        future_date = today + datetime.timedelta(days=365)
        age_future = calculate_age(future_date)
        self.assertLessEqual(age_future, 0)
    
    def test_format_age_comprehensive(self):
        """اختبار شامل لتنسيق العمر"""
        test_cases = [
            (-1, '0 شهر'),  # عمر سالب
            (0, '0 شهر'),
            (1, '1 شهر'),
            (2, '2 شهر'),
            (11, '11 شهر'),
            (12, 'سنة واحدة'),
            (13, 'سنة واحدة و شهر واحد'),
            (24, 'سنتان'),
            (25, 'سنتان و شهر واحد'),
            (26, 'سنتان و شهران'),
            (36, '3 سنوات'),
            (37, '3 سنوات و شهر واحد'),
            (120, '10 سنوات'),  # 10 سنوات
            (132, '11 سنة'),    # أكثر من 10 سنوات
        ]
        
        for age_months, expected_pattern in test_cases:
            result = format_age_in_years_months(age_months)
            self.assertIsInstance(result, str)
            # التحقق من وجود كلمات عربية مناسبة
            if age_months <= 0:
                self.assertIn('شهر', result)
            elif age_months < 12:
                self.assertIn('شهر', result)
            else:
                # يجب أن يحتوي على كلمة سنة أو سنوات أو سنتان
                self.assertTrue(any(word in result for word in ['سنة', 'سنوات', 'سنتان']))
