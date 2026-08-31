"""
Management command لتهيئة تطبيقات النظام
"""
from django.core.management.base import BaseCommand
from core.models import SystemModule, SystemSetting


class Command(BaseCommand):
    help = 'تهيئة تطبيقات النظام القابلة للتفعيل/التعطيل'
    
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('بدء تهيئة تطبيقات النظام...'))
        
        # استقراء القيم الحالية من إعدادات النظام لوراثتها في حالة الإنشاء الجديد
        legacy_quotations_enabled = SystemSetting.get_bool('enable_quotations', False)
        legacy_so_enabled = SystemSetting.get_bool('enable_sales_orders', False)
        legacy_po_enabled = SystemSetting.get_bool('enable_purchase_orders', False)
        
        modules_data = [
            # التطبيقات الأساسية (غير قابلة للتعطيل)
            {
                'code': 'core',
                'name_ar': 'النظام الأساسي',
                'name_en': 'Core System',
                'description': 'النواة الأساسية للنظام - لا يمكن تعطيله',
                'icon': 'fas fa-cog',
                'module_type': 'core',
                'order': 1,
                'url_namespace': 'core',
                'menu_id': '',
            },
            {
                'code': 'financial',
                'name_ar': 'الإدارة المالية',
                'name_en': 'Financial Management',
                'description': 'المحاسبة والتقارير المالية - شغال افتراضياً',
                'icon': 'fas fa-money-bill-wave',
                'module_type': 'core',
                'order': 2,
                'url_namespace': 'financial',
                'menu_id': 'financialManagementMenu',
            },
            
            # التطبيقات القابلة للتفعيل/التعطيل
            {
                'code': 'customers_sales',
                'name_ar': 'إدارة العملاء والمبيعات',
                'name_en': 'Customers & Sales Management',
                'description': 'إدارة العملاء وفواتير المبيعات والمرتجعات',
                'icon': 'fas fa-users',
                'module_type': 'optional',
                'order': 10,
                'url_namespace': 'client,sale',
                'menu_id': 'customerMenu,salesMenu',
                'required_modules_codes': [],
            },
            {
                'code': 'quotations',
                'name_ar': 'عروض الأسعار',
                'name_en': 'Quotations',
                'description': 'إدارة عروض الأسعار للعملاء وتحويلها المباشر لفواتير وأوامر بيع',
                'icon': 'fas fa-file-contract',
                'module_type': 'optional',
                'is_enabled': legacy_quotations_enabled,
                'order': 11,
                'url_namespace': '',
                'menu_id': 'salesMenu',
                'required_modules_codes': ['customers_sales'],
            },
            {
                'code': 'sales_orders',
                'name_ar': 'أوامر البيع والتسليم',
                'name_en': 'Sales Orders',
                'description': 'إدارة أوامر البيع وحجز المخزون وإذون تسليم البضاعة',
                'icon': 'fas fa-clipboard-list',
                'module_type': 'optional',
                'is_enabled': legacy_so_enabled,
                'order': 12,
                'url_namespace': '',
                'menu_id': 'salesMenu',
                'required_modules_codes': ['customers_sales'],
            },
            {
                'code': 'suppliers_purchases',
                'name_ar': 'إدارة الموردين والمشتريات',
                'name_en': 'Suppliers & Purchases Management',
                'description': 'إدارة الموردين وفواتير المشتريات والمرتجعات',
                'icon': 'fas fa-people-carry',
                'module_type': 'optional',
                'order': 20,
                'url_namespace': 'supplier,purchase',
                'menu_id': 'supplierMenu,purchaseMenu',
                'required_modules_codes': [],
            },
            {
                'code': 'purchase_orders',
                'name_ar': 'أوامر الشراء والتوريد',
                'name_en': 'Purchase Orders',
                'description': 'إدارة أوامر الشراء ومتابعة التوريدات واستلام البضاعة بالمخزن',
                'icon': 'fas fa-shopping-cart',
                'module_type': 'optional',
                'is_enabled': legacy_po_enabled,
                'order': 21,
                'url_namespace': '',
                'menu_id': 'purchaseMenu',
                'required_modules_codes': ['suppliers_purchases'],
            },
            {
                'code': 'warehouses',
                'name_ar': 'إدارة المخازن',
                'name_en': 'Warehouse Management',
                'description': 'إدارة المنتجات والخدمات والمخازن والمخزون',
                'icon': 'fas fa-warehouse',
                'module_type': 'optional',
                'order': 30,
                'url_namespace': 'product',
                'menu_id': 'productsMenu,warehousesMenu',
                'required_modules_codes': [],
            },
            {
                'code': 'hr',
                'name_ar': 'إدارة الموارد البشرية',
                'name_en': 'Human Resources Management',
                'description': 'إدارة الموظفين والحضور والرواتب والعقود',
                'icon': 'fas fa-users-cog',
                'module_type': 'optional',
                'order': 40,
                'url_namespace': 'hr',
                'menu_id': 'hrMenu',
                'required_modules_codes': [],
            },
            {
                'code': 'printing_pricing',
                'name_ar': 'نظام تسعير المطبوعات',
                'name_en': 'Printing Pricing System',
                'description': 'إدارة طلبات تسعير المطبوعات وحساب التكاليف',
                'icon': 'fas fa-print',
                'module_type': 'optional',
                'is_enabled': False,
                'order': 50,
                'url_namespace': 'printing_pricing',
                'menu_id': 'printingPricingMenu',
                'required_modules_codes': [],
            },
            {
                'code': 'work_orders',
                'name_ar': 'إدارة أوامر الشغل',
                'name_en': 'Work Orders Management',
                'description': 'إدارة أوامر الشغل ومراكز التكاليف والأرباح للطلبات',
                'icon': 'fas fa-tasks',
                'module_type': 'optional',
                'is_enabled': False,
                'order': 60,
                'url_namespace': 'work_order',
                'menu_id': 'workOrdersMenu',
                'required_modules_codes': ['customers_sales'],
            },
        ]
        
        created_count = 0
        updated_count = 0
        
        for data in modules_data:
            required_codes = data.pop('required_modules_codes', [])
            code = data.pop('code')
            module, created = SystemModule.objects.get_or_create(
                code=code,
                defaults=data
            )
            
            if not created:
                # تحديث البيانات فقط دون تغيير حالة التفعيل الحالية
                for key, value in data.items():
                    if key != 'is_enabled':
                        setattr(module, key, value)
                module.save()
            
            # ربط التطبيقات المطلوبة
            if required_codes:
                required_modules = SystemModule.objects.filter(code__in=required_codes)
                module.required_modules.set(required_modules)
            
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'[+] تم إنشاء التطبيق: {module.name_ar}')
                )
            else:
                updated_count += 1
                self.stdout.write(
                    self.style.WARNING(f'[*] تم تحديث التطبيق: {module.name_ar}')
                )
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 50))
        self.stdout.write(self.style.SUCCESS(f'تم إنشاء {created_count} تطبيق جديد'))
        self.stdout.write(self.style.SUCCESS(f'تم تحديث {updated_count} تطبيق موجود'))
        self.stdout.write(self.style.SUCCESS('=' * 50))
        
        # مسح الكاش الشامل
        from django.core.cache import cache
        cache.delete('enabled_modules_dict')
        cache.delete('enabled_modules_dict_v2')
        cache.delete('enabled_modules_set')
        SystemSetting.invalidate_all_system_caches()
        try:
            cache.delete_pattern('module_enabled_*')
        except AttributeError:
            pass
        
        self.stdout.write(self.style.SUCCESS('[+] تم مسح كاش المنظومة بالكامل'))
