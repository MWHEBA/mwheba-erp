"""
خدمة إدارة التنبيهات والإشعارات
"""
from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from datetime import datetime, timedelta
from decimal import Decimal
import logging

from ..models import Notification, SystemSetting, NotificationPreference
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
    def create_notification(user, title, message, notification_type="info", related_model=None, related_id=None, link_url=None, **kwargs):
        """
        إنشاء إشعار جديد مع مراعاة تفضيلات المستخدم
        
        Args:
            user: المستخدم المستهدف
            title: عنوان الإشعار
            message: نص الإشعار
            notification_type: نوع الإشعار
            related_model: اسم النموذج المرتبط (مثل: Sale, Purchase, Product)
            related_id: معرف الكائن المرتبط
            link_url: رابط مباشر (اختياري)
        """
        try:
            # الحصول على تفضيلات المستخدم
            preference = NotificationPreference.get_or_create_for_user(user)
            
            # التحقق من تفعيل هذا النوع من الإشعارات
            if not preference.is_notification_enabled(notification_type):
                logger.info(f"الإشعار {notification_type} معطل للمستخدم {user.username}")
                return None
            
            # التحقق من فترة عدم الإزعاج
            if preference.is_in_do_not_disturb_period():
                logger.info(f"المستخدم {user.username} في فترة عدم الإزعاج")
                return None
            
            # إنشاء الإشعار داخل النظام إذا كان مفعلاً
            notification = None
            if preference.notify_in_app:
                notification = Notification.objects.create(
                    user=user, 
                    title=title, 
                    message=message, 
                    type=notification_type,
                    related_model=related_model,
                    related_id=related_id,
                    link_url=link_url
                )
                logger.info(f"تم إنشاء إشعار جديد: {title} للمستخدم {user.username}")
            
            # إرسال إشعار بريد إلكتروني إذا كان مفعلاً
            if preference.notify_email and preference.email_for_notifications:
                NotificationService._send_email_notification(
                    user, title, message, preference.email_for_notifications
                )
            
            # إرسال إشعار SMS إذا كان مفعلاً
            if preference.notify_sms and preference.phone_for_notifications:
                NotificationService._send_sms_notification(
                    user, title, message, preference.phone_for_notifications
                )
            
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
                    title__contains=f"فاتورة مبيعات متأخرة: {sale.number}",
                    created_at__gte=timezone.now() - timedelta(days=7),
                ).exists()

                if not recent_alert:
                    days_overdue = (today - sale.due_date).days
                    title = f"فاتورة مبيعات متأخرة: {sale.number}"
                    message = (
                        f"فاتورة المبيعات رقم {sale.number} متأخرة منذ {days_overdue} يوم.\n"
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
                    title__contains=f"فاتورة مشتريات مستحقة: {purchase.number}",
                    created_at__gte=timezone.now() - timedelta(days=7),
                ).exists()

                if not recent_alert:
                    days_overdue = (today - purchase.due_date).days
                    title = f"فاتورة مشتريات مستحقة: {purchase.number}"
                    message = (
                        f"فاتورة المشتريات رقم {purchase.number} مستحقة منذ {days_overdue} يوم.\n"
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
    
    @staticmethod
    def _send_email_notification(user, title, message, email):
        """
        إرسال إشعار عبر البريد الإلكتروني
        (يحتاج إعداد SMTP في settings.py)
        """
        try:
            from django.core.mail import send_mail
            from django.conf import settings
            
            subject = f"[{SystemSetting.get_site_name()}] {title}"
            html_message = f"""
            <html>
                <body style="font-family: Arial, sans-serif; direction: rtl; text-align: right;">
                    <div style="background-color: #f8f9fa; padding: 20px; border-radius: 5px;">
                        <h2 style="color: #333;">{title}</h2>
                        <p style="color: #666; line-height: 1.6;">{message}</p>
                        <hr style="border: 1px solid #ddd; margin: 20px 0;">
                        <p style="color: #999; font-size: 12px;">
                            هذا إشعار تلقائي من نظام {SystemSetting.get_site_name()}
                        </p>
                    </div>
                </body>
            </html>
            """
            
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                html_message=html_message,
                fail_silently=True
            )
            
            logger.info(f"تم إرسال إشعار بريد إلكتروني إلى {email}")
            return True
            
        except Exception as e:
            logger.error(f"خطأ في إرسال إشعار البريد الإلكتروني: {e}")
            return False
    
    @staticmethod
    def _send_sms_notification(user, title, message, phone):
        """
        إرسال إشعار عبر SMS
        يدعم Twilio و Nexmo - يتم التفعيل من خلال إعدادات Django
        """
        try:
            from django.conf import settings
            
            # التحقق من تفعيل خدمة SMS
            sms_provider = getattr(settings, 'SMS_PROVIDER', None)
            
            if not sms_provider:
                logger.info(f"خدمة SMS غير مفعلة - تخطي الإرسال إلى {phone}")
                return False
            
            # تكامل مع Twilio
            if sms_provider == 'twilio':
                from twilio.rest import Client
                
                account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', None)
                auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', None)
                from_number = getattr(settings, 'TWILIO_PHONE_NUMBER', None)
                
                if not all([account_sid, auth_token, from_number]):
                    logger.error("إعدادات Twilio غير مكتملة")
                    return False
                
                client = Client(account_sid, auth_token)
                sms_message = client.messages.create(
                    body=f"{title}: {message[:140]}",  # تحديد الطول
                    from_=from_number,
                    to=phone
                )
                
                logger.info(f"تم إرسال SMS عبر Twilio إلى {phone} - SID: {sms_message.sid}")
                return True
            
            # تكامل مع Nexmo/Vonage
            elif sms_provider == 'nexmo':
                import nexmo
                
                api_key = getattr(settings, 'NEXMO_API_KEY', None)
                api_secret = getattr(settings, 'NEXMO_API_SECRET', None)
                from_number = getattr(settings, 'NEXMO_PHONE_NUMBER', None)
                
                if not all([api_key, api_secret, from_number]):
                    logger.error("إعدادات Nexmo غير مكتملة")
                    return False
                
                client = nexmo.Client(key=api_key, secret=api_secret)
                response = client.send_message({
                    'from': from_number,
                    'to': phone,
                    'text': f"{title}: {message[:140]}"
                })
                
                if response['messages'][0]['status'] == '0':
                    logger.info(f"تم إرسال SMS عبر Nexmo إلى {phone}")
                    return True
                else:
                    logger.error(f"فشل إرسال SMS عبر Nexmo: {response['messages'][0]['error-text']}")
                    return False
            
            else:
                logger.warning(f"مزود SMS غير مدعوم: {sms_provider}")
                return False
            
        except ImportError as e:
            logger.error(f"مكتبة SMS غير مثبتة: {e}")
            return False
        except Exception as e:
            logger.error(f"خطأ في إرسال إشعار SMS: {e}")
            return False
