"""
Product Signal Handlers - Governed Low-Risk Signals (Phase 3.2)
معالجات إشارات المنتجات - إشارات منخفضة المخاطر محكومة

This module has been migrated to use governance system with:
- @governed_signal_handler decorators for all handlers
- Kill switches and audit logging capabilities
- Performance optimization with transaction.on_commit
- Comprehensive error handling and logging
- Maintains backward compatibility

Migration Status: Phase 3.2 - Low-Risk Signal Processing ✅
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
from governance.services import signal_router, governance_switchboard
from governance.services.monitoring_service import monitoring_service
from governance.models import GovernanceContext

from .models import StockMovement, Stock, Product, ProductImage
from purchase.models import Purchase

logger = logging.getLogger(__name__)

# استيراد آمن للنماذج المحسنة
try:
    from .models.inventory_movement import InventoryMovement
    from .services.inventory_service import InventoryService
    from core.services.notification_service import NotificationService
except ImportError:
    InventoryMovement = InventoryService = NotificationService = None


@governed_signal_handler(
    "product_sku_generation",
    critical=False,
    description="Generate unique SKU for products automatically"
)
@receiver(pre_save, sender=Product)
def ensure_unique_sku(sender, instance, **kwargs):
    """
    التأكد من أن الـ كود المنتج فريد وإنشاءه تلقائيًا إذا لم يتم توفيره
    Governed handler: Ensures unique product SKU generation
    """
    # Route through governance signal_router with workflow control
    routing_result = signal_router.route_signal(
        signal_name='product_sku_generation',
        sender=sender,
        instance=instance,
        critical=False
    )
    
    # Check if governance allows this operation
    if not governance_switchboard.is_workflow_enabled('audit_logging'):
        logger.debug("Product SKU generation disabled by governance - skipping")
        return
    
    if routing_result['blocked']:
        monitoring_service.record_violation(
            violation_type='product_sku_generation_blocked',
            component='product',
            details={
                'product_id': getattr(instance, 'id', None),
                'product_name': instance.name,
                'block_reason': routing_result['block_reason']
            }
        )
        return
    
    if not instance.sku:
        # إنشاء كود المنتج فريد من اسم المنتج والوقت
        timestamp = timezone.now().strftime("%y%m%d%H%M")
        base_slug = slugify(instance.name)[:10]
        instance.sku = f"{base_slug}-{timestamp}"
        


@governed_signal_handler(
    "product_image_primary_management",
    critical=False,
    description="Manage primary product image constraints"
)
@receiver(post_save, sender=ProductImage)
def ensure_single_primary_image(sender, instance, created, **kwargs):
    """
    التأكد من وجود صورة رئيسية واحدة فقط لكل منتج
    Governed handler: Ensures single primary image per product
    """
    # Route through governance signal_router with workflow control
    routing_result = signal_router.route_signal(
        signal_name='product_image_primary_management',
        sender=sender,
        instance=instance,
        critical=False,
        created=created
    )
    
    # Check if governance allows this operation
    if not governance_switchboard.is_workflow_enabled('audit_logging'):
        logger.debug("Product image management disabled by governance - skipping")
        return
    
    if routing_result['blocked']:
        monitoring_service.record_violation(
            violation_type='product_image_management_blocked',
            component='product',
            details={
                'image_id': instance.id,
                'product_id': instance.product.id,
                'product_name': instance.product.name,
                'block_reason': routing_result['block_reason']
            }
        )
        return
    
    if instance.is_primary:
        # إذا تم تعيين هذه الصورة كصورة رئيسية، قم بإلغاء تعيين أي صور أخرى كصور رئيسية
        ProductImage.objects.filter(product=instance.product, is_primary=True).exclude(
            pk=instance.pk
        ).update(is_primary=False)
        
    else:
        # إذا لم تكن هناك صورة رئيسية للمنتج، قم بتعيين أول صورة كصورة رئيسية
        if not ProductImage.objects.filter(
            product=instance.product, is_primary=True
        ).exists():
            instance.is_primary = True
            instance.save()
            


@governed_signal_handler(
    signal_name="stock_movement_processing",
    critical=True,
    description="Process stock movements and update inventory levels"
)
# DISABLED: This signal is replaced by thin_adapter_signals.stock_movement_orchestrator_adapter
# The old signal was causing duplicate stock updates (both this and the orchestrator were updating stock)
# @receiver(post_save, sender=StockMovement)
def update_stock_on_movement_DISABLED(sender, instance, created, **kwargs):
    """
    تحديث المخزون بعد حفظ حركة المخزون بنجاح

    هذا هو المكان الصحيح لتحديث المخزون (Django Best Practice)
    Signal يضمن تحديث المخزون فقط بعد حفظ الحركة بنجاح
    
    Governed critical handler: Updates stock levels after successful movement save
    
    DISABLED: Replaced by product/signals/thin_adapter_signals.py:stock_movement_orchestrator_adapter
    """
    if not created:
        return
        
    # تحقق من flag لتجنب التحديث المزدوج
    if hasattr(instance, "_skip_update") and instance._skip_update:
        logger.debug(f"Skipping stock update for movement {instance.id} due to skip flag")
        return

    # Route through governance signal_router with kill switch support
    routing_result = signal_router.route_signal(
        signal_name='stock_movement_processing',
        sender=sender,
        instance=instance,
        critical=True,
        created=created
    )
    
    # Check if governance allows this operation
    if not governance_switchboard.is_workflow_enabled('stock_movement_to_journal_entry'):
        logger.warning("Stock movement processing disabled by governance - skipping stock update")
        monitoring_service.record_violation(
            violation_type='stock_movement_processing_disabled',
            component='product',
            details={
                'movement_id': instance.id,
                'product_id': instance.product.id,
                'movement_type': instance.movement_type,
                'quantity': str(instance.quantity)
            }
        )
        return
    
    if routing_result['blocked']:
        logger.error(f"Critical stock movement processing blocked: {routing_result['block_reason']}")
        monitoring_service.record_violation(
            violation_type='critical_stock_movement_blocked',
            component='product',
            details={
                'movement_id': instance.id,
                'product_id': instance.product.id,
                'block_reason': routing_result['block_reason'],
                'movement_type': instance.movement_type
            }
        )
        # For critical signals, we still need to process to maintain data integrity
        logger.warning("Processing critical stock movement despite governance block")

    # Use transaction.on_commit for performance optimization
    transaction.on_commit(
        lambda: _process_stock_movement_update(instance)
    )


def _process_stock_movement_update(stock_movement):
    """
    Process stock movement update with comprehensive error handling and audit logging
    """
    try:
        # الحصول على المخزون الحالي أو إنشاء واحد جديد
        stock, created_stock = Stock.objects.get_or_create(
            product=stock_movement.product,
            warehouse=stock_movement.warehouse,
            defaults={"quantity": Decimal("0")},
        )

        old_quantity = stock.quantity

        # تحديث المخزون بناءً على نوع الحركة
        if stock_movement.movement_type in ["in", "return_in"]:
            stock.quantity += Decimal(stock_movement.quantity)
        elif stock_movement.movement_type in ["out", "return_out"]:
            stock.quantity = max(
                Decimal("0"), stock.quantity - Decimal(stock_movement.quantity)
            )
        elif stock_movement.movement_type == "transfer" and stock_movement.destination_warehouse:
            # خفض المخزون من المخزن المصدر
            stock.quantity = max(
                Decimal("0"), stock.quantity - Decimal(stock_movement.quantity)
            )

            # زيادة المخزون في المخزن الوجهة
            dest_stock, dest_created = Stock.objects.get_or_create(
                product=stock_movement.product,
                warehouse=stock_movement.destination_warehouse,
                defaults={"quantity": Decimal("0")},
            )
            dest_stock.quantity += Decimal(stock_movement.quantity)
            # استخدام update_fields لتجنب circular signal calls
            dest_stock.save(update_fields=['quantity'])
            
            # Audit destination stock update
            AuditService.create_audit_record(
                model_name='Stock',
                object_id=dest_stock.id,
                operation='TRANSFER_IN',
                user=GovernanceContext.get_current_user(),
                source_service='ProductSignals',
                before_data={'quantity': str(dest_stock.quantity - Decimal(stock_movement.quantity))},
                after_data={'quantity': str(dest_stock.quantity)},
                additional_context={
                    'movement_id': stock_movement.id,
                    'warehouse': stock_movement.destination_warehouse.name
                }
            )
            
        elif stock_movement.movement_type == "adjustment":
            stock.quantity = Decimal(stock_movement.quantity)

        # حفظ التغييرات بدون trigger للـ signals
        # استخدام update_fields لتجنب circular signal calls
        stock.save(update_fields=['quantity'])
        
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
                'movement_quantity': str(stock_movement.quantity),
                'warehouse': stock_movement.warehouse.name
            }
        )


        # فحص تنبيهات المخزون المنخفض للنظام المحسن
        if NotificationService:
            try:
                # البحث عن Stock المحسن
                enhanced_stock = Stock.objects.filter(
                    product=stock_movement.product, warehouse=stock_movement.warehouse
                ).first()

                if enhanced_stock and enhanced_stock.is_low_stock:
                    # إنشاء تنبيه فوري
                    _create_low_stock_alert(stock_movement.product, enhanced_stock)
            except Exception as e:
                # تسجيل الخطأ بدون إيقاف العملية
                logger.error(f"Error checking enhanced low stock alert: {e}")

        # فحص تنبيهات المخزون للنظام القديم
        elif (
            stock_movement.product.min_stock > 0
            and stock.quantity <= stock_movement.product.min_stock
        ):
            _create_legacy_low_stock_alert(stock_movement.product, stock)
            
    except Exception as e:
        logger.error(f"Error processing stock movement {stock_movement.id}: {e}")
        
        # Record violation in monitoring service
        monitoring_service.record_violation(
            violation_type='stock_movement_processing_error',
            component='product',
            details={
                'movement_id': stock_movement.id,
                'product_id': stock_movement.product.id,
                'movement_type': stock_movement.movement_type,
                'error': str(e)
            }
        )
        
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
    signal_name="revert_stock_on_movement_delete",
    critical=True,
    description="إرجاع تغييرات المخزون عند حذف الحركة"
)
@receiver(post_delete, sender=StockMovement)
def revert_stock_on_movement_delete(sender, instance, **kwargs):
    """
    إلغاء تأثير حركة المخزون عند حذفها
    Governed critical handler: Reverts stock impact when movement is deleted
    """
    # Route through governance signal_router with kill switch support
    routing_result = signal_router.route_signal(
        signal_name='stock_movement_reversal',
        sender=sender,
        instance=instance,
        critical=True
    )
    
    # Check if governance allows this operation
    if not governance_switchboard.is_workflow_enabled('stock_movement_to_journal_entry'):
        logger.warning("Stock movement reversal disabled by governance - skipping reversal")
        monitoring_service.record_violation(
            violation_type='stock_movement_reversal_disabled',
            component='product',
            details={
                'movement_id': instance.id,
                'product_id': instance.product.id,
                'movement_type': instance.movement_type,
                'quantity': str(instance.quantity)
            }
        )
        return
    
    if routing_result['blocked']:
        logger.error(f"Critical stock movement reversal blocked: {routing_result['block_reason']}")
        monitoring_service.record_violation(
            violation_type='critical_stock_reversal_blocked',
            component='product',
            details={
                'movement_id': instance.id,
                'product_id': instance.product.id,
                'block_reason': routing_result['block_reason'],
                'movement_type': instance.movement_type
            }
        )
        # For critical signals, we still need to process to maintain data integrity
        logger.warning("Processing critical stock reversal despite governance block")
    
    try:
        # البحث عن سجل المخزون المرتبط
        stock = Stock.objects.get(
            product=instance.product, warehouse=instance.warehouse
        )

        old_quantity = stock.quantity

        if instance.movement_type in ["in", "return_in"]:
            # إلغاء تأثير الإضافة - خفض المخزون
            stock.quantity = max(
                Decimal("0"), stock.quantity - Decimal(instance.quantity)
            )
        elif instance.movement_type in ["out", "return_out"]:
            # إلغاء تأثير السحب - زيادة المخزون
            stock.quantity += Decimal(instance.quantity)
        elif instance.movement_type == "transfer":
            # إلغاء تأثير التحويل
            stock.quantity += Decimal(instance.quantity)

            # معالجة المخزن المستلم إذا كان موجودًا
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
                    
                    # Audit destination stock reversal
                    AuditService.create_audit_record(
                        model_name='Stock',
                        object_id=dest_stock.id,
                        operation='TRANSFER_REVERSAL',
                        user=GovernanceContext.get_current_user(),
                        source_service='ProductSignals',
                        before_data={'quantity': str(dest_stock.quantity + Decimal(instance.quantity))},
                        after_data={'quantity': str(dest_stock.quantity)},
                        additional_context={
                            'deleted_movement_id': instance.id,
                            'warehouse': instance.destination_warehouse.name
                        }
                    )
                    
                except Stock.DoesNotExist:
                    logger.warning(f"Destination stock not found for transfer reversal: movement {instance.id}")

        # حفظ التغييرات على المخزون
        stock.save()
        
        # Audit stock reversal
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
                'movement_type': instance.movement_type,
                'warehouse': instance.warehouse.name
            }
        )
        
        
    except Stock.DoesNotExist:
        # إذا لم يكن هناك سجل مخزون، فلا يوجد شيء للتعديل
        logger.warning(f"No stock record found for product {instance.product.name} in warehouse {instance.warehouse.name}")


# @receiver(post_delete, sender=Sale)  # تم تعطيل المبيعات
# def handle_sale_delete(sender, instance, **kwargs):
#     """
#     معالجة حذف فاتورة المبيعات
#     """
#     # لا نقوم بإعادة تعيين الرقم التسلسلي عند الحذف
#     pass


@side_effect_handler(
    "purchase_deletion_cleanup",
    "Handle purchase deletion cleanup"
)
@receiver(post_delete, sender=Purchase)
def handle_purchase_delete(sender, instance, **kwargs):
    """
    معالجة حذف فاتورة المشتريات
    Governed side effect handler: Handles purchase deletion
    """
    # Route through governance signal_router
    routing_result = signal_router.route_signal(
        signal_name='purchase_deletion_cleanup',
        sender=sender,
        instance=instance,
        critical=False
    )
    
    # Check if governance allows this operation
    if not governance_switchboard.is_workflow_enabled('audit_logging'):
        logger.debug("Purchase deletion cleanup disabled by governance - skipping")
        return
    
    if routing_result['blocked']:
        monitoring_service.record_violation(
            violation_type='purchase_deletion_cleanup_blocked',
            component='product',
            details={
                'purchase_id': instance.id,
                'block_reason': routing_result['block_reason']
            }
        )
        return
    
    # لا نقوم بإعادة تعيين الرقم التسلسلي عند الحذف


@side_effect_handler(
    "stock_movement_deletion_cleanup",
    "Handle stock movement deletion cleanup"
)
@governed_signal_handler(
    signal_name="handle_stock_movement_delete",
    critical=True,
    description="معالجة حذف حركة المخزون وتنظيف البيانات"
)
@receiver(post_delete, sender=StockMovement)
def handle_stock_movement_delete(sender, instance, **kwargs):
    """
    معالجة حذف حركة المخزون
    Governed side effect handler: Handles stock movement deletion
    """
    # Route through governance signal_router
    routing_result = signal_router.route_signal(
        signal_name='stock_movement_deletion_cleanup',
        sender=sender,
        instance=instance,
        critical=False
    )
    
    # Check if governance allows this operation
    if not governance_switchboard.is_workflow_enabled('audit_logging'):
        logger.debug("Stock movement deletion cleanup disabled by governance - skipping")
        return
    
    if routing_result['blocked']:
        monitoring_service.record_violation(
            violation_type='stock_movement_deletion_cleanup_blocked',
            component='product',
            details={
                'movement_id': instance.id,
                'product_id': instance.product.id,
                'block_reason': routing_result['block_reason']
            }
        )
        return
    
    # لا نقوم بإعادة تعيين الرقم التسلسلي عند الحذف


def _create_low_stock_alert(product, stock):
    """
    إنشاء تنبيه مخزون منخفض للنظام المحسن
    Create low stock alert for enhanced system with governance audit
    """
    if not NotificationService:
        return

    try:
        from django.contrib.auth import get_user_model
        from django.db import models

        User = get_user_model()

        # الحصول على المستخدمين المخولين
        authorized_users = User.objects.filter(
            models.Q(groups__name__in=["مدير مخزون", "مدير", "Admin"])
            | models.Q(is_superuser=True),
            is_active=True,
        ).distinct()

        # تحديد نوع التنبيه
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

        # إنشاء تنبيه لجميع المستخدمين المخولين
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
    إنشاء تنبيه مخزون منخفض للنظام القديم
    Create low stock alert for legacy system with governance audit
    """
    try:
        from django.contrib.auth import get_user_model
        from django.db import models
        from core.models import Notification

        User = get_user_model()

        # الحصول على المستخدمين المخولين
        authorized_users = User.objects.filter(
            models.Q(groups__name__in=["مدير مخزون", "مدير", "Admin"])
            | models.Q(is_superuser=True),
            is_active=True,
        ).distinct()

        # تحديد نوع التنبيه
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

        # إنشاء تنبيه لجميع المستخدمين المخولين
        for user in authorized_users:
            Notification.objects.create(
                user=user, title=title, message=message, type=notification_type
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


# Signal للنظام المحسن
if InventoryMovement:

    @governed_signal_handler(
        signal_name="handle_enhanced_inventory_movement",
        critical=False,
        description="معالجة حركات المخزون المحسنة مع تنبيهات فورية"
    )
    @receiver(post_save, sender=InventoryMovement)
    def handle_enhanced_inventory_movement(sender, instance, created, **kwargs):
        """
        معالجة حركات المخزون المحسنة مع تنبيهات فورية
        Governed side effect handler: Enhanced inventory movement processing
        """
        # تشغيل عند الإنشاء المعتمد أو عند الاعتماد
        if not instance.is_approved:
            return
        
        # تسجيل الحركة في StockMovement
        try:
            # التحقق من عدم وجود حركة مسجلة مسبقاً
            existing_movement = StockMovement.objects.filter(
                product=instance.product,
                warehouse=instance.warehouse,
                movement_type=instance.movement_type,
                quantity=instance.quantity,
                reference=instance.movement_number
            ).first()
            
            if not existing_movement:
                StockMovement.objects.create(
                    product=instance.product,
                    warehouse=instance.warehouse,
                    movement_type=instance.movement_type,
                    quantity=instance.quantity,
                    unit_cost=instance.unit_cost,
                    total_cost=instance.total_cost,
                    reference=instance.movement_number,
                    notes=f'{instance.get_voucher_type_display()} - {instance.get_purpose_type_display() if instance.purpose_type else ""}',
                    created_by=instance.approved_by
                )
        except Exception as e:
            logger.error(f"Error creating StockMovement for InventoryMovement {instance.id}: {e}")
            
        # Route through governance signal_router
        routing_result = signal_router.route_signal(
            signal_name='enhanced_inventory_movement',
            sender=sender,
            instance=instance,
            critical=False,
            created=created
        )
        
        # Check if governance allows this operation
        if not governance_switchboard.is_workflow_enabled('audit_logging'):
            logger.debug("Enhanced inventory movement disabled by governance - skipping")
            return
        
        if routing_result['blocked']:
            monitoring_service.record_violation(
                violation_type='enhanced_inventory_movement_blocked',
                component='product',
                details={
                    'movement_id': instance.id,
                    'product_id': instance.product.id,
                    'block_reason': routing_result['block_reason']
                }
            )
            return
        
        # فحص تنبيهات المخزون المنخفض
        try:
            stock = Stock.objects.get(
                product=instance.product, warehouse=instance.warehouse
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
            monitoring_service.record_violation(
                violation_type='enhanced_inventory_movement_error',
                component='product',
                details={
                    'movement_id': instance.id,
                    'product_id': instance.product.id,
                    'error': str(e)
                }
            )
