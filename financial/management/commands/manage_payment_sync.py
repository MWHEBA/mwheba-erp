"""
أمر Django لإدارة العمليات الفاشلة في نظام تزامن المدفوعات
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta


class Command(BaseCommand):
    help = 'إدارة العمليات الفاشلة في نظام تزامن المدفوعات'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--action',
            type=str,
            choices=['list-failed', 'list-pending', 'retry-failed', 'resolve-errors', 'reset-all'],
            default='list-failed',
            help='الإجراء المطلوب'
        )
        
        parser.add_argument(
            '--operation-id',
            type=int,
            help='معرف العملية المحددة'
        )
    
    def handle(self, *args, **options):
        action = options['action']
        operation_id = options.get('operation_id')
        
        if action == 'list-failed':
            self.list_failed_operations()
        elif action == 'list-pending':
            self.list_pending_operations()
        elif action == 'retry-failed':
            self.retry_failed_operations(operation_id)
        elif action == 'resolve-errors':
            self.resolve_errors()
        elif action == 'reset-all':
            self.reset_all_data()
    
    def list_failed_operations(self):
        """عرض العمليات الفاشلة"""
        try:
            from financial.models.payment_sync import PaymentSyncOperation, PaymentSyncError
            
            self.stdout.write(self.style.ERROR('=== العمليات الفاشلة ==='))
            
            failed_ops = PaymentSyncOperation.objects.filter(status='failed').order_by('-created_at')
            
            if not failed_ops.exists():
                self.stdout.write(self.style.SUCCESS('لا توجد عمليات فاشلة'))
                return
            
            for op in failed_ops:
                self.stdout.write(f'\n--- العملية #{op.id} ---')
                self.stdout.write(f'النوع: {op.operation_type}')
                self.stdout.write(f'الحالة: {op.status}')
                self.stdout.write(f'تاريخ الإنشاء: {op.created_at}')
                self.stdout.write(f'المحاولات: {op.retry_count}/{op.max_retries}')
                
                # عرض الأخطاء المرتبطة
                errors = PaymentSyncError.objects.filter(sync_operation=op)
                if errors.exists():
                    self.stdout.write('الأخطاء:')
                    for error in errors:
                        status = '✓ محلول' if error.is_resolved else '✗ غير محلول'
                        self.stdout.write(f'  - {error.error_type}: {error.error_message[:80]}... [{status}]')
                
                # اقتراح الحل
                self.suggest_solution(op)
        
        except ImportError:
            self.stdout.write(self.style.ERROR('نماذج التزامن غير متاحة'))
    
    def list_pending_operations(self):
        """عرض العمليات المعلقة"""
        try:
            from financial.models.payment_sync import PaymentSyncOperation
            
            self.stdout.write(self.style.WARNING('=== العمليات المعلقة ==='))
            
            # العمليات في حالة انتظار
            pending_ops = PaymentSyncOperation.objects.filter(status='pending').order_by('-created_at')
            
            # العمليات قيد المعالجة
            processing_ops = PaymentSyncOperation.objects.filter(status='processing').order_by('-created_at')
            
            if not pending_ops.exists() and not processing_ops.exists():
                self.stdout.write(self.style.SUCCESS('لا توجد عمليات معلقة'))
                return
            
            # عرض العمليات المعلقة
            if pending_ops.exists():
                self.stdout.write(f'\n--- العمليات في الانتظار ({pending_ops.count()}) ---')
                for op in pending_ops:
                    self.stdout.write(f'العملية #{op.id}: {op.operation_type}')
                    self.stdout.write(f'  تاريخ الإنشاء: {op.created_at}')
                    self.stdout.write(f'  المحاولات: {op.retry_count}/{op.max_retries}')
                    
                    # حساب الوقت المنقضي
                    from django.utils import timezone
                    elapsed = timezone.now() - op.created_at
                    self.stdout.write(f'  منذ: {elapsed}')
                    
                    # تحديد ما إذا كانت معلقة طويلاً
                    if elapsed.total_seconds() > 300:  # أكثر من 5 دقائق
                        self.stdout.write(self.style.ERROR('  ⚠️ معلقة لفترة طويلة - قد تحتاج تدخل'))
                    else:
                        self.stdout.write(self.style.SUCCESS('  ⏳ في الانتظار الطبيعي'))
            
            # عرض العمليات قيد المعالجة
            if processing_ops.exists():
                self.stdout.write(f'\n--- العمليات قيد المعالجة ({processing_ops.count()}) ---')
                for op in processing_ops:
                    self.stdout.write(f'العملية #{op.id}: {op.operation_type}')
                    self.stdout.write(f'  بدأت في: {op.started_at}')
                    
                    # حساب وقت المعالجة
                    if op.started_at:
                        from django.utils import timezone
                        processing_time = timezone.now() - op.started_at
                        self.stdout.write(f'  وقت المعالجة: {processing_time}')
                        
                        if processing_time.total_seconds() > 600:  # أكثر من 10 دقائق
                            self.stdout.write(self.style.ERROR('  ⚠️ معالجة طويلة - قد تكون معلقة'))
                        else:
                            self.stdout.write(self.style.SUCCESS('  🔄 قيد المعالجة'))
            
            # نصائح للمستخدم
            self.stdout.write('\n--- نصائح ---')
            self.stdout.write('• العمليات "pending" تنتظر المعالجة')
            self.stdout.write('• العمليات "processing" قيد التنفيذ حالياً')
            self.stdout.write('• إذا كانت العملية معلقة أكثر من 10 دقائق، قد تحتاج إعادة تشغيل')
            
        except ImportError:
            self.stdout.write(self.style.ERROR('نماذج التزامن غير متاحة'))
    
    def suggest_solution(self, operation):
        """اقتراح حل للعملية الفاشلة"""
        if operation.operation_type == 'test_payment':
            self.stdout.write(self.style.WARNING('  💡 الحل: هذه عملية اختبار، يمكن حذفها'))
        elif 'import' in str(operation.payment_data).lower():
            self.stdout.write(self.style.WARNING('  💡 الحل: مشكلة في استيراد النماذج، تحقق من التكامل'))
        elif operation.retry_count >= operation.max_retries:
            self.stdout.write(self.style.WARNING('  💡 الحل: تم استنفاد المحاولات، يحتاج تدخل يدوي'))
        else:
            self.stdout.write(self.style.WARNING('  💡 الحل: يمكن إعادة المحاولة'))
    
    def retry_failed_operations(self, operation_id=None):
        """إعادة محاولة العمليات الفاشلة"""
        try:
            from financial.models.payment_sync import PaymentSyncOperation
            from financial.services.payment_sync_service import PaymentSyncService
            
            if operation_id:
                operations = PaymentSyncOperation.objects.filter(id=operation_id, status='failed')
                if not operations.exists():
                    self.stdout.write(self.style.ERROR(f'العملية #{operation_id} غير موجودة أو ليست فاشلة'))
                    return
            else:
                operations = PaymentSyncOperation.objects.filter(
                    status='failed',
                    retry_count__lt=models.F('max_retries')
                )
            
            if not operations.exists():
                self.stdout.write(self.style.WARNING('لا توجد عمليات قابلة لإعادة المحاولة'))
                return
            
            service = PaymentSyncService()
            success_count = 0
            
            for operation in operations:
                self.stdout.write(f'إعادة محاولة العملية #{operation.id}...')
                
                try:
                    # إعادة تعيين الحالة
                    operation.status = 'pending'
                    operation.retry_count += 1
                    operation.save()
                    
                    # محاولة التزامن مرة أخرى
                    # ملاحظة: هذا يحتاج تطوير دالة retry في الخدمة
                    self.stdout.write(self.style.SUCCESS(f'  ✓ تم إعادة تعيين العملية #{operation.id}'))
                    success_count += 1
                    
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'  ✗ فشل في العملية #{operation.id}: {e}'))
            
            self.stdout.write(self.style.SUCCESS(f'تم إعادة تعيين {success_count} عملية'))
            
        except ImportError:
            self.stdout.write(self.style.ERROR('خدمة التزامن غير متاحة'))
    
    def resolve_errors(self):
        """وضع علامة حل على الأخطاء القديمة"""
        try:
            from financial.models.payment_sync import PaymentSyncError
            
            # حل الأخطاء المتعلقة بالاستيراد (تم إصلاحها)
            import_errors = PaymentSyncError.objects.filter(
                error_message__icontains='import',
                is_resolved=False
            )
            
            resolved_count = import_errors.update(
                is_resolved=True,
                resolved_at=timezone.now(),
                resolution_notes='تم إنشاء النماذج المفقودة'
            )
            
            self.stdout.write(self.style.SUCCESS(f'تم حل {resolved_count} خطأ استيراد'))
            
            # حل الأخطاء القديمة (أكثر من 7 أيام)
            old_errors = PaymentSyncError.objects.filter(
                occurred_at__lt=timezone.now() - timedelta(days=7),
                is_resolved=False
            )
            
            old_resolved = old_errors.update(
                is_resolved=True,
                resolved_at=timezone.now(),
                resolution_notes='حل تلقائي للأخطاء القديمة'
            )
            
            self.stdout.write(self.style.SUCCESS(f'تم حل {old_resolved} خطأ قديم'))
            
        except ImportError:
            self.stdout.write(self.style.ERROR('نماذج الأخطاء غير متاحة'))
    
    
    def reset_all_data(self):
        """إعادة تعيين جميع البيانات (خطير!)"""
        confirm = input('هل أنت متأكد من حذف جميع بيانات التزامن؟ (yes/no): ')
        
        if confirm.lower() != 'yes':
            self.stdout.write(self.style.WARNING('تم إلغاء العملية'))
            return
        
        try:
            from financial.models.payment_sync import (
                PaymentSyncOperation, PaymentSyncLog, PaymentSyncError
            )
            
            # حذف جميع البيانات
            log_count = PaymentSyncLog.objects.count()
            error_count = PaymentSyncError.objects.count()
            operation_count = PaymentSyncOperation.objects.count()
            
            PaymentSyncLog.objects.all().delete()
            PaymentSyncError.objects.all().delete()
            PaymentSyncOperation.objects.all().delete()
            
            self.stdout.write(self.style.SUCCESS(f'تم حذف:'))
            self.stdout.write(f'  - {operation_count} عملية')
            self.stdout.write(f'  - {log_count} سجل')
            self.stdout.write(f'  - {error_count} خطأ')
            
        except ImportError:
            self.stdout.write(self.style.ERROR('نماذج التزامن غير متاحة'))
