"""
أمر إدارة لتهيئة نظام الشراكة
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from decimal import Decimal

from financial.models import (
    PartnerSettings, 
    PartnerPermission, 
    PartnerBalance,
    ChartOfAccounts
)
from financial.utils.partner_integration import PartnerFinancialIntegration

User = get_user_model()


class Command(BaseCommand):
    help = 'تهيئة نظام الشراكة وإعداد البيانات الأساسية'

    def add_arguments(self, parser):
        parser.add_argument(
            '--partner-name',
            type=str,
            default='محمد يوسف',
            help='اسم الشريك (افتراضي: محمد يوسف)'
        )
        
        parser.add_argument(
            '--admin-username',
            type=str,
            help='اسم المستخدم المدير لمنحه صلاحيات الشراكة'
        )
        
        parser.add_argument(
            '--sync-existing',
            action='store_true',
            help='مزامنة المعاملات الموجودة'
        )

    def handle(self, *args, **options):
        partner_name = options['partner_name']
        admin_username = options.get('admin_username')
        sync_existing = options['sync_existing']
        
        self.stdout.write(
            self.style.SUCCESS('🚀 بدء تهيئة نظام الشراكة...')
        )
        
        # 1. إنشاء الإعدادات الافتراضية
        self.setup_default_settings()
        
        # 2. إنشاء أو العثور على حساب الشريك
        partner_account = self.setup_partner_account(partner_name)
        
        # 3. إنشاء رصيد الشريك
        self.setup_partner_balance(partner_account)
        
        # 4. منح صلاحيات للمدير
        if admin_username:
            self.setup_admin_permissions(admin_username)
        
        # 5. مزامنة المعاملات الموجودة
        if sync_existing:
            self.sync_existing_transactions()
        
        self.stdout.write(
            self.style.SUCCESS('✅ تم إعداد نظام الشراكة بنجاح!')
        )

    def setup_default_settings(self):
        """إنشاء الإعدادات الافتراضية"""
        settings = PartnerSettings.get_settings()
        
        self.stdout.write('📋 تم إنشاء الإعدادات الافتراضية:')
        self.stdout.write(f'   • الحد الأقصى للمساهمة اليومية: {settings.max_daily_contribution} ج.م')
        self.stdout.write(f'   • الحد الأقصى للسحب اليومي: {settings.max_daily_withdrawal} ج.م')
        self.stdout.write(f'   • الحد الأقصى للسحب الشهري: {settings.max_monthly_withdrawal} ج.م')

    def setup_partner_account(self, partner_name):
        """إنشاء أو العثور على حساب الشريك"""
        try:
            partner_account = PartnerFinancialIntegration.find_or_create_partner_account(partner_name)
            self.stdout.write(
                self.style.SUCCESS(f'💼 حساب الشريك: {partner_account.name}')
            )
            return partner_account
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ خطأ في إنشاء حساب الشريك: {str(e)}')
            )
            return None

    def setup_partner_balance(self, partner_account):
        """إنشاء رصيد الشريك"""
        if not partner_account:
            return
        
        partner_balance, created = PartnerBalance.objects.get_or_create(
            partner_account=partner_account
        )
        
        if created:
            self.stdout.write('💰 تم إنشاء رصيد جديد للشريك')
        else:
            self.stdout.write('💰 تم العثور على رصيد موجود للشريك')
        
        # تحديث الرصيد
        partner_balance.update_balance()
        
        self.stdout.write(f'   • إجمالي المساهمات: {partner_balance.total_contributions} ج.م')
        self.stdout.write(f'   • إجمالي السحوبات: {partner_balance.total_withdrawals} ج.م')
        self.stdout.write(f'   • الرصيد الحالي: {partner_balance.current_balance} ج.م')

    def setup_admin_permissions(self, admin_username):
        """منح صلاحيات الشراكة للمدير"""
        try:
            admin_user = User.objects.get(username=admin_username)
        except User.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'❌ لم يتم العثور على المستخدم: {admin_username}')
            )
            return
        
        # قائمة الصلاحيات الأساسية للمدير
        admin_permissions = [
            'view_dashboard',
            'create_contribution',
            'create_withdrawal',
            'view_transactions',
            'view_balance',
            'approve_transactions',
            'view_reports',
            'manage_settings',
        ]
        
        granted_count = 0
        for permission_type in admin_permissions:
            permission = PartnerPermission.grant_permission(
                user=admin_user,
                permission_type=permission_type,
                granted_by=admin_user  # المدير يمنح لنفسه
            )
            granted_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(
                f'🔐 تم منح {granted_count} صلاحية للمستخدم {admin_user.get_full_name() or admin_username}'
            )
        )

    def sync_existing_transactions(self):
        """مزامنة المعاملات الموجودة"""
        self.stdout.write('🔄 بدء مزامنة المعاملات الموجودة...')
        
        try:
            synced_count = PartnerFinancialIntegration.sync_existing_transactions()
            self.stdout.write(
                self.style.SUCCESS(f'✅ تم مزامنة {synced_count} حساب شريك')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ خطأ في المزامنة: {str(e)}')
            )

    def display_summary(self):
        """عرض ملخص النظام"""
        self.stdout.write('\n' + '='*50)
        self.stdout.write(self.style.SUCCESS('📊 ملخص نظام الشراكة:'))
        
        # عدد الشركاء
        partner_count = PartnerBalance.objects.count()
        self.stdout.write(f'👥 عدد الشركاء: {partner_count}')
        
        # إجمالي الأرصدة
        total_balance = PartnerBalance.objects.aggregate(
            total=models.Sum('current_balance')
        )['total'] or Decimal('0')
        self.stdout.write(f'💰 إجمالي أرصدة الشركاء: {total_balance} ج.م')
        
        # عدد المستخدمين بصلاحيات
        users_with_permissions = PartnerPermission.objects.values('user').distinct().count()
        self.stdout.write(f'🔐 المستخدمون بصلاحيات: {users_with_permissions}')
        
        self.stdout.write('='*50)
