from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from sale.models import Customer, Sale, SaleItem, SaleReturn, SaleReturnItem
from product.models import Category, Unit, Product, Warehouse, Stock
from decimal import Decimal
import datetime

User = get_user_model()

class CustomerModelTest(TestCase):
    """
    اختبارات نموذج العملاء
    """
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        self.customer = Customer.objects.create(
            name='عميل اختبار',
            phone='01234567890',
            email='customer@example.com',
            address='عنوان العميل للاختبار',
            tax_number='123456789',
            notes='ملاحظات خاصة بالعميل',
            created_by=self.user
        )

    def test_customer_creation(self):
        """
        اختبار إنشاء عميل بشكل صحيح
        """
        self.assertEqual(self.customer.name, 'عميل اختبار')
        self.assertEqual(self.customer.phone, '01234567890')
        self.assertEqual(self.customer.email, 'customer@example.com')
        self.assertEqual(self.customer.address, 'عنوان العميل للاختبار')
        self.assertEqual(self.customer.tax_number, '123456789')
        self.assertEqual(self.customer.notes, 'ملاحظات خاصة بالعميل')
        self.assertTrue(self.customer.is_active)
        self.assertEqual(self.customer.created_by, self.user)
        self.assertIsNotNone(self.customer.created_at)
        self.assertIsNotNone(self.customer.updated_at)

    def test_customer_str(self):
        """
        اختبار تمثيل العميل كنص
        """
        self.assertEqual(str(self.customer), 'عميل اختبار')

    def test_customer_soft_delete(self):
        """
        اختبار الحذف الناعم للعميل
        """
        customer_id = self.customer.id
        self.customer.delete()
        
        # يجب أن يكون الكائن غير موجود عند استخدام الدالة الافتراضية للحصول عليه
        self.assertFalse(Customer.objects.filter(id=customer_id).exists())
        
        # يجب أن يكون الكائن موجودًا عند استخدام all_objects
        self.assertTrue(Customer.all_objects.filter(id=customer_id).exists())
        
        # يجب أن تكون قيمة deleted_at محددة
        deleted_customer = Customer.all_objects.get(id=customer_id)
        self.assertIsNotNone(deleted_customer.deleted_at)


class SaleModelTest(TestCase):
    """
    اختبارات نموذج المبيعات
    """
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        self.customer = Customer.objects.create(
            name='عميل اختبار',
            phone='01234567890',
            created_by=self.user
        )
        
        # إنشاء المستودع
        self.warehouse = Warehouse.objects.create(
            name='مستودع اختبار',
            code='WH001',
            created_by=self.user
        )
        
        # إنشاء المنتجات للاختبار
        self.category = Category.objects.create(
            name='فئة اختبار',
            created_by=self.user
        )
        
        self.unit = Unit.objects.create(
            name='قطعة',
            abbreviation='ق',
            created_by=self.user
        )
        
        self.product1 = Product.objects.create(
            name='منتج اختبار 1',
            sku='P001',
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('80.00'),
            selling_price=Decimal('100.00'),
            created_by=self.user
        )
        
        self.product2 = Product.objects.create(
            name='منتج اختبار 2',
            sku='P002',
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('120.00'),
            selling_price=Decimal('150.00'),
            created_by=self.user
        )
        
        # إنشاء المخزون
        self.stock1 = Stock.objects.create(
            product=self.product1,
            warehouse=self.warehouse,
            quantity=20,
            created_by=self.user
        )
        
        self.stock2 = Stock.objects.create(
            product=self.product2,
            warehouse=self.warehouse,
            quantity=15,
            created_by=self.user
        )
        
        # إنشاء فاتورة مبيعات
        self.sale = Sale.objects.create(
            number='INV-001',
            customer=self.customer,
            warehouse=self.warehouse,
            date=timezone.now().date(),
            status='completed',
            payment_status='paid',
            reference='REF123',
            notes='ملاحظات فاتورة الاختبار',
            created_by=self.user
        )
        
        # إضافة بنود الفاتورة
        self.sale_item1 = SaleItem.objects.create(
            sale=self.sale,
            product=self.product1,
            quantity=5,
            unit_price=Decimal('100.00'),
            discount=Decimal('50.00'),
            created_by=self.user
        )
        
        self.sale_item2 = SaleItem.objects.create(
            sale=self.sale,
            product=self.product2,
            quantity=3,
            unit_price=Decimal('150.00'),
            discount=Decimal('0.00'),
            created_by=self.user
        )

    def test_sale_creation(self):
        """
        اختبار إنشاء فاتورة مبيعات بشكل صحيح
        """
        self.assertEqual(self.sale.number, 'INV-001')
        self.assertEqual(self.sale.customer, self.customer)
        self.assertEqual(self.sale.warehouse, self.warehouse)
        self.assertEqual(self.sale.status, 'completed')
        self.assertEqual(self.sale.payment_status, 'paid')
        self.assertEqual(self.sale.reference, 'REF123')
        self.assertEqual(self.sale.notes, 'ملاحظات فاتورة الاختبار')
        self.assertEqual(self.sale.created_by, self.user)
        self.assertIsNotNone(self.sale.created_at)

    def test_sale_str(self):
        """
        اختبار تمثيل فاتورة المبيعات كنص
        """
        expected_str = f"فاتورة مبيعات #{self.sale.number}"
        self.assertEqual(str(self.sale), expected_str)

    def test_sale_items_count(self):
        """
        اختبار عدد بنود الفاتورة
        """
        self.assertEqual(self.sale.items.count(), 2)

    def test_sale_total_calculation(self):
        """
        اختبار حساب إجمالي الفاتورة
        """
        # الإجمالي = (5 * 100 - 50) + (3 * 150) = 450 + 450 = 900
        expected_total = Decimal('900.00')
        self.assertEqual(self.sale.total, expected_total)

    def test_sale_item_subtotal_calculation(self):
        """
        اختبار حساب إجمالي البند
        """
        # إجمالي البند الأول = 5 * 100 - 50 = 450
        expected_subtotal1 = Decimal('450.00')
        self.assertEqual(self.sale_item1.subtotal, expected_subtotal1)
        
        # إجمالي البند الثاني = 3 * 150 = 450
        expected_subtotal2 = Decimal('450.00')
        self.assertEqual(self.sale_item2.subtotal, expected_subtotal2)
    
    def test_sale_profit_calculation(self):
        """
        اختبار حساب الربح من الفاتورة
        """
        # تكلفة البند الأول = 5 * 80 = 400
        # تكلفة البند الثاني = 3 * 120 = 360
        # إجمالي التكلفة = 400 + 360 = 760
        # الربح = إجمالي الفاتورة - إجمالي التكلفة = 900 - 760 = 140
        expected_profit = Decimal('140.00')
        self.assertEqual(self.sale.profit, expected_profit)


class SaleReturnModelTest(TestCase):
    """
    اختبارات نموذج مرتجع المبيعات
    """
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        self.customer = Customer.objects.create(
            name='عميل اختبار',
            phone='01234567890',
            created_by=self.user
        )
        
        # إنشاء المستودع
        self.warehouse = Warehouse.objects.create(
            name='مستودع اختبار',
            code='WH001',
            created_by=self.user
        )
        
        # إنشاء المنتجات للاختبار
        self.category = Category.objects.create(
            name='فئة اختبار',
            created_by=self.user
        )
        
        self.unit = Unit.objects.create(
            name='قطعة',
            abbreviation='ق',
            created_by=self.user
        )
        
        self.product = Product.objects.create(
            name='منتج اختبار',
            sku='P001',
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('80.00'),
            selling_price=Decimal('100.00'),
            created_by=self.user
        )
        
        # إنشاء المخزون
        self.stock = Stock.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=10,
            created_by=self.user
        )
        
        # إنشاء فاتورة مبيعات
        self.sale = Sale.objects.create(
            number='INV-001',
            customer=self.customer,
            warehouse=self.warehouse,
            date=timezone.now().date(),
            status='completed',
            payment_status='paid',
            created_by=self.user
        )
        
        # إضافة بند الفاتورة
        self.sale_item = SaleItem.objects.create(
            sale=self.sale,
            product=self.product,
            quantity=5,
            unit_price=Decimal('100.00'),
            discount=Decimal('0.00'),
            created_by=self.user
        )
        
        # إنشاء مرتجع مبيعات
        self.sale_return = SaleReturn.objects.create(
            number='SRET-001',
            sale=self.sale,
            date=timezone.now().date(),
            notes='ملاحظات مرتجع الاختبار',
            created_by=self.user
        )
        
        # إضافة بند المرتجع
        self.return_item = SaleReturnItem.objects.create(
            sale_return=self.sale_return,
            sale_item=self.sale_item,
            product=self.product,
            quantity=2,
            unit_price=Decimal('100.00'),
            reason='منتج تالف',
            created_by=self.user
        )

    def test_sale_return_creation(self):
        """
        اختبار إنشاء مرتجع مبيعات بشكل صحيح
        """
        self.assertEqual(self.sale_return.number, 'SRET-001')
        self.assertEqual(self.sale_return.sale, self.sale)
        self.assertEqual(self.sale_return.notes, 'ملاحظات مرتجع الاختبار')
        self.assertEqual(self.sale_return.created_by, self.user)
        self.assertIsNotNone(self.sale_return.created_at)

    def test_sale_return_str(self):
        """
        اختبار تمثيل مرتجع المبيعات كنص
        """
        expected_str = f"مرتجع مبيعات #{self.sale_return.number}"
        self.assertEqual(str(self.sale_return), expected_str)

    def test_sale_return_total_calculation(self):
        """
        اختبار حساب إجمالي المرتجع
        """
        # الإجمالي = 2 * 100 = 200
        expected_total = Decimal('200.00')
        self.assertEqual(self.sale_return.total, expected_total)

    def test_sale_return_item_subtotal_calculation(self):
        """
        اختبار حساب إجمالي بند المرتجع
        """
        # إجمالي البند = 2 * 100 = 200
        expected_subtotal = Decimal('200.00')
        self.assertEqual(self.return_item.subtotal, expected_subtotal) 