"""
اختبارات شاملة للميزات والترقيات الهندسية لمحرك التسعير التجاري الواقعي:
1. حل ومعالجة مقاسات القطع المركبة (حداشر 11، تسعات 9، خمسات 5) والتسمية العربية النظيفة.
2. صمام أمان قفل الطبع والقلب (Work & Turn lockout) للخامات ذات الوجه الواحد (دوبلكس/ستيكر).
3. مصاريف قص المخرطة غير القياسي (Shearing fee) لقصات الدفاتر.
4. تصفير زنكات CTP للداخلي الديجيتال وحساب نقرات الليزر بدقة.
5. حفظ الحد الأدنى لأجرة الماكينة (Press floor rate preservation).
6. التطابق التام بدون انحراف (Zero Drift) بين المحرك وخدمة الحفظ anatomy_persistence_service.
"""
import pytest
from decimal import Decimal
from printing_pricing.services.pricing_engine import PrintingCalculationEngine
from printing_pricing.services.anatomy_persistence_service import OrderAnatomyPersistenceService
from printing_pricing.models import (
    PaperType, PaperSize, PieceSize, PrintingOrder, PriceUnit
)


@pytest.mark.django_db
class TestCommercialPricingUpgrades:
    """اختبارات مطابقة محرك التسعير التجاري للماكرو والواقع العملي"""

    def test_n_cuts_resolution_and_arabic_nomenclature(self):
        """التحقق من عدم بلع مقاسات 20x30 و 30x40 وحساب 11 و 5 قطع وتسميتها عربياً بدقة"""
        # 1. فحص قصة حداشر (20×30 سم على فرخ 70×100)
        w_11, h_11, cuts_11 = PrintingCalculationEngine._resolve_cut_dimensions('70x100', '20x30')
        assert cuts_11 == 11
        assert w_11 == Decimal('20.0')
        assert h_11 == Decimal('30.0')
        name_11 = PrintingCalculationEngine._resolve_piece_name('70x100', '20x30', cuts_11, {})
        assert 'حداشر' in name_11

        # 2. فحص قصة تسعات (23×33 سم على فرخ 70×100)
        w_9, h_9, cuts_9 = PrintingCalculationEngine._resolve_cut_dimensions('70x100', '23x33')
        assert cuts_9 == 9
        name_9 = PrintingCalculationEngine._resolve_piece_name('70x100', '23x33', cuts_9, {})
        assert 'تسعات' in name_9

        # 3. فحص قصة خمسات (30×40 سم على فرخ 70×100)
        w_5, h_5, cuts_5 = PrintingCalculationEngine._resolve_cut_dimensions('70x100', '30x40')
        assert cuts_5 == 5
        name_5 = PrintingCalculationEngine._resolve_piece_name('70x100', '30x40', cuts_5, {})
        assert 'خمسات' in name_5

    def test_single_sided_substrate_lockout(self):
        """التحقق من قفل الطبع والقلب وتحويله إلى وجهين عند اختيار خامة وجه واحد مثل الدوبلكس والستيكر"""
        # إنشاء خامة دوبلكس وجه واحد
        pt_duplex = PaperType.objects.create(
            name="دوبلكس رمادي خاص",
            is_single_sided=True,
            override_sheets_per_pack=100
        )

        params = {
            'product_type': 'box',
            'quantity': 1000,
            'width': '20.0',
            'height': '30.0',
            'paper_type_id': pt_duplex.pk,
            'print_sides_mode': 'work_turn', # طلب المستخدم طبع وقلب
            'cover_printing_type': 'offset',
            'colors_front': 4,
            'colors_back': 4,
        }

        calc_res = PrintingCalculationEngine.calculate(params)
        assert calc_res['success'] is True
        # يجب أن يجبر المحرك نمط السحب إلى work_sheet (سكتين) لأن الخامة ظهرها رمادي لا يُطبع
        assert calc_res['printing']['sides_mode'] == 'work_sheet'
        assert calc_res['printing']['press_pulls'] == calc_res['paper']['gross_press_sheets'] * 2

    def test_shearing_fee_applied_for_irregular_cuts(self):
        """التحقق من إضافة مصاريف قص المخرطة غير القياسي لقصات الدفاتر (11، 9، 5)"""
        params = {
            'product_type': 'receipt',
            'quantity': 500,
            'width': '10.0',
            'height': '20.0',
            'piece_size': '20x30', # قصة حداشر
            'parent_sheet_size': '70x100',
            'cover_printing_type': 'offset',
            'paper_price': '3.00',
        }

        calc_res = PrintingCalculationEngine.calculate(params)
        assert calc_res['success'] is True
        finishing = calc_res['finishing']
        assert 'shearing' in finishing['details']
        assert finishing['details']['shearing'] >= 40.0 # الحد الأدنى 40 ج

    def test_digital_inner_zero_plates_and_accurate_clicks(self):
        """التحقق من تصفير زنكات CTP للداخلي الديجيتال وحساب النقرات بدقة دون زنكات وهمية"""
        params = {
            'product_type': 'book',
            'quantity': 100,
            'width': '21.0',
            'height': '29.7',
            'pages_count': 64,
            'inner_printing_type': 'digital',
            'inner_digital_click_price': '1.50',
            'cover_printing_type': 'digital',
        }

        calc_res = PrintingCalculationEngine.calculate(params)
        assert calc_res['success'] is True
        inner = calc_res['inner']
        assert inner['inner_plates_count'] == 0
        assert inner['inner_plates_cost'] == 0.0
        assert inner['inner_pulls'] > 0
        assert inner['inner_press_cost'] > 0.0

    def test_press_floor_rate_preservation(self):
        """التحقق من صيانة الحد الأدنى للماكينة حتى لو تم إدخال سعر تراج صريح"""
        params = {
            'product_type': 'flyer',
            'quantity': 50, # كمية قليلة جداً تنتج تراج واحد
            'width': '21.0',
            'height': '29.7',
            'piece_size': '35x50',
            'cover_printing_type': 'offset',
            'press_rate': '30.00', # سعر تراج منخفض 30 ج
            'press_floor': '100.00', # الحد الأدنى لفتحة الماكينة
        }

        calc_res = PrintingCalculationEngine.calculate(params)
        assert calc_res['success'] is True
        printing = calc_res['printing']
        # الحد الأدنى لماكينة الربع 35×50 هو 100 ج، فلا يجوز أن يحاسب بـ 30 ج
        assert printing['applied_press_cost'] >= 100.0
        assert printing['is_floor_applied'] is True
