"""
Thin Adapter Signals for Product/Stock Operations - Feature flag protected signal adapters.

These signals replace the heavy business logic signals with thin adapters that:
1. Route to orchestrator services instead of containing business logic
2. Are protected by feature flags for safe rollback
3. Follow signal independence principle (failures don't break writes)
4. Provide proper audit trails and monitoring

IMPORTANT: These signals are BEHIND FEATURE FLAGS and can be safely disabled.
"""

import logging
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.db import transaction

from ..models import StockMovement, Stock, Product
from governance.services import governance_switchboard, signal_router
from governance.models import GovernanceContext as GovContext
from governance.signal_integration import governed_signal_handler

logger = logging.getLogger(__name__)


# ==================== StockMovement Signals ====================

@governed_signal_handler(
    "stock_movement_orchestrator_adapter",
    critical=False,
    description="Thin adapter for StockMovement changes - routes to orchestrator service"
)
@receiver(post_save, sender=StockMovement)
def stock_movement_orchestrator_adapter(sender, instance, created, **kwargs):
    """
    Thin adapter for StockMovement changes - routes to orchestrator service.
    
    Replaces heavy business logic from:
    - product/signals.py:update_stock_on_movement
    
    FEATURE FLAG PROTECTED: Can be safely disabled via governance switchboard.
    """
    # Skip if this movement has the skip flag (to prevent double processing)
    if hasattr(instance, "_skip_update") and instance._skip_update:
        logger.debug(f"Skipping stock movement {instance.id} due to skip flag")
        return
    
    # Route through SignalRouter with governance controls
    routing_result = signal_router.route_signal(
        signal_name='stock_movement_change',
        sender=sender,
        instance=instance,
        critical=False,  # Non-critical - failure shouldn't break writes
        created=created
    )
    
    if routing_result['blocked']:
        return
    
    # Check workflow-specific feature flag
    if not governance_switchboard.is_workflow_enabled('stock_movement_to_journal_entry'):
        return
    
    # Route to orchestrator service (non-blocking)
    def process_stock_movement_orchestration():
        try:
            from ..services.stock_orchestrator_service import StockOrchestratorService
            
            result = StockOrchestratorService.handle_stock_movement_change(
                movement=instance,
                created=created,
                user=GovContext.get_current_user()
            )
            
            if result['success']:
                actions_count = len(result.get('actions_taken', []))
                
                # Log important events
                if result.get('negative_stock_prevented'):
                    logger.warning(f"Negative stock prevented for product {instance.product.id} in movement {instance.id}")
                
                    
            else:
                logger.warning(f"Stock movement orchestration failed for movement {instance.id}: {result.get('message', 'Unknown error')}")
                
        except Exception as e:
            # Signal failure must not break the main operation
            logger.error(f"Stock movement orchestration failed for movement {instance.id}: {e}")
            # Continue - signal independence principle
    
    # Execute after transaction commits to avoid blocking the main operation
    transaction.on_commit(process_stock_movement_orchestration)


@governed_signal_handler(
    "stock_movement_deletion_orchestrator_adapter",
    critical=False,
    description="Thin adapter for StockMovement deletion - routes to orchestrator service"
)
@receiver(post_delete, sender=StockMovement)
def stock_movement_deletion_orchestrator_adapter(sender, instance, **kwargs):
    """
    Thin adapter for StockMovement deletion - routes to orchestrator service.
    
    Replaces heavy business logic from:
    - product/signals.py:revert_stock_on_movement_delete
    
    FEATURE FLAG PROTECTED: Can be safely disabled via governance switchboard.
    """
    # Route through SignalRouter with governance controls
    routing_result = signal_router.route_signal(
        signal_name='stock_movement_deletion',
        sender=sender,
        instance=instance,
        critical=False,  # Non-critical - failure shouldn't break writes
    )
    
    if routing_result['blocked']:
        return
    
    # Check workflow-specific feature flag
    if not governance_switchboard.is_workflow_enabled('stock_movement_to_journal_entry'):
        return
    
    # Route to orchestrator service (non-blocking)
    def process_stock_movement_deletion_orchestration():
        try:
            from ..services.stock_orchestrator_service import StockOrchestratorService
            
            result = StockOrchestratorService.handle_stock_movement_deletion(
                movement=instance,
                user=GovContext.get_current_user()
            )
            
            if result['success']:
                actions_count = len(result.get('actions_taken', []))
            else:
                logger.warning(f"Stock movement deletion orchestration failed for movement {instance.id}: {result.get('message', 'Unknown error')}")
                
        except Exception as e:
            # Signal failure must not break the main operation
            logger.error(f"Stock movement deletion orchestration failed for movement {instance.id}: {e}")
            # Continue - signal independence principle
    
    # Execute after transaction commits to avoid blocking the main operation
    transaction.on_commit(process_stock_movement_deletion_orchestration)


# ==================== Product Management Signals ====================

@governed_signal_handler(
    "product_sku_generation_adapter",
    critical=False,
    description="Thin adapter for Product SKU generation with feature flag control"
)
@governed_signal_handler(
    signal_name="product_sku_generation_adapter",
    critical=False,
    description="محول إنشاء رمز المنتج مع التحكم في الميزة"
)
@receiver(pre_save, sender=Product)
def product_sku_generation_adapter(sender, instance, **kwargs):
    """
    Thin adapter for Product SKU generation.
    
    Replaces logic from:
    - product/signals.py:ensure_unique_sku
    
    This is already thin, but we wrap it for consistency and feature flag control.
    """
    # Route through SignalRouter with governance controls
    routing_result = signal_router.route_signal(
        signal_name='product_sku_generation',
        sender=sender,
        instance=instance,
        critical=False,  # Non-critical - failure shouldn't break writes
    )
    
    if routing_result['blocked']:
        return
    
    # Check component-level feature flag
    if not governance_switchboard.is_component_enabled('auto_sku_generation'):
        return
    
    # Execute SKU generation logic (this is already thin)
    if not instance.sku:
        from django.utils.text import slugify
        from django.utils import timezone
        
        timestamp = timezone.now().strftime("%y%m%d%H%M")
        base_slug = slugify(instance.name)[:10]
        instance.sku = f"{base_slug}-{timestamp}"
        
        logger.debug(f"Generated SKU for product {instance.id}: {instance.sku}")


@governed_signal_handler(
    "product_image_primary_adapter",
    critical=False,
    description="Thin adapter for ProductImage primary management with feature flag control"
)
@governed_signal_handler(
    signal_name="product_image_primary_adapter",
    critical=False,
    description="محول إدارة الصورة الأساسية للمنتج مع التحكم في الميزة"
)
@receiver(post_save, sender='product.ProductImage')
def product_image_primary_adapter(sender, instance, created, **kwargs):
    """
    Thin adapter for ProductImage primary image management.
    
    Replaces logic from:
    - product/signals.py:ensure_single_primary_image
    
    This is already thin, but we wrap it for consistency and feature flag control.
    """
    # Route through SignalRouter with governance controls
    routing_result = signal_router.route_signal(
        signal_name='product_image_primary',
        sender=sender,
        instance=instance,
        critical=False,  # Non-critical - failure shouldn't break writes
        created=created
    )
    
    if routing_result['blocked']:
        return
    
    # Check component-level feature flag
    if not governance_switchboard.is_component_enabled('auto_image_management'):
        return
    
    # Execute primary image logic (this is already thin)
    def process_primary_image_logic():
        try:
            from product.models import ProductImage
            
            if instance.is_primary:
                # Remove primary flag from other images
                ProductImage.objects.filter(
                    product=instance.product, 
                    is_primary=True
                ).exclude(pk=instance.pk).update(is_primary=False)
                
                logger.debug(f"Set primary image for product {instance.product.id}: image {instance.id}")
            else:
                # If no primary image exists, make this one primary
                if not ProductImage.objects.filter(
                    product=instance.product, 
                    is_primary=True
                ).exists():
                    instance.is_primary = True
                    instance.save(update_fields=['is_primary'])
                    
                    logger.debug(f"Auto-set primary image for product {instance.product.id}: image {instance.id}")
                    
        except Exception as e:
            # Signal failure must not break the main operation
            logger.error(f"Product image primary logic failed for image {instance.id}: {e}")
            # Continue - signal independence principle
    
    # Execute after transaction commits to avoid blocking the main operation
    transaction.on_commit(process_primary_image_logic)


# ==================== Signal Registration ====================

def register_thin_adapter_signals():
    """
    Register all thin adapter signals with the SignalRouter.
    
    This function should be called during app initialization to register
    all signal handlers with proper descriptions and criticality levels.
    """
    from governance.services.signal_router import register_signal_handler
    
    # Register StockMovement signals
    register_signal_handler(
        signal_name='stock_movement_change',
        handler=stock_movement_orchestrator_adapter,
        critical=False,
        description='Routes StockMovement changes to orchestrator service'
    )
    
    register_signal_handler(
        signal_name='stock_movement_deletion',
        handler=stock_movement_deletion_orchestrator_adapter,
        critical=False,
        description='Routes StockMovement deletions to orchestrator service'
    )
    
    # Register Product management signals
    register_signal_handler(
        signal_name='product_sku_generation',
        handler=product_sku_generation_adapter,
        critical=False,
        description='Handles automatic SKU generation for products'
    )
    
    register_signal_handler(
        signal_name='product_image_primary',
        handler=product_image_primary_adapter,
        critical=False,
        description='Manages primary image selection for products'
    )
    


# ==================== Migration Helper ====================

def enable_thin_adapter_signals():
    """
    Helper function to enable thin adapter signals via feature flags.
    
    This provides a programmatic way to enable the new signal system
    after validation and testing.
    """
    # Enable workflow flags
    governance_switchboard.enable_workflow('stock_movement_to_journal_entry')
    
    # Enable component flags
    governance_switchboard.enable_component('auto_sku_generation')
    governance_switchboard.enable_component('auto_image_management')
    


def disable_thin_adapter_signals():
    """
    Helper function to disable thin adapter signals via feature flags.
    
    This provides emergency rollback capability if issues are discovered.
    """
    # Disable workflow flags
    governance_switchboard.disable_workflow('stock_movement_to_journal_entry', 'Emergency rollback')
    
    # Disable component flags
    governance_switchboard.disable_component('auto_sku_generation', 'Emergency rollback')
    governance_switchboard.disable_component('auto_image_management', 'Emergency rollback')
    
    logger.warning("Product thin adapter signals disabled via governance switchboard - emergency rollback active")


def validate_signal_independence():
    """
    Validation function to test that write operations work with signals disabled.
    
    This should be called during testing to ensure signal independence.
    """
    
    # Temporarily disable all signals
    with signal_router.signals_disabled("Independence test"):
        try:
            # Test basic operations work without signals
            from ..models import Product, StockMovement
            
            # Test product creation
            test_product = Product.objects.create(
                name="Test Product",
                description="Test Description"
            )
            
            # Test stock movement creation
            test_movement = StockMovement.objects.create(
                product=test_product,
                movement_type='in',
                quantity=10,
                document_type='test',
                document_number='TEST-001',
                notes='Signal independence test'
            )
            
            # Clean up
            test_movement.delete()
            test_product.delete()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Signal independence test failed: {e}")
            return False