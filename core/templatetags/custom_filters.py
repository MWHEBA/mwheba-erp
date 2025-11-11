from django import template
from django.utils.safestring import mark_safe
from django.utils.html import format_html
from django.urls import reverse
from decimal import Decimal
import re
import json
from django.template.defaultfilters import floatformat
import locale
from django.contrib.auth.models import Permission
from django.utils import timezone
from datetime import datetime
import datetime as dt

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
def format_minutes(minutes):
    """
    تنسيق الدقائق - إذا كانت أكثر من 90 دقيقة، تحول لساعات ودقائق
    استخدام: {{ late_minutes|format_minutes }}
    """
    if not minutes or minutes == 0:
        return ""
    
    try:
        minutes = int(minutes)
        
        # إذا أقل من أو يساوي 90 دقيقة، اعرض بالدقائق فقط
        if minutes <= 90:
            return f"{minutes} د"
        
        # إذا أكثر من 90 دقيقة، حول لساعات ودقائق
        hours = minutes // 60
        remaining_minutes = minutes % 60
        
        if remaining_minutes == 0:
            return f"{hours}س"
        else:
            return f"{hours}س {remaining_minutes}د"
    except (ValueError, TypeError):
        return str(minutes)


@register.filter
def format_work_hours(hours):
    """
    تنسيق ساعات العمل من decimal لساعات ودقائق بشكل احترافي
    استخدام: {{ work_hours|format_work_hours }}
    مثال: 8.5 → 8 ساعات و 30 دقيقة
    """
    if not hours or hours == 0:
        return "-"
    
    try:
        hours_float = float(hours)
        
        # تحويل لدقائق
        total_minutes = int(hours_float * 60)
        
        # إذا أقل من 90 دقيقة، اعرض بالدقائق فقط
        if total_minutes < 90:
            if total_minutes == 1:
                return "دقيقة"
            elif total_minutes == 2:
                return "دقيقتان"
            elif total_minutes <= 10:
                return f"{total_minutes} دقائق"
            else:
                return f"{total_minutes} دقيقة"
        
        # إذا 90 دقيقة أو أكثر، حول لساعات ودقائق
        hours_int = total_minutes // 60
        remaining_minutes = total_minutes % 60
        
        # تنسيق الساعات
        if hours_int == 1:
            hours_text = "ساعة"
        elif hours_int == 2:
            hours_text = "ساعتان"
        elif hours_int <= 10:
            hours_text = f"{hours_int} ساعات"
        else:
            hours_text = f"{hours_int} ساعة"
        
        # إذا لا توجد دقائق متبقية
        if remaining_minutes == 0:
            return hours_text
        
        # تنسيق الدقائق
        if remaining_minutes == 1:
            minutes_text = "دقيقة"
        elif remaining_minutes == 2:
            minutes_text = "دقيقتان"
        elif remaining_minutes <= 10:
            minutes_text = f"{remaining_minutes} دقائق"
        else:
            minutes_text = f"{remaining_minutes} دقيقة"
        
        return f"{hours_text} و {minutes_text}"
    except (ValueError, TypeError):
        return str(hours)


@register.filter
def arabic_day(value):
    """
    تحويل اسم اليوم للعربي
    استخدام: {{ date|arabic_day }}
    """
    if not value:
        return ""
    
    days_map = {
        'Saturday': 'السبت',
        'Sunday': 'الأحد',
        'Monday': 'الاثنين',
        'Tuesday': 'الثلاثاء',
        'Wednesday': 'الأربعاء',
        'Thursday': 'الخميس',
        'Friday': 'الجمعة'
    }
    
    try:
        day_name = value.strftime('%A')
        return days_map.get(day_name, day_name)
    except (AttributeError, ValueError):
        return ""


@register.filter
def arabic_timesince(value):
    """
    تحويل الوقت إلى صيغة عربية (منذ كم) - حساب دقيق بالسنوات والشهور
    """
    if not value:
        return ""
    
    # تحويل date إلى datetime إذا لزم الأمر
    if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
        value = dt.datetime.combine(value, dt.time.min)
    
    # الحصول على التاريخ الحالي
    if timezone.is_aware(value):
        now = timezone.now()
    else:
        now = datetime.now()
        
    # حساب الفرق بالسنوات والشهور والأيام
    years = now.year - value.year
    months = now.month - value.month
    days = now.day - value.day
    
    # تعديل الحساب إذا كان الشهر أو اليوم سالب
    if days < 0:
        months -= 1
        # حساب عدد الأيام في الشهر السابق
        if now.month == 1:
            prev_month_days = 31
        else:
            prev_month = now.month - 1
            prev_month_year = now.year
            if prev_month == 2:
                prev_month_days = 29 if (prev_month_year % 4 == 0 and prev_month_year % 100 != 0) or prev_month_year % 400 == 0 else 28
            elif prev_month in [4, 6, 9, 11]:
                prev_month_days = 30
            else:
                prev_month_days = 31
        days += prev_month_days
    
    if months < 0:
        years -= 1
        months += 12
    
    # تنسيق النتيجة بالعربي
    if years > 0:
        if months > 0:
            # سنوات وشهور
            year_text = "سنة" if years == 1 else "سنتين" if years == 2 else f"{years} سنوات" if years <= 10 else f"{years} سنة"
            month_text = "شهر" if months == 1 else "شهرين" if months == 2 else f"{months} أشهر" if months <= 10 else f"{months} شهر"
            return f"{year_text} و{month_text}"
        else:
            # سنوات فقط
            if years == 1:
                return "سنة واحدة"
            elif years == 2:
                return "سنتين"
            elif years <= 10:
                return f"{years} سنوات"
            else:
                return f"{years} سنة"
    elif months > 0:
        if days > 15:
            # إضافة شهر إذا كان أكثر من نصف شهر
            months += 1
        if months == 1:
            return "شهر واحد"
        elif months == 2:
            return "شهرين"
        elif months <= 10:
            return f"{months} أشهر"
        else:
            return f"{months} شهر"
    elif days > 0:
        if days == 1:
            return "يوم واحد"
        elif days == 2:
            return "يومين"
        elif days <= 10:
            return f"{days} أيام"
        else:
            return f"{days} يوم"
    else:
        return "اليوم"


@register.filter
def arabic_month_year(date_value):
    """
    تحويل التاريخ إلى شهر وسنة بالعربي
    مثال: 2025-01-15 -> يناير 2025
    """
    from utils.helpers import arabic_date_format
    
    if not date_value:
        return ""
    
    try:
        # استخدام الدالة الموجودة في utils.helpers
        formatted = arabic_date_format(date_value, with_time=False)
        # استخراج الشهر والسنة فقط (بدون اليوم)
        parts = formatted.split()
        if len(parts) >= 3:
            return f"{parts[1]} {parts[2]}"  # الشهر والسنة
        return formatted
    except:
        return str(date_value)


@register.inclusion_tag('components/partials/action_button.html')
def render_action_button(button, item, primary_key='id'):
    """
    عرض زر الإجراء مع التحقق من الشروط
    """
    # التحقق من الشرط
    show_button = True
    
    # التحقق من وجود شرط في الزر
    if hasattr(button, 'condition') and button.condition:
        if button.condition == 'not_fully_paid':
            show_button = getattr(item, 'payment_status', None) != 'paid'
        elif button.condition == 'no_posted_payments':
            show_button = not getattr(item, 'has_posted_payments', False)
        elif button.condition == 'status == \'draft\'':
            show_button = getattr(item, 'status', None) == 'draft'
        elif button.condition == 'can_delete':
            show_button = getattr(item, 'can_delete', True)
        elif button.condition == "status != 'approved' and status != 'paid'":
            status = getattr(item, 'status', None)
            show_button = status != 'approved' and status != 'paid'
        elif button.condition == "status == 'approved'":
            show_button = getattr(item, 'status', None) == 'approved'
    elif hasattr(button, 'get') and button.get('condition'):
        # للتعامل مع dictionary buttons
        if button.get('condition') == 'not_fully_paid':
            show_button = getattr(item, 'payment_status', None) != 'paid'
        elif button.get('condition') == 'no_posted_payments':
            show_button = not getattr(item, 'has_posted_payments', False)
        elif button.get('condition') == 'status == \'draft\'':
            show_button = getattr(item, 'status', None) == 'draft'
        elif button.get('condition') == 'can_delete':
            show_button = getattr(item, 'can_delete', True)
        elif button.get('condition') == "status != 'approved' and status != 'paid'":
            status = getattr(item, 'status', None)
            show_button = status != 'approved' and status != 'paid'
        elif button.get('condition') == "status == 'approved'":
            show_button = getattr(item, 'status', None) == 'approved'
    
    # الحصول على المفتاح الأساسي
    if hasattr(item, primary_key):
        item_id = getattr(item, primary_key, '0')
    else:
        item_id = getattr(item, 'id', '0')
    
    return {
        'button': button,
        'item': item,
        'item_id': item_id,
        'show_button': show_button,
    }


@register.filter
def format_date_safe(value, format_type='date'):
    """
    تنسيق التاريخ مع معالجة آمنة للقيم الفارغة
    """
    if not value:
        return '<span class="text-muted">-</span>'
    
    try:
        if format_type == 'date':
            return f'<span class="transaction-date">{value.strftime("%d-%m-%Y")}</span>'
        elif format_type == 'datetime':
            return f'<span class="transaction-date">{value.strftime("%d-%m-%Y %H:%M")}</span>'
        elif format_type == 'datetime_12h':
            date_part = value.strftime("%Y-%m-%d")
            time_part = value.strftime("%I:%M %p")
            return f'<div>{date_part}</div><small class="text-muted">{time_part}</small>'
    except:
        return '<span class="text-muted">-</span>'
    
    return '<span class="text-muted">-</span>'


@register.filter  
def is_empty_value(value):
    """
    فحص آمن للقيم الفارغة
    """
    if value is None:
        return True
    if str(value).strip() == "":
        return True
    return False


@register.filter
def format_boolean_badge(value, field_key=''):
    """
    تنسيق القيم المنطقية كـ badges
    """
    if field_key == 'is_active':
        if value:
            return '<span class="badge bg-success">نشط</span>'
        else:
            return '<span class="badge bg-secondary">غير نشط</span>'
    else:
        if value:
            return '<span class="badge bg-success">نعم</span>'
        else:
            return '<span class="badge bg-secondary">لا</span>'
