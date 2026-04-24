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
            if setting.data_type == "boolean":
                value = setting.value.lower() in ["true", "1", "yes", "نعم"]
            elif setting.data_type == "integer":
                try:
                    value = int(setting.value)
                except ValueError:
                    value = 0
            elif setting.data_type == "float":
                try:
                    value = float(setting.value)
                except ValueError:
                    value = 0.0
            elif setting.data_type == "json":
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
    # تحويل maintenance_mode من string إلى boolean
    maintenance_value = settings_dict.get("maintenance_mode", False)
    if isinstance(maintenance_value, str):
        maintenance_value = maintenance_value.lower() in ["true", "1", "yes", "نعم"]
    
    return {
        "settings": settings_dict,
        "SITE_NAME": settings_dict.get("site_name", "موهبة ERP"),
        "maintenance_mode": maintenance_value,
    }


def user_permissions(request):
    """
    إضافة بيانات المستخدم والصلاحيات للقوالب
    """
    # في حالة عدم تسجيل الدخول
    if not request.user.is_authenticated:
        return {"user_permissions": {}}

    # قائمة بالصلاحيات المهمة
    permissions = {}

    # إضافة المزيد من الصلاحيات حسب الحاجة

    return {"user_permissions": permissions}


def notifications(request):
    """
    إضافة الإشعارات للمستخدم الحالي
    """
    from core.models import Notification

    # في حالة عدم تسجيل الدخول
    if not request.user.is_authenticated:
        return {"notifications": []}

    # جلب أحدث 10 إشعارات لم يتم قراءتها للمستخدم الحالي
    user_notifications = []

    try:
        # جلب الإشعارات غير المقروءة أولاً، ثم أحدث الإشعارات المقروءة
        unread_notifications = Notification.objects.filter(
            user=request.user, is_read=False
        ).order_by("-created_at")[:10]

        # إذا كان عدد الإشعارات غير المقروءة أقل من 10، أضف بعض الإشعارات المقروءة
        unread_count = unread_notifications.count()

        if unread_count < 10:
            # جلب الإشعارات المقروءة خلال آخر 7 أيام
            one_week_ago = timezone.now() - timedelta(days=7)
            read_notifications = Notification.objects.filter(
                user=request.user, is_read=True, created_at__gte=one_week_ago
            ).order_by("-created_at")[: 10 - unread_count]

            # دمج الإشعارات
            user_notifications = list(unread_notifications) + list(read_notifications)
        else:
            user_notifications = list(unread_notifications)

    except Exception as e:
        # في حالة حدوث أي استثناء، عد بقائمة فارغة
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error loading notifications in context processor: {str(e)}")
        pass

    # إعادة قائمة الإشعارات (كـ objects مباشرة)
    return {"notifications": user_notifications}


def payment_accounts(request):
    """
    إضافة حسابات الدفع (الخزينة/البنك) للقوالب
    متاح في جميع الصفحات تلقائياً لاستخدامه في المودالات والفورمات
    """
    try:
        from financial.models import ChartOfAccounts
        from django.db import models
        
        # جلب حسابات الخزينة والبنك النشطة
        accounts = ChartOfAccounts.objects.filter(
            is_active=True
        ).filter(
            models.Q(is_cash_account=True) | models.Q(is_bank_account=True)
        ).order_by('code')
        
        # الحساب الافتراضي (الخزينة - 10100)
        default_account = ChartOfAccounts.objects.filter(
            code='10100',
            is_active=True
        ).first()
        
        return {
            'payment_accounts': accounts,
            'default_payment_account': default_account
        }
    except Exception as e:
        # في حالة عدم وجود موديول المحاسبة أو أي خطأ
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"Payment accounts context processor: {str(e)}")
        return {
            'payment_accounts': [],
            'default_payment_account': None
        }


def enabled_modules(request):
    """
    إضافة التطبيقات المفعلة للقوالب
    """
    try:
        from core.models import SystemModule
        from django.core.cache import cache
        
        # محاولة الحصول من الكاش
        cache_key = 'enabled_modules_dict'
        enabled_modules_dict = cache.get(cache_key)
        
        if enabled_modules_dict is None:
            modules = SystemModule.objects.filter(is_enabled=True).values(
                'code', 'name_ar', 'icon', 'menu_id', 'url_namespace'
            )
            enabled_modules_dict = {m['code']: m for m in modules}
            cache.set(cache_key, enabled_modules_dict, 300)  # 5 دقائق
        
        return {
            'enabled_modules': enabled_modules_dict,
            'is_module_enabled': lambda code: code in enabled_modules_dict
        }
    except Exception:
        return {'enabled_modules': {}, 'is_module_enabled': lambda code: True}

