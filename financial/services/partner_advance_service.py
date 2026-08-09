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

        if not currency:
            return Decimal("0.00")

        snapshot = PartnerCurrencyBalanceSnapshot.objects.filter(
            partner_type=partner_type,
            partner_id=partner_id,
            currency=currency,
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
    ) -> PartnerAdvanceSettlement:
        """
        تخصيص وتسوية مبلغ من الدفعة المقدمة على الفاتورة بنسبة 1:1 للعملات المتطابقة
        تأمين التزامن عبر transaction.atomic() و select_for_update()
        """
        amount = Decimal(str(amount))
        if amount <= Decimal("0.00"):
            raise ValidationError(_("يجب أن يكون المبلغ المخصص أكبر من صفر."))

        partner_type = "customer" if hasattr(partner, "payments") or partner.__class__.__name__ == "Customer" else "supplier"
        partner_id = partner.id if hasattr(partner, "id") else partner

        # التحقق من عملة الفاتورة وعملة الدفعة
        target_currency = getattr(invoice, "currency", None) or getattr(payment, "currency", None)
        if not target_currency:
            from financial.services.exchange_rate_service import ExchangeRateService
            target_currency = ExchangeRateService.get_functional_currency()

        if getattr(invoice, "currency", None) and getattr(payment, "currency", None):
            if invoice.currency_id != payment.currency_id:
                raise ValidationError(_("قاعدة التخصيص الأحادي: يجب أن تطابق عملة الفاتورة عملة الدفعة المقدمة تماماً."))

        with transaction.atomic():
            # قفل التزامن السريع ومنع سباق البيانات (Concurrency Lock)
            snapshot, created = PartnerCurrencyBalanceSnapshot.objects.select_for_update().get_or_create(
                partner_type=partner_type,
                partner_id=partner_id,
                currency=target_currency,
                defaults={"advance_balance": Decimal("0.00")},
            )

            # تحقق من كفاية الرصيد المتاح
            if amount > snapshot.advance_balance:
                raise ValidationError(f"الرصيد المتاح في المحفظة ({snapshot.advance_balance}) أقل من المبلغ المراد تخصيصه ({amount}).")

            # خصم الرصيد المتاح من اللقطة
            snapshot.advance_balance -= amount
            snapshot.save(update_fields=["advance_balance", "updated_at"])

            # إنشاء سجل التسوية المستقل
            settlement_kwargs = {
                "allocated_amount": amount,
                "currency": target_currency,
                "exchange_rate_snapshot": getattr(payment, "exchange_rate_snapshot", Decimal("1.000000")),
                "created_by": user,
                "status": "APPLIED",
            }

            if partner_type == "customer":
                settlement_kwargs["customer_payment"] = payment
                settlement_kwargs["sale"] = invoice
            else:
                settlement_kwargs["supplier_payment"] = payment
                settlement_kwargs["purchase"] = invoice

            settlement = PartnerAdvanceSettlement.objects.create(**settlement_kwargs)

            # تحديث المبلغ المخصص بالدفعة
            if hasattr(payment, "allocated_amount"):
                payment.allocated_amount += amount
                payment.save(update_fields=["allocated_amount"])

            # تحديث المبلغ المسدد بالفاتورة
            if hasattr(invoice, "amount_paid"):
                invoice.amount_paid += amount
                if hasattr(invoice, "update_payment_status"):
                    invoice.update_payment_status()
                else:
                    invoice.save()

            return settlement

    @classmethod
    def unallocate(cls, settlement_id: int, user=None) -> PartnerAdvanceSettlement:
        """
        إلغاء وعكس تسوية سابقة وإعادة الرصيد للمحفظة فورياً
        """
        with transaction.atomic():
            settlement = PartnerAdvanceSettlement.objects.select_for_update().get(pk=settlement_id)
            if settlement.status == "REVERSED":
                raise ValidationError(_("هذه التسوية معكوسة بالفعل."))

            partner = settlement.customer_payment.customer if settlement.customer_payment else settlement.supplier_payment.supplier
            partner_type = "customer" if settlement.customer_payment else "supplier"
            partner_id = partner.id

            snapshot, created = PartnerCurrencyBalanceSnapshot.objects.select_for_update().get_or_create(
                partner_type=partner_type,
                partner_id=partner_id,
                currency=settlement.currency,
                defaults={"advance_balance": Decimal("0.00")},
            )

            # إعادة المبلغ المخصص للرصيد المتاح
            snapshot.advance_balance += settlement.allocated_amount
            snapshot.save(update_fields=["advance_balance", "updated_at"])

            # عكس المبالغ بالفاتورة والدفعة
            payment = settlement.customer_payment or settlement.supplier_payment
            if payment and hasattr(payment, "allocated_amount"):
                payment.allocated_amount = max(Decimal("0.00"), payment.allocated_amount - settlement.allocated_amount)
                payment.save(update_fields=["allocated_amount"])

            invoice = settlement.sale or settlement.purchase
            if invoice and hasattr(invoice, "amount_paid"):
                invoice.amount_paid = max(Decimal("0.00"), invoice.amount_paid - settlement.allocated_amount)
                if hasattr(invoice, "update_payment_status"):
                    invoice.update_payment_status()
                else:
                    invoice.save()

            settlement.status = "REVERSED"
            settlement.save(update_fields=["status"])

            return settlement

    @classmethod
    def rebuild_all_snapshots(cls, partner):
        """
        إعادة بناء كافة اللقطات المالية لجميع العملات الخاصة بالشريك
        """
        partner_type = "customer" if hasattr(partner, "payments") or partner.__class__.__name__ == "Customer" else "supplier"
        from financial.services.exchange_rate_service import ExchangeRateService
        func_curr = ExchangeRateService.get_functional_currency()

        currencies = set()
        if func_curr:
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

        if not currency:
            return Decimal("0.00")

        is_func = (func_curr and currency.id == func_curr.id)

        if partner_type == "customer":
            if hasattr(partner, "payments"):
                if is_func:
                    payments = partner.payments.exclude(status="cancelled").filter(Q(currency=currency) | Q(currency__isnull=True))
                else:
                    payments = partner.payments.exclude(status="cancelled").filter(currency=currency)
            else:
                payments = []
            total_paid = sum((p.transaction_amount or p.amount) for p in payments)

            from sale.models import SalePayment
            settled = Decimal("0.00")
            for p in payments:
                sp_s = sum(sp.amount for sp in SalePayment.objects.filter(customer_payment=p))
                cs_s = sum(s.allocated_amount for s in p.customer_settlements.filter(status="APPLIED")) if hasattr(p, "customer_settlements") else Decimal("0.00")
                settled += sp_s if sp_s > Decimal("0.00") else cs_s
        else:
            if hasattr(partner, "advance_payments"):
                if is_func:
                    payments = partner.advance_payments.filter(Q(currency=currency) | Q(currency__isnull=True))
                else:
                    payments = partner.advance_payments.filter(currency=currency)
            else:
                payments = []
            total_paid = sum((p.transaction_amount or p.amount) for p in payments)

            from purchase.models import PurchasePayment
            from supplier.models import SupplierAllocationAudit
            settled = Decimal("0.00")
            for p in payments:
                pp_s = sum(pp.amount for pp in PurchasePayment.objects.filter(reference_number=f"ADV-{p.id}"))
                aud_s = sum(a.allocated_amount for a in SupplierAllocationAudit.objects.filter(source_document_number=f"ADV-{p.id}", allocation_status="APPLIED"))
                ss_s = sum(s.allocated_amount for s in p.supplier_settlements.filter(status="APPLIED")) if hasattr(p, "supplier_settlements") else Decimal("0.00")
                settled += max(pp_s, aud_s, ss_s)

        net_balance = max(Decimal("0.00"), total_paid - settled)

        snapshot, created = PartnerCurrencyBalanceSnapshot.objects.update_or_create(
            partner_type=partner_type,
            partner_id=partner_id,
            currency=currency,
            defaults={"advance_balance": net_balance},
        )
        return snapshot.advance_balance
