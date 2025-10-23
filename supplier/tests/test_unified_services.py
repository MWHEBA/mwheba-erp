"""
اختبارات النظام الموحد للخدمات المتخصصة
"""

from django.test import TestCase
from decimal import Decimal

from ..forms.service_form_factory import ServiceFormFactory
from ..models import SupplierType, Supplier


class UnifiedServicesTest(TestCase):
    """اختبارات النظام الموحد للخدمات"""
    
    fixtures = [
        'supplier/fixtures/supplier_types.json',
        'printing_pricing/fixtures/initial_data.json'
    ]
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.factory = ServiceFormFactory()
        
    def test_unified_paper_choices(self):
        """اختبار خيارات الورق الموحدة"""
        choices = self.factory.get_unified_paper_choices()
        
        # التحقق من وجود الخيارات الأساسية
        self.assertIn('paper_types', choices)
        self.assertIn('paper_weights', choices)
        self.assertIn('paper_sizes', choices)
        self.assertIn('paper_origins', choices)
        
        # التحقق من أن الخيارات ليست فارغة
        if choices['paper_types']:
            self.assertIsInstance(choices['paper_types'], list)
            
    def test_unified_offset_choices(self):
        """اختبار خيارات الأوفست الموحدة"""
        choices = self.factory.get_unified_offset_choices()
        
        # التحقق من وجود الخيارات الأساسية
        self.assertIn('machine_types', choices)
        self.assertIn('sheet_sizes', choices)
        
    def test_unified_ctp_choices(self):
        """اختبار خيارات الزنكات الموحدة"""
        choices = self.factory.get_unified_ctp_choices()
        
        # التحقق من وجود خيارات مقاسات الزنكات
        self.assertIn('plate_sizes', choices)
        
    def test_normalize_legacy_paper_data(self):
        """اختبار تطبيع بيانات الورق القديمة"""
        legacy_data = {
            'paper_type': 'coated',
            'sheet_size': 'full_70x100'
        }
        
        normalized = self.factory.normalize_legacy_paper_data(legacy_data)
        
        # التحقق من تحويل البيانات القديمة
        self.assertEqual(normalized.get('paper_type'), 'كوشيه')
        self.assertEqual(normalized.get('sheet_size'), '70.00x100.00')
        
    def test_normalize_legacy_offset_data(self):
        """اختبار تطبيع بيانات الأوفست القديمة"""
        legacy_data = {
            'machine_type': 'heidelberg_sm52',
            'sheet_size': '35x50'
        }
        
        normalized = self.factory.normalize_legacy_offset_data(legacy_data)
        
        # التحقق من تحويل البيانات القديمة
        self.assertEqual(normalized.get('machine_type'), 'sm52')
        self.assertEqual(normalized.get('sheet_size'), 'quarter_sheet')
        
    def test_normalize_legacy_ctp_data(self):
        """اختبار تطبيع بيانات الزنكات القديمة"""
        legacy_data = {
            'plate_size': 'quarter_sheet'
        }
        
        normalized = self.factory.normalize_legacy_ctp_data(legacy_data)
        
        # التحقق من تحويل البيانات القديمة
        self.assertEqual(normalized.get('plate_size'), '35.00x50.00')
        
    def test_validate_paper_data(self):
        """اختبار التحقق من صحة بيانات الورق"""
        valid_data = {
            'paper_type': 'كوشيه',
            'gsm': 120,
            'sheet_size': '70.00x100.00'
        }
        
        is_valid, errors = self.factory.validate_paper_data(valid_data)
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)
        
        # اختبار بيانات غير صحيحة
        invalid_data = {
            'paper_type': '',
            'gsm': -10
        }
        
        is_valid, errors = self.factory.validate_paper_data(invalid_data)
        self.assertFalse(is_valid)
        self.assertGreater(len(errors), 0)
        
    def test_validate_offset_data(self):
        """اختبار التحقق من صحة بيانات الأوفست"""
        valid_data = {
            'machine_type': 'sm52',
            'sheet_size': 'quarter_sheet',
            'colors': 4
        }
        
        is_valid, errors = self.factory.validate_offset_data(valid_data)
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)
        
    def test_validate_ctp_data(self):
        """اختبار التحقق من صحة بيانات الزنكات"""
        valid_data = {
            'plate_size': '35.00x50.00'
        }
        
        is_valid, errors = self.factory.validate_ctp_data(valid_data)
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)
        
    def test_convert_legacy_sheet_size(self):
        """اختبار تحويل مقاسات الفرخ القديمة"""
        # اختبار التحويلات المختلفة
        conversions = {
            'full_70x100': '70.00x100.00',
            'half_50x70': '50.00x70.00',
            'quarter_35x50': '35.00x50.00',
            'a4': 'a4',
            'custom': 'custom'
        }
        
        for old_size, expected_new in conversions.items():
            converted = self.factory.convert_legacy_sheet_size(old_size)
            self.assertEqual(converted, expected_new)
            
    def test_convert_legacy_paper_type(self):
        """اختبار تحويل أنواع الورق القديمة"""
        conversions = {
            'coated': 'كوشيه',
            'offset': 'أوفست',
            'art': 'آرت'
        }
        
        for old_type, expected_new in conversions.items():
            converted = self.factory.convert_legacy_paper_type(old_type)
            self.assertEqual(converted, expected_new)
            
    def test_convert_legacy_machine_type(self):
        """اختبار تحويل أنواع الماكينات القديمة"""
        conversions = {
            'heidelberg_sm52': 'sm52',
            'heidelberg_sm74': 'sm74',
            'komori_ls40': 'ls40',
            'ryobi_524': 'ryobi_524'
        }
        
        for old_type, expected_new in conversions.items():
            converted = self.factory.convert_legacy_machine_type(old_type)
            self.assertEqual(converted, expected_new)
            
    def test_convert_legacy_offset_sheet_size(self):
        """اختبار تحويل مقاسات الأوفست القديمة"""
        conversions = {
            '35x50': 'quarter_sheet',
            '50x70': 'half_sheet',
            '70x100': 'full_sheet'
        }
        
        for old_size, expected_new in conversions.items():
            converted = self.factory.convert_legacy_offset_sheet_size(old_size)
            self.assertEqual(converted, expected_new)
            
    def test_convert_legacy_plate_size(self):
        """اختبار تحويل مقاسات الزنكات القديمة"""
        conversions = {
            'quarter_sheet': '35.00x50.00',
            'half_sheet': '50.00x70.00',
            'full_sheet': '70.00x100.00'
        }
        
        for old_size, expected_new in conversions.items():
            converted = self.factory.convert_legacy_plate_size(old_size)
            self.assertEqual(converted, expected_new)


class ServiceIntegrationTest(TestCase):
    """اختبارات تكامل الخدمات مع النظام الموحد"""
    
    fixtures = [
        'supplier/fixtures/supplier_types.json',
        'printing_pricing/fixtures/initial_data.json'
    ]
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.paper_type = SupplierType.objects.filter(
            supplier_type_settings__type_key="paper"
        ).first()
        
        self.supplier = Supplier.objects.create(
            name="مورد متكامل",
            supplier_type=self.paper_type
        )
        
    def test_service_creation_with_unified_system(self):
        """اختبار إنشاء خدمة باستخدام النظام الموحد"""
        from ..models import PaperServiceDetails
        
        # إنشاء خدمة بالبيانات الموحدة
        service = PaperServiceDetails.objects.create(
            supplier=self.supplier,
            paper_type="كوشيه",  # بيانات موحدة
            gsm=120,
            sheet_size="70.00x100.00",  # مقاس موحد
            country_of_origin="مصر",
            price_per_sheet=Decimal('2.50')
        )
        
        # التحقق من إنشاء الخدمة بنجاح
        self.assertEqual(service.paper_type, "كوشيه")
        self.assertEqual(service.sheet_size, "70.00x100.00")
        
        # التحقق من عمل دالة العرض
        display = service.get_sheet_size_display()
        self.assertIsNotNone(display)
        
    def test_legacy_data_compatibility(self):
        """اختبار التوافق مع البيانات القديمة"""
        from ..models import PaperServiceDetails
        
        # إنشاء خدمة ببيانات قديمة (محاكاة)
        service = PaperServiceDetails.objects.create(
            supplier=self.supplier,
            paper_type="coated",  # بيانات قديمة
            sheet_size="full_70x100"  # مقاس قديم
        )
        
        # النظام يجب أن يتعامل مع البيانات القديمة
        self.assertIsNotNone(service)
        
    def test_form_choices_integration(self):
        """اختبار تكامل خيارات النماذج"""
        from ..forms.service_form_factory import get_form_choices_for_category
        
        # اختبار الحصول على خيارات الورق
        choices = get_form_choices_for_category('paper')
        self.assertIsNotNone(choices)
        
        # اختبار الحصول على خيارات الأوفست
        choices = get_form_choices_for_category('offset_printing')
        self.assertIsNotNone(choices)
        
        # اختبار الحصول على خيارات الزنكات
        choices = get_form_choices_for_category('plates')
        self.assertIsNotNone(choices)
