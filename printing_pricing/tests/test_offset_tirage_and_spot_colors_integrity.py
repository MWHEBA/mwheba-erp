"""
حزمة اختبارات شاملة للتأكد من نزاهة تسعير طباعة الأوفست واستقلالية التراج عن الألوان والزنكات
Test Suite for Offset Tirage Independence, Machine Cuts, Signature Tirages, and Spot Color Washup
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from customer.models import Customer
from printing_pricing.models import PrintingOrder, OrderService, ProductType
from printing_pricing.services.anatomy_persistence_service import OrderAnatomyPersistenceService

User = get_user_model()


@pytest.fixture
def test_user(db):
    return User.objects.create_user(username='estimator_tester', password='password123', is_staff=True)


@pytest.fixture
def test_customer(db):
    return Customer.objects.create(name='عميل تجارب تسعير الأوفست')


@pytest.fixture
def flyer_type(db):
    return ProductType.objects.create(name='فلاير', base_archetype='flyer', is_active=True)


@pytest.fixture
def catalog_type(db):
    return ProductType.objects.create(name='كتالوج', base_archetype='catalog', is_active=True)


@pytest.mark.django_db
class TestOffsetTirageAndSpotColorsIntegrity:
    """اختبارات مطابقة تسعير الأوفست واستقلالية التراج عن الألوان والزنكات 100%"""

    def test_cover_tirage_independent_of_colors_count(self, test_customer, test_user, flyer_type):
        """1. التأكد من أن تغيير عدد الألوان الأساسية لا يغير عدد التراجات أو تكلفة السحب نهائياً"""
        # الطلب الأول: لون واحد وجه
        order_1_color = PrintingOrder.objects.create(
            customer=test_customer,
            product_type=flyer_type,
            order_type='flyer',
            title='فلاير 1 لون',
            quantity=1000,
            width=Decimal('14.8'),
            height=Decimal('21.0'),
            cover_printing_type='offset',
            print_sides_mode='single',
            created_by=test_user
        )
        post_data_1 = {
            'quantity': '1000',
            'product_type': str(flyer_type.pk),
            'order_type': 'flyer',
            'width': '14.8',
            'height': '21.0',
            'cover_printing_type': 'offset',
            'colors_front': '1',
            'colors_back': '0',
            'print_sides_mode': 'single',
            'zinc_plates_count': '1',
            'press_rate': '45.00',
            'plate_price': '85.00'
        }
        OrderAnatomyPersistenceService.persist_order_anatomy(order_1_color, post_data_1)
        press_svc_1 = order_1_color.services.filter(service_name__startswith='[غلاف أوفست] سحبات').first()
        plate_svc_1 = order_1_color.services.filter(service_name__startswith='[غلاف أوفست] تجهيز زنكات CTP').first()

        assert press_svc_1 is not None
        assert plate_svc_1 is not None
        assert plate_svc_1.quantity == Decimal('1')  # زنكة واحدة
        assert plate_svc_1.total_cost == Decimal('85.00')

        # الطلب الثاني: 4 ألوان وجه لنفس الكمية والمقاس
        order_4_colors = PrintingOrder.objects.create(
            customer=test_customer,
            product_type=flyer_type,
            order_type='flyer',
            title='فلاير 4 ألوان',
            quantity=1000,
            width=Decimal('14.8'),
            height=Decimal('21.0'),
            cover_printing_type='offset',
            print_sides_mode='single',
            created_by=test_user
        )
        post_data_4 = {
            'quantity': '1000',
            'product_type': str(flyer_type.pk),
            'order_type': 'flyer',
            'width': '14.8',
            'height': '21.0',
            'cover_printing_type': 'offset',
            'colors_front': '4',
            'colors_back': '0',
            'print_sides_mode': 'single',
            'zinc_plates_count': '4',
            'press_rate': '45.00',
            'plate_price': '85.00'
        }
        OrderAnatomyPersistenceService.persist_order_anatomy(order_4_colors, post_data_4)
        press_svc_4 = order_4_colors.services.filter(service_name__startswith='[غلاف أوفست] سحبات').first()
        plate_svc_4 = order_4_colors.services.filter(service_name__startswith='[غلاف أوفست] تجهيز زنكات CTP').first()

        assert plate_svc_4.quantity == Decimal('4')  # 4 زنكات
        assert plate_svc_4.total_cost == Decimal('340.00')

        # النتيجة الجوهرية: تكلفة وسحبات وتراج الماكينة متطابقة 100% بين اللون الواحد والـ 4 ألوان
        assert press_svc_1.quantity == press_svc_4.quantity
        assert press_svc_1.total_cost == press_svc_4.total_cost

    def test_spot_colors_add_washup_fee_without_altering_tirage(self, test_customer, test_user, flyer_type):
        """2. التأكد من أن إضافة ألوان بانتون مخصوصة يضيف زنكاتها وغسيل الحوض (150 ج) دون تغيير التراج"""
        order = PrintingOrder.objects.create(
            customer=test_customer,
            product_type=flyer_type,
            order_type='flyer',
            title='فلاير لون مخصوص بانتون',
            quantity=1000,
            width=Decimal('14.8'),
            height=Decimal('21.0'),
            cover_printing_type='offset',
            print_sides_mode='single',
            spot_colors_front=2,  # لونين مخصوص
            created_by=test_user
        )
        post_data = {
            'quantity': '1000',
            'product_type': str(flyer_type.pk),
            'order_type': 'flyer',
            'width': '14.8',
            'height': '21.0',
            'cover_printing_type': 'offset',
            'colors_front': '4',
            'spot_colors_front': '2',
            'print_sides_mode': 'single',
            'zinc_plates_count': '6',  # 4 ألوان أساسية + 2 مخصوص
            'press_rate': '45.00',
            'plate_price': '85.00'
        }
        OrderAnatomyPersistenceService.persist_order_anatomy(order, post_data)

        # التحقق من خدمة الزنكات: 6 زنكات
        plate_svc = order.services.filter(service_name__startswith='[غلاف أوفست] تجهيز زنكات CTP').first()
        assert plate_svc.quantity == Decimal('6')
        assert plate_svc.total_cost == Decimal('510.00')

        # التحقق من خدمة غسيل أحواض الألوان المخصوصة: 2 لون * 150 ج = 300 ج
        washup_svc = order.services.filter(service_name__contains='تجهيز وغسيل حوض حبر لون مخصوص').first()
        assert washup_svc is not None
        assert washup_svc.quantity == Decimal('2')
        assert washup_svc.unit_price == Decimal('150.00')
        assert washup_svc.total_cost == Decimal('300.00')

        # التحقق من أن سحبات التراج لم تتغير وظلت 1 تراج (45 ج)
        press_svc = order.services.filter(service_name__startswith='[غلاف أوفست] سحبات').first()
        assert press_svc.total_cost == Decimal('45.00')

    def test_machine_cuts_multiplication_in_backend(self, test_customer, test_user, flyer_type):
        """3. التحقق من مطابقة سحبات الباك إند بضرب معامل تفصيل الفرخ للماكينة (machine_cuts = 2 لنصف فرخ)"""
        order = PrintingOrder.objects.create(
            customer=test_customer,
            product_type=flyer_type,
            order_type='flyer',
            title='فلاير ماكينة 50x70',
            quantity=10000,
            width=Decimal('21.0'),
            height=Decimal('29.7'),
            cover_printing_type='offset',
            created_by=test_user
        )
        post_data = {
            'quantity': '10000',
            'product_type': str(flyer_type.pk),
            'order_type': 'flyer',
            'width': '21.0',
            'height': '29.7',
            'cover_printing_type': 'offset',
            'cover_press_machine': '50x70',
            'piece_size': '50x70',  # تفصيل نصف فرخ -> machine_cuts = 2
            'press_rate': '45.00',
            'plate_price': '85.00'
        }
        OrderAnatomyPersistenceService.persist_order_anatomy(order, post_data)
        press_svc = order.services.filter(service_name__startswith='[غلاف أوفست] سحبات').first()
        assert press_svc is not None
        # في 10,000 نسخة A4 على فرخ كبير (9 على الفرخ) -> حوالي 1150 فرخ كبير
        # سحبات الماكينة الـ 50x70 يجب أن تضرب في 2 سحبة لكل فرخ كبير -> ~2300 سحبة (3 تراج)
        assert press_svc.quantity >= Decimal('3')

    def test_inner_signatures_calculated_per_signature(self, test_customer, test_user, catalog_type):
        """4. التحقق من احتساب تراج الداخلي مستقلاً لكل ملزمة (Signatures Tirages) لمنع خسارة الملازم"""
        order = PrintingOrder.objects.create(
            customer=test_customer,
            product_type=catalog_type,
            order_type='catalog',
            title='كتالوج 64 صفحة 4 ملازم',
            quantity=500,  # 500 كتالوج
            width=Decimal('21.0'),
            height=Decimal('29.7'),
            pages_count=64,  # 4 ملازم A4 (16 صفحة للملزمة)
            inner_printing_type='offset',
            cover_printing_type='offset',
            created_by=test_user
        )
        post_data = {
            'quantity': '500',
            'product_type': str(catalog_type.pk),
            'order_type': 'catalog',
            'width': '21.0',
            'height': '29.7',
            'pages_count': '64',
            'color_signatures_count': '4',  # 4 ملازم ألوان
            'bw_signatures_count': '0',
            'inner_printing_type': 'offset',
            'cover_printing_type': 'offset',
            'inner_press_rate': '45.00',
            'inner_print_sides_mode': 'work_turn'
        }
        OrderAnatomyPersistenceService.persist_order_anatomy(order, post_data)
        inner_press_svc = order.services.filter(service_name__startswith='[داخلي أوفست] سحبات').first()
        assert inner_press_svc is not None
        # كل ملزمة تحتاج 500 سحبة = 1 تراج مستقل
        # 4 ملازم × 1 تراج = 4 تراجات = 4 * 45 = 180 ج (وليس 2 تراج بـ 90 ج كالسابق)
        assert inner_press_svc.quantity == Decimal('4')
        assert inner_press_svc.total_cost == Decimal('180.00')

    def test_inner_spot_colors_washup_service(self, test_customer, test_user, catalog_type):
        """5. التحقق من إنشاء خدمة غسيل أحواض الحبر للألوان المخصوصة في الداخلي (150 ج)"""
        order = PrintingOrder.objects.create(
            customer=test_customer,
            product_type=catalog_type,
            order_type='catalog',
            title='كتالوج داخلي لون بانتون',
            quantity=1000,
            pages_count=16,
            inner_printing_type='offset',
            inner_spot_colors=2,  # لونين بانتون مخصوص للداخلي
            created_by=test_user
        )
        post_data = {
            'quantity': '1000',
            'product_type': str(catalog_type.pk),
            'order_type': 'catalog',
            'pages_count': '16',
            'inner_printing_type': 'offset',
            'inner_spot_colors': '2',
            'color_signatures_count': '2',
            'bw_signatures_count': '0',
        }
        OrderAnatomyPersistenceService.persist_order_anatomy(order, post_data)
        inner_washup_svc = order.services.filter(service_name__contains='[داخلي أوفست] تجهيز وغسيل حوض حبر لون مخصوص').first()
        assert inner_washup_svc is not None
        assert inner_washup_svc.quantity == Decimal('2')
        assert inner_washup_svc.unit_price == Decimal('150.00')
        assert inner_washup_svc.total_cost == Decimal('300.00')

    def test_manual_plates_override_preserved_with_independent_tirage(self, test_customer, test_user, flyer_type):
        """6. التحقق من احترام التعديل اليدوي لعدد الزنكات وثبات التراج مستقلاً عنها"""
        order = PrintingOrder.objects.create(
            customer=test_customer,
            product_type=flyer_type,
            order_type='flyer',
            title='فلاير زنكات يدوية',
            quantity=1000,
            width=Decimal('14.8'),
            height=Decimal('21.0'),
            cover_printing_type='offset',
            print_sides_mode='single',
            created_by=test_user
        )
        post_data = {
            'quantity': '1000',
            'product_type': str(flyer_type.pk),
            'order_type': 'flyer',
            'width': '14.8',
            'height': '21.0',
            'cover_printing_type': 'offset',
            'colors_front': '4',
            'zinc_plates_count': '8',  # تعديل يدوي: المستخدم فرض 8 زنكات بدلاً من 4
            'plate_price': '85.00',
            'press_rate': '45.00'
        }
        OrderAnatomyPersistenceService.persist_order_anatomy(order, post_data)
        plate_svc = order.services.filter(service_name__startswith='[غلاف أوفست] تجهيز زنكات CTP').first()
        press_svc = order.services.filter(service_name__startswith='[غلاف أوفست] سحبات').first()

        # تم احترام التعديل اليدوي للزنكات: 8 زنكات * 85 = 680 ج
        assert plate_svc.quantity == Decimal('8')
        assert plate_svc.total_cost == Decimal('680.00')

        # التراج الميكانيكي لم يتغير وظل 1 تراج (45 ج)
        assert press_svc.quantity == Decimal('1')
        assert press_svc.total_cost == Decimal('45.00')

    def test_archived_plates_has_zero_cost_with_active_tirage(self, test_customer, test_user, flyer_type):
        """7. التحقق من زنكات الأرشيف (0 ج) مع استمرار حساب التراج الميكانيكي بشكل كامل"""
        order = PrintingOrder.objects.create(
            customer=test_customer,
            product_type=flyer_type,
            order_type='flyer',
            title='فلاير زنكات من الأرشيف',
            quantity=2000,
            width=Decimal('14.8'),
            height=Decimal('21.0'),
            cover_printing_type='offset',
            created_by=test_user
        )
        post_data = {
            'quantity': '2000',
            'product_type': str(flyer_type.pk),
            'order_type': 'flyer',
            'width': '14.8',
            'height': '21.0',
            'cover_printing_type': 'offset',
            'colors_front': '4',
            'is_plates_archived': '1',  # زنكات أرشيف
            'plates_option': 'archived',
            'plate_price': '85.00',
            'press_rate': '45.00'
        }
        OrderAnatomyPersistenceService.persist_order_anatomy(order, post_data)
        plate_svc = order.services.filter(service_name__startswith='[غلاف أوفست] تجهيز زنكات CTP').first()
        press_svc = order.services.filter(service_name__startswith='[غلاف أوفست] سحبات').first()

        assert plate_svc is not None
        assert plate_svc.unit_price == Decimal('0.00')
        assert plate_svc.total_cost == Decimal('0.00')

        # التراج يحسب طبيعياً (2000 سحبة على ربع فرخ = 1 تراج = 45 ج)
        assert press_svc is not None
        assert press_svc.total_cost == Decimal('45.00')
