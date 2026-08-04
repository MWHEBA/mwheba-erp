import logging
from decimal import Decimal
from typing import Any
from presentation.dto.document_dto import DocumentFinancialBreakdownDTO

logger = logging.getLogger("presentation.services.document_financial_presenter")


class DocumentFinancialPresenter:
    """
    FIN-EEL: Document Financial Presenter Service
    تحضير تفكيك المبالغ المالية (subtotal, discount, tax, total, currency, exchange_rate, functional_total_egp)
    """

    @classmethod
    def get_breakdown(
        cls,
        subtotal: Decimal,
        tax_amount: Decimal,
        total_amount: Decimal,
        discount_amount: Decimal = Decimal("0.00"),
        currency: str = "EGP",
        exchange_rate: Decimal = Decimal("1.000000"),
        payment_terms: str = None,
        due_date: str = None
    ) -> DocumentFinancialBreakdownDTO:
        taxable = max(Decimal("0.00"), subtotal - discount_amount)
        func_total = (total_amount * exchange_rate).quantize(Decimal("0.01"))

        return DocumentFinancialBreakdownDTO(
            subtotal=subtotal,
            discount_amount=discount_amount,
            taxable_amount=taxable,
            tax_amount=tax_amount,
            total_amount=total_amount,
            currency=currency,
            exchange_rate=exchange_rate,
            functional_total_egp=func_total,
            payment_terms=payment_terms,
            due_date=due_date
        )

    @classmethod
    def get_sales_invoice_breakdown(cls, invoice) -> DocumentFinancialBreakdownDTO:
        subtotal = getattr(invoice, "subtotal_amount", getattr(invoice, "total_amount", Decimal("0.00")))
        tax = getattr(invoice, "tax_amount", Decimal("0.00"))
        tot = getattr(invoice, "total_amount", Decimal("0.00"))
        disc = getattr(invoice, "discount_amount", Decimal("0.00"))
        curr = getattr(invoice, "currency", "EGP")
        rate = getattr(invoice, "exchange_rate", Decimal("1.000000"))

        return cls.get_breakdown(
            subtotal=subtotal,
            tax_amount=tax,
            total_amount=tot,
            discount_amount=disc,
            currency=curr,
            exchange_rate=rate
        )

    @classmethod
    def get_credit_note_breakdown(cls, credit_note) -> DocumentFinancialBreakdownDTO:
        subtotal = credit_note.subtotal_amount
        tax = credit_note.tax_amount
        tot = credit_note.total_amount
        curr = credit_note.currency
        rate = credit_note.exchange_rate

        return cls.get_breakdown(
            subtotal=subtotal,
            tax_amount=tax,
            total_amount=tot,
            discount_amount=Decimal("0.00"),
            currency=curr,
            exchange_rate=rate
        )
