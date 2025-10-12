from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from datetime import timedelta

def global_settings(request):
    """
    إضافة إعدادات عامة للقوالب
    """
    from core.models import SystemSetting
    
    # جلب الإعدادات من قاعدة البيانات 
    settings_dict = {}
    
    try:
        # الحصول على جميع الإعدادات النشطة
        all_settings = SystemSetting.objects.filter(is_active=True)
        
        for setting in all_settings:
            # تحويل القيمة إلى النوع المناسب
            if setting.data_type == 'boolean':
                value = setting.value.lower() in ['true', '1', 'yes', 'نعم']
            elif setting.data_type == 'integer':
                try:
                    value = int(setting.value)
                except ValueError:
                    value = 0
            elif setting.data_type == 'float':
                try:
                    value = float(setting.value)
                except ValueError:
                    value = 0.0
            elif setting.data_type == 'json':
                try:
                    import json
                    value = json.loads(setting.value)
                except Exception:
                    value = {}
            else:
                # النص والأنواع الأخرى
                value = setting.value
            
            # إضافة القيمة إلى القاموس
            settings_dict[setting.key] = value
    except Exception:
        # في حالة عدم وجود جدول الإعدادات أو أي استثناء
        pass
    
    # إعادة قاموس الإعدادات
    return {
        'settings': settings_dict,
        'SITE_NAME': settings_dict.get('site_name', 'موهبة ERP'),
    }


def user_permissions(request):
    """
    إضافة بيانات المستخدم والصلاحيات للقوالب
    """
    # في حالة عدم تسجيل الدخول
    if not request.user.is_authenticated:
        return {'user_permissions': {}}
    
    # قائمة بالصلاحيات المهمة
    permissions = {}
    
    # إضافة المزيد من الصلاحيات حسب الحاجة
    
    return {'user_permissions': permissions}


def notifications(request):
    """
    إضافة الإشعارات للمستخدم الحالي
    """
    from core.models import Notification
    
    # في حالة عدم تسجيل الدخول
    if not request.user.is_authenticated:
        return {'notifications': []}
    
    # جلب أحدث 10 إشعارات لم يتم قراءتها للمستخدم الحالي
    user_notifications = []
    
    try:
        # جلب الإشعارات غير المقروءة أولاً، ثم أحدث الإشعارات المقروءة
        unread_notifications = Notification.objects.filter(
            user=request.user, 
            is_read=False
        ).order_by('-created_at')[:10]
        
        # إذا كان عدد الإشعارات غير المقروءة أقل من 10، أضف بعض الإشعارات المقروءة
        unread_count = unread_notifications.count()
        
        if unread_count < 10:
            # جلب الإشعارات المقروءة خلال آخر 7 أيام
            one_week_ago = timezone.now() - timedelta(days=7)
            read_notifications = Notification.objects.filter(
                user=request.user,
                is_read=True,
                created_at__gte=one_week_ago
            ).order_by('-created_at')[:10-unread_count]
            
            # دمج الإشعارات
            user_notifications = list(unread_notifications) + list(read_notifications)
        else:
            user_notifications = list(unread_notifications)
            
        # تحويل كل إشعار إلى قاموس بالمعلومات المطلوبة
        notifications_data = []
        for notification in user_notifications:
            # تحديد الرابط بناء على نوع الإشعار (يمكن تخصيصه حسب أنواع الإشعارات)
            link = "#"
            if notification.type == 'inventory_alert':
                link = "/product/inventory/"
            elif notification.type == 'payment_received':
                link = "/financial/payments/"
            elif notification.type == 'new_invoice':
                link = "/sale/invoices/"
            elif notification.type == 'return_request':
                link = "/sale/returns/"
            
            # إضافة بيانات الإشعار
            notifications_data.append({
                'id': notification.id,
                'title': notification.title,
                'message': notification.message,
                'notification_type': notification.type,
                'read': notification.is_read,
                'created_at': notification.created_at,
                'link': link,
            })
    except Exception:
        # في حالة حدوث أي استثناء، عد بقائمة فارغة
        pass
    
    # إعادة قائمة الإشعارات
    return {'notifications': notifications_data} 