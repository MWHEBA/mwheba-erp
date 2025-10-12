from django import template
from django.forms.widgets import CheckboxInput

register = template.Library()

@register.filter
def add_class(field, css_class):
    """
    إضافة فئة CSS إلى حقل نموذج
    """
    if not field or not css_class:
        return field
    
    existing_classes = field.field.widget.attrs.get('class', '')
    if existing_classes:
        field.field.widget.attrs['class'] = f"{existing_classes} {css_class}"
    else:
        field.field.widget.attrs['class'] = css_class
    
    return field

@register.filter
def add_placeholder(field, placeholder):
    """
    إضافة placeholder إلى حقل نموذج
    """
    if not field or not placeholder:
        return field
    
    field.field.widget.attrs['placeholder'] = placeholder
    return field

@register.filter
def add_attr(field, attr_str):
    """
    إضافة سمة HTML إلى حقل نموذج
    الصيغة: "name:value" أو "name:" للسمات بلا قيمة
    """
    if not field or not attr_str:
        return field
    
    parts = attr_str.split(':')
    attr_name = parts[0]
    attr_value = parts[1] if len(parts) > 1 else True
    
    field.field.widget.attrs[attr_name] = attr_value
    return field

@register.filter
def is_checkbox(field):
    """
    التحقق مما إذا كان الحقل هو خانة اختيار
    """
    return isinstance(field.field.widget, CheckboxInput)

@register.filter
def is_disabled(field):
    """
    التحقق مما إذا كان الحقل معطلاً
    """
    return field.field.widget.attrs.get('disabled', False)

@register.filter
def is_readonly(field):
    """
    التحقق مما إذا كان الحقل للقراءة فقط
    """
    return field.field.widget.attrs.get('readonly', False)

@register.filter
def set_data_attributes(field, data_attrs):
    """
    تعيين سمات data- متعددة لحقل
    الصيغة: "data-foo:bar;data-baz:qux"
    """
    if not field or not data_attrs:
        return field
    
    pairs = data_attrs.split(';')
    for pair in pairs:
        if ':' in pair:
            name, value = pair.split(':', 1)
            field.field.widget.attrs[name.strip()] = value.strip()
    
    return field 