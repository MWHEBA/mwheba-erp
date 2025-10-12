from django import template

register = template.Library()

@register.filter
def product_mul(value, arg):
    """
    فلتر لضرب القيمة الأولى بالقيمة الثانية
    """
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return value

@register.filter
def product_div(value, arg):
    """
    فلتر لقسمة القيمة الأولى على القيمة الثانية
    """
    try:
        return float(value) / float(arg)
    except (ValueError, TypeError, ZeroDivisionError):
        return value

@register.filter(name='product_add')
def add_float(value, arg):
    """
    فلتر لإضافة القيمة الأولى والثانية كأرقام عشرية
    """
    try:
        return float(value) + float(arg)
    except (ValueError, TypeError):
        return value

@register.filter(name='product_sub')
def sub(value, arg):
    """
    فلتر لطرح القيمة الثانية من القيمة الأولى
    """
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return value 