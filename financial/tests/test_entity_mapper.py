"""
اختبارات خدمة EntityAccountMapper
"""

import pytest
from django.test import TestCase
from financial.services.entity_mapper import EntityAccountMapper


class TestEntityAccountMapper(TestCase):
    """اختبارات خدمة ربط الكيانات بالحسابات المحاسبية"""
    
    def test_entity_account_fields_defined(self):
        """اختبار أن قاموس ENTITY_ACCOUNT_FIELDS محدد بشكل صحيح"""
        self.assertIsNotNone(EntityAccountMapper.ENTITY_ACCOUNT_FIELDS)
        
        # التحقق من وجود الأنواع المدعومة فقط
        expected_types = ['supplier', 'employee']
        for entity_type in expected_types:
            self.assertIn(entity_type, EntityAccountMapper.ENTITY_ACCOUNT_FIELDS)
    
    def test_model_to_entity_type_mapping(self):
        """اختبار أن خريطة MODEL_TO_ENTITY_TYPE محددة بشكل صحيح"""
        self.assertIsNotNone(EntityAccountMapper.MODEL_TO_ENTITY_TYPE)
        
        # التحقق من وجود النماذج المدعومة فقط
        expected_models = ['Supplier', 'Employee']
        for model_name in expected_models:
            self.assertIn(model_name, EntityAccountMapper.MODEL_TO_ENTITY_TYPE)
    
    def test_get_supported_entity_types(self):
        """اختبار الحصول على قائمة أنواع الكيانات المدعومة"""
        supported_types = EntityAccountMapper.get_supported_entity_types()
        
        self.assertGreater(len(supported_types), 0)
        self.assertIn('supplier', supported_types)
    
    def test_is_entity_type_supported(self):
        """اختبار التحقق من دعم نوع كيان معين"""
        self.assertTrue(EntityAccountMapper.is_entity_type_supported('supplier'))
        self.assertTrue(EntityAccountMapper.is_entity_type_supported('employee'))
        
        # أنواع غير مدعومة
        self.assertFalse(EntityAccountMapper.is_entity_type_supported('unknown'))
        self.assertFalse(EntityAccountMapper.is_entity_type_supported('student'))
        self.assertFalse(EntityAccountMapper.is_entity_type_supported('parent'))
    
    def test_detect_entity_type_with_none(self):
        """اختبار استنتاج نوع الكيان مع None"""
        entity_type = EntityAccountMapper.detect_entity_type(None)
        self.assertIsNone(entity_type)
    
    def test_get_account_with_none_entity(self):
        """اختبار الحصول على الحساب المحاسبي مع كيان None"""
        account = EntityAccountMapper.get_account(None)
        self.assertIsNone(account)
    
    def test_validate_entity_account_with_none(self):
        """اختبار التحقق من الحساب المحاسبي مع كيان None"""
        is_valid, message = EntityAccountMapper.validate_entity_account(None)
        self.assertFalse(is_valid)
        self.assertEqual(message, "الكيان غير موجود")
    
    def test_get_entity_info_structure(self):
        """اختبار بنية معلومات الكيان"""
        info = EntityAccountMapper.get_entity_info(None)
        
        expected_keys = ['entity', 'entity_type', 'entity_name', 'model_name', 'account', 'account_field_path', 'has_account']
        for key in expected_keys:
            self.assertIn(key, info)
        
        self.assertIsNone(info['entity'])
        self.assertIsNone(info['entity_type'])
        self.assertIsNone(info['account'])
        self.assertFalse(info['has_account'])


class TestEntityAccountMapperIntegration(TestCase):
    """اختبارات التكامل لخدمة EntityAccountMapper"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        from financial.models import ChartOfAccounts, AccountType
        from supplier.models import Supplier
        
        self.account_type = AccountType.objects.create(
            code='1000',
            name='أصول',
            category='asset'
        )
        
        self.chart_account = ChartOfAccounts.objects.create(
            code='1001',
            name='حساب اختبار',
            account_type=self.account_type,
            is_active=True,
            is_leaf=True
        )
        
        self.supplier_with_account = Supplier.objects.create(
            name='مورد اختبار',
            code='SUP001',
            phone='01234567892',
            financial_account=self.chart_account
        )
    
    def test_detect_entity_type_supplier(self):
        """اختبار استنتاج نوع الكيان للمورد"""
        entity_type = EntityAccountMapper.detect_entity_type(self.supplier_with_account)
        self.assertEqual(entity_type, 'supplier')
    
    def test_get_account_supplier_with_account(self):
        """اختبار الحصول على الحساب المحاسبي لمورد لديه حساب"""
        account = EntityAccountMapper.get_account(self.supplier_with_account, 'supplier')
        self.assertIsNotNone(account)
        self.assertEqual(account, self.chart_account)
    
    def test_get_account_with_auto_detection(self):
        """اختبار الحصول على الحساب المحاسبي مع الاستنتاج التلقائي"""
        account = EntityAccountMapper.get_account(self.supplier_with_account)
        self.assertIsNotNone(account)
        self.assertEqual(account, self.chart_account)
    
    def test_validate_entity_account_supplier_with_account(self):
        """اختبار التحقق من الحساب المحاسبي لمورد لديه حساب"""
        is_valid, message = EntityAccountMapper.validate_entity_account(self.supplier_with_account)
        self.assertTrue(is_valid)
        self.assertIn("موجود وصحيح", message)
