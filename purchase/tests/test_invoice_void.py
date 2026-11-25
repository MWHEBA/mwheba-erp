import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied
from django.urls import reverse
from django.utils import timezone

from financial.models import JournalEntry
from financial.services.period_control_service import PeriodControlService
from product.models import Stock
from purchase.models import Purchase, PurchasePayment, PurchaseReturn
from purchase.services.purchase_service import PurchaseService
from purchase.tests.test_purchase_service import (
    user,
    supplier,
    warehouse,
    product,
    chart_of_accounts,
)
from sale.models import Sale, SalePayment
from sale.services.sale_service import SaleService
from sale.tests.test_sale_service import customer, chart_of_accounts as sale_chart_of_accounts

User = get_user_model()


@pytest.mark.django_db
class TestInvoiceVoid:
    """
    اختبارات إلغاء الفواتير المعتمدة (Void) بشروط الحوكمة الصارمة
    """

    def _create_purchase(self, user, supplier, warehouse, product, qty=Decimal("5.00")):
        data = {
            "date": timezone.localdate(),
            "supplier_id": supplier.id,
            "warehouse_id": warehouse.id,
            "payment_method": "credit",
            "discount": Decimal("0"),
            "tax": Decimal("0"),
            "notes": "فاتورة مشتريات للاختبار",
            "items": [
                {
                    "product_id": product.id,
                    "quantity": qty,
                    "unit_price": Decimal("50.00"),
                    "discount": Decimal("0"),
                }
            ],
        }
        return PurchaseService.create_purchase(data=data, user=user)

    def _create_sale(self, user, customer, warehouse, product, qty=Decimal("2.00")):
        data = {
            "date": timezone.localdate(),
            "customer_id": customer.id,
            "warehouse_id": warehouse.id,
            "payment_method": "credit",
            "discount": Decimal("0"),
            "tax": Decimal("0"),
            "notes": "فاتورة مبيعات للاختبار",
            "items": [
                {
                    "product_id": product.id,
                    "quantity": qty,
                    "unit_price": Decimal("100.00"),
                    "discount": Decimal("0"),
                }
            ],
        }
        return SaleService.create_sale(data=data, user=user)

    def test_void_purchase_reverses_journal_stock_and_supplier_balance(
        self, user, supplier, warehouse, product, chart_of_accounts
    ):
        initial_stock = Stock.objects.filter(product=product, warehouse=warehouse).first()
        initial_qty = initial_stock.quantity if initial_stock else Decimal("0.00")
        initial_balance = supplier.balance

        purchase = self._create_purchase(user, supplier, warehouse, product, qty=Decimal("5.00"))
        assert purchase.status == "confirmed"
        assert purchase.journal_entry_id is not None

        stock_after_create = Stock.objects.get(product=product, warehouse=warehouse)
        assert stock_after_create.quantity == initial_qty + Decimal("5.00")

        voided = PurchaseService.void_purchase(purchase, user, reason="إدخال خاطئ للصنف")
        assert voided.status == "cancelled"
        assert "إدخال خاطئ للصنف" in (voided.notes or "")

        # المخزون عاد للوضع السابق
        stock_after_void = Stock.objects.get(product=product, warehouse=warehouse)
        assert stock_after_void.quantity == initial_qty

        # رصيد المورد عاد للوضع السابق
        supplier.refresh_from_db()
        assert supplier.balance == initial_balance

        # القيد المحاسبي تم عكسه بقيد عكسي
        orig_je = JournalEntry.objects.get(pk=purchase.journal_entry_id)
        assert orig_je.reversal_entries.exists()

    def test_void_purchase_blocks_without_permission(
        self, user, supplier, warehouse, product, chart_of_accounts
    ):
        purchase = self._create_purchase(user, supplier, warehouse, product)
        no_perm_user = User.objects.create_user(
            username="noperm_void", email="noperm@test.com", password="pass"
        )
        with pytest.raises(PermissionDenied):
            PurchaseService.void_purchase(purchase, no_perm_user, reason="اختبار صلاحية")

    def test_void_purchase_blocks_without_reason(
        self, user, supplier, warehouse, product, chart_of_accounts
    ):
        purchase = self._create_purchase(user, supplier, warehouse, product)
        with pytest.raises(ValidationError):
            PurchaseService.void_purchase(purchase, user, reason="   ")

    def test_void_purchase_blocks_if_has_posted_payment(
        self, user, supplier, warehouse, product, chart_of_accounts
    ):
        purchase = self._create_purchase(user, supplier, warehouse, product)
        PurchasePayment.objects.create(
            purchase=purchase,
            amount=Decimal("50.00"),
            payment_date=timezone.localdate(),
            status="posted",
            created_by=user,
        )
        with pytest.raises(ValidationError) as exc:
            PurchaseService.void_purchase(purchase, user, reason="محاولة إلغاء")
        assert "دفعات" in str(exc.value)

    def test_void_purchase_blocks_if_stock_consumed(
        self, user, supplier, warehouse, product, chart_of_accounts
    ):
        # إفراغ المخزون الابتدائي لضمان أن المتاح بعد الشراء هو 5 فقط
        Stock.objects.filter(product=product, warehouse=warehouse).update(quantity=Decimal("0.00"))
        purchase = self._create_purchase(user, supplier, warehouse, product, qty=Decimal("5.00"))

        # سحب 2 قطعة من المخزن
        Stock.objects.filter(product=product, warehouse=warehouse).update(quantity=Decimal("3.00"))

        with pytest.raises(ValidationError) as exc:
            PurchaseService.void_purchase(purchase, user, reason="محاولة إلغاء بعد الصرف")
        assert "الكمية المتاحة" in str(exc.value)

    def test_void_purchase_blocks_if_period_closed(
        self, user, supplier, warehouse, product, chart_of_accounts
    ):
        today = timezone.localdate()
        fy = PeriodControlService.create_fiscal_year_with_periods(
            year_code=f"FY-{today.year}",
            name=f"السنة المالية {today.year}",
            start_date=today.replace(month=1, day=1),
            end_date=today.replace(month=12, day=31),
        )
        purchase = self._create_purchase(user, supplier, warehouse, product)
        period = fy.periods.filter(start_date__lte=today, end_date__gte=today).first()
        period.status = "closed"
        period.save(update_fields=["status"])

        with pytest.raises(ValidationError) as exc:
            PurchaseService.void_purchase(purchase, user, reason="فترة مغلقة")
        assert "مغلقة" in str(exc.value)

    def test_void_sale_reverses_journal_stock_and_customer_balance(
        self, user, customer, warehouse, product, sale_chart_of_accounts
    ):
        # تأكيد توفر مخزون كافٍ للبيع
        Stock.objects.update_or_create(
            product=product, warehouse=warehouse, defaults={"quantity": Decimal("20.00")}
        )
        initial_balance = customer.balance

        sale = self._create_sale(user, customer, warehouse, product, qty=Decimal("2.00"))
        assert sale.status == "confirmed"
        assert sale.journal_entry_id is not None

        stock_after_sale = Stock.objects.get(product=product, warehouse=warehouse)
        assert stock_after_sale.quantity == Decimal("18.00")

        voided = SaleService.void_sale(sale, user, reason="خطأ في بيانات العميل")
        assert voided.status == "cancelled"

        stock_after_void = Stock.objects.get(product=product, warehouse=warehouse)
        assert stock_after_void.quantity == Decimal("20.00")

        customer.refresh_from_db()
        assert customer.balance == initial_balance

        orig_je = JournalEntry.objects.get(pk=sale.journal_entry_id)
        assert orig_je.reversal_entries.exists()

    def test_void_purchase_view_post(
        self, client, user, supplier, warehouse, product, chart_of_accounts
    ):
        purchase = self._create_purchase(user, supplier, warehouse, product)
        client.force_login(user)
        url = reverse("purchase:purchase_void", kwargs={"pk": purchase.pk})
        response = client.post(url, {"cancellation_reason": "إلغاء عبر الواجهة"}, follow=True)
        assert response.status_code == 200
        msgs = [str(m) for m in (response.context["messages"] if response.context and "messages" in response.context else [])]
        purchase.refresh_from_db()
        assert purchase.status == "cancelled", f"Messages: {msgs}, Redirects: {response.redirect_chain}"

    def test_void_sale_view_post(
        self, client, user, customer, warehouse, product, sale_chart_of_accounts
    ):
        Stock.objects.update_or_create(
            product=product, warehouse=warehouse, defaults={"quantity": Decimal("20.00")}
        )
        sale = self._create_sale(user, customer, warehouse, product)
        client.force_login(user)
        url = reverse("sale:sale_void", kwargs={"pk": sale.pk})
        response = client.post(url, {"cancellation_reason": "إلغاء عبر الواجهة"}, follow=True)
        assert response.status_code == 200
        sale.refresh_from_db()
        assert sale.status == "cancelled"
