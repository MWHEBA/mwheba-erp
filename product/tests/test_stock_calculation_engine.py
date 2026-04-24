# -*- coding: utf-8 -*-
"""
اختبارات محرك حساب مخزون المنتجات المجمعة
Unit Tests for Stock Calculation Engine

Requirements: 2.2, 2.3, 2.4
"""

import pytest
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from product.models import Product, Category, Unit, Warehouse, Stock, BundleComponent
from product.services.stock_calculation_engine import StockCalculationEngine

User = get_user_model()


@pytest.mark.django_db
class TestStockCalculationEngine:
    """اختبارات محرك حساب مخزون المنتجات المجمعة"""

    @pytest.fixture(autouse=True)
    def setup_test_data(self, user, category, unit, warehouse):
        """إعداد بيانات الاختبار"""
        self.user = user
        self.category = category
        self.unit = unit
        self.warehouse = warehouse
        
        # إنشاء منتجات مكونة
        self.component1 = Product.objects.create(
            name="مكون 1",
            sku="COMP001",
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('10.00'),
            selling_price=Decimal('15.00'),
            is_active=True,
            created_by=self.user
        )
        
        self.component2 = Product.objects.create(
            name="مكون 2", 
            sku="COMP002",
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('20.00'),
            selling_price=Decimal('30.00'),
            is_active=True,
            created_by=self.user
        )
        
        self.component3 = Product.objects.create(
            name="مكون 3",
            sku="COMP003", 
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('5.00'),
            selling_price=Decimal('8.00'),
            is_active=True,
            created_by=self.user
        )
        
        # إنشاء منتج مجمع
        self.bundle_product = Product.objects.create(
            name="منتج مجمع",
            sku="BUNDLE001",
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('35.00'),
            selling_price=Decimal('60.00'),
            is_bundle=True,
            is_active=True,
            created_by=self.user
        )
        
        # إضافة مخزون للمكونات
        Stock.objects.create(product=self.component1, warehouse=self.warehouse, quantity=100)
        Stock.objects.create(product=self.component2, warehouse=self.warehouse, quantity=50)
        Stock.objects.create(product=self.component3, warehouse=self.warehouse, quantity=200)

    def test_calculate_bundle_stock_basic(self):
        """اختبار حساب مخزون المنتج المجمع - الحالة الأساسية"""
        # إنشاء مكونات المنتج المجمع
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
        BundleComponent.objects.create(
            bundle_product=self.bundle_product,
            component_product=self.component3,
            required_quantity=3
        )
        
        # حساب المخزون المتوقع:
        # المكون 1: 100 ÷ 2 = 50 وحدة مجمعة
        # المكون 2: 50 ÷ 1 = 50 وحدة مجمعة  
        # المكون 3: 200 ÷ 3 = 66 وحدة مجمعة
        # الحد الأدنى = 50
        
        calculated_stock = StockCalculationEngine.calculate_bundle_stock(self.bundle_product)
        assert calculated_stock == 50

    def test_calculate_bundle_stock_zero_component(self):
        """اختبار حساب مخزون المنتج المجمع عند وجود مكون بدون مخزون"""
        # إنشاء مكونات المنتج المجمع
        BundleComponent.objects.create(
            bundle_product=self.bundle_product,
            component_product=self.component1,
            required_quantity=1
        )
        BundleComponent.objects.create(
            bundle_product=self.bundle_product,
            component_product=self.component2,
            required_quantity=1
        )
        
        # إزالة مخزون المكون الثاني
        Stock.objects.filter(product=self.component2).update(quantity=0)
        
        calculated_stock = StockCalculationEngine.calculate_bundle_stock(self.bundle_product)
        assert calculated_stock == 0

    def test_calculate_bundle_stock_inactive_component(self):
        """اختبار حساب مخزون المنتج المجمع عند وجود مكون غير نشط"""
        # إنشاء مكونات المنتج المجمع
        BundleComponent.objects.create(
            bundle_product=self.bundle_product,
            component_product=self.component1,
            required_quantity=1
        )
        BundleComponent.objects.create(
            bundle_product=self.bundle_product,
            component_product=self.component2,
            required_quantity=1
        )
        
        # تعطيل المكون الثاني
        self.component2.is_active = False
        self.component2.save()
        
        calculated_stock = StockCalculationEngine.calculate_bundle_stock(self.bundle_product)
        assert calculated_stock == 0

    def test_calculate_bundle_stock_no_components(self):
        """اختبار حساب مخزون المنتج المجمع بدون مكونات"""
        calculated_stock = StockCalculationEngine.calculate_bundle_stock(self.bundle_product)
        assert calculated_stock == 0

    def test_calculate_bundle_stock_non_bundle_product(self):
        """اختبار حساب مخزون منتج عادي (ليس مجمع)"""
        calculated_stock = StockCalculationEngine.calculate_bundle_stock(self.component1)
        assert calculated_stock == 0

    def test_recalculate_affected_bundles(self):
        """اختبار إعادة حساب المنتجات المجمعة المتأثرة"""
        # إنشاء منتج مجمع آخر
        bundle2 = Product.objects.create(
            name="منتج مجمع 2",
            sku="BUNDLE002",
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('25.00'),
            selling_price=Decimal('40.00'),
            is_bundle=True,
            is_active=True,
            created_by=self.user
        )
        
        # إضافة مكونات للمنتجين المجمعين
        BundleComponent.objects.create(
            bundle_product=self.bundle_product,
            component_product=self.component1,
            required_quantity=2
        )
        BundleComponent.objects.create(
            bundle_product=bundle2,
            component_product=self.component1,
            required_quantity=3
        )
        
        # إعادة حساب المنتجات المتأثرة بتغيير المكون الأول
        results = StockCalculationEngine.recalculate_affected_bundles(self.component1)
        
        assert len(results) == 2
        assert any(r['bundle_product'].id == self.bundle_product.id for r in results)
        assert any(r['bundle_product'].id == bundle2.id for r in results)

    def test_bulk_recalculate_all_bundles(self):
        """اختبار إعادة الحساب الجماعي لجميع المنتجات المجمعة"""
        # إنشاء منتج مجمع آخر
        bundle2 = Product.objects.create(
            name="منتج مجمع 2",
            sku="BUNDLE002",
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('25.00'),
            selling_price=Decimal('40.00'),
            is_bundle=True,
            is_active=True,
            created_by=self.user
        )
        
        # إضافة مكونات
        BundleComponent.objects.create(
            bundle_product=self.bundle_product,
            component_product=self.component1,
            required_quantity=1
        )
        BundleComponent.objects.create(
            bundle_product=bundle2,
            component_product=self.component2,
            required_quantity=1
        )
        
        # إعادة الحساب الجماعي
        result = StockCalculationEngine.bulk_recalculate()
        
        assert result['success'] is True
        assert result['total_processed'] == 2
        assert len(result['results']) == 2
        assert len(result['errors']) == 0

    def test_bulk_recalculate_specific_bundles(self):
        """اختبار إعادة الحساب الجماعي لمنتجات مجمعة محددة"""
        # إنشاء منتج مجمع آخر
        bundle2 = Product.objects.create(
            name="منتج مجمع 2",
            sku="BUNDLE002",
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('25.00'),
            selling_price=Decimal('40.00'),
            is_bundle=True,
            is_active=True,
            created_by=self.user
        )
        
        # إضافة مكونات
        BundleComponent.objects.create(
            bundle_product=self.bundle_product,
            component_product=self.component1,
            required_quantity=1
        )
        BundleComponent.objects.create(
            bundle_product=bundle2,
            component_product=self.component2,
            required_quantity=1
        )
        
        # إعادة الحساب لمنتج واحد فقط
        result = StockCalculationEngine.bulk_recalculate([self.bundle_product.id])
        
        assert result['success'] is True
        assert result['total_processed'] == 1
        assert len(result['results']) == 1
        assert result['results'][0]['bundle_id'] == self.bundle_product.id

    def test_validate_bundle_availability_sufficient_stock(self):
        """اختبار التحقق من توفر المنتج المجمع - مخزون كافي"""
        # إنشاء مكونات المنتج المجمع
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
        
        # المخزون المتاح: min(100÷2, 50÷1) = min(50, 50) = 50
        # طلب 30 وحدة (أقل من المتاح)
        is_available, message = StockCalculationEngine.validate_bundle_availability(
            self.bundle_product, 30
        )
        
        assert is_available is True
        assert "متوفرة" in message

    def test_validate_bundle_availability_insufficient_stock(self):
        """اختبار التحقق من توفر المنتج المجمع - مخزون غير كافي"""
        # إنشاء مكونات المنتج المجمع
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
        
        # المخزون المتاح: min(100÷2, 50÷1) = min(50, 50) = 50
        # طلب 60 وحدة (أكثر من المتاح)
        is_available, message = StockCalculationEngine.validate_bundle_availability(
            self.bundle_product, 60
        )
        
        assert is_available is False
        assert "مخزون غير كافي" in message or "المخزون المتاح" in message

    def test_validate_bundle_availability_zero_quantity(self):
        """اختبار التحقق من توفر المنتج المجمع - كمية صفر"""
        is_available, message = StockCalculationEngine.validate_bundle_availability(
            self.bundle_product, 0
        )
        
        assert is_available is False
        assert "أكبر من صفر" in message

    def test_validate_bundle_availability_non_bundle(self):
        """اختبار التحقق من توفر منتج عادي (ليس مجمع)"""
        is_available, message = StockCalculationEngine.validate_bundle_availability(
            self.component1, 10
        )
        
        assert is_available is False
        assert "ليس منتجاً مجمعاً" in message

    def test_get_bundle_stock_breakdown(self):
        """اختبار الحصول على تفصيل مخزون المنتج المجمع"""
        # إنشاء مكونات المنتج المجمع
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
        BundleComponent.objects.create(
            bundle_product=self.bundle_product,
            component_product=self.component3,
            required_quantity=4
        )
        
        breakdown = StockCalculationEngine.get_bundle_stock_breakdown(self.bundle_product)
        
        assert 'error' not in breakdown
        assert breakdown['bundle_name'] == "منتج مجمع"
        assert breakdown['calculated_stock'] == 50  # min(100÷2, 50÷1, 200÷4) = min(50, 50, 50)
        assert breakdown['total_components'] == 3
        
        # التحقق من معلومات المكونات
        components = breakdown['components']
        assert len(components) == 3
        
        # البحث عن المكون الأول
        comp1_info = next(c for c in components if c['component_name'] == "مكون 1")
        assert comp1_info['current_stock'] == 100
        assert comp1_info['required_quantity'] == 2
        assert comp1_info['possible_bundles'] == 50

    def test_get_bundle_stock_breakdown_non_bundle(self):
        """اختبار الحصول على تفصيل مخزون منتج عادي (ليس مجمع)"""
        breakdown = StockCalculationEngine.get_bundle_stock_breakdown(self.component1)
        
        assert 'error' in breakdown
        assert "ليس منتجاً مجمعاً" in breakdown['error']

    def test_product_calculated_stock_property_bundle(self):
        """اختبار خاصية calculated_stock للمنتج المجمع"""
        # إنشاء مكونات المنتج المجمع
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
        
        # المخزون المحسوب يجب أن يكون min(100÷2, 50÷1) = 50
        assert self.bundle_product.calculated_stock == 50

    def test_product_calculated_stock_property_regular(self):
        """اختبار خاصية calculated_stock للمنتج العادي"""
        # للمنتج العادي، calculated_stock يجب أن يساوي current_stock
        assert self.component1.calculated_stock == self.component1.current_stock
        assert self.component1.calculated_stock == 100

    def test_product_get_bundle_stock_method(self):
        """اختبار دالة get_bundle_stock في نموذج المنتج"""
        # إنشاء مكونات المنتج المجمع
        BundleComponent.objects.create(
            bundle_product=self.bundle_product,
            component_product=self.component1,
            required_quantity=3
        )
        BundleComponent.objects.create(
            bundle_product=self.bundle_product,
            component_product=self.component2,
            required_quantity=2
        )
        
        # المخزون المحسوب: min(100÷3, 50÷2) = min(33, 25) = 25
        assert self.bundle_product.get_bundle_stock() == 25

    def test_product_get_bundle_stock_method_non_bundle(self):
        """اختبار دالة get_bundle_stock للمنتج العادي"""
        # للمنتج العادي، get_bundle_stock يجب أن يُرجع 0
        assert self.component1.get_bundle_stock() == 0

    def test_product_validate_bundle_availability_method(self):
        """اختبار دالة validate_bundle_availability في نموذج المنتج"""
        # إنشاء مكونات المنتج المجمع
        BundleComponent.objects.create(
            bundle_product=self.bundle_product,
            component_product=self.component1,
            required_quantity=2
        )
        
        # المخزون المتاح: 100÷2 = 50
        is_available, message = self.bundle_product.validate_bundle_availability(30)
        assert is_available is True
        
        is_available, message = self.bundle_product.validate_bundle_availability(60)
        assert is_available is False

    def test_product_get_bundle_stock_breakdown_method(self):
        """اختبار دالة get_bundle_stock_breakdown في نموذج المنتج"""
        # إنشاء مكونات المنتج المجمع
        BundleComponent.objects.create(
            bundle_product=self.bundle_product,
            component_product=self.component1,
            required_quantity=1
        )
        
        breakdown = self.bundle_product.get_bundle_stock_breakdown()
        
        assert breakdown is not None
        assert 'error' not in breakdown
        assert breakdown['bundle_name'] == "منتج مجمع"
        assert breakdown['calculated_stock'] == 100

    def test_product_get_bundle_stock_breakdown_method_non_bundle(self):
        """اختبار دالة get_bundle_stock_breakdown للمنتج العادي"""
        breakdown = self.component1.get_bundle_stock_breakdown()
        assert breakdown is None


@pytest.mark.django_db
class TestStockCalculationEngineEdgeCases:
    """اختبارات الحالات الحدية لمحرك حساب المخزون"""

    @pytest.fixture(autouse=True)
    def setup_edge_case_data(self, user, category, unit, warehouse):
        """إعداد بيانات اختبار الحالات الحدية"""
        self.user = user
        self.category = category
        self.unit = unit
        self.warehouse = warehouse

    def test_calculate_bundle_stock_with_large_numbers(self):
        """اختبار حساب المخزون مع أرقام كبيرة"""
        # إنشاء مكونات بأرقام كبيرة
        component = Product.objects.create(
            name="مكون كبير",
            sku="LARGE001",
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('1.00'),
            selling_price=Decimal('2.00'),
            is_active=True,
            created_by=self.user
        )
        
        bundle = Product.objects.create(
            name="منتج مجمع كبير",
            sku="LARGEBUNDLE001",
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('100.00'),
            selling_price=Decimal('200.00'),
            is_bundle=True,
            is_active=True,
            created_by=self.user
        )
        
        # إضافة مخزون كبير
        Stock.objects.create(product=component, warehouse=self.warehouse, quantity=1000000)
        
        # إنشاء مكون المنتج المجمع
        BundleComponent.objects.create(
            bundle_product=bundle,
            component_product=component,
            required_quantity=100
        )
        
        calculated_stock = StockCalculationEngine.calculate_bundle_stock(bundle)
        assert calculated_stock == 10000  # 1000000 ÷ 100

    def test_calculate_bundle_stock_with_fractional_division(self):
        """اختبار حساب المخزون مع القسمة التي تنتج كسور"""
        component = Product.objects.create(
            name="مكون كسري",
            sku="FRAC001",
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('1.00'),
            selling_price=Decimal('2.00'),
            is_active=True,
            created_by=self.user
        )
        
        bundle = Product.objects.create(
            name="منتج مجمع كسري",
            sku="FRACBUNDLE001",
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('10.00'),
            selling_price=Decimal('20.00'),
            is_bundle=True,
            is_active=True,
            created_by=self.user
        )
        
        # مخزون 10، مطلوب 3 لكل وحدة مجمعة
        # النتيجة: 10 ÷ 3 = 3.33... يجب أن تُقرب إلى 3
        Stock.objects.create(product=component, warehouse=self.warehouse, quantity=10)
        
        BundleComponent.objects.create(
            bundle_product=bundle,
            component_product=component,
            required_quantity=3
        )
        
        calculated_stock = StockCalculationEngine.calculate_bundle_stock(bundle)
        assert calculated_stock == 3  # floor(10 ÷ 3)

    def test_calculate_bundle_stock_single_component(self):
        """اختبار حساب المخزون مع مكون واحد فقط"""
        component = Product.objects.create(
            name="مكون وحيد",
            sku="SINGLE001",
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('5.00'),
            selling_price=Decimal('10.00'),
            is_active=True,
            created_by=self.user
        )
        
        bundle = Product.objects.create(
            name="منتج مجمع وحيد",
            sku="SINGLEBUNDLE001",
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('5.00'),
            selling_price=Decimal('10.00'),
            is_bundle=True,
            is_active=True,
            created_by=self.user
        )
        
        Stock.objects.create(product=component, warehouse=self.warehouse, quantity=25)
        
        BundleComponent.objects.create(
            bundle_product=bundle,
            component_product=component,
            required_quantity=1
        )
        
        calculated_stock = StockCalculationEngine.calculate_bundle_stock(bundle)
        assert calculated_stock == 25

    def test_error_handling_invalid_bundle(self):
        """اختبار معالجة الأخطاء مع منتج مجمع غير صالح"""
        # محاولة حساب مخزون منتج غير موجود
        result = StockCalculationEngine.calculate_bundle_stock(None)
        assert result == 0
        
        # محاولة حساب مخزون منتج بدون معرف
        fake_product = Product(name="منتج وهمي", is_bundle=True)
        result = StockCalculationEngine.calculate_bundle_stock(fake_product)
        assert result == 0