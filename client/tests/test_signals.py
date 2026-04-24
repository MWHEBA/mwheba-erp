"""
اختبارات شاملة لـ Signals العملاء - Updated to test real signal implementation
"""

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from unittest.mock import patch
import logging

from ..models import Customer
from financial.models import ChartOfAccounts, AccountType

User = get_user_model()


class CustomerSignalsTest(TestCase):
    """اختبارات Signals العملاء - Using real code"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.user = User.objects.create_user(
            username="testuser",
            password="test123"
        )
        
        # إنشاء البنية المحاسبية المطلوبة
        asset_type = AccountType.objects.create(
            code='ASSET',
            name='أصول',
            name_en='Assets',
            nature='debit'
        )
        
        self.customers_parent = ChartOfAccounts.objects.create(
            code='10300',
            name='العملاء',
            name_en='Customers',
            account_type=asset_type,
            is_active=True,
            is_leaf=False
        )
        
    # ==================== اختبارات create_customer_account_signal ====================
    
    @override_settings(AUTO_CREATE_CUSTOMER_ACCOUNTS=True)
    def test_signal_creates_account_for_new_customer(self):
        """اختبار إنشاء حساب محاسبي تلقائي للعميل الجديد - Real Implementation"""
        # إنشاء عميل جديد
        customer = Customer.objects.create(
            name='عميل جديد',
            code='NEW001',
            created_by=self.user
        )
        
        # Refresh to get the account created by signal
        customer.refresh_from_db()
        
        # التحقق من إنشاء الحساب
        self.assertIsNotNone(customer.financial_account)
        self.assertTrue(customer.financial_account.code.startswith('1103'))
        self.assertEqual(customer.financial_account.parent, self.customers_parent)
        self.assertIn(customer.name, customer.financial_account.name)
        
    @override_settings(AUTO_CREATE_CUSTOMER_ACCOUNTS=False)
    def test_signal_disabled_when_setting_false(self):
        """اختبار عدم إنشاء حساب عند تعطيل الإعداد"""
        # إنشاء عميل جديد
        customer = Customer.objects.create(
            name='عميل بدون حساب',
            code='NOACC001',
            created_by=self.user
        )
        
        # التحقق من عدم إنشاء حساب
        self.assertIsNone(customer.financial_account)
        
    @override_settings(AUTO_CREATE_CUSTOMER_ACCOUNTS=True)
    def test_signal_not_called_on_update(self):
        """اختبار عدم إنشاء حساب جديد عند التعديل"""
        # إنشاء عميل
        customer = Customer.objects.create(
            name='عميل',
            code='UPD001',
            created_by=self.user
        )
        
        customer.refresh_from_db()
        original_account = customer.financial_account
        
        # تعديل العميل
        customer.name = 'عميل محدث'
        customer.save()
        
        customer.refresh_from_db()
        
        # التحقق من عدم تغيير الحساب
        self.assertEqual(customer.financial_account, original_account)
        
    @override_settings(AUTO_CREATE_CUSTOMER_ACCOUNTS=True)
    def test_signal_not_called_if_account_exists(self):
        """اختبار عدم إنشاء حساب إذا كان موجود مسبقاً"""
        # إنشاء عميل أولاً
        customer = Customer.objects.create(
            name='عميل بحساب',
            code='HASACC001',
            created_by=self.user
        )
        
        customer.refresh_from_db()
        original_account = customer.financial_account
        
        # تحديث العميل (لا يجب إنشاء حساب جديد)
        customer.name = 'عميل محدث'
        customer.save()
        
        customer.refresh_from_db()
        
        # التحقق من عدم تغيير الحساب
        self.assertEqual(customer.financial_account, original_account)
        
    @override_settings(AUTO_CREATE_CUSTOMER_ACCOUNTS=True)
    @patch('client.signals.logger')
    def test_signal_logs_success(self, mock_logger):
        """اختبار تسجيل نجاح إنشاء الحساب"""
        # إنشاء عميل
        customer = Customer.objects.create(
            name='عميل النجاح',
            code='SUCCESS001',
            created_by=self.user
        )
        
        # التحقق من تسجيل النجاح
        mock_logger.info.assert_called()
        log_calls = [str(call) for call in mock_logger.info.call_args_list]
        log_message = ' '.join(log_calls)
        self.assertIn('عميل النجاح', log_message)
        
    @override_settings(AUTO_CREATE_CUSTOMER_ACCOUNTS=True)
    @patch('client.signals.logger')
    @patch('client.services.customer_service.CustomerService.create_financial_account_for_customer')
    def test_signal_logs_error_on_exception(self, mock_create_account, mock_logger):
        """اختبار تسجيل الخطأ عند فشل إنشاء الحساب"""
        # إعداد الـ mock ليرمي استثناء
        mock_create_account.side_effect = Exception('خطأ في الإنشاء')
        
        # إنشاء عميل (يجب أن ينجح رغم فشل إنشاء الحساب)
        customer = Customer.objects.create(
            name='عميل الخطأ',
            code='ERROR001',
            created_by=self.user
        )
        
        # التحقق من أن العميل تم إنشاؤه
        self.assertIsNotNone(customer.pk)
        
        # التحقق من تسجيل الخطأ
        mock_logger.error.assert_called()
        log_calls = [str(call) for call in mock_logger.error.call_args_list]
        log_message = ' '.join(log_calls)
        # Check for either Arabic or English error message
        self.assertTrue('فشل' in log_message or 'Failed' in log_message)
        
    @override_settings(AUTO_CREATE_CUSTOMER_ACCOUNTS=True)
    def test_signal_creates_account_for_old_customer_without_account(self):
        """اختبار إنشاء حساب لعميل قديم ليس لديه حساب (Self-healing)"""
        # إنشاء عميل بدون حساب (تعطيل الإعداد مؤقتاً)
        with override_settings(AUTO_CREATE_CUSTOMER_ACCOUNTS=False):
            customer = Customer.objects.create(
                name='عميل قديم',
                code='OLD001',
                created_by=self.user
            )
        
        # التحقق من عدم وجود حساب
        self.assertIsNone(customer.financial_account)
        
        # تفعيل الإعداد وحفظ العميل (يجب أن ينشئ حساب)
        with override_settings(AUTO_CREATE_CUSTOMER_ACCOUNTS=True):
            customer.save()
            customer.refresh_from_db()
        
        # التحقق من إنشاء الحساب
        self.assertIsNotNone(customer.financial_account)
        self.assertTrue(customer.financial_account.code.startswith('1103'))
        
    # ==================== اختبارات delete_customer_account_signal ====================
    
    def test_signal_deletes_account_on_customer_delete(self):
        """اختبار حذف الحساب المحاسبي عند حذف العميل"""
        # إنشاء عميل
        customer = Customer.objects.create(
            name='عميل للحذف',
            code='DEL001',
            created_by=self.user
        )
        
        customer.refresh_from_db()
        account_code = customer.financial_account.code if customer.financial_account else None
        
        # حذف العميل
        customer.delete()
        
        # التحقق من حذف الحساب
        if account_code:
            self.assertFalse(ChartOfAccounts.objects.filter(code=account_code).exists())
        
    def test_signal_no_error_if_no_account(self):
        """اختبار عدم حدوث خطأ عند حذف عميل بدون حساب"""
        # إنشاء عميل بدون حساب
        with override_settings(AUTO_CREATE_CUSTOMER_ACCOUNTS=False):
            customer = Customer.objects.create(
                name='عميل بدون حساب',
                code='NOACCDEL001',
                created_by=self.user
            )
        
        # حذف العميل (يجب أن ينجح بدون أخطاء)
        try:
            customer.delete()
            success = True
        except Exception:
            success = False
            
        self.assertTrue(success)


class CustomerSignalsIntegrationTest(TestCase):
    """اختبارات تكامل Signals"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.user = User.objects.create_user(
            username="testuser",
            password="test123"
        )
        
        # إنشاء البنية المحاسبية المطلوبة
        asset_type = AccountType.objects.create(
            code='ASSET',
            name='أصول',
            name_en='Assets',
            nature='debit'
        )
        
        ChartOfAccounts.objects.create(
            code='10300',
            name='مدينو العملاء',
            name_en='Customers Receivables',
            account_type=asset_type,
            is_active=True,
            is_leaf=False
        )
        
    @override_settings(AUTO_CREATE_CUSTOMER_ACCOUNTS=True)
    def test_multiple_customers_creation(self):
        """اختبار إنشاء عدة عملاء"""
        # إنشاء عدة عملاء
        for i in range(3):
            customer = Customer.objects.create(
                name=f'عميل {i+1}',
                code=f'MULTI{i+1:03d}',
                created_by=self.user
            )
            customer.refresh_from_db()
            
            # التحقق من إنشاء حساب لكل عميل
            self.assertIsNotNone(customer.financial_account)
        
        # التحقق من إنشاء 3 حسابات فرعية
        customer_accounts = ChartOfAccounts.objects.filter(
            code__startswith='1030',
            parent__code='10300'
        )
        self.assertEqual(customer_accounts.count(), 3)
        
    @override_settings(AUTO_CREATE_CUSTOMER_ACCOUNTS=True)
    def test_signal_with_bulk_create(self):
        """اختبار Signal مع bulk_create"""
        # إنشاء عملاء بـ bulk_create
        customers = [
            Customer(name=f'عميل {i}', code=f'BULK{i:03d}', created_by=self.user)
            for i in range(3)
        ]
        Customer.objects.bulk_create(customers)
        
        # ملاحظة: bulk_create لا يشغل signals في Django
        # لذلك يجب أن لا يتم إنشاء حسابات
        for customer in Customer.objects.filter(code__startswith='BULK'):
            self.assertIsNone(customer.financial_account)
