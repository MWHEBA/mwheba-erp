from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from product.models import Product, Category, Brand, Unit, Warehouse, Stock
from product.api.serializers import (
    ProductSerializer, CategorySerializer, BrandSerializer,
    UnitSerializer, WarehouseSerializer, StockSerializer
)
from decimal import Decimal

User = get_user_model()

class ProductSerializersTestCase(APITestCase):
    """
    اختبارات متسلسلات API تطبيق المنتجات
    """
    def setUp(self):
        """
        إعداد البيانات المطلوبة للاختبارات
        """
        # إنشاء مستخدم للاختبارات
        self.user = User.objects.create_user(
            username='serializer_user',
            email='serializer@example.com',
            password='serializer123'
        )
        
        # إنشاء بيانات الاختبار
        self.category = Category.objects.create(
            name='فئة المتسلسلات',
            description='وصف فئة المتسلسلات',
            created_by=self.user
        )
        
        self.brand = Brand.objects.create(
            name='علامة تجارية للمتسلسلات',
            description='وصف علامة تجارية للمتسلسلات',
            created_by=self.user
        )
        
        self.unit = Unit.objects.create(
            name='وحدة المتسلسلات',
            abbreviation='و.م',
            created_by=self.user
        )
        
        self.product = Product.objects.create(
            name='منتج المتسلسلات',
            code='SER001',
            description='وصف منتج المتسلسلات',
            category=self.category,
            brand=self.brand,
            unit=self.unit,
            purchase_price=Decimal('100.00'),
            sale_price=Decimal('150.00'),
            created_by=self.user
        )
        
        self.warehouse = Warehouse.objects.create(
            name='مستودع المتسلسلات',
            code='SER-WH',
            location='موقع مستودع المتسلسلات',
            created_by=self.user
        )
        
        self.stock = Stock.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=50,
            created_by=self.user
        )
    
    def test_product_serializer(self):
        """
        اختبار متسلسل المنتج
        """
        serializer = ProductSerializer(self.product)
        data = serializer.data
        
        # التحقق من البيانات المتسلسلة
        self.assertEqual(data['name'], 'منتج المتسلسلات')
        self.assertEqual(data['code'], 'SER001')
        self.assertEqual(data['description'], 'وصف منتج المتسلسلات')
        self.assertEqual(Decimal(str(data['purchase_price'])), Decimal('100.00'))
        self.assertEqual(Decimal(str(data['sale_price'])), Decimal('150.00'))
        
        # التحقق من العلاقات
        self.assertEqual(data['category'], self.category.id)
        self.assertEqual(data['brand'], self.brand.id)
        self.assertEqual(data['unit'], self.unit.id)
    
    def test_product_serializer_validation(self):
        """
        اختبار التحقق من صحة متسلسل المنتج
        """
        # بيانات غير صالحة - سعر بيع أقل من سعر الشراء
        invalid_data = {
            'name': 'منتج اختبار التحقق',
            'code': 'VAL001',
            'category': self.category.id,
            'unit': self.unit.id,
            'purchase_price': '200.00',
            'sale_price': '150.00'  # سعر بيع أقل من سعر الشراء
        }
        
        serializer = ProductSerializer(data=invalid_data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('non_field_errors', serializer.errors)
        
        # بيانات صالحة
        valid_data = {
            'name': 'منتج اختبار التحقق',
            'code': 'VAL001',
            'category': self.category.id,
            'unit': self.unit.id,
            'purchase_price': '100.00',
            'sale_price': '150.00'
        }
        
        serializer = ProductSerializer(data=valid_data)
        self.assertTrue(serializer.is_valid())
    
    def test_product_serializer_create(self):
        """
        اختبار إنشاء منتج باستخدام المتسلسل
        """
        product_data = {
            'name': 'منتج متسلسل جديد',
            'code': 'SER002',
            'description': 'وصف منتج متسلسل جديد',
            'category': self.category.id,
            'brand': self.brand.id,
            'unit': self.unit.id,
            'purchase_price': '120.00',
            'sale_price': '180.00'
        }
        
        serializer = ProductSerializer(data=product_data)
        self.assertTrue(serializer.is_valid())
        
        # إنشاء المنتج
        product = serializer.save(created_by=self.user)
        
        # التحقق من البيانات المحفوظة
        self.assertEqual(product.name, 'منتج متسلسل جديد')
        self.assertEqual(product.code, 'SER002')
        self.assertEqual(product.purchase_price, Decimal('120.00'))
        self.assertEqual(product.sale_price, Decimal('180.00'))
        self.assertEqual(product.created_by, self.user)
    
    def test_product_serializer_update(self):
        """
        اختبار تحديث منتج باستخدام المتسلسل
        """
        update_data = {
            'name': 'منتج متسلسل محدث',
            'description': 'وصف محدث',
            'sale_price': '200.00'
        }
        
        serializer = ProductSerializer(self.product, data=update_data, partial=True)
        self.assertTrue(serializer.is_valid())
        
        # تحديث المنتج
        updated_product = serializer.save()
        
        # التحقق من البيانات المحدثة
        self.assertEqual(updated_product.name, 'منتج متسلسل محدث')
        self.assertEqual(updated_product.description, 'وصف محدث')
        self.assertEqual(updated_product.sale_price, Decimal('200.00'))
        
        # التحقق من عدم تغيير البيانات الأخرى
        self.assertEqual(updated_product.code, 'SER001')
        self.assertEqual(updated_product.purchase_price, Decimal('100.00'))
    
    def test_category_serializer(self):
        """
        اختبار متسلسل التصنيف
        """
        serializer = CategorySerializer(self.category)
        data = serializer.data
        
        # التحقق من البيانات المتسلسلة
        self.assertEqual(data['name'], 'فئة المتسلسلات')
        self.assertEqual(data['description'], 'وصف فئة المتسلسلات')
        
        # إنشاء فئة فرعية
        child_category = Category.objects.create(
            name='فئة فرعية للمتسلسلات',
            description='وصف التصنيف الفرعية',
            parent=self.category,
            created_by=self.user
        )
        
        # اختبار متسلسل التصنيف الفرعية
        child_serializer = CategorySerializer(child_category)
        child_data = child_serializer.data
        
        self.assertEqual(child_data['name'], 'فئة فرعية للمتسلسلات')
        self.assertEqual(child_data['parent'], self.category.id)
        
        # اختبار إنشاء فئة جديدة
        category_data = {
            'name': 'فئة متسلسل جديدة',
            'description': 'وصف فئة متسلسل جديدة',
            'parent': self.category.id
        }
        
        serializer = CategorySerializer(data=category_data)
        self.assertTrue(serializer.is_valid())
        
        new_category = serializer.save(created_by=self.user)
        self.assertEqual(new_category.name, 'فئة متسلسل جديدة')
        self.assertEqual(new_category.parent, self.category)
    
    def test_brand_serializer(self):
        """
        اختبار متسلسل النوع
        """
        serializer = BrandSerializer(self.brand)
        data = serializer.data
        
        # التحقق من البيانات المتسلسلة
        self.assertEqual(data['name'], 'علامة تجارية للمتسلسلات')
        self.assertEqual(data['description'], 'وصف علامة تجارية للمتسلسلات')
        
        # اختبار إنشاء علامة تجارية جديدة
        brand_data = {
            'name': 'علامة تجارية جديدة',
            'description': 'وصف علامة تجارية جديدة'
        }
        
        serializer = BrandSerializer(data=brand_data)
        self.assertTrue(serializer.is_valid())
        
        new_brand = serializer.save(created_by=self.user)
        self.assertEqual(new_brand.name, 'علامة تجارية جديدة')
    
    def test_unit_serializer(self):
        """
        اختبار متسلسل الوحدة
        """
        serializer = UnitSerializer(self.unit)
        data = serializer.data
        
        # التحقق من البيانات المتسلسلة
        self.assertEqual(data['name'], 'وحدة المتسلسلات')
        self.assertEqual(data['abbreviation'], 'و.م')
        
        # اختبار إنشاء وحدة جديدة
        unit_data = {
            'name': 'كيلوجرام',
            'abbreviation': 'كجم'
        }
        
        serializer = UnitSerializer(data=unit_data)
        self.assertTrue(serializer.is_valid())
        
        new_unit = serializer.save(created_by=self.user)
        self.assertEqual(new_unit.name, 'كيلوجرام')
        self.assertEqual(new_unit.abbreviation, 'كجم')
    
    def test_warehouse_serializer(self):
        """
        اختبار متسلسل المستودع
        """
        serializer = WarehouseSerializer(self.warehouse)
        data = serializer.data
        
        # التحقق من البيانات المتسلسلة
        self.assertEqual(data['name'], 'مستودع المتسلسلات')
        self.assertEqual(data['code'], 'SER-WH')
        self.assertEqual(data['location'], 'موقع مستودع المتسلسلات')
        
        # اختبار إنشاء مستودع جديد
        warehouse_data = {
            'name': 'مستودع جديد',
            'code': 'NEW-WH',
            'location': 'موقع المستودع الجديد'
        }
        
        serializer = WarehouseSerializer(data=warehouse_data)
        self.assertTrue(serializer.is_valid())
        
        new_warehouse = serializer.save(created_by=self.user)
        self.assertEqual(new_warehouse.name, 'مستودع جديد')
        self.assertEqual(new_warehouse.code, 'NEW-WH')
    
    def test_stock_serializer(self):
        """
        اختبار متسلسل المخزون
        """
        serializer = StockSerializer(self.stock)
        data = serializer.data
        
        # التحقق من البيانات المتسلسلة
        self.assertEqual(data['product'], self.product.id)
        self.assertEqual(data['warehouse'], self.warehouse.id)
        self.assertEqual(data['quantity'], 50)
        
        # اختبار إنشاء مخزون جديد
        # أولاً، إنشاء منتج جديد للمخزون
        new_product = Product.objects.create(
            name='منتج مخزون جديد',
            code='STOCK001',
            category=self.category,
            unit=self.unit,
            purchase_price=Decimal('150.00'),
            sale_price=Decimal('200.00'),
            created_by=self.user
        )
        
        stock_data = {
            'product': new_product.id,
            'warehouse': self.warehouse.id,
            'quantity': 100
        }
        
        serializer = StockSerializer(data=stock_data)
        self.assertTrue(serializer.is_valid())
        
        new_stock = serializer.save(created_by=self.user)
        self.assertEqual(new_stock.product, new_product)
        self.assertEqual(new_stock.warehouse, self.warehouse)
        self.assertEqual(new_stock.quantity, 100)
        
        # اختبار تحديث كمية المخزون
        update_data = {
            'quantity': 75
        }
        
        serializer = StockSerializer(self.stock, data=update_data, partial=True)
        self.assertTrue(serializer.is_valid())
        
        updated_stock = serializer.save()
        self.assertEqual(updated_stock.quantity, 75) 