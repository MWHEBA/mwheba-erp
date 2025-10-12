"""
Signals للعملاء
"""
import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings

from .models import Customer

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Customer)
def create_customer_account_signal(sender, instance, created, **kwargs):
    """
    إنشاء حساب محاسبي تلقائياً عند إضافة عميل جديد
    """
    # التحقق من تفعيل الميزة في الإعدادات
    if not getattr(settings, "AUTO_CREATE_CUSTOMER_ACCOUNTS", True):
        return

    # فقط للعملاء الجدد الذين ليس لديهم حساب
    if created and not instance.financial_account:
        try:
            from financial.services.supplier_customer_account_service import (
                SupplierCustomerAccountService,
            )

            account = SupplierCustomerAccountService.create_customer_account(
                instance, user=instance.created_by
            )
            logger.info(
                f"✅ تم إنشاء حساب محاسبي {account.code} للعميل {instance.name} تلقائياً"
            )
        except Exception as e:
            # نسجل الخطأ لكن لا نوقف العملية
            logger.error(f"❌ فشل إنشاء حساب تلقائي للعميل {instance.name}: {e}")


@receiver(post_delete, sender=Customer)
def delete_customer_account_signal(sender, instance, **kwargs):
    """
    حذف الحساب المحاسبي عند حذف العميل (اختياري)
    """
    if instance.financial_account:
        try:
            account_code = instance.financial_account.code
            instance.financial_account.delete()
            logger.info(f"تم حذف الحساب المحاسبي {account_code} للعميل {instance.name}")
        except Exception as e:
            logger.error(f"فشل حذف الحساب المحاسبي للعميل {instance.name}: {e}")
