"""
اختبارات شاملة لنماذج الموردين (بدون تخطي اختبارات)
"""

from django.test import TestCase
from django.contrib.auth import get_user_model

from supplier.models import Supplier, SupplierType
from supplier.forms import SupplierForm, SupplierAccountChangeForm

User = get_user_model()


class SupplierFormTest(TestCase):
    """اختبارات نموذج المورد"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.user = User.objects.create_user(
            username='testuser_supplier_forms',
            password='test123'
        )
        
        # إنشاء نوع مورد
        self.supplier_type = SupplierType.objects.create(
            name="موردي الكتب",
            code="books"
        )
        
    def test_form_valid_data(self):
        """اختبار نموذج بيانات صحيحة"""
        form_data = {
            'name': 'مورد الكتب المصري',
            'code': 'BOOKS001',
            'primary_type': self.supplier_type.id,
            'email': 'supplier@books.com',
            'phone': '+201234567890',
            'address': 'القاهرة، مصر',
            'is_active': True,
        }
        
        form = SupplierForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        
    def test_form_save(self):
        """اختبار حفظ النموذج"""
        form_data = {
            'name': 'مورد اختبار',
            'code': 'TEST001',
            'primary_type': self.supplier_type.id,
            'email': 'test@supplier.com',
            'is_active': True,
        }
        
        form = SupplierForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        supplier = form.save()
        self.assertEqual(supplier.name, 'مورد اختبار')
        self.assertEqual(supplier.code, 'TEST001')
        
    def test_form_required_fields(self):
        """اختبار الحقول المطلوبة"""
        form = SupplierForm(data={})
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)
        
    def test_form_duplicate_code_on_create(self):
        """اختبار منع تكرار الكود عند الإنشاء"""
        Supplier.objects.create(
            name="مورد موجود",
            code="DUP001",
            primary_type=self.supplier_type
        )
        
        form_data = {
            'name': 'مورد جديد',
            'code': 'DUP001',
            'primary_type': self.supplier_type.id,
            'is_active': True
        }
        
        form = SupplierForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('code', form.errors)
        
    def test_form_duplicate_code_on_edit_same_supplier(self):
        """اختبار السماح بنفس الكود عند تعديل نفس المورد"""
        supplier = Supplier.objects.create(
            name="مورد للتعديل",
            code="EDIT001",
            primary_type=self.supplier_type
        )
        
        form_data = {
            'name': 'مورد معدل',
            'code': 'EDIT001',
            'primary_type': self.supplier_type.id,
            'is_active': True,
        }
        
        form = SupplierForm(data=form_data, instance=supplier)
        self.assertTrue(form.is_valid(), form.errors)
        
    def test_form_duplicate_code_on_edit_different_supplier(self):
        """اختبار منع تكرار الكود عند تعديل مورد آخر"""
        Supplier.objects.create(
            name="مورد 1",
            code="SUP001",
            primary_type=self.supplier_type
        )
        
        supplier2 = Supplier.objects.create(
            name="مورد 2",
            code="SUP002",
            primary_type=self.supplier_type
        )
        
        form_data = {
            'name': 'مورد 2 معدل',
            'code': 'SUP001',
            'primary_type': self.supplier_type.id,
            'is_active': True
        }
        
        form = SupplierForm(data=form_data, instance=supplier2)
        self.assertFalse(form.is_valid())
        self.assertIn('code', form.errors)
        
    def test_form_valid_email(self):
        """اختبار بريد إلكتروني صحيح"""
        form_data = {
            'name': 'مورد',
            'code': 'TEST003',
            'primary_type': self.supplier_type.id,
            'email': 'valid@email.com',
            'is_active': True,
        }
        
        form = SupplierForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        
    def test_form_optional_fields_can_be_empty(self):
        """اختبار أن الحقول الاختيارية يمكن أن تكون فارغة"""
        form_data = {
            'name': 'مورد',
            'code': 'TEST004',
            'primary_type': self.supplier_type.id,
            'is_active': True,
        }
        
        form = SupplierForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        
    def test_form_widgets_have_correct_classes(self):
        """اختبار أن الـ widgets تحتوي على classes صحيحة"""
        form = SupplierForm()
        self.assertIn('form-control', form.fields['name'].widget.attrs.get('class', ''))
        self.assertIn('form-control', form.fields['code'].widget.attrs.get('class', ''))
        
    def test_form_phone_field_has_ltr_direction(self):
        """اختبار أن حقل الهاتف له اتجاه ltr"""
        form = SupplierForm()
        self.assertEqual(form.fields['phone'].widget.attrs.get('dir'), 'ltr')
        
    def test_form_with_supplier_types(self):
        """اختبار النموذج مع أنواع الموردين"""
        form_data = {
            'name': 'مورد متعدد',
            'code': 'MULTI001',
            'primary_type': self.supplier_type.id,
            'is_active': True
        }
        
        form = SupplierForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        supplier = form.save()
        self.assertEqual(supplier.primary_type, self.supplier_type)


class SupplierAccountChangeFormTest(TestCase):
    """اختبارات نموذج تغيير الحساب المحاسبي"""
    
    def setUp(self):
        self.supplier_type = SupplierType.objects.create(name="عام", code="gen_acc")
        self.supplier = Supplier.objects.create(
            name="مورد اختبار",
            code="TEST001_ACC",
            primary_type=self.supplier_type
        )
        
    def test_form_has_only_financial_account_field(self):
        form = SupplierAccountChangeForm(instance=self.supplier)
        self.assertEqual(len(form.fields), 1)
        self.assertIn('financial_account', form.fields)


class FormIntegrationTest(TestCase):
    """اختبارات تكامل النماذج"""
    
    def setUp(self):
        self.supplier_type = SupplierType.objects.create(name="عام", code="gen_integ")

    def test_create_and_edit_supplier_through_form(self):
        create_data = {
            'name': 'مورد جديد',
            'code': 'NEW001',
            'primary_type': self.supplier_type.id,
            'email': 'new@supplier.com',
            'phone': '+201234567890',
            'is_active': True,
        }
        
        create_form = SupplierForm(data=create_data)
        self.assertTrue(create_form.is_valid(), create_form.errors)
        supplier = create_form.save()
        supplier.refresh_from_db()
        
        self.assertEqual(supplier.name, 'مورد جديد')
        
        edit_data = {
            'name': 'مورد معدل',
            'code': 'NEW001',
            'primary_type': self.supplier_type.id,
            'email': 'updated@supplier.com',
            'is_active': True
        }
        
        edit_form = SupplierForm(data=edit_data, instance=supplier)
        self.assertTrue(edit_form.is_valid(), edit_form.errors)
        updated_supplier = edit_form.save()
        
        self.assertEqual(updated_supplier.name, 'مورد معدل')
        self.assertEqual(updated_supplier.email, 'updated@supplier.com')
