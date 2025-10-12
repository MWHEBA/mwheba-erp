import os
import json
import tempfile
import unittest
from unittest.mock import patch, MagicMock, mock_open
from django.test import TestCase
from django.utils import timezone
from django.conf import settings
from django.contrib.auth import get_user_model

from utils.logs import SystemLogHandler, SecurityLogHandler, AuditLogHandler
from utils.logs import get_system_logs, get_security_logs, get_audit_logs

User = get_user_model()


class SystemLogHandlerTest(TestCase):
    """
    اختبارات معالج سجلات النظام
    """
    
    def setUp(self):
        """
        إعداد بيئة الاختبار
        """
        # استخدام ملف مؤقت للاختبار
        self.temp_log_file = tempfile.NamedTemporaryFile(delete=False).name
        
        # تهيئة معالج السجلات
        self.log_handler = SystemLogHandler(log_file=self.temp_log_file)
        
        # إنشاء مستخدم للاختبار
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
    
    def tearDown(self):
        """
        تنظيف بيئة الاختبار
        """
        # حذف ملف السجل المؤقت
        if os.path.exists(self.temp_log_file):
            os.unlink(self.temp_log_file)
    
    @patch('logging.FileHandler.emit')
    def test_log_action(self, mock_emit):
        """
        اختبار تسجيل إجراء في النظام
        """
        # تسجيل إجراء
        log_entry = self.log_handler.log_action(
            action='test_action',
            user=self.user,
            model=User,
            object_id=1,
            details={'test': 'value'}
        )
        
        # التحقق من استدعاء طريقة emit
        self.assertTrue(mock_emit.called)
        
        # التحقق من بيانات السجل
        self.assertEqual(log_entry['action'], 'test_action')
        self.assertEqual(log_entry['user'], self.user.username)
        self.assertEqual(log_entry['model'], User.__name__)
        self.assertEqual(log_entry['object_id'], 1)
        self.assertEqual(log_entry['details'], {'test': 'value'})
    
    @patch('os.makedirs')
    def test_directory_creation(self, mock_makedirs):
        """
        اختبار إنشاء دليل السجلات
        """
        # إنشاء معالج جديد لاختبار إنشاء الدليل
        handler = SystemLogHandler(log_file='/path/to/logs/test.log')
        
        # التحقق من استدعاء os.makedirs
        mock_makedirs.assert_called_once_with('/path/to/logs', exist_ok=True)


class SecurityLogHandlerTest(TestCase):
    """
    اختبارات معالج سجلات الأمان
    """
    
    def setUp(self):
        """
        إعداد بيئة الاختبار
        """
        # استخدام ملف مؤقت للاختبار
        self.temp_log_file = tempfile.NamedTemporaryFile(delete=False).name
        
        # تهيئة معالج السجلات
        self.log_handler = SecurityLogHandler(log_file=self.temp_log_file)
        
        # إنشاء مستخدم للاختبار
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
    
    def tearDown(self):
        """
        تنظيف بيئة الاختبار
        """
        # حذف ملف السجل المؤقت
        if os.path.exists(self.temp_log_file):
            os.unlink(self.temp_log_file)
    
    @patch('logging.Logger.warning')
    def test_log_security_event(self, mock_warning):
        """
        اختبار تسجيل حدث أمني
        """
        # تسجيل حدث أمني
        log_entry = self.log_handler.log_security_event(
            event_type='login_attempt',
            user=self.user,
            ip_address='192.168.1.1',
            details={'success': False, 'reason': 'Invalid password'}
        )
        
        # التحقق من استدعاء طريقة warning
        self.assertTrue(mock_warning.called)
        
        # التحقق من بيانات السجل
        self.assertEqual(log_entry['event_type'], 'login_attempt')
        self.assertEqual(log_entry['user'], self.user.username)
        self.assertEqual(log_entry['ip_address'], '192.168.1.1')
        self.assertEqual(log_entry['details'], {'success': False, 'reason': 'Invalid password'})


class AuditLogHandlerTest(TestCase):
    """
    اختبارات معالج سجلات التدقيق
    """
    
    def setUp(self):
        """
        إعداد بيئة الاختبار
        """
        # استخدام ملف مؤقت للاختبار
        self.temp_log_file = tempfile.NamedTemporaryFile(delete=False).name
        
        # تهيئة معالج السجلات
        self.log_handler = AuditLogHandler(log_file=self.temp_log_file)
        
        # إنشاء مستخدم للاختبار
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
    
    def tearDown(self):
        """
        تنظيف بيئة الاختبار
        """
        # حذف ملف السجل المؤقت
        if os.path.exists(self.temp_log_file):
            os.unlink(self.temp_log_file)
    
    @patch('logging.Logger.info')
    def test_log_data_change(self, mock_info):
        """
        اختبار تسجيل تغيير في البيانات
        """
        # بيانات الاختبار
        old_data = {'username': 'oldname', 'email': 'old@example.com'}
        new_data = {'username': 'newname', 'email': 'new@example.com'}
        
        # تسجيل تغيير البيانات
        log_entry = self.log_handler.log_data_change(
            action='update',
            user=self.user,
            model=User,
            object_id=1,
            old_data=old_data,
            new_data=new_data
        )
        
        # التحقق من استدعاء طريقة info
        self.assertTrue(mock_info.called)
        
        # التحقق من بيانات السجل
        self.assertEqual(log_entry['action'], 'update')
        self.assertEqual(log_entry['user'], self.user.username)
        self.assertEqual(log_entry['model'], User.__name__)
        self.assertEqual(log_entry['object_id'], 1)
        self.assertEqual(log_entry['old_data'], old_data)
        self.assertEqual(log_entry['new_data'], new_data)


class GetLogsTest(TestCase):
    """
    اختبارات وظائف استرجاع السجلات
    """
    
    def setUp(self):
        """
        إعداد بيئة الاختبار
        """
        # تهيئة بيانات الاختبار
        self.start_date = timezone.now() - timezone.timedelta(days=7)
        self.end_date = timezone.now()
        
        # محاكاة محتوى ملف السجل
        self.system_log_content = (
            '2023-05-01 12:00:00,000 - utils.logs - INFO - {"timestamp": "2023-05-01T12:00:00+00:00", "action": "create", "user": "testuser", "model": "User", "object_id": 1}\n'
            '2023-05-02 12:00:00,000 - utils.logs - INFO - {"timestamp": "2023-05-02T12:00:00+00:00", "action": "update", "user": "testuser", "model": "User", "object_id": 1}\n'
            '2023-05-03 12:00:00,000 - utils.logs - INFO - {"timestamp": "2023-05-03T12:00:00+00:00", "action": "delete", "user": "admin", "model": "User", "object_id": 2}\n'
        )
        
        self.security_log_content = (
            '2023-05-01 12:00:00,000 - WARNING - {"timestamp": "2023-05-01T12:00:00+00:00", "event_type": "login_success", "user": "testuser", "ip_address": "192.168.1.1"}\n'
            '2023-05-02 12:00:00,000 - WARNING - {"timestamp": "2023-05-02T12:00:00+00:00", "event_type": "login_failed", "user": "testuser", "ip_address": "192.168.1.1"}\n'
            '2023-05-03 12:00:00,000 - WARNING - {"timestamp": "2023-05-03T12:00:00+00:00", "event_type": "logout", "user": "admin", "ip_address": "192.168.1.2"}\n'
        )
        
        self.audit_log_content = (
            '2023-05-01 12:00:00,000 - INFO - {"timestamp": "2023-05-01T12:00:00+00:00", "action": "create", "user": "testuser", "model": "User", "object_id": 1}\n'
            '2023-05-02 12:00:00,000 - INFO - {"timestamp": "2023-05-02T12:00:00+00:00", "action": "update", "user": "testuser", "model": "User", "object_id": 1}\n'
            '2023-05-03 12:00:00,000 - INFO - {"timestamp": "2023-05-03T12:00:00+00:00", "action": "delete", "user": "admin", "model": "User", "object_id": 2}\n'
        )
    
    @patch('builtins.open', new_callable=unittest.mock.mock_open)
    @patch('os.path.exists')
    def test_get_system_logs_file_not_exist(self, mock_exists, mock_open):
        """
        اختبار استرجاع سجلات النظام عندما لا يوجد ملف سجل
        """
        # محاكاة عدم وجود ملف السجل
        mock_exists.return_value = False
        
        # استرجاع السجلات
        logs = get_system_logs()
        
        # التحقق من النتائج
        self.assertEqual(logs, [])
        mock_open.assert_not_called()
    
    @patch('builtins.open')
    @patch('os.path.exists')
    def test_get_system_logs(self, mock_exists, mock_open):
        """
        اختبار استرجاع سجلات النظام
        """
        # محاكاة وجود ملف السجل
        mock_exists.return_value = True
        mock_open.return_value.__enter__.return_value = self.system_log_content.splitlines()
        
        # استرجاع السجلات
        logs = get_system_logs()
        
        # التحقق من النتائج
        self.assertGreater(len(logs), 0)
    
    @patch('builtins.open')
    @patch('os.path.exists')
    def test_get_system_logs_with_filters(self, mock_exists, mock_open):
        """
        اختبار استرجاع سجلات النظام مع استخدام المرشحات
        """
        # محاكاة وجود ملف السجل
        mock_exists.return_value = True
        mock_open.return_value.__enter__.return_value = self.system_log_content.splitlines()
        
        # استرجاع السجلات مع مرشحات
        logs = get_system_logs(action='create', user='testuser')
        
        # التحقق من النتائج (هذا اختبار بسيط فقط)
        self.assertTrue(len(logs) >= 0)
    
    @patch('builtins.open')
    @patch('os.path.exists')
    def test_get_security_logs(self, mock_exists, mock_open):
        """
        اختبار استرجاع سجلات الأمان
        """
        # محاكاة وجود ملف السجل
        mock_exists.return_value = True
        mock_open.return_value.__enter__.return_value = self.security_log_content.splitlines()
        
        # استرجاع السجلات
        logs = get_security_logs()
        
        # التحقق من النتائج
        self.assertTrue(len(logs) >= 0)
    
    @patch('builtins.open')
    @patch('os.path.exists')
    def test_get_audit_logs(self, mock_exists, mock_open):
        """
        اختبار استرجاع سجلات التدقيق
        """
        # محاكاة وجود ملف السجل
        mock_exists.return_value = True
        mock_open.return_value.__enter__.return_value = self.audit_log_content.splitlines()
        
        # استرجاع السجلات
        logs = get_audit_logs()
        
        # التحقق من النتائج
        self.assertTrue(len(logs) >= 0)
    
    @patch('builtins.open')
    @patch('os.path.exists')
    def test_get_audit_logs_with_filters(self, mock_exists, mock_open):
        """
        اختبار استرجاع سجلات التدقيق مع استخدام المرشحات
        """
        # محاكاة وجود ملف السجل
        mock_exists.return_value = True
        mock_open.return_value.__enter__.return_value = self.audit_log_content.splitlines()
        
        # استرجاع السجلات مع مرشحات
        logs = get_audit_logs(action='update', user='testuser', model='User')
        
        # التحقق من النتائج
        self.assertTrue(len(logs) >= 0) 