"""
Django Signals محسنة لتزامن المدفوعات
"""
from django.db.models.signals import post_save, post_delete, pre_delete
from django.dispatch import receiver
from django.db import transaction
from django.core.exceptions import ValidationError
import logging

logger = logging.getLogger(__name__)

from ..services.payment_sync_service import payment_sync_service

# إضافة الخدمة الجديدة
try:
    from ..services.payment_integration_service import payment_integration_service

    INTEGRATION_SERVICE_AVAILABLE = True
except ImportError:
    INTEGRATION_SERVICE_AVAILABLE = False
    logger.warning("خدمة التكامل المالي غير متاحة في الـ Signals")


class PaymentSignalHandler:
    """
    معالج إشارات المدفوعات المحسن
    """

    @staticmethod
    def handle_payment_created(sender, instance, created, **kwargs):
        """
        معالجة إنشاء دفعة جديدة
        """
        if not created:
            return

        # التحقق من نوع الكائن
        if not hasattr(instance, "id"):
            logger.debug(
                f"تم تخطي Signal لكائن غير صالح في handle_payment_created: {type(instance).__name__}"
            )
            return

        try:
            # تأجيل التزامن حتى انتهاء المعاملة الحالية
            transaction.on_commit(
                lambda: PaymentSignalHandler._sync_payment_async(
                    instance, "create_payment"
                )
            )
        except Exception as e:
            logger.error(
                f"خطأ في معالجة إنشاء الدفعة {getattr(instance, 'id', 'unknown')}: {str(e)}"
            )

    @staticmethod
    def handle_payment_updated(sender, instance, created, **kwargs):
        """
        معالجة تحديث دفعة موجودة
        """
        if created:
            return

        # التحقق من نوع الكائن
        if not hasattr(instance, "id"):
            logger.debug(
                f"تم تخطي Signal لكائن غير صالح في handle_payment_updated: {type(instance).__name__}"
            )
            return

        try:
            # التحقق من تغيير الحقول المهمة
            if PaymentSignalHandler._has_significant_changes(instance):
                transaction.on_commit(
                    lambda: PaymentSignalHandler._sync_payment_async(
                        instance, "update_payment"
                    )
                )
        except Exception as e:
            logger.error(
                f"خطأ في معالجة تحديث الدفعة {getattr(instance, 'id', 'unknown')}: {str(e)}"
            )

    @staticmethod
    def handle_payment_deleted(sender, instance, **kwargs):
        """
        معالجة حذف دفعة
        """
        # التحقق من نوع الكائن
        if not hasattr(instance, "id"):
            logger.debug(
                f"تم تخطي Signal لكائن غير صالح في handle_payment_deleted: {type(instance).__name__}"
            )
            return

        try:
            # تسجيل حذف الدفعة
            logger.info(f"تم حذف الدفعة {instance.id} من {sender.__name__}")

            # يمكن إضافة منطق إضافي هنا إذا لزم الأمر
            # مثل تنظيف القيود المحاسبية المرتبطة

        except Exception as e:
            logger.error(
                f"خطأ في معالجة حذف الدفعة {getattr(instance, 'id', 'unknown')}: {str(e)}"
            )

    @staticmethod
    def _sync_payment_async(instance, operation_type):
        """
        تزامن الدفعة بشكل غير متزامن - محدث للخدمة الجديدة

        ملاحظة هامة: تم تعطيل هذا Signal لأن الربط المالي يتم في Views مباشرة
        الـ View يستخدم PaymentIntegrationService ويعالج جميع الحالات
        تشغيل هذا Signal سيسبب قيود مكررة!
        """
        # التحقق من نوع الكائن قبل محاولة الوصول للـ id
        if not hasattr(instance, "id"):
            logger.debug(f"تم تخطي Signal لكائن غير صالح: {type(instance).__name__}")
            return

        # التحقق من أن الكائن هو دفعة وليس كائن آخر
        payment_model_names = [
            "SalePayment",
            "PurchasePayment",
            "CustomerPayment",
            "SupplierPayment",
        ]
        if type(instance).__name__ not in payment_model_names:
            logger.debug(f"تم تخطي Signal لكائن ليس دفعة: {type(instance).__name__}")
            return

        # تم تعطيل التزامن التلقائي - الربط يتم في Views فقط
        logger.debug(f"تم تخطي Signal للدفعة {instance.id} - الربط يتم في View")
        pass

        # الكود القديم (معطل):
        # try:
        #     # تحديد نوع الدفعة
        #     payment_type = PaymentSignalHandler._get_payment_type(instance)
        #
        #     # استخدام الخدمة الجديدة إذا كانت متاحة
        #     if INTEGRATION_SERVICE_AVAILABLE and hasattr(instance, 'financial_account') and instance.financial_account:
        #         try:
        #             integration_result = payment_integration_service.process_payment(
        #                 payment=instance,
        #                 payment_type=payment_type,
        #                 user=getattr(instance, 'created_by', None)
        #             )
        #
        #             if integration_result['success']:
        #                 logger.info(f"تم ربط الدفعة {instance.id} بالنظام المالي عبر الـ Signal")
        #             else:
        #                 logger.warning(f"فشل في ربط الدفعة {instance.id} عبر الـ Signal: {integration_result.get('message')}")
        #
        #         except Exception as e:
        #             logger.error(f"خطأ في خدمة التكامل المالي للدفعة {instance.id}: {str(e)}")
        #             # التراجع للطريقة القديمة
        #             PaymentSignalHandler._fallback_to_old_sync(instance, operation_type, payment_type)
        #     else:
        #         # استخدام الطريقة القديمة
        #         PaymentSignalHandler._fallback_to_old_sync(instance, operation_type, payment_type)
        #
        # except Exception as e:
        #     logger.error(f"خطأ في التزامن غير المتزامن للدفعة {instance.id}: {str(e)}")

    @staticmethod
    def _fallback_to_old_sync(instance, operation_type, payment_type):
        """
        التراجع للطريقة القديمة في التزامن

        ملاحظة: تم تعطيل الطريقة القديمة لأنها تسبب مشاكل في إنشاء القيود
        الخدمة الجديدة PaymentIntegrationService هي الوحيدة المستخدمة الآن
        """
        # تم تعطيل الطريقة القديمة - لا نريد قيود مكررة أو أخطاء
        logger.info(f"تم تخطي التزامن القديم للدفعة {instance.id} - الخدمة الجديدة فقط")
        pass

    @staticmethod
    def _has_significant_changes(instance):
        """
        التحقق من وجود تغييرات مهمة تستدعي التزامن
        """
        # الحقول المهمة التي تستدعي التزامن
        significant_fields = ["amount", "payment_date", "payment_method", "notes"]

        if not hasattr(instance, "_state") or not instance._state.db:
            return True

        # مقارنة القيم الحالية مع القيم في قاعدة البيانات
        try:
            old_instance = instance.__class__.objects.get(pk=instance.pk)

            for field in significant_fields:
                if hasattr(instance, field) and hasattr(old_instance, field):
                    if getattr(instance, field) != getattr(old_instance, field):
                        return True

            return False
        except instance.__class__.DoesNotExist:
            return True


# تسجيل الإشارات لدفعات المبيعات
try:
    from sale.models import SalePayment

    @receiver(post_save, sender=SalePayment)
    def sale_payment_saved(sender, instance, created, **kwargs):
        """إشارة حفظ دفعة مبيعات"""
        if created:
            PaymentSignalHandler.handle_payment_created(
                sender, instance, created, **kwargs
            )
        else:
            PaymentSignalHandler.handle_payment_updated(
                sender, instance, created, **kwargs
            )

    @receiver(post_delete, sender=SalePayment)
    def sale_payment_deleted(sender, instance, **kwargs):
        """إشارة حذف دفعة مبيعات"""
        PaymentSignalHandler.handle_payment_deleted(sender, instance, **kwargs)

    logger.info("تم تسجيل إشارات دفعات المبيعات")

except ImportError:
    pass

# تسجيل الإشارات لدفعات المشتريات
try:
    from purchase.models import PurchasePayment

    @receiver(post_save, sender=PurchasePayment)
    def purchase_payment_saved(sender, instance, created, **kwargs):
        """إشارة حفظ دفعة مشتريات"""
        if created:
            PaymentSignalHandler.handle_payment_created(
                sender, instance, created, **kwargs
            )
        else:
            PaymentSignalHandler.handle_payment_updated(
                sender, instance, created, **kwargs
            )

    @receiver(post_delete, sender=PurchasePayment)
    def purchase_payment_deleted(sender, instance, **kwargs):
        """إشارة حذف دفعة مشتريات"""
        PaymentSignalHandler.handle_payment_deleted(sender, instance, **kwargs)

    logger.info("تم تسجيل إشارات دفعات المشتريات")

except ImportError:
    pass

# تسجيل الإشارات لدفعات العملاء
try:
    from client.models import CustomerPayment

    @receiver(post_save, sender=CustomerPayment)
    def customer_payment_saved(sender, instance, created, **kwargs):
        """إشارة حفظ دفعة عميل"""
        # تجنب التزامن المتبادل - فقط للدفعات المنشأة يدوياً
        if created and not getattr(instance, "_sync_created", False):
            PaymentSignalHandler.handle_payment_created(
                sender, instance, created, **kwargs
            )

    @receiver(post_delete, sender=CustomerPayment)
    def customer_payment_deleted(sender, instance, **kwargs):
        """إشارة حذف دفعة عميل"""
        # تجنب التزامن المتبادل
        if not getattr(instance, "_sync_deleted", False):
            PaymentSignalHandler.handle_payment_deleted(sender, instance, **kwargs)

    logger.info("تم تسجيل إشارات دفعات العملاء")

except ImportError:
    pass

# تسجيل الإشارات لدفعات الموردين
try:
    from supplier.models import SupplierPayment

    @receiver(post_save, sender=SupplierPayment)
    def supplier_payment_saved(sender, instance, created, **kwargs):
        """إشارة حفظ دفعة مورد"""
        # تجنب التزامن المتبادل - فقط للدفعات المنشأة يدوياً
        if created and not getattr(instance, "_sync_created", False):
            PaymentSignalHandler.handle_payment_created(
                sender, instance, created, **kwargs
            )

    @receiver(post_delete, sender=SupplierPayment)
    def supplier_payment_deleted(sender, instance, **kwargs):
        """إشارة حذف دفعة مورد"""
        # تجنب التزامن المتبادل
        if not getattr(instance, "_sync_deleted", False):
            PaymentSignalHandler.handle_payment_deleted(sender, instance, **kwargs)

    logger.info("تم تسجيل إشارات دفعات الموردين")

except ImportError:
    pass


class PaymentSyncSignalManager:
    """
    مدير إشارات تزامن المدفوعات
    """

    @staticmethod
    def disable_signals():
        """
        تعطيل إشارات التزامن مؤقتاً
        """
        # يمكن استخدامها أثناء عمليات الاستيراد الكبيرة
        pass

    @staticmethod
    def enable_signals():
        """
        تفعيل إشارات التزامن
        """
        pass

    @staticmethod
    def get_signal_status():
        """
        الحصول على حالة الإشارات
        """
        return {
            "sale_payment_signals": True,
            "purchase_payment_signals": True,
            "customer_payment_signals": True,
            "supplier_payment_signals": True,
        }
