from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from purchase.models import Supplier, Purchase, PurchaseItem, PurchaseReturn, PurchaseReturnItem
from product.models import Product, Category, Brand, Unit, Warehouse, Stock
from decimal import Decimal

User = get_user_model()

class SupplierModelTest(TestCase):
    """
    اختبارات نموذج المورد
    """
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        
        self.supplier = Supplier.objects.create(
            name='مورد اختبار',
            phone='01234567890',
            email='supplier@test.com',
            address='عنوان المورد للاختبار',
            created_by=self.user
        )
    
    def test_supplier_creation(self):
        """
        اختبار إنشاء مورد بالبيانات الصحيحة
        """
        self.assertEqual(self.supplier.name, 'مورد اختبار')
        self.assertEqual(self.supplier.phone, '01234567890')
        self.assertEqual(self.supplier.email, 'supplier@test.com')
        self.assertEqual(self.supplier.address, 'عنوان المورد للاختبار')
        self.assertEqual(self.supplier.created_by, self.user)
        self.assertIsNotNone(self.supplier.created_at)
    
    def test_supplier_str(self):
        """
        اختبار النص التمثيلي للمورد
        """
        self.assertEqual(str(self.supplier), 'مورد اختبار')
    
    def test_supplier_soft_delete(self):
        """
        اختبار الحذف الناعم للمورد
        """
        supplier_id = self.supplier.id
        self.supplier.delete()
        
        # التأكد من عدم وجود المورد في الاستعلام العادي
        self.assertFalse(Supplier.objects.filter(id=supplier_id).exists())
        
        # التأكد من وجود المورد في all_objects (الكائنات المحذوفة)
        self.assertTrue(Supplier.all_objects.filter(id=supplier_id).exists())
        
        # التأكد من أن المورد تم تعليمه كمحذوف
        supplier = Supplier.all_objects.get(id=supplier_id)
        self.assertTrue(supplier.is_deleted)


class PurchaseModelTest(TestCase):
    """
    اختبارات نموذج المشتريات
    """
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        
        # إنشاء مورد للاختبار
        self.supplier = Supplier.objects.create(
            name='مورد المنتجات',
            phone='01234567890',
            created_by=self.user
        )
        
        # إنشاء مستودع
        self.warehouse = Warehouse.objects.create(
            name='المستودع الرئيسي',
            location='موقع المستودع',
            created_by=self.user
        )
        
        # إنشاء فئة ووحدة وعلامة تجارية
        self.category = Category.objects.create(
            name='فئة اختبار',
            created_by=self.user
        )
        
        self.brand = Brand.objects.create(
            name='علامة تجارية',
            created_by=self.user
        )
        
        self.unit = Unit.objects.create(
            name='قطعة',
            created_by=self.user
        )
        
        # إنشاء منتجات للاختبار
        self.product1 = Product.objects.create(
            name='منتج اختبار 1',
            code='TEST001',
            category=self.category,
            brand=self.brand,
            unit=self.unit,
            purchase_price=Decimal('100.00'),
            sale_price=Decimal('150.00'),
            created_by=self.user
        )
        
        self.product2 = Product.objects.create(
            name='منتج اختبار 2',
            code='TEST002',
            category=self.category,
            brand=self.brand,
            unit=self.unit,
            purchase_price=Decimal('200.00'),
            sale_price=Decimal('300.00'),
            created_by=self.user
        )
        
        # إنشاء عملية شراء
        self.purchase = Purchase.objects.create(
            date=timezone.now().date(),
            supplier=self.supplier,
            warehouse=self.warehouse,
            reference='PO-001',
            discount=Decimal('50.00'),
            tax=Decimal('10.00'),
            shipping=Decimal('20.00'),
            status='completed',
            notes='ملاحظات للاختبار',
            created_by=self.user
        )
        
        # إنشاء عناصر الشراء
        self.purchase_item1 = PurchaseItem.objects.create(
            purchase=self.purchase,
            product=self.product1,
            quantity=5,
            price=Decimal('100.00'),
            created_by=self.user
        )
        
        self.purchase_item2 = PurchaseItem.objects.create(
            purchase=self.purchase,
            product=self.product2,
            quantity=3,
            price=Decimal('200.00'),
            created_by=self.user
        )
    
    def test_purchase_creation(self):
        """
        اختبار إنشاء عملية شراء بالبيانات الصحيحة
        """
        self.assertEqual(self.purchase.supplier, self.supplier)
        self.assertEqual(self.purchase.warehouse, self.warehouse)
        self.assertEqual(self.purchase.reference, 'PO-001')
        self.assertEqual(self.purchase.discount, Decimal('50.00'))
        self.assertEqual(self.purchase.tax, Decimal('10.00'))
        self.assertEqual(self.purchase.shipping, Decimal('20.00'))
        self.assertEqual(self.purchase.status, 'completed')
        self.assertEqual(self.purchase.notes, 'ملاحظات للاختبار')
        self.assertEqual(self.purchase.created_by, self.user)
        self.assertIsNotNone(self.purchase.created_at)
    
    def test_purchase_str(self):
        """
        اختبار النص التمثيلي لعملية الشراء
        """
        expected = f'PO-001 - مورد المنتجات - {self.purchase.date}'
        self.assertEqual(str(self.purchase), expected)
    
    def test_purchase_items_count(self):
        """
        اختبار عدد عناصر عملية الشراء
        """
        self.assertEqual(self.purchase.items.count(), 2)
    
    def test_purchase_total_calculation(self):
        """
        اختبار حساب إجمالي عملية الشراء
        """
        # حساب الإجمالي يدوياً
        # (5 * 100) + (3 * 200) = 500 + 600 = 1100
        # الإجمالي = 1100 - الخصم (50) + الضريبة (10) + الشحن (20) = 1080
        expected_total = Decimal('1080.00')
        self.assertEqual(self.purchase.total, expected_total)
    
    def test_purchase_subtotal_calculation(self):
        """
        اختبار حساب المجموع الفرعي لعملية الشراء (قبل الخصم والضريبة والشحن)
        """
        # (5 * 100) + (3 * 200) = 500 + 600 = 1100
        expected_subtotal = Decimal('1100.00')
        self.assertEqual(self.purchase.subtotal, expected_subtotal)
    
    def test_purchase_item_subtotal_calculation(self):
        """
        اختبار حساب المجموع الفرعي لعنصر الشراء
        """
        # عنصر الشراء 1: 5 * 100 = 500
        self.assertEqual(self.purchase_item1.subtotal, Decimal('500.00'))
        
        # عنصر الشراء 2: 3 * 200 = 600
        self.assertEqual(self.purchase_item2.subtotal, Decimal('600.00'))


class PurchaseReturnModelTest(TestCase):
    """
    اختبارات نموذج مرتجعات المشتريات
    """
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        
        # إنشاء مورد للاختبار
        self.supplier = Supplier.objects.create(
            name='مورد المنتجات',
            phone='01234567890',
            created_by=self.user
        )
        
        # إنشاء مستودع
        self.warehouse = Warehouse.objects.create(
            name='المستودع الرئيسي',
            location='موقع المستودع',
            created_by=self.user
        )
        
        # إنشاء فئة ووحدة وعلامة تجارية
        self.category = Category.objects.create(
            name='فئة اختبار',
            created_by=self.user
        )
        
        self.brand = Brand.objects.create(
            name='علامة تجارية',
            created_by=self.user
        )
        
        self.unit = Unit.objects.create(
            name='قطعة',
            created_by=self.user
        )
        
        # إنشاء منتجات للاختبار
        self.product1 = Product.objects.create(
            name='منتج اختبار 1',
            code='TEST001',
            category=self.category,
            brand=self.brand,
            unit=self.unit,
            purchase_price=Decimal('100.00'),
            sale_price=Decimal('150.00'),
            created_by=self.user
        )
        
        self.product2 = Product.objects.create(
            name='منتج اختبار 2',
            code='TEST002',
            category=self.category,
            brand=self.brand,
            unit=self.unit,
            purchase_price=Decimal('200.00'),
            sale_price=Decimal('300.00'),
            created_by=self.user
        )
        
        # إنشاء عملية شراء
        self.purchase = Purchase.objects.create(
            date=timezone.now().date(),
            supplier=self.supplier,
            warehouse=self.warehouse,
            reference='PO-001',
            status='completed',
            created_by=self.user
        )
        
        # إنشاء عناصر الشراء
        self.purchase_item1 = PurchaseItem.objects.create(
            purchase=self.purchase,
            product=self.product1,
            quantity=5,
            price=Decimal('100.00'),
            created_by=self.user
        )
        
        self.purchase_item2 = PurchaseItem.objects.create(
            purchase=self.purchase,
            product=self.product2,
            quantity=3,
            price=Decimal('200.00'),
            created_by=self.user
        )
        
        # إنشاء مرتجع شراء
        self.purchase_return = PurchaseReturn.objects.create(
            date=timezone.now().date(),
            purchase=self.purchase,
            warehouse=self.warehouse,
            reference='PRET-001',
            notes='ملاحظات مرتجع للاختبار',
            created_by=self.user
        )
        
        # إنشاء عناصر مرتجع الشراء
        self.return_item1 = PurchaseReturnItem.objects.create(
            purchase_return=self.purchase_return,
            product=self.product1,
            quantity=2,
            price=Decimal('100.00'),
            reason='منتج تالف',
            created_by=self.user
        )
        
        self.return_item2 = PurchaseReturnItem.objects.create(
            purchase_return=self.purchase_return,
            product=self.product2,
            quantity=1,
            price=Decimal('200.00'),
            reason='منتج خاطئ',
            created_by=self.user
        )
    
    def test_purchase_return_creation(self):
        """
        اختبار إنشاء مرتجع شراء بالبيانات الصحيحة
        """
        self.assertEqual(self.purchase_return.purchase, self.purchase)
        self.assertEqual(self.purchase_return.warehouse, self.warehouse)
        self.assertEqual(self.purchase_return.reference, 'PRET-001')
        self.assertEqual(self.purchase_return.notes, 'ملاحظات مرتجع للاختبار')
        self.assertEqual(self.purchase_return.created_by, self.user)
        self.assertIsNotNone(self.purchase_return.created_at)
    
    def test_purchase_return_str(self):
        """
        اختبار النص التمثيلي لمرتجع الشراء
        """
        expected = f'PRET-001 - {self.purchase_return.date}'
        self.assertEqual(str(self.purchase_return), expected)
    
    def test_purchase_return_total_calculation(self):
        """
        اختبار حساب إجمالي مرتجع الشراء
        """
        # حساب الإجمالي يدوياً
        # (2 * 100) + (1 * 200) = 200 + 200 = 400
        expected_total = Decimal('400.00')
        self.assertEqual(self.purchase_return.total, expected_total)
    
    def test_purchase_return_item_subtotal_calculation(self):
        """
        اختبار حساب المجموع الفرعي لعنصر مرتجع الشراء
        """
        # عنصر المرتجع 1: 2 * 100 = 200
        self.assertEqual(self.return_item1.subtotal, Decimal('200.00'))
        
        # عنصر المرتجع 2: 1 * 200 = 200
        self.assertEqual(self.return_item2.subtotal, Decimal('200.00'))
    
    def test_purchase_return_items_count(self):
        """
        اختبار عدد عناصر مرتجع الشراء
        """
        self.assertEqual(self.purchase_return.items.count(), 2) 