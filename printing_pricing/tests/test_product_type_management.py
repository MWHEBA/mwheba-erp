import pytest
import json
from decimal import Decimal
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.db.models import ProtectedError

from printing_pricing.models import (
    ProductType, PrintingOrder, PricingStatus, OrderType
)
from customer.models import Customer
from printing_pricing.services.anatomy_persistence_service import OrderAnatomyPersistenceService

User = get_user_model()

@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        username='admin_test',
        email='admin@test.com',
        password='password123'
    )

@pytest.fixture
def test_customer(db):
    return Customer.objects.create(
        name='شركة الأمل للطباعة',
        code='CUST-TEST-001',
        phone='01012345678'
    )

@pytest.mark.django_db
class TestProductTypeManagement:
    """اختبارات إدارة أنواع المطبوعات والتصميم الموحد والترتيب"""

    def test_product_type_crud_and_sorting(self, client, admin_user):
        client.force_login(admin_user)

        # 1. إنشاء نوع جديد
        create_url = reverse('printing_pricing:product_type_create')
        res = client.post(create_url, {
            'name': 'كارت شخصي فاخر',
            'base_archetype': 'flyer',
            'sort_order': 15,
            'description': 'كروت شخصية 9×5 سم سلوفان مط وجهين',
            'is_active': True,
            'is_default': False
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert res.status_code in [200, 302]
        
        pt = ProductType.objects.get(name='كارت شخصي فاخر')
        assert pt.base_archetype == 'flyer'
        assert pt.sort_order == 15

        # 2. التحقق من منع تكرار نفس الاسم
        res_dup = client.post(create_url, {
            'name': 'كارت شخصي فاخر',
            'base_archetype': 'flyer',
            'sort_order': 16,
            'is_active': True
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        # Form error
        data = res_dup.json() if res_dup.status_code == 200 else {}
        assert not data.get('success', False)

    def test_reorder_and_toggle_active_endpoints(self, client, admin_user):
        client.force_login(admin_user)

        # حذف الأصناف المؤقتة لبدء قائمة نظيفة للاختبار
        ProductType.objects.all().delete()
        pt1 = ProductType.objects.create(name='نوع 1', base_archetype='flyer', sort_order=10)
        pt2 = ProductType.objects.create(name='نوع 2', base_archetype='catalog', sort_order=20)

        # Reorder pt2 UP
        reorder_url = reverse('printing_pricing:product_type_reorder')
        res = client.post(
            reorder_url,
            data=json.dumps({'item_id': pt2.pk, 'direction': 'up'}),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        assert res.status_code == 200
        assert res.json()['success'] is True

        pt2.refresh_from_db()
        pt1.refresh_from_db()
        assert pt2.sort_order < pt1.sort_order

        # Toggle Active
        toggle_url = reverse('printing_pricing:product_type_toggle_active', kwargs={'pk': pt1.pk})
        res_toggle = client.post(toggle_url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert res_toggle.status_code == 200
        assert res_toggle.json()['is_active'] is False
        pt1.refresh_from_db()
        assert pt1.is_active is False

    def test_protected_error_delete_guard(self, client, admin_user, test_customer):
        client.force_login(admin_user)

        pt = ProductType.objects.create(name='فولدر للطلب', base_archetype='folder', sort_order=30)
        order = PrintingOrder.objects.create(
            order_number='ORD-PT-001',
            customer=test_customer,
            title='طلب فولدر',
            product_type=pt,
            order_type='folder',
            quantity=1000,
            created_by=admin_user,
            updated_by=admin_user
        )

        delete_url = reverse('printing_pricing:product_type_delete', kwargs={'pk': pt.pk})
        res = client.post(delete_url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert res.status_code == 400
        data = res.json()
        assert data['success'] is False
        assert 'لا يمكن حذف هذا الصنف' in data['message']
        assert ProductType.objects.filter(pk=pt.pk).exists()

    def test_duplicate_order_preserves_product_type(self, client, admin_user, test_customer):
        client.force_login(admin_user)

        pt = ProductType.objects.create(name='كتالوج سنوي', base_archetype='catalog', sort_order=20)
        order = PrintingOrder.objects.create(
            order_number='ORD-PT-ORIG',
            customer=test_customer,
            title='كتالوج الشركة 2026',
            product_type=pt,
            order_type='catalog',
            quantity=500,
            created_by=admin_user,
            updated_by=admin_user
        )

        dup_url = reverse('printing_pricing:duplicate_order', kwargs={'pk': order.pk})
        res = client.post(dup_url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert res.status_code == 200
        new_order_id = res.json()['new_order_id']

        cloned_order = PrintingOrder.objects.get(pk=new_order_id)
        assert cloned_order.product_type == pt
        assert cloned_order.order_type == 'catalog'
        assert 'نسخة' in cloned_order.title

    def test_anatomy_persistence_fallback_resolution(self, db, admin_user, test_customer):
        pt_flyer = ProductType.objects.create(name='مطبوع مفرود عام', base_archetype='flyer', is_active=True, sort_order=10)

        order = PrintingOrder.objects.create(
            order_number='ORD-FALLBACK-001',
            customer=test_customer,
            title='فلاير سريع',
            quantity=1000,
            created_by=admin_user,
            updated_by=admin_user
        )

        # POST data from API without product_type ID, only order_type='flyer'
        post_data = {
            'order_type': 'flyer',
            'quantity': '2000',
            'width': '21.0',
            'height': '29.7',
            'paper_weight': '150'
        }

        OrderAnatomyPersistenceService.persist_order_anatomy(order, post_data)
        order.refresh_from_db()
        assert order.product_type is not None
        assert order.product_type.base_archetype == 'flyer'
        assert order.order_type == 'flyer'
