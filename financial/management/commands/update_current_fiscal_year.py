"""
Management command لتحديث السنة المالية الحالية تلقائياً
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from financial.models import AccountingPeriod


class Command(BaseCommand):
    help = 'تحديث علامة السنة المالية الحالية بناءً على التاريخ الحالي'

    def add_arguments(self, parser):
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='عرض تفاصيل إضافية',
        )

    def handle(self, *args, **options):
        verbose = options.get('verbose', False)
        
        self.stdout.write(self.style.WARNING('=' * 70))
        self.stdout.write(self.style.WARNING('تحديث السنة المالية الحالية'))
        self.stdout.write(self.style.WARNING('=' * 70))
        
        try:
            # تحديث العلامة
            updated_count, current_period = AccountingPeriod.update_current_period_flag()
            
            if current_period:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✓ تم تحديث السنة المالية الحالية: {current_period.fiscal_year} - {current_period.name}'
                    )
                )
                
                if verbose:
                    self.stdout.write(f'  • من: {current_period.start_date}')
                    self.stdout.write(f'  • إلى: {current_period.end_date}')
                    self.stdout.write(f'  • الحالة: {current_period.get_status_display()}')
                    self.stdout.write(f'  • نسبة التقدم: {current_period.progress_percentage}%')
                    self.stdout.write(f'  • الأيام المتبقية: {current_period.remaining_days} يوم')
            else:
                self.stdout.write(
                    self.style.WARNING(
                        '⚠ لا توجد سنة مالية مفتوحة تحتوي على التاريخ الحالي'
                    )
                )
                self.stdout.write(
                    self.style.WARNING(
                        f'  التاريخ الحالي: {timezone.now().date()}'
                    )
                )
                
                # عرض السنوات المتاحة
                if verbose:
                    self.stdout.write('\nالسنوات المالية المتاحة:')
                    periods = AccountingPeriod.objects.all().order_by('start_date')
                    for period in periods:
                        status_icon = '✓' if period.status == 'open' else '✗'
                        self.stdout.write(
                            f'  {status_icon} {period.fiscal_year}: '
                            f'{period.start_date} → {period.end_date} '
                            f'({period.get_status_display()})'
                        )
            
            self.stdout.write(self.style.WARNING('=' * 70))
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'✗ حدث خطأ أثناء التحديث: {str(e)}')
            )
            raise
