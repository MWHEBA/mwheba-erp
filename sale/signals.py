"""
Sale Signals - Updated
⚠️ معظم الـ Signals تم تعطيلها لأن SaleService يتولى كل شيء

الـ Signals المتبقية:
- update_payment_status_and_balance_on_payment: تحديث حالة الدفع والرصيد عند الدفع
- update_customer_balance_on_payment_delete: تحديث الرصيد عند حذف الدفعة
- update_customer_balance_on_sale_save: تحديث الرصيد عند حفظ الفاتورة
- update_customer_balance_on_sale_delete: تحديث الرصيد عند حذف الفاتورة
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db.models import Sum
from decimal import Decimal
from .models import SalePayment, Sale


def recalculate_customer_balance(customer):
    """
    إعادة حساب رصيد العميل الفعلي وتحديثه في قاعدة البيانات
    """
    if not customer:
        return
    
    # مجموع كل فواتير المبيعات للعميل
    total_sales = customer.sales.aggregate(total=Sum('total'))['total'] or Decimal('0')
    
    # مجموع كل الدفعات المرحلة للعميل
    total_payments = SalePayment.objects.filter(
        sale__customer=customer,
        status='posted'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    
    # تحديث الحقل المخزن بالرصيد الفعلي
    customer.balance = total_sales - total_payments
    customer.save(update_fields=['balance'])


# ✅ Signal نشط: تحديث حالة الدفع ورصيد العميل عند الدفع
@receiver(post_save, sender=SalePayment)
def update_payment_status_and_balance_on_payment(sender, instance, created, **kwargs):
    """
    تحديث حالة الدفع ورصيد العميل عند تسجيل دفعة أو تعديلها
    """
    if created:
        instance.sale.update_payment_status()
    
    if instance.sale and instance.sale.customer:
        recalculate_customer_balance(instance.sale.customer)


# ✅ Signal نشط: تحديث رصيد العميل عند حذف الدفعة
@receiver(post_delete, sender=SalePayment)
def update_customer_balance_on_payment_delete(sender, instance, **kwargs):
    """
    تحديث رصيد العميل عند حذف دفعة
    """
    if instance.sale and instance.sale.customer:
        recalculate_customer_balance(instance.sale.customer)


# ✅ Signal نشط: تحديث رصيد العميل عند حفظ الفاتورة
@receiver(post_save, sender=Sale)
def update_customer_balance_on_sale_save(sender, instance, created, **kwargs):
    """
    تحديث رصيد العميل عند إنشاء أو تعديل فاتورة مبيعات
    """
    if instance.customer:
        recalculate_customer_balance(instance.customer)


# ✅ Signal نشط: تحديث رصيد العميل عند حذف الفاتورة
@receiver(post_delete, sender=Sale)
def update_customer_balance_on_sale_delete(sender, instance, **kwargs):
    """
    تحديث رصيد العميل عند حذف فاتورة مبيعات
    """
    if instance.customer:
        recalculate_customer_balance(instance.customer)



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

