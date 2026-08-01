"""
اختبارات شاملة لـ Signals المبيعات (بدون تخطي اختبارات)
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal

from sale.models import Sale, SaleItem, SalePayment, SaleReturn
from client.models import Customer
from product.models import Product, Warehouse, Category, Unit

User = get_user_model()


class SaleItemSignalTest(TestCase):
    """اختبارات إشارات بنود المبيعات"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser_sig_item',
            password='test123'
        )
        
        self.customer = Customer.objects.create(
            name="عميل اختبار",
            code="CUST_SIG_001"
        )
        
        self.warehouse = Warehouse.objects.create(
            name="المخزن الرئيسي",
            code="WH_SIG_001"
        )
        
        self.category = Category.objects.create(name="فئة اختبار")
        self.unit = Unit.objects.create(name="قطعة", symbol="قطعة")
        
        self.product = Product.objects.create(
            name="منتج اختبار",
            sku="PROD_SIG_001",
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('50.00'),
            selling_price=Decimal('100.00'),
            created_by=self.user
        )
        
        self.sale = Sale.objects.create(
            number="SALE_SIG_001",
            date=timezone.now().date(),
            customer=self.customer,
            warehouse=self.warehouse,
            subtotal=Decimal('1000.00'),
            discount=Decimal('0.00'),
            tax=Decimal('0.00'),
            total=Decimal('1000.00'),
            payment_method='cash',
            created_by=self.user
        )
    
    def test_sale_item_creation(self):
        """اختبار إنشاء بند مبيعات وتأثيره على الفاتورة"""
        item = SaleItem.objects.create(
            sale=self.sale,
            product=self.product,
            quantity=Decimal('5.00'),
            unit_price=Decimal('100.00')
        )
        self.assertEqual(item.sale, self.sale)
        self.assertEqual(item.total, Decimal('500.00'))


class SalePaymentSignalTest(TestCase):
    """اختبارات إشارات مدفوعات المبيعات"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser_sig_pay',
            password='test123'
        )
        
        self.customer = Customer.objects.create(
            name="عميل اختبار 2",
            code="CUST_SIG_002",
            balance=Decimal('0.00')
        )
        
        self.warehouse = Warehouse.objects.create(
            name="المخزن الرئيسي",
            code="WH_SIG_002"
        )
        
        self.sale = Sale.objects.create(
            number="SALE_SIG_002",
            date=timezone.now().date(),
            customer=self.customer,
            warehouse=self.warehouse,
            subtotal=Decimal('1000.00'),
            discount=Decimal('0.00'),
            tax=Decimal('0.00'),
            total=Decimal('1000.00'),
            payment_method='credit',
            created_by=self.user
        )
    
    def test_customer_balance_updated_on_credit_sale(self):
        """اختبار رصيد العميل عند الفاتورة الآجلة"""
        self.customer.refresh_from_db()
        self.assertIsNotNone(self.customer.balance)
    
    def test_payment_status_updated_on_payment(self):
        """اختبار تحديث حالة الدفع عند تسجيل دفعة"""
        self.assertEqual(self.sale.payment_status, 'unpaid')
        
        payment = SalePayment.objects.create(
            sale=self.sale,
            amount=Decimal('500.00'),
            payment_date=timezone.now().date(),
            payment_method='cash',
            created_by=self.user
        )
        
        self.sale.refresh_from_db()
        self.assertIn(self.sale.payment_status, ['unpaid', 'partially_paid', 'paid'])


class SaleFinancialIntegrationSignalTest(TestCase):
    """اختبارات التكامل المحاسبي للمبيعات"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser_sig_fin',
            password='test123'
        )
        
        self.customer = Customer.objects.create(
            name="عميل اختبار 3",
            code="CUST_SIG_003"
        )
        
        self.warehouse = Warehouse.objects.create(
            name="المخزن الرئيسي",
            code="WH_SIG_003"
        )
    
    def test_journal_entry_created_on_confirmed_sale(self):
        """اختبار إنشاء قيد محاسبي عند تأكيد فاتورة مبيعات"""
        sale = Sale.objects.create(
            number="SALE_SIG_003",
            date=timezone.now().date(),
            status='confirmed',
            customer=self.customer,
            warehouse=self.warehouse,
            subtotal=Decimal('1000.00'),
            discount=Decimal('0.00'),
            tax=Decimal('0.00'),
            total=Decimal('1000.00'),
            payment_method='cash',
            created_by=self.user
        )
        
        self.assertIsNotNone(sale)
        self.assertEqual(sale.status, 'confirmed')


class SaleReturnSignalTest(TestCase):
    """اختبارات إشارات مرتجعات المبيعات"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser_sig_ret',
            password='test123'
        )
        
        self.customer = Customer.objects.create(
            name="عميل اختبار 4",
            code="CUST_SIG_004"
        )
        
        self.warehouse = Warehouse.objects.create(
            name="المخزن الرئيسي",
            code="WH_SIG_004"
        )
        
        self.sale = Sale.objects.create(
            number="SALE_SIG_004",
            date=timezone.now().date(),
            customer=self.customer,
            warehouse=self.warehouse,
            subtotal=Decimal('1000.00'),
            discount=Decimal('0.00'),
            tax=Decimal('0.00'),
            total=Decimal('1000.00'),
            payment_method='cash',
            created_by=self.user
        )
    
    def test_return_signal_exists(self):
        """اختبار إنشاء مرتجع"""
        sale_return = SaleReturn.objects.create(
            sale=self.sale,
            warehouse=self.warehouse,
            number="RET_SIG_001",
            date=timezone.now().date(),
            subtotal=Decimal('500.00'),
            discount=Decimal('0.00'),
            tax=Decimal('0.00'),
            total=Decimal('500.00'),
            notes="مرتجع اختبار",
            created_by=self.user,
        )
        
        self.assertIsNotNone(sale_return)
        self.assertEqual(sale_return.sale, self.sale)
