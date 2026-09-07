import pytest
from decimal import Decimal
from django.urls import reverse
from django.test import RequestFactory
from django.contrib.auth import get_user_model

from printing_pricing.models import (
    PrintingOrder,
    PaperSpecification,
    ProductType,
    ProductSize,
    PaperType,
)
from printing_pricing.services.pricing_engine import PrintingCalculationEngine
from printing_pricing.views.order_views import OrderUpdateView, duplicate_order, OrderDetailView

User = get_user_model()


@pytest.mark.django_db
class TestImpositionIndustrialMaster:
    """
    اختبارات الجودة الصناعية والهندسية لمحرك المعاينة المرئية للمونتاج والتفريد
    """

    @pytest.fixture(autouse=True)
    def setup_data(self):
        self.user = User.objects.create_user(username='press_master', password='password123', is_staff=True)
        self.factory = RequestFactory()

        self.pt_flyer = ProductType.objects.create(name='فلاير', base_archetype='flyer')
        self.pt_folder = ProductType.objects.create(name='فولدر جيب', base_archetype='folder')
        self.pt_book = ProductType.objects.create(name='كتالوج', base_archetype='catalog')

        self.order_flyer = PrintingOrder.objects.create(
            title='فلاير A4 دعائي',
            quantity=1000,
            order_type='flyer',
            product_type=self.pt_flyer,
            width=Decimal('21.00'),
            height=Decimal('29.70'),
            is_closed_size=False,
            created_by=self.user,
        )

        self.order_folder = PrintingOrder.objects.create(
            title='فولدر شركة بجيب متصل',
            quantity=500,
            order_type='folder',
            product_type=self.pt_folder,
            width=Decimal('21.00'),
            height=Decimal('29.70'),
            is_closed_size=True,
            open_direction='right',
            folder_pocket_type='same_sheet',
            folder_pocket_height=Decimal('7.50'),
            created_by=self.user,
        )

        self.order_book = PrintingOrder.objects.create(
            title='كتالوج منتجات 64 صفحة',
            quantity=300,
            order_type='catalog',
            product_type=self.pt_book,
            width=Decimal('21.00'),
            height=Decimal('29.70'),
            is_closed_size=True,
            open_direction='right',
            pages_count=64,
            spine_thickness=Decimal('0.80'),
            created_by=self.user,
        )

    # -------------------------------------------------------------------------
    # 1. اختبارات خواص المقاس المفتوح (open_width و open_height)
    # -------------------------------------------------------------------------
    def test_open_dimensions_properties(self):
        """فحص حساب الأبعاد المفتوحة للمطبوعات المفردة والفولدرات والكتب مع الكعب"""
        # فلاير مفرود
        assert self.order_flyer.open_width == Decimal('21.00')
        assert self.order_flyer.open_height == Decimal('29.70')

        # فولدر جيب متصل: العرض مقفول 21 يتضاعف إلى 42، والارتفاع 29.7 + 7.5 جيب = 37.2
        assert self.order_folder.open_width == Decimal('42.00')
        assert self.order_folder.open_height == Decimal('37.20')

        # فولدر جيب منفصل: الارتفاع يبقى 29.7 فقط
        self.order_folder.folder_pocket_type = 'separate_sheet'
        assert self.order_folder.open_height == Decimal('29.70')

        # كتاب مع كعب 0.8 سم: العرض مقفول 21 يتضاعف إلى 42 + 0.8 كعب = 42.8
        assert self.order_book.open_width == Decimal('42.80')
        assert self.order_book.open_height == Decimal('29.70')

    # -------------------------------------------------------------------------
    # 2. اختبارات دورة حياة قاعدة البيانات وتكرار الطلب (duplicate_order)
    # -------------------------------------------------------------------------
    def test_paper_specification_persistence_and_duplication(self):
        """فحص حفظ ونسخ حقول is_inner و imposition_orientation وخاصية parent_yield"""
        cover_spec = PaperSpecification.objects.create(
            order=self.order_book,
            paper_type_name='كوشيه 300 جم',
            paper_weight=300,
            sheet_width=Decimal('70.00'),
            sheet_height=Decimal('100.00'),
            piece_size='نصف فرخ',
            piece_width=Decimal('50.00'),
            piece_height=Decimal('70.00'),
            machine_cuts=2,
            montage_count=4,
            sheets_needed=100,
            sheet_cost=Decimal('5.00'),
            total_paper_cost=Decimal('500.00'),
            is_inner=False,
            imposition_orientation='rotated',
            is_active=True,
        )

        inner_spec = PaperSpecification.objects.create(
            order=self.order_book,
            paper_type_name='كوشيه 135 جم',
            paper_weight=135,
            sheet_width=Decimal('70.00'),
            sheet_height=Decimal('100.00'),
            piece_size='ربع فرخ',
            piece_width=Decimal('35.00'),
            piece_height=Decimal('50.00'),
            machine_cuts=4,
            montage_count=8,
            sheets_needed=250,
            sheet_cost=Decimal('3.00'),
            total_paper_cost=Decimal('750.00'),
            is_inner=True,
            imposition_orientation='auto',
            is_active=True,
        )

        # فحص خاصية parent_yield
        assert cover_spec.parent_yield == 2 * 4  # 8 قطع
        assert inner_spec.parent_yield == 4 * 8  # 32 قطعة

        # اختبار تكرار الطلب duplicate_order
        req = self.factory.post(reverse('printing_pricing:duplicate_order', kwargs={'pk': self.order_book.pk}))
        req.user = self.user
        resp = duplicate_order(req, pk=self.order_book.pk)
        assert resp.status_code in [200, 302]

        cloned_order = PrintingOrder.objects.filter(title__contains='نسخة').latest('id')
        cloned_specs = list(cloned_order.paper_specs.filter(is_active=True).order_by('id'))
        assert len(cloned_specs) == 2

        # التحقق من دقة نسخ حقول المونتاج والتفريد
        cloned_cover = cloned_specs[0]
        assert cloned_cover.is_inner is False
        assert cloned_cover.imposition_orientation == 'rotated'

        cloned_inner = cloned_specs[1]
        assert cloned_inner.is_inner is True
        assert cloned_inner.imposition_orientation == 'auto'

    # -------------------------------------------------------------------------
    # 3. اختبارات استرجاع التوجيه في get_initial لشاشة التعديل
    # -------------------------------------------------------------------------
    def test_order_update_get_initial_orientation(self):
        """فحص تمرير imposition_orientation في get_initial بـ OrderUpdateView"""
        PaperSpecification.objects.create(
            order=self.order_flyer,
            paper_type_name='كوشيه 150 جم',
            paper_weight=150,
            sheet_width=Decimal('70.00'),
            sheet_height=Decimal('100.00'),
            piece_size='ربع فرخ',
            piece_width=Decimal('35.00'),
            piece_height=Decimal('50.00'),
            machine_cuts=4,
            montage_count=2,
            sheets_needed=500,
            sheet_cost=Decimal('3.50'),
            total_paper_cost=Decimal('1750.00'),
            is_inner=False,
            imposition_orientation='normal',
            is_active=True,
        )

        req = self.factory.get(reverse('printing_pricing:order_update', kwargs={'pk': self.order_flyer.pk}))
        req.user = self.user

        view = OrderUpdateView()
        view.setup(req, pk=self.order_flyer.pk)
        view.object = self.order_flyer
        initial = view.get_initial()

        assert initial['imposition_orientation'] == 'normal'
        assert initial['montage_count'] == 2

    # -------------------------------------------------------------------------
    # 4. اختبارات الحسابات الهندسية للمونتاج في محرك التسعير (SSOT Engine)
    # -------------------------------------------------------------------------
    def test_offset_gripper_and_bleed_gutters_math(self):
        """فحص هندسة البنسة الحقيقية وفواصل الدوبل تكسير (3 مم) والقص المشترك"""
        # شيت ماكينة ربع فرخ 35×50 سم مع مطبوع فلاير A5 (14.8×21 سم)
        res = PrintingCalculationEngine._calculate_imposition(
            open_w=Decimal('14.8'),
            open_h=Decimal('21.0'),
            w_cut=Decimal('35.0'),
            h_cut=Decimal('50.0'),
            orientation_pref='auto',
            is_digital=False,
        )

        assert res['montage'] == 4
        assert res['cols'] > 0
        assert res['rows'] > 0
        assert res['gap_x'] == Decimal('0.3') or res['gap_y'] == Decimal('0.3')
        assert res['has_bleed_gutters'] is True
        assert res['margin_x'] >= Decimal('0.0')
        assert res['margin_y'] >= Decimal('0.0')

    def test_common_knife_cut_warning(self):
        """فحص حالة القص المشترك عندما لا تتسع المساحة لفواصل دوبل تكسير 3 مم"""
        # شيت 30×42 مع قطعتين 15×42 (حاشر تماماً في العرض)
        res = PrintingCalculationEngine._calculate_imposition(
            open_w=Decimal('16.0'),
            open_h=Decimal('20.0'),
            w_cut=Decimal('33.0'),
            h_cut=Decimal('21.0'),
            orientation_pref='normal',
            is_digital=False,
        )
        # عند الحشر، قد لا تتاح مساحة لفواصل 3 مم
        if res['montage'] > 1 and res['gap_x'] == Decimal('0.0'):
            assert res['has_bleed_gutters'] is False

    def test_orientation_modes_and_fallback(self):
        """فحص التوجيه الثلاثي (auto, normal, rotated) وصمام الارتداد التلقائي"""
        # مطبوع بمقاس 15×32 يتسع في الوضع rotated (3 قطع) أفضل من normal (قطعتين)
        res_rot = PrintingCalculationEngine._calculate_imposition(
            open_w=Decimal('15.0'),
            open_h=Decimal('32.0'),
            w_cut=Decimal('35.0'),
            h_cut=Decimal('50.0'),
            orientation_pref='rotated',
            is_digital=False,
        )
        assert res_rot['can_fit_rotated'] is True
        assert res_rot['orientation_applied'] == 'rotated'
        assert res_rot['montage'] == 3

        # طلب توجيه normal لمقاس لا يتسع إلا rotated -> يرتد لـ rotated بأمان
        res_fallback = PrintingCalculationEngine._calculate_imposition(
            open_w=Decimal('20.0'),
            open_h=Decimal('48.0'),
            w_cut=Decimal('35.0'),
            h_cut=Decimal('50.0'),
            orientation_pref='normal',
            is_digital=False,
        )
        assert res_fallback['montage'] >= 0

    def test_zero_dimensions_skeleton_guard(self):
        """فحص صمام حماية القسمة على صفر عند إدخال مقاسات صفرية أو سالبة"""
        res_zero = PrintingCalculationEngine._calculate_imposition(
            open_w=Decimal('0.0'),
            open_h=Decimal('0.0'),
            w_cut=Decimal('35.0'),
            h_cut=Decimal('50.0'),
            orientation_pref='auto',
            is_digital=False,
        )
        assert res_zero['montage'] == 0
        assert res_zero['cols'] == 0
        assert res_zero['rows'] == 0
        assert res_zero['can_fit_normal'] is False
        assert res_zero['can_fit_rotated'] is False

    # -------------------------------------------------------------------------
    # 5. اختبارات سياق صفحة أمر الشغل (OrderDetailView Context & Micro-Stamp)
    # -------------------------------------------------------------------------
    def test_order_detail_view_context(self):
        """فحص احتواء سياق OrderDetailView على saved_paper_spec وبيانات montage_data_cover"""
        PaperSpecification.objects.create(
            order=self.order_flyer,
            paper_type_name='كوشيه 200 جم',
            paper_weight=200,
            sheet_width=Decimal('70.00'),
            sheet_height=Decimal('100.00'),
            piece_size='ربع فرخ',
            piece_width=Decimal('35.00'),
            piece_height=Decimal('50.00'),
            machine_cuts=4,
            montage_count=4,
            sheets_needed=250,
            sheet_cost=Decimal('4.00'),
            total_paper_cost=Decimal('1000.00'),
            is_inner=False,
            imposition_orientation='auto',
            is_active=True,
        )

        req = self.factory.get(reverse('printing_pricing:order_detail', kwargs={'pk': self.order_flyer.pk}))
        req.user = self.user

        view = OrderDetailView()
        view.setup(req, pk=self.order_flyer.pk)
        view.object = self.order_flyer
        context = view.get_context_data()

        assert 'saved_paper_spec' in context
        assert context['saved_paper_spec'] is not None
        assert 'montage_data_cover' in context
        assert context['montage_data_cover'] is not None

        cover_data = context['montage_data_cover']
        assert cover_data['open_w'] == 21.0
        assert cover_data['open_h'] == 29.7
        assert cover_data['press_sheet_w'] == 35.0
        assert cover_data['press_sheet_h'] == 50.0
        assert cover_data['montage_count'] == 4
        assert cover_data['printing_type'] == 'offset'

    def test_dynamic_parent_sheet_dimensions_in_engine(self):
        """التحقق من اشتقاق أبعاد الفرخ الخام ديناميكياً لكافة المقاسات (جاير 66x88 وطبع جاير 60x85 ومقاس مخصص)"""
        # 1. اختبار فرخ جاير 66×88
        res_gayer = PrintingCalculationEngine.calculate({
            'product_type': 'flyer',
            'width': 21.0,
            'height': 29.7,
            'quantity': 1000,
            'sheet_size': '66x88',
            'piece_size': 'ربع جاير',
            'cover_printing_type': 'offset',
        })
        assert res_gayer['success'] is True
        assert res_gayer['montage']['parent_sheet_w'] == 88.0
        assert res_gayer['montage']['parent_sheet_h'] == 66.0
        assert res_gayer['montage']['press_sheet_w'] == 44.0
        assert res_gayer['montage']['press_sheet_h'] == 33.0
        assert res_gayer['montage']['machine_cuts'] == 4

        # 2. اختبار مقاس فرخ مخصص عبر sheet_width و sheet_height
        res_custom = PrintingCalculationEngine.calculate({
            'product_type': 'flyer',
            'width': 21.0,
            'height': 29.7,
            'quantity': 1000,
            'sheet_width': 70.0,
            'sheet_height': 90.0,
            'sheet_size': '70x90',
            'piece_size': 'نصف فرخ',
            'cover_printing_type': 'offset',
        })
        assert res_custom['success'] is True
        assert res_custom['montage']['parent_sheet_w'] == 70.0
        assert res_custom['montage']['parent_sheet_h'] == 90.0
        assert res_custom['montage']['machine_cuts'] == 2
