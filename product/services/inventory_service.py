"""
خدمة إدارة المخزون وتتبع الحركات
"""
from django.db import models, transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from decimal import Decimal
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

from ..models import (
    Product, Warehouse, ProductStock, StockTransfer, 
    InventoryMovement, InventoryAdjustment, StockSnapshot
)
from core.services.notification_service import NotificationService

User = get_user_model()
logger = logging.getLogger(__name__)


class InventoryService:
    """
    خدمة شاملة لإدارة المخزون
    """
    
    @staticmethod
    def record_movement(
        product, 
        movement_type, 
        quantity, 
        warehouse=None, 
        source='manual',
        unit_cost=None,
        reference_number=None,
        notes=None,
        user=None,
        purchase_id=None,
        sale_id=None
    ):
        """
        تسجيل حركة مخزون
        """
        try:
            with transaction.atomic():
                # التأكد من وجود مستودع
                if not warehouse:
                    warehouse = Warehouse.get_main_warehouse()
                    if not warehouse:
                        raise ValueError("لا يوجد مستودع متاح")
                
                # الحصول على أو إنشاء مخزون المنتج
                stock, created = ProductStock.objects.get_or_create(
                    product=product,
                    warehouse=warehouse,
                    defaults={
                        'quantity': Decimal('0'),
                        'average_cost': unit_cost or product.cost_price
                    }
                )
                
                # حساب تكلفة الوحدة إذا لم تُحدد
                if not unit_cost:
                    unit_cost = stock.average_cost or product.cost_price
                
                # تحديث المخزون حسب نوع الحركة
                old_quantity = stock.quantity
                
                if movement_type in ['in', 'return_in']:
                    # دخول للمخزون
                    stock.update_average_cost(quantity, unit_cost)
                    new_quantity = stock.quantity
                elif movement_type in ['out', 'return_out', 'damage', 'expired']:
                    # خروج من المخزون
                    if stock.quantity < quantity:
                        raise ValueError(f"الكمية المطلوبة ({quantity}) أكبر من المتاح ({stock.quantity})")
                    
                    stock.quantity -= quantity
                    new_quantity = stock.quantity
                    stock.save()
                else:
                    # حركات أخرى (تحويل، تسوية)
                    new_quantity = old_quantity
                
                # إنشاء سجل الحركة
                movement = InventoryMovement.objects.create(
                    product=product,
                    warehouse=warehouse,
                    movement_type=movement_type,
                    document_type=source,
                    quantity=quantity,
                    unit_cost=unit_cost,
                    total_cost=quantity * unit_cost,
                    document_number=reference_number,
                    notes=notes,
                    created_by=user,
                    quantity_before=old_quantity,
                    quantity_after=new_quantity
                )
                
                # تحديث تاريخ آخر حركة
                stock.last_movement_date = timezone.now()
                stock.save()
                
                # فحص تنبيهات المخزون المنخفض
                InventoryService._check_low_stock_alert(product, stock)
                
                logger.info(f"تم تسجيل حركة مخزون: {movement}")
                return movement
                
        except Exception as e:
            logger.error(f"خطأ في تسجيل حركة المخزون: {e}")
            raise
    
    @staticmethod
    def _check_low_stock_alert(product, stock):
        """
        فحص تنبيه المخزون المنخفض
        """
        try:
            if stock.is_low_stock or stock.is_out_of_stock:
                # إنشاء تنبيه فوري
                authorized_users = User.objects.filter(
                    models.Q(groups__name__in=['مدير مخزون', 'مدير', 'Admin']) |
                    models.Q(is_superuser=True),
                    is_active=True
                ).distinct()
                
                status = "نفد" if stock.is_out_of_stock else "منخفض"
                title = f"تنبيه مخزون {status}: {product.name}"
                message = (
                    f"المنتج '{product.name}' في المستودع '{stock.warehouse.name}' {status}.\n"
                    f"الكمية الحالية: {stock.quantity} {product.unit.symbol}\n"
                    f"الحد الأدنى: {product.min_stock} {product.unit.symbol}"
                )
                
                for user in authorized_users:
                    NotificationService.create_notification(
                        user=user,
                        title=title,
                        message=message,
                        notification_type='inventory_alert'
                    )
        except Exception as e:
            logger.error(f"خطأ في فحص تنبيه المخزون المنخفض: {e}")
    
    @staticmethod
    def create_adjustment(
        product,
        warehouse,
        expected_quantity,
        actual_quantity,
        adjustment_type,
        reason,
        user,
        unit_cost=None
    ):
        """
        إنشاء تسوية مخزون (الدالة الأصلية)
        """
        # استخدام الدالة الجديدة
        return InventoryService.create_stock_adjustment(
            product=product,
            warehouse=warehouse,
            actual_quantity=actual_quantity,
            reason=reason,
            user=user,
            unit_cost=unit_cost
        )
    
    @staticmethod
    def create_stock_adjustment(
        product,
        warehouse,
        actual_quantity,
        reason,
        user,
        unit_cost=None,
        **kwargs  # لقبول معاملات إضافية
    ):
        """
        إنشاء تسوية مخزون
        """
        try:
            with transaction.atomic():
                # الحصول على مخزون المنتج
                stock = ProductStock.objects.get(
                    product=product,
                    warehouse=warehouse
                )
                
                if not unit_cost:
                    unit_cost = stock.average_cost or product.cost_price
                
                # حساب الفرق
                expected_quantity = stock.quantity
                difference = actual_quantity - expected_quantity
                
                # تحديد نوع التسوية
                if difference > 0:
                    adjustment_type = 'increase'
                elif difference < 0:
                    adjustment_type = 'decrease'
                else:
                    adjustment_type = 'no_change'
                
                # إنشاء سجل التسوية
                adjustment = InventoryAdjustment.objects.create(
                    product=product,
                    warehouse=warehouse,
                    adjustment_type=adjustment_type,
                    expected_quantity=expected_quantity,
                    actual_quantity=actual_quantity,
                    unit_cost=unit_cost,
                    reason=reason,
                    created_by=user
                )
                
                # تحديد نوع الحركة
                if adjustment.difference > 0:
                    movement_type = 'in'
                    movement_quantity = adjustment.difference
                elif adjustment.difference < 0:
                    movement_type = 'out'
                    movement_quantity = abs(adjustment.difference)
                else:
                    # لا يوجد فرق، لا حاجة لحركة
                    return adjustment
                
                # إنشاء حركة المخزون
                movement = InventoryService.record_movement(
                    product=product,
                    movement_type=movement_type,
                    quantity=movement_quantity,
                    warehouse=warehouse,
                    source='adjustment',
                    unit_cost=unit_cost,
                    reference_number=f"ADJ-{adjustment.id}",
                    notes=f"تسوية مخزون: {reason}",
                    user=user
                )
                
                # ربط التسوية بالحركة
                adjustment.movement = movement
                adjustment.save()
                
                logger.info(f"تم إنشاء تسوية مخزون: {adjustment}")
                return adjustment
                
        except Exception as e:
            logger.error(f"خطأ في إنشاء تسوية المخزون: {e}")
            raise
    
    @staticmethod
    def update_stock_quantity(
        product,
        warehouse,
        quantity_change,
        movement_type,
        reference,
        user,
        unit_cost=None,
        **kwargs  # لقبول معاملات إضافية
    ):
        """
        تحديث كمية المخزون
        """
        try:
            # تحديد نوع الحركة
            if quantity_change > 0:
                movement_type_code = 'in'
            else:
                movement_type_code = 'out'
                quantity_change = abs(quantity_change)
            
            # تسجيل الحركة
            return InventoryService.record_movement(
                product=product,
                movement_type=movement_type_code,
                quantity=quantity_change,
                warehouse=warehouse,
                source=movement_type,
                unit_cost=unit_cost,
                reference_number=reference,
                user=user
            )
        except Exception as e:
            logger.error(f"خطأ في تحديث كمية المخزون: {e}")
            raise
    
    @staticmethod
    def transfer_stock(
        product,
        from_warehouse,
        to_warehouse,
        quantity,
        user,
        notes=None
    ):
        """
        تحويل مخزون بين المستودعات
        """
        try:
            with transaction.atomic():
                # التحقق من توفر الكمية في المستودع المصدر
                from_stock = ProductStock.objects.get(
                    product=product,
                    warehouse=from_warehouse
                )
                
                if from_stock.available_quantity < quantity:
                    raise ValueError(
                        f"الكمية المطلوبة ({quantity}) أكبر من المتاح ({from_stock.available_quantity})"
                    )
                
                # إنشاء سجل التحويل
                transfer = StockTransfer.objects.create(
                    from_warehouse=from_warehouse,
                    to_warehouse=to_warehouse,
                    product=product,
                    quantity=quantity,
                    transfer_cost=from_stock.average_cost * quantity,
                    notes=notes,
                    requested_by=user,
                    status='completed'  # تحويل فوري
                )
                
                # تسجيل حركة خروج من المستودع المصدر
                InventoryService.record_movement(
                    product=product,
                    movement_type='out',
                    quantity=quantity,
                    warehouse=from_warehouse,
                    source='transfer',
                    unit_cost=from_stock.average_cost,
                    reference_number=transfer.transfer_number,
                    notes=f"تحويل إلى {to_warehouse.name}",
                    user=user
                )
                
                # تسجيل حركة دخول للمستودع الهدف
                InventoryService.record_movement(
                    product=product,
                    movement_type='in',
                    quantity=quantity,
                    warehouse=to_warehouse,
                    source='transfer',
                    unit_cost=from_stock.average_cost,
                    reference_number=transfer.transfer_number,
                    notes=f"تحويل من {from_warehouse.name}",
                    user=user
                )
                
                logger.info(f"تم تحويل المخزون: {transfer}")
                return transfer
                
        except Exception as e:
            logger.error(f"خطأ في تحويل المخزون: {e}")
            raise
    
    @staticmethod
    def generate_daily_snapshots(date=None):
        """
        إنشاء لقطات المخزون اليومية
        """
        try:
            if not date:
                date = timezone.now().date()
            
            snapshots_created = 0
            
            # الحصول على جميع المنتجات النشطة
            products = Product.objects.filter(is_active=True)
            warehouses = Warehouse.objects.filter(is_active=True)
            
            for product in products:
                for warehouse in warehouses:
                    try:
                        # التحقق من وجود لقطة لهذا اليوم
                        snapshot, created = StockSnapshot.objects.get_or_create(
                            product=product,
                            warehouse=warehouse,
                            date=date,
                            defaults={
                                'opening_balance': Decimal('0'),
                                'total_in': Decimal('0'),
                                'total_out': Decimal('0'),
                                'closing_balance': Decimal('0'),
                                'average_cost': Decimal('0'),
                                'total_value': Decimal('0')
                            }
                        )
                        
                        if created or True:  # إعادة حساب دائماً
                            # حساب الحركات لهذا اليوم
                            movements = InventoryMovement.objects.filter(
                                product=product,
                                warehouse=warehouse,
                                date__date=date
                            )
                            
                            total_in = movements.filter(
                                movement_type__in=['in', 'return_in']
                            ).aggregate(
                                total=models.Sum('quantity')
                            )['total'] or Decimal('0')
                            
                            total_out = movements.filter(
                                movement_type__in=['out', 'return_out', 'damage', 'expired']
                            ).aggregate(
                                total=models.Sum('quantity')
                            )['total'] or Decimal('0')
                            
                            # الحصول على الرصيد الحالي
                            try:
                                stock = ProductStock.objects.get(
                                    product=product,
                                    warehouse=warehouse
                                )
                                closing_balance = stock.quantity
                                average_cost = stock.average_cost
                            except ProductStock.DoesNotExist:
                                closing_balance = Decimal('0')
                                average_cost = product.cost_price
                            
                            # حساب الرصيد الافتتاحي
                            opening_balance = closing_balance - total_in + total_out
                            
                            # تحديث اللقطة
                            snapshot.opening_balance = opening_balance
                            snapshot.total_in = total_in
                            snapshot.total_out = total_out
                            snapshot.closing_balance = closing_balance
                            snapshot.average_cost = average_cost
                            snapshot.total_value = closing_balance * average_cost
                            snapshot.save()
                            
                            if created:
                                snapshots_created += 1
                    
                    except Exception as e:
                        logger.error(f"خطأ في إنشاء لقطة المخزون للمنتج {product.name}: {e}")
                        continue
            
            logger.info(f"تم إنشاء {snapshots_created} لقطة مخزون جديدة ليوم {date}")
            return snapshots_created
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء لقطات المخزون اليومية: {e}")
            return 0
    
    @staticmethod
    def get_inventory_report(warehouse=None, category=None, low_stock_only=False):
        """
        تقرير المخزون الشامل
        """
        try:
            # بناء الاستعلام
            queryset = ProductStock.objects.select_related(
                'product', 'product__category', 'product__unit', 'warehouse'
            )
            
            if warehouse:
                queryset = queryset.filter(warehouse=warehouse)
            
            if category:
                queryset = queryset.filter(product__category=category)
            
            if low_stock_only:
                queryset = queryset.filter(
                    models.Q(quantity__lte=models.F('product__min_stock')) |
                    models.Q(quantity__lte=models.F('reorder_point'))
                )
            
            # حساب الإحصائيات
            stats = queryset.aggregate(
                total_products=models.Count('id'),
                total_quantity=models.Sum('quantity'),
                total_value=models.Sum(
                    models.F('quantity') * models.F('average_cost')
                ),
                low_stock_count=models.Count(
                    'id',
                    filter=models.Q(quantity__lte=models.F('product__min_stock'))
                ),
                out_of_stock_count=models.Count(
                    'id',
                    filter=models.Q(quantity=0)
                )
            )
            
            return {
                'stocks': list(queryset.order_by('product__name')),
                'stats': stats,
                'generated_at': timezone.now()
            }
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء تقرير المخزون: {e}")
            return {
                'stocks': [],
                'stats': {},
                'error': str(e)
            }
    
    @staticmethod
    def get_movement_report(
        product=None, 
        warehouse=None, 
        date_from=None, 
        date_to=None,
        movement_type=None
    ):
        """
        تقرير حركات المخزون
        """
        try:
            queryset = InventoryMovement.objects.select_related(
                'product', 'warehouse', 'created_by'
            )
            
            if product:
                queryset = queryset.filter(product=product)
            
            if warehouse:
                queryset = queryset.filter(warehouse=warehouse)
            
            if date_from:
                queryset = queryset.filter(date__gte=date_from)
            
            if date_to:
                queryset = queryset.filter(date__lte=date_to)
            
            if movement_type:
                queryset = queryset.filter(movement_type=movement_type)
            
            # حساب الإحصائيات
            stats = queryset.aggregate(
                total_movements=models.Count('id'),
                total_in=models.Sum(
                    'quantity',
                    filter=models.Q(movement_type__in=['in', 'return_in'])
                ),
                total_out=models.Sum(
                    'quantity',
                    filter=models.Q(movement_type__in=['out', 'return_out', 'damage', 'expired'])
                ),
                total_value=models.Sum('total_cost')
            )
            
            return {
                'movements': list(queryset.order_by('-date')),
                'stats': stats,
                'generated_at': timezone.now()
            }
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء تقرير حركات المخزون: {e}")
            return {
                'movements': [],
                'stats': {},
                'error': str(e)
            }
    
    @staticmethod
    def create_stock_adjustment(product, warehouse, adjustment_quantity, reason, user):
        """إنشاء تعديل مخزون"""
        try:
            with transaction.atomic():
                # الحصول على المخزون الحالي
                stock, created = ProductStock.objects.get_or_create(
                    product=product,
                    warehouse=warehouse,
                    defaults={'quantity': 0}
                )
                
                # إنشاء تعديل المخزون
                adjustment = InventoryAdjustment.objects.create(
                    product=product,
                    warehouse=warehouse,
                    adjustment_quantity=adjustment_quantity,
                    reason=reason,
                    created_by=user,
                    status='approved'
                )
                
                # تحديث المخزون
                stock.quantity += adjustment_quantity
                stock.save()
                
                # إنشاء حركة مخزون
                movement = InventoryMovement.objects.create(
                    product=product,
                    warehouse=warehouse,
                    movement_type='adjustment',
                    quantity=abs(adjustment_quantity),
                    direction='in' if adjustment_quantity > 0 else 'out',
                    notes=f"تعديل مخزون: {reason}",
                    created_by=user
                )
                
                return adjustment
                
        except Exception as e:
            logger.error(f"خطأ في إنشاء تعديل المخزون: {e}")
            raise
    
    @staticmethod
    def update_stock_quantity(product, warehouse, new_quantity, user, reason="تحديث مخزون"):
        """تحديث كمية المخزون"""
        try:
            with transaction.atomic():
                # الحصول على المخزون الحالي
                stock, created = ProductStock.objects.get_or_create(
                    product=product,
                    warehouse=warehouse,
                    defaults={'quantity': 0}
                )
                
                old_quantity = stock.quantity
                adjustment_quantity = new_quantity - old_quantity
                
                if adjustment_quantity != 0:
                    # تحديث المخزون
                    stock.quantity = new_quantity
                    stock.save()
                    
                    # إنشاء حركة مخزون
                    movement = InventoryMovement.objects.create(
                        product=product,
                        warehouse=warehouse,
                        movement_type='adjustment',
                        quantity=abs(adjustment_quantity),
                        direction='in' if adjustment_quantity > 0 else 'out',
                        notes=f"{reason} - من {old_quantity} إلى {new_quantity}",
                        created_by=user
                    )
                    
                    return movement
                
                return None
                
        except Exception as e:
            logger.error(f"خطأ في تحديث كمية المخزون: {e}")
            raise
