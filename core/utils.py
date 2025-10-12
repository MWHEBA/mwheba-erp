from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
import random
import string
import re
import datetime
from decimal import Decimal
from dateutil.relativedelta import relativedelta
import math
import locale


def format_currency(amount, currency_code='EGP', decimal_places=2, show_symbol=True):
    """
    تنسيق المبلغ بعملة معينة
    
    المعلمات:
    amount (float, int, Decimal): المبلغ المراد تنسيقه
    currency_code (str): رمز العملة مثل EGP, USD
    decimal_places (int): عدد المنازل العشرية
    show_symbol (bool): عرض رمز العملة أم لا
    
    تُرجع: سلسلة نصية تمثل المبلغ بتنسيق العملة المحددة
    """
    # تحديد رمز العملة المناسب
    currency_symbols = {
        'EGP': 'ج.م',
        'USD': '$',
        'EUR': '€',
        'GBP': '£',
        'SAR': 'ر.س',
        'AED': 'د.إ',
        'KWD': 'د.ك',
    }
    
    # تنسيق المبلغ كرقم
    formatted_amount = format_number(amount, decimal_places=decimal_places)
    
    # إضافة رمز العملة إذا كان مطلوبًا
    if show_symbol:
        symbol = currency_symbols.get(currency_code, currency_code)
        if currency_code == 'USD' or currency_code == 'EUR' or currency_code == 'GBP':
            return f"{symbol}{formatted_amount}"
        else:
            return f"{formatted_amount} {symbol}"
    
    return formatted_amount


def format_number(number, decimal_places=None, thousand_separator=',', decimal_separator='.'):
    """
    تنسيق الرقم بفواصل الآلاف والعلامة العشرية
    
    المعلمات:
    number (float, int, Decimal): الرقم المراد تنسيقه
    decimal_places (int): عدد المنازل العشرية، إذا كان None فلن يتم تحديد عدد المنازل العشرية
    thousand_separator (str): الفاصل للآلاف
    decimal_separator (str): الفاصل العشري
    
    تُرجع: سلسلة نصية للرقم المنسق
    """
    if number is None:
        return '0'
    
    # تحويل الرقم إلى Decimal للتعامل بدقة مع الأرقام العشرية
    if not isinstance(number, Decimal):
        number = Decimal(str(number))
    
    # التقريب إلى عدد المنازل العشرية المحدد
    if decimal_places is not None:
        number = round(number, decimal_places)
    
    # تقسيم الرقم إلى جزء صحيح وعشري
    integer_part, decimal_part = str(number).split('.') if '.' in str(number) else (str(number), '0')
    
    # تنسيق الجزء الصحيح بفواصل الآلاف
    integer_part = thousand_separator.join([integer_part[max(0, i - 3):i] for i in range(len(integer_part), 0, -3)][::-1])
    
    # إذا تم تحديد عدد المنازل العشرية، قم بضبط طول الجزء العشري
    if decimal_places is not None:
        decimal_part = decimal_part.ljust(decimal_places, '0')[:decimal_places]
        # إذا كان عدد المنازل العشرية 0، فلا تعرض الجزء العشري
        if decimal_places == 0:
            return integer_part
    
    # إذا كان هناك جزء عشري، أضفه إلى الجزء الصحيح
    if decimal_part != '0' or (decimal_places is not None and decimal_places > 0):
        return f"{integer_part}{decimal_separator}{decimal_part}"
    else:
        return integer_part


def format_date(date_obj, date_format='default'):
    """
    تنسيق التاريخ بنمط معين
    
    المعلمات:
    date_obj (date, datetime): كائن التاريخ المراد تنسيقه
    date_format (str): نمط التنسيق ('default', 'short', 'long')
    
    تُرجع: سلسلة نصية للتاريخ المنسق
    """
    if date_obj is None:
        return ''
    
    # التحقق من نوع الكائن
    if not isinstance(date_obj, (datetime.date, datetime.datetime)):
        raise TypeError("التاريخ يجب أن يكون من نوع date أو datetime")
    
    # إذا كان كائن datetime، استخرج التاريخ فقط
    if isinstance(date_obj, datetime.datetime):
        date_obj = date_obj.date()
    
    # تنسيق التاريخ بناءً على النمط المحدد
    if date_format == 'short':
        return date_obj.strftime('%d/%m/%Y')
    elif date_format == 'long':
        # استخدام أسماء الأشهر العربية
        month_names_ar = [
            'يناير', 'فبراير', 'مارس', 'إبريل', 'مايو', 'يونيو',
            'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر'
        ]
        return f"{date_obj.day} {month_names_ar[date_obj.month - 1]} {date_obj.year}"
    else:  # default
        return date_obj.strftime('%Y-%m-%d')


def calculate_total(items, discount=0, tax_rate=0):
    """
    حساب المجموع الإجمالي لقائمة من العناصر
    
    المعلمات:
    items (list): قائمة من العناصر، كل عنصر عبارة عن قاموس به price و quantity
    discount (float, int, Decimal): قيمة الخصم
    tax_rate (float, int, Decimal): نسبة الضريبة (0-100)
    
    تُرجع: المجموع الإجمالي بعد الخصم والضريبة
    """
    if not items:
        return 0
    
    # حساب المجموع قبل الخصم والضريبة
    subtotal = sum(item['price'] * item['quantity'] for item in items)
    
    # حساب المجموع بعد الخصم
    if discount:
        subtotal = subtotal - discount
    
    # حساب المجموع بعد الضريبة
    if tax_rate:
        tax_multiplier = tax_rate / 100
        subtotal = subtotal + (subtotal * tax_multiplier)
    
    # التحقق مما إذا كان المجموع عشري
    if any(isinstance(item['price'], Decimal) for item in items):
        return Decimal(str(subtotal))
    
    return subtotal


def calculate_due_date(start_date, days=0):
    """
    حساب تاريخ الاستحقاق بناءً على تاريخ البداية وعدد الأيام
    
    المعلمات:
    start_date (date, datetime): تاريخ البداية
    days (int): عدد الأيام للإضافة
    
    تُرجع: تاريخ الاستحقاق ككائن date
    """
    if start_date is None:
        return None
    
    # التحقق من صحة تاريخ البداية
    if isinstance(start_date, datetime.datetime):
        start_date = start_date.date()
    elif not isinstance(start_date, datetime.date):
        raise TypeError("تاريخ البداية يجب أن يكون من نوع date أو datetime")
    
    # التحقق من عدد الأيام
    if days <= 0:
        return start_date
    
    # حساب تاريخ الاستحقاق
    due_date = start_date + datetime.timedelta(days=days)
    return due_date


def is_arabic_text(text):
    """
    التحقق مما إذا كان النص يحتوي على أحرف عربية فقط
    
    المعلمات:
    text (str): النص المراد فحصه
    
    تُرجع: True إذا كان النص عربيًا، False خلاف ذلك
    """
    if not text:
        return False
    
    # تعريف نمط للأحرف العربية والأرقام وعلامات الترقيم
    arabic_pattern = re.compile(r'^[\u0600-\u06FF\s0-9.,!؟:؛،\(\)]+$')
    
    return bool(arabic_pattern.match(text))


def validate_phone_number(phone_number):
    """
    التحقق من صحة رقم الهاتف
    
    المعلمات:
    phone_number (str): رقم الهاتف المراد التحقق منه
    
    تُرجع: True إذا كان الرقم صحيحًا، False خلاف ذلك
    """
    if not phone_number:
        return False
    
    # تنظيف رقم الهاتف من الأحرف غير الرقمية
    phone_number = re.sub(r'\D', '', phone_number)
    
    # التحقق من طول رقم الهاتف (يمكن تعديل هذا حسب قواعد البلد)
    if len(phone_number) < 10 or len(phone_number) > 15:
        return False
    
    # التحقق من صيغة رقم الهاتف المصري
    egyptian_pattern = re.compile(r'^01[0-9]{9}$')
    if len(phone_number) == 11 and egyptian_pattern.match(phone_number):
        return True
    
    # التحقق من صيغة رقم الهاتف الدولي
    international_pattern = re.compile(r'^\d{10,15}$')
    return bool(international_pattern.match(phone_number))


def generate_invoice_number(prefix='INV', length=6):
    """
    توليد رقم فاتورة فريد
    
    المعلمات:
    prefix (str): بادئة لرقم الفاتورة
    length (int): طول الجزء العددي من رقم الفاتورة
    
    تُرجع: رقم فاتورة فريد
    """
    now = timezone.now()
    year = now.year
    month = now.month
    
    # توليد رقم عشوائي للجزء العددي
    random_part = ''.join(random.choices(string.digits, k=length))
    
    # بناء رقم الفاتورة
    invoice_number = f"{prefix}-{year}{month:02d}-{random_part}"
    
    return invoice_number


def get_default_currency():
    """
    استرجاع العملة الافتراضية من إعدادات التطبيق
    
    تُرجع: رمز العملة الافتراضية
    """
    # يمكن استرجاع العملة من إعدادات التطبيق أو قاعدة البيانات
    return getattr(settings, 'DEFAULT_CURRENCY', 'EGP')


def get_tax_rate():
    """
    استرجاع معدل الضريبة الافتراضي من إعدادات التطبيق
    
    تُرجع: معدل الضريبة الافتراضي
    """
    # يمكن استرجاع معدل الضريبة من إعدادات التطبيق أو قاعدة البيانات
    return getattr(settings, 'DEFAULT_TAX_RATE', Decimal('14.0'))


def get_financial_period(period_type='month', date=None):
    """
    استرجاع الفترة المالية (بداية ونهاية) لفترة معينة
    
    المعلمات:
    period_type (str): نوع الفترة ('day', 'week', 'month', 'quarter', 'year')
    date (date): التاريخ المرجعي، إذا كان None فسيتم استخدام التاريخ الحالي
    
    تُرجع: (تاريخ البداية، تاريخ النهاية)
    """
    if date is None:
        date = timezone.now().date()
    elif isinstance(date, datetime.datetime):
        date = date.date()
    
    if period_type == 'day':
        return date, date
    elif period_type == 'week':
        # اعتبار أن بداية الأسبوع هي الأحد
        start = date - datetime.timedelta(days=date.weekday() + 1)  # الأحد
        end = start + datetime.timedelta(days=6)  # السبت
        return start, end
    elif period_type == 'month':
        start = date.replace(day=1)
        # آخر يوم في الشهر
        if date.month == 12:
            end = date.replace(day=31)
        else:
            next_month = date.replace(month=date.month + 1, day=1)
            end = next_month - datetime.timedelta(days=1)
        return start, end
    elif period_type == 'quarter':
        # تحديد الربع الحالي
        quarter = (date.month - 1) // 3 + 1
        start_month = (quarter - 1) * 3 + 1
        end_month = quarter * 3
        
        start = date.replace(month=start_month, day=1)
        end = date.replace(month=end_month)
        
        # آخر يوم في آخر شهر من الربع
        if end_month == 12:
            end = end.replace(day=31)
        else:
            next_month = end.replace(month=end_month + 1, day=1)
            end = next_month - datetime.timedelta(days=1)
        
        return start, end
    elif period_type == 'year':
        start = date.replace(month=1, day=1)
        end = date.replace(month=12, day=31)
        return start, end
    else:
        raise ValueError(f"نوع الفترة غير صالح: {period_type}")


def get_date_range(start_date, end_date, interval='days'):
    """
    استرجاع قائمة بالتواريخ ضمن نطاق معين
    
    المعلمات:
    start_date (date): تاريخ البداية
    end_date (date): تاريخ النهاية
    interval (str): الفاصل الزمني ('days', 'weeks', 'months')
    
    تُرجع: قائمة من التواريخ
    """
    if not isinstance(start_date, datetime.date) or not isinstance(end_date, datetime.date):
        raise TypeError("التواريخ يجب أن تكون من نوع date")
    
    if start_date > end_date:
        return []
    
    result = []
    current = start_date
    
    while current <= end_date:
        result.append(current)
        if interval == 'days':
            current += datetime.timedelta(days=1)
        elif interval == 'weeks':
            current += datetime.timedelta(weeks=1)
        elif interval == 'months':
            # استخدام relativedelta للتعامل مع الأشهر بشكل صحيح
            current += relativedelta(months=1)
        else:
            raise ValueError(f"فاصل زمني غير صالح: {interval}")
    
    return result


def get_model_permissions(model):
    """
    الحصول على كافة الأذونات المرتبطة بنموذج معين
    
    المعلمات:
    model (Model): نموذج جانغو
    
    تُرجع: قائمة الأذونات
    """
    content_type = ContentType.objects.get_for_model(model)
    return Permission.objects.filter(content_type=content_type)


def create_user_group(name, permissions=None):
    """
    إنشاء مجموعة مستخدمين جديدة أو إرجاع المجموعة الموجودة
    
    المعلمات:
    name (str): اسم المجموعة
    permissions (list): قائمة الأذونات
    
    تُرجع: مجموعة المستخدمين
    """
    group, created = Group.objects.get_or_create(name=name)
    
    if created and permissions:
        for permission in permissions:
            group.permissions.add(permission)
    
    return group


def generate_report(model, report_type, start_date=None, end_date=None, filters=None, user=None):
    """
    توليد تقرير استنادًا إلى النموذج ونوع التقرير
    
    المعلمات:
    model (Model): نموذج جانغو
    report_type (str): نوع التقرير
    start_date (date): تاريخ بدء التقرير
    end_date (date): تاريخ نهاية التقرير
    filters (dict): مرشحات إضافية
    user (User): المستخدم الذي طلب التقرير
    
    تُرجع: بيانات التقرير
    """
    if end_date is None:
        end_date = timezone.now().date()
    
    if start_date is None:
        start_date = end_date - datetime.timedelta(days=30)
    
    # تهيئة مرشحات البحث
    query_filters = {}
    
    # إضافة تصفية التاريخ إذا كان ذلك مناسبًا للنموذج
    date_field = 'created_at'
    if hasattr(model, 'created_at'):
        query_filters[f'{date_field}__gte'] = start_date
        query_filters[f'{date_field}__lte'] = end_date
    
    # إضافة مرشحات إضافية
    if filters:
        query_filters.update(filters)
    
    # استعلام البيانات
    queryset = model.objects.filter(**query_filters)
    
    # تهيئة معلومات التقرير
    report_data = {
        'model': model.__name__,
        'data': list(queryset.values()),
        'metadata': {
            'report_type': report_type,
            'start_date': start_date,
            'end_date': end_date,
            'filters': filters,
            'generated_at': timezone.now(),
            'generated_by': user.username if user else None,
            'total_count': queryset.count(),
        }
    }
    
    return report_data


def clean_html(html_content):
    """
    تنظيف محتوى HTML من النصوص البرمجية الضارة
    
    المعلمات:
    html_content (str): محتوى HTML
    
    تُرجع: محتوى HTML نظيف
    """
    # هذه تنفيذ بسيط، يمكن استخدام مكتبات مثل bleach للتنفيذ الحقيقي
    if not html_content:
        return ""
    
    # إزالة النصوص البرمجية
    clean_content = re.sub(r'<script.*?>.*?</script>', '', html_content, flags=re.DOTALL)
    
    # إزالة الأحداث المضمنة
    clean_content = re.sub(r' on\w+=".*?"', '', clean_content, flags=re.IGNORECASE)
    
    # إزالة إطارات iframe
    clean_content = re.sub(r'<iframe.*?>.*?</iframe>', '', clean_content, flags=re.DOTALL)
    
    return clean_content


def paginate_queryset(queryset, page_size, page_number):
    """
    تقسيم استعلام إلى صفحات
    
    المعلمات:
    queryset (QuerySet): الاستعلام للتقسيم
    page_size (int): حجم الصفحة
    page_number (int): رقم الصفحة
    
    تُرجع: (قائمة العناصر، إجمالي العناصر، إجمالي الصفحات)
    """
    # التحقق من صحة المدخلات
    if page_size <= 0:
        page_size = 10
    
    if page_number <= 0:
        page_number = 1
    
    # حساب العدد الإجمالي والصفحات
    total_items = queryset.count()
    total_pages = math.ceil(total_items / page_size)
    
    # تصحيح رقم الصفحة إذا كان أكبر من العدد الإجمالي
    if page_number > total_pages and total_pages > 0:
        page_number = total_pages
    
    # حساب الفهارس
    start_index = (page_number - 1) * page_size
    end_index = start_index + page_size
    
    # الحصول على عناصر الصفحة
    page_items = list(queryset[start_index:end_index])
    
    return page_items, total_items, total_pages


def generate_unique_slug(model, title, slug_field='slug', instance=None):
    """
    توليد slug فريد للنموذج
    
    المعلمات:
    model (Model): نموذج جانغو
    title (str): العنوان لإنشاء slug منه
    slug_field (str): اسم حقل slug
    instance (instance): نسخة النموذج الحالية (للتحديث)
    
    تُرجع: slug فريد
    """
    from django.utils.text import slugify
    
    # إنشاء slug أساسي
    slug = slugify(title)
    
    # التحقق من أن slug فريد
    unique_slug = slug
    counter = 1
    
    # إنشاء استعلام للتحقق من الفرادة
    query = {}
    
    # استثناء النسخة الحالية من الاستعلام في حالة التحديث
    if instance and instance.pk:
        query['pk__ne'] = instance.pk
    
    while model.objects.filter(**{slug_field: unique_slug}).exists():
        unique_slug = f"{slug}-{counter}"
        counter += 1
    
    return unique_slug 