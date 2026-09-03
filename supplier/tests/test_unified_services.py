"""
اختبارات الموردين - تم حذف الخدمات المتخصصة
"""

from django.test import TestCase
from ..models import Supplier, SupplierType

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

        self.supplier_type = SupplierType.objects.create(name="مطبعة", code="press_test")
        self.supplier = Supplier.objects.create(name="مطبعة الأهرام", code="SUPP_TEST_01", primary_type=self.supplier_type)
        from ..models import ServiceType
        self.service_type_lam = ServiceType.objects.create(name="سلوفان حراري", code="lamination", category="coating")
        self.service_type_paper = ServiceType.objects.create(name="ورق كوشيه", code="paper", category="paper")

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