"""
مصدر موحد لأيقونات الإشعارات
يوفر mapping واحد لجميع أنواع الإشعارات في النظام
"""

# خريطة أيقونات الإشعارات - المصدر الوحيد للحقيقة
NOTIFICATION_ICONS = {
    # أنواع عامة
    'info': 'fa-info',
    'success': 'fa-check',
    'warning': 'fa-exclamation-triangle',
    'danger': 'fa-times',
    
    # المخزون والمنتجات
    'inventory_alert': 'fa-box',
    'product_expiry': 'fa-calendar-times',
    'stock_transfer': 'fa-exchange-alt',
    
    # المبيعات
    'new_sale': 'fa-shopping-cart',
    'sale_payment': 'fa-money-bill-wave',
    'sale_return': 'fa-undo-alt',
    
    # المشتريات
    'new_purchase': 'fa-shopping-bag',
    'purchase_payment': 'fa-hand-holding-usd',
    'purchase_return': 'fa-reply',
    
    # المالية
    'payment_received': 'fa-money-bill-wave',  # دفعة مستلمة
    'payment_made': 'fa-credit-card',  # دفعة مسددة ✅
    'new_invoice': 'fa-file-invoice',  # فاتورة جديدة ✅
    
    # الموارد البشرية
    'hr_leave_request': 'fa-calendar-check',
    'hr_attendance': 'fa-user-clock',
    'hr_payroll': 'fa-wallet',
    'hr_contract': 'fa-file-contract',  # عقد موظف (عام)
    
    # إشعارات العقود (محددة)
    'contract_created': 'fa-file-contract',  # عقد جديد ✅
    'contract_activated': 'fa-check-circle',  # تفعيل عقد ✅
    'contract_terminated': 'fa-ban',  # إنهاء عقد ✅
    'probation_ending': 'fa-clock',  # انتهاء فترة تجربة ✅
    'contract_expiring_soon': 'fa-calendar-exclamation',  # عقد سينتهي قريباً ✅
    'contract_expiring_urgent': 'fa-exclamation-triangle',  # عقد سينتهي عاجل ✅
    
    # أخرى
    'return_request': 'fa-undo',
    'system_alert': 'fa-exclamation-circle',
}

# الأيقونة الافتراضية
DEFAULT_ICON = 'fa-bell'


def get_notification_icon(notification_type):
    """
    الحصول على أيقونة الإشعار حسب النوع
    
    Args:
        notification_type: نوع الإشعار
        
    Returns:
        str: اسم فئة الأيقونة (مثل: 'fa-check')
    """
    return NOTIFICATION_ICONS.get(notification_type, DEFAULT_ICON)


def get_all_notification_types():
    """
    الحصول على جميع أنواع الإشعارات المدعومة
    
    Returns:
        list: قائمة بأنواع الإشعارات
    """
    return list(NOTIFICATION_ICONS.keys())


def get_notification_icon_html(notification_type, additional_classes=''):
    """
    الحصول على HTML كامل للأيقونة
    
    Args:
        notification_type: نوع الإشعار
        additional_classes: فئات CSS إضافية
        
    Returns:
        str: HTML للأيقونة
    """
    icon_class = get_notification_icon(notification_type)
    return f'<i class="fas {icon_class} {additional_classes}"></i>'
