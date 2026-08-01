"""
اختبارات شاملة لنماذج المبيعات (بدون تخطي وإصلاح كافة الإعدادات)
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal

from sale.models import Sale, SaleItem, SalePayment, SaleReturn, SaleReturnItem
from client.models import Customer
from product.models import Product, Category, Unit, Warehouse

User = get_user_model()


class SaleModelTest(TestCase):
    """اختبارات نموذج المبيعات"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser_sale_model',
            password='testpass123',
            email='sale_model@example.com'
        )
        
        self.customer = Customer.objects.create(
            name='عميل اختبار',
            code='CUST_MODEL_01',
            phone='01234567890',
            email='customer@test.com'
        )
        
        self.warehouse = Warehouse.objects.create(
            name='المخزن الرئيسي',
            code='WH_MODEL_01'
        )
    
    def test_create_sale(self):
        """اختبار إنشاء فاتورة مبيعات"""
        sale = Sale.objects.create(
            number='SAL001',
            date=timezone.now().date(),
            customer=self.customer,
            warehouse=self.warehouse,
            subtotal=Decimal('1500.00'),
            discount=Decimal('75.00'),
            tax=Decimal('142.50'),
            total=Decimal('1567.50'),
            payment_method='cash',
            payment_status='paid',
            created_by=self.user
        )
        
        self.assertEqual(sale.number, 'SAL001')
        self.assertEqual(sale.customer, self.customer)
        self.assertEqual(sale.warehouse, self.warehouse)
        self.assertEqual(sale.total, Decimal('1567.50'))
        self.assertEqual(sale.status, 'confirmed')
    
    def test_sale_total_calculation(self):
        """اختبار حساب إجمالي الفاتورة"""
        sale = Sale.objects.create(
            number='SAL002',
            date=timezone.now().date(),
            customer=self.customer,
            warehouse=self.warehouse,
            subtotal=Decimal('2000.00'),
            discount=Decimal('100.00'),
            tax=Decimal('285.00'),
            total=Decimal('2185.00'),
            payment_method='cash',
            created_by=self.user
        )
        
        expected_total = sale.subtotal - sale.discount + sale.tax
        self.assertEqual(sale.total, expected_total)


class SaleItemModelTest(TestCase):
    """اختبارات نموذج عناصر المبيعات"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser_item_model',
            password='testpass123'
        )
        
        self.customer = Customer.objects.create(
            name='عميل اختبار 2',
            code='CUST_ITEM_01',
            phone='01234567891'
        )
        
        self.warehouse = Warehouse.objects.create(
            name='المخزن الفرعي',
            code='WH_ITEM_01'
        )
        
        self.category = Category.objects.create(
            name='فئة اختبار'
        )
        
        self.unit = Unit.objects.create(
            name='قطعة',
            symbol='قطعة'
        )
        
        self.product = Product.objects.create(
            name='منتج اختبار',
            sku='PROD_ITEM_01',
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('50.00'),
            selling_price=Decimal('100.00'),
            created_by=self.user
        )
        
        self.sale = Sale.objects.create(
            number='SAL_ITEM_001',
            date=timezone.now().date(),
            customer=self.customer,
            warehouse=self.warehouse,
            subtotal=Decimal('1000.00'),
            total=Decimal('1000.00'),
            payment_method='cash',
            created_by=self.user
        )
    
    def test_create_sale_item(self):
        """اختبار إنشاء عنصر مبيعات"""
        item = SaleItem.objects.create(
            sale=self.sale,
            product=self.product,
            quantity=Decimal('10.00'),
            unit_price=Decimal('50.00')
        )
        
        self.assertEqual(item.sale, self.sale)
        self.assertEqual(item.product, self.product)
        self.assertEqual(item.quantity, Decimal('10.00'))
        self.assertEqual(item.unit_price, Decimal('50.00'))
    
    def test_sale_item_with_discount(self):
        """اختبار عنصر مبيعات مع خصم"""
        item = SaleItem.objects.create(
            sale=self.sale,
            product=self.product,
            quantity=Decimal('20.00'),
            unit_price=Decimal('30.00'),
            discount=Decimal('60.00')
        )
        
        expected_total = (item.quantity * item.unit_price) - item.discount
        self.assertEqual(item.total, expected_total)


class SalePaymentModelTest(TestCase):
    """اختبارات نموذج دفعات المبيعات"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser_payment_model',
            password='testpass123'
        )
        
        self.customer = Customer.objects.create(
            name='عميل الدفعات',
            code='CUST_PAY_01',
            phone='01234567892'
        )
        
        self.warehouse = Warehouse.objects.create(
            name='مخزن الدفعات',
            code='WH_PAY_01'
        )
        
        self.sale = Sale.objects.create(
            number='SAL_PAY_001',
            date=timezone.now().date(),
            customer=self.customer,
            warehouse=self.warehouse,
            subtotal=Decimal('2000.00'),
            total=Decimal('2000.00'),
            payment_method='cash',
            payment_status='unpaid',
            created_by=self.user
        )
    
    def test_create_sale_payment(self):
        """اختبار إنشاء دفعة مبيعات"""
        payment = SalePayment.objects.create(
            sale=self.sale,
            amount=Decimal('1000.00'),
            payment_date=timezone.now().date(),
            payment_method='cash',
            reference_number='PAY001',
            created_by=self.user
        )
        
        self.assertEqual(payment.sale, self.sale)
        self.assertEqual(payment.amount, Decimal('1000.00'))


class SaleReturnModelTest(TestCase):
    """اختبارات نموذج مرتجعات المبيعات"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser_return_model',
            password='testpass123'
        )
        
        self.customer = Customer.objects.create(
            name='عميل المرتجعات',
            code='CUST_RET_01',
            phone='01234567893'
        )
        
        self.warehouse = Warehouse.objects.create(
            name='مخزن المرتجعات',
            code='WH_RET_01'
        )
        
        self.sale = Sale.objects.create(
            number='SAL_RET_001',
            date=timezone.now().date(),
            customer=self.customer,
            warehouse=self.warehouse,
            subtotal=Decimal('1500.00'),
            total=Decimal('1500.00'),
            payment_method='cash',
            created_by=self.user
        )
    
    def test_create_sale_return(self):
        """اختبار إنشاء مرتجع مبيعات"""
        return_obj = SaleReturn.objects.create(
            sale=self.sale,
            warehouse=self.warehouse,
            number='RET001',
            date=timezone.now().date(),
            subtotal=Decimal('300.00'),
            discount=Decimal('0.00'),
            tax=Decimal('0.00'),
            total=Decimal('300.00'),
            created_by=self.user,
            status='draft'
        )
        
        self.assertEqual(return_obj.sale, self.sale)
        self.assertEqual(return_obj.total, Decimal('300.00'))
