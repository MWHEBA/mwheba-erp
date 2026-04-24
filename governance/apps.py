from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)


class GovernanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "governance"
    
    def ready(self):
        """
        Initialize governance system when Django starts.
        
        ✅ PERFORMANCE: Simplified startup - minimal DB queries
        """
        # Only run during normal Django startup, not during migrations
        import sys
        if 'migrate' in sys.argv or 'makemigrations' in sys.argv:
            return
            
        try:
            # ✅ PERFORMANCE: Skip AuthorityService validation (heavy operation)
            # This validation is deferred to runtime when actually needed
            pass
            
            # Initialize payroll signal adapters
            try:
                from .signals import payroll_signals
            except ImportError as e:
                logger.warning(f"Could not initialize payroll signal adapters: {e}")
            except Exception as e:
                logger.error(f"Payroll signal adapter initialization failed: {e}", exc_info=True)
            
            # Initialize auto-activation signals
            try:
                from .signals import auto_activation
            except ImportError as e:
                logger.warning(f"Could not initialize auto-activation signals: {e}")
            except Exception as e:
                logger.error(f"Auto-activation signal initialization failed: {e}", exc_info=True)
            
            # Initialize security signals
            try:
                from .signals import security_signals
                from .middleware import security_middleware
            except Exception as e:
                logger.warning(f"Could not initialize security signals: {e}")
            
            # ✅ PERFORMANCE: Lightweight health check (no heavy DB queries)
            try:
                from .signals.auto_activation import GovernanceAutoActivation
                
                # فحص صحة Governance (lightweight - in-memory only)
                health = GovernanceAutoActivation.is_governance_healthy()
                
                if not health.get('healthy', False):
                    logger.warning("🔴 Governance غير صحي عند بدء التشغيل")
                    
                    # محاولة التفعيل التلقائي (lightweight)
                    if GovernanceAutoActivation.ensure_governance_active():
                        pass
                    else:
                        logger.warning("⚠️ فشل التفعيل التلقائي لـ Governance عند بدء التشغيل")
                    
            except Exception as e:
                logger.warning(f"فشل فحص/تفعيل Governance عند بدء التشغيل: {e}")
                
        except ImportError as e:
            logger.warning(f"Could not initialize governance system: {e}")
        except Exception as e:
            logger.error(f"Governance system initialization failed: {e}", exc_info=True)
