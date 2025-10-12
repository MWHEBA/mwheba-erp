from django.core.management.base import BaseCommand
from financial.models import ChartOfAccounts, AccountType


class Command(BaseCommand):
    help = 'تحليل دليل الحسابات الحالي واقتراح التحسينات'

    def handle(self, *args, **options):
        self.stdout.write(self.style.HTTP_INFO('\n=== تحليل دليل الحسابات ===\n'))
        
        # 1. عرض الحسابات الموجودة
        self.show_current_accounts()
        
        # 2. عرض الأنواع المتاحة
        self.show_available_types()
        
        # 3. تحليل التغطية
        self.analyze_coverage()
        
        # 4. اقتراح الحسابات المطلوبة
        self.suggest_accounts()

    def show_current_accounts(self):
        """عرض الحسابات الموجودة حالياً"""
        accounts = ChartOfAccounts.objects.all().order_by('account_type__category', 'code')
        
        self.stdout.write(self.style.SUCCESS(f'\n📊 الحسابات الموجودة ({accounts.count()} حساب):\n'))
        
        current_category = None
        for account in accounts:
            category = account.account_type.get_category_display()
            if category != current_category:
                current_category = category
                self.stdout.write(f'\n{self.get_category_icon(account.account_type.category)} {category}:')
            
            status = '✅' if account.is_active else '❌'
            leaf = '🍃' if account.is_leaf else '🌳'
            balance = f'{account.opening_balance:,.2f}' if account.opening_balance else '0.00'
            
            self.stdout.write(
                f'  {status} {leaf} [{account.code}] {account.name} '
                f'({account.account_type.name}) - رصيد: {balance}'
            )

    def show_available_types(self):
        """عرض أنواع الحسابات المتاحة"""
        types = AccountType.objects.filter(is_active=True).order_by('category', 'code')
        
        self.stdout.write(self.style.HTTP_INFO(f'\n\n🏷️  أنواع الحسابات المتاحة ({types.count()} نوع):\n'))
        
        current_category = None
        for acc_type in types:
            category = acc_type.get_category_display()
            if category != current_category:
                current_category = category
                self.stdout.write(f'\n{self.get_category_icon(acc_type.category)} {category}:')
            
            # عد الحسابات المرتبطة
            accounts_count = ChartOfAccounts.objects.filter(account_type=acc_type).count()
            
            self.stdout.write(
                f'  {self.get_icon(acc_type.code)} {acc_type.name} ({acc_type.code}) '
                f'- {accounts_count} حساب'
            )

    def analyze_coverage(self):
        """تحليل تغطية الأنواع بالحسابات"""
        self.stdout.write(self.style.WARNING(f'\n\n⚠️  تحليل التغطية:\n'))
        
        types = AccountType.objects.filter(is_active=True)
        empty_types = []
        
        for acc_type in types:
            accounts_count = ChartOfAccounts.objects.filter(account_type=acc_type).count()
            if accounts_count == 0:
                empty_types.append(acc_type)
        
        if empty_types:
            self.stdout.write(f'\n❌ أنواع بدون حسابات ({len(empty_types)} نوع):')
            for acc_type in empty_types:
                self.stdout.write(f'  - {acc_type.name} ({acc_type.code})')
        else:
            self.stdout.write(self.style.SUCCESS('✅ جميع الأنواع لديها حسابات'))

    def suggest_accounts(self):
        """اقتراح الحسابات المطلوبة لنظام إدارة مخزون"""
        self.stdout.write(self.style.HTTP_INFO(f'\n\n💡 الحسابات المقترحة لنظام إدارة المخزون:\n'))
        
        suggestions = {
            'CASH': [
                {'code': '1010', 'name': 'الخزينة الرئيسية', 'priority': 'عالية'},
                {'code': '1011', 'name': 'خزينة الفرع', 'priority': 'متوسطة'},
            ],
            'BANK': [
                {'code': '1020', 'name': 'البنك الأهلي', 'priority': 'عالية'},
                {'code': '1021', 'name': 'بنك مصر', 'priority': 'متوسطة'},
            ],
            'INVENTORY': [
                {'code': '1030', 'name': 'مخزون البضاعة', 'priority': 'عالية'},
                {'code': '1031', 'name': 'مخزون قطع الغيار', 'priority': 'متوسطة'},
            ],
            'RECEIVABLES': [
                {'code': '1040', 'name': 'العملاء', 'priority': 'عالية'},
                {'code': '1041', 'name': 'أوراق القبض', 'priority': 'منخفضة'},
            ],
            'PAYABLES': [
                {'code': '2010', 'name': 'الموردين', 'priority': 'عالية'},
                {'code': '2011', 'name': 'أوراق الدفع', 'priority': 'منخفضة'},
            ],
            'CAPITAL': [
                {'code': '3010', 'name': 'رأس المال', 'priority': 'عالية'},
            ],
            'SALES_REVENUE': [
                {'code': '4010', 'name': 'إيرادات المبيعات', 'priority': 'عالية'},
                {'code': '4011', 'name': 'خصم مسموح به', 'priority': 'متوسطة'},
            ],
            'COGS': [
                {'code': '5010', 'name': 'تكلفة البضاعة المباعة', 'priority': 'عالية'},
            ],
            'OPERATING_EXPENSE': [
                {'code': '5020', 'name': 'مصروفات الإيجار', 'priority': 'عالية'},
                {'code': '5021', 'name': 'مصروفات الرواتب', 'priority': 'عالية'},
                {'code': '5022', 'name': 'مصروفات الكهرباء والماء', 'priority': 'متوسطة'},
                {'code': '5023', 'name': 'مصروفات الصيانة', 'priority': 'متوسطة'},
                {'code': '5024', 'name': 'مصروفات النقل', 'priority': 'متوسطة'},
            ],
        }
        
        # التحقق من الحسابات الموجودة
        for type_code, accounts in suggestions.items():
            try:
                acc_type = AccountType.objects.get(code=type_code)
                existing_accounts = ChartOfAccounts.objects.filter(account_type=acc_type)
                
                self.stdout.write(f'\n{self.get_icon(type_code)} {acc_type.name}:')
                
                for suggestion in accounts:
                    # التحقق من وجود الحساب
                    exists = ChartOfAccounts.objects.filter(code=suggestion['code']).exists()
                    
                    priority_color = {
                        'عالية': '🔴',
                        'متوسطة': '🟡',
                        'منخفضة': '🟢'
                    }.get(suggestion['priority'], '⚪')
                    
                    if exists:
                        self.stdout.write(f'  ✅ [{suggestion["code"]}] {suggestion["name"]} - موجود')
                    else:
                        self.stdout.write(
                            f'  {priority_color} [{suggestion["code"]}] {suggestion["name"]} '
                            f'- مقترح ({suggestion["priority"]} الأولوية)'
                        )
                        
            except AccountType.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'\n❌ النوع {type_code} غير موجود'))

        # ملخص التوصيات
        self.stdout.write(self.style.HTTP_INFO(f'\n\n📋 ملخص التوصيات:\n'))
        self.stdout.write('1. احذف الحسابات غير المستخدمة أو غير المناسبة')
        self.stdout.write('2. أضف الحسابات ذات الأولوية العالية (🔴) أولاً')
        self.stdout.write('3. تأكد من ربط كل حساب بنوع الحساب الصحيح')
        self.stdout.write('4. حدد الحسابات النهائية (is_leaf=True) للحسابات التي ستستخدم في القيود')
        self.stdout.write('5. حدد الحسابات البنكية والنقدية بشكل صحيح')

    def get_category_icon(self, category):
        """الحصول على أيقونة التصنيف"""
        icons = {
            'asset': '🏢',
            'liability': '📋',
            'equity': '🏛️',
            'revenue': '💵',
            'expense': '📊',
        }
        return icons.get(category, '📁')

    def get_icon(self, code):
        """الحصول على أيقونة النوع"""
        icons = {
            'CASH': '💰',
            'BANK': '🏦',
            'INVENTORY': '📦',
            'RECEIVABLES': '👥',
            'PAYABLES': '🏪',
            'CAPITAL': '💎',
            'SALES_REVENUE': '💸',
            'COGS': '📉',
            'OPERATING_EXPENSE': '🔧',
        }
        return icons.get(code, '📁')
