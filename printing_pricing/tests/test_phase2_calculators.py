import pytest
from decimal import Decimal
from django.urls import reverse
from django.contrib.auth import get_user_model
from customer.models import Customer
from printing_pricing.models import (
    PrintingOrder, OrderMaterial, OrderService, OrderSummary, CostCalculation,
    CalculationType, PricingStatus, OrderType
)
from printing_pricing.services.calculators import (
    BaseCalculator, MaterialCalculator, PrintingCalculator, ServiceCalculator
)

User = get_user_model()


@pytest.fixture
def auth_user(db):
    user = User.objects.create_user(
        username="phase2_estimator",
        email="phase2@mwheba.com",
        password="secure_password_123",
        is_staff=True
    )
    return user


@pytest.fixture
def customer(db):
    return Customer.objects.create(
        name="شركة الأهرام للتجارة",
        phone="01099998888",
        customer_type="corporate"
    )


@pytest.fixture
def base_order(db, customer, auth_user):
    return PrintingOrder.objects.create(
        order_number="PR260099",
        customer=customer,
        title="مطبوعات وكتالوجات وهدايا الربع الأول",
        order_type=OrderType.BROCHURE,
        status=PricingStatus.DRAFT,
        quantity=1000,
        pages_count=16,
        created_by=auth_user
    )


# 1. اختبار المفاضلة الآلية بين مقاسات الأفرخ (70x100 vs 66x88)
@pytest.mark.django_db
def test_auto_optimize_sheet_size_comparison(base_order):
    calc = MaterialCalculator(base_order)
    # لمنتج 21x28 سم
    result = calc.auto_optimize_sheet_size(
        item_width_cm=Decimal('21.00'),
        item_height_cm=Decimal('28.00'),
        cost_70x100=Decimal('2.00'),
        cost_66x88=Decimal('1.65')
    )
    assert result['success'] is True
    assert result['optimal_sheet_size'] == '66x88'
    assert result['optimal_items_per_sheet'] == 9
    assert result['optimal_cost_per_item'] < Decimal('0.25')
    assert result['savings_percentage'] > Decimal('0.00')


# 2. اختبار إضافة خلوص سكاكين التكسير (5 مم) وقفل اتجاه الألياف
@pytest.mark.django_db
def test_sheets_with_knife_clearance_and_grain_lock(base_order):
    calc = MaterialCalculator(base_order)
    # منتج 10x15 سم عادي بدون تكسير
    normal_res = calc.calculate_sheets_with_knife_clearance(
        sheet_width_cm=Decimal('100.00'),
        sheet_height_cm=Decimal('70.00'),
        item_width_cm=Decimal('10.00'),
        item_height_cm=Decimal('15.00'),
        is_die_cut=False
    )
    # نفس المنتج مع اسطمبة تكسير (5 مم clearance)
    diecut_res = calc.calculate_sheets_with_knife_clearance(
        sheet_width_cm=Decimal('100.00'),
        sheet_height_cm=Decimal('70.00'),
        item_width_cm=Decimal('10.00'),
        item_height_cm=Decimal('15.00'),
        is_die_cut=True,
        knife_clearance_mm=5,
        grain_direction_lock=True
    )
    assert normal_res['success'] is True
    assert diecut_res['success'] is True
    assert diecut_res['is_die_cut'] is True
    assert diecut_res['effective_item_width'] == Decimal('10.50')
    assert diecut_res['effective_item_height'] == Decimal('15.50')
    assert diecut_res['grain_direction_locked'] is True


# 3. اختبار تسعير خدمات الـ UV المباشر والـ UV-DTF عند الموردين
@pytest.mark.django_db
def test_vendor_uv_and_uvdtf_service_cost(base_order):
    calc = ServiceCalculator(base_order)
    # 500 قطعة مجات UV-DTF كريستال مع مصنعية لصق يدوي
    result = calc.calculate_vendor_uv_and_uvdtf_cost(
        service_subtype='UVDTF_PER_PIECE',
        quantity=Decimal('500'),
        unit_rate=Decimal('2.50'),
        setup_fee=Decimal('50.00'),
        manual_application_fee_per_item=Decimal('0.50')
    )
    assert result['success'] is True
    assert result['vendor_cost'] == Decimal('1300.00')  # 50 + (500 * 2.50)
    assert result['manual_application_cost'] == Decimal('250.00')  # 500 * 0.50
    assert result['total_cost'] == Decimal('1550.00')


# 4. اختبار حساب مصاريف كراسة الشروط وعمولات خطابات الضمان البنكية
@pytest.mark.django_db
def test_tender_bank_lg_and_portal_fee_calculation(base_order):
    calc = ServiceCalculator(base_order)
    result = calc.calculate_tender_financials_and_samples(
        specs_portal_fee=Decimal('1500.00'),
        lab_testing_fee=Decimal('800.00'),
        contract_estimated_value=Decimal('500000.00'),
        lg_bid_bond_rate_pct=Decimal('1.00'),  # 5,000
        lg_performance_bond_rate_pct=Decimal('5.00'),  # 25,000 -> مجموع 30,000
        bank_lg_commission_rate_pct=Decimal('0.50'),  # 150 ج عمولة
        has_bank_lg=True
    )
    assert result['success'] is True
    assert result['bid_bond_amount'] == Decimal('5000.00')
    assert result['performance_bond_amount'] == Decimal('25000.00')
    assert result['bank_commission_cost'] == Decimal('150.00')
    assert result['total_tender_cost'] == Decimal('2450.00')  # 1500 + 800 + 150


# 5. اختبار مطابقة أبعاد ملف التصميم المرفوع (Artwork Dimensions Matcher)
@pytest.mark.django_db
def test_artwork_dimensions_matcher_and_variance(base_order):
    calc = MaterialCalculator(base_order)
    # تصميم متطابق
    res_matched = calc.validate_artwork_dimensions_match(
        quoted_width_cm=Decimal('20.00'),
        quoted_height_cm=Decimal('30.00'),
        artwork_width_cm=Decimal('20.10'),
        artwork_height_cm=Decimal('30.00'),
        tolerance_percentage=Decimal('1.00')
    )
    assert res_matched['is_matched'] is True
    assert res_matched['is_escalation_required'] is False

    # تصميم به زيادة 20%
    res_mismatch = calc.validate_artwork_dimensions_match(
        quoted_width_cm=Decimal('20.00'),
        quoted_height_cm=Decimal('30.00'),
        artwork_width_cm=Decimal('24.00'),
        artwork_height_cm=Decimal('30.00'),
        tolerance_percentage=Decimal('1.00')
    )
    assert res_mismatch['is_matched'] is False
    assert res_mismatch['is_escalation_required'] is True
    assert res_mismatch['area_difference_percentage'] == Decimal('20.00')


# 6. اختبار تسعير الهدايا الدعائية بالقطعة مع فتحة الماكينة
@pytest.mark.django_db
def test_merchandise_giveaways_blank_and_setup_fee(base_order):
    calc = ServiceCalculator(base_order)
    # 1000 قلم جاف معدني
    result = calc.calculate_merchandise_cost(
        blank_item_cost=Decimal('15.00'),
        quantity=1000,
        setup_fee=Decimal('200.00'),
        print_technique_cost_per_item=Decimal('2.00'),
        is_electronics=False
    )
    assert result['success'] is True
    assert result['ordered_quantity'] == 1000
    assert result['purchased_quantity'] == 1000
    assert result['blank_material_cost'] == Decimal('15000.00')
    assert result['printing_cost'] == Decimal('2000.00')
    assert result['total_cost'] == Decimal('17200.00')  # 15000 + 200 + 2000
    assert result['cost_per_unit'] == Decimal('17.20')


# 7. اختبار إضافة 3% احتياطي عيوب فحص الإلكترونيات الدعائية (فلاشات USB)
@pytest.mark.django_db
def test_merchandise_electronics_defect_buffer(base_order):
    calc = ServiceCalculator(base_order)
    # 1000 فلاشة USB مع تفعيل فحص الإلكترونيات
    result = calc.calculate_merchandise_cost(
        blank_item_cost=Decimal('80.00'),
        quantity=1000,
        setup_fee=Decimal('150.00'),
        print_technique_cost_per_item=Decimal('5.00'),
        is_electronics=True,
        defect_buffer_percentage=Decimal('3.00')
    )
    assert result['success'] is True
    assert result['ordered_quantity'] == 1000
    assert result['purchased_quantity'] == 1030  # 1000 + 3%
    assert result['defect_buffer_items'] == 30
    assert result['blank_material_cost'] == Decimal('82400.00')  # 1030 * 80
    assert result['total_cost'] == Decimal('87550.00')  # 82400 + 150 + 5000


# 8. اختبار حساب سمك كعب الكتاب بالمليمتر ومطابقة نوع التجليد فيزيائياً
@pytest.mark.django_db
def test_spine_thickness_calculation_and_binding_physics(base_order):
    calc = ServiceCalculator(base_order)
    # كتاب 200 صفحة ورق بلكي 70 جم (تجليد غراء وبشر)
    res_perfect = calc.calculate_spine_thickness_and_binding(
        pages_count=200,
        paper_type='BULKY',
        paper_gsm=70,
        binding_method='PERFECT_BINDING',
        quantity=500,
        unit_rate=Decimal('3.50')
    )
    assert res_perfect['success'] is True
    assert res_perfect['spine_thickness_mm'] == Decimal('14.0')  # 100 leaves * 0.14mm
    assert res_perfect['warning_message'] is None
    assert res_perfect['total_binding_cost'] == Decimal('1750.00')

    # كتيب 120 صفحة تم اختيار دبوس وسط بالخطأ
    res_saddle_warning = calc.calculate_spine_thickness_and_binding(
        pages_count=120,
        paper_type='COATED',
        paper_gsm=150,
        binding_method='SADDLE_STITCH',
        quantity=100
    )
    assert res_saddle_warning['warning_message'] is not None


# 9. اختبار تجليد السلك المزدوج Wire-O وشماعة نتائج الحائط
@pytest.mark.django_db
def test_wire_o_pitch_and_calendar_wall_hanger_cost(base_order):
    calc = ServiceCalculator(base_order)
    # 500 نتيجة حائط مع شماعة معدنية وتخريم نصف دائري
    result = calc.calculate_wire_o_and_calendar_hanger_cost(
        books_count=500,
        wire_pitch='PITCH_3_TO_1',
        has_calendar_wall_hanger=True,
        wire_unit_cost=Decimal('2.00'),
        hanger_unit_cost=Decimal('0.80'),
        punch_thumbcut_rate=Decimal('0.20')
    )
    assert result['success'] is True
    assert result['total_wire_cost'] == Decimal('1000.00')  # 500 * 2.00
    assert result['total_hanger_cost'] == Decimal('500.00')  # 500 * (0.80 + 0.20)
    assert result['total_cost'] == Decimal('1500.00')


# 10. اختبار دفاتر الفواتير الكربونية NCR والترقيم والتثقيب
@pytest.mark.django_db
def test_ncr_carbonless_numbering_and_perforation_cost(base_order):
    calc = ServiceCalculator(base_order)
    # 100 دفتر فواتير (أصل + 2 صورة = 3 أجزاء) كل دفتر 50 مجموعة
    result = calc.calculate_ncr_carbonless_books_cost(
        books_count=100,
        sets_per_book=50,
        parts_count=3,
        numbering_rate_per_1000=Decimal('20.00'),
        perforation_rate_per_book=Decimal('1.50'),
        binding_tape_cost_per_book=Decimal('2.50'),
        ncr_waste_pct=Decimal('8.00'),
        sheet_unit_cost=Decimal('0.25')
    )
    assert result['success'] is True
    assert result['books_count'] == 100
    assert result['parts_count'] == 3
    assert result['numbering_cost'] == Decimal('100.00')  # (5000 / 1000) * 20
    assert result['finishing_cost'] == Decimal('400.00')  # 100 * (1.50 + 2.50)
    assert result['total_cost'] > Decimal('4000.00')


# 11. اختبار صمام منع تقوس الورق عند السلوفان وجه واحد
@pytest.mark.django_db
def test_anti_curl_lamination_guard_for_lightweight_paper(base_order):
    calc = ServiceCalculator(base_order)
    # ورق 135 جم مع سلوفان وجه واحد -> يظهر تحذير
    res_warning = calc.calculate_finishing_special_effects_cost(
        effect_type='LAMINATION_MATT',
        quantity=1000,
        unit_run_rate=Decimal('0.20'),
        paper_gsm=135,
        is_single_sided_lamination=True
    )
    assert res_warning['anti_curl_warning'] is not None

    # ورق 250 جم مع سلوفان وجه واحد -> بدون تحذير
    res_ok = calc.calculate_finishing_special_effects_cost(
        effect_type='LAMINATION_MATT',
        quantity=1000,
        unit_run_rate=Decimal('0.20'),
        paper_gsm=250,
        is_single_sided_lamination=True
    )
    assert res_ok['anti_curl_warning'] is None


# 12. اختبار كليشيهات البصمة الذهبية وترقية السلوفان المعالج للبصمة
@pytest.mark.django_db
def test_special_effects_foil_stamping_and_foil_receptive_lamination(base_order):
    calc = ServiceCalculator(base_order)
    result = calc.calculate_finishing_special_effects_cost(
        effect_type='HOT_FOIL_STAMPING',
        quantity=2000,
        unit_run_rate=Decimal('0.15'),
        cliche_tooling_cost=Decimal('350.00'),
        is_foil_receptive_required=True,
        foil_receptive_upgrade_fee=Decimal('150.00')
    )
    assert result['success'] is True
    assert result['run_cost'] == Decimal('300.00')  # 2000 * 0.15
    assert result['cliche_tooling_cost'] == Decimal('350.00')
    assert result['foil_receptive_upgrade_cost'] == Decimal('150.00')
    assert result['total_cost'] == Decimal('800.00')  # 300 + 350 + 150


# 13. اختبار أتعاب التصميم وفصل الألوان والـ Trapping المتقدم
@pytest.mark.django_db
def test_prepress_color_separation_and_trapping_fee(base_order):
    calc = ServiceCalculator(base_order)
    result = calc.calculate_prepress_trapping_and_design_fee(
        creative_design_fee=Decimal('1200.00'),
        color_separation_fee=Decimal('300.00'),
        prepress_trapping_fee=Decimal('200.00')
    )
    assert result['success'] is True
    assert result['total_prepress_cost'] == Decimal('1700.00')


# 14. اختبار ساعات انتظار ماكينة الأوفست لاعتماد العميل وأحبار البانتون
@pytest.mark.django_db
def test_press_standby_hours_and_pantone_washup(base_order):
    calc = PrintingCalculator(base_order)
    result = calc.calculate_spot_colors_and_varnish_cost(
        pantone_colors_count=2,
        pantone_ink_cost_per_color=Decimal('300.00'),
        washup_fee_per_color=Decimal('150.00'),
        sheets_count=2000,
        press_standby_hours=Decimal('2.00'),
        standby_hourly_rate=Decimal('500.00')
    )
    assert result['success'] is True
    assert result['pantone_cost'] == Decimal('900.00')  # 2 * (300 + 150)
    assert result['standby_cost'] == Decimal('1000.00')  # 2 hours * 500
    assert result['total_cost'] == Decimal('1900.00')


# 15. اختبار إضافة الورنيش المائي المجفف للأوردرات المستعجلة
@pytest.mark.django_db
def test_inline_aqueous_varnish_rush_dry(base_order):
    calc = PrintingCalculator(base_order)
    result = calc.calculate_spot_colors_and_varnish_cost(
        has_aqueous_varnish=True,
        varnish_rate_per_1000=Decimal('80.00'),
        sheets_count=5000
    )
    assert result['success'] is True
    assert result['has_aqueous_varnish'] is True
    assert result['varnish_cost'] == Decimal('400.00')  # 5 * 80.00
    assert result['total_cost'] == Decimal('400.00')


# 16. اختبار محاكاة الطباعة التجميعية للشركات (Gang Run Mode)
@pytest.mark.django_db
def test_gang_run_multi_name_cost_distribution(base_order):
    calc = PrintingCalculator(base_order)
    # 4 أسماء كروت شخصية كل اسم 1000 كارت
    result = calc.calculate_gang_run_cost(
        names_count=4,
        quantity_per_name=1000,
        total_plate_set_cost=Decimal('200.00'),
        total_press_run_cost=Decimal('400.00')
    )
    assert result['success'] is True
    assert result['shared_fixed_cost'] == Decimal('600.00')
    assert result['cost_per_name'] == Decimal('150.00')  # 600 / 4
    assert result['cost_per_item'] == Decimal('0.1500')
    assert result['savings_percentage'] == Decimal('75.00')  # وفر 75% عن 4 طلبيات منفصلة


# 17. اختبار تصفير تكلفة اسطمبة التكسير عند استخدام اسطمبة بالأرشيف
@pytest.mark.django_db
def test_die_cutting_archived_mould_zero_cost(base_order):
    calc = PrintingCalculator(base_order)
    # استخدام اسطمبة العميل من الأرشيف
    res_archived = calc.calculate_die_cutting_cost(
        sheets_count=3000,
        run_rate_per_1000=Decimal('50.00'),
        min_setup_fee=Decimal('100.00'),
        is_archived_mould=True,
        customer_mould_rack="RACK-C-12"
    )
    assert res_archived['success'] is True
    assert res_archived['mould_cost'] == Decimal('0.00')
    assert res_archived['run_pull_cost'] == Decimal('150.00')  # 3 * 50
    assert res_archived['total_cost'] == Decimal('150.00')

    # تفصيل اسطمبة جديدة لأول مرة
    res_new = calc.calculate_die_cutting_cost(
        sheets_count=3000,
        run_rate_per_1000=Decimal('50.00'),
        min_setup_fee=Decimal('100.00'),
        is_archived_mould=False,
        new_mould_cost=Decimal('400.00')
    )
    assert res_new['mould_cost'] == Decimal('400.00')
    assert res_new['total_cost'] == Decimal('550.00')  # 400 + 150


# 18. اختبار حساب تكلفة إعادة التشغيل للعيوب (Remake / COPQ Costing)
@pytest.mark.django_db
def test_remake_job_copq_costing_deduction(base_order):
    calc = BaseCalculator(base_order)
    result = calc.calculate_remake_copq_cost(
        original_selling_price=Decimal('50000.00'),
        original_order_cost=Decimal('35000.00'),  # ربح أولي 15,000
        remake_material_cost=Decimal('3000.00'),
        remake_workshop_cost=Decimal('2000.00')   # إجمالي COPQ = 5,000
    )
    assert result['success'] is True
    assert result['total_copq_cost'] == Decimal('5000.00')
    assert result['initial_profit'] == Decimal('15000.00')
    assert result['realized_net_profit'] == Decimal('10000.00')
    assert result['profit_erosion_percentage'] == Decimal('33.33')


# 19. اختبار الشحن على دفعات مجدولة للمخازن وتأمين الشحن والحد الأدنى
@pytest.mark.django_db
def test_staggered_multi_drop_freight_and_insurance(base_order):
    calc = ServiceCalculator(base_order)
    legs = [{'from': 'المطبعة', 'to': 'مخزن العاشر', 'cost': 120}]
    result = calc.calculate_multi_leg_freight(
        legs=legs,
        minimum_drop_fee=Decimal('150.00'),  # يرفع الـ 120 لـ 150
        staggered_drops_count=4,              # 4 دفعات
        is_insured_cargo=True,
        cargo_value=Decimal('100000.00'),
        insurance_rate_pct=Decimal('0.50')   # 500 ج تأمين
    )
    assert result['success'] is True
    assert result['total_freight_drops'] == Decimal('600.00')  # 4 * 150
    assert result['insurance_fee'] == Decimal('500.00')
    assert result['total_freight_cost'] == Decimal('1100.00')  # 600 + 500


# 20. اختبار احتساب القيمة الاستردادية لبيع دشت وفضلات الورق
@pytest.mark.django_db
def test_scrap_paper_salvage_value_recovery(base_order):
    calc = MaterialCalculator(base_order)
    result = calc.calculate_scrap_salvage_value(
        total_waste_weight_kg=Decimal('250.00'),
        scrap_rate_per_kg=Decimal('8.50')
    )
    assert result['success'] is True
    assert result['scrap_salvage_value'] == Decimal('2125.00')


# 21. اختبار شرط تقلبات أسعار صرف الورق وصلاحية العرض
@pytest.mark.django_db
def test_quotation_fx_escalation_clause(base_order):
    calc = BaseCalculator(base_order)
    # زاد سعر الدولار من 48 لـ 52.8 (زيادة 10%)
    result = calc.calculate_quotation_validity_and_fx_escalation(
        validity_days=5,
        paper_cost_component=Decimal('20000.00'),
        original_usd_rate=Decimal('48.00'),
        current_usd_rate=Decimal('52.80')
    )
    assert result['success'] is True
    assert result['validity_days'] == 5
    assert result['fx_increase_percentage'] == Decimal('10.00')
    assert result['paper_escalation_adjustment'] == Decimal('2000.00')  # 10% من 20,000
    assert result['is_price_adjusted'] is True


# 22. اختبار تسوية الكمية المستلمة في إذن التسليم ونسبة التسامح (±5%)
@pytest.mark.django_db
def test_delivery_tolerance_quantity_adjustment(base_order):
    calc = BaseCalculator(base_order)
    # تم تسليم 9,800 بدلاً من 10,000 (نقص 2% مسموح)
    result = calc.calculate_delivered_quantity_adjustment(
        ordered_quantity=10000,
        delivered_quantity=9800,
        unit_price=Decimal('2.50'),
        tolerance_percentage=Decimal('5.00')
    )
    assert result['success'] is True
    assert result['is_within_tolerance'] is True
    assert result['quantity_difference'] == -200
    assert result['ordered_total_price'] == Decimal('25000.00')
    assert result['delivered_total_price'] == Decimal('24500.00')
    assert result['adjustment_amount'] == Decimal('-500.00')


# 23. اختبار معالجة ضريبة الخصم من المنبع 1% (نموذج 41)
@pytest.mark.django_db
def test_withholding_tax_settlement(base_order):
    calc = BaseCalculator(base_order)
    result = calc.calculate_withholding_tax_settlement(
        invoice_total_amount=Decimal('100000.00'),
        wht_rate_pct=Decimal('1.00')
    )
    assert result['success'] is True
    assert result['wht_deduction_amount'] == Decimal('1000.00')
    assert result['net_cash_receivable'] == Decimal('99000.00')


# 24. اختبار محاكي مصفوفة الكميات المتعددة السريع (Quantity Breaks)
@pytest.mark.django_db
def test_quantity_breaks_simulator(base_order):
    calc = BaseCalculator(base_order)
    result = calc.calculate_quantity_breaks(
        quantities=[1000, 2500, 5000, 10000],
        fixed_costs=Decimal('1500.00'),  # زنكات + فتحة ماكينة
        variable_cost_per_item=Decimal('1.20'),  # ورق وسحب
        profit_margin_pct=Decimal('20.00')
    )
    assert result['success'] is True
    breaks = result['quantity_breaks']
    assert len(breaks) == 4
    # التحقق من انخفاض تكلفة وسعر القطعة مع زيادة الكمية
    assert breaks[0]['cost_per_unit'] > breaks[1]['cost_per_unit'] > breaks[2]['cost_per_unit'] > breaks[3]['cost_per_unit']
    assert breaks[3]['savings_percentage'] > Decimal('40.00')


# 25. اختبار نقطة نهاية calculate_order_cost وتحديث OrderSummary و CostCalculation ذرياً
@pytest.mark.django_db
def test_order_views_calculate_order_cost_atomic_endpoint(client, auth_user, base_order):
    client.force_login(auth_user)

    # إضافة مواد وخدمات للطلب
    OrderMaterial.objects.create(
        order=base_order,
        material_name="ورق كوشيه 150 جم",
        material_type="paper",
        quantity=Decimal('500'),
        unit="sheet",
        unit_cost=Decimal('2.00'),
        waste_percentage=Decimal('5.00')
    )
    OrderService.objects.create(
        order=base_order,
        service_name="سحب أوفست 4 لون",
        service_category="printing",
        quantity=Decimal('500'),
        unit="thousand_sheets",
        unit_price=Decimal('0.50')
    )

    url = reverse('printing_pricing:calculate_order_cost', kwargs={'pk': base_order.pk})
    response = client.post(url)

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True
    assert data['estimated_cost'] > 0
    assert data['final_price'] > data['estimated_cost']

    # التحقق من تحديث OrderSummary في قاعدة البيانات
    summary = OrderSummary.objects.get(order=base_order)
    assert summary.material_cost > Decimal('0.00')
    assert summary.printing_cost > Decimal('0.00')
    assert summary.final_price == Decimal(str(data['final_price']))

    # التحقق من إنشاء CostCalculation
    calc_record = CostCalculation.objects.get(order=base_order, calculation_type=CalculationType.TOTAL, is_current=True)
    assert calc_record.total_cost == summary.total_cost

    # التحقق من تحديث رأس الطلب
    base_order.refresh_from_db()
    assert base_order.estimated_cost == summary.total_cost
    assert base_order.final_price == summary.final_price
