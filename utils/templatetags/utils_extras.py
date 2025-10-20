from django import template
from django.template.defaultfilters import floatformat
from django.utils.safestring import mark_safe
from decimal import Decimal

register = template.Library()


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
        return value * arg
    except (ValueError, TypeError):
        try:
            return float(value) * float(arg)
        except (ValueError, TypeError):
            return 0


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
            return 0
        return floatformat((value / arg) * 100, 2)
    except (ValueError, TypeError):
        try:
            if float(arg) == 0:
                return 0
            return floatformat((float(value) / float(arg)) * 100, 2)
        except (ValueError, TypeError):
            return 0


# فلاتر إضافية للتوافق مع pricing_filters
@register.filter
def currency(value):
    """تنسيق العملة"""
    if value is None:
        return "0.00"
    try:
        value = Decimal(str(value))
        return f"{value:,.2f}"
    except (ValueError, TypeError):
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
    إزالة الأصفار الزائدة من الأرقام العشرية
    مثال: 7.00 -> 7, 7.50 -> 7.5, 7.25 -> 7.25
    """
    if value is None:
        return ""

    try:
        # التعامل مع Decimal بشكل مباشر
        if isinstance(value, Decimal):
            # استخدام normalize لإزالة الأصفار الزائدة
            normalized = value.normalize()
            # تحويل إلى string وإزالة الأصفار إذا لزم الأمر
            result = str(normalized)
            # التأكد من عدم وجود تدوين علمي
            if "E" in result.upper():
                # تحويل إلى float ثم إلى string
                result = f"{float(normalized):g}"
            return result

        # التعامل مع الأنواع الأخرى
        if isinstance(value, (int, float, str)):
            # تحويل إلى Decimal أولاً للحصول على دقة أفضل
            decimal_value = Decimal(str(value))
            normalized = decimal_value.normalize()
            result = str(normalized)
            # التأكد من عدم وجود تدوين علمي
            if "E" in result.upper():
                result = f"{float(normalized):g}"
            return result

        return str(value)
    except (ValueError, TypeError, Exception):
        return str(value)


@register.filter
def format_dimension(value):
    """
    تنسيق الأبعاد بإزالة الأصفار الزائدة
    """
    return remove_trailing_zeros(value)
