"""
أمر تشخيص شامل لقيود COGS
"""
from django.core.management.base import BaseCommand
from sale.models import Sale
from financial.models import JournalEntry, JournalEntryLine
from financial.services.accounting_integration_service import AccountingIntegrationService
from decimal import Decimal


class Command(BaseCommand):
    help = 'تشخيص شامل لقيود تكلفة البضاعة المباعة'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\n' + '='*80))
        self.stdout.write(self.style.SUCCESS('🔍 تشخيص شامل لقيود COGS'))
        self.stdout.write(self.style.SUCCESS('='*80 + '\n'))

        # 1. فحص الحسابات المطلوبة
        self.stdout.write(self.style.WARNING('📊 الخطوة 1: فحص الحسابات المحاسبية'))
        self.stdout.write('-' * 80)
        
        accounts = AccountingIntegrationService._get_required_accounts_for_sale()
        if accounts:
            self.stdout.write(self.style.SUCCESS('✅ جميع الحسابات المطلوبة موجودة:'))
            for key, account in accounts.items():
                self.stdout.write(f'   - {key}: {account.code} - {account.name}')
        else:
            self.stdout.write(self.style.ERROR('❌ بعض الحسابات المطلوبة مفقودة!'))
            return

        # 2. فحص الفواتير المؤكدة
        self.stdout.write(self.style.WARNING('\n📊 الخطوة 2: فحص الفواتير المؤكدة'))
        self.stdout.write('-' * 80)
        
        confirmed_sales = Sale.objects.filter(status='confirmed').order_by('-created_at')[:10]
        self.stdout.write(f'عدد الفواتير المؤكدة (آخر 10): {confirmed_sales.count()}\n')

        for sale in confirmed_sales:
            self.stdout.write(f'\n🔹 فاتورة {sale.number}:')
            self.stdout.write(f'   التاريخ: {sale.date}')
            self.stdout.write(f'   الإجمالي: {sale.total} ج.م')
            
            # فحص القيد المحاسبي
            if sale.journal_entry:
                self.stdout.write(f'   ✅ القيد المحاسبي: {sale.journal_entry.number}')
                
                # فحص بنود القيد
                lines = sale.journal_entry.lines.all()
                self.stdout.write(f'   عدد البنود: {lines.count()}')
                
                # البحث عن قيد COGS
                cogs_line = lines.filter(account__code='51010').first()
                inventory_line = lines.filter(account__code='11051').first()
                
                if cogs_line and inventory_line:
                    self.stdout.write(self.style.SUCCESS(f'   ✅ قيد COGS موجود: {cogs_line.debit} ج.م'))
                else:
                    self.stdout.write(self.style.ERROR('   ❌ قيد COGS مفقود!'))
                    
                    # حساب التكلفة المتوقعة
                    total_cost = AccountingIntegrationService._calculate_sale_cost(sale)
                    self.stdout.write(f'   التكلفة المحسوبة: {total_cost} ج.م')
                    
                    # فحص المنتجات
                    self.stdout.write('   المنتجات:')
                    for item in sale.items.all():
                        cost = item.product.cost_price or 0
                        self.stdout.write(
                            f'      - {item.product.name}: '
                            f'الكمية={item.quantity}, '
                            f'السعر={item.unit_price}, '
                            f'التكلفة={cost}'
                        )
                        if cost == 0:
                            self.stdout.write(self.style.ERROR('        ⚠️ التكلفة = 0!'))
                
                # عرض جميع البنود
                self.stdout.write('   البنود المحاسبية:')
                for line in lines:
                    self.stdout.write(
                        f'      {line.account.code} - {line.account.name}: '
                        f'مدين={line.debit}, دائن={line.credit}'
                    )
            else:
                self.stdout.write(self.style.ERROR('   ❌ لا يوجد قيد محاسبي!'))

        # 3. الإحصائيات
        self.stdout.write(self.style.WARNING('\n📊 الخطوة 3: الإحصائيات'))
        self.stdout.write('-' * 80)
        
        total_sales = Sale.objects.filter(status='confirmed').count()
        sales_with_journal = Sale.objects.filter(
            status='confirmed',
            journal_entry__isnull=False
        ).count()
        
        # عدد القيود التي تحتوي على COGS
        sales_with_cogs = 0
        for sale in Sale.objects.filter(status='confirmed', journal_entry__isnull=False):
            if sale.journal_entry.lines.filter(account__code='51010').exists():
                sales_with_cogs += 1
        
        self.stdout.write(f'إجمالي الفواتير المؤكدة: {total_sales}')
        self.stdout.write(f'الفواتير بقيود محاسبية: {sales_with_journal}')
        self.stdout.write(f'الفواتير بقيود COGS: {sales_with_cogs}')
        self.stdout.write(f'الفواتير بدون قيود COGS: {sales_with_journal - sales_with_cogs}')
        
        # 4. التوصيات
        self.stdout.write(self.style.WARNING('\n💡 التوصيات'))
        self.stdout.write('-' * 80)
        
        if sales_with_journal - sales_with_cogs > 0:
            self.stdout.write(self.style.ERROR(
                f'⚠️ هناك {sales_with_journal - sales_with_cogs} فاتورة بدون قيود COGS!'
            ))
            self.stdout.write('الأسباب المحتملة:')
            self.stdout.write('  1. المنتجات ليس لها سعر تكلفة (cost_price = 0)')
            self.stdout.write('  2. الحسابات المحاسبية مفقودة (51010 أو 11051)')
            self.stdout.write('  3. خطأ في دالة _calculate_sale_cost()')
        else:
            self.stdout.write(self.style.SUCCESS('✅ جميع الفواتير تحتوي على قيود COGS!'))

        self.stdout.write(self.style.SUCCESS('\n' + '='*80))
        self.stdout.write(self.style.SUCCESS('✅ انتهى التشخيص'))
        self.stdout.write(self.style.SUCCESS('='*80 + '\n'))
