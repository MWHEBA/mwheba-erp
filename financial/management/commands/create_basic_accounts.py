from django.core.management.base import BaseCommand
from django.db import transaction
from financial.models import AccountType, ChartOfAccounts


class Command(BaseCommand):
    help = 'إنشاء الحسابات الأساسية للنظام المالي'

    def handle(self, *args, **options):
        self.stdout.write('بدء إنشاء الحسابات الأساسية...')
        
        with transaction.atomic():
            # إنشاء أنواع الحسابات الأساسية
            asset_type, _ = AccountType.objects.get_or_create(
                name="الأصول",
                defaults={
                    'nature': 'debit',
                    'code': '1',
                    'description': 'حسابات الأصول'
                }
            )
            
            liability_type, _ = AccountType.objects.get_or_create(
                name="الخصوم",
                defaults={
                    'nature': 'credit',
                    'code': '2',
                    'description': 'حسابات الخصوم'
                }
            )
            
            equity_type, _ = AccountType.objects.get_or_create(
                name="حقوق الملكية",
                defaults={
                    'nature': 'credit',
                    'code': '3',
                    'description': 'حسابات حقوق الملكية'
                }
            )
            
            revenue_type, _ = AccountType.objects.get_or_create(
                name="الإيرادات",
                defaults={
                    'nature': 'credit',
                    'code': '4',
                    'description': 'حسابات الإيرادات'
                }
            )
            
            expense_type, _ = AccountType.objects.get_or_create(
                name="المصروفات",
                defaults={
                    'nature': 'debit',
                    'code': '5',
                    'description': 'حسابات المصروفات'
                }
            )

            # إنشاء الحسابات الأساسية
            accounts_data = [
                # حسابات نقدية
                {
                    'name': 'الصندوق',
                    'code': '1001',
                    'account_type': asset_type,
                    'is_cash_account': True,
                    'is_leaf': True,
                },
                {
                    'name': 'البنك الأهلي المصري',
                    'code': '1002',
                    'account_type': asset_type,
                    'is_bank_account': True,
                    'is_leaf': True,
                },
                {
                    'name': 'بنك مصر',
                    'code': '1003',
                    'account_type': asset_type,
                    'is_bank_account': True,
                    'is_leaf': True,
                },
                
                # حسابات المصروفات
                {
                    'name': 'مصروفات عامة',
                    'code': '5001',
                    'account_type': expense_type,
                    'is_leaf': True,
                },
                {
                    'name': 'مصروفات إدارية',
                    'code': '5002',
                    'account_type': expense_type,
                    'is_leaf': True,
                },
                {
                    'name': 'مصروفات تشغيلية',
                    'code': '5003',
                    'account_type': expense_type,
                    'is_leaf': True,
                },
                {
                    'name': 'مصروفات صيانة',
                    'code': '5004',
                    'account_type': expense_type,
                    'is_leaf': True,
                },
                
                # حسابات الإيرادات
                {
                    'name': 'إيرادات المبيعات',
                    'code': '4001',
                    'account_type': revenue_type,
                    'is_leaf': True,
                },
                {
                    'name': 'إيرادات الخدمات',
                    'code': '4002',
                    'account_type': revenue_type,
                    'is_leaf': True,
                },
                {
                    'name': 'إيرادات أخرى',
                    'code': '4003',
                    'account_type': revenue_type,
                    'is_leaf': True,
                },
            ]

            created_count = 0
            for account_data in accounts_data:
                account, created = ChartOfAccounts.objects.get_or_create(
                    code=account_data['code'],
                    defaults=account_data
                )
                if created:
                    created_count += 1
                    self.stdout.write(f'تم إنشاء الحساب: {account.name} ({account.code})')
                else:
                    self.stdout.write(f'الحساب موجود بالفعل: {account.name} ({account.code})')

            self.stdout.write(
                self.style.SUCCESS(
                    f'تم الانتهاء! تم إنشاء {created_count} حساب جديد.'
                )
            )
