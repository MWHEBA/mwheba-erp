# -*- coding: utf-8 -*-
import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command

from customer.models import Customer, CustomerCreditProfile
from financial.models import Currency, ChartOfAccounts
from product.models.product_core import Product, Unit, Category
from product.models.stock_management import Warehouse
from sale.models import (
    Sale,
    SalePayment,
    DeliveryNote,
    SalesOrder,
    InstallmentPlan,
    InstallmentItem,
)
from sale.services.installment_engine import InstallmentEngine
from sale.services.delivery_block_service import DeliveryBlockService
from sale.services.driver_authorization_service import DriverAuthorizationService
from sale.services.raw_material_escalation_service import RawMaterialEscalationService
from sale.services.pricing_validator import PricingSecurityValidator

User = get_user_model()


@pytest.mark.django_db
class TestInstallmentsEngineAndServices:

    @pytest.fixture
    def setup_data(self):
        user = User.objects.create_user(username="test_fin_user", password="password123")
        currency, _ = Currency.objects.get_or_create(
            code="EGP", defaults={"name": "Egyptian Pound", "symbol": "ج.م", "is_functional": True}
        )
        customer = Customer.objects.create(
            name="شركة الأهرام للتغليف المضلع",
            code="CUST-7701",
            credit_limit=Decimal("100000.00"),
            installment_credit_limit=Decimal("300000.00"),
            default_currency=currency,
        )
        credit_profile, _ = CustomerCreditProfile.objects.get_or_create(
            customer=customer,
            defaults={
                "credit_limit": Decimal("100000.00"),
                "installment_credit_limit": Decimal("300000.00"),
                "grace_period_days": 5,
            },
        )
        wh, _ = Warehouse.objects.get_or_create(name="مخزن الكرتون التام", defaults={"code": "WH-CARTON-1"})
        unit, _ = Unit.objects.get_or_create(name="قطعة", defaults={"symbol": "قطعة"})
        cat, _ = Category.objects.get_or_create(name="كرتون مضلع", defaults={"code": "CAT-CARTON"})
        prod = Product.objects.create(name="كرتونة مضلعة 5 طبقات C-Flute", unit=unit, category=cat, sku="SKU-CART-01", cost_price=Decimal("10.00"), selling_price=Decimal("15.00"), created_by=user)

        return {
            "user": user,
            "currency": currency,
            "customer": customer,
            "credit_profile": credit_profile,
            "warehouse": wh,
            "product": prod,
        }

    def test_penny_rounding_precision_3_and_7_installments(self, setup_data):
        """
        اختبار ضبط كسور الجنيه بالمليم (Penny Rounding Precision):
        التحقق من أن مجموع أقساط خطة 100,000 مقسمة على 3 أو 7 أشهر يطابق الإجمالي بالمليم
        مع تحميل فرق الكسور على القسط الأول لضمان توازن الأستاذ العام
        """
        customer = setup_data["customer"]
        user = setup_data["user"]
        currency = setup_data["currency"]

        sale = Sale.objects.create(
            number="INV-2026-8801",
            customer=customer,
            created_by=user,
            currency=currency,
            date=timezone.now().date(),
            subtotal=Decimal("100000.00"),
            total=Decimal("100000.00"),
        )

        # 1. اختبار التقسيم على 3 أقساط
        res3 = InstallmentEngine.calculate_installment_schedule(
            sale=sale,
            number_of_installments=3,
            markup_rate=Decimal("10.000"),  # 10,000 فايدة -> الإجمالي 110,000
            start_date=date(2026, 11, 1),
        )
        assert res3["contract_total"] == Decimal("110000.00")
        sum3_principal = sum(it["principal_amount"] for it in res3["items"])
        sum3_interest = sum(it["interest_amount"] for it in res3["items"])
        sum3_total = sum(it["total_amount"] for it in res3["items"])

        assert sum3_principal == Decimal("100000.00")
        assert sum3_interest == Decimal("10000.00")
        assert sum3_total == Decimal("110000.00")

        # 2. اختبار التقسيم على 7 أقساط (كسور لا نهائية)
        res7 = InstallmentEngine.calculate_installment_schedule(
            sale=sale,
            number_of_installments=7,
            markup_rate=Decimal("7.500"),  # 7,500 فايدة -> الإجمالي 107,500
            start_date=date(2026, 11, 1),
        )
        assert res7["contract_total"] == Decimal("107500.00")
        sum7_principal = sum(it["principal_amount"] for it in res7["items"])
        sum7_interest = sum(it["interest_amount"] for it in res7["items"])
        sum7_total = sum(it["total_amount"] for it in res7["items"])

        assert sum7_principal == Decimal("100000.00")
        assert sum7_interest == Decimal("7500.00")
        assert sum7_total == Decimal("107500.00")

    def test_down_payment_deduction_before_markup_and_so_advance(self, setup_data, monkeypatch):
        """
        التحقق من أن الفائدة تحسب فقط على المتبقي بعد خصم المقدم وعربون أمر البيع السابق
        وميكنة سند الدفعة المقدمة SalePayment فوراً
        """
        customer = setup_data["customer"]
        user = setup_data["user"]
        currency = setup_data["currency"]
        wh = setup_data["warehouse"]

        so = SalesOrder.objects.create(
            order_number="SO-2026-8802",
            order_date=timezone.now().date(),
            customer=customer,
            warehouse=wh,
            total_amount=Decimal("100000.00"),
            created_by=user,
        )
        monkeypatch.setattr(SalesOrder, "paid_down_payment", property(lambda self: Decimal("20000.00")))

        sale = Sale.objects.create(
            number="INV-2026-8802",
            customer=customer,
            sales_order=so,
            created_by=user,
            currency=currency,
            date=timezone.now().date(),
            subtotal=Decimal("100000.00"),
            total=Decimal("100000.00"),
        )

        plan = InstallmentEngine.generate_installment_plan(
            sale=sale,
            user=user,
            number_of_installments=2,
            markup_rate=Decimal("10.000"),
            fresh_down_payment=Decimal("10000.00"),  # دفعة مقدمة جديدة
        )

        # إجمالي المقدم المجمع = 10,000 كاش جديد + 20,000 عربون = 30,000
        # وعاء الفائدة = 100,000 - 30,000 = 70,000
        # الفائدة = 70,000 * 10% = 7,000
        # أصل الدين المجدول = 70,000
        # إجمالي العقد = 107,000
        assert plan.down_payment == Decimal("30000.00")
        assert plan.total_markup == Decimal("7000.00")
        assert plan.total_principal == Decimal("70000.00")
        assert plan.total_amount == Decimal("107000.00")

        # التحقق من ميكنة سند الدفعة المقدمة الكاش
        dp_payment = SalePayment.objects.filter(sale=sale, reference_number__startswith="DP-").first()
        assert dp_payment is not None
        assert dp_payment.amount == Decimal("10000.00")
        assert "[INSTALLMENT_DOWN_PAYMENT]" in dp_payment.notes

    def test_pro_rata_underpayment_and_forward_spillover(self, setup_data):
        """
        اختبار السداد النسبي Pro-Rata وشلال الفائض الأمامي إلى القسط التالي،
        وفي القسط الأخير يوجه الفائض تلقائياً كرصيد دائن مسبق للعميل (PREPAID_BALANCE)
        """
        customer = setup_data["customer"]
        user = setup_data["user"]
        currency = setup_data["currency"]

        sale = Sale.objects.create(
            number="INV-2026-8803", customer=customer, created_by=user,
            currency=currency, date=timezone.now().date(),
            subtotal=Decimal("20000.00"), total=Decimal("20000.00"),
        )
        plan = InstallmentEngine.generate_installment_plan(
            sale=sale, user=user, number_of_installments=2,
            markup_rate=Decimal("10.000"), fresh_down_payment=Decimal("0.00"),
        )
        item1 = plan.items.get(installment_number=1)
        item2 = plan.items.get(installment_number=2)

        # 1. سداد جزئي لقسط 1 (11,000): سداد 5,500 بنسبة وتناسب
        InstallmentEngine.record_installment_payment(
            installment_item=item1,
            amount=Decimal("5500.00"),
            payment_date=timezone.now().date(),
            user=user,
        )
        item1.refresh_from_db()
        assert item1.paid_amount == Decimal("5500.00")
        assert item1.paid_principal == Decimal("5000.00")
        assert item1.paid_interest == Decimal("500.00")
        assert item1.remaining_balance == Decimal("5500.00")
        assert item1.cash_status == InstallmentItem.CashStatus.PARTIALLY_PAID

        # 2. سداد بفائض: سداد 8,500 على القسط الأول (المتبقي عليه 5,500)
        # يجب أن يغلق القسط 1 تماماً (5,500)، ويفيض 3,000 إلى القسط الثاني تلقائياً
        InstallmentEngine.record_installment_payment(
            installment_item=item1,
            amount=Decimal("8500.00"),
            payment_date=timezone.now().date(),
            user=user,
        )
        item1.refresh_from_db()
        item2.refresh_from_db()

        assert item1.remaining_balance == Decimal("0.00")
        assert item1.cash_status == InstallmentItem.CashStatus.COLLECTED

        # القسط الثاني استقبل الفائض (3,000)
        assert item2.paid_amount == Decimal("3000.00")
        assert item2.cash_status == InstallmentItem.CashStatus.PARTIALLY_PAID

        # 3. سداد بفائض على القسط الأخير (القسط 2): المتبقي 8,000، وسدد 10,000
        # الفائض 2,000 يجب أن يوجه لرصيد العميل المسبق وتغلق الخطة بـ COMPLETED
        initial_balance = customer.balance
        InstallmentEngine.record_installment_payment(
            installment_item=item2,
            amount=Decimal("10000.00"),
            payment_date=timezone.now().date(),
            user=user,
        )
        item2.refresh_from_db()
        plan.refresh_from_db()
        customer.refresh_from_db()

        assert item2.remaining_balance == Decimal("0.00")
        assert item2.cash_status == InstallmentItem.CashStatus.COLLECTED
        assert plan.status == InstallmentPlan.PlanStatus.COMPLETED
        assert plan.sale.payment_status == 'paid'
        # رصيد العميل انخفض بالفائض (2,000)
        assert customer.balance == initial_balance - Decimal("2000.00")

    def test_article_232_penalty_calculation_on_principal_only(self, setup_data):
        """
        التحقق من احتساب غرامة التأخير اليومية على أصل الدين غير المسدد فقط (المادة 232 مدني مصري):
        استبعاد الفوائد، وسقف الغرامة، وتوقفها عند HOLD_REWORK
        """
        customer = setup_data["customer"]
        user = setup_data["user"]
        currency = setup_data["currency"]

        sale = Sale.objects.create(
            number="INV-2026-8804", customer=customer, created_by=user,
            currency=currency, date=timezone.now().date(),
            subtotal=Decimal("10000.00"), total=Decimal("10000.00"),
        )
        plan = InstallmentPlan.objects.create(
            sale=sale, customer=customer, total_principal=Decimal("10000.00"),
            total_amount=Decimal("11000.00"), number_of_installments=1,
            start_date=timezone.now().date(), created_by=user,
        )
        item = InstallmentItem.objects.create(
            plan=plan, installment_number=1,
            due_date=date(2026, 10, 1),
            principal_amount=Decimal("10000.00"),
            interest_amount=Decimal("1000.00"),
            total_amount=Decimal("11000.00"),
            grace_period_days=5,
        )

        # بعد انتهاء فترة السماح بـ 30 يوماً
        check_date = date(2026, 11, 5)  # 10/1 + 5 سماح = 10/6 -> التأخير 30 يوماً
        penalty = InstallmentEngine.calculate_article_232_penalty(
            item, current_date=check_date, annual_rate_percent=Decimal("12.00")
        )
        # 10,000 * (12% / 365) * 30 = 98.63
        assert penalty == Decimal("98.63")

        # تعليق القسط لعيب تشغيل (HOLD_REWORK): يجب أن تتوقف الغرامة تماماً (0)
        item.cash_status = InstallmentItem.CashStatus.HOLD_REWORK
        item.save()
        penalty_rework = InstallmentEngine.calculate_article_232_penalty(item, current_date=check_date)
        assert penalty_rework == Decimal("0.00")

    def test_banking_calendar_weekend_shift(self, setup_data):
        """
        التحقق من ترحيل الاستحقاق في الجمعة والسبت إلى الأحد تلقائياً
        """
        friday = date(2026, 11, 6)   # الجمعة
        saturday = date(2026, 11, 7) # السبت
        sunday = date(2026, 11, 8)   # الأحد

        assert InstallmentEngine.adjust_for_banking_calendar(friday) == sunday
        assert InstallmentEngine.adjust_for_banking_calendar(saturday) == sunday
        assert InstallmentEngine.adjust_for_banking_calendar(sunday) == sunday

    def test_delivery_block_on_overdue_and_cfo_override(self, setup_data):
        """
        اختبار حظر الصرف المخزني للتعثر وفك الحظر باستثناء معتمد من المدير المالي
        """
        customer = setup_data["customer"]
        user = setup_data["user"]
        wh = setup_data["warehouse"]

        so = SalesOrder.objects.create(
            order_number="SO-2026-8805", order_date=timezone.now().date(),
            customer=customer, warehouse=wh, total_amount=Decimal("50000.00"),
            created_by=user,
        )
        dn = DeliveryNote.objects.create(
            delivery_number="DN-2026-8805", sales_order=so,
            customer=customer, warehouse=wh, delivery_date=timezone.now().date(),
            created_by=user,
        )

        # في البداية: مسموح
        allowed, reason = DeliveryBlockService.check_delivery_allowed(dn, user)
        assert allowed is True

        # إنشاء قسط متأخر للعميل
        sale = Sale.objects.create(
            number="INV-2026-8805", customer=customer, created_by=user,
            date=timezone.now().date(), subtotal=Decimal("10000.00"), total=Decimal("10000.00"),
        )
        plan = InstallmentPlan.objects.create(
            sale=sale, customer=customer, total_principal=Decimal("10000.00"),
            total_amount=Decimal("10000.00"), number_of_installments=1,
            start_date=timezone.now().date(), created_by=user,
        )
        InstallmentItem.objects.create(
            plan=plan, installment_number=1, due_date=date(2026, 9, 1),
            principal_amount=Decimal("10000.00"), total_amount=Decimal("10000.00"),
            cash_status=InstallmentItem.CashStatus.OVERDUE,
        )

        # الآن: محظور آلياً
        allowed2, reason2 = DeliveryBlockService.check_delivery_allowed(dn, user)
        assert allowed2 is False
        assert "محظور من استلام بضاعة جديدة" in reason2

        # فك الحظر باستثناء المدير المالي
        user.is_superuser = True
        allowed_override, _ = DeliveryBlockService.check_delivery_allowed(dn, user, cfo_override=True)
        assert allowed_override is True

    def test_clearing_float_dispatch_lock(self, setup_data):
        """
        اختبار قفل صرف البضاعة أثناء فترة مقاصة الشيك بالبنك (BANK_DEPOSITED)
        """
        customer = setup_data["customer"]
        user = setup_data["user"]
        wh = setup_data["warehouse"]

        so = SalesOrder.objects.create(
            order_number="SO-2026-8806", order_date=timezone.now().date(),
            customer=customer, warehouse=wh, total_amount=Decimal("30000.00"),
            created_by=user,
        )
        dn = DeliveryNote.objects.create(
            delivery_number="DN-2026-8806", sales_order=so,
            customer=customer, warehouse=wh, delivery_date=timezone.now().date(),
            created_by=user,
        )
        sale = Sale.objects.create(
            number="INV-2026-8806", customer=customer, created_by=user,
            date=timezone.now().date(), subtotal=Decimal("30000.00"), total=Decimal("30000.00"),
        )
        plan = InstallmentPlan.objects.create(
            sale=sale, customer=customer, total_principal=Decimal("30000.00"),
            total_amount=Decimal("30000.00"), number_of_installments=1,
            start_date=timezone.now().date(), created_by=user,
        )
        item = InstallmentItem.objects.create(
            plan=plan, installment_number=1, due_date=timezone.now().date(),
            principal_amount=Decimal("30000.00"), total_amount=Decimal("30000.00"),
            paper_coverage=InstallmentItem.PaperCoverage.BANK_DEPOSITED,
            cash_status=InstallmentItem.CashStatus.PENDING,
            linked_delivery_note=dn,
        )

        allowed, reason = DeliveryBlockService.check_delivery_allowed(dn, user)
        assert allowed is False
        assert "مغطى بشيك تحت المقاصة البنكية" in reason

    def test_driver_authorization_validation_and_pilot_run(self, setup_data):
        """
        اختبار التحقق من تفويض السائق وسند البوابة، وتمرير تشغيلة العينات التجريبية is_pilot_run
        """
        customer = setup_data["customer"]
        user = setup_data["user"]
        wh = setup_data["warehouse"]

        so = SalesOrder.objects.create(
            order_number="SO-2026-8807", order_date=timezone.now().date(),
            customer=customer, warehouse=wh, total_amount=Decimal("10000.00"),
            created_by=user,
        )
        dn = DeliveryNote.objects.create(
            delivery_number="DN-2026-8807", sales_order=so,
            customer=customer, warehouse=wh, delivery_date=timezone.now().date(),
            created_by=user,
        )

        # بدون بيانات سائق: يجب أن يطلق خطأ
        with pytest.raises(ValidationError):
            DriverAuthorizationService.validate_driver_authorization(dn, is_strict=True)

        # تشغيلة عينات تجريبية (Pilot Run): معفاة ومسموح خروجها
        dn.is_pilot_run = True
        assert DriverAuthorizationService.validate_driver_authorization(dn, is_strict=True) is True

    def test_raw_material_price_escalation_future_tranches_only(self, setup_data):
        """
        اختبار تعديل أسعار الخامات التضخمي على الأقساط المستقبلية المتبقية فقط
        """
        customer = setup_data["customer"]
        user = setup_data["user"]
        currency = setup_data["currency"]

        sale = Sale.objects.create(
            number="INV-2026-8808", customer=customer, created_by=user,
            currency=currency, date=timezone.now().date(),
            subtotal=Decimal("30000.00"), total=Decimal("30000.00"),
        )
        plan = InstallmentPlan.objects.create(
            sale=sale, customer=customer, total_principal=Decimal("30000.00"),
            markup_rate=Decimal("10.000"), total_markup=Decimal("3000.00"),
            total_amount=Decimal("33000.00"), number_of_installments=3,
            start_date=timezone.now().date(), status=InstallmentPlan.PlanStatus.ACTIVE,
            created_by=user,
        )
        item1 = InstallmentItem.objects.create(
            plan=plan, installment_number=1, due_date=timezone.now().date(),
            principal_amount=Decimal("10000.00"), interest_amount=Decimal("1000.00"),
            total_amount=Decimal("11000.00"), cash_status=InstallmentItem.CashStatus.COLLECTED,
            paid_amount=Decimal("11000.00"), paid_principal=Decimal("10000.00"),
        )
        item2 = InstallmentItem.objects.create(
            plan=plan, installment_number=2, due_date=timezone.now().date() + timedelta(days=30),
            principal_amount=Decimal("10000.00"), interest_amount=Decimal("1000.00"),
            total_amount=Decimal("11000.00"), cash_status=InstallmentItem.CashStatus.PENDING,
        )
        item3 = InstallmentItem.objects.create(
            plan=plan, installment_number=3, due_date=timezone.now().date() + timedelta(days=60),
            principal_amount=Decimal("10000.00"), interest_amount=Decimal("1000.00"),
            total_amount=Decimal("11000.00"), cash_status=InstallmentItem.CashStatus.PENDING,
        )

        # تطبيق زيادة تضخمية 10%
        result = RawMaterialEscalationService.apply_raw_material_escalation(
            plan=plan,
            escalation_percentage=Decimal("10.00"),
            reason="ارتفاع أسعار بكر الورق المستورد عالمياً",
            user=user,
        )

        item1.refresh_from_db()
        item2.refresh_from_db()
        item3.refresh_from_db()
        plan.refresh_from_db()

        # القسط المسدد (1) يظل ثابتاً تماماً دون مساس
        assert item1.principal_amount == Decimal("10000.00")
        assert item1.total_amount == Decimal("11000.00")

        # القسطان 2 و 3 زاد أصلهما 10% (10,000 -> 11,000) وفائدتهما التناسبية 10% (1,000 -> 1,100)
        assert item2.principal_amount == Decimal("11000.00")
        assert item2.interest_amount == Decimal("1100.00")
        assert item2.total_amount == Decimal("12100.00")

        assert item3.principal_amount == Decimal("11000.00")
        assert item3.total_amount == Decimal("12100.00")

        assert plan.is_escalation_adjusted is True
        assert result["total_principal_increase"] == Decimal("2000.00")

    def test_pricing_validator_vat_liquidity_guard_and_tooling_policy(self, setup_data):
        """
        اختبار درع حماية سيولة ضريبة القيمة المضافة وحظر تقسيط الاسطمبات في PricingSecurityValidator
        """
        customer = setup_data["customer"]
        user = setup_data["user"]
        currency = setup_data["currency"]
        cat, _ = Category.objects.get_or_create(name="اسطمبات وتجهيزات", defaults={"code": "CAT-TOOLING"})
        unit, _ = Unit.objects.get_or_create(name="قطعة", defaults={"symbol": "قطعة"})
        tooling_prod = Product.objects.create(name="اسطمبة تكسير علب كرتون 4 درج", unit=unit, category=cat, sku="SKU-TOOL-01", cost_price=Decimal("5000.00"), selling_price=Decimal("6000.00"), created_by=user)

        sale = Sale.objects.create(
            number="INV-2026-8809", customer=customer, created_by=user,
            currency=currency, date=timezone.now().date(),
            subtotal=Decimal("50000.00"), tax=Decimal("7000.00"), total=Decimal("57000.00"),
        )

        items_data = [
            {"product_id": tooling_prod.id, "quantity": 1, "unit_price": Decimal("5000.00")},
        ]

        # 1. إذا كانت الدفعة المقدمة أقل من قيمة الاسطمبة (5,000) يجب أن ترفض
        with pytest.raises(ValidationError) as exc1:
            PricingSecurityValidator.validate_installment_sale_rules(
                sale=sale,
                down_payment=Decimal("3000.00"),
                items_data=items_data,
            )
        assert "تحظر تقسيط تكاليف الاسطمبات" in str(exc1.value)

        # 2. درع حماية سيولة الـ VAT: ضريبة الـ VAT = 7,000؛ إذا كانت تغطية أول 30 يوماً = 5,000 ترفض
        items_schedule = [
            {"installment_number": 1, "due_date": timezone.now().date() + timedelta(days=60), "total_amount": Decimal("10000.00")},
        ]
        with pytest.raises(ValidationError) as exc2:
            PricingSecurityValidator.validate_installment_sale_rules(
                sale=sale,
                down_payment=Decimal("5000.00"),
                items_schedule=items_schedule,
                items_data=items_data,
            )
        assert "درع حماية السيولة الضريبية" in str(exc2.value)

    def test_evaluate_installment_dues_command(self, setup_data):
        """
        اختبار تشغيل أمر الإدارة اليومي وتحويل الأقساط المنتهية فترات سماحها إلى OVERDUE وتحديث الغرامات
        """
        customer = setup_data["customer"]
        user = setup_data["user"]
        currency = setup_data["currency"]

        sale = Sale.objects.create(
            number="INV-2026-8810", customer=customer, created_by=user,
            currency=currency, date=timezone.now().date(),
            subtotal=Decimal("20000.00"), total=Decimal("20000.00"),
        )
        plan = InstallmentPlan.objects.create(
            sale=sale, customer=customer, total_principal=Decimal("20000.00"),
            total_amount=Decimal("20000.00"), number_of_installments=1,
            start_date=timezone.now().date(), created_by=user,
        )
        item = InstallmentItem.objects.create(
            plan=plan, installment_number=1,
            due_date=timezone.now().date() - timedelta(days=20),
            principal_amount=Decimal("20000.00"), total_amount=Decimal("20000.00"),
            grace_period_days=3, cash_status=InstallmentItem.CashStatus.PENDING,
        )

        call_command("evaluate_installment_dues")

        item.refresh_from_db()
        sale.refresh_from_db()

        assert item.cash_status == InstallmentItem.CashStatus.OVERDUE
        assert item.penalty_amount > Decimal("0.00")
        assert sale.delivery_blocked_on_overdue is True
