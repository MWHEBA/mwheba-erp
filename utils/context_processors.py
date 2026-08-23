from django.conf import settings
from django.utils import timezone
from django.core.cache import cache
import datetime
from core.models import SystemSetting


def common_variables(request):
    """
    إضافة متغيرات مشتركة للاستخدام في جميع القوالب
    """
    current_date = timezone.now()

    # currency_symbol مع cache - بدلاً من DB query في كل request
    currency_symbol = cache.get('default_currency_symbol')
    currency_symbol_en = cache.get('default_currency_symbol_en')
    if currency_symbol is None or currency_symbol_en is None:
        from core.utils import get_default_currency
        currency_symbol = get_default_currency()
        currency_symbol_en = SystemSetting.get_currency_symbol_en()
        cache.set('default_currency_symbol', currency_symbol, 3600)
        cache.set('default_currency_symbol_en', currency_symbol_en, 3600)

    # installed_apps - لا تحتاج DB
    installed_apps = [
        app.split(".")[-1]
        for app in settings.INSTALLED_APPS
        if not app.startswith("django.") and not app.startswith("crispy_")
    ]

    # بيانات المؤسسة - يمكن cache لمدة طويلة
    cache_key = 'company_info_v1'
    company_info = cache.get(cache_key)
    
    if company_info is None:
        try:
            company_info = {
                'name': SystemSetting.get_setting('company_name', "موهبة ERP"),
                'slogan': SystemSetting.get_setting('company_slogan', "نظام إدارة المبيعات والمخزون"),
                'logo': settings.STATIC_URL + "img/logo.png",
                'stamp': "",
                'enable_stamp': SystemSetting.get_setting('enable_company_stamp', True),
                'address': SystemSetting.get_setting('company_address', "القاهرة، مصر"),
                'phone': SystemSetting.get_setting('company_phone', "+201234567890"),
                'email': SystemSetting.get_setting('company_email', "info@mwheba-erp.com"),
                'website': SystemSetting.get_setting('company_website', "www.mwheba-erp.com"),
            }
            db_logo = SystemSetting.get_setting('company_logo')
            if db_logo:
                company_info['logo'] = db_logo.replace('/media/', '').lstrip('/')
            db_stamp = SystemSetting.get_setting('company_stamp')
            if db_stamp:
                company_info['stamp'] = db_stamp.replace('/media/', '').lstrip('/')
        except Exception:
            company_info = {
                'name': "موهبة ERP",
                'slogan': "نظام إدارة المبيعات والمخزون",
                'logo': settings.STATIC_URL + "img/logo.png",
                'stamp': "",
                'enable_stamp': True,
                'address': "القاهرة، مصر",
                'phone': "+201234567890",
                'email': "info@mwheba-erp.com",
                'website': "www.mwheba-erp.com",
            }
        # Cache لمدة ساعة
        cache.set(cache_key, company_info, 3600)

    from financial.services.exchange_rate_service import ExchangeRateService
    try:
        func_curr_obj = ExchangeRateService.get_functional_currency()
        func_curr_id = func_curr_obj.id if func_curr_obj else None
    except Exception:
        func_curr_id = None

    try:
        from financial.models.currency import Currency
        active_currencies = list(Currency.objects.filter(is_active=True).order_by("-is_functional", "code"))
        for curr in active_currencies:
            try:
                curr.current_rate = ExchangeRateService.get_exchange_rate(curr)
            except Exception:
                curr.current_rate = 1.0
    except Exception:
        active_currencies = []

    return {
        "current_date": current_date,
        "current_year": current_date.year,
        "currency_symbol": currency_symbol,
        "currency_symbol_en": currency_symbol_en,
        "active_currencies": active_currencies,
        "functional_currency": {
            "id": func_curr_id,
            "symbol": currency_symbol,
            "code": currency_symbol_en,
            "name": "العملة المحلية",
        },
        "company_name": company_info['name'],
        "company_slogan": company_info['slogan'],
        "company_logo": company_info['logo'],
        "company_stamp": company_info.get('stamp', ''),
        "enable_company_stamp": company_info.get('enable_stamp', True),
        "enable_quotations": SystemSetting.get_bool('enable_quotations', False),
        "enable_sales_orders": SystemSetting.get_bool('enable_sales_orders', False),
        "enable_purchase_orders": SystemSetting.get_bool('enable_purchase_orders', False),
        "company_address": company_info['address'],
        "company_phone": company_info['phone'],
        "company_email": company_info['email'],
        "company_website": company_info['website'],
        "main_models": {},  # counts أُزيلت - لا تُستخدم في أي template
        "installed_apps": installed_apps,
        "debug": settings.DEBUG,
    }



def user_permissions(request):
    """
    إضافة صلاحيات المستخدم للاستخدام في القوالب
    """
    if not request.user.is_authenticated:
        return {"user_perms": {}}

    # قائمة بجميع الإجراءات الشائعة للنماذج
    common_actions = ["view", "add", "change", "delete"]

    # قائمة بالنماذج الشائعة
    common_models = [
        "user",
        "group",
        "permission",
        "customer",
        "supplier",
        "product",
        "category",
        "payment",
        "sale",
        "purchase",
        "expense",
        "expensecategory",
        "report",
        "settings",
    ]

    # إنشاء قاموس بجميع الصلاحيات المحتملة
    user_perms = {}
    user = request.user

    # إضافة الصلاحيات العامة
    user_perms["is_staff"] = user.is_staff
    user_perms["is_superuser"] = user.is_superuser

    # إضافة الصلاحيات التفصيلية
    if not user.is_superuser:  # المدير العام لديه جميع الصلاحيات
        for model in common_models:
            for action in common_actions:
                perm_codename = f"{action}_{model}"
                user_perms[perm_codename] = user.has_perm(f"app_label.{perm_codename}")
    else:
        # المدير العام لديه جميع الصلاحيات
        for model in common_models:
            for action in common_actions:
                perm_codename = f"{action}_{model}"
                user_perms[perm_codename] = True

    return {"user_perms": user_perms}


def breadcrumb_context(request):
    """
    توفير سياق شريط التنقل (Breadcrumb) للقوالب

    هذه الدالة تقوم بإنشاء قائمة افتراضية لشريط التنقل بناءً على رابط URL الحالي
    ويمكن استبدالها أو تعديلها بواسطة العرض (View) عن طريق إضافة متغير breadcrumb_items للسياق
    """
    # لا حاجة لإنشاء breadcrumb للصفحة الرئيسية
    if request.path == "/" or request.path == "/login/" or request.path == "/logout/":
        return {"generated_breadcrumb_items": []}

    # تجزئة المسار الحالي للحصول على قائمة breadcrumb
    path_parts = request.path.strip("/").split("/")
    breadcrumb_items = []

    # إضافة الصفحة الرئيسية كعنصر أول دائمًا
    breadcrumb_items.append({"title": "الرئيسية", "url": "/", "icon": "fas fa-home"})

    # ترجمة بعض الكلمات الشائعة - تعريف خارج الشروط ليكون متاح في كل مكان
    translations = {
        "Product": "المنتجات",
        "Products": "المنتجات",
        "Category": "التصنيفات",
        "Categories": "التصنيفات",
        "Financial": "الإدارة المالية",
        "Client": "العملاء",
        "Clients": "العملاء",
        "Customer": "العملاء",
        "Customers": "العملاء",
        "Sale": "المبيعات",
        "Sales": "المبيعات",
        "Purchase": "المشتريات",
        "Purchases": "المشتريات",
        "Supplier": "الموردين",
        "Suppliers": "الموردين",
        "Account": "الحسابات",
        "Accounts": "الحسابات",
        "Expense": "المصروفات",
        "Expenses": "المصروفات",
        "Income": "الإيرادات",
        "Incomes": "الإيرادات",
        "Transaction": "المعاملات المالية",
        "Transactions": "المعاملات المالية",
        "Return": "المرتجعات",
        "Returns": "المرتجعات",
        "List": "قائمة",
        "Create": "إضافة",
        "Edit": "تعديل",
        "Add": "إضافة",
        "Delete": "حذف",
        "Detail": "تفاصيل",
        "Details": "تفاصيل",
    }

    # معالجة أجزاء المسار لإنشاء بقية العناصر
    current_path = ""
    for i, part in enumerate(path_parts):
        # تخطي الجزء الأخير لأنه سيكون العنصر النشط
        if i == len(path_parts) - 1 and not part.isdigit():
            if part:
                # تنظيف الجزء وتحويله لصيغة مقروءة
                title = part.replace("-", " ").replace("_", " ").title()

                for eng, ar in translations.items():
                    if eng.lower() in title.lower():
                        title = title.lower().replace(eng.lower(), ar)

                breadcrumb_items.append(
                    {
                        "title": title,
                        "url": "",  # العنصر النشط ليس له رابط
                        "active": True,
                    }
                )
        else:
            # إضافة المسار الحالي
            current_path += "/" + part

            # تخطي المعرفات الرقمية
            if part.isdigit():
                continue

            # تحويل الاسم إلى صيغة مقروءة
            title = part.replace("-", " ").replace("_", " ").title()

            # ترجمة الكلمات الشائعة
            for eng, ar in translations.items():
                if eng.lower() in title.lower():
                    title = title.lower().replace(eng.lower(), ar)

            breadcrumb_items.append(
                {"title": title, "url": current_path + "/", "active": False}
            )

    return {"generated_breadcrumb_items": breadcrumb_items}


def get_dashboard_counts():
    """
    جلب الإحصائيات للـ Dashboard فقط
    استخدمها في dashboard view بدلاً من context processor
    """
    from django.apps import apps
    import logging
    logger = logging.getLogger(__name__)

    cache_key = 'dashboard_counts_v1'
    counts = cache.get(cache_key)

    if counts is None:
        counts = {}

        try:
            from django.db.models import Count

            if apps.is_installed('product'):
                Product = apps.get_model('product', 'Product')
                counts['products'] = Product.objects.aggregate(
                    total=Count('id')
                )['total']

            if apps.is_installed('client'):
                Customer = apps.get_model('client', 'Customer')
                counts['customers'] = Customer.objects.filter(
                    is_active=True
                ).aggregate(total=Count('id'))['total']

            if apps.is_installed('supplier'):
                Supplier = apps.get_model('supplier', 'Supplier')
                counts['suppliers'] = Supplier.objects.aggregate(
                    total=Count('id')
                )['total']

            if apps.is_installed('sale'):
                Sale = apps.get_model('sale', 'Sale')
                counts['sales'] = Sale.objects.aggregate(
                    total=Count('id')
                )['total']

            if apps.is_installed('purchase'):
                Purchase = apps.get_model('purchase', 'Purchase')
                counts['purchases'] = Purchase.objects.aggregate(
                    total=Count('id')
                )['total']

        except Exception as e:
            logger.error(f"Error getting dashboard counts: {e}")

        cache.set(cache_key, counts, 300)

    return counts

