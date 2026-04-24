"""
Governed Product Signal Handlers - Phase 3.2 Migration
معالجات إشارات المنتجات المحكومة - هجرة المرحلة 3.2

This module converts product signals to use governance system with:
- @governed_signal_handler decorators
- Kill switches and audit logging
- Performance optimization with transaction.on_commit
- Comprehensive error handling
- Maintains existing functionality
"""

from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.db import transaction
from django.utils.text import slugify
from django.utils import timezone
from decimal import Decimal
import logging

from governance.signal_integration import governed_signal_handler, side_effect_handler, critical_signal_handler
from governance.services.audit_service import AuditService
from governance.models import GovernanceContext

from .models import StockMovement, Stock, Product, ProductImage

logger = logging.getLogger(__name__)

# Safe imports for enhanced models
try:
    from .models.inventory_movement import InventoryMovement
    from .services.inventory_service import InventoryService
    from core.services.notification_service import NotificationService
except ImportError:
    InventoryMovement = InventoryService = NotificationService = None


@governed_signal_handler(
    signal_name="product_sku_generation",
    critical=False,
    description="Generate unique SKU for products"
)
@receiver(pre_save, sender=Product)
def ensure_unique_sku_governed(sender, instance, **kwargs):
    """
    Governed handler: Ensure unique SKU generation for products
    التأكد من أن كود المنتج فريد وإنشاءه تلقائياً إذا لم يتم توفيره
    """
    if not instance.sku:
        # Generate unique product code from name and timestamp
        timestamp = timezone.now().strftime("%y%m%d%H%M")
        base_slug = slugify(instance.name)[:10]
        instance.sku = f"{base_slug}-{timestamp}"
        


@governed_signal_handler(
    signal_name="product_image_primary_management",
    critical=False,
    description="Manage primary product image constraints"
)
@receiver(post_save, sender=ProductImage)
def ensure_single_primary_image_governed(sender, instance, created, **kwargs):
    """
    Governed handler: Ensure single primary image per product
    التأكد من وجود صورة رئيسية واحدة فقط لكل منتج
    """
    if instance.is_primary:
        # If this image is set as primary, unset other primary images
        ProductImage.objects.filter(
            product=instance.product, 
            is_primary=True
        ).exclude(pk=instance.pk).update(is_primary=False)
        
    else:
        # If no primary image exists for product, set first image as primary
        if not ProductImage.objects.filter(
            product=instance.product, 
            is_primary=True
        ).exists():
            instance.is_primary = True
            instance.save()
            


@governed_signal_handler(
    signal_name="stock_movement_inventory_update",
    critical=True,
    description="Process stock movements and update inventory levels"
)
@receiver(post_save, sender=StockMovement)
def update_stock_on_movement_governed(sender, instance, created, **kwargs):
    """
    Governed handler: Update stock levels after stock movement
    تحديث المخزون بعد حفظ حركة المخزون بنجاح
    
    This is critical for inventory integrity
    
    ⚠️ DEPRECATION WARNING: StockMovement is being phased out.
    All new movements should use InventoryMovement instead.
    This signal is kept for backward compatibility only.
    """
    if not created:
        return
    
    # Skip if flagged to avoid double updates
    if hasattr(instance, "_skip_update") and instance._skip_update:
        return
    
    # Log deprecation warning
    import logging
    logger = logging.getLogger(__name__)
    logger.warning(
        f"⚠️ DEPRECATED: StockMovement {instance.id} created. "
        f"Please use InventoryMovement instead for new movements."
    )
    
    # Use transaction.on_commit for performance
    transaction.on_commit(
        lambda: _process_stock_movement(instance)
    )


def _process_stock_movement(stock_movement):
    """
    Process stock movement with comprehensive error handling and audit logging
    """
    try:
        # Get or create stock record
        stock, created_stock = Stock.objects.get_or_create(
            product=stock_movement.product,
            warehouse=stock_movement.warehouse,
            defaults={"quantity": Decimal("0")},
        )
        
        old_quantity = stock.quantity
        
        # Update stock based on movement type
        if stock_movement.movement_type in ["in", "return_in"]:
            stock.quantity += Decimal(stock_movement.quantity)
        elif stock_movement.movement_type in ["out", "return_out"]:
            stock.quantity = max(
                Decimal("0"), stock.quantity - Decimal(stock_movement.quantity)
            )
        elif stock_movement.movement_type == "transfer" and stock_movement.destination_warehouse:
            # Reduce stock from source warehouse
            stock.quantity = max(
                Decimal("0"), stock.quantity - Decimal(stock_movement.quantity)
            )
            
            # Increase stock in destination warehouse
            dest_stock, dest_created = Stock.objects.get_or_create(
                product=stock_movement.product,
                warehouse=stock_movement.destination_warehouse,
                defaults={"quantity": Decimal("0")},
            )
            dest_stock.quantity += Decimal(stock_movement.quantity)
            dest_stock.save()
            
            # Audit destination stock update
            AuditService.create_audit_record(
                model_name='Stock',
                object_id=dest_stock.id,
                operation='TRANSFER_IN',
                user=GovernanceContext.get_current_user(),
                source_service='ProductSignals',
                before_data={'quantity': str(dest_stock.quantity - Decimal(stock_movement.quantity))},
                after_data={'quantity': str(dest_stock.quantity)}
            )
            
        elif stock_movement.movement_type == "adjustment":
            stock.quantity = Decimal(stock_movement.quantity)
        
        # Save stock changes
        stock.save()
        
        # Audit stock update
        AuditService.create_audit_record(
            model_name='Stock',
            object_id=stock.id,
            operation=f'STOCK_{stock_movement.movement_type.upper()}',
            user=GovernanceContext.get_current_user(),
            source_service='ProductSignals',
            before_data={'quantity': str(old_quantity)},
            after_data={'quantity': str(stock.quantity)},
            additional_context={
                'movement_id': stock_movement.id,
                'movement_type': stock_movement.movement_type,
                'movement_quantity': str(stock_movement.quantity)
            }
        )
        
        
        # Check low stock alerts
        _check_low_stock_alerts(stock_movement.product, stock)
        
    except Exception as e:
        logger.error(f"Error processing stock movement {stock_movement.id}: {e}")
        
        # Audit error
        AuditService.create_audit_record(
            model_name='StockMovement',
            object_id=stock_movement.id,
            operation='STOCK_UPDATE_ERROR',
            user=GovernanceContext.get_current_user(),
            source_service='ProductSignals',
            additional_context={
                'error': str(e),
                'movement_type': stock_movement.movement_type
            }
        )
        raise


@governed_signal_handler(
    signal_name="stock_movement_revert_on_delete",
    critical=True,
    description="Revert stock changes when movement is deleted"
)
@receiver(post_delete, sender=StockMovement)
def revert_stock_on_movement_delete_governed(sender, instance, **kwargs):
    """
    Governed handler: Revert stock impact when movement is deleted
    إلغاء تأثير حركة المخزون عند حذفها
    """
    try:
        # Find related stock record
        stock = Stock.objects.get(
            product=instance.product, 
            warehouse=instance.warehouse
        )
        
        old_quantity = stock.quantity
        
        if instance.movement_type in ["in", "return_in"]:
            # Reverse addition - reduce stock
            stock.quantity = max(
                Decimal("0"), stock.quantity - Decimal(instance.quantity)
            )
        elif instance.movement_type in ["out", "return_out"]:
            # Reverse withdrawal - increase stock
            stock.quantity += Decimal(instance.quantity)
        elif instance.movement_type == "transfer":
            # Reverse transfer
            stock.quantity += Decimal(instance.quantity)
            
            # Handle destination warehouse if exists
            if instance.destination_warehouse:
                try:
                    dest_stock = Stock.objects.get(
                        product=instance.product,
                        warehouse=instance.destination_warehouse,
                    )
                    dest_stock.quantity = max(
                        Decimal("0"), dest_stock.quantity - Decimal(instance.quantity)
                    )
                    dest_stock.save()
                except Stock.DoesNotExist:
                    pass
        
        # Save stock changes
        stock.save()
        
        # Audit reversal
        AuditService.create_audit_record(
            model_name='Stock',
            object_id=stock.id,
            operation='STOCK_MOVEMENT_REVERSAL',
            user=GovernanceContext.get_current_user(),
            source_service='ProductSignals',
            before_data={'quantity': str(old_quantity)},
            after_data={'quantity': str(stock.quantity)},
            additional_context={
                'deleted_movement_id': instance.id,
                'movement_type': instance.movement_type
            }
        )
        
        
    except Stock.DoesNotExist:
        # If no stock record exists, nothing to revert
        logger.warning(f"No stock record found for product {instance.product.name} in warehouse {instance.warehouse.name}")


@governed_signal_handler(
    signal_name="handle_purchase_delete_governed",
    critical=False,
    description="معالجة حذف فاتورة المشتريات"
)
@receiver(post_delete, sender='purchase.Purchase')
def handle_purchase_delete_governed(sender, instance, **kwargs):
    """
    Governed handler: Handle purchase deletion
    معالجة حذف فاتورة المشتريات
    """
    # No sequential number reset on deletion (as per original logic)


@governed_signal_handler(
    signal_name="handle_stock_movement_delete_governed",
    critical=False,
    description="معالجة حذف حركة المخزون"
)
@receiver(post_delete, sender=StockMovement)
def handle_stock_movement_delete_governed(sender, instance, **kwargs):
    """
    Governed handler: Handle stock movement deletion
    معالجة حذف حركة المخزون
    """
    # No sequential number reset on deletion (as per original logic)


def _check_low_stock_alerts(product, stock):
    """
    Check and create low stock alerts with governance audit
    فحص وإنشاء تنبيهات المخزون المنخفض
    """
    try:
        # Enhanced system check
        if NotificationService:
            enhanced_stock = Stock.objects.filter(
                product=product, 
                warehouse=stock.warehouse
            ).first()
            
            if enhanced_stock and hasattr(enhanced_stock, 'is_low_stock') and enhanced_stock.is_low_stock:
                _create_low_stock_alert(product, enhanced_stock)
        
        # Legacy system check
        elif product.min_stock > 0 and stock.quantity <= product.min_stock:
            _create_legacy_low_stock_alert(product, stock)
            
    except Exception as e:
        logger.error(f"Error checking low stock alerts for product {product.name}: {e}")


def _create_low_stock_alert(product, stock):
    """
    Create low stock alert for enhanced system
    إنشاء تنبيه مخزون منخفض للنظام المحسن
    """
    if not NotificationService:
        return
    
    try:
        from django.contrib.auth import get_user_model
        from django.db import models
        
        User = get_user_model()
        
        # Get authorized users
        authorized_users = User.objects.filter(
            models.Q(groups__name__in=["مدير مخزون", "مدير", "Admin"])
            | models.Q(is_superuser=True),
            is_active=True,
        ).distinct()
        
        # Determine alert type
        if hasattr(stock, 'is_out_of_stock') and stock.is_out_of_stock:
            alert_type = "نفذ"
            notification_type = "danger"
        else:
            alert_type = "منخفض"
            notification_type = "warning"
        
        title = f"تنبيه مخزون {alert_type}: {product.name}"
        message = (
            f"المنتج '{product.name}' في المخزن '{stock.warehouse.name}' {alert_type}.\n"
            f"الكمية الحالية: {stock.quantity} {product.unit.symbol}\n"
            f"الحد الأدنى: {stock.min_stock_level} {product.unit.symbol}\n"
            f"يُرجى إعادة التزويد فوراً."
        )
        
        # Create notifications for authorized users
        for user in authorized_users:
            NotificationService.create_notification(
                user=user,
                title=title,
                message=message,
                notification_type=notification_type,
                related_model="Product",
                related_id=product.id,
                link_url=f"/products/{product.id}/"
            )
        
        # Audit alert creation
        AuditService.create_audit_record(
            model_name='Product',
            object_id=product.id,
            operation='LOW_STOCK_ALERT_CREATED',
            user=GovernanceContext.get_current_user(),
            source_service='ProductSignals',
            additional_context={
                'alert_type': alert_type,
                'current_quantity': str(stock.quantity),
                'min_stock_level': str(stock.min_stock_level),
                'warehouse': stock.warehouse.name,
                'notification_count': authorized_users.count()
            }
        )
        
        
    except Exception as e:
        logger.error(f"Error creating enhanced low stock alert for product {product.name}: {e}")


def _create_legacy_low_stock_alert(product, stock):
    """
    Create low stock alert for legacy system
    إنشاء تنبيه مخزون منخفض للنظام القديم
    """
    try:
        from django.contrib.auth import get_user_model
        from django.db import models
        from core.models import Notification
        
        User = get_user_model()
        
        # Get authorized users
        authorized_users = User.objects.filter(
            models.Q(groups__name__in=["مدير مخزون", "مدير", "Admin"])
            | models.Q(is_superuser=True),
            is_active=True,
        ).distinct()
        
        # Determine alert type
        if stock.quantity == 0:
            alert_type = "نفذ"
            notification_type = "danger"
        else:
            alert_type = "منخفض"
            notification_type = "warning"
        
        title = f"تنبيه مخزون {alert_type}: {product.name}"
        message = (
            f"المنتج '{product.name}' {alert_type} في المخزون.\n"
            f"الكمية الحالية: {stock.quantity} {product.unit.symbol}\n"
            f"الحد الأدنى: {product.min_stock} {product.unit.symbol}\n"
            f"يُرجى إعادة التزويد فوراً."
        )
        
        # Create notifications for authorized users
        for user in authorized_users:
            Notification.objects.create(
                user=user, 
                title=title, 
                message=message, 
                type=notification_type
            )
        
        # Audit alert creation
        AuditService.create_audit_record(
            model_name='Product',
            object_id=product.id,
            operation='LEGACY_LOW_STOCK_ALERT_CREATED',
            user=GovernanceContext.get_current_user(),
            source_service='ProductSignals',
            additional_context={
                'alert_type': alert_type,
                'current_quantity': str(stock.quantity),
                'min_stock': str(product.min_stock),
                'notification_count': authorized_users.count()
            }
        )
        
        
    except Exception as e:
        logger.error(f"Error creating legacy low stock alert for product {product.name}: {e}")


# Enhanced inventory movement signal (if available)
if InventoryMovement:
    @governed_signal_handler(
        signal_name="handle_enhanced_inventory_movement_governed",
        critical=True,
        description="معالجة حركات المخزون المحسنة مع تنبيهات فورية"
    )
    @receiver(post_save, sender=InventoryMovement)
    def handle_enhanced_inventory_movement_governed(sender, instance, created, **kwargs):
        """
        Governed handler: Enhanced inventory movement processing
        معالجة حركات المخزون المحسنة مع تنبيهات فورية
        """
        # تشغيل عند الإنشاء المعتمد أو عند الاعتماد
        if instance.is_approved:
            try:
                stock = Stock.objects.get(
                    product=instance.product, 
                    warehouse=instance.warehouse
                )
                
                if (hasattr(stock, 'is_low_stock') and stock.is_low_stock) or \
                   (hasattr(stock, 'is_out_of_stock') and stock.is_out_of_stock):
                    _create_low_stock_alert(instance.product, stock)
                
                # Audit enhanced movement
                AuditService.create_audit_record(
                    model_name='InventoryMovement',
                    object_id=instance.id,
                    operation='ENHANCED_INVENTORY_PROCESSED',
                    user=GovernanceContext.get_current_user(),
                    source_service='ProductSignals',
                    additional_context={
                        'product_name': instance.product.name,
                        'warehouse': instance.warehouse.name,
                        'is_approved': instance.is_approved
                    }
                )
                
            except Stock.DoesNotExist:
                logger.warning(f"No stock record found for enhanced inventory movement {instance.id}")
            except Exception as e:
                logger.error(f"Error processing enhanced inventory movement {instance.id}: {e}")