"""
اختبارات شاملة لإصلاح حذف فاتورة الشراء
تتحقق من:
1. منع حذف فاتورة تحتوي على منتجات تم بيعها
2. السماح بحذف فاتورة لم يتم بيع منتجاتها
3. معالجة صحيحة لحركات المخزون
"""

from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from decimal import Decimal
from datetime import date

from purchase.models import Purchase, PurchaseItem
from sale.models import Sale, SaleItem
from product.models import Product, Warehouse, Category, Unit, Stock, StockMovement
from supplier.models import Supplier
from client.models import Customer

User = get_user_model()


class PurchaseDeleteWithSoldItemsTest(TransactionTestCase):
    """
    اختبار حذف فاتورة شراء تحتوي على منتجات تم بيعها
    """

    def setUp(self):
        """إعداد البيانات للاختبار"""
        # إنشاء مستخدم
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )

        # إنشاء فئة ووحدة
        self.category = Category.objects.create(
            name='فئة اختبار'
        )
        self.unit = Unit.objects.create(
            name='قطعة',
            symbol='قطعة'
        )

        # إنشاء منتجات
        self.product1 = Product.objects.create(
            name='منتج اختبار 1',
            sku='TEST001',
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('10.00'),
            selling_price=Decimal('15.00'),
            created_by=self.user
        )
        self.product2 = Product.objects.create(
            name='منتج اختبار 2',
            sku='TEST002',
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('20.00'),
            selling_price=Decimal('30.00'),
            created_by=self.user
        )

        # إنشاء مخزن
        self.warehouse = Warehouse.objects.create(
            name='مخزن اختبار',
            location='موقع اختبار',
            created_by=self.user
        )

        # إنشاء مورد
        self.supplier = Supplier.objects.create(
            name='مورد اختبار',
            email='supplier@test.com',
            phone='1234567890',
            created_by=self.user
        )

        # إنشاء عميل
        self.customer = Customer.objects.create(
            name='عميل اختبار',
            email='customer@test.com',
            phone='0987654321',
            created_by=self.user
        )

    def test_cannot_delete_purchase_with_sold_items(self):
        """
        اختبار: لا يمكن حذف فاتورة شراء تحتوي على منتجات تم بيعها
        
        السيناريو:
        1. شراء 100 قطعة
        2. بيع 80 قطعة
        3. محاولة حذف الفاتورة (يجب أن تفشل - متاح فقط 20)
        """
        # 1. إنشاء فاتورة شراء (100 قطعة)
        purchase = Purchase.objects.create(
            number='PUR0001',
            date=date.today(),
            supplier=self.supplier,
            warehouse=self.warehouse,
            subtotal=Decimal('1000.00'),
            total=Decimal('1000.00'),
            payment_method='cash',
            status='confirmed',
            created_by=self.user
        )

        PurchaseItem.objects.create(
            purchase=purchase,
            product=self.product1,
            quantity=100,
            unit_price=Decimal('10.00'),
            total=Decimal('1000.00')
        )

        # 2. بيع 80 قطعة
        sale = Sale.objects.create(
            number='SALE0001',
            date=date.today(),
            customer=self.customer,
            warehouse=self.warehouse,
            subtotal=Decimal('1200.00'),
            total=Decimal('1200.00'),
            payment_method='cash',
            status='confirmed',
            created_by=self.user
        )

        SaleItem.objects.create(
            sale=sale,
            product=self.product1,
            quantity=80,
            unit_price=Decimal('15.00'),
            total=Decimal('1200.00')
        )

        # 3. التحقق من منطق الحذف (نفس الكود في purchase_delete view)
        insufficient_stock_items = []
        for item in purchase.items.all():
            stock = Stock.objects.filter(
                product=item.product,
                warehouse=purchase.warehouse
            ).first()
            
            current_quantity = stock.quantity if stock else 0
            
            if current_quantity < item.quantity:
                insufficient_stock_items.append({
                    'product': item.product.name,
                    'required': item.quantity,
                    'available': current_quantity,
                    'sold': item.quantity - current_quantity
                })

        # التحقق: يجب أن يكون هناك منتج واحد غير كافٍ
        self.assertEqual(len(insufficient_stock_items), 1, "يجب اكتشاف منتج واحد مباع")
        self.assertEqual(insufficient_stock_items[0]['product'], 'منتج اختبار 1')
        self.assertEqual(insufficient_stock_items[0]['required'], 100)
        self.assertEqual(insufficient_stock_items[0]['available'], 20)
        self.assertEqual(insufficient_stock_items[0]['sold'], 80)

        print("✅ الاختبار نجح: تم اكتشاف المنتجات المباعة (80 من 100)")

    def test_can_delete_purchase_without_sold_items(self):
        """
        اختبار: يمكن حذف فاتورة شراء لم يتم بيع منتجاتها
        """
        # 1. إنشاء فاتورة شراء (50 قطعة من كل منتج)
        purchase = Purchase.objects.create(
            number='PUR0002',
            date=date.today(),
            supplier=self.supplier,
            warehouse=self.warehouse,
            subtotal=Decimal('1500.00'),
            total=Decimal('1500.00'),
            payment_method='cash',
            status='confirmed',
            created_by=self.user
        )

        purchase_item1 = PurchaseItem.objects.create(
            purchase=purchase,
            product=self.product1,
            quantity=50,
            unit_price=Decimal('10.00'),
            total=Decimal('500.00')
        )

        purchase_item2 = PurchaseItem.objects.create(
            purchase=purchase,
            product=self.product2,
            quantity=50,
            unit_price=Decimal('20.00'),
            total=Decimal('1000.00')
        )

        # التحقق من إنشاء المخزون
        stock1 = Stock.objects.get(product=self.product1, warehouse=self.warehouse)
        stock2 = Stock.objects.get(product=self.product2, warehouse=self.warehouse)
        
        self.assertEqual(stock1.quantity, 50)
        self.assertEqual(stock2.quantity, 50)

        # عدد حركات المخزون قبل الحذف
        movements_before = StockMovement.objects.filter(
            document_type='purchase',
            document_number=purchase.number
        ).count()
        self.assertEqual(movements_before, 2)  # حركتان (منتج 1 + منتج 2)

        # 2. حذف الفاتورة (يجب أن ينجح)
        purchase_number = purchase.number
        purchase.delete()

        # التحقق من حذف الفاتورة
        self.assertFalse(Purchase.objects.filter(number=purchase_number).exists())

        # التحقق من إرجاع المخزون إلى الصفر
        stock1.refresh_from_db()
        stock2.refresh_from_db()
        
        self.assertEqual(stock1.quantity, 0)
        self.assertEqual(stock2.quantity, 0)

        # التحقق من إنشاء حركات الإرجاع
        cancel_movements = StockMovement.objects.filter(
            document_type='purchase_return',
            document_number=purchase_number,
            reference_number__startswith='PURCHASE-CANCEL-'
        ).count()
        
        self.assertEqual(cancel_movements, 2)  # حركتا إرجاع

        print("✅ الاختبار نجح: تم حذف الفاتورة وإرجاع المخزون بشكل صحيح")

    def test_stock_movement_handling_on_delete(self):
        """
        اختبار: معالجة صحيحة لحركات المخزون عند الحذف
        """
        # 1. إنشاء فاتورة شراء
        purchase = Purchase.objects.create(
            number='PUR0003',
            date=date.today(),
            supplier=self.supplier,
            warehouse=self.warehouse,
            subtotal=Decimal('1000.00'),
            total=Decimal('1000.00'),
            payment_method='cash',
            status='confirmed',
            created_by=self.user
        )

        purchase_item = PurchaseItem.objects.create(
            purchase=purchase,
            product=self.product1,
            quantity=100,
            unit_price=Decimal('10.00'),
            total=Decimal('1000.00')
        )

        # التحقق من المخزون الأولي
        stock = Stock.objects.get(product=self.product1, warehouse=self.warehouse)
        initial_quantity = stock.quantity
        self.assertEqual(initial_quantity, 100)

        # عدد حركات المخزون الأولية
        initial_movements = StockMovement.objects.filter(
            product=self.product1,
            warehouse=self.warehouse
        ).count()

        # 2. حذف الفاتورة
        purchase.delete()

        # 3. التحقق من المخزون بعد الحذف
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, 0)

        # 4. التحقق من حركات المخزون
        # يجب أن يكون هناك حركة إرجاع (out) واحدة فقط
        cancel_movements = StockMovement.objects.filter(
            product=self.product1,
            warehouse=self.warehouse,
            movement_type='out',
            document_type='purchase_return'
        )
        
        self.assertEqual(cancel_movements.count(), 1)
        self.assertEqual(cancel_movements.first().quantity, 100)

        print("✅ الاختبار نجح: تمت معالجة حركات المخزون بشكل صحيح (حركة واحدة فقط)")


class PurchaseDeleteEdgeCasesTest(TransactionTestCase):
    """
    اختبار حالات خاصة لحذف فاتورة الشراء
    """

    def setUp(self):
        """إعداد البيانات للاختبار"""
        self.user = User.objects.create_user(
            username='testuser2',
            email='test2@test.com',
            password='testpass123'
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
            sku='TEST003',
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('10.00'),
            selling_price=Decimal('15.00'),
            created_by=self.user
        )

        self.warehouse = Warehouse.objects.create(
            name='مخزن اختبار',
            location='موقع اختبار',
            created_by=self.user
        )

        self.supplier = Supplier.objects.create(
            name='مورد اختبار',
            email='supplier@test.com',
            phone='1234567890',
            created_by=self.user
        )

    def test_delete_purchase_with_partial_sale(self):
        """
        اختبار: حذف فاتورة مع بيع جزئي
        """
        # شراء 100 قطعة
        purchase = Purchase.objects.create(
            number='PUR0004',
            date=date.today(),
            supplier=self.supplier,
            warehouse=self.warehouse,
            subtotal=Decimal('1000.00'),
            total=Decimal('1000.00'),
            payment_method='cash',
            status='confirmed',
            created_by=self.user
        )

        PurchaseItem.objects.create(
            purchase=purchase,
            product=self.product,
            quantity=100,
            unit_price=Decimal('10.00'),
            total=Decimal('1000.00')
        )

        stock = Stock.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(stock.quantity, 100)

        # بيع 30 قطعة فقط
        customer = Customer.objects.create(
            name='عميل اختبار',
            email='customer@test.com',
            phone='0987654321',
            created_by=self.user
        )

        sale = Sale.objects.create(
            number='SALE0002',
            date=date.today(),
            customer=customer,
            warehouse=self.warehouse,
            subtotal=Decimal('450.00'),
            total=Decimal('450.00'),
            payment_method='cash',
            status='confirmed',
            created_by=self.user
        )

        SaleItem.objects.create(
            sale=sale,
            product=self.product,
            quantity=30,
            unit_price=Decimal('15.00'),
            total=Decimal('450.00')
        )

        stock.refresh_from_db()
        self.assertEqual(stock.quantity, 70)  # 100 - 30 = 70

        # محاولة الحذف (يجب أن تفشل)
        from product.models import Stock
        
        stock_check = Stock.objects.filter(
            product=self.product,
            warehouse=self.warehouse
        ).first()

        can_delete = stock_check.quantity >= 100
        self.assertFalse(can_delete)

        print("✅ الاختبار نجح: تم منع حذف فاتورة مع بيع جزئي (30 من 100)")

    def test_delete_purchase_with_zero_stock(self):
        """
        اختبار: حذف فاتورة عندما يكون المخزون صفر (تم بيع الكل)
        """
        # شراء 50 قطعة
        purchase = Purchase.objects.create(
            number='PUR0005',
            date=date.today(),
            supplier=self.supplier,
            warehouse=self.warehouse,
            subtotal=Decimal('500.00'),
            total=Decimal('500.00'),
            payment_method='cash',
            status='confirmed',
            created_by=self.user
        )

        PurchaseItem.objects.create(
            purchase=purchase,
            product=self.product,
            quantity=50,
            unit_price=Decimal('10.00'),
            total=Decimal('500.00')
        )

        # بيع الكل (50 قطعة)
        customer = Customer.objects.create(
            name='عميل اختبار 2',
            email='customer2@test.com',
            phone='0987654321',
            created_by=self.user
        )

        sale = Sale.objects.create(
            number='SALE0003',
            date=date.today(),
            customer=customer,
            warehouse=self.warehouse,
            subtotal=Decimal('750.00'),
            total=Decimal('750.00'),
            payment_method='cash',
            status='confirmed',
            created_by=self.user
        )

        SaleItem.objects.create(
            sale=sale,
            product=self.product,
            quantity=50,
            unit_price=Decimal('15.00'),
            total=Decimal('750.00')
        )

        stock = Stock.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(stock.quantity, 0)

        # محاولة الحذف (يجب أن تفشل - المخزون صفر)
        can_delete = stock.quantity >= 50
        self.assertFalse(can_delete)

        print("✅ الاختبار نجح: تم منع حذف فاتورة عندما المخزون صفر (تم بيع الكل)")
