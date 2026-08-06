import uuid
import hashlib
from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.conf import settings

from supplier.models import Supplier, SupplierTransaction


class ImmutableSupplierAllocationAuditManager(models.Manager):
    def update(self, **kwargs):
        raise ValueError("FIN-AP-004 Immutability Guard: Bulk UPDATE operations on SupplierAllocationAudit are strictly prohibited.")

    def delete(self):
        raise ValueError("FIN-AP-004 Immutability Guard: Bulk DELETE operations on SupplierAllocationAudit are strictly prohibited.")


class SupplierAllocationAudit(models.Model):
    """
    FIN-AP-004: Supplier Allocation Audit Evidence Model
    سجل تدقيق وإثبات توزيعات سداد مستحقات الموردين غير القابل للتعديل
    """
    objects = ImmutableSupplierAllocationAuditManager()

    TYPE_CHOICES = (
        ("PAYMENT_TO_BILL", _("سداد فاتورة مشتريات")),
        ("ADVANCE_TO_BILL", _("تسوية دفعة مقدمة")),
        ("DEBIT_NOTE_TO_BILL", _("تسوية إشعار خصم/مردودات")),
        ("REVERSAL", _("عكس توزيع سداد")),
    )

    STATUS_CHOICES = (
        ("APPLIED", _("مطبق")),
        ("REVERSED", _("معكوس")),
    )

    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="allocation_audits", verbose_name=_("المورد"))
    allocation_reference = models.CharField(_("مرجع التوزيع الفريد"), max_length=100, unique=True, default=uuid.uuid4)
    payment_transaction = models.ForeignKey(SupplierTransaction, on_delete=models.PROTECT, related_name="payment_allocations", verbose_name=_("معاملة التحصيل/الإشعار"))
    invoice_transaction = models.ForeignKey(SupplierTransaction, on_delete=models.PROTECT, related_name="bill_allocations", verbose_name=_("معاملة الفاتورة المستهدفة"))

    source_document_type = models.CharField(_("نوع المستند المصدر"), max_length=50, blank=True, null=True)
    source_document_number = models.CharField(_("رقم المستند المصدر"), max_length=100, blank=True, null=True)
    target_document_type = models.CharField(_("نوع المستند المستهدف"), max_length=50, blank=True, null=True)
    target_document_number = models.CharField(_("رقم المستند المستهدف"), max_length=100, blank=True, null=True)

    allocation_type = models.CharField(_("نوع التوزيع"), max_length=30, choices=TYPE_CHOICES, default="ADVANCE_TO_BILL")
    allocated_amount = models.DecimalField(_("المبلغ المخصص بالعملة الأصلي"), max_digits=15, decimal_places=2)
    allocation_currency = models.CharField(_("عملة التوزيع"), max_length=3, default="EGP")
    exchange_rate = models.DecimalField(_("سعر الصرف"), max_digits=12, decimal_places=6, default=Decimal("1.000000"))
    functional_amount = models.DecimalField(_("المبلغ الوظيفي المخصص (EGP)"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    realized_fx_difference = models.DecimalField(_("فروق عملة محققة (EGP)"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    allocation_status = models.CharField(_("حالة التوزيع"), max_length=20, choices=STATUS_CHOICES, default="APPLIED")
    reversed_audit = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="reversals", verbose_name=_("سجل التدقيق المعكوس"))
    allocation_date = models.DateField(_("تاريخ التوزيع"), default=timezone.now)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("أنشئ بواسطة"))
    evidence_hash = models.CharField(_("توقيع إثبات التوزيع SHA256"), max_length=64, blank=True, null=True)
    created_at = models.DateTimeField(_("تاريخ التسجيل"), auto_now_add=True)

    class Meta:
        verbose_name = _("تدقيق توزيعات سداد الموردين")
        verbose_name_plural = _("سجلات تدقيق توزيعات سداد الموردين")
        ordering = ["-allocation_date", "-created_at"]
        indexes = [
            models.Index(fields=["supplier", "allocation_date"]),
            models.Index(fields=["allocation_reference", "created_at"], name="idx_supp_alloc_corr_time"),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("FIN-AP-004 Immutability Guard: SupplierAllocationAudit records are strictly INSERT-ONLY and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("FIN-AP-004 Immutability Guard: SupplierAllocationAudit records cannot be deleted.")

    def __str__(self):
        return f"Supplier Allocation Audit [{self.allocation_type}]: {self.source_document_number} -> {self.target_document_number} ({self.allocated_amount} {self.allocation_currency})"
