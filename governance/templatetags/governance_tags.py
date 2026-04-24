"""
Template tags for governance system.
"""

from django import template

register = template.Library()


@register.filter
def lookup(dictionary, key):
    """
    Template filter to lookup dictionary values by key.
    Usage: {{ dict|lookup:key }}
    """
    if isinstance(dictionary, dict):
        return dictionary.get(key, False)
    return False


@register.filter
def governance_status_class(status):
    """
    Convert governance status to CSS class.
    """
    status_map = {
        'healthy': 'success',
        'warning': 'warning', 
        'critical': 'danger',
        'unknown': 'secondary'
    }
    return status_map.get(status, 'secondary')


@register.filter
def violation_severity_class(severity):
    """
    Convert violation severity to CSS class.
    """
    severity_map = {
        'info': 'info',
        'warning': 'warning',
        'error': 'danger',
        'critical': 'danger'
    }
    return severity_map.get(severity, 'secondary')


@register.simple_tag
def governance_health_icon(status):
    """
    Return appropriate icon for governance health status.
    """
    icon_map = {
        'healthy': 'fas fa-check-circle text-success',
        'warning': 'fas fa-exclamation-triangle text-warning',
        'critical': 'fas fa-times-circle text-danger',
        'unknown': 'fas fa-question-circle text-secondary'
    }
    return icon_map.get(status, 'fas fa-question-circle text-secondary')


@register.inclusion_tag('governance/tags/flag_status.html')
def flag_status(flag_name, enabled, flag_type='component'):
    """
    Render flag status badge.
    """
    return {
        'flag_name': flag_name,
        'enabled': enabled,
        'flag_type': flag_type
    }


@register.inclusion_tag('governance/tags/health_badge.html')
def health_badge(component, status, message=''):
    """
    Render health status badge.
    """
    return {
        'component': component,
        'status': status,
        'message': message
    }