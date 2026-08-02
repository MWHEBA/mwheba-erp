"""
Sale Signals - Updated
⚠️ معظم الـ Signals تم تعطيلها لأن SaleService يتولى كل شيء

الـ Signals المتبقية:
- update_payment_status_and_balance_on_payment: تحديث حالة الدفع والرصيد عند الدفع
- update_customer_balance_on_payment_delete: تحديث الرصيد عند حذف الدفعة
- update_customer_balance_on_sale_save: تحديث الرصيد عند حفظ الفاتورة
- update_customer_balance_on_sale_delete: تحديث الرصيد عند حذف الفاتورة
"""
from django.db import transaction as db_transaction
from django.db.models import Sum
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from decimal import Decimal
from client.models import Customer
from .models import SalePayment, Sale, SaleReturn, CustomFieldDefinition
from django.core.cache import cache
from django.conf import settings


def recalculate_customer_balance(customer):
    """
    إعادة حساب رصيد العميل الفعلي وتحديثه بحماية كاملة للتزامن (Atomic Transaction & Row Locking)
    الحسبة الشاملة: (إجمالي الفواتير - إجمالي المرتجعات - إجمالي المدفوعات)
    """
    if not customer or not customer.pk:
        return
    
    with db_transaction.atomic():
        try:
            locked_customer = Customer.objects.select_for_update().get(pk=customer.pk)
        except Customer.DoesNotExist:
            return

        # مجموع كل فواتير المبيعات للعميل (المؤكدة وغير الملغاة)
        total_sales = Sale.objects.filter(
            customer=locked_customer
        ).exclude(status='cancelled').aggregate(total=Sum('total'))['total'] or Decimal('0')
        
        # مجموع كل المرتجعات المؤكدة للعميل
        total_returns = SaleReturn.objects.filter(
            sale__customer=locked_customer,
            status='confirmed'
        ).aggregate(total=Sum('total'))['total'] or Decimal('0')

        # مجموع كل الدفعات المرحلة للعميل
        total_payments = SalePayment.objects.filter(
            sale__customer=locked_customer,
            status='posted'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        # تحديث الحقل المخزن بالرصيد الفعلي بحماية ضد الـ Race Conditions
        new_balance = total_sales - total_returns - total_payments
        locked_customer.balance = new_balance
        locked_customer.save(update_fields=['balance'])
        customer.balance = new_balance


@receiver(post_save, sender=CustomFieldDefinition)
@receiver(post_delete, sender=CustomFieldDefinition)
def invalidate_custom_fields_cache(sender, instance, **kwargs):
    """
    إبطال كاش تعاريف الحقول المخصصة فور تعديلها أو حذفها
    """
    client_name = getattr(settings, 'CLIENT_NAME', 'mwheba')
    for module in ['sale', 'quotation', 'both']:
        cache.delete(f"custom_field_defs_{module}_{client_name}")


# ✅ Signal نشط: تحديث حالة الدفع ورصيد العميل عند الدفع
@receiver(post_save, sender=SalePayment)
def update_payment_status_and_balance_on_payment(sender, instance, created, **kwargs):
    """
    تحديث حالة الدفع ورصيد العميل عند تسجيل دفعة أو تعديلها أو ترحيلها
    """
    if instance.sale:
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

