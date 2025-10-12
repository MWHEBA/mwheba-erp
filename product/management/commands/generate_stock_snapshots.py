"""
أمر Django لإنشاء لقطات المخزون اليومية
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime, timedelta
from product.services.inventory_service import InventoryService
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'إنشاء لقطات المخزون اليومية'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            help='التاريخ المراد إنشاء لقطة له (YYYY-MM-DD). افتراضي: أمس'
        )
        parser.add_argument(
            '--days',
            type=int,
            default=1,
            help='عدد الأيام السابقة لإنشاء لقطات لها'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='إعادة إنشاء اللقطات الموجودة'
        )

    def handle(self, *args, **options):
        date_str = options['date']
        days = options['days']
        force = options['force']
        
        if date_str:
            try:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                self.stdout.write(
                    self.style.ERROR('تنسيق التاريخ غير صحيح. استخدم YYYY-MM-DD')
                )
                return
        else:
            # افتراضي: أمس
            target_date = (timezone.now() - timedelta(days=1)).date()
        
        self.stdout.write(
            self.style.SUCCESS(f'بدء إنشاء لقطات المخزون')
        )
        
        total_snapshots = 0
        
        # إنشاء لقطات للأيام المطلوبة
        for i in range(days):
            current_date = target_date - timedelta(days=i)
            
            self.stdout.write(f'إنشاء لقطات ليوم {current_date}...')
            
            try:
                snapshots_count = InventoryService.generate_daily_snapshots(current_date)
                total_snapshots += snapshots_count
                
                if snapshots_count > 0:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✅ تم إنشاء {snapshots_count} لقطة ليوم {current_date}'
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f'⚠️ لا توجد لقطات جديدة ليوم {current_date}'
                        )
                    )
                    
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ خطأ في إنشاء لقطات يوم {current_date}: {e}')
                )
                logger.error(f"خطأ في إنشاء لقطات المخزون ليوم {current_date}: {e}")
                continue
        
        # ملخص النتائج
        self.stdout.write(
            self.style.SUCCESS(
                f'\n🎉 تم الانتهاء من إنشاء لقطات المخزون'
                f'\n📊 إجمالي اللقطات المُنشأة: {total_snapshots}'
                f'\n📅 عدد الأيام المعالجة: {days}'
                f'\n⏰ وقت الانتهاء: {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}'
            )
        )
        
        if total_snapshots == 0:
            self.stdout.write(
                self.style.WARNING(
                    '\n💡 نصيحة: تأكد من وجود منتجات ومستودعات نشطة في النظام'
                )
            )
