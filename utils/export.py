import xlsxwriter
import io
from django.http import HttpResponse
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT
import csv
import os
import datetime
from io import BytesIO
from django.utils.translation import gettext as _


def export_to_excel(data, fields, headers=None, sheet_name='Sheet1'):
    """
    تصدير بيانات إلى ملف Excel
    
    المعلمات:
    data (list): قائمة بالبيانات للتصدير، حيث كل عنصر هو قاموس (dict)
    fields (list): قائمة بأسماء الحقول للتصدير
    headers (list): قائمة بعناوين الأعمدة (اختياري)
    sheet_name (str): اسم ورقة العمل
    
    تُرجع: HttpResponse مع ملف Excel
    """
    # إنشاء ملف Excel في الذاكرة
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet(sheet_name)
    
    # تنسيق للعناوين
    header_format = workbook.add_format({
        'bold': True,
        'align': 'center',
        'valign': 'vcenter',
        'bg_color': '#D3D3D3',
        'border': 1
    })
    
    # تنسيق للخلايا
    cell_format = workbook.add_format({
        'align': 'center',
        'valign': 'vcenter',
        'border': 1
    })
    
    # إضافة العناوين
    if headers:
        for col_num, header in enumerate(headers):
            worksheet.write(0, col_num, header, header_format)
    else:
        for col_num, field in enumerate(fields):
            worksheet.write(0, col_num, field, header_format)
    
    # إضافة البيانات
    for row_num, item in enumerate(data):
        for col_num, field in enumerate(fields):
            value = item.get(field, '')
            worksheet.write(row_num + 1, col_num, value, cell_format)
    
    # ضبط عرض الأعمدة تلقائيًا
    for col_num in range(len(fields)):
        worksheet.set_column(col_num, col_num, 15)
    
    # إغلاق الملف وإرجاع المحتوى
    workbook.close()
    output.seek(0)
    
    return output.getvalue()


def export_to_pdf(data, fields, headers=None, title='تقرير', orientation='portrait'):
    """
    تصدير بيانات إلى ملف PDF
    
    المعلمات:
    data (list): قائمة بالبيانات للتصدير، حيث كل عنصر هو قاموس (dict)
    fields (list): قائمة بأسماء الحقول للتصدير
    headers (list): قائمة بعناوين الأعمدة (اختياري)
    title (str): عنوان التقرير
    orientation (str): اتجاه الصفحة ('portrait' أو 'landscape')
    
    تُرجع: HttpResponse مع ملف PDF
    """
    # إنشاء ملف PDF في الذاكرة
    buffer = io.BytesIO()
    
    # تحديد حجم الصفحة
    page_size = A4
    if orientation == 'landscape':
        page_size = (A4[1], A4[0])  # تبديل العرض والارتفاع
    
    # إنشاء مستند PDF
    doc = SimpleDocTemplate(buffer, pagesize=page_size, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    
    # تحميل الخط العربي (مع افتراض أن الخط موجود في المسار المحدد)
    try:
        # محاولة تسجيل الخط، إذا كان الخط غير موجود، يستخدم الخط الافتراضي
        pdfmetrics.registerFont(TTFont('Arabic', 'static/fonts/arabic.ttf'))
    except:
        # استخدام الخط الافتراضي إذا فشل تحميل الخط العربي
        pass
    
    # إنشاء أنماط للنصوص
    styles = getSampleStyleSheet()
    
    # إنشاء نمط للنص العربي
    arabic_style = ParagraphStyle(
        'Arabic',
        parent=styles['Heading1'],
        fontName='Arabic' if 'Arabic' in pdfmetrics.getRegisteredFontNames() else 'Helvetica',
        alignment=TA_RIGHT,
        fontSize=14,
        leading=16
    )
    
    # إنشاء عناصر المستند
    elements = []
    
    # إضافة عنوان التقرير
    title_paragraph = Paragraph(title, arabic_style)
    elements.append(title_paragraph)
    elements.append(Paragraph("<br/><br/>", styles['Normal']))
    
    # إعداد البيانات للجدول
    if not headers:
        headers = fields
    
    table_data = []
    table_data.append(headers)
    
    for item in data:
        row = []
        for field in fields:
            value = item.get(field, '')
            # تحويل القيم إلى نصوص
            row.append(str(value))
        table_data.append(row)
    
    # إنشاء الجدول
    if table_data:
        table = Table(table_data)
        
        # تنسيق الجدول
        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Arabic' if 'Arabic' in pdfmetrics.getRegisteredFontNames() else 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ])
        
        # إضافة تنسيق لصفوف البيانات
        for i, row in enumerate(table_data):
            if i > 0:
                style.add('FONTNAME', (0, i), (-1, i), 'Arabic' if 'Arabic' in pdfmetrics.getRegisteredFontNames() else 'Helvetica')
                style.add('FONTSIZE', (0, i), (-1, i), 10)
                
                # تلوين الصفوف البديلة
                if i % 2 == 0:
                    style.add('BACKGROUND', (0, i), (-1, i), colors.lightgrey)
        
        table.setStyle(style)
        elements.append(table)
    
    # بناء المستند
    doc.build(elements)
    
    # إرجاع محتوى الملف
    buffer.seek(0)
    
    return buffer.getvalue()


def export_to_csv(data, fields, headers=None):
    """
    تصدير بيانات إلى ملف CSV
    
    المعلمات:
    data (list): قائمة بالبيانات للتصدير، حيث كل عنصر هو قاموس (dict)
    fields (list): قائمة بأسماء الحقول للتصدير
    headers (list): قائمة بعناوين الأعمدة (اختياري)
    
    تُرجع: HttpResponse مع ملف CSV
    """
    # إنشاء ملف CSV في الذاكرة
    output = io.StringIO()
    writer = csv.writer(output)
    
    # كتابة العناوين
    if headers:
        writer.writerow(headers)
    else:
        writer.writerow(fields)
    
    # كتابة البيانات
    for item in data:
        row = []
        for field in fields:
            value = item.get(field, '')
            row.append(str(value))
        writer.writerow(row)
    
    # إعادة مؤشر القراءة إلى بداية الملف
    output.seek(0)
    
    return output.getvalue()


def generate_report_response(data, fields, headers, format_type, filename_prefix):
    """
    إنشاء استجابة HTTP مع الملف المصدر
    
    المعلمات:
    data (list): البيانات للتصدير
    fields (list): الحقول للتصدير
    headers (list): عناوين الأعمدة
    format_type (str): نوع التنسيق ('excel', 'pdf', 'csv')
    filename_prefix (str): بادئة اسم الملف
    
    تُرجع: HttpResponse
    """
    if format_type == 'excel':
        content = export_to_excel(data, fields, headers)
        response = HttpResponse(content, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="{filename_prefix}.xlsx"'
    elif format_type == 'pdf':
        content = export_to_pdf(data, fields, headers, title=f'تقرير {filename_prefix}')
        response = HttpResponse(content, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename_prefix}.pdf"'
    elif format_type == 'csv':
        content = export_to_csv(data, fields, headers)
        response = HttpResponse(content, content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename_prefix}.csv"'
    else:
        # إذا كان التنسيق غير معروف، ارجع استجابة خطأ
        response = HttpResponse(status=400)
    
    return response 


class ExcelExporter:
    """
    فئة لتصدير البيانات إلى ملف Excel
    """
    
    def __init__(self, filename=None, sheet_name=None):
        """
        تهيئة مصدر ملفات Excel
        
        المعلمات:
        filename (str): اسم ملف التصدير
        sheet_name (str): اسم الورقة في ملف Excel
        """
        self.filename = filename or f"export_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        self.sheet_name = sheet_name or "Sheet1"
        
        # التأكد من إضافة امتداد الملف المناسب
        if not self.filename.endswith('.xlsx'):
            self.filename += '.xlsx'
        
        # تهيئة كائن الذاكرة المؤقتة لتخزين الملف
        self.output = BytesIO()
        
        # إنشاء كتاب عمل جديد
        self.workbook = xlsxwriter.Workbook(self.output)
        
        # إنشاء ورقة عمل جديدة
        self.worksheet = self.workbook.add_worksheet(self.sheet_name)
        
        # إنشاء تنسيقات
        self.header_format = self.workbook.add_format({
            'bold': True,
            'bg_color': '#4F81BD',
            'font_color': 'white',
            'align': 'center',
            'valign': 'vcenter',
            'border': 1
        })
        
        self.data_format = self.workbook.add_format({
            'border': 1
        })
        
        self.date_format = self.workbook.add_format({
            'border': 1,
            'num_format': 'yyyy-mm-dd'
        })
        
        self.number_format = self.workbook.add_format({
            'border': 1,
            'num_format': '#,##0.00'
        })
        
        # تتبع الصف الحالي
        self.current_row = 0
    
    def add_headers(self, headers):
        """
        إضافة صف العناوين
        
        المعلمات:
        headers (list): قائمة بعناوين الأعمدة
        """
        for col, header in enumerate(headers):
            self.worksheet.write(self.current_row, col, header, self.header_format)
        
        # تعيين عرض الأعمدة بناءً على النصوص
        for col, header in enumerate(headers):
            width = max(15, len(str(header)) + 2)  # الحد الأدنى للعرض هو 15
            self.worksheet.set_column(col, col, width)
        
        self.current_row += 1
        return self
    
    def add_data(self, data_rows):
        """
        إضافة صفوف البيانات
        
        المعلمات:
        data_rows (list): قائمة بصفوف البيانات، كل صف عبارة عن قائمة بالخلايا
        """
        for row_data in data_rows:
            for col, cell_data in enumerate(row_data):
                # تنسيق البيانات حسب نوعها
                if isinstance(cell_data, datetime.date) or isinstance(cell_data, datetime.datetime):
                    self.worksheet.write(self.current_row, col, cell_data, self.date_format)
                elif isinstance(cell_data, (int, float)):
                    self.worksheet.write(self.current_row, col, cell_data, self.number_format)
                else:
                    self.worksheet.write(self.current_row, col, cell_data, self.data_format)
            
            self.current_row += 1
        
        return self
    
    def add_queryset(self, queryset, fields=None, headers=None, annotations=None):
        """
        إضافة بيانات من مجموعة استعلام
        
        المعلمات:
        queryset (QuerySet): مجموعة الاستعلام
        fields (list): قائمة بأسماء الحقول المراد تصديرها
        headers (list): قائمة بعناوين الأعمدة (اختياري)
        annotations (dict): قاموس بدالات الحصول على البيانات المشتقة
        """
        if not fields:
            if hasattr(queryset.model, 'export_fields'):
                fields = queryset.model.export_fields
            else:
                # استخدام جميع الحقول المعروضة في النموذج
                fields = [f.name for f in queryset.model._meta.fields if not f.name.startswith('_')]
        
        # إذا لم يتم تحديد العناوين، استخدم أسماء الحقول
        if not headers:
            headers = []
            for field in fields:
                if hasattr(queryset.model, 'get_export_field_name'):
                    headers.append(queryset.model.get_export_field_name(field))
                else:
                    # محاولة الحصول على الاسم المعروض للحقل
                    try:
                        field_obj = queryset.model._meta.get_field(field)
                        header = field_obj.verbose_name
                    except:
                        header = field.replace('_', ' ').title()
                    headers.append(header)
        
        # إضافة العناوين
        self.add_headers(headers)
        
        # إضافة صفوف البيانات
        for obj in queryset:
            row_data = []
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
                        value = "N/A"
                
                row_data.append(value)
            
            self.add_data([row_data])
        
        return self
    
    def save(self):
        """
        حفظ ملف Excel وإعادة استجابة HTTP
        
        تُرجع:
        HttpResponse: استجابة HTTP تحتوي على ملف Excel
        """
        # إغلاق كتاب العمل لإكمال الكتابة إلى BytesIO
        self.workbook.close()
        
        # إعادة مؤشر القراءة/الكتابة إلى بداية الملف
        self.output.seek(0)
        
        # إنشاء استجابة HTTP
        response = HttpResponse(
            self.output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{self.filename}"'
        
        return response
    
    def save_to_file(self, filepath=None):
        """
        حفظ ملف Excel إلى المسار المحدد
        
        المعلمات:
        filepath (str): المسار الكامل لملف Excel
        
        تُرجع:
        str: مسار الملف المحفوظ
        """
        # إذا لم يتم تحديد مسار، استخدم اسم الملف فقط
        if not filepath:
            filepath = self.filename
        
        # إغلاق كتاب العمل الحالي
        self.workbook.close()
        
        # إعادة إنشاء كتاب عمل جديد بالمسار المحدد
        workbook = xlsxwriter.Workbook(filepath)
        
        # كتابة البيانات من BytesIO إلى الملف
        with open(filepath, 'wb') as f:
            f.write(self.output.getvalue())
        
        return filepath


class CSVExporter:
    """
    فئة لتصدير البيانات إلى ملف CSV
    """
    
    def __init__(self, filename=None):
        """
        تهيئة مصدر ملفات CSV
        
        المعلمات:
        filename (str): اسم ملف التصدير
        """
        self.filename = filename or f"export_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        # التأكد من إضافة امتداد الملف المناسب
        if not self.filename.endswith('.csv'):
            self.filename += '.csv'
        
        # تهيئة كائن الذاكرة المؤقتة لتخزين الملف
        self.output = BytesIO()
        
        # إنشاء كاتب CSV
        self.writer = None
        
        # تخزين البيانات مؤقتًا
        self.headers = None
        self.data_rows = []
    
    def add_headers(self, headers):
        """
        إضافة صف العناوين
        
        المعلمات:
        headers (list): قائمة بعناوين الأعمدة
        """
        self.headers = headers
        return self
    
    def add_data(self, data_rows):
        """
        إضافة صفوف البيانات
        
        المعلمات:
        data_rows (list): قائمة بصفوف البيانات، كل صف عبارة عن قائمة بالخلايا
        """
        self.data_rows.extend(data_rows)
        return self
    
    def add_queryset(self, queryset, fields=None, headers=None, annotations=None):
        """
        إضافة بيانات من مجموعة استعلام
        
        المعلمات:
        queryset (QuerySet): مجموعة الاستعلام
        fields (list): قائمة بأسماء الحقول المراد تصديرها
        headers (list): قائمة بعناوين الأعمدة (اختياري)
        annotations (dict): قاموس بدالات الحصول على البيانات المشتقة
        """
        if not fields:
            if hasattr(queryset.model, 'export_fields'):
                fields = queryset.model.export_fields
            else:
                # استخدام جميع الحقول المعروضة في النموذج
                fields = [f.name for f in queryset.model._meta.fields if not f.name.startswith('_')]
        
        # إذا لم يتم تحديد العناوين، استخدم أسماء الحقول
        if not headers:
            headers = []
            for field in fields:
                if hasattr(queryset.model, 'get_export_field_name'):
                    headers.append(queryset.model.get_export_field_name(field))
                else:
                    # محاولة الحصول على الاسم المعروض للحقل
                    try:
                        field_obj = queryset.model._meta.get_field(field)
                        header = field_obj.verbose_name
                    except:
                        header = field.replace('_', ' ').title()
                    headers.append(header)
        
        # إضافة العناوين
        self.add_headers(headers)
        
        # إضافة صفوف البيانات
        data_rows = []
        for obj in queryset:
            row_data = []
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
                        value = "N/A"
                
                # تحويل التاريخ والوقت إلى سلسلة نصية
                if isinstance(value, (datetime.date, datetime.datetime)):
                    value = value.isoformat()
                
                row_data.append(value)
            
            data_rows.append(row_data)
        
        self.add_data(data_rows)
        return self
    
    def save(self):
        """
        حفظ ملف CSV وإعادة استجابة HTTP
        
        تُرجع:
        HttpResponse: استجابة HTTP تحتوي على ملف CSV
        """
        # إنشاء كائن CSV في الذاكرة
        self.output = BytesIO()
        self.writer = csv.writer(self.output)
        
        # كتابة العناوين
        if self.headers:
            self.writer.writerow(self.headers)
        
        # كتابة البيانات
        for row_data in self.data_rows:
            self.writer.writerow(row_data)
        
        # إعادة مؤشر القراءة/الكتابة إلى بداية الملف
        self.output.seek(0)
        
        # إنشاء استجابة HTTP
        response = HttpResponse(self.output.read(), content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{self.filename}"'
        
        return response
    
    def save_to_file(self, filepath=None):
        """
        حفظ ملف CSV إلى المسار المحدد
        
        المعلمات:
        filepath (str): المسار الكامل لملف CSV
        
        تُرجع:
        str: مسار الملف المحفوظ
        """
        # إذا لم يتم تحديد مسار، استخدم اسم الملف فقط
        if not filepath:
            filepath = self.filename
        
        with open(filepath, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            
            # كتابة العناوين
            if self.headers:
                writer.writerow(self.headers)
            
            # كتابة البيانات
            for row_data in self.data_rows:
                writer.writerow(row_data)
        
        return filepath


def export_queryset_to_excel(queryset, filename=None, sheet_name=None, fields=None, headers=None, annotations=None):
    """
    تصدير مجموعة استعلام إلى ملف Excel
    
    المعلمات:
    queryset (QuerySet): مجموعة الاستعلام
    filename (str): اسم ملف التصدير
    sheet_name (str): اسم الورقة في ملف Excel
    fields (list): قائمة بأسماء الحقول المراد تصديرها
    headers (list): قائمة بعناوين الأعمدة
    annotations (dict): قاموس بدالات الحصول على البيانات المشتقة
    
    تُرجع:
    HttpResponse: استجابة HTTP تحتوي على ملف Excel
    """
    exporter = ExcelExporter(filename=filename, sheet_name=sheet_name)
    return exporter.add_queryset(queryset, fields=fields, headers=headers, annotations=annotations).save()


def export_queryset_to_csv(queryset, filename=None, fields=None, headers=None, annotations=None):
    """
    تصدير مجموعة استعلام إلى ملف CSV
    
    المعلمات:
    queryset (QuerySet): مجموعة الاستعلام
    filename (str): اسم ملف التصدير
    fields (list): قائمة بأسماء الحقول المراد تصديرها
    headers (list): قائمة بعناوين الأعمدة
    annotations (dict): قاموس بدالات الحصول على البيانات المشتقة
    
    تُرجع:
    HttpResponse: استجابة HTTP تحتوي على ملف CSV
    """
    exporter = CSVExporter(filename=filename)
    return exporter.add_queryset(queryset, fields=fields, headers=headers, annotations=annotations).save() 