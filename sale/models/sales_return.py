import uuid
import json
import hashlib
from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.conf import settings

from customer.models import Customer
from product.models import Product, Warehouse
from sale.models.sales_models import SalesOrder, DeliveryNote, DeliveryNoteItem, SalesInvoice
from financial.models.journal_entry import JournalEntry


class ReturnAuthorization(models.Model):
    """
    FIN-SAL-002 v2.0: Sales Return Authorization Model
    تصريح وإذن إرجاع مبيعات محوكم
    """
    REASON_CHOICES = (
        ("CUSTOMER_COMPLAINT", _("شكوى عميل")),
        ("WRONG_DELIVERY", _("تسليم خاطئ")),
        ("WARRANTY", _("ضمان وسياسة الاستبدال")),
        ("DAMAGED_SHIPMENT", _("تلف أثناء الشحن")),
    )

    STATUS_CHOICES = (
        ("PENDING", _("قيد الانتظار")),
        ("APPROVED", _("معتمد")),
        ("REJECTED", _("مرفوض")),
        ("EXPIRED", _("منتهي الصلاحية")),
    )

    authorization_number = models.CharField(_("رقم تصريح الإرجاع"), max_length=50, unique=True)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="return_authorizations", verbose_name=_("العميل"))
    reason_category = models.CharField(_("تصنيف سبب الإرجاع"), max_length=40, choices=REASON_CHOICES, default="CUSTOMER_COMPLAINT")
    notes = models.TextField(_("تفاصيل السبب والملاحظات"), blank=True, null=True)

    status = models.CharField(_("حالة التصريح"), max_length=20, choices=STATUS_CHOICES, default="PENDING")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("اعتمد بواسطة"))
    approved_at = models.DateTimeField(_("تاريخ الاعتماد"), null=True, blank=True)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        verbose_name = _("تصريح إرجاع مبيعات")
        verbose_name_plural = _("تصاريح إرجاع المبيعات")
        ordering = ["-created_at"]

    def __str__(self):
        return f"ReturnAuth #{self.authorization_number} - Customer: {self.customer.name} ({self.status})"


class SalesReturnHeader(models.Model):
    """
    FIN-SAL-002 v2.0: Sales Return Document Lifecycle Header Model
    مستند وقورة طلب إرجاع المبيعات مع تتبع دورة الحياة
    """
    STATUS_CHOICES = (
        ("DRAFT", _("مسودة")),
        ("SUBMITTED", _("مقدم")),
        ("UNDER_INSPECTION", _("قيد الفحص الفني")),
        ("INSPECTED", _("تم الفحص")),
        ("APPROVED", _("موافق عليه")),
        ("REJECTED", _("مرفوض")),
        ("PROCESSED", _("تم التنفيذ المحاسبي والمخزني")),
        ("CANCELLED", _("ملغي")),
    )

    return_number = models.CharField(_("رقم مستند الإرجاع"), max_length=50, unique=True)
    authorization = models.ForeignKey(ReturnAuthorization, on_delete=models.PROTECT, related_name="returns", verbose_name=_("تصريح الإرجاع المرتبط"))
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="sales_returns", verbose_name=_("العميل"))
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.PROTECT, null=True, blank=True, related_name="sales_returns", verbose_name=_("أمر البيع الأصلي"))
    delivery_note = models.ForeignKey(DeliveryNote, on_delete=models.PROTECT, related_name="sales_returns", verbose_name=_("إذن التسليم الأصلي"))
    sales_invoice = models.ForeignKey(SalesInvoice, on_delete=models.SET_NULL, null=True, blank=True, related_name="sales_returns", verbose_name=_("فاتورة المبيعات المرتبطة"))

    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="sales_returns", verbose_name=_("مخزن الاستلام الرئيسي"))
    status = models.CharField(_("حالة دورة مستند الإرجاع"), max_length=25, choices=STATUS_CHOICES, default="DRAFT")

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("أنشئ بواسطة"))
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        verbose_name = _("مستند إرجاع مبيعات")
        verbose_name_plural = _("مستندات إرجاع المبيعات")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer", "status", "created_at"]),
        ]

    def __str__(self):
        return f"SalesReturn #{self.return_number} (DN #{self.delivery_note.delivery_number}) - {self.status}"


class SalesReturnItem(models.Model):
    """
    FIN-SAL-002 v2.0: Sales Return Item Line Model linked to Delivery Note Line
    بند مستند الإرجاع المرتبط مباشرة بسطر إذن التسليم وتكلفة FIFO
    """
    return_header = models.ForeignKey(SalesReturnHeader, on_delete=models.CASCADE, related_name="items", verbose_name=_("مستند الإرجاع"))
    delivery_item = models.ForeignKey(DeliveryNoteItem, on_delete=models.PROTECT, related_name="return_items", verbose_name=_("سطر إذن التسليم الأصلي"))
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="return_items", verbose_name=_("المنتج"))

    requested_qty = models.DecimalField(_("الكمية المطلوبة للإرجاع"), max_digits=15, decimal_places=4)
    approved_qty = models.DecimalField(_("الكمية الموافق عليها"), max_digits=15, decimal_places=4, default=Decimal("0.0000"))
    inspected_qty = models.DecimalField(_("الكمية المفحوصة فعلياً"), max_digits=15, decimal_places=4, default=Decimal("0.0000"))
    restored_qty = models.DecimalField(_("الكمية المعادة للمخزون الصالح"), max_digits=15, decimal_places=4, default=Decimal("0.0000"))
    unit_cost_restored = models.DecimalField(_("تكلفة الوحدة المرتجعة المستردة (FIFO Cost)"), max_digits=15, decimal_places=4, default=Decimal("0.0000"))

    class Meta:
        verbose_name = _("بند مستند إرجاع المبيعات")
        verbose_name_plural = _("بنود مستندات إرجاع المبيعات")

    def __str__(self):
        return f"ReturnItem #{self.id}: {self.product.name} ({self.requested_qty} PCS)"


class SalesReturnInspection(models.Model):
    """
    FIN-SAL-002 v2.0: Quality Inspection Log Model
    سجل التفتيش والفحص الفني لجودة البضاعة المرتجعة (صالح / تالف / كهنة)
    """
    RESULT_CHOICES = (
        ("GOOD", _("سليم قابل للبيع")),
        ("DAMAGED", _("تالف يوجه للمحجر/التخريد")),
        ("SCRAP_REJECTED", _("مرفوض ومرفوض استلامه")),
    )

    DISPOSITION_CHOICES = (
        ("QUARANTINE", _("تحويل لمخزن المحجر")),
        ("SCRAP", _("تخريد وتخفيض مخزون")),
        ("WRITE_OFF", _("إعدام خسارة")),
        ("RETURN_TO_VENDOR", _("إرجاع للمورد")),
    )

    return_item = models.ForeignKey(SalesReturnItem, on_delete=models.CASCADE, related_name="inspections", verbose_name=_("بند الإرجاع"))
    inspection_result = models.CharField(_("نتيجة الفحص الفني"), max_length=20, choices=RESULT_CHOICES, default="GOOD")

    good_qty = models.DecimalField(_("الكمية السليمة"), max_digits=15, decimal_places=4, default=Decimal("0.0000"))
    damaged_qty = models.DecimalField(_("الكمية التالفة"), max_digits=15, decimal_places=4, default=Decimal("0.0000"))
    scrap_qty = models.DecimalField(_("الكمية المرفوضة/المكهنة"), max_digits=15, decimal_places=4, default=Decimal("0.0000"))

    unit_cost_restored = models.DecimalField(_("تكلفة الوحدة من FIFO"), max_digits=15, decimal_places=4, default=Decimal("0.0000"))
    damaged_disposition = models.CharField(_("قرار التعامل مع التالف"), max_length=30, choices=DISPOSITION_CHOICES, default="QUARANTINE")

    inspected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("فحص بواسطة"))
    inspected_at = models.DateTimeField(_("تاريخ الفحص"), auto_now_add=True)

    class Meta:
        verbose_name = _("فحص جودة مرتجع مبيعات")
        verbose_name_plural = _("سجلات فحص جودة مرتجعات المبيعات")
        ordering = ["-inspected_at"]

    def __str__(self):
        return f"Inspection #{self.id} [{self.inspection_result}]: Good {self.good_qty} / Damaged {self.damaged_qty}"


class ReturnCostTrace(models.Model):
    """
    FIN-SAL-002 v2.0: Return Cost Traceability Model
    سجل تتبع واسترجاع تكلفة الوحدة من طبقات FIFO التاريخية
    """
    return_item = models.ForeignKey(SalesReturnItem, on_delete=models.CASCADE, related_name="cost_traces", verbose_name=_("بند الإرجاع"))
    original_stock_movement_id = models.IntegerField(_("معرف حركة الصرف الأصلي"))
    delivery_document_number = models.CharField(_("رقم إذن التسليم الأصلي"), max_length=100)
    fifo_layer_id = models.IntegerField(_("معرف طبقة FIFO"), null=True, blank=True)

    original_quantity = models.DecimalField(_("الكمية الأصلية المسلمة"), max_digits=15, decimal_places=4)
    returned_quantity = models.DecimalField(_("الكمية المرتجعة"), max_digits=15, decimal_places=4)
    original_unit_cost = models.DecimalField(_("تكلفة الوحدة الأصلية"), max_digits=15, decimal_places=4)
    restored_value = models.DecimalField(_("إجمالي القيمة المستردة (EGP)"), max_digits=15, decimal_places=2)

    class Meta:
        verbose_name = _("سجل تتبع تكلفة المرتجع FIFO")
        verbose_name_plural = _("سجلات تتبع تكاليف المرتجعات FIFO")

    def __str__(self):
        return f"CostTrace for Item #{self.return_item.id}: Cost {self.original_unit_cost} x {self.returned_quantity} = {self.restored_value} EGP"


class SalesReturnAudit(models.Model):
    """
    FIN-SAL-002 v2.0: Immutable Sales Return Audit Evidence Log Model
    سجل تدقيق وإثبات الإرجاع وتغييرات الحالات غير القابل للتعديل
    """
    return_header = models.ForeignKey(SalesReturnHeader, on_delete=models.CASCADE, related_name="audit_logs", verbose_name=_("مستند الإرجاع"))
    event_type = models.CharField(_("نوع الحدث"), max_length=50)
    old_status = models.CharField(_("الحالة السابقة"), max_length=30)
    new_status = models.CharField(_("الحالة الجديدة"), max_length=30)

    inspection_result = models.CharField(_("نتيجة الفحص الفني"), max_length=30, blank=True, null=True)
    movement_reference = models.CharField(_("مرجع حركة المخزون"), max_length=100, blank=True, null=True)
    journal_reference = models.CharField(_("مرجع القيد المحاسبي"), max_length=100, blank=True, null=True)

    correlation_id = models.UUIDField(_("معرف التتبع Correlation UUID"), default=uuid.uuid4, editable=False)
    processed_event_id = models.CharField(_("معرف الحدث المعالج الفريد"), max_length=100, unique=True)
    audit_hash = models.CharField(_("التوقيع المشفر Canonical SHA256"), max_length=64)

    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("قيد الأستاذ"))
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        verbose_name = _("تدقيق مرتجع المبيعات")
        verbose_name_plural = _("سجلات تدقيق مرتجعات المبيعات")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["processed_event_id"], name="unique_return_processed_event_id")
        ]
        indexes = [
            models.Index(fields=["correlation_id", "created_at"], name="idx_sal_ret_audit_corr_time"),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("FIN-SAL-002 Immutability Guard: SalesReturnAudit records are strictly INSERT-ONLY and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("FIN-SAL-002 Immutability Guard: SalesReturnAudit records cannot be deleted.")

    def __str__(self):
        return f"SalesReturn Audit [{self.event_type}]: Return #{self.return_header.return_number} (Hash: {self.audit_hash[:8]}...)"
