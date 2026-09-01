import pytest
import json
from decimal import Decimal
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.db import models

from printing_pricing.models import (
    ProductSize, ProductType, PrintingOrder, OrderMaterial, OrderService, OrderSummary
)
from customer.models import Customer
from printing_pricing.services.anatomy_persistence_service import OrderAnatomyPersistenceService

User = get_user_model()


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        username='testadmin',
        email='admin@test.com',
        password='password123'
    )


@pytest.fixture
def test_customer(db):
    return Customer.objects.create(
        name='شركة الأمل للطباعة والتغليف',
        phone='01012345678',
        is_active=True
    )


@pytest.fixture
def sample_product_sizes(db):
    s1, _ = ProductSize.objects.get_or_create(name='A4 معياري', defaults={'width': Decimal('21.0'), 'height': Decimal('29.7'), 'sort_order': 10, 'is_default': True})
    s2, _ = ProductSize.objects.get_or_create(name='A5 كتيب / فلاير', defaults={'width': Decimal('14.8'), 'height': Decimal('21.0'), 'sort_order': 20})
    s3, _ = ProductSize.objects.get_or_create(name='كارت شخصي فاخر', defaults={'width': Decimal('9.0'), 'height': Decimal('5.0'), 'sort_order': 30})
    return [s1, s2, s3]


@pytest.mark.django_db
class TestProductSizeModel:
    """اختبارات نموذج مقاسات المطبوعات ProductSize"""

    def test_product_size_creation_and_str(self):
        size = ProductSize.objects.create(name='A3 بوستر', width=Decimal('29.7'), height=Decimal('42.0'), sort_order=15)
        assert str(size) == 'A3 بوستر (29.7×42.0 سم)'
        assert size.sort_order == 15
        assert size.is_active is True

    def test_product_size_unique_name(self):
        ProductSize.objects.create(name='UniqueSize', width=Decimal('10.0'), height=Decimal('10.0'))
        with pytest.raises(Exception):
            ProductSize.objects.create(name='UniqueSize', width=Decimal('20.0'), height=Decimal('20.0'))


@pytest.mark.django_db
class TestProductSizeViews:
    """اختبارات عروض الإعدادات والـ AJAX لمقاسات المطبوعات"""

    def test_product_size_list_view(self, client, admin_user, sample_product_sizes):
        client.force_login(admin_user)
        url = reverse('printing_pricing:product_size_list')
        response = client.get(url)
        assert response.status_code == 200
        assert 'A4 معياري' in response.content.decode('utf-8')
        assert 'A5 كتيب' in response.content.decode('utf-8')

    def test_product_size_create_view_ajax(self, client, admin_user):
        client.force_login(admin_user)
        url = reverse('printing_pricing:product_size_create')
        data = {
            'name': 'B5 كتاب',
            'width': '17.6',
            'height': '25.0',
            'sort_order': 50,
            'is_active': 'on'
        }
        response = client.post(url, data, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert response.status_code == 200
        res_json = response.json()
        assert res_json['success'] is True
        assert ProductSize.objects.filter(name='B5 كتاب').exists()

    def test_product_size_update_view_ajax(self, client, admin_user, sample_product_sizes):
        client.force_login(admin_user)
        size = sample_product_sizes[0]
        url = reverse('printing_pricing:product_size_edit', kwargs={'pk': size.pk})
        data = {
            'name': 'A4 معدل',
            'width': '21.0',
            'height': '29.7',
            'sort_order': 10,
            'is_active': 'on'
        }
        response = client.post(url, data, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert response.status_code == 200
        size.refresh_from_db()
        assert size.name == 'A4 معدل'

    def test_product_size_toggle_active(self, client, admin_user, sample_product_sizes):
        client.force_login(admin_user)
        size = sample_product_sizes[1]
        assert size.is_active is True
        url = reverse('printing_pricing:product_size_toggle_active', kwargs={'pk': size.pk})
        response = client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert response.status_code == 200
        size.refresh_from_db()
        assert size.is_active is False

    def test_product_size_delete_modal_get(self, client, admin_user, sample_product_sizes):
        client.force_login(admin_user)
        size = sample_product_sizes[0]
        url = reverse('printing_pricing:product_size_delete', kwargs={'pk': size.pk})
        response = client.get(url)
        assert response.status_code == 200
        assert 'تأكيد حذف مقاس المطبوع' in response.content.decode('utf-8')

    def test_product_size_delete_post_ajax(self, client, admin_user, sample_product_sizes):
        client.force_login(admin_user)
        size = sample_product_sizes[2]
        size_id = size.pk
        url = reverse('printing_pricing:product_size_delete', kwargs={'pk': size_id})
        response = client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert response.status_code == 200
        res_json = response.json()
        assert res_json['success'] is True
        assert not ProductSize.objects.filter(pk=size_id).exists()

    def test_product_size_delete_protected_error(self, client, admin_user, test_customer, sample_product_sizes):
        client.force_login(admin_user)
        size = sample_product_sizes[0]
        
        # إنشاء طلب مرتبط بالمقاس
        PrintingOrder.objects.create(
            customer=test_customer,
            title='طلب مرتبط بالمقاس',
            product_size=size,
            quantity=1000,
            created_by=admin_user
        )

        url = reverse('printing_pricing:product_size_delete', kwargs={'pk': size.pk})
        response = client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert response.status_code == 400
        res_json = response.json()
        assert res_json['success'] is False
        assert 'لا يمكن حذف هذا المقاس' in res_json['message']



@pytest.mark.django_db
class TestOrderProductSizeIntegration:
    """اختبارات تكامل مقاس المطبوع واتجاه الطباعة في طلب التسعير"""

    def test_order_creation_with_product_size_and_orientation(self, client, admin_user, test_customer, sample_product_sizes):
        client.force_login(admin_user)
        size = sample_product_sizes[0] # A4

        order = PrintingOrder.objects.create(
            customer=test_customer,
            title='طباعة كتيب تجريبي',
            product_size=size,
            print_orientation='landscape',
            width=Decimal('29.7'),
            height=Decimal('21.0'),
            quantity=1000,
            created_by=admin_user
        )

        assert order.get_dimensions_display() == 'A4 معياري (29.7×21 سم) - عرضي (أفقي)'

    def test_order_custom_size_display(self, client, admin_user, test_customer):
        order = PrintingOrder.objects.create(
            customer=test_customer,
            title='طباعة علبة بمقاس مخصص',
            product_size=None,
            print_orientation='portrait',
            width=Decimal('15.5'),
            height=Decimal('35.0'),
            quantity=500,
            created_by=admin_user
        )

        assert order.get_dimensions_display() == 'مقاس مخصص (15.5×35 سم) - طولي (رأسي)'

    def test_anatomy_persistence_preserves_size_and_orientation(self, admin_user, test_customer, sample_product_sizes):
        size = sample_product_sizes[2] # كارت شخصي
        order = PrintingOrder.objects.create(
            customer=test_customer,
            title='طلب كروت شخصية',
            quantity=2000,
            created_by=admin_user
        )

        post_data = {
            'product_size': str(size.pk),
            'print_orientation': 'landscape',
            'width': '9.0',
            'height': '5.0',
            'quantity': '2000',
            'paper_weight': '350',
            'plate_count': '4'
        }

        OrderAnatomyPersistenceService.persist_order_anatomy(order, post_data)
        order.refresh_from_db()
        assert order.product_size == size
        assert order.print_orientation == 'landscape'

    def test_duplicate_order_preserves_product_size_and_orientation(self, client, admin_user, test_customer, sample_product_sizes):
        client.force_login(admin_user)
        size = sample_product_sizes[1] # A5

        original = PrintingOrder.objects.create(
            customer=test_customer,
            title='أمر فلاير أصلي',
            product_size=size,
            print_orientation='landscape',
            width=Decimal('21.0'),
            height=Decimal('14.8'),
            quantity=5000,
            created_by=admin_user
        )

        url = reverse('printing_pricing:duplicate_order', kwargs={'pk': original.pk})
        response = client.post(url)
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

        duplicated = PrintingOrder.objects.get(pk=data['new_order_id'])
        assert duplicated.product_size == size
        assert duplicated.print_orientation == 'landscape'
        assert duplicated.width == Decimal('21.0')
        assert duplicated.height == Decimal('14.8')

    def test_closed_size_open_dimensions_calculation(self, admin_user, test_customer, sample_product_sizes):
        size = sample_product_sizes[0] # A4 (21 x 29.7)
        pt_catalog = ProductType.objects.create(name='كتالوج شركات', base_archetype='catalog')

        order = PrintingOrder.objects.create(
            customer=test_customer,
            title='كتالوج A4 مع غلاف',
            product_type=pt_catalog,
            product_size=size,
            is_closed_size=True,
            open_direction='right',
            width=Decimal('21.0'),
            height=Decimal('29.7'),
            pages_count=4,
            quantity=1000,
            created_by=admin_user
        )

        open_w, open_h = order.get_open_dimensions()
        assert open_w == Decimal('42.0')
        assert open_h == Decimal('29.7')
        assert 'مقفول' in order.get_dimensions_display()
        assert 'عربي (يمين)' in order.get_dimensions_display()

    def test_top_open_direction_calculation(self, admin_user, test_customer, sample_product_sizes):
        size = sample_product_sizes[0] # A4 (21 x 29.7)
        pt_invoice = ProductType.objects.create(name='دفتر إيصالات', base_archetype='invoice')

        order = PrintingOrder.objects.create(
            customer=test_customer,
            title='دفتر إيصالات فتح رأسي',
            product_type=pt_invoice,
            product_size=size,
            is_closed_size=True,
            open_direction='top',
            width=Decimal('21.0'),
            height=Decimal('29.7'),
            quantity=500,
            created_by=admin_user
        )

        open_w, open_h = order.get_open_dimensions()
        assert open_w == Decimal('21.0')
        assert open_h == Decimal('59.4')
        assert 'من أعلى (رأسي)' in order.get_dimensions_display()

    def test_trifold_brochure_open_dimensions(self, admin_user, test_customer):
        pt_brochure = ProductType.objects.create(name='بروشور 3 بوابة', base_archetype='brochure')

        order = PrintingOrder.objects.create(
            customer=test_customer,
            title='بروشور ثلاثي الطي',
            product_type=pt_brochure,
            is_closed_size=True,
            open_direction='right',
            width=Decimal('9.9'),
            height=Decimal('21.0'),
            quantity=2500,
            created_by=admin_user
        )

        open_w, open_h = order.get_open_dimensions()
        assert open_w == Decimal('29.7')
        assert open_h == Decimal('21.0')

    def test_catalog_spine_calculation(self, admin_user, test_customer, sample_product_sizes):
        size = sample_product_sizes[0] # A4
        pt_catalog = ProductType.objects.create(name='كتالوج سنوي', base_archetype='catalog')

        order = PrintingOrder.objects.create(
            customer=test_customer,
            title='كتالوج 64 صفحة كعب مربع',
            product_type=pt_catalog,
            product_size=size,
            is_closed_size=True,
            open_direction='right',
            width=Decimal('21.0'),
            height=Decimal('29.7'),
            pages_count=64,
            quantity=1000,
            created_by=admin_user
        )

        open_w, open_h = order.get_open_dimensions()
        # 21 * 2 + (64/2 * 0.012) = 42 + 0.384 ≈ 42.4
        assert open_w == Decimal('42.4')
        assert open_h == Decimal('29.7')

    def test_flat_product_not_closed_size(self, admin_user, test_customer, sample_product_sizes):
        size = sample_product_sizes[0] # A4 (21 x 29.7)
        pt_flyer = ProductType.objects.create(name='فلاير مفرود', base_archetype='flyer')

        order = PrintingOrder.objects.create(
            customer=test_customer,
            title='فلاير A4 مفرود',
            product_type=pt_flyer,
            product_size=size,
            is_closed_size=False,
            width=Decimal('21.0'),
            height=Decimal('29.7'),
            quantity=1000,
            created_by=admin_user
        )

        open_w, open_h = order.get_open_dimensions()
        assert open_w == Decimal('21.0')
        assert open_h == Decimal('29.7')
        assert 'مقفول' not in order.get_dimensions_display()

    def test_duplicate_order_preserves_open_direction(self, client, admin_user, test_customer, sample_product_sizes):
        client.force_login(admin_user)
        size = sample_product_sizes[0]

        original = PrintingOrder.objects.create(
            customer=test_customer,
            title='كتالوج أصلي مع فتح إنجليزي',
            product_size=size,
            is_closed_size=True,
            open_direction='left',
            print_orientation='portrait',
            width=Decimal('21.0'),
            height=Decimal('29.7'),
            quantity=1000,
            created_by=admin_user
        )

        url = reverse('printing_pricing:duplicate_order', kwargs={'pk': original.pk})
        response = client.post(url)
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

        duplicated = PrintingOrder.objects.get(pk=data['new_order_id'])
        assert duplicated.is_closed_size is True
        assert duplicated.open_direction == 'left'


