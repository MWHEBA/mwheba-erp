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

    # إذا كان الحساب موجوداً بالفعل، نزامن التعديلات (الاسم والحالة)
    if instance.financial_account:
        from financial.services.subledger_account_service import SubledgerAccountService
        SubledgerAccountService.sync_entity_to_account(instance)
        return
    
    try:
        from financial.services.subledger_account_service import SubledgerAccountService
        
        account = SubledgerAccountService.create_customer_account(
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
    تطهير شجرة الحسابات: حذف الحساب المالي الفرعي نهائياً إذا لم تكن به أي قيود يومية،
    أو تعطيله بدلاً من الحذف الصلب لحماية قيود اليومية التاريخية إن وُجدت.
    """
    if instance.financial_account_id:
        try:
            from financial.models import ChartOfAccounts, JournalEntryLine
            account = ChartOfAccounts.objects.filter(id=instance.financial_account_id).first()
            if account:
                has_lines = JournalEntryLine.objects.filter(account=account).exists()
                has_children = account.children.exists()
                if not has_lines and not has_children:
                    account.delete()
                    logger.info(f"✅ تم تطهير وحذف الحساب المالي الفارغ ({account.code}) للعميل {instance.name} نهائياً")
                else:
                    account.is_active = False
                    account.save(update_fields=['is_active'])
                    logger.info(f"تم تعطيل الحساب المحاسبي للعميل {instance.name} بنجاح لوجود قيود تاريخية")
        except Exception as e:
            logger.error(f"فشل معالجة الحساب المحاسبي للعميل {instance.name}: {e}")


# ⚠️ تم نقل مزامنة الأستاذ المساعد CustomerTransaction إلى خط التدفق الخدمي الصريح (PartnerSubledgerService)

# @receiver(post_save, sender="sale.Sale")
# def sync_sale_subledger_signal(sender, instance, created, **kwargs):
#     pass

# @receiver(post_save, sender="client.CustomerPayment")
# def sync_customer_payment_subledger_signal(sender, instance, created, **kwargs):
#     pass

