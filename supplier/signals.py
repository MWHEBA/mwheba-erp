"""
Signals للموردين
"""
import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings

from .models import Supplier

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Supplier)
def create_supplier_account_signal(sender, instance, created, **kwargs):
    """
    إنشاء حساب محاسبي تلقائياً عند إضافة مورد جديد
    """
    # التحقق من تفعيل الميزة في الإعدادات
    if not getattr(settings, 'AUTO_CREATE_SUPPLIER_ACCOUNTS', True):
        return
    
    # فقط للموردين الجدد الذين ليس لديهم حساب
    if created and not instance.financial_account:
        try:
            from financial.services.supplier_customer_account_service import SupplierCustomerAccountService
            account = SupplierCustomerAccountService.create_supplier_account(
                instance,
                user=instance.created_by
            )
            logger.info(f"✅ تم إنشاء حساب محاسبي {account.code} للمورد {instance.name} تلقائياً")
        except Exception as e:
            # نسجل الخطأ لكن لا نوقف العملية
            logger.error(f"❌ فشل إنشاء حساب تلقائي للمورد {instance.name}: {e}")


@receiver(post_delete, sender=Supplier)
def delete_supplier_account_signal(sender, instance, **kwargs):
    """
    حذف الحساب المحاسبي عند حذف المورد (اختياري)
    """
    if instance.financial_account:
        try:
            account_code = instance.financial_account.code
            instance.financial_account.delete()
            logger.info(f"تم حذف الحساب المحاسبي {account_code} للمورد {instance.name}")
        except Exception as e:
            logger.error(f"فشل حذف الحساب المحاسبي للمورد {instance.name}: {e}")
