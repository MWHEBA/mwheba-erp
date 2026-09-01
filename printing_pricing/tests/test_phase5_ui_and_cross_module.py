import pytest
from decimal import Decimal
from django.urls import reverse
from django.contrib.auth import get_user_model
from customer.models import Customer
from supplier.models import Supplier
from printing_pricing.models import PrintingOrder, OrderSummary, ProductionStage
from printing_pricing.views.order_views import check_can_view_margins

User = get_user_model()

@pytest.fixture
def admin_user(db):
    user = User.objects.create_superuser(
        username='admin_phase5',
        password='password123',
        email='admin@phase5.com'
    )
    return user

@pytest.fixture
def sales_rep_user(db):
    user = User.objects.create_user(
        username='sales_rep_phase5',
        password='password123',
        email='sales@phase5.com'
    )
    return user

@pytest.fixture
def sample_customer(db):
    return Customer.objects.create(
        name='شركة الأمل للدعاية',
        phone='01012345678',
        is_active=True
    )

@pytest.fixture
def sample_courier_supplier(db):
    return Supplier.objects.create(
        name='سائق مشوار حر',
        phone='01198765432',
        supplier_type='services'
    )

@pytest.fixture
def sample_order(db, sample_customer, admin_user):
    order = PrintingOrder.objects.create(
        order_number='ORD-PH5-001',
        title='كتالوج معرض 2026',
        customer=sample_customer,
        order_type='catalog',
        quantity=1000,
        width=Decimal('21.0'),
        height=Decimal('29.7'),
        pages_count=64,
        final_price=Decimal('12500.00'),
        estimated_cost=Decimal('8500.00'),
        current_stage=ProductionStage.PRESS,
        created_by=admin_user,
        updated_by=admin_user
    )
    OrderSummary.objects.create(
        order=order,
        material_cost=Decimal('4500.00'),
        printing_cost=Decimal('2500.00'),
        finishing_cost=Decimal('1500.00'),
        subtotal=Decimal('12500.00'),
        final_price=Decimal('12500.00')
    )
    return order



@pytest.mark.django_db
class TestPhase5UIAndSecurity:

    def test_margin_security_check(self, admin_user, sales_rep_user):
        """التحقق من حجب التكلفة وهوامش الربح عن المناديب وتفعيلها للإدارة"""
        assert check_can_view_margins(admin_user) is True
        assert check_can_view_margins(sales_rep_user) is False

    def test_order_detail_view_admin_context(self, client, admin_user, sample_order):
        """التحقق من تحميل لوحة 360 درجة وصلاحيات الإدارة في شاشة التفاصيل"""
        client.force_login(admin_user)
        url = reverse('printing_pricing:order_detail', kwargs={'pk': sample_order.pk})
        response = client.get(url)

        assert response.status_code == 200
        assert response.context['can_view_margins'] is True
        assert 'summary' in response.context
        assert response.context['order'].order_number == 'ORD-PH5-001'

    def test_order_detail_view_sales_rep_sanitized(self, client, sales_rep_user, sample_order):
        """التحقق من عزل التكاليف للمندوب في شاشة التفاصيل"""
        sample_order.created_by = sales_rep_user
        sample_order.save()

        client.force_login(sales_rep_user)
        url = reverse('printing_pricing:order_detail', kwargs={'pk': sample_order.pk})
        response = client.get(url)

        assert response.status_code == 200
        assert response.context['can_view_margins'] is False
        assert response.context['current_calculations'] == []


    def test_order_list_view_and_stats(self, client, admin_user, sample_order):
        """التحقق من تحميل قائمة المقايسات والكروت الإحصائية"""
        client.force_login(admin_user)
        url = reverse('printing_pricing:order_list')
        response = client.get(url)

        assert response.status_code == 200
        assert 'orders' in response.context
        assert 'stats' in response.context
        assert response.context['stats']['total_orders'] >= 1

    def test_mobile_pricing_view(self, client, admin_user):
        """التحقق من شاشة تسعير الموبايل الميداني"""
        client.force_login(admin_user)
        url = reverse('printing_pricing:mobile_pricing')
        response = client.get(url)

        assert response.status_code == 200
        assert 'customers' in response.context

    def test_generate_whatsapp_quote_api(self, client, admin_user, sample_order):
        """التحقق من توليد رابط الواتساب المشفر لعرض السعر النظيف"""
        client.force_login(admin_user)
        url = reverse('printing_pricing:api_whatsapp_quote_link', kwargs={'order_id': sample_order.pk})
        response = client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'https://wa.me/' in data['whatsapp_url']
        assert 'ORD-PH5-001' in data['whatsapp_url'] or '2026' in data['whatsapp_url']

    def test_dashboard_view(self, client, admin_user, sample_order):
        """التحقق من لوحة التحكم ومؤشرات الأداء"""
        client.force_login(admin_user)
        url = reverse('printing_pricing:dashboard')
        response = client.get(url)

        assert response.status_code == 200
        assert 'stats' in response.context
        assert 'recent_orders' in response.context

    def test_save_quick_mobile_quote_api(self, client, admin_user, sample_customer):
        """التحقق من حفظ المقايسة السريعة كطلب رسمي في النظام من الموبايل"""
        client.force_login(admin_user)
        url = reverse('printing_pricing:api_save_quick_mobile_quote')
        payload = {
            'customer_id': sample_customer.pk,
            'product_type': 'business_card',
            'quantity': 2000,
            'price': '1250.00',
            'title': 'كروت ميدانية مستعجلة'
        }
        response = client.post(url, data=payload, content_type='application/json')

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'order_id' in data
        assert PrintingOrder.objects.filter(pk=data['order_id']).exists()

