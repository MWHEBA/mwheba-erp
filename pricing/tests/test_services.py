"""
اختبارات شاملة لخدمات نظام التسعير
Comprehensive Tests for Pricing System Services
"""
import pytest
from django.test import TestCase
from decimal import Decimal
from unittest.mock import Mock, patch

from pricing.services.calculator import PricingCalculator
from pricing.services.paper_calculator import PaperCalculator
from pricing.services.print_calculator import PrintCalculator
from pricing.services.finishing_calculator import FinishingCalculator
from pricing.simple_calculation_service import SimplePricingCalculator
from pricing.models import PaperType, PaperSize, PlateSize, CoatingType, FinishingType


class PricingCalculatorTestCase(TestCase):
    """اختبارات حاسبة التسعير الرئيسية"""

    def setUp(self):
        """إعداد البيانات للاختبارات"""
        self.calculator = PricingCalculator()

        # إنشاء البيانات المرجعية
        self.paper_type = PaperType.objects.create(
            name="ورق أبيض", weight=80, price_per_kg=Decimal("15.00")
        )

        self.paper_size = PaperSize.objects.create(name="A4", width=21.0, height=29.7)

        self.plate_size = PlateSize.objects.create(
            name="70x100", width=70.0, height=100.0, price=Decimal("200.00")
        )

    def test_calculate_total_cost(self):
        """اختبار حساب التكلفة الإجمالية"""
        costs = {
            "paper_cost": Decimal("500.00"),
            "printing_cost": Decimal("300.00"),
            "finishing_cost": Decimal("200.00"),
            "plate_cost": Decimal("100.00"),
        }

        total_cost = self.calculator.calculate_total_cost(costs)
        expected_total = Decimal("1100.00")

        self.assertEqual(total_cost, expected_total)

    def test_calculate_profit_margin(self):
        """اختبار حساب هامش الربح"""
        total_cost = Decimal("1000.00")
        profit_percentage = Decimal("20.00")  # 20%

        profit_amount = self.calculator.calculate_profit_margin(
            total_cost, profit_percentage
        )
        expected_profit = Decimal("200.00")

        self.assertEqual(profit_amount, expected_profit)

    def test_calculate_selling_price(self):
        """اختبار حساب سعر البيع"""
        total_cost = Decimal("1000.00")
        profit_margin = Decimal("20.00")

        selling_price = self.calculator.calculate_selling_price(
            total_cost, profit_margin
        )
        expected_price = Decimal("1200.00")

        self.assertEqual(selling_price, expected_price)

    def test_calculate_vat(self):
        """اختبار حساب ضريبة القيمة المضافة"""
        amount = Decimal("1000.00")
        vat_rate = Decimal("14.00")  # 14%

        vat_amount = self.calculator.calculate_vat(amount, vat_rate)
        expected_vat = Decimal("140.00")

        self.assertEqual(vat_amount, expected_vat)


class PaperCalculatorTestCase(TestCase):
    """اختبارات حاسبة تكلفة الورق"""

    def setUp(self):
        """إعداد البيانات للاختبارات"""
        self.calculator = PaperCalculator()

        self.paper_type = PaperType.objects.create(
            name="ورق أبيض", weight=80, price_per_kg=Decimal("15.00")
        )

        self.paper_size = PaperSize.objects.create(name="A4", width=21.0, height=29.7)

    def test_calculate_paper_weight(self):
        """اختبار حساب وزن الورق"""
        # A4 = 21cm x 29.7cm = 623.7 cm²
        # وزن الورق = (المساحة بالمتر المربع) × (وزن الورق بالجرام) × الكمية
        quantity = 1000
        paper_weight_gsm = 80

        weight = self.calculator.calculate_paper_weight(
            width=21.0, height=29.7, quantity=quantity, paper_weight=paper_weight_gsm
        )

        # المساحة = 0.21 × 0.297 = 0.06237 متر مربع
        # الوزن = 0.06237 × 80 × 1000 = 4989.6 جرام = 4.99 كيلو
        expected_weight = Decimal("4.99")
        self.assertAlmostEqual(weight, expected_weight, places=2)

    def test_calculate_paper_cost(self):
        """اختبار حساب تكلفة الورق"""
        paper_weight_kg = Decimal("5.00")
        price_per_kg = Decimal("15.00")

        cost = self.calculator.calculate_paper_cost(paper_weight_kg, price_per_kg)
        expected_cost = Decimal("75.00")

        self.assertEqual(cost, expected_cost)

    def test_calculate_paper_sheets_needed(self):
        """اختبار حساب عدد الأوراق المطلوبة"""
        # حساب عدد الأوراق المطلوبة بناءً على المقاس والكمية
        product_width = 21.0  # A4
        product_height = 29.7
        sheet_width = 70.0  # ورقة كبيرة
        sheet_height = 100.0
        quantity = 1000

        sheets_needed = self.calculator.calculate_sheets_needed(
            product_width, product_height, sheet_width, sheet_height, quantity
        )

        # عدد القطع في الورقة الواحدة = (70/21) × (100/29.7) = 3 × 3 = 9 قطع
        # عدد الأوراق المطلوبة = 1000 / 9 = 112 ورقة (تقريباً)
        expected_sheets = 112
        self.assertAlmostEqual(sheets_needed, expected_sheets, delta=5)


class PrintCalculatorTestCase(TestCase):
    """اختبارات حاسبة تكلفة الطباعة"""

    def setUp(self):
        """إعداد البيانات للاختبارات"""
        self.calculator = PrintCalculator()

    def test_calculate_offset_printing_cost(self):
        """اختبار حساب تكلفة الطباعة الأوفست"""
        sheets = 1000
        colors = 4  # CMYK
        cost_per_sheet_per_color = Decimal("0.05")

        cost = self.calculator.calculate_offset_cost(
            sheets, colors, cost_per_sheet_per_color
        )

        expected_cost = Decimal("200.00")  # 1000 × 4 × 0.05
        self.assertEqual(cost, expected_cost)

    def test_calculate_digital_printing_cost(self):
        """اختبار حساب تكلفة الطباعة الديجيتال"""
        sheets = 500
        cost_per_sheet = Decimal("0.50")

        cost = self.calculator.calculate_digital_cost(sheets, cost_per_sheet)
        expected_cost = Decimal("250.00")  # 500 × 0.50

        self.assertEqual(cost, expected_cost)

    def test_calculate_plate_cost(self):
        """اختبار حساب تكلفة الزنكات"""
        colors = 4
        plate_cost_per_color = Decimal("50.00")

        total_plate_cost = self.calculator.calculate_plate_cost(
            colors, plate_cost_per_color
        )

        expected_cost = Decimal("200.00")  # 4 × 50
        self.assertEqual(total_plate_cost, expected_cost)

    def test_calculate_setup_cost(self):
        """اختبار حساب تكلفة الإعداد"""
        colors = 4
        setup_cost_per_color = Decimal("25.00")

        setup_cost = self.calculator.calculate_setup_cost(colors, setup_cost_per_color)

        expected_cost = Decimal("100.00")  # 4 × 25
        self.assertEqual(setup_cost, expected_cost)


class FinishingCalculatorTestCase(TestCase):
    """اختبارات حاسبة تكلفة التشطيب"""

    def setUp(self):
        """إعداد البيانات للاختبارات"""
        self.calculator = FinishingCalculator()

        self.coating_type = CoatingType.objects.create(
            name="لامينيشن لامع", price_per_sheet=Decimal("0.25")
        )

        self.finishing_type = FinishingType.objects.create(
            name="تجليد حلزوني", price_per_unit=Decimal("2.00")
        )

    def test_calculate_lamination_cost(self):
        """اختبار حساب تكلفة اللامينيشن"""
        sheets = 1000
        price_per_sheet = Decimal("0.25")

        cost = self.calculator.calculate_lamination_cost(sheets, price_per_sheet)
        expected_cost = Decimal("250.00")  # 1000 × 0.25

        self.assertEqual(cost, expected_cost)

    def test_calculate_binding_cost(self):
        """اختبار حساب تكلفة التجليد"""
        units = 1000
        price_per_unit = Decimal("2.00")

        cost = self.calculator.calculate_binding_cost(units, price_per_unit)
        expected_cost = Decimal("2000.00")  # 1000 × 2.00

        self.assertEqual(cost, expected_cost)

    def test_calculate_cutting_cost(self):
        """اختبار حساب تكلفة القص"""
        cuts = 4  # عدد القصات
        cost_per_cut = Decimal("10.00")

        cost = self.calculator.calculate_cutting_cost(cuts, cost_per_cut)
        expected_cost = Decimal("40.00")  # 4 × 10

        self.assertEqual(cost, expected_cost)

    def test_calculate_folding_cost(self):
        """اختبار حساب تكلفة الطي"""
        sheets = 1000
        folds = 2  # عدد الطيات
        cost_per_fold_per_sheet = Decimal("0.02")

        cost = self.calculator.calculate_folding_cost(
            sheets, folds, cost_per_fold_per_sheet
        )

        expected_cost = Decimal("40.00")  # 1000 × 2 × 0.02
        self.assertEqual(cost, expected_cost)


class SimplePricingCalculatorTestCase(TestCase):
    """اختبارات حاسبة التسعير البسيطة"""

    def setUp(self):
        """إعداد البيانات للاختبارات"""
        self.calculator = SimplePricingCalculator()

    def test_calculate_simple_pricing(self):
        """اختبار حساب التسعير البسيط"""
        data = {
            "quantity": 1000,
            "paper_cost_per_unit": Decimal("0.50"),
            "printing_cost_per_unit": Decimal("0.30"),
            "finishing_cost_per_unit": Decimal("0.20"),
            "profit_margin": Decimal("20.00"),
        }

        result = self.calculator.calculate(data)

        # التكلفة الإجمالية = 1000 × (0.50 + 0.30 + 0.20) = 1000
        # الربح = 1000 × 20% = 200
        # السعر النهائي = 1000 + 200 = 1200

        self.assertEqual(result["total_cost"], Decimal("1000.00"))
        self.assertEqual(result["profit_amount"], Decimal("200.00"))
        self.assertEqual(result["selling_price"], Decimal("1200.00"))


class PricingIntegrationTestCase(TestCase):
    """اختبارات التكامل بين خدمات التسعير"""

    def setUp(self):
        """إعداد البيانات للاختبارات"""
        # إنشاء البيانات المرجعية
        self.paper_type = PaperType.objects.create(
            name="ورق أبيض", weight=80, price_per_kg=Decimal("15.00")
        )

        self.paper_size = PaperSize.objects.create(name="A4", width=21.0, height=29.7)

        self.plate_size = PlateSize.objects.create(
            name="70x100", width=70.0, height=100.0, price=Decimal("200.00")
        )

    def test_complete_pricing_calculation(self):
        """اختبار حساب التسعير الكامل"""
        # بيانات الطلب
        order_data = {
            "quantity": 1000,
            "paper_type": self.paper_type,
            "paper_size": self.paper_size,
            "colors": 4,
            "finishing_required": True,
            "profit_margin": Decimal("20.00"),
        }

        # حساب تكلفة الورق
        paper_calculator = PaperCalculator()
        paper_weight = paper_calculator.calculate_paper_weight(
            width=21.0, height=29.7, quantity=1000, paper_weight=80
        )
        paper_cost = paper_calculator.calculate_paper_cost(
            paper_weight, Decimal("15.00")
        )

        # حساب تكلفة الطباعة
        print_calculator = PrintCalculator()
        printing_cost = print_calculator.calculate_offset_cost(
            sheets=1000, colors=4, cost_per_sheet_per_color=Decimal("0.05")
        )

        # حساب تكلفة التشطيب
        finishing_calculator = FinishingCalculator()
        finishing_cost = finishing_calculator.calculate_lamination_cost(
            sheets=1000, price_per_sheet=Decimal("0.25")
        )

        # حساب التكلفة الإجمالية
        main_calculator = PricingCalculator()
        costs = {
            "paper_cost": paper_cost,
            "printing_cost": printing_cost,
            "finishing_cost": finishing_cost,
            "plate_cost": Decimal("200.00"),
        }

        total_cost = main_calculator.calculate_total_cost(costs)
        profit_amount = main_calculator.calculate_profit_margin(
            total_cost, Decimal("20.00")
        )
        selling_price = main_calculator.calculate_selling_price(
            total_cost, Decimal("20.00")
        )

        # التحقق من النتائج
        self.assertGreater(total_cost, Decimal("0"))
        self.assertGreater(profit_amount, Decimal("0"))
        self.assertGreater(selling_price, total_cost)
        self.assertEqual(selling_price, total_cost + profit_amount)


class PricingServiceErrorHandlingTestCase(TestCase):
    """اختبارات معالجة الأخطاء في خدمات التسعير"""

    def test_division_by_zero_handling(self):
        """اختبار معالجة القسمة على صفر"""
        calculator = PricingCalculator()

        with self.assertRaises(ValueError):
            calculator.calculate_profit_margin(Decimal("0"), Decimal("20.00"))

    def test_negative_values_handling(self):
        """اختبار معالجة القيم السالبة"""
        calculator = PaperCalculator()

        with self.assertRaises(ValueError):
            calculator.calculate_paper_cost(Decimal("-5.00"), Decimal("15.00"))

    def test_invalid_data_handling(self):
        """اختبار معالجة البيانات غير الصحيحة"""
        calculator = SimplePricingCalculator()

        invalid_data = {
            "quantity": "invalid",  # نص بدلاً من رقم
            "paper_cost_per_unit": Decimal("0.50"),
        }

        with self.assertRaises((ValueError, TypeError)):
            calculator.calculate(invalid_data)


class PricingServicePerformanceTestCase(TestCase):
    """اختبارات الأداء لخدمات التسعير"""

    def test_large_quantity_calculation(self):
        """اختبار حساب كميات كبيرة"""
        calculator = PricingCalculator()

        # حساب تكلفة كمية كبيرة
        costs = {
            "paper_cost": Decimal("50000.00"),
            "printing_cost": Decimal("30000.00"),
            "finishing_cost": Decimal("20000.00"),
        }

        import time

        start_time = time.time()

        total_cost = calculator.calculate_total_cost(costs)

        end_time = time.time()
        calculation_time = end_time - start_time

        # يجب أن يكون الحساب سريعاً (أقل من ثانية واحدة)
        self.assertLess(calculation_time, 1.0)
        self.assertEqual(total_cost, Decimal("100000.00"))


if __name__ == "__main__":
    pytest.main([__file__])
