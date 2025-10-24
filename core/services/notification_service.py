"""
خدمة إدارة التنبيهات والإشعارات
"""
from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model
from datetime import datetime, timedelta
from decimal import Decimal
import logging

from ..models import Notification, SystemSetting
from product.models import Product
from sale.models import Sale
from purchase.models import Purchase

User = get_user_model()
logger = logging.getLogger(__name__)


class NotificationService:
    """
    خدمة شاملة لإدارة التنبيهات والإشعارات
    """

    @staticmethod
    def create_notification(user, title, message, notification_type="info", **kwargs):
        """
        إنشاء إشعار جديد
        """
        try:
            notification = Notification.objects.create(
                user=user, title=title, message=message, type=notification_type
            )
            logger.info(f"تم إنشاء إشعار جديد: {title} للمستخدم {user.username}")
            return notification
        except Exception as e:
            logger.error(f"خطأ في إنشاء الإشعار: {e}")
            return None

    @staticmethod
    def create_bulk_notification(users, title, message, notification_type="info"):
        """
        إنشاء إشعار لعدة مستخدمين
        """
        try:
            notifications = []
            for user in users:
                notifications.append(
                    Notification(
                        user=user, title=title, message=message, type=notification_type
                    )
                )

            created_notifications = Notification.objects.bulk_create(notifications)
            logger.info(f"تم إنشاء {len(created_notifications)} إشعار جماعي")
            return created_notifications
        except Exception as e:
            logger.error(f"خطأ في إنشاء الإشعارات الجماعية: {e}")
            return []

    @staticmethod
    def check_low_stock_alerts():
        """
        فحص تنبيهات المخزون المنخفض
        """
        try:
            # الحصول على جميع المنتجات النشطة التي لها حد أدنى محدد
            products = Product.objects.filter(
                is_active=True, min_stock__gt=0
            ).select_related("category", "unit")

            # فلترة المنتجات التي وصلت للحد الأدنى أو أقل
            low_stock_products = [
                product
                for product in products
                if product.current_stock <= product.min_stock
            ]

            if not low_stock_products:
                return []

            # الحصول على المستخدمين المخولين (مدراء المخزون والمدراء)
            authorized_users = User.objects.filter(
                models.Q(groups__name__in=["مدير مخزون", "مدير", "Admin"])
                | models.Q(is_superuser=True),
                is_active=True,
            ).distinct()

            notifications_created = []

            for product in low_stock_products:
                # التحقق من عدم وجود تنبيه حديث لنفس المنتج (خلال آخر 24 ساعة)
                recent_alert = Notification.objects.filter(
                    type="inventory_alert",
                    title__contains=product.name,
                    created_at__gte=timezone.now() - timedelta(hours=24),
                ).exists()

                if not recent_alert:
                    title = f"تنبيه مخزون منخفض: {product.name}"
                    message = (
                        f"المنتج '{product.name}' وصل لمستوى منخفض في المخزون.\n"
                        f"الكمية الحالية: {product.current_stock} {product.unit.symbol}\n"
                        f"الحد الأدنى: {product.min_stock} {product.unit.symbol}\n"
                        f"يُرجى إعادة التزويد في أقرب وقت ممكن."
                    )

                    # إنشاء تنبيه لجميع المستخدمين المخولين
                    for user in authorized_users:
                        notification = NotificationService.create_notification(
                            user=user,
                            title=title,
                            message=message,
                            notification_type="inventory_alert",
                        )
                        if notification:
                            notifications_created.append(notification)

            logger.info(f"تم إنشاء {len(notifications_created)} تنبيه مخزون منخفض")
            return notifications_created

        except Exception as e:
            logger.error(f"خطأ في فحص تنبيهات المخزون المنخفض: {e}")
            return []

    @staticmethod
    def check_due_invoices_alerts():
        """
        فحص تنبيهات الفواتير المستحقة
        ملاحظة: معطل مؤقتاً حتى يتم إضافة حقل due_date للنماذج
        """
        try:
            # معطل مؤقتاً - يحتاج إضافة due_date و remaining_amount للنماذج
            logger.info("فحص تنبيهات الفواتير المستحقة معطل مؤقتاً")
            return []

            # الكود الأصلي (معطل):
            # today = timezone.now().date()
            # overdue_sales = Sale.objects.filter(...)
            # overdue_purchases = Purchase.objects.filter(...)

            # الحصول على المستخدمين المخولين (المحاسبين والمدراء)
            authorized_users = User.objects.filter(
                models.Q(groups__name__in=["محاسب", "مدير", "Admin"])
                | models.Q(is_superuser=True),
                is_active=True,
            ).distinct()

            notifications_created = []

            # تنبيهات فواتير المبيعات المستحقة
            for sale in overdue_sales:
                # التحقق من عدم وجود تنبيه حديث (خلال آخر 7 أيام)
                recent_alert = Notification.objects.filter(
                    type="warning",
                    title__contains=f"فاتورة مبيعات متأخرة: {sale.invoice_number}",
                    created_at__gte=timezone.now() - timedelta(days=7),
                ).exists()

                if not recent_alert:
                    days_overdue = (today - sale.due_date).days
                    title = f"فاتورة مبيعات متأخرة: {sale.invoice_number}"
                    message = (
                        f"فاتورة المبيعات رقم {sale.invoice_number} متأخرة منذ {days_overdue} يوم.\n"
                        f"العميل: {sale.customer.name}\n"
                        f"المبلغ المستحق: {sale.remaining_amount} {SystemSetting.get_currency_symbol()}\n"
                        f"تاريخ الاستحقاق: {sale.due_date}\n"
                        f"يُرجى المتابعة مع العميل لتحصيل المبلغ."
                    )

                    for user in authorized_users:
                        notification = NotificationService.create_notification(
                            user=user,
                            title=title,
                            message=message,
                            notification_type="warning",
                        )
                        if notification:
                            notifications_created.append(notification)

            # تنبيهات فواتير المشتريات المستحقة
            for purchase in overdue_purchases:
                # التحقق من عدم وجود تنبيه حديث (خلال آخر 7 أيام)
                recent_alert = Notification.objects.filter(
                    type="danger",
                    title__contains=f"فاتورة مشتريات مستحقة: {purchase.invoice_number}",
                    created_at__gte=timezone.now() - timedelta(days=7),
                ).exists()

                if not recent_alert:
                    days_overdue = (today - purchase.due_date).days
                    title = f"فاتورة مشتريات مستحقة: {purchase.invoice_number}"
                    message = (
                        f"فاتورة المشتريات رقم {purchase.invoice_number} مستحقة منذ {days_overdue} يوم.\n"
                        f"المورد: {purchase.supplier.name}\n"
                        f"المبلغ المستحق: {purchase.remaining_amount} {SystemSetting.get_currency_symbol()}\n"
                        f"تاريخ الاستحقاق: {purchase.due_date}\n"
                        f"يُرجى سداد المبلغ في أقرب وقت ممكن."
                    )

                    for user in authorized_users:
                        notification = NotificationService.create_notification(
                            user=user,
                            title=title,
                            message=message,
                            notification_type="danger",
                        )
                        if notification:
                            notifications_created.append(notification)

            logger.info(f"تم إنشاء {len(notifications_created)} تنبيه فواتير مستحقة")
            return notifications_created

        except Exception as e:
            logger.error(f"خطأ في فحص تنبيهات الفواتير المستحقة: {e}")
            return []

    @staticmethod
    def check_all_alerts():
        """
        فحص جميع التنبيهات
        """
        try:
            all_notifications = []

            # فحص تنبيهات المخزون المنخفض
            stock_alerts = NotificationService.check_low_stock_alerts()
            all_notifications.extend(stock_alerts)

            # فحص تنبيهات الفواتير المستحقة
            invoice_alerts = NotificationService.check_due_invoices_alerts()
            all_notifications.extend(invoice_alerts)

            logger.info(
                f"تم فحص جميع التنبيهات - إجمالي {len(all_notifications)} تنبيه جديد"
            )
            return all_notifications

        except Exception as e:
            logger.error(f"خطأ في فحص جميع التنبيهات: {e}")
            return []

    @staticmethod
    def mark_as_read(notification_ids, user=None):
        """
        تعليم الإشعارات كمقروءة
        """
        try:
            queryset = Notification.objects.filter(id__in=notification_ids)
            if user:
                queryset = queryset.filter(user=user)

            updated_count = queryset.update(is_read=True)
            logger.info(f"تم تعليم {updated_count} إشعار كمقروء")
            return updated_count

        except Exception as e:
            logger.error(f"خطأ في تعليم الإشعارات كمقروءة: {e}")
            return 0

    @staticmethod
    def get_user_notifications(user, unread_only=False, limit=None):
        """
        الحصول على إشعارات المستخدم
        """
        try:
            queryset = Notification.objects.filter(user=user)

            if unread_only:
                queryset = queryset.filter(is_read=False)

            queryset = queryset.order_by("-created_at")

            if limit:
                queryset = queryset[:limit]

            return list(queryset)

        except Exception as e:
            logger.error(f"خطأ في الحصول على إشعارات المستخدم: {e}")
            return []

    @staticmethod
    def get_notification_stats(user=None):
        """
        الحصول على إحصائيات الإشعارات
        """
        try:
            queryset = Notification.objects.all()
            if user:
                queryset = queryset.filter(user=user)

            stats = {
                "total": queryset.count(),
                "unread": queryset.filter(is_read=False).count(),
                "read": queryset.filter(is_read=True).count(),
                "by_type": {},
            }

            # إحصائيات حسب النوع
            type_stats = (
                queryset.values("type")
                .annotate(count=models.Count("id"))
                .order_by("-count")
            )

            for stat in type_stats:
                stats["by_type"][stat["type"]] = stat["count"]

            return stats

        except Exception as e:
            logger.error(f"خطأ في الحصول على إحصائيات الإشعارات: {e}")
            return {"total": 0, "unread": 0, "read": 0, "by_type": {}}
