"""
Template tags للتحكم في صلاحيات القائمة الجانبية
"""
from django import template
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

register = template.Library()

@register.simple_tag(takes_context=True)
def has_sidebar_permission(context, permission_name):
    """
    التحقق من صلاحية المستخدم لعرض عنصر في القائمة الجانبية
    
    Usage: {% has_sidebar_permission 'financial.view_account' as can_view_accounts %}
    """
    user = context['request'].user
    
    if not user.is_authenticated:
        return False
    
    if user.is_superuser:
        return True
    
    return user.has_perm(permission_name)

@register.simple_tag(takes_context=True)
def has_any_sidebar_permission(context, *permission_names):
    """
    التحقق من وجود أي من الصلاحيات المطلوبة
    
    Usage: {% has_any_sidebar_permission 'financial.view_account' 'financial.add_account' as can_access_accounts %}
    """
    user = context['request'].user
    
    if not user.is_authenticated:
        return False
    
    if user.is_superuser:
        return True
    
    return any(user.has_perm(perm) for perm in permission_names)

@register.simple_tag(takes_context=True)
def has_all_sidebar_permissions(context, *permission_names):
    """
    التحقق من وجود جميع الصلاحيات المطلوبة
    
    Usage: {% has_all_sidebar_permissions 'financial.view_account' 'financial.add_account' as can_manage_accounts %}
    """
    user = context['request'].user
    
    if not user.is_authenticated:
        return False
    
    if user.is_superuser:
        return True
    
    return all(user.has_perm(perm) for perm in permission_names)

@register.simple_tag(takes_context=True)
def has_module_access(context, module_name):
    """
    التحقق من صلاحية الوصول لوحدة كاملة
    
    Usage: {% has_module_access 'financial' as can_access_financial %}
    """
    user = context['request'].user
    
    if not user.is_authenticated:
        return False
    
    if user.is_superuser:
        return True
    
    # قائمة الصلاحيات المطلوبة لكل وحدة
    module_permissions = {
        'financial': [
            'financial.view_account',
            'financial.view_transaction',
            'financial.view_expense',
            'financial.view_income',
        ],
        'advanced_accounting': [
            'financial.view_chartofaccounts',
            'financial.view_journalentry',
            'financial.view_accountingperiod',
        ],
        'enhanced_financial': [
            'financial.view_account',
            'financial.view_enhancedbalance',
            'financial.view_paymentsync',
        ],
        'advanced_reports': [
            'financial.view_account',
            'financial.view_journalentry',
            'financial.view_transaction',
        ],
        'sales': [
            'sale.view_sale',
            'sale.view_salereturn',
        ],
        'purchases': [
            'purchase.view_purchase',
            'purchase.view_purchasereturn',
        ],
        'clients': [
            'client.view_customer',
            'client.view_customerpayment',
        ],
        'suppliers': [
            'supplier.view_supplier',
            'supplier.view_supplierpayment',
        ],
        'inventory': [
            'product.view_product',
            'product.view_category',
            'product.view_warehouse',
        ],
        'users': [
            'auth.view_user',
            'users.view_profile',
        ],
        'settings': [
            'core.view_settings',
            'core.view_backup',
        ],
    }
    
    permissions = module_permissions.get(module_name, [])
    if not permissions:
        return False
    
    # يكفي وجود صلاحية واحدة للوصول للوحدة
    return any(user.has_perm(perm) for perm in permissions)

@register.simple_tag(takes_context=True)
def get_user_role_badge(context):
    """
    الحصول على شارة دور المستخدم
    
    Usage: {% get_user_role_badge as user_badge %}
    """
    user = context['request'].user
    
    if not user.is_authenticated:
        return {'text': 'غير مسجل', 'class': 'bg-secondary'}
    
    if user.is_superuser:
        return {'text': 'مدير النظام', 'class': 'bg-danger'}
    
    if user.is_staff:
        return {'text': 'موظف', 'class': 'bg-warning'}
    
    # تحديد الدور بناءً على الصلاحيات
    if user.has_perm('financial.add_account'):
        return {'text': 'محاسب', 'class': 'bg-success'}
    
    if user.has_perm('sale.add_sale'):
        return {'text': 'مبيعات', 'class': 'bg-info'}
    
    if user.has_perm('purchase.add_purchase'):
        return {'text': 'مشتريات', 'class': 'bg-primary'}
    
    return {'text': 'مستخدم', 'class': 'bg-secondary'}

@register.simple_tag(takes_context=True)
def is_feature_enabled(context, feature_name):
    """
    التحقق من تفعيل ميزة معينة
    
    Usage: {% is_feature_enabled 'advanced_accounting' as is_advanced_enabled %}
    """
    # يمكن ربط هذا بإعدادات النظام أو قاعدة البيانات
    enabled_features = {
        'advanced_accounting': True,
        'enhanced_financial': True,
        'advanced_reports': True,
        'payment_sync': True,
        'redis_cache': True,
        'financial_backup': True,
    }
    
    return enabled_features.get(feature_name, False)

@register.simple_tag(takes_context=True)
def get_sidebar_notifications(context):
    """
    الحصول على إشعارات القائمة الجانبية
    
    Usage: {% get_sidebar_notifications as notifications %}
    """
    user = context['request'].user
    
    if not user.is_authenticated:
        return {}
    
    notifications = {}
    
    # إشعارات النظام المالي
    if user.has_perm('financial.view_account'):
        # يمكن إضافة منطق للحصول على عدد الحسابات غير المتوازنة
        notifications['financial'] = {
            'count': 0,
            'type': 'info',
            'message': 'لا توجد تنبيهات مالية'
        }
    
    # إشعارات المبيعات
    if user.has_perm('sale.view_sale'):
        # يمكن إضافة منطق للحصول على عدد الفواتير المعلقة
        notifications['sales'] = {
            'count': 0,
            'type': 'warning',
            'message': 'لا توجد فواتير معلقة'
        }
    
    return notifications

@register.inclusion_tag('partials/sidebar_menu_item.html', takes_context=True)
def sidebar_menu_item(context, title, icon, url=None, permissions=None, badge=None, children=None):
    """
    عرض عنصر في القائمة الجانبية مع التحقق من الصلاحيات
    
    Usage: 
    {% sidebar_menu_item title="الحسابات المالية" icon="fas fa-landmark" url="financial:account_list" permissions="financial.view_account" %}
    """
    user = context['request'].user
    
    # التحقق من الصلاحيات
    has_permission = True
    if permissions:
        if isinstance(permissions, str):
            permissions = [permissions]
        has_permission = any(user.has_perm(perm) for perm in permissions) if user.is_authenticated else False
        if user.is_superuser:
            has_permission = True
    
    return {
        'title': title,
        'icon': icon,
        'url': url,
        'badge': badge,
        'children': children or [],
        'has_permission': has_permission,
        'user': user,
        'request': context['request'],
    }
