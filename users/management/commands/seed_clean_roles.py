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

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("=== Starting Clean RBAC Initialization ==="))

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
                        'view_sale', 'print_sale_invoice', 'view_salesinvoice',
                        'view_salepayment', 'view_creditnote', 'view_salereturn'
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
                        'view_product', 'view_category', 'view_unit', 'view_stock'
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
                        'view_category', 'view_unit', 'view_stock', 'view_supplierproductprice',
                        'add_supplierproductprice', 'change_supplierproductprice'
                    ])
                ),
            },
            'inventory_manager': {
                'display_name': 'أمين مخزن ومواد',
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
                'display_name': 'مشرف صالة الطباعة والتنفيذ',
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
                        'view_product', 'view_stock', 'view_unit'
                    ])
                ),
            },
            'hr_officer': {
                'display_name': 'مسؤول شؤون عاملين ورواتب',
                'description': 'إدارة الموظفين، الحضور والانصراف، الإجازات، مسيرات الرواتب والسلف',
                'is_system_role': True,
                'perm_filter': Q(content_type__app_label='hr'),
            },
            'viewer': {
                'display_name': 'مستعرض فقط',
                'description': 'الاطلاع العام فقط دون صلاحية إضافة أو تعديل أو حذف أي بيانات',
                'is_system_role': False,
                'perm_filter': (
                    Q(codename__startswith='view_') &
                    Q(content_type__app_label__in=[
                        'sale', 'purchase', 'product', 'customer', 'supplier',
                        'financial', 'work_order', 'printing_pricing', 'hr'
                    ])
                ),
            },
        }

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

            if config['perm_filter'] is None:
                # Admin gets ALL permissions
                role.permissions.set(all_valid_perms)
            else:
                matched_perms = Permission.objects.filter(config['perm_filter']).distinct()
                role.permissions.set(matched_perms)

            count = role.permissions.count()
            verb = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"[+] {verb} role '{role_name}' ({config['display_name']}): {count} permissions."))

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
