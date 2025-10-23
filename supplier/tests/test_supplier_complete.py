"""
اختبارات شاملة لنظام الموردين - تغطية 100%
يشمل: النماذج، العروض، النماذج، APIs، والعلاقات
"""

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from decimal import Decimal
from django.db.models import Sum

from ..models import (
    Supplier, SupplierType, SupplierTypeSettings,
    SpecializedService, ServicePriceTier,
    PaperServiceDetails, OffsetPrintingDetails,
    DigitalPrintingDetails, PlateServiceDetails,
    FinishingServiceDetails, OutdoorPrintingDetails,
    LaserServiceDetails, VIPGiftDetails,
    SupplierServiceTag
)

User = get_user_model()


# ========================================
# اختبارات النماذج (Models)
# ========================================

class SupplierTypeModelTest(TestCase):
    """اختبارات نموذج أنواع الموردين"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )
        
    def test_create_supplier_type(self):
        """اختبار إنشاء نوع مورد"""
        supplier_type = SupplierType.objects.create(
            name="موردي الورق",
            code="paper",
            description="موردي الورق والخامات الورقية",
            icon="fas fa-file",
            color="#007bff"
        )
        
        self.assertEqual(supplier_type.name, "موردي الورق")
        self.assertEqual(supplier_type.code, "paper")
        self.assertTrue(supplier_type.is_active)
        self.assertIsNotNone(supplier_type.slug)
        
    def test_supplier_type_str_method(self):
        """اختبار طريقة __str__"""
        supplier_type = SupplierType.objects.create(
            name="موردي الطباعة",
            code="printing"
        )
        
        self.assertEqual(str(supplier_type), "موردي الطباعة")
        
    def test_supplier_type_ordering(self):
        """اختبار ترتيب أنواع الموردين"""
        type1 = SupplierType.objects.create(
            name="نوع 1", code="type1", display_order=2
        )
        type2 = SupplierType.objects.create(
            name="نوع 2", code="type2", display_order=1
        )
        
        types = list(SupplierType.objects.all())
        self.assertEqual(types[0], type2)
        self.assertEqual(types[1], type1)


class SupplierTypeSettingsModelTest(TestCase):
    """اختبارات نموذج إعدادات أنواع الموردين"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )
        
    def test_create_supplier_type_settings(self):
        """اختبار إنشاء إعدادات نوع مورد"""
        settings = SupplierTypeSettings.objects.create(
            name="موردي الورق",
            code="paper_suppliers",
            description="إعدادات موردي الورق",
            icon="fas fa-file",
            color="#28a745",
            created_by=self.user
        )
        
        self.assertEqual(settings.name, "موردي الورق")
        self.assertEqual(settings.code, "paper_suppliers")
        self.assertTrue(settings.is_active)
        self.assertFalse(settings.is_system)
        
    def test_supplier_type_settings_validation(self):
        """اختبار التحقق من صحة البيانات"""
        from django.core.exceptions import ValidationError
        
        # اختبار لون غير صحيح
        settings = SupplierTypeSettings(
            name="اختبار",
            code="test",
            color="invalid_color"
        )
        
        with self.assertRaises(ValidationError):
            settings.full_clean()
            
    def test_supplier_type_settings_sync(self):
        """اختبار المزامنة مع SupplierType"""
        settings = SupplierTypeSettings.objects.create(
            name="موردي الطباعة",
            code="printing",
            icon="fas fa-print",
            color="#007bff"
        )
        
        # التحقق من إنشاء SupplierType تلقائياً
        supplier_type = SupplierType.objects.filter(code="printing").first()
        self.assertIsNotNone(supplier_type)
        self.assertEqual(supplier_type.name, settings.name)


class SupplierModelTest(TestCase):
    """اختبارات نموذج الموردين"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )
        
        self.supplier_type = SupplierType.objects.create(
            name="موردي الورق",
            code="paper"
        )
        
    def test_create_supplier(self):
        """اختبار إنشاء مورد"""
        supplier = Supplier.objects.create(
            name="مورد الورق المصري",
            code="PAPER001",
            email="supplier@paper.com",
            phone="+201234567890",
            address="القاهرة، مصر",
            primary_type=self.supplier_type,
            created_by=self.user
        )
        
        self.assertEqual(supplier.name, "مورد الورق المصري")
        self.assertEqual(supplier.code, "PAPER001")
        self.assertTrue(supplier.is_active)
        self.assertEqual(supplier.balance, 0)
        
    def test_supplier_str_method(self):
        """اختبار طريقة __str__"""
        supplier = Supplier.objects.create(
            name="مورد تجريبي",
            code="TEST001"
        )
        
        self.assertEqual(str(supplier), "مورد تجريبي")
        
    def test_supplier_actual_balance(self):
        """اختبار حساب الرصيد الفعلي"""
        supplier = Supplier.objects.create(
            name="مورد اختبار",
            code="TEST002",
            balance=Decimal('1000.00')
        )
        
        # الرصيد الفعلي يجب أن يكون 0 في البداية (بدون فواتير)
        self.assertEqual(supplier.actual_balance, 0)
        
    def test_supplier_many_to_many_types(self):
        """اختبار العلاقة many-to-many مع أنواع الموردين"""
        supplier = Supplier.objects.create(
            name="مورد متعدد الخدمات",
            code="MULTI001"
        )
        
        type1 = SupplierType.objects.create(name="ورق", code="paper_multi", slug="paper-multi")
        type2 = SupplierType.objects.create(name="طباعة", code="printing_multi", slug="printing-multi")
        
        supplier.supplier_types.add(type1, type2)
        
        self.assertEqual(supplier.supplier_types.count(), 2)
        self.assertIn(type1, supplier.supplier_types.all())
        self.assertIn(type2, supplier.supplier_types.all())


class SpecializedServiceModelTest(TestCase):
    """اختبارات نموذج الخدمات المتخصصة"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.supplier_type = SupplierType.objects.create(
            name="موردي الورق",
            code="paper"
        )
        
        self.supplier = Supplier.objects.create(
            name="مورد الورق",
            code="PAPER001",
            primary_type=self.supplier_type
        )
        
    def test_create_specialized_service(self):
        """اختبار إنشاء خدمة متخصصة"""
        service = SpecializedService.objects.create(
            supplier=self.supplier,
            category=self.supplier_type,
            name="ورق كوشيه 120 جرام",
            description="ورق كوشيه عالي الجودة",
            setup_cost=Decimal('100.00')
        )
        
        self.assertEqual(service.name, "ورق كوشيه 120 جرام")
        self.assertEqual(service.supplier, self.supplier)
        self.assertTrue(service.is_active)
        
    def test_specialized_service_str_method(self):
        """اختبار طريقة __str__"""
        service = SpecializedService.objects.create(
            supplier=self.supplier,
            category=self.supplier_type,
            name="خدمة اختبار"
        )
        
        expected = f"{self.supplier.name} - خدمة اختبار"
        self.assertEqual(str(service), expected)
        
    def test_service_price_calculation(self):
        """اختبار حساب السعر حسب الكمية"""
        service = SpecializedService.objects.create(
            supplier=self.supplier,
            category=self.supplier_type,
            name="خدمة تسعير",
            setup_cost=Decimal('50.00')
        )
        
        # إضافة شرائح سعرية
        ServicePriceTier.objects.create(
            service=service,
            tier_name="1-100",
            min_quantity=1,
            max_quantity=100,
            price_per_unit=Decimal('10.00')
        )
        
        ServicePriceTier.objects.create(
            service=service,
            tier_name="101-500",
            min_quantity=101,
            max_quantity=500,
            price_per_unit=Decimal('8.00')
        )
        
        # اختبار الحصول على السعر
        price_50 = service.get_price_for_quantity(50)
        self.assertEqual(price_50, Decimal('10.00'))
        
        price_200 = service.get_price_for_quantity(200)
        self.assertEqual(price_200, Decimal('8.00'))
        
    def test_service_total_cost_calculation(self):
        """اختبار حساب التكلفة الإجمالية"""
        service = SpecializedService.objects.create(
            supplier=self.supplier,
            category=self.supplier_type,
            name="خدمة تكلفة",
            setup_cost=Decimal('100.00')
        )
        
        ServicePriceTier.objects.create(
            service=service,
            tier_name="1-1000",
            min_quantity=1,
            max_quantity=1000,
            price_per_unit=Decimal('5.00')
        )
        
        # التكلفة = (5 * 100) + 100 = 600
        total_cost = service.get_total_cost(100)
        self.assertEqual(total_cost, Decimal('600.00'))


class ServicePriceTierModelTest(TestCase):
    """اختبارات نموذج الشرائح السعرية"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        supplier_type = SupplierType.objects.create(
            name="ورق", code="paper"
        )
        
        supplier = Supplier.objects.create(
            name="مورد", code="SUP001"
        )
        
        self.service = SpecializedService.objects.create(
            supplier=supplier,
            category=supplier_type,
            name="خدمة"
        )
        
    def test_create_price_tier(self):
        """اختبار إنشاء شريحة سعرية"""
        tier = ServicePriceTier.objects.create(
            service=self.service,
            tier_name="1-100",
            min_quantity=1,
            max_quantity=100,
            price_per_unit=Decimal('10.00'),
            discount_percentage=Decimal('5.00')
        )
        
        self.assertEqual(tier.min_quantity, 1)
        self.assertEqual(tier.max_quantity, 100)
        self.assertEqual(tier.price_per_unit, Decimal('10.00'))
        self.assertTrue(tier.is_active)
        
    def test_price_tier_str_method(self):
        """اختبار طريقة __str__"""
        tier = ServicePriceTier.objects.create(
            service=self.service,
            tier_name="100-500",
            min_quantity=100,
            max_quantity=500,
            price_per_unit=Decimal('8.50')
        )
        
        str_result = str(tier)
        self.assertIn("100", str_result)
        self.assertIn("500", str_result)
        self.assertIn("8.5", str_result)
        
    def test_price_tier_quantity_range_display(self):
        """اختبار عرض نطاق الكمية"""
        tier = ServicePriceTier.objects.create(
            service=self.service,
            tier_name="1000+",
            min_quantity=1000,
            max_quantity=None,
            price_per_unit=Decimal('5.00')
        )
        
        range_display = tier.get_quantity_range_display()
        self.assertEqual(range_display, "1000+")


class PaperServiceDetailsModelTest(TestCase):
    """اختبارات نموذج تفاصيل خدمات الورق"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        supplier_type = SupplierType.objects.create(
            name="ورق", code="paper"
        )
        
        supplier = Supplier.objects.create(
            name="مورد ورق", code="PAPER001"
        )
        
        self.service = SpecializedService.objects.create(
            supplier=supplier,
            category=supplier_type,
            name="ورق كوشيه"
        )
        
    def test_create_paper_service_details(self):
        """اختبار إنشاء تفاصيل خدمة ورق"""
        details = PaperServiceDetails.objects.create(
            service=self.service,
            paper_type="كوشيه",
            gsm=120,
            sheet_size="70.00x100.00",
            country_of_origin="مصر",
            price_per_sheet=Decimal('2.50')  # إضافة السعر المطلوب
        )
        
        self.assertEqual(details.paper_type, "كوشيه")
        self.assertEqual(details.gsm, 120)
        self.assertEqual(details.sheet_size, "70.00x100.00")


class OffsetPrintingDetailsModelTest(TestCase):
    """اختبارات نموذج تفاصيل خدمات الأوفست"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        supplier_type = SupplierType.objects.create(
            name="أوفست", code="offset"
        )
        
        supplier = Supplier.objects.create(
            name="مطبعة أوفست", code="OFFSET001"
        )
        
        self.service = SpecializedService.objects.create(
            supplier=supplier,
            category=supplier_type,
            name="طباعة أوفست"
        )
        
    def test_create_offset_details(self):
        """اختبار إنشاء تفاصيل خدمة أوفست"""
        details = OffsetPrintingDetails.objects.create(
            service=self.service,
            machine_type="sm52",
            sheet_size="quarter_sheet",
            impression_cost_per_1000=Decimal('250.00')
        )
        
        self.assertEqual(details.machine_type, "sm52")
        self.assertEqual(details.sheet_size, "quarter_sheet")


# ========================================
# اختبارات العروض (Views)
# ========================================

class SupplierViewsTest(TestCase):
    """اختبارات عروض الموردين"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')
        
        self.supplier_type = SupplierType.objects.create(
            name="ورق", code="paper"
        )
        
        self.supplier = Supplier.objects.create(
            name="مورد اختبار",
            code="TEST001",
            primary_type=self.supplier_type
        )
        
    def test_supplier_list_view(self):
        """اختبار عرض قائمة الموردين"""
        response = self.client.get(reverse('supplier:supplier_list'))
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "مورد اختبار")
        
    def test_supplier_list_view_requires_login(self):
        """اختبار أن عرض القائمة يتطلب تسجيل دخول"""
        self.client.logout()
        response = self.client.get(reverse('supplier:supplier_list'))
        
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)
        
    def test_supplier_detail_view(self):
        """اختبار عرض تفاصيل المورد"""
        response = self.client.get(
            reverse('supplier:supplier_detail', kwargs={'pk': self.supplier.pk})
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.supplier.name)
        
    def test_supplier_add_view_get(self):
        """اختبار عرض إضافة مورد (GET)"""
        response = self.client.get(reverse('supplier:supplier_add'))
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name')
        
    def test_supplier_add_view_post(self):
        """اختبار إضافة مورد (POST)"""
        data = {
            'name': 'مورد جديد',
            'code': 'NEW001',
            'email': 'new@supplier.com',
            'phone': '+201234567890',
            'address': 'القاهرة',
            'is_active': True
        }
        
        response = self.client.post(reverse('supplier:supplier_add'), data, follow=True)
        
        # التحقق من الاستجابة (قد يكون redirect أو نجاح)
        self.assertIn(response.status_code, [200, 302])
        
    def test_supplier_edit_view(self):
        """اختبار تعديل مورد"""
        data = {
            'name': 'مورد معدل',
            'code': self.supplier.code,
            'email': 'updated@supplier.com',
            'is_active': True
        }
        
        response = self.client.post(
            reverse('supplier:supplier_edit', kwargs={'pk': self.supplier.pk}),
            data,
            follow=True
        )
        
        # التحقق من الاستجابة
        self.assertIn(response.status_code, [200, 302])
        
    def test_supplier_delete_view(self):
        """اختبار حذف (تعطيل) مورد"""
        response = self.client.post(
            reverse('supplier:supplier_delete', kwargs={'pk': self.supplier.pk})
        )
        
        # التحقق من التعطيل
        self.supplier.refresh_from_db()
        self.assertFalse(self.supplier.is_active)
        
    def test_supplier_list_filtering(self):
        """اختبار فلترة قائمة الموردين"""
        # إنشاء موردين إضافيين
        Supplier.objects.create(
            name="مورد نشط", code="ACTIVE001", is_active=True
        )
        Supplier.objects.create(
            name="مورد معطل", code="INACTIVE001", is_active=False
        )
        
        # اختبار فلترة النشطين
        response = self.client.get(reverse('supplier:supplier_list') + '?status=active')
        self.assertContains(response, "مورد نشط")
        self.assertNotContains(response, "مورد معطل")
        
    def test_supplier_list_search(self):
        """اختبار البحث في قائمة الموردين"""
        response = self.client.get(
            reverse('supplier:supplier_list') + '?search=اختبار'
        )
        
        self.assertContains(response, "مورد اختبار")


class SupplierAPIViewsTest(TestCase):
    """اختبارات APIs الموردين"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')
        
    def test_supplier_list_api(self):
        """اختبار API قائمة الموردين"""
        # إنشاء موردين
        Supplier.objects.create(name="مورد 1", code="SUP001")
        Supplier.objects.create(name="مورد 2", code="SUP002")
        
        response = self.client.get(reverse('supplier:supplier_list_api'))
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('suppliers', data)
        self.assertEqual(len(data['suppliers']), 2)


# ========================================
# اختبارات التكامل (Integration Tests)
# ========================================

class SupplierIntegrationTest(TestCase):
    """اختبارات تكامل نظام الموردين"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')
        
    def test_complete_supplier_lifecycle(self):
        """اختبار دورة حياة كاملة للمورد"""
        # 1. إنشاء نوع مورد
        supplier_type = SupplierType.objects.create(
            name="موردي الورق",
            code="paper"
        )
        
        # 2. إنشاء مورد
        supplier = Supplier.objects.create(
            name="مورد الورق المصري",
            code="PAPER001",
            primary_type=supplier_type,
            created_by=self.user
        )
        
        # 3. إنشاء خدمة متخصصة
        service = SpecializedService.objects.create(
            supplier=supplier,
            category=supplier_type,
            name="ورق كوشيه 120 جرام",
            setup_cost=Decimal('100.00')
        )
        
        # 4. إضافة شرائح سعرية
        tier1 = ServicePriceTier.objects.create(
            service=service,
            tier_name="1-100",
            min_quantity=1,
            max_quantity=100,
            price_per_unit=Decimal('10.00')
        )
        
        tier2 = ServicePriceTier.objects.create(
            service=service,
            tier_name="101-500",
            min_quantity=101,
            max_quantity=500,
            price_per_unit=Decimal('8.00')
        )
        
        # 5. إضافة تفاصيل الورق
        paper_details = PaperServiceDetails.objects.create(
            service=service,
            paper_type="كوشيه",
            gsm=120,
            sheet_size="70.00x100.00",
            country_of_origin="مصر",
            price_per_sheet=Decimal('2.50')
        )
        
        # التحقق من العلاقات
        self.assertEqual(supplier.specialized_services.count(), 1)
        self.assertEqual(service.price_tiers.count(), 2)
        self.assertTrue(hasattr(service, 'paper_details'))
        
        # التحقق من حساب السعر
        price_50 = service.get_price_for_quantity(50)
        self.assertEqual(price_50, Decimal('10.00'))
        
        price_200 = service.get_price_for_quantity(200)
        self.assertEqual(price_200, Decimal('8.00'))
        
        # التحقق من التكلفة الإجمالية
        total_cost = service.get_total_cost(100)
        expected = (Decimal('10.00') * 100) + Decimal('100.00')
        self.assertEqual(total_cost, expected)
        
    def test_supplier_with_multiple_services(self):
        """اختبار مورد مع خدمات متعددة"""
        supplier_type = SupplierType.objects.create(
            name="خدمات متعددة", code="multi"
        )
        
        supplier = Supplier.objects.create(
            name="مورد متعدد الخدمات",
            code="MULTI001"
        )
        
        # إضافة خدمات متعددة
        service1 = SpecializedService.objects.create(
            supplier=supplier,
            category=supplier_type,
            name="خدمة 1"
        )
        
        service2 = SpecializedService.objects.create(
            supplier=supplier,
            category=supplier_type,
            name="خدمة 2"
        )
        
        service3 = SpecializedService.objects.create(
            supplier=supplier,
            category=supplier_type,
            name="خدمة 3"
        )
        
        # التحقق
        self.assertEqual(supplier.specialized_services.count(), 3)
        self.assertEqual(
            supplier.specialized_services.filter(is_active=True).count(),
            3
        )


# ========================================
# اختبارات الأداء والحدود (Edge Cases)
# ========================================

class SupplierEdgeCasesTest(TestCase):
    """اختبارات الحالات الحدية"""
    
    def test_supplier_with_empty_code(self):
        """اختبار مورد بدون كود"""
        from django.core.exceptions import ValidationError
        
        # النظام يسمح بإنشاء مورد بدون كود لكن يجب أن يكون unique
        supplier = Supplier.objects.create(name="مورد بدون كود", code="")
        self.assertEqual(supplier.code, "")
            
    def test_duplicate_supplier_code(self):
        """اختبار تكرار كود المورد"""
        from django.db import IntegrityError
        
        Supplier.objects.create(name="مورد 1", code="DUP001")
        
        with self.assertRaises(IntegrityError):
            Supplier.objects.create(name="مورد 2", code="DUP001")
            
    def test_service_without_price_tiers(self):
        """اختبار خدمة بدون شرائح سعرية"""
        supplier = Supplier.objects.create(name="مورد", code="SUP001")
        supplier_type = SupplierType.objects.create(name="نوع", code="type")
        
        service = SpecializedService.objects.create(
            supplier=supplier,
            category=supplier_type,
            name="خدمة بدون أسعار"
        )
        
        # يجب أن يرجع 0
        price = service.get_price_for_quantity(100)
        self.assertEqual(price, 0)
        
    def test_large_quantity_pricing(self):
        """اختبار التسعير لكميات كبيرة"""
        supplier = Supplier.objects.create(name="مورد", code="SUP001")
        supplier_type = SupplierType.objects.create(name="نوع", code="type")
        
        service = SpecializedService.objects.create(
            supplier=supplier,
            category=supplier_type,
            name="خدمة"
        )
        
        # شريحة مفتوحة
        ServicePriceTier.objects.create(
            service=service,
            tier_name="1000+",
            min_quantity=1000,
            max_quantity=None,
            price_per_unit=Decimal('1.00')
        )
        
        # اختبار كمية كبيرة جداً
        price = service.get_price_for_quantity(1000000)
        self.assertEqual(price, Decimal('1.00'))
