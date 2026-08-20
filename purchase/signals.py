from decimal import Decimal
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


# ⚠️ تم نقل معالجة حذف بنود وحركات المشتريات وإدارتها إلى خط التدفق الخدمي الصريح (PurchaseService & PartnerBalanceService)

# @receiver(post_delete, sender=PurchaseItem)
# def handle_deleted_purchase_item(sender, instance, **kwargs):
#     pass

# @receiver(post_save, sender=PurchasePayment)
# def update_payment_status_on_payment(sender, instance, created, **kwargs):
#     pass

@receiver(post_delete, sender=PurchasePayment)
def update_supplier_balance_on_payment_delete(sender, instance, **kwargs):
    """
    تحديث حالة وأستاذ المورد عند حذف دفعة مشتريات (Safety Net)
    """
    if instance.purchase and instance.purchase.supplier:
        from financial.services.partner_subledger_service import PartnerSubledgerService
        PartnerSubledgerService.record_purchase_bill(instance.purchase)
        instance.purchase.update_payment_status()

# @receiver(post_save, sender=Purchase)
# def update_supplier_balance_on_purchase(sender, instance, created, **kwargs):
#     pass


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
