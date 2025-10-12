from django.core.management.base import BaseCommand
from django.db import transaction
from financial.models import AccountType, ChartOfAccounts


class Command(BaseCommand):
    help = 'تبسيط أنواع الحسابات للتركيز على إدارة المخزون'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='تأكيد حذف الأنواع غير الضرورية',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='عرض ما سيتم حذفه دون تنفيذ الحذف الفعلي',
        )

    def handle(self, *args, **options):
        if not options['confirm'] and not options['dry_run']:
            self.stdout.write(
                self.style.ERROR(
                    'يجب استخدام --confirm لتأكيد الحذف أو --dry-run لمعاينة العملية'
                )
            )
            return

        # الأنواع الأساسية التي يجب الاحتفاظ بها (بالأكواد)
        essential_types = [
            # الأصول الأساسية
            'ASSET',           # الأصول (رئيسي)
            'CURRENT_ASSET',   # الأصول المتداولة
            'CASH',            # النقدية
            'BANK',            # البنوك
            'INVENTORY',       # المخزون ⭐
            'RECEIVABLES',     # العملاء
            
            # الخصوم الأساسية
            'LIABILITY',       # الخصوم (رئيسي)
            'CURRENT_LIABILITY', # الخصوم المتداولة
            'PAYABLES',        # الموردين
            
            # حقوق الملكية
            'EQUITY',          # حقوق الملكية (رئيسي)
            'CAPITAL',         # رأس المال
            
            # الإيرادات
            'REVENUE',         # الإيرادات (رئيسي)
            'SALES_REVENUE',   # إيرادات المبيعات
            
            # المصروفات
            'EXPENSE',         # المصروفات (رئيسي)
            'COGS',            # تكلفة البضاعة المباعة ⭐
            'OPERATING_EXPENSE', # المصروفات التشغيلية
        ]

        if options['dry_run']:
            self.preview_deletion(essential_types)
        else:
            self.stdout.write(
                self.style.WARNING(
                    'تحذير: سيتم حذف أنواع الحسابات غير الضرورية!'
                )
            )
            response = input('هل أنت متأكد؟ اكتب "نعم" للمتابعة: ')
            if response.lower() in ['نعم', 'yes', 'y']:
                self.simplify_account_types(essential_types)
            else:
                self.stdout.write(self.style.SUCCESS('تم إلغاء العملية'))

    def preview_deletion(self, essential_types):
        """معاينة الأنواع التي سيتم حذفها"""
        self.stdout.write(self.style.HTTP_INFO('\n=== معاينة التبسيط ===\n'))
        
        # الأنواع التي ستبقى
        types_to_keep = AccountType.objects.filter(code__in=essential_types)
        self.stdout.write(self.style.SUCCESS(f'\n✅ الأنواع التي ستبقى ({types_to_keep.count()} نوع):\n'))
        for acc_type in types_to_keep.order_by('code'):
            icon = self.get_icon(acc_type.code)
            self.stdout.write(f'  {icon} {acc_type.name} ({acc_type.code})')
        
        # الأنواع التي سيتم حذفها
        types_to_delete = AccountType.objects.exclude(code__in=essential_types)
        self.stdout.write(self.style.WARNING(f'\n❌ الأنواع التي سيتم حذفها ({types_to_delete.count()} نوع):\n'))
        for acc_type in types_to_delete.order_by('code'):
            # التحقق من وجود حسابات مرتبطة
            accounts_count = ChartOfAccounts.objects.filter(account_type=acc_type).count()
            warning = f' ⚠️  [{accounts_count} حساب مرتبط]' if accounts_count > 0 else ''
            self.stdout.write(f'  ❌ {acc_type.name} ({acc_type.code}){warning}')
        
        self.stdout.write(self.style.HTTP_INFO(f'\n📊 الإحصائيات:'))
        self.stdout.write(f'  - الأنواع الحالية: {AccountType.objects.count()}')
        self.stdout.write(f'  - سيتم الاحتفاظ بـ: {types_to_keep.count()}')
        self.stdout.write(f'  - سيتم حذف: {types_to_delete.count()}')
        self.stdout.write(f'  - النسبة المتبقية: {(types_to_keep.count() / AccountType.objects.count() * 100):.1f}%')

    def simplify_account_types(self, essential_types):
        """حذف الأنواع غير الضرورية"""
        self.stdout.write(self.style.HTTP_INFO('\n=== بدء عملية التبسيط ===\n'))
        
        try:
            with transaction.atomic():
                # الحصول على الأنواع المراد حذفها
                types_to_delete = AccountType.objects.exclude(code__in=essential_types)
                
                # التحقق من الحسابات المرتبطة
                self.stdout.write('التحقق من الحسابات المرتبطة...')
                types_with_accounts = []
                for acc_type in types_to_delete:
                    accounts_count = ChartOfAccounts.objects.filter(account_type=acc_type).count()
                    if accounts_count > 0:
                        types_with_accounts.append((acc_type, accounts_count))
                
                if types_with_accounts:
                    self.stdout.write(
                        self.style.WARNING(
                            f'\n⚠️  وجدنا {len(types_with_accounts)} نوع مرتبط بحسابات:\n'
                        )
                    )
                    for acc_type, count in types_with_accounts:
                        self.stdout.write(f'  - {acc_type.name}: {count} حساب')
                    
                    self.stdout.write(
                        self.style.HTTP_INFO(
                            '\n🔄 سيتم نقل الحسابات للأنواع المناسبة...\n'
                        )
                    )
                    
                    # نقل الحسابات للأنواع المناسبة
                    self.migrate_accounts(types_with_accounts, essential_types)
                
                # حذف الأنواع غير المرتبطة
                deleted_count = types_to_delete.count()
                types_to_delete.delete()
                
                self.stdout.write(
                    self.style.SUCCESS(f'\n✅ تم حذف {deleted_count} نوع بنجاح!')
                )
                
                # عرض الإحصائيات النهائية
                remaining_count = AccountType.objects.count()
                self.stdout.write(self.style.HTTP_INFO(f'\n📊 النتيجة النهائية:'))
                self.stdout.write(f'  - الأنواع المتبقية: {remaining_count}')
                self.stdout.write(f'  - تم التبسيط بنسبة: {(deleted_count / (deleted_count + remaining_count) * 100):.1f}%')
                
                self.stdout.write(
                    self.style.SUCCESS(
                        '\n🎉 تم تبسيط أنواع الحسابات بنجاح!'
                    )
                )
                self.stdout.write(
                    self.style.HTTP_INFO(
                        '\n💡 الآن نظامك مركز على إدارة المخزون بشكل أفضل!\n'
                    )
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ حدث خطأ أثناء التبسيط: {str(e)}')
            )
            raise

    def migrate_accounts(self, types_with_accounts, essential_types):
        """نقل الحسابات من الأنواع القديمة للأنواع الجديدة المناسبة"""
        
        # خريطة النقل: من النوع القديم -> للنوع الجديد
        migration_map = {
            # الموردين -> الموردون والدائنون
            'الموردين والذمم الدائنة': 'PAYABLES',
            '2100': 'PAYABLES',
            
            # حقوق الملكية -> رأس المال
            'حقوق الملكية': 'CAPITAL',
            '3000': 'CAPITAL',
            '3': 'EQUITY',
            
            # الإيرادات -> إيرادات المبيعات
            'الإيرادات': 'SALES_REVENUE',
            '4000': 'SALES_REVENUE',
            
            # المصروفات -> المصروفات التشغيلية
            'المصروفات': 'OPERATING_EXPENSE',
            '5000': 'OPERATING_EXPENSE',
        }
        
        migrated_count = 0
        
        for old_type, accounts_count in types_with_accounts:
            # البحث عن النوع الجديد المناسب
            new_type_code = None
            
            # البحث بالاسم أو الكود
            for key, value in migration_map.items():
                if key in old_type.name or key == old_type.code:
                    new_type_code = value
                    break
            
            # إذا لم نجد نوع محدد، نستخدم النوع الرئيسي حسب التصنيف
            if not new_type_code:
                category_defaults = {
                    'asset': 'CURRENT_ASSET',
                    'liability': 'CURRENT_LIABILITY',
                    'equity': 'CAPITAL',
                    'revenue': 'SALES_REVENUE',
                    'expense': 'OPERATING_EXPENSE',
                }
                new_type_code = category_defaults.get(old_type.category, 'CURRENT_ASSET')
            
            # الحصول على النوع الجديد
            try:
                new_type = AccountType.objects.get(code=new_type_code)
                
                # نقل جميع الحسابات
                accounts = ChartOfAccounts.objects.filter(account_type=old_type)
                for account in accounts:
                    account.account_type = new_type
                    account.save()
                    migrated_count += 1
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  ✅ تم نقل {accounts_count} حساب من "{old_type.name}" إلى "{new_type.name}"'
                    )
                )
                
            except AccountType.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(
                        f'  ❌ خطأ: لم يتم العثور على النوع الجديد {new_type_code}'
                    )
                )
        
        self.stdout.write(
            self.style.SUCCESS(f'\n✅ تم نقل {migrated_count} حساب بنجاح!\n')
        )

    def get_icon(self, code):
        """الحصول على أيقونة مناسبة لكل نوع"""
        icons = {
            'ASSET': '🏢',
            'CURRENT_ASSET': '💼',
            'CASH': '💰',
            'BANK': '🏦',
            'INVENTORY': '📦',
            'RECEIVABLES': '👥',
            'LIABILITY': '📋',
            'CURRENT_LIABILITY': '📝',
            'PAYABLES': '🏪',
            'EQUITY': '🏛️',
            'CAPITAL': '💎',
            'REVENUE': '💵',
            'SALES_REVENUE': '💸',
            'EXPENSE': '📊',
            'COGS': '📉',
            'OPERATING_EXPENSE': '🔧',
        }
        return icons.get(code, '📁')
