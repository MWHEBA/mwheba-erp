"""
Context Processors موحدة ومحسّنة للأداء
تستخدم Cache لتقليل استعلامات قاعدة البيانات
"""
import logging
from datetime import timedelta
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

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

            all_settings = SystemSetting.objects.filter(is_active=True).values(
                'key', 'value', 'data_type'
            )

            settings_dict = {}
            for setting in all_settings:
                key = setting['key']
                value = setting['value']
                data_type = setting['data_type']

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

            cache.set(cache_key, settings_dict, 15)

        except Exception as e:
            logger.error(f"Error loading global settings: {e}")
            settings_dict = {}

    DEFAULT_SETTINGS = {
        'invoice_product_code_display': 'none',
        'sale_invoice_item_types': 'both',
        'site_name': 'موهبة ERP',
        'enable_thermal_printing': False,
        'enable_company_stamp': True,
        'color_primary': '#04578d',
        'color_primary_dark': '#033d64',
        'color_primary_light': '#e6f0fa',
        'color_primary_hover': '#0462a0',
    }
    for def_key, def_val in DEFAULT_SETTINGS.items():
        if def_key not in settings_dict or settings_dict[def_key] is None or settings_dict[def_key] == '':
            settings_dict[def_key] = def_val

    maintenance_value = settings_dict.get("maintenance_mode", False)
    if isinstance(maintenance_value, str):
        maintenance_value = maintenance_value.lower() in ["true", "1", "yes", "نعم"]

    thermal_value = settings_dict.get("enable_thermal_printing", False)
    if isinstance(thermal_value, str):
        thermal_value = thermal_value.lower() in ["true", "1", "yes", "نعم"]
    settings_dict["enable_thermal_printing"] = thermal_value

    stamp_value = settings_dict.get("enable_company_stamp", True)
    if isinstance(stamp_value, str):
        stamp_value = stamp_value.lower() in ["true", "1", "yes", "نعم"]
    settings_dict["enable_company_stamp"] = stamp_value

    return {
        "settings": settings_dict,
        "SITE_NAME": settings_dict.get("site_name", "موهبة ERP"),
        "maintenance_mode": maintenance_value,
    }


def user_permissions(request):
    """
    إضافة بيانات المستخدم والصلاحيات للقوالب
    """
    if not request.user.is_authenticated:
        return {"user_permissions": {}}

    permissions = {}
    return {"user_permissions": permissions}


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

            accounts_data = list(
                ChartOfAccounts.objects.filter(
                    is_active=True
                ).filter(
                    Q(is_cash_account=True) | Q(is_bank_account=True)
                ).values('id', 'code', 'name', 'is_cash_account', 'is_bank_account')
                .order_by('code')
            )

            from financial.services.role_registry import AccountRoleRegistry
            def_code = AccountRoleRegistry.resolve_role_code("DEFAULT_CASH_DRAWER")
            default_account_data = ChartOfAccounts.objects.filter(
                code=def_code,
                is_active=True
            ).values('id', 'code', 'name').first()

            def_bank_code = AccountRoleRegistry.resolve_role_code("DEFAULT_BANK_ACCOUNT")
            default_bank_data = ChartOfAccounts.objects.filter(
                code=def_bank_code,
                is_active=True
            ).values('id', 'code', 'name').first()

            cached_data = {
                'accounts': accounts_data,
                'default': default_account_data,
                'default_bank': default_bank_data
            }

            cache.set(cache_key, cached_data, 600)

        except Exception as e:
            logger.debug(f"Payment accounts context processor: {e}")
            cached_data = {
                'accounts': [],
                'default': None,
                'default_bank': None
            }

    return {
        'payment_accounts': cached_data['accounts'],
        'default_payment_account': cached_data['default'],
        'default_bank_account': cached_data.get('default_bank')
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
    """
    from core.models import Notification

    if not request.user.is_authenticated:
        return {"notifications": []}

    try:
        user_notifications = list(
            Notification.objects.filter(
                user=request.user,
                is_read=False
            ).select_related('user')
            .order_by("-created_at")[:10]
            .values('id', 'title', 'message', 'created_at', 'is_read', 'notification_type')
        )

    except Exception as e:
        logger.error(f"Error loading notifications: {e}")
        user_notifications = []

    return {"notifications": user_notifications}
