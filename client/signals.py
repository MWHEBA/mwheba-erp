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
    إنشاء حساب محاسبي تلقائياً عند إضافة عميل جديد أو عند الحاجة
    
    ✅ Single Source of Truth for customer financial account creation
    
    This signal is the ONLY place where customer financial accounts are created.
    All customer creation flows (views, services, admin, scripts) rely on this signal.
    
    Handles two cases:
    1. New customer creation (created=True)
    2. Existing customer without account (created=False but no financial_account)
    """
    # التحقق من تفعيل الميزة في الإعدادات
    if not getattr(settings, "AUTO_CREATE_CUSTOMER_ACCOUNTS", True):
        return

    # إنشاء حساب فقط إذا لم يكن موجوداً
    if instance.financial_account:
        return
    
    try:
        from .services import CustomerService
        
        service = CustomerService()
        account = service.create_financial_account_for_customer(
            customer=instance,
            user=instance.created_by
        )
        
        # Update customer with financial account using update() to avoid triggering signal again
        Customer.objects.filter(pk=instance.pk).update(financial_account=account)
        instance.financial_account = account  # Update in-memory instance
        instance.financial_account_id = account.id
        
        action = "created" if created else "recovered"
        logger.info(
            f"✅ Financial account {account.code} {action} for customer {instance.name} "
            f"automatically via post_save signal"
        )
    except Exception as e:
        # Log error but don't stop the customer creation process
        logger.error(f"❌ Failed to create financial account for customer {instance.name}: {e}")


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


@receiver(post_save, sender="sale.Sale")
def sync_sale_subledger_signal(sender, instance, created, **kwargs):
    """
    مزامنة فاتورة المبيعات مع أستاذ العملاء الفرعي CustomerTransaction
    """
    try:
        from decimal import Decimal
        from django.db.models import Sum
        from client.models import CustomerTransaction
        from sale.models import SalePayment
        
        paid = SalePayment.objects.filter(sale=instance).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
        due = instance.total - paid
        status = 'PAID' if due <= 0 else ('PARTIAL' if paid > 0 else 'OPEN')
        
        txn, is_new = CustomerTransaction.objects.get_or_create(
            customer=instance.customer,
            transaction_type='INVOICE',
            reference_id=str(instance.id),
            defaults={
                'transaction_number': instance.number,
                'issue_date': instance.date,
                'due_date': instance.date,
                'currency': 'EGP',
                'foreign_amount': instance.total,
                'exchange_rate': Decimal('1.000000'),
                'functional_amount': instance.total,
                'open_amount': due,
                'open_amount_functional': due,
                'open_amount_foreign': due,
                'status': status
            }
        )
        if not is_new:
            txn.open_amount = due
            txn.open_amount_functional = due
            txn.open_amount_foreign = due
            txn.status = status
            txn.save()
    except Exception as e:
        logger.error(f"Failed to sync sale {instance.number} to subledger: {e}")


@receiver(post_save, sender="client.CustomerPayment")
def sync_customer_payment_subledger_signal(sender, instance, created, **kwargs):
    """
    مزامنة الدفعات المقدمة مع أستاذ العملاء الفرعي CustomerTransaction
    """
    try:
        from decimal import Decimal
        from client.models import CustomerTransaction
        
        CustomerTransaction.objects.get_or_create(
            customer=instance.customer,
            transaction_type='ADVANCE',
            reference_id=str(instance.id),
            defaults={
                'transaction_number': instance.reference_number or f'CP-{instance.id}',
                'issue_date': instance.payment_date,
                'due_date': instance.payment_date,
                'currency': 'EGP',
                'foreign_amount': instance.amount,
                'exchange_rate': Decimal('1.000000'),
                'functional_amount': instance.amount,
                'open_amount': instance.amount,
                'open_amount_functional': instance.amount,
                'open_amount_foreign': instance.amount,
                'status': 'OPEN'
            }
        )
    except Exception as e:
        logger.error(f"Failed to sync CustomerPayment {instance.id} to subledger: {e}")

