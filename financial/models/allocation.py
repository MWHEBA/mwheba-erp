from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class PaymentAllocation(models.Model):
    """
    نموذج تخصيص السداد المحكوم والمجرد (Payment Allocation Engine - FIN-SUB-001 & FIN-SUB-002)
    يدير التخصيص والمطابقة بين مستندات المدين والمدفوعات والمستندات الدائنة بشكل مجرد ومعزول.
    """
    SUBLEDGER_TYPES = (
        ("customer", _("عميل")),
        ("supplier", _("مورد")),
    )

    allocation_number = models.CharField(_("رقم التخصيص"), max_length=50, unique=True)

    # مستند المدين (Debit Document e.g. SALE_INVOICE, PURCHASE_BILL)
    debit_document_type = models.CharField(_("نوع مستند المدين"), max_length=50)
    debit_document_id = models.CharField(_("معرف مستند المدين"), max_length=100)

    # مستند الدائن (Credit Document e.g. CUSTOMER_PAYMENT, SUPPLIER_PAYMENT, CREDIT_NOTE)
    credit_document_type = models.CharField(_("نوع مستند الدائن"), max_length=50)
    credit_document_id = models.CharField(_("معرف مستند الدائن"), max_length=100)

    # نوع الدفتر الفرعي والمشترك (Customer/Supplier)
    subledger_type = models.CharField(_("نوع الدفتر الفرعي"), max_length=20, choices=SUBLEDGER_TYPES)
    entity_id = models.IntegerField(_("معرف الكيان"), help_text=_("معرف العميل أو المورد"))

    allocated_amount = models.DecimalField(
        _("المبلغ المخصص"),
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00")
    )
    allocation_date = models.DateField(_("تاريخ التخصيص"))

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_("أنشئ بواسطة"),
        related_name="payment_allocations_created"
    )
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        verbose_name = _("تخصيص سداد")
        verbose_name_plural = _("تخصيصات المدفوعات")
        ordering = ["-allocation_date", "-id"]
        indexes = [
            models.Index(fields=["debit_document_type", "debit_document_id"]),
            models.Index(fields=["credit_document_type", "credit_document_id"]),
            models.Index(fields=["subledger_type", "entity_id"]),
        ]

    def __str__(self):
        return f"Alloc #{self.allocation_number}: {self.allocated_amount} ({self.debit_document_type} <- {self.credit_document_type})"
