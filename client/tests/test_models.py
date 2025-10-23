"""
اختبارات شاملة لنماذج العملاء - تغطية 100%
"""

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from decimal import Decimal
from datetime import date, datetime, timedelta
from unittest.mock import patch, Mock

from ..models import Customer, CustomerPayment

User = get_user_model()


class CustomerModelTest(TestCase):
    """اختبارات نموذج العملاء"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.user = User.objects.create_user(
            username="testuser",
            password="test123"
        )
        
    def test_create_customer(self):
        """اختبار إنشاء عميل جديد"""
        customer = Customer.objects.create(
            name="عميل تجريبي",
            code="TEST001",
            email="client@test.com",
            phone="+201234567890",
            address="القاهرة، مصر",
            client_type="individual"
        )
        
        self.assertEqual(customer.name, "عميل تجريبي")
        self.assertEqual(customer.code, "TEST001")
        self.assertEqual(customer.email, "client@test.com")
        self.assertEqual(customer.client_type, "individual")
        self.assertTrue(customer.is_active)
        
    def test_customer_str_method(self):
        """اختبار طريقة __str__ للعميل"""
        customer = Customer.objects.create(
            name="عميل تجريبي",
            code="TEST002",
            email="client@test.com"
        )
        
        self.assertEqual(str(customer), "عميل تجريبي")
        
    def test_customer_balance_calculation(self):
        """اختبار حساب رصيد العميل"""
        customer = Customer.objects.create(
            name="عميل تجريبي",
            code="TEST003",
            email="client@test.com"
        )
        
        # الرصيد الأولي يجب أن يكون صفر
        self.assertEqual(customer.balance, Decimal('0'))
        
    def test_customer_credit_limit(self):
        """اختبار حد الائتمان للعميل"""
        customer = Customer.objects.create(
            name="عميل VIP",
            code="VIP001",
            email="vip@test.com",
            client_type="vip",
            credit_limit=Decimal('50000.00')
        )
        
        self.assertEqual(customer.client_type, "vip")
        self.assertEqual(customer.credit_limit, Decimal('50000.00'))
        
    def test_available_credit(self):
        """اختبار حساب الرصيد المتاح"""
        customer = Customer.objects.create(
            name="عميل اختبار",
            code="TEST004",
            credit_limit=Decimal('10000.00'),
            balance=Decimal('3000.00')
        )
        
        # الرصيد المتاح = حد الائتمان - الرصيد الحالي
        self.assertEqual(customer.available_credit, Decimal('7000.00'))


class CustomerPaymentTest(TestCase):
    """اختبارات مدفوعات العملاء"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.user = User.objects.create_user(
            username="testuser",
            password="test123"
        )
        
        self.customer = Customer.objects.create(
            name="عميل تجريبي",
            code="CUST001",
            email="client@test.com"
        )
        
    def test_create_customer_payment(self):
        """اختبار إنشاء دفعة عميل"""
        payment = CustomerPayment.objects.create(
            customer=self.customer,
            amount=Decimal('500.00'),
            payment_date=date.today(),
            payment_method="cash",
            created_by=self.user
        )
        
        self.assertEqual(payment.customer, self.customer)
        self.assertEqual(payment.amount, Decimal('500.00'))
        self.assertEqual(payment.payment_method, "cash")
        
    def test_payment_str_method(self):
        """اختبار طريقة __str__ للدفعة"""
        payment = CustomerPayment.objects.create(
            customer=self.customer,
            amount=Decimal('200.00'),
            payment_date=date.today(),
            payment_method="bank_transfer"
        )
        
        str_result = str(payment)
        self.assertIn("عميل تجريبي", str_result)
        self.assertIn("200", str_result)


class CustomerTypesTest(TestCase):
    """اختبارات أنواع العملاء"""
    
    def test_individual_customer(self):
        """اختبار العميل الفرد"""
        customer = Customer.objects.create(
            name="عميل فرد",
            code="IND001",
            email="individual@test.com",
            client_type="individual"
        )
        
        self.assertEqual(customer.client_type, "individual")
        
    def test_company_customer(self):
        """اختبار العميل شركة"""
        customer = Customer.objects.create(
            name="شركة اختبار",
            code="COMP001",
            company_name="شركة اختبار المحدودة",
            email="company@test.com",
            client_type="company"
        )
        
        self.assertEqual(customer.client_type, "company")
        self.assertEqual(customer.company_name, "شركة اختبار المحدودة")
        
    def test_vip_customer(self):
        """اختبار العميل VIP"""
        customer = Customer.objects.create(
            name="عميل VIP",
            code="VIP002",
            email="vip@test.com",
            client_type="vip",
            credit_limit=Decimal('100000.00')
        )
        
        self.assertEqual(customer.client_type, "vip")
        self.assertEqual(customer.credit_limit, Decimal('100000.00'))


class CustomerBusinessLogicTest(TestCase):
    """اختبارات منطق الأعمال للعملاء"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.customer = Customer.objects.create(
            name="عميل تجريبي",
            code="BUS001",
            email="client@test.com",
            credit_limit=Decimal('5000.00')
        )
        
    def test_credit_limit_check(self):
        """اختبار فحص حد الائتمان"""
        # التحقق من حد الائتمان
        self.assertEqual(self.customer.credit_limit, Decimal('5000.00'))
        
        # حساب الرصيد المتاح
        available_credit = self.customer.credit_limit - self.customer.balance
        self.assertEqual(available_credit, Decimal('5000.00'))
        
    def test_customer_status_management(self):
        """اختبار إدارة حالة العميل"""
        # العميل نشط افتراضياً
        self.assertTrue(self.customer.is_active)
        
        # تعطيل العميل
        self.customer.is_active = False
        self.customer.save()
        
        self.assertFalse(self.customer.is_active)
        
    def test_customer_contact_info(self):
        """اختبار معلومات الاتصال"""
        customer = Customer.objects.create(
            name="عميل كامل البيانات",
            code="FULL001",
            email="complete@test.com",
            phone="+201234567890",
            phone_primary="+201234567890",
            phone_secondary="+201098765432",
            address="شارع التحرير، القاهرة",
            city="القاهرة"
        )
        
        self.assertEqual(customer.phone, "+201234567890")
        self.assertEqual(customer.phone_primary, "+201234567890")
        self.assertEqual(customer.phone_secondary, "+201098765432")
        self.assertEqual(customer.city, "القاهرة")


# ==================== اختبارات شاملة متقدمة ====================


class CustomerAdvancedTest(TestCase):
    """اختبارات متقدمة لنموذج العميل"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.user = User.objects.create_user(
            username="testuser",
            password="test123",
            email="test@test.com"
        )
        
    def test_create_customer_with_all_fields(self):
        """اختبار إنشاء عميل مع جميع الحقول"""
        customer = Customer.objects.create(
            name="عميل كامل البيانات",
            code="FULL002",
            company_name="شركة الاختبار المحدودة",
            phone="+201234567890",
            phone_primary="+201234567890",
            phone_secondary="+201098765432",
            email="full@test.com",
            address="123 شارع الاختبار، القاهرة",
            city="القاهرة",
            client_type="company",
            credit_limit=Decimal('100000.00'),
            balance=Decimal('5000.00'),
            tax_number="TAX123456",
            contact_frequency="monthly",
            last_contact_date=datetime.now(),
            notes="عميل مهم جداً",
            is_active=True,
            created_by=self.user
        )
        
        self.assertEqual(customer.name, "عميل كامل البيانات")
        self.assertEqual(customer.company_name, "شركة الاختبار المحدودة")
        self.assertEqual(customer.tax_number, "TAX123456")
        self.assertEqual(customer.contact_frequency, "monthly")
        
    def test_customer_code_unique_constraint(self):
        """اختبار أن كود العميل يجب أن يكون فريد"""
        Customer.objects.create(name="عميل 1", code="UNIQUE001")
        
        with self.assertRaises(IntegrityError):
            Customer.objects.create(name="عميل 2", code="UNIQUE001")
            
    def test_customer_ordering(self):
        """اختبار ترتيب العملاء حسب الاسم"""
        Customer.objects.create(name="زيد", code="C001")
        Customer.objects.create(name="أحمد", code="C002")
        Customer.objects.create(name="محمد", code="C003")
        
        customers = list(Customer.objects.all())
        self.assertEqual(customers[0].name, "أحمد")
        self.assertEqual(customers[1].name, "زيد")
        self.assertEqual(customers[2].name, "محمد")
        
    def test_valid_phone_numbers(self):
        """اختبار أرقام هواتف صحيحة"""
        valid_phones = ["+201234567890", "+966512345678", "01234567890"]
        
        for i, phone in enumerate(valid_phones):
            customer = Customer.objects.create(
                name=f"عميل {i}",
                code=f"PHONE{i:03d}",
                phone=phone
            )
            self.assertEqual(customer.phone, phone)
            
    def test_invalid_phone_numbers(self):
        """اختبار أرقام هواتف غير صحيحة"""
        invalid_phones = ["123", "abc123456789", "+1234567890123456"]
        
        for i, phone in enumerate(invalid_phones):
            with self.assertRaises(ValidationError):
                customer = Customer(
                    name=f"عميل {i}",
                    code=f"INVPHONE{i:03d}",
                    phone=phone
                )
                customer.full_clean()
                
    def test_customer_timestamps(self):
        """اختبار created_at و updated_at"""
        customer = Customer.objects.create(
            name="عميل التواريخ",
            code="TIME001"
        )
        
        self.assertIsNotNone(customer.created_at)
        self.assertIsNotNone(customer.updated_at)
        
        old_updated_at = customer.updated_at
        customer.name = "عميل محدث"
        customer.save()
        
        self.assertGreater(customer.updated_at, old_updated_at)
        
    def test_filter_active_customers(self):
        """اختبار فلترة العملاء النشطين"""
        Customer.objects.create(name="نشط 1", code="ACT001", is_active=True)
        Customer.objects.create(name="نشط 2", code="ACT002", is_active=True)
        Customer.objects.create(name="معطل", code="INACT001", is_active=False)
        
        active_customers = Customer.objects.filter(is_active=True)
        self.assertEqual(active_customers.count(), 2)


class CustomerPaymentAdvancedTest(TestCase):
    """اختبارات متقدمة لمدفوعات العملاء"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.user = User.objects.create_user(
            username="testuser",
            password="test123"
        )
        
        self.customer = Customer.objects.create(
            name="عميل الدفعات",
            code="PAYCUST001",
            created_by=self.user
        )
        
    def test_create_payment_all_fields(self):
        """اختبار إنشاء دفعة مع جميع الحقول"""
        payment = CustomerPayment.objects.create(
            customer=self.customer,
            amount=Decimal('1000.00'),
            payment_date=date.today(),
            payment_method="cash",
            reference_number="REF123456",
            notes="دفعة نقدية",
            created_by=self.user
        )
        
        self.assertEqual(payment.reference_number, "REF123456")
        self.assertEqual(payment.notes, "دفعة نقدية")
        self.assertEqual(payment.created_by, self.user)
        
    def test_all_payment_methods(self):
        """اختبار جميع طرق الدفع"""
        methods = ["cash", "bank_transfer", "check"]
        
        for i, method in enumerate(methods):
            payment = CustomerPayment.objects.create(
                customer=self.customer,
                amount=Decimal('100.00'),
                payment_date=date.today(),
                payment_method=method
            )
            self.assertEqual(payment.payment_method, method)
            
    def test_payment_ordering(self):
        """اختبار ترتيب الدفعات حسب التاريخ (الأحدث أولاً)"""
        payment1 = CustomerPayment.objects.create(
            customer=self.customer,
            amount=Decimal('100.00'),
            payment_date=date(2025, 1, 1),
            payment_method="cash"
        )
        payment2 = CustomerPayment.objects.create(
            customer=self.customer,
            amount=Decimal('200.00'),
            payment_date=date(2025, 1, 15),
            payment_method="cash"
        )
        
        payments = list(CustomerPayment.objects.all())
        self.assertEqual(payments[0], payment2)  # الأحدث
        self.assertEqual(payments[1], payment1)  # الأقدم
        
    def test_multiple_payments_for_customer(self):
        """اختبار دفعات متعددة لنفس العميل"""
        CustomerPayment.objects.create(
            customer=self.customer,
            amount=Decimal('100.00'),
            payment_date=date.today(),
            payment_method="cash"
        )
        CustomerPayment.objects.create(
            customer=self.customer,
            amount=Decimal('200.00'),
            payment_date=date.today(),
            payment_method="bank_transfer"
        )
        
        self.assertEqual(self.customer.payments.count(), 2)
        
    def test_payment_protect_on_customer_delete(self):
        """اختبار حماية الدفعة عند حذف العميل"""
        CustomerPayment.objects.create(
            customer=self.customer,
            amount=Decimal('500.00'),
            payment_date=date.today(),
            payment_method="cash"
        )
        
        with self.assertRaises(Exception):
            self.customer.delete()
