"""
حزمة اختبارات التحقق من مزامنة أسعار الوحدة الصافية وحراسة بوابات أوامر الشراء
Unit Price Synchronization (Option B) & Procurement PO Gating Test Suite
"""
import pytest
import json
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.exceptions import ValidationError

from supplier.models import Supplier, ServiceType, SupplierService, ServicePriceHistory
from printing_pricing.models import (
    PrintingOrder, OrderMaterial, OrderService, PaperType, PaperSize, PaperWeight
)
from printing_pricing.services.procurement_bridge import ProcurementBridgeService

User = get_user_model()


@pytest.fixture
def test_user(db):
    return User.objects.create_user(username='estimator_sync', password='password123', is_staff=True)


@pytest.fixture
def paper_supplier(db):
    return Supplier.objects.create(name='شركة الفرات للورق', code='SUP-FURAT-01', is_active=True)


@pytest.fixture
def offset_supplier(db):
    return Supplier.objects.create(name='مطبعة السلام الأوفست', code='SUP-SALAM-01', is_active=True)


@pytest.fixture
def service_types(db):
    st_paper, _ = ServiceType.objects.get_or_create(code='paper', defaults={'name': 'خام الورق', 'default_validity_days': 30})
    st_offset, _ = ServiceType.objects.get_or_create(code='offset', defaults={'name': 'طباعة أوفست', 'default_validity_days': 45})
    st_ctp, _ = ServiceType.objects.get_or_create(code='ctp', defaults={'name': 'زنكات CTP', 'default_validity_days': 60})
    return {'paper': st_paper, 'offset': st_offset, 'ctp': st_ctp}


@pytest.fixture
def paper_service(db, paper_supplier, service_types):
    ps = PaperSize.objects.create(name='70x100', width=70.0, height=100.0)
    pw = PaperWeight.objects.create(gsm=300)
    pt = PaperType.objects.create(name='كوشيه فاخر')
    
    return SupplierService.objects.create(
        supplier=paper_supplier,
        service_type=service_types['paper'],
        name='كوشيه 300 جم 70×100',
        pricing_formula='PER_TON',
        price_per_ton=Decimal('45000.00'),
        base_price=Decimal('9.45'),
        paper_size=ps,
        paper_weight=pw,
        paper_type_ref=pt,
        gsm=300,
        price_updated_at=timezone.now() - timedelta(days=5),
        price_valid_until=timezone.now().date() + timedelta(days=25),
        is_active=True
    )


@pytest.fixture
def offset_service(db, offset_supplier, service_types):
    return SupplierService.objects.create(
        supplier=offset_supplier,
        service_type=service_types['offset'],
        name='تراج أوفست 4 لون ربع فرخ',
        pricing_formula='PER_1000',
        base_price=Decimal('120.00'),
        price_updated_at=timezone.now() - timedelta(days=10),
        price_valid_until=timezone.now().date() + timedelta(days=35),
        is_active=True
    )


@pytest.mark.django_db
class TestSyncOrderUnitPricesAPI:
    """اختبارات نقطة نهاية مزامنة أسعار الوحدة الصافية للموردين (Option B)"""

    def test_sync_unit_price_by_service_id_per_ton_recalculation(self, client, test_user, paper_service):
        """التحقق من تحديث سعر الفرخ وإعادة الحساب العكسي الصافي لسعر الطن بدقة"""
        client.force_login(test_user)
        url = reverse('printing_pricing:api_sync_order_unit_prices')

        # sheet_weight_kg for 70x100 at 300 gsm = (70 * 100 * 300) / 10,000,000 = 0.21 kg
        # If new sheet price = 10.50 EGP, new ton price = (10.50 / 0.21) * 1000 = 50,000.00 EGP
        payload = {
            'order_number': 'ORD-2026-001',
            'updates': [
                {
                    'service_id': paper_service.id,
                    'new_unit_price': 10.50,
                    'width': 70,
                    'height': 100,
                    'gsm': 300
                }
            ]
        }

        resp = client.post(url, data=json.dumps(payload), content_type='application/json')
        assert resp.status_code == 200
        data = resp.json()
        assert data['success'] is True
        assert data['updated_count'] == 1

        paper_service.refresh_from_db()
        assert paper_service.price_per_ton == Decimal('50000.00')
        assert paper_service.price_age_days == 0
        assert paper_service.price_staleness_status == 'fresh'

        # التحقق من تسجيل السجل في ServicePriceHistory بمصدر ORDER_FLOW
        history = ServicePriceHistory.objects.filter(service=paper_service).first()
        assert history is not None
        assert history.change_source == 'ORDER_FLOW'
        assert 'ORD-2026-001' in history.quote_reference
        assert history.changed_by == test_user

    def test_sync_unit_price_by_supplier_and_service_type_fallback(self, client, test_user, offset_service, offset_supplier):
        """التحقق من المزامنة عند عدم توفر معرف الخدمة المباشر والاعتماد على المورد ونوع الخدمة"""
        client.force_login(test_user)
        url = reverse('printing_pricing:api_sync_order_unit_prices')

        payload = {
            'order_number': 'ORD-2026-002',
            'updates': [
                {
                    'supplier_id': offset_supplier.id,
                    'service_type': 'offset',
                    'new_unit_price': 140.00
                }
            ]
        }

        resp = client.post(url, data=json.dumps(payload), content_type='application/json')
        assert resp.status_code == 200
        data = resp.json()
        assert data['success'] is True
        assert data['updated_count'] == 1

        offset_service.refresh_from_db()
        assert offset_service.base_price == Decimal('140.00')
        assert offset_service.price_age_days == 0
        assert offset_service.price_valid_until > timezone.now().date()

        history = ServicePriceHistory.objects.filter(service=offset_service).first()
        assert history is not None
        assert history.change_source == 'ORDER_FLOW'
        assert history.old_unit_price == Decimal('120.00')
        assert history.new_unit_price == Decimal('140.00')


@pytest.mark.django_db
class TestProcurementBridgePOGating:
    """اختبارات حراسة وتطويق إصدار أوامر الشراء (PO Gating) بناءً على صلاحية أسعار الموردين"""

    def test_gating_blocks_stale_service_po_generation(self, test_user, offset_service):
        """منع إصدار أمر الشراء إذا كان سعر الخدمة منتهياً أو متقادماً دون سبب تجاوز إداري"""
        # جعل سعر خدمة الأوفست منتهياً
        offset_service.price_updated_at = timezone.now() - timedelta(days=60)
        offset_service.price_valid_until = timezone.now().date() - timedelta(days=10)
        offset_service.save()
        assert offset_service.is_price_stale is True

        order = PrintingOrder.objects.create(
            order_number='ORD-GATE-01',
            title='بروشور شركات فاخر',
            quantity=1000,
            status='approved',
            created_by=test_user
        )
        OrderService.objects.create(
            order=order,
            supplier_service=offset_service,
            service_category='printing',
            service_name='طباعة أوفست',
            quantity=1,
            unit_price=Decimal('500.00'),
            total_cost=Decimal('500.00')
        )

        # 1. فحص البوابة
        gating_res = ProcurementBridgeService.check_po_gating(order)
        assert gating_res['is_gated_ready'] is False
        assert len(gating_res['issues']) >= 1
        assert len(gating_res['stale_services']) == 1

        # 2. محاولة توليد أوامر الشراء مع تفعيل البوابة دون سبب تجاوز
        with pytest.raises(ValidationError) as exc:
            ProcurementBridgeService.generate_vendor_purchase_orders(
                order=order,
                gated=True,
                override_reason='',
                user=test_user
            )
        assert "لا يمكن إصدار أوامر الشراء للورش" in str(exc.value)

    def test_gating_allows_override_with_reason(self, test_user, offset_service):
        """السماح للمدير بإصدار أمر الشراء الاستثنائي مع تسجيل سبب التجاوز"""
        offset_service.price_updated_at = timezone.now() - timedelta(days=60)
        offset_service.price_valid_until = timezone.now().date() - timedelta(days=10)
        offset_service.save()

        order = PrintingOrder.objects.create(
            order_number='ORD-GATE-02',
            title='فولدر تعريفي',
            quantity=500,
            status='approved',
            created_by=test_user
        )
        OrderService.objects.create(
            order=order,
            supplier_service=offset_service,
            service_category='printing',
            service_name='طباعة أوفست',
            quantity=1,
            unit_price=Decimal('350.00'),
            total_cost=Decimal('350.00')
        )

        pos = ProcurementBridgeService.generate_vendor_purchase_orders(
            order=order,
            gated=True,
            override_reason='موافقة استثنائية من المدير المالي بسبب ثبات الأسعار مع المطبعة هاتفياً',
            user=test_user
        )

        assert len(pos) == 1
        po = pos[0]
        assert po.supplier == offset_service.supplier
        assert po.total == Decimal('346.50')
