from django import template
from decimal import Decimal, ROUND_HALF_UP
import json
from django.utils.safestring import mark_safe
from django.template.defaultfilters import floatformat
import locale
from django.contrib.auth.models import Permission
from django.utils import timezone
from datetime import datetime

register = template.Library()


@register.filter
def custom_number_format(value, decimals=2):
    """
    تنسيق الأرقام بالشكل المطلوب:
    - علامة عشرية واحدة فقط إذا كانت هناك كسور
    - بدون علامة عشرية إذا كان العدد صحيح
    - فاصلة لكل ألف
    """
    if value is None:
        return "0"

    try:
        value = float(value)
        
        # إذا كانت القيمة عدد صحيح أو decimals=0، نعرضها بدون علامة عشرية
        if value == int(value) or decimals == 0:
            return "{:,}".format(int(value))
        
        # إذا كانت هناك كسور، نعرضها مع المنازل العشرية المطلوبة
        return "{:,.{prec}f}".format(value, prec=decimals)
    except (ValueError, TypeError):
        return value


@register.filter
def custom_load_json(json_string):
    """
    تحويل سلسلة JSON إلى كائن بايثون
    استخدام: {{ json_string|custom_load_json }}
    """
    try:
        if isinstance(json_string, str):
            return json.loads(json_string)
        return json_string
    except json.JSONDecodeError:
        return []


@register.filter
def format_phone(value):
    """
    تنسيق رقم الهاتف بطريقة صحيحة دون معاملته كرقم عُملة
    مع ضبط الاتجاه من اليسار إلى اليمين
    """
    if value is None or value == "":
        return "-"

    # إزالة أي علامات تنسيق أضيفت بالخطأ
    phone = str(value).replace(",", "").replace(".", "").strip()

    # تنسيق الرقم حسب الطول
    if len(phone) == 11 and phone.startswith("01"):  # أرقام مصرية
        formatted = f"{phone[:3]} {phone[3:7]} {phone[7:]}"
    elif len(phone) > 10:  # أرقام دولية طويلة
        if phone.startswith("+"):
            country_code = phone[:3]  # رمز الدولة مع +
            rest = phone[3:]
            formatted = f"{country_code} {rest}"
        else:
            formatted = phone
    else:
        formatted = phone

    # إضافة وسم direction لضبط اتجاه النص من اليسار إلى اليمين وجعله آمن
    return mark_safe(
        f'<span dir="ltr" style="display:inline-block; text-align:left;">{formatted}</span>'
    )


# الفلاتر المضافة من تطبيق product


@register.filter
def divide(value, arg):
    """قسمة القيمة الأولى على القيمة الثانية"""
    try:
        return float(value) / float(arg)
    except (ValueError, ZeroDivisionError):
        return 0


@register.filter
def div(value, arg):
    """مرادف لفلتر divide للتوافق"""
    return divide(value, arg)


@register.filter
def multiply(value, arg):
    """ضرب القيمة الأولى في القيمة الثانية"""
    try:
        return float(value) * float(arg)
    except ValueError:
        return 0


@register.filter
def mul(value, arg):
    """مرادف لفلتر multiply للتوافق"""
    return multiply(value, arg)


@register.filter
def subtract(value, arg):
    """طرح القيمة الثانية من القيمة الأولى"""
    try:
        return float(value) - float(arg)
    except ValueError:
        return 0


@register.filter
def add_float(value, arg):
    """جمع القيمة الأولى مع القيمة الثانية"""
    try:
        return float(value) + float(arg)
    except ValueError:
        return 0


@register.filter
def percentage(value, arg):
    """حساب النسبة المئوية للقيمة الأولى من القيمة الثانية"""
    try:
        return (float(value) / float(arg)) * 100
    except (ValueError, ZeroDivisionError):
        return 0


@register.filter
def get_attr(obj, attr):
    """
    الحصول على قيمة سمة من كائن أو dictionary باستخدام اسم السمة
    يدعم أيضًا معالجة الكائنات المتداخلة باستخدام النقاط في سلسلة السمة
    مثال: {{ object|get_attr:"user.name" }}
    """
    if obj is None:
        return ""

    # التعامل مع dictionaries
    if isinstance(obj, dict):
        return obj.get(attr, "")

    if "." in attr:
        # تقسيم السمة بالنقط للوصول إلى السمات المتداخلة
        parts = attr.split(".")
        result = obj
        for part in parts:
            if result is None:
                return ""

            # التعامل مع dictionaries في المستويات المتداخلة
            if isinstance(result, dict):
                result = result.get(part, "")
            else:
                # محاولة تنفيذ تابع بدون وسيطات إذا كان
                if callable(getattr(result, part, None)):
                    result = getattr(result, part)()
                else:
                    result = getattr(result, part, "")

        return result
    else:
        # التعامل مع dictionaries
        if isinstance(obj, dict):
            return obj.get(attr, "")

        # محاولة تنفيذ تابع بدون وسيطات إذا كان
        attr_value = getattr(obj, attr, "")
        if callable(attr_value):
            try:
                # تجنب استدعاء RelatedManager والدوال التي تحتاج معاملات
                attr_type_str = str(type(attr_value))
                if (
                    "RelatedManager" in attr_type_str
                    or "ManyRelatedManager" in attr_type_str
                ):
                    return attr_value

                # محاولة استدعاء الدالة
                return attr_value()
            except (TypeError, AttributeError):
                # إذا فشل الاستدعاء، أرجع الكائن نفسه
                return attr_value
        return attr_value


@register.filter
def call(obj, method_name):
    """
    استدعاء طريقة (تابع) من كائن باسم التابع
    مثال: {{ object|call:"get_absolute_url" }}
    """
    if obj is None:
        return ""

    method = getattr(obj, method_name, None)
    if callable(method):
        return method()
    return ""


@register.filter
def replace_id(url, obj_id):
    """
    استبدال '{id}' أو '{pk}' بقيمة محددة في URL
    مثال: {{ "product/{id}/edit"|replace_id:product.id }}
    """
    if url is None or obj_id is None:
        return ""

    return str(url).replace("{id}", str(obj_id)).replace("{pk}", str(obj_id))


@register.filter
def split(value, sep):
    """
    تقسيم سلسلة نصية بناءً على فاصل معين وإرجاع قائمة
    مثال: {{ "10,25,50,100"|split:"," }}
    """
    if value is None:
        return []
    return str(value).split(sep)


@register.filter
def to_int(value, default=0):
    """
    تحويل قيمة إلى عدد صحيح
    مثال: {{ "15"|to_int }}
    """
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


@register.filter
def to_float(value, default=0.0):
    """
    تحويل قيمة إلى عدد عشري
    مثال: {{ "15.5"|to_float }}
    """
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


@register.filter
def format_table_cell(value, format_type):
    """
    تنسيق خلية في جدول حسب نوع التنسيق
    يستخدم: {{ value|format_table_cell:"currency" }}
    """
    if value is None:
        return "-"

    if format_type == "currency":
        from core.utils import get_default_currency
        currency_symbol = get_default_currency()
        return f"{custom_number_format(value)} {currency_symbol}"
    elif format_type == "date":
        return value.strftime("%Y-%m-%d") if value else "-"
    elif format_type == "datetime":
        return value.strftime("%Y-%m-%d %H:%M") if value else "-"
    elif format_type == "boolean":
        return "نعم" if value else "لا"
    elif format_type == "percentage":
        return f"{custom_number_format(value, 1)}%"
    else:
        return value


@register.filter
def safe_datetime_format(value, format_str):
    """
    تنسيق آمن للتاريخ والوقت - يتعامل مع date و datetime
    """
    if value is None:
        return ""

    try:
        # إذا كان datetime، استخدم التنسيق المطلوب
        if hasattr(value, "hour"):
            return value.strftime(format_str)
        # إذا كان date فقط، لا تستخدم تنسيقات الوقت
        elif (
            "h" in format_str.lower() or "i" in format_str or "a" in format_str.lower()
        ):
            return ""
        else:
            return value.strftime(format_str)
    except (AttributeError, ValueError):
        return ""


# Template tags للصلاحيات والقائمة الجانبية
@register.simple_tag(takes_context=True)
def has_sidebar_permission(context, permission_name):
    """التحقق من صلاحية المستخدم لعرض عنصر في القائمة الجانبية"""
    user = context["request"].user

    if not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    return user.has_perm(permission_name)


@register.simple_tag(takes_context=True)
def has_module_access(context, module_name):
    """التحقق من صلاحية الوصول لوحدة كاملة"""
    user = context["request"].user

    if not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    # قائمة الصلاحيات المطلوبة لكل وحدة
    module_permissions = {
        "financial": ["financial.view_account", "financial.view_transaction"],
        "advanced_accounting": [
            "financial.view_chartofaccounts",
            "financial.view_journalentry",
        ],
        "enhanced_financial": ["financial.view_account", "financial.view_transaction"],
        "advanced_reports": ["financial.view_account", "financial.view_transaction"],
        "sales": ["sale.view_sale"],
        "purchases": ["purchase.view_purchase"],
        "clients": ["client.view_customer"],
        "suppliers": ["supplier.view_supplier"],
        "inventory": ["product.view_product"],
        "users": ["auth.view_user"],
        "settings": True,  # الإعدادات متاحة للجميع
    }

    permissions = module_permissions.get(module_name, [])
    if permissions is True:
        return True
    if not permissions:
        return False

    # يكفي وجود صلاحية واحدة للوصول للوحدة
    return any(user.has_perm(perm) for perm in permissions)


@register.filter
def currency(value, decimals=2):
    """
    تنسيق الرقم كعملة باستخدام العملة الافتراضية من إعدادات الشركة
    استخدام: {{ amount|currency }} أو {{ amount|currency:0 }}
    """
    from core.utils import format_currency
    return format_currency(value, decimal_places=decimals)


@register.simple_tag
def currency_symbol():
    """
    الحصول على رمز العملة الافتراضية
    استخدام: {% currency_symbol %}
    """
    from core.utils import get_default_currency
    return get_default_currency()


@register.filter
def arabic_timesince(value):
    """
    تحويل الوقت إلى صيغة عربية (منذ كم)
    """
    if not value:
        return ""
    
    now = timezone.now()
    if timezone.is_aware(value):
        diff = now - value
    else:
        diff = datetime.now() - value
    
    seconds = diff.total_seconds()
    
    if seconds < 60:
        return "الآن"
    elif seconds < 3600:  # أقل من ساعة
        minutes = int(seconds / 60)
        if minutes == 1:
            return "منذ دقيقة"
        elif minutes == 2:
            return "منذ دقيقتين"
        elif minutes <= 10:
            return f"منذ {minutes} دقائق"
        else:
            return f"منذ {minutes} دقيقة"
    elif seconds < 86400:  # أقل من يوم
        hours = int(seconds / 3600)
        if hours == 1:
            return "منذ ساعة"
        elif hours == 2:
            return "منذ ساعتين"
        elif hours <= 10:
            return f"منذ {hours} ساعات"
        else:
            return f"منذ {hours} ساعة"
    elif seconds < 604800:  # أقل من أسبوع
        days = int(seconds / 86400)
        if days == 1:
            return "منذ يوم"
        elif days == 2:
            return "منذ يومين"
        elif days <= 10:
            return f"منذ {days} أيام"
        else:
            return f"منذ {days} يوم"
    elif seconds < 2592000:  # أقل من شهر
        weeks = int(seconds / 604800)
        if weeks == 1:
            return "منذ أسبوع"
        elif weeks == 2:
            return "منذ أسبوعين"
        else:
            return f"منذ {weeks} أسابيع"
    elif seconds < 31536000:  # أقل من سنة
        months = int(seconds / 2592000)
        if months == 1:
            return "منذ شهر"
        elif months == 2:
            return "منذ شهرين"
        elif months <= 10:
            return f"منذ {months} أشهر"
        else:
            return f"منذ {months} شهر"
    else:  # أكثر من سنة
        years = int(seconds / 31536000)
        if years == 1:
            return "منذ سنة"
        elif years == 2:
            return "منذ سنتين"
        elif years <= 10:
            return f"منذ {years} سنوات"
        else:
            return f"منذ {years} سنة"
