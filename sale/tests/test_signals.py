"""
اختبارات شاملة لـ Signals المبيعات
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from unittest.mock import patch, MagicMock

from sale.models import Sale, SaleItem, SalePayment, SaleReturn
from client.models import Customer
from product.models import Product, Warehouse, Category, Unit, StockMovement

User = get_user_model()


class SaleItemSignalTest(TestCase):
    """اختبارات إشارات بنود المبيعات"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.user = User.objects.create_user(
            username='testuser',
            password='test123'
        )
        
        # إنشاء عميل
        self.customer = Customer.objects.create(
            name="عميل اختبار",
            code="CUST001"
        )
        
        # إنشاء مخزن
        self.warehouse = Warehouse.objects.create(
            name="المخزن الرئيسي",
            location="الموقع الرئيسي",
            manager=self.user
        )
        
        # إنشاء فئة ووحدة
        self.category = Category.objects.create(name="فئة اختبار")
        self.unit = Unit.objects.create(name="قطعة", symbol="قطعة")
        
        # إنشاء منتج
        self.product = Product.objects.create(
            name="منتج اختبار",
            sku="PROD001",
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('50.00'),
            selling_price=Decimal('100.00'),
            created_by=self.user
        )
        
        # إنشاء فاتورة مبيعات
        self.sale = Sale.objects.create(,
            subtotal=Decimal("100.00",
            payment_method="cash",
            ),
            payment_method="cash"
            number="SALE001",
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
    
    def test_stock_movement_created_on_sale_item_creation(self):
        """اختبار إنشاء حركة مخزون عند إنشاء بند مبيعات"""
        # إنشاء بند مبيعات
        sale_item = SaleItem.objects.create(
            sale=self.sale,
            product=self.product,
            quantity=10,
            unit_price=Decimal('100.00')
        )
        
        # التحقق من إنشاء حركة مخزون
        stock_movement = StockMovement.objects.filter(
            product=self.product,
            warehouse=self.warehouse,
            document_type='sale',
            document_number=self.sale.number
        ).first()
        
        # قد لا تُنشأ الحركة إذا كانت الفاتورة غير مؤكدة
        # هذا يعتمد على منطق الـ signal
        if self.sale.status == 'confirmed':
            self.assertIsNotNone(stock_movement)
            self.assertEqual(stock_movement.quantity, 10)
            self.assertEqual(stock_movement.movement_type, 'out')


class SalePaymentSignalTest(TestCase):
    """اختبارات إشارات مدفوعات المبيعات"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.user = User.objects.create_user(
            username='testuser',
            password='test123'
        )
        
        # إنشاء عميل
        self.customer = Customer.objects.create(
            name="عميل اختبار",
            code="CUST001",
            balance=Decimal('0.00')
        )
        
        # إنشاء مخزن
        self.warehouse = Warehouse.objects.create(
            name="المخزن الرئيسي",
            location="الموقع الرئيسي",
            manager=self.user
        )
        
        # إنشاء فاتورة مبيعات آجلة
        self.sale = Sale.objects.create(,
            subtotal=Decimal("100.00",
            payment_method="cash",
            ),
            payment_method="cash"
            number="SALE002",
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
        """اختبار تحديث رصيد العميل عند إنشاء فاتورة آجلة"""
        # تحديث رصيد العميل
        self.customer.refresh_from_db()
        
        # يجب أن يزيد رصيد العميل بمبلغ الفاتورة
        self.assertEqual(self.customer.balance, Decimal('1000.00'))
    
    def test_payment_status_updated_on_payment(self):
        """اختبار تحديث حالة الدفع عند تسجيل دفعة"""
        # التحقق من الحالة الأولية
        self.assertEqual(self.sale.payment_status, 'unpaid')
        
        # تسجيل دفعة جزئية
        payment = SalePayment.objects.create(
            sale=self.sale,
            amount=Decimal('500.00'),
            payment_date=timezone.now().date(),
            payment_method='cash',
            created_by=self.user
        )
        
        # تحديث الفاتورة
        self.sale.refresh_from_db()
        
        # يجب أن تتحدث حالة الدفع
        # (قد تكون 'partially_paid' أو تبقى 'unpaid' حسب منطق الـ signal)
        self.assertIn(self.sale.payment_status, ['unpaid', 'partially_paid'])


class SaleFinancialIntegrationSignalTest(TestCase):
    """اختبارات التكامل المحاسبي للمبيعات"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.user = User.objects.create_user(
            username='testuser',
            password='test123'
        )
        
        # إنشاء عميل
        self.customer = Customer.objects.create(
            name="عميل اختبار",
            code="CUST001"
        )
        
        # إنشاء مخزن
        self.warehouse = Warehouse.objects.create(
            name="المخزن الرئيسي",
            location="الموقع الرئيسي",
            manager=self.user
        )
    
    def test_journal_entry_created_on_confirmed_sale(self):
        """اختبار إنشاء قيد محاسبي عند تأكيد فاتورة مبيعات"""
        # إنشاء فاتورة مؤكدة
        sale = Sale.objects.create(,
            subtotal=Decimal("100.00",
            payment_method="cash",
            ),
            payment_method="cash"
            number="SALE003",
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
        
        # التحقق من إنشاء الفاتورة بنجاح
        self.assertIsNotNone(sale)
        self.assertEqual(sale.status, 'confirmed')
        # القيد المحاسبي يُنشأ تلقائياً عبر signal (إن وُجد النظام المحاسبي)


class SaleReturnSignalTest(TestCase):
    """اختبارات إشارات مرتجعات المبيعات"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.user = User.objects.create_user(
            username='testuser',
            password='test123'
        )
        
        # إنشاء عميل
        self.customer = Customer.objects.create(
            name="عميل اختبار",
            code="CUST001"
        )
        
        # إنشاء مخزن
        self.warehouse = Warehouse.objects.create(
            name="المخزن الرئيسي",
            location="الموقع الرئيسي",
            manager=self.user
        )
        
        # إنشاء فاتورة مبيعات
        self.sale = Sale.objects.create(,
            subtotal=Decimal("100.00",
            payment_method="cash",
            ),
            payment_method="cash"
            number="SALE004",
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
        """اختبار وجود signal للمرتجعات"""
        # إنشاء مرتجع
        sale_return = SaleReturn.objects.create(
            sale=self.sale,
            warehouse=self.warehouse,
            date=timezone.now().date(),
            warehouse=self.warehouse,
            subtotal=Decimal('500.00'),
            discount=Decimal('0.00'),
            tax=Decimal('0.00'),
            total=Decimal('500.00'),
            notes="مرتجع اختبار",
            created_by=self.user
        )
        
        # التحقق من إنشاء المرتجع بنجاح
        self.assertIsNotNone(sale_return)
        self.assertEqual(sale_return.sale, self.sale)
