import pandas as pd
import io
from django.db import transaction
from django.core.exceptions import ValidationError
import csv
import json
import logging
import os
import tempfile
import datetime
from io import BytesIO, StringIO
from django.db.models import Model
from django.db.utils import IntegrityError

logger = logging.getLogger(__name__)


def import_from_excel(file, field_mapping=None, required_fields=None):
    """
    استيراد بيانات من ملف Excel

    المعلمات:
    file (UploadedFile): ملف Excel المرفوع
    field_mapping (dict): تعيين الحقول من الملف إلى النظام
    required_fields (list): قائمة بالحقول المطلوبة

    تُرجع: قائمة بالبيانات المستوردة
    """
    try:
        # قراءة ملف Excel
        df = pd.read_excel(file, engine="openpyxl")

        # تحويل الأعمدة إلى قائمة من القواميس
        records = df.to_dict("records")

        # معالجة البيانات باستخدام الوظيفة المشتركة
        return process_imported_data(records, field_mapping, required_fields)

    except Exception as e:
        logger.error(f"خطأ في استيراد ملف Excel: {str(e)}")
        raise ValidationError(f"فشل استيراد ملف Excel: {str(e)}")


def import_from_csv(file, field_mapping=None, required_fields=None):
    """
    استيراد بيانات من ملف CSV

    المعلمات:
    file (UploadedFile): ملف CSV المرفوع
    field_mapping (dict): تعيين الحقول من الملف إلى النظام
    required_fields (list): قائمة بالحقول المطلوبة

    تُرجع: قائمة بالبيانات المستوردة
    """
    try:
        # قراءة ملف CSV
        content = file.read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))
        records = list(reader)

        # معالجة البيانات باستخدام الوظيفة المشتركة
        return process_imported_data(records, field_mapping, required_fields)

    except Exception as e:
        logger.error(f"خطأ في استيراد ملف CSV: {str(e)}")
        raise ValidationError(f"فشل استيراد ملف CSV: {str(e)}")


def import_from_json(file, field_mapping=None, required_fields=None):
    """
    استيراد بيانات من ملف JSON

    المعلمات:
    file (UploadedFile): ملف JSON المرفوع
    field_mapping (dict): تعيين الحقول من الملف إلى النظام
    required_fields (list): قائمة بالحقول المطلوبة

    تُرجع: قائمة بالبيانات المستوردة
    """
    try:
        # قراءة ملف JSON
        content = file.read().decode("utf-8")
        records = json.loads(content)

        # التأكد من أن البيانات عبارة عن قائمة
        if not isinstance(records, list):
            raise ValidationError("يجب أن تكون بيانات JSON عبارة عن قائمة من العناصر")

        # معالجة البيانات باستخدام الوظيفة المشتركة
        return process_imported_data(records, field_mapping, required_fields)

    except Exception as e:
        logger.error(f"خطأ في استيراد ملف JSON: {str(e)}")
        raise ValidationError(f"فشل استيراد ملف JSON: {str(e)}")


def process_imported_data(records, field_mapping=None, required_fields=None):
    """
    معالجة البيانات المستوردة

    المعلمات:
    records (list): قائمة بالسجلات المستوردة
    field_mapping (dict): تعيين الحقول من الملف إلى النظام
    required_fields (list): قائمة بالحقول المطلوبة

    تُرجع: قائمة بالبيانات المعالجة
    """
    processed_data = []

    for i, record in enumerate(records):
        # تخطي الصفوف الفارغة
        if not any(record.values()):
            continue

        # تطبيق تعيين الحقول
        processed_record = {}
        if field_mapping:
            for source_field, target_field in field_mapping.items():
                if source_field in record:
                    processed_record[target_field] = record[source_field]
        else:
            processed_record = record.copy()

        # التحقق من وجود الحقول المطلوبة
        if required_fields:
            missing_fields = [
                field
                for field in required_fields
                if field not in processed_record or not processed_record[field]
            ]
            if missing_fields:
                logger.warning(f"حقول مفقودة في السجل {i + 1}: {missing_fields}")
                # يمكن اختيار تخطي هذا السجل أو استمرار المعالجة
                continue

        processed_data.append(processed_record)

    return processed_data


@transaction.atomic
def bulk_create_from_import(model_class, data, unique_fields=None):
    """
    إنشاء سجلات بشكل جماعي من البيانات المستوردة

    المعلمات:
    model_class (Model): فئة النموذج للإنشاء
    data (list): قائمة بالبيانات للإنشاء
    unique_fields (list): قائمة بالحقول الفريدة للتحقق من التكرار

    تُرجع: (عدد السجلات المنشأة، عدد السجلات المحدثة، عدد الأخطاء)
    """
    created_count = 0
    updated_count = 0
    error_count = 0

    for item in data:
        try:
            # إذا تم تحديد حقول فريدة، تحقق من وجود السجل
            if unique_fields:
                filters = {
                    field: item[field] for field in unique_fields if field in item
                }
                if filters:
                    obj, created = model_class.objects.update_or_create(
                        defaults=item, **filters
                    )
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1
                    continue

            # إنشاء سجل جديد
            model_class.objects.create(**item)
            created_count += 1

        except Exception as e:
            logger.error(f"خطأ في إنشاء سجل: {str(e)}")
            error_count += 1

    return created_count, updated_count, error_count


def validate_import_data(data, validators=None):
    """
    التحقق من صحة البيانات المستوردة

    المعلمات:
    data (list): قائمة بالبيانات للتحقق
    validators (dict): قاموس من الدوال المتحققة، حيث المفتاح هو اسم الحقل

    تُرجع: (البيانات الصالحة، قائمة بالأخطاء)
    """
    valid_data = []
    errors = []

    for i, item in enumerate(data):
        item_errors = {}
        valid_item = {}

        for field, value in item.items():
            # إضافة القيمة إلى العنصر الصالح
            valid_item[field] = value

            # تطبيق المتحققات إذا وجدت
            if validators and field in validators:
                validator = validators[field]
                try:
                    validator(value)
                except ValidationError as e:
                    item_errors[field] = str(
                        e.messages[0] if hasattr(e, "messages") else e
                    )

        if item_errors:
            errors.append({"row": i + 1, "errors": item_errors, "data": item})
        else:
            valid_data.append(valid_item)

    return valid_data, errors


class BaseImporter:
    """
    التصنيف الأساسية لاستيراد البيانات
    """

    def __init__(self, model_class=None, mapping=None, validators=None):
        """
        تهيئة المستورد

        المعلمات:
        model_class (Model): فئة النموذج المستهدف
        mapping (dict): تعيين الأعمدة للحقول
        validators (dict): دوال التحقق من صحة البيانات
        """
        self.model_class = model_class
        self.mapping = mapping or {}
        self.validators = validators or {}
        self.errors = []
        self.created_count = 0
        self.updated_count = 0
        self.skipped_count = 0

        # التحقق من أن النموذج المحدد صالح
        if model_class and not issubclass(model_class, Model):
            raise ValueError("يجب أن تكون فئة النموذج مشتقة من Model")

    def _map_column_to_field(self, column_name):
        """
        تعيين اسم العمود إلى اسم الحقل

        المعلمات:
        column_name (str): اسم العمود

        تُرجع:
        str: اسم الحقل المقابل
        """
        if column_name in self.mapping:
            return self.mapping[column_name]
        return column_name

    def _validate_field(self, field_name, value):
        """
        التحقق من صحة قيمة الحقل

        المعلمات:
        field_name (str): اسم الحقل
        value: قيمة الحقل

        تُرجع:
        tuple: (صحيح/خطأ, رسالة الخطأ)
        """
        if field_name in self.validators:
            validator = self.validators[field_name]
            try:
                return validator(value)
            except Exception as e:
                return False, str(e)
        return True, None

    def convert_value(self, value, field_name):
        """
        تحويل القيمة إلى النوع المناسب

        المعلمات:
        value: القيمة الأصلية
        field_name (str): اسم الحقل

        تُرجع:
        القيمة المحولة
        """
        # يمكن تجاوز هذه الطريقة في التصنيفات الفرعية
        return value

    def process_row(self, row_data):
        """
        معالجة صف من البيانات

        المعلمات:
        row_data (dict): بيانات الصف

        تُرجع:
        dict: البيانات المعالجة
        """
        processed_data = {}

        for column_name, value in row_data.items():
            field_name = self._map_column_to_field(column_name)
            if field_name:
                # التحقق من صحة القيمة
                is_valid, error_message = self._validate_field(field_name, value)
                if not is_valid:
                    self.errors.append(
                        {"field": field_name, "value": value, "error": error_message}
                    )
                    continue

                # تحويل القيمة
                processed_value = self.convert_value(value, field_name)
                processed_data[field_name] = processed_value

        return processed_data

    def create_object(self, data):
        """
        إنشاء كائن جديد

        المعلمات:
        data (dict): بيانات الكائن

        تُرجع:
        Model: الكائن المنشأ
        """
        try:
            obj = self.model_class.objects.create(**data)
            self.created_count += 1
            return obj
        except (ValidationError, IntegrityError) as e:
            self.errors.append({"data": data, "error": str(e)})
            self.skipped_count += 1
            return None

    def update_object(self, obj, data):
        """
        تحديث كائن موجود

        المعلمات:
        obj (Model): الكائن المراد تحديثه
        data (dict): بيانات التحديث

        تُرجع:
        Model: الكائن المحدث
        """
        try:
            for key, value in data.items():
                setattr(obj, key, value)
            obj.save()
            self.updated_count += 1
            return obj
        except (ValidationError, IntegrityError) as e:
            self.errors.append({"data": data, "error": str(e)})
            self.skipped_count += 1
            return None

    def import_data(self, data):
        """
        استيراد البيانات

        المعلمات:
        data (list): قائمة بالبيانات

        تُرجع:
        tuple: (الكائنات المنشأة, الكائنات المحدثة, الأخطاء)
        """
        # إعادة تعيين العدادات
        self.errors = []
        self.created_count = 0
        self.updated_count = 0
        self.skipped_count = 0

        created_objects = []
        updated_objects = []

        for row_data in data:
            processed_data = self.process_row(row_data)
            if not processed_data:
                self.skipped_count += 1
                continue

            # محاولة إنشاء كائن جديد
            obj = self.create_object(processed_data)
            if obj:
                created_objects.append(obj)

        return created_objects, updated_objects, self.errors

    def get_stats(self):
        """
        الحصول على إحصائيات الاستيراد

        تُرجع:
        dict: إحصائيات الاستيراد
        """
        return {
            "created": self.created_count,
            "updated": self.updated_count,
            "skipped": self.skipped_count,
            "errors": len(self.errors),
        }


class PandasImporter(BaseImporter):
    """
    استيراد البيانات باستخدام pandas
    """

    def __init__(
        self, model_class=None, mapping=None, validators=None, unique_fields=None
    ):
        """
        تهيئة المستورد

        المعلمات:
        model_class (Model): فئة النموذج المستهدف
        mapping (dict): تعيين الأعمدة للحقول
        validators (dict): دوال التحقق من صحة البيانات
        unique_fields (list): حقول التفرد لتحديد الكائنات الموجودة
        """
        super().__init__(model_class, mapping, validators)
        self.unique_fields = unique_fields or ["id"]
        self.df = None

    @classmethod
    def from_excel(cls, file_path, sheet_name=0, **kwargs):
        """
        إنشاء مستورد من ملف Excel

        المعلمات:
        file_path (str): مسار ملف Excel
        sheet_name (str/int): اسم أو رقم الورقة
        **kwargs: معلمات أخرى

        تُرجع:
        PandasImporter: كائن المستورد
        """
        importer = cls(**kwargs)
        importer.df = pd.read_excel(file_path, sheet_name=sheet_name)
        return importer

    @classmethod
    def from_excel_file(cls, file_obj, sheet_name=0, **kwargs):
        """
        إنشاء مستورد من كائن ملف Excel

        المعلمات:
        file_obj (File): كائن الملف
        sheet_name (str/int): اسم أو رقم الورقة
        **kwargs: معلمات أخرى

        تُرجع:
        PandasImporter: كائن المستورد
        """
        importer = cls(**kwargs)
        importer.df = pd.read_excel(file_obj, sheet_name=sheet_name)
        return importer

    @classmethod
    def from_csv(cls, file_path, **kwargs):
        """
        إنشاء مستورد من ملف CSV

        المعلمات:
        file_path (str): مسار ملف CSV
        **kwargs: معلمات أخرى

        تُرجع:
        PandasImporter: كائن المستورد
        """
        importer = cls(**kwargs)
        importer.df = pd.read_csv(file_path)
        return importer

    @classmethod
    def from_csv_file(cls, file_obj, **kwargs):
        """
        إنشاء مستورد من كائن ملف CSV

        المعلمات:
        file_obj (File): كائن الملف
        **kwargs: معلمات أخرى

        تُرجع:
        PandasImporter: كائن المستورد
        """
        importer = cls(**kwargs)
        importer.df = pd.read_csv(file_obj)
        return importer

    @classmethod
    def from_dataframe(cls, df, **kwargs):
        """
        إنشاء مستورد من إطار بيانات pandas

        المعلمات:
        df (DataFrame): إطار بيانات pandas
        **kwargs: معلمات أخرى

        تُرجع:
        PandasImporter: كائن المستورد
        """
        importer = cls(**kwargs)
        importer.df = df
        return importer

    def clean_data(self):
        """
        تنظيف البيانات

        تُرجع:
        PandasImporter: نفس الكائن
        """
        # التعامل مع القيم المفقودة
        self.df = self.df.fillna("")

        # إزالة الأسطر المكررة
        self.df = self.df.drop_duplicates()

        # إزالة الأعمدة غير المطلوبة
        if self.mapping:
            columns_to_keep = list(self.mapping.keys())
            columns_in_df = [col for col in columns_to_keep if col in self.df.columns]
            self.df = self.df[columns_in_df]

        return self

    def preprocess_data(self):
        """
        معالجة البيانات قبل الاستيراد

        تُرجع:
        PandasImporter: نفس الكائن
        """
        # يمكن تجاوز هذه الطريقة في التصنيفات الفرعية
        return self

    def find_existing_object(self, row_data):
        """
        البحث عن كائن موجود

        المعلمات:
        row_data (dict): بيانات الصف

        تُرجع:
        Model: الكائن الموجود أو None
        """
        if not self.unique_fields:
            return None

        query = {}
        for field in self.unique_fields:
            if field in row_data and row_data[field]:
                query[field] = row_data[field]

        if not query:
            return None

        try:
            return self.model_class.objects.get(**query)
        except self.model_class.DoesNotExist:
            return None
        except self.model_class.MultipleObjectsReturned:
            # إذا تم العثور على أكثر من كائن، تخطى هذا الصف
            self.errors.append(
                {
                    "data": row_data,
                    "error": f"تم العثور على كائنات متعددة باستخدام {query}",
                }
            )
            self.skipped_count += 1
            return None

    def import_all(self, update_existing=True):
        """
        استيراد جميع البيانات

        المعلمات:
        update_existing (bool): تحديث الكائنات الموجودة

        تُرجع:
        tuple: (الكائنات المنشأة, الكائنات المحدثة, الأخطاء)
        """
        # إعادة تعيين العدادات
        self.errors = []
        self.created_count = 0
        self.updated_count = 0
        self.skipped_count = 0

        # تنظيف ومعالجة البيانات
        self.clean_data()
        self.preprocess_data()

        # تحويل DataFrame إلى قائمة من القواميس
        data = self.df.to_dict("records")

        created_objects = []
        updated_objects = []

        # استخدام المعاملة لضمان سلامة البيانات
        with transaction.atomic():
            for row_data in data:
                processed_data = self.process_row(row_data)
                if not processed_data:
                    self.skipped_count += 1
                    continue

                # البحث عن كائن موجود
                existing_obj = self.find_existing_object(processed_data)

                if existing_obj and update_existing:
                    # تحديث الكائن الموجود
                    updated_obj = self.update_object(existing_obj, processed_data)
                    if updated_obj:
                        updated_objects.append(updated_obj)
                elif not existing_obj:
                    # إنشاء كائن جديد
                    new_obj = self.create_object(processed_data)
                    if new_obj:
                        created_objects.append(new_obj)
                else:
                    # تخطي الكائن الموجود
                    self.skipped_count += 1

        return created_objects, updated_objects, self.errors


def import_excel_to_model(
    file_path,
    model_class,
    mapping=None,
    validators=None,
    unique_fields=None,
    update_existing=True,
):
    """
    استيراد بيانات من ملف Excel إلى نموذج

    المعلمات:
    file_path (str): مسار ملف Excel
    model_class (Model): فئة النموذج المستهدف
    mapping (dict): تعيين الأعمدة للحقول
    validators (dict): دوال التحقق من صحة البيانات
    unique_fields (list): حقول التفرد لتحديد الكائنات الموجودة
    update_existing (bool): تحديث الكائنات الموجودة

    تُرجع:
    tuple: (الكائنات المنشأة, الكائنات المحدثة, الأخطاء, الإحصائيات)
    """
    importer = PandasImporter.from_excel(
        file_path,
        model_class=model_class,
        mapping=mapping,
        validators=validators,
        unique_fields=unique_fields,
    )

    created, updated, errors = importer.import_all(update_existing=update_existing)
    stats = importer.get_stats()

    return created, updated, errors, stats


def import_csv_to_model(
    file_path,
    model_class,
    mapping=None,
    validators=None,
    unique_fields=None,
    update_existing=True,
):
    """
    استيراد بيانات من ملف CSV إلى نموذج

    المعلمات:
    file_path (str): مسار ملف CSV
    model_class (Model): فئة النموذج المستهدف
    mapping (dict): تعيين الأعمدة للحقول
    validators (dict): دوال التحقق من صحة البيانات
    unique_fields (list): حقول التفرد لتحديد الكائنات الموجودة
    update_existing (bool): تحديث الكائنات الموجودة

    تُرجع:
    tuple: (الكائنات المنشأة, الكائنات المحدثة, الأخطاء, الإحصائيات)
    """
    importer = PandasImporter.from_csv(
        file_path,
        model_class=model_class,
        mapping=mapping,
        validators=validators,
        unique_fields=unique_fields,
    )

    created, updated, errors = importer.import_all(update_existing=update_existing)
    stats = importer.get_stats()

    return created, updated, errors, stats
