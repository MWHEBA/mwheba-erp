"""
Enterprise RBAC Clean Seeding Command
Deletes legacy/Arabic ghost permissions and establishes the 10 Enterprise System Roles
with exact standard Django permissions.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Permission
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from users.models import User, Role


class Command(BaseCommand):
    help = "Seed clean enterprise roles and purge legacy/Arabic permissions"

    def add_arguments(self, parser):
        parser.add_argument(
            '--force-reset',
            action='store_true',
            help='Reset all roles to default canonical permissions, wiping any customizations',
        )

    def handle(self, *args, **options):
        force_reset = options.get('force_reset', False)
        mode_str = "FORCE RESET MODE" if force_reset else "SAFE UPDATE MODE (Preserving Customizations)"
        self.stdout.write(self.style.NOTICE(f"=== Starting Clean RBAC Initialization [{mode_str}] ==="))

        # 1. Purge legacy / non-ascii / Arabic permissions from auth_permission
        arabic_perms = Permission.objects.filter(codename__regex=r'[^\x00-\x7F]')
        deleted_count = arabic_perms.count()
        if deleted_count > 0:
            arabic_perms.delete()
            self.stdout.write(self.style.SUCCESS(f"[+] Purged {deleted_count} Arabic/non-ascii ghost permissions."))
        else:
            self.stdout.write("[i] No non-ascii permissions found.")

        # Delete any obsolete qrapplication permissions
        qr_perms = Permission.objects.filter(content_type__model__icontains='qrapplication')
        if qr_perms.exists():
            cnt = qr_perms.count()
            qr_perms.delete()
            self.stdout.write(self.style.SUCCESS(f"[+] Purged {cnt} obsolete qrapplication permissions."))

        # 2. Define the 10 Enterprise Roles and their permission query specifications
        roles_config = {
            'admin': {
                'display_name': 'مدير النظام',
                'description': 'صلاحيات كاملة وغير مقيدة على كافة موديولات النظام ولوحة التحكم',
                'is_system_role': True,
                'perm_filter': None,  # ALL permissions
            },
            'financial_manager': {
                'display_name': 'مدير مالي',
                'description': 'إدارة القيود، الحسابات، إغلاق الفترات، إعادة تقييم العملات IAS 21، ومراجعة التكاليف وهامش الربح',
                'is_system_role': True,
                'perm_filter': (
                    Q(content_type__app_label='financial') |
                    Q(content_type__app_label='printing_pricing', codename__in=[
                        'view_cost_breakdown', 'view_profit_margins', 'view_all_orders',
                        'view_costcalculation', 'view_printingorder', 'view_ordersummary'
                    ]) |
                    Q(content_type__app_label='sale', codename__in=[
                        'view_sale', 'view_all_sales', 'view_saleitem', 'view_salepayment',
                        'view_salereturn', 'view_salesinvoice', 'view_salesorder', 'view_quotation',
                        'change_unit_price', 'apply_special_discount', 'print_sale_invoice',
                        'view_creditnote', 'view_creditnoteallocation'
                    ]) |
                    Q(content_type__app_label='purchase', codename__in=[
                        'view_purchase', 'view_purchaseitem', 'view_purchasepayment',
                        'view_purchasereturn', 'view_purchaseorder', 'approve_purchase',
                        'view_goodsreceivednote', 'view_supplierbill'
                    ]) |
                    Q(content_type__app_label='customer', codename__startswith='view_') |
                    Q(content_type__app_label='customer', codename__in=[
                        'add_customerpayment', 'change_customerpayment'
                    ]) |
                    Q(content_type__app_label='supplier', codename__startswith='view_') |
                    Q(content_type__app_label='supplier', codename__in=[
                        'add_suppliertransaction', 'change_suppliertransaction'
                    ]) |
                    Q(content_type__app_label='product', codename__startswith='view_')
                ),
            },
            'accountant': {
                'display_name': 'محاسب',
                'description': 'إنشاء وتعديل القيود المحاسبية وسندات القبض والصرف وعرض كشوف الحسابات والفواتير',
                'is_system_role': True,
                'perm_filter': (
                    (
                        Q(content_type__app_label='financial') & (
                            Q(codename__startswith='view_') |
                            Q(codename__startswith='add_') |
                            Q(codename__startswith='change_')
                        ) & ~Q(codename__in=[
                            'close_accounting_period', 'reopen_accounting_period',
                            'run_fx_revaluation', 'delete_accountingperiod',
                            'delete_chartofaccounts', 'delete_journalentry'
                        ])
                    ) |
                    Q(content_type__app_label='customer', codename__in=[
                        'view_customer', 'add_customerpayment', 'change_customerpayment',
                        'view_customerpayment', 'view_customertransaction'
                    ]) |
                    Q(content_type__app_label='supplier', codename__in=[
                        'view_supplier', 'add_suppliertransaction', 'change_suppliertransaction',
                        'view_suppliertransaction', 'view_supplieradvancepayment'
                    ]) |
                    Q(content_type__app_label='sale', codename__in=[
                        'view_sale', 'view_all_sales', 'print_sale_invoice', 'view_salesinvoice',
                        'view_salepayment', 'view_creditnote', 'view_salereturn',
                        'view_quotation', 'view_all_quotations',
                        'view_salesorder', 'view_all_salesorders',
                        'view_deliverynote'
                    ]) |
                    Q(content_type__app_label='purchase', codename__in=[
                        'view_purchase', 'view_purchasepayment', 'view_purchasereturn',
                        'view_supplierbill'
                    ]) |
                    Q(content_type__app_label='product', codename__in=[
                        'view_product', 'view_category', 'view_unit', 'view_stock'
                    ])
                ),
            },
            'sales_manager': {
                'display_name': 'مشرف مبيعات',
                'description': 'الاطلاع على فواتير كافة المناديب، اعتماد الخصومات وتعديل الأسعار وإدارة العملاء',
                'is_system_role': True,
                'perm_filter': (
                    Q(content_type__app_label='sale') |
                    Q(content_type__app_label='customer') |
                    Q(content_type__app_label='printing_pricing', codename__in=[
                        'view_printingorder', 'add_printingorder', 'change_printingorder',
                        'view_all_orders', 'view_profit_margins', 'override_pricing_rules',
                        'view_productsize', 'view_producttype', 'view_papersize',
                        'view_papertype', 'view_costcalculation'
                    ]) |
                    Q(content_type__app_label='product', codename__in=[
                        'view_product', 'view_category', 'view_unit', 'view_stock'
                    ])
                ),
            },
            'sales_rep': {
                'display_name': 'مندوب مبيعات',
                'description': 'إنشاء عروض الأسعار وفواتير المبيعات الخاصة به مع حماية الأسعار وهوامش الربح',
                'is_system_role': True,
                'perm_filter': (
                    Q(content_type__app_label='sale', codename__in=[
                        'view_sale', 'add_sale', 'print_sale_invoice',
                        'view_quotation', 'add_quotation', 'change_quotation',
                        'convert_to_order', 'convert_quotation',
                        'view_salesorder', 'add_salesorder', 'change_salesorder'
                    ]) |
                    Q(content_type__app_label='customer', codename__in=[
                        'view_customer', 'add_customer', 'change_customer'
                    ]) |
                    Q(content_type__app_label='printing_pricing', codename__in=[
                        'view_printingorder', 'add_printingorder', 'change_printingorder',
                        'view_productsize', 'view_producttype'
                    ]) |
                    Q(content_type__app_label='product', codename__in=[
                        'view_product', 'view_category', 'view_unit', 'view_stock', 'view_warehouse'
                    ]) |
                    Q(content_type__app_label='financial', codename__in=[
                        'view_currency', 'view_tax'
                    ])
                ),
            },
            'procurement_officer': {
                'display_name': 'مسؤول مشتريات وموردين',
                'description': 'إنشاء ومتابعة أوامر الشراء وفواتير المشتريات والموردين',
                'is_system_role': True,
                'perm_filter': (
                    Q(content_type__app_label='purchase') |
                    Q(content_type__app_label='supplier') |
                    Q(content_type__app_label='product', codename__in=[
                        'view_product', 'add_product', 'change_product',
                        'view_category', 'view_unit', 'view_stock', 'view_warehouse',
                        'view_supplierproductprice', 'add_supplierproductprice', 'change_supplierproductprice'
                    ]) |
                    Q(content_type__app_label='financial', codename__in=[
                        'view_currency', 'view_tax'
                    ])
                ),
            },
            'inventory_manager': {
                'display_name': 'أمين مخازن ومنتجات',
                'description': 'إدارة الأصناف، حركات المخزن، أذونات الاستلام والتحويلات المخزنية',
                'is_system_role': True,
                'perm_filter': (
                    Q(content_type__app_label='product') |
                    Q(content_type__app_label='purchase', codename__in=[
                        'view_purchase', 'view_goodsreceivednote', 'add_goodsreceivednote',
                        'change_goodsreceivednote', 'view_purchaseorder'
                    ]) |
                    Q(content_type__app_label='sale', codename__in=[
                        'view_sale', 'view_deliverynote', 'add_deliverynote',
                        'change_deliverynote'
                    ]) |
                    Q(content_type__app_label='work_order', codename__in=['view_workorder'])
                ),
            },
            'production_supervisor': {
                'display_name': 'مسؤول تشغيل وإنتاج',
                'description': 'متابعة أوامر الشغل ومراحل الطباعة والتشطيب والتنفيذ الفني',
                'is_system_role': True,
                'perm_filter': (
                    Q(content_type__app_label='work_order') |
                    Q(content_type__app_label='printing_pricing', codename__in=[
                        'view_printingorder', 'view_cost_breakdown', 'view_costcalculation',
                        'view_ordermaterial', 'view_orderservice', 'view_printingmachine',
                        'view_finishingtype', 'view_papersize'
                    ]) |
                    Q(content_type__app_label='product', codename__in=[
                        'view_product', 'view_stock', 'view_unit', 'view_warehouse'
                    ])
                ),
            },
            'hr_officer': {
                'display_name': 'مسؤول موارد بشرية',
                'description': 'إدارة الموظفين، الحضور والانصراف، الإجازات، مسيرات الرواتب والسلف',
                'is_system_role': True,
                'perm_filter': Q(content_type__app_label='hr'),
            },
            'viewer': {
                'display_name': 'مستخدم استعلام',
                'description': 'الاطلاع العام فقط دون صلاحية إضافة أو تعديل أو حذف أي بيانات',
                'is_system_role': True,
                'perm_filter': (
                    Q(codename__startswith='view_') &
                    Q(content_type__app_label__in=[
                        'sale', 'purchase', 'product', 'customer', 'supplier',
                        'financial', 'work_order', 'printing_pricing', 'hr'
                    ])
                ),
            },
        }

        # 2.1 Purge Ghost/Obsolete Roles from database
        ghost_role_names = [
            'activities_coordinator', 'transportation_coordinator',
            'receptionist', 'manager', 'hr_manager'
        ]
        ghost_roles = Role.objects.filter(name__in=ghost_role_names)
        ghost_count = ghost_roles.count()
        if ghost_count > 0:
            for gr in ghost_roles:
                # Reassign any users belonging to ghost role to viewer or admin
                fallback_role = Role.objects.filter(name='viewer').first()
                for user in gr.users.all():
                    user.role = fallback_role
                    user.save(update_fields=['role'])
                gr.delete()
            self.stdout.write(self.style.SUCCESS(f"[+] Purged {ghost_count} ghost roles: {ghost_role_names}"))

        all_valid_perms = Permission.objects.all()

        for role_name, config in roles_config.items():
            role, created = Role.objects.get_or_create(
                name=role_name,
                defaults={
                    'display_name': config['display_name'],
                    'description': config['description'],
                    'is_system_role': config['is_system_role'],
                    'is_active': True,
                }
            )
            # Update display name & description
            role.display_name = config['display_name']
            role.description = config['description']
            role.is_system_role = config['is_system_role']
            role.is_active = True
            role.save()

            if created or force_reset:
                if config['perm_filter'] is None:
                    # Admin gets ALL permissions
                    role.permissions.set(all_valid_perms)
                else:
                    matched_perms = Permission.objects.filter(config['perm_filter']).distinct()
                    role.permissions.set(matched_perms)
            else:
                # Safe mode: Add base canonical permissions without dropping any user customizations
                if config['perm_filter'] is None:
                    role.permissions.add(*all_valid_perms)
                else:
                    matched_perms = Permission.objects.filter(config['perm_filter']).distinct()
                    role.permissions.add(*matched_perms)

            # Auto-resolve prerequisites explicitly in database for every canonical role
            from users.services.permission_dependency import PermissionDependencyService
            added_deps = PermissionDependencyService.auto_resolve_dependencies_for_role(role)

            count = role.permissions.count()
            verb = "Created" if created else "Updated"
            dep_msg = f" (+{added_deps} prerequisites resolved)" if added_deps > 0 else ""
            self.stdout.write(self.style.SUCCESS(f"[+] {verb} role '{role_name}' ({config['display_name']}): {count} permissions{dep_msg}."))

        # 3. Establish correct roles and staff/superuser flags for primary users
        admin_role = Role.objects.get(name='admin')

        mwheba_user = User.objects.filter(username='mwheba').first()
        if mwheba_user:
            mwheba_user.role = admin_role
            mwheba_user.is_staff = True
            mwheba_user.is_superuser = True
            mwheba_user.save()
            self.stdout.write(self.style.SUCCESS("[+] User 'mwheba' set to Role='admin', is_staff=True, is_superuser=True."))

        admin_user = User.objects.filter(username='admin').first()
        if admin_user:
            admin_user.role = admin_role
            admin_user.is_staff = True
            admin_user.is_superuser = True
            admin_user.save()
            self.stdout.write(self.style.SUCCESS("[+] User 'admin' set to Role='admin', is_staff=True, is_superuser=True."))

        # Verify other users: if any user is not admin, ensure is_staff=False, is_superuser=False
        non_admin_users = User.objects.exclude(role__name='admin')
        for u in non_admin_users:
            if u.is_staff or u.is_superuser:
                u.is_staff = False
                u.is_superuser = False
                u.save()
                self.stdout.write(self.style.WARNING(f"[!] User '{u.username}' demoted to is_staff=False, is_superuser=False (Segregation of Duties)."))

        self.stdout.write(self.style.SUCCESS("=== Clean RBAC Initialization Completed Successfully ==="))
