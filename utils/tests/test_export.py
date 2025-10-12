import os
import tempfile
import datetime
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.http import HttpResponse
from django.db import models
from django.contrib.auth import get_user_model

from utils.export import ExcelExporter, CSVExporter
from utils.export import export_queryset_to_excel, export_queryset_to_csv

User = get_user_model()


# إنشاء نموذج اختبار للاستخدام في الاختبارات
class TestModel(models.Model):
    """نموذج اختبار للتصدير"""
    name = models.CharField(max_length=100)
    value = models.IntegerField()
    date_created = models.DateField(default=datetime.date.today)
    
    class Meta:
        app_label = 'utils'
        managed = False  # نموذج غير مدار، لن يتم إنشاء جدول في قاعدة البيانات
    
    def __str__(self):
        return self.name


class ExcelExporterTest(TestCase):
    """
    اختبارات فئة ExcelExporter
    """
    
    def setUp(self):
        """إعداد بيئة الاختبار"""
        # استخدام ملف مؤقت للاختبار
        self.temp_file = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
        self.temp_filename = self.temp_file.name
        self.temp_file.close()
        
        # إنشاء مصدر Excel للاختبار
        self.exporter = ExcelExporter(filename=self.temp_filename)
        
        # تهيئة بيانات الاختبار
        self.headers = ['الاسم', 'القيمة', 'التاريخ']
        self.data = [
            ['منتج 1', 100, datetime.date.today()],
            ['منتج 2', 200, datetime.date.today() - datetime.timedelta(days=1)],
            ['منتج 3', 300, datetime.date.today() - datetime.timedelta(days=2)],
        ]
    
    def tearDown(self):
        """تنظيف بيئة الاختبار"""
        # حذف الملف المؤقت
        if os.path.exists(self.temp_filename):
            os.unlink(self.temp_filename)
    
    def test_add_headers(self):
        """اختبار إضافة عناوين الأعمدة"""
        self.exporter.add_headers(self.headers)
        self.assertEqual(self.exporter.current_row, 1)
    
    def test_add_data(self):
        """اختبار إضافة صفوف البيانات"""
        self.exporter.add_headers(self.headers)
        self.exporter.add_data(self.data)
        self.assertEqual(self.exporter.current_row, 4)  # 1 للعناوين + 3 صفوف بيانات
    
    @patch('xlsxwriter.Workbook.close')
    def test_save(self, mock_close):
        """اختبار حفظ الملف وإنشاء استجابة HTTP"""
        self.exporter.add_headers(self.headers)
        self.exporter.add_data(self.data)
        
        response = self.exporter.save()
        
        # التحقق من استدعاء close
        mock_close.assert_called_once()
        
        # التحقق من أن الاستجابة هي HttpResponse
        self.assertIsInstance(response, HttpResponse)
        
        # التحقق من نوع المحتوى
        self.assertEqual(response['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        
        # التحقق من الاسم المتوقع في الاستجابة
        self.assertIn(os.path.basename(self.temp_filename), response['Content-Disposition'])
    
    def test_add_queryset(self):
        """اختبار إضافة بيانات من مجموعة استعلام"""
        # محاكاة مجموعة استعلام وقيمها
        queryset = MagicMock()
        
        # إنشاء نماذج وهمية
        model1 = MagicMock(spec=TestModel)
        model1.name = 'منتج 1'
        model1.value = 100
        model1.date_created = datetime.date.today()
        
        model2 = MagicMock(spec=TestModel)
        model2.name = 'منتج 2'
        model2.value = 200
        model2.date_created = datetime.date.today() - datetime.timedelta(days=1)
        
        # تعيين النموذج ونتيجة الاستعلام
        queryset.model = TestModel
        queryset.__iter__.return_value = [model1, model2]
        
        # تعيين الحقول الظاهرية
        TestModel._meta.fields = [
            MagicMock(name='name', verbose_name='الاسم'),
            MagicMock(name='value', verbose_name='القيمة'),
            MagicMock(name='date_created', verbose_name='التاريخ'),
        ]
        
        # استخدام الطريقة add_queryset
        self.exporter.add_queryset(queryset, fields=['name', 'value', 'date_created'])
        
        # التحقق من عدد الصفوف
        self.assertEqual(self.exporter.current_row, 3)  # 1 للعناوين + 2 صفوف بيانات


class CSVExporterTest(TestCase):
    """
    اختبارات فئة CSVExporter
    """
    
    def setUp(self):
        """إعداد بيئة الاختبار"""
        # استخدام ملف مؤقت للاختبار
        self.temp_file = tempfile.NamedTemporaryFile(suffix='.csv', delete=False)
        self.temp_filename = self.temp_file.name
        self.temp_file.close()
        
        # إنشاء مصدر CSV للاختبار
        self.exporter = CSVExporter(filename=self.temp_filename)
        
        # تهيئة بيانات الاختبار
        self.headers = ['الاسم', 'القيمة', 'التاريخ']
        self.data = [
            ['منتج 1', 100, datetime.date.today()],
            ['منتج 2', 200, datetime.date.today() - datetime.timedelta(days=1)],
            ['منتج 3', 300, datetime.date.today() - datetime.timedelta(days=2)],
        ]
    
    def tearDown(self):
        """تنظيف بيئة الاختبار"""
        # حذف الملف المؤقت
        if os.path.exists(self.temp_filename):
            os.unlink(self.temp_filename)
    
    def test_add_headers(self):
        """اختبار إضافة عناوين الأعمدة"""
        self.exporter.add_headers(self.headers)
        self.assertEqual(self.exporter.headers, self.headers)
    
    def test_add_data(self):
        """اختبار إضافة صفوف البيانات"""
        self.exporter.add_data(self.data)
        self.assertEqual(len(self.exporter.data_rows), 3)
        self.assertEqual(self.exporter.data_rows, self.data)
    
    def test_save(self):
        """اختبار حفظ الملف وإنشاء استجابة HTTP"""
        self.exporter.add_headers(self.headers)
        self.exporter.add_data(self.data)
        
        response = self.exporter.save()
        
        # التحقق من أن الاستجابة هي HttpResponse
        self.assertIsInstance(response, HttpResponse)
        
        # التحقق من نوع المحتوى
        self.assertEqual(response['Content-Type'], 'text/csv')
        
        # التحقق من الاسم المتوقع في الاستجابة
        self.assertIn(os.path.basename(self.temp_filename), response['Content-Disposition'])
    
    def test_save_to_file(self):
        """اختبار حفظ الملف إلى المسار المحدد"""
        self.exporter.add_headers(self.headers)
        self.exporter.add_data(self.data)
        
        filepath = self.exporter.save_to_file()
        
        # التحقق من وجود الملف
        self.assertTrue(os.path.exists(filepath))
        
        # التحقق من أن المسار المرجع هو المتوقع
        self.assertEqual(filepath, self.temp_filename)
    
    def test_add_queryset(self):
        """اختبار إضافة بيانات من مجموعة استعلام"""
        # محاكاة مجموعة استعلام وقيمها
        queryset = MagicMock()
        
        # إنشاء نماذج وهمية
        model1 = MagicMock(spec=TestModel)
        model1.name = 'منتج 1'
        model1.value = 100
        model1.date_created = datetime.date.today()
        
        model2 = MagicMock(spec=TestModel)
        model2.name = 'منتج 2'
        model2.value = 200
        model2.date_created = datetime.date.today() - datetime.timedelta(days=1)
        
        # تعيين النموذج ونتيجة الاستعلام
        queryset.model = TestModel
        queryset.__iter__.return_value = [model1, model2]
        
        # تعيين الحقول الظاهرية
        TestModel._meta.fields = [
            MagicMock(name='name', verbose_name='الاسم'),
            MagicMock(name='value', verbose_name='القيمة'),
            MagicMock(name='date_created', verbose_name='التاريخ'),
        ]
        
        # استخدام الطريقة add_queryset
        self.exporter.add_queryset(queryset, fields=['name', 'value', 'date_created'])
        
        # التحقق من أن العناوين قد تمت إضافتها
        self.assertEqual(len(self.exporter.headers), 3)
        
        # التحقق من أن البيانات قد تمت إضافتها
        self.assertEqual(len(self.exporter.data_rows), 2)


class ExportFunctionsTest(TestCase):
    """
    اختبارات دوال التصدير المساعدة
    """
    
    @patch('utils.export.ExcelExporter')
    def test_export_queryset_to_excel(self, mock_exporter):
        """اختبار دالة export_queryset_to_excel"""
        # محاكاة مجموعة استعلام
        queryset = MagicMock()
        
        # محاكاة استجابة
        mock_instance = MagicMock()
        mock_instance.add_queryset.return_value = mock_instance
        mock_exporter.return_value = mock_instance
        
        # استدعاء الدالة
        export_queryset_to_excel(queryset, filename='test.xlsx', fields=['name'])
        
        # التحقق من استدعاء المصدر
        mock_exporter.assert_called_once_with(filename='test.xlsx', sheet_name=None)
        
        # التحقق من استدعاء add_queryset
        mock_instance.add_queryset.assert_called_once_with(
            queryset, fields=['name'], headers=None, annotations=None
        )
        
        # التحقق من استدعاء save
        mock_instance.save.assert_called_once()
    
    @patch('utils.export.CSVExporter')
    def test_export_queryset_to_csv(self, mock_exporter):
        """اختبار دالة export_queryset_to_csv"""
        # محاكاة مجموعة استعلام
        queryset = MagicMock()
        
        # محاكاة استجابة
        mock_instance = MagicMock()
        mock_instance.add_queryset.return_value = mock_instance
        mock_exporter.return_value = mock_instance
        
        # استدعاء الدالة
        export_queryset_to_csv(queryset, filename='test.csv', fields=['name'])
        
        # التحقق من استدعاء المصدر
        mock_exporter.assert_called_once_with(filename='test.csv')
        
        # التحقق من استدعاء add_queryset
        mock_instance.add_queryset.assert_called_once_with(
            queryset, fields=['name'], headers=None, annotations=None
        )
        
        # التحقق من استدعاء save
        mock_instance.save.assert_called_once() 