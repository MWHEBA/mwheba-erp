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
        """التحقق من فتح شاشة إنشاء طلب تسعير جديد بدون أي خطأ في القوالب وبوجود عناصر البوابات"""
        client.force_login(self.user)
        url = reverse('printing_pricing:order_create')
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'card_step1_scope' in content
        assert 'card_step2_cover' in content
        assert 'card_step3_inner' in content
        assert 'summary_main_card' in content
        # التحقق من عناصر معمارية البوابة المزدوجة
        assert 'step1_status_badge' in content
        assert 'btn_quick_quote_fill' in content
        assert 'btn_proceed_to_step2' in content
        assert 'step2_technical_gate_notice' in content
        assert 'sidebar_commit_gate_alert' in content

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

    def test_plate_size_list_view_renders_successfully(self, client):
        """التحقق من فتح شاشة مقاسات زنكات CTP بدون أي خطأ في القوالب"""
        client.force_login(self.user)
        url = reverse('printing_pricing:plate_size_list')
        response = client.get(url)
        assert response.status_code == 200
        assert 'مقاسات زنكات CTP' in response.content.decode('utf-8')

    def test_pricing_order_form_requires_customer_and_title(self):
        """التحقق من رفض النموذج عند غياب العميل أو وصف الطلب"""
        from printing_pricing.forms import PricingOrderForm
        form = PricingOrderForm(data={
            'quantity': 1000,
            'order_type': 'flyer',
            'width': 21.0,
            'height': 29.7,
        })
        assert not form.is_valid()
        assert 'customer_name' in form.errors
        assert 'title' in form.errors

    def test_pricing_order_form_valid_with_cash_customer_and_title(self):
        """التحقق من خلو أخطاء العميل والوصف عند ملء العميل النقدي والوصف"""
        from printing_pricing.forms import PricingOrderForm
        form = PricingOrderForm(data={
            'customer_name': 'عميل استفسار سريع',
            'title': 'طباعة فلاير A4',
            'quantity': 1000,
            'order_type': 'flyer',
            'width': 21.0,
            'height': 29.7,
            'order_date': '2026-09-06',
        })
        form.is_valid()
        assert 'customer_name' not in form.errors
        assert 'customer' not in form.errors
        assert 'title' not in form.errors
