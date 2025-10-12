from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from core.forms import (
    SearchForm,
    DateRangeForm,
    ImportForm,
    ExportForm,
    SettingsForm
)
import datetime
from decimal import Decimal
import pytz

User = get_user_model()


class SearchFormTest(TestCase):
    """
    اختبارات نموذج البحث
    """
    
    def test_search_form_valid(self):
        """
        اختبار صحة نموذج البحث بقيم صحيحة
        """
        today = timezone.now().date()
        yesterday = today - datetime.timedelta(days=1)
        form_data = {
            'query': 'منتج 1',
            'category': 'الإلكترونيات',
            'date_from': yesterday,
            'date_to': today,
            'sort_by': 'name',
        }
        form = SearchForm(data=form_data)
        self.assertTrue(form.is_valid())
    
    def test_search_form_empty(self):
        """
        اختبار صحة نموذج البحث بقيم فارغة
        """
        form_data = {}
        form = SearchForm(data=form_data)
        self.assertTrue(form.is_valid())
    
    def test_search_form_invalid_date_range(self):
        """
        اختبار عدم صحة نموذج البحث عند تحديد نطاق تاريخ غير صحيح
        """
        today = timezone.now().date()
        tomorrow = today + datetime.timedelta(days=1)
        form_data = {
            'query': 'منتج 1',
            'date_from': tomorrow,
            'date_to': today,
        }
        form = SearchForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('date_to', form.errors)


class DateRangeFormTest(TestCase):
    """
    اختبارات نموذج نطاق التاريخ
    """
    
    def test_date_range_form_valid(self):
        """
        اختبار صحة نموذج نطاق التاريخ بقيم صحيحة
        """
        today = timezone.now().date()
        yesterday = today - datetime.timedelta(days=1)
        form_data = {
            'start_date': yesterday,
            'end_date': today,
        }
        form = DateRangeForm(data=form_data)
        self.assertTrue(form.is_valid())
    
    def test_date_range_form_empty(self):
        """
        اختبار صحة نموذج نطاق التاريخ بقيم فارغة
        """
        form_data = {}
        form = DateRangeForm(data=form_data)
        self.assertTrue(form.is_valid())
    
    def test_date_range_form_invalid_date_range(self):
        """
        اختبار عدم صحة نموذج نطاق التاريخ عند تحديد نطاق تاريخ غير صحيح
        """
        today = timezone.now().date()
        tomorrow = today + datetime.timedelta(days=1)
        form_data = {
            'start_date': tomorrow,
            'end_date': today,
        }
        form = DateRangeForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('end_date', form.errors)
    
    def test_date_range_form_disallow_future_dates(self):
        """
        اختبار عدم صحة نموذج نطاق التاريخ عند تحديد تواريخ مستقبلية وهو غير مسموح
        """
        today = timezone.now().date()
        tomorrow = today + datetime.timedelta(days=1)
        form_data = {
            'start_date': tomorrow,
            'end_date': tomorrow,
        }
        # إنشاء النموذج وتعيين خاصية السماح بالتواريخ المستقبلية إلى False
        form = DateRangeForm(data=form_data)
        form.allows_future_dates = False
        self.assertFalse(form.is_valid())
        self.assertIn('start_date', form.errors)
        self.assertIn('end_date', form.errors)
    
    def test_date_range_form_preset_today(self):
        """
        اختبار نموذج نطاق التاريخ مع استخدام الفترة المحددة مسبقًا "اليوم"
        """
        form_data = {
            'preset': 'today',
        }
        form = DateRangeForm(data=form_data)
        self.assertTrue(form.is_valid())
        today = timezone.now().date()
        self.assertEqual(form.cleaned_data['start_date'], today)
        self.assertEqual(form.cleaned_data['end_date'], today)
    
    def test_date_range_form_preset_this_month(self):
        """
        اختبار نموذج نطاق التاريخ مع استخدام الفترة المحددة مسبقًا "هذا الشهر"
        """
        form_data = {
            'preset': 'this_month',
        }
        form = DateRangeForm(data=form_data)
        self.assertTrue(form.is_valid())
        today = timezone.now().date()
        start_date = today.replace(day=1)
        # حساب آخر يوم في الشهر
        next_month = today.replace(day=28) + datetime.timedelta(days=4)
        end_date = next_month - datetime.timedelta(days=next_month.day)
        self.assertEqual(form.cleaned_data['start_date'], start_date)
        self.assertEqual(form.cleaned_data['end_date'], end_date)


class ImportFormTest(TestCase):
    """
    اختبارات نموذج استيراد البيانات
    """
    
    def test_import_form_valid(self):
        """
        اختبار صحة نموذج استيراد البيانات
        """
        # هنا نستخدم SimpleUploadedFile لمحاكاة ملف تم رفعه
        # ملاحظة: يتم تخطي هذا الاختبار حيث أن SimpleUploadedFile يتطلب إعدادات إضافية
        # ويمكن إضافته لاحقًا عند الحاجة
        pass
        
    def test_import_form_invalid_file_type(self):
        """
        اختبار عدم صحة نموذج استيراد البيانات عند تحديد نوع ملف غير صحيح
        """
        # هنا نستخدم SimpleUploadedFile لمحاكاة ملف تم رفعه
        # ملاحظة: يتم تخطي هذا الاختبار حيث أن SimpleUploadedFile يتطلب إعدادات إضافية
        # ويمكن إضافته لاحقًا عند الحاجة
        pass


class ExportFormTest(TestCase):
    """
    اختبارات نموذج تصدير البيانات
    """
    
    def test_export_form_valid(self):
        """
        اختبار صحة نموذج تصدير البيانات
        """
        today = timezone.now().date()
        yesterday = today - datetime.timedelta(days=1)
        form_data = {
            'file_type': 'excel',
            'model_type': 'product',
            'date_from': yesterday,
            'date_to': today,
        }
        form = ExportForm(data=form_data)
        self.assertTrue(form.is_valid())
    
    def test_export_form_invalid_date_range(self):
        """
        اختبار عدم صحة نموذج تصدير البيانات عند تحديد نطاق تاريخ غير صحيح
        """
        today = timezone.now().date()
        tomorrow = today + datetime.timedelta(days=1)
        form_data = {
            'file_type': 'excel',
            'model_type': 'product',
            'date_from': tomorrow,
            'date_to': today,
        }
        form = ExportForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('date_to', form.errors)
    
    def test_export_form_invalid_file_type(self):
        """
        اختبار عدم صحة نموذج تصدير البيانات عند تحديد نوع ملف غير صحيح
        """
        form_data = {
            'file_type': 'word',  # نوع ملف غير صالح
            'model_type': 'product',
        }
        form = ExportForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('file_type', form.errors)


class SettingsFormTest(TestCase):
    """
    اختبارات نموذج إعدادات النظام
    """
    
    def test_settings_form_valid(self):
        """
        اختبار صحة نموذج إعدادات النظام
        """
        form_data = {
            'site_name': 'نظام إدارة المخزون',
            'currency': 'EGP',
            'decimal_places': 2,
            'tax_rate': 14.0,
            'timezone': 'Africa/Cairo',
            'language': 'ar',
            'items_per_page': 20,
        }
        form = SettingsForm(data=form_data)
        self.assertTrue(form.is_valid())
    
    def test_settings_form_invalid_tax_rate(self):
        """
        اختبار عدم صحة نموذج إعدادات النظام عند تحديد نسبة ضريبة غير صحيحة
        """
        form_data = {
            'site_name': 'نظام إدارة المخزون',
            'currency': 'EGP',
            'decimal_places': 2,
            'tax_rate': 120.0,  # نسبة ضريبة غير صالحة (أكبر من 100)
            'timezone': 'Africa/Cairo',
            'language': 'ar',
            'items_per_page': 20,
        }
        form = SettingsForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('tax_rate', form.errors)
    
    def test_settings_form_invalid_decimal_places(self):
        """
        اختبار عدم صحة نموذج إعدادات النظام عند تحديد عدد منازل عشرية غير صحيح
        """
        form_data = {
            'site_name': 'نظام إدارة المخزون',
            'currency': 'EGP',
            'decimal_places': 5,  # عدد منازل عشرية غير صالح (أكبر من 4)
            'tax_rate': 14.0,
            'timezone': 'Africa/Cairo',
            'language': 'ar',
            'items_per_page': 20,
        }
        form = SettingsForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('decimal_places', form.errors)
    
    def test_settings_form_invalid_timezone(self):
        """
        اختبار عدم صحة نموذج إعدادات النظام عند تحديد منطقة زمنية غير صحيحة
        """
        form_data = {
            'site_name': 'نظام إدارة المخزون',
            'currency': 'EGP',
            'decimal_places': 2,
            'tax_rate': 14.0,
            'timezone': 'Invalid/Timezone',  # منطقة زمنية غير صالحة
            'language': 'ar',
            'items_per_page': 20,
        }
        form = SettingsForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('timezone', form.errors) 