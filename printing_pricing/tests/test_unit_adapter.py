"""
Unit tests for PrintingUnitAdapter, OrderValidator and Trade Procurement Bridge
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock

from printing_pricing.services.unit_adapter import PrintingUnitAdapter
from printing_pricing.services.validators.order_validator import OrderValidator
from printing_pricing.models.order import PrintingOrder


def test_unit_adapter_per_ton():
    service = MagicMock()
    service.pricing_formula = 'PER_TON'
    
    # 500 فرخ مقاس 70*100 سم بجراماج 300
    # وزن الفرخ = (70 * 100 * 300) / 10,000,000 = 0.21 كجم
    # إجمالي الأطنان = (500 * 0.21) / 1,000 = 0.105 طن
    tons = PrintingUnitAdapter.normalize_quantity(
        service,
        raw_qty=500,
        width_cm=70,
        height_cm=100,
        gsm=300
    )
    assert tons == Decimal('0.1050')


def test_unit_adapter_per_sqm():
    service = MagicMock()
    service.pricing_formula = 'PER_SQM'
    
    # 10 أفرخ مقاس 70*100 سم
    # المساحة = (70 * 100 / 10,000) * 10 = 7 متر مربع
    sqm = PrintingUnitAdapter.normalize_quantity(
        service,
        raw_qty=10,
        width_cm=70,
        height_cm=100
    )
    assert sqm == Decimal('7.00')


def test_unit_adapter_per_thousand():
    service = MagicMock()
    service.pricing_formula = 'PER_THOUSAND'
    
    # 2500 سحبة = 2.5 تراج
    thousands = PrintingUnitAdapter.normalize_quantity(service, raw_qty=2500)
    assert thousands == Decimal('2.500')


def test_unit_adapter_per_ream():
    service = MagicMock()
    service.pricing_formula = 'PER_REAM'
    service.sheets_per_pack = 500
    
    # 750 فرخ = 1.5 رزمة
    reams = PrintingUnitAdapter.normalize_quantity(service, raw_qty=750)
    assert reams == Decimal('1.50')


def test_unit_adapter_fixed_tooling():
    service = MagicMock()
    service.pricing_formula = 'FIXED_TOOLING'
    
    val = PrintingUnitAdapter.normalize_quantity(service, raw_qty=1500)
    assert val == Decimal('1.00')


@pytest.mark.django_db
def test_order_validator_uses_title_and_cost():
    order = MagicMock()
    order.customer = MagicMock()
    order.title = "بروشور إعلاني لشركة الأمل"
    order.product_name = None
    order.quantity = 1000
    order.estimated_cost = Decimal('500.00')
    order.total_cost = None
    order.status = 'draft'
    order.profit_margin = Decimal('20.00')
    
    validator = OrderValidator()
    # التحقق من أن الفحص لا يرمي كراش AttributeError بسبب product_name أو total_cost
    result = validator.validate_order_for_approval(order)
    assert result['can_approve'] is True


@pytest.mark.django_db
def test_order_validator_margin_gate():
    order = MagicMock()
    order.customer = MagicMock()
    order.title = "كروت شخصية"
    order.quantity = 1000
    order.estimated_cost = Decimal('200.00')
    order.status = 'draft'
    order.profit_margin = Decimal('10.00')  # أقل من 15%
    
    user = MagicMock()
    user.is_staff = False
    user.is_superuser = False
    
    validator = OrderValidator()
    result = validator.validate_order_for_approval(order, user=user)
    assert result['can_approve'] is False
    assert any('15%' in err for err in result['errors'])
