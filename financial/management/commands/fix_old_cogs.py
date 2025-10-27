"""
إصلاح قيود COGS للفواتير القديمة
"""
from django.core.management.base import BaseCommand
from sale.models import Sale
from financial.models import JournalEntryLine
from financial.services.accounting_integration_service import AccountingIntegrationService
from decimal import Decimal


class Command(BaseCommand):
    help = 'إصلاح قيود COGS للفواتير القديمة'

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='إصلاح جميع الفواتير (بدلاً من SALE0001 و SALE0002 فقط)',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\n' + '='*80))
        self.stdout.write(self.style.SUCCESS('🔧 إصلاح قيود COGS للفواتير القديمة'))
        self.stdout.write(self.style.SUCCESS('='*80 + '\n'))

        # الحصول على الحسابات المطلوبة
        accounts = AccountingIntegrationService._get_required_accounts_for_sale()
        if not accounts:
            self.stdout.write(self.style.ERROR('❌ الحسابات المطلوبة غير موجودة'))
            return

        # تحديد الفواتير المستهدفة
        if options['all']:
            sales = Sale.objects.filter(
                status='confirmed',
                journal_entry__isnull=False
            ).order_by('created_at')
            self.stdout.write(f'🔍 فحص جميع الفواتير المؤكدة ({sales.count()} فاتورة)...\n')
        else:
            sales = Sale.objects.filter(
                number__in=['SALE0001', 'SALE0002'],
                status='confirmed',
                journal_entry__isnull=False
            )
            self.stdout.write(f'🔍 فحص الفواتير المحددة (SALE0001, SALE0002)...\n')

        fixed_count = 0
        skipped_exists = 0
        skipped_zero = 0

        for sale in sales:
            # التحقق من عدم وجود قيد COGS
            cogs_exists = sale.journal_entry.lines.filter(
                account__code='51010'
            ).exists()

            if cogs_exists:
                self.stdout.write(f'⏭️  {sale.number}: قيد COGS موجود بالفعل')
                skipped_exists += 1
                continue

            # حساب التكلفة
            total_cost = AccountingIntegrationService._calculate_sale_cost(sale)

            if total_cost > 0:
                # إضافة قيد COGS
                JournalEntryLine.objects.create(
                    journal_entry=sale.journal_entry,
                    account=accounts["cost_of_goods_sold"],
                    debit=total_cost,
                    credit=Decimal("0.00"),
                    description=f"تكلفة البضاعة المباعة - فاتورة {sale.number}",
                )

                JournalEntryLine.objects.create(
                    journal_entry=sale.journal_entry,
                    account=accounts["inventory"],
                    debit=Decimal("0.00"),
                    credit=total_cost,
                    description=f"تخفيض المخزون - فاتورة {sale.number}",
                )

                self.stdout.write(
                    self.style.SUCCESS(
                        f'✅ {sale.number}: تم إضافة قيد COGS - التكلفة: {total_cost} ج.م'
                    )
                )
                fixed_count += 1
            else:
                self.stdout.write(
                    self.style.WARNING(f'⚠️  {sale.number}: التكلفة = 0 (تم التخطي)')
                )
                skipped_zero += 1

        # الإحصائيات
        self.stdout.write('\n' + '-'*80)
        self.stdout.write(self.style.SUCCESS(f'✅ تم إصلاح {fixed_count} فاتورة'))
        self.stdout.write(f'⏭️  تم تخطي {skipped_exists} فاتورة (قيد COGS موجود)')
        self.stdout.write(f'⚠️  تم تخطي {skipped_zero} فاتورة (التكلفة = 0)')

        self.stdout.write(self.style.SUCCESS('\n' + '='*80))
        self.stdout.write(self.style.SUCCESS('✅ انتهى الإصلاح'))
        self.stdout.write(self.style.SUCCESS('='*80 + '\n'))
