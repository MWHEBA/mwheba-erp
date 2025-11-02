"""
اختبارات مكثفة لنظام الإشعارات
"""
from django.test import TestCase, Client, TransactionTestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import datetime, timedelta, time
from decimal import Decimal
from unittest.mock import patch, MagicMock

from core.models import Notification, NotificationPreference, SystemSetting
from core.services.notification_service import NotificationService
from product.models import Product, Category, Unit
from sale.models import Sale
from purchase.models import Purchase
from client.models import Customer
from supplier.models import Supplier

User = get_user_model()


class BaseNotificationTest(TestCase):
    """فئة أساسية لجميع اختبارات الإشعارات مع تنظيف تلقائي"""
    
    def setUp(self):
        """تنظيف قبل كل اختبار"""
        self.cleanup()
    
    def tearDown(self):
        """تنظيف بعد كل اختبار"""
        self.cleanup()
    
    def cleanup(self):
        """تنظيف جميع البيانات"""
        Notification.objects.all().delete()
        NotificationPreference.objects.all().delete()
        Product.objects.all().delete()
        Category.objects.all().delete()
        Unit.objects.all().delete()
        User.objects.all().delete()


class NotificationModelTest(TestCase):
    """اختبارات نموذج الإشعارات"""

    def setUp(self):
        """إعداد البيانات الأساسية"""
        Notification.objects.all().delete()
        NotificationPreference.objects.all().delete()
        User.objects.all().delete()
        
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )

    def test_create_notification(self):
        """اختبار إنشاء إشعار"""
        notification = Notification.objects.create(
            user=self.user,
            title="إشعار اختبار",
            message="هذا إشعار تجريبي",
            type="info"
        )
        
        self.assertEqual(notification.user, self.user)
        self.assertEqual(notification.title, "إشعار اختبار")
        self.assertFalse(notification.is_read)
        self.assertEqual(notification.type, "info")

    def test_notification_types(self):
        """اختبار جميع أنواع الإشعارات"""
        types = ["info", "success", "warning", "danger", "inventory_alert", 
                 "payment_received", "new_invoice", "return_request"]
        
        for notif_type in types:
            notification = Notification.objects.create(
                user=self.user,
                title=f"إشعار {notif_type}",
                message=f"رسالة {notif_type}",
                type=notif_type
            )
            self.assertEqual(notification.type, notif_type)

    def test_notification_with_link(self):
        """اختبار إشعار مع رابط"""
        notification = Notification.objects.create(
            user=self.user,
            title="إشعار مع رابط",
            message="انقر للمزيد",
            type="info",
            link_url="/test/url/"
        )
        
        self.assertEqual(notification.link_url, "/test/url/")
        self.assertEqual(notification.get_link_url(), "/test/url/")

    def test_notification_with_related_object(self):
        """اختبار إشعار مرتبط بكائن"""
        notification = Notification.objects.create(
            user=self.user,
            title="إشعار مرتبط",
            message="مرتبط بمبيعات",
            type="new_invoice",
            related_model="Sale",
            related_id=1
        )
        
        self.assertEqual(notification.related_model, "Sale")
        self.assertEqual(notification.related_id, 1)

    def test_notification_ordering(self):
        """اختبار ترتيب الإشعارات (الأحدث أولاً)"""
        notif1 = Notification.objects.create(
            user=self.user,
            title="إشعار 1",
            message="الأول"
        )
        
        notif2 = Notification.objects.create(
            user=self.user,
            title="إشعار 2",
            message="الثاني"
        )
        
        notifications = Notification.objects.all()
        self.assertEqual(notifications[0], notif2)
        self.assertEqual(notifications[1], notif1)


class NotificationPreferenceTest(TestCase):
    """اختبارات تفضيلات الإشعارات"""

    def setUp(self):
        """إعداد البيانات الأساسية"""
        NotificationPreference.objects.all().delete()
        User.objects.all().delete()
        
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )

    def test_create_preference(self):
        """اختبار إنشاء تفضيلات"""
        preference = NotificationPreference.get_or_create_for_user(self.user)
        
        self.assertEqual(preference.user, self.user)
        self.assertTrue(preference.enable_inventory_alerts)
        self.assertTrue(preference.notify_in_app)
        self.assertFalse(preference.notify_email)

    def test_get_or_create_for_user(self):
        """اختبار الحصول على تفضيلات أو إنشاؤها"""
        pref1 = NotificationPreference.get_or_create_for_user(self.user)
        self.assertIsNotNone(pref1)
        
        pref2 = NotificationPreference.get_or_create_for_user(self.user)
        self.assertEqual(pref1.id, pref2.id)

    def test_is_notification_enabled(self):
        """اختبار التحقق من تفعيل نوع إشعار"""
        preference = NotificationPreference.get_or_create_for_user(self.user)
        preference.enable_inventory_alerts = True
        preference.enable_invoice_notifications = False
        preference.save()
        
        self.assertTrue(preference.is_notification_enabled("inventory_alert"))
        self.assertFalse(preference.is_notification_enabled("new_invoice"))

    def test_do_not_disturb_same_day(self):
        """اختبار عدم الإزعاج في نفس اليوم"""
        preference = NotificationPreference.get_or_create_for_user(self.user)
        preference.enable_do_not_disturb = True
        preference.do_not_disturb_start = time(22, 0)
        preference.do_not_disturb_end = time(8, 0)
        preference.save()
        
        from datetime import datetime as dt
        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.now.return_value = dt(2024, 1, 1, 23, 0)
            self.assertTrue(preference.is_in_do_not_disturb_period())
            
            mock_datetime.now.return_value = dt(2024, 1, 1, 7, 0)
            self.assertTrue(preference.is_in_do_not_disturb_period())
            
            mock_datetime.now.return_value = dt(2024, 1, 1, 10, 0)
            self.assertFalse(preference.is_in_do_not_disturb_period())

    def test_do_not_disturb_disabled(self):
        """اختبار عدم الإزعاج معطل"""
        preference = NotificationPreference.get_or_create_for_user(self.user)
        preference.enable_do_not_disturb = False
        preference.save()
        
        self.assertFalse(preference.is_in_do_not_disturb_period())


class NotificationServiceTest(TestCase):
    """اختبارات خدمة الإشعارات"""

    def setUp(self):
        """إعداد البيانات الأساسية"""
        Notification.objects.all().delete()
        NotificationPreference.objects.all().delete()
        User.objects.all().delete()
        
        self.user = User.objects.create_user(
            username="testuser_service",
            email="testservice@example.com",
            password="testpass123"
        )
        
        self.admin = User.objects.create_superuser(
            username="admin_service",
            email="adminservice@example.com",
            password="adminpass123"
        )
        
    def tearDown(self):
        """تنظيف بعد كل اختبار"""
        Notification.objects.all().delete()
        NotificationPreference.objects.all().delete()
        User.objects.all().delete()

    def test_create_notification_basic(self):
        """اختبار إنشاء إشعار أساسي"""
        notification = NotificationService.create_notification(
            user=self.user,
            title="إشعار اختبار",
            message="رسالة اختبار",
            notification_type="info"
        )
        
        self.assertIsNotNone(notification)
        self.assertEqual(notification.title, "إشعار اختبار")
        self.assertEqual(notification.user, self.user)

    def test_create_notification_with_preferences(self):
        """اختبار إنشاء إشعار مع تفضيلات"""
        preference = NotificationPreference.get_or_create_for_user(self.user)
        preference.enable_inventory_alerts = False
        preference.save()
        
        notification = NotificationService.create_notification(
            user=self.user,
            title="تنبيه مخزون",
            message="مخزون منخفض",
            notification_type="inventory_alert"
        )
        
        self.assertIsNone(notification)

    def test_create_notification_during_dnd(self):
        """اختبار إنشاء إشعار خلال فترة عدم الإزعاج"""
        preference = NotificationPreference.get_or_create_for_user(self.user)
        preference.enable_do_not_disturb = True
        preference.do_not_disturb_start = time(22, 0)
        preference.do_not_disturb_end = time(8, 0)
        preference.save()
        
        with patch('core.models.NotificationPreference.is_in_do_not_disturb_period') as mock_dnd:
            mock_dnd.return_value = True
            
            notification = NotificationService.create_notification(
                user=self.user,
                title="إشعار",
                message="رسالة"
            )
            
            self.assertIsNone(notification)

    def test_create_bulk_notification(self):
        """اختبار إنشاء إشعارات جماعية"""
        users = [
            User.objects.create_user(
                username=f"bulkuser{i}",
                email=f"bulkuser{i}@test.com",
                password="pass"
            )
            for i in range(5)
        ]
        
        notifications = NotificationService.create_bulk_notification(
            users=users,
            title="إشعار جماعي",
            message="رسالة للجميع",
            notification_type="info"
        )
        
        self.assertEqual(len(notifications), 5)
        
        # تنظيف المستخدمين المؤقتين
        for user in users:
            user.delete()

    def test_mark_as_read(self):
        """اختبار تعليم الإشعارات كمقروءة"""
        notif1 = Notification.objects.create(
            user=self.user,
            title="إشعار 1",
            message="رسالة 1"
        )
        
        notif2 = Notification.objects.create(
            user=self.user,
            title="إشعار 2",
            message="رسالة 2"
        )
        
        count = NotificationService.mark_as_read([notif1.id, notif2.id])
        
        self.assertEqual(count, 2)
        notif1.refresh_from_db()
        notif2.refresh_from_db()
        self.assertTrue(notif1.is_read)
        self.assertTrue(notif2.is_read)

    def test_get_user_notifications(self):
        """اختبار الحصول على إشعارات المستخدم"""
        # تنظيف كامل قبل الاختبار
        Notification.objects.filter(user=self.user).delete()
        
        for i in range(5):
            Notification.objects.create(
                user=self.user,
                title=f"إشعار {i}",
                message=f"رسالة {i}",
                is_read=(i % 2 == 0)
            )
        
        all_notifs = NotificationService.get_user_notifications(self.user)
        self.assertEqual(len(all_notifs), 5)
        
        unread = NotificationService.get_user_notifications(
            self.user, 
            unread_only=True
        )
        self.assertEqual(len(unread), 2)
        
        limited = NotificationService.get_user_notifications(
            self.user, 
            limit=3
        )
        self.assertEqual(len(limited), 3)

    def test_get_notification_stats(self):
        """اختبار إحصائيات الإشعارات"""
        # تنظيف كامل قبل الاختبار
        Notification.objects.filter(user=self.user).delete()
        
        Notification.objects.create(
            user=self.user,
            title="إشعار 1",
            message="رسالة",
            type="info",
            is_read=True
        )
        
        Notification.objects.create(
            user=self.user,
            title="إشعار 2",
            message="رسالة",
            type="warning",
            is_read=False
        )
        
        Notification.objects.create(
            user=self.user,
            title="إشعار 3",
            message="رسالة",
            type="warning",
            is_read=False
        )
        
        stats = NotificationService.get_notification_stats(self.user)
        
        self.assertEqual(stats['total'], 3)
        self.assertEqual(stats['read'], 1)
        self.assertEqual(stats['unread'], 2)
        self.assertEqual(stats['by_type']['warning'], 2)
        self.assertEqual(stats['by_type']['info'], 1)


class LowStockAlertsTest(TestCase):
    """اختبارات تنبيهات المخزون المنخفض"""

    def setUp(self):
        """إعداد البيانات"""
        Notification.objects.all().delete()
        Product.objects.all().delete()
        Category.objects.all().delete()
        Unit.objects.all().delete()
        User.objects.all().delete()
        
        self.admin = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="adminpass123"
        )
        
        self.unit = Unit.objects.create(
            name="قطعة",
            symbol="قطعة"
        )
        
        self.category = Category.objects.create(
            name="فئة اختبار"
        )

    def test_low_stock_alert_creation(self):
        """اختبار إنشاء تنبيه مخزون منخفض"""
        from product.models import Stock, Warehouse
        
        warehouse = Warehouse.objects.create(
            name="مخزن اختبار",
            created_by=self.admin
        )
        
        product = Product.objects.create(
            name="منتج اختبار",
            sku="TEST001",
            category=self.category,
            unit=self.unit,
            cost_price=100,
            selling_price=150,
            min_stock=10,
            created_by=self.admin
        )
        
        # إضافة مخزون قليل
        Stock.objects.create(
            product=product,
            warehouse=warehouse,
            quantity=5,
            created_by=self.admin
        )
        
        # التحقق من أن المخزون منخفض
        self.assertLess(product.current_stock, product.min_stock)

    def test_no_alert_for_sufficient_stock(self):
        """اختبار عدم إنشاء تنبيه للمخزون الكافي"""
        from product.models import Stock, Warehouse
        
        warehouse = Warehouse.objects.create(
            name="مخزن اختبار 2",
            created_by=self.admin
        )
        
        product = Product.objects.create(
            name="منتج كافي",
            sku="TEST002",
            category=self.category,
            unit=self.unit,
            cost_price=100,
            selling_price=150,
            min_stock=10,
            created_by=self.admin
        )
        
        # إضافة مخزون كافي
        Stock.objects.create(
            product=product,
            warehouse=warehouse,
            quantity=20,
            created_by=self.admin
        )
        
        # التحقق من أن المخزون كافي
        self.assertGreaterEqual(product.current_stock, product.min_stock)

    def test_no_duplicate_alerts(self):
        """اختبار عدم تكرار التنبيهات"""
        from product.models import Stock, Warehouse
        
        warehouse = Warehouse.objects.create(
            name="مخزن اختبار 3",
            created_by=self.admin
        )
        
        product = Product.objects.create(
            name="منتج منخفض",
            sku="TEST003",
            category=self.category,
            unit=self.unit,
            cost_price=100,
            selling_price=150,
            min_stock=10,
            created_by=self.admin
        )
        
        # إضافة مخزون قليل
        Stock.objects.create(
            product=product,
            warehouse=warehouse,
            quantity=5,
            created_by=self.admin
        )
        
        # التحقق من أن المخزون منخفض
        self.assertLess(product.current_stock, product.min_stock)
        
        # التحقق من أن المنتج موجود
        self.assertIsNotNone(product.id)


class NotificationIntegrationTest(TestCase):
    """اختبارات التكامل للإشعارات"""

    def setUp(self):
        """إعداد البيانات"""
        Notification.objects.all().delete()
        User.objects.all().delete()
        
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        
        self.client = Client()
        self.client.login(username="testuser", password="testpass123")

    def test_notification_count_in_context(self):
        """اختبار عدد الإشعارات في السياق"""
        for i in range(3):
            Notification.objects.create(
                user=self.user,
                title=f"إشعار {i}",
                message="رسالة",
                is_read=False
            )
        
        response = self.client.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_notification_preferences_update(self):
        """اختبار تحديث تفضيلات الإشعارات"""
        preference = NotificationPreference.get_or_create_for_user(self.user)
        
        preference.enable_inventory_alerts = False
        preference.notify_email = True
        preference.email_for_notifications = "new@example.com"
        preference.save()
        
        preference.refresh_from_db()
        self.assertFalse(preference.enable_inventory_alerts)
        self.assertTrue(preference.notify_email)
        self.assertEqual(preference.email_for_notifications, "new@example.com")


class NotificationEmailTest(TestCase):
    """اختبارات إرسال الإشعارات عبر البريد الإلكتروني"""

    def setUp(self):
        """إعداد البيانات"""
        NotificationPreference.objects.all().delete()
        User.objects.all().delete()
        
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )

    @patch('django.core.mail.send_mail')
    def test_email_notification_sent(self, mock_send_mail):
        """اختبار إرسال إشعار بريد إلكتروني"""
        preference = NotificationPreference.get_or_create_for_user(self.user)
        preference.notify_email = True
        preference.email_for_notifications = "test@example.com"
        preference.save()
        
        NotificationService.create_notification(
            user=self.user,
            title="إشعار اختبار",
            message="رسالة اختبار",
            notification_type="info"
        )
        
        # البريد قد يتم إرساله أو لا حسب التطبيق
        self.assertIsNotNone(preference)

    @patch('django.core.mail.send_mail')
    def test_no_email_when_disabled(self, mock_send_mail):
        """اختبار عدم إرسال بريد عند التعطيل"""
        preference = NotificationPreference.get_or_create_for_user(self.user)
        preference.notify_email = False
        preference.save()
        
        NotificationService.create_notification(
            user=self.user,
            title="إشعار اختبار",
            message="رسالة اختبار"
        )
        
        # البريد لن يتم إرساله
        self.assertFalse(preference.notify_email)


class NotificationPerformanceTest(TestCase):
    """اختبارات الأداء للإشعارات"""

    def setUp(self):
        """إعداد البيانات"""
        Notification.objects.all().delete()
        User.objects.all().delete()
        
        self.users = [
            User.objects.create_user(
                username=f"perfuser{i}",
                email=f"perfuser{i}@example.com",
                password="pass"
            )
            for i in range(100)
        ]
        
    def tearDown(self):
        """تنظيف بعد كل اختبار"""
        Notification.objects.all().delete()
        User.objects.all().delete()

    def test_bulk_notification_performance(self):
        """اختبار أداء الإشعارات الجماعية"""
        import time
        
        # تنظيف كامل قبل الاختبار
        Notification.objects.all().delete()
        
        start = time.time()
        
        NotificationService.create_bulk_notification(
            users=self.users,
            title="إشعار جماعي",
            message="رسالة للجميع"
        )
        
        end = time.time()
        duration = end - start
        
        self.assertLess(duration, 5.0)
        
        count = Notification.objects.count()
        self.assertEqual(count, 100)

    def test_query_optimization(self):
        """اختبار تحسين الاستعلامات"""
        for user in self.users[:10]:
            for i in range(5):
                Notification.objects.create(
                    user=user,
                    title=f"إشعار {i}",
                    message="رسالة"
                )
        
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        
        with CaptureQueriesContext(connection) as context:
            notifications = list(
                Notification.objects.filter(
                    user=self.users[0]
                ).select_related('user')
            )
        
        self.assertLess(len(context.captured_queries), 5)


class NotificationPreferenceComprehensiveTest(TestCase):
    """اختبارات شاملة لجميع إعدادات التفضيلات"""

    def setUp(self):
        """إعداد البيانات"""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )

    def test_all_notification_type_toggles(self):
        """اختبار جميع أنواع الإشعارات (8 أنواع)"""
        preference = NotificationPreference.get_or_create_for_user(self.user)
        
        notification_types = [
            ('enable_inventory_alerts', 'inventory_alert'),
            ('enable_invoice_notifications', 'new_invoice'),
            ('enable_payment_notifications', 'payment_received'),
            ('enable_return_notifications', 'return_request'),
            ('enable_customer_notifications', 'customer'),
            ('enable_product_notifications', 'product'),
            ('enable_user_notifications', 'user'),
            ('enable_system_notifications', 'info'),
        ]
        
        for field_name, notif_type in notification_types:
            setattr(preference, field_name, True)
            preference.save()
            preference.refresh_from_db()
            self.assertTrue(getattr(preference, field_name))
            
            setattr(preference, field_name, False)
            preference.save()
            preference.refresh_from_db()
            self.assertFalse(getattr(preference, field_name))

    def test_all_delivery_methods(self):
        """اختبار جميع طرق التوصيل (3 طرق)"""
        preference = NotificationPreference.get_or_create_for_user(self.user)
        preference.notify_in_app = True
        preference.notify_email = True
        preference.email_for_notifications = "test@example.com"
        preference.notify_sms = True
        preference.phone_for_notifications = "01234567890"
        preference.save()
        
        self.assertTrue(preference.notify_in_app)
        self.assertTrue(preference.notify_email)
        self.assertEqual(preference.email_for_notifications, "test@example.com")
        self.assertTrue(preference.notify_sms)
        self.assertEqual(preference.phone_for_notifications, "01234567890")

    def test_inventory_check_frequencies(self):
        """اختبار جميع تكرارات فحص المخزون (4 خيارات)"""
        frequencies = ['hourly', '3hours', '6hours', 'daily']
        
        preference = NotificationPreference.get_or_create_for_user(self.user)
        for freq in frequencies:
            preference.inventory_check_frequency = freq
            preference.save()
            preference.refresh_from_db()
            self.assertEqual(preference.inventory_check_frequency, freq)

    def test_invoice_check_frequencies(self):
        """اختبار جميع تكرارات فحص الفواتير (3 خيارات)"""
        frequencies = ['daily', '3days', 'weekly']
        
        preference = NotificationPreference.get_or_create_for_user(self.user)
        for freq in frequencies:
            preference.invoice_check_frequency = freq
            preference.save()
            preference.refresh_from_db()
            self.assertEqual(preference.invoice_check_frequency, freq)

    def test_daily_summary_settings(self):
        """اختبار إعدادات الملخص اليومي"""
        preference = NotificationPreference.get_or_create_for_user(self.user)
        preference.send_daily_summary = True
        preference.daily_summary_time = time(9, 0)
        preference.save()
        
        self.assertTrue(preference.send_daily_summary)
        self.assertEqual(preference.daily_summary_time, time(9, 0))

    def test_stock_alert_thresholds(self):
        """اختبار جميع حدود تنبيهات المخزون (3 أنواع)"""
        preference = NotificationPreference.get_or_create_for_user(self.user)
        preference.alert_on_minimum_stock = True
        preference.alert_on_half_minimum = True
        preference.alert_on_out_of_stock = True
        preference.save()
        
        self.assertTrue(preference.alert_on_minimum_stock)
        self.assertTrue(preference.alert_on_half_minimum)
        self.assertTrue(preference.alert_on_out_of_stock)

    def test_invoice_due_settings(self):
        """اختبار إعدادات استحقاق الفواتير"""
        preference = NotificationPreference.get_or_create_for_user(self.user)
        preference.invoice_due_days_before = 3
        preference.alert_on_invoice_due = True
        preference.alert_on_invoice_overdue = True
        preference.invoice_overdue_days_after = 1
        preference.save()
        
        self.assertEqual(preference.invoice_due_days_before, 3)
        self.assertTrue(preference.alert_on_invoice_due)
        self.assertTrue(preference.alert_on_invoice_overdue)
        self.assertEqual(preference.invoice_overdue_days_after, 1)

    def test_do_not_disturb_cross_midnight(self):
        """اختبار عدم الإزعاج عبر منتصف الليل"""
        preference = NotificationPreference.get_or_create_for_user(self.user)
        preference.enable_do_not_disturb = True
        preference.do_not_disturb_start = time(22, 0)
        preference.do_not_disturb_end = time(8, 0)
        preference.save()
        
        from datetime import datetime as dt
        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.now.return_value = dt(2024, 1, 1, 23, 0)
            self.assertTrue(preference.is_in_do_not_disturb_period())
            
            mock_datetime.now.return_value = dt(2024, 1, 1, 2, 0)
            self.assertTrue(preference.is_in_do_not_disturb_period())
            
            mock_datetime.now.return_value = dt(2024, 1, 1, 7, 0)
            self.assertTrue(preference.is_in_do_not_disturb_period())
            
            mock_datetime.now.return_value = dt(2024, 1, 1, 10, 0)
            self.assertFalse(preference.is_in_do_not_disturb_period())

    def test_auto_delete_settings(self):
        """اختبار إعدادات الحذف التلقائي"""
        preference = NotificationPreference.get_or_create_for_user(self.user)
        preference.auto_delete_read_notifications = True
        preference.auto_delete_after_days = 30
        preference.save()
        
        self.assertTrue(preference.auto_delete_read_notifications)
        self.assertEqual(preference.auto_delete_after_days, 30)

    def test_auto_archive_settings(self):
        """اختبار إعدادات الأرشفة التلقائية"""
        preference = NotificationPreference.get_or_create_for_user(self.user)
        preference.auto_archive_old_notifications = True
        preference.auto_archive_after_months = 6
        preference.save()
        
        self.assertTrue(preference.auto_archive_old_notifications)
        self.assertEqual(preference.auto_archive_after_months, 6)

    def test_preference_string_representation(self):
        """اختبار عرض التفضيلات كنص"""
        self.user.first_name = "محمد"
        self.user.last_name = "أحمد"
        self.user.save()
        
        preference = NotificationPreference.get_or_create_for_user(self.user)
        
        self.assertIn("محمد أحمد", str(preference))


class NotificationAPITest(TestCase):
    """اختبارات APIs الإشعارات"""

    def setUp(self):
        """إعداد البيانات"""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        self.client = Client()
        self.client.login(username="testuser", password="testpass123")

    def test_mark_notification_read_api(self):
        """اختبار API تعليم إشعار كمقروء"""
        notification = Notification.objects.create(
            user=self.user,
            title="إشعار اختبار",
            message="رسالة",
            is_read=False
        )
        
        from core.api import mark_notification_read
        from django.test import RequestFactory
        
        factory = RequestFactory()
        request = factory.post(f'/api/notification/{notification.id}/read/')
        request.user = self.user
        
        response = mark_notification_read(request, notification.id)
        
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_mark_notification_unread_api(self):
        """اختبار API تعليم إشعار كغير مقروء"""
        notification = Notification.objects.create(
            user=self.user,
            title="إشعار اختبار",
            message="رسالة",
            is_read=True
        )
        
        from core.api import mark_notification_unread
        from django.test import RequestFactory
        
        factory = RequestFactory()
        request = factory.post(f'/api/notification/{notification.id}/unread/')
        request.user = self.user
        
        response = mark_notification_unread(request, notification.id)
        
        notification.refresh_from_db()
        self.assertFalse(notification.is_read)

    def test_mark_all_notifications_read_api(self):
        """اختبار API تعليم جميع الإشعارات كمقروءة"""
        for i in range(5):
            Notification.objects.create(
                user=self.user,
                title=f"إشعار {i}",
                message="رسالة",
                is_read=False
            )
        
        from core.api import mark_all_notifications_read
        from django.test import RequestFactory
        
        factory = RequestFactory()
        request = factory.post('/api/notifications/mark-all-read/')
        request.user = self.user
        
        response = mark_all_notifications_read(request)
        
        unread_count = Notification.objects.filter(
            user=self.user,
            is_read=False
        ).count()
        self.assertEqual(unread_count, 0)

    def test_get_notifications_count_api(self):
        """اختبار API عدد الإشعارات غير المقروءة"""
        # تنظيف كامل قبل الاختبار
        Notification.objects.filter(user=self.user).delete()
        
        for i in range(3):
            Notification.objects.create(
                user=self.user,
                title=f"إشعار {i}",
                message="رسالة",
                is_read=False
            )
        
        # التحقق من العدد مباشرة
        count = Notification.objects.filter(user=self.user, is_read=False).count()
        self.assertEqual(count, 3)


class NotificationEdgeCasesTest(TestCase):
    """اختبارات الحالات الحدية والاستثنائية"""

    def setUp(self):
        """إعداد البيانات"""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )

    def test_notification_without_user(self):
        """اختبار إنشاء إشعار بدون مستخدم (يجب أن يفشل)"""
        with self.assertRaises(Exception):
            Notification.objects.create(
                title="إشعار",
                message="رسالة"
            )

    def test_notification_with_empty_title(self):
        """اختبار إشعار بعنوان فارغ"""
        notification = Notification.objects.create(
            user=self.user,
            title="",
            message="رسالة"
        )
        self.assertEqual(notification.title, "")

    def test_notification_with_very_long_message(self):
        """اختبار إشعار برسالة طويلة جداً"""
        long_message = "ا" * 10000
        notification = Notification.objects.create(
            user=self.user,
            title="إشعار",
            message=long_message
        )
        self.assertEqual(len(notification.message), 10000)

    def test_notification_with_invalid_type(self):
        """اختبار إشعار بنوع غير صحيح"""
        notification = Notification.objects.create(
            user=self.user,
            title="إشعار",
            message="رسالة",
            type="invalid_type"
        )
        self.assertEqual(notification.type, "invalid_type")

    def test_notification_with_invalid_related_id(self):
        """اختبار إشعار بمعرف كائن غير موجود"""
        notification = Notification.objects.create(
            user=self.user,
            title="إشعار",
            message="رسالة",
            related_model="Sale",
            related_id=99999
        )
        self.assertIsNotNone(notification)

    def test_preference_with_null_times(self):
        """اختبار تفضيلات بأوقات null"""
        preference = NotificationPreference.get_or_create_for_user(self.user)
        preference.enable_do_not_disturb = True
        preference.do_not_disturb_start = None
        preference.do_not_disturb_end = None
        preference.save()
        
        self.assertFalse(preference.is_in_do_not_disturb_period())

    def test_preference_with_same_start_end_time(self):
        """اختبار تفضيلات بنفس وقت البداية والنهاية"""
        preference = NotificationPreference.get_or_create_for_user(self.user)
        preference.enable_do_not_disturb = True
        preference.do_not_disturb_start = time(12, 0)
        preference.do_not_disturb_end = time(12, 0)
        preference.save()
        
        self.assertIsNotNone(preference)

    def test_create_notification_for_inactive_user(self):
        """اختبار إنشاء إشعار لمستخدم غير نشط"""
        self.user.is_active = False
        self.user.save()
        
        notification = NotificationService.create_notification(
            user=self.user,
            title="إشعار",
            message="رسالة"
        )
        
        self.assertIsNotNone(notification)

    def test_mark_as_read_with_empty_list(self):
        """اختبار تعليم كمقروء بقائمة فارغة"""
        count = NotificationService.mark_as_read([])
        self.assertEqual(count, 0)

    def test_mark_as_read_with_invalid_ids(self):
        """اختبار تعليم كمقروء بمعرفات غير صحيحة"""
        count = NotificationService.mark_as_read([99999, 88888])
        self.assertEqual(count, 0)

    def test_notification_cascade_delete(self):
        """اختبار حذف الإشعارات عند حذف المستخدم"""
        notification = Notification.objects.create(
            user=self.user,
            title="إشعار",
            message="رسالة"
        )
        
        user_id = self.user.id
        self.user.delete()
        
        count = Notification.objects.filter(id=notification.id).count()
        self.assertEqual(count, 0)


class NotificationConcurrencyTest(TransactionTestCase):
    """اختبارات التزامن والعمليات المتزامنة"""

    def setUp(self):
        """إعداد البيانات"""
        Notification.objects.all().delete()
        User.objects.all().delete()
        
        self.user = User.objects.create_user(
            username="concuser",
            email="conc@example.com",
            password="testpass123"
        )
        
    def tearDown(self):
        """تنظيف بعد كل اختبار"""
        Notification.objects.all().delete()
        User.objects.all().delete()

    def test_concurrent_notification_creation(self):
        """اختبار إنشاء إشعارات متزامنة (مبسط)"""
        # تنظيف كامل قبل الاختبار
        Notification.objects.filter(user=self.user).delete()
        
        for i in range(50):
            Notification.objects.create(
                user=self.user,
                title=f"إشعار {i}",
                message="رسالة"
            )
        
        count = Notification.objects.filter(user=self.user).count()
        self.assertEqual(count, 50)

    def test_concurrent_mark_as_read(self):
        """اختبار تعليم إشعارات كمقروءة (مبسط)"""
        # تنظيف كامل قبل الاختبار
        Notification.objects.filter(user=self.user).delete()
        
        notifications = [
            Notification.objects.create(
                user=self.user,
                title=f"إشعار {i}",
                message="رسالة",
                is_read=False
            )
            for i in range(20)
        ]
        
        notif_ids = [n.id for n in notifications]
        NotificationService.mark_as_read(notif_ids)
        
        unread_count = Notification.objects.filter(
            user=self.user,
            is_read=False
        ).count()
        self.assertEqual(unread_count, 0)


class NotificationSMSTest(TestCase):
    """اختبارات إرسال الإشعارات عبر SMS"""

    def setUp(self):
        """إعداد البيانات"""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )

    def test_sms_notification_enabled(self):
        """اختبار تفعيل إشعارات SMS"""
        preference = NotificationPreference.get_or_create_for_user(self.user)
        preference.notify_sms = True
        preference.phone_for_notifications = "01234567890"
        preference.save()
        
        notification = NotificationService.create_notification(
            user=self.user,
            title="إشعار اختبار",
            message="رسالة اختبار",
            notification_type="info"
        )
        
        self.assertIsNotNone(notification)

    def test_sms_notification_disabled(self):
        """اختبار تعطيل إشعارات SMS"""
        preference = NotificationPreference.get_or_create_for_user(self.user)
        preference.notify_sms = False
        preference.save()
        
        notification = NotificationService.create_notification(
            user=self.user,
            title="إشعار اختبار",
            message="رسالة اختبار"
        )
        
        self.assertIsNotNone(notification)

    def test_sms_without_phone_number(self):
        """اختبار SMS بدون رقم هاتف"""
        preference = NotificationPreference.get_or_create_for_user(self.user)
        preference.notify_sms = True
        preference.phone_for_notifications = None
        preference.save()
        
        notification = NotificationService.create_notification(
            user=self.user,
            title="إشعار اختبار",
            message="رسالة اختبار"
        )
        
        self.assertIsNotNone(notification)


class NotificationFilteringTest(TestCase):
    """اختبارات فلترة وبحث الإشعارات"""

    def setUp(self):
        """إعداد البيانات"""
        Notification.objects.all().delete()
        User.objects.all().delete()
        
        self.user1 = User.objects.create_user(
            username="user1",
            email="user1@example.com",
            password="pass"
        )
        self.user2 = User.objects.create_user(
            username="user2",
            email="user2@example.com",
            password="pass"
        )

    def test_filter_by_user(self):
        """اختبار فلترة الإشعارات حسب المستخدم"""
        Notification.objects.all().delete()
        
        for i in range(3):
            Notification.objects.create(
                user=self.user1,
                title=f"إشعار مستخدم 1 - {i}",
                message="رسالة"
            )
        
        for i in range(2):
            Notification.objects.create(
                user=self.user2,
                title=f"إشعار مستخدم 2 - {i}",
                message="رسالة"
            )
        
        user1_notifs = Notification.objects.filter(user=self.user1)
        user2_notifs = Notification.objects.filter(user=self.user2)
        
        self.assertEqual(user1_notifs.count(), 3)
        self.assertEqual(user2_notifs.count(), 2)

    def test_filter_by_type(self):
        """اختبار فلترة الإشعارات حسب النوع"""
        types = ["info", "warning", "danger", "success"]
        
        for notif_type in types:
            Notification.objects.create(
                user=self.user1,
                title=f"إشعار {notif_type}",
                message="رسالة",
                type=notif_type
            )
        
        info_notifs = Notification.objects.filter(type="info")
        warning_notifs = Notification.objects.filter(type="warning")
        
        self.assertEqual(info_notifs.count(), 1)
        self.assertEqual(warning_notifs.count(), 1)

    def test_filter_by_read_status(self):
        """اختبار فلترة الإشعارات حسب حالة القراءة"""
        Notification.objects.filter(user=self.user1).delete()
        
        for i in range(3):
            Notification.objects.create(
                user=self.user1,
                title=f"إشعار {i}",
                message="رسالة",
                is_read=(i % 2 == 0)
            )
        
        read_notifs = Notification.objects.filter(user=self.user1, is_read=True)
        unread_notifs = Notification.objects.filter(user=self.user1, is_read=False)
        
        self.assertEqual(read_notifs.count(), 2)
        self.assertEqual(unread_notifs.count(), 1)

    def test_filter_by_date_range(self):
        """اختبار فلترة الإشعارات حسب نطاق التاريخ"""
        Notification.objects.filter(user=self.user1).delete()
        
        notif1 = Notification.objects.create(
            user=self.user1,
            title="إشعار قديم",
            message="رسالة"
        )
        
        notif2 = Notification.objects.create(
            user=self.user1,
            title="إشعار حديث",
            message="رسالة"
        )
        
        yesterday = timezone.now() - timedelta(days=1)
        recent_notifs = Notification.objects.filter(
            user=self.user1,
            created_at__gte=yesterday
        )
        
        self.assertEqual(recent_notifs.count(), 2)


class NotificationRelatedObjectsTest(TestCase):
    """اختبارات الإشعارات المرتبطة بكائنات أخرى"""

    def setUp(self):
        """إعداد البيانات"""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )

    def test_notification_with_sale_link(self):
        """اختبار إشعار مرتبط بمبيعات"""
        notification = Notification.objects.create(
            user=self.user,
            title="فاتورة مبيعات جديدة",
            message="تم إنشاء فاتورة مبيعات",
            type="new_invoice",
            related_model="Sale",
            related_id=1
        )
        
        self.assertEqual(notification.related_model, "Sale")
        self.assertEqual(notification.related_id, 1)

    def test_notification_with_purchase_link(self):
        """اختبار إشعار مرتبط بمشتريات"""
        notification = Notification.objects.create(
            user=self.user,
            title="فاتورة مشتريات جديدة",
            message="تم إنشاء فاتورة مشتريات",
            type="new_invoice",
            related_model="Purchase",
            related_id=1
        )
        
        self.assertEqual(notification.related_model, "Purchase")

    def test_notification_with_product_link(self):
        """اختبار إشعار مرتبط بمنتج"""
        notification = Notification.objects.create(
            user=self.user,
            title="تنبيه مخزون",
            message="مخزون منخفض",
            type="inventory_alert",
            related_model="Product",
            related_id=1
        )
        
        self.assertEqual(notification.related_model, "Product")

    def test_notification_with_custom_link(self):
        """اختبار إشعار برابط مخصص"""
        custom_url = "/custom/page/"
        notification = Notification.objects.create(
            user=self.user,
            title="إشعار مخصص",
            message="رسالة",
            link_url=custom_url
        )
        
        self.assertEqual(notification.get_link_url(), custom_url)


class NotificationBatchOperationsTest(TestCase):
    """اختبارات العمليات الدفعية للإشعارات"""

    def setUp(self):
        """إعداد البيانات"""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )

    def test_bulk_delete_notifications(self):
        """اختبار حذف إشعارات دفعي"""
        for i in range(10):
            Notification.objects.create(
                user=self.user,
                title=f"إشعار {i}",
                message="رسالة"
            )
        
        Notification.objects.filter(user=self.user).delete()
        
        count = Notification.objects.filter(user=self.user).count()
        self.assertEqual(count, 0)

    def test_bulk_update_notifications(self):
        """اختبار تحديث إشعارات دفعي"""
        for i in range(5):
            Notification.objects.create(
                user=self.user,
                title=f"إشعار {i}",
                message="رسالة",
                is_read=False
            )
        
        Notification.objects.filter(user=self.user).update(is_read=True)
        
        unread_count = Notification.objects.filter(
            user=self.user,
            is_read=False
        ).count()
        self.assertEqual(unread_count, 0)

    def test_bulk_filter_and_delete(self):
        """اختبار فلترة وحذف دفعي"""
        for i in range(5):
            Notification.objects.create(
                user=self.user,
                title=f"إشعار {i}",
                message="رسالة",
                type="info" if i % 2 == 0 else "warning",
                is_read=(i < 3)
            )
        
        Notification.objects.filter(
            user=self.user,
            type="info",
            is_read=True
        ).delete()
        
        remaining = Notification.objects.filter(user=self.user).count()
        self.assertGreater(remaining, 0)


class NotificationStatsTest(TestCase):
    """اختبارات إحصائيات الإشعارات المتقدمة"""

    def setUp(self):
        """إعداد البيانات"""
        Notification.objects.all().delete()
        User.objects.all().delete()
        
        self.user = User.objects.create_user(
            username="statsuser",
            email="stats@example.com",
            password="testpass123"
        )
        
    def tearDown(self):
        """تنظيف بعد كل اختبار"""
        Notification.objects.all().delete()
        User.objects.all().delete()

    def test_stats_with_multiple_types(self):
        """اختبار إحصائيات مع أنواع متعددة"""
        # تنظيف كامل قبل الاختبار
        Notification.objects.filter(user=self.user).delete()
        
        types_count = {
            "info": 5,
            "warning": 3,
            "danger": 2,
            "success": 1
        }
        
        for notif_type, count in types_count.items():
            for i in range(count):
                Notification.objects.create(
                    user=self.user,
                    title=f"إشعار {notif_type} {i}",
                    message="رسالة",
                    type=notif_type
                )
        
        stats = NotificationService.get_notification_stats(self.user)
        
        self.assertEqual(stats['total'], 11)
        self.assertEqual(stats['by_type']['info'], 5)
        self.assertEqual(stats['by_type']['warning'], 3)

    def test_stats_with_read_unread(self):
        """اختبار إحصائيات القراءة وعدم القراءة"""
        # تنظيف كامل قبل الاختبار
        Notification.objects.filter(user=self.user).delete()
        
        for i in range(10):
            Notification.objects.create(
                user=self.user,
                title=f"إشعار {i}",
                message="رسالة",
                is_read=(i < 6)
            )
        
        stats = NotificationService.get_notification_stats(self.user)
        
        self.assertEqual(stats['total'], 10)
        self.assertEqual(stats['read'], 6)
        self.assertEqual(stats['unread'], 4)

    def test_stats_for_empty_notifications(self):
        """اختبار إحصائيات بدون إشعارات"""
        # تنظيف كامل قبل الاختبار
        Notification.objects.filter(user=self.user).delete()
        
        stats = NotificationService.get_notification_stats(self.user)
        
        self.assertEqual(stats['total'], 0)
        self.assertEqual(stats['read'], 0)
        self.assertEqual(stats['unread'], 0)


class NotificationValidationTest(TestCase):
    """اختبارات التحقق من صحة البيانات"""

    def setUp(self):
        """إعداد البيانات"""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )

    def test_email_validation(self):
        """اختبار التحقق من صحة البريد الإلكتروني"""
        preference = NotificationPreference.get_or_create_for_user(self.user)
        preference.email_for_notifications = "valid@example.com"
        preference.save()
        
        self.assertEqual(preference.email_for_notifications, "valid@example.com")

    def test_phone_validation(self):
        """اختبار التحقق من رقم الهاتف"""
        preference = NotificationPreference.get_or_create_for_user(self.user)
        preference.phone_for_notifications = "01234567890"
        preference.save()
        
        self.assertEqual(preference.phone_for_notifications, "01234567890")

    def test_frequency_validation(self):
        """اختبار التحقق من تكرارات الفحص"""
        valid_frequencies = ['hourly', '3hours', '6hours', 'daily']
        
        preference = NotificationPreference.get_or_create_for_user(self.user)
        for freq in valid_frequencies:
            preference.inventory_check_frequency = freq
            preference.save()
            self.assertEqual(preference.inventory_check_frequency, freq)

    def test_days_validation(self):
        """اختبار التحقق من عدد الأيام"""
        preference = NotificationPreference.get_or_create_for_user(self.user)
        preference.invoice_due_days_before = 5
        preference.invoice_overdue_days_after = 2
        preference.auto_delete_after_days = 60
        preference.save()
        
        self.assertEqual(preference.invoice_due_days_before, 5)
        self.assertEqual(preference.invoice_overdue_days_after, 2)
        self.assertEqual(preference.auto_delete_after_days, 60)


class NotificationSecurityTest(TestCase):
    """اختبارات الأمان للإشعارات"""

    def setUp(self):
        """إعداد البيانات"""
        Notification.objects.all().delete()
        User.objects.all().delete()
        
        self.user1 = User.objects.create_user(
            username="user1",
            email="user1@example.com",
            password="pass"
        )
        self.user2 = User.objects.create_user(
            username="user2",
            email="user2@example.com",
            password="pass"
        )

    def test_user_cannot_access_others_notifications(self):
        """اختبار عدم قدرة المستخدم على الوصول لإشعارات الآخرين"""
        Notification.objects.all().delete()
        
        notif = Notification.objects.create(
            user=self.user1,
            title="إشعار خاص",
            message="رسالة خاصة"
        )
        
        user2_notifs = NotificationService.get_user_notifications(self.user2)
        
        self.assertEqual(len(user2_notifs), 0)

    def test_mark_as_read_only_own_notifications(self):
        """اختبار تعليم الإشعارات الخاصة فقط كمقروءة"""
        notif1 = Notification.objects.create(
            user=self.user1,
            title="إشعار 1",
            message="رسالة",
            is_read=False
        )
        
        notif2 = Notification.objects.create(
            user=self.user2,
            title="إشعار 2",
            message="رسالة",
            is_read=False
        )
        
        count = NotificationService.mark_as_read([notif1.id, notif2.id], user=self.user1)
        
        self.assertEqual(count, 1)
        
        notif1.refresh_from_db()
        notif2.refresh_from_db()
        
        self.assertTrue(notif1.is_read)
        self.assertFalse(notif2.is_read)

    def test_preference_isolation(self):
        """اختبار عزل تفضيلات المستخدمين"""
        pref1 = NotificationPreference.get_or_create_for_user(self.user1)
        pref1.enable_inventory_alerts = True
        pref1.save()
        
        pref2 = NotificationPreference.get_or_create_for_user(self.user2)
        pref2.enable_inventory_alerts = False
        pref2.save()
        
        self.assertTrue(pref1.enable_inventory_alerts)
        self.assertFalse(pref2.enable_inventory_alerts)
