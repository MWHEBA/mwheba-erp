"""
اختبارات الموردين - تم حذف الخدمات المتخصصة
"""

from django.test import TestCase
from ..models import Supplier, SupplierType
from decimal import Decimal

# ملاحظة: تم حذف اختبارات الخدمات المتخصصة كجزء من تنظيف فئات الموردين
# تم حذف الفئات التالية:
# - UnifiedServicesTest
# - PaperServicesTest  
# - OffsetServicesTest
# - DigitalServicesTest
# - PlateServicesTest
# - FinishingServicesTest
# - PackagingServicesTest
# - CoatingServicesTest
# - OutdoorServicesTest
# - LaserServicesTest
# - VIPGiftServicesTest

class BasicSupplierTest(TestCase):
    """اختبارات أساسية للموردين بعد حذف الخدمات المتخصصة"""
    
    def test_supplier_creation_works(self):
        """اختبار أن إنشاء الموردين يعمل بعد حذف الخدمات المتخصصة"""
        supplier_type = SupplierType.objects.create(
            name="مورد عام",
            code="general"
        )
        
        supplier = Supplier.objects.create(
            name="مورد اختبار",
            code="TEST001",
            primary_type=supplier_type
        )
        
        self.assertEqual(supplier.name, "مورد اختبار")
        self.assertEqual(supplier.code, "TEST001")
        self.assertTrue(supplier.is_active)


class SupplierServiceIndustrialPricingTest(TestCase):
    """اختبارات منظومة التسعير الصناعية والتحويلات للخدمات والموردين"""

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(username='admin_test_pricing', password='password123', is_staff=True)
        self.client.login(username='admin_test_pricing', password='password123')

        from core.models import SystemModule
        SystemModule.objects.update_or_create(
            code='printing_pricing',
            defaults={'name': 'تسعير المطبوعات', 'is_enabled': True}
        )

        self.supplier_type = SupplierType.objects.create(name="مطبعة", code="press_test")
        self.supplier = Supplier.objects.create(name="مطبعة الأهرام", code="SUPP_TEST_01", primary_type=self.supplier_type)
        from ..models import ServiceType
        self.service_type_lam, _ = ServiceType.objects.get_or_create(code="lamination", defaults={"name": "سلوفان حراري", "category": "coating"})
        self.service_type_paper, _ = ServiceType.objects.get_or_create(code="paper", defaults={"name": "ورق كوشيه", "category": "paper"})
        self.service_type_offset, _ = ServiceType.objects.get_or_create(code="offset_printing", defaults={"name": "طباعة أوفست", "category": "press"})

    def test_calculate_cost_with_minimum_charge_floor(self):
        """اختبار معادلة التكلفة مع تطبيق الحد الأدنى للتشغيل"""
        from ..models import SupplierService
        from decimal import Decimal

        # خدمة بسعر 0.50 للفرخ، إعداد 50 جنيه، لكن الحد الأدنى للطلبية 200 جنيه
        svc = SupplierService.objects.create(
            supplier=self.supplier,
            service_type=self.service_type_lam,
            name="سلوفان مط وجه واحد",
            pricing_formula="PER_SHEET",
            base_price=Decimal('0.50'),
            setup_cost=Decimal('50.00'),
            minimum_charge=Decimal('200.00')
        )

        # كمية صغيرة: 100 فرخ × 0.50 = 50 + 50 إعداد = 100 جنيه
        # بما أن 100 < 200 (الحد الأدنى)، التكلفة يجب أن ترتفع لـ 200 جنيه إجبارياً
        cost_small = svc.calculate_cost(quantity=100)
        self.assertEqual(cost_small, Decimal('200.00'))

        # كمية كبيرة: 1000 فرخ × 0.50 = 500 + 50 إعداد = 550 جنيه
        # بما أن 550 > 200، التكلفة تكون 550 جنيه
        cost_large = svc.calculate_cost(quantity=1000)
        self.assertEqual(cost_large, Decimal('550.00'))

    def test_effective_sheet_price_from_ton(self):
        """اختبار التحويل التلقائي لسعر الفرخ من سعر الطن وفق وزن الفرخ"""
        from ..models import SupplierService
        from decimal import Decimal

        # طن كوشيه 150 جرام بسعر 50,000 جنيه للطن، مقاس 70×100 سم
        svc = SupplierService.objects.create(
            supplier=self.supplier,
            service_type=self.service_type_paper,
            name="كوشيه 150 جم مستورد",
            pricing_formula="PER_TON",
            price_per_ton=Decimal('50000.00')
        )

        # وزن فرخ 70×100 سم 150 جم = (70 × 100 × 150) / 10,000,000 = 0.105 كجم
        # سعر الفرخ = 0.105 × (50,000 / 1000) = 0.105 × 50 = 5.25 جنيه
        calculated_sheet_price = svc.get_effective_sheet_price(width_cm=70, height_cm=100, gsm=150)
        self.assertEqual(calculated_sheet_price, Decimal('5.2500'))

    def test_effective_sheet_price_from_ream(self):
        """اختبار التحويل التلقائي لسعر الفرخ من سعر الرزمة (500 فرخ)"""
        from ..models import SupplierService
        from decimal import Decimal

        # رزمة 500 فرخ بسعر 1,500 جنيه
        svc = SupplierService.objects.create(
            supplier=self.supplier,
            service_type=self.service_type_paper,
            name="طبع أبيض 80 جم رزم",
            pricing_formula="PER_REAM",
            base_price=Decimal('1500.00'),
            sheets_per_pack=500
        )

        # سعر الفرخ = 1500 / 500 = 3.00 جنيه
        calculated_sheet_price = svc.get_effective_sheet_price()
        self.assertEqual(calculated_sheet_price, Decimal('3.0000'))

    def test_bulk_adjust_services(self):
        """اختبار التعديل النسبي المجمع للأسعار (+10%)"""
        from ..models import SupplierService
        from decimal import Decimal
        from django.urls import reverse

        svc = SupplierService.objects.create(
            supplier=self.supplier,
            service_type=self.service_type_lam,
            name="سلوفان مط",
            base_price=Decimal('100.00'),
            setup_cost=Decimal('50.00'),
            minimum_charge=Decimal('200.00')
        )

        url = reverse('supplier:supplier_services_bulk_adjust', kwargs={'pk': self.supplier.pk})
        response = self.client.post(url, {
            'percentage': '10',
            'apply_to_setup': 'true'
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

        svc.refresh_from_db()
        self.assertEqual(svc.base_price, Decimal('110.00'))
        self.assertEqual(svc.setup_cost, Decimal('55.00'))
        self.assertEqual(svc.minimum_charge, Decimal('220.00'))

    def test_bulk_update_services(self):
        """اختبار حفظ مصفوفة الخدمات دفعة واحدة بالـ JSON"""
        import json
        from ..models import SupplierService
        from decimal import Decimal
        from django.urls import reverse

        url = reverse('supplier:supplier_services_bulk_update', kwargs={'pk': self.supplier.pk})
        payload = {
            'services': [
                {
                    'service_type_id': self.service_type_lam.pk,
                    'name': 'سلوفان لميع وجهين',
                    'pricing_formula': 'PER_SHEET',
                    'base_price': '0.90',
                    'setup_cost': '60.00',
                    'minimum_charge': '250.00'
                },
                {
                    'service_type_id': self.service_type_paper.pk,
                    'name': 'طبع أبيض 70 جم',
                    'pricing_formula': 'PER_REAM',
                    'base_price': '1200.00',
                    'sheets_per_pack': 500,
                    'minimum_charge': '0.00'
                }
            ]
        }
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['created_count'], 2)

        created_lam = SupplierService.objects.filter(supplier=self.supplier, name='سلوفان لميع وجهين').first()
        self.assertIsNotNone(created_lam)
        self.assertEqual(created_lam.base_price, Decimal('0.90'))
        self.assertEqual(created_lam.minimum_charge, Decimal('250.00'))

    def test_relational_bridge_auto_sync(self):
        """اختبار الجسر العلائقي والمزامنة التلقائية لـ attributes"""
        from ..models import SupplierService
        from printing_pricing.models import PrintingMachine, MachineDimension

        mach = PrintingMachine.objects.create(
            name="Heidelberg Speedmaster SM 74",
            machine_category="offset",
            colors_capacity=4,
            max_sheet_size="53x74"
        )
        dim = MachineDimension.objects.create(
            name="50×70 سم",
            code="50x70",
            dimension_type="offset_sheet",
            width=Decimal('50.00'),
            height=Decimal('70.00')
        )

        svc = SupplierService.objects.create(
            supplier=self.supplier,
            service_type=self.service_type_offset,
            name="ماكينة 50x70 تجريبية",
            base_price=Decimal('45.00'),
            machine=mach,
            dimension=dim
        )
        # Verify auto-sync hook populated attributes
        self.assertEqual(svc.attributes.get('sheet_size'), '50x70')
        self.assertEqual(svc.attributes.get('machine_type'), 'Heidelberg Speedmaster SM 74')
        self.assertEqual(svc.attributes.get('max_colors'), 4)

    def test_seed_standard_presses_view(self):
        """اختبار تهيئة ماكينات الطباعة القياسية للمورد بنجاح"""
        from django.urls import reverse
        from ..models import SupplierService
        from printing_pricing.models import PrintingMachine, MachineDimension

        PrintingMachine.objects.create(
            name="Heidelberg Speedmaster SM 74",
            machine_category="offset",
            colors_capacity=4,
            max_sheet_size="53x74"
        )
        PrintingMachine.objects.create(
            name="Heidelberg Speedmaster CD 102",
            machine_category="offset",
            colors_capacity=4,
            max_sheet_size="72x102"
        )
        MachineDimension.objects.create(
            name="50×70 سم",
            code="50x70",
            dimension_type="offset_sheet",
            width=Decimal('50.00'),
            height=Decimal('70.00')
        )
        MachineDimension.objects.create(
            name="70×100 سم",
            code="70x100",
            dimension_type="offset_sheet",
            width=Decimal('70.00'),
            height=Decimal('100.00')
        )

        url = reverse('supplier:supplier_seed_standard_presses', kwargs={'pk': self.supplier.pk})
        response = self.client.post(url, {
            'press_50x70_price': '45.00',
            'press_70x100_price': '75.00'
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['created_count'], 2)

        # Check created services
        sm_svc = SupplierService.objects.filter(supplier=self.supplier, name__icontains='SM 74').first()
        self.assertIsNotNone(sm_svc)
        self.assertEqual(sm_svc.base_price, Decimal('45.00'))
        self.assertIsNotNone(sm_svc.machine)
        self.assertIsNotNone(sm_svc.dimension)

        cd_svc = SupplierService.objects.filter(supplier=self.supplier, name__icontains='CD 102').first()
        self.assertIsNotNone(cd_svc)
        self.assertEqual(cd_svc.base_price, Decimal('75.00'))

    def test_clean_decimal_input_utility(self):
        """اختبار تنظيف الفاصلة العربية والإنجليزية في القيم النقدية"""
        from supplier.views import _clean_decimal_input

        d1, err1 = _clean_decimal_input("45,50")
        self.assertIsNone(err1)
        self.assertEqual(d1, Decimal('45.50'))

        d2, err2 = _clean_decimal_input("75،25")
        self.assertIsNone(err2)
        self.assertEqual(d2, Decimal('75.25'))

        d3, err3 = _clean_decimal_input("-10.00")
        self.assertIsNotNone(err3)

    def test_relational_fks_and_mutual_exclusivity(self):
        """اختبار إنشاء الخدمات بالربط العلائقي المباشر مع التحقق من الحصرية التخصصية"""
        from django.core.exceptions import ValidationError
        from ..models import SupplierService
        from printing_pricing.models import (
            PrintingMachine, MachineDimension, CoatingType, FinishingType,
            PackagingType, PaperSize, PaperOrigin, PaperWeight, PaperType
        )

        plate = MachineDimension.objects.create(
            name="زنك 50×70 سم",
            code="plate_50x70",
            dimension_type="plate",
            width=Decimal('50.00'),
            height=Decimal('70.00')
        )
        coating = CoatingType.objects.create(
            name="سلوفان حراري مط",
            unit_rate=Decimal('0.40')
        )

        # 1. إنشاء خدمة زنك بالربط المباشر
        svc_plate = SupplierService(
            supplier=self.supplier,
            service_type=self.service_type_lam, # or ctp
            name="زنك CTP 50x70",
            base_price=Decimal('75.00'),
            plate_size=plate
        )
        svc_plate.full_clean()
        svc_plate.save()
        self.assertEqual(svc_plate.plate_size, plate)
        self.assertEqual(svc_plate.attributes.get('plate_size'), 'زنك 50×70 سم')

        # 2. التحقق من الحصرية: دمج زنك مع ماكينة طباعة يجب أن يرمي ValidationError
        mach = PrintingMachine.objects.create(
            name="SM 52",
            machine_category="offset",
            colors_capacity=2
        )
        invalid_svc = SupplierService(
            supplier=self.supplier,
            service_type=self.service_type_offset,
            name="خدمة غير صالحة للدمج",
            base_price=Decimal('100.00'),
            machine=mach,
            plate_size=plate
        )
        with self.assertRaises(ValidationError):
            invalid_svc.full_clean()

    def test_tiered_pricing_with_service_price_tier(self):
        """اختبار حساب الأسعار عبر الشرائح السعرية المتدرجة"""
        from ..models import SupplierService, ServicePriceTier

        svc = SupplierService.objects.create(
            supplier=self.supplier,
            service_type=self.service_type_offset,
            name="أوفست مع شرائح",
            base_price=Decimal('50.00'),
            setup_cost=Decimal('100.00')
        )
        ServicePriceTier.objects.create(
            service=svc,
            min_quantity=1,
            max_quantity=3000,
            price_per_unit=Decimal('50.00')
        )
        ServicePriceTier.objects.create(
            service=svc,
            min_quantity=3001,
            max_quantity=6000,
            price_per_unit=Decimal('42.00')
        )
        ServicePriceTier.objects.create(
            service=svc,
            min_quantity=6001,
            max_quantity=None,
            price_per_unit=Decimal('35.00')
        )

        # 2000 وحدة -> 50 جنيه
        self.assertEqual(svc.get_price_for_quantity(2000), Decimal('50.00'))
        # 5000 وحدة -> 42 جنيه
        self.assertEqual(svc.get_price_for_quantity(5000), Decimal('42.00'))
        # 10000 وحدة -> 35 جنيه
        self.assertEqual(svc.get_price_for_quantity(10000), Decimal('35.00'))

    def test_supplier_service_add_page_renders_successfully(self):
        """اختبار تحميل صفحة إضافة خدمة للمورد بدون أخطاء قوالب أو متغيرات مفقودة"""
        from django.urls import reverse
        from printing_pricing.models import CoatingType, FinishingType, PackagingType

        CoatingType.objects.create(name="سلوفان لامع", unit_rate=Decimal('0.35'), minimum_charge=Decimal('100.00'))
        FinishingType.objects.create(name="تكسير فورمة", unit_rate=Decimal('0.25'))
        PackagingType.objects.create(name="كرتونة مضلعة", unit_rate=Decimal('15.00'))

        url = reverse('supplier:supplier_service_add', kwargs={'pk': self.supplier.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "سلوفان لامع")
        self.assertContains(response, "تكسير فورمة")
        self.assertContains(response, "كرتونة مضلعة")

    def test_ton_to_sheet_price_calculation_exact(self):
        """اختبار دقة المعادلة الحسابية لاشتقاق سعر الفرخ من الطن ومزامنة المقاس"""
        from ..models import SupplierService
        from printing_pricing.models import PaperSize, PaperType

        ps_70x100 = PaperSize.objects.create(name="70×100 سم", width=Decimal('70.00'), height=Decimal('100.00'))
        pt_couche = PaperType.objects.create(name="كوشيه فاخر")

        svc = SupplierService.objects.create(
            supplier=self.supplier,
            service_type=self.service_type_paper,
            name="ورق كوشيه 300 جم",
            pricing_formula="PER_TON",
            price_per_ton=Decimal('50000.00'),
            paper_size=ps_70x100,
            paper_type_ref=pt_couche,
            gsm=300
        )

        # 70 * 100 * 300 / 10,000,000 = 0.21 kg
        # 0.21 * (50000 / 1000) = 10.50 EGP
        self.assertEqual(svc.base_price, Decimal('10.5000'))
        self.assertEqual(svc.attributes.get('sheet_size'), '70x100')
        self.assertEqual(svc.attributes.get('parent_sheet_size'), '70×100 سم')

    def test_form_guards_prevent_disabling_pricing_when_active_services_exist(self):
        """اختبار صمام الأمان: منع إلغاء اعتماد التسعير لمورد لديه خدمات نشطة"""
        from ..models import SupplierService
        from ..forms import SupplierForm

        SupplierService.objects.create(
            supplier=self.supplier,
            service_type=self.service_type_offset,
            name="خدمة طباعة نشطة",
            base_price=Decimal('50.00')
        )

        form_data = {
            'name': self.supplier.name,
            'code': self.supplier.code,
            'entity_type': 'company',
            'primary_type': self.supplier.primary_type.id,
            'is_active': True,
            'is_pricing_supplier': False,  # Attempting to disable
        }
        form = SupplierForm(data=form_data, instance=self.supplier)
        self.assertFalse(form.is_valid())
        self.assertIn('is_pricing_supplier', form.errors)

    def test_backend_authorization_rejects_unauthorized_seed_presses(self):
        """اختبار رفض تهيئة ماكينات قياسية لمورد غير معتمد لطباعة الأوفست (403)"""
        from django.urls import reverse
        paper_type = SupplierType.objects.create(name="مخزن ورق", code="paper_store")
        paper_supplier = Supplier.objects.create(
            name="شركة الأهرام للورق",
            code="PAPER_001",
            primary_type=paper_type,
            is_pricing_supplier=True
        )
        paper_supplier.provided_services.set([self.service_type_paper])

        url = reverse('supplier:supplier_seed_standard_presses', kwargs={'pk': paper_supplier.pk})
        response = self.client.post(url, {'press_50x70_price': '50.00'})
        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertFalse(data['success'])

    def test_supplier_services_api_includes_currency_metadata(self):
        """اختبار إرجاع كود العملة ورمزها في API خدمات الموردين"""
        from django.urls import reverse
        from ..models import SupplierService

        SupplierService.objects.create(
            supplier=self.supplier,
            service_type=self.service_type_offset,
            name="ماكينة 4 لون",
            base_price=Decimal('60.00')
        )

        url = reverse('supplier:supplier_services_api', kwargs={'pk': self.supplier.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertGreater(len(data['services']), 0)
        first_svc = data['services'][0]
        self.assertIn('currency_code', first_svc)
        self.assertIn('currency_symbol', first_svc)

    def test_supplier_seed_paper_matrix(self):
        """اختبار توليد مصفوفة أسعار الورق بالطن والمقاس والجراماجات تلقائياً"""
        from django.urls import reverse
        from ..models import SupplierService
        from printing_pricing.models import PaperType, PaperSize, PaperWeight, PaperOrigin

        pt, _ = PaperType.objects.get_or_create(name="كوشيه فاخر", defaults={'sort_order': 1})
        ps1, _ = PaperSize.objects.get_or_create(name="70x100", defaults={'width': Decimal('70.00'), 'height': Decimal('100.00'), 'sort_order': 1})
        pw1, _ = PaperWeight.objects.get_or_create(gsm=150, defaults={'name': "150 جم"})
        po, _ = PaperOrigin.objects.get_or_create(code="KR", defaults={'name': "كوري"})

        url = reverse('supplier:supplier_seed_paper_matrix', kwargs={'pk': self.supplier.pk})
        response = self.client.post(url, {
            'paper_type_id': pt.id,
            'paper_origin_id': po.id,
            'price_per_ton': '45000.00',
            'paper_sizes': [ps1.id],
            'paper_weights': [pw1.id],
        })

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['created_count'], 1)

        # التحقق من حساب سعر الفرخ: (70 * 100 * 150 / 10000000) * (45000 / 1000) = 0.105 * 45 = 4.7250
        svc = SupplierService.objects.get(supplier=self.supplier, paper_type_ref=pt, paper_size=ps1, gsm=150)
        self.assertEqual(svc.pricing_formula, 'PER_TON')
        self.assertEqual(svc.price_per_ton, Decimal('45000.00'))
        self.assertEqual(svc.base_price, Decimal('4.73'))
        self.assertEqual(svc.get_effective_sheet_price(), Decimal('4.7250'))
        self.assertEqual(svc.paper_origin, po)
        self.assertTrue(svc.is_active)

    def test_supplier_service_delete_soft_delete_when_used_in_orders(self):
        """اختبار التعطيل الآمن للخدمة بدلاً من الحذف عند وجود أوامر عمل مرتبطة بها"""
        from django.urls import reverse
        from ..models import SupplierService
        from printing_pricing.models import OrderService, PrintingOrder

        svc = SupplierService.objects.create(
            supplier=self.supplier,
            service_type=self.service_type_offset,
            name="ماكينة طباعة قديمة",
            base_price=Decimal('50.00'),
            is_active=True
        )

        # محاكاة أمر عمل مسجل بهذه الخدمة
        order = PrintingOrder.objects.create(
            order_number="ORD-TEST-001",
            customer_name="عميل اختبار",
            quantity=1000,
            created_by=self.user
        )
        OrderService.objects.create(
            order=order,
            service_category='printing',
            service_name="طباعة أوفست تجريبية",
            quantity=Decimal('1.000'),
            unit='piece',
            unit_price=Decimal('50.00'),
            total_cost=Decimal('50.00'),
            supplier_service=svc
        )

        url = reverse('supplier:supplier_service_delete', kwargs={'pk': self.supplier.pk, 'service_pk': svc.pk})
        response = self.client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertTrue(data.get('soft_deleted'))

        # الخدمة لم تُحذف من قاعدة البيانات بل تم تعطيلها للحفاظ على السجل التاريخي
        svc.refresh_from_db()
        self.assertFalse(svc.is_active)

    def test_supplier_service_sheet_price_fallback_logic(self):
        """اختبار حساب سعر الفرخ بالسقوط الآمن على الأبعاد في حال عدم وجود قاموس attributes"""
        from ..models import SupplierService
        from printing_pricing.models import PaperSize

        ps = PaperSize.objects.create(name="66x88", width=Decimal('66.00'), height=Decimal('88.00'))
        svc = SupplierService.objects.create(
            supplier=self.supplier,
            service_type=self.service_type_paper,
            name="ورق بدون attributes",
            pricing_formula='PER_TON',
            price_per_ton=Decimal('50000.00'),
            paper_size=ps,
            gsm=200,
            attributes={}
        )

        effective_price = svc.get_effective_sheet_price()
        # وزن الفرخ: (66 * 88 * 200) / 10000000 = 0.11616 كجم
        # سعر الفرخ: 0.11616 * (50000 / 1000) = 5.808
        expected_price = (Decimal('0.11616') * Decimal('50')).quantize(Decimal('0.0001'))
        self.assertEqual(effective_price, expected_price)

    def test_pricing_endpoints_and_ui_strictly_blocked_when_module_disabled(self):
        """اختبار حظر جميع مسارات وشاشات ونماذج التسعير تماماً عند تعطيل موديول تسعير الطباعة"""
        from core.models import SystemModule
        from django.urls import reverse
        from supplier.forms import SupplierForm

        # 1. تعطيل موديول التسعير
        SystemModule.objects.filter(code='printing_pricing').update(is_enabled=False)

        # 2. التحقق من حظر الوصول المباشر لشاشات إضافة وتعديل الخدمات
        add_url = reverse('supplier:supplier_service_add', kwargs={'pk': self.supplier.pk})
        resp_add = self.client.get(add_url)
        self.assertEqual(resp_add.status_code, 302)

        # 3. التحقق من إرجاع 403 Forbidden لطلبات AJAX عند تعطيل الموديول
        bulk_url = reverse('supplier:supplier_services_bulk_update', kwargs={'pk': self.supplier.pk})
        resp_bulk = self.client.post(bulk_url, {}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp_bulk.status_code, 403)
        self.assertIn('موديول تسعير الطباعة غير مفعّل', resp_bulk.json().get('error', ''))

        adjust_url = reverse('supplier:supplier_services_bulk_adjust', kwargs={'pk': self.supplier.pk})
        resp_adjust = self.client.post(adjust_url, {}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp_adjust.status_code, 403)

        # 4. التحقق من نموذج المورد SupplierForm: إخفاء حقول التسعير وتحويلها لـ Hidden
        form = SupplierForm()
        self.assertEqual(form.fields['is_pricing_supplier'].widget.input_type, 'hidden')
        self.assertEqual(form.fields['provided_services'].widget.input_type, 'hidden')