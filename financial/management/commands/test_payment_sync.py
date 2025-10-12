"""
أمر Django لاختبار نظام تزامن المدفوعات
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
User = get_user_model()
from django.utils import timezone
from decimal import Decimal
import random


class Command(BaseCommand):
    help = 'اختبار نظام تزامن المدفوعات'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--mode',
            type=str,
            choices=['check', 'test-sync', 'enable', 'disable'],
            default='check',
            help='وضع التشغيل'
        )
    
    def handle(self, *args, **options):
        mode = options['mode']
        
        if mode == 'check':
            self.check_system()
        elif mode == 'test-sync':
            self.test_sync()
        elif mode == 'enable':
            self.enable_sync()
        elif mode == 'disable':
            self.disable_sync()
    
    def check_system(self):
        """فحص حالة النظام"""
        self.stdout.write(self.style.SUCCESS('=== فحص نظام تزامن المدفوعات ==='))
        
        try:
            from financial.models.payment_sync import PaymentSyncRule, PaymentSyncOperation
            from financial.services.payment_sync_service import PaymentSyncService
            
            # فحص القواعد
            total_rules = PaymentSyncRule.objects.count()
            active_rules = PaymentSyncRule.objects.filter(is_active=True).count()
            
            self.stdout.write(f'إجمالي القواعد: {total_rules}')
            self.stdout.write(f'القواعد النشطة: {active_rules}')
            
            # فحص العمليات
            total_operations = PaymentSyncOperation.objects.count()
            self.stdout.write(f'إجمالي العمليات: {total_operations}')
            
            # فحص الخدمة
            service = PaymentSyncService()
            stats = service.get_sync_statistics()
            self.stdout.write(f'معدل النجاح: {stats.get("success_rate", 0)}%')
            
            # فحص النماذج المطلوبة
            self.check_required_models()
            
        except ImportError as e:
            self.stdout.write(
                self.style.ERROR(f'خطأ في استيراد النماذج: {e}')
            )
    
    def check_required_models(self):
        """فحص النماذج المطلوبة"""
        self.stdout.write('\n--- فحص النماذج المطلوبة ---')
        
        # فحص CustomerPayment
        try:
            from client.models.payment import CustomerPayment
            self.stdout.write(self.style.SUCCESS('✓ CustomerPayment متاح'))
        except ImportError:
            self.stdout.write(self.style.ERROR('✗ CustomerPayment غير متاح'))
        
        # فحص SupplierPayment
        try:
            from supplier.models.payment import SupplierPayment
            self.stdout.write(self.style.SUCCESS('✓ SupplierPayment متاح'))
        except ImportError:
            self.stdout.write(self.style.ERROR('✗ SupplierPayment غير متاح'))
        
        # فحص SalePayment
        try:
            from sale.models import SalePayment
            self.stdout.write(self.style.SUCCESS('✓ SalePayment متاح'))
        except ImportError:
            self.stdout.write(self.style.ERROR('✗ SalePayment غير متاح'))
        
        # فحص PurchasePayment
        try:
            from purchase.models import PurchasePayment
            self.stdout.write(self.style.SUCCESS('✓ PurchasePayment متاح'))
        except ImportError:
            self.stdout.write(self.style.ERROR('✗ PurchasePayment غير متاح'))
    
    
    def test_sync(self):
        """اختبار عملية التزامن"""
        self.stdout.write(self.style.SUCCESS('=== اختبار التزامن ==='))
        
        try:
            from financial.services.payment_sync_service import PaymentSyncService
            
            service = PaymentSyncService()
            
            # محاولة تزامن وهمي
            self.stdout.write('اختبار خدمة التزامن...')
            
            # فحص الإحصائيات
            stats = service.get_sync_statistics()
            self.stdout.write(f'إجمالي العمليات: {stats.get("total_operations", 0)}')
            self.stdout.write(f'العمليات المكتملة: {stats.get("completed_operations", 0)}')
            self.stdout.write(f'العمليات الفاشلة: {stats.get("failed_operations", 0)}')
            self.stdout.write(f'معدل النجاح: {stats.get("success_rate", 0)}%')
            
            self.stdout.write(self.style.SUCCESS('اختبار التزامن مكتمل'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'خطأ في اختبار التزامن: {e}'))
    
    def enable_sync(self):
        """تفعيل نظام التزامن"""
        try:
            from financial.models.payment_sync import PaymentSyncRule
            
            rules_updated = PaymentSyncRule.objects.filter(is_active=False).update(is_active=True)
            self.stdout.write(
                self.style.SUCCESS(f'تم تفعيل {rules_updated} قاعدة تزامن')
            )
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'خطأ في التفعيل: {e}'))
    
    def disable_sync(self):
        """تعطيل نظام التزامن"""
        try:
            from financial.models.payment_sync import PaymentSyncRule
            
            rules_updated = PaymentSyncRule.objects.filter(is_active=True).update(is_active=False)
            self.stdout.write(
                self.style.WARNING(f'تم تعطيل {rules_updated} قاعدة تزامن')
            )
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'خطأ في التعطيل: {e}'))
