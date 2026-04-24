from django import template
from django.template.defaultfilters import floatformat
from django.utils.safestring import mark_safe
from django.utils import timezone
from decimal import Decimal, InvalidOperation
import pytz

register = template.Library()


@register.filter
def translate_formula(value):
    """
    ترجمة المتغيرات في المعادلات من الإنجليزية للعربية
    وتحويل الأرقام العشرية إلى نسب مئوية
    """
    if not value:
        return value
    
    import re
    
    result = str(value)
    
    # ترجمة المتغيرات
    translations = {
        'basic': 'الأساسي',
        'gross': 'الإجمالي',
        'net': 'الصافي',
    }
    
    for eng, ar in translations.items():
        result = result.replace(eng, ar)
    
    # تحويل الأرقام العشرية إلى نسب مئوية
    # البحث عن أرقام عشرية (مثل 0.25, 0.5, 0.05)
    def convert_to_percentage(match):
        number = float(match.group(0))
        # إذا كان الرقم بين 0 و 1، حوله لنسبة مئوية
        if 0 < number < 1:
            percentage = number * 100
            # إزالة الأصفار الزائدة
            if percentage == int(percentage):
                return f"{int(percentage)}%"
            else:
                return f"{percentage:g}%"
        return match.group(0)
    
    # البحث عن الأرقام العشرية في الصيغة
    result = re.sub(r'\b0\.\d+\b', convert_to_percentage, result)
    
    return result


@register.filter
def sub(value, arg):
    """
    طرح arg من value
    """
    try:
        return value - arg
    except (ValueError, TypeError):
        try:
            return float(value) - float(arg)
        except (ValueError, TypeError):
            return 0


@register.filter
def multiply(value, arg):
    """
    ضرب value في arg
    """
    try:
        # التأكد من أن القيم رقمية
        if isinstance(value, str) and not value.replace('.', '').replace('-', '').isdigit():
            return value
        if isinstance(arg, str) and not arg.replace('.', '').replace('-', '').isdigit():
            return value
        
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return value


@register.filter
def divide(value, arg):
    """
    قسمة value على arg
    """
    try:
        if arg == 0:
            return 0
        return value / arg
    except (ValueError, TypeError):
        try:
            if float(arg) == 0:
                return 0
            return float(value) / float(arg)
        except (ValueError, TypeError):
            return 0


@register.filter
def percentage(value, arg):
    """
    حساب النسبة المئوية: (value / arg) * 100
    """
    try:
        if arg == 0:
            return "0.00"
        return floatformat((value / arg) * 100, 2)
    except (ValueError, TypeError):
        try:
            if float(arg) == 0:
                return "0.00"
            return floatformat((float(value) / float(arg)) * 100, 2)
        except (ValueError, TypeError):
            return "0.00"


# فلاتر إضافية للتوافق مع pricing_filters
@register.filter
def currency(value):
    """تنسيق العملة"""
    if value is None or value == '':
        return "0.00"
    try:
        # تحويل آمن لـ Decimal
        if isinstance(value, Decimal):
            return f"{value:,.2f}"
        elif isinstance(value, (int, float)):
            value = Decimal(str(value))
            return f"{value:,.2f}"
        else:
            # محاولة تحويل النص
            value_str = str(value).strip()
            if not value_str or value_str == 'None':
                return "0.00"
            value = Decimal(value_str)
            return f"{value:,.2f}"
    except (ValueError, TypeError, InvalidOperation):
        return "0.00"


@register.filter
def status_badge(status):
    """عرض حالة كـ badge"""
    if not status:
        return ""
    
    status_classes = {
        'active': 'bg-success',
        'inactive': 'bg-secondary',
        'pending': 'bg-warning',
        'completed': 'bg-primary',
        'cancelled': 'bg-danger',
        'draft': 'bg-info',
    }
    
    status_text = {
        'active': 'نشط',
        'inactive': 'غير نشط',
        'pending': 'قيد الانتظار',
        'completed': 'مكتمل',
        'cancelled': 'ملغي',
        'draft': 'مسودة',
    }
    
    css_class = status_classes.get(status, 'bg-secondary')
    text = status_text.get(status, status)
    
    return mark_safe(f'<span class="badge {css_class}">{text}</span>')


@register.filter
def paper_size_display(paper_size):
    """عرض مقاس الورق بشكل منسق"""
    if not paper_size:
        return "-"
    
    if hasattr(paper_size, 'width') and hasattr(paper_size, 'height'):
        return f"{paper_size.name} ({paper_size.width}×{paper_size.height})"
    
    return str(paper_size)


@register.filter
def gsm_display(gsm):
    """عرض وزن الورق بالجرام"""
    if not gsm:
        return "-"
    return f"{gsm} جم"


@register.filter
def yesno_arabic(value):
    """تحويل True/False إلى نعم/لا"""
    if value is True:
        return "نعم"
    elif value is False:
        return "لا"
    else:
        return "-"


@register.filter
def format_phone(phone):
    """تنسيق رقم الهاتف"""
    if not phone:
        return ""
    
    # إزالة المسافات والرموز
    phone = str(phone).replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    
    # تنسيق الرقم المصري
    if phone.startswith("20"):
        phone = phone[2:]
    elif phone.startswith("+20"):
        phone = phone[3:]
    
    if len(phone) == 11 and phone.startswith("01"):
        return f"{phone[:4]} {phone[4:7]} {phone[7:]}"
    elif len(phone) == 10:
        return f"01{phone[2:5]} {phone[5:8]} {phone[8:]}"
    
    return phone


@register.simple_tag
def calculate_total_cost(*args):
    """حساب التكلفة الإجمالية"""
    total = 0
    for arg in args:
        try:
            total += float(arg or 0)
        except (ValueError, TypeError):
            continue
    return total


@register.filter
def remove_trailing_zeros(value):
    """
    إزالة الأصفار الزائدة من الأرقام العشرية مع إضافة فواصل الآلاف
    مثال: 7.00 -> 7 | 7.50 -> 7.5 | 10000 -> 10,000 | 10000.50 -> 10,000.5
    """
    if value is None:
        return ""

    try:
        # تحويل القيمة إلى Decimal
        if isinstance(value, str):
            value = value.replace(',', '')  # إزالة الفواصل الموجودة
        
        decimal_value = Decimal(str(value))
        
        # استخدام normalize لإزالة الأصفار الزائدة
        normalized = decimal_value.normalize()
        
        # فصل الجزء الصحيح والعشري
        str_value = str(normalized)
        if "E" in str_value.upper():
            str_value = f"{float(normalized):g}"
        
        # فصل الجزء الصحيح والعشري
        if '.' in str_value:
            integer_part, decimal_part = str_value.split('.')
            # إضافة فواصل الآلاف للجزء الصحيح
            integer_part = f"{int(integer_part):,}"
            result = f"{integer_part}.{decimal_part}"
        else:
            # رقم صحيح - إضافة فواصل الآلاف فقط
            result = f"{int(str_value):,}"
        
        return result

    except (ValueError, TypeError, Exception):
        return str(value)


@register.filter
def format_dimension(value):
    """
    تنسيق الأبعاد بإزالة الأصفار الزائدة
    """
    return remove_trailing_zeros(value)


@register.filter
def get_attr(obj, attr_name):
    """
    الحصول على خاصية من كائن أو dictionary
    يدعم nested attributes مثل: product.name, product.category.name
    """
    if obj is None:
        return ''
    
    # التعامل مع dictionaries
    if isinstance(obj, dict):
        return obj.get(attr_name, '')
    
    # التعامل مع nested attributes (product.name)
    if '.' in attr_name:
        parts = attr_name.split('.')
        result = obj
        for part in parts:
            if result is None:
                return ''
            
            if isinstance(result, dict):
                result = result.get(part, '')
            else:
                # محاولة الحصول على الخاصية
                attr_value = getattr(result, part, '')
                # إذا كانت دالة، استدعيها
                if callable(attr_value):
                    try:
                        result = attr_value()
                    except:
                        result = attr_value
                else:
                    result = attr_value
        
        return result
    else:
        # خاصية بسيطة
        attr_value = getattr(obj, attr_name, '')
        # إذا كانت دالة، استدعيها
        if callable(attr_value):
            try:
                return attr_value()
            except:
                return attr_value
        return attr_value


@register.filter
def call(obj, method_name):
    """
    استدعاء دالة على كائن
    """
    if hasattr(obj, method_name):
        method = getattr(obj, method_name)
        if callable(method):
            return method()
    return ''


@register.filter
def split(value, delimiter):
    """
    تقسيم نص بناءً على فاصل
    """
    if isinstance(value, str):
        return value.split(delimiter)
    return []


@register.filter
def currency_format(value, decimal_places=2):
    """
    تنسيق الأرقام كعملة مع إخفاء العلامة العشرية للأرقام الصحيحة وإضافة علامة الألف
    مثال: 1000 -> 1,000 | 1000.5 -> 1,000.5 | 1000.00 -> 1,000
    يستخدم دائماً "." للعلامة العشرية و "," لفاصلة الآلاف
    """
    if value is None or value == "":
        return "0"
    
    try:
        # تحويل القيمة إلى Decimal للحصول على دقة أفضل
        if isinstance(value, str):
            # إزالة الفواصل الموجودة مسبقاً
            value = value.replace(',', '')
        
        decimal_value = Decimal(str(value))
        
        # التحقق من أن الرقم صحيح (لا يحتوي على كسور)
        if decimal_value == decimal_value.to_integral_value():
            # رقم صحيح - عرض بدون علامة عشرية مع فواصل الآلاف
            int_value = int(decimal_value)
            formatted = format_integer_with_commas(int_value)
        else:
            # رقم عشري - عرض مع العلامة العشرية
            if decimal_places == 0:
                # إذا طُلب عدم عرض أي منازل عشرية
                int_value = int(decimal_value)
                formatted = format_integer_with_commas(int_value)
            else:
                # عرض المنازل العشرية المطلوبة
                float_value = float(decimal_value)
                formatted_float = f"{float_value:.{decimal_places}f}"
                
                # فصل الجزء الصحيح والعشري
                if '.' in formatted_float:
                    integer_part, decimal_part = formatted_float.split('.')
                    int_val = int(integer_part)
                    
                    # تنسيق الجزء الصحيح
                    integer_formatted = format_integer_with_commas(int_val)
                    
                    # إزالة الأصفار الزائدة من الجزء العشري
                    decimal_part = decimal_part.rstrip('0')
                    if decimal_part:
                        formatted = f"{integer_formatted}.{decimal_part}"
                    else:
                        formatted = integer_formatted
                else:
                    formatted = formatted_float
        
        return formatted
        
    except (ValueError, TypeError, Exception):
        return str(value)


def format_integer_with_commas(int_value):
    """
    تنسيق الأرقام الصحيحة مع فواصل الآلاف
    يضمن استخدام "," للآلاف دائماً
    """
    if abs(int_value) < 1000:
        return str(int_value)
    
    # تنسيق يدوي للأرقام الكبيرة لضمان استخدام "," للآلاف
    str_value = str(abs(int_value))
    formatted_parts = []
    for i, digit in enumerate(reversed(str_value)):
        if i > 0 and i % 3 == 0:
            formatted_parts.append(',')
        formatted_parts.append(digit)
    formatted = ''.join(reversed(formatted_parts))
    
    if int_value < 0:
        formatted = '-' + formatted
    
    return formatted


@register.filter  
def smart_float(value, decimal_places=2):
    """
    فلتر ذكي للأرقام - يخفي العلامة العشرية للأرقام الصحيحة ويضيف فواصل الآلاف
    بديل محسن لـ floatformat
    """
    return currency_format(value, decimal_places)


@register.filter
def format_age(age_in_months):
    """
    تحويل العمر من شهور إلى سنين وشهور
    """
    from utils.helpers import format_age_in_years_months
    return format_age_in_years_months(age_in_months)


@register.filter
def system_time(value):
    """
    تحويل التاريخ والوقت إلى المنطقة الزمنية المحددة في إعدادات النظام
    """
    if not value:
        return value
    
    # إذا كان التاريخ naive، اجعله aware بـ UTC أولاً
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.utc)
    
    # الحصول على المنطقة الزمنية من الإعدادات
    try:
        from core.models import SystemSetting
        timezone_name = SystemSetting.get_timezone()
    except:
        # fallback إذا لم تكن الإعدادات متاحة
        timezone_name = 'Africa/Cairo'
    
    # تحويل إلى المنطقة الزمنية المحددة
    system_tz = pytz.timezone(timezone_name)
    return value.astimezone(system_tz)


@register.filter
def system_date(value, format_string="d/m/Y"):
    """
    عرض التاريخ بالمنطقة الزمنية المحددة في إعدادات النظام مع تنسيق مخصص
    """
    if not value:
        return ""
    
    # تحويل إلى المنطقة الزمنية المحددة
    system_time_value = system_time(value)
    if not system_time_value:
        return ""
    
    # تطبيق التنسيق
    from django.template.defaultfilters import date
    return date(system_time_value, format_string)


@register.filter
def system_datetime(value, format_string="d/m/Y H:i"):
    """
    عرض التاريخ والوقت بالمنطقة الزمنية المحددة في إعدادات النظام مع تنسيق مخصص
    """
    if not value:
        return ""
    
    # تحويل إلى المنطقة الزمنية المحددة
    system_time_value = system_time(value)
    if not system_time_value:
        return ""
    
    # تطبيق التنسيق
    from django.template.defaultfilters import date
    return date(system_time_value, format_string)


@register.filter
def raw_number(value):
    """
    إرجاع القيمة الرقمية الخام بدون تنسيق للاستخدام في حقول HTML
    يحول القيمة إلى رقم عشري بدون فواصل أو تنسيق
    يدعم الأرقام التي تستخدم الفاصلة كعلامة عشرية (مثل 810,00)
    مثال: 1,000.50 -> 1000.5 | 1,000 -> 1000 | 810,00 -> 810
    """
    if value is None or value == "":
        return "0"
    
    try:
        # تحويل إلى string أولاً
        str_value = str(value).strip()
        
        # التعامل مع الأرقام التي تستخدم الفاصلة كعلامة عشرية
        # مثل: 810,00 أو 5400,00
        if ',' in str_value and '.' not in str_value:
            # التحقق من أن الفاصلة في النهاية (علامة عشرية)
            parts = str_value.split(',')
            if len(parts) == 2 and len(parts[1]) <= 2 and parts[1].isdigit():
                # هذه فاصلة عشرية، ليس فاصلة آلاف
                str_value = parts[0] + '.' + parts[1]
            else:
                # فاصلة آلاف، أزلها
                str_value = str_value.replace(',', '')
        elif ',' in str_value and '.' in str_value:
            # يحتوي على كلاهما - الفاصلة للآلاف والنقطة للعشرية
            str_value = str_value.replace(',', '')
        
        # تحويل إلى Decimal
        decimal_value = Decimal(str_value)
        
        # تحويل إلى string وإزالة الأصفار الزائدة
        normalized = decimal_value.normalize()
        result = str(normalized)
        
        # التعامل مع العلامة العلمية
        if "E" in result.upper():
            result = f"{float(normalized):g}"
        
        return result
        
    except (ValueError, TypeError, InvalidOperation):
        return "0"


@register.filter
def product_type_label(product, context='default'):
    """
    عرض تسمية ديناميكية حسب نوع المنتج/الخدمة
    
    Args:
        product: كائن المنتج
        context: السياق (default, plural, with_article)
    
    Returns:
        str: التسمية المناسبة
    """
    if not product:
        return "عنصر"
    
    is_service = getattr(product, 'is_service', False)
    
    if context == 'plural':
        return "خدمات" if is_service else "منتجات"
    elif context == 'with_article':
        return "الخدمة" if is_service else "المنتج"
    else:  # default
        return "خدمة" if is_service else "منتج"


@register.simple_tag
def product_icon(product):
    """
    عرض أيقونة حسب نوع المنتج/الخدمة
    
    Args:
        product: كائن المنتج
    
    Returns:
        str: class الأيقونة
    """
    if not product:
        return "fa-box"
    
    is_service = getattr(product, 'is_service', False)
    is_bundle = getattr(product, 'is_bundle', False)
    
    if is_service:
        return "fa-concierge-bell"
    elif is_bundle:
        return "fa-boxes"
    else:
        return "fa-box"


@register.simple_tag
def product_badge(product):
    """
    عرض badge HTML حسب نوع المنتج/الخدمة
    
    Args:
        product: كائن المنتج
    
    Returns:
        str: HTML للـ badge
    """
    if not product:
        return ""
    
    is_service = getattr(product, 'is_service', False)
    is_bundle = getattr(product, 'is_bundle', False)
    
    if is_service:
        return mark_safe('<span class="badge bg-success"><i class="fas fa-concierge-bell me-1"></i>خدمة</span>')
    elif is_bundle:
        return mark_safe('<span class="badge bg-info"><i class="fas fa-boxes me-1"></i>منتج مجمع</span>')
    else:
        return mark_safe('<span class="badge bg-secondary"><i class="fas fa-box me-1"></i>منتج</span>')
