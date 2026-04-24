"""
Template tags للإشعارات
"""
from django import template
from core.notification_icons import get_notification_icon, get_notification_icon_html

register = template.Library()


@register.simple_tag
def notification_icon(notification_type):
    """
    الحصول على فئة أيقونة الإشعار
    
    الاستخدام في القالب:
        {% notification_icon notification.type %}
    """
    return get_notification_icon(notification_type)


@register.simple_tag
def notification_icon_html(notification_type, additional_classes=''):
    """
    الحصول على HTML كامل للأيقونة
    
    الاستخدام في القالب:
        {% notification_icon_html notification.type "me-2" %}
    """
    return get_notification_icon_html(notification_type, additional_classes)


@register.filter
def get_icon(notification):
    """
    فلتر للحصول على أيقونة الإشعار من الكائن
    
    الاستخدام في القالب:
        {{ notification|get_icon }}
    """
    if hasattr(notification, 'get_icon'):
        return notification.get_icon()
    return get_notification_icon(notification.type if hasattr(notification, 'type') else 'info')
