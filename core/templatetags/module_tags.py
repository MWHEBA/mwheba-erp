"""
Template tags لإدارة التطبيقات القابلة للتفعيل/التعطيل
"""
from django import template
from django.core.cache import cache
import logging

register = template.Library()
logger = logging.getLogger(__name__)


@register.simple_tag(takes_context=True)
def is_module_enabled(context, module_code):
    """
    التحقق من تفعيل تطبيق معين
    Usage: {% is_module_enabled 'sale' as sale_enabled %}
    """
    # محاولة الحصول من الكاش أولاً
    cache_key = f'module_enabled_{module_code}'
    is_enabled = cache.get(cache_key)
    
    if is_enabled is None:
        try:
            from core.models import SystemModule
            is_enabled = SystemModule.objects.filter(
                code=module_code, 
                is_enabled=True
            ).exists()
            cache.set(cache_key, is_enabled, 300)  # 5 دقائق
            logger.debug(f"Module {module_code} enabled status: {is_enabled}")
        except Exception as e:
            # في حالة عدم وجود الجدول أو أي خطأ، افترض أن التطبيق مفعّل
            logger.error(f"Error checking module {module_code}: {str(e)}")
            is_enabled = True
    
    return is_enabled


@register.filter(name='is_module_enabled')
def is_module_enabled_filter(module_code):
    """
    فلتر للتحقق من تفعيل تطبيق
    Usage: {% if 'sale'|is_module_enabled %}
    """
    cache_key = f'module_enabled_{module_code}'
    is_enabled = cache.get(cache_key)
    
    if is_enabled is None:
        try:
            from core.models import SystemModule
            is_enabled = SystemModule.objects.filter(
                code=module_code, 
                is_enabled=True
            ).exists()
            cache.set(cache_key, is_enabled, 300)
        except Exception as e:
            logger.error(f"Error in filter for module {module_code}: {str(e)}")
            is_enabled = True
    
    return is_enabled
