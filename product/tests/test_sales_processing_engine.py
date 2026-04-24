# -*- coding: utf-8 -*-
"""
اختبارات محرك معالجة مبيعات المنتجات المجمعة
Unit Tests for Sales Processing Engine

Requirements: 3.1, 3.2, 3.3, 3.5, 3.6
"""

import pytest
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from unittest.mock import patch, MagicMock

from product.models import Product, Category, Unit, Warehouse, Stock, BundleComponent, StockMovement
from product.services.sales_processing_engine import SalesProcessingEngine

User = get_user_model()


@pytest.mark.django_db
class TestSalesProcessingEngine:
    """اختبارات محرك معالجة مبيعات المنتجات المجمعة"""

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
        
        # إنشاء منتج مجمع
        self.bundle_product = Product.objects.create(
            name="منتج مجمع",
            sku="BUNDLE001",
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('30.00'),
            selling_price=Decimal('60.00'),
            is_bundle=True,
            is_active=True,
            created_by=self.user
        )
        
        # إضافة مخزون للمكونات
        Stock.objects.create(product=self.component1, warehouse=self.warehouse, quantity=100)
        Stock.objects.create(product=self.component2, warehouse=self.warehouse, quantity=50)
        
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
        
        # سياق المعاملة الأساسي
        self.transaction_context = {
            'created_by_id': self.user.id,
            'sale_reference': 'SALE001',
            'customer_id': 123,
            'notes': 'اختبار بيع منتج مجمع'
        }

    def test_validate_bundle_availability_sufficient_stock(self):
        """اختبار التحقق من توفر المنتج المجمع - مخزون كافي"""
        # المخزون المتاح: min(100÷2, 50÷1) = min(50, 50) = 50
        # طلب 30 وحدة (أقل من المتاح)
        is_available, message = SalesProcessingEngine.validate_bundle_availability(
            self.bundle_product, 30
        )
        
        assert is_available is True
        assert "متوفرة للبيع" in message

    def test_validate_bundle_availability_insufficient_stock(self):
        """اختبار التحقق من توفر المنتج المجمع - مخزون غير كافي"""
        # المخزون المتاح: min(100÷2, 50÷1) = min(50, 50) = 50
        # طلب 60 وحدة (أكثر من المتاح)
        is_available, message = SalesProcessingEngine.validate_bundle_availability(
            self.bundle_product, 60
        )
        
        assert is_available is False
        assert "مخزون غير كافي" in message
        assert "مكون 1" in message or "مكون 2" in message

    def test_validate_bundle_availability_inactive_component(self):
        """اختبار التحقق من توفر المنتج المجمع - مكون غير نشط"""
        # تعطيل أحد المكونات
        self.component1.is_active = False
        self.component1.save()
        
        is_available, message = SalesProcessingEngine.validate_bundle_availability(
            self.bundle_product, 10
        )
        
        assert is_available is False
        assert "غير نشط" in message

    def test_validate_bundle_availability_non_bundle_product(self):
        """اختبار التحقق من توفر منتج عادي (ليس مجمع)"""
        is_available, message = SalesProcessingEngine.validate_bundle_availability(
            self.component1, 10
        )
        
        assert is_available is False
        assert "ليس منتجاً مجمعاً" in message

    def test_validate_bundle_availability_zero_quantity(self):
        """اختبار التحقق من توفر المنتج المجمع - كمية صفر"""
        is_available, message = SalesProcessingEngine.validate_bundle_availability(
            self.bundle_product, 0
        )
        
        assert is_available is False
        assert "أكبر من صفر" in message

    def test_validate_bundle_availability_inactive_bundle(self):
        """اختبار التحقق من توفر منتج مجمع غير نشط"""
        self.bundle_product.is_active = False
        self.bundle_product.save()
        
        is_available, message = SalesProcessingEngine.validate_bundle_availability(
            self.bundle_product, 10
        )
        
        assert is_available is False
        assert "غير نشط" in message

    def test_process_bundle_sale_success(self):
        """اختبار معالجة بيع المنتج المجمع - حالة النجاح"""
        # معالجة البيع (بدون mock - استخدام النظام الحقيقي)
        success, transaction_record, error_message = SalesProcessingEngine.process_bundle_sale(
            self.bundle_product, 10, self.transaction_context
        )
        
        assert success is True
        assert transaction_record is not None
        assert error_message is None
        
        # التحقق من تفاصيل سجل المعاملة
        assert transaction_record['transaction_type'] == 'bundle_sale'
        assert transaction_record['bundle_product_id'] == self.bundle_product.id
        assert transaction_record['quantity_sold'] == 10
        assert transaction_record['unit_price'] == self.bundle_product.selling_price
        assert transaction_record['total_amount'] == self.bundle_product.selling_price * 10
        assert transaction_record['status'] == 'completed'
        assert transaction_record['reversed'] is False
        
        # التحقق من تفاصيل خصم المكونات
        component_deductions = transaction_record['component_deductions']
        assert len(component_deductions) == 2
        
        # التحقق من خصم المكون الأول (2 × 10 = 20)
        comp1_deduction = next(d for d in component_deductions if d['component_id'] == self.component1.id)
        assert comp1_deduction['deducted_quantity'] == 20
        assert comp1_deduction['required_per_unit'] == 2
        assert comp1_deduction['units_sold'] == 10
        
        # التحقق من خصم المكون الثاني (1 × 10 = 10)
        comp2_deduction = next(d for d in component_deductions if d['component_id'] == self.component2.id)
        assert comp2_deduction['deducted_quantity'] == 10
        assert comp2_deduction['required_per_unit'] == 1
        assert comp2_deduction['units_sold'] == 10
        
        # التحقق من تحديث المخزون الفعلي
        stock1 = Stock.objects.get(product=self.component1, warehouse=self.warehouse)
        stock2 = Stock.objects.get(product=self.component2, warehouse=self.warehouse)
        assert stock1.quantity == 80  # 100 - 20
        assert stock2.quantity == 40  # 50 - 10

    def test_process_bundle_sale_insufficient_stock(self):
        """اختبار معالجة بيع المنتج المجمع - مخزون غير كافي"""
        # محاولة بيع كمية أكبر من المتاح (المتاح = 50، الطلب = 60)
        success, transaction_record, error_message = SalesProcessingEngine.process_bundle_sale(
            self.bundle_product, 60, self.transaction_context
        )
        
        assert success is False
        assert transaction_record is None
        assert error_message is not None
        assert "مخزون غير كافي" in error_message

    def test_process_bundle_sale_invalid_inputs(self):
        """اختبار معالجة بيع المنتج المجمع - مدخلات غير صحيحة"""
        # منتج فارغ
        success, transaction_record, error_message = SalesProcessingEngine.process_bundle_sale(
            None, 10, self.transaction_context
        )
        assert success is False
        assert "غير محدد" in error_message
        
        # كمية صفر
        success, transaction_record, error_message = SalesProcessingEngine.process_bundle_sale(
            self.bundle_product, 0, self.transaction_context
        )
        assert success is False
        assert "أكبر من صفر" in error_message
        
        # سياق معاملة غير صحيح
        success, transaction_record, error_message = SalesProcessingEngine.process_bundle_sale(
            self.bundle_product, 10, "invalid_context"
        )
        assert success is False
        assert "قاموس" in error_message
        
        # سياق معاملة ناقص
        incomplete_context = {'sale_reference': 'SALE001'}
        success, transaction_record, error_message = SalesProcessingEngine.process_bundle_sale(
            self.bundle_product, 10, incomplete_context
        )
        assert success is False
        assert "مفقودة" in error_message

    def test_process_bundle_sale_non_bundle_product(self):
        """اختبار معالجة بيع منتج عادي (ليس مجمع)"""
        success, transaction_record, error_message = SalesProcessingEngine.process_bundle_sale(
            self.component1, 10, self.transaction_context
        )
        
        assert success is False
        assert transaction_record is None
        assert "ليس منتجاً مجمعاً" in error_message

    def test_reverse_bundle_sale_success(self):
        """اختبار عكس بيع المنتج المجمع - حالة النجاح"""
        # أولاً، قم بإجراء بيع حقيقي
        success, transaction_record, error = SalesProcessingEngine.process_bundle_sale(
            self.bundle_product, 5, self.transaction_context
        )
        assert success is True
        
        # التحقق من خصم المخزون
        stock1_after_sale = Stock.objects.get(product=self.component1, warehouse=self.warehouse)
        stock2_after_sale = Stock.objects.get(product=self.component2, warehouse=self.warehouse)
        assert stock1_after_sale.quantity == 90  # 100 - (5 * 2)
        assert stock2_after_sale.quantity == 45  # 50 - (5 * 1)
        
        # عكس البيع
        success, error_message = SalesProcessingEngine.reverse_bundle_sale(transaction_record)
        
        assert success is True
        assert error_message is None
        
        # التحقق من تحديث سجل المعاملة
        assert transaction_record['reversed'] is True
        assert 'reversed_at' in transaction_record
        assert 'restored_components' in transaction_record
        
        # التحقق من تفاصيل إرجاع المكونات
        restored_components = transaction_record['restored_components']
        assert len(restored_components) == 2
        
        # التحقق من إرجاع المكون الأول
        comp1_restore = next(r for r in restored_components if r['component_id'] == self.component1.id)
        assert comp1_restore['restored_quantity'] == 10
        
        # التحقق من إرجاع المكون الثاني
        comp2_restore = next(r for r in restored_components if r['component_id'] == self.component2.id)
        assert comp2_restore['restored_quantity'] == 5
        
        # التحقق من إرجاع المخزون الفعلي
        stock1_after_reverse = Stock.objects.get(product=self.component1, warehouse=self.warehouse)
        stock2_after_reverse = Stock.objects.get(product=self.component2, warehouse=self.warehouse)
        assert stock1_after_reverse.quantity == 100  # العودة للمخزون الأصلي
        assert stock2_after_reverse.quantity == 50   # العودة للمخزون الأصلي

    def test_reverse_bundle_sale_invalid_transaction(self):
        """اختبار عكس بيع المنتج المجمع - سجل معاملة غير صحيح"""
        # سجل معاملة فارغ
        success, error_message = SalesProcessingEngine.reverse_bundle_sale(None)
        assert success is False
        assert "غير صحيح" in error_message
        
        # سجل معاملة غير مكتمل
        incomplete_record = {'status': 'processing'}
        success, error_message = SalesProcessingEngine.reverse_bundle_sale(incomplete_record)
        assert success is False
        assert "غير مكتمل" in error_message
        
        # سجل معاملة تم عكسها مسبقاً
        reversed_record = {'status': 'completed', 'reversed': True}
        success, error_message = SalesProcessingEngine.reverse_bundle_sale(reversed_record)
        assert success is False
        assert "تم عكسها مسبقاً" in error_message
        
        # سجل معاملة بدون معرف منتج
        no_product_record = {'status': 'completed', 'reversed': False}
        success, error_message = SalesProcessingEngine.reverse_bundle_sale(no_product_record)
        assert success is False
        assert "غير موجود" in error_message

    def test_reverse_bundle_sale_nonexistent_product(self):
        """اختبار عكس بيع المنتج المجمع - منتج غير موجود"""
        transaction_record = {
            'status': 'completed',
            'reversed': False,
            'bundle_product_id': 99999,  # معرف غير موجود
            'component_deductions': []
        }
        
        success, error_message = SalesProcessingEngine.reverse_bundle_sale(transaction_record)
        assert success is False
        assert "غير موجود" in error_message

    def test_get_bundle_sale_summary(self):
        """اختبار الحصول على ملخص بيع المنتج المجمع"""
        summary = SalesProcessingEngine.get_bundle_sale_summary(self.bundle_product, 20)
        
        # التحقق من معلومات المنتج المجمع
        bundle_info = summary['bundle_info']
        assert bundle_info['name'] == "منتج مجمع"
        assert bundle_info['sku'] == "BUNDLE001"
        assert bundle_info['quantity'] == 20
        assert bundle_info['unit_price'] == float(self.bundle_product.selling_price)
        assert bundle_info['total_amount'] == float(self.bundle_product.selling_price * 20)
        
        # التحقق من فحص التوفر
        availability_check = summary['availability_check']
        assert availability_check['available'] is True  # المتاح = 50، الطلب = 20
        assert summary['can_proceed'] is True
        
        # التحقق من تأثير المكونات
        components_impact = summary['components_impact']
        assert len(components_impact) == 2
        
        # التحقق من تأثير المكون الأول (مطلوب: 2×20=40، متاح: 100، متبقي: 60)
        comp1_impact = next(c for c in components_impact if c['component_name'] == "مكون 1")
        assert comp1_impact['required_per_unit'] == 2
        assert comp1_impact['total_required'] == 40
        assert comp1_impact['current_stock'] == 100
        assert comp1_impact['remaining_after_sale'] == 60
        assert comp1_impact['sufficient'] is True
        
        # التحقق من تأثير المكون الثاني (مطلوب: 1×20=20، متاح: 50، متبقي: 30)
        comp2_impact = next(c for c in components_impact if c['component_name'] == "مكون 2")
        assert comp2_impact['required_per_unit'] == 1
        assert comp2_impact['total_required'] == 20
        assert comp2_impact['current_stock'] == 50
        assert comp2_impact['remaining_after_sale'] == 30
        assert comp2_impact['sufficient'] is True

    def test_get_bundle_sale_summary_insufficient_stock(self):
        """اختبار ملخص بيع المنتج المجمع - مخزون غير كافي"""
        summary = SalesProcessingEngine.get_bundle_sale_summary(self.bundle_product, 60)
        
        # التحقق من فحص التوفر
        availability_check = summary['availability_check']
        assert availability_check['available'] is False
        assert summary['can_proceed'] is False
        
        # التحقق من تأثير المكونات
        components_impact = summary['components_impact']
        
        # المكون الثاني سيكون غير كافي (مطلوب: 1×60=60، متاح: 50)
        comp2_impact = next(c for c in components_impact if c['component_name'] == "مكون 2")
        assert comp2_impact['total_required'] == 60
        assert comp2_impact['current_stock'] == 50
        assert comp2_impact['remaining_after_sale'] == 0  # max(0, 50-60)
        assert comp2_impact['sufficient'] is False

    @patch('product.services.sales_processing_engine.logger')
    def test_error_logging(self, mock_logger):
        """اختبار تسجيل الأخطاء"""
        # محاولة معالجة بيع بمدخلات غير صحيحة لإثارة خطأ
        with patch.object(SalesProcessingEngine, '_validate_sale_inputs', side_effect=Exception("Test error")):
            SalesProcessingEngine.process_bundle_sale(self.bundle_product, 10, self.transaction_context)
        
        # التحقق من تسجيل الخطأ
        mock_logger.error.assert_called()

    def test_transaction_atomicity(self):
        """اختبار الطبيعة الذرية للمعاملات"""
        # إنشاء حالة تؤدي إلى فشل في منتصف المعاملة
        # عن طريق إثارة خطأ في إنشاء حركة المخزون
        
        with patch.object(SalesProcessingEngine, '_create_stock_movement', side_effect=Exception("Database error")):
            # محاولة معالجة البيع
            success, transaction_record, error_message = SalesProcessingEngine.process_bundle_sale(
                self.bundle_product, 10, self.transaction_context
            )
            
            # يجب أن تفشل المعاملة
            assert success is False
            assert transaction_record is None
            assert error_message is not None
            
            # التحقق من أن المخزون لم يتأثر (الطبيعة الذرية)
            # المكونات يجب أن تحتفظ بمخزونها الأصلي
            self.component1.refresh_from_db()
            self.component2.refresh_from_db()
            stock1 = Stock.objects.get(product=self.component1, warehouse=self.warehouse)
            stock2 = Stock.objects.get(product=self.component2, warehouse=self.warehouse)
            assert stock1.quantity == 100  # المخزون الأصلي
            assert stock2.quantity == 50   # المخزون الأصلي


@pytest.mark.django_db
class TestSalesProcessingEngineIntegration:
    """اختبارات التكامل لمحرك معالجة المبيعات"""

    @pytest.fixture(autouse=True)
    def setup_integration_data(self, user, category, unit, warehouse):
        """إعداد بيانات اختبار التكامل"""
        self.user = user
        self.category = category
        self.unit = unit
        self.warehouse = warehouse
        
        # إنشاء منتجات مكونة متعددة
        self.components = []
        for i in range(5):
            component = Product.objects.create(
                name=f"مكون {i+1}",
                sku=f"COMP{i+1:03d}",
                category=self.category,
                unit=self.unit,
                cost_price=Decimal(f'{(i+1)*5}.00'),
                selling_price=Decimal(f'{(i+1)*8}.00'),
                is_active=True,
                created_by=self.user
            )
            # إضافة مخزون متدرج
            Stock.objects.create(
                product=component, 
                warehouse=self.warehouse, 
                quantity=(i+1)*20
            )
            self.components.append(component)
        
        # إنشاء منتج مجمع معقد
        self.complex_bundle = Product.objects.create(
            name="منتج مجمع معقد",
            sku="COMPLEXBUNDLE001",
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('75.00'),
            selling_price=Decimal('150.00'),
            is_bundle=True,
            is_active=True,
            created_by=self.user
        )
        
        # إضافة مكونات بكميات مختلفة
        required_quantities = [1, 2, 1, 3, 1]
        for i, (component, qty) in enumerate(zip(self.components, required_quantities)):
            BundleComponent.objects.create(
                bundle_product=self.complex_bundle,
                component_product=component,
                required_quantity=qty
            )
        
        self.transaction_context = {
            'created_by_id': self.user.id,
            'sale_reference': 'INTEGRATION_TEST_001',
            'customer_id': 456,
            'notes': 'اختبار تكامل معقد'
        }

    def test_complex_bundle_stock_calculation(self):
        """اختبار حساب مخزون منتج مجمع معقد"""
        # المخزون المتوقع:
        # المكون 1: 20 ÷ 1 = 20
        # المكون 2: 40 ÷ 2 = 20  
        # المكون 3: 60 ÷ 1 = 60
        # المكون 4: 80 ÷ 3 = 26
        # المكون 5: 100 ÷ 1 = 100
        # الحد الأدنى = 20
        
        from product.services.stock_calculation_engine import StockCalculationEngine
        calculated_stock = StockCalculationEngine.calculate_bundle_stock(self.complex_bundle)
        assert calculated_stock == 20

    def test_complex_bundle_sale_processing(self):
        """اختبار معالجة بيع منتج مجمع معقد"""
        # بيع 15 وحدة (أقل من المتاح = 20)
        success, transaction_record, error_message = SalesProcessingEngine.process_bundle_sale(
            self.complex_bundle, 15, self.transaction_context
        )
        
        assert success is True
        assert transaction_record is not None
        assert error_message is None
        
        # التحقق من خصم المكونات الصحيح
        component_deductions = transaction_record['component_deductions']
        assert len(component_deductions) == 5
        
        expected_deductions = [15*1, 15*2, 15*1, 15*3, 15*1]  # [15, 30, 15, 45, 15]
        
        for i, expected_deduction in enumerate(expected_deductions):
            comp_deduction = next(
                d for d in component_deductions 
                if d['component_id'] == self.components[i].id
            )
            assert comp_deduction['deducted_quantity'] == expected_deduction

    def test_multiple_bundle_sales_sequence(self):
        """اختبار تسلسل مبيعات متعددة للمنتج المجمع"""
        # البيع الأول: 10 وحدات
        success1, record1, error1 = SalesProcessingEngine.process_bundle_sale(
            self.complex_bundle, 10, self.transaction_context
        )
        assert success1 is True
        
        # البيع الثاني: 5 وحدات (المتبقي = 20-10 = 10، والطلب = 5)
        success2, record2, error2 = SalesProcessingEngine.process_bundle_sale(
            self.complex_bundle, 5, self.transaction_context
        )
        assert success2 is True
        
        # البيع الثالث: 10 وحدات (المتبقي = 10-5 = 5، والطلب = 10) - يجب أن يفشل
        success3, record3, error3 = SalesProcessingEngine.process_bundle_sale(
            self.complex_bundle, 10, self.transaction_context
        )
        assert success3 is False
        assert "مخزون غير كافي" in error3

    def test_sale_and_reversal_cycle(self):
        """اختبار دورة البيع والعكس الكاملة"""
        # تسجيل المخزون الأصلي
        original_stocks = {}
        for component in self.components:
            stock = Stock.objects.get(product=component, warehouse=self.warehouse)
            original_stocks[component.id] = stock.quantity
        
        # البيع (بدون mock - استخدام النظام الحقيقي)
        success, transaction_record, error = SalesProcessingEngine.process_bundle_sale(
            self.complex_bundle, 8, self.transaction_context
        )
        assert success is True
        
        # التحقق من خصم المخزون
        for i, component in enumerate(self.components):
            stock = Stock.objects.get(product=component, warehouse=self.warehouse)
            required_qty = [1, 2, 1, 3, 1][i]  # الكميات المطلوبة
            expected_remaining = original_stocks[component.id] - (8 * required_qty)
            assert stock.quantity == expected_remaining
        
        # عكس البيع (بدون mock - استخدام النظام الحقيقي)
        success_reverse, error_reverse = SalesProcessingEngine.reverse_bundle_sale(transaction_record)
        assert success_reverse is True
        assert error_reverse is None
        
        # التحقق من إرجاع المخزون للحالة الأصلية
        for component in self.components:
            stock = Stock.objects.get(product=component, warehouse=self.warehouse)
            assert stock.quantity == original_stocks[component.id]

    def test_concurrent_sales_handling(self):
        """اختبار التعامل مع المبيعات المتزامنة"""
        # محاكاة مبيعات متزامنة باستخدام معاملات منفصلة
        from django.db import transaction
        
        results = []
        
        def sale_in_transaction(quantity, context_suffix):
            try:
                with transaction.atomic():
                    context = self.transaction_context.copy()
                    context['sale_reference'] += f'_{context_suffix}'
                    return SalesProcessingEngine.process_bundle_sale(
                        self.complex_bundle, quantity, context
                    )
            except Exception as e:
                return False, None, str(e)
        
        # محاولة بيع 15 وحدة مرتين (المجموع = 30، المتاح = 20)
        result1 = sale_in_transaction(15, 'A')
        result2 = sale_in_transaction(15, 'B')
        
        # يجب أن ينجح واحد فقط
        successful_sales = sum(1 for r in [result1, result2] if r[0])
        assert successful_sales == 1

    def test_performance_with_large_bundle(self):
        """اختبار الأداء مع منتج مجمع كبير"""
        # إنشاء منتج مجمع بعدد كبير من المكونات
        large_bundle = Product.objects.create(
            name="منتج مجمع كبير",
            sku="LARGEBUNDLE001",
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('500.00'),
            selling_price=Decimal('1000.00'),
            is_bundle=True,
            is_active=True,
            created_by=self.user
        )
        
        # إضافة جميع المكونات الموجودة
        for component in self.components:
            BundleComponent.objects.create(
                bundle_product=large_bundle,
                component_product=component,
                required_quantity=1
            )
        
        # قياس وقت معالجة البيع
        import time
        start_time = time.time()
        
        success, transaction_record, error = SalesProcessingEngine.process_bundle_sale(
            large_bundle, 5, self.transaction_context
        )
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        assert success is True
        assert processing_time < 2.0  # يجب أن يكتمل في أقل من ثانيتين
        
        # التحقق من صحة النتائج
        assert len(transaction_record['component_deductions']) == 5