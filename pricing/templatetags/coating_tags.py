from django import template
from ..models import CoatingType

register = template.Library()

@register.simple_tag
def get_coating_types():
    """جلب جميع أنواع التغطية النشطة من الإعدادات"""
    return CoatingType.objects.filter(is_active=True).order_by('name')
