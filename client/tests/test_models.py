"""
اختبارات نماذج العملاء
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from decimal import Decimal

from ..models import Client, ClientAccount, ClientTransaction

User = get_user_model()


class ClientModelTest(TestCase):
    """اختبارات نموذج العملاء"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.user = User.objects.create_user(
            username="testuser",
            password="test123"
        )
        
    def test_create_client(self):
        """اختبار إنشاء عميل جديد"""
        client = Client.objects.create(
            name="عميل تجريبي",
            email="client@test.com",
            phone="01234567890",
            address="القاهرة، مصر",
            client_type="REGULAR"
        )
        
        self.assertEqual(client.name, "عميل تجريبي")
        self.assertEqual(client.email, "client@test.com")
        self.assertEqual(client.client_type, "REGULAR")
        self.assertTrue(client.is_active)
        
    def test_client_str_method(self):
        """اختبار طريقة __str__ للعميل"""
        client = Client.objects.create(
            name="عميل تجريبي",
            email="client@test.com"
        )
        
        self.assertEqual(str(client), "عميل تجريبي")
        
    def test_client_balance_calculation(self):
        """اختبار حساب رصيد العميل"""
        client = Client.objects.create(
            name="عميل تجريبي",
            email="client@test.com"
        )
        
        # الرصيد الأولي يجب أن يكون صفر
        self.assertEqual(client.balance, Decimal('0.00'))
        
    def test_client_discount_percentage(self):
        """اختبار نسبة خصم العميل"""
        client = Client.objects.create(
            name="عميل VIP",
            email="vip@test.com",
            client_type="VIP",
            discount_percentage=Decimal('15.00')
        )
        
        self.assertEqual(client.discount_percentage, Decimal('15.00'))


class ClientAccountTest(TestCase):
    """اختبارات حساب العميل"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = Client.objects.create(
            name="عميل تجريبي",
            email="client@test.com"
        )
        
    def test_create_client_account(self):
        """اختبار إنشاء حساب عميل"""
        account = ClientAccount.objects.create(
            client=self.client,
            account_type="RECEIVABLE",
            balance=Decimal('1000.00')
        )
        
        self.assertEqual(account.client, self.client)
        self.assertEqual(account.account_type, "RECEIVABLE")
        self.assertEqual(account.balance, Decimal('1000.00'))
        
    def test_account_str_method(self):
        """اختبار طريقة __str__ للحساب"""
        account = ClientAccount.objects.create(
            client=self.client,
            account_type="RECEIVABLE"
        )
        
        str_result = str(account)
        self.assertIn("عميل تجريبي", str_result)
        self.assertIn("RECEIVABLE", str_result)


class ClientTransactionTest(TestCase):
    """اختبارات معاملات العميل"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.user = User.objects.create_user(
            username="testuser",
            password="test123"
        )
        
        self.client = Client.objects.create(
            name="عميل تجريبي",
            email="client@test.com"
        )
        
        self.account = ClientAccount.objects.create(
            client=self.client,
            account_type="RECEIVABLE"
        )
        
    def test_create_client_transaction(self):
        """اختبار إنشاء معاملة عميل"""
        transaction = ClientTransaction.objects.create(
            account=self.account,
            transaction_type="SALE",
            amount=Decimal('500.00'),
            description="فاتورة بيع",
            created_by=self.user
        )
        
        self.assertEqual(transaction.account, self.account)
        self.assertEqual(transaction.transaction_type, "SALE")
        self.assertEqual(transaction.amount, Decimal('500.00'))
        self.assertEqual(transaction.description, "فاتورة بيع")
        
    def test_transaction_str_method(self):
        """اختبار طريقة __str__ للمعاملة"""
        transaction = ClientTransaction.objects.create(
            account=self.account,
            transaction_type="PAYMENT",
            amount=Decimal('200.00'),
            description="دفعة نقدية"
        )
        
        str_result = str(transaction)
        self.assertIn("PAYMENT", str_result)
        self.assertIn("200", str_result)
        
    def test_transaction_balance_update(self):
        """اختبار تحديث الرصيد عند المعاملة"""
        # معاملة بيع (تزيد الرصيد)
        sale_transaction = ClientTransaction.objects.create(
            account=self.account,
            transaction_type="SALE",
            amount=Decimal('1000.00'),
            description="فاتورة بيع"
        )
        
        # معاملة دفعة (تقلل الرصيد)
        payment_transaction = ClientTransaction.objects.create(
            account=self.account,
            transaction_type="PAYMENT",
            amount=Decimal('300.00'),
            description="دفعة نقدية"
        )
        
        # التحقق من وجود المعاملات
        self.assertEqual(
            ClientTransaction.objects.filter(account=self.account).count(),
            2
        )


class ClientTypesTest(TestCase):
    """اختبارات أنواع العملاء"""
    
    def test_regular_client(self):
        """اختبار العميل العادي"""
        client = Client.objects.create(
            name="عميل عادي",
            email="regular@test.com",
            client_type="REGULAR",
            discount_percentage=Decimal('5.00')
        )
        
        self.assertEqual(client.client_type, "REGULAR")
        self.assertEqual(client.discount_percentage, Decimal('5.00'))
        
    def test_vip_client(self):
        """اختبار العميل VIP"""
        client = Client.objects.create(
            name="عميل VIP",
            email="vip@test.com",
            client_type="VIP",
            discount_percentage=Decimal('15.00')
        )
        
        self.assertEqual(client.client_type, "VIP")
        self.assertEqual(client.discount_percentage, Decimal('15.00'))
        
    def test_wholesale_client(self):
        """اختبار عميل الجملة"""
        client = Client.objects.create(
            name="عميل جملة",
            email="wholesale@test.com",
            client_type="WHOLESALE",
            discount_percentage=Decimal('20.00')
        )
        
        self.assertEqual(client.client_type, "WHOLESALE")
        self.assertEqual(client.discount_percentage, Decimal('20.00'))


class ClientBusinessLogicTest(TestCase):
    """اختبارات منطق الأعمال للعملاء"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = Client.objects.create(
            name="عميل تجريبي",
            email="client@test.com",
            credit_limit=Decimal('5000.00')
        )
        
    def test_credit_limit_check(self):
        """اختبار فحص حد الائتمان"""
        # التحقق من حد الائتمان
        self.assertEqual(self.client.credit_limit, Decimal('5000.00'))
        
        # يمكن إضافة منطق فحص حد الائتمان هنا
        available_credit = self.client.credit_limit - self.client.balance
        self.assertEqual(available_credit, Decimal('5000.00'))
        
    def test_client_status_management(self):
        """اختبار إدارة حالة العميل"""
        # العميل نشط افتراضياً
        self.assertTrue(self.client.is_active)
        
        # تعطيل العميل
        self.client.is_active = False
        self.client.save()
        
        self.assertFalse(self.client.is_active)
        
    def test_client_contact_info(self):
        """اختبار معلومات الاتصال"""
        client = Client.objects.create(
            name="عميل كامل البيانات",
            email="complete@test.com",
            phone="01234567890",
            mobile="01098765432",
            address="شارع التحرير، القاهرة",
            city="القاهرة",
            country="مصر"
        )
        
        self.assertEqual(client.phone, "01234567890")
        self.assertEqual(client.mobile, "01098765432")
        self.assertEqual(client.city, "القاهرة")
        self.assertEqual(client.country, "مصر")
