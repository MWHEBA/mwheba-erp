"""
خدمة إدارة حجوزات المخزون
تتعامل مع إنشاء وإدارة وتنفيذ حجوزات المخزون
"""
from django.db import models, transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from decimal import Decimal
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

from ..models.reservation_system import (
    StockReservation,
    ReservationFulfillment,
    ReservationRule,
)
from ..models.warehouse import ProductStock
from ..models import Product, Warehouse

User = get_user_model()
logger = logging.getLogger(__name__)


class ReservationService:
    """
    خدمة شاملة لإدارة حجوزات المخزون
    """

    @staticmethod
    def create_reservation(
        product,
        warehouse,
        quantity,
        reservation_type="manual",
        user=None,
        sale_order_id=None,
        purchase_order_id=None,
        reference_number=None,
        expires_in_days=7,
        priority=5,
        notes=None,
    ):
        """
        إنشاء حجز مخزون جديد
        """
        try:
            with transaction.atomic():
                # التحقق من توفر الكمية
                available_quantity = ReservationService.get_available_quantity(
                    product, warehouse
                )

                if available_quantity < quantity:
                    raise ValueError(
                        f"الكمية المطلوبة ({quantity}) غير متاحة. "
                        f"المتاح: {available_quantity}"
                    )

                # تحديد تاريخ انتهاء الصلاحية
                expires_at = timezone.now() + timedelta(days=expires_in_days)

                # إنشاء الحجز
                reservation = StockReservation.objects.create(
                    product=product,
                    warehouse=warehouse,
                    quantity_reserved=quantity,
                    reservation_type=reservation_type,
                    sale_order_id=sale_order_id,
                    purchase_order_id=purchase_order_id,
                    reference_number=reference_number,
                    expires_at=expires_at,
                    priority=priority,
                    notes=notes,
                    reserved_by=user,
                )

                # تحديث المخزون المحجوز
                stock, created = ProductStock.objects.get_or_create(
                    product=product,
                    warehouse=warehouse,
                    defaults={"quantity": 0, "reserved_quantity": 0},
                )
                stock.reserved_quantity += quantity
                stock.save()

                logger.info(f"تم إنشاء حجز جديد: {reservation}")
                return reservation

        except Exception as e:
            logger.error(f"خطأ في إنشاء الحجز: {e}")
            raise

    @staticmethod
    def get_available_quantity(product, warehouse):
        """
        حساب الكمية المتاحة للحجز (المخزون - الحجوزات النشطة)
        """
        try:
            # الحصول على المخزون الحالي
            try:
                stock = ProductStock.objects.get(product=product, warehouse=warehouse)
                total_stock = stock.quantity
            except ProductStock.DoesNotExist:
                total_stock = 0

            # حساب إجمالي الحجوزات النشطة
            active_reservations = (
                StockReservation.objects.filter(
                    product=product, warehouse=warehouse, status="active"
                ).aggregate(
                    total_reserved=models.Sum("quantity_reserved")
                    - models.Sum("quantity_fulfilled")
                )[
                    "total_reserved"
                ]
                or 0
            )

            # الكمية المتاحة = المخزون - الحجوزات النشطة
            available = max(0, total_stock - active_reservations)

            return available

        except Exception as e:
            logger.error(f"خطأ في حساب الكمية المتاحة: {e}")
            return 0

    @staticmethod
    def fulfill_reservation(
        reservation_id, quantity, user=None, inventory_movement=None
    ):
        """
        تنفيذ كمية من الحجز
        """
        try:
            with transaction.atomic():
                reservation = StockReservation.objects.get(id=reservation_id)

                if reservation.status != "active":
                    raise ValueError(
                        f"لا يمكن تنفيذ حجز بحالة: {reservation.get_status_display()}"
                    )

                # تنفيذ الكمية
                reservation.fulfill_quantity(quantity, user)

                # الحصول على سجل التنفيذ الأخير
                fulfillment = reservation.fulfillments.latest("fulfilled_at")

                # ربط بحركة المخزون إذا وجدت
                if inventory_movement:
                    fulfillment.inventory_movement = inventory_movement
                    fulfillment.save()

                logger.info(f"تم تنفيذ {quantity} من الحجز {reservation}")
                return fulfillment

        except Exception as e:
            logger.error(f"خطأ في تنفيذ الحجز: {e}")
            raise

    @staticmethod
    def cancel_reservation(reservation_id, reason=None, user=None):
        """
        إلغاء حجز
        """
        try:
            with transaction.atomic():
                reservation = StockReservation.objects.get(id=reservation_id)
                reservation.cancel_reservation(reason, user)

                logger.info(f"تم إلغاء الحجز {reservation}")
                return reservation

        except Exception as e:
            logger.error(f"خطأ في إلغاء الحجز: {e}")
            raise

    @staticmethod
    def auto_expire_reservations():
        """
        إنهاء صلاحية الحجوزات المنتهية تلقائياً
        """
        try:
            expired_reservations = StockReservation.objects.filter(
                status="active", expires_at__lt=timezone.now()
            )

            expired_count = 0
            for reservation in expired_reservations:
                reservation.status = "expired"
                reservation.save()

                # إنشاء سجل انتهاء الصلاحية
                ReservationFulfillment.objects.create(
                    reservation=reservation,
                    quantity_fulfilled=0,
                    notes="انتهت صلاحية الحجز تلقائياً",
                )

                expired_count += 1

            logger.info(f"تم إنهاء صلاحية {expired_count} حجز")
            return expired_count

        except Exception as e:
            logger.error(f"خطأ في إنهاء صلاحية الحجوزات: {e}")
            return 0

    @staticmethod
    def get_product_reservations(product, warehouse=None, status="active"):
        """
        الحصول على حجوزات منتج معين
        """
        try:
            queryset = StockReservation.objects.filter(
                product=product, status=status
            ).select_related("warehouse", "reserved_by")

            if warehouse:
                queryset = queryset.filter(warehouse=warehouse)

            return queryset.order_by("priority", "reserved_at")

        except Exception as e:
            logger.error(f"خطأ في الحصول على حجوزات المنتج: {e}")
            return StockReservation.objects.none()

    @staticmethod
    def get_reservation_summary(warehouse=None):
        """
        ملخص الحجوزات
        """
        try:
            queryset = StockReservation.objects.all()

            if warehouse:
                queryset = queryset.filter(warehouse=warehouse)

            summary = queryset.aggregate(
                total_reservations=models.Count("id"),
                active_reservations=models.Count(
                    "id", filter=models.Q(status="active")
                ),
                fulfilled_reservations=models.Count(
                    "id", filter=models.Q(status="fulfilled")
                ),
                cancelled_reservations=models.Count(
                    "id", filter=models.Q(status="cancelled")
                ),
                expired_reservations=models.Count(
                    "id", filter=models.Q(status="expired")
                ),
                total_quantity_reserved=models.Sum(
                    "quantity_reserved", filter=models.Q(status="active")
                )
                or 0,
                total_quantity_fulfilled=models.Sum("quantity_fulfilled") or 0,
            )

            # حساب معدل التنفيذ
            if summary["total_quantity_reserved"] > 0:
                fulfillment_rate = (
                    summary["total_quantity_fulfilled"]
                    / summary["total_quantity_reserved"]
                ) * 100
            else:
                fulfillment_rate = 0

            summary["fulfillment_rate"] = round(fulfillment_rate, 2)

            return summary

        except Exception as e:
            logger.error(f"خطأ في إنشاء ملخص الحجوزات: {e}")
            return {}

    @staticmethod
    def allocate_stock_by_priority(product, warehouse, available_quantity):
        """
        تخصيص المخزون حسب الأولوية
        """
        try:
            # الحصول على الحجوزات النشطة مرتبة حسب الأولوية
            reservations = StockReservation.objects.filter(
                product=product, warehouse=warehouse, status="active"
            ).order_by("priority", "reserved_at")

            allocated_quantity = 0
            allocation_results = []

            for reservation in reservations:
                remaining_needed = reservation.quantity_remaining

                if allocated_quantity >= available_quantity:
                    # لا توجد كمية متاحة أكثر
                    allocation_results.append(
                        {
                            "reservation": reservation,
                            "allocated": 0,
                            "remaining_needed": remaining_needed,
                            "status": "waiting",
                        }
                    )
                    continue

                # حساب الكمية التي يمكن تخصيصها
                can_allocate = min(
                    remaining_needed, available_quantity - allocated_quantity
                )

                allocated_quantity += can_allocate

                allocation_results.append(
                    {
                        "reservation": reservation,
                        "allocated": can_allocate,
                        "remaining_needed": remaining_needed - can_allocate,
                        "status": "allocated"
                        if can_allocate == remaining_needed
                        else "partial",
                    }
                )

            return {
                "total_allocated": allocated_quantity,
                "remaining_stock": available_quantity - allocated_quantity,
                "allocations": allocation_results,
            }

        except Exception as e:
            logger.error(f"خطأ في تخصيص المخزون: {e}")
            return {
                "total_allocated": 0,
                "remaining_stock": available_quantity,
                "allocations": [],
            }

    @staticmethod
    def create_auto_reservation_for_order(order_type, order_id, order_items, user=None):
        """
        إنشاء حجوزات تلقائية لطلب
        """
        try:
            reservations_created = []

            with transaction.atomic():
                for item in order_items:
                    product = item.get("product")
                    warehouse = item.get("warehouse")
                    quantity = item.get("quantity")

                    if not all([product, warehouse, quantity]):
                        continue

                    # التحقق من قواعد الحجز التلقائي
                    rules = ReservationRule.objects.filter(
                        is_active=True, rule_type="auto_reserve_on_order"
                    )

                    # تطبيق القواعد
                    should_reserve = False
                    expiry_days = 7

                    for rule in rules:
                        if (
                            not rule.product_category
                            or product.category == rule.product_category
                        ):
                            if not rule.warehouse or warehouse == rule.warehouse:
                                should_reserve = rule.auto_reserve_enabled
                                expiry_days = rule.default_expiry_days
                                break

                    if should_reserve:
                        try:
                            reservation = ReservationService.create_reservation(
                                product=product,
                                warehouse=warehouse,
                                quantity=quantity,
                                reservation_type=order_type,
                                user=user,
                                sale_order_id=order_id
                                if order_type == "sale_order"
                                else None,
                                purchase_order_id=order_id
                                if order_type == "purchase_order"
                                else None,
                                reference_number=f"{order_type.upper()}-{order_id}",
                                expires_in_days=expiry_days,
                                priority=3,  # أولوية متوسطة للطلبات
                                notes=f"حجز تلقائي لـ {order_type} رقم {order_id}",
                            )

                            reservations_created.append(reservation)

                        except Exception as e:
                            logger.warning(
                                f"فشل في إنشاء حجز تلقائي للمنتج {product.name}: {e}"
                            )
                            continue

            logger.info(
                f"تم إنشاء {len(reservations_created)} حجز تلقائي للطلب {order_id}"
            )
            return reservations_created

        except Exception as e:
            logger.error(f"خطأ في إنشاء الحجوزات التلقائية: {e}")
            return []

    @staticmethod
    def get_low_stock_with_reservations(warehouse=None):
        """
        تقرير المنتجات منخفضة المخزون مع مراعاة الحجوزات
        """
        try:
            # بناء الاستعلام
            from ..models.warehouse import ProductStock

            queryset = ProductStock.objects.select_related("product", "warehouse")

            if warehouse:
                queryset = queryset.filter(warehouse=warehouse)

            low_stock_data = []

            for stock in queryset:
                # حساب الكمية المتاحة (بعد خصم الحجوزات)
                available_quantity = ReservationService.get_available_quantity(
                    stock.product, stock.warehouse
                )

                # التحقق من المخزون المنخفض
                min_stock = stock.product.min_stock or 0

                if available_quantity <= min_stock:
                    # الحصول على الحجوزات النشطة
                    active_reservations = (
                        StockReservation.objects.filter(
                            product=stock.product,
                            warehouse=stock.warehouse,
                            status="active",
                        ).aggregate(
                            total_reserved=models.Sum("quantity_reserved")
                            - models.Sum("quantity_fulfilled")
                        )[
                            "total_reserved"
                        ]
                        or 0
                    )

                    low_stock_data.append(
                        {
                            "product": stock.product,
                            "warehouse": stock.warehouse,
                            "total_stock": stock.quantity,
                            "reserved_quantity": active_reservations,
                            "available_quantity": available_quantity,
                            "min_stock": min_stock,
                            "shortage": max(0, min_stock - available_quantity),
                            "status": "نفد" if available_quantity <= 0 else "منخفض",
                        }
                    )

            # ترتيب حسب النقص
            low_stock_data.sort(key=lambda x: x["shortage"], reverse=True)

            return low_stock_data

        except Exception as e:
            logger.error(f"خطأ في تقرير المخزون المنخفض: {e}")
            return []
