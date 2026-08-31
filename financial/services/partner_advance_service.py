from decimal import Decimal
from typing import Dict, Any, Optional
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.db.models import Q
from financial.models import (
    PartnerCurrencyBalanceSnapshot,
    PartnerAdvanceSettlement,
    Currency,
)


class PartnerAdvanceService:
    """
    خدمة الأرصدة المسبقة وتسويات الدفعات المقدمة المحوكمة للعملاء والموردين
    """

    @classmethod
    def get_available_balance(cls, partner, currency=None) -> Decimal:
        """
        قراءة الرصيد المسبق المتاح لشريك (عميل أو مورد) حسب عملة محددة أو العملة الوظيفية
        SLA < 300ms دون بطء
        """
        partner_type = "customer" if hasattr(partner, "payments") or partner.__class__.__name__ == "Customer" else "supplier"
        partner_id = partner.id if hasattr(partner, "id") else partner

        if not currency:
            from financial.services.exchange_rate_service import ExchangeRateService
            currency = ExchangeRateService.get_functional_currency()

        curr_code = currency.code if hasattr(currency, "code") else (str(currency) if currency else "EGP")
        snapshot = PartnerCurrencyBalanceSnapshot.objects.filter(
            partner_type=partner_type,
            partner_id=partner_id,
            currency__code=curr_code,
        ).first()

        if snapshot:
            return snapshot.advance_balance

        # إذا لم توجد لقطة مخصصة، يتم احتساب اللقطة وتأسيسها آلياً
        return cls.rebuild_snapshot(partner, currency=currency)

    @classmethod
    def get_all_balances(cls, partner) -> Dict[str, Dict[str, Any]]:
        """
        ترجيع جميع محافظ الأرصدة المسبقة المتاحة للشريك مقسمة حسب كود كل عملة شاملة الرمز والاسم
        """
        cls.rebuild_all_snapshots(partner)
        partner_type = "customer" if hasattr(partner, "payments") or partner.__class__.__name__ == "Customer" else "supplier"
        partner_id = partner.id if hasattr(partner, "id") else partner

        snapshots = PartnerCurrencyBalanceSnapshot.objects.filter(
            partner_type=partner_type,
            partner_id=partner_id,
            advance_balance__gt=Decimal("0.00"),
        ).select_related("currency")

        balances = {}
        for snap in snapshots:
            if snap.currency:
                balances[snap.currency.code] = {
                    "balance": snap.advance_balance,
                    "symbol": snap.currency.symbol or snap.currency.code,
                    "name": snap.currency.name,
                    "code": snap.currency.code,
                }
        return balances

    @classmethod
    def allocate(
        cls,
        partner,
        payment,
        invoice,
        amount: Decimal,
        user=None,
    ):
        """
        توجيه التخصيص آلياً وحصرياً لنواة الـ Audit الموحدة Single Source of Truth
        """
        partner_type = "customer" if hasattr(partner, "payments") or partner.__class__.__name__ == "Customer" else "supplier"

        if partner_type == "customer":
            from customer.services.customer_allocation_audit_service import CustomerAllocationAuditService
            return CustomerAllocationAuditService.allocate_customer_prepaid_balance_to_sale(
                sale=invoice,
                amount_to_allocate=amount,
                user=user
            )
        else:
            from supplier.services.supplier_allocation_service import SupplierAllocationService
            return SupplierAllocationService.allocate_advance_to_purchase_bill(
                purchase=invoice,
                amount_to_allocate=amount,
                user=user
            )

    @classmethod
    def unallocate(cls, audit_id: int, user=None, partner_type: str = "customer"):
        """
        توجيه عكس التوزيع آلياً وحصرياً لنواة الـ Audit الموحدة Single Source of Truth
        """
        if partner_type == "customer":
            from customer.services.customer_allocation_audit_service import CustomerAllocationAuditService
            return CustomerAllocationAuditService.reverse_customer_allocation(audit_id=audit_id, user=user)
        else:
            from supplier.services.supplier_allocation_service import SupplierAllocationService
            return SupplierAllocationService.reverse_supplier_allocation(audit_id=audit_id, user=user)

    @classmethod
    def rebuild_all_snapshots(cls, partner):
        """
        إعادة بناء كافة اللقطات المالية لجميع العملات الخاصة بالشريك
        """
        partner_type = "customer" if hasattr(partner, "payments") or partner.__class__.__name__ == "Customer" else "supplier"
        from financial.services.exchange_rate_service import ExchangeRateService
        func_curr = ExchangeRateService.get_functional_currency()
        if func_curr and not isinstance(func_curr, Currency):
            curr_code = getattr(func_curr, 'code', 'EGP')
            func_curr = Currency.objects.filter(code=curr_code).first()

        currencies = set()
        if func_curr and isinstance(func_curr, Currency):
            currencies.add(func_curr)

        if partner_type == "customer" and hasattr(partner, "payments"):
            for c_id in partner.payments.exclude(status="cancelled").values_list("currency_id", flat=True).distinct():
                if c_id:
                    c_obj = Currency.objects.filter(pk=c_id).first()
                    if c_obj:
                        currencies.add(c_obj)
        elif partner_type == "supplier" and hasattr(partner, "advance_payments"):
            for c_id in partner.advance_payments.values_list("currency_id", flat=True).distinct():
                if c_id:
                    c_obj = Currency.objects.filter(pk=c_id).first()
                    if c_obj:
                        currencies.add(c_obj)

        for curr in currencies:
            cls.rebuild_snapshot(partner, currency=curr)

    @classmethod
    def rebuild_snapshot(cls, partner, currency=None) -> Decimal:
        """
        إعادة حساب اللقطة المالية وتحديثها للشريك بناءً على الدفعات والتسويات
        """
        partner_type = "customer" if hasattr(partner, "payments") or partner.__class__.__name__ == "Customer" else "supplier"
        partner_id = partner.id if hasattr(partner, "id") else partner

        from financial.services.exchange_rate_service import ExchangeRateService
        func_curr = ExchangeRateService.get_functional_currency()
        if not currency:
            currency = func_curr

        if currency and not isinstance(currency, Currency):
            curr_code = getattr(currency, "code", str(currency) if currency else "EGP")
            currency = Currency.objects.filter(code=curr_code).first()

        if func_curr and not isinstance(func_curr, Currency):
            f_code = getattr(func_curr, "code", "EGP")
            func_curr = Currency.objects.filter(code=f_code).first()

        is_func = (not currency or (func_curr and currency and currency.id == func_curr.id))

        if partner_type == "customer":
            if hasattr(partner, "payments"):
                if is_func or not currency:
                    if currency:
                        payments = partner.payments.exclude(status="cancelled").filter(Q(currency=currency) | Q(currency__isnull=True))
                    else:
                        payments = partner.payments.exclude(status="cancelled").all()
                else:
                    payments = partner.payments.exclude(status="cancelled").filter(currency=currency)
            else:
                payments = []
            total_paid = sum((p.transaction_amount or p.amount) for p in payments)

            from customer.models import CustomerAllocationAudit
            settled = Decimal("0.00")
            for p in payments:
                settled += sum(
                    a.allocated_amount for a in CustomerAllocationAudit.objects.filter(
                        source_document_number=f"PAY-{p.id}",
                        allocation_status="APPLIED"
                    )
                )
        else:
            if hasattr(partner, "advance_payments"):
                if is_func:
                    payments = partner.advance_payments.filter(Q(currency=currency) | Q(currency__isnull=True))
                else:
                    payments = partner.advance_payments.filter(currency=currency)
            else:
                payments = []
            total_paid = sum((p.transaction_amount or p.amount) for p in payments)

            from supplier.models import SupplierAllocationAudit
            settled = Decimal("0.00")
            for p in payments:
                settled += sum(
                    a.allocated_amount for a in SupplierAllocationAudit.objects.filter(
                        source_document_number=f"ADV-{p.id}",
                        allocation_status="APPLIED"
                    )
                )

        net_balance = max(Decimal("0.00"), total_paid - settled)

        curr_obj = currency if isinstance(currency, Currency) else Currency.objects.filter(code=str(currency)).first()
        if not curr_obj:
            curr_obj = func_curr

        if not curr_obj:
            return net_balance

        snapshot, created = PartnerCurrencyBalanceSnapshot.objects.update_or_create(
            partner_type=partner_type,
            partner_id=partner_id,
            currency=curr_obj,
            defaults={
                "advance_balance": net_balance,
            },
        )
        return snapshot.advance_balance

    @classmethod
    def run_daily_balance_reconciliation(cls) -> Dict[str, Any]:
        """
        خدمة المطابقة الفوقية الشمولية التي تعمل دورياً (Daily Job at 00:00)
        تقارن رصيد اللقطة المخزنة مع مجموع سجلات الـ Audit وتولد ReconciliationIssue في حال وجود فروق
        """
        from financial.models import PartnerCurrencyBalanceSnapshot, ReconciliationIssue, Currency
        from customer.models import Customer, CustomerAllocationAudit, CustomerPayment
        from supplier.models import Supplier, SupplierAllocationAudit, SupplierAdvancePayment

        issues_found = []

        snapshots = PartnerCurrencyBalanceSnapshot.objects.select_related("currency").all()
        for snap in snapshots:
            calculated_balance = Decimal("0.00")
            if snap.partner_type == "customer":
                customer = Customer.objects.filter(pk=snap.partner_id).first()
                if customer:
                    payments = CustomerPayment.objects.filter(customer=customer, currency=snap.currency).exclude(status="cancelled")
                    total_adv = sum(p.amount for p in payments)
                    total_alloc = sum(
                        a.allocated_amount for a in CustomerAllocationAudit.objects.filter(
                            customer=customer,
                            allocation_currency=snap.currency.code,
                            allocation_status="APPLIED"
                        )
                    )
                    calculated_balance = max(Decimal("0.00"), total_adv - total_alloc)
            else:
                supplier = Supplier.objects.filter(pk=snap.partner_id).first()
                if supplier:
                    advances = SupplierAdvancePayment.objects.filter(supplier=supplier, currency=snap.currency)
                    total_adv = sum(a.amount for a in advances)
                    total_alloc = sum(
                        a.allocated_amount for a in SupplierAllocationAudit.objects.filter(
                            supplier=supplier,
                            allocation_status="APPLIED"
                        )
                    )
                    calculated_balance = max(Decimal("0.00"), total_adv - total_alloc)

            diff = snap.advance_balance - calculated_balance
            if abs(diff) > Decimal("0.01"):
                issue = ReconciliationIssue.objects.create(
                    partner_type=snap.partner_type,
                    partner_id=snap.partner_id,
                    currency_code=snap.currency.code if snap.currency else "EGP",
                    expected_balance=calculated_balance,
                    actual_balance=snap.advance_balance,
                    difference=diff,
                    status="OPEN",
                    notes=f"اختلاف مكتشف بواسطة محرك المطابقة الدوري تلقائياً: متوقع {calculated_balance} مقابل مخزن {snap.advance_balance}"
                )
                issues_found.append(issue)

        return {
            "processed_snapshots": snapshots.count(),
            "issues_count": len(issues_found),
            "issues": issues_found
        }

