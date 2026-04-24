"""
🔒 Security Template Tags
إضافة nonce وحماية CSP للقوالب
"""

from django import template
from django.utils.safestring import mark_safe
from django.conf import settings

register = template.Library()


@register.simple_tag(takes_context=True)
def csp_nonce(context):
    """
    إرجاع nonce للاستخدام في scripts و styles
    """
    # في التطوير، لا نحتاج nonce
    if settings.DEBUG:
        return ''
        
    request = context.get('request')
    if request and hasattr(request, 'csp_nonce'):
        return request.csp_nonce
    return ''


@register.simple_tag(takes_context=True)
def script_nonce(context):
    """
    إرجاع nonce attribute كامل للـ script tags
    """
    # في التطوير، لا نحتاج nonce
    if settings.DEBUG:
        return ''
        
    request = context.get('request')
    if request and hasattr(request, 'csp_nonce'):
        return mark_safe(f'nonce="{request.csp_nonce}"')
    return ''


@register.simple_tag(takes_context=True)
def style_nonce(context):
    """
    إرجاع nonce attribute كامل للـ style tags
    """
    # في التطوير، لا نحتاج nonce
    if settings.DEBUG:
        return ''
        
    request = context.get('request')
    if request and hasattr(request, 'csp_nonce'):
        return mark_safe(f'nonce="{request.csp_nonce}"')
    return ''


@register.inclusion_tag('security/csp_script.html', takes_context=True)
def csp_script(context, content=''):
    """
    إنشاء script tag مع nonce تلقائياً
    """
    return {
        'nonce': csp_nonce(context),
        'content': content,
        'debug': settings.DEBUG
    }


@register.inclusion_tag('security/csp_style.html', takes_context=True)
def csp_style(context, content=''):
    """
    إنشاء style tag مع nonce تلقائياً
    """
    return {
        'nonce': csp_nonce(context),
        'content': content,
        'debug': settings.DEBUG
    }