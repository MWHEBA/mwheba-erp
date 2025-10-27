"""
فحص فاتورة محددة
"""
from django.core.management.base import BaseCommand
from sale.models import Sale


class Command(BaseCommand):
    help = 'فحص فاتورة محددة'

    def add_arguments(self, parser):
        parser.add_argument('sale_number', type=str, help='رقم الفاتورة')

    def handle(self, *args, **options):
        sale_number = options['sale_number']
        
        try:
            sale = Sale.objects.get(number=sale_number)
            
            self.stdout.write(self.style.SUCCESS(f'\n{"="*80}'))
            self.stdout.write(self.style.SUCCESS(f'🔍 فحص الفاتورة {sale.number}'))
            self.stdout.write(self.style.SUCCESS(f'{"="*80}\n'))
            
            self.stdout.write(f'التاريخ: {sale.date}')
            self.stdout.write(f'الحالة: {sale.status}')
            self.stdout.write(f'الإجمالي: {sale.total} ج.م')
            self.stdout.write(f'وقت الإنشاء: {sale.created_at}')
            
            if sale.journal_entry:
                self.stdout.write(f'\n✅ القيد المحاسبي: {sale.journal_entry.number}')
                self.stdout.write(f'عدد البنود: {sale.journal_entry.lines.count()}')
                
                self.stdout.write('\nالبنود:')
                for line in sale.journal_entry.lines.all():
                    self.stdout.write(
                        f'  {line.account.code} - {line.account.name}: '
                        f'مدين={line.debit}, دائن={line.credit}'
                    )
                
                # التحقق من وجود COGS
                cogs_line = sale.journal_entry.lines.filter(account__code='51010').first()
                if cogs_line:
                    self.stdout.write(self.style.SUCCESS(f'\n✅ قيد COGS موجود: {cogs_line.debit} ج.م'))
                else:
                    self.stdout.write(self.style.ERROR('\n❌ قيد COGS مفقود!'))
            else:
                self.stdout.write(self.style.ERROR('\n❌ لا يوجد قيد محاسبي!'))
            
            # حساب التكلفة المتوقعة
            from financial.services.accounting_integration_service import AccountingIntegrationService
            total_cost = AccountingIntegrationService._calculate_sale_cost(sale)
            self.stdout.write(f'\nالتكلفة المحسوبة: {total_cost} ج.م')
            
            self.stdout.write('\nالمنتجات:')
            for item in sale.items.all():
                cost = item.product.cost_price or 0
                self.stdout.write(
                    f'  - {item.product.name}: '
                    f'الكمية={item.quantity}, '
                    f'السعر={item.unit_price}, '
                    f'التكلفة={cost}'
                )
            
            self.stdout.write(self.style.SUCCESS(f'\n{"="*80}\n'))
            
        except Sale.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'❌ الفاتورة {sale_number} غير موجودة'))
