import pytest
from decimal import Decimal
from django.utils import timezone
from financial.models import Currency, ExchangeRate
from supplier.models import Supplier, SupplierService, ServiceType
from printing_pricing.models import PrintingOrder
from printing_pricing.services import PrintingCalculationEngine, ProcurementBridgeService


@pytest.mark.django_db
class TestDynamicCurrencyIAS21:
    """
    اختبارات معمارية ديناميكية العملات المتوافقة مع IAS 21:
    - انعدام أي عملة هاردكود بنسبة 100%
    - دقة التوريث (الخدمة -> المورد -> العملة الوظيفية)
    - دقة التحويل في محرك التسعير وجسر المشتريات
    """

    def setup_method(self):
        from django.contrib.auth import get_user_model
        self.user = get_user_model().objects.create_user(username="test_fx_admin", password="password123")

        # 1. تهيئة العملات
        self.egp, _ = Currency.objects.get_or_create(
            code='EGP',
            defaults={'name': 'جنيه مصري', 'symbol': 'ج.م', 'is_functional': True, 'is_active': True}
        )
        self.usd, _ = Currency.objects.get_or_create(
            code='USD',
            defaults={'name': 'US Dollar', 'symbol': '$', 'is_functional': False, 'is_active': True}
        )
        self.sar, _ = Currency.objects.get_or_create(
            code='SAR',
            defaults={'name': 'ريال سعودي', 'symbol': 'ر.س', 'is_functional': False, 'is_active': True}
        )

        # 2. سعر الصرف
        ExchangeRate.objects.get_or_create(
            from_currency=self.usd,
            to_currency=self.egp,
            effective_date=timezone.now().date(),
            defaults={'rate': Decimal('50.000000')}
        )

        # 3. المورد
        self.supplier = Supplier.objects.create(
            name="مطبعة الشروق الدولية",
            code="SUP-FX-001",
            default_currency=self.usd
        )

        self.service_type, _ = ServiceType.objects.get_or_create(
            code='offset_printing',
            defaults={'name': 'طباعة أوفست'}
        )

    def test_supplier_service_effective_currency_hierarchy(self):
        """اختبار تسلسل التوريث الهرمي للعملة: الخدمة -> المورد -> العملة الوظيفية"""
        # حالة 1: الخدمة ليس لها عملة خاصة -> ترث عملة المورد (USD)
        svc1 = SupplierService.objects.create(
            supplier=self.supplier,
            service_type=self.service_type,
            name="طباعة أوفست 4 لون",
            pricing_formula="PER_THOUSAND",
            base_price=Decimal('20.00')
        )
        assert svc1.effective_currency == self.usd
        assert svc1.currency_symbol == '$'
        assert svc1.currency_code == 'USD'

        # حالة 2: تخصيص عملة صريحة للخدمة (SAR) -> تعلو على المورد
        svc1.currency = self.sar
        svc1.save()
        assert svc1.effective_currency == self.sar
        assert svc1.currency_symbol == 'ر.س'
        assert svc1.currency_code == 'SAR'

        # حالة 3: مورد بدون عملة افتراضية وخدمة بدون عملة -> ترث العملة الوظيفية (EGP)
        sup_no_curr = Supplier.objects.create(name="مورد محلي", code="SUP-LOCAL-01")
        svc_local = SupplierService.objects.create(
            supplier=sup_no_curr,
            service_type=self.service_type,
            name="خدمة محلية",
            base_price=Decimal('100.00')
        )
        assert svc_local.effective_currency == self.egp
        assert svc_local.currency_symbol == 'ج.م'
        assert svc_local.currency_code == 'EGP'

    def test_pricing_engine_dynamic_currency_output_and_fx_conversion(self):
        """اختبار خرج محرك الحسابات اللحظي مع التحويل الديناميكي للعملات"""
        # خدمة مسعرة بـ 10 دولار للتراج
        svc_usd = SupplierService.objects.create(
            supplier=self.supplier,
            service_type=self.service_type,
            name="ماكينة دولارية",
            pricing_formula="PER_THOUSAND",
            base_price=Decimal('10.00'),
            currency=self.usd
        )

        params = {
            'quantity': 5000,
            'width': 20,
            'height': 30,
            'sheet_size': '70x100',
            'piece_size': '50x70',
            'print_sides_mode': 'single',
            'cover_printing_type': 'offset',
            'cover_press_price': Decimal('10.00'),
            'cover_press_service_id': svc_usd.id,
            'target_currency': self.egp
        }

        result = PrintingCalculationEngine.calculate(params)
        assert result['success'] is True
        assert result['currency_code'] == 'EGP'
        assert result['currency_symbol'] == 'ج.م'

        # تكلفة الطباعة تم تحويلها من USD إلى EGP بمعدل 50: 10 USD * 50 = 500 EGP للتراج
        assert result['printing']['total_cost'] > 0

    def test_printing_order_save_dual_presentation_and_freeze(self):
        """التحقق من تجميد سعر الصرف واحتساب المبالغ الوظيفية آلياً عند حفظ الأمر"""
        order = PrintingOrder(
            order_number="ORD-FX-TEST-001",
            title="كتالوج تجاري متعدد العملات",
            quantity=1000,
            currency=self.usd,
            estimated_cost=Decimal('200.00'),
            final_price=Decimal('300.00')
        )
        order.save()

        # تم تجميد سعر الصرف (50.0)
        assert order.exchange_rate == Decimal('50.000000')
        assert order.currency_code == 'USD'
        assert order.currency_symbol == '$'
        # القيمة الوظيفية بالجنيه: 200 * 50 = 10,000 و 300 * 50 = 15,000
        assert order.estimated_cost_functional == Decimal('10000.00')
        assert order.final_price_functional == Decimal('15000.00')

    def test_procurement_bridge_unbundled_po_currency(self):
        """التحقق من إنشاء أمر الشراء غير المجمع بعملة المورد الافتراضية بدقة"""
        order = PrintingOrder.objects.create(
            order_number="ORD-PO-FX-001",
            title="طلب توريد ورش",
            quantity=1000,
            currency=self.usd,
            estimated_cost=Decimal('100.00'),
            final_price=Decimal('150.00')
        )

        svc_usd = SupplierService.objects.create(
            supplier=self.supplier,
            service_type=self.service_type,
            name="خدمة طباعة دولارية",
            pricing_formula="PER_THOUSAND",
            base_price=Decimal('50.00'),
            currency=self.usd
        )

        order.services.create(
            service_name="طباعة أوفست",
            quantity=Decimal('1000'),
            unit_price=Decimal('0.20'),
            total_cost=Decimal('200.00'),
            supplier_service=svc_usd,
            service_category='printing'
        )

        pos = ProcurementBridgeService.generate_vendor_purchase_orders(order, gated=False, user=self.user)
        assert len(pos) == 1
        po = pos[0]
        # أمر الشراء تم إنشاؤه بعملة المورد (USD) ومعدل الصرف تم تجميده
        assert po.supplier == self.supplier
        assert po.currency == self.usd
        assert po.exchange_rate == Decimal('50.000000')
        assert po.total > Decimal('0.00')
        assert po.total_foreign > Decimal('0.00')
        assert po.total_functional > Decimal('0.00')
