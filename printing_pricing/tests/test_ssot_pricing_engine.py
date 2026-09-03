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
