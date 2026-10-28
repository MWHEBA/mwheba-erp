import pytest
from decimal import Decimal
from django.utils import timezone
from django.core.exceptions import ValidationError, PermissionDenied
from django.urls import reverse

from sale.models import Sale, SaleItem, SalePayment
from sale.services.sale_service import SaleService
from sale.tests.test_sale_service import user, customer, warehouse, product, chart_of_accounts
from product.models import Stock
from financial.models import JournalEntry


@pytest.mark.django_db
class TestSaleDelete:
    """
    اختبارات حذف فاتورة المبيعات واستعادة المخزون وحذف القيد وإعادة رصيد العميل
    """

    def test_delete_sale_restores_stock_deletes_journal_and_recalculates_balance(
        self, user, customer, warehouse, product, chart_of_accounts
    ):
        """
        التحقق من أن حذف فاتورة المبيعات:
        1. يعيد كميات المخزون للوضع السابق بدقة.
        2. يحذف حركات المخزون المرتبطة بها.
        3. يحذف القيد المحاسبي.
        4. يعيد حساب رصيد العميل ويخصم قيمة الفاتورة.
        5. يحذف الفاتورة من النظام.
        """
        initial_stock = Stock.objects.filter(product=product, warehouse=warehouse).first()
        initial_qty = initial_stock.quantity if initial_stock else Decimal("0.00")
        initial_customer_balance = customer.balance

        sale_data = {
            'date': timezone.now().date(),
            'customer_id': customer.id,
            'warehouse_id': warehouse.id,
            'payment_method': 'credit',
            'discount': Decimal('0'),
            'tax': Decimal('0'),
            'notes': 'فاتورة مبيعات لاختبار الحذف واستعادة المخزون',
            'items': [
                {
                    'product_id': product.id,
                    'quantity': Decimal('3.00'),
                    'unit_price': Decimal('100.00'),
                    'discount': Decimal('0'),
                }
            ]
        }

        # 1. إنشاء الفاتورة
        sale = SaleService.create_sale(data=sale_data, user=user)
        sale_id = sale.id
        sale_number = sale.number
        je_id = sale.journal_entry_id

        # التحقق من خصم المخزون وزيادة رصيد العميل
        stock_after = Stock.objects.filter(product=product, warehouse=warehouse).first()
        assert stock_after.quantity == initial_qty - Decimal('3.00')

        customer.refresh_from_db()
        assert customer.balance == initial_customer_balance + Decimal('300.00')

        # 2. تنفيذ حذف الفاتورة عبر SaleService.delete_sale
        result = SaleService.delete_sale(sale=sale, user=user)
        assert result is True

        # 3. التحقق بعد الحذف
        # أ. الفاتورة حُذفت
        assert not Sale.objects.filter(id=sale_id).exists()

        # ب. كمية المخزون عادت للوضع الأصلي بالكامل
        stock_restored = Stock.objects.filter(product=product, warehouse=warehouse).first()
        assert stock_restored.quantity == initial_qty

        # ج. رصيد العميل عاد للوضع الأصلي
        customer.refresh_from_db()
        assert customer.balance == initial_customer_balance

        # د. القيد المحاسبي حُذف
        assert not JournalEntry.objects.filter(id=je_id).exists()

    def test_cannot_delete_sale_with_posted_payments(self, user, customer, warehouse):
        """
        التحقق من منع حذف فاتورة مبيعات بها دفعات مرحلة
        """
        sale = Sale.objects.create(
            number="INV-WITH-PAYMENT-DEL",
            date=timezone.now().date(),
            customer=customer,
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
            status="confirmed",
            payment_status="paid",
            created_by=user
        )
        SalePayment.objects.create(
            sale=sale,
            amount=Decimal("100.00"),
            payment_date=timezone.now().date(),
            status="posted",
            created_by=user
        )

        with pytest.raises(ValidationError) as exc:
            SaleService.delete_sale(sale=sale, user=user)
        assert "مدفوعات مرحلة" in str(exc.value)

    def test_delete_sale_view_post(self, client, user, customer, warehouse, product, chart_of_accounts):
        """
        التحقق من عمل View الحذف عبر طلب POST
        """
        client.force_login(user)

        sale_data = {
            'date': timezone.now().date(),
            'customer_id': customer.id,
            'warehouse_id': warehouse.id,
            'payment_method': 'credit',
            'discount': Decimal('0'),
            'tax': Decimal('0'),
            'notes': 'فاتورة لاختبار الـ View',
            'items': [
                {
                    'product_id': product.id,
                    'quantity': Decimal('2.00'),
                    'unit_price': Decimal('100.00'),
                    'discount': Decimal('0'),
                }
            ]
        }
        sale = SaleService.create_sale(data=sale_data, user=user)
        sale_id = sale.id

        url = reverse("sale:sale_delete", kwargs={"pk": sale_id})
        response = client.post(url, follow=True)

        assert response.status_code == 200
        assert not Sale.objects.filter(id=sale_id).exists()
