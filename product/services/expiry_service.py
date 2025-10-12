"""
خدمة إدارة تواريخ انتهاء الصلاحية
تتعامل مع الدفعات والتنبيهات وإدارة FIFO
"""
from django.db import models, transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from decimal import Decimal
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

from ..models.expiry_tracking import ProductBatch, BatchConsumption, ExpiryAlert, ExpiryRule
from ..models.warehouse import ProductStock
from ..models import Product, Warehouse
from core.services.notification_service import NotificationService

User = get_user_model()
logger = logging.getLogger(__name__)


class ExpiryService:
    """
    خدمة شاملة لإدارة تواريخ انتهاء الصلاحية
    """
    
    @staticmethod
    def create_batch(
        product,
        warehouse,
        batch_number,
        initial_quantity,
        unit_cost,
        expiry_date=None,
        production_date=None,
        supplier=None,
        supplier_batch_number=None,
        location_code=None,
        notes=None,
        user=None
    ):
        """
        إنشاء دفعة جديدة من المنتج
        """
        try:
            with transaction.atomic():
                # التحقق من عدم تكرار رقم الدفعة
                if ProductBatch.objects.filter(
                    batch_number=batch_number,
                    product=product
                ).exists():
                    raise ValueError(f"رقم الدفعة {batch_number} موجود مسبقاً لهذا المنتج")
                
                # حساب التكلفة الإجمالية
                total_cost = Decimal(str(initial_quantity)) * unit_cost
                
                # إنشاء الدفعة
                batch = ProductBatch.objects.create(
                    batch_number=batch_number,
                    product=product,
                    warehouse=warehouse,
                    initial_quantity=initial_quantity,
                    current_quantity=initial_quantity,
                    unit_cost=unit_cost,
                    total_cost=total_cost,
                    expiry_date=expiry_date,
                    production_date=production_date,
                    supplier=supplier,
                    supplier_batch_number=supplier_batch_number,
                    location_code=location_code,
                    notes=notes,
                    created_by=user
                )
                
                # فحص التنبيهات فوراً
                ExpiryService._check_batch_alerts(batch)
                
                logger.info(f"تم إنشاء دفعة جديدة: {batch}")
                return batch
                
        except Exception as e:
            logger.error(f"خطأ في إنشاء الدفعة: {e}")
            raise
    
    @staticmethod
    def consume_from_batches(product, warehouse, quantity, user=None, fifo=True):
        """
        استهلاك كمية من المنتج باستخدام FIFO أو LIFO
        """
        try:
            with transaction.atomic():
                # الحصول على الدفعات المتاحة
                batches_query = ProductBatch.objects.filter(
                    product=product,
                    warehouse=warehouse,
                    status='active',
                    current_quantity__gt=0
                )
                
                # ترتيب حسب FIFO أو LIFO
                if fifo:
                    # FIFO: الأقدم أولاً (حسب تاريخ انتهاء الصلاحية ثم تاريخ الاستلام)
                    batches = batches_query.order_by('expiry_date', 'received_date')
                else:
                    # LIFO: الأحدث أولاً
                    batches = batches_query.order_by('-expiry_date', '-received_date')
                
                remaining_quantity = quantity
                consumed_batches = []
                
                for batch in batches:
                    if remaining_quantity <= 0:
                        break
                    
                    # تحديد الكمية المستهلكة من هذه الدفعة
                    available = batch.available_quantity
                    consume_qty = min(remaining_quantity, available)
                    
                    if consume_qty > 0:
                        # استهلاك من الدفعة
                        batch.consume_quantity(consume_qty, user)
                        
                        consumed_batches.append({
                            'batch': batch,
                            'quantity': consume_qty,
                            'remaining_in_batch': batch.current_quantity
                        })
                        
                        remaining_quantity -= consume_qty
                
                if remaining_quantity > 0:
                    raise ValueError(
                        f"الكمية المطلوبة ({quantity}) أكبر من المتاح. "
                        f"تم استهلاك {quantity - remaining_quantity} فقط"
                    )
                
                logger.info(f"تم استهلاك {quantity} من {product.name} من {len(consumed_batches)} دفعة")
                return consumed_batches
                
        except Exception as e:
            logger.error(f"خطأ في استهلاك الدفعات: {e}")
            raise
    
    @staticmethod
    def get_available_batches(product, warehouse=None, exclude_expired=True):
        """
        الحصول على الدفعات المتاحة لمنتج معين
        """
        try:
            queryset = ProductBatch.objects.filter(
                product=product,
                status='active',
                current_quantity__gt=0
            )
            
            if warehouse:
                queryset = queryset.filter(warehouse=warehouse)
            
            if exclude_expired:
                queryset = queryset.filter(
                    models.Q(expiry_date__isnull=True) |
                    models.Q(expiry_date__gt=timezone.now().date())
                )
            
            return queryset.order_by('expiry_date', 'received_date')
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على الدفعات المتاحة: {e}")
            return ProductBatch.objects.none()
    
    @staticmethod
    def check_expiry_alerts():
        """
        فحص جميع الدفعات وإنشاء التنبيهات اللازمة
        """
        try:
            alerts_created = 0
            today = timezone.now().date()
            
            # الحصول على جميع الدفعات النشطة مع تواريخ انتهاء صلاحية
            active_batches = ProductBatch.objects.filter(
                status='active',
                current_quantity__gt=0,
                expiry_date__isnull=False
            )
            
            for batch in active_batches:
                alerts_created += ExpiryService._check_batch_alerts(batch)
            
            logger.info(f"تم فحص التنبيهات وإنشاء {alerts_created} تنبيه جديد")
            return alerts_created
            
        except Exception as e:
            logger.error(f"خطأ في فحص تنبيهات انتهاء الصلاحية: {e}")
            return 0
    
    @staticmethod
    def _check_batch_alerts(batch):
        """
        فحص تنبيهات دفعة معينة
        """
        try:
            if not batch.expiry_date:
                return 0
            
            today = timezone.now().date()
            days_to_expiry = (batch.expiry_date - today).days
            alerts_created = 0
            
            # الحصول على قواعد التنبيه المطبقة
            rules = ExpiryRule.objects.filter(
                is_active=True
            )
            
            # تطبيق الفلاتر
            applicable_rules = []
            for rule in rules:
                if (not rule.product_category or 
                    batch.product.category == rule.product_category):
                    if (not rule.warehouse or 
                        batch.warehouse == rule.warehouse):
                        applicable_rules.append(rule)
            
            # إنشاء التنبيهات حسب القواعد
            for rule in applicable_rules:
                alert_type = None
                
                if days_to_expiry < 0:
                    # منتهي الصلاحية
                    alert_type = 'expired'
                    if rule.auto_block_expired and batch.status == 'active':
                        batch.status = 'expired'
                        batch.save()
                elif days_to_expiry <= rule.critical_days:
                    # حالة حرجة
                    alert_type = 'critical'
                elif days_to_expiry <= rule.warning_days:
                    # تحذير
                    alert_type = 'near_expiry'
                
                if alert_type:
                    # التحقق من عدم وجود تنبيه مماثل لنفس اليوم
                    existing_alert = ExpiryAlert.objects.filter(
                        batch=batch,
                        alert_type=alert_type,
                        alert_date=today
                    ).exists()
                    
                    if not existing_alert:
                        # إنشاء التنبيه
                        alert = ExpiryAlert.objects.create(
                            batch=batch,
                            alert_type=alert_type,
                            days_to_expiry=days_to_expiry
                        )
                        
                        # إرسال إشعارات للمستخدمين
                        ExpiryService._send_expiry_notifications(alert, rule)
                        alerts_created += 1
            
            return alerts_created
            
        except Exception as e:
            logger.error(f"خطأ في فحص تنبيهات الدفعة {batch.batch_number}: {e}")
            return 0
    
    @staticmethod
    def _send_expiry_notifications(alert, rule):
        """
        إرسال إشعارات انتهاء الصلاحية
        """
        try:
            if not NotificationService:
                return
            
            batch = alert.batch
            
            # تحديد نوع الإشعار
            if alert.alert_type == 'expired':
                title = f"منتج منتهي الصلاحية: {batch.product.name}"
                notification_type = 'danger'
                message = (
                    f"الدفعة '{batch.batch_number}' من المنتج '{batch.product.name}' "
                    f"منتهية الصلاحية منذ {abs(alert.days_to_expiry)} يوم.\n"
                    f"الكمية المتبقية: {batch.current_quantity} {batch.product.unit.symbol}\n"
                    f"المستودع: {batch.warehouse.name}\n"
                    f"يجب سحب المنتج فوراً من المخزون."
                )
            elif alert.alert_type == 'critical':
                title = f"تنبيه حرج - انتهاء صلاحية قريب: {batch.product.name}"
                notification_type = 'warning'
                message = (
                    f"الدفعة '{batch.batch_number}' من المنتج '{batch.product.name}' "
                    f"ستنتهي صلاحيتها خلال {alert.days_to_expiry} يوم.\n"
                    f"الكمية المتبقية: {batch.current_quantity} {batch.product.unit.symbol}\n"
                    f"المستودع: {batch.warehouse.name}\n"
                    f"يُرجى اتخاذ إجراء عاجل."
                )
            else:  # near_expiry
                title = f"تحذير انتهاء صلاحية: {batch.product.name}"
                notification_type = 'info'
                message = (
                    f"الدفعة '{batch.batch_number}' من المنتج '{batch.product.name}' "
                    f"ستنتهي صلاحيتها خلال {alert.days_to_expiry} يوم.\n"
                    f"الكمية المتبقية: {batch.current_quantity} {batch.product.unit.symbol}\n"
                    f"المستودع: {batch.warehouse.name}\n"
                    f"يُرجى التخطيط للبيع أو التصريف."
                )
            
            # إرسال الإشعارات للمستخدمين المحددين في القاعدة
            users_to_notify = rule.notify_users.all()
            
            # إذا لم يتم تحديد مستخدمين، إرسال للمدراء
            if not users_to_notify.exists():
                users_to_notify = User.objects.filter(
                    models.Q(groups__name__in=['مدير مخزون', 'مدير', 'Admin']) |
                    models.Q(is_superuser=True),
                    is_active=True
                ).distinct()
            
            for user in users_to_notify:
                NotificationService.create_notification(
                    user=user,
                    title=title,
                    message=message,
                    notification_type=notification_type
                )
            
        except Exception as e:
            logger.error(f"خطأ في إرسال إشعارات انتهاء الصلاحية: {e}")
    
    @staticmethod
    def get_expiry_report(warehouse=None, days_ahead=90):
        """
        تقرير انتهاء الصلاحية
        """
        try:
            today = timezone.now().date()
            future_date = today + timedelta(days=days_ahead)
            
            # بناء الاستعلام
            queryset = ProductBatch.objects.filter(
                status='active',
                current_quantity__gt=0,
                expiry_date__isnull=False,
                expiry_date__lte=future_date
            ).select_related('product', 'warehouse', 'supplier')
            
            if warehouse:
                queryset = queryset.filter(warehouse=warehouse)
            
            # تصنيف الدفعات
            expired_batches = []
            critical_batches = []
            warning_batches = []
            
            for batch in queryset:
                days_to_expiry = (batch.expiry_date - today).days
                
                if days_to_expiry < 0:
                    expired_batches.append(batch)
                elif days_to_expiry <= 7:
                    critical_batches.append(batch)
                elif days_to_expiry <= 30:
                    warning_batches.append(batch)
            
            # حساب الإحصائيات
            total_value_at_risk = sum(
                batch.current_quantity * batch.unit_cost
                for batch in queryset
            )
            
            expired_value = sum(
                batch.current_quantity * batch.unit_cost
                for batch in expired_batches
            )
            
            return {
                'expired_batches': expired_batches,
                'critical_batches': critical_batches,
                'warning_batches': warning_batches,
                'summary': {
                    'total_batches': queryset.count(),
                    'expired_count': len(expired_batches),
                    'critical_count': len(critical_batches),
                    'warning_count': len(warning_batches),
                    'total_value_at_risk': float(total_value_at_risk),
                    'expired_value': float(expired_value)
                },
                'generated_at': timezone.now()
            }
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء تقرير انتهاء الصلاحية: {e}")
            return {
                'expired_batches': [],
                'critical_batches': [],
                'warning_batches': [],
                'summary': {},
                'error': str(e)
            }
    
    @staticmethod
    def auto_expire_batches():
        """
        تحديث حالة الدفعات المنتهية الصلاحية تلقائياً
        """
        try:
            today = timezone.now().date()
            
            expired_batches = ProductBatch.objects.filter(
                status='active',
                expiry_date__lt=today
            )
            
            expired_count = 0
            for batch in expired_batches:
                batch.status = 'expired'
                batch.save()
                
                # إنشاء تنبيه إذا لم يكن موجوداً
                ExpiryAlert.objects.get_or_create(
                    batch=batch,
                    alert_type='expired',
                    alert_date=today,
                    defaults={'days_to_expiry': (batch.expiry_date - today).days}
                )
                
                expired_count += 1
            
            logger.info(f"تم تحديث حالة {expired_count} دفعة منتهية الصلاحية")
            return expired_count
            
        except Exception as e:
            logger.error(f"خطأ في تحديث الدفعات المنتهية الصلاحية: {e}")
            return 0
    
    @staticmethod
    def get_batch_history(batch):
        """
        الحصول على تاريخ الدفعة (الاستهلاك والحجوزات)
        """
        try:
            consumptions = BatchConsumption.objects.filter(
                batch=batch
            ).order_by('-consumed_at')
            
            from ..models.reservation_system import BatchReservation
            reservations = BatchReservation.objects.filter(
                batch=batch
            ).order_by('-reserved_at')
            
            alerts = ExpiryAlert.objects.filter(
                batch=batch
            ).order_by('-created_at')
            
            return {
                'consumptions': list(consumptions),
                'reservations': list(reservations),
                'alerts': list(alerts),
                'current_status': {
                    'current_quantity': batch.current_quantity,
                    'reserved_quantity': batch.reserved_quantity,
                    'available_quantity': batch.available_quantity,
                    'days_to_expiry': batch.days_to_expiry,
                    'expiry_status': batch.expiry_status
                }
            }
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على تاريخ الدفعة: {e}")
            return {
                'consumptions': [],
                'reservations': [],
                'alerts': [],
                'current_status': {},
                'error': str(e)
            }
    
    @staticmethod
    def get_expiring_products(days_ahead=30):
        """الحصول على المنتجات القريبة من انتهاء الصلاحية"""
        try:
            expiry_date_limit = timezone.now().date() + timedelta(days=days_ahead)
            
            expiring_batches = ProductBatch.objects.filter(
                expiry_date__lte=expiry_date_limit,
                expiry_date__gt=timezone.now().date(),
                current_quantity__gt=0,
                status='active'
            ).select_related('product', 'warehouse').order_by('expiry_date')
            
            return expiring_batches
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على المنتجات القريبة من انتهاء الصلاحية: {e}")
            return ProductBatch.objects.none()
    
    @staticmethod
    def get_expired_products():
        """الحصول على المنتجات منتهية الصلاحية"""
        try:
            expired_batches = ProductBatch.objects.filter(
                expiry_date__lt=timezone.now().date(),
                current_quantity__gt=0,
                status='active'
            ).select_related('product', 'warehouse').order_by('expiry_date')
            
            return expired_batches
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على المنتجات منتهية الصلاحية: {e}")
            return ProductBatch.objects.none()
