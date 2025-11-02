# financial/management/commands/create_ledger_test_data.py
"""
إنشاء بيانات وهمية واقعية لاختبار تقرير دفتر الأستاذ
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from decimal import Decimal
from datetime import date, timedelta
import random

from financial.models import (
    ChartOfAccounts,
    AccountType,
    JournalEntry,
    JournalEntryLine,
)

User = get_user_model()


class Command(BaseCommand):
    help = 'إنشاء بيانات وهمية لاختبار تقرير دفتر الأستاذ'

    def add_arguments(self, parser):
        parser.add_argument(
            '--entries',
            type=int,
            default=50,
            help='عدد القيود المحاسبية (افتراضي: 50)'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='حذف البيانات الوهمية القديمة أولاً'
        )

    @transaction.atomic
    def handle(self, *args, **options):
        entries_count = options['entries']
        clear_old = options['clear']

        self.stdout.write(self.style.SUCCESS('🚀 بدء إنشاء البيانات الوهمية...'))

        # حذف البيانات القديمة إذا طُلب ذلك
        if clear_old:
            self.stdout.write('🗑️  حذف البيانات الوهمية القديمة...')
            JournalEntry.objects.filter(
                number__startswith='TEST-'
            ).delete()

        # الحصول على مستخدم أو إنشاء واحد
        user = self._get_or_create_user()

        # إنشاء أنواع الحسابات إذا لم تكن موجودة
        account_types = self._create_account_types()

        # إنشاء الحسابات إذا لم تكن موجودة
        accounts = self._create_accounts(account_types)

        # إنشاء القيود المحاسبية
        self._create_journal_entries(user, accounts, entries_count)

        self.stdout.write(self.style.SUCCESS('✅ تم إنشاء البيانات الوهمية بنجاح!'))
        self.stdout.write(self.style.SUCCESS(f'📊 عدد القيود: {entries_count}'))
        self.stdout.write(self.style.SUCCESS(f'📁 عدد الحسابات: {len(accounts)}'))
        self.stdout.write(self.style.WARNING('\n💡 لعرض التقرير:'))
        self.stdout.write(self.style.WARNING('   http://localhost:8000/financial/reports/ledger/'))

    def _get_or_create_user(self):
        """
        الحصول على مستخدم أو إنشاء واحد
        """
        user, created = User.objects.get_or_create(
            username='test_user',
            defaults={
                'email': 'test@example.com',
                'first_name': 'مستخدم',
                'last_name': 'اختبار'
            }
        )
        if created:
            user.set_password('test123456')
            user.save()
            self.stdout.write(self.style.SUCCESS('✅ تم إنشاء مستخدم اختبار'))
        return user

    def _create_account_types(self):
        """
        إنشاء أنواع الحسابات
        """
        self.stdout.write('📋 إنشاء أنواع الحسابات...')
        
        types_data = [
            ('1', 'أصول متداولة', 'asset', 'debit'),
            ('2', 'خصوم متداولة', 'liability', 'credit'),
            ('3', 'حقوق الملكية', 'equity', 'credit'),
            ('4', 'إيرادات', 'revenue', 'credit'),
            ('5', 'مصروفات', 'expense', 'debit'),
        ]

        account_types = {}
        for code, name, category, nature in types_data:
            acc_type, created = AccountType.objects.get_or_create(
                code=code,
                defaults={
                    'name': name,
                    'category': category,
                    'nature': nature
                }
            )
            account_types[category] = acc_type
            if created:
                self.stdout.write(f'  ✅ {name}')

        return account_types

    def _create_accounts(self, account_types):
        """
        إنشاء الحسابات
        """
        self.stdout.write('💰 إنشاء الحسابات...')

        accounts_data = [
            # أصول
            ('1001', 'الخزينة', 'asset'),
            ('1002', 'البنك - الأهلي', 'asset'),
            ('1003', 'البنك - مصر', 'asset'),
            ('1101', 'العملاء', 'asset'),
            ('1102', 'أوراق القبض', 'asset'),
            ('1201', 'المخزون', 'asset'),
            
            # خصوم
            ('2101', 'الموردين', 'liability'),
            ('2102', 'أوراق الدفع', 'liability'),
            ('2201', 'قروض قصيرة الأجل', 'liability'),
            
            # حقوق ملكية
            ('3001', 'رأس المال', 'equity'),
            ('3101', 'الأرباح المحتجزة', 'equity'),
            
            # إيرادات
            ('4001', 'إيرادات المبيعات', 'revenue'),
            ('4002', 'إيرادات الخدمات', 'revenue'),
            ('4101', 'إيرادات أخرى', 'revenue'),
            
            # مصروفات
            ('5001', 'مصروف الرواتب', 'expense'),
            ('5002', 'مصروف الإيجار', 'expense'),
            ('5003', 'مصروف الكهرباء', 'expense'),
            ('5004', 'مصروف المياه', 'expense'),
            ('5005', 'مصروف الصيانة', 'expense'),
            ('5101', 'مصروفات إدارية', 'expense'),
            ('5201', 'مصروفات تسويق', 'expense'),
        ]

        accounts = {}
        for code, name, category in accounts_data:
            account, created = ChartOfAccounts.objects.get_or_create(
                code=code,
                defaults={
                    'name': name,
                    'account_type': account_types[category],
                    'is_leaf': True,
                    'is_active': True
                }
            )
            accounts[code] = account
            if created:
                self.stdout.write(f'  ✅ {code} - {name}')

        return accounts

    def _create_journal_entries(self, user, accounts, count):
        """
        إنشاء القيود المحاسبية
        """
        self.stdout.write(f'📝 إنشاء {count} قيد محاسبي...')

        # سيناريوهات واقعية
        scenarios = [
            # مبيعات نقدية
            {
                'description': 'مبيعات نقدية',
                'lines': [
                    ('1001', 'debit', (1000, 5000)),
                    ('4001', 'credit', (1000, 5000)),
                ]
            },
            # مبيعات آجلة
            {
                'description': 'مبيعات آجلة',
                'lines': [
                    ('1101', 'debit', (2000, 10000)),
                    ('4001', 'credit', (2000, 10000)),
                ]
            },
            # تحصيل من عملاء
            {
                'description': 'تحصيل من عملاء',
                'lines': [
                    ('1001', 'debit', (1000, 8000)),
                    ('1101', 'credit', (1000, 8000)),
                ]
            },
            # إيداع بنكي
            {
                'description': 'إيداع في البنك',
                'lines': [
                    ('1002', 'debit', (5000, 20000)),
                    ('1001', 'credit', (5000, 20000)),
                ]
            },
            # مشتريات نقدية
            {
                'description': 'مشتريات نقدية',
                'lines': [
                    ('1201', 'debit', (3000, 15000)),
                    ('1001', 'credit', (3000, 15000)),
                ]
            },
            # مشتريات آجلة
            {
                'description': 'مشتريات آجلة',
                'lines': [
                    ('1201', 'debit', (5000, 20000)),
                    ('2101', 'credit', (5000, 20000)),
                ]
            },
            # سداد للموردين
            {
                'description': 'سداد للموردين',
                'lines': [
                    ('2101', 'debit', (2000, 10000)),
                    ('1001', 'credit', (2000, 10000)),
                ]
            },
            # دفع رواتب
            {
                'description': 'دفع رواتب الموظفين',
                'lines': [
                    ('5001', 'debit', (10000, 30000)),
                    ('1001', 'credit', (10000, 30000)),
                ]
            },
            # دفع إيجار
            {
                'description': 'دفع إيجار المقر',
                'lines': [
                    ('5002', 'debit', (5000, 15000)),
                    ('1001', 'credit', (5000, 15000)),
                ]
            },
            # مصروفات متنوعة
            {
                'description': 'مصروفات كهرباء ومياه',
                'lines': [
                    ('5003', 'debit', (500, 2000)),
                    ('5004', 'debit', (300, 1000)),
                    ('1001', 'credit', (800, 3000)),
                ]
            },
            # إيرادات خدمات
            {
                'description': 'إيرادات خدمات',
                'lines': [
                    ('1001', 'debit', (1000, 5000)),
                    ('4002', 'credit', (1000, 5000)),
                ]
            },
            # سحب من البنك
            {
                'description': 'سحب من البنك',
                'lines': [
                    ('1001', 'debit', (5000, 15000)),
                    ('1002', 'credit', (5000, 15000)),
                ]
            },
        ]

        # تاريخ البداية (قبل 3 أشهر)
        start_date = date.today() - timedelta(days=90)

        created_count = 0
        for i in range(count):
            # اختيار سيناريو عشوائي
            scenario = random.choice(scenarios)

            # تاريخ عشوائي
            days_offset = random.randint(0, 90)
            entry_date = start_date + timedelta(days=days_offset)

            # إنشاء القيد
            entry = JournalEntry.objects.create(
                number=f'TEST-{i+1:04d}',
                date=entry_date,
                description=scenario['description'],
                status='posted',  # 90% مرحلة
                created_by=user
            )

            # إنشاء البنود
            total_debit = Decimal('0')
            total_credit = Decimal('0')

            for line_data in scenario['lines']:
                account_code, side, amount_range = line_data
                amount = Decimal(str(random.randint(*amount_range)))

                if side == 'debit':
                    JournalEntryLine.objects.create(
                        journal_entry=entry,
                        account=accounts[account_code],
                        debit=amount,
                        credit=Decimal('0'),
                        description=scenario['description']
                    )
                    total_debit += amount
                else:
                    JournalEntryLine.objects.create(
                        journal_entry=entry,
                        account=accounts[account_code],
                        debit=Decimal('0'),
                        credit=amount,
                        description=scenario['description']
                    )
                    total_credit += amount

            # موازنة القيد إذا لزم الأمر
            if total_debit != total_credit:
                diff = total_debit - total_credit
                if diff > 0:
                    # نحتاج دائن إضافي
                    lines = entry.lines.filter(credit__gt=0)
                    if lines.exists():
                        line = lines.first()
                        line.credit += diff
                        line.save()
                else:
                    # نحتاج مدين إضافي
                    lines = entry.lines.filter(debit__gt=0)
                    if lines.exists():
                        line = lines.first()
                        line.debit += abs(diff)
                        line.save()

            created_count += 1
            if created_count % 10 == 0:
                self.stdout.write(f'  ✅ تم إنشاء {created_count} قيد...')

        # إنشاء بعض القيود كمسودات (10%)
        draft_count = max(1, count // 10)
        self.stdout.write(f'📝 إنشاء {draft_count} قيد مسودة...')

        for i in range(draft_count):
            scenario = random.choice(scenarios)
            entry_date = start_date + timedelta(days=random.randint(0, 90))

            entry = JournalEntry.objects.create(
                number=f'TEST-DRAFT-{i+1:04d}',
                date=entry_date,
                description=f'{scenario["description"]} (مسودة)',
                status='draft',
                created_by=user
            )

            for line_data in scenario['lines']:
                account_code, side, amount_range = line_data
                amount = Decimal(str(random.randint(*amount_range)))

                if side == 'debit':
                    JournalEntryLine.objects.create(
                        journal_entry=entry,
                        account=accounts[account_code],
                        debit=amount,
                        credit=Decimal('0'),
                        description=scenario['description']
                    )
                else:
                    JournalEntryLine.objects.create(
                        journal_entry=entry,
                        account=accounts[account_code],
                        debit=Decimal('0'),
                        credit=amount,
                        description=scenario['description']
                    )

        self.stdout.write(self.style.SUCCESS(f'✅ تم إنشاء {created_count} قيد مرحل'))
        self.stdout.write(self.style.SUCCESS(f'✅ تم إنشاء {draft_count} قيد مسودة'))
