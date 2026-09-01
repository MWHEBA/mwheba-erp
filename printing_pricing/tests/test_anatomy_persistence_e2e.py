"""
اختبارات التحقق الشاملة لخدمة الحفظ الذري وتفكيك بنود الخامات والخدمات
Anatomy-Driven End-to-End Workflow & Procurement Bridge Tests
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from customer.models import Customer
from printing_pricing.models import (
    PrintingOrder, OrderMaterial, OrderService, OrderSummary, PricingStatus
)
from printing_pricing.services.anatomy_persistence_service import OrderAnatomyPersistenceService
from printing_pricing.services.procurement_bridge import ProcurementBridgeService

User = get_user_model()


@pytest.mark.django_db
class TestAnatomyPersistenceWorkflow:
    """اختبارات تفكيك الشغلانة وحفظها وتوليد أوامر الشراء"""

    def setup_method(self):
        self.user = User.objects.create_user(
            username='estimator_user',
            email='estimator@mwheba.com',
            password='password123'
        )
        self.customer = Customer.objects.create(
            name='شركة النجاح للطباعة والتجارة',
            phone='01012345678'
        )

    def test_single_sheet_flyer_anatomy_persistence(self):
        """اختبار تسعير وحفظ فلاير مفرد وتوليد بنود الورق والزنكات والتراج والسلوفان"""
        order = PrintingOrder.objects.create(
            order_number='ORD-TEST-001',
            customer=self.customer,
            title='طباعة فلاير دعائي A4',
            order_type='flyer',
            quantity=5000,
            width=Decimal('21.0'),
            height=Decimal('29.7'),
            created_by=self.user,
            status=PricingStatus.DRAFT
        )

        post_data = {
            'order_type': 'flyer',
            'quantity': '5000',
            'width': '21.0',
            'height': '29.7',
            'paper_weight': '150',
            'zinc_plates_count': '4',
            'coating_type': 'matte_2_sides',
            'finishing': 'none',
            'die_cutting': 'straight_cut',
            'extra_cost': '150.00',
            'profit_margin': '25.00'
        }

        summary = OrderAnatomyPersistenceService.persist_order_anatomy(order, post_data)

        # 1. التحقق من إنشاء بنود الخامات
        materials = OrderMaterial.objects.filter(order=order)
        assert materials.count() == 1
        cover_mat = materials.first()
        assert cover_mat.material_type == 'paper'
        assert '150' in cover_mat.material_name
        assert cover_mat.quantity > 0
        assert cover_mat.total_cost > Decimal('0.00')

        # 2. التحقق من إنشاء بنود الخدمات (زنكات + تراج + سلوفان)
        services = OrderService.objects.filter(order=order)
        assert services.count() >= 3  # زنكات CTP + طباعة تراج + سلوفان
        assert services.filter(service_name__contains='CTP').exists()
        assert services.filter(service_name__contains='تراج').exists()
        assert services.filter(service_name__contains='سلوفان').exists()

        # 3. التحقق من OrderSummary الصافي بدون ضريبة
        assert summary.material_cost > Decimal('0.00')
        assert summary.printing_cost > Decimal('0.00')
        assert summary.finishing_cost > Decimal('0.00')
        assert summary.other_costs == Decimal('150.00')
        assert summary.tax_amount == Decimal('0.00')
        assert summary.final_price == summary.subtotal
        assert summary.final_price > summary.total_cost

    def test_book_catalog_mixed_anatomy_persistence(self):
        """اختبار تسعير وحفظ كتالوج (غلاف + داخلي + تجليد)"""
        order = PrintingOrder.objects.create(
            order_number='ORD-TEST-002',
            customer=self.customer,
            title='طباعة كتالوج سنوي 32 صفحة',
            order_type='catalog',
            quantity=1000,
            width=Decimal('21.0'),
            height=Decimal('29.7'),
            pages_count=32,
            created_by=self.user,
            status=PricingStatus.DRAFT
        )

        post_data = {
            'order_type': 'catalog',
            'quantity': '1000',
            'width': '21.0',
            'height': '29.7',
            'pages_count': '32',
            'paper_weight': '300',
            'zinc_plates_count': '4',
            'coating_type': 'matte_1_side',
            'die_cutting': 'straight_cut',
            'extra_cost': '200.00',
            'profit_margin': '25.00'
        }

        summary = OrderAnatomyPersistenceService.persist_order_anatomy(order, post_data)

        # 1. التحقق من إنشاء خامتين (ورق غلاف 300 جم + ورق داخلي 135 جم)
        materials = OrderMaterial.objects.filter(order=order)
        assert materials.count() == 2
        assert materials.filter(material_name__contains='300').exists()
        assert materials.filter(material_name__contains='داخلي').exists()

        # 2. التحقق من إنشاء خدمة التجليد
        services = OrderService.objects.filter(order=order)
        assert services.filter(service_category='packaging').exists()

        # 3. التحقق من إعفاء الكتب من الـ VAT (0%)
        assert summary.tax_amount == Decimal('0.00')
