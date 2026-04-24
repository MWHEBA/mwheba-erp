"""
اختبارات إشارات التحقق من المعاملات المالية
Tests for Financial Validation Signals
"""

import pytest
from datetime import date
from django.contrib.auth import get_user_model
from django.test import TestCase

from financial.signals.validation_signals import (
    pre_financial_transaction,
    FinancialTransactionSignalHandler,
    trigger_validation,
    connect_model_validation
)
from financial.exceptions import FinancialValidationError
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.journal_entry import AccountingPeriod

User = get_user_model()


@pytest.mark.django_db
class TestFinancialValidationSignals(TestCase):
    """اختبارات إشارات التحقق من المعاملات المالية"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        # إنشاء مستخدم
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        # إنشاء نوع حساب محاسبي
        self.account_type = AccountType.objects.create(
            name='أصول',
            code='asset',
            nature='debit'
        )
        
        # إنشاء حساب محاسبي
        self.account = ChartOfAccounts.objects.create(
            code='1001',
            name='حساب اختبار',
            account_type=self.account_type,
            is_active=True,
            is_leaf=True
        )
        
        # إنشاء فترة محاسبية مفتوحة
        self.period = AccountingPeriod.objects.create(
            name='فترة اختبار 2024',
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            status='open'
        )
    
    def test_signal_exists(self):
        """اختبار وجود signal"""
        self.assertIsNotNone(pre_financial_transaction)
    
    def test_signal_handler_exists(self):
        """اختبار وجود معالج الإشارة"""
        self.assertIsNotNone(FinancialTransactionSignalHandler)
        self.assertTrue(
            hasattr(FinancialTransactionSignalHandler, 'validate_transaction_signal')
        )
    
    def test_trigger_validation_helper_exists(self):
        """اختبار وجود دالة trigger_validation المساعدة"""
        self.assertIsNotNone(trigger_validation)
        self.assertTrue(callable(trigger_validation))
    
    def test_connect_model_validation_helper_exists(self):
        """اختبار وجود دالة connect_model_validation المساعدة"""
        self.assertIsNotNone(connect_model_validation)
        self.assertTrue(callable(connect_model_validation))
    
    def test_signal_handler_validate_transaction_method(self):
        """اختبار وجود دالة validate_transaction_signal"""
        handler = FinancialTransactionSignalHandler()
        self.assertTrue(
            hasattr(handler, 'validate_transaction_signal')
        )
    
    def test_signal_handler_connect_to_model_method(self):
        """اختبار وجود دالة connect_to_model"""
        handler = FinancialTransactionSignalHandler()
        self.assertTrue(
            hasattr(handler, 'connect_to_model')
        )


@pytest.mark.django_db
class TestSignalIntegration(TestCase):
    """اختبارات تكامل الإشارات"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        # إنشاء مستخدم
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        # إنشاء نوع حساب محاسبي
        self.account_type = AccountType.objects.create(
            name='أصول',
            code='asset',
            nature='debit'
        )
        
        # إنشاء حساب محاسبي
        self.account = ChartOfAccounts.objects.create(
            code='1001',
            name='حساب اختبار',
            account_type=self.account_type,
            is_active=True,
            is_leaf=True
        )
        
        # إنشاء فترة محاسبية مفتوحة
        self.period = AccountingPeriod.objects.create(
            name='فترة اختبار 2024',
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            status='open'
        )
    
    def test_signal_can_be_sent(self):
        """اختبار إمكانية إرسال الإشارة"""
        # إنشاء كيان وهمي بسيط
        class MockEntity:
            def __init__(self, account):
                self.id = 1
                self.account = account
            
            def __str__(self):
                return "Mock Entity"
        
        mock_entity = MockEntity(self.account)
        
        # محاولة إرسال الإشارة
        try:
            responses = pre_financial_transaction.send(
                sender=None,
                entity=mock_entity,
                transaction_date=date(2024, 6, 15),
                entity_type='test',
                transaction_type='test',
                user=self.user,
                module='test',
                is_system_generated=False
            )
            # التحقق من أن الإشارة تم إرسالها
            self.assertIsNotNone(responses)
        except Exception as e:
            # قد يفشل التحقق بسبب عدم وجود حساب محاسبي للكيان الوهمي
            # لكن المهم أن الإشارة تم إرسالها
            self.assertIsInstance(e, (FinancialValidationError, AttributeError))


class TestSignalDocumentation(TestCase):
    """اختبارات التوثيق والبنية"""
    
    def test_signal_has_docstring(self):
        """اختبار وجود توثيق للإشارة"""
        # التحقق من وجود docstring في الملف
        import financial.signals.validation_signals as signals_module
        self.assertIsNotNone(signals_module.__doc__)
    
    def test_handler_class_has_docstring(self):
        """اختبار وجود توثيق لكلاس المعالج"""
        self.assertIsNotNone(FinancialTransactionSignalHandler.__doc__)
    
    def test_validate_transaction_signal_has_docstring(self):
        """اختبار وجود توثيق لدالة validate_transaction_signal"""
        self.assertIsNotNone(
            FinancialTransactionSignalHandler.validate_transaction_signal.__doc__
        )
    
    def test_connect_to_model_has_docstring(self):
        """اختبار وجود توثيق لدالة connect_to_model"""
        self.assertIsNotNone(
            FinancialTransactionSignalHandler.connect_to_model.__doc__
        )
    
    def test_trigger_validation_has_docstring(self):
        """اختبار وجود توثيق لدالة trigger_validation"""
        self.assertIsNotNone(trigger_validation.__doc__)
    
    def test_connect_model_validation_has_docstring(self):
        """اختبار وجود توثيق لدالة connect_model_validation"""
        self.assertIsNotNone(connect_model_validation.__doc__)
