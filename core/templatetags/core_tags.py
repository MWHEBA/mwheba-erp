from django import template
from core.models import SystemSetting

register = template.Library()

@register.simple_tag
def currency_symbol():
    """
    إرجاع رمز العملة من إعدادات النظام
    """
    return SystemSetting.get_currency_symbol()

@register.filter
def format_currency(value):
    """
    تنسيق المبلغ مع رمز العملة مع إزالة العلامات العشرية للأرقام الصحيحة
    """
    if value is None:
        return '-'
    try:
        # التحقق من كون الرقم صحيح (بدون كسور)
        float_value = float(value)
        is_whole_number = float_value == int(float_value)
        
        # تنسيق القيمة
        if is_whole_number:
            # رقم صحيح - بدون علامات عشرية
            formatted_value = f"{int(float_value):,}"
        else:
            # رقم عشري - مع العلامات العشرية
            formatted_value = f"{float_value:,.2f}"
        
        currency = SystemSetting.get_currency_symbol()
        return f"{formatted_value} {currency}"
    except (ValueError, TypeError):
        return str(value)

@register.inclusion_tag('hr/attendance/partials/status_badge.html')
def display_attendance_status(status):
    """
    يعرض badge منسق لحالة الحضور.
    """
    status_map = {
        'present': {'label': 'حاضر', 'color': 'success'},
        'absent': {'label': 'غائب', 'color': 'danger'},
        'late': {'label': 'متأخر', 'color': 'warning'},
        'early_leave': {'label': 'انصراف مبكر', 'color': 'info'},
        'on_leave': {'label': 'إجازة', 'color': 'purple'},
        'weekend': {'label': 'عطلة', 'color': 'secondary'},
        'holiday': {'label': 'عطلة رسمية', 'color': 'primary'},
        'no_shift': {'label': 'لا توجد وردية', 'color': 'dark'},
    }
    default_status = {'label': status, 'color': 'light'}
    status_info = status_map.get(status, default_status)

    return {
        'label': status_info['label'],
        'color': status_info['color'],
    }
