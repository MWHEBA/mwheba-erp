from django import template
from django.db.models import Q

register = template.Library()


@register.simple_tag
def get_service_categories(supplier):
    """الحصول على فئات الخدمات المتاحة لمورد معين"""
    # الحصول على الفئات من الخدمات المتخصصة لهذا المورد
    categories = []
    for service in supplier.specialized_services.all():
        if service.category and service.category not in categories:
            categories.append(service.category)

    return categories


@register.simple_tag
def get_all_service_categories(supplier):
    """الحصول على فئات الخدمات المختارة للمورد"""
    try:
        # إرجاع فقط الفئات المختارة لهذا المورد
        return supplier.supplier_types.filter(is_active=True).order_by(
            "display_order", "name"
        )
    except AttributeError:
        # في حالة عدم وجود supplier_types، إرجاع قائمة فارغة
        return []


@register.filter
def filter_by_category(services, category):
    """فلترة الخدمات حسب الفئة"""
    return services.filter(category=category)


@register.simple_tag
def has_services_for_category(services_by_category, category_id):
    """التحقق من وجود خدمات لفئة معينة"""
    for category_group in services_by_category:
        if category_group.grouper and category_group.grouper.id == category_id:
            return True
    return False
