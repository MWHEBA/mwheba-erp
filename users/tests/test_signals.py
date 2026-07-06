from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_logged_out
from users.models import ActivityLog, Role
from core.middleware.current_user import _thread_locals

User = get_user_model()

class ActivityLogSignalsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser_sig",
            password="password123",
            first_name="Ahmed"
        )
        # Set user in thread local for signals
        _thread_locals.user = self.user
        
    def tearDown(self):
        if hasattr(_thread_locals, 'user'):
            del _thread_locals.user

    def test_user_save_creates_log(self):
        # Create a new user
        another_user = User.objects.create_user(
            username="newuser_sig",
            password="password123",
            first_name="Sayed"
        )
        
        # Verify log entry exists
        logs = ActivityLog.objects.filter(model_name="User", object_id=another_user.id)
        self.assertTrue(logs.exists())
        self.assertEqual(logs.first().action, "إنشاء مستخدم")
        
        # Update user
        another_user.first_name = "Ali"
        another_user.save()
        
        # Verify log entry exists for update
        update_logs = ActivityLog.objects.filter(model_name="User", object_id=another_user.id).order_by('-timestamp')
        self.assertEqual(update_logs.first().action, "تعديل مستخدم")

    def test_user_delete_creates_log(self):
        another_user = User.objects.create_user(
            username="newuser_del_sig",
            password="password123"
        )
        user_id = another_user.id
        another_user.delete()
        
        logs = ActivityLog.objects.filter(model_name="User", object_id=user_id, action="حذف مستخدم")
        self.assertTrue(logs.exists())

    def test_login_signal_creates_log(self):
        # Trigger login signal
        user_logged_in.send(sender=User, request=None, user=self.user)
        
        logs = ActivityLog.objects.filter(action="تسجيل دخول", user=self.user)
        self.assertTrue(logs.exists())

    def test_logout_signal_creates_log(self):
        # Trigger logout signal
        user_logged_out.send(sender=User, request=None, user=self.user)
        
        logs = ActivityLog.objects.filter(action="تسجيل خروج", user=self.user)
        self.assertTrue(logs.exists())
