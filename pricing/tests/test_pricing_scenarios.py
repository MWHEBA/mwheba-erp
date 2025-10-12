"""
اختبارات سيناريوهات التسعير المختلفة
Pricing Scenarios Test Cases
"""
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth.models import User
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
    SupplierServiceTag,
    SpecializedService,
    PaperServiceDetails,
    DigitalPrintingDetails,
    PlateServiceDetails,
    ServicePriceTier,
)
from client.models import Customer


class PricingScenarioTestCase(TestCase):
    """اختبارات سيناريوهات التسعير المختلفة"""

    def setUp(self):
        """إعداد البيانات الأساسية"""
        # المستخدم
        self.user = User.objects.create_user(
            username="scenario_user", password="testpass123"
        )

        # العميل
        self.customer = Customer.objects.create(
            name="شركة السيناريوهات",
            code="SCEN001",
            phone="01234567890",
            email="scenarios@test.com",
        )

        # أنواع الموردين
        self.paper_supplier_type = SupplierType.objects.create(
            name="موردي الورق", code="paper", description="موردي الورق والخامات"
        )

        self.printing_supplier_type = SupplierType.objects.create(
            name="موردي الطباعة", code="printing", description="موردي خدمات الطباعة"
        )

        self.finishing_supplier_type = SupplierType.objects.create(
            name="موردي التشطيب", code="finishing", description="موردي خدمات التشطيب"
        )

        # خدمات الموردين
        self.paper_service_tag = SupplierServiceTag.objects.create(
            name="ورق عادي", code="paper_normal", description="خدمات الورق العادي"
        )

        self.printing_service_tag = SupplierServiceTag.objects.create(
            name="طباعة رقمية",
            code="digital_print",
            description="خدمات الطباعة الرقمية",
        )

        # الموردين
        self.paper_supplier = Supplier.objects.create(
            name="مورد الورق المميز",
            code="PAPER001",
            primary_type=self.paper_supplier_type,
            phone="01111111111",
            email="paper@supplier.com",
        )
        self.paper_supplier.service_tags.add(self.paper_service_tag)

        self.printing_supplier = Supplier.objects.create(
            name="مورد الطباعة المتقدم",
            code="PRINT001",
            primary_type=self.printing_supplier_type,
            phone="01222222222",
            email="print@supplier.com",
        )
        self.printing_supplier.service_tags.add(self.printing_service_tag)

        # أنواع الورق والمقاسات
        self.paper_type_normal = PaperType.objects.create(
            name="ورق أبيض عادي",
            code="WHITE_NORMAL",
            description="ورق أبيض عادي للطباعة",
        )

        self.paper_type_glossy = PaperType.objects.create(
            name="ورق لامع", code="GLOSSY", description="ورق لامع للطباعة الفاخرة"
        )

        self.paper_size_a4 = PaperSize.objects.create(
            name="A4", width=210, height=297, unit="mm"
        )

        self.paper_size_a3 = PaperSize.objects.create(
            name="A3", width=297, height=420, unit="mm"
        )

        # خدمات الورق
        self.paper_service_a4_normal = PaperServiceDetails.objects.create(
            supplier=self.paper_supplier,
            paper_type=self.paper_type_normal,
            paper_size=self.paper_size_a4,
            gsm=80,
            price_per_sheet=Decimal("0.50"),
            price_per_kg=Decimal("15.00"),
            is_active=True,
        )

        self.paper_service_a3_glossy = PaperServiceDetails.objects.create(
            supplier=self.paper_supplier,
            paper_type=self.paper_type_glossy,
            paper_size=self.paper_size_a3,
            gsm=150,
            price_per_sheet=Decimal("2.00"),
            price_per_kg=Decimal("25.00"),
            is_active=True,
        )

        # خدمات الطباعة
        self.digital_service_a4_color = DigitalPrintingDetails.objects.create(
            supplier=self.printing_supplier,
            paper_size=self.paper_size_a4,
            color_type="color",
            price_per_copy=Decimal("2.00"),
            minimum_quantity=1,
            is_active=True,
        )

        self.digital_service_a4_bw = DigitalPrintingDetails.objects.create(
            supplier=self.printing_supplier,
            paper_size=self.paper_size_a4,
            color_type="bw",
            price_per_copy=Decimal("0.50"),
            minimum_quantity=1,
            is_active=True,
        )

        # إعدادات الضريبة
        self.vat_setting = VATSetting.objects.create(
            rate=Decimal("15.00"), is_active=True
        )

    def test_scenario_small_business_cards(self):
        """سيناريو: كروت شخصية صغيرة"""

        order = PricingOrder.objects.create(
            customer=self.customer,
            order_type="digital",
            paper_type=self.paper_type_glossy,
            paper_size=self.paper_size_a4,
            quantity=500,  # كمية صغيرة
            description="كروت شخصية لشركة صغيرة",
            supplier=self.printing_supplier,
            created_by=self.user,
        )

        # حساب التكاليف
        paper_cost = order.calculate_paper_cost()
        printing_cost = order.calculate_printing_cost()
        total_cost = order.calculate_total_cost()

        # التحقق من المنطق
        self.assertGreater(paper_cost, 0, "تكلفة الورق يجب أن تكون أكبر من صفر")
        self.assertGreater(printing_cost, 0, "تكلفة الطباعة يجب أن تكون أكبر من صفر")
        self.assertGreater(
            total_cost,
            paper_cost + printing_cost,
            "التكلفة الإجمالية يجب أن تشمل الضريبة",
        )

        # اختبار اختيار المورد
        selection = PricingSupplierSelection.objects.create(
            order=order,
            supplier=self.printing_supplier,
            service_tag=self.printing_service_tag,
            quoted_price=total_cost,
            estimated_cost=total_cost * Decimal("0.9"),
            status="quoted",
            priority="medium",
            created_by=self.user,
        )

        self.assertEqual(selection.status, "quoted")
        self.assertFalse(selection.is_overdue())

        return order

    def test_scenario_large_catalog_printing(self):
        """سيناريو: طباعة كتالوج كبير"""

        order = PricingOrder.objects.create(
            customer=self.customer,
            order_type="offset",  # طباعة أوفست للكميات الكبيرة
            paper_type=self.paper_type_glossy,
            paper_size=self.paper_size_a3,
            quantity=10000,  # كمية كبيرة
            description="كتالوج منتجات للشركة",
            supplier=self.printing_supplier,
            created_by=self.user,
        )

        # حساب التكاليف للكمية الكبيرة
        paper_cost = order.calculate_paper_cost()
        printing_cost = order.calculate_printing_cost()
        total_cost = order.calculate_total_cost()

        # في الكميات الكبيرة، تكلفة الورق تكون أكبر نسبياً
        self.assertGreater(
            paper_cost,
            printing_cost * 0.3,
            "تكلفة الورق يجب أن تكون نسبة معقولة من تكلفة الطباعة",
        )

        # اختبار خصومات الكمية (إذا كانت متوفرة)
        unit_cost = total_cost / order.quantity
        self.assertLess(
            unit_cost, Decimal("5.00"), "تكلفة الوحدة يجب أن تقل في الكميات الكبيرة"
        )

        return order

    def test_scenario_multi_supplier_comparison(self):
        """سيناريو: مقارنة عدة موردين"""

        # إنشاء موردين إضافيين
        supplier2 = Supplier.objects.create(
            name="مورد الطباعة الثاني",
            code="PRINT002",
            primary_type=self.printing_supplier_type,
            phone="01333333333",
            email="print2@supplier.com",
        )

        supplier3 = Supplier.objects.create(
            name="مورد الطباعة الثالث",
            code="PRINT003",
            primary_type=self.printing_supplier_type,
            phone="01444444444",
            email="print3@supplier.com",
        )

        # إنشاء طلب تسعير
        order = PricingOrder.objects.create(
            customer=self.customer,
            order_type="digital",
            paper_type=self.paper_type_normal,
            paper_size=self.paper_size_a4,
            quantity=2000,
            description="مقارنة موردين متعددين",
            created_by=self.user,
        )

        # إضافة عروض من موردين مختلفين
        suppliers_quotes = [
            (self.printing_supplier, Decimal("3000.00")),
            (supplier2, Decimal("2800.00")),  # أرخص
            (supplier3, Decimal("3200.00")),  # أغلى
        ]

        selections = []
        for supplier, quote in suppliers_quotes:
            selection = PricingSupplierSelection.objects.create(
                order=order,
                supplier=supplier,
                service_tag=self.printing_service_tag,
                quoted_price=quote,
                estimated_cost=Decimal("2500.00"),
                status="quoted",
                created_by=self.user,
            )
            selections.append(selection)

        # اختيار أفضل عرض (الأقل سعراً)
        best_selection = min(selections, key=lambda x: x.quoted_price)
        best_selection.is_selected = True
        best_selection.selection_reason = "أفضل سعر مع جودة مناسبة"
        best_selection.save()

        # التحقق من الاختيار
        self.assertTrue(best_selection.is_selected)
        self.assertEqual(best_selection.supplier, supplier2)
        self.assertEqual(best_selection.status, "selected")

        # التحقق من حساب الفروقات
        for selection in selections:
            difference = selection.get_price_difference()
            percentage = selection.get_price_difference_percentage()

            self.assertIsNotNone(difference)
            self.assertIsNotNone(percentage)

            if selection.quoted_price > selection.estimated_cost:
                self.assertGreater(difference, 0)
                self.assertGreater(percentage, 0)

        return order, selections

    def test_scenario_rush_order(self):
        """سيناريو: طلب عاجل"""

        order = PricingOrder.objects.create(
            customer=self.customer,
            order_type="digital",
            paper_type=self.paper_type_normal,
            paper_size=self.paper_size_a4,
            quantity=1000,
            description="طلب عاجل - مطلوب خلال 24 ساعة",
            created_by=self.user,
        )

        # إضافة اختيار مورد مع أولوية عاجلة
        selection = PricingSupplierSelection.objects.create(
            order=order,
            supplier=self.printing_supplier,
            service_tag=self.printing_service_tag,
            quoted_price=Decimal("2500.00"),
            estimated_cost=Decimal("2000.00"),
            status="quoted",
            priority="urgent",  # أولوية عاجلة
            expected_delivery=timezone.now().date() + timezone.timedelta(days=1),
            contact_person="أحمد محمد",
            contact_phone="01555555555",
            notes="طلب عاجل - يحتاج متابعة مستمرة",
            created_by=self.user,
        )

        # التحقق من الأولوية
        self.assertEqual(selection.priority, "urgent")
        self.assertIsNotNone(selection.expected_delivery)
        self.assertFalse(selection.is_overdue())  # لم يتأخر بعد

        # محاكاة تأخير التسليم
        selection.expected_delivery = timezone.now().date() - timezone.timedelta(days=1)
        selection.save()

        self.assertTrue(selection.is_overdue())  # أصبح متأخراً

        return order, selection

    def test_scenario_complex_finishing_services(self):
        """سيناريو: خدمات تشطيب معقدة"""

        # إنشاء مورد تشطيب
        finishing_supplier = Supplier.objects.create(
            name="مورد التشطيب المتخصص",
            code="FINISH001",
            primary_type=self.finishing_supplier_type,
            phone="01666666666",
            email="finishing@supplier.com",
        )

        # إنشاء خدمات تشطيب متخصصة
        coating_service = SpecializedService.objects.create(
            supplier=finishing_supplier,
            category=self.finishing_supplier_type,
            name="تغطية لامع",
            description="تغطية لامع عالي الجودة",
            base_price=Decimal("1.50"),
            setup_cost=Decimal("100.00"),
            min_quantity=500,
            is_active=True,
        )

        # إنشاء شرائح سعرية
        ServicePriceTier.objects.create(
            service=coating_service,
            min_quantity=500,
            max_quantity=1000,
            unit_price=Decimal("1.50"),
            discount_percentage=Decimal("0.00"),
        )

        ServicePriceTier.objects.create(
            service=coating_service,
            min_quantity=1001,
            max_quantity=5000,
            unit_price=Decimal("1.30"),
            discount_percentage=Decimal("13.33"),
        )

        # إنشاء طلب مع خدمات تشطيب
        order = PricingOrder.objects.create(
            customer=self.customer,
            order_type="digital",
            paper_type=self.paper_type_glossy,
            paper_size=self.paper_size_a4,
            quantity=2000,
            description="طلب مع خدمات تشطيب معقدة",
            supplier=self.printing_supplier,
            created_by=self.user,
        )

        # إضافة اختيار مورد التشطيب
        finishing_selection = PricingSupplierSelection.objects.create(
            order=order,
            supplier=finishing_supplier,
            service_tag=self.paper_service_tag,  # مؤقت
            quoted_price=Decimal("2700.00"),  # 2000 × 1.30 + 100 setup
            estimated_cost=Decimal("3000.00"),
            status="quoted",
            selection_reason="متخصص في التشطيب عالي الجودة",
            created_by=self.user,
        )

        # التحقق من الخصم للكمية الكبيرة
        applicable_tier = coating_service.get_applicable_tier(2000)
        self.assertIsNotNone(applicable_tier)
        self.assertEqual(applicable_tier.unit_price, Decimal("1.30"))
        self.assertGreater(applicable_tier.discount_percentage, 0)

        # التحقق من السعر النهائي
        final_price = coating_service.get_price_for_quantity(2000)
        expected_price = Decimal("1.30")  # السعر مع الخصم
        self.assertEqual(final_price, expected_price)

        return order, finishing_selection

    def test_scenario_budget_constraints(self):
        """سيناريو: قيود الميزانية"""

        # طلب مع ميزانية محدودة
        order = PricingOrder.objects.create(
            customer=self.customer,
            order_type="digital",
            paper_type=self.paper_type_normal,  # ورق أرخص
            paper_size=self.paper_size_a4,
            quantity=1000,
            description="طلب مع ميزانية محدودة - أقل من 2000 ريال",
            supplier=self.printing_supplier,
            created_by=self.user,
        )

        # حساب التكلفة الأساسية
        total_cost = order.calculate_total_cost()
        budget_limit = Decimal("2000.00")

        # إذا كانت التكلفة تتجاوز الميزانية، نبحث عن بدائل
        if total_cost > budget_limit:
            # اقتراح بدائل: تقليل الكمية أو تغيير نوع الورق

            # البديل الأول: تقليل الكمية
            reduced_quantity = int((budget_limit / total_cost) * order.quantity)

            order_reduced = PricingOrder.objects.create(
                customer=self.customer,
                order_type="digital",
                paper_type=self.paper_type_normal,
                paper_size=self.paper_size_a4,
                quantity=reduced_quantity,
                description=f"طلب معدل - كمية مقللة إلى {reduced_quantity}",
                supplier=self.printing_supplier,
                created_by=self.user,
            )

            reduced_cost = order_reduced.calculate_total_cost()
            self.assertLessEqual(reduced_cost, budget_limit)

        # إضافة ملاحظة عن قيود الميزانية
        selection = PricingSupplierSelection.objects.create(
            order=order,
            supplier=self.printing_supplier,
            service_tag=self.printing_service_tag,
            quoted_price=total_cost,
            estimated_cost=total_cost,
            status="pending",
            notes=f"الميزانية المحددة: {budget_limit} ريال",
            created_by=self.user,
        )

        if total_cost > budget_limit:
            selection.status = "rejected"
            selection.selection_reason = "تجاوز الميزانية المحددة"
            selection.save()

        return order, selection
