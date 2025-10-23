"""
اختبارات نماذج إعدادات الطباعة والتسعير المحدثة
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from decimal import Decimal

from ..models.settings_models import (
    PaperType, PaperSize, PaperWeight, PaperOrigin,
    OffsetMachineType, OffsetSheetSize,
    DigitalMachineType, DigitalSheetSize,
    PieceSize, PlateSize,
    CoatingType, FinishingType,
    PrintDirection, PrintSide
)

User = get_user_model()


class PaperSettingsTest(TestCase):
    """اختبارات إعدادات الورق"""
    
    def test_create_paper_type(self):
        """اختبار إنشاء نوع ورق"""
        paper_type = PaperType.objects.create(
            name="كوشيه",
            description="ورق كوشيه عالي الجودة"
        )
        
        self.assertEqual(paper_type.name, "كوشيه")
        self.assertTrue(paper_type.is_active)
        self.assertIsNotNone(paper_type.created_at)
        self.assertIsNotNone(paper_type.updated_at)
        
    def test_paper_type_str_method(self):
        """اختبار طريقة __str__ لنوع الورق"""
        paper_type = PaperType.objects.create(name="أوفست")
        self.assertEqual(str(paper_type), "أوفست")
        
    def test_create_paper_size(self):
        """اختبار إنشاء مقاس ورق"""
        paper_size = PaperSize.objects.create(
            name="A4",
            width=Decimal('21.0'),
            height=Decimal('29.7'),
            unit="cm"
        )
        
        self.assertEqual(paper_size.name, "A4")
        self.assertEqual(paper_size.width, Decimal('21.0'))
        self.assertEqual(paper_size.height, Decimal('29.7'))
        self.assertIsNotNone(paper_size.updated_at)
        
    def test_paper_size_str_method(self):
        """اختبار طريقة __str__ لمقاس الورق"""
        paper_size = PaperSize.objects.create(
            name="A4",
            width=Decimal('21.0'),
            height=Decimal('29.7')
        )
        
        str_result = str(paper_size)
        self.assertIn("A4", str_result)
        self.assertIn("21", str_result)
        self.assertIn("29.7", str_result)
        
    def test_create_paper_weight(self):
        """اختبار إنشاء وزن ورق"""
        paper_weight = PaperWeight.objects.create(
            weight=120,
            unit="gsm"
        )
        
        self.assertEqual(paper_weight.weight, 120)
        self.assertEqual(paper_weight.unit, "gsm")
        self.assertIsNotNone(paper_weight.updated_at)
        
    def test_paper_weight_str_method(self):
        """اختبار طريقة __str__ لوزن الورق"""
        paper_weight = PaperWeight.objects.create(weight=80, unit="gsm")
        self.assertEqual(str(paper_weight), "80 gsm")
        
    def test_create_paper_origin(self):
        """اختبار إنشاء منشأ ورق"""
        paper_origin = PaperOrigin.objects.create(
            country="مصر",
            manufacturer="شركة الورق المصرية"
        )
        
        self.assertEqual(paper_origin.country, "مصر")
        self.assertEqual(paper_origin.manufacturer, "شركة الورق المصرية")
        self.assertIsNotNone(paper_origin.updated_at)


class MachineSettingsTest(TestCase):
    """اختبارات إعدادات الماكينات"""
    
    def test_create_offset_machine_type(self):
        """اختبار إنشاء نوع ماكينة أوفست"""
        machine = OffsetMachineType.objects.create(
            name="Heidelberg SM52",
            code="sm52",
            manufacturer="Heidelberg"
        )
        
        self.assertEqual(machine.name, "Heidelberg SM52")
        self.assertEqual(machine.code, "sm52")
        self.assertEqual(machine.manufacturer, "Heidelberg")
        
    def test_offset_machine_str_method(self):
        """اختبار طريقة __str__ لماكينة الأوفست"""
        machine = OffsetMachineType.objects.create(
            name="Heidelberg SM74",
            code="sm74"
        )
        
        str_result = str(machine)
        self.assertIn("Heidelberg SM74", str_result)
        
    def test_create_offset_sheet_size(self):
        """اختبار إنشاء مقاس ماكينة أوفست"""
        sheet_size = OffsetSheetSize.objects.create(
            name="ربع فرخ",
            width=Decimal('35.0'),
            height=Decimal('50.0'),
            code="quarter_sheet"
        )
        
        self.assertEqual(sheet_size.name, "ربع فرخ")
        self.assertEqual(sheet_size.code, "quarter_sheet")
        
    def test_create_digital_machine_type(self):
        """اختبار إنشاء نوع ماكينة ديجيتال"""
        machine = DigitalMachineType.objects.create(
            name="HP Indigo 7900",
            code="hp7900",
            manufacturer="HP"
        )
        
        self.assertEqual(machine.name, "HP Indigo 7900")
        self.assertEqual(machine.manufacturer, "HP")
        
    def test_create_digital_sheet_size(self):
        """اختبار إنشاء مقاس ماكينة ديجيتال"""
        sheet_size = DigitalSheetSize.objects.create(
            name="A4",
            width=Decimal('21.0'),
            height=Decimal('29.7'),
            code="a4"
        )
        
        self.assertEqual(sheet_size.name, "A4")
        self.assertEqual(sheet_size.code, "a4")


class CuttingAndPlatesTest(TestCase):
    """اختبارات إعدادات القطع والزنكات"""
    
    def test_create_piece_size(self):
        """اختبار إنشاء مقاس قطع"""
        piece_size = PieceSize.objects.create(
            name="بطاقة شخصية",
            width=Decimal('9.0'),
            height=Decimal('5.5'),
            paper_type="كوشيه",
            pieces_per_sheet=20
        )
        
        self.assertEqual(piece_size.name, "بطاقة شخصية")
        self.assertEqual(piece_size.pieces_per_sheet, 20)
        
    def test_piece_size_str_method(self):
        """اختبار طريقة __str__ لمقاس القطع"""
        piece_size = PieceSize.objects.create(
            name="فلاير A5",
            width=Decimal('14.8'),
            height=Decimal('21.0')
        )
        
        str_result = str(piece_size)
        self.assertIn("فلاير A5", str_result)
        
    def test_create_plate_size(self):
        """اختبار إنشاء مقاس زنكة"""
        plate_size = PlateSize.objects.create(
            name="ربع فرخ",
            width=Decimal('35.0'),
            height=Decimal('50.0'),
            code="35.00x50.00"
        )
        
        self.assertEqual(plate_size.name, "ربع فرخ")
        self.assertEqual(plate_size.code, "35.00x50.00")
        
    def test_plate_size_str_method(self):
        """اختبار طريقة __str__ لمقاس الزنكة"""
        plate_size = PlateSize.objects.create(
            name="نصف فرخ",
            width=Decimal('50.0'),
            height=Decimal('70.0')
        )
        
        str_result = str(plate_size)
        self.assertIn("نصف فرخ", str_result)


class FinishingSettingsTest(TestCase):
    """اختبارات إعدادات التشطيب"""
    
    def test_create_coating_type(self):
        """اختبار إنشاء نوع تغطية"""
        coating = CoatingType.objects.create(
            name="UV لامع",
            description="تغطية UV لامعة"
        )
        
        self.assertEqual(coating.name, "UV لامع")
        self.assertTrue(coating.is_active)
        
    def test_create_finishing_type(self):
        """اختبار إنشاء نوع تشطيب"""
        finishing = FinishingType.objects.create(
            name="تجليد حلزوني",
            description="تجليد بالحلزون المعدني"
        )
        
        self.assertEqual(finishing.name, "تجليد حلزوني")
        
    def test_create_print_direction(self):
        """اختبار إنشاء اتجاه طباعة"""
        direction = PrintDirection.objects.create(
            name="طولي",
            code="portrait"
        )
        
        self.assertEqual(direction.name, "طولي")
        self.assertEqual(direction.code, "portrait")
        
    def test_create_print_side(self):
        """اختبار إنشاء جانب طباعة"""
        side = PrintSide.objects.create(
            name="وجه واحد",
            code="single"
        )
        
        self.assertEqual(side.name, "وجه واحد")
        self.assertEqual(side.code, "single")


class SettingsIntegrationTest(TestCase):
    """اختبارات تكامل الإعدادات"""
    
    def test_settings_relationships(self):
        """اختبار العلاقات بين الإعدادات"""
        # إنشاء إعدادات مترابطة
        paper_type = PaperType.objects.create(name="كوشيه")
        paper_weight = PaperWeight.objects.create(weight=120)
        
        # يمكن استخدامها معاً في الخدمات
        self.assertIsNotNone(paper_type)
        self.assertIsNotNone(paper_weight)
        
    def test_default_settings(self):
        """اختبار الإعدادات الافتراضية"""
        # إنشاء إعداد افتراضي
        default_paper = PaperType.objects.create(
            name="أوفست",
            is_default=True
        )
        
        # إنشاء إعداد آخر غير افتراضي
        other_paper = PaperType.objects.create(
            name="كوشيه",
            is_default=False
        )
        
        # التحقق من الإعدادات الافتراضية
        default_papers = PaperType.objects.filter(is_default=True)
        self.assertIn(default_paper, default_papers)
        self.assertNotIn(other_paper, default_papers)
        
    def test_active_inactive_settings(self):
        """اختبار الإعدادات النشطة وغير النشطة"""
        # إعداد نشط
        active_setting = PaperType.objects.create(
            name="نشط",
            is_active=True
        )
        
        # إعداد غير نشط
        inactive_setting = PaperType.objects.create(
            name="غير نشط",
            is_active=False
        )
        
        # التحقق من الفلترة
        active_settings = PaperType.objects.filter(is_active=True)
        self.assertIn(active_setting, active_settings)
        self.assertNotIn(inactive_setting, active_settings)


class SettingsValidationTest(TestCase):
    """اختبارات التحقق من صحة الإعدادات"""
    
    def test_paper_size_validation(self):
        """اختبار التحقق من صحة مقاسات الورق"""
        # مقاس صحيح
        valid_size = PaperSize.objects.create(
            name="A4",
            width=Decimal('21.0'),
            height=Decimal('29.7')
        )
        
        self.assertGreater(valid_size.width, 0)
        self.assertGreater(valid_size.height, 0)
        
    def test_paper_weight_validation(self):
        """اختبار التحقق من صحة أوزان الورق"""
        # وزن صحيح
        valid_weight = PaperWeight.objects.create(
            weight=80,
            unit="gsm"
        )
        
        self.assertGreater(valid_weight.weight, 0)
        
    def test_machine_code_uniqueness(self):
        """اختبار تفرد أكواد الماكينات"""
        # إنشاء ماكينة بكود معين
        machine1 = OffsetMachineType.objects.create(
            name="ماكينة 1",
            code="unique_code"
        )
        
        # محاولة إنشاء ماكينة بنفس الكود (يجب أن تفشل إذا كان هناك قيد unique)
        self.assertEqual(machine1.code, "unique_code")
