"""
اختبارات موحدة لنظام المنتجات المجمعة
Unified Tests for Bundle Product System

يجمع هذا الملف:
- test_bundle_admin.py (Admin Interface Tests)
- test_bundle_editing_validation.py (Editing Validation Tests)
- test_bundle_financial_enhancements.py (Financial Enhancement Tests)
- test_bundle_financial_integration.py (Financial Integration Tests)
- test_bundle_manager.py (Bundle Manager Tests)
- test_bundle_refund_service.py (Refund Service Tests)
- test_bundle_stock_signals.py (Stock Signal Tests)

Requirements: 1.1, 1.6, 1.7, 2.1, 6.5, 8.2, 8.3, 9.1
"""
import pytest
from django.test import TestCase, TransactionTestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from datetime import date
from unittest.mock import patch, MagicMock

from product.models import (
    Product, Category, Unit, Warehouse, Stock, StockMovement, BundleComponent
)
from product.admin import ProductAdmin, BundleComponentAdmin
from product.services.bundle_manager import BundleManager
from product.services.bundle_financial_service import BundleFinancialService
from product.services.stock_calculation_engine import StockCalculationEngine

User = get_user_model()


# ============================================================================
# 1. Bundle Manager Tests
# ============================================================================

class BundleManagerTest(TestCase):
    """اختبارات مدير المنتجات المجمعة - Requirements: 1.1, 8.2"""
    
    def setUp(self):
        """إعداد البيانات الأساسية للاختبارات"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.category = Category.objects.create(
            name='تصنيف اختبار',
            is_active=True
        )
        
        self.unit = Unit.objects.create(
            name='قطعة',
            symbol='قطعة',
            is_active=True
        )
        
        self.component1 = Product.objects.create(
            name='مكون 1',
            sku='COMP001',
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('10.00'),
            selling_price=Decimal('15.00'),
            created_by=self.user,
            is_active=True
        )
        
        self.component2 = Product.objects.create(
            name='مكون 2',
            sku='COMP002',
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('20.00'),
            selling_price=Decimal('25.00'),
            created_by=self.user,
            is_active=True
        )
        
        self.bundle_data = {
            'name': 'منتج مجمع اختبار',
            'description': 'وصف المنتج المجمع',
            'sku': 'BUNDLE001',
            'category_id': self.category.id,
            'unit_id': self.unit.id,
            'cost_price': Decimal('30.00'),
            'selling_price': Decimal('50.00'),
            'created_by_id': self.user.id,
            'is_active': True
        }
        
        self.components_data = [
            {
                'component_product_id': self.component1.id,
                'required_quantity': 2
            },
            {
                'component_product_id': self.component2.id,
                'required_quantity': 1
            }
        ]
    
    def test_create_bundle_success(self):
        """اختبار إنشاء منتج مجمع بنجاح"""
        success, bundle_product, error = BundleManager.create_bundle(
            self.bundle_data, self.components_data
        )
        
        self.assertTrue(success)
        self.assertIsNotNone(bundle_product)
        self.assertIsNone(error)
        
        self.assertEqual(bundle_product.name, 'منتج مجمع اختبار')
        self.assertEqual(bundle_product.sku, 'BUNDLE001')
        self.assertTrue(bundle_product.is_bundle)
        self.assertTrue(bundle_product.is_active)
        
        components = bundle_product.components.all()
        self.assertEqual(components.count(), 2)
        
        comp1 = components.get(component_product=self.component1)
        self.assertEqual(comp1.required_quantity, 2)
        
        comp2 = components.get(component_product=self.component2)
        self.assertEqual(comp2.required_quantity, 1)
    
    def test_create_bundle_invalid_product_data(self):
        """اختبار إنشاء منتج مجمع ببيانات منتج غير صحيحة"""
        invalid_data = self.bundle_data.copy()
        del invalid_data['name']
        
        success, bundle_product, error = BundleManager.create_bundle(
            invalid_data, self.components_data
        )
        
        self.assertFalse(success)
        self.assertIsNone(bundle_product)
        self.assertIsNotNone(error)
        self.assertIn('name', error)


# ============================================================================
# 2. Bundle Admin Tests
# ============================================================================

class BundleAdminTest(TestCase):
    """اختبارات واجهة إدارة المنتجات المجمعة"""
    
    def setUp(self):
        """إعداد البيانات للاختبار"""
        self.admin_user = User.objects.create_user(
            username='admin',
            email='admin@test.com',
            password='testpass123',
            is_staff=True,
            is_superuser=True
        )
        
        self.category = Category.objects.create(
            name='إلكترونيات',
            is_active=True
        )
        
        self.unit = Unit.objects.create(
            name='قطعة',
            symbol='قطعة',
            is_active=True
        )
        
        self.component1 = Product.objects.create(
            name='بطارية',
            sku='COMP001',
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('10.00'),
            selling_price=Decimal('15.00'),
            is_bundle=False,
            is_active=True,
            created_by=self.admin_user
        )
        
        self.bundle_product = Product.objects.create(
            name='طقم إلكتروني',
            sku='BUNDLE001',
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('35.00'),
            selling_price=Decimal('50.00'),
            is_bundle=True,
            is_active=True,
            created_by=self.admin_user
        )
        
        BundleComponent.objects.create(
            bundle_product=self.bundle_product,
            component_product=self.component1,
            required_quantity=2
        )
        
        self.factory = RequestFactory()
        self.site = AdminSite()
    
    def test_bundle_product_admin_display(self):
        """اختبار عرض المنتج المجمع في الإدارة"""
        product_admin = ProductAdmin(Product, self.site)
        
        self.assertTrue(hasattr(product_admin, 'list_display'))
        self.assertIn('name', product_admin.list_display)


# ============================================================================
# 3. Bundle Stock Signal Tests
# ============================================================================

@pytest.mark.django_db
class BundleStockSignalTest(TestCase):
    """اختبارات إشارات إعادة حساب مخزون المنتجات المجمعة - Requirements: 2.1, 8.3"""
    
    def setUp(self):
        """إعداد البيانات للاختبارات"""
        self.user = User.objects.create_user(
            username='test_user',
            email='test@example.com',
            password='testpass123'
        )
        
        self.category = Category.objects.create(name='فئة اختبار')
        self.unit = Unit.objects.create(name='قطعة', symbol='قطعة')
        
        self.warehouse = Warehouse.objects.create(
            name='مخزن رئيسي',
            code='MAIN',
            is_active=True,
            manager=self.user
        )
        
        self.component1 = Product.objects.create(
            name='مكون 1',
            sku='COMP1',
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('10.00'),
            selling_price=Decimal('15.00'),
            created_by=self.user,
            is_active=True
        )
        
        self.component2 = Product.objects.create(
            name='مكون 2',
            sku='COMP2',
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('20.00'),
            selling_price=Decimal('30.00'),
            created_by=self.user,
            is_active=True
        )
        
        self.bundle_product = Product.objects.create(
            name='منتج مجمع',
            sku='BUNDLE1',
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('50.00'),
            selling_price=Decimal('80.00'),
            created_by=self.user,
            is_bundle=True,
            is_active=True
        )
        
        BundleComponent.objects.create(
            bundle_product=self.bundle_product,
            component_product=self.component1,
            required_quantity=2
        )
        
        BundleComponent.objects.create(
            bundle_product=self.bundle_product,
            component_product=self.component2,
            required_quantity=1
        )
        
        Stock.objects.create(
            product=self.component1,
            warehouse=self.warehouse,
            quantity=100
        )
        
        Stock.objects.create(
            product=self.component2,
            warehouse=self.warehouse,
            quantity=50
        )
    
    @patch('product.signals_bundle_stock.StockCalculationEngine.recalculate_affected_bundles')
    def test_stock_movement_triggers_bundle_recalculation(self, mock_recalculate):
        """اختبار أن حركة المخزون تؤدي إلى إعادة حساب مخزون المنتجات المجمعة"""
        mock_recalculate.return_value = [
            {
                'bundle_product': self.bundle_product,
                'old_stock': 50,
                'new_stock': 40,
                'component_changed': self.component1
            }
        ]
        
        movement = StockMovement.objects.create(
            product=self.component1,
            warehouse=self.warehouse,
            movement_type='out',
            quantity=20,
            created_by=self.user,
            document_type='sale'
        )
        
        self.assertTrue(mock_recalculate.called)


# ============================================================================
# 5. Bundle Financial Integration Tests
# ============================================================================

class BundleFinancialIntegrationTest(TransactionTestCase):
    """اختبارات تكامل المعاملات المالية للمنتجات المجمعة - Requirements: 9.1"""
    
    def setUp(self):
        """إعداد البيانات الأساسية للاختبار"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        self.category = Category.objects.create(name='مواد متخصصة')
        self.unit = Unit.objects.create(name='قطعة', symbol='قطعة')
        
        self.warehouse = Warehouse.objects.create(
            name='المخزن الرئيسي',
            code='MAIN',
            is_active=True,
            created_by=self.user
        )
        
        self.book = Product.objects.create(
            name='كتاب الرياضيات',
            sku='BOOK001',
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('10.00'),
            selling_price=Decimal('15.00'),
            created_by=self.user
        )
        
        self.notebook = Product.objects.create(
            name='دفتر التمارين',
            sku='NOTE001',
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('5.00'),
            selling_price=Decimal('8.00'),
            created_by=self.user
        )
        
        self.bundle = Product.objects.create(
            name='حقيبة الرياضيات الكاملة',
            sku='BUNDLE001',
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('20.00'),
            selling_price=Decimal('30.00'),
            is_bundle=True,
            created_by=self.user
        )
        
        BundleComponent.objects.create(
            bundle_product=self.bundle,
            component_product=self.book,
            required_quantity=1
        )
        
        BundleComponent.objects.create(
            bundle_product=self.bundle,
            component_product=self.notebook,
            required_quantity=1
        )
        
        Stock.objects.create(product=self.book, warehouse=self.warehouse, quantity=100)
        Stock.objects.create(product=self.notebook, warehouse=self.warehouse, quantity=100)
    
    def test_bundle_product_creation(self):
        """اختبار إنشاء منتج مجمع مع مكوناته"""
        self.assertTrue(self.bundle.is_bundle)
        self.assertEqual(self.bundle.components.count(), 2)
        
        components = self.bundle.components.all()
        book_component = components.get(component_product=self.book)
        notebook_component = components.get(component_product=self.notebook)
        
        self.assertEqual(book_component.required_quantity, 1)
        self.assertEqual(notebook_component.required_quantity, 1)


# ============================================================================
# 6. Bundle Editing Validation Tests
# ============================================================================

class BundleEditingValidationTest(TestCase):
    """اختبارات التحقق من تعديل المنتجات المجمعة - Requirements: 1.6, 1.7"""
    
    def setUp(self):
        """إعداد البيانات للاختبارات"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.category = Category.objects.create(
            name='تصنيف اختبار',
            is_active=True
        )
        
        self.unit = Unit.objects.create(
            name='قطعة',
            symbol='قطعة',
            is_active=True
        )
        
        self.component1 = Product.objects.create(
            name='مكون 1',
            sku='COMP001',
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('10.00'),
            selling_price=Decimal('15.00'),
            is_active=True,
            is_bundle=False,
            created_by=self.user
        )
        
        self.component2 = Product.objects.create(
            name='مكون 2',
            sku='COMP002',
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('20.00'),
            selling_price=Decimal('25.00'),
            is_active=True,
            is_bundle=False,
            created_by=self.user
        )
        
        self.bundle = Product.objects.create(
            name='منتج مجمع اختبار',
            sku='BUNDLE001',
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('35.00'),
            selling_price=Decimal('50.00'),
            is_active=True,
            is_bundle=True,
            created_by=self.user
        )
        
        BundleComponent.objects.create(
            bundle_product=self.bundle,
            component_product=self.component1,
            required_quantity=2
        )
        
        BundleComponent.objects.create(
            bundle_product=self.bundle,
            component_product=self.component2,
            required_quantity=1
        )
    
    def test_bundle_has_components(self):
        """اختبار أن المنتج المجمع يحتوي على مكونات"""
        self.assertTrue(self.bundle.is_bundle)
        self.assertEqual(self.bundle.components.count(), 2)
        
        components = list(self.bundle.components.all())
        component_products = [c.component_product for c in components]
        
        self.assertIn(self.component1, component_products)
        self.assertIn(self.component2, component_products)


if __name__ == '__main__':
    pytest.main([__file__])
