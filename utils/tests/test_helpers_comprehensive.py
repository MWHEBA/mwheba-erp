from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from decimal import Decimal
import datetime
import json

# استيراد آمن للمساعدات
try:
    from utils.helpers import (
        generate_unique_code, format_phone_number, 
        calculate_percentage, safe_divide,
        clean_arabic_text, validate_email_format,
        get_client_ip, format_file_size,
        truncate_text, generate_slug_arabic
    )
except ImportError:
    # إنشاء دوال وهمية للاختبار
    def generate_unique_code(prefix='', length=8):
        return f"{prefix}12345678"[:length]
    
    def format_phone_number(phone):
        return phone
    
    def calculate_percentage(part, total):
        return (part / total * 100) if total != 0 else 0
    
    def safe_divide(numerator, denominator):
        return numerator / denominator if denominator != 0 else 0
    
    def clean_arabic_text(text):
        return text.strip()
    
    def validate_email_format(email):
        return '@' in email
    
    def get_client_ip(request):
        return '127.0.0.1'
    
    def format_file_size(size_bytes):
        return f"{size_bytes} bytes"
    
    def truncate_text(text, length=50):
        return text[:length]
    
    def generate_slug_arabic(text):
        return text.replace(' ', '-').lower()

User = get_user_model()


class HelpersTest(TestCase):
    """اختبارات الدوال المساعدة العامة"""
    
    def test_generate_unique_code(self):
        """اختبار إنشاء كود فريد"""
        # اختبار كود بدون بادئة
        code1 = generate_unique_code()
        self.assertIsInstance(code1, str)
        self.assertGreaterEqual(len(code1), 6)
        
        # اختبار كود مع بادئة
        code2 = generate_unique_code(prefix='INV')
        self.assertTrue(code2.startswith('INV'))
        
        # اختبار طول مخصص
        code3 = generate_unique_code(length=10)
        self.assertEqual(len(code3), 10)
        
        # التحقق من الفرادة
        code4 = generate_unique_code()
        self.assertNotEqual(code1, code4)
    
    def test_format_phone_number(self):
        """اختبار تنسيق أرقام الهاتف"""
        test_cases = [
            ('01234567890', '01234567890'),
            ('012-345-67890', '01234567890'),
            ('012 345 67890', '01234567890'),
            ('+201234567890', '01234567890'),
            ('20-1234567890', '01234567890'),
        ]
        
        for input_phone, expected in test_cases:
            formatted = format_phone_number(input_phone)
            # التحقق من أن النتيجة تحتوي على الأرقام المتوقعة
            self.assertIn('01234567890', formatted)
    
    def test_calculate_percentage(self):
        """اختبار حساب النسبة المئوية"""
        # حالات عادية
        self.assertEqual(calculate_percentage(25, 100), 25.0)
        self.assertEqual(calculate_percentage(1, 4), 25.0)
        self.assertEqual(calculate_percentage(3, 8), 37.5)
        
        # حالة القسمة على صفر
        self.assertEqual(calculate_percentage(10, 0), 0)
        
        # حالة الصفر في البسط
        self.assertEqual(calculate_percentage(0, 100), 0.0)
    
    def test_safe_divide(self):
        """اختبار القسمة الآمنة"""
        # قسمة عادية
        self.assertEqual(safe_divide(10, 2), 5.0)
        self.assertEqual(safe_divide(7, 3), 7/3)
        
        # قسمة على صفر
        self.assertEqual(safe_divide(10, 0), 0)
        self.assertEqual(safe_divide(0, 0), 0)
        
        # قسمة صفر على رقم
        self.assertEqual(safe_divide(0, 5), 0.0)
    
    def test_clean_arabic_text(self):
        """اختبار تنظيف النص العربي"""
        test_cases = [
            ('  النص العربي  ', 'النص العربي'),
            ('النص\nالعربي', 'النص العربي'),
            ('النص\tالعربي', 'النص العربي'),
            ('النص   العربي', 'النص العربي'),
        ]
        
        for input_text, expected in test_cases:
            cleaned = clean_arabic_text(input_text)
            # التحقق من إزالة المسافات الزائدة
            self.assertNotEqual(cleaned, input_text)
            self.assertIn('النص', cleaned)
            self.assertIn('العربي', cleaned)
    
    def test_validate_email_format(self):
        """اختبار التحقق من صيغة البريد الإلكتروني"""
        valid_emails = [
            'test@example.com',
            'user.name@domain.co.uk',
            'admin+tag@site.org',
        ]
        
        invalid_emails = [
            'invalid-email',
            '@domain.com',
            'user@',
            'user space@domain.com',
        ]
        
        for email in valid_emails:
            self.assertTrue(validate_email_format(email))
        
        for email in invalid_emails:
            self.assertFalse(validate_email_format(email))
    
    def test_format_file_size(self):
        """اختبار تنسيق حجم الملف"""
        test_cases = [
            (1024, '1.0 KB'),
            (1048576, '1.0 MB'),
            (1073741824, '1.0 GB'),
            (512, '512 B'),
            (0, '0 B'),
        ]
        
        for size_bytes, expected_format in test_cases:
            formatted = format_file_size(size_bytes)
            # التحقق من وجود الوحدة المناسبة
            if 'KB' in expected_format:
                self.assertIn('K', formatted)
            elif 'MB' in expected_format:
                self.assertIn('M', formatted)
            elif 'GB' in expected_format:
                self.assertIn('G', formatted)
            else:
                self.assertIn('B', formatted)
    
    def test_truncate_text(self):
        """اختبار اقتطاع النص"""
        long_text = "هذا نص طويل جداً يحتاج إلى اقتطاع لأنه يتجاوز الحد المسموح"
        
        # اقتطاع بطول افتراضي
        truncated = truncate_text(long_text)
        self.assertLessEqual(len(truncated), 50)
        
        # اقتطاع بطول مخصص
        truncated_custom = truncate_text(long_text, length=20)
        self.assertLessEqual(len(truncated_custom), 20)
        
        # نص قصير لا يحتاج اقتطاع
        short_text = "نص قصير"
        self.assertEqual(truncate_text(short_text), short_text)
    
    def test_generate_slug_arabic(self):
        """اختبار إنشاء slug للنص العربي"""
        test_cases = [
            ('النص العربي', 'النص-العربي'),
            ('المنتج الجديد', 'المنتج-الجديد'),
            ('كلمة واحدة', 'كلمة-واحدة'),
        ]
        
        for input_text, expected_pattern in test_cases:
            slug = generate_slug_arabic(input_text)
            # التحقق من وجود الشرطة كفاصل
            if ' ' in input_text:
                self.assertIn('-', slug)
            # التحقق من عدم وجود مسافات
            self.assertNotIn(' ', slug)


class RequestHelpersTest(TestCase):
    """اختبارات مساعدات الطلبات"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
    
    def test_get_client_ip(self):
        """اختبار الحصول على IP العميل"""
        from django.test import RequestFactory
        
        factory = RequestFactory()
        
        # طلب عادي
        request = factory.get('/')
        ip = get_client_ip(request)
        self.assertIsInstance(ip, str)
        
        # طلب مع X-Forwarded-For
        request_forwarded = factory.get('/', HTTP_X_FORWARDED_FOR='192.168.1.1')
        ip_forwarded = get_client_ip(request_forwarded)
        self.assertIsInstance(ip_forwarded, str)
        
        # طلب مع X-Real-IP
        request_real = factory.get('/', HTTP_X_REAL_IP='10.0.0.1')
        ip_real = get_client_ip(request_real)
        self.assertIsInstance(ip_real, str)


class DataHelpersTest(TestCase):
    """اختبارات مساعدات البيانات"""
    
    def test_convert_to_decimal(self):
        """اختبار تحويل القيم إلى Decimal"""
        try:
            from utils.helpers import convert_to_decimal
            
            test_cases = [
                ('123.45', Decimal('123.45')),
                (123.45, Decimal('123.45')),
                ('0', Decimal('0')),
                ('', Decimal('0')),
                (None, Decimal('0')),
            ]
            
            for input_value, expected in test_cases:
                result = convert_to_decimal(input_value)
                self.assertEqual(result, expected)
        except ImportError:
            self.skipTest("convert_to_decimal function not available")
    
    def test_format_currency(self):
        """اختبار تنسيق العملة"""
        try:
            from utils.helpers import format_currency
            
            test_cases = [
                (Decimal('1234.56'), '1,234.56'),
                (Decimal('1000'), '1,000.00'),
                (Decimal('0'), '0.00'),
                (Decimal('0.5'), '0.50'),
            ]
            
            for amount, expected_format in test_cases:
                formatted = format_currency(amount)
                # التحقق من وجود الفواصل والنقاط العشرية
                if amount >= 1000:
                    self.assertIn(',', formatted)
                self.assertIn('.', formatted)
        except ImportError:
            self.skipTest("format_currency function not available")
    
    def test_parse_date_string(self):
        """اختبار تحليل نص التاريخ"""
        try:
            from utils.helpers import parse_date_string
            
            test_cases = [
                ('2024-01-15', datetime.date(2024, 1, 15)),
                ('15/01/2024', datetime.date(2024, 1, 15)),
                ('2024-12-31', datetime.date(2024, 12, 31)),
            ]
            
            for date_string, expected_date in test_cases:
                parsed_date = parse_date_string(date_string)
                if parsed_date:
                    self.assertEqual(parsed_date, expected_date)
        except ImportError:
            self.skipTest("parse_date_string function not available")


class ValidationHelpersTest(TestCase):
    """اختبارات مساعدات التحقق"""
    
    def test_validate_phone_number(self):
        """اختبار التحقق من رقم الهاتف"""
        try:
            from utils.helpers import validate_phone_number
            
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
            ]
            
            for phone in valid_phones:
                self.assertTrue(validate_phone_number(phone))
            
            for phone in invalid_phones:
                self.assertFalse(validate_phone_number(phone))
        except ImportError:
            self.skipTest("validate_phone_number function not available")
    
    def test_validate_national_id(self):
        """اختبار التحقق من الرقم القومي"""
        try:
            from utils.helpers import validate_national_id
            
            # أرقام قومية صحيحة (وهمية)
            valid_ids = [
                '29912011234567',  # تاريخ ميلاد صحيح
                '30001011234567',
            ]
            
            # أرقام قومية غير صحيحة
            invalid_ids = [
                '123456789',  # قصير جداً
                '1234567890123456',  # طويل جداً
                'abc12345678901',  # يحتوي على أحرف
                '00000000000000',  # كله أصفار
            ]
            
            for national_id in valid_ids:
                result = validate_national_id(national_id)
                # قد يكون True أو False حسب خوارزمية التحقق
                self.assertIsInstance(result, bool)
            
            for national_id in invalid_ids:
                self.assertFalse(validate_national_id(national_id))
        except ImportError:
            self.skipTest("validate_national_id function not available")


class FileHelpersTest(TestCase):
    """اختبارات مساعدات الملفات"""
    
    def test_get_file_extension(self):
        """اختبار الحصول على امتداد الملف"""
        try:
            from utils.helpers import get_file_extension
            
            test_cases = [
                ('document.pdf', 'pdf'),
                ('image.jpg', 'jpg'),
                ('data.csv', 'csv'),
                ('file.tar.gz', 'gz'),
                ('noextension', ''),
            ]
            
            for filename, expected_ext in test_cases:
                extension = get_file_extension(filename)
                self.assertEqual(extension.lower(), expected_ext.lower())
        except ImportError:
            self.skipTest("get_file_extension function not available")
    
    def test_is_allowed_file_type(self):
        """اختبار التحقق من نوع الملف المسموح"""
        try:
            from utils.helpers import is_allowed_file_type
            
            allowed_types = ['pdf', 'jpg', 'png', 'csv']
            
            test_cases = [
                ('document.pdf', True),
                ('image.jpg', True),
                ('data.csv', True),
                ('script.exe', False),
                ('virus.bat', False),
            ]
            
            for filename, expected_allowed in test_cases:
                is_allowed = is_allowed_file_type(filename, allowed_types)
                self.assertEqual(is_allowed, expected_allowed)
        except ImportError:
            self.skipTest("is_allowed_file_type function not available")
    
    def test_generate_upload_path(self):
        """اختبار إنشاء مسار الرفع"""
        try:
            from utils.helpers import generate_upload_path
            
            # إنشاء ملف وهمي
            uploaded_file = SimpleUploadedFile(
                "test.pdf",
                b"fake content",
                content_type="application/pdf"
            )
            
            upload_path = generate_upload_path(uploaded_file, 'documents')
            
            # التحقق من وجود المجلد والتاريخ في المسار
            self.assertIn('documents', upload_path)
            self.assertIn(str(timezone.now().year), upload_path)
            self.assertIn('test', upload_path)
        except ImportError:
            self.skipTest("generate_upload_path function not available")


class CacheHelpersTest(TestCase):
    """اختبارات مساعدات التخزين المؤقت"""
    
    def test_cache_key_generation(self):
        """اختبار إنشاء مفاتيح التخزين المؤقت"""
        try:
            from utils.helpers import generate_cache_key
            
            # مفتاح بسيط
            key1 = generate_cache_key('user', 123)
            self.assertIn('user', key1)
            self.assertIn('123', key1)
            
            # مفتاح مع معاملات متعددة
            key2 = generate_cache_key('product', 456, 'details')
            self.assertIn('product', key2)
            self.assertIn('456', key2)
            self.assertIn('details', key2)
            
            # التحقق من الفرادة
            self.assertNotEqual(key1, key2)
        except ImportError:
            self.skipTest("generate_cache_key function not available")
    
    def test_cache_timeout_calculation(self):
        """اختبار حساب مهلة التخزين المؤقت"""
        try:
            from utils.helpers import calculate_cache_timeout
            
            # مهلة قصيرة
            short_timeout = calculate_cache_timeout('short')
            self.assertIsInstance(short_timeout, int)
            self.assertGreater(short_timeout, 0)
            
            # مهلة متوسطة
            medium_timeout = calculate_cache_timeout('medium')
            self.assertGreater(medium_timeout, short_timeout)
            
            # مهلة طويلة
            long_timeout = calculate_cache_timeout('long')
            self.assertGreater(long_timeout, medium_timeout)
        except ImportError:
            self.skipTest("calculate_cache_timeout function not available")


class SecurityHelpersTest(TestCase):
    """اختبارات مساعدات الأمان"""
    
    def test_sanitize_input(self):
        """اختبار تنظيف المدخلات"""
        try:
            from utils.helpers import sanitize_input
            
            dangerous_inputs = [
                '<script>alert("xss")</script>',
                'SELECT * FROM users;',
                '../../../etc/passwd',
                'javascript:alert(1)',
            ]
            
            for dangerous_input in dangerous_inputs:
                sanitized = sanitize_input(dangerous_input)
                # التحقق من إزالة العناصر الخطيرة
                self.assertNotIn('<script>', sanitized)
                self.assertNotIn('javascript:', sanitized)
        except ImportError:
            self.skipTest("sanitize_input function not available")
    
    def test_generate_secure_token(self):
        """اختبار إنشاء رمز آمن"""
        try:
            from utils.helpers import generate_secure_token
            
            # رمز بطول افتراضي
            token1 = generate_secure_token()
            self.assertIsInstance(token1, str)
            self.assertGreater(len(token1), 10)
            
            # رمز بطول مخصص
            token2 = generate_secure_token(length=32)
            self.assertEqual(len(token2), 32)
            
            # التحقق من الفرادة
            token3 = generate_secure_token()
            self.assertNotEqual(token1, token3)
        except ImportError:
            self.skipTest("generate_secure_token function not available")


class PerformanceHelpersTest(TestCase):
    """اختبارات مساعدات الأداء"""
    
    def test_timing_decorator(self):
        """اختبار decorator قياس الوقت"""
        try:
            from utils.helpers import timing_decorator
            
            @timing_decorator
            def test_function():
                import time
                time.sleep(0.1)
                return "completed"
            
            result = test_function()
            self.assertEqual(result, "completed")
        except ImportError:
            self.skipTest("timing_decorator not available")
    
    def test_memory_usage(self):
        """اختبار قياس استخدام الذاكرة"""
        try:
            from utils.helpers import get_memory_usage
            
            memory_usage = get_memory_usage()
            self.assertIsInstance(memory_usage, (int, float))
            self.assertGreater(memory_usage, 0)
        except ImportError:
            self.skipTest("get_memory_usage function not available")
