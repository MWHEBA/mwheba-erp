"""
اختبارات التحقق من رندرة قالب order_form.html وشاشات الإنشاء والتعديل بدون أخطاء
Order Form Template Rendering & Syntax Tests
"""
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from customer.models import Customer
from printing_pricing.models import PrintingOrder

User = get_user_model()


@pytest.mark.django_db
class TestOrderFormRendering:
    """اختبارات رندرة شاشة تسعير المطبوعات"""

    def setup_method(self):
        self.user = User.objects.create_superuser(
            username='admin_user',
            email='admin@mwheba.com',
            password='password123'
        )
        self.customer = Customer.objects.create(
            name='شركة النجاح',
            phone='01012345678'
        )

    def test_order_create_view_renders_successfully(self, client):
        """التحقق من فتح شاشة إنشاء طلب تسعير جديد بدون أي خطأ في القوالب"""
        client.force_login(self.user)
        url = reverse('printing_pricing:order_create')
        response = client.get(url)
        assert response.status_code == 200
        assert 'card_step1_scope' in response.content.decode('utf-8')
        assert 'card_step2_cover' in response.content.decode('utf-8')
        assert 'card_step3_inner' in response.content.decode('utf-8')
        assert 'summary_main_card' in response.content.decode('utf-8')

    def test_order_update_view_renders_successfully(self, client):
        """التحقق من فتح شاشة تعديل طلب تسعير قائم بدون أي خطأ في القوالب"""
        client.force_login(self.user)
        order = PrintingOrder.objects.create(
            order_number='ORD-TEST-999',
            customer=self.customer,
            title='طباعة بروشور دعائي',
            order_type='flyer',
            quantity=1000,
            created_by=self.user
        )
        url = reverse('printing_pricing:order_update', kwargs={'pk': order.pk})
        response = client.get(url)
        assert response.status_code == 200
        assert 'ORD-TEST-999' in response.content.decode('utf-8')
