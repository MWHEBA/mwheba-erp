"""
حزمة اختبارات شاملة للمعمارية الهجينة وسد الثغرات الصناعية الـ 11
Comprehensive Test Suite for Hybrid Print Architecture & 11 Industrial Fixes
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.urls import reverse
from customer.models import Customer
from printing_pricing.models import (
    PrintingOrder, OrderMaterial, OrderService, OrderSummary, ProductType, ProductSize
)
from printing_pricing.services.anatomy_persistence_service import OrderAnatomyPersistenceService

User = get_user_model()


@pytest.fixture
def test_user(db):
    return User.objects.create_user(username='test_estimator', password='password123', is_staff=True)


@pytest.fixture
def test_customer(db):
    return Customer.objects.create(name='شركة الإبداع للطباعة والتسويق')


@pytest.fixture
def catalog_product_type(db):
    return ProductType.objects.create(name='كتالوج شركات', base_archetype='catalog', is_active=True)


@pytest.fixture
def flyer_product_type(db):
    return ProductType.objects.create(name='فلاير دعائي', base_archetype='flyer', is_active=True)


@pytest.mark.django_db
class TestHybridPrintingArchitecture:
    """اختبارات المعمارية الهجينة للطباعة"""

    def test_model_fields_defaults_and_choices(self, test_customer, test_user):
        """اختبار القيم الافتراضية وحقول تقنيات الطباعة الهجينة في PrintingOrder"""
        order = PrintingOrder.objects.create(
            customer=test_customer,
            title='كتالوج تعريفي',
            quantity=500,
            width=Decimal('21.0'),
            height=Decimal('29.7'),
            created_by=test_user
        )
        assert order.cover_printing_type == 'offset'
        assert order.inner_printing_type == 'offset'

        order.cover_printing_type = 'digital'
        order.inner_printing_type = 'offset'
        order.save()

        refreshed = PrintingOrder.objects.get(pk=order.pk)
        assert refreshed.cover_printing_type == 'digital'
        assert refreshed.inner_printing_type == 'offset'

    def test_hybrid_catalog_persistence_digital_cover_offset_inner(self, test_customer, test_user, catalog_product_type):
        """اختبار تسعير كتالوج هجين: غلاف ديجيتال + داخلي أوفست ملازم"""
        order = PrintingOrder.objects.create(
            customer=test_customer,
            product_type=catalog_product_type,
            order_type='catalog',
            title='كتالوج 500 نسخة هجين',
            quantity=500,
            pages_count=32,
            width=Decimal('21.0'),
            height=Decimal('29.7'),
            is_closed_size=True,
            open_direction='right',
            cover_printing_type='digital',
            inner_printing_type='offset',
            created_by=test_user
        )

        post_data = {
            'quantity': '500',
            'product_type': str(catalog_product_type.pk),
            'order_type': 'catalog',
            'width': '21.0',
            'height': '29.7',
            'is_closed_size': 'true',
            'open_direction': 'right',
            'pages_count': '32',
            'paper_weight': '350',
            'cover_printing_type': 'digital',
            'digital_sheet_price': '2.50',
            'inner_printing_type': 'offset',
            'coating_type': 'matte_2_sides',
            'finishing': 'none',
            'die_cutting': 'straight_cut',
            'profit_margin': '25.00'
        }

        summary = OrderAnatomyPersistenceService.persist_order_anatomy(order, post_data)

        # التحقق من حفظ تقنيات الطباعة
        order.refresh_from_db()
        assert order.cover_printing_type == 'digital'
        assert order.inner_printing_type == 'offset'

        # التحقق من تفكيك الخامات والخدمات
        services = list(order.services.all())
        service_names = [s.service_name for s in services]

        # يجب أن يحتوي على طباعة غلاف ديجيتال وقص مقص
        assert any('[غلاف ديجيتال]' in name for name in service_names)
        assert any('قص شيتات الديجيتال' in name for name in service_names)

        # يجب أن يحتوي على زنكات أوفست للداخلي وسحبات ملازم الداخلي
        assert any('[داخلي أوفست] زنكات CTP' in name for name in service_names)
        assert any('[داخلي أوفست] سحبات ملازم' in name for name in service_names)

        # التحقق من هدر ورق الغلاف للديجيتال (2%)
        cover_mat = order.materials.filter(material_name__startswith='[غلاف').first()
        assert cover_mat is not None
        assert cover_mat.waste_percentage == Decimal('2.00')

        # التحقق من أن السعر النهائي تم حسابه بنجاح
        assert summary.final_price > Decimal('0.00')

    def test_digital_inner_mixed_pages_calculation(self, test_customer, test_user, catalog_product_type):
        """اختبار الداخلي الديجيتال ذي الصفحات المختلطة (ألوان + أسود)"""
        order = PrintingOrder.objects.create(
            customer=test_customer,
            product_type=catalog_product_type,
            order_type='catalog',
            title='كتاب 100 نسخة ديجيتال بالكامل',
            quantity=100,
            pages_count=64,
            width=Decimal('21.0'),
            height=Decimal('29.7'),
            is_closed_size=True,
            cover_printing_type='digital',
            inner_printing_type='digital',
            created_by=test_user
        )

        post_data = {
            'quantity': '100',
            'product_type': str(catalog_product_type.pk),
            'order_type': 'catalog',
            'width': '21.0',
            'height': '29.7',
            'is_closed_size': 'true',
            'pages_count': '64',
            'cover_printing_type': 'digital',
            'inner_printing_type': 'digital',
            'digital_inner_color_pages': '16',
            'digital_inner_bw_pages': '48',
            'profit_margin': '20.00'
        }

        summary = OrderAnatomyPersistenceService.persist_order_anatomy(order, post_data)

        # التحقق من سطري خدمات الداخلي الديجيتال (ألوان + أسود)
        color_service = order.services.filter(service_name__contains='صفحة ألوان').first()
        bw_service = order.services.filter(service_name__contains='صفحة أسود').first()

        assert color_service is not None
        assert color_service.total_cost == Decimal('640.00')

        assert bw_service is not None
        assert bw_service.total_cost == Decimal('600.00')

        # إجمالي تكلفة طباعة الداخلي: 640 + 600 = 1240 ج
        assert (color_service.total_cost + bw_service.total_cost) == Decimal('1240.00')

    def test_minimum_press_floor_and_creasing_on_heavy_stock(self, test_customer, test_user, flyer_product_type):
        """اختبار صمام الحد الأدنى لفتحة الماكينة والريجة للورق السميك المطوي"""
        order = PrintingOrder.objects.create(
            customer=test_customer,
            product_type=flyer_product_type,
            order_type='flyer',
            title='مطوية بروشور 200 نسخة',
            quantity=200,
            width=Decimal('10.0'),
            height=Decimal('21.0'),
            is_closed_size=True,
            cover_printing_type='offset',
            created_by=test_user
        )

        post_data = {
            'quantity': '200',
            'product_type': str(flyer_product_type.pk),
            'order_type': 'flyer',
            'width': '10.0',
            'height': '21.0',
            'is_closed_size': 'true',
            'paper_weight': '350',
            'cover_printing_type': 'offset',
            'zinc_plates_count': '4',
            'finishing': 'gold_foiling',
            'profit_margin': '30.00'
        }

        summary = OrderAnatomyPersistenceService.persist_order_anatomy(order, post_data)

        # التحقق من تطبيق صمام الحد الأدنى لسحب الأوفست (200 ج)
        press_service = order.services.filter(service_name__startswith='[غلاف أوفست] سحبات').first()
        assert press_service is not None
        assert press_service.total_cost >= Decimal('200.00')

        # التحقق من إضافة كليشيه البصمة الذهبي (150 ج)
        foil_service = order.services.filter(service_name__contains='تشطيب خاص فاخر وكليشيه').first()
        assert foil_service is not None
        assert foil_service.total_cost >= Decimal('230.00')

        # التحقق من إضافة خدمة الريجة والتكسير للورق المطوي السميك 350 جم
        creasing_service = order.services.filter(service_name__contains='ريجة وتكسير').first()
        assert creasing_service is not None
        assert creasing_service.total_cost >= Decimal('80.00')

    def test_job_sheet_and_detail_view_rendering(self, client, test_user, test_customer, catalog_product_type):
        """اختبار رندرة شاشة تفاصيل الطلب وأمر التشغيل المجمع بالمعمارية الهجينة"""
        client.force_login(test_user)

        order = PrintingOrder.objects.create(
            customer=test_customer,
            product_type=catalog_product_type,
            order_type='catalog',
            title='كتالوج هجين جاهز للعرض',
            quantity=1000,
            pages_count=32,
            cover_printing_type='digital',
            inner_printing_type='offset',
            created_by=test_user
        )

        # اختبار شاشة تفاصيل الطلب
        detail_url = reverse('printing_pricing:order_detail', kwargs={'pk': order.pk})
        resp_detail = client.get(detail_url)
        assert resp_detail.status_code == 200
        assert 'بطاقة المواصفات الفنية والهندسة الهجينة' in resp_detail.content.decode('utf-8')
        assert 'ديجيتال' in resp_detail.content.decode('utf-8')

        # اختبار أمر التشغيل المجمع
        sheet_url = reverse('printing_pricing:consolidated_job_sheet', kwargs={'pk': order.pk})
        resp_sheet = client.get(sheet_url)
        assert resp_sheet.status_code == 200
        assert 'أمر تشغيل الغلاف' in resp_sheet.content.decode('utf-8')
        assert 'أمر تشغيل الداخلي والتجليد' in resp_sheet.content.decode('utf-8')

    def test_offset_work_and_turn_and_pantone_spot_colors(self, test_customer, test_user, flyer_product_type):
        """اختبار الأوفست بنمط طبع وقلب (Work & Turn) مع أحبار بانتون مخصوصة"""
        order = PrintingOrder.objects.create(
            customer=test_customer,
            product_type=flyer_product_type,
            order_type='flyer',
            title='بروشور 4 ألوان + بانتون ذهبي طبع وقلب',
            quantity=1000,
            width=Decimal('21.0'),
            height=Decimal('29.7'),
            is_closed_size=False,
            cover_printing_type='offset',
            print_sides_mode='work_turn',
            colors_front=4,
            colors_back=0,
            spot_colors_front=1,
            created_by=test_user
        )

        post_data = {
            'quantity': '1000',
            'product_type': str(flyer_product_type.pk),
            'order_type': 'flyer',
            'width': '21.0',
            'height': '29.7',
            'paper_weight': '300',
            'cover_printing_type': 'offset',
            'print_sides_mode': 'work_turn',
            'colors_front': '4',
            'colors_back': '0',
            'spot_colors_front': '1',
            'profit_margin': '25.00'
        }

        summary = OrderAnatomyPersistenceService.persist_order_anatomy(order, post_data)
        order.refresh_from_db()

        assert order.print_sides_mode == 'work_turn'
        assert order.spot_colors_front == 1

        services = list(order.services.all())
        service_names = [s.service_name for s in services]

        # زنكات: 4 ألوان + 1 بانتون = 5 زنكات
        plates_service = next(s for s in services if 'تجهيز زنكات CTP' in s.service_name)
        assert plates_service.quantity == Decimal('5')

        # خدمة غسيل وتجهيز حوض لون مخصوص (150 ج)
        spot_service = next((s for s in services if 'لون مخصوص' in s.service_name), None)
        assert spot_service is not None
        assert spot_service.total_cost == Decimal('150.00')

        # هدر ورق الطبع والقلب (4%)
        cover_mat = order.materials.filter(material_name__startswith='[غلاف').first()
        assert cover_mat.waste_percentage == Decimal('4.00')

    def test_digital_click_modes_and_large_format_banner(self, test_customer, test_user, flyer_product_type):
        """اختبار أنماط نقرات الديجيتال وطباعة الخامات الكبيرة بالمتر المربع"""
        # 1. اختبار الديجيتال 4/4
        order_digi = PrintingOrder.objects.create(
            customer=test_customer,
            product_type=flyer_product_type,
            order_type='flyer',
            title='كروت شخصية ديجيتال 4/4',
            quantity=1000,
            width=Decimal('9.0'),
            height=Decimal('5.0'),
            cover_printing_type='digital',
            digital_color_mode='4_4',
            created_by=test_user
        )

        post_data_digi = {
            'quantity': '1000',
            'product_type': str(flyer_product_type.pk),
            'order_type': 'flyer',
            'width': '9.0',
            'height': '5.0',
            'cover_printing_type': 'digital',
            'digital_color_mode': '4_4',
            'profit_margin': '25.00'
        }

        OrderAnatomyPersistenceService.persist_order_anatomy(order_digi, post_data_digi)
        order_digi.refresh_from_db()
        assert order_digi.digital_color_mode == '4_4'

        digi_service = next(s for s in order_digi.services.all() if '[غلاف ديجيتال]' in s.service_name)
        assert digi_service.unit_price == Decimal('4.50')

        # 2. اختبار الخامات الكبيرة مع حبر أبيض
        order_banner = PrintingOrder.objects.create(
            customer=test_customer,
            product_type=flyer_product_type,
            order_type='flyer',
            title='يافطة خارجية بانر',
            quantity=2,
            width=Decimal('200.0'),
            height=Decimal('100.0'),
            cover_printing_type='digital_banner',
            banner_sqm_price=Decimal('60.00'),
            has_white_ink=True,
            created_by=test_user
        )

        post_data_banner = {
            'quantity': '2',
            'product_type': str(flyer_product_type.pk),
            'order_type': 'flyer',
            'width': '200.0',
            'height': '100.0',
            'cover_printing_type': 'digital_banner',
            'banner_sqm_price': '60.00',
            'has_white_ink': 'on',
            'profit_margin': '25.00'
        }

        OrderAnatomyPersistenceService.persist_order_anatomy(order_banner, post_data_banner)
        order_banner.refresh_from_db()

        assert order_banner.cover_printing_type == 'digital_banner'
        assert order_banner.has_white_ink is True
        assert order_banner.banner_sqm_price == Decimal('60.00')

        banner_mat = order_banner.materials.filter(material_type='banner').first()
        assert banner_mat is not None
        # المساحة: (200 * 100 / 10000) * 2 = 4.00 م²
        assert banner_mat.quantity == Decimal('4.00')

        banner_service = next(s for s in order_banner.services.all() if '[خامات كبيرة]' in s.service_name)
        assert banner_service.unit_price == Decimal('85.00') # 60 + 25 حبر أبيض
        assert banner_service.total_cost == Decimal('340.00') # 4 م² * 85 ج

    def test_step3_hardcover_materials_and_case_making_service(self, test_customer, catalog_product_type, test_user):
        """اختبار تفكيك خامات الهارد كوفر (كرتون رمادي 2.5 مم + ورق بطانة 150 جم) وخدمة التقفيل الفاخر"""
        order = PrintingOrder.objects.create(
            order_number="HC-BOOK-001",
            title="كتاب تجليد فاخر هارد كوفر",
            customer=test_customer,
            product_type=catalog_product_type,
            order_type='book',
            quantity=500,
            width=Decimal('21.0'),
            height=Decimal('29.7'),
            pages_count=96,
            inner_printing_type='offset',
            inner_print_sides_mode='work_sheet',
            binding_type='hardcover',
            inner_paper_type='couche',
            inner_paper_weight='135',
            created_by=test_user
        )
        post_data = {
            'order_type': 'book',
            'quantity': '500',
            'width': '21.0',
            'height': '29.7',
            'pages_count': '96',
            'inner_printing_type': 'offset',
            'inner_print_sides_mode': 'work_sheet',
            'binding_type': 'hardcover',
            'inner_paper_type': 'couche',
            'inner_paper_weight': '135'
        }
        OrderAnatomyPersistenceService.persist_order_anatomy(order, post_data)
        order.refresh_from_db()

        assert order.binding_type == 'hardcover'
        # التحقق من وجود خامات الكرتون والبطانة
        cardboard_mat = order.materials.filter(material_type='cardboard', material_name__contains='كرتون رمادي مقوى').first()
        assert cardboard_mat is not None
        assert cardboard_mat.unit_cost == Decimal('18.00')

        endpaper_mat = order.materials.filter(material_name__contains='ورق بطانة بيضاء').first()
        assert endpaper_mat is not None

        # التحقق من خدمة التقفيل الهارد كوفر
        hc_service = order.services.filter(service_category='packaging', service_name__contains='Hardcover Case Making').first()
        assert hc_service is not None
        assert hc_service.setup_cost == Decimal('150.00')

    def test_step3_offset_mixed_signatures_and_spot_colors(self, test_customer, catalog_product_type, test_user):
        """اختبار الداخلي الأوفست بالملازم المختلطة (ألوان + أسود + لون بانتون مخصوص)"""
        order = PrintingOrder.objects.create(
            order_number="MIX-SIG-002",
            title="كتالوج بملازم ملونة وأسود وبانتون",
            customer=test_customer,
            product_type=catalog_product_type,
            order_type='catalog',
            quantity=1000,
            width=Decimal('21.0'),
            height=Decimal('29.7'),
            pages_count=64, # 4 ملازم (16 صفحة/ملزمة)
            inner_printing_type='offset',
            inner_print_sides_mode='work_sheet',
            inner_color_mode='mixed',
            inner_spot_colors=1,
            created_by=test_user
        )
        post_data = {
            'order_type': 'catalog',
            'quantity': '1000',
            'width': '21.0',
            'height': '29.7',
            'pages_count': '64',
            'inner_printing_type': 'offset',
            'inner_print_sides_mode': 'work_sheet',
            'inner_color_mode': 'mixed',
            'color_signatures_count': '2', # ملزمتين ألوان (2 * 8 = 16 زنكة)
            'bw_signatures_count': '2',    # ملزمتين أسود (2 * 2 = 4 زنكات)
            'inner_spot_colors': '1',      # لون بانتون على كل الملازم (4 زنكات) -> الإجمالي = 24 زنكة
            'binding_type': 'perfect_binding'
        }
        OrderAnatomyPersistenceService.persist_order_anatomy(order, post_data)
        order.refresh_from_db()

        # التحقق من زنكات الملازم: (2*8) + (2*2) + (1*4) = 24 زنكة
        inner_plates_service = order.services.filter(service_name__contains='زنكات CTP لملازم الداخلي').first()
        assert inner_plates_service is not None
        assert inner_plates_service.quantity == Decimal('24')
        assert inner_plates_service.unit_price == Decimal('85.00')

        # التحقق من خدمة التجليد غراء حراري PUR
        pb_service = order.services.filter(service_name__contains='PUR Perfect Binding').first()
        assert pb_service is not None
        assert pb_service.unit_price == Decimal('1.80')

    def test_step3_ncr_invoices_and_sequential_numbering(self, test_customer, test_user):
        """اختبار دفاتر فواتير NCR وترقيم السيريال وتكعيب البلوكات"""
        invoice_type = ProductType.objects.create(name='دفاتر فواتير وإيصالات', base_archetype='invoice', is_active=True)
        order = PrintingOrder.objects.create(
            order_number="NCR-INV-003",
            title="دفاتر فواتير 3 ألوان كربون",
            customer=test_customer,
            product_type=invoice_type,
            order_type='invoice',
            quantity=20,
            width=Decimal('15.0'),
            height=Decimal('21.0'),
            ncr_sets_count=3,
            ncr_book_capacity=50,
            ncr_serial_start=1001,
            created_by=test_user
        )
        post_data = {
            'product_type': str(invoice_type.pk),
            'order_type': 'invoice',
            'quantity': '20',
            'width': '15.0',
            'height': '21.0',
            'ncr_sets_count': '3',
            'ncr_book_capacity': '50',
            'ncr_serial_start': '1001'
        }
        OrderAnatomyPersistenceService.persist_order_anatomy(order, post_data)
        order.refresh_from_db()

        # السيريال: 1001 إلى 1001 + (20 * 50) - 1 = 2000
        assert order.ncr_serial_start == 1001
        assert order.ncr_serial_end == 2000

        # التحقق من خامات ورق الكربون NCR
        ncr_mat = order.materials.filter(material_name__contains='ورق كربون ذاتي').first()
        assert ncr_mat is not None

        # التحقق من خدمة الترقيم
        numbering_service = order.services.filter(service_name__contains='ترقيم سيريال أوتوماتيك').first()
        assert numbering_service is not None
        assert numbering_service.quantity == Decimal('1000') # 20 * 50

    def test_offset_independent_front_back_and_spot_colors(self, test_customer, flyer_product_type, test_user):
        """اختبار الأوفست وجهين بزنكات وألوان مخصوصة حرة للوجه والظهر (4+1 ألوان أساسية + 1+1 ألوان مخصوصة = 7 زنكات)"""
        order = PrintingOrder.objects.create(
            order_number="OFF-SEPARATE-001",
            title="فلاير 4 ألوان وجه + 1 لون ظهر + لونين مخصوصين",
            customer=test_customer,
            product_type=flyer_product_type,
            order_type='flyer',
            quantity=1000,
            width=Decimal('21.0'),
            height=Decimal('29.7'),
            cover_printing_type='offset',
            print_sides_mode='work_sheet',
            colors_front=4,
            colors_back=1,
            spot_colors_front=1,
            spot_colors_back=1,
            created_by=test_user
        )
        post_data = {
            'quantity': '1000',
            'product_type': str(flyer_product_type.pk),
            'order_type': 'flyer',
            'width': '21.0',
            'height': '29.7',
            'cover_printing_type': 'offset',
            'print_sides_mode': 'work_sheet',
            'colors_front': '4',
            'colors_back': '1',
            'spot_colors_front': '1',
            'spot_colors_back': '1'
        }
        OrderAnatomyPersistenceService.persist_order_anatomy(order, post_data)
        order.refresh_from_db()

        assert order.print_sides_mode == 'work_sheet'
        assert order.colors_front == 4
        assert order.colors_back == 1
        assert order.spot_colors_front == 1
        assert order.spot_colors_back == 1

        # الزنكات: 4 + 1 + 1 + 1 = 7 زنكات
        plates_service = order.services.filter(service_name__contains='تجهيز زنكات CTP').first()
        assert plates_service is not None
        assert plates_service.quantity == Decimal('7')

        # خدمة غسيل أحواض الألوان المخصوصة: 2 لون * 150 ج = 300 ج
        spot_service = order.services.filter(service_name__contains='تجهيز وغسيل حوض حبر لون مخصوص').first()
        assert spot_service is not None
        assert spot_service.quantity == Decimal('2')
        assert spot_service.total_cost == Decimal('300.00')

    def test_offset_double_press_floor_guard(self, test_customer, flyer_product_type, test_user):
        """اختبار صمام المينيمم المزدوج (400 ج) للأوفست وجهين في الكميات الصغيرة مقابل 200 ج للوجه الواحد"""
        # 1. وجهين مستقلين كمية صغيرة (100 فرخ)
        order_ws = PrintingOrder.objects.create(
            order_number="OFF-MIN-WS-001",
            title="فلاير وجهين كمية صغيرة",
            customer=test_customer,
            product_type=flyer_product_type,
            order_type='flyer',
            quantity=100,
            width=Decimal('21.0'),
            height=Decimal('29.7'),
            cover_printing_type='offset',
            print_sides_mode='work_sheet',
            colors_front=4,
            colors_back=4,
            created_by=test_user
        )
        post_data_ws = {
            'quantity': '100',
            'product_type': str(flyer_product_type.pk),
            'order_type': 'flyer',
            'width': '21.0',
            'height': '29.7',
            'cover_printing_type': 'offset',
            'print_sides_mode': 'work_sheet',
            'colors_front': '4',
            'colors_back': '4',
            'press_rate': '45.00'
        }
        OrderAnatomyPersistenceService.persist_order_anatomy(order_ws, post_data_ws)
        press_service_ws = order_ws.services.filter(service_name__contains='سحبات ماكينة أوفست بالتراج').first()
        assert press_service_ws is not None
        # في 100 فرخ: raw_press = 1 ألف * 45 = 45 ج، المينيمم 400 ج -> setup_cost = 400 - 45 = 355 ج -> إجمالي خدمة السحبات = 400 ج
        assert press_service_ws.setup_cost == Decimal('355.00')

        # 2. وجه واحد كمية صغيرة (100 فرخ)
        order_single = PrintingOrder.objects.create(
            order_number="OFF-MIN-SG-001",
            title="فلاير وجه واحد كمية صغيرة",
            customer=test_customer,
            product_type=flyer_product_type,
            order_type='flyer',
            quantity=100,
            width=Decimal('21.0'),
            height=Decimal('29.7'),
            cover_printing_type='offset',
            print_sides_mode='single',
            colors_front=4,
            colors_back=0,
            created_by=test_user
        )
        post_data_single = {
            'quantity': '100',
            'product_type': str(flyer_product_type.pk),
            'order_type': 'flyer',
            'width': '21.0',
            'height': '29.7',
            'cover_printing_type': 'offset',
            'print_sides_mode': 'single',
            'colors_front': '4',
            'colors_back': '0',
            'press_rate': '45.00'
        }
        OrderAnatomyPersistenceService.persist_order_anatomy(order_single, post_data_single)
        press_service_single = order_single.services.filter(service_name__contains='سحبات ماكينة أوفست بالتراج').first()
        assert press_service_single is not None
        # في 100 فرخ وجه واحد: raw_press = 1 ألف * 45 = 45 ج، المينيمم 200 ج -> setup_cost = 200 - 45 = 155 ج -> إجمالي خدمة السحبات = 200 ج
        assert press_service_single.setup_cost == Decimal('155.00')


