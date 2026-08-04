import uuid
import json
import hashlib
from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.conf import settings

from client.models import Customer
from product.models import Product
from sale.models.sales_models import SalesInvoice
from sale.models.sales_return import SalesReturnHeader
from financial.models.journal_entry import JournalEntry


class CreditNote(models.Model):
    """
    FIN-SAL-005 v2.0: Financial Credit Note Model (إشعار دائن مالي محوكم)
    """
    SOURCE_TYPE_CHOICES = (
        ("SALES_RETURN", _("مرتجع مبيعات")),
        ("INVOICE_CANCELLATION", _("إلغاء فاتورة")),
        ("PRICE_ADJUSTMENT", _("تسوية تسعير خصم")),
        ("MANUAL_ADJUSTMENT", _("تسوية دائنة يدوية")),
    )

    STATUS_CHOICES = (
        ("DRAFT", _("مسودة")),
        ("PENDING_APPROVAL", _("قيد اعتماد الموافقة")),
        ("APPROVED", _("معتمد")),
        ("POSTED", _("رحل مالياً للدفاتر")),
        ("PARTIALLY_APPLIED", _("مطبق جزئياً")),
        ("FULLY_APPLIED", _("مطبق بالكامل")),
        ("REVERSED", _("معكوس")),
        ("CANCELLED", _("ملغي")),
    )

    credit_note_number = models.CharField(_("رقم الإشعار الدائن"), max_length=50, unique=True)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="credit_notes", verbose_name=_("العميل"))
    sale = models.ForeignKey("sale.Sale", on_delete=models.SET_NULL, null=True, blank=True, related_name="credit_notes", verbose_name=_("الفاتورة الأصلية"))
    sales_invoice = models.ForeignKey(SalesInvoice, on_delete=models.SET_NULL, null=True, blank=True, related_name="credit_notes_legacy", verbose_name=_("الفاتورة الأصلية (legacy)"))
    sales_return = models.ForeignKey(SalesReturnHeader, on_delete=models.SET_NULL, null=True, blank=True, related_name="credit_notes_legacy", verbose_name=_("مستند الإرجاع الأصلي (legacy)"))

    source_type = models.CharField(_("مصدر الإشعار الدائن"), max_length=30, choices=SOURCE_TYPE_CHOICES, default="SALES_RETURN")
    status = models.CharField(_("حالة الإشعار الدائن"), max_length=25, choices=STATUS_CHOICES, default="DRAFT")

    subtotal_amount = models.DecimalField(_("المبلغ الإجمالي قبل الضريبة"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    tax_amount = models.DecimalField(_("مبلغ ضريبة المخرجات المعكوسة"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(_("إجمالي مبلغ الإشعار الدائن (شامل الضريبة)"), max_digits=15, decimal_places=2, default=Decimal("0.00"))

    currency = models.CharField(_("العملة"), max_length=10, default="EGP")
    exchange_rate = models.DecimalField(_("سعر الصرف IAS 21"), max_digits=12, decimal_places=6, default=Decimal("1.000000"))

    reason = models.TextField(_("سبب إصدار الإشعار الدائن"), blank=True, null=True)
    posting_command_id = models.UUIDField(_("معرف أمر الترحيل الفريد Idempotency UUID"), default=uuid.uuid4, unique=True)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("أنشئ بواسطة"))
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        verbose_name = _("إشعار دائن مالي")
        verbose_name_plural = _("إشعارات دائنة مالية")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer", "status", "created_at"]),
        ]

    def __str__(self):
        return f"CreditNote #{self.credit_note_number} - {self.customer.name} ({self.total_amount} {self.currency}) [{self.status}]"


class CreditNoteItem(models.Model):
    """
    FIN-SAL-005 v2.0: Credit Note Line Item Breakdown
    سطر بند تفاصيل الإشعار الدائن
    """
    credit_note = models.ForeignKey(CreditNote, on_delete=models.CASCADE, related_name="items", verbose_name=_("الإشعار الدائن"))
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name="credit_note_items", verbose_name=_("المنتج"))
    description = models.CharField(_("الوصف"), max_length=255)

    quantity = models.DecimalField(_("الكمية"), max_digits=15, decimal_places=4, default=Decimal("1.0000"))
    unit_price = models.DecimalField(_("سعر الوحدة"), max_digits=15, decimal_places=2, default=Decimal("0.00"))

    subtotal = models.DecimalField(_("المبلغ قبل الضريبة"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    tax_amount = models.DecimalField(_("مبلغ الضريبة"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(_("الإجمالي"), max_digits=15, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        verbose_name = _("بند إشعار دائن")
        verbose_name_plural = _("بنود الإشعارات الدائنة")

    def __str__(self):
        return f"CN Line #{self.id}: {self.description} ({self.total_amount})"


class CreditNoteAllocation(models.Model):
    """
    FIN-SAL-005 v2.0: Credit Note Allocation Model
    ربط وتسوية الإشعار الدائن بالفاتورة ودفتر الأستاذ الفرعي للعملاء
    """
    credit_note = models.ForeignKey(CreditNote, on_delete=models.CASCADE, related_name="allocations", verbose_name=_("الإشعار الدائن"))
    invoice_transaction_id = models.IntegerField(_("معرف معاملة الفاتورة بالأستاذ الفرعي"))
    allocated_amount = models.DecimalField(_("المبلغ المخصص المخصوم"), max_digits=15, decimal_places=2)
    created_at = models.DateTimeField(_("تاريخ التسوية"), auto_now_add=True)

    class Meta:
        verbose_name = _("تخصيص إشعار دائن")
        verbose_name_plural = _("تخصيصات الإشعارات الدائنة")

    def __str__(self):
        return f"Allocation CN #{self.credit_note.credit_note_number} -> Tx #{self.invoice_transaction_id}: {self.allocated_amount}"


class CreditNoteReversal(models.Model):
    """
    FIN-SAL-005 v2.0: Credit Note Reversal Model
    عكس واسترداد الإشعار الدائن المرحل
    """
    original_credit_note = models.ForeignKey(CreditNote, on_delete=models.PROTECT, related_name="reversals_as_original", verbose_name=_("الإشعار الدائن الأصلي"))
    reversal_credit_note = models.ForeignKey(CreditNote, on_delete=models.PROTECT, related_name="reversals_as_reversal", verbose_name=_("إشعار العكس"))
    reason = models.TextField(_("سبب العكس الإداري"))
    reversal_entry_id = models.IntegerField(_("معرف قيد العكس بالدفاتر"), null=True, blank=True)
    created_at = models.DateTimeField(_("تاريخ العكس"), auto_now_add=True)

    class Meta:
        verbose_name = _("عكس إشعار دائن")
        verbose_name_plural = _("عكوسات الإشعارات الدائنة")

    def __str__(self):
        return f"Reversal of CN #{self.original_credit_note.credit_note_number} by CN #{self.reversal_credit_note.credit_note_number}"


class CreditNoteAudit(models.Model):
    """
    FIN-SAL-005 v2.0: Immutable Credit Note Audit Evidence Log Model
    سجل تدقيق وإثبات إشعار دائن المالي غير القابل للتعديل
    """
    credit_note = models.ForeignKey(CreditNote, on_delete=models.CASCADE, related_name="audit_logs", verbose_name=_("الإشعار الدائن"))
    event_type = models.CharField(_("نوع الحدث"), max_length=50)
    old_status = models.CharField(_("الحالة السابقة"), max_length=30)
    new_status = models.CharField(_("الحالة الجديدة"), max_length=30)

    journal_reference = models.CharField(_("مرجع القيد المحاسبي"), max_length=100, blank=True, null=True)
    customer_transaction_reference = models.CharField(_("مرجع حركات أستاذ العملاء الفرعي"), max_length=100, blank=True, null=True)

    correlation_id = models.UUIDField(_("معرف التتبع Correlation UUID"), default=uuid.uuid4, editable=False)
    processed_event_id = models.CharField(_("معرف الحدث المعالج الفريد"), max_length=100, unique=True)
    audit_hash = models.CharField(_("التوقيع المشفر Canonical SHA256"), max_length=64)

    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("قيد الأستاذ"))
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        verbose_name = _("تدقيق إشعار دائن")
        verbose_name_plural = _("سجلات تدقيق الإشعارات الدائنة")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["processed_event_id"], name="unique_cn_processed_event_id")
        ]
        indexes = [
            models.Index(fields=["correlation_id", "created_at"], name="idx_cn_audit_corr_time"),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("FIN-SAL-005 Immutability Guard: CreditNoteAudit records are strictly INSERT-ONLY and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("FIN-SAL-005 Immutability Guard: CreditNoteAudit records cannot be deleted.")

    def __str__(self):
        return f"CreditNote Audit [{self.event_type}]: CN #{self.credit_note.credit_note_number} (Hash: {self.audit_hash[:8]}...)"
