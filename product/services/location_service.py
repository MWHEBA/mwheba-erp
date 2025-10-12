"""
خدمة إدارة المواقع داخل المستودعات
تتعامل مع الأرفف والممرات ومواقع المنتجات
"""
from django.db import models, transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from decimal import Decimal
import logging
from typing import Dict, List, Optional, Tuple

from ..models.location_system import (
    LocationZone, LocationAisle, LocationShelf, 
    ProductLocation, LocationMovement, LocationTask
)
from ..models import Product, Warehouse

User = get_user_model()
logger = logging.getLogger(__name__)


class LocationService:
    """
    خدمة شاملة لإدارة المواقع داخل المستودعات
    """
    
    @staticmethod
    def create_warehouse_structure(warehouse, zones_data, user=None):
        """
        إنشاء هيكل كامل للمستودع (مناطق، ممرات، أرفف)
        """
        try:
            with transaction.atomic():
                created_zones = []
                
                for zone_data in zones_data:
                    # إنشاء المنطقة
                    zone = LocationZone.objects.create(
                        warehouse=warehouse,
                        name=zone_data['name'],
                        code=zone_data['code'],
                        zone_type=zone_data.get('zone_type', 'normal'),
                        description=zone_data.get('description'),
                        temperature_min=zone_data.get('temperature_min'),
                        temperature_max=zone_data.get('temperature_max'),
                        humidity_max=zone_data.get('humidity_max'),
                        requires_authorization=zone_data.get('requires_authorization', False),
                        created_by=user
                    )
                    
                    # إنشاء الممرات
                    for aisle_data in zone_data.get('aisles', []):
                        aisle = LocationAisle.objects.create(
                            zone=zone,
                            name=aisle_data['name'],
                            code=aisle_data['code'],
                            description=aisle_data.get('description'),
                            sequence=aisle_data.get('sequence', 1)
                        )
                        
                        # إنشاء الأرفف
                        for shelf_data in aisle_data.get('shelves', []):
                            LocationShelf.objects.create(
                                aisle=aisle,
                                name=shelf_data['name'],
                                code=shelf_data['code'],
                                levels=shelf_data.get('levels', 1),
                                max_weight=shelf_data.get('max_weight'),
                                max_volume=shelf_data.get('max_volume'),
                                sequence=shelf_data.get('sequence', 1)
                            )
                    
                    created_zones.append(zone)
                
                logger.info(f"تم إنشاء {len(created_zones)} منطقة في المستودع {warehouse.name}")
                return created_zones
                
        except Exception as e:
            logger.error(f"خطأ في إنشاء هيكل المستودع: {e}")
            raise
    
    @staticmethod
    def assign_product_location(
        product,
        shelf,
        level=1,
        position=None,
        location_type='primary',
        max_quantity=None,
        min_quantity=0,
        user=None
    ):
        """
        تعيين موقع لمنتج
        """
        try:
            with transaction.atomic():
                # التحقق من عدم وجود موقع مماثل
                existing_location = ProductLocation.objects.filter(
                    product=product,
                    shelf=shelf,
                    level=level,
                    position=position
                ).first()
                
                if existing_location:
                    raise ValueError(f"الموقع موجود مسبقاً: {existing_location.full_location_code}")
                
                # إنشاء الموقع
                location = ProductLocation.objects.create(
                    product=product,
                    shelf=shelf,
                    level=level,
                    position=position,
                    location_type=location_type,
                    max_quantity=max_quantity,
                    min_quantity=min_quantity,
                    created_by=user
                )
                
                logger.info(f"تم تعيين موقع جديد: {location}")
                return location
                
        except Exception as e:
            logger.error(f"خطأ في تعيين موقع المنتج: {e}")
            raise
    
    @staticmethod
    def move_product_between_locations(
        product,
        from_location,
        to_location,
        quantity,
        movement_type='move',
        reason=None,
        user=None
    ):
        """
        نقل منتج بين المواقع
        """
        try:
            with transaction.atomic():
                # التحقق من توفر الكمية في الموقع المصدر
                if from_location and from_location.current_quantity < quantity:
                    raise ValueError(
                        f"الكمية المطلوبة ({quantity}) أكبر من المتاحة "
                        f"في الموقع ({from_location.current_quantity})"
                    )
                
                # التحقق من قدرة الموقع الوجهة على الاستيعاب
                if to_location and not to_location.can_accommodate(quantity):
                    raise ValueError(
                        f"الموقع الوجهة لا يمكنه استيعاب الكمية المطلوبة. "
                        f"المساحة المتاحة: {to_location.available_space}"
                    )
                
                # تحديث الكميات
                if from_location:
                    from_location.current_quantity -= quantity
                    from_location.save()
                
                if to_location:
                    to_location.current_quantity += quantity
                    to_location.save()
                
                # إنشاء سجل الحركة
                movement = LocationMovement.objects.create(
                    product=product,
                    from_location=from_location,
                    to_location=to_location,
                    movement_type=movement_type,
                    quantity=quantity,
                    reason=reason,
                    moved_by=user
                )
                
                logger.info(f"تم نقل {quantity} من {product.name} بين المواقع")
                return movement
                
        except Exception as e:
            logger.error(f"خطأ في نقل المنتج بين المواقع: {e}")
            raise
    
    @staticmethod
    def find_optimal_location(product, warehouse, quantity, location_type='primary'):
        """
        العثور على أفضل موقع لتخزين المنتج
        """
        try:
            # البحث عن المواقع المتاحة للمنتج
            existing_locations = ProductLocation.objects.filter(
                product=product,
                shelf__aisle__zone__warehouse=warehouse,
                location_type=location_type,
                is_active=True
            ).order_by('current_quantity')
            
            # البحث في المواقع الموجودة أولاً
            for location in existing_locations:
                if location.can_accommodate(quantity):
                    return location
            
            # البحث عن مواقع فارغة مناسبة
            empty_locations = ProductLocation.objects.filter(
                shelf__aisle__zone__warehouse=warehouse,
                current_quantity=0,
                is_active=True
            ).exclude(
                product=product
            ).order_by('shelf__aisle__sequence', 'shelf__sequence')
            
            for location in empty_locations:
                if location.can_accommodate(quantity):
                    # تحديث المنتج المرتبط بالموقع
                    location.product = product
                    location.save()
                    return location
            
            # لم يتم العثور على موقع مناسب
            return None
            
        except Exception as e:
            logger.error(f"خطأ في البحث عن موقع مثالي: {e}")
            return None
    
    @staticmethod
    def get_product_locations(product, warehouse=None):
        """
        الحصول على جميع مواقع المنتج
        """
        try:
            queryset = ProductLocation.objects.filter(
                product=product,
                is_active=True
            ).select_related('shelf__aisle__zone')
            
            if warehouse:
                queryset = queryset.filter(shelf__aisle__zone__warehouse=warehouse)
            
            return queryset.order_by('location_type', 'shelf__aisle__sequence', 'shelf__sequence')
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على مواقع المنتج: {e}")
            return ProductLocation.objects.none()
    
    @staticmethod
    def get_location_utilization(warehouse):
        """
        حساب معدل استغلال المواقع في المستودع
        """
        try:
            # إجمالي المواقع
            total_locations = ProductLocation.objects.filter(
                shelf__aisle__zone__warehouse=warehouse,
                is_active=True
            ).count()
            
            # المواقع المستخدمة
            occupied_locations = ProductLocation.objects.filter(
                shelf__aisle__zone__warehouse=warehouse,
                is_active=True,
                current_quantity__gt=0
            ).count()
            
            # المواقع الممتلئة
            full_locations = ProductLocation.objects.filter(
                shelf__aisle__zone__warehouse=warehouse,
                is_active=True,
                current_quantity__gte=models.F('max_quantity')
            ).exclude(max_quantity__isnull=True).count()
            
            # حساب النسب
            utilization_rate = (occupied_locations / total_locations * 100) if total_locations > 0 else 0
            capacity_rate = (full_locations / total_locations * 100) if total_locations > 0 else 0
            
            return {
                'total_locations': total_locations,
                'occupied_locations': occupied_locations,
                'empty_locations': total_locations - occupied_locations,
                'full_locations': full_locations,
                'utilization_rate': round(utilization_rate, 2),
                'capacity_rate': round(capacity_rate, 2)
            }
            
        except Exception as e:
            logger.error(f"خطأ في حساب معدل استغلال المواقع: {e}")
            return {}
    
    @staticmethod
    def create_location_task(
        task_type,
        title,
        location,
        product=None,
        quantity=None,
        priority=3,
        due_date=None,
        assigned_to=None,
        description=None,
        user=None
    ):
        """
        إنشاء مهمة موقع
        """
        try:
            task = LocationTask.objects.create(
                task_type=task_type,
                title=title,
                description=description,
                location=location,
                product=product,
                quantity=quantity,
                priority=priority,
                due_date=due_date,
                assigned_to=assigned_to,
                created_by=user
            )
            
            if assigned_to:
                task.assign_to(assigned_to)
            
            logger.info(f"تم إنشاء مهمة موقع جديدة: {task}")
            return task
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء مهمة الموقع: {e}")
            raise
    
    @staticmethod
    def get_location_tasks(warehouse=None, status=None, assigned_to=None):
        """
        الحصول على مهام المواقع
        """
        try:
            queryset = LocationTask.objects.select_related(
                'location__shelf__aisle__zone',
                'product',
                'assigned_to',
                'created_by'
            )
            
            if warehouse:
                queryset = queryset.filter(
                    location__shelf__aisle__zone__warehouse=warehouse
                )
            
            if status:
                queryset = queryset.filter(status=status)
            
            if assigned_to:
                queryset = queryset.filter(assigned_to=assigned_to)
            
            return queryset.order_by('priority', '-created_at')
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على مهام المواقع: {e}")
            return LocationTask.objects.none()
    
    @staticmethod
    def generate_picking_route(warehouse, pick_list):
        """
        إنشاء مسار انتقاء محسن
        """
        try:
            # الحصول على مواقع المنتجات المطلوبة
            product_locations = []
            
            for item in pick_list:
                product = item['product']
                quantity_needed = item['quantity']
                
                locations = ProductLocation.objects.filter(
                    product=product,
                    shelf__aisle__zone__warehouse=warehouse,
                    current_quantity__gt=0,
                    is_active=True
                ).order_by(
                    'shelf__aisle__zone__sequence',
                    'shelf__aisle__sequence',
                    'shelf__sequence'
                )
                
                quantity_collected = 0
                for location in locations:
                    if quantity_collected >= quantity_needed:
                        break
                    
                    available_qty = min(
                        location.current_quantity,
                        quantity_needed - quantity_collected
                    )
                    
                    if available_qty > 0:
                        product_locations.append({
                            'product': product,
                            'location': location,
                            'quantity': available_qty,
                            'sort_key': (
                                location.shelf.aisle.zone.warehouse.id,
                                location.shelf.aisle.sequence,
                                location.shelf.sequence,
                                location.level
                            )
                        })
                        quantity_collected += available_qty
            
            # ترتيب المواقع حسب المسار الأمثل
            optimized_route = sorted(product_locations, key=lambda x: x['sort_key'])
            
            return optimized_route
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء مسار الانتقاء: {e}")
            return []
    
    @staticmethod
    def get_location_report(warehouse):
        """
        تقرير شامل عن المواقع
        """
        try:
            # إحصائيات المناطق
            zones_stats = LocationZone.objects.filter(
                warehouse=warehouse,
                is_active=True
            ).annotate(
                aisles_count=models.Count('aisles'),
                shelves_count=models.Count('aisles__shelves'),
                locations_count=models.Count('aisles__shelves__product_locations')
            )
            
            # المواقع منخفضة المخزون
            low_stock_locations = ProductLocation.objects.filter(
                shelf__aisle__zone__warehouse=warehouse,
                current_quantity__lte=models.F('min_quantity'),
                is_active=True
            ).select_related('product', 'shelf__aisle__zone')
            
            # المواقع الممتلئة
            full_locations = ProductLocation.objects.filter(
                shelf__aisle__zone__warehouse=warehouse,
                current_quantity__gte=models.F('max_quantity'),
                is_active=True
            ).exclude(max_quantity__isnull=True).select_related('product', 'shelf__aisle__zone')
            
            # المهام المعلقة
            pending_tasks = LocationTask.objects.filter(
                location__shelf__aisle__zone__warehouse=warehouse,
                status__in=['pending', 'assigned', 'in_progress']
            ).select_related('location', 'product', 'assigned_to')
            
            # معدل الاستغلال
            utilization = LocationService.get_location_utilization(warehouse)
            
            return {
                'zones_stats': list(zones_stats),
                'low_stock_locations': list(low_stock_locations),
                'full_locations': list(full_locations),
                'pending_tasks': list(pending_tasks),
                'utilization': utilization,
                'generated_at': timezone.now()
            }
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء تقرير المواقع: {e}")
            return {
                'zones_stats': [],
                'low_stock_locations': [],
                'full_locations': [],
                'pending_tasks': [],
                'utilization': {},
                'error': str(e)
            }
