"""
إشارات التفعيل التلقائي لموديول Governance
Auto-activation signals for Governance module

يتم تفعيل Governance تلقائياً بعد:
1. تطبيق الهجرات (post_migrate)
2. إنشاء مستخدم جديد (post_save User)
3. بدء تشغيل Django (ready)
"""

import logging
from django.db.models.signals import post_migrate, post_save
from django.contrib.auth.signals import user_logged_in
from django.contrib.auth import get_user_model
from django.dispatch import receiver
from django.apps import apps
from django.core.management import call_command
from django.db import transaction

# Governance integration
from governance.signal_integration import governed_signal_handler

logger = logging.getLogger(__name__)

@governed_signal_handler(
    signal_name="auto_activate_governance_after_migrate",
    critical=True,
    description="تفعيل Governance تلقائياً بعد تطبيق الهجرات"
)
@receiver(post_migrate)
def auto_activate_governance_after_migrate(sender, **kwargs):
    """
    تفعيل Governance تلقائياً بعد تطبيق الهجرات
    Auto-activate Governance after migrations
    """
    
    # التأكد أن هذا تطبيق governance أو تطبيق رئيسي
    if sender.name not in ['governance', 'core', 'users']:
        return
    
    try:
        # التأكد من وجود جداول governance
        from governance.models import GovernanceContext
        
        # محاولة الوصول للجدول للتأكد من وجوده
        GovernanceContext.objects.exists()
        
        logger.info("🚀 تفعيل Governance تلقائياً بعد migrate...")
        
        # استدعاء أمر التفعيل
        call_command('activate_governance', '--silent')
        
        logger.info("✅ تم تفعيل Governance تلقائياً بعد migrate")
        
    except Exception as e:
        # تجاهل الأخطاء في المراحل المبكرة من الهجرة
        logger.debug(f"تم تخطي تفعيل Governance التلقائي: {e}")

@governed_signal_handler(
    signal_name="auto_activate_governance_on_first_user",
    critical=True,
    description="تفعيل Governance عند إنشاء أول مستخدم superuser"
)
@receiver(post_save, sender=get_user_model())
def auto_activate_governance_on_first_user(sender, instance, created, **kwargs):
    """
    تفعيل Governance عند إنشاء أول مستخدم superuser
    Auto-activate Governance when first superuser is created
    """
    
    if not created or not instance.is_superuser:
        return
    
    try:
        # التحقق من عدد المستخدمين الـ superuser
        User = get_user_model()
        superuser_count = User.objects.filter(is_superuser=True).count()
        
        # إذا كان هذا أول أو ثاني superuser، فعل Governance
        if superuser_count <= 2:
            logger.info(f"🚀 تفعيل Governance تلقائياً لأول superuser: {instance.username}")
            
            # استدعاء أمر التفعيل
            call_command('activate_governance', '--silent')
            
            logger.info("✅ تم تفعيل Governance تلقائياً لأول superuser")
            
    except Exception as e:
        logger.warning(f"فشل تفعيل Governance التلقائي لأول مستخدم: {e}")

@governed_signal_handler(
    signal_name="check_governance_on_admin_login",
    critical=False,
    description="فحص Governance عند تسجيل دخول المدير"
)
@receiver(user_logged_in)
def check_governance_on_admin_login(sender, request, user, **kwargs):
    """
    فحص Governance عند تسجيل دخول المدير
    Check Governance when admin logs in
    """
    
    if not user.is_superuser:
        return
    
    try:
        from governance.services import governance_switchboard
        
        # فحص سريع للحالة
        stats = governance_switchboard.get_governance_statistics()
        
        # إذا كانت المكونات الحرجة معطلة، فعلها
        critical_components = [
            'accounting_gateway_enforcement',
            'admin_lockdown_enforcement',
            'authority_boundary_enforcement'
        ]
        
        disabled_critical = [
            comp for comp in critical_components
            if comp not in stats['components']['enabled_list']
        ]
        
        if disabled_critical:
            logger.warning(f"🔴 مكونات Governance حرجة معطلة عند دخول {user.username}: {disabled_critical}")
            
            # محاولة التفعيل التلقائي
            try:
                call_command('activate_governance', '--silent')
                logger.info(f"✅ تم تفعيل Governance تلقائياً عند دخول {user.username}")
            except Exception as e:
                logger.error(f"فشل التفعيل التلقائي عند دخول {user.username}: {e}")
        
    except Exception as e:
        logger.debug(f"تم تخطي فحص Governance عند دخول {user.username}: {e}")

class GovernanceAutoActivation:
    """
    فئة مساعدة للتفعيل التلقائي
    Helper class for auto-activation
    """
    
    @staticmethod
    def ensure_governance_active():
        """
        ضمان تفعيل Governance
        Ensure Governance is active
        """
        try:
            from governance.services import governance_switchboard
            
            # فحص المكونات الحرجة
            critical_components = [
                'accounting_gateway_enforcement',
                'movement_service_enforcement',
                'admin_lockdown_enforcement',
                'authority_boundary_enforcement',
                'audit_trail_enforcement',
                'idempotency_enforcement'
            ]
            
            needs_activation = False
            for component in critical_components:
                if not governance_switchboard.is_component_enabled(component):
                    needs_activation = True
                    break
            
            if needs_activation:
                logger.info("🚀 تفعيل Governance مطلوب...")
                call_command('activate_governance', '--silent')
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"خطأ في ضمان تفعيل Governance: {e}")
            return False
    
    @staticmethod
    def is_governance_healthy():
        """
        فحص صحة Governance
        Check Governance health
        """
        try:
            from governance.services import governance_switchboard
            
            stats = governance_switchboard.get_governance_statistics()
            
            # المكونات الحرجة
            critical_components = [
                'accounting_gateway_enforcement',
                'movement_service_enforcement',
                'admin_lockdown_enforcement',
                'authority_boundary_enforcement',
                'audit_trail_enforcement',
                'idempotency_enforcement'
            ]
            
            # سير العمل الحرج
            critical_workflows = [
                'customer_payment_to_journal_entry',
                'stock_movement_to_journal_entry',
                'purchase_payment_to_journal_entry',
                'admin_direct_edit_prevention',
                'cross_service_validation',
                'audit_logging',
                'duplicate_operation_prevention'
            ]
            
            enabled_components = stats['components']['enabled_list']
            enabled_workflows = stats['workflows']['enabled_list']
            
            # فحص المكونات
            missing_components = [
                comp for comp in critical_components
                if comp not in enabled_components
            ]
            
            # فحص سير العمل
            missing_workflows = [
                workflow for workflow in critical_workflows
                if workflow not in enabled_workflows
            ]
            
            # فحص حالات الطوارئ
            emergency_active = stats['emergency']['active'] > 0
            
            return {
                'healthy': len(missing_components) == 0 and len(missing_workflows) == 0 and not emergency_active,
                'missing_components': missing_components,
                'missing_workflows': missing_workflows,
                'emergency_active': emergency_active,
                'emergency_list': stats['emergency']['active_list'] if emergency_active else []
            }
            
        except Exception as e:
            logger.error(f"خطأ في فحص صحة Governance: {e}")
            return {
                'healthy': False,
                'error': str(e)
            }