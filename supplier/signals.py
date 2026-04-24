"""
Signals للموردين
Integrated with Governance System for monitoring and control
"""
import logging
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.conf import settings
from django.utils import timezone

# Governance integration
from governance.services import signal_router, governance_switchboard
from governance.services.audit_service import AuditService
from governance.services.monitoring_service import monitoring_service
from governance.models import GovernanceContext

from .models import Supplier

logger = logging.getLogger(__name__)


from governance.signal_integration import governed_signal_handler

@governed_signal_handler(
    signal_name="supplier_account_creation",
    critical=True,
    description="إنشاء حساب محاسبي تلقائياً عند إضافة مورد جديد"
)
@receiver(post_save, sender=Supplier)
def create_supplier_account_signal(sender, instance, created, **kwargs):
    """
    إنشاء حساب محاسبي تلقائياً عند إضافة مورد جديد
    
    ✅ Single Source of Truth for supplier financial account creation
    
    This signal is the ONLY place where supplier financial accounts are created.
    All supplier creation flows (views, services, admin, scripts) rely on this signal.
    
    Integrated with Governance: audit_logging workflow
    """
    from django.db import transaction
    
    # التحقق من وجود primary_type قبل أي شيء
    if not instance.primary_type:
        logger.debug(f"تخطي إنشاء حساب للمورد {instance.name} - لا يوجد نوع محدد")
        return
    
    # Route through governance signal_router
    routing_result = signal_router.route_signal(
        signal_name='supplier_account_creation',
        sender=sender,
        instance=instance,
        critical=False,  # Non-critical audit signal
        created=created,
        **kwargs
    )
    
    # Check if governance allows this operation
    if not governance_switchboard.is_workflow_enabled('audit_logging'):
        logger.debug("Supplier account creation audit disabled - skipping")
        return
    
    # التحقق من تفعيل الميزة في الإعدادات
    if not getattr(settings, "AUTO_CREATE_SUPPLIER_ACCOUNTS", True):
        return

    # إنشاء حساب فقط إذا لم يكن موجوداً
    if instance.financial_account:
        return
    
    try:
        # ✅ استخدام SupplierService الموحد بدلاً من SupplierParentAccountService
        from supplier.services.supplier_service import SupplierService
        
        account = SupplierService.create_financial_account_for_supplier(
            supplier=instance,
            user=instance.created_by
        )
        
        # Update supplier with financial account using update() to avoid triggering signal again
        Supplier.objects.filter(pk=instance.pk).update(financial_account=account)
        instance.financial_account = account  # Update in-memory instance
        
        # Log successful account creation to governance audit service
        AuditService.log_signal_operation(
            signal_name='supplier_account_creation',
            sender_model='Supplier',
            sender_id=instance.id,
            operation='ACCOUNT_CREATED',
            user=GovernanceContext.get_current_user(),
            supplier_name=instance.name,
            account_code=account.code,
            supplier_type=instance.primary_type.code if instance.primary_type else 'unknown'
        )
        
        action = "created" if created else "recovered"
        logger.info(
            f"✅ Financial account {account.code} {action} for supplier {instance.name} "
            f"automatically via post_save signal"
        )
        
    except Exception as e:
        # Log account creation failure
        try:
            AuditService.log_signal_operation(
                signal_name='supplier_account_creation',
                sender_model='Supplier',
                sender_id=instance.id,
                operation='ACCOUNT_CREATION_FAILED',
                user=GovernanceContext.get_current_user(),
                supplier_name=instance.name,
                error=str(e)
            )
            
            # Record violation in monitoring service
            monitoring_service.record_violation(
                violation_type='supplier_account_creation_failure',
                component='supplier',
                details={
                    'supplier_id': instance.id,
                    'supplier_name': instance.name,
                    'error': str(e)
                },
                user=GovernanceContext.get_current_user()
            )
        except Exception:
            pass  # تجنب أخطاء إضافية في الـ logging
        
        # نسجل الخطأ لكن لا نوقف العملية
        logger.error(f"❌ Failed to create financial account for supplier {instance.name}: {e}")


@governed_signal_handler(
    signal_name="delete_supplier_account",
    critical=True,
    description="حذف حساب المورد المحاسبي عند حذف المورد"
)
@receiver(post_delete, sender=Supplier)
def delete_supplier_account_signal(sender, instance, **kwargs):
    """
    حذف الحساب المحاسبي عند حذف المورد (اختياري)
    """
    if instance.financial_account:
        try:
            account_code = instance.financial_account.code
            instance.financial_account.delete()
            logger.info(f"تم حذف الحساب المحاسبي {account_code} للمورد {instance.name}")
        except Exception as e:
            logger.error(f"فشل حذف الحساب المحاسبي للمورد {instance.name}: {e}")




