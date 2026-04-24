"""
Context Processors محسّنة للأداء
استخدام Cache لتقليل استعلامات قاعدة البيانات
"""
from django.core.cache import cache
from django.utils import timezone
from django.db.models import Q
import logging

logger = logging.getLogger(__name__)


def global_settings(request):
    """
    إضافة إعدادات عامة للقوالب مع Cache
    ✅ تحسين: استخدام cache بدلاً من query في كل طلب
    """
    cache_key = 'global_settings_dict_v2'
    settings_dict = cache.get(cache_key)
    
    if settings_dict is None:
        try:
            from core.models import SystemSetting
            
            # جلب جميع الإعدادات النشطة مرة واحدة
            all_settings = SystemSetting.objects.filter(is_active=True).values(
                'key', 'value', 'data_type'
            )
            
            settings_dict = {}
            for setting in all_settings:
                key = setting['key']
                value = setting['value']
                data_type = setting['data_type']
                
                # تحويل القيمة إلى النوع المناسب
                if data_type == "boolean":
                    value = value.lower() in ["true", "1", "yes", "نعم"]
                elif data_type == "integer":
                    try:
                        value = int(value)
                    except ValueError:
                        value = 0
                elif data_type == "float":
                    try:
                        value = float(value)
                    except ValueError:
                        value = 0.0
                elif data_type == "json":
                    try:
                        import json
                        value = json.loads(value)
                    except Exception:
                        value = {}
                
                settings_dict[key] = value
            
            # Cache لمدة 5 دقائق
            cache.set(cache_key, settings_dict, 300)
            
        except Exception as e:
            logger.error(f"Error loading global settings: {e}")
            settings_dict = {}
    
    # تحويل maintenance_mode من string إلى boolean
    maintenance_value = settings_dict.get("maintenance_mode", False)
    if isinstance(maintenance_value, str):
        maintenance_value = maintenance_value.lower() in ["true", "1", "yes", "نعم"]
    
    return {
        "settings": settings_dict,
        "SITE_NAME": settings_dict.get("site_name", "موهبة ERP"),
        "maintenance_mode": maintenance_value,
    }


def payment_accounts(request):
    """
    إضافة حسابات الدفع (الخزينة/البنك) للقوالب مع Cache
    ✅ تحسين: cache لمدة 10 دقائق + استخدام values() بدلاً من objects
    """
    cache_key = 'payment_accounts_data_v2'
    cached_data = cache.get(cache_key)
    
    if cached_data is None:
        try:
            from financial.models import ChartOfAccounts
            
            # جلب الحسابات كـ dictionaries بدلاً من objects (أخف)
            accounts_data = list(
                ChartOfAccounts.objects.filter(
                    is_active=True
                ).filter(
                    Q(is_cash_account=True) | Q(is_bank_account=True)
                ).values('id', 'code', 'name', 'is_cash_account', 'is_bank_account')
                .order_by('code')
            )
            
            # الحساب الافتراضي
            default_account_data = ChartOfAccounts.objects.filter(
                code='10100',
                is_active=True
            ).values('id', 'code', 'name').first()
            
            cached_data = {
                'accounts': accounts_data,
                'default': default_account_data
            }
            
            # Cache لمدة 10 دقائق
            cache.set(cache_key, cached_data, 600)
            
        except Exception as e:
            logger.debug(f"Payment accounts context processor: {e}")
            cached_data = {
                'accounts': [],
                'default': None
            }
    
    return {
        'payment_accounts': cached_data['accounts'],
        'default_payment_account': cached_data['default']
    }


def enabled_modules(request):
    """
    إضافة التطبيقات المفعلة للقوالب مع Cache
    ✅ تحسين: cache لمدة 5 دقائق
    """
    cache_key = 'enabled_modules_dict_v2'
    enabled_modules_dict = cache.get(cache_key)
    
    if enabled_modules_dict is None:
        try:
            from core.models import SystemModule
            
            modules = SystemModule.objects.filter(is_enabled=True).values(
                'code', 'name_ar', 'icon', 'menu_id', 'url_namespace'
            )
            enabled_modules_dict = {m['code']: m for m in modules}
            
            # Cache لمدة 5 دقائق
            cache.set(cache_key, enabled_modules_dict, 300)
            
        except Exception as e:
            logger.error(f"Error loading enabled modules: {e}")
            enabled_modules_dict = {}
    
    return {
        'enabled_modules': enabled_modules_dict,
        'is_module_enabled': lambda code: code in enabled_modules_dict
    }


def notifications(request):
    """
    إضافة الإشعارات للمستخدم الحالي
    ⚠️ هذا context processor معطل حالياً في settings.py
    """
    from core.models import Notification
    from datetime import timedelta

    if not request.user.is_authenticated:
        return {"notifications": []}

    try:
        # جلب أحدث 10 إشعارات غير مقروءة فقط
        user_notifications = list(
            Notification.objects.filter(
                user=request.user, 
                is_read=False
            ).select_related('user')  # ✅ تحسين: select_related
            .order_by("-created_at")[:10]
            .values('id', 'title', 'message', 'created_at', 'is_read', 'notification_type')
        )
        
    except Exception as e:
        logger.error(f"Error loading notifications: {e}")
        user_notifications = []

    return {"notifications": user_notifications}
