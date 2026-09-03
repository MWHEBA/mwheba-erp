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
        'enable_tax': False,
        'default_tax_rate': 14.0,
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

    enable_tax_value = settings_dict.get("enable_tax", True)
    if isinstance(enable_tax_value, str):
        enable_tax_value = enable_tax_value.lower() in ["true", "1", "yes", "نعم"]
    settings_dict["enable_tax"] = enable_tax_value

    try:
        settings_dict["default_tax_rate"] = float(settings_dict.get("default_tax_rate", 14.0))
    except (ValueError, TypeError):
        settings_dict["default_tax_rate"] = 14.0

    pending_approvals_count = 0
    if getattr(request, 'user', None) and request.user.is_authenticated:
        if request.user.is_superuser or getattr(request.user, 'is_admin', False) or request.user.has_perm('users.ادارة_المالية') or request.user.has_perm('governance.approve_workflow'):
            try:
                from financial.models.approval import EnterpriseApprovalRequest
                pending_approvals_count = EnterpriseApprovalRequest.objects.filter(status="PENDING").count()
            except Exception:
                pending_approvals_count = 0

    cache_key_modules = 'enabled_modules_dict_v1'
    enabled_modules = cache.get(cache_key_modules)
    if enabled_modules is None:
        try:
            from core.models import SystemModule
            enabled_modules = {
                m.code: m.is_enabled
                for m in SystemModule.objects.all()
            }
            cache.set(cache_key_modules, enabled_modules, 300)
        except Exception as e:
            logger.error(f"Error loading enabled modules: {e}")
            enabled_modules = {}

    return {
        "settings": settings_dict,
        "SITE_NAME": settings_dict.get("site_name", "موهبة ERP"),
        "maintenance_mode": maintenance_value,
        "pending_approvals_count": pending_approvals_count,
        "enabled_modules": enabled_modules,
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
    إضافة حسابات الدفع (الخزينة/البنك) المصنفة للقوالب مع Cache
    ✅ استخدام AccountHelperService للمرجعية الموحدة وتقديم الخزن والبنك والافتراضي بمرونة
    """
    cache_key = 'payment_accounts_data_v5'
    cached_data = cache.get(cache_key)

    if cached_data is None:
        try:
            from financial.services.account_helper import AccountHelperService

            cash_qs = AccountHelperService.get_cash_accounts().select_related('currency')
            bank_qs = AccountHelperService.get_bank_accounts().select_related('currency')
            custody_qs = AccountHelperService.get_custody_accounts().select_related('currency')

            def _serialize_acc(acc):
                curr_code = 'EGP'
                curr_symbol = 'ج.م'
                curr_rate = '1.000000'
                is_func = '1'
                if getattr(acc, 'currency', None):
                    curr = acc.currency
                    curr_code = curr.code or 'EGP'
                    curr_symbol = getattr(curr, 'symbol', None) or curr_code
                    curr_rate = str(getattr(curr, 'rate', getattr(curr, 'current_rate', '1.000000')) or '1.000000')
                    is_func = '1' if getattr(curr, 'is_functional', False) else '0'
                return {
                    'id': acc.id,
                    'code': acc.code,
                    'name': acc.name,
                    'currency_code': curr_code,
                    'currency_symbol': curr_symbol,
                    'currency_rate': curr_rate,
                    'currency_is_functional': is_func,
                    'is_cash_account': getattr(acc, 'is_cash_account', False),
                    'is_bank_account': getattr(acc, 'is_bank_account', False),
                }

            cash_accounts_data = [_serialize_acc(a) for a in cash_qs]
            bank_accounts_data = [_serialize_acc(a) for a in bank_qs]
            custody_accounts_data = [_serialize_acc(a) for a in custody_qs]

            # الدمج للقوائم العامة
            all_accounts_data = cash_accounts_data + bank_accounts_data

            # الحساب الافتراضي الرئيسي للنقدية بسلسلة السقوط الاحتياطي
            def_cash_obj = AccountHelperService.get_default_cash_account()
            default_account_data = None
            if def_cash_obj:
                default_account_data = _serialize_acc(def_cash_obj)

            # الحساب الافتراضي للبنك
            default_bank_data = None
            if bank_accounts_data:
                default_bank_data = bank_accounts_data[0]

            cached_data = {
                'accounts': all_accounts_data,
                'cash_accounts': cash_accounts_data,
                'bank_accounts': bank_accounts_data,
                'custody_accounts': custody_accounts_data,
                'default': default_account_data,
                'default_bank': default_bank_data
            }

            cache.set(cache_key, cached_data, 600)

        except Exception as e:
            logger.debug(f"Payment accounts context processor error: {e}")
            cached_data = {
                'accounts': [],
                'cash_accounts': [],
                'bank_accounts': [],
                'custody_accounts': [],
                'default': None,
                'default_bank': None
            }

    return {
        'payment_accounts': cached_data['accounts'],
        'cash_payment_accounts': cached_data.get('cash_accounts', []),
        'bank_payment_accounts': cached_data.get('bank_accounts', []),
        'custody_payment_accounts': cached_data.get('custody_accounts', []),
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
