"""
Management command لتهيئة تطبيقات النظام
"""
from django.core.management.base import BaseCommand
from core.models import SystemModule


class Command(BaseCommand):
    help = 'تهيئة تطبيقات النظام القابلة للتفعيل/التعطيل'
    
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('بدء تهيئة تطبيقات النظام...'))
        
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
                'order': 50,
                'url_namespace': 'printing_pricing',
                'menu_id': 'printingPricingMenu',
                'required_modules_codes': [],
            },
        ]
        
        created_count = 0
        updated_count = 0
        
        for data in modules_data:
            required_codes = data.pop('required_modules_codes', [])
            module, created = SystemModule.objects.update_or_create(
                code=data['code'],
                defaults=data
            )
            
            # ربط التطبيقات المطلوبة
            if required_codes:
                required_modules = SystemModule.objects.filter(code__in=required_codes)
                module.required_modules.set(required_modules)
            
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'✓ تم إنشاء التطبيق: {module.name_ar}')
                )
            else:
                updated_count += 1
                self.stdout.write(
                    self.style.WARNING(f'⟳ تم تحديث التطبيق: {module.name_ar}')
                )
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 50))
        self.stdout.write(self.style.SUCCESS(f'تم إنشاء {created_count} تطبيق جديد'))
        self.stdout.write(self.style.SUCCESS(f'تم تحديث {updated_count} تطبيق موجود'))
        self.stdout.write(self.style.SUCCESS('=' * 50))
        
        # مسح الكاش
        from django.core.cache import cache
        cache.delete('enabled_modules_dict')
        cache.delete('enabled_modules_set')
        # محاولة مسح pattern إذا كان متاح
        try:
            cache.delete_pattern('module_enabled_*')
        except AttributeError:
            # LocMemCache لا يدعم delete_pattern
            pass
        
        self.stdout.write(self.style.SUCCESS('✓ تم مسح الكاش'))
