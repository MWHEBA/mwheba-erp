"""
اختبارات التكامل الشاملة لنظام التسعير
Integration Tests for Complete Pricing System
"""
import json
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from pricing.models import (
    PricingOrder,
    PaperType,
    PaperSize,
    CoatingType,
    FinishingType,
    PlateSize,
    VATSetting,
    PricingSupplierSelection,
)
from supplier.models import (
    Supplier,
    SupplierType,
    SpecializedService,
    PaperServiceDetails,
    DigitalPrintingDetails,
    PlateServiceDetails,
    ServicePriceTier,
)
from client.models import Customer


class PricingIntegrationTestCase(TestCase):
    """اختبارات التكامل الأساسية للتسعير"""

    def setUp(self):
        """إعداد البيانات للاختبار"""
        # إنشاء مستخدم
        self.user = User.objects.create_user(
            username="test_user", email="test@example.com", password="testpass123"
        )

        # إنشاء عميل
        self.customer = Customer.objects.create(
            name="شركة الاختبار",
            code="TEST001",
            phone="01234567890",
            email="customer@test.com",
        )

        # إنشاء أنواع الموردين
        self.paper_type_supplier = SupplierType.objects.create(
            name="موردي الورق", code="paper", description="موردي الورق والخامات"
        )

        self.printing_type_supplier = SupplierType.objects.create(
            name="موردي الطباعة", code="printing", description="موردي خدمات الطباعة"
        )

        # إنشاء موردين
        self.paper_supplier = Supplier.objects.create(
            name="مورد الورق الأول",
            code="PAPER001",
            primary_type=self.paper_type_supplier,
            phone="01111111111",
            email="paper@supplier.com",
        )

        self.printing_supplier = Supplier.objects.create(
            name="مورد الطباعة الأول",
            code="PRINT001",
            primary_type=self.printing_type_supplier,
            phone="01222222222",
            email="print@supplier.com",
        )

        # إنشاء أنواع الورق والمقاسات
        self.paper_type = PaperType.objects.create(
            name="ورق أبيض", code="WHITE", description="ورق أبيض عادي"
        )

        self.paper_size = PaperSize.objects.create(
            name="A4", width=210, height=297, unit="mm"
        )

        # إنشاء خدمات الورق
        self.paper_service = PaperServiceDetails.objects.create(
            supplier=self.paper_supplier,
            paper_type=self.paper_type,
            paper_size=self.paper_size,
            gsm=80,
            price_per_sheet=Decimal("0.50"),
            price_per_kg=Decimal("15.00"),
            is_active=True,
        )

        # إنشاء خدمات الطباعة الرقمية
        self.digital_service = DigitalPrintingDetails.objects.create(
            supplier=self.printing_supplier,
            paper_size=self.paper_size,
            color_type="color",
            price_per_copy=Decimal("2.00"),
            minimum_quantity=1,
            is_active=True,
        )

        # إنشاء إعدادات الضريبة
        self.vat_setting = VATSetting.objects.create(
            rate=Decimal("15.00"), is_active=True
        )

        # إنشاء عميل HTTP للاختبار
        self.client_http = Client()
        self.client_http.login(username="test_user", password="testpass123")

    def test_complete_pricing_workflow(self):
        """اختبار سير العمل الكامل للتسعير"""

        # 1. إنشاء طلب تسعير جديد
        pricing_data = {
            "customer": self.customer.id,
            "order_type": "digital",
            "paper_type": self.paper_type.id,
            "paper_size": self.paper_size.id,
            "quantity": 1000,
            "description": "طلب تسعير اختباري",
            "supplier": self.printing_supplier.id,
        }

        response = self.client_http.post(
            reverse("pricing:pricing_create"), data=pricing_data
        )

        # التحقق من إنشاء الطلب
        self.assertEqual(response.status_code, 302)  # Redirect after creation

        # التحقق من وجود الطلب في قاعدة البيانات
        order = PricingOrder.objects.filter(customer=self.customer).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.quantity, 1000)
        self.assertEqual(order.order_type, "digital")

        # 2. اختبار حساب التكلفة التلقائي
        paper_cost = order.calculate_paper_cost()
        self.assertGreater(paper_cost, 0)

        printing_cost = order.calculate_printing_cost()
        self.assertGreater(printing_cost, 0)

        total_cost = order.calculate_total_cost()
        self.assertGreater(total_cost, 0)

        # 3. اختبار إضافة اختيار مورد
        supplier_selection = PricingSupplierSelection.objects.create(
            order=order,
            supplier=self.printing_supplier,
            service_tag_id=1,  # سنحتاج لإنشاء service tag
            quoted_price=Decimal("2500.00"),
            estimated_cost=Decimal("2000.00"),
            status="quoted",
            created_by=self.user,
        )

        self.assertEqual(supplier_selection.get_price_difference(), Decimal("500.00"))
        self.assertEqual(supplier_selection.get_price_difference_percentage(), 25.0)

        return order

    def test_pricing_apis(self):
        """اختبار APIs التسعير"""

        # اختبار API الحصول على الموردين حسب نوع الخدمة
        response = self.client_http.get(
            reverse("pricing:suppliers_by_service_type"), {"service_type": "printing"}
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data["success"])

        # اختبار API خدمات التشطيب
        response = self.client_http.get(
            reverse("pricing:coating_services_api"),
            {"supplier_id": self.printing_supplier.id},
        )

        self.assertEqual(response.status_code, 200)

    def test_pricing_calculations(self):
        """اختبار دقة الحسابات"""

        order = PricingOrder.objects.create(
            customer=self.customer,
            order_type="digital",
            paper_type=self.paper_type,
            paper_size=self.paper_size,
            quantity=500,
            supplier=self.printing_supplier,
            created_by=self.user,
        )

        # اختبار حساب تكلفة الورق
        paper_cost = order.calculate_paper_cost()
        expected_paper_cost = 500 * Decimal("0.50")  # 500 ورقة × 0.50
        self.assertEqual(paper_cost, expected_paper_cost)

        # اختبار حساب تكلفة الطباعة
        printing_cost = order.calculate_printing_cost()
        expected_printing_cost = 500 * Decimal("2.00")  # 500 نسخة × 2.00
        self.assertEqual(printing_cost, expected_printing_cost)

        # اختبار حساب الضريبة
        vat_amount = order.calculate_vat()
        subtotal = paper_cost + printing_cost
        expected_vat = subtotal * (Decimal("15.00") / 100)
        self.assertEqual(vat_amount, expected_vat)

    def test_supplier_selection_workflow(self):
        """اختبار سير عمل اختيار الموردين"""

        order = PricingOrder.objects.create(
            customer=self.customer,
            order_type="digital",
            paper_type=self.paper_type,
            paper_size=self.paper_size,
            quantity=1000,
            created_by=self.user,
        )

        # إضافة عدة موردين للمقارنة
        suppliers = [self.paper_supplier, self.printing_supplier]
        selections = []

        for i, supplier in enumerate(suppliers):
            selection = PricingSupplierSelection.objects.create(
                order=order,
                supplier=supplier,
                service_tag_id=1,
                quoted_price=Decimal(f"{2000 + (i * 100)}.00"),
                estimated_cost=Decimal("2000.00"),
                status="quoted",
                created_by=self.user,
            )
            selections.append(selection)

        # اختيار أفضل مورد (الأقل سعراً)
        best_selection = min(selections, key=lambda x: x.quoted_price)
        best_selection.is_selected = True
        best_selection.save()

        self.assertTrue(best_selection.is_selected)
        self.assertEqual(best_selection.status, "selected")
        self.assertIsNotNone(best_selection.selected_at)


class PricingPerformanceTestCase(TestCase):
    """اختبارات الأداء للتسعير"""

    def setUp(self):
        """إعداد بيانات كبيرة للاختبار"""
        self.user = User.objects.create_user(
            username="perf_user", password="testpass123"
        )

        # إنشاء عدد كبير من الموردين والخدمات
        self.create_bulk_data()

    def create_bulk_data(self):
        """إنشاء بيانات كبيرة للاختبار"""

        # إنشاء أنواع موردين
        supplier_types = []
        for i in range(5):
            supplier_type = SupplierType.objects.create(
                name=f"نوع مورد {i+1}",
                code=f"TYPE{i+1:02d}",
                description=f"وصف نوع المورد {i+1}",
            )
            supplier_types.append(supplier_type)

        # إنشاء موردين
        suppliers = []
        for i in range(20):
            supplier = Supplier.objects.create(
                name=f"مورد رقم {i+1}",
                code=f"SUP{i+1:03d}",
                primary_type=supplier_types[i % 5],
                phone=f"0111111{i+1:04d}",
                email=f"supplier{i+1}@test.com",
            )
            suppliers.append(supplier)

        # إنشاء خدمات متخصصة
        for supplier in suppliers:
            for j in range(3):
                SpecializedService.objects.create(
                    supplier=supplier,
                    category=supplier.primary_type,
                    name=f"خدمة {j+1} - {supplier.name}",
                    description=f"وصف الخدمة {j+1}",
                    base_price=Decimal(f"{100 + (j * 50)}.00"),
                    setup_cost=Decimal("50.00"),
                    is_active=True,
                )

    def test_bulk_pricing_calculation(self):
        """اختبار حساب التسعير لعدد كبير من الطلبات"""
        import time

        # إنشاء عملاء
        customers = []
        for i in range(10):
            customer = Customer.objects.create(
                name=f"عميل رقم {i+1}", code=f"CUST{i+1:03d}", phone=f"0122222{i+1:04d}"
            )
            customers.append(customer)

        # قياس وقت إنشاء طلبات متعددة
        start_time = time.time()

        orders = []
        for i in range(50):
            order = PricingOrder.objects.create(
                customer=customers[i % 10],
                order_type="digital",
                quantity=1000 + (i * 100),
                description=f"طلب اختبار أداء {i+1}",
                created_by=self.user,
            )
            orders.append(order)

        creation_time = time.time() - start_time

        # قياس وقت حساب التكاليف
        start_time = time.time()

        total_calculations = 0
        for order in orders:
            try:
                total_cost = order.calculate_total_cost()
                if total_cost > 0:
                    total_calculations += 1
            except:
                pass  # تجاهل الأخطاء في اختبار الأداء

        calculation_time = time.time() - start_time

        # التحقق من الأداء
        self.assertLess(creation_time, 5.0, "إنشاء الطلبات يجب أن يكون أقل من 5 ثواني")
        self.assertLess(
            calculation_time, 10.0, "حساب التكاليف يجب أن يكون أقل من 10 ثواني"
        )

        print(f"تم إنشاء {len(orders)} طلب في {creation_time:.2f} ثانية")
        print(f"تم حساب {total_calculations} تكلفة في {calculation_time:.2f} ثانية")


class PricingErrorHandlingTestCase(TestCase):
    """اختبارات معالجة الأخطاء"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="error_user", password="testpass123"
        )

        self.customer = Customer.objects.create(
            name="عميل الاختبار", code="ERR001", phone="01234567890"
        )

    def test_missing_supplier_services(self):
        """اختبار التعامل مع عدم وجود خدمات المورد"""

        # إنشاء مورد بدون خدمات
        supplier = Supplier.objects.create(
            name="مورد بدون خدمات", code="NOSRV001", phone="01111111111"
        )

        order = PricingOrder.objects.create(
            customer=self.customer,
            order_type="digital",
            quantity=1000,
            supplier=supplier,
            created_by=self.user,
        )

        # يجب أن تعيد الحسابات قيم افتراضية أو صفر
        paper_cost = order.calculate_paper_cost()
        printing_cost = order.calculate_printing_cost()

        # التحقق من عدم حدوث خطأ
        self.assertIsNotNone(paper_cost)
        self.assertIsNotNone(printing_cost)

    def test_invalid_pricing_data(self):
        """اختبار التعامل مع بيانات تسعير غير صحيحة"""

        # اختبار كمية صفر أو سالبة
        order = PricingOrder.objects.create(
            customer=self.customer,
            order_type="digital",
            quantity=0,  # كمية صفر
            created_by=self.user,
        )

        total_cost = order.calculate_total_cost()
        self.assertEqual(total_cost, 0)

        # اختبار بيانات مفقودة
        order2 = PricingOrder.objects.create(
            customer=self.customer,
            order_type="digital",
            quantity=1000,
            # بدون paper_type أو paper_size
            created_by=self.user,
        )

        # يجب ألا يحدث خطأ
        total_cost2 = order2.calculate_total_cost()
        self.assertIsNotNone(total_cost2)
