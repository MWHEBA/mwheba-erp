from django import template
from decimal import Decimal

register = template.Library()


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
