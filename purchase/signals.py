from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import transaction
from .models import PurchaseItem, PurchasePayment, Purchase, PurchaseReturn


@receiver(post_save, sender=PurchaseItem)
def create_stock_movement_for_purchase_item(sender, instance, created, **kwargs):
    """
    إنشاء حركة مخزون تلقائياً عند إنشاء بند فاتورة مشتريات

    هذا هو المكان الصحيح لإنشاء حركات المخزون (Django Best Practice)
    Signal يضمن إنشاء الحركة في جميع الحالات (View, Admin, API, etc.)
    """
    if created and instance.purchase.status == "confirmed":
        # استيراد StockMovement محلياً لتجنب مشاكل الاستيراد الدائري
        from product.models import StockMovement
        
        # التحقق من عدم وجود حركة مخزون مسبقاً لتجنب الازدواجية
        existing_movement = StockMovement.objects.filter(
            product=instance.product,
            warehouse=instance.purchase.warehouse,
            document_type="purchase",
            document_number=instance.purchase.number,
            reference_number=f"PURCHASE-{instance.purchase.number}-ITEM-{instance.id}",
        ).exists()

        if not existing_movement:
            with transaction.atomic():
                # إنشاء حركة مخزون للوارد
                StockMovement.objects.create(
                    product=instance.product,
                    warehouse=instance.purchase.warehouse,
                    movement_type="in",
                    quantity=instance.quantity,
                    document_type="purchase",
                    document_number=instance.purchase.number,
                    reference_number=f"PURCHASE-{instance.purchase.number}-ITEM-{instance.id}",
                    notes=f"مشتريات - فاتورة رقم {instance.purchase.number}",
                    created_by=instance.purchase.created_by,
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


@receiver(post_delete, sender=PurchaseItem)
def handle_deleted_purchase_item(sender, instance, **kwargs):
    """
    إلغاء حركة المخزون عند حذف بند الفاتورة
    """
    try:
        # استيراد StockMovement محلياً لتجنب مشاكل الاستيراد الدائري
        from product.models import StockMovement
        
        # البحث عن حركة المخزون المرتبطة وحذفها
        related_movement = StockMovement.objects.filter(
            product=instance.product,
            warehouse=instance.purchase.warehouse,
            document_type="purchase",
            document_number=instance.purchase.number,
            reference_number=f"PURCHASE-{instance.purchase.number}-ITEM-{instance.id}",
        ).first()

        if related_movement:
            with transaction.atomic():
                # إنشاء حركة مخزون معاكسة (إخراج المخزون)
                StockMovement.objects.create(
                    product=instance.product,
                    warehouse=instance.purchase.warehouse,
                    movement_type="out",
                    quantity=related_movement.quantity,
                    document_type="purchase_return",
                    document_number=instance.purchase.number,
                    reference_number=f"PURCHASE-CANCEL-{instance.purchase.number}-ITEM-{instance.id}",
                    notes=f"إلغاء بند مشتريات - فاتورة رقم {instance.purchase.number}",
                    created_by=instance.purchase.created_by,
                )

                # حذف الحركة الأصلية
                related_movement.delete()

    except Exception as e:
        # تسجيل الخطأ دون إيقاف العملية
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"خطأ في معالجة حذف بند المشتريات: {str(e)}")


@receiver(post_save, sender=PurchasePayment)
def update_payment_status_on_payment(sender, instance, created, **kwargs):
    """
    تحديث حالة الدفع عند تسجيل دفعة
    """
    if created:
        instance.purchase.update_payment_status()

        # تحديث رصيد المورد
        supplier = instance.purchase.supplier
        if supplier:
            supplier.balance -= instance.amount
            supplier.save(update_fields=["balance"])


@receiver(post_save, sender=Purchase)
def update_supplier_balance_on_purchase(sender, instance, created, **kwargs):
    """
    تحديث رصيد المورد عند إنشاء فاتورة مشتريات
    """
    if created and instance.payment_method == "credit":
        supplier = instance.supplier
        if supplier:
            supplier.balance += instance.total
            supplier.save(update_fields=["balance"])


@receiver(post_save, sender=Purchase)
def create_financial_transaction_for_purchase(sender, instance, created, **kwargs):
    """
    إنشاء قيد محاسبي تلقائي عند إنشاء فاتورة مشتريات جديدة

    يتم إنشاء قيد محاسبي مباشرة عند تأكيد الفاتورة يشمل:
    - مدين: المخزون
    - دائن: الصندوق (نقدي) أو الموردين (آجل)
    """
    if created and instance.status == "confirmed":
        try:
            from financial.services.accounting_integration_service import (
                AccountingIntegrationService,
            )
            import logging

            logger = logging.getLogger(__name__)

            # إنشاء القيد المحاسبي
            journal_entry = AccountingIntegrationService.create_purchase_journal_entry(
                purchase=instance, user=instance.created_by
            )

            if journal_entry:
                logger.info(
                    f"✅ تم إنشاء قيد محاسبي للمشتريات: {journal_entry.number} - فاتورة {instance.number}"
                )
            else:
                logger.warning(
                    f"⚠️ فشل في إنشاء قيد محاسبي للمشتريات - فاتورة {instance.number}"
                )

        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(
                f"❌ خطأ في إنشاء قيد محاسبي للمشتريات: {str(e)} - فاتورة {instance.number}"
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


@receiver(post_save, sender=PurchaseReturn)
def create_financial_transaction_for_return(sender, instance, **kwargs):
    """
    إنشاء معاملة مالية عند تأكيد مرتجع مشتريات
    تم تعطيل إنشاء الحسابات التلقائية - يجب استخدام النظام الجديد
    """
    # تم تعطيل هذه الوظيفة مؤقتاً حتى يتم تحديث النظام المحاسبي
    pass
