from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import transaction
from governance.signal_integration import governed_signal_handler
from .models import PurchaseItem, PurchasePayment, Purchase, PurchaseReturn


@governed_signal_handler(
    signal_name="create_stock_movement_for_purchase_item",
    critical=False,  # Changed to False - Service handles this now
    description="إنشاء حركة مخزون لبند المشتريات (DISABLED - Service handles this)"
)
@receiver(post_save, sender=PurchaseItem)
def create_stock_movement_for_purchase_item(sender, instance, created, **kwargs):
    """
    إنشاء حركة مخزون تلقائياً عند إنشاء بند فاتورة مشتريات
    
    ⚠️ DISABLED: PurchaseService now handles stock movements
    This signal is kept for backward compatibility but does nothing
    """
    # Signal disabled - PurchaseService handles stock movements
    return


@governed_signal_handler(
    signal_name="update_product_prices_on_purchase",
    critical=True,
    description="تحديث أسعار المنتجات عند الشراء"
)
@receiver(post_save, sender=PurchaseItem)
def update_product_prices_on_purchase(sender, instance, created, **kwargs):
    """
    تحديث أسعار المنتجات حسب المورد تلقائياً عند الشراء

    النظام الجديد:
    - تحديث سعر المنتج للمورد المحدد
    - تسجيل تاريخ التغيير
    - تحديث السعر الرئيسي إذا كان المورد افتراضي أو السعر أحدث
    """
    if created and instance.purchase.status == "confirmed":
        try:
            from product.services import PricingService
            import logging

            logger = logging.getLogger(__name__)

            # تحديث سعر المنتج للمورد
            supplier_price = PricingService.update_supplier_price(
                product=instance.product,
                supplier=instance.purchase.supplier,
                new_price=instance.unit_price,
                user=instance.purchase.created_by,
                reason="purchase",
                purchase_reference=instance.purchase.number,
                purchase_quantity=instance.quantity,
                notes=f"تحديث تلقائي من فاتورة شراء {instance.purchase.number}",
            )

            if supplier_price:
                logger.info(
                    f"✅ تم تحديث سعر المنتج '{instance.product.name}' "
                    f"للمورد '{instance.purchase.supplier.name}' إلى {instance.unit_price} "
                    f"من فاتورة {instance.purchase.number}"
                )

                # إشعار المستخدم بالتحديث (يمكن إضافة نظام إشعارات لاحقاً)
                if supplier_price.is_default:
                    logger.info(
                        f"📢 تم تحديث السعر الرئيسي للمنتج '{instance.product.name}' "
                        f"إلى {instance.unit_price} (المورد الافتراضي)"
                    )
            else:
                logger.warning(
                    f"⚠️ فشل في تحديث سعر المنتج '{instance.product.name}' "
                    f"للمورد '{instance.purchase.supplier.name}'"
                )

        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"❌ خطأ في تحديث أسعار المنتج: {e}")

            # Fallback للنظام القديم في حالة فشل النظام الجديد
            product = instance.product
            purchase_price = instance.unit_price

            if purchase_price > product.cost_price:
                # حساب نسبة الربح الحالية قبل التحديث
                if product.cost_price > 0:
                    profit_margin = (
                        product.selling_price - product.cost_price
                    ) / product.cost_price
                else:
                    profit_margin = 0.2  # نسبة ربح افتراضية 20%

                # تحديث سعر التكلفة
                old_cost_price = product.cost_price
                product.cost_price = purchase_price

                # تحديث سعر البيع بناءً على نسبة الربح السابقة
                new_selling_price = product.cost_price * (1 + profit_margin)
                old_selling_price = product.selling_price
                product.selling_price = new_selling_price

                # حفظ التحديثات
                product.save(update_fields=["cost_price", "selling_price"])

                logger.info(
                    f"✅ تحديث أسعار المنتج (النظام القديم) '{product.name}' - "
                    f"سعر التكلفة: {old_cost_price} ← {product.cost_price} | "
                    f"سعر البيع: {old_selling_price} ← {product.selling_price:.2f}"
                )


@governed_signal_handler(
    signal_name="handle_deleted_purchase_item",
    critical=True,
    description="معالجة حذف بند المشتريات"
)
@receiver(post_delete, sender=PurchaseItem)
def handle_deleted_purchase_item(sender, instance, **kwargs):
    """
    إلغاء حركة المخزون عند حذف بند الفاتورة
    
    ✅ محدث: يستخدم MovementService لإنشاء حركة معاكسة
    """
    try:
        # ✨ تخطي الخدمات - لا تحتاج حركات مخزون
        if instance.product.is_service:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(
                f"⏭️ تخطي معالجة حذف الخدمة '{instance.product.name}' - "
                f"فاتورة {instance.purchase.number}"
            )
            return
        
        # ✅ استخدام MovementService لإنشاء حركة معاكسة
        from governance.services import MovementService
        from product.models import StockMovement
        from decimal import Decimal
        import logging
        
        logger = logging.getLogger(__name__)
        
        # البحث عن حركة المخزون المرتبطة
        related_movement = StockMovement.objects.filter(
            idempotency_key=f"purchase_item_{instance.id}_create"
        ).first()

        if related_movement:
            with transaction.atomic():
                # ✅ إنشاء حركة معاكسة عبر MovementService
                movement_service = MovementService()
                reversal_movement = movement_service.process_movement(
                    product_id=instance.product.id,
                    quantity_change=-Decimal(str(instance.quantity)),  # سالب للإرجاع
                    movement_type='out',
                    source_reference=f"PUR-CANCEL-{instance.purchase.number}",
                    idempotency_key=f"purchase_item_{instance.id}_delete",
                    user=instance.purchase.created_by,
                    unit_cost=instance.unit_price,
                    document_number=instance.purchase.number,
                    notes=f"إلغاء بند مشتريات - فاتورة رقم {instance.purchase.number}"
                )
                
                logger.info(
                    f"✅ تم إنشاء حركة إرجاع عبر MovementService: {reversal_movement.id} - "
                    f"المنتج '{instance.product.name}' - الكمية: {instance.quantity}"
                )

                # ✅ حذف الحركة الأصلية بطريقة مباشرة
                StockMovement.objects.filter(pk=related_movement.pk).delete()
                
                logger.info(
                    f"✅ تم حذف حركة المخزون الأصلية للمنتج '{instance.product.name}'"
                )
        else:
            logger.warning(
                f"⚠️ لم يتم العثور على حركة مخزون للبند المحذوف: "
                f"{instance.product.name} - فاتورة {instance.purchase.number}"
            )

    except Exception as e:
        # تسجيل الخطأ ورفعه لإيقاف العملية
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"❌ خطأ في معالجة حذف بند المشتريات: {str(e)}")
        # ✅ رفع الخطأ لإيقاف عملية الحذف إذا فشلت معالجة المخزون
        raise


@governed_signal_handler(
    signal_name="update_payment_status_on_purchase_payment",
    critical=True,
    description="تحديث حالة الدفع عند دفعة المشتريات"
)
@receiver(post_save, sender=PurchasePayment)
def update_payment_status_on_payment(sender, instance, created, **kwargs):
    """
    تحديث حالة الدفع عند تسجيل دفعة أو تعديلها أو ترحيلها
    """
    if instance.purchase:
        instance.purchase.update_payment_status()

    if created:
        # تحديث رصيد المورد عند إضافة الدفعة لأول مرة
        supplier = instance.purchase.supplier
        if supplier:
            supplier.balance -= instance.amount
            supplier.save(update_fields=["balance"])


@governed_signal_handler(
    signal_name="update_supplier_balance_on_purchase",
    critical=True,
    description="تحديث رصيد المورد عند الشراء"
)
@receiver(post_save, sender=Purchase)
def update_supplier_balance_on_purchase(sender, instance, created, **kwargs):
    """
    تحديث رصيد المورد عند إنشاء فاتورة مشتريات
    """
    if created and instance.payment_method == "credit":
        supplier = instance.supplier
        if supplier:
            rate = getattr(instance, 'exchange_rate', Decimal('1.000000')) or Decimal('1.000000')
            func_total = getattr(instance, 'total_functional', None) or (instance.total * rate).quantize(Decimal('0.01'))
            supplier.balance += func_total
            supplier.save(update_fields=["balance"])


@governed_signal_handler(
    signal_name="create_financial_transaction_for_purchase",
    critical=False,  # Changed to False - Service handles this now
    description="إنشاء معاملة مالية للمشتريات (DISABLED - Service handles this)"
)
@receiver(post_save, sender=Purchase)
def create_financial_transaction_for_purchase(sender, instance, created, **kwargs):
    """
    إنشاء قيد محاسبي تلقائي عند إنشاء فاتورة مشتريات جديدة

    ⚠️ DISABLED: PurchaseService now handles journal entries
    This signal is kept for backward compatibility but does nothing
    """
    # Signal disabled - PurchaseService handles journal entries
    return


@governed_signal_handler(
    signal_name="create_financial_transaction_for_purchase_payment",
    critical=True,
    description="إنشاء معاملة مالية لدفعة المشتريات"
)
@receiver(post_save, sender=PurchasePayment)
def create_financial_transaction_for_payment(sender, instance, created, **kwargs):
    """
    إنشاء قيد محاسبي تلقائي عند دفع دفعة لفاتورة مشتريات

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
    #             payment_type='purchase_payment',
    #             user=instance.created_by
    #         )
    #
    #         if journal_entry:
    #             import logging
    #             logger = logging.getLogger(__name__)
    #             logger.info(f"تم إنشاء قيد محاسبي لدفعة المشتريات: {journal_entry.number}")
    #         else:
    #             import logging
    #             logger = logging.getLogger(__name__)
    #             logger.warning(f"فشل في إنشاء قيد محاسبي لدفعة المشتريات - دفعة {instance.id}")
    #
    #     except Exception as e:
    #         import logging
    #         logger = logging.getLogger(__name__)
    #         logger.error(f"خطأ في إنشاء قيد محاسبي لدفعة المشتريات: {str(e)} - دفعة {instance.id}")


@governed_signal_handler(
    signal_name="create_financial_transaction_for_purchase_return",
    critical=True,
    description="إنشاء معاملة مالية لمرتجع المشتريات"
)
@receiver(post_save, sender=PurchaseReturn)
def create_financial_transaction_for_return(sender, instance, **kwargs):
    """
    إنشاء معاملة مالية عند تأكيد مرتجع مشتريات
    تم تعطيل إنشاء الحسابات التلقائية - يجب استخدام النظام الجديد
    """
    # تم تعطيل هذه الوظيفة مؤقتاً حتى يتم تحديث النظام المحاسبي
    pass
