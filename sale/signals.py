from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import transaction
from .models import SaleItem, SalePayment, Sale, SaleReturn
from product.models import StockMovement


@receiver(post_save, sender=SaleItem)
def create_stock_movement_for_sale_item(sender, instance, created, **kwargs):
    """
    إنشاء حركة مخزون عند إنشاء بند فاتورة مبيعات
    """
    if created and instance.sale.status == "confirmed":
        # التحقق من عدم وجود حركة مخزون مسبقاً لتجنب الازدواجية
        existing_movement = StockMovement.objects.filter(
            product=instance.product,
            warehouse=instance.sale.warehouse,
            document_type="sale",
            document_number=instance.sale.number,
            reference_number=f"SALE-{instance.sale.number}-ITEM-{instance.id}",
        ).exists()

        if not existing_movement:
            with transaction.atomic():
                # إنشاء حركة مخزون للصادر
                StockMovement.objects.create(
                    product=instance.product,
                    warehouse=instance.sale.warehouse,
                    movement_type="out",
                    quantity=instance.quantity,
                    document_type="sale",
                    document_number=instance.sale.number,
                    reference_number=f"SALE-{instance.sale.number}-ITEM-{instance.id}",
                    notes=f"مبيعات - فاتورة رقم {instance.sale.number}",
                    created_by=instance.sale.created_by,
                )


@receiver(post_delete, sender=SaleItem)
def handle_deleted_sale_item(sender, instance, **kwargs):
    """
    إلغاء حركة المخزون عند حذف بند الفاتورة
    """
    try:
        # البحث عن حركة المخزون المرتبطة وحذفها
        related_movement = StockMovement.objects.filter(
            product=instance.product,
            warehouse=instance.sale.warehouse,
            document_type="sale",
            document_number=instance.sale.number,
            reference_number=f"SALE-{instance.sale.number}-ITEM-{instance.id}",
        ).first()

        if related_movement:
            with transaction.atomic():
                # إنشاء حركة مخزون معاكسة (إرجاع المخزون)
                StockMovement.objects.create(
                    product=instance.product,
                    warehouse=instance.sale.warehouse,
                    movement_type="in",
                    quantity=related_movement.quantity,
                    document_type="sale_return",
                    document_number=instance.sale.number,
                    reference_number=f"SALE-CANCEL-{instance.sale.number}-ITEM-{instance.id}",
                    notes=f"إلغاء بند مبيعات - فاتورة رقم {instance.sale.number}",
                    created_by=instance.sale.created_by,
                )

                # حذف الحركة الأصلية
                related_movement.delete()

    except Exception as e:
        # تسجيل الخطأ دون إيقاف العملية
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"خطأ في معالجة حذف بند المبيعات: {str(e)}")


@receiver(post_save, sender=SalePayment)
def update_payment_status_on_payment(sender, instance, created, **kwargs):
    """
    تحديث حالة الدفع عند تسجيل دفعة
    """
    if created:
        instance.sale.update_payment_status()

        # تحديث رصيد العميل
        customer = instance.sale.customer
        if customer:
            customer.balance -= instance.amount
            customer.save(update_fields=["balance"])


@receiver(post_save, sender=Sale)
def update_customer_balance_on_sale(sender, instance, created, **kwargs):
    """
    تحديث رصيد العميل عند إنشاء فاتورة مبيعات
    """
    if created and instance.payment_method == "credit":
        customer = instance.customer
        if customer:
            customer.balance += instance.total
            customer.save(update_fields=["balance"])


@receiver(post_save, sender=Sale)
def create_financial_transaction_for_sale(sender, instance, created, **kwargs):
    """
    إنشاء قيد محاسبي تلقائي عند إنشاء فاتورة مبيعات جديدة

    يتم إنشاء قيد محاسبي مباشرة عند تأكيد الفاتورة يشمل:
    - مدين: الصندوق (نقدي) أو العملاء (آجل)
    - دائن: إيرادات المبيعات
    - مدين: تكلفة البضاعة المباعة
    - دائن: المخزون
    """
    if created and instance.status == "confirmed":
        try:
            from financial.services.accounting_integration_service import (
                AccountingIntegrationService,
            )
            import logging

            logger = logging.getLogger(__name__)

            # إنشاء القيد المحاسبي
            journal_entry = AccountingIntegrationService.create_sale_journal_entry(
                sale=instance, user=instance.created_by
            )

            if journal_entry:
                logger.info(
                    f"✅ تم إنشاء قيد محاسبي للمبيعات: {journal_entry.number} - فاتورة {instance.number}"
                )
            else:
                logger.warning(
                    f"⚠️ فشل في إنشاء قيد محاسبي للمبيعات - فاتورة {instance.number}"
                )

        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(
                f"❌ خطأ في إنشاء قيد محاسبي للمبيعات: {str(e)} - فاتورة {instance.number}"
            )


@receiver(post_save, sender=SalePayment)
def create_financial_transaction_for_payment(sender, instance, created, **kwargs):
    """
    إنشاء قيد محاسبي تلقائي عند استلام دفعة من فاتورة مبيعات

    ملاحظة: تم تعطيل هذا Signal لأن الخدمة الجديدة PaymentIntegrationService تتولى كل شيء
    القيود تُنشأ عبر الخدمة الجديدة في Views مع معالجة أخطاء أفضل
    """
    # تم تعطيل هذا Signal - الخدمة الجديدة تتولى إنشاء القيود
    pass

    # الكود القديم (معطل):
    # if created:
    #     try:
    #         from financial.services.accounting_integration_service import AccountingIntegrationService
    #
    #         # إنشاء القيد المحاسبي للدفعة
    #         journal_entry = AccountingIntegrationService.create_payment_journal_entry(
    #             payment=instance,
    #             payment_type='sale_payment',
    #             user=instance.created_by
    #         )
    #
    #         if journal_entry:
    #             import logging
    #             logger = logging.getLogger(__name__)
    #             logger.info(f"تم إنشاء قيد محاسبي لدفعة المبيعات: {journal_entry.number}")
    #         else:
    #             import logging
    #             logger = logging.getLogger(__name__)
    #             logger.warning(f"فشل في إنشاء قيد محاسبي لدفعة المبيعات - دفعة {instance.id}")
    #
    #     except Exception as e:
    #         import logging
    #         logger = logging.getLogger(__name__)
    #         logger.error(f"خطأ في إنشاء قيد محاسبي لدفعة المبيعات: {str(e)} - دفعة {instance.id}")


@receiver(post_save, sender=SaleReturn)
def create_financial_transaction_for_return(sender, instance, **kwargs):
    """
    إنشاء معاملة مالية عند تأكيد مرتجع مبيعات
    تم تعطيل إنشاء الحسابات التلقائية - يجب استخدام النظام الجديد
    """
    # تم تعطيل هذه الوظيفة مؤقتاً حتى يتم تحديث النظام المحاسبي
    pass
