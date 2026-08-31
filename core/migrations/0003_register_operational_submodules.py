# Generated manually for MWHEBA ERP Sub-Modules Architecture

from django.db import migrations


def register_submodules(apps, schema_editor):
    SystemModule = apps.get_model('core', 'SystemModule')
    SystemSetting = apps.get_model('core', 'SystemSetting')

    def get_setting_bool(key, default=False):
        setting = SystemSetting.objects.filter(key=key).first()
        if setting:
            return setting.value.lower() in ('true', '1', 'yes', 'on')
        return default

    # جلب التطبيقات الأصلية لربط الاعتماديات
    sales_module = SystemModule.objects.filter(code='customers_sales').first()
    purchase_module = SystemModule.objects.filter(code='suppliers_purchases').first()

    # 1. عروض الأسعار
    quotations_mod, created = SystemModule.objects.get_or_create(
        code='quotations',
        defaults={
            'name_ar': 'عروض الأسعار',
            'name_en': 'Quotations',
            'description': 'إدارة عروض الأسعار للعملاء وتحويلها المباشر لفواتير وأوامر بيع',
            'icon': 'fas fa-file-contract',
            'module_type': 'optional',
            'is_enabled': get_setting_bool('enable_quotations', False),
            'order': 11,
            'url_namespace': '',
            'menu_id': 'salesMenu',
        }
    )
    if sales_module:
        quotations_mod.required_modules.add(sales_module)

    # 2. أوامر البيع والتسليم
    so_mod, created = SystemModule.objects.get_or_create(
        code='sales_orders',
        defaults={
            'name_ar': 'أوامر البيع والتسليم',
            'name_en': 'Sales Orders',
            'description': 'إدارة أوامر البيع وحجز المخزون وإذون تسليم البضاعة',
            'icon': 'fas fa-clipboard-list',
            'module_type': 'optional',
            'is_enabled': get_setting_bool('enable_sales_orders', False),
            'order': 12,
            'url_namespace': '',
            'menu_id': 'salesMenu',
        }
    )
    if sales_module:
        so_mod.required_modules.add(sales_module)

    # 3. أوامر الشراء والتوريد
    po_mod, created = SystemModule.objects.get_or_create(
        code='purchase_orders',
        defaults={
            'name_ar': 'أوامر الشراء والتوريد',
            'name_en': 'Purchase Orders',
            'description': 'إدارة أوامر الشراء ومتابعة التوريدات واستلام البضاعة بالمخزن',
            'icon': 'fas fa-shopping-cart',
            'module_type': 'optional',
            'is_enabled': get_setting_bool('enable_purchase_orders', False),
            'order': 21,
            'url_namespace': '',
            'menu_id': 'purchaseMenu',
        }
    )
    if purchase_module:
        po_mod.required_modules.add(purchase_module)


def reverse_submodules(apps, schema_editor):
    SystemModule = apps.get_model('core', 'SystemModule')
    SystemModule.objects.filter(code__in=['quotations', 'sales_orders', 'purchase_orders']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_initial"),
    ]

    operations = [
        migrations.RunPython(register_submodules, reverse_submodules),
    ]
