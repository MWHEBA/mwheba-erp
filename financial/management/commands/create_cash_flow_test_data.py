# financial/management/commands/create_cash_flow_test_data.py
"""
أمر لإنشاء بيانات وهمية لاختبار تقرير التدفقات النقدية
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from datetime import datetime, timedelta
import random

from financial.models import (
    ChartOfAccounts,
    AccountType,
    JournalEntry,
    JournalEntryLine,
    AccountingPeriod,
)

User = get_user_model()


class Command(BaseCommand):
    help = 'إنشاء بيانات وهمية لاختبار تقرير التدفقات النقدية'

    def add_arguments(self, parser):
        parser.add_argument(
            '--entries',
            type=int,
            default=30,
            help='عدد القيود المراد إنشاؤها (افتراضي: 30)'
        )

    @transaction.atomic
    def handle(self, *args, **options):
        entries_count = options['entries']
        
        self.stdout.write(self.style.SUCCESS('🚀 بدء إنشاء بيانات التدفقات النقدية...'))
        
        # الحصول على مستخدم
        user = User.objects.first()
        if not user:
            self.stdout.write(self.style.ERROR('❌ لا يوجد مستخدمين في النظام'))
            return
        
        # الحصول على أو إنشاء الفترة المحاسبية
        current_year = timezone.now().year
        period, created = AccountingPeriod.objects.get_or_create(
            name=f'السنة المالية {current_year}',
            defaults={
                'start_date': datetime(current_year, 1, 1).date(),
                'end_date': datetime(current_year, 12, 31).date(),
                'is_active': True,
                'is_closed': False,
            }
        )
        
        # إنشاء أو الحصول على الحسابات
        accounts = self._create_accounts()
        
        # إنشاء قيود التدفقات النقدية
        created_entries = self._create_cash_flow_entries(
            accounts, 
            user, 
            period, 
            entries_count
        )
        
        self.stdout.write(self.style.SUCCESS(
            f'✅ تم إنشاء {created_entries} قيد للتدفقات النقدية بنجاح!'
        ))
    
    def _create_accounts(self):
        """إنشاء أو الحصول على الحسابات المطلوبة"""
        
        # أنواع الحسابات - استخدام filter().first() بدلاً من get_or_create لتجنب تضارب الأكواد
        asset_type = AccountType.objects.filter(category='asset').first()
        if not asset_type:
            asset_type = AccountType.objects.create(
                name='أصول متداولة',
                category='asset',
                code='101'
            )
        
        revenue_type = AccountType.objects.filter(category='revenue').first()
        if not revenue_type:
            revenue_type = AccountType.objects.create(
                name='إيرادات',
                category='revenue',
                code='401'
            )
        
        expense_type = AccountType.objects.filter(category='expense').first()
        if not expense_type:
            expense_type = AccountType.objects.create(
                name='مصروفات',
                category='expense',
                code='501'
            )
        
        equity_type = AccountType.objects.filter(category='equity').first()
        if not equity_type:
            equity_type = AccountType.objects.create(
                name='حقوق ملكية',
                category='equity',
                code='301'
            )
        
        # الحسابات النقدية
        cash_account, _ = ChartOfAccounts.objects.get_or_create(
            code='1010',
            defaults={
                'name': 'الخزينة',
                'account_type': asset_type,
                'is_active': True,
                'is_leaf': True,
            }
        )
        
        bank_account, _ = ChartOfAccounts.objects.get_or_create(
            code='1020',
            defaults={
                'name': 'البنك',
                'account_type': asset_type,
                'is_active': True,
                'is_leaf': True,
            }
        )
        
        # حسابات الإيرادات
        sales_revenue, _ = ChartOfAccounts.objects.get_or_create(
            code='4010',
            defaults={
                'name': 'إيرادات المبيعات',
                'account_type': revenue_type,
                'is_active': True,
                'is_leaf': True,
            }
        )
        
        service_revenue, _ = ChartOfAccounts.objects.get_or_create(
            code='4020',
            defaults={
                'name': 'إيرادات الخدمات',
                'account_type': revenue_type,
                'is_active': True,
                'is_leaf': True,
            }
        )
        
        # حسابات المصروفات
        salaries_expense, _ = ChartOfAccounts.objects.get_or_create(
            code='5010',
            defaults={
                'name': 'مصروفات الرواتب',
                'account_type': expense_type,
                'is_active': True,
                'is_leaf': True,
            }
        )
        
        rent_expense, _ = ChartOfAccounts.objects.get_or_create(
            code='5020',
            defaults={
                'name': 'مصروفات الإيجار',
                'account_type': expense_type,
                'is_active': True,
                'is_leaf': True,
            }
        )
        
        utilities_expense, _ = ChartOfAccounts.objects.get_or_create(
            code='5030',
            defaults={
                'name': 'مصروفات الكهرباء والماء',
                'account_type': expense_type,
                'is_active': True,
                'is_leaf': True,
            }
        )
        
        # حسابات الأصول الثابتة
        equipment_account, _ = ChartOfAccounts.objects.get_or_create(
            code='1510',
            defaults={
                'name': 'معدات',
                'account_type': asset_type,
                'is_active': True,
                'is_leaf': True,
            }
        )
        
        # حسابات حقوق الملكية
        capital_account, _ = ChartOfAccounts.objects.get_or_create(
            code='3010',
            defaults={
                'name': 'رأس المال',
                'account_type': equity_type,
                'is_active': True,
                'is_leaf': True,
            }
        )
        
        loan_account, _ = ChartOfAccounts.objects.get_or_create(
            code='2510',
            defaults={
                'name': 'قروض طويلة الأجل',
                'account_type': equity_type,
                'is_active': True,
                'is_leaf': True,
            }
        )
        
        return {
            'cash': cash_account,
            'bank': bank_account,
            'sales_revenue': sales_revenue,
            'service_revenue': service_revenue,
            'salaries_expense': salaries_expense,
            'rent_expense': rent_expense,
            'utilities_expense': utilities_expense,
            'equipment': equipment_account,
            'capital': capital_account,
            'loan': loan_account,
        }
    
    def _create_cash_flow_entries(self, accounts, user, period, count):
        """إنشاء قيود التدفقات النقدية"""
        
        created = 0
        today = timezone.now().date()
        
        # قيود الأنشطة التشغيلية (60%)
        operating_count = int(count * 0.6)
        for i in range(operating_count):
            date = today - timedelta(days=random.randint(1, 90))
            
            # إيرادات نقدية
            if random.choice([True, False]):
                amount = Decimal(random.randint(5000, 50000))
                entry = JournalEntry.objects.create(
                    date=date,
                    description=f'إيراد نقدي - {random.choice(["مبيعات", "خدمات"])}',
                    status='posted',
                    created_by=user,
                    accounting_period=period,
                )
                
                # مدين: الخزينة/البنك
                JournalEntryLine.objects.create(
                    journal_entry=entry,
                    account=random.choice([accounts['cash'], accounts['bank']]),
                    debit=amount,
                    credit=Decimal('0'),
                )
                
                # دائن: إيرادات
                JournalEntryLine.objects.create(
                    journal_entry=entry,
                    account=random.choice([accounts['sales_revenue'], accounts['service_revenue']]),
                    debit=Decimal('0'),
                    credit=amount,
                )
                created += 1
            
            # مصروفات نقدية
            else:
                amount = Decimal(random.randint(2000, 20000))
                entry = JournalEntry.objects.create(
                    date=date,
                    description=f'مصروف نقدي - {random.choice(["رواتب", "إيجار", "كهرباء"])}',
                    status='posted',
                    created_by=user,
                    accounting_period=period,
                )
                
                # مدين: مصروفات
                JournalEntryLine.objects.create(
                    journal_entry=entry,
                    account=random.choice([
                        accounts['salaries_expense'], 
                        accounts['rent_expense'],
                        accounts['utilities_expense']
                    ]),
                    debit=amount,
                    credit=Decimal('0'),
                )
                
                # دائن: الخزينة/البنك
                JournalEntryLine.objects.create(
                    journal_entry=entry,
                    account=random.choice([accounts['cash'], accounts['bank']]),
                    debit=Decimal('0'),
                    credit=amount,
                )
                created += 1
        
        # قيود الأنشطة الاستثمارية (20%)
        investing_count = int(count * 0.2)
        for i in range(investing_count):
            date = today - timedelta(days=random.randint(1, 90))
            
            # شراء أصول
            if random.choice([True, False]):
                amount = Decimal(random.randint(10000, 100000))
                entry = JournalEntry.objects.create(
                    date=date,
                    description='شراء معدات',
                    status='posted',
                    created_by=user,
                    accounting_period=period,
                )
                
                # مدين: معدات
                JournalEntryLine.objects.create(
                    journal_entry=entry,
                    account=accounts['equipment'],
                    debit=amount,
                    credit=Decimal('0'),
                )
                
                # دائن: البنك
                JournalEntryLine.objects.create(
                    journal_entry=entry,
                    account=accounts['bank'],
                    debit=Decimal('0'),
                    credit=amount,
                )
                created += 1
            
            # بيع أصول
            else:
                amount = Decimal(random.randint(5000, 50000))
                entry = JournalEntry.objects.create(
                    date=date,
                    description='بيع معدات',
                    status='posted',
                    created_by=user,
                    accounting_period=period,
                )
                
                # مدين: البنك
                JournalEntryLine.objects.create(
                    journal_entry=entry,
                    account=accounts['bank'],
                    debit=amount,
                    credit=Decimal('0'),
                )
                
                # دائن: معدات
                JournalEntryLine.objects.create(
                    journal_entry=entry,
                    account=accounts['equipment'],
                    debit=Decimal('0'),
                    credit=amount,
                )
                created += 1
        
        # قيود الأنشطة التمويلية (20%)
        financing_count = int(count * 0.2)
        for i in range(financing_count):
            date = today - timedelta(days=random.randint(1, 90))
            
            # الحصول على تمويل
            if random.choice([True, False]):
                amount = Decimal(random.randint(50000, 200000))
                entry = JournalEntry.objects.create(
                    date=date,
                    description=f'الحصول على {random.choice(["قرض", "زيادة رأس المال"])}',
                    status='posted',
                    created_by=user,
                    accounting_period=period,
                )
                
                # مدين: البنك
                JournalEntryLine.objects.create(
                    journal_entry=entry,
                    account=accounts['bank'],
                    debit=amount,
                    credit=Decimal('0'),
                )
                
                # دائن: قرض/رأس المال
                JournalEntryLine.objects.create(
                    journal_entry=entry,
                    account=random.choice([accounts['loan'], accounts['capital']]),
                    debit=Decimal('0'),
                    credit=amount,
                )
                created += 1
            
            # سداد تمويل
            else:
                amount = Decimal(random.randint(10000, 50000))
                entry = JournalEntry.objects.create(
                    date=date,
                    description='سداد قرض',
                    status='posted',
                    created_by=user,
                    accounting_period=period,
                )
                
                # مدين: قرض
                JournalEntryLine.objects.create(
                    journal_entry=entry,
                    account=accounts['loan'],
                    debit=amount,
                    credit=Decimal('0'),
                )
                
                # دائن: البنك
                JournalEntryLine.objects.create(
                    journal_entry=entry,
                    account=accounts['bank'],
                    debit=Decimal('0'),
                    credit=amount,
                )
                created += 1
        
        return created
