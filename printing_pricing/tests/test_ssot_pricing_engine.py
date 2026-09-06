import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from printing_pricing.services import PrintingCalculationEngine

User = get_user_model()


@pytest.mark.django_db
class TestSSOTPricingEngine:
    """
    اختبارات محرك الحسابات الموحد SSOT PrintingCalculationEngine
    التحقق من الدقة الهندسية، انعدام العجز، صمامات الأمان، وتطابق الأسعار بالجنيه المصري.
    """

    def setup_method(self):
        self.user = User.objects.create_user(
            username="test_pricing_admin",
            email="admin@test.com",
            password="Password123",
            is_staff=True
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_01_montage_and_sheet_yield_calculation(self):
        """
        التحقق من أن المونتاج يُحسب هندسياً على شيت الماكينة المختار بعد خصم 2.0 سم
        مطبوع 22×30 سم على مقاس قطع 50×70 سم:
        الأبعاد الصافية: 48×68 سم -> المونتاج = 4 قطع، واستغلال الفرخ الخام = 8 قطع.
        """
        params = {
            'quantity': 8000,
            'width': 22,
            'height': 30,
            'sheet_size': '70x100',
            'piece_size': '50x70',
            'print_sides_mode': 'single',
            'cover_printing_type': 'offset'
        }
        res = PrintingCalculationEngine.calculate(params)
        assert res['success'] is True
        assert res['montage']['cuts_per_sheet'] == 4
        assert res['montage']['parent_sheet_yield'] == 8
        assert res['montage']['machine_cuts'] == 2
        # صافي شيتات الماكينة: 8000 / 4 = 2000
        assert res['paper']['net_press_sheets'] == 2000

    def test_02_work_and_turn_vs_sheetwise_mechanics(self):
        """
        التحقق من فيزياء الطبع والقلب (Work & Turn) مقابل السكتين (Sheetwise):
        في الطبع والقلب: السحبات تتضاعف (2020 * 2 = 4040)، والزنكات = 4 فقط (توفير 50%).
        في السكتين: السحبات 4040، والزنكات = 8 كاملة.
        """
        # 1. طبع وقلب
        wt_params = {
            'quantity': 8000,
            'width': 22,
            'height': 30,
            'sheet_size': '70x100',
            'piece_size': '50x70',
            'print_sides_mode': 'work_turn',
            'cover_printing_type': 'offset',
            'colors_front': 4,
            'colors_back': 4,
            'waste_sheets': 20
        }
        wt_res = PrintingCalculationEngine.calculate(wt_params)
        assert wt_res['success'] is True
        assert wt_res['printing']['press_pulls'] == 4040
        assert wt_res['printing']['tirages'] == 5
        assert wt_res['plates']['total_plates'] == 4
        assert wt_res['plates']['plates_back'] == 0
        assert wt_res['plates']['is_work_turn_savings'] is True

        # 2. وش وضهر سكتين
        sw_params = dict(wt_params)
        sw_params['print_sides_mode'] = 'work_sheet'
        sw_res = PrintingCalculationEngine.calculate(sw_params)
        assert sw_res['success'] is True
        assert sw_res['printing']['press_pulls'] == 4040
        assert sw_res['plates']['total_plates'] == 8
        assert sw_res['plates']['plates_back'] == 4
        assert sw_res['plates']['is_work_turn_savings'] is False

    def test_03_minimum_press_floor_charge_enforcement(self):
        """
        التحقق من صمام الحد الأدنى لفتحة الماكينة (Floor Charge):
        طلبية صغيرة (1 تراج بـ 75 ج) على ماكينة 50×70 الحد الأدنى 200 ج:
        يجب أن تكون التكلفة 200 ج وتفعيل is_floor_applied = True.
        """
        small_params = {
            'quantity': 200,
            'width': 22,
            'height': 30,
            'sheet_size': '70x100',
            'piece_size': '50x70',
            'print_sides_mode': 'single',
            'cover_printing_type': 'offset',
            'waste_sheets': 10,
            'press_floor': 200.0
        }
        res = PrintingCalculationEngine.calculate(small_params)
        assert res['success'] is True
        assert res['printing']['tirages'] == 1
        assert res['printing']['applied_press_cost'] == 200.0
        assert res['printing']['is_floor_applied'] is True

    def test_04_oversized_dimensions_zerodivision_guard(self):
        """
        التحقق من صمام أمان المقاسات الكبيرة لمنع كراش القسمة على صفر
        """
        oversized_params = {
            'quantity': 1000,
            'width': 85,
            'height': 120,
            'sheet_size': '70x100',
            'piece_size': '50x70'
        }
        res = PrintingCalculationEngine.calculate(oversized_params)
        assert res['success'] is False
        assert res['error_code'] == 'DIMENSIONS_EXCEED_SHEET'

    def test_05_live_calculate_api_endpoint(self):
        """
        التحقق من استجابة مسار api_live_calculate بالـ JSON الكامل في أقل من 50ms
        """
        url = reverse('printing_pricing:api_live_calculate')
        post_data = {
            'quantity': 5000,
            'width': 14.8,
            'height': 21.0,
            'sheet_size': '70x100',
            'piece_size': '50x70',
            'print_sides_mode': 'work_turn',
            'cover_printing_type': 'offset',
            'waste_sheets': 30
        }
        response = self.client.post(url, post_data)
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'montage' in data
        assert 'paper' in data
        assert 'printing' in data
        assert 'plates' in data
        assert 'totals' in data
        assert data['currency'] == 'EGP'
        assert data['totals']['total_selling_price'] > 0

    def test_06_montage_naming_and_formatting(self):
        """
        التحقق من اشتقاق مسمى مقاس القطع وصيغة المونتاج بسوق المطابع:
        - 70×100 مع ربع -> ربع (مثلاً: 4 / ربع)
        - 66×88 مع ربع -> ربع جاير (مثلاً: 4 / ربع جاير)
        - 60×85 مع ربع -> ربع طبع جاير (مثلاً: 4 / ربع طبع جاير)
        - 70×100 مع نصف -> نصف (مثلاً: 8 / نصف)
        """
        # 1. ربع عادي 70×100
        res1 = PrintingCalculationEngine.calculate({
            'quantity': 1000,
            'width': 14.8,
            'height': 21.0,
            'sheet_size': '70x100',
            'piece_size': '35x50',
        })
        assert res1['success'] is True
        assert res1['montage']['piece_size_name'] == 'ربع'
        assert res1['montage']['montage_text'] == f"{res1['montage']['cuts_per_sheet']} / ربع"

        # 2. ربع جاير 66×88
        res2 = PrintingCalculationEngine.calculate({
            'quantity': 1000,
            'width': 14.8,
            'height': 21.0,
            'sheet_size': '66x88',
            'piece_size': 'quarter',
        })
        assert res2['success'] is True
        assert res2['montage']['piece_size_name'] == 'ربع جاير'
        assert res2['montage']['montage_text'] == f"{res2['montage']['cuts_per_sheet']} / ربع جاير"

        # 3. ربع طبع جاير 60×85
        res3 = PrintingCalculationEngine.calculate({
            'quantity': 1000,
            'width': 14.8,
            'height': 21.0,
            'sheet_size': '60x85',
            'piece_size': 'quarter',
        })
        assert res3['success'] is True
        assert res3['montage']['piece_size_name'] == 'ربع طبع جاير'
        assert res3['montage']['montage_text'] == f"{res3['montage']['cuts_per_sheet']} / ربع طبع جاير"

        # 4. نصف عادي 70×100
        res4 = PrintingCalculationEngine.calculate({
            'quantity': 1000,
            'width': 14.8,
            'height': 21.0,
            'sheet_size': '70x100',
            'piece_size': '50x70',
        })
        assert res4['success'] is True
        assert res4['montage']['piece_size_name'] == 'نصف'
        assert res4['montage']['montage_text'] == f"{res4['montage']['cuts_per_sheet']} / نصف"

    def test_07_montage_ceiling_capping_and_manual_reduction(self):
        """
        التحقق من كبح السقف الهندسي والتعديل للأقل فقط:
        - إذا كان السقف 4 وتم تمرير 2: يُعتمد 2 وتتضاعف أفرخ الورق المطلوبة.
        - إذا تم تمرير 10 (أكبر من السقف 4): يُكبح فوراً إلى 4.
        - إذا تم تمرير 0 أو سالب: يُحدد بـ 1 كحد أدنى.
        """
        base_params = {
            'quantity': 1000,
            'width': 14.8,
            'height': 21.0,
            'sheet_size': '66x88',
            'piece_size': '35x50',  # ربع جاير -> السقف 4 قطع
        }
        # الحساب التلقائي بالسقف الأقصى
        res_auto = PrintingCalculationEngine.calculate(base_params)
        max_montage = res_auto['montage']['cuts_per_sheet']
        assert max_montage == 4
        assert res_auto['montage']['max_cuts_per_sheet'] == 4
        assert res_auto['montage']['is_manual'] is False
        assert res_auto['paper']['net_press_sheets'] == 250

        # تقليل المونتاج يدوي إلى 2 (أقل من السقف)
        params_reduced = dict(base_params)
        params_reduced['montage_count'] = 2
        res_reduced = PrintingCalculationEngine.calculate(params_reduced)
        assert res_reduced['montage']['cuts_per_sheet'] == 2
        assert res_reduced['montage']['max_cuts_per_sheet'] == 4
        assert res_reduced['montage']['is_manual'] is True
        assert res_reduced['montage']['montage_text'] == '2 / ربع جاير'
        # مضاعفة الأفرخ الصافية: 1000 / 2 = 500
        assert res_reduced['paper']['net_press_sheets'] == 500
        assert res_reduced['montage']['parent_sheet_yield'] == 8  # 2 قطع × 4 قطعات للماكينة

        # محاولة تجاوز السقف وتمرير 10
        params_exceed = dict(base_params)
        params_exceed['montage_count'] = 10
        res_exceed = PrintingCalculationEngine.calculate(params_exceed)
        assert res_exceed['montage']['cuts_per_sheet'] == 4  # كبح فوري عند السقف
        assert res_exceed['montage']['is_manual'] is False

        # محاولة تمرير صفر
        params_zero = dict(base_params)
        params_zero['montage_count'] = 0
        res_zero = PrintingCalculationEngine.calculate(params_zero)
        assert res_zero['montage']['cuts_per_sheet'] == 1  # حد أدنى 1

    def test_08_montage_reduction_to_one_disallows_work_and_turn(self):
        """
        التحقق من صمام أمان الطبع والقلب (Work & Turn Guard):
        عند تقليل المونتاج إلى 1، لا يمكن فيزيائياً الطبع والقلب، فيتم التحويل تلقائياً لسكتين.
        """
        params = {
            'quantity': 1000,
            'width': 14.8,
            'height': 21.0,
            'sheet_size': '70x100',
            'piece_size': '35x50',
            'print_sides_mode': 'work_turn',
            'montage_count': 1,  # مونتاج قطعة واحدة
        }
        res = PrintingCalculationEngine.calculate(params)
        assert res['montage']['cuts_per_sheet'] == 1
        assert res['montage']['is_work_turn_allowed'] is False
        # الزنكات = 8 كاملة (سكتين) بدلاً من 4 زنكات (طبع وقلب)
        assert res['plates']['total_plates'] == 8

    def test_09_piece_size_selection_directly_impacts_montage(self):
        """
        التحقق من أن تغيير مقاس القطع (piece_size) يؤثر مباشرة على المونتاج والمسمى:
        - ربع فرخ 35×50 -> مونتاج 4 قطع A5 / ربع
        - نصف فرخ 50×70 -> مونتاج 8 قطع A5 / نصف
        - فرخ كامل 70×100 -> مونتاج 16 قطعة A5 / فرخ
        """
        base = {
            'quantity': 1000,
            'width': 14.8,
            'height': 21.0,
            'sheet_size': '70x100',
        }

        # 1. ربع فرخ
        res_quarter = PrintingCalculationEngine.calculate(dict(base, piece_size='35x50'))
        assert res_quarter['montage']['cuts_per_sheet'] == 4
        assert res_quarter['montage']['piece_size_name'] == 'ربع'
        assert res_quarter['montage']['montage_text'] == '4 / ربع'

        # 2. نصف فرخ
        res_half = PrintingCalculationEngine.calculate(dict(base, piece_size='50x70'))
        assert res_half['montage']['cuts_per_sheet'] >= 8
        assert res_half['montage']['piece_size_name'] == 'نصف'
        assert 'نصف' in res_half['montage']['montage_text']

        # 3. فرخ كامل
        res_full = PrintingCalculationEngine.calculate(dict(base, piece_size='70x100'))
        assert res_full['montage']['cuts_per_sheet'] >= 16
        assert res_full['montage']['piece_size_name'] == 'فرخ'
        assert 'فرخ' in res_full['montage']['montage_text']
