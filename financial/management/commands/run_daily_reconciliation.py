"""
أمر إدارة لتشغيل المطابقة اليومية للبيانات المالية
Management command to run daily financial data reconciliation
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import datetime, date, timedelta
from financial.services.data_reconciliation_service import DataReconciliationService
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'تشغيل المطابقة اليومية للبيانات المالية'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            help='تاريخ المطابقة (YYYY-MM-DD) - افتراضي: أمس'
        )
        
        parser.add_argument(
            '--types',
            type=str,
            nargs='+',
            choices=DataReconciliationService.RECONCILIATION_TYPES,
            help='أنواع المطابقة المطلوبة'
        )
        
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='عرض تفاصيل مفصلة'
        )
        
        parser.add_argument(
            '--force',
            action='store_true',
            help='تشغيل المطابقة حتى لو تم تشغيلها مسبقاً لنفس التاريخ'
        )
    
    def handle(self, *args, **options):
        """تنفيذ أمر المطابقة اليومية"""
        
        # تحديد تاريخ المطابقة
        if options['date']:
            try:
                reconciliation_date = datetime.strptime(options['date'], '%Y-%m-%d').date()
            except ValueError:
                raise CommandError('تنسيق التاريخ غير صحيح. استخدم YYYY-MM-DD')
        else:
            # افتراضي: أمس
            reconciliation_date = (timezone.now() - timedelta(days=1)).date()
        
        # تحديد أنواع المطابقة
        reconciliation_types = options.get('types') or DataReconciliationService.RECONCILIATION_TYPES
        
        self.stdout.write(
            self.style.SUCCESS(
                f'🔄 بدء المطابقة اليومية لتاريخ: {reconciliation_date}'
            )
        )
        
        if options['verbose']:
            self.stdout.write(f'أنواع المطابقة: {", ".join(reconciliation_types)}')
        
        try:
            # فحص إذا كانت المطابقة تمت مسبقاً
            if not options['force']:
                existing_report = DataReconciliationService.get_reconciliation_report(reconciliation_date)
                if existing_report:
                    self.stdout.write(
                        self.style.WARNING(
                            f'⚠️ المطابقة تمت مسبقاً لتاريخ {reconciliation_date}. '
                            f'استخدم --force للتشغيل مرة أخرى.'
                        )
                    )
                    self._display_existing_results(existing_report, options['verbose'])
                    return
            
            # تشغيل المطابقة
            results = DataReconciliationService.run_daily_reconciliation(
                reconciliation_date=reconciliation_date,
                reconciliation_types=reconciliation_types
            )
            
            # عرض النتائج
            self._display_results(results, options['verbose'])
            
            # تحديد رمز الخروج حسب النتيجة
            if results['status'] == 'passed':
                self.stdout.write(
                    self.style.SUCCESS('✅ المطابقة اليومية اكتملت بنجاح')
                )
            elif results['status'] == 'warning':
                self.stdout.write(
                    self.style.WARNING('⚠️ المطابقة اليومية اكتملت مع تحذيرات')
                )
            elif results['status'] == 'failed':
                self.stdout.write(
                    self.style.ERROR('❌ المطابقة اليومية فشلت')
                )
                raise CommandError('فشلت المطابقة اليومية')
            else:
                self.stdout.write(
                    self.style.ERROR('💥 خطأ في المطابقة اليومية')
                )
                raise CommandError(f'خطأ في المطابقة: {results.get("error", "خطأ غير معروف")}')
                
        except Exception as e:
            logger.error(f'خطأ في تشغيل المطابقة اليومية: {e}')
            raise CommandError(f'خطأ في تشغيل المطابقة: {str(e)}')
    
    def _display_results(self, results, verbose=False):
        """عرض نتائج المطابقة"""
        
        # الملخص العام
        summary = results['summary']
        self.stdout.write('\n📊 ملخص المطابقة:')
        self.stdout.write(f'   إجمالي الفحوصات: {summary["total_checks"]}')
        self.stdout.write(f'   الفحوصات الناجحة: {summary["passed_checks"]} ✅')
        
        if summary['failed_checks'] > 0:
            self.stdout.write(
                self.style.ERROR(f'   الفحوصات الفاشلة: {summary["failed_checks"]} ❌')
            )
        
        if summary['warnings'] > 0:
            self.stdout.write(
                self.style.WARNING(f'   التحذيرات: {summary["warnings"]} ⚠️')
            )
        
        # التناقضات
        if results['discrepancies']:
            self.stdout.write(f'\n🔍 التناقضات المكتشفة ({len(results["discrepancies"])}):\n')
            
            for i, discrepancy in enumerate(results['discrepancies'], 1):
                severity_icon = {
                    'critical': '🔴',
                    'high': '🟠', 
                    'medium': '🟡',
                    'low': '🟢'
                }.get(discrepancy.get('severity', 'medium'), '⚪')
                
                self.stdout.write(
                    f'{i}. {severity_icon} {discrepancy["description"]}'
                )
                
                if verbose and discrepancy.get('details'):
                    for key, value in discrepancy['details'].items():
                        self.stdout.write(f'     {key}: {value}')
                    self.stdout.write('')
        
        # تفاصيل كل نوع مطابقة
        if verbose:
            self.stdout.write('\n📋 تفاصيل المطابقة:\n')
            
            for reconciliation_type, result in results['results'].items():
                self.stdout.write(f'🔸 {reconciliation_type}:')
                self.stdout.write(f'   الفحوصات: {result["total_checks"]}')
                self.stdout.write(f'   النجح: {result["passed_checks"]}')
                self.stdout.write(f'   الفشل: {result["failed_checks"]}')
                self.stdout.write(f'   التحذيرات: {result["warnings"]}')
                
                if result.get('details'):
                    for key, value in result['details'].items():
                        self.stdout.write(f'   {key}: {value}')
                
                self.stdout.write('')
    
    def _display_existing_results(self, results, verbose=False):
        """عرض نتائج موجودة مسبقاً"""
        self.stdout.write('\n📋 نتائج المطابقة الموجودة:')
        self._display_results(results, verbose)