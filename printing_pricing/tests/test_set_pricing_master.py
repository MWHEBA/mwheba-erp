"""
Master Test Suite for Set Pricing Architecture across MWHEBA ERP
اختبارات التحقق الشاملة لنظام تسعير الأطقم (زنكات CTP وماكينات الأوفست)
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from customer.models import Customer
from supplier.models import Supplier, SupplierService, ServiceType
from financial.models.currency import Currency
from financial.services.exchange_rate_service import ExchangeRateService
from printing_pricing.models import (
    PrintingOrder, OrderService, OrderSummary, PricingStatus, MachineDimension
)
from printing_pricing.services.pricing_engine import PrintingCalculationEngine
from printing_pricing.services.anatomy_persistence_service import OrderAnatomyPersistenceService
from printing_pricing.services.procurement_bridge import ProcurementBridgeService

User = get_user_model()


@pytest.mark.django_db
class TestSetPricingMaster:
    """مجموعة الاختبارات الصناعية الكاملة لنظام الأطقم والـ SSOT"""

    def setup_method(self):
        self.user = User.objects.create_user(
            username='set_pricing_admin',
            email='admin@mwheba.com',
            password='password123'
        )
        self.customer = Customer.objects.create(
            name='شركة المتحدة للنشر والتوزيع',
            phone='01099998888'
        )
        self.func_curr, _ = Currency.objects.get_or_create(
            code='EGP',
            defaults={
                'name': 'Egyptian Pound',
                'symbol': 'ج.م',
                'decimal_places': 2,
                'is_functional': True,
                'is_active': True,
            }
        )
        if not self.func_curr.is_functional:
            self.func_curr.is_functional = True
            self.func_curr.save()

        # أبعاد الزنك
        self.dim_50x70, _ = MachineDimension.objects.get_or_create(
            dimension_type='plate',
            name='نصف فرخ 50×70 سم',
            defaults={'code': '50x70', 'width': Decimal('50.0'), 'height': Decimal('70.0'), 'is_active': True}
        )
        self.dim_70x100, _ = MachineDimension.objects.get_or_create(
            dimension_type='plate',
            name='فرخ كامل 70×100 سم',
            defaults={'code': '70x100', 'width': Decimal('70.0'), 'height': Decimal('100.0'), 'is_active': True}
        )

        # أنواع الخدمات
        self.ctp_type, _ = ServiceType.objects.get_or_create(
            code='ctp_plates',
            defaults={'name': 'فصل زنكات CTP', 'category': 'prepress'}
        )
        self.offset_type, _ = ServiceType.objects.get_or_create(
            code='offset_printing',
            defaults={'name': 'طباعة أوفست تجاري', 'category': 'printing'}
        )

        # مورد محلي بالعملة الوظيفية
        self.local_supplier = Supplier.objects.create(
            name='مطبعة الأهرام التجارية وفصل الألوان',
            is_active=True,
            default_currency=self.func_curr
        )

        # خدمة زنكات CTP للمورد
        self.ctp_service = SupplierService.objects.create(
            supplier=self.local_supplier,
            service_type=self.ctp_type,
            name='زنك 50×70 سم حراري',
            pricing_formula='PER_PIECE',
            base_price=Decimal('85.00'),
            set_price=Decimal('280.00'),
            is_active=True,
            plate_size=self.dim_50x70
        )

        # خدمة طباعة أوفست للمورد
        self.offset_service = SupplierService.objects.create(
            supplier=self.local_supplier,
            service_type=self.offset_type,
            name='ماكينة هايدلبرج Speedmaster 50×70 (4 ألوان)',
            pricing_formula='PER_THOUSAND',
            base_price=Decimal('45.00'),
            set_price=Decimal('150.00'),
            set_included_tirages=1,
            is_active=True
        )

    # -------------------------------------------------------------------------
    # 1. اختبارات حساب تكلفة الزنكات بالموديل SupplierService
    # -------------------------------------------------------------------------
    def test_01_ctp_calculate_cost_single_plates_and_full_sets(self):
        """
        التحقق من حساب تكلفة الزنكات الفردية والأطقم (3-Way Optimization):
        زنكة واحدة: 85
        2 زنكة: 170
        3 زنكات: 255
        4 زنكات (طقم): 280 (توفير مقابل 340)
        5 زنكات: 280 + 85 = 365
        6 زنكات: 280 + 170 = 450
        7 زنكات: 280 + 255 = 535
        8 زنكات (طقمين): 560
        """
        assert self.ctp_service.calculate_cost(1) == Decimal('85.00')
        assert self.ctp_service.calculate_cost(2) == Decimal('170.00')
        assert self.ctp_service.calculate_cost(3) == Decimal('255.00')
        assert self.ctp_service.calculate_cost(4) == Decimal('280.00')
        assert self.ctp_service.calculate_cost(5) == Decimal('365.00')
        assert self.ctp_service.calculate_cost(6) == Decimal('450.00')
        assert self.ctp_service.calculate_cost(7) == Decimal('535.00')
        assert self.ctp_service.calculate_cost(8) == Decimal('560.00')

    def test_02_ctp_next_set_jump_optimization(self):
        """
        اختبار قفزة الطقم التالي (Next-Set Jump):
        إذا كان سعر الزنكة المفردة 100 وسعر الطقم 280:
        7 زنكات:
        - فردي: 7 * 100 = 700
        - طقم + فكة: 280 + 300 = 580
        - قفزة لطقمين كاملين: 2 * 280 = 560 (أرخص بـ 20 ج)
        المحرك يجب أن يختار 560!
        """
        custom_ctp = SupplierService.objects.create(
            supplier=self.local_supplier,
            service_type=self.ctp_type,
            name='زنك 70×100 سم فاخر',
            pricing_formula='PER_PIECE',
            base_price=Decimal('100.00'),
            set_price=Decimal('280.00'),
            plate_size=self.dim_70x100,
            is_active=True
        )
        assert custom_ctp.calculate_cost(7) == Decimal('560.00')

    def test_03_ctp_inverted_price_protection(self):
        """
        صمام أمان ضد الأسعار المعكوسة:
        إذا أدخل المستخدم بالخطأ سعر طقم 400 ج وسعر زنكة 85 ج (4*85 = 340 < 400)
        يجب أن يحمي النظام المستخدم ويحسب على السعر الأوفر (340 ج)
        """
        inverted_ctp = SupplierService.objects.create(
            supplier=self.local_supplier,
            service_type=self.ctp_type,
            name='زنك بحماية سعرية',
            pricing_formula='PER_PIECE',
            base_price=Decimal('85.00'),
            set_price=Decimal('400.00'),
            plate_size=self.dim_50x70,
            is_active=True
        )
        assert inverted_ctp.calculate_cost(4) == Decimal('340.00')

    def test_04_ctp_zero_base_price_handling(self):
        """
        التعامل مع مورد يسعر بالأطقم فقط (base_price = 0)
        3 زنكات يجب أن تحسب كطقم كامل (280) وليس 0!
        """
        set_only_ctp = SupplierService.objects.create(
            supplier=self.local_supplier,
            service_type=self.ctp_type,
            name='زنك طقم مقطوعية فقط',
            pricing_formula='PER_PIECE',
            base_price=Decimal('0.00'),
            set_price=Decimal('280.00'),
            plate_size=self.dim_50x70,
            is_active=True
        )
        assert set_only_ctp.calculate_cost(1) == Decimal('280.00')
        assert set_only_ctp.calculate_cost(4) == Decimal('280.00')
        assert set_only_ctp.calculate_cost(6) == Decimal('560.00')

    # -------------------------------------------------------------------------
    # 2. اختبارات حساب تكلفة طباعة الأوفست بالموديل SupplierService
    # -------------------------------------------------------------------------
    def test_05_offset_printing_set_price_with_included_tirages(self):
        """
        التحقق من حساب فتحة الماكينة كطقم يشمل تراج محدد:
        سعر الطقم = 150 (يشمل 1 تراج)
        سعر التراج الإضافي = 45
        - 1 تراج: 150
        - 2 تراج: 150 + 45 = 195
        - 3 تراج: 150 + 90 = 240
        """
        assert self.offset_service.calculate_cost(1) == Decimal('150.00')
        assert self.offset_service.calculate_cost(2) == Decimal('195.00')
        assert self.offset_service.calculate_cost(3) == Decimal('240.00')

    # -------------------------------------------------------------------------
    # 3. اختبارات محرك التسعير الآلي PrintingCalculationEngine
    # -------------------------------------------------------------------------
    def test_06_pricing_engine_resolves_ctp_and_press_set_prices(self):
        """
        التحقق من أن محرك التسعير PrintingCalculationEngine يتعرف على المورد وخدماته
        ويطبق نظام الأطقم بدقة.
        طلب فلاير: 1000 نسخة، وجه واحد (1 طقم ماكينة، 4 زنكات)
        - تكلفة الزنكات: 280 (طقم)
        - تكلفة الماكينة: 150 (1 تراج مشمول في الطقم)
        """
        params = {
            'quantity': 1000,
            'width': 21,
            'height': 29.7,
            'sheet_size': '70x100',
            'piece_size': '50x70',
            'print_sides_mode': 'single',
            'cover_printing_type': 'offset',
            'cover_ctp_supplier': self.local_supplier.id,
            'cover_offset_supplier': self.local_supplier.id,
            'colors_front': 4,
            'press_bed_size': '50x70'
        }
        res = PrintingCalculationEngine.calculate(params)
        assert res['success'] is True
        assert res['plates']['total_cost'] == 280.0
        assert res['printing']['applied_press_cost'] == 150.0

    def test_07_pricing_engine_work_sheet_double_sets(self):
        """
        في حالة السكتين وجه وظهر (work_sheet):
        الماكينة تحتاج طقمين (طقم للوجه وطقم للظهر = 2 أطقم):
        - الزنكات: 8 زنكات = 2 * 280 = 560
        - الماكينة: 2 طقم * 150 = 300
        """
        params = {
            'quantity': 1000,
            'width': 21,
            'height': 29.7,
            'sheet_size': '70x100',
            'piece_size': '50x70',
            'print_sides_mode': 'work_sheet',
            'cover_printing_type': 'offset',
            'cover_ctp_supplier': self.local_supplier.id,
            'cover_offset_supplier': self.local_supplier.id,
            'colors_front': 4,
            'colors_back': 4,
            'press_bed_size': '50x70'
        }
        res = PrintingCalculationEngine.calculate(params)
        assert res['success'] is True
        assert res['plates']['total_cost'] == 560.0
        assert res['printing']['applied_press_cost'] == 300.0

    # -------------------------------------------------------------------------
    # 4. اختبار تفكيك الشغلانة وحل مشكلة Recalculate Amnesia
    # -------------------------------------------------------------------------
    def test_08_anatomy_persistence_and_recalculate_amnesia_cure(self):
        """
        اختبار الحفظ وتفكيك بنود الخدمات مع علاج فقدان الذاكرة عند إعادة الحساب:
        1. حفظ الطلب لأول مرة بمعرفات الموردين في post_data.
        2. استدعاء persist_order_anatomy(order, {}) بدون post_data (محاكاة لإعادة الحساب البرمجية).
        3. التأكد من بقاء الموردين ونظام الطقم وتكلفة الخدمات دون تصفير أو استبدال بالقيم الافتراضية.
        """
        order = PrintingOrder.objects.create(
            order_number='ORD-SET-001',
            customer=self.customer,
            title='بروشور 4 ألوان طقم زنكات وماكينة',
            order_type='flyer',
            quantity=1000,
            width=Decimal('21.0'),
            height=Decimal('29.7'),
            created_by=self.user,
            status=PricingStatus.DRAFT
        )

        post_data = {
            'order_type': 'flyer',
            'quantity': '1000',
            'width': '21.0',
            'height': '29.7',
            'paper_weight': '150',
            'cover_printing_type': 'offset',
            'print_sides_mode': 'single',
            'cover_offset_supplier': str(self.local_supplier.id),
            'cover_ctp_supplier': str(self.local_supplier.id),
            'zinc_plates_count': '4',
            'press_bed_size': '50x70',
            'profit_margin': '25.00'
        }

        # 1. الحفظ الأولي
        OrderAnatomyPersistenceService.persist_order_anatomy(order, post_data)
        
        ctp_svc = order.services.filter(supplier_service__service_type__code='ctp_plates').first()
        press_svc = order.services.filter(supplier_service__service_type__code='offset_printing').first()

        assert ctp_svc is not None
        assert ctp_svc.total_cost == Decimal('280.00')
        assert ctp_svc.supplier_service == self.ctp_service

        assert press_svc is not None
        assert press_svc.total_cost == Decimal('150.00')
        assert press_svc.supplier_service == self.offset_service

        # 2. إعادة الحساب بدون post_data (Recalculate Amnesia test)
        OrderAnatomyPersistenceService.persist_order_anatomy(order, {})

        ctp_svc_after = order.services.filter(supplier_service__service_type__code='ctp_plates').first()
        press_svc_after = order.services.filter(supplier_service__service_type__code='offset_printing').first()

        assert ctp_svc_after is not None
        assert ctp_svc_after.supplier_service == self.ctp_service
        assert ctp_svc_after.total_cost == Decimal('280.00')

        assert press_svc_after is not None
        assert press_svc_after.supplier_service == self.offset_service
        assert press_svc_after.total_cost == Decimal('150.00')

    # -------------------------------------------------------------------------
    # 5. اختبار حماية OrderService.calculate_total_cost() من مسح الخصومات
    # -------------------------------------------------------------------------
    def test_09_order_service_calculate_total_cost_no_overwrite(self):
        """
        التحقق من أن استدعاء calculate_total_cost() أو save() على OrderService
        لا يعيد ضرب (4 * 85 = 340) ويمسح سعر الطقم (280) إذا كان total_cost مسجلاً بالفعل
        """
        svc = OrderService(
            order=PrintingOrder.objects.create(
                order_number='ORD-DUMMY',
                customer=self.customer,
                title='Dummy',
                quantity=1000,
                width=Decimal('21.0'),
                height=Decimal('29.7'),
                created_by=self.user
            ),
            service_name='زنكات CTP طقم',
            service_category='prepress',
            quantity=Decimal('4'),
            unit_price=Decimal('85.00'),
            total_cost=Decimal('280.00'),
            supplier_service=self.ctp_service
        )
        calculated = svc.calculate_total_cost()
        assert calculated == Decimal('280.00')

    # -------------------------------------------------------------------------
    # 6. اختبار جسر أوامر الشراء Procurement Bridge
    # -------------------------------------------------------------------------
    def test_10_procurement_bridge_descriptions_and_wht(self):
        """
        التحقق من توليد أوامر الشراء وإثراء وصف البنود ببيانات الطقم والتراج
        مع خصم 1% ضريبة الخصم والإضافة
        """
        order = PrintingOrder.objects.create(
            order_number='ORD-SET-PO',
            customer=self.customer,
            title='طلب طباعة مجلة',
            order_type='flyer',
            quantity=1000,
            width=Decimal('21.0'),
            height=Decimal('29.7'),
            created_by=self.user,
            status=PricingStatus.APPROVED
        )

        OrderService.objects.create(
            order=order,
            service_name='طباعة أوفست 4 ألوان',
            service_category='printing',
            quantity=Decimal('1'),
            unit_price=Decimal('150.00'),
            total_cost=Decimal('150.00'),
            supplier_service=self.offset_service
        )

        OrderService.objects.create(
            order=order,
            service_name='زنكات CTP 50×70',
            service_category='prepress',
            quantity=Decimal('4'),
            unit_price=Decimal('85.00'),
            total_cost=Decimal('280.00'),
            supplier_service=self.ctp_service
        )

        pos = ProcurementBridgeService.generate_vendor_purchase_orders(order, gated=False, user=self.user)
        assert len(pos) == 1
        po = pos[0]
        assert po.supplier == self.local_supplier
        # إجمالي البندين: 150 + 280 = 430
        assert po.subtotal == Decimal('430.00')
        # ضريبة الخصم 1%: 4.30
        assert po.wht_amount == Decimal('4.30')
        # الصافي: 425.70
        assert po.total == Decimal('425.70')
        # التحقق من إثراء الوصف
        assert "[نظام طقم ماكينة: يشمل 1 تراج]" in po.notes
        assert "[نظام طقم زنكات 4 ألوان]" in po.notes

    # -------------------------------------------------------------------------
    # 7. اختبار التوافق مع معيار IAS 21 للعملات الأجنبية
    # -------------------------------------------------------------------------
    def test_11_foreign_currency_supplier_service_ias21_conversion(self):
        """
        التحقق من تحويل أسعار الأطقم للمورد الأجنبي وفق سعر الصرف اللحظي
        إذا كان المورد بالدولار USD وسعر الصرف 50.00 ج:
        سعر طقم زنكات = 10 USD -> 500 EGP
        سعر طقم ماكينة = 5 USD -> 250 EGP
        """
        usd_currency, _ = Currency.objects.get_or_create(
            code='USD',
            defaults={'name': 'US Dollar', 'symbol': '$'}
        )
        foreign_supplier = Supplier.objects.create(
            name='International Plates LLC',
            default_currency=usd_currency,
            is_active=True
        )
        foreign_ctp = SupplierService.objects.create(
            supplier=foreign_supplier,
            service_type=self.ctp_type,
            name='Imported CTP Plates 50x70',
            pricing_formula='PER_PIECE',
            base_price=Decimal('3.00'),
            set_price=Decimal('10.00'),
            currency=usd_currency,
            plate_size=self.dim_50x70,
            is_active=True
        )

        # محاكاة سعر الصرف 50.00
        from unittest.mock import patch
        with patch('financial.services.exchange_rate_service.ExchangeRateService.get_rate', return_value=Decimal('50.000000')):
            params = {
                'quantity': 1000,
                'width': 21,
                'height': 29.7,
                'sheet_size': '70x100',
                'piece_size': '50x70',
                'print_sides_mode': 'single',
                'cover_printing_type': 'offset',
                'cover_ctp_supplier': foreign_supplier.id,
                'colors_front': 4,
                'press_bed_size': '50x70'
            }
            res = PrintingCalculationEngine.calculate(params)
            assert res['success'] is True
            # 10 USD * 50 = 500 EGP
            assert res['plates']['total_cost'] == 500.0
