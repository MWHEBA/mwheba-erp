# -*- coding: utf-8 -*-
"""
Tests for Bundle Alternatives System
اختبارات نظام البدائل للمنتجات المجمعة
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from product.models import (
    Category, Unit, Product, BundleComponent, BundleComponentAlternative
)
from product.services.bundle_alternatives_service import BundleAlternativesService

User = get_user_model()


@pytest.fixture
def setup_data(db):
    """إعداد البيانات الأساسية للاختبارات"""
    # إنشاء مستخدم
    user = User.objects.create_user(
        username='testuser',
        email='test@test.com',
        password='testpass123'
    )
    
    # إنشاء تصنيف ووحدة
    category = Category.objects.create(name='ملابس', code='CLO')
    unit = Unit.objects.create(name='قطعة', symbol='قطعة')
    
    # إنشاء منتجات عادية
    shirt_white = Product.objects.create(
        name='قميص أبيض',
        sku='SHT-WHT-001',
        category=category,
        unit=unit,
        cost_price=Decimal('80.00'),
        selling_price=Decimal('100.00'),
        is_active=True,
        created_by=user
    )
    
    shirt_blue = Product.objects.create(
        name='قميص أزرق',
        sku='SHT-BLU-001',
        category=category,
        unit=unit,
        cost_price=Decimal('100.00'),
        selling_price=Decimal('150.00'),
        is_active=True,
        created_by=user
    )
    
    pants_black = Product.objects.create(
        name='بنطلون أسود',
        sku='PNT-BLK-001',
        category=category,
        unit=unit,
        cost_price=Decimal('120.00'),
        selling_price=Decimal('200.00'),
        is_active=True,
        created_by=user
    )
    
    # إنشاء منتج مجمع
    bundle = Product.objects.create(
        name='يونيفورم كامل',
        sku='UNI-FUL-001',
        category=category,
        unit=unit,
        cost_price=Decimal('200.00'),
        selling_price=Decimal('300.00'),
        is_bundle=True,
        is_active=True,
        created_by=user
    )
    
    # إنشاء مكونات
    component_shirt = BundleComponent.objects.create(
        bundle_product=bundle,
        component_product=shirt_white,
        required_quantity=1
    )
    
    component_pants = BundleComponent.objects.create(
        bundle_product=bundle,
        component_product=pants_black,
        required_quantity=1
    )
    
    return {
        'user': user,
        'category': category,
        'unit': unit,
        'shirt_white': shirt_white,
        'shirt_blue': shirt_blue,
        'pants_black': pants_black,
        'bundle': bundle,
        'component_shirt': component_shirt,
        'component_pants': component_pants
    }


@pytest.mark.django_db
class TestBundleComponentAlternative:
    """اختبارات موديل BundleComponentAlternative"""
    
    def test_create_alternative(self, setup_data):
        """اختبار إنشاء بديل"""
        alternative = BundleComponentAlternative.objects.create(
            bundle_component=setup_data['component_shirt'],
            alternative_product=setup_data['shirt_blue'],
            is_default=False,
            price_adjustment=Decimal('50.00'),
            display_order=1,
            is_active=True
        )
        
        assert alternative.id is not None
        assert alternative.alternative_product == setup_data['shirt_blue']
        assert alternative.price_adjustment == Decimal('50.00')
        assert alternative.final_price == Decimal('150.00')
    
    def test_unique_default_alternative(self, setup_data):
        """اختبار وجود بديل افتراضي واحد فقط"""
        # إنشاء بديل افتراضي
        BundleComponentAlternative.objects.create(
            bundle_component=setup_data['component_shirt'],
            alternative_product=setup_data['shirt_blue'],
            is_default=True,
            price_adjustment=Decimal('50.00')
        )
        
        # محاولة إنشاء بديل افتراضي آخر يجب أن تفشل
        with pytest.raises(ValidationError):
            alt2 = BundleComponentAlternative(
                bundle_component=setup_data['component_shirt'],
                alternative_product=setup_data['pants_black'],
                is_default=True,
                price_adjustment=Decimal('0.00')
            )
            alt2.full_clean()
    
    def test_alternative_validation(self, setup_data):
        """اختبار التحقق من صحة البديل"""
        # محاولة إضافة منتج مجمع كبديل يجب أن تفشل
        with pytest.raises(ValidationError):
            alt = BundleComponentAlternative(
                bundle_component=setup_data['component_shirt'],
                alternative_product=setup_data['bundle'],
                is_default=False
            )
            alt.full_clean()


@pytest.mark.django_db
class TestBundleAlternativesService:
    """اختبارات خدمة البدائل"""
    
    def test_get_bundle_with_alternatives(self, setup_data):
        """اختبار جلب المنتج المجمع مع البدائل"""
        # إضافة بديل
        alt = BundleComponentAlternative.objects.create(
            bundle_component=setup_data['component_shirt'],
            alternative_product=setup_data['shirt_blue'],
            is_default=False,
            price_adjustment=Decimal('50.00'),
            is_active=True
        )

        # تأكيد أن البديل تم إنشاؤه
        assert alt.id is not None
        count = BundleComponentAlternative.objects.filter(
            bundle_component=setup_data['component_shirt']
        ).count()
        print(f"\nAlternatives count in DB: {count}")

        # جلب البيانات
        data = BundleAlternativesService.get_bundle_with_alternatives(
            setup_data['bundle'].id
        )

        # Debug
        print(f"Components count: {len(data['components'])}")
        for i, comp in enumerate(data['components']):
            print(f"Component {i}: {comp['name']}, alternatives: {len(comp['alternatives'])}")

        assert data['id'] == setup_data['bundle'].id
        assert data['name'] == 'يونيفورم كامل'
        assert len(data['components']) == 2

        # Find the shirt component
        shirt_comp = next((c for c in data['components'] if c['name'] == 'قميص أبيض'), None)
        assert shirt_comp is not None
        assert len(shirt_comp['alternatives']) == 1

    
    def test_calculate_bundle_price_with_selections(self, setup_data):
        """اختبار حساب السعر مع الاختيارات"""
        # إضافة بديل
        BundleComponentAlternative.objects.create(
            bundle_component=setup_data['component_shirt'],
            alternative_product=setup_data['shirt_blue'],
            price_adjustment=Decimal('50.00'),
            is_active=True
        )
        
        # حساب السعر مع اختيار البديل
        selections = {
            setup_data['component_shirt'].id: setup_data['shirt_blue'].id,
            setup_data['component_pants'].id: setup_data['pants_black'].id
        }
        
        price_data = BundleAlternativesService.calculate_bundle_price_with_selections(
            setup_data['bundle'].id, selections
        )
        
        assert price_data['base_price'] == 300.00
        assert price_data['total_adjustment'] == 50.00
        assert price_data['final_price'] == 350.00
    
    def test_validate_component_selections(self, setup_data):
        """اختبار التحقق من صحة الاختيارات"""
        from product.models import Warehouse, Stock
        
        # إنشاء مخزن ومخزون
        warehouse = Warehouse.objects.create(name='المخزن الرئيسي', is_active=True)
        Stock.objects.create(
            product=setup_data['shirt_white'],
            warehouse=warehouse,
            quantity=100
        )
        Stock.objects.create(
            product=setup_data['pants_black'],
            warehouse=warehouse,
            quantity=100
        )
        
        # اختيارات صحيحة
        selections = {
            setup_data['component_shirt'].id: setup_data['shirt_white'].id,
            setup_data['component_pants'].id: setup_data['pants_black'].id
        }
        
        is_valid, msg = BundleAlternativesService.validate_component_selections(
            setup_data['bundle'].id, selections
        )
        
        print(f"\nValidation result: is_valid={is_valid}, msg={msg}")
        assert is_valid is True, f"Validation failed: {msg}"
        assert msg == "الاختيارات صحيحة"
    
    def test_validate_missing_component(self, setup_data):
        """اختبار التحقق من مكون مفقود"""
        # اختيارات ناقصة (مكون واحد فقط)
        selections = {
            setup_data['component_shirt'].id: setup_data['shirt_white'].id
        }
        
        is_valid, msg = BundleAlternativesService.validate_component_selections(
            setup_data['bundle'].id, selections
        )
        
        assert is_valid is False
        assert 'يجب اختيار جميع المكونات' in msg
    
    def test_get_default_selections(self, setup_data):
        """اختبار الحصول على الاختيارات الافتراضية"""
        # إضافة بديل افتراضي
        BundleComponentAlternative.objects.create(
            bundle_component=setup_data['component_shirt'],
            alternative_product=setup_data['shirt_blue'],
            is_default=True,
            is_active=True
        )
        
        selections = BundleAlternativesService.get_default_selections(
            setup_data['bundle'].id
        )
        
        # يجب أن يختار البديل الافتراضي للقميص
        assert selections[setup_data['component_shirt'].id] == setup_data['shirt_blue'].id
        # يجب أن يختار المكون الأساسي للبنطلون
        assert selections[setup_data['component_pants'].id] == setup_data['pants_black'].id


@pytest.mark.django_db
class TestCriticalScenarios:
    """اختبارات السيناريوهات الحرجة"""
    
    def test_stock_validation_before_submit(self, setup_data):
        """اختبار التحقق من المخزون قبل Submit"""
        from product.models import Stock, Warehouse
        
        # إنشاء مخزن ومخزون
        warehouse = Warehouse.objects.create(name='المخزن الرئيسي', is_active=True)
        Stock.objects.create(
            product=setup_data['shirt_white'],
            warehouse=warehouse,
            quantity=0  # مخزون صفر
        )
        
        selections = {
            setup_data['component_shirt'].id: setup_data['shirt_white'].id,
            setup_data['component_pants'].id: setup_data['pants_black'].id
        }
        
        is_valid, msg = BundleAlternativesService.validate_component_selections(
            setup_data['bundle'].id, selections
        )
        
        assert is_valid is False
        assert 'المخزون غير كافي' in msg
    
    def test_alternative_not_available(self, setup_data):
        """اختبار اختيار بديل غير متاح"""
        # إضافة بديل غير نشط
        alt = BundleComponentAlternative.objects.create(
            bundle_component=setup_data['component_shirt'],
            alternative_product=setup_data['shirt_blue'],
            is_active=False  # غير نشط
        )
        
        selections = {
            setup_data['component_shirt'].id: setup_data['shirt_blue'].id,
            setup_data['component_pants'].id: setup_data['pants_black'].id
        }
        
        is_valid, msg = BundleAlternativesService.validate_component_selections(
            setup_data['bundle'].id, selections
        )
        
        assert is_valid is False
        assert 'ليس بديلاً متاحاً' in msg
