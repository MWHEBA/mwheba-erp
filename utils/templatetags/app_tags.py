from django import template
from django.urls import reverse
import re
from decimal import Decimal, InvalidOperation

register = template.Library()


@register.filter
def get_attr(obj, attr):
    """
    الحصول على قيمة خاصية من كائن
    سواء كانت خاصية عادية أو خاصية متداخلة مفصولة بنقطة
    مثل: user.profile.avatar
    """
    if not obj:
        return None

    # دعم الخصائص المتداخلة (مثل user.profile.name)
    attrs = attr.split(".")
    value = obj

    for a in attrs:
        # دعم الـ attributes والـ methods والـ dict keys
        if hasattr(value, a):
            value = getattr(value, a)
            if callable(value):
                value = value()
        elif isinstance(value, dict) and a in value:
            value = value[a]
        else:
            return None

    return value


@register.filter
def replace_id(url, id_value):
    """
    استبدال '{id}' في URL بقيمة معينة
    مثال: "/products/{id}/edit/" سيصبح "/products/123/edit/"
    """
    if not url or not id_value:
        return url

    return url.replace("{id}", str(id_value))


@register.filter
def currency(value, currency_symbol=None):
    """
    تنسيق قيمة كعملة
    """
    if value is None:
        return None

    try:
        from core.models import SystemSetting
        if currency_symbol is None:
            currency_symbol = SystemSetting.get_currency_symbol()
        
        value = Decimal(value)
        # إذا كان الرقم صحيح (بدون كسور)، اعرضه بدون خانات عشرية
        if value == value.to_integral_value():
            formatted = "{:,.0f}".format(value)
        else:
            formatted = "{:,.2f}".format(value)
        return f"{formatted} {currency_symbol}"
    except (ValueError, TypeError, InvalidOperation):
        return value


@register.filter
def subtract(value, arg):
    """
    طرح قيمة من قيمة أخرى
    """
    try:
        return value - arg
    except (TypeError, ValueError):
        return value


@register.filter
def add(value, arg):
    """
    إضافة قيمة لقيمة أخرى
    """
    try:
        return value + arg
    except (TypeError, ValueError):
        return value


@register.filter
def multiply(value, arg):
    """
    ضرب قيمة في قيمة أخرى
    """
    try:
        # التأكد من أن القيم رقمية
        if isinstance(value, str) and not value.replace('.', '').replace('-', '').isdigit():
            return value
        if isinstance(arg, str) and not arg.replace('.', '').replace('-', '').isdigit():
            return value
        
        return float(value) * float(arg)
    except (TypeError, ValueError):
        return value


@register.filter
def divide(value, arg):
    """
    قسمة قيمة على قيمة أخرى
    """
    try:
        if arg == 0:
            return 0
        return value / arg
    except (TypeError, ValueError, ZeroDivisionError):
        return 0


@register.filter
def percentage(value, total):
    """
    حساب نسبة مئوية من قيمة بالنسبة للمجموع
    """
    try:
        if total == 0:
            return 0
        return (value / total) * 100
    except (TypeError, ValueError, ZeroDivisionError):
        return 0


@register.simple_tag
def url_replace(request, *args, **kwargs):
    """
    استبدال أو إضافة معلمات URL مع الحفاظ على المعلمات الحالية والـ Multi-select inputs.
    يدعم النمطين:
    1. أزواج البارامترات المباشرة: {% url_replace request 'page' 2 'per_page' 50 %}
    2. الـ Keyword arguments: {% url_replace request page=2 per_page=50 %}
    3. البارامتر الفردي: {% url_replace request 'page' 2 %}
    """
    if not request:
        return ""
    
    dict_ = request.GET.copy()
    
    # تنظيف التوكنات غير المطلوبة
    for key_to_remove in ['csrfmiddlewaretoken', '_']:
        if key_to_remove in dict_:
            dict_.pop(key_to_remove, None)

    param_args = list(args)
    # معالجة الحالة التي يُمرر فيها request كأول positional arg
    if param_args and hasattr(param_args[0], 'GET'):
        param_args.pop(0)

    # معالجة الـ positional args كأزواج (key, val)
    i = 0
    while i < len(param_args):
        k = str(param_args[i])
        v = param_args[i+1] if (i + 1) < len(param_args) else None
        if v is None or v == "":
            dict_.pop(k, None)
        else:
            dict_[k] = str(v)
        i += 2

    # معالجة الـ kwargs (مثال: page=2 per_page=50)
    for key, val in kwargs.items():
        if val is None or val == "":
            dict_.pop(key, None)
        else:
            dict_[key] = str(val)

    return dict_.urlencode()


@register.simple_tag
def active_url(request, urls):
    """
    تعيين فئة active للروابط النشطة
    """
    if not request:
        return ""

    for url in urls.split():
        if url == "/":
            if request.path == "/":
                return "active"
        elif request.path.startswith(url):
            return "active"
    return ""


@register.filter
def custom_number_format(value, decimals=2):
    """
    تنسيق الأرقام بشكل جميل مع فواصل الآلاف
    مثال: 1234.56 تصبح 1,234.56
    """
    if value is None:
        return "-"

    try:
        # تحويل القيمة إلى Decimal للتعامل مع الأرقام العشرية بدقة
        value = float(value)
        # تنسيق الرقم مع إضافة فواصل الآلاف
        return "{:,.{prec}f}".format(value, prec=decimals)
    except (ValueError, TypeError):
        return value
