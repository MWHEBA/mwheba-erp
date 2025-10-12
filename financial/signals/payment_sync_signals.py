"""
إشارات تزامن المدفوعات
ربط المدفوعات بين أنظمة المبيعات والمشتريات والعملاء والموردين
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import transaction
import logging

logger = logging.getLogger(__name__)

# تجنب الاستيراد الدائري
def get_payment_sync_service():
    """الحصول على خدمة تزامن المدفوعات"""
    try:
        from ..services.payment_sync_service import payment_sync_service

        return payment_sync_service
    except ImportError:
        logger.warning("خدمة تزامن المدفوعات غير متاحة")
        return None


@receiver(post_save, sender="sale.SalePayment")
def sync_sale_payment_on_save(sender, instance, created, **kwargs):
    """
    تزامن دفعة المبيعات عند الحفظ

    ملاحظة: تم تعطيل هذا Signal لتجنب القيود المكررة
    الربط المالي يتم عبر PaymentIntegrationService في Views
    """
    # تم تعطيل التزامن التلقائي
    pass


@receiver(post_save, sender="purchase.PurchasePayment")
def sync_purchase_payment_on_save(sender, instance, created, **kwargs):
    """
    تزامن دفعة المشتريات عند الحفظ

    ملاحظة: تم تعطيل هذا Signal لتجنب القيود المكررة
    الربط المالي يتم عبر PaymentIntegrationService في Views
    """
    # تم تعطيل التزامن التلقائي
    pass


@receiver(post_save, sender="client.CustomerPayment")
def sync_customer_payment_on_save(sender, instance, created, **kwargs):
    """
    تزامن دفعة العميل عند الحفظ (إذا لم تكن من التزامن التلقائي)
    """
    if created and not getattr(instance, "_synced_from_sale", False):
        try:
            sync_service = get_payment_sync_service()
            if sync_service:
                # تأجيل التزامن حتى انتهاء المعاملة
                transaction.on_commit(
                    lambda: sync_service.sync_payment(
                        payment_obj=instance,
                        operation_type="create_payment",
                        user=getattr(instance, "created_by", None),
                    )
                )
                logger.info(f"تم جدولة تزامن دفعة العميل: {instance.id}")
            else:
                logger.warning(
                    f"لا يمكن تزامن دفعة العميل {instance.id} - الخدمة غير متاحة"
                )

        except Exception as e:
            logger.error(f"خطأ في تزامن دفعة العميل {instance.id}: {str(e)}")


# تم حذف signal الخاص بـ SupplierPayment
# الدفع للموردين يتم فقط عبر فواتير المشتريات


@receiver(post_delete, sender="sale.SalePayment")
def sync_sale_payment_on_delete(sender, instance, **kwargs):
    """
    تزامن حذف دفعة المبيعات
    """
    try:
        sync_service = get_payment_sync_service()
        if sync_service:
            sync_service.sync_payment(
                payment_obj=instance, operation_type="delete_payment", user=None
            )
            logger.info(f"تم تزامن حذف دفعة المبيعات: {instance.id}")
        else:
            logger.warning(
                f"لا يمكن تزامن حذف دفعة المبيعات {instance.id} - الخدمة غير متاحة"
            )

    except Exception as e:
        logger.error(f"خطأ في تزامن حذف دفعة المبيعات {instance.id}: {str(e)}")


@receiver(post_delete, sender="purchase.PurchasePayment")
def sync_purchase_payment_on_delete(sender, instance, **kwargs):
    """
    تزامن حذف دفعة المشتريات
    """
    try:
        sync_service = get_payment_sync_service()
        if sync_service:
            sync_service.sync_payment(
                payment_obj=instance, operation_type="delete_payment", user=None
            )
            logger.info(f"تم تزامن حذف دفعة المشتريات: {instance.id}")
        else:
            logger.warning(
                f"لا يمكن تزامن حذف دفعة المشتريات {instance.id} - الخدمة غير متاحة"
            )

    except Exception as e:
        logger.error(f"خطأ في تزامن حذف دفعة المشتريات {instance.id}: {str(e)}")


# دوال مساعدة للتحقق من حالة التزامن
def check_payment_sync_status():
    """التحقق من حالة نظام تزامن المدفوعات"""
    try:
        from ..models.payment_sync import PaymentSyncOperation

        # إحصائيات التزامن
        total_operations = PaymentSyncOperation.objects.count()
        successful_operations = PaymentSyncOperation.objects.filter(
            status="completed"
        ).count()
        failed_operations = PaymentSyncOperation.objects.filter(status="failed").count()
        pending_operations = PaymentSyncOperation.objects.filter(
            status="pending"
        ).count()

        return {
            "total": total_operations,
            "successful": successful_operations,
            "failed": failed_operations,
            "pending": pending_operations,
            "success_rate": (successful_operations / total_operations * 100)
            if total_operations > 0
            else 0,
        }

    except Exception as e:
        logger.error(f"خطأ في فحص حالة تزامن المدفوعات: {str(e)}")
        return None


def force_sync_all_payments():
    """إجبار تزامن جميع المدفوعات"""
    try:
        sync_service = get_payment_sync_service()
        if not sync_service:
            return False, "خدمة التزامن غير متاحة"

        # تزامن دفعات المبيعات
        from sale.models import SalePayment

        sale_payments = SalePayment.objects.all()

        synced_count = 0
        for payment in sale_payments:
            try:
                sync_service.sync_payment(
                    payment_obj=payment,
                    operation_type="create_payment",
                    force_sync=True,
                )
                synced_count += 1
            except Exception as e:
                logger.error(f"فشل في تزامن دفعة المبيعات {payment.id}: {str(e)}")

        # تزامن دفعات المشتريات
        from purchase.models import PurchasePayment

        purchase_payments = PurchasePayment.objects.all()

        for payment in purchase_payments:
            try:
                sync_service.sync_payment(
                    payment_obj=payment,
                    operation_type="create_payment",
                    force_sync=True,
                )
                synced_count += 1
            except Exception as e:
                logger.error(f"فشل في تزامن دفعة المشتريات {payment.id}: {str(e)}")

        return True, f"تم تزامن {synced_count} دفعة"

    except Exception as e:
        logger.error(f"خطأ في التزامن القسري: {str(e)}")
        return False, str(e)
