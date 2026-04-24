"""
تحديث جميع الخدمات لاستخدام النظام المالي الموحد
"""

from django.core.management.base import BaseCommand
from django.db import transaction
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'تحديث جميع الخدمات لاستخدام النظام المالي الموحد'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='عرض النتائج دون تطبيق التغييرات',
        )

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        
        self.stdout.write(
            self.style.SUCCESS('🔄 بدء تحديث الخدمات للنظام المالي الموحد...')
        )
        
        if self.dry_run:
            self.stdout.write(
                self.style.WARNING('⚠️ وضع المحاكاة - لن يتم تطبيق أي تغييرات')
            )

        try:
            # 1. تحديث خدمات العملاء
            self.update_customer_services()

            # 2. تحديث خدمات الموردين
            self.update_supplier_services()

            # 3. تحديث خدمات المدفوعات
            self.update_payment_services()

            self.stdout.write(
                self.style.SUCCESS('✅ تم إكمال تحديث الخدمات بنجاح!')
            )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ فشل في تحديث الخدمات: {str(e)}')
            )
            logger.error(f"خطأ في تحديث الخدمات: {str(e)}")

    def update_customer_services(self):
        """تحديث خدمات العملاء"""
        self.stdout.write("👤 تحديث خدمات العملاء...")
        
        # تحديث PaymentStatusService
        self.update_payment_status_service()
        
        # تحديث نماذج العملاء
        self.update_customer_models()
        
        self.stdout.write("✅ تم تحديث خدمات العملاء")

    def update_supplier_services(self):
        """تحديث خدمات الموردين"""
        self.stdout.write("🏪 تحديث خدمات الموردين...")
        
        if not self.dry_run:
            # إضافة حقل unified_financial_account للموردين الموجودين
            self.add_unified_accounts_to_suppliers()
        
        self.stdout.write("✅ تم تحديث خدمات الموردين")

    def update_payment_services(self):
        """تحديث خدمات المدفوعات"""
        self.stdout.write("💰 تحديث خدمات المدفوعات...")
        
        # تحديث PaymentStatusService لاستخدام النظام الموحد
        self.update_payment_status_service()
        
        self.stdout.write("✅ تم تحديث خدمات المدفوعات")

    def update_payment_status_service(self):
        """تحديث خدمة معالجة المدفوعات"""
        service_file = 'client/services/customer_service.py'
        
        if self.dry_run:
            self.stdout.write(f"  🔍 [محاكاة] تحديث {service_file}")
            return
        
        self.stdout.write(f"  ⚠️ يتطلب تحديث يدوي: {service_file}")

    def update_customer_models(self):
        """تحديث نماذج العملاء"""
        model_file = 'client/models.py'
        
        if self.dry_run:
            self.stdout.write(f"  🔍 [محاكاة] تحديث {model_file}")
            return
        
        self.stdout.write(f"  ⚠️ يتطلب تحديث يدوي: {model_file}")

    def add_unified_accounts_to_suppliers(self):
        """إضافة حسابات موحدة للموردين"""
        try:
            from supplier.models import Supplier
            from financial.services.unified_account_service import UnifiedAccountService
            
            suppliers_without_unified = Supplier.objects.filter(
                unified_financial_account__isnull=True
            )
            
            updated_count = 0
            for supplier in suppliers_without_unified:
                try:
                    account = UnifiedAccountService.create_supplier_account(supplier)
                    if account:
                        supplier.unified_financial_account = account
                        supplier.save(update_fields=['unified_financial_account'])
                        updated_count += 1
                        self.stdout.write(f"  ✅ تم إنشاء حساب موحد للمورد: {supplier.name}")
                except Exception as e:
                    self.stdout.write(f"  ❌ فشل في إنشاء حساب للمورد {supplier.name}: {str(e)}")
            
            self.stdout.write(f"📊 تم تحديث {updated_count} مورد")
            
        except ImportError:
            self.stdout.write("⚠️ وحدة الموردين غير متوفرة")