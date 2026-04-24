"""
اختبارات شاملة لنماذج العملاء (Forms)
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from decimal import Decimal

from ..models import Customer
from ..forms import CustomerForm, CustomerAccountChangeForm

User = get_user_model()


class CustomerFormTest(TestCase):
    """اختبارات نموذج العميل"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.user = User.objects.create_user(
            username="testuser",
            password="test123"
        )
        
    # ==================== اختبارات النموذج الصحيح ====================
    
    def test_valid_customer_form(self):
        """اختبار نموذج صحيح"""
        form_data = {
            'name': 'عميل جديد',
            'code': 'NEW001',
            'phone': '+201234567890',
            'email': 'new@test.com',
            'address': 'القاهرة',
            'credit_limit': '10000.00',
            'tax_number': 'TAX123',
            'is_active': True,
            'notes': 'عميل مهم'
        }
        
        form = CustomerForm(data=form_data)
        self.assertTrue(form.is_valid())
        
    def test_form_saves_correctly(self):
        """اختبار حفظ النموذج بشكل صحيح"""
        form_data = {
            'name': 'عميل الحفظ',
            'code': 'SAVE001',
            'phone': '+201234567890',
            'email': 'save@test.com',
            'credit_limit': '5000.00',
            'is_active': True
        }
        
        form = CustomerForm(data=form_data)
        self.assertTrue(form.is_valid())
        
        customer = form.save()
        self.assertEqual(customer.name, 'عميل الحفظ')
        self.assertEqual(customer.code, 'SAVE001')
        self.assertEqual(customer.credit_limit, Decimal('5000.00'))
        
    # ==================== اختبارات الحقول المطلوبة ====================
    
    def test_name_required(self):
        """اختبار أن الاسم مطلوب"""
        form_data = {
            'code': 'NONAME001',
            'is_active': True
        }
        
        form = CustomerForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)
        
    def test_code_required(self):
        """اختبار أن الكود مطلوب"""
        form_data = {
            'name': 'عميل بدون كود',
            'is_active': True
        }
        
        form = CustomerForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('code', form.errors)
        
    # ==================== اختبارات clean_code ====================
    
    def test_unique_code_validation_on_create(self):
        """اختبار التحقق من فرادة الكود عند الإنشاء"""
        # إنشاء عميل موجود
        Customer.objects.create(
            name='عميل موجود',
            code='EXIST001'
        )
        
        # محاولة إنشاء عميل بنفس الكود
        form_data = {
            'name': 'عميل جديد',
            'code': 'EXIST001',
            'is_active': True
        }
        
        form = CustomerForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('code', form.errors)
        self.assertIn('مستخدم من قبل', str(form.errors['code']))
        
    def test_unique_code_validation_on_update(self):
        """اختبار التحقق من فرادة الكود عند التعديل"""
        # إنشاء عميلين
        customer1 = Customer.objects.create(
            name='عميل 1',
            code='CUST001'
        )
        customer2 = Customer.objects.create(
            name='عميل 2',
            code='CUST002'
        )
        
        # محاولة تعديل customer2 ليستخدم كود customer1
        form_data = {
            'name': 'عميل 2 محدث',
            'code': 'CUST001',  # كود موجود مسبقاً
            'is_active': True
        }
        
        form = CustomerForm(data=form_data, instance=customer2)
        self.assertFalse(form.is_valid())
        self.assertIn('code', form.errors)
        
    def test_same_code_on_update_allowed(self):
        """اختبار أن نفس الكود مسموح عند التعديل"""
        customer = Customer.objects.create(
            name='عميل',
            code='SAME001'
        )
        
        # تعديل العميل بنفس الكود
        form_data = {
            'name': 'عميل محدث',
            'code': 'SAME001',  # نفس الكود
            'phone': '',
            'address': '',
            'email': '',
            'credit_limit': '0',
            'tax_number': '',
            'notes': '',
            'is_active': True
        }
        
        form = CustomerForm(data=form_data, instance=customer)
        if not form.is_valid():
            print("Form errors:", form.errors)
        self.assertTrue(form.is_valid())
        
    # ==================== اختبارات التحقق من البيانات ====================
    
    def test_invalid_email(self):
        """اختبار بريد إلكتروني غير صحيح"""
        form_data = {
            'name': 'عميل',
            'code': 'EMAIL001',
            'email': 'invalid-email',  # بريد غير صحيح
            'is_active': True
        }
        
        form = CustomerForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)
        
    def test_valid_email(self):
        """اختبار بريد إلكتروني صحيح"""
        form_data = {
            'name': 'عميل',
            'code': 'EMAIL002',
            'phone': '',
            'address': '',
            'email': 'valid@test.com',
            'credit_limit': '0',
            'tax_number': '',
            'notes': '',
            'is_active': True
        }
        
        form = CustomerForm(data=form_data)
        if not form.is_valid():
            print("Form errors:", form.errors)
        self.assertTrue(form.is_valid())
        
    def test_negative_credit_limit(self):
        """اختبار حد ائتمان سالب"""
        form_data = {
            'name': 'عميل',
            'code': 'NEG001',
            'credit_limit': '-1000.00',  # قيمة سالبة
            'is_active': True
        }
        
        form = CustomerForm(data=form_data)
        # Django يسمح بالقيم السالبة في DecimalField
        # لكن يمكن إضافة validator مخصص إذا لزم الأمر
        self.assertTrue(form.is_valid())
        
    # ==================== اختبارات الحقول الاختيارية ====================
    
    def test_optional_fields_can_be_empty(self):
        """اختبار أن الحقول الاختيارية يمكن أن تكون فارغة"""
        form_data = {
            'name': 'عميل بسيط',
            'code': 'SIMPLE001',
            'phone': '',
            'address': '',
            'email': '',
            'credit_limit': '0',
            'tax_number': '',
            'notes': '',
            'is_active': True
        }
        
        form = CustomerForm(data=form_data)
        if not form.is_valid():
            print("Form errors:", form.errors)
        self.assertTrue(form.is_valid())
        
        customer = form.save()
        self.assertEqual(customer.phone, '')
        self.assertEqual(customer.credit_limit, Decimal('0'))
        
    # ==================== اختبارات الـ Widgets ====================
    
    def test_form_widgets_classes(self):
        """اختبار أن الـ widgets تحتوي على الـ classes الصحيحة"""
        form = CustomerForm()
        
        self.assertIn('form-control', form.fields['name'].widget.attrs['class'])
        self.assertIn('form-control', form.fields['phone'].widget.attrs['class'])
        self.assertIn('form-control', form.fields['email'].widget.attrs['class'])
        
    def test_phone_field_direction(self):
        """اختبار أن حقل الهاتف له اتجاه ltr"""
        form = CustomerForm()
        self.assertEqual(form.fields['phone'].widget.attrs['dir'], 'ltr')
        
    def test_email_field_direction(self):
        """اختبار أن حقل البريد له اتجاه ltr"""
        form = CustomerForm()
        self.assertEqual(form.fields['email'].widget.attrs['dir'], 'ltr')


class CustomerAccountChangeFormTest(TestCase):
    """اختبارات نموذج تغيير الحساب المحاسبي"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.customer = Customer.objects.create(
            name='عميل الاختبار',
            code='TEST001'
        )
        
    def test_form_only_has_financial_account_field(self):
        """اختبار أن النموذج يحتوي فقط على حقل الحساب المحاسبي"""
        form = CustomerAccountChangeForm(instance=self.customer)
        self.assertEqual(len(form.fields), 1)
        self.assertIn('financial_account', form.fields)
        
    def test_form_widget_has_select2_class(self):
        """اختبار أن الـ widget يحتوي على select2"""
        form = CustomerAccountChangeForm(instance=self.customer)
        widget_attrs = form.fields['financial_account'].widget.attrs
        
        self.assertIn('form-control', widget_attrs['class'])
        self.assertIn('select2-search', widget_attrs['class'])
        
    def test_form_placeholder(self):
        """اختبار placeholder الحقل"""
        form = CustomerAccountChangeForm(instance=self.customer)
        widget_attrs = form.fields['financial_account'].widget.attrs
        
        self.assertIn('data-placeholder', widget_attrs)
        self.assertIn('ابحث واختر', widget_attrs['data-placeholder'])


class CustomerFormIntegrationTest(TestCase):
    """اختبارات تكامل النماذج"""
    
    def test_create_and_update_customer_via_form(self):
        """اختبار إنشاء وتعديل عميل عبر النموذج"""
        # إنشاء
        create_data = {
            'name': 'عميل التكامل',
            'code': 'INT001',
            'phone': '+201234567890',
            'email': 'integration@test.com',
            'credit_limit': '15000.00',
            'is_active': True
        }
        
        create_form = CustomerForm(data=create_data)
        self.assertTrue(create_form.is_valid())
        customer = create_form.save()
        
        # التحقق من الإنشاء
        self.assertEqual(customer.name, 'عميل التكامل')
        self.assertEqual(customer.code, 'INT001')
        
        # التعديل
        update_data = {
            'name': 'عميل التكامل المحدث',
            'code': 'INT001',  # نفس الكود
            'phone': '+201098765432',
            'email': 'updated@test.com',
            'credit_limit': '20000.00',
            'is_active': True
        }
        
        update_form = CustomerForm(data=update_data, instance=customer)
        self.assertTrue(update_form.is_valid())
        updated_customer = update_form.save()
        
        # التحقق من التعديل
        self.assertEqual(updated_customer.name, 'عميل التكامل المحدث')
        self.assertEqual(updated_customer.phone, '+201098765432')
        self.assertEqual(updated_customer.credit_limit, Decimal('20000.00'))
        self.assertEqual(Customer.objects.count(), 1)  # لم يتم إنشاء عميل جديد
