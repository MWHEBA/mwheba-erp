from django import template
from django.template.defaultfilters import floatformat

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