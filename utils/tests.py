from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal
import json
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.defaultfilters import slugify
import random
import string
from .models import SystemLog
from .logs import create_log, get_logs
import tempfile
import os
from django.conf import settings
import uuid

User = get_user_model()

def random_email(prefix='test'):
    """توليد بريد إلكتروني عشوائي فريد"""
    random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{prefix}_{random_str}@example.com"

# دالة مساعدة لإنشاء بريد إلكتروني فريد
def get_unique_email(prefix):
    """
    إنشاء عنوان بريد إلكتروني فريد باستخدام معرف UUID
    """
    unique_id = str(uuid.uuid4())[:8]
    return f"{prefix}_{unique_id}@example.com"

class HelperFunctionsTest(TestCase):
    """
    اختبارات الوظائف المساعدة
    """
    
    def test_arabic_slugify(self):
        """
        اختبار تحويل النص العربي إلى slug
        """
        from utils.helpers import arabic_slugify
        
        # تحويل نص عربي إلى slug
        arabic_text = "منتج جديد للبيع"
        slug = arabic_slugify(arabic_text)
        # التحقق من أن الـ slug لا يحتوي على مسافات أو أحرف خاصة
        self.assertFalse(' ' in slug)
        self.assertTrue('-' in slug)
        
        # التحقق من تحويل الأحرف الكبيرة إلى صغيرة
        english_text = "New Product FOR SALE"
        slug = arabic_slugify(english_text)
        self.assertEqual(slug, "new-product-for-sale")
        
        # التحقق من تعامل الدالة مع الأرقام
        mixed_text = "منتج رقم 123"
        slug = arabic_slugify(mixed_text)
        self.assertTrue('123' in slug)
    
    def test_generate_random_code(self):
        """
        اختبار توليد كود عشوائي
        """
        from utils.helpers import generate_random_code
        
        # توليد كود بطول افتراضي
        code = generate_random_code()
        self.assertEqual(len(code), 8)  # افتراض طول افتراضي 8
        
        # توليد كود بطول محدد
        code = generate_random_code(length=12)
        self.assertEqual(len(code), 12)
        
        # توليد كود يتكون من أحرف فقط
        code = generate_random_code(digits_only=False)
        self.assertTrue(any(c.isalpha() for c in code))
        
        # توليد كود يتكون من أرقام فقط
        code = generate_random_code(digits_only=True)
        self.assertTrue(all(c.isdigit() for c in code))
        
        # التحقق من عدم تكرار الأكواد المولدة
        codes = [generate_random_code() for _ in range(100)]
        self.assertEqual(len(codes), len(set(codes)))
    
    def test_format_currency(self):
        """
        اختبار تنسيق العملة
        """
        from utils.helpers import format_currency
        
        # تنسيق رقم صحيح
        value = 1000
        formatted = format_currency(value)
        self.assertEqual(formatted, "1,000.00")
        
        # تنسيق رقم عشري
        value = 1234.56
        formatted = format_currency(value)
        self.assertEqual(formatted, "1,234.56")
        
        # تنسيق مع عملة
        value = 1000
        formatted = format_currency(value, currency="$")
        self.assertEqual(formatted, "$1,000.00")
        
        # تنسيق مع عدد منازل عشرية مختلفة
        value = 1000
        formatted = format_currency(value, decimal_places=0)
        self.assertEqual(formatted, "1,000")
    
    def test_calculate_vat(self):
        """
        اختبار حساب ضريبة القيمة المضافة
        """
        from utils.helpers import calculate_vat
        
        # حساب الضريبة بالنسبة الافتراضية
        amount = 100
        vat = calculate_vat(amount)
        self.assertEqual(vat, 15)  # افتراض النسبة الافتراضية 15%
        
        # حساب الضريبة بنسبة محددة
        amount = 100
        vat = calculate_vat(amount, rate=5)
        self.assertEqual(vat, 5)
        
        # حساب ضريبة قيمة عشرية
        amount = 123.45
        vat = calculate_vat(amount, rate=10)
        self.assertEqual(vat, 12.345)
    
    def test_arabic_date_format(self):
        """
        اختبار تنسيق التاريخ بالعربية
        """
        from utils.helpers import arabic_date_format
        
        # تنسيق تاريخ محدد
        date = timezone.datetime(2023, 4, 5).date()
        formatted = arabic_date_format(date)
        # التحقق من وجود اسم الشهر بالعربية في النتيجة
        self.assertTrue("أبريل" in formatted or "إبريل" in formatted or "نيسان" in formatted)
        
        # تنسيق تاريخ مع وقت
        date_time = timezone.datetime(2023, 4, 5, 14, 30)
        formatted = arabic_date_format(date_time, with_time=True)
        # التحقق من وجود الوقت في النتيجة
        self.assertTrue("14:30" in formatted or "02:30" in formatted)


class ExportImportTest(TestCase):
    """
    اختبارات وظائف التصدير والاستيراد
    """
    def setUp(self):
        # إنشاء مستخدم عادي
        self.user = User.objects.create_user(
            username='testuser_export',
            email=get_unique_email('testuser_export'),
            password='testpassword123'
        )
        
        # إنشاء بيانات اختبارية للتصدير
        self.test_data = [
            {'id': 1, 'name': 'منتج 1', 'price': 100, 'quantity': 10},
            {'id': 2, 'name': 'منتج 2', 'price': 200, 'quantity': 20},
            {'id': 3, 'name': 'منتج 3', 'price': 300, 'quantity': 30}
        ]
        
        # تحديد تعيين الحقول للتصدير
        self.field_mapping = {
            'id': 'الرقم',
            'name': 'اسم المنتج',
            'price': 'السعر',
            'quantity': 'الكمية'
        }
        
        # إنشاء عميل للاختبارات
        self.client = Client()
        
        # تسجيل دخول المستخدم
        self.client.login(username='testuser_export', password='testpassword123')
    
    def test_export_to_excel(self):
        """
        اختبار تصدير البيانات إلى Excel
        """
        from utils.export import export_to_excel
        import pandas as pd
        import io
        
        # استدعاء دالة التصدير
        excel_content = export_to_excel(
            data=self.test_data,
            fields=['id', 'name', 'price', 'quantity'],
            headers=['الرقم', 'اسم المنتج', 'السعر', 'الكمية']
        )
        
        # التحقق من نوع الخرج
        self.assertIsNotNone(excel_content)
        
        # استخدام pandas لقراءة ملف Excel (مع BytesIO لتجنب التحذير)
        excel_file = io.BytesIO(excel_content)
        df = pd.read_excel(excel_file)
        
        # التحقق من عدد الصفوف
        self.assertEqual(len(df), 3)
        
        # التحقق من أسماء الأعمدة
        self.assertListEqual(list(df.columns), ['الرقم', 'اسم المنتج', 'السعر', 'الكمية'])
        
        # التحقق من البيانات
        self.assertEqual(df.iloc[0]['اسم المنتج'], 'منتج 1')
        self.assertEqual(df.iloc[1]['السعر'], 200)
        self.assertEqual(df.iloc[2]['الكمية'], 30)
    
    def test_export_to_pdf(self):
        """
        اختبار تصدير البيانات إلى PDF
        """
        from utils.export import export_to_pdf
        
        # استدعاء دالة التصدير
        pdf_file = export_to_pdf(
            data=self.test_data,
            fields=['id', 'name', 'price', 'quantity'],
            headers=['الرقم', 'اسم المنتج', 'السعر', 'الكمية'],
            title="تقرير المنتجات"
        )
        
        # التحقق من نوع الخرج
        self.assertIsNotNone(pdf_file)
        
        # التحقق من أن الخرج هو بايتات
        self.assertIsInstance(pdf_file, bytes)
        
        # التحقق من توقيع ملف PDF (يبدأ بـ %PDF-)
        self.assertTrue(pdf_file.startswith(b'%PDF-'), "الملف ليس بتنسيق PDF صالح")
    
    def test_import_from_excel(self):
        """
        اختبار استيراد البيانات من Excel
        """
        from utils.importers import import_from_excel
        import pandas as pd
        import io
        
        # إنشاء ملف Excel للاختبار
        df = pd.DataFrame(self.test_data)
        excel_file = io.BytesIO()
        with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        excel_file.seek(0)
        
        # إنشاء ملف مرفق وهمي
        from django.core.files.uploadedfile import SimpleUploadedFile
        file_content = excel_file.read()
        excel_file.seek(0)
        
        test_file = SimpleUploadedFile(
            "test_import.xlsx",
            file_content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        # تعيين الحقول
        field_mapping = {
            'id': 'id',
            'name': 'name',
            'price': 'price',
            'quantity': 'quantity'
        }
        
        # استدعاء دالة الاستيراد (مع استخدام BytesIO للتعامل مع البيانات)
        bytes_content = test_file.read()
        test_file.seek(0)
        imported_data = import_from_excel(io.BytesIO(bytes_content), field_mapping)
        
        # التحقق من البيانات المستوردة
        self.assertEqual(len(imported_data), 3)
        self.assertEqual(imported_data[0]['id'], 1)
        self.assertEqual(imported_data[0]['name'], 'منتج 1')
        self.assertEqual(imported_data[1]['price'], 200)
        self.assertEqual(imported_data[2]['quantity'], 30)


class BackupRestoreTest(TestCase):
    """
    اختبارات وظائف النسخ الاحتياطي واستعادة النظام
    """
    def setUp(self):
        # إنشاء مستخدم عادي
        self.user = User.objects.create_user(
            username='testuser_backup',
            email=get_unique_email('testuser_backup'),
            password='testpassword123'
        )
        
        # إنشاء مستخدم مشرف
        self.admin_user = User.objects.create_user(
            username='adminuser_backup',
            email=get_unique_email('adminuser_backup'),
            password='adminpassword123',
            is_superuser=True
        )
        
        # إنشاء عميل للاختبارات
        self.client = Client()
    
    def test_backup_access_permissions(self):
        """
        اختبار صلاحيات الوصول لنسخ قاعدة البيانات احتياطياً
        """
        # المستخدم العادي لا يجب أن يكون قادراً على الوصول
        self.client.login(username='testuser_backup', password='testpassword123')
        response = self.client.get(reverse('utils:backup_system'))
        self.assertEqual(response.status_code, 302)  # إعادة توجيه لعدم وجود صلاحية
        
        # المشرف يجب أن يكون قادراً على الوصول
        self.client.login(username='adminuser_backup', password='adminpassword123')
        response = self.client.get(reverse('utils:backup_system'))
        self.assertEqual(response.status_code, 200)
    
    def test_backup_download(self):
        """
        اختبار تنزيل نسخة احتياطية من قاعدة البيانات
        """
        # تسجيل دخول كمشرف
        self.client.login(username='adminuser_backup', password='adminpassword123')
        
        # إنشاء ملف مؤقت وهمي
        with tempfile.NamedTemporaryFile(delete=False) as temp:
            temp.write(b'test database backup content')
            temp_path = temp.name
        
        # عمل باتش (تجاوز مؤقت) لدالة النسخ الاحتياطي
        original_settings = settings.DATABASES
        
        try:
            # تعديل إعدادات قاعدة البيانات مؤقتًا للاختبار
            settings.DATABASES = {
                'default': {
                    'ENGINE': 'django.db.backends.sqlite3',
                    'NAME': temp_path,
                }
            }
            
            # طلب نسخة احتياطية
            response = self.client.post(reverse('utils:backup_system'))
            
            # التحقق من أن الاستجابة تحتوي على ملف للتنزيل
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], 'application/octet-stream')
            self.assertTrue('Content-Disposition' in response)
            self.assertTrue('attachment; filename=' in response['Content-Disposition'])
        finally:
            # استعادة إعدادات قاعدة البيانات الأصلية
            settings.DATABASES = original_settings
            # تنظيف الملف المؤقت
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def test_restore_access_permissions(self):
        """
        اختبار صلاحيات الوصول لاستعادة قاعدة البيانات
        """
        # المستخدم العادي لا يجب أن يكون قادراً على الوصول
        self.client.login(username='testuser_backup', password='testpassword123')
        response = self.client.get(reverse('utils:restore_database'))
        self.assertEqual(response.status_code, 302)  # إعادة توجيه لعدم وجود صلاحية
        
        # المشرف يجب أن يكون قادراً على الوصول
        self.client.login(username='adminuser_backup', password='adminpassword123')
        response = self.client.get(reverse('utils:restore_database'))
        self.assertEqual(response.status_code, 200)


class LogsTest(TestCase):
    """
    اختبارات وظائف سجلات النظام
    """
    def setUp(self):
        # إنشاء مستخدم عادي
        self.user = User.objects.create_user(
            username='testuser_logs',
            email=get_unique_email('testuser_logs'),
            password='testpassword123'
        )
        
        # إنشاء مستخدم مشرف
        self.admin_user = User.objects.create_user(
            username='adminuser_logs',
            email=get_unique_email('adminuser_logs'),
            password='adminpassword123',
            is_superuser=True
        )
        
        # إنشاء بعض سجلات النظام للاختبار
        SystemLog.objects.create(
            user=self.user,
            action='تسجيل دخول',
            model_name='User',
            object_id='1',
            details='تسجيل دخول ناجح',
            ip_address='127.0.0.1'
        )
        
        SystemLog.objects.create(
            user=self.admin_user,
            action='تحديث منتج',
            model_name='Product',
            object_id='5',
            details='تغيير سعر المنتج',
            ip_address='127.0.0.1'
        )
        
        SystemLog.objects.create(
            user=self.admin_user,
            action='إضافة مستخدم',
            model_name='User',
            object_id='3',
            details='إنشاء حساب جديد',
            ip_address='127.0.0.1'
        )
        
        # إنشاء عميل للاختبارات
        self.client = Client()
    
    def test_log_creation(self):
        """
        اختبار إنشاء سجل نظام
        """
        # إنشاء سجل جديد
        create_log(
            user=self.user,
            action='اختبار',
            model_name='Test',
            object_id='999',
            details='هذا اختبار',
            ip_address='192.168.1.1'
        )
        
        # التحقق من وجود السجل في قاعدة البيانات
        log = SystemLog.objects.filter(action='اختبار').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.model_name, 'Test')
        self.assertEqual(log.object_id, '999')
        self.assertEqual(log.details, 'هذا اختبار')
        self.assertEqual(log.ip_address, '192.168.1.1')
    
    def test_logs_filtering(self):
        """
        اختبار تصفية سجلات النظام
        """
        # الحصول على جميع السجلات
        all_logs = get_logs()
        self.assertEqual(len(all_logs), 3)
        
        # التصفية حسب المستخدم
        user_logs = get_logs(user_id=self.user.id)
        self.assertEqual(len(user_logs), 1)
        
        # التصفية حسب النموذج
        model_logs = get_logs(model_name='User')
        self.assertEqual(len(model_logs), 2)
        
        # التصفية حسب الإجراء
        action_logs = get_logs(action='تحديث منتج')
        self.assertEqual(len(action_logs), 1)
        
        # تصفية مركبة
        combined_logs = get_logs(user_id=self.admin_user.id, model_name='User')
        self.assertEqual(len(combined_logs), 1)
    
    def test_logs_view(self):
        """
        اختبار عرض سجلات النظام
        """
        # تسجيل دخول كمستخدم عادي
        self.client.login(username='testuser_logs', password='testpassword123')
        
        # المستخدم العادي لا يجب أن يكون قادراً على الوصول
        response = self.client.get(reverse('utils:system_logs'))
        self.assertEqual(response.status_code, 403)  # رفض الوصول - غير مصرح به
        
        # تسجيل دخول كمشرف
        self.client.login(username='adminuser_logs', password='adminpassword123')
        
        # المشرف يجب أن يكون قادراً على الوصول
        response = self.client.get(reverse('utils:system_logs'))
        self.assertEqual(response.status_code, 200)
        
        # التحقق من وجود السجلات في السياق
        self.assertTrue('logs' in response.context)
        self.assertIsNotNone(response.context['logs'])
        self.assertEqual(len(response.context['logs']), 3)
        
        # اختبار التصفية في واجهة المستخدم
        response = self.client.get(reverse('utils:system_logs') + '?model_name=User')
        self.assertEqual(response.status_code, 200)
        self.assertTrue('logs' in response.context)
        self.assertIsNotNone(response.context['logs'])
        self.assertEqual(len(response.context['logs']), 2) 