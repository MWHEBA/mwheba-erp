import logging
from decimal import Decimal
from django.db import models, transaction
from customer.models import Customer
from supplier.models import Supplier

logger = logging.getLogger(__name__)


class PartnerBalanceAuditService:
    """
    خدمة المراجعة والتدقيق والمطابقة الدورية لأرصدة الشركاء (Reconciliation & Audit Service)
    - فحص ومطابقة رصيد الشريك مع الأستاذ المساعد وقيود الأستاذ العام
    - تشغيل المزامنة الأولية لرصيد الأساس (Baseline Sync)
    """

    @classmethod
    def audit_customer_balance(cls, customer_id: int) -> dict:
        """
        تدقيق ومطابقة رصيد عميل محدد
        """
        from sale.models import Sale, SalePayment, SaleReturn
        from customer.models import CustomerTransaction

        try:
            customer = Customer.objects.get(pk=customer_id)
        except Customer.DoesNotExist:
            return {"error": "العميل غير موجود"}

        sales_qs = Sale.objects.filter(customer=customer).exclude(status="cancelled")
        total_sales_func = sum(
            (getattr(s, "total_functional", None) or (s.total * (getattr(s, "exchange_rate", Decimal("1.000000")) or Decimal("1.000000")))).quantize(Decimal("0.01"))
            for s in sales_qs
        ) if sales_qs.exists() else Decimal("0.00")

        returns_qs = SaleReturn.objects.filter(sale__customer=customer, status="confirmed").select_related("sale")
        total_returns_func = sum(
            (r.total * (getattr(r.sale, "exchange_rate", Decimal("1.000000")) or Decimal("1.000000"))).quantize(Decimal("0.01"))
            for r in returns_qs
        ) if returns_qs.exists() else Decimal("0.00")

        payments_qs = SalePayment.objects.filter(sale__customer=customer, status="posted").select_related("sale")
        total_payments_func = Decimal("0.00")
        for p in payments_qs:
            rate = getattr(p.sale, "exchange_rate", Decimal("1.000000")) or Decimal("1.000000")
            settled = getattr(p, "amount_settled_invoice_currency", p.amount) or p.amount
            total_payments_func += (Decimal(str(settled)) * Decimal(str(rate))).quantize(Decimal("0.01"))

        calculated_balance = (total_sales_func - total_returns_func - total_payments_func).quantize(Decimal("0.01"))
        current_stored_balance = customer.balance

        diff = (calculated_balance - current_stored_balance).quantize(Decimal("0.01"))

        return {
            "customer_id": customer.id,
            "customer_name": customer.name,
            "calculated_balance": calculated_balance,
            "stored_balance": current_stored_balance,
            "difference": diff,
            "is_matched": diff == Decimal("0.00"),
        }

    @classmethod
    def sync_baseline_balances(cls):
        """
        مزامنة وضبط رصيد الأساس لكافة العملاء والموردين لمرة واحدة
        """
        logger.info("🔄 بدء مزامنة وتدقيق رصيد الأساس لكافة الشركاء...")
        fixed_count = 0

        # العملاء
        for customer in Customer.objects.all():
            res = cls.audit_customer_balance(customer.id)
            if not res.get("is_matched"):
                calc_bal = res.get("calculated_balance", Decimal("0.00"))
                Customer.objects.filter(pk=customer.pk).update(balance=calc_bal)
                fixed_count += 1

        logger.info(f"✅ اكتملت مزامنة رصيد الأساس. تم تصحيح {fixed_count} حساب.")
        return fixed_count
