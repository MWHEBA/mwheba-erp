"""
دوال مساعدة مشتركة لوحدة الموارد البشرية
"""
from datetime import date


def get_min_allowed_date():
    """
    أقدم تاريخ مسموح بإدخال بيانات تؤثر على الراتب.
    القاعدة: 26 من الشهر السابق.

    Returns:
        date: أقدم تاريخ مسموح به
    """
    today = date.today()
    if today.month == 1:
        return date(today.year - 1, 12, 26)
    return date(today.year, today.month - 1, 26)


def validate_entry_date(entry_date, field_name='date'):
    """
    التحقق من أن التاريخ لا يسبق 26 من الشهر السابق.
    يُستخدم في clean() لأي موديل يؤثر على الراتب.

    Args:
        entry_date: التاريخ المراد التحقق منه
        field_name: اسم الحقل لرسالة الخطأ

    Returns:
        dict: قاموس الأخطاء (فارغ إذا لم يكن هناك خطأ)
    """
    if not entry_date:
        return {}

    min_date = get_min_allowed_date()
    if entry_date < min_date:
        return {field_name: f'لا يمكن إدخال بيانات بتاريخ قبل {min_date.strftime("%Y-%m-%d")}'}
    return {}
