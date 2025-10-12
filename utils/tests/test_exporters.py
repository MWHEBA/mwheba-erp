import io
import json
import csv
import unittest
from django.test import TestCase
from unittest.mock import patch, MagicMock, mock_open
from django.http import HttpResponse
import os
import pandas as pd
import tempfile
import datetime
from django.db import models

from utils.exporters import export_to_excel, export_to_csv, export_to_json
from utils.exporters import generate_excel_response, generate_csv_response, generate_json_response
from utils.exporters import PandasExporter
from utils.exporters import export_queryset_to_pandas, export_data_to_pandas


class ExporterTests(TestCase):
    """
    اختبارات لوظائف التصدير
    """

    def setUp(self):
        """
        إعداد بيئة الاختبار
        """
        # بيانات اختبار مشتركة
        self.test_data = [
            {'product_name': 'منتج 1', 'product_price': 100, 'stock_quantity': 10},
            {'product_name': 'منتج 2', 'product_price': 200, 'stock_quantity': 20},
            {'product_name': 'منتج 3', 'product_price': 300, 'stock_quantity': 30},
        ]
        
        # تعيين الأعمدة للتصدير
        self.field_mapping = {
            'product_name': 'اسم المنتج',
            'product_price': 'سعر المنتج',
            'stock_quantity': 'الكمية في المخزن'
        }

    @patch('utils.exporters.pd.DataFrame.to_excel')
    def test_export_to_excel(self, mock_to_excel):
        """
        اختبار تصدير البيانات إلى ملف Excel
        """
        # محاكاة دالة to_excel
        mock_to_excel.return_value = None
        
        # تنفيذ دالة التصدير
        output = export_to_excel(self.test_data, self.field_mapping)
        
        # التحقق من أن الدالة قد تم استدعاؤها بشكل صحيح
        mock_to_excel.assert_called_once()
        
        # التحقق من نوع الملف الناتج
        self.assertIsInstance(output, io.BytesIO)

    def test_export_to_csv(self):
        """
        اختبار تصدير البيانات إلى ملف CSV
        """
        # تنفيذ دالة التصدير
        output = export_to_csv(self.test_data, self.field_mapping)
        
        # التحقق من نوع الملف الناتج
        self.assertIsInstance(output, io.StringIO)
        
        # قراءة محتوى الملف للتحقق
        output.seek(0)
        reader = csv.reader(output)
        rows = list(reader)
        
        # التحقق من العناوين
        self.assertEqual(rows[0], ['اسم المنتج', 'سعر المنتج', 'الكمية في المخزن'])
        
        # التحقق من البيانات
        self.assertEqual(rows[1][0], 'منتج 1')
        self.assertEqual(rows[2][1], '200')  # تحويل تلقائي إلى نص في CSV
        self.assertEqual(rows[3][2], '30')

    def test_export_to_json(self):
        """
        اختبار تصدير البيانات إلى ملف JSON
        """
        # تنفيذ دالة التصدير
        output = export_to_json(self.test_data, self.field_mapping)
        
        # التحقق من نوع الملف الناتج
        self.assertIsInstance(output, io.StringIO)
        
        # قراءة محتوى الملف للتحقق
        output.seek(0)
        result = json.load(output)
        
        # التحقق من البيانات
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]['اسم المنتج'], 'منتج 1')
        self.assertEqual(result[1]['سعر المنتج'], 200)
        self.assertEqual(result[2]['الكمية في المخزن'], 30)

    @patch('utils.exporters.export_to_excel')
    def test_generate_excel_response(self, mock_export):
        """
        اختبار إنشاء استجابة Excel
        """
        # محاكاة دالة التصدير
        mock_buffer = io.BytesIO()
        mock_export.return_value = mock_buffer
        
        # تنفيذ دالة إنشاء الاستجابة
        response = generate_excel_response(self.test_data, self.field_mapping, 'test_file')
        
        # التحقق من نوع الاستجابة والعناوين
        self.assertIsInstance(response, HttpResponse)
        self.assertEqual(response['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="test_file.xlsx"')

    @patch('utils.exporters.export_to_csv')
    def test_generate_csv_response(self, mock_export):
        """
        اختبار إنشاء استجابة CSV
        """
        # محاكاة دالة التصدير
        mock_buffer = io.StringIO()
        mock_export.return_value = mock_buffer
        
        # تنفيذ دالة إنشاء الاستجابة
        response = generate_csv_response(self.test_data, self.field_mapping, 'test_file')
        
        # التحقق من نوع الاستجابة والعناوين
        self.assertIsInstance(response, HttpResponse)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="test_file.csv"')

    @patch('utils.exporters.export_to_json')
    def test_generate_json_response(self, mock_export):
        """
        اختبار إنشاء استجابة JSON
        """
        # محاكاة دالة التصدير
        mock_buffer = io.StringIO()
        mock_export.return_value = mock_buffer
        
        # تنفيذ دالة إنشاء الاستجابة
        response = generate_json_response(self.test_data, self.field_mapping, 'test_file')
        
        # التحقق من نوع الاستجابة والعناوين
        self.assertIsInstance(response, HttpResponse)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="test_file.json"')


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


class PandasExporterTest(TestCase):
    """
    اختبارات فئة PandasExporter
    """
    
    def setUp(self):
        """إعداد بيئة الاختبار"""
        # تهيئة بيانات الاختبار
        self.data = {
            'name': ['منتج 1', 'منتج 2', 'منتج 3'],
            'value': [100, 200, 300],
            'date_created': [datetime.date.today(), datetime.date.today(), datetime.date.today()]
        }
        self.df = pd.DataFrame(self.data)
        
        # إنشاء مصدر التصدير
        self.exporter = PandasExporter(self.df)
    
    def test_init(self):
        """اختبار تهيئة المصدر"""
        # اختبار إنشاء مصدر بإطار بيانات
        self.assertIsNotNone(self.exporter.df)
        self.assertEqual(len(self.exporter.df), 3)
        
        # اختبار إنشاء مصدر بدون إطار بيانات
        empty_exporter = PandasExporter()
        self.assertIsNotNone(empty_exporter.df)
        self.assertEqual(len(empty_exporter.df), 0)
    
    @patch('utils.exporters.pd.DataFrame')
    def test_from_queryset(self, mock_df):
        """اختبار إنشاء مصدر من مجموعة استعلام"""
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
        model2.date_created = datetime.date.today()
        
        # تعيين النموذج ونتيجة الاستعلام
        queryset.model = TestModel
        queryset.__iter__.return_value = [model1, model2]
        
        # استخدام الطريقة from_queryset
        mock_df.return_value = pd.DataFrame(self.data)
        
        result = PandasExporter.from_queryset(queryset, fields=['name', 'value', 'date_created'])
        
        # التحقق من إنشاء DataFrame
        mock_df.assert_called_once()
        
        # التحقق من إرجاع كائن PandasExporter
        self.assertIsInstance(result, PandasExporter)
    
    def test_from_data(self):
        """اختبار إنشاء مصدر من بيانات"""
        # استخدام الطريقة from_data
        result = PandasExporter.from_data(self.data)
        
        # التحقق من إنشاء DataFrame
        self.assertIsInstance(result, PandasExporter)
        self.assertEqual(len(result.df), 3)
        
        # التحقق من وجود الأعمدة المتوقعة
        for column in self.data.keys():
            self.assertIn(column, result.df.columns)
    
    def test_filter(self):
        """اختبار تصفية البيانات"""
        # تصفية باستخدام تعبير نصي
        result = self.exporter.filter("value > 100")
        
        # التحقق من النتيجة
        self.assertEqual(len(result.df), 2)  # منتج 2 و 3 فقط
        
        # تصفية باستخدام دالة
        result = self.exporter.filter(self.exporter.df['name'] == 'منتج 1')
        
        # التحقق من النتيجة
        self.assertEqual(len(result.df), 1)  # منتج 1 فقط
    
    def test_sort(self):
        """اختبار ترتيب البيانات"""
        # ترتيب تصاعدي
        result = self.exporter.sort('value', ascending=True)
        
        # التحقق من النتيجة
        self.assertEqual(result.df.iloc[0]['value'], 100)
        self.assertEqual(result.df.iloc[2]['value'], 300)
        
        # ترتيب تنازلي
        result = self.exporter.sort('value', ascending=False)
        
        # التحقق من النتيجة
        self.assertEqual(result.df.iloc[0]['value'], 300)
        self.assertEqual(result.df.iloc[2]['value'], 100)
    
    def test_group_by(self):
        """اختبار تجميع البيانات"""
        # إنشاء بيانات للتجميع
        data = {
            'category': ['فئة أ', 'فئة أ', 'فئة ب', 'فئة ب'],
            'value': [100, 200, 300, 400],
        }
        df = pd.DataFrame(data)
        exporter = PandasExporter(df)
        
        # تجميع بدون دالة تجميع
        result = exporter.group_by('category')
        
        # التحقق من النتيجة
        self.assertEqual(len(result.df), 2)  # فئتان فقط
        
        # تجميع مع دالة تجميع
        result = exporter.group_by('category', {'value': 'sum'})
        
        # التحقق من النتيجة
        self.assertEqual(len(result.df), 2)  # فئتان فقط
        
        # التحقق من مجموع القيم
        category_a = result.df[result.df['category'] == 'فئة أ']['value'].iloc[0]
        category_b = result.df[result.df['category'] == 'فئة ب']['value'].iloc[0]
        self.assertEqual(category_a, 300)  # 100 + 200
        self.assertEqual(category_b, 700)  # 300 + 400
    
    def test_pivot(self):
        """اختبار إنشاء جدول محوري"""
        # إنشاء بيانات للجدول المحوري
        data = {
            'المنطقة': ['شمال', 'شمال', 'جنوب', 'جنوب'],
            'الصنف': ['أ', 'ب', 'أ', 'ب'],
            'القيمة': [100, 200, 300, 400],
        }
        df = pd.DataFrame(data)
        exporter = PandasExporter(df)
        
        # إنشاء جدول محوري
        result = exporter.pivot(index='المنطقة', columns='الصنف', values='القيمة')
        
        # التحقق من النتيجة
        self.assertEqual(len(result.df), 2)  # منطقتان فقط
        self.assertEqual(len(result.df.columns), 2)  # صنفان فقط
    
    def test_add_column(self):
        """اختبار إضافة عمود جديد"""
        # إضافة عمود جديد
        result = self.exporter.add_column('double_value', lambda row: row['value'] * 2)
        
        # التحقق من النتيجة
        self.assertIn('double_value', result.df.columns)
        self.assertEqual(result.df['double_value'].iloc[0], 200)  # 100 * 2
        self.assertEqual(result.df['double_value'].iloc[1], 400)  # 200 * 2
        self.assertEqual(result.df['double_value'].iloc[2], 600)  # 300 * 2
    
    def test_rename_columns(self):
        """اختبار إعادة تسمية الأعمدة"""
        # إعادة تسمية الأعمدة
        result = self.exporter.rename_columns({'name': 'الاسم', 'value': 'القيمة'})
        
        # التحقق من النتيجة
        self.assertIn('الاسم', result.df.columns)
        self.assertIn('القيمة', result.df.columns)
        self.assertNotIn('name', result.df.columns)
        self.assertNotIn('value', result.df.columns)
    
    def test_select_columns(self):
        """اختبار اختيار أعمدة محددة"""
        # اختيار أعمدة محددة
        result = self.exporter.select_columns(['name', 'value'])
        
        # التحقق من النتيجة
        self.assertEqual(len(result.df.columns), 2)
        self.assertIn('name', result.df.columns)
        self.assertIn('value', result.df.columns)
        self.assertNotIn('date_created', result.df.columns)
    
    @patch('utils.exporters.ExcelExporter')
    def test_to_excel(self, mock_excel):
        """اختبار تصدير البيانات إلى ملف Excel"""
        # محاكاة مصدر Excel
        mock_instance = MagicMock()
        mock_instance.add_headers.return_value = mock_instance
        mock_instance.add_data.return_value = mock_instance
        mock_excel.return_value = mock_instance
        
        # تصدير البيانات إلى Excel
        self.exporter.to_excel(filename='test.xlsx')
        
        # التحقق من استدعاء ExcelExporter
        mock_excel.assert_called_once_with(filename='test.xlsx', sheet_name=None)
        
        # التحقق من استدعاء add_headers
        mock_instance.add_headers.assert_called_once()
        
        # التحقق من استدعاء add_data
        mock_instance.add_data.assert_called_once()
        
        # التحقق من استدعاء save
        mock_instance.save.assert_called_once()
    
    @patch('utils.exporters.CSVExporter')
    def test_to_csv(self, mock_csv):
        """اختبار تصدير البيانات إلى ملف CSV"""
        # محاكاة مصدر CSV
        mock_instance = MagicMock()
        mock_instance.add_headers.return_value = mock_instance
        mock_instance.add_data.return_value = mock_instance
        mock_csv.return_value = mock_instance
        
        # تصدير البيانات إلى CSV
        self.exporter.to_csv(filename='test.csv')
        
        # التحقق من استدعاء CSVExporter
        mock_csv.assert_called_once_with(filename='test.csv')
        
        # التحقق من استدعاء add_headers
        mock_instance.add_headers.assert_called_once()
        
        # التحقق من استدعاء add_data
        mock_instance.add_data.assert_called_once()
        
        # التحقق من استدعاء save
        mock_instance.save.assert_called_once()
    
    def test_to_json(self):
        """اختبار تصدير البيانات إلى ملف JSON"""
        # تصدير البيانات إلى JSON
        response = self.exporter.to_json(filename='test.json')
        
        # التحقق من نوع الاستجابة
        self.assertIsInstance(response, HttpResponse)
        
        # التحقق من نوع المحتوى
        self.assertEqual(response['Content-Type'], 'application/json')
        
        # التحقق من اسم الملف
        self.assertIn('test.json', response['Content-Disposition'])
    
    def test_to_html(self):
        """اختبار تصدير البيانات إلى ملف HTML"""
        # تصدير البيانات إلى HTML
        response = self.exporter.to_html(filename='test.html')
        
        # التحقق من نوع الاستجابة
        self.assertIsInstance(response, HttpResponse)
        
        # التحقق من نوع المحتوى
        self.assertEqual(response['Content-Type'], 'text/html')
        
        # التحقق من اسم الملف
        self.assertIn('test.html', response['Content-Disposition'])
    
    def test_to_df(self):
        """اختبار إرجاع إطار البيانات"""
        # الحصول على إطار البيانات
        df = self.exporter.to_df()
        
        # التحقق من نوع إطار البيانات
        self.assertIsInstance(df, pd.DataFrame)
        
        # التحقق من أن إطار البيانات هو نفسه
        pd.testing.assert_frame_equal(df, self.df)


class ExportFunctionsTest(TestCase):
    """
    اختبارات دوال التصدير المساعدة
    """
    
    @patch('utils.exporters.PandasExporter.from_queryset')
    def test_export_queryset_to_pandas(self, mock_from_queryset):
        """اختبار دالة export_queryset_to_pandas"""
        # محاكاة مصدر Pandas
        mock_instance = MagicMock(spec=PandasExporter)
        mock_from_queryset.return_value = mock_instance
        
        # استدعاء الدالة
        queryset = MagicMock()
        result = export_queryset_to_pandas(queryset, fields=['name', 'value'])
        
        # التحقق من استدعاء from_queryset
        mock_from_queryset.assert_called_once_with(queryset, fields=['name', 'value'], annotations=None)
        
        # التحقق من النتيجة
        self.assertEqual(result, mock_instance)
    
    @patch('utils.exporters.PandasExporter.from_data')
    def test_export_data_to_pandas(self, mock_from_data):
        """اختبار دالة export_data_to_pandas"""
        # محاكاة مصدر Pandas
        mock_instance = MagicMock(spec=PandasExporter)
        mock_from_data.return_value = mock_instance
        
        # استدعاء الدالة
        data = {'name': ['منتج 1'], 'value': [100]}
        result = export_data_to_pandas(data)
        
        # التحقق من استدعاء from_data
        mock_from_data.assert_called_once_with(data)
        
        # التحقق من النتيجة
        self.assertEqual(result, mock_instance) 