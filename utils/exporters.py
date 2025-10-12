import pandas as pd
import io
import csv
import json
import logging
import datetime
from django.http import HttpResponse
from django.db.models import QuerySet
from utils.export import ExcelExporter, CSVExporter

logger = logging.getLogger(__name__)


def export_to_excel(data, field_mapping=None):
    """
    تصدير البيانات إلى ملف Excel
    
    المعلمات:
    data (list): قائمة البيانات للتصدير
    field_mapping (dict): تعيين الحقول للعرض (من اسم الحقل في النظام إلى العنوان المعروض)
    
    تُرجع: كائن BytesIO يحتوي على بيانات Excel
    """
    try:
        # إذا تم تحديد تعيين الحقول، قم بتغيير أسماء الأعمدة
        if field_mapping:
            # نسخ البيانات لتجنب تعديل البيانات الأصلية
            formatted_data = []
            for item in data:
                formatted_item = {}
                for key, value in item.items():
                    if key in field_mapping:
                        formatted_item[field_mapping[key]] = value
                    else:
                        formatted_item[key] = value
                formatted_data.append(formatted_item)
        else:
            formatted_data = data
        
        # إنشاء DataFrame
        df = pd.DataFrame(formatted_data)
        
        # حفظ البيانات في ملف ذاكرة
        output = io.BytesIO()
        df.to_excel(output, index=False, engine='openpyxl')
        output.seek(0)
        
        return output
    
    except Exception as e:
        logger.error(f"خطأ في تصدير البيانات إلى Excel: {str(e)}")
        raise e


def export_to_csv(data, field_mapping=None):
    """
    تصدير البيانات إلى ملف CSV
    
    المعلمات:
    data (list): قائمة البيانات للتصدير
    field_mapping (dict): تعيين الحقول للعرض (من اسم الحقل في النظام إلى العنوان المعروض)
    
    تُرجع: كائن StringIO يحتوي على بيانات CSV
    """
    try:
        # إنشاء ملف ذاكرة
        output = io.StringIO()
        
        # إذا لم تكن هناك بيانات، أرجع ملف فارغ
        if not data:
            return output
        
        # تحديد الأعمدة
        if field_mapping:
            # الحصول على قائمة الحقول المتوفرة في البيانات
            all_fields = set()
            for item in data:
                all_fields.update(item.keys())
            
            # تهيئة الحقول المعروضة والعناوين
            fieldnames = []
            headers = []
            
            for field in all_fields:
                if field in field_mapping:
                    fieldnames.append(field)
                    headers.append(field_mapping[field])
            
            # إنشاء كاتب CSV مع العناوين المخصصة
            writer = csv.writer(output)
            writer.writerow(headers)
            
            # كتابة البيانات
            for item in data:
                row = [item.get(field, '') for field in fieldnames]
                writer.writerow(row)
        else:
            # استخدام كاتب القاموس مع الحقول الأصلية
            fieldnames = data[0].keys() if data else []
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        
        output.seek(0)
        return output
    
    except Exception as e:
        logger.error(f"خطأ في تصدير البيانات إلى CSV: {str(e)}")
        raise e


def export_to_json(data, field_mapping=None):
    """
    تصدير البيانات إلى ملف JSON
    
    المعلمات:
    data (list): قائمة البيانات للتصدير
    field_mapping (dict): تعيين الحقول للعرض (من اسم الحقل في النظام إلى العنوان المعروض)
    
    تُرجع: كائن StringIO يحتوي على بيانات JSON
    """
    try:
        # إذا تم تحديد تعيين الحقول، قم بتغيير أسماء الأعمدة
        if field_mapping:
            # نسخ البيانات لتجنب تعديل البيانات الأصلية
            formatted_data = []
            for item in data:
                formatted_item = {}
                for key, value in item.items():
                    if key in field_mapping:
                        formatted_item[field_mapping[key]] = value
                    else:
                        formatted_item[key] = value
                formatted_data.append(formatted_item)
        else:
            formatted_data = data
        
        # إنشاء ملف ذاكرة
        output = io.StringIO()
        
        # تحويل البيانات إلى JSON وكتابتها إلى الملف
        json.dump(formatted_data, output, ensure_ascii=False, indent=2)
        
        output.seek(0)
        return output
    
    except Exception as e:
        logger.error(f"خطأ في تصدير البيانات إلى JSON: {str(e)}")
        raise e


def generate_excel_response(data, field_mapping=None, filename='export'):
    """
    إنشاء كائن استجابة للتصدير إلى ملف Excel
    
    المعلمات:
    data (list): قائمة البيانات للتصدير
    field_mapping (dict): تعيين الحقول للعرض
    filename (str): اسم الملف المصدر بدون الامتداد
    
    تُرجع: كائن HttpResponse مع ملف Excel مرفق
    """
    buffer = export_to_excel(data, field_mapping)
    
    # إنشاء كائن استجابة
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}.xlsx"'
    
    return response


def generate_csv_response(data, field_mapping=None, filename='export'):
    """
    إنشاء كائن استجابة للتصدير إلى ملف CSV
    
    المعلمات:
    data (list): قائمة البيانات للتصدير
    field_mapping (dict): تعيين الحقول للعرض
    filename (str): اسم الملف المصدر بدون الامتداد
    
    تُرجع: كائن HttpResponse مع ملف CSV مرفق
    """
    buffer = export_to_csv(data, field_mapping)
    
    # إنشاء كائن استجابة
    response = HttpResponse(buffer.getvalue(), content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'
    
    return response


def generate_json_response(data, field_mapping=None, filename='export'):
    """
    إنشاء كائن استجابة للتصدير إلى ملف JSON
    
    المعلمات:
    data (list): قائمة البيانات للتصدير
    field_mapping (dict): تعيين الحقول للعرض
    filename (str): اسم الملف المصدر بدون الامتداد
    
    تُرجع: كائن HttpResponse مع ملف JSON مرفق
    """
    buffer = export_to_json(data, field_mapping)
    
    # إنشاء كائن استجابة
    response = HttpResponse(buffer.getvalue(), content_type='application/json')
    response['Content-Disposition'] = f'attachment; filename="{filename}.json"'
    
    return response


class PandasExporter:
    """
    فئة لتصدير البيانات باستخدام مكتبة pandas
    توفر وظائف متقدمة للتحليل والمعالجة قبل التصدير
    """
    
    def __init__(self, dataframe=None):
        """
        تهيئة مصدر البيانات
        
        المعلمات:
        dataframe (DataFrame): إطار بيانات pandas
        """
        self.df = dataframe if dataframe is not None else pd.DataFrame()
    
    @classmethod
    def from_queryset(cls, queryset, fields=None, annotations=None):
        """
        إنشاء مصدر بيانات من مجموعة استعلام
        
        المعلمات:
        queryset (QuerySet): مجموعة الاستعلام
        fields (list): قائمة بأسماء الحقول المراد تصديرها
        annotations (dict): قاموس بدالات الحصول على البيانات المشتقة
        
        تُرجع:
        PandasExporter: كائن من نوع PandasExporter
        """
        # تحديد الحقول المراد استخدامها
        if not fields:
            if hasattr(queryset.model, 'export_fields'):
                fields = queryset.model.export_fields
            else:
                # استخدام جميع الحقول في النموذج
                fields = [f.name for f in queryset.model._meta.fields if not f.name.startswith('_')]
        
        # استخراج البيانات من مجموعة الاستعلام
        data = []
        for obj in queryset:
            row_data = {}
            for field in fields:
                # التحقق من وجود دالة تعليق
                if annotations and field in annotations:
                    # استخدام دالة التعليق للحصول على القيمة
                    value = annotations[field](obj)
                else:
                    # محاولة الحصول على القيمة بطريقة عادية
                    try:
                        # التحقق من وجود خاصية أو طريقة بهذا الاسم
                        if hasattr(obj, field):
                            attr = getattr(obj, field)
                            # إذا كانت دالة، استدعها
                            if callable(attr):
                                value = attr()
                            else:
                                value = attr
                        else:
                            # قد يكون اسم حقل في علاقة متداخلة، مثل user.email
                            parts = field.split('.')
                            value = obj
                            for part in parts:
                                if value is None:
                                    break
                                value = getattr(value, part)
                                if callable(value):
                                    value = value()
                    except:
                        value = None
                
                row_data[field] = value
            
            data.append(row_data)
        
        # إنشاء إطار بيانات من القاموس
        df = pd.DataFrame(data)
        
        # إنشاء كائن المصدر
        return cls(df)
    
    @classmethod
    def from_data(cls, data):
        """
        إنشاء مصدر بيانات من بيانات مهيكلة
        
        المعلمات:
        data (list/dict): بيانات مهيكلة (قائمة أو قاموس)
        
        تُرجع:
        PandasExporter: كائن من نوع PandasExporter
        """
        # إنشاء إطار بيانات
        df = pd.DataFrame(data)
        
        # إنشاء كائن المصدر
        return cls(df)
    
    def filter(self, condition):
        """
        تصفية البيانات
        
        المعلمات:
        condition (str/func): شرط التصفية
        
        تُرجع:
        PandasExporter: نفس الكائن بعد التصفية
        """
        self.df = self.df.query(condition) if isinstance(condition, str) else self.df[condition]
        return self
    
    def sort(self, columns, ascending=True):
        """
        ترتيب البيانات
        
        المعلمات:
        columns (list/str): أسماء الأعمدة للترتيب
        ascending (bool/list): ترتيب تصاعدي أو تنازلي
        
        تُرجع:
        PandasExporter: نفس الكائن بعد الترتيب
        """
        self.df = self.df.sort_values(by=columns, ascending=ascending)
        return self
    
    def group_by(self, columns, agg_func=None):
        """
        تجميع البيانات
        
        المعلمات:
        columns (list/str): أسماء الأعمدة للتجميع
        agg_func (dict): دالات التجميع
        
        تُرجع:
        PandasExporter: نفس الكائن بعد التجميع
        """
        if agg_func:
            self.df = self.df.groupby(columns).agg(agg_func).reset_index()
        else:
            self.df = self.df.groupby(columns).count().reset_index()
        return self
    
    def pivot(self, index, columns, values, aggfunc='mean'):
        """
        إنشاء جدول محوري
        
        المعلمات:
        index (list/str): أسماء الأعمدة للصفوف
        columns (str): اسم العمود للأعمدة
        values (list/str): أسماء الأعمدة للقيم
        aggfunc (str/func): دالة التجميع
        
        تُرجع:
        PandasExporter: نفس الكائن بعد إنشاء الجدول المحوري
        """
        self.df = pd.pivot_table(self.df, index=index, columns=columns, values=values, aggfunc=aggfunc)
        return self
    
    def add_column(self, name, func):
        """
        إضافة عمود جديد
        
        المعلمات:
        name (str): اسم العمود الجديد
        func (func): دالة لحساب قيم العمود
        
        تُرجع:
        PandasExporter: نفس الكائن بعد إضافة العمود
        """
        self.df[name] = self.df.apply(func, axis=1)
        return self
    
    def rename_columns(self, columns_map):
        """
        إعادة تسمية الأعمدة
        
        المعلمات:
        columns_map (dict): قاموس بالأسماء القديمة والجديدة
        
        تُرجع:
        PandasExporter: نفس الكائن بعد إعادة التسمية
        """
        self.df = self.df.rename(columns=columns_map)
        return self
    
    def select_columns(self, columns):
        """
        اختيار أعمدة محددة
        
        المعلمات:
        columns (list): قائمة بأسماء الأعمدة المطلوبة
        
        تُرجع:
        PandasExporter: نفس الكائن بعد اختيار الأعمدة
        """
        self.df = self.df[columns]
        return self
    
    def to_excel(self, filename=None, sheet_name=None):
        """
        تصدير البيانات إلى ملف Excel
        
        المعلمات:
        filename (str): اسم ملف التصدير
        sheet_name (str): اسم الورقة في ملف Excel
        
        تُرجع:
        HttpResponse: استجابة HTTP تحتوي على ملف Excel
        """
        # إنشاء مصدر Excel
        exporter = ExcelExporter(filename=filename, sheet_name=sheet_name)
        
        # إضافة العناوين (أسماء الأعمدة)
        exporter.add_headers(self.df.columns.tolist())
        
        # إضافة البيانات
        exporter.add_data(self.df.values.tolist())
        
        # حفظ وإرجاع الاستجابة
        return exporter.save()
    
    def to_csv(self, filename=None):
        """
        تصدير البيانات إلى ملف CSV
        
        المعلمات:
        filename (str): اسم ملف التصدير
        
        تُرجع:
        HttpResponse: استجابة HTTP تحتوي على ملف CSV
        """
        # إنشاء مصدر CSV
        exporter = CSVExporter(filename=filename)
        
        # إضافة العناوين (أسماء الأعمدة)
        exporter.add_headers(self.df.columns.tolist())
        
        # إضافة البيانات
        exporter.add_data(self.df.values.tolist())
        
        # حفظ وإرجاع الاستجابة
        return exporter.save()
    
    def to_json(self, filename=None):
        """
        تصدير البيانات إلى ملف JSON
        
        المعلمات:
        filename (str): اسم ملف التصدير
        
        تُرجع:
        HttpResponse: استجابة HTTP تحتوي على ملف JSON
        """
        # تحويل البيانات إلى تنسيق JSON
        json_data = self.df.to_json(orient='records')
        
        # إنشاء اسم الملف
        if not filename:
            filename = f"export_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        elif not filename.endswith('.json'):
            filename += '.json'
        
        # إنشاء استجابة HTTP
        response = HttpResponse(json_data, content_type='application/json')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
    
    def to_html(self, filename=None):
        """
        تصدير البيانات إلى ملف HTML
        
        المعلمات:
        filename (str): اسم ملف التصدير
        
        تُرجع:
        HttpResponse: استجابة HTTP تحتوي على ملف HTML
        """
        # تحويل البيانات إلى تنسيق HTML
        html_data = self.df.to_html(index=False, classes=['table', 'table-striped', 'table-bordered'])
        
        # إضافة تنسيقات Bootstrap
        html_template = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>تقرير البيانات</title>
            <link href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css" rel="stylesheet">
            <style>
                body {{ direction: rtl; padding: 20px; }}
                h1 {{ text-align: center; margin-bottom: 20px; }}
                .table {{ margin-top: 20px; }}
                .table th {{ background-color: #4F81BD; color: white; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>تقرير البيانات</h1>
                <div class="table-responsive">
                    {html_data}
                </div>
                <p class="text-muted mt-3">تم إنشاؤه في: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
        </body>
        </html>
        """
        
        # إنشاء اسم الملف
        if not filename:
            filename = f"export_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        elif not filename.endswith('.html'):
            filename += '.html'
        
        # إنشاء استجابة HTTP
        response = HttpResponse(html_template, content_type='text/html')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
    
    def to_df(self):
        """
        إرجاع إطار البيانات pandas
        
        تُرجع:
        DataFrame: إطار البيانات pandas
        """
        return self.df


def export_queryset_to_pandas(queryset, fields=None, annotations=None):
    """
    تصدير مجموعة استعلام إلى مصدر pandas
    
    المعلمات:
    queryset (QuerySet): مجموعة الاستعلام
    fields (list): قائمة بأسماء الحقول المراد تصديرها
    annotations (dict): قاموس بدالات الحصول على البيانات المشتقة
    
    تُرجع:
    PandasExporter: كائن من نوع PandasExporter
    """
    return PandasExporter.from_queryset(queryset, fields=fields, annotations=annotations)


def export_data_to_pandas(data):
    """
    تصدير بيانات إلى مصدر pandas
    
    المعلمات:
    data (list/dict): بيانات مهيكلة (قائمة أو قاموس)
    
    تُرجع:
    PandasExporter: كائن من نوع PandasExporter
    """
    return PandasExporter.from_data(data) 