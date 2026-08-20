import logging
from decimal import Decimal
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


class PartnerSubledgerService:
    """
    خدمة الأستاذ المساعد المركزي الموحد (Unified Partner Subledger Service)
    FIN-AR-003 & FIN-AP-003: إدارة حركات الأستاذ المساعد المفتوحة للعملاء والموردين بدعم العملات المتعددة وIAS 21
    """

    @classmethod
    def record_sale_invoice(cls, sale, user=None):
        """
        تسجيل أو تحديث فاتورة مبيعات في أستاذ العملاء الفرعي CustomerTransaction
        """
        if not sale or not sale.customer:
            return None

        try:
            from client.models import CustomerTransaction
            from sale.models import SalePayment

            paid_foreign = SalePayment.objects.filter(sale=sale, status="posted").aggregate(
                t=models.Sum("amount")
            )["t"] or Decimal("0.00")
            due_foreign = max(Decimal("0.00"), sale.total - paid_foreign - getattr(sale, "amount_returned", Decimal("0.00")))

            curr_code = sale.currency.code if (hasattr(sale, "currency") and sale.currency) else (getattr(sale, "currency", None) or "EGP")
            raw_rate = getattr(sale, "exchange_rate", Decimal("1.000000")) or Decimal("1.000000")
            rate = Decimal(str(raw_rate))

            func_total = getattr(sale, "total_functional", None)
            if not func_total or func_total == Decimal("0.00"):
                func_total = (Decimal(str(sale.total)) * rate).quantize(Decimal("0.01"))

            due_functional = (due_foreign * rate).quantize(Decimal("0.01"))
            status = "CLOSED" if due_foreign <= Decimal("0.00") else ("PARTIAL" if paid_foreign > Decimal("0.00") else "OPEN")

            txn, is_new = CustomerTransaction.objects.get_or_create(
                customer=sale.customer,
                transaction_type="INVOICE",
                reference_id=str(sale.id),
                defaults={
                    "transaction_number": sale.number,
                    "issue_date": sale.date,
                    "due_date": sale.date,
                    "currency": curr_code,
                    "foreign_amount": sale.total,
                    "exchange_rate": rate,
                    "functional_amount": func_total,
                    "open_amount": due_functional,
                    "open_amount_functional": due_functional,
                    "open_amount_foreign": due_foreign,
                    "status": status,
                }
            )
            if not is_new:
                txn.currency = curr_code
                txn.exchange_rate = rate
                txn.foreign_amount = sale.total
                txn.functional_amount = func_total
                txn.open_amount = due_functional
                txn.open_amount_functional = due_functional
                txn.open_amount_foreign = due_foreign
                txn.status = status
                txn.save()

            return txn
        except Exception as e:
            logger.error(f"❌ فشل تسجيل فاتورة المبيعات {sale.number} في الأستاذ المساعد: {e}")
            return None

    @classmethod
    def record_purchase_bill(cls, purchase, user=None):
        """
        تسجيل أو تحديث فاتورة مشتريات في أستاذ الموردين الفرعي SupplierTransaction
        """
        if not purchase or not purchase.supplier:
            return None

        try:
            from supplier.models import SupplierTransaction
            from purchase.models import PurchasePayment

            paid_foreign = PurchasePayment.objects.filter(purchase=purchase, status="posted").aggregate(
                t=models.Sum("amount")
            )["t"] or Decimal("0.00")
            due_foreign = max(Decimal("0.00"), purchase.total - paid_foreign - getattr(purchase, "amount_returned", Decimal("0.00")))

            curr_code = purchase.currency.code if (hasattr(purchase, "currency") and purchase.currency) else (getattr(purchase, "currency", None) or "EGP")
            raw_rate = getattr(purchase, "exchange_rate", Decimal("1.000000")) or Decimal("1.000000")
            rate = Decimal(str(raw_rate))

            func_total = getattr(purchase, "total_functional", None)
            if not func_total or func_total == Decimal("0.00"):
                func_total = (Decimal(str(purchase.total)) * rate).quantize(Decimal("0.01"))

            due_functional = (due_foreign * rate).quantize(Decimal("0.01"))
            status = "CLOSED" if due_foreign <= Decimal("0.00") else ("PARTIAL" if paid_foreign > Decimal("0.00") else "OPEN")

            txn, is_new = SupplierTransaction.objects.get_or_create(
                supplier=purchase.supplier,
                transaction_type="BILL",
                transaction_number=purchase.number,
                defaults={
                    "issue_date": purchase.date,
                    "due_date": purchase.date,
                    "currency": curr_code,
                    "foreign_amount": purchase.total,
                    "exchange_rate": rate,
                    "functional_amount": func_total,
                    "open_amount": due_functional,
                    "open_amount_functional": due_functional,
                    "open_amount_foreign": due_foreign,
                    "status": status,
                }
            )
            if not is_new:
                txn.currency = curr_code
                txn.exchange_rate = rate
                txn.foreign_amount = purchase.total
                txn.functional_amount = func_total
                txn.open_amount = due_functional
                txn.open_amount_functional = due_functional
                txn.open_amount_foreign = due_foreign
                txn.status = status
                txn.save()

            return txn
        except Exception as e:
            logger.error(f"❌ فشل تسجيل فاتورة المشتريات {purchase.number} في الأستاذ المساعد: {e}")
            return None

    @classmethod
    def record_payment_settlement(cls, payment, partner_type: str, user=None):
        """
        تحديث المتبقي في الأستاذ المساعد عند سداد دفعة
        """
        if partner_type == "customer" and getattr(payment, "sale", None):
            return cls.record_sale_invoice(payment.sale, user)
        elif partner_type == "supplier" and getattr(payment, "purchase", None):
            return cls.record_purchase_bill(payment.purchase, user)
        return None

    @classmethod
    def reverse_payment_settlement(cls, payment, partner_type: str, user=None):
        """
        إعادة فتح واستعادة المتبقي في الأستاذ المساعد عند حذف أو إلغاء دفعة
        """
        if partner_type == "customer" and getattr(payment, "sale", None):
            return cls.record_sale_invoice(payment.sale, user)
        elif partner_type == "supplier" and getattr(payment, "purchase", None):
            return cls.record_purchase_bill(payment.purchase, user)
        return None

    @classmethod
    def record_advance_payment(cls, advance_payment, partner_type: str, user=None):
        """
        تسجيل دفعة مقدمة في الأستاذ المساعد
        """
        try:
            if partner_type == "customer":
                from client.models import CustomerTransaction
                curr_code = getattr(advance_payment, "currency_code", "EGP") or "EGP"
                raw_rate = getattr(advance_payment, "exchange_rate", Decimal("1.000000")) or Decimal("1.000000")
                rate = Decimal(str(raw_rate))
                func_amt = (Decimal(str(advance_payment.amount)) * rate).quantize(Decimal("0.01"))

                txn, _ = CustomerTransaction.objects.get_or_create(
                    customer=advance_payment.customer,
                    transaction_type="ADVANCE",
                    reference_id=str(advance_payment.id),
                    defaults={
                        "transaction_number": getattr(advance_payment, "reference_number", None) or f"CP-{advance_payment.id}",
                        "issue_date": getattr(advance_payment, "payment_date", timezone.now().date()),
                        "due_date": getattr(advance_payment, "payment_date", timezone.now().date()),
                        "currency": curr_code,
                        "foreign_amount": advance_payment.amount,
                        "exchange_rate": rate,
                        "functional_amount": func_amt,
                        "open_amount": func_amt,
                        "open_amount_functional": func_amt,
                        "open_amount_foreign": advance_payment.amount,
                        "status": "OPEN",
                    }
                )
                return txn
            elif partner_type == "supplier":
                from supplier.models import SupplierTransaction
                curr_code = getattr(advance_payment, "currency_code", "EGP") or "EGP"
                raw_rate = getattr(advance_payment, "exchange_rate", Decimal("1.000000")) or Decimal("1.000000")
                rate = Decimal(str(raw_rate))
                func_amt = (Decimal(str(advance_payment.amount)) * rate).quantize(Decimal("0.01"))

                txn, _ = SupplierTransaction.objects.get_or_create(
                    supplier=advance_payment.supplier,
                    transaction_type="ADVANCE",
                    transaction_number=getattr(advance_payment, "reference_number", None) or f"SP-{advance_payment.id}",
                    defaults={
                        "issue_date": getattr(advance_payment, "payment_date", timezone.now().date()),
                        "due_date": getattr(advance_payment, "payment_date", timezone.now().date()),
                        "currency": curr_code,
                        "foreign_amount": advance_payment.amount,
                        "exchange_rate": rate,
                        "functional_amount": func_amt,
                        "open_amount": func_amt,
                        "open_amount_functional": func_amt,
                        "open_amount_foreign": advance_payment.amount,
                        "status": "OPEN",
                    }
                )
                return txn
        except Exception as e:
            logger.error(f"❌ فشل تسجيل الدفعة المقدمة في الأستاذ المساعد ({partner_type}): {e}")
            return None
