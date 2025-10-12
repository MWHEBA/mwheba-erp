"""
اختبارات شاملة لنماذج نظام التسعير
Comprehensive Tests for Pricing System Models
"""
import pytest
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from decimal import Decimal
from datetime import date, datetime, timedelta

from pricing.models import (
    PricingOrder, PaperType, PaperSize, PlateSize, CoatingType, 
    FinishingType, PrintDirection, PricingQuotation, OrderSupplier,
    InternalContent, OrderFinishing, ExtraExpense, OrderComment,
    PricingApproval, PricingApprovalWorkflow
)
from client.models import Client
from supplier.models import Supplier


class PricingModelsTestCase(TestCase):
    """اختبارات النماذج الأساسية لنظام التسعير"""
    
    def setUp(self):
        """إعداد البيانات للاختبارات"""
        # إنشاء مستخدم للاختبار
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # إنشاء عميل للاختبار
        self.client = Client.objects.create(
            name='عميل تجريبي',
            email='client@test.com',
            phone='01234567890'
        )
        
        # إنشاء مورد للاختبار
        self.supplier = Supplier.objects.create(
            name='مورد تجريبي',
            email='supplier@test.com',
            phone='01234567890'
        )
        
        # إنشاء البيانات المرجعية
        self.paper_type = PaperType.objects.create(
            name='ورق أبيض',
            description='ورق أبيض عادي'
        )
        
        self.paper_size = PaperSize.objects.create(
            name='A4',
            width=21.0,
            height=29.7
        )
        
        self.plate_size = PlateSize.objects.create(
            name='70x100',
            width=70.0,
            height=100.0
        )
        
        self.coating_type = CoatingType.objects.create(
            name='لامينيشن لامع',
            description='طلاء لامع'
        )
        
        self.finishing_type = FinishingType.objects.create(
            name='تجليد حلزوني',
            description='تجليد بالحلزون'
        )
        
        self.print_direction = PrintDirection.objects.create(
            name='طباعة وجه واحد',
            description='طباعة على وجه واحد فقط'
        )

    def test_pricing_order_creation(self):
        """اختبار إنشاء طلب تسعير"""
        order = PricingOrder.objects.create(
            client=self.client,
            product_name='كتالوج شركة',
            quantity=1000,
            created_by=self.user
        )
        
        self.assertEqual(order.client, self.client)
        self.assertEqual(order.product_name, 'كتالوج شركة')
        self.assertEqual(order.quantity, 1000)
        self.assertEqual(order.status, 'draft')
        self.assertEqual(order.created_by, self.user)
        self.assertIsNotNone(order.created_at)
        
    def test_pricing_order_str_method(self):
        """اختبار دالة __str__ لطلب التسعير"""
        order = PricingOrder.objects.create(
            client=self.client,
            product_name='كتالوج شركة',
            quantity=1000,
            created_by=self.user
        )
        
        expected_str = f"طلب تسعير #{order.id} - كتالوج شركة"
        self.assertEqual(str(order), expected_str)
        
    def test_pricing_order_validation(self):
        """اختبار التحقق من صحة بيانات طلب التسعير"""
        # اختبار الكمية السالبة
        with self.assertRaises(ValidationError):
            order = PricingOrder(
                client=self.client,
                product_name='كتالوج شركة',
                quantity=-100,
                created_by=self.user
            )
            order.full_clean()
            
    def test_pricing_order_total_cost_calculation(self):
        """اختبار حساب التكلفة الإجمالية"""
        order = PricingOrder.objects.create(
            client=self.client,
            product_name='كتالوج شركة',
            quantity=1000,
            paper_cost=Decimal('500.00'),
            printing_cost=Decimal('300.00'),
            finishing_cost=Decimal('200.00'),
            created_by=self.user
        )
        
        expected_total = Decimal('1000.00')
        self.assertEqual(order.total_cost, expected_total)
        
    def test_paper_type_creation(self):
        """اختبار إنشاء نوع ورق"""
        paper_type = PaperType.objects.create(
            name='ورق مقوى',
            description='ورق مقوى للأغلفة',
            weight=300
        )
        
        self.assertEqual(paper_type.name, 'ورق مقوى')
        self.assertEqual(paper_type.weight, 300)
        self.assertTrue(paper_type.is_active)
        
    def test_paper_size_creation(self):
        """اختبار إنشاء مقاس ورق"""
        paper_size = PaperSize.objects.create(
            name='A3',
            width=29.7,
            height=42.0
        )
        
        self.assertEqual(paper_size.name, 'A3')
        self.assertEqual(paper_size.width, 29.7)
        self.assertEqual(paper_size.height, 42.0)
        
    def test_plate_size_creation(self):
        """اختبار إنشاء مقاس زنك"""
        plate_size = PlateSize.objects.create(
            name='50x70',
            width=50.0,
            height=70.0,
            price=Decimal('150.00')
        )
        
        self.assertEqual(plate_size.name, '50x70')
        self.assertEqual(plate_size.price, Decimal('150.00'))
        
    def test_internal_content_creation(self):
        """اختبار إنشاء محتوى داخلي"""
        order = PricingOrder.objects.create(
            client=self.client,
            product_name='كتالوج شركة',
            quantity=1000,
            created_by=self.user
        )
        
        internal_content = InternalContent.objects.create(
            order=order,
            paper_type=self.paper_type,
            paper_size=self.paper_size,
            pages=16,
            colors=4
        )
        
        self.assertEqual(internal_content.order, order)
        self.assertEqual(internal_content.pages, 16)
        self.assertEqual(internal_content.colors, 4)
        
    def test_order_finishing_creation(self):
        """اختبار إنشاء خدمة تشطيب"""
        order = PricingOrder.objects.create(
            client=self.client,
            product_name='كتالوج شركة',
            quantity=1000,
            created_by=self.user
        )
        
        finishing = OrderFinishing.objects.create(
            order=order,
            finishing_type=self.finishing_type,
            cost=Decimal('100.00'),
            supplier=self.supplier
        )
        
        self.assertEqual(finishing.order, order)
        self.assertEqual(finishing.cost, Decimal('100.00'))
        self.assertEqual(finishing.supplier, self.supplier)
        
    def test_extra_expense_creation(self):
        """اختبار إنشاء مصروف إضافي"""
        order = PricingOrder.objects.create(
            client=self.client,
            product_name='كتالوج شركة',
            quantity=1000,
            created_by=self.user
        )
        
        expense = ExtraExpense.objects.create(
            order=order,
            description='مصروف شحن',
            amount=Decimal('50.00')
        )
        
        self.assertEqual(expense.order, order)
        self.assertEqual(expense.description, 'مصروف شحن')
        self.assertEqual(expense.amount, Decimal('50.00'))
        
    def test_order_comment_creation(self):
        """اختبار إنشاء تعليق على الطلب"""
        order = PricingOrder.objects.create(
            client=self.client,
            product_name='كتالوج شركة',
            quantity=1000,
            created_by=self.user
        )
        
        comment = OrderComment.objects.create(
            order=order,
            comment='تعليق تجريبي',
            created_by=self.user
        )
        
        self.assertEqual(comment.order, order)
        self.assertEqual(comment.comment, 'تعليق تجريبي')
        self.assertEqual(comment.created_by, self.user)
        
    def test_pricing_quotation_creation(self):
        """اختبار إنشاء عرض سعر"""
        order = PricingOrder.objects.create(
            client=self.client,
            product_name='كتالوج شركة',
            quantity=1000,
            created_by=self.user
        )
        
        quotation = PricingQuotation.objects.create(
            order=order,
            total_price=Decimal('1500.00'),
            profit_margin=Decimal('20.00'),
            valid_until=date.today() + timedelta(days=30),
            created_by=self.user
        )
        
        self.assertEqual(quotation.order, order)
        self.assertEqual(quotation.total_price, Decimal('1500.00'))
        self.assertEqual(quotation.profit_margin, Decimal('20.00'))
        
    def test_order_supplier_creation(self):
        """اختبار إنشاء مورد للطلب"""
        order = PricingOrder.objects.create(
            client=self.client,
            product_name='كتالوج شركة',
            quantity=1000,
            created_by=self.user
        )
        
        order_supplier = OrderSupplier.objects.create(
            order=order,
            supplier=self.supplier,
            service_type='printing',
            cost=Decimal('300.00')
        )
        
        self.assertEqual(order_supplier.order, order)
        self.assertEqual(order_supplier.supplier, self.supplier)
        self.assertEqual(order_supplier.service_type, 'printing')
        
    def test_pricing_approval_workflow(self):
        """اختبار سير عمل الموافقات"""
        workflow = PricingApprovalWorkflow.objects.create(
            name='سير موافقة عادي',
            description='سير موافقة للطلبات العادية',
            created_by=self.user
        )
        
        self.assertEqual(workflow.name, 'سير موافقة عادي')
        self.assertTrue(workflow.is_active)
        
    def test_pricing_approval_creation(self):
        """اختبار إنشاء موافقة"""
        order = PricingOrder.objects.create(
            client=self.client,
            product_name='كتالوج شركة',
            quantity=1000,
            created_by=self.user
        )
        
        workflow = PricingApprovalWorkflow.objects.create(
            name='سير موافقة عادي',
            created_by=self.user
        )
        
        approval = PricingApproval.objects.create(
            order=order,
            workflow=workflow,
            approver=self.user,
            level=1
        )
        
        self.assertEqual(approval.order, order)
        self.assertEqual(approval.workflow, workflow)
        self.assertEqual(approval.approver, self.user)
        self.assertEqual(approval.status, 'pending')


class PricingCalculationTestCase(TestCase):
    """اختبارات حسابات التسعير"""
    
    def setUp(self):
        """إعداد البيانات للاختبارات"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        self.client = Client.objects.create(
            name='عميل تجريبي',
            email='client@test.com'
        )
        
    def test_total_cost_calculation(self):
        """اختبار حساب التكلفة الإجمالية"""
        order = PricingOrder.objects.create(
            client=self.client,
            product_name='كتالوج',
            quantity=1000,
            paper_cost=Decimal('500.00'),
            printing_cost=Decimal('300.00'),
            finishing_cost=Decimal('200.00'),
            plate_cost=Decimal('100.00'),
            created_by=self.user
        )
        
        # التكلفة الإجمالية = تكلفة الورق + تكلفة الطباعة + تكلفة التشطيب + تكلفة الزنكات
        expected_total = Decimal('1100.00')
        self.assertEqual(order.total_cost, expected_total)
        
    def test_profit_calculation(self):
        """اختبار حساب الربح"""
        order = PricingOrder.objects.create(
            client=self.client,
            product_name='كتالوج',
            quantity=1000,
            paper_cost=Decimal('500.00'),
            printing_cost=Decimal('300.00'),
            finishing_cost=Decimal('200.00'),
            profit_margin=Decimal('20.00'),  # 20%
            created_by=self.user
        )
        
        total_cost = order.total_cost  # 1000.00
        expected_profit = total_cost * (order.profit_margin / 100)  # 200.00
        expected_selling_price = total_cost + expected_profit  # 1200.00
        
        self.assertEqual(order.profit_amount, expected_profit)
        self.assertEqual(order.selling_price, expected_selling_price)


class PricingStatusTestCase(TestCase):
    """اختبارات حالات طلبات التسعير"""
    
    def setUp(self):
        """إعداد البيانات للاختبارات"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        self.client = Client.objects.create(
            name='عميل تجريبي',
            email='client@test.com'
        )
        
    def test_order_status_transitions(self):
        """اختبار تغيير حالات الطلب"""
        order = PricingOrder.objects.create(
            client=self.client,
            product_name='كتالوج',
            quantity=1000,
            created_by=self.user
        )
        
        # الحالة الافتراضية
        self.assertEqual(order.status, 'draft')
        
        # تغيير إلى قيد المراجعة
        order.status = 'pending'
        order.save()
        self.assertEqual(order.status, 'pending')
        
        # تغيير إلى معتمد
        order.status = 'approved'
        order.save()
        self.assertEqual(order.status, 'approved')
        
        # تغيير إلى مكتمل
        order.status = 'completed'
        order.save()
        self.assertEqual(order.status, 'completed')


if __name__ == '__main__':
    pytest.main([__file__])
