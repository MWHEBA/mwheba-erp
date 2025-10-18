from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from decimal import Decimal

from ..models import (
    PrintingOrder, OrderMaterial, OrderService, 
    PaperSpecification, PrintingSpecification,
    CostCalculation, OrderSummary
)
from client.models import Customer


class PrintingOrderModelTest(TestCase):
    """
    اختبارات نموذج طلب التسعير
    """
    
    def setUp(self):
        """إعداد البيانات للاختبار"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        self.customer = Customer.objects.create(
            name='عميل تجريبي',
            phone='01234567890',
            email='test@example.com'
        )
    
    def test_create_printing_order(self):
        """اختبار إنشاء طلب تسعير"""
        order = PrintingOrder.objects.create(
            customer=self.customer,
            title='طلب تسعير تجريبي',
            order_type='book',
            quantity=1000,
            created_by=self.user
        )
        
        self.assertEqual(order.customer, self.customer)
        self.assertEqual(order.title, 'طلب تسعير تجريبي')
        self.assertEqual(order.quantity, 1000)
        self.assertTrue(order.order_number.startswith('PO'))
        self.assertEqual(order.status, 'draft')
    
    def test_order_number_generation(self):
        """اختبار توليد رقم الطلب"""
        order1 = PrintingOrder.objects.create(
            customer=self.customer,
            title='طلب 1',
            order_type='book',
            quantity=100,
            created_by=self.user
        )
        
        order2 = PrintingOrder.objects.create(
            customer=self.customer,
            title='طلب 2',
            order_type='magazine',
            quantity=200,
            created_by=self.user
        )
        
        self.assertNotEqual(order1.order_number, order2.order_number)
        self.assertTrue(order1.order_number.startswith('PO'))
        self.assertTrue(order2.order_number.startswith('PO'))
    
    def test_total_pages_property(self):
        """اختبار خاصية إجمالي الصفحات"""
        order = PrintingOrder.objects.create(
            customer=self.customer,
            title='طلب تجريبي',
            order_type='book',
            quantity=100,
            pages_count=20,
            copies_count=5,
            created_by=self.user
        )
        
        self.assertEqual(order.total_pages, 100)  # 20 * 5
    
    def test_total_items_property(self):
        """اختبار خاصية إجمالي القطع"""
        order = PrintingOrder.objects.create(
            customer=self.customer,
            title='طلب تجريبي',
            order_type='book',
            quantity=100,
            copies_count=5,
            created_by=self.user
        )
        
        self.assertEqual(order.total_items, 500)  # 100 * 5
    
    def test_calculate_final_price(self):
        """اختبار حساب السعر النهائي"""
        order = PrintingOrder.objects.create(
            customer=self.customer,
            title='طلب تجريبي',
            order_type='book',
            quantity=100,
            estimated_cost=Decimal('1000.00'),
            profit_margin=Decimal('20.00'),
            rush_fee=Decimal('50.00'),
            created_by=self.user
        )
        
        final_price = order.calculate_final_price()
        expected_price = Decimal('1000.00') + (Decimal('1000.00') * Decimal('0.20')) + Decimal('50.00')
        
        self.assertEqual(final_price, expected_price)
    
    def test_update_status(self):
        """اختبار تحديث حالة الطلب"""
        order = PrintingOrder.objects.create(
            customer=self.customer,
            title='طلب تجريبي',
            order_type='book',
            quantity=100,
            created_by=self.user
        )
        
        old_status, new_status = order.update_status('approved', self.user)
        
        self.assertEqual(old_status, 'draft')
        self.assertEqual(new_status, 'approved')
        self.assertEqual(order.status, 'approved')
        self.assertIsNotNone(order.approved_at)


class OrderMaterialModelTest(TestCase):
    """
    اختبارات نموذج مواد الطلب
    """
    
    def setUp(self):
        """إعداد البيانات للاختبار"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        self.customer = Customer.objects.create(
            name='عميل تجريبي',
            phone='01234567890'
        )
        
        self.order = PrintingOrder.objects.create(
            customer=self.customer,
            title='طلب تجريبي',
            order_type='book',
            quantity=100,
            created_by=self.user
        )
    
    def test_create_order_material(self):
        """اختبار إنشاء مادة للطلب"""
        material = OrderMaterial.objects.create(
            order=self.order,
            material_type='paper',
            material_name='ورق أبيض 80 جرام',
            quantity=Decimal('10.000'),
            unit='sheet',
            unit_cost=Decimal('2.50'),
            waste_percentage=Decimal('5.00'),
            created_by=self.user
        )
        
        self.assertEqual(material.order, self.order)
        self.assertEqual(material.material_type, 'paper')
        self.assertEqual(material.quantity, Decimal('10.000'))
    
    def test_calculate_total_cost(self):
        """اختبار حساب التكلفة الإجمالية"""
        material = OrderMaterial.objects.create(
            order=self.order,
            material_type='paper',
            material_name='ورق أبيض 80 جرام',
            quantity=Decimal('10.000'),
            unit='sheet',
            unit_cost=Decimal('2.50'),
            waste_percentage=Decimal('5.00'),
            created_by=self.user
        )
        
        # التكلفة الأساسية: 10 * 2.50 = 25.00
        # الهالك: 25.00 * 0.05 = 1.25
        # الإجمالي: 25.00 + 1.25 = 26.25
        expected_total = Decimal('26.25')
        
        self.assertEqual(material.total_cost, expected_total)


class OrderServiceModelTest(TestCase):
    """
    اختبارات نموذج خدمات الطلب
    """
    
    def setUp(self):
        """إعداد البيانات للاختبار"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        self.customer = Customer.objects.create(
            name='عميل تجريبي',
            phone='01234567890'
        )
        
        self.order = PrintingOrder.objects.create(
            customer=self.customer,
            title='طلب تجريبي',
            order_type='book',
            quantity=100,
            created_by=self.user
        )
    
    def test_create_order_service(self):
        """اختبار إنشاء خدمة للطلب"""
        service = OrderService.objects.create(
            order=self.order,
            service_category='printing',
            service_name='طباعة رقمية ملونة',
            quantity=Decimal('100.000'),
            unit='piece',
            unit_price=Decimal('0.50'),
            setup_cost=Decimal('25.00'),
            created_by=self.user
        )
        
        self.assertEqual(service.order, self.order)
        self.assertEqual(service.service_category, 'printing')
        self.assertEqual(service.quantity, Decimal('100.000'))
    
    def test_calculate_total_cost(self):
        """اختبار حساب التكلفة الإجمالية للخدمة"""
        service = OrderService.objects.create(
            order=self.order,
            service_category='printing',
            service_name='طباعة رقمية ملونة',
            quantity=Decimal('100.000'),
            unit='piece',
            unit_price=Decimal('0.50'),
            setup_cost=Decimal('25.00'),
            created_by=self.user
        )
        
        # التكلفة: (100 * 0.50) + 25.00 = 75.00
        expected_total = Decimal('75.00')
        
        self.assertEqual(service.total_cost, expected_total)


class CostCalculationModelTest(TestCase):
    """
    اختبارات نموذج حسابات التكلفة
    """
    
    def setUp(self):
        """إعداد البيانات للاختبار"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        self.customer = Customer.objects.create(
            name='عميل تجريبي',
            phone='01234567890'
        )
        
        self.order = PrintingOrder.objects.create(
            customer=self.customer,
            title='طلب تجريبي',
            order_type='book',
            quantity=100,
            created_by=self.user
        )
    
    def test_create_cost_calculation(self):
        """اختبار إنشاء حساب تكلفة"""
        calculation = CostCalculation.objects.create(
            order=self.order,
            calculation_type='material',
            base_cost=Decimal('100.00'),
            additional_costs=Decimal('20.00'),
            created_by=self.user
        )
        
        self.assertEqual(calculation.order, self.order)
        self.assertEqual(calculation.calculation_type, 'material')
        self.assertEqual(calculation.total_cost, Decimal('120.00'))
    
    def test_unique_current_calculation(self):
        """اختبار فرادة الحساب الحالي"""
        # إنشاء حساب أول
        calc1 = CostCalculation.objects.create(
            order=self.order,
            calculation_type='material',
            base_cost=Decimal('100.00'),
            is_current=True,
            created_by=self.user
        )
        
        # إنشاء حساب ثاني من نفس النوع
        calc2 = CostCalculation.objects.create(
            order=self.order,
            calculation_type='material',
            base_cost=Decimal('150.00'),
            is_current=True,
            created_by=self.user
        )
        
        # التحقق من أن الحساب الأول لم يعد حالياً
        calc1.refresh_from_db()
        self.assertFalse(calc1.is_current)
        self.assertTrue(calc2.is_current)


class OrderSummaryModelTest(TestCase):
    """
    اختبارات نموذج ملخص الطلب
    """
    
    def setUp(self):
        """إعداد البيانات للاختبار"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        self.customer = Customer.objects.create(
            name='عميل تجريبي',
            phone='01234567890'
        )
        
        self.order = PrintingOrder.objects.create(
            customer=self.customer,
            title='طلب تجريبي',
            order_type='book',
            quantity=100,
            created_by=self.user
        )
    
    def test_create_order_summary(self):
        """اختبار إنشاء ملخص الطلب"""
        summary = OrderSummary.objects.create(
            order=self.order,
            material_cost=Decimal('100.00'),
            printing_cost=Decimal('200.00'),
            finishing_cost=Decimal('50.00'),
            profit_margin_percentage=Decimal('20.00')
        )
        
        self.assertEqual(summary.order, self.order)
        self.assertEqual(summary.material_cost, Decimal('100.00'))
    
    def test_calculate_all(self):
        """اختبار حساب جميع القيم"""
        summary = OrderSummary.objects.create(
            order=self.order,
            material_cost=Decimal('100.00'),
            printing_cost=Decimal('200.00'),
            finishing_cost=Decimal('50.00'),
            design_cost=Decimal('30.00'),
            discount_amount=Decimal('20.00'),
            tax_amount=Decimal('15.00'),
            rush_fee=Decimal('10.00'),
            profit_margin_percentage=Decimal('20.00')
        )
        
        summary.calculate_all()
        
        # المجموع الفرعي: 100 + 200 + 50 + 30 = 380
        self.assertEqual(summary.subtotal, Decimal('380.00'))
        
        # إجمالي التكلفة: 380 - 20 + 15 + 10 = 385
        self.assertEqual(summary.total_cost, Decimal('385.00'))
        
        # الربح: 385 * 0.20 = 77
        self.assertEqual(summary.profit_amount, Decimal('77.00'))
        
        # السعر النهائي: 385 + 77 = 462
        self.assertEqual(summary.final_price, Decimal('462.00'))
