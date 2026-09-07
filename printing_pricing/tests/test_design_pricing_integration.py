import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from customer.models import Customer
from printing_pricing.models import (
    PrintingOrder, OrderService, OrderSummary, ProductType, ProductSize
)
from printing_pricing.services.pricing_engine import PrintingCalculationEngine
from printing_pricing.services.anatomy_persistence_service import OrderAnatomyPersistenceService

User = get_user_model()


@pytest.mark.django_db
class TestDesignPricingIntegration:
    """
    اختبارات معمارية متكاملة لجزئية التصميم والتجهيز الفني
    """

    @pytest.fixture(autouse=True)
    def setup_data(self):
        self.user = User.objects.create_superuser(
            username='admin_designer',
            email='admin@design.test',
            password='Password123!'
        )
        self.client = APIClient()
        self.client.force_login(self.user)

        self.customer = Customer.objects.create(
            name='شركة الاختبار للتصميم',
            code='CUST-DSG-001',
            is_active=True
        )

        self.product_type = ProductType.objects.create(
            name='فلاير دعائي',
            base_archetype='flyer',
            is_active=True,
            is_default=True
        )

        self.product_size = ProductSize.objects.create(
            name='A4',
            width=Decimal('21.0'),
            height=Decimal('29.7'),
            is_active=True,
            is_default=True
        )

    def test_pricing_engine_design_fee_separation(self):
        """
        اختبار محرك الحسابات: التحقق من فصل سعر القطعة الصناعي عن أتعاب التصميم
        """
        params = {
            'product_type': 'flyer',
            'quantity': 1000,
            'profit_margin': '25.0',
            'design_service_type': 'NEW_CONCEPT',
            'design_fee': '500.00',
            'width': 21.0,
            'height': 29.7
        }

        result = PrintingCalculationEngine.calculate(params)
        assert result['success'] is True
        totals = result['totals']

        assert totals['design_fee'] == 500.00
        assert totals['design_cost'] == 500.00
        assert totals['design_service_type'] == 'NEW_CONCEPT'
        # التحقق من أن السعر الإجمالي يشمل سعر الإنتاج + أتعاب التصميم
        expected_total = totals['production_selling_price'] + 500.00
        assert round(totals['total_selling_price'], 2) == round(expected_total, 2)
        # التحقق من نقاء سعر القطعة: يحسب فقط من سعر إنتاج المطبوعات
        expected_unit = round(totals['production_selling_price'] / 1000, 4)
        assert round(totals['unit_selling_price'], 4) == expected_unit

    def test_persist_order_anatomy_creates_order_service_for_design(self):
        """
        اختبار الحفظ الذري: توليد بند نظامي في OrderService بفئة design وحفظ OrderSummary.design_cost
        """
        order = PrintingOrder.objects.create(
            customer=self.customer,
            title='بروشور تعريفي بتصميم جديد',
            product_type=self.product_type,
            product_size=self.product_size,
            order_type='flyer',
            quantity=1000,
            created_by=self.user
        )

        post_data = {
            'design_service_type': 'NEW_CONCEPT',
            'design_fee': '750.00',
            'profit_margin': '30.00',
            'quantity': 1000
        }

        summary = OrderAnatomyPersistenceService.persist_order_anatomy(order, post_data)
        order.refresh_from_db()

        assert order.design_service_type == 'NEW_CONCEPT'
        assert order.design_fee == Decimal('750.00')

        # التحقق من توليد سجل OrderService
        design_services = OrderService.objects.filter(order=order, service_category='design')
        assert design_services.count() == 1
        d_service = design_services.first()
        assert d_service.unit_price == Decimal('750.00')
        assert d_service.total_cost == Decimal('750.00')

        # التحقق من OrderSummary
        assert summary.design_cost == Decimal('750.00')
        assert summary.final_price == order.final_price

    def test_customer_ready_removes_design_service_and_zeros_fee(self):
        """
        اختبار التحويل لتصميم جاهز من العميل: تصفير الأتعاب وحذف أي بند خدمة سابق
        """
        order = PrintingOrder.objects.create(
            customer=self.customer,
            title='طلب تم تعديله ليصبح تصميماً جاهزاً',
            product_type=self.product_type,
            product_size=self.product_size,
            order_type='flyer',
            quantity=500,
            design_service_type='NEW_CONCEPT',
            design_fee=Decimal('600.00'),
            created_by=self.user
        )
        OrderService.objects.create(
            order=order,
            service_category='design',
            service_name='تصميم قديم',
            quantity=1,
            unit='piece',
            unit_price=Decimal('600.00'),
            total_cost=Decimal('600.00')
        )

        post_data = {
            'design_service_type': 'CUSTOMER_READY',
            'design_fee': '600.00',  # حتى لو أرسل الفورم قيمة بالخطأ، يجب تصفيرها
            'profit_margin': '25.00'
        }

        summary = OrderAnatomyPersistenceService.persist_order_anatomy(order, post_data)
        order.refresh_from_db()

        assert order.design_service_type == 'CUSTOMER_READY'
        assert order.design_fee == Decimal('0.00')
        assert OrderService.objects.filter(order=order, service_category='design').count() == 0
        assert summary.design_cost == Decimal('0.00')

    def test_work_order_gating_note_for_prepress_or_new_concept(self):
        """
        اختبار أمر الشغل: التحقق من إدراج تنبيه صالة الإنتاج بحظر سحب الخامات حتى اعتماد البروفة
        """
        order = PrintingOrder.objects.create(
            customer=self.customer,
            title='أمر طباعة تصميم جديد',
            product_type=self.product_type,
            product_size=self.product_size,
            order_type='flyer',
            quantity=1000,
            design_service_type='PREPRESS_EDIT',
            design_fee=Decimal('300.00'),
            created_by=self.user
        )

        wo = order.create_work_order(user=self.user)
        assert wo is not None
        assert 'تنبيه إنتاج: أمر الشغل يتطلب تصميم ومونتاج' in wo.notes
        assert 'تعديل ومونتاج' in wo.notes

    def test_approved_orders_api_returns_clean_design_separation(self):
        """
        اختبار API الطلبات المعتمدة للمبيعات: التحقق من إرجاع سعر القطعة الصافي وأتعاب التصميم المستقلة
        """
        order = PrintingOrder.objects.create(
            customer=self.customer,
            title='طلب معتمد للشراء',
            product_type=self.product_type,
            product_size=self.product_size,
            order_type='flyer',
            quantity=1000,
            final_price=Decimal('10500.00'),
            design_service_type='NEW_CONCEPT',
            design_fee=Decimal('500.00'),
            status='approved',
            created_by=self.user
        )

        url = reverse('printing_pricing:api_approved_orders')
        response = self.client.get(f"{url}?customer_id={self.customer.pk}")
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert len(data['orders']) >= 1

        order_item = next(o for o in data['orders'] if o['id'] == order.id)
        assert order_item['has_design'] is True
        assert order_item['design_fee'] == '500.00'
        # سعر الطباعة الصافي = 10,500 - 500 = 10,000 ج.م
        assert Decimal(order_item['print_selling_price']) == Decimal('10000.00')
        # سعر القطعة الصافي = 10,000 / 1000 = 10.00 ج.م
        assert Decimal(order_item['print_unit_price']) == Decimal('10.0000')
