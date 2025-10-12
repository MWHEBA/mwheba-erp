from django import template

register = template.Library()

@register.filter
def get(dictionary, key):
    """
    الحصول على قيمة من قاموس باستخدام المفتاح
    """
    if not dictionary:
        return None
    
    if not isinstance(dictionary, dict):
        return None
    
    return dictionary.get(key)

@register.filter
def get_item(dictionary, key):
    """
    الحصول على قيمة من قاموس باستخدام المفتاح (مماثل لـ get ولكن باسم مختلف)
    """
    return get(dictionary, key)

@register.filter
def items(dictionary):
    """
    الحصول على العناصر من قاموس
    """
    if not dictionary:
        return []
    
    if not isinstance(dictionary, dict):
        return []
    
    return dictionary.items()

@register.filter
def keys(dictionary):
    """
    الحصول على المفاتيح من قاموس
    """
    if not dictionary:
        return []
    
    if not isinstance(dictionary, dict):
        return []
    
    return dictionary.keys()

@register.filter
def values(dictionary):
    """
    الحصول على القيم من قاموس
    """
    if not dictionary:
        return []
    
    if not isinstance(dictionary, dict):
        return []
    
    return dictionary.values()

@register.filter
def dict_contains(dictionary, key):
    """
    التحقق مما إذا كان المفتاح موجودًا في القاموس
    """
    if not dictionary:
        return False
    
    if not isinstance(dictionary, dict):
        return False
    
    return key in dictionary 