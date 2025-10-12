"""
اختبارات شاملة لنماذج نظام التسعير
Comprehensive Tests for Pricing System Forms
"""
import pytest
from django.test import TestCase
from django.contrib.auth.models import User
from decimal import Decimal

from pricing.forms import (
    PricingOrderForm, PricingQuotationForm, OrderSupplierForm,
    InternalContentForm, OrderFinishingForm, ExtraExpenseForm,
    OrderCommentForm, PaperTypeForm, PaperSizeForm, PlateSizeForm,
    CoatingTypeForm, FinishingTypeForm, PrintDirectionForm
)
from pricing.models import (
    PricingOrder, PaperType, PaperSize, PlateSize, 
    CoatingType, FinishingType, PrintDirection
)
from client.models import Client
from supplier.models import Supplier


class PricingOrderFormTestCase(TestCase):
    """اختبارات نموذج طلب التسعير"""
    
    def setUp(self):
        """إعداد البيانات للاختبارات"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        self.client = Client.objects.create(
            name='عميل تجريبي',
            email='client@test.com',
            phone='01234567890'
        )
        
        self.paper_type = PaperType.objects.create(
            name='ورق أبيض',
            weight=80
        )
        
        self.paper_size = PaperSize.objects.create(
            name='A4',
            width=21.0,
            height=29.7
        )
        
    def test_valid_pricing_order_form(self):
        """اختبار نموذج طلب تسعير صحيح"""
        form_data = {
            'client': self.client.id,
            'product_name': 'كتالوج شركة',
            'quantity': 1000,
            'paper_type': self.paper_type.id,
            'paper_size': self.paper_size.id,
            'description': 'كتالوج تعريفي للشركة',
            'colors': 4,
            'pages': 16
        }
        
        form = PricingOrderForm(data=form_data)
        self.assertTrue(form.is_valid())
        
    def test_invalid_pricing_order_form_missing_required(self):
        """اختبار نموذج طلب تسعير مع حقول مطلوبة ناقصة"""
        form_data = {
            'product_name': 'كتالوج شركة',
            # client مفقود
            # quantity مفقود
        }
        
        form = PricingOrderForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('client', form.errors)
        self.assertIn('quantity', form.errors)
        
    def test_invalid_pricing_order_form_negative_quantity(self):
        """اختبار نموذج طلب تسعير مع كمية سالبة"""
        form_data = {
            'client': self.client.id,
            'product_name': 'كتالوج شركة',
            'quantity': -100,  # كمية سالبة
        }
        
        form = PricingOrderForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('quantity', form.errors)
        
    def test_pricing_order_form_save(self):
        """اختبار حفظ نموذج طلب التسعير"""
        form_data = {
            'client': self.client.id,
            'product_name': 'كتالوج شركة',
            'quantity': 1000,
            'description': 'كتالوج تعريفي'
        }
        
        form = PricingOrderForm(data=form_data)
        self.assertTrue(form.is_valid())
        
        order = form.save(commit=False)
        order.created_by = self.user
        order.save()
        
        self.assertEqual(order.client, self.client)
        self.assertEqual(order.product_name, 'كتالوج شركة')
        self.assertEqual(order.quantity, 1000)


class PricingQuotationFormTestCase(TestCase):
    """اختبارات نموذج عرض السعر"""
    
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
        
        self.order = PricingOrder.objects.create(
            client=self.client,
            product_name='كتالوج شركة',
            quantity=1000,
            created_by=self.user
        )
        
    def test_valid_quotation_form(self):
        """اختبار نموذج عرض سعر صحيح"""
        form_data = {
            'order': self.order.id,
            'total_price': Decimal('1500.00'),
            'profit_margin': Decimal('20.00'),
            'notes': 'عرض سعر للكتالوج'
        }
        
        form = PricingQuotationForm(data=form_data)
        self.assertTrue(form.is_valid())
        
    def test_invalid_quotation_form_negative_price(self):
        """اختبار نموذج عرض سعر مع سعر سالب"""
        form_data = {
            'order': self.order.id,
            'total_price': Decimal('-100.00'),  # سعر سالب
            'profit_margin': Decimal('20.00')
        }
        
        form = PricingQuotationForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('total_price', form.errors)


class OrderSupplierFormTestCase(TestCase):
    """اختبارات نموذج مورد الطلب"""
    
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
        
        self.supplier = Supplier.objects.create(
            name='مورد تجريبي',
            email='supplier@test.com'
        )
        
        self.order = PricingOrder.objects.create(
            client=self.client,
            product_name='كتالوج شركة',
            quantity=1000,
            created_by=self.user
        )
        
    def test_valid_order_supplier_form(self):
        """اختبار نموذج مورد طلب صحيح"""
        form_data = {
            'order': self.order.id,
            'supplier': self.supplier.id,
            'service_type': 'printing',
            'cost': Decimal('300.00'),
            'notes': 'خدمة طباعة'
        }
        
        form = OrderSupplierForm(data=form_data)
        self.assertTrue(form.is_valid())
        
    def test_invalid_order_supplier_form_missing_supplier(self):
        """اختبار نموذج مورد طلب مع مورد مفقود"""
        form_data = {
            'order': self.order.id,
            'service_type': 'printing',
            'cost': Decimal('300.00')
            # supplier مفقود
        }
        
        form = OrderSupplierForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('supplier', form.errors)


class InternalContentFormTestCase(TestCase):
    """اختبارات نموذج المحتوى الداخلي"""
    
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
        
        self.order = PricingOrder.objects.create(
            client=self.client,
            product_name='كتالوج شركة',
            quantity=1000,
            created_by=self.user
        )
        
        self.paper_type = PaperType.objects.create(
            name='ورق أبيض',
            weight=80
        )
        
        self.paper_size = PaperSize.objects.create(
            name='A4',
            width=21.0,
            height=29.7
        )
        
    def test_valid_internal_content_form(self):
        """اختبار نموذج محتوى داخلي صحيح"""
        form_data = {
            'order': self.order.id,
            'paper_type': self.paper_type.id,
            'paper_size': self.paper_size.id,
            'pages': 16,
            'colors': 4,
            'description': 'محتوى داخلي للكتالوج'
        }
        
        form = InternalContentForm(data=form_data)
        self.assertTrue(form.is_valid())
        
    def test_invalid_internal_content_form_zero_pages(self):
        """اختبار نموذج محتوى داخلي مع صفر صفحات"""
        form_data = {
            'order': self.order.id,
            'paper_type': self.paper_type.id,
            'paper_size': self.paper_size.id,
            'pages': 0,  # صفر صفحات
            'colors': 4
        }
        
        form = InternalContentForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('pages', form.errors)


class OrderFinishingFormTestCase(TestCase):
    """اختبارات نموذج تشطيب الطلب"""
    
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
        
        self.supplier = Supplier.objects.create(
            name='مورد تجريبي',
            email='supplier@test.com'
        )
        
        self.order = PricingOrder.objects.create(
            client=self.client,
            product_name='كتالوج شركة',
            quantity=1000,
            created_by=self.user
        )
        
        self.finishing_type = FinishingType.objects.create(
            name='تجليد حلزوني',
            price_per_unit=Decimal('2.00')
        )
        
    def test_valid_order_finishing_form(self):
        """اختبار نموذج تشطيب طلب صحيح"""
        form_data = {
            'order': self.order.id,
            'finishing_type': self.finishing_type.id,
            'cost': Decimal('100.00'),
            'supplier': self.supplier.id,
            'notes': 'تجليد حلزوني للكتالوج'
        }
        
        form = OrderFinishingForm(data=form_data)
        self.assertTrue(form.is_valid())
        
    def test_invalid_order_finishing_form_negative_cost(self):
        """اختبار نموذج تشطيب طلب مع تكلفة سالبة"""
        form_data = {
            'order': self.order.id,
            'finishing_type': self.finishing_type.id,
            'cost': Decimal('-50.00'),  # تكلفة سالبة
            'supplier': self.supplier.id
        }
        
        form = OrderFinishingForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('cost', form.errors)


class ExtraExpenseFormTestCase(TestCase):
    """اختبارات نموذج المصروف الإضافي"""
    
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
        
        self.order = PricingOrder.objects.create(
            client=self.client,
            product_name='كتالوج شركة',
            quantity=1000,
            created_by=self.user
        )
        
    def test_valid_extra_expense_form(self):
        """اختبار نموذج مصروف إضافي صحيح"""
        form_data = {
            'order': self.order.id,
            'description': 'مصروف شحن',
            'amount': Decimal('50.00')
        }
        
        form = ExtraExpenseForm(data=form_data)
        self.assertTrue(form.is_valid())
        
    def test_invalid_extra_expense_form_empty_description(self):
        """اختبار نموذج مصروف إضافي مع وصف فارغ"""
        form_data = {
            'order': self.order.id,
            'description': '',  # وصف فارغ
            'amount': Decimal('50.00')
        }
        
        form = ExtraExpenseForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('description', form.errors)


class OrderCommentFormTestCase(TestCase):
    """اختبارات نموذج تعليق الطلب"""
    
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
        
        self.order = PricingOrder.objects.create(
            client=self.client,
            product_name='كتالوج شركة',
            quantity=1000,
            created_by=self.user
        )
        
    def test_valid_order_comment_form(self):
        """اختبار نموذج تعليق طلب صحيح"""
        form_data = {
            'order': self.order.id,
            'comment': 'تعليق على الطلب'
        }
        
        form = OrderCommentForm(data=form_data)
        self.assertTrue(form.is_valid())
        
    def test_invalid_order_comment_form_empty_comment(self):
        """اختبار نموذج تعليق طلب مع تعليق فارغ"""
        form_data = {
            'order': self.order.id,
            'comment': ''  # تعليق فارغ
        }
        
        form = OrderCommentForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('comment', form.errors)


class SettingsFormsTestCase(TestCase):
    """اختبارات نماذج الإعدادات"""
    
    def test_valid_paper_type_form(self):
        """اختبار نموذج نوع ورق صحيح"""
        form_data = {
            'name': 'ورق مقوى',
            'description': 'ورق مقوى للأغلفة',
            'weight': 300,
            'price_per_kg': Decimal('20.00')
        }
        
        form = PaperTypeForm(data=form_data)
        self.assertTrue(form.is_valid())
        
    def test_valid_paper_size_form(self):
        """اختبار نموذج مقاس ورق صحيح"""
        form_data = {
            'name': 'A3',
            'width': 29.7,
            'height': 42.0,
            'description': 'مقاس A3 قياسي'
        }
        
        form = PaperSizeForm(data=form_data)
        self.assertTrue(form.is_valid())
        
    def test_valid_plate_size_form(self):
        """اختبار نموذج مقاس زنك صحيح"""
        form_data = {
            'name': '50x70',
            'width': 50.0,
            'height': 70.0,
            'price': Decimal('150.00')
        }
        
        form = PlateSizeForm(data=form_data)
        self.assertTrue(form.is_valid())
        
    def test_valid_coating_type_form(self):
        """اختبار نموذج نوع طلاء صحيح"""
        form_data = {
            'name': 'لامينيشن مط',
            'description': 'طلاء مط',
            'price_per_sheet': Decimal('0.30')
        }
        
        form = CoatingTypeForm(data=form_data)
        self.assertTrue(form.is_valid())
        
    def test_valid_finishing_type_form(self):
        """اختبار نموذج نوع تشطيب صحيح"""
        form_data = {
            'name': 'تجليد سلك',
            'description': 'تجليد بالسلك',
            'price_per_unit': Decimal('1.50')
        }
        
        form = FinishingTypeForm(data=form_data)
        self.assertTrue(form.is_valid())
        
    def test_valid_print_direction_form(self):
        """اختبار نموذج اتجاه طباعة صحيح"""
        form_data = {
            'name': 'طباعة وجهين',
            'description': 'طباعة على الوجهين'
        }
        
        form = PrintDirectionForm(data=form_data)
        self.assertTrue(form.is_valid())


class FormValidationTestCase(TestCase):
    """اختبارات التحقق من صحة النماذج"""
    
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
        
    def test_form_clean_methods(self):
        """اختبار دوال التحقق المخصصة في النماذج"""
        # اختبار التحقق من الكمية في نموذج طلب التسعير
        form_data = {
            'client': self.client.id,
            'product_name': 'كتالوج شركة',
            'quantity': 0  # كمية صفر
        }
        
        form = PricingOrderForm(data=form_data)
        self.assertFalse(form.is_valid())
        
    def test_form_field_widgets(self):
        """اختبار widgets الحقول في النماذج"""
        form = PricingOrderForm()
        
        # التحقق من وجود widgets مخصصة
        self.assertIn('class', form.fields['description'].widget.attrs)
        self.assertIn('placeholder', form.fields['product_name'].widget.attrs)
        
    def test_form_help_texts(self):
        """اختبار نصوص المساعدة في النماذج"""
        form = PricingOrderForm()
        
        # التحقق من وجود نصوص مساعدة
        self.assertIsNotNone(form.fields['quantity'].help_text)
        self.assertIsNotNone(form.fields['description'].help_text)


class FormRenderingTestCase(TestCase):
    """اختبارات عرض النماذج"""
    
    def test_form_as_p_rendering(self):
        """اختبار عرض النموذج كفقرات"""
        form = PaperTypeForm()
        html = form.as_p()
        
        self.assertIn('<p>', html)
        self.assertIn('name', html)
        self.assertIn('description', html)
        
    def test_form_field_rendering(self):
        """اختبار عرض حقول النموذج"""
        form = PricingOrderForm()
        
        # التحقق من عرض حقل العميل
        client_field = form['client']
        self.assertIn('select', str(client_field))
        
        # التحقق من عرض حقل الكمية
        quantity_field = form['quantity']
        self.assertIn('number', str(quantity_field))


if __name__ == '__main__':
    pytest.main([__file__])
