# -*- coding: utf-8 -*-
"""
إشارات إعادة حساب مخزون المنتجات المجمعة - Governed Signals (Phase 3.2)
Bundle Stock Recalculation Signals - Low-Risk Signal Processing

تتعامل مع إعادة حساب مخزون المنتجات المجمعة تلقائياً عند:
- تغيير مخزون المكونات
- تفعيل/إلغاء تفعيل المنتجات
- حركات المخزون

Migration Status: Phase 3.2 - Low-Risk Signal Processing ✅
Requirements: 2.1, 8.3
"""

from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.db import transaction
from django.utils import timezone
from django.core.cache import cache
import logging
from typing import Set

from governance.signal_integration import governed_signal_handler, side_effect_handler
from governance.services.audit_service import AuditService
from governance.models import GovernanceContext

from .models import Product, Stock, StockMovement
from .services.stock_calculation_engine import StockCalculationEngine
from .services.bundle_cache_service import BundleCacheService

logger = logging.getLogger('bundle_system')


@governed_signal_handler(
    signal_name="bundle_stock_recalculation_on_movement",
    critical=True,
    description="إعادة حساب مخزون المنتجات المجمعة عند حدوث حركة مخزون"
)
@receiver(post_save, sender=StockMovement)
def recalculate_bundle_stock_on_movement(sender, instance, created, **kwargs):
    """
    إعادة حساب مخزون المنتجات المجمعة عند حدوث حركة مخزون
    
    يتم استدعاؤها بعد حفظ حركة المخزون لإعادة حساب مخزون جميع المنتجات المجمعة
    التي تحتوي على المنتج المتأثر كمكون
    
    Governed side effect handler: Recalculates bundle stock after component movement
    Requirements: 2.1
    """
    if not created:
        return
    
    try:
        # تجنب المعالجة المزدوجة
        if hasattr(instance, '_skip_bundle_recalc') and instance._skip_bundle_recalc:
            logger.debug(f"Skipping bundle recalculation for movement {instance.id} due to skip flag")
            return
        
        product = instance.product
        
        # إنشاء مفتاح cache فريد لتجنب المعالجة المزدوجة
        cache_key = f"bundle_recalc_movement_{product.id}_{instance.id}"
        if cache.get(cache_key):
            logger.debug(f"Skipping duplicate bundle recalculation for movement {instance.id}")
            return
        cache.set(cache_key, True, timeout=10)  # منع المعالجة المزدوجة لمدة 10 ثوان
        
        # التحقق من وجود منتجات مجمعة تحتوي على هذا المنتج كمكون
        affected_bundles = Product.objects.filter(
            is_bundle=True,
            is_active=True,
            components__component_product=product
        ).distinct()
        
        if not affected_bundles.exists():
            logger.debug(f"No affected bundles found for product {product.name} movement")
            return
        
        # إبطال التخزين المؤقت للمكون المتأثر
        BundleCacheService.invalidate_component_cache(product.id)
        
        # إعادة حساب مخزون المنتجات المجمعة المتأثرة
        recalculation_results = StockCalculationEngine.recalculate_affected_bundles(product)
        
        # Audit bundle recalculation
        AuditService.create_audit_record(
            model_name='StockMovement',
            object_id=instance.id,
            operation='BUNDLE_STOCK_RECALCULATION',
            user=GovernanceContext.get_current_user(),
            source_service='BundleStockSignals',
            additional_context={
                'component_product': product.name,
                'affected_bundles_count': len(recalculation_results),
                'movement_type': instance.movement_type,
                'movement_quantity': str(instance.quantity)
            }
        )
        
        # تسجيل النتائج
        for result in recalculation_results:
            bundle = result['bundle_product']
            old_stock = result.get('old_stock', 'غير محدد')
            new_stock = result['new_stock']
            
        
        # إنشاء إشعارات للمخزون المنخفض إذا لزم الأمر
        _check_low_stock_alerts(recalculation_results)
        
    except Exception as e:
        logger.error(f"Error recalculating bundle stock after movement {instance.id}: {e}")
        
        # Audit error
        AuditService.create_audit_record(
            model_name='StockMovement',
            object_id=instance.id,
            operation='BUNDLE_RECALCULATION_ERROR',
            user=GovernanceContext.get_current_user(),
            source_service='BundleStockSignals',
            additional_context={
                'error': str(e),
                'component_product': instance.product.name
            }
        )


@governed_signal_handler(
    signal_name="product_activation_tracking",
    critical=False,
    description="تتبع تغييرات تفعيل/إلغاء تفعيل المنتجات"
)
@receiver(pre_save, sender=Product)
def track_product_activation_changes(sender, instance, **kwargs):
    """
    تتبع تغييرات تفعيل/إلغاء تفعيل المنتجات
    
    يحفظ الحالة السابقة للمنتج لمقارنتها بعد الحفظ
    
    Governed side effect handler: Tracks product activation changes
    Requirements: 8.3
    """
    if instance.pk:
        try:
            # الحصول على الحالة السابقة للمنتج
            old_instance = Product.objects.get(pk=instance.pk)
            instance._old_is_active = old_instance.is_active
            
            logger.debug(f"Tracked activation state for product {instance.name}: {old_instance.is_active}")
        except Product.DoesNotExist:
            instance._old_is_active = None
    else:
        instance._old_is_active = None


@governed_signal_handler(
    signal_name="product_activation_bundle_impact",
    critical=True,
    description="معالجة تغيير حالة تفعيل المنتج وتأثيره على المنتجات المجمعة"
)
@receiver(post_save, sender=Product)
def handle_product_activation_change(sender, instance, created, **kwargs):
    """
    معالجة تغيير حالة تفعيل المنتج وتأثيره على المنتجات المجمعة
    
    عند إلغاء تفعيل منتج مكون، يجب إعادة حساب مخزون جميع المنتجات المجمعة
    التي تحتوي عليه (سيصبح مخزونها صفر)
    
    Governed side effect handler: Handles product activation changes affecting bundles
    Requirements: 8.3
    """
    if created:
        return
    
    try:
        old_is_active = getattr(instance, '_old_is_active', None)
        current_is_active = instance.is_active
        
        # التحقق من حدوث تغيير في حالة التفعيل
        if old_is_active is None or old_is_active == current_is_active:
            return
        
        # البحث عن المنتجات المجمعة المتأثرة
        affected_bundles = Product.objects.filter(
            is_bundle=True,
            is_active=True,
            components__component_product=instance
        ).distinct()
        
        if not affected_bundles.exists():
            return
        
        activation_status = "تفعيل" if current_is_active else "إلغاء تفعيل"
        
        # Audit activation change
        AuditService.create_audit_record(
            model_name='Product',
            object_id=instance.id,
            operation='PRODUCT_ACTIVATION_CHANGE',
            user=GovernanceContext.get_current_user(),
            source_service='BundleStockSignals',
            before_data={'is_active': old_is_active},
            after_data={'is_active': current_is_active},
            additional_context={
                'activation_status': activation_status,
                'affected_bundles_count': affected_bundles.count()
            }
        )
        
        
        # إعادة حساب مخزون المنتجات المجمعة المتأثرة
        recalculation_results = StockCalculationEngine.recalculate_affected_bundles(instance)
        
        # تسجيل النتائج وإنشاء إشعارات
        for result in recalculation_results:
            bundle = result['bundle_product']
            old_stock = result.get('old_stock', 'غير محدد')
            new_stock = result['new_stock']
            
        
        # إنشاء إشعارات خاصة لحالات إلغاء التفعيل
        if not current_is_active:
            _create_component_deactivation_alerts(instance, affected_bundles)
        
        # فحص تنبيهات المخزون المنخفض
        _check_low_stock_alerts(recalculation_results)
        
    except Exception as e:
        logger.error(f"Error handling product activation change for {instance.name}: {e}")
        
        # Audit error
        AuditService.create_audit_record(
            model_name='Product',
            object_id=instance.id,
            operation='ACTIVATION_CHANGE_ERROR',
            user=GovernanceContext.get_current_user(),
            source_service='BundleStockSignals',
            additional_context={
                'error': str(e),
                'old_is_active': old_is_active,
                'current_is_active': current_is_active
            }
        )


@governed_signal_handler(
    signal_name="bundle_stock_direct_change",
    critical=True,
    description="إعادة حساب مخزون المنتجات المجمعة عند تغيير المخزون مباشرة"
)
@receiver(post_save, sender=Stock)
def recalculate_bundle_stock_on_direct_stock_change(sender, instance, **kwargs):
    """
    إعادة حساب مخزون المنتجات المجمعة عند تغيير المخزون مباشرة
    
    يتعامل مع التغييرات المباشرة في جدول Stock (بدون حركة مخزون)
    
    Governed side effect handler: Recalculates bundle stock on direct stock changes
    Requirements: 2.1
    """
    try:
        product = instance.product
        
        # تجنب المعالجة المزدوجة مع إشارة StockMovement
        cache_key = f"bundle_recalc_stock_{product.id}_{timezone.now().timestamp():.0f}"
        if cache.get(cache_key):
            logger.debug(f"Skipping duplicate bundle recalculation for direct stock change: {product.name}")
            return
        cache.set(cache_key, True, timeout=5)  # منع المعالجة المزدوجة لمدة 5 ثوان
        
        # البحث عن المنتجات المجمعة المتأثرة
        affected_bundles = Product.objects.filter(
            is_bundle=True,
            is_active=True,
            components__component_product=product
        ).distinct()
        
        if not affected_bundles.exists():
            return
        
        # إعادة حساب مخزون المنتجات المجمعة المتأثرة
        recalculation_results = StockCalculationEngine.recalculate_affected_bundles(product)
        
        # Audit direct stock change impact
        AuditService.create_audit_record(
            model_name='Stock',
            object_id=instance.id,
            operation='BUNDLE_STOCK_DIRECT_RECALCULATION',
            user=GovernanceContext.get_current_user(),
            source_service='BundleStockSignals',
            additional_context={
                'component_product': product.name,
                'affected_bundles_count': len(recalculation_results),
                'stock_quantity': str(instance.quantity)
            }
        )
        
        
        # فحص تنبيهات المخزون المنخفض
        _check_low_stock_alerts(recalculation_results)
        
    except Exception as e:
        logger.error(f"Error recalculating bundle stock after direct stock change for {instance.product.name}: {e}")
        
        # Audit error
        AuditService.create_audit_record(
            model_name='Stock',
            object_id=instance.id,
            operation='DIRECT_RECALCULATION_ERROR',
            user=GovernanceContext.get_current_user(),
            source_service='BundleStockSignals',
            additional_context={
                'error': str(e),
                'component_product': instance.product.name
            }
        )


def _check_low_stock_alerts(recalculation_results):
    """
    فحص وإنشاء تنبيهات المخزون المنخفض للمنتجات المجمعة
    Check and create low stock alerts for bundle products with governance audit
    
    Args:
        recalculation_results: نتائج إعادة حساب المخزون
    """
    try:
        from core.models import Notification
        from django.contrib.auth import get_user_model
        from django.db import models
        
        User = get_user_model()
        
        # الحصول على المستخدمين المخولين لتلقي تنبيهات المخزون
        authorized_users = User.objects.filter(
            models.Q(groups__name__in=["مدير مخزون", "مدير", "Admin"])
            | models.Q(is_superuser=True),
            is_active=True,
        ).distinct()
        
        alerts_created = 0
        
        for result in recalculation_results:
            bundle = result['bundle_product']
            new_stock = result['new_stock']
            
            # التحقق من المخزون المنخفض
            if new_stock == 0:
                alert_type = "نفذ"
                notification_type = "danger"
            elif bundle.min_stock > 0 and new_stock <= bundle.min_stock:
                alert_type = "منخفض"
                notification_type = "warning"
            else:
                continue  # لا حاجة لتنبيه
            
            title = f"تنبيه مخزون {alert_type}: {bundle.name} (منتج مجمع)"
            message = (
                f"المنتج المجمع '{bundle.name}' {alert_type}.\n"
                f"المخزون المحسوب: {new_stock} وحدة\n"
                f"الحد الأدنى: {bundle.min_stock} وحدة\n"
                f"يُرجى مراجعة مخزون المكونات وإعادة التزويد."
            )
            
            # إنشاء تنبيه لجميع المستخدمين المخولين
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
                object_id=bundle.id,
                operation='BUNDLE_LOW_STOCK_ALERT_CREATED',
                user=GovernanceContext.get_current_user(),
                source_service='BundleStockSignals',
                additional_context={
                    'alert_type': alert_type,
                    'calculated_stock': str(new_stock),
                    'min_stock': str(bundle.min_stock),
                    'notification_count': authorized_users.count(),
                    'is_bundle': True
                }
            )
            
            alerts_created += 1
        
            
    except Exception as e:
        logger.error(f"Error creating bundle low stock alerts: {e}")


def _create_component_deactivation_alerts(deactivated_product, affected_bundles):
    """
    إنشاء تنبيهات خاصة عند إلغاء تفعيل مكون يؤثر على منتجات مجمعة
    Create special alerts when deactivating a component affecting bundle products
    
    Args:
        deactivated_product: المنتج المكون الذي تم إلغاء تفعيله
        affected_bundles: المنتجات المجمعة المتأثرة
    """
    try:
        from core.models import Notification
        from django.contrib.auth import get_user_model
        from django.db import models
        
        User = get_user_model()
        
        # الحصول على المستخدمين المخولين
        authorized_users = User.objects.filter(
            models.Q(groups__name__in=["مدير مخزون", "مدير", "Admin"])
            | models.Q(is_superuser=True),
            is_active=True,
        ).distinct()
        
        bundle_names = [bundle.name for bundle in affected_bundles]
        
        title = f"تحذير: إلغاء تفعيل مكون يؤثر على منتجات مجمعة"
        message = (
            f"تم إلغاء تفعيل المنتج '{deactivated_product.name}' "
            f"والذي يُستخدم كمكون في المنتجات المجمعة التالية:\n\n"
            f"• {chr(10).join(bundle_names)}\n\n"
            f"جميع هذه المنتجات المجمعة أصبحت غير متوفرة حتى يتم إعادة تفعيل المكون."
        )
        
        # إنشاء تنبيه لجميع المستخدمين المخولين
        for user in authorized_users:
            Notification.objects.create(
                user=user,
                title=title,
                message=message,
                type="warning"
            )
        
        # Audit component deactivation alert
        AuditService.create_audit_record(
            model_name='Product',
            object_id=deactivated_product.id,
            operation='COMPONENT_DEACTIVATION_ALERT_CREATED',
            user=GovernanceContext.get_current_user(),
            source_service='BundleStockSignals',
            additional_context={
                'deactivated_component': deactivated_product.name,
                'affected_bundles_count': len(affected_bundles),
                'affected_bundle_names': bundle_names,
                'notification_count': authorized_users.count()
            }
        )
        
        
    except Exception as e:
        logger.error(f"Error creating component deactivation alerts: {e}")