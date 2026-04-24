"""
Sale Signals - Updated
⚠️ معظم الـ Signals تم تعطيلها لأن SaleService يتولى كل شيء

الـ Signals المتبقية:
- update_payment_status_on_payment: تحديث حالة الدفع (بسيط)
- update_customer_balance_on_sale: تحديث رصيد العميل (بسيط)

الـ Signals المعطلة:
- create_stock_movement_for_sale_item: يتم عبر MovementService
- create_financial_transaction_for_payment: يتم عبر AccountingGateway
- create_financial_transaction_for_return: يتم عبر AccountingGateway
- handle_deleted_sale: يتم عبر SaleService.delete_sale()
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import SalePayment, Sale


# ✅ Signal نشط: تحديث حالة الدفع
@receiver(post_save, sender=SalePayment)
def update_payment_status_on_payment(sender, instance, created, **kwargs):
    """
    تحديث حالة الدفع عند تسجيل دفعة
    """
    if created:
        instance.sale.update_payment_status()


# ✅ Signal نشط: تحديث رصيد العميل
@receiver(post_save, sender=Sale)
def update_customer_balance_on_sale(sender, instance, created, **kwargs):
    """
    تحديث رصيد العميل عند إنشاء فاتورة مبيعات آجلة
    """
    if created and instance.payment_method == "credit":
        customer = instance.customer
        if customer:
            customer.balance += instance.total
            customer.save(update_fields=["balance"])


# ❌ Signals معطلة - يتم التعامل معها عبر SaleService

# @receiver(post_save, sender=SaleItem)
# def create_stock_movement_for_sale_item(sender, instance, created, **kwargs):
#     """
#     ❌ معطل: حركات المخزون تُنشأ عبر MovementService في SaleService
#     """
#     pass


# @receiver(post_delete, sender=SaleItem)
# def handle_deleted_sale_item(sender, instance, **kwargs):
#     """
#     ❌ معطل: يتم التعامل مع الحذف عبر SaleService
#     """
#     pass


# @receiver(post_save, sender=SalePayment)
# def create_financial_transaction_for_payment(sender, instance, created, **kwargs):
#     """
#     ❌ معطل: القيود المحاسبية تُنشأ عبر AccountingGateway في SaleService
#     """
#     pass


# @receiver(post_save, sender=SaleReturn)
# def create_financial_transaction_for_return(sender, instance, created, **kwargs):
#     """
#     ❌ معطل: القيود المحاسبية تُنشأ عبر AccountingGateway في SaleService
#     """
#     pass


# @receiver(pre_delete, sender=Sale)
# def handle_deleted_sale(sender, instance, **kwargs):
#     """
#     ❌ معطل: الحذف يتم عبر SaleService.delete_sale()
#     """
#     pass

