"""
أمر بسيط لإنشاء قيود محاسبية لاختبار تقارير أرصدة العملاء والموردين
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from datetime import datetime, timedelta
import random

from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.journal_entry import JournalEntry, JournalEntryLine, AccountingPeriod

User = get_user_model()


class Command(BaseCommand):
    help = 'إنشاء قيود محاسبية بسيطة لاختبار تقارير أرصدة العملاء والموردين'

    def add_arguments(self, parser):
        parser.add_argument(
            '--count',
            type=int,
            default=50,
            help='عدد القيود (افتراضي: 50)'
        )

    @transaction.atomic
    def handle(self, *args, **options):
        count = options['count']
        
        self.stdout.write(self.style.SUCCESS('🚀 بدء إنشاء قيود أرصدة العملاء والموردين...'))
        
        # الحصول على مستخدم
        user = User.objects.first()
        if not user:
            self.stdout.write(self.style.ERROR('❌ لا يوجد مستخدمين في النظام'))
            return
        
        # الحصول على الفترة المحاسبية
        period = AccountingPeriod.objects.filter(status='open').first()
        if not period:
            self.stdout.write(self.style.ERROR('❌ لا توجد فترة محاسبية مفتوحة'))
            return
        
        # الحصول على الحسابات
        try:
            # حسابات الأصول (سنستخدمها للذمم المدينة)
            asset_accounts = list(ChartOfAccounts.objects.filter(
                account_type__category='asset'
            )[:5])  # أول 5 حسابات
            
            # حسابات الخصوم (سنستخدمها للذمم الدائنة)
            liability_accounts = list(ChartOfAccounts.objects.filter(
                account_type__category='liability'
            )[:5])  # أول 5 حسابات
            
            if not asset_accounts:
                self.stdout.write(self.style.ERROR('❌ لا توجد حسابات أصول'))
                return
            
            self.stdout.write(self.style.SUCCESS(f'✅ وجدنا {len(asset_accounts)} حساب أصول و {len(liability_accounts)} حساب خصوم'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ خطأ في جلب الحسابات: {e}'))
            return
        
        created = 0
        today = timezone.now().date()
        
        # إنشاء قيود ذمم مدينة (مبيعات آجلة)
        for i in range(count // 2):
            try:
                # تاريخ عشوائي في آخر 120 يوم
                days_ago = random.randint(1, 120)
                entry_date = today - timedelta(days=days_ago)
                
                # مبلغ عشوائي
                amount = Decimal(random.randint(1000, 50000))
                
                # إنشاء القيد
                entry = JournalEntry.objects.create(
                    number=f'AR-TEST-{i+1:05d}',
                    date=entry_date,
                    description=f'قيد اختبار ذمم مدينة {i+1}',
                    entry_type='manual',
                    status='posted',
                    accounting_period=period,
                    created_by=user,
                    posted_by=user,
                    posted_at=timezone.now()
                )
                
                # سطر مدين (حساب أصول)
                JournalEntryLine.objects.create(
                    journal_entry=entry,
                    account=random.choice(asset_accounts),
                    description=f'ذمة مدينة - قيد اختبار {i+1}',
                    debit=amount,
                    credit=Decimal('0')
                )
                
                # سطر دائن (حساب أصول آخر للموازنة)
                other_asset = random.choice([acc for acc in asset_accounts if acc != asset_accounts[0]])
                JournalEntryLine.objects.create(
                    journal_entry=entry,
                    account=other_asset if other_asset else asset_accounts[0],
                    description=f'حساب موازن - قيد اختبار {i+1}',
                    debit=Decimal('0'),
                    credit=amount
                )
                
                created += 1
                
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'⚠️ فشل إنشاء قيد مدين: {e}'))
        
        # إنشاء قيود ذمم دائنة (إذا كانت هناك حسابات خصوم)
        if liability_accounts:
            for i in range(count // 2):
                try:
                    # تاريخ عشوائي في آخر 120 يوم
                    days_ago = random.randint(1, 120)
                    entry_date = today - timedelta(days=days_ago)
                    
                    # مبلغ عشوائي
                    amount = Decimal(random.randint(2000, 80000))
                    
                    # إنشاء القيد
                    entry = JournalEntry.objects.create(
                        number=f'AP-TEST-{i+1:05d}',
                        date=entry_date,
                        description=f'قيد اختبار ذمم دائنة {i+1}',
                        entry_type='manual',
                        status='posted',
                        accounting_period=period,
                        created_by=user,
                        posted_by=user,
                        posted_at=timezone.now()
                    )
                    
                    # سطر مدين (حساب أصول)
                    JournalEntryLine.objects.create(
                        journal_entry=entry,
                        account=random.choice(asset_accounts),
                        description=f'حساب موازن - قيد اختبار {i+1}',
                        debit=amount,
                        credit=Decimal('0')
                    )
                    
                    # سطر دائن (حساب خصوم)
                    JournalEntryLine.objects.create(
                        journal_entry=entry,
                        account=random.choice(liability_accounts),
                        description=f'ذمة دائنة - قيد اختبار {i+1}',
                        debit=Decimal('0'),
                        credit=amount
                    )
                    
                    created += 1
                    
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'⚠️ فشل إنشاء قيد دائن: {e}'))
        
        self.stdout.write(self.style.SUCCESS(
            f'✅ تم إنشاء {created} قيد محاسبي بنجاح!'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'📊 يمكنك الآن مشاهدة تقارير أعمار الذمم'
        ))
