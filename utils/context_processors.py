from django.conf import settings
from django.utils import timezone
import datetime


def common_variables(request):
    """
    إضافة متغيرات مشتركة للاستخدام في جميع القوالب
    """
    from django.apps import apps

    # متغيرات التاريخ
    current_date = timezone.now()
    current_year = current_date.year

    # متغيرات العملة
    currency_symbol = "ج.م"

    # بيانات المؤسسة
    # يمكن استبدالها بنموذج في قاعدة البيانات في المستقبل
    company_name = "موهبة ERP"
    company_slogan = "نظام إدارة المبيعات والمخزون"
    company_logo = settings.STATIC_URL + "img/logo.png"
    company_address = "القاهرة، مصر"
    company_phone = "+201234567890"
    company_email = "info@mwheba-erp.com"
    company_website = "www.mwheba-erp.com"

    # الحصول على أسماء جميع التطبيقات المثبتة
    installed_apps = [
        app.split(".")[-1]
        for app in settings.INSTALLED_APPS
        if not app.startswith("django.") and not app.startswith("crispy_")
    ]

    # الحصول على قائمة النماذج الرئيسية
    main_models = {}
    if request.user.is_authenticated:
        try:
            if "product" in installed_apps:
                Product = apps.get_model("product", "Product")
                main_models["products_count"] = Product.objects.count()

            if "client" in installed_apps:
                Customer = apps.get_model("client", "Customer")
                main_models["customers_count"] = Customer.objects.count()

            if "supplier" in installed_apps:
                Supplier = apps.get_model("supplier", "Supplier")
                main_models["suppliers_count"] = Supplier.objects.count()

            if "sale" in installed_apps:
                Sale = apps.get_model("sale", "Sale")
                main_models["sales_count"] = Sale.objects.count()

            if "purchase" in installed_apps:
                Purchase = apps.get_model("purchase", "Purchase")
                main_models["purchases_count"] = Purchase.objects.count()
        except Exception:
            # تجاهل أي استثناءات (مثلاً إذا لم يكن هناك جدول أو صلاحيات)
            pass

    # إرجاع السياق
    return {
        "current_date": current_date,
        "current_year": current_year,
        "currency_symbol": currency_symbol,
        "company_name": company_name,
        "company_slogan": company_slogan,
        "company_logo": company_logo,
        "company_address": company_address,
        "company_phone": company_phone,
        "company_email": company_email,
        "company_website": company_website,
        "main_models": main_models,
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
        "brand",
        "sale",
        "saleinvoice",
        "payment",
        "purchase",
        "purchaseinvoice",
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
        "Sale": "المبيعات",
        "Sales": "المبيعات",
        "Purchase": "المشتريات",
        "Purchases": "المشتريات",
        "Customer": "العملاء",
        "Customers": "العملاء",
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
