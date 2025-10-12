import io
import json
import pandas as pd
import unittest
from django.test import TestCase
from django.core.exceptions import ValidationError
from unittest.mock import patch, MagicMock
from django.db import transaction
import os
import tempfile
import datetime
from django.db import models
from django.db.utils import IntegrityError
from django.contrib.auth import get_user_model

from utils.importers import import_from_excel, import_from_csv, import_from_json, process_imported_data
from utils.importers import bulk_create_from_import, validate_import_data
from utils.importers import BaseImporter, PandasImporter
from utils.importers import import_excel_to_model, import_csv_to_model

User = get_user_model()


# إنشاء نموذج اختبار للاستخدام في الاختبارات
class TestModel(models.Model):
    """نموذج اختبار للاستيراد"""
    name = models.CharField(max_length=100)
    value = models.IntegerField()
    date_created = models.DateField(default=datetime.date.today)
    
    class Meta:
        app_label = 'utils'
        managed = False  # نموذج غير مدار، لن يتم إنشاء جدول في قاعدة البيانات
    
    def __str__(self):
        return self.name


class ImporterTests(TestCase):
    """
    اختبارات لوظائف الاستيراد
    """

    def setUp(self):
        """
        إعداد بيئة الاختبار
        """
        # بيانات اختبار مشتركة
        self.test_data = [
            {'name': 'منتج 1', 'price': '100', 'quantity': '10'},
            {'name': 'منتج 2', 'price': '200', 'quantity': '20'},
            {'name': 'منتج 3', 'price': '300', 'quantity': '30'},
        ]
        
        # تعيين الحقول
        self.field_mapping = {
            'name': 'product_name',
            'price': 'product_price',
            'quantity': 'stock_quantity'
        }
        
        # الحقول المطلوبة
        self.required_fields = ['product_name', 'product_price']

    def test_process_imported_data_without_mapping(self):
        """
        اختبار معالجة البيانات المستوردة بدون تعيين الحقول
        """
        result = process_imported_data(self.test_data)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]['name'], 'منتج 1')
        self.assertEqual(result[1]['price'], '200')
        self.assertEqual(result[2]['quantity'], '30')

    def test_process_imported_data_with_mapping(self):
        """
        اختبار معالجة البيانات المستوردة مع تعيين الحقول
        """
        result = process_imported_data(self.test_data, self.field_mapping)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]['product_name'], 'منتج 1')
        self.assertEqual(result[1]['product_price'], '200')
        self.assertEqual(result[2]['stock_quantity'], '30')
        # التأكد من عدم وجود الحقول الأصلية
        self.assertNotIn('name', result[0])
        self.assertNotIn('price', result[1])

    def test_process_imported_data_with_required_fields(self):
        """
        اختبار معالجة البيانات المستوردة مع تحديد الحقول المطلوبة
        """
        # إنشاء بيانات بها سجل ناقص
        data_with_missing = self.test_data.copy()
        data_with_missing.append({'name': '', 'price': '', 'quantity': '40'})
        
        result = process_imported_data(data_with_missing, self.field_mapping, self.required_fields)
        # يجب أن يتم تخطي السجل الناقص
        self.assertEqual(len(result), 3)

    def test_import_from_excel(self):
        """
        اختبار استيراد البيانات من ملف Excel
        """
        # إنشاء ملف Excel وهمي
        df = pd.DataFrame(self.test_data)
        excel_file = io.BytesIO()
        df.to_excel(excel_file, index=False, engine='openpyxl')
        excel_file.seek(0)
        
        # تحويل BytesIO إلى ملف وهمي متوافق مع Django
        mock_file = MagicMock()
        mock_file.read = excel_file.read
        
        with patch('pandas.read_excel') as mock_read_excel:
            mock_read_excel.return_value = df
            result = import_from_excel(mock_file, self.field_mapping, self.required_fields)
            
            self.assertEqual(len(result), 3)
            self.assertEqual(result[0]['product_name'], 'منتج 1')
            self.assertEqual(result[1]['product_price'], '200')
            self.assertEqual(result[2]['stock_quantity'], '30')

    def test_import_from_csv(self):
        """
        اختبار استيراد البيانات من ملف CSV
        """
        # إنشاء ملف CSV وهمي
        csv_data = "name,price,quantity\nمنتج 1,100,10\nمنتج 2,200,20\nمنتج 3,300,30"
        csv_file = io.BytesIO(csv_data.encode('utf-8'))
        
        # تحويل BytesIO إلى ملف وهمي متوافق مع Django
        mock_file = MagicMock()
        mock_file.read = lambda: csv_file.getvalue()
        
        result = import_from_csv(mock_file, self.field_mapping, self.required_fields)
        
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]['product_name'], 'منتج 1')
        self.assertEqual(result[1]['product_price'], '200')
        self.assertEqual(result[2]['stock_quantity'], '30')

    def test_import_from_json(self):
        """
        اختبار استيراد البيانات من ملف JSON
        """
        # إنشاء ملف JSON وهمي
        json_data = json.dumps(self.test_data)
        json_file = io.BytesIO(json_data.encode('utf-8'))
        
        # تحويل BytesIO إلى ملف وهمي متوافق مع Django
        mock_file = MagicMock()
        mock_file.read = lambda: json_file.getvalue()
        
        result = import_from_json(mock_file, self.field_mapping, self.required_fields)
        
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]['product_name'], 'منتج 1')
        self.assertEqual(result[1]['product_price'], '200')
        self.assertEqual(result[2]['stock_quantity'], '30')

    def test_import_from_json_invalid_format(self):
        """
        اختبار استيراد بيانات من ملف JSON بتنسيق غير صالح
        """
        # إنشاء ملف JSON وهمي بتنسيق غير صالح (كائن بدلاً من قائمة)
        json_data = json.dumps({'name': 'منتج 1', 'price': '100', 'quantity': '10'})
        json_file = io.BytesIO(json_data.encode('utf-8'))
        
        # تحويل BytesIO إلى ملف وهمي متوافق مع Django
        mock_file = MagicMock()
        mock_file.read = lambda: json_file.getvalue()
        
        with self.assertRaises(ValidationError):
            import_from_json(mock_file, self.field_mapping, self.required_fields)

    def test_bulk_create_from_import(self):
        """
        اختبار إنشاء سجلات بشكل جماعي من البيانات المستوردة
        """
        # إنشاء نموذج وهمي للاختبار
        mock_model = MagicMock()
        mock_objects = MagicMock()
        mock_model.objects = mock_objects
        
        # محاكاة الإنشاء الناجح
        mock_objects.create.return_value = MagicMock()
        
        # محاكاة update_or_create
        mock_objects.update_or_create.return_value = (MagicMock(), True)
        
        with patch.object(transaction, 'atomic', lambda func: func):
            created, updated, errors = bulk_create_from_import(mock_model, self.test_data)
            
            self.assertEqual(created, 3)
            self.assertEqual(updated, 0)
            self.assertEqual(errors, 0)
            
            # اختبار مع حقول فريدة
            created, updated, errors = bulk_create_from_import(mock_model, self.test_data, ['name'])
            
            # يجب أن تتم 3 استدعاءات لـ update_or_create بدلاً من create
            self.assertEqual(mock_objects.update_or_create.call_count, 3)

    def test_validate_import_data(self):
        """
        اختبار التحقق من صحة البيانات المستوردة
        """
        # إنشاء دوال تحقق وهمية
        validators = {
            'name': lambda x: None if x else ValidationError('الاسم مطلوب'),
            'price': lambda x: None if x.isdigit() else ValidationError('السعر يجب أن يكون رقمًا'),
        }
        
        # بيانات اختبار تحتوي على أخطاء
        test_data_with_errors = [
            {'name': 'منتج 1', 'price': '100', 'quantity': '10'},  # صحيح
            {'name': '', 'price': '200', 'quantity': '20'},  # اسم فارغ
            {'name': 'منتج 3', 'price': 'غير رقمي', 'quantity': '30'},  # سعر غير رقمي
        ]
        
        valid_data, errors = validate_import_data(test_data_with_errors, validators)
        
        # يجب أن يكون هناك سجل واحد صالح وسجلان خاطئان
        self.assertEqual(len(valid_data), 1)
        self.assertEqual(len(errors), 2)
        
        # التحقق من أخطاء السجل الثاني
        self.assertEqual(errors[0]['row'], 2)
        self.assertIn('name', errors[0]['errors'])
        
        # التحقق من أخطاء السجل الثالث
        self.assertEqual(errors[1]['row'], 3)
        self.assertIn('price', errors[1]['errors'])


class BaseImporterTest(TestCase):
    """
    اختبارات فئة BaseImporter
    """
    
    def setUp(self):
        """إعداد بيئة الاختبار"""
        # تهيئة المستورد
        self.importer = BaseImporter(model_class=TestModel)
        
        # تهيئة بيانات الاختبار
        self.row_data = {
            'name': 'منتج اختبار',
            'value': 123,
            'date_created': datetime.date.today(),
        }
    
    def test_init_invalid_model(self):
        """اختبار تهيئة المستورد بنموذج غير صالح"""
        with self.assertRaises(ValueError):
            BaseImporter(model_class=str)  # str ليس نموذجًا
    
    def test_map_column_to_field(self):
        """اختبار تعيين اسم العمود إلى اسم الحقل"""
        # إنشاء مستورد بتعيين حقول
        importer = BaseImporter(model_class=TestModel, mapping={'الاسم': 'name'})
        
        # اختبار حالة وجود التعيين
        self.assertEqual(importer._map_column_to_field('الاسم'), 'name')
        
        # اختبار حالة عدم وجود التعيين
        self.assertEqual(importer._map_column_to_field('غير موجود'), 'غير موجود')
    
    def test_validate_field(self):
        """اختبار التحقق من صحة قيمة الحقل"""
        # إنشاء دالة تحقق وهمية
        def validate_name(value):
            if not value:
                return False, 'الاسم مطلوب'
            elif len(value) < 3:
                return False, 'الاسم قصير جدًا'
            return True, None
        
        # إنشاء مستورد بدوال تحقق
        importer = BaseImporter(model_class=TestModel, validators={'name': validate_name})
        
        # اختبار قيمة صحيحة
        is_valid, error = importer._validate_field('name', 'منتج اختبار')
        self.assertTrue(is_valid)
        self.assertIsNone(error)
        
        # اختبار قيمة غير صحيحة
        is_valid, error = importer._validate_field('name', 'من')
        self.assertFalse(is_valid)
        self.assertEqual(error, 'الاسم قصير جدًا')
    
    def test_convert_value(self):
        """اختبار تحويل القيمة إلى النوع المناسب"""
        # القيمة الافتراضية تعيد نفس القيمة
        self.assertEqual(self.importer.convert_value('test', 'name'), 'test')
    
    def test_process_row(self):
        """اختبار معالجة صف من البيانات"""
        # إنشاء دالة تحقق وهمية
        def validate_value(value):
            if value <= 0:
                return False, 'القيمة يجب أن تكون موجبة'
            return True, None
        
        # إنشاء مستورد بتعيين حقول ودوال تحقق
        importer = BaseImporter(
            model_class=TestModel,
            mapping={'الاسم': 'name', 'القيمة': 'value'},
            validators={'value': validate_value}
        )
        
        # اختبار معالجة صف صحيح
        row_data = {'الاسم': 'منتج اختبار', 'القيمة': 123}
        processed_data = importer.process_row(row_data)
        self.assertEqual(processed_data, {'name': 'منتج اختبار', 'value': 123})
        
        # اختبار معالجة صف به قيمة غير صحيحة
        row_data = {'الاسم': 'منتج اختبار', 'القيمة': -1}
        processed_data = importer.process_row(row_data)
        self.assertEqual(processed_data, {'name': 'منتج اختبار'})  # القيمة السالبة تم تجاهلها
        self.assertEqual(len(importer.errors), 1)
    
    @patch('utils.importers.TestModel.objects.create')
    def test_create_object(self, mock_create):
        """اختبار إنشاء كائن جديد"""
        # محاكاة إنشاء كائن ناجح
        mock_create.return_value = MagicMock(spec=TestModel)
        
        # اختبار إنشاء كائن
        self.importer.create_object(self.row_data)
        
        # التحقق من استدعاء create
        mock_create.assert_called_once_with(**self.row_data)
        
        # التحقق من تحديث العداد
        self.assertEqual(self.importer.created_count, 1)
    
    @patch('utils.importers.TestModel.objects.create')
    def test_create_object_error(self, mock_create):
        """اختبار إنشاء كائن جديد مع خطأ"""
        # محاكاة خطأ أثناء الإنشاء
        mock_create.side_effect = ValidationError('خطأ في التحقق')
        
        # اختبار إنشاء كائن
        result = self.importer.create_object(self.row_data)
        
        # التحقق من النتيجة
        self.assertIsNone(result)
        
        # التحقق من تحديث العدادات
        self.assertEqual(self.importer.created_count, 0)
        self.assertEqual(self.importer.skipped_count, 1)
        self.assertEqual(len(self.importer.errors), 1)
    
    def test_update_object(self):
        """اختبار تحديث كائن موجود"""
        # إنشاء كائن وهمي
        obj = MagicMock(spec=TestModel)
        
        # اختبار تحديث الكائن
        updated_obj = self.importer.update_object(obj, self.row_data)
        
        # التحقق من تحديث الخصائص
        for key, value in self.row_data.items():
            self.assertEqual(getattr(obj, key), value)
        
        # التحقق من استدعاء save
        obj.save.assert_called_once()
        
        # التحقق من تحديث العداد
        self.assertEqual(self.importer.updated_count, 1)
        
        # التحقق من إرجاع الكائن المحدث
        self.assertEqual(updated_obj, obj)
    
    def test_update_object_error(self):
        """اختبار تحديث كائن موجود مع خطأ"""
        # إنشاء كائن وهمي يرفع خطأ عند الحفظ
        obj = MagicMock(spec=TestModel)
        obj.save.side_effect = ValidationError('خطأ في التحقق')
        
        # اختبار تحديث الكائن
        result = self.importer.update_object(obj, self.row_data)
        
        # التحقق من النتيجة
        self.assertIsNone(result)
        
        # التحقق من تحديث العدادات
        self.assertEqual(self.importer.updated_count, 0)
        self.assertEqual(self.importer.skipped_count, 1)
        self.assertEqual(len(self.importer.errors), 1)
    
    def test_import_data(self):
        """اختبار استيراد البيانات"""
        # محاكاة إنشاء كائنات
        self.importer.process_row = MagicMock(return_value=self.row_data)
        self.importer.create_object = MagicMock(return_value=MagicMock(spec=TestModel))
        
        # اختبار استيراد البيانات
        data = [self.row_data, self.row_data]
        created, updated, errors = self.importer.import_data(data)
        
        # التحقق من عدد مرات استدعاء process_row و create_object
        self.assertEqual(self.importer.process_row.call_count, 2)
        self.assertEqual(self.importer.create_object.call_count, 2)
        
        # التحقق من النتائج
        self.assertEqual(len(created), 2)
        self.assertEqual(len(updated), 0)
        self.assertEqual(len(errors), 0)
    
    def test_get_stats(self):
        """اختبار الحصول على إحصائيات الاستيراد"""
        # تعيين قيم العدادات
        self.importer.created_count = 10
        self.importer.updated_count = 5
        self.importer.skipped_count = 3
        self.importer.errors = ['خطأ 1', 'خطأ 2']
        
        # اختبار الحصول على الإحصائيات
        stats = self.importer.get_stats()
        
        # التحقق من القيم
        self.assertEqual(stats['created'], 10)
        self.assertEqual(stats['updated'], 5)
        self.assertEqual(stats['skipped'], 3)
        self.assertEqual(stats['errors'], 2)


class PandasImporterTest(TestCase):
    """
    اختبارات فئة PandasImporter
    """
    
    def setUp(self):
        """إعداد بيئة الاختبار"""
        # إنشاء ملف Excel مؤقت للاختبار
        self.temp_excel = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
        self.temp_excel_path = self.temp_excel.name
        self.temp_excel.close()
        
        # إنشاء ملف CSV مؤقت للاختبار
        self.temp_csv = tempfile.NamedTemporaryFile(suffix='.csv', delete=False)
        self.temp_csv_path = self.temp_csv.name
        self.temp_csv.close()
        
        # تهيئة البيانات للاختبار
        self.data = {
            'name': ['منتج 1', 'منتج 2', 'منتج 3'],
            'value': [100, 200, 300],
            'date_created': [datetime.date.today(), datetime.date.today(), datetime.date.today()]
        }
        self.df = pd.DataFrame(self.data)
        
        # حفظ البيانات في الملفات المؤقتة
        self.df.to_excel(self.temp_excel_path, index=False)
        self.df.to_csv(self.temp_csv_path, index=False)
        
        # تهيئة المستورد
        self.importer = PandasImporter(model_class=TestModel)
    
    def tearDown(self):
        """تنظيف بيئة الاختبار"""
        # حذف الملفات المؤقتة
        if os.path.exists(self.temp_excel_path):
            os.unlink(self.temp_excel_path)
        if os.path.exists(self.temp_csv_path):
            os.unlink(self.temp_csv_path)
    
    def test_from_excel(self):
        """اختبار إنشاء مستورد من ملف Excel"""
        # استخدام الطريقة from_excel
        importer = PandasImporter.from_excel(self.temp_excel_path, model_class=TestModel)
        
        # التحقق من إنشاء DataFrame
        self.assertIsNotNone(importer.df)
        self.assertGreater(len(importer.df), 0)
        
        # التحقق من وجود الأعمدة المتوقعة
        for column in self.data.keys():
            self.assertIn(column, importer.df.columns)
    
    def test_from_csv(self):
        """اختبار إنشاء مستورد من ملف CSV"""
        # استخدام الطريقة from_csv
        importer = PandasImporter.from_csv(self.temp_csv_path, model_class=TestModel)
        
        # التحقق من إنشاء DataFrame
        self.assertIsNotNone(importer.df)
        self.assertGreater(len(importer.df), 0)
        
        # التحقق من وجود الأعمدة المتوقعة
        for column in self.data.keys():
            self.assertIn(column, importer.df.columns)
    
    def test_from_dataframe(self):
        """اختبار إنشاء مستورد من إطار بيانات pandas"""
        # استخدام الطريقة from_dataframe
        importer = PandasImporter.from_dataframe(self.df, model_class=TestModel)
        
        # التحقق من تعيين DataFrame
        self.assertIsNotNone(importer.df)
        
        # التحقق من أن إطار البيانات هو نفسه
        pd.testing.assert_frame_equal(importer.df, self.df)
    
    def test_clean_data(self):
        """اختبار تنظيف البيانات"""
        # تهيئة DataFrame به قيم مفقودة وصفوف مكررة
        df = pd.DataFrame({
            'name': ['منتج 1', 'منتج 2', 'منتج 2', None],
            'value': [100, 200, 200, 300],
        })
        
        # إنشاء مستورد وتنظيف البيانات
        importer = PandasImporter.from_dataframe(df, model_class=TestModel)
        importer.clean_data()
        
        # التحقق من استبدال القيم المفقودة
        self.assertEqual(importer.df['name'].isnull().sum(), 0)
        
        # التحقق من إزالة الصفوف المكررة
        self.assertEqual(len(importer.df), 3)  # 3 صفوف فريدة
    
    def test_clean_data_with_mapping(self):
        """اختبار تنظيف البيانات مع تعيين الأعمدة"""
        # تهيئة DataFrame
        df = pd.DataFrame({
            'الاسم': ['منتج 1', 'منتج 2'],
            'القيمة': [100, 200],
            'أخرى': ['غير مطلوبة', 'غير مطلوبة'],
        })
        
        # إنشاء مستورد بتعيين أعمدة
        importer = PandasImporter.from_dataframe(
            df,
            model_class=TestModel,
            mapping={'الاسم': 'name', 'القيمة': 'value'}
        )
        
        # تنظيف البيانات
        importer.clean_data()
        
        # التحقق من إزالة الأعمدة غير المطلوبة
        self.assertIn('الاسم', importer.df.columns)
        self.assertIn('القيمة', importer.df.columns)
        self.assertNotIn('أخرى', importer.df.columns)
    
    @patch('utils.importers.TestModel.objects.get')
    def test_find_existing_object(self, mock_get):
        """اختبار البحث عن كائن موجود"""
        # محاكاة العثور على كائن
        mock_obj = MagicMock(spec=TestModel)
        mock_get.return_value = mock_obj
        
        # تهيئة مستورد بحقول تفرد
        importer = PandasImporter(model_class=TestModel, unique_fields=['name'])
        
        # البحث عن كائن موجود
        row_data = {'name': 'منتج 1', 'value': 100}
        obj = importer.find_existing_object(row_data)
        
        # التحقق من استدعاء get
        mock_get.assert_called_once_with(name='منتج 1')
        
        # التحقق من إرجاع الكائن
        self.assertEqual(obj, mock_obj)
    
    @patch('utils.importers.TestModel.objects.get')
    def test_find_existing_object_not_found(self, mock_get):
        """اختبار البحث عن كائن غير موجود"""
        # محاكاة عدم العثور على كائن
        mock_get.side_effect = TestModel.DoesNotExist()
        
        # تهيئة مستورد بحقول تفرد
        importer = PandasImporter(model_class=TestModel, unique_fields=['name'])
        
        # البحث عن كائن غير موجود
        row_data = {'name': 'غير موجود', 'value': 100}
        obj = importer.find_existing_object(row_data)
        
        # التحقق من استدعاء get
        mock_get.assert_called_once()
        
        # التحقق من إرجاع None
        self.assertIsNone(obj)
    
    @patch('utils.importers.TestModel.objects.get')
    def test_find_existing_object_multiple(self, mock_get):
        """اختبار البحث عن كائن مع وجود كائنات متعددة"""
        # محاكاة العثور على كائنات متعددة
        mock_get.side_effect = TestModel.MultipleObjectsReturned()
        
        # تهيئة مستورد بحقول تفرد
        importer = PandasImporter(model_class=TestModel, unique_fields=['name'])
        
        # البحث عن كائن
        row_data = {'name': 'منتج 1', 'value': 100}
        obj = importer.find_existing_object(row_data)
        
        # التحقق من استدعاء get
        mock_get.assert_called_once()
        
        # التحقق من إرجاع None
        self.assertIsNone(obj)
        
        # التحقق من تسجيل خطأ
        self.assertEqual(len(importer.errors), 1)
        self.assertEqual(importer.skipped_count, 1)
    
    @patch('utils.importers.PandasImporter.find_existing_object')
    @patch('utils.importers.PandasImporter.update_object')
    @patch('utils.importers.PandasImporter.create_object')
    @patch('utils.importers.PandasImporter.process_row')
    def test_import_all(self, mock_process, mock_create, mock_update, mock_find):
        """اختبار استيراد جميع البيانات"""
        # إعداد البيانات
        self.importer.df = self.df
        
        # محاكاة معالجة الصفوف
        processed_data = {'name': 'منتج 1', 'value': 100}
        mock_process.return_value = processed_data
        
        # محاكاة البحث عن كائنات موجودة
        mock_obj = MagicMock(spec=TestModel)
        
        # السطر الأول: كائن موجود
        # السطر الثاني: كائن غير موجود
        # السطر الثالث: كائن موجود لكن التحديث معطل
        mock_find.side_effect = [mock_obj, None, mock_obj]
        
        # محاكاة إنشاء وتحديث الكائنات
        mock_create.return_value = MagicMock(spec=TestModel)
        mock_update.return_value = MagicMock(spec=TestModel)
        
        # استيراد البيانات
        created, updated, errors = self.importer.import_all(update_existing=True)
        
        # التحقق من عدد مرات استدعاء الدوال
        self.assertEqual(mock_process.call_count, 3)
        self.assertEqual(mock_find.call_count, 3)
        self.assertEqual(mock_update.call_count, 1)
        self.assertEqual(mock_create.call_count, 1)
        
        # التحقق من النتائج
        self.assertEqual(len(created), 1)
        self.assertEqual(len(updated), 1)
        self.assertEqual(len(errors), 0)
        
        # التحقق من العدادات
        self.assertEqual(self.importer.created_count, 1)
        self.assertEqual(self.importer.updated_count, 1)
        self.assertEqual(self.importer.skipped_count, 1)
    
    @patch('utils.importers.PandasImporter.from_excel')
    @patch('utils.importers.PandasImporter.import_all')
    def test_import_excel_to_model(self, mock_import_all, mock_from_excel):
        """اختبار دالة import_excel_to_model"""
        # محاكاة إنشاء المستورد
        mock_importer = MagicMock()
        mock_from_excel.return_value = mock_importer
        
        # محاكاة نتائج الاستيراد
        created = [MagicMock(spec=TestModel)]
        updated = [MagicMock(spec=TestModel)]
        errors = []
        stats = {'created': 1, 'updated': 1, 'skipped': 0, 'errors': 0}
        
        mock_import_all.return_value = (created, updated, errors)
        mock_importer.get_stats.return_value = stats
        
        # استدعاء الدالة
        result = import_excel_to_model(
            file_path=self.temp_excel_path,
            model_class=TestModel,
            mapping={'الاسم': 'name'},
            unique_fields=['name']
        )
        
        # التحقق من استدعاء from_excel
        mock_from_excel.assert_called_once_with(
            self.temp_excel_path,
            model_class=TestModel,
            mapping={'الاسم': 'name'},
            validators=None,
            unique_fields=['name']
        )
        
        # التحقق من استدعاء import_all
        mock_import_all.assert_called_once_with(update_existing=True)
        
        # التحقق من النتائج
        self.assertEqual(result, (created, updated, errors, stats))
    
    @patch('utils.importers.PandasImporter.from_csv')
    @patch('utils.importers.PandasImporter.import_all')
    def test_import_csv_to_model(self, mock_import_all, mock_from_csv):
        """اختبار دالة import_csv_to_model"""
        # محاكاة إنشاء المستورد
        mock_importer = MagicMock()
        mock_from_csv.return_value = mock_importer
        
        # محاكاة نتائج الاستيراد
        created = [MagicMock(spec=TestModel)]
        updated = [MagicMock(spec=TestModel)]
        errors = []
        stats = {'created': 1, 'updated': 1, 'skipped': 0, 'errors': 0}
        
        mock_import_all.return_value = (created, updated, errors)
        mock_importer.get_stats.return_value = stats
        
        # استدعاء الدالة
        result = import_csv_to_model(
            file_path=self.temp_csv_path,
            model_class=TestModel,
            mapping={'الاسم': 'name'},
            unique_fields=['name']
        )
        
        # التحقق من استدعاء from_csv
        mock_from_csv.assert_called_once_with(
            self.temp_csv_path,
            model_class=TestModel,
            mapping={'الاسم': 'name'},
            validators=None,
            unique_fields=['name']
        )
        
        # التحقق من استدعاء import_all
        mock_import_all.assert_called_once_with(update_existing=True)
        
        # التحقق من النتائج
        self.assertEqual(result, (created, updated, errors, stats)) 