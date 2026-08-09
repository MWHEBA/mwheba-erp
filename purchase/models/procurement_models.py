from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from product.models.product_core import Product, ProductVariant, Unit
from product.models.stock_management import Warehouse
from financial.models.journal_entry import JournalEntry


class PurchaseOrder(models.Model):
    """
    نموذج أمر الشراء المعتمد (Purchase Order - FIN-PUR-001)
    التزام تشغيلي محوكم بدورة اعتماد موافقات
    """
    STATUS_CHOICES = (
        ("DRAFT", _("مسودة")),
        ("SUBMITTED", _("مقدم للاعتماد")),
        ("APPROVED", _("معتمد")),
        ("PARTIALLY_RECEIVED", _("مستلم جزئياً")),
        ("FULLY_RECEIVED", _("مستلم بالكامل")),
        ("CANCELLED", _("ملغى")),
    )
    COST_SOURCE_POLICIES = (
        ("PO_PRICE", _("سعر أمر الشراء الأصلي")),
        ("LIST_PRICE", _("سعر قائمة المورد")),
        ("CUSTOM", _("سعر مخصص")),
    )

    order_number = models.CharField(_("رقم أمر الشراء"), max_length=50, unique=True)
    supplier = models.ForeignKey(
        "supplier.Supplier",
        on_delete=models.PROTECT,
        verbose_name=_("المورد"),
        related_name="purchase_orders"
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        verbose_name=_("المستودع المستهدف"),
        related_name="purchase_orders"
    )
    order_date = models.DateField(_("تاريخ أمر الشراء"))
    delivery_due_date = models.DateField(_("تاريخ التوريد المتوقع"), null=True, blank=True)

    currency = models.CharField(_("العملة"), max_length=10, blank=True, null=True)
    exchange_rate = models.DecimalField(_("سعر الصرف"), max_digits=10, decimal_places=4, default=Decimal("1.0000"))
    cost_source_policy = models.CharField(_("سياسة سعر التكلفة"), max_length=20, choices=COST_SOURCE_POLICIES, default="PO_PRICE")

    status = models.CharField(_("الحالة"), max_length=30, choices=STATUS_CHOICES, default="DRAFT")

    total_amount = models.DecimalField(_("الإجمالي بعملة الفاتورة"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    functional_amount = models.DecimalField(_("الإجمالي بالعملة الوظيفية"), max_digits=15, decimal_places=2, default=Decimal("0.00"))

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_("أنشئ بواسطة"),
        related_name="purchase_orders_created"
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_("اعتمد بواسطة"),
        null=True,
        blank=True,
        related_name="purchase_orders_approved"
    )
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        verbose_name = _("أمر شراء")
        verbose_name_plural = _("أوامر الشراء")
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"PO #{self.order_number} - {self.supplier.name} ({self.get_status_display()})"


class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, verbose_name=_("المنتج"))
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, null=True, blank=True, verbose_name=_("النوع"))
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, null=True, blank=True, verbose_name=_("وحدة القياس"))

    ordered_qty = models.DecimalField(_("الكمية المطلوبة"), max_digits=15, decimal_places=4)
    received_qty = models.DecimalField(_("الكمية المستلمة فعلياً"), max_digits=15, decimal_places=4, default=Decimal("0.0000"))
    billed_qty = models.DecimalField(_("الكمية المفوترة"), max_digits=15, decimal_places=4, default=Decimal("0.0000"))

    unit_price = models.DecimalField(_("سعر الوحدة المحدد في PO"), max_digits=15, decimal_places=4)
    total_price = models.DecimalField(_("إجمالي السطر"), max_digits=15, decimal_places=2)

    class Meta:
        verbose_name = _("بند أمر شراء")
        verbose_name_plural = _("بنود أوامر الشراء")


class GoodsReceivedNote(models.Model):
    """
    إذن الاستلام الفعلي بالمخزن (Goods Received Note - GRN - FIN-PUR-002)
    ينتج حركة أستاذ المخزون وقيد الاستلام المحاسبي 11040/20150 GRNI
    """
    STATUS_CHOICES = (
        ("DRAFT", _("مسودة")),
        ("SUBMITTED", _("مقدم للاعتماد")),
        ("APPROVED", _("معتمد")),
        ("POSTED", _("مرحل مخزنياً ومالياً")),
        ("REVERSED", _("معكوس")),
    )
    VALID_TRANSITIONS = {
        "DRAFT": ["SUBMITTED", "POSTED"],
        "SUBMITTED": ["APPROVED", "DRAFT"],
        "APPROVED": ["POSTED", "DRAFT"],
        "POSTED": ["REVERSED"],
        "REVERSED": [],
    }

    grn_number = models.CharField(_("رقم إذن الاستلام GRN"), max_length=50, unique=True)
    purchase = models.ForeignKey("purchase.Purchase", on_delete=models.SET_NULL, null=True, blank=True, related_name="grns", verbose_name=_("فاتورة المشتريات"))
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name="grns")
    supplier = models.ForeignKey("supplier.Supplier", on_delete=models.PROTECT, related_name="grns")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="grns")

    received_date = models.DateTimeField(_("تاريخ الاستلام الفعلي"), auto_now_add=True)
    supplier_delivery_note_ref = models.CharField(_("رقم إذن تسليم المورد"), max_length=100, blank=True)

    status = models.CharField(_("الحالة"), max_length=20, choices=STATUS_CHOICES, default="DRAFT")
    currency = models.CharField(_("العملة"), max_length=10, blank=True, null=True)
    exchange_rate = models.DecimalField(_("سعر الصرف"), max_digits=18, decimal_places=6, default=Decimal("1.000000"))
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, null=True, blank=True)
    idempotency_key = models.CharField(_("مفتاح منع التكرار"), max_length=100, db_index=True, blank=True)

    class Meta:
        verbose_name = _("إذن استلام مخزني GRN")
        verbose_name_plural = _("أذون الاستلام المخزنية GRN")
        ordering = ["-received_date", "-id"]

    def __str__(self):
        po_info = f" for PO #{self.purchase_order.order_number}" if self.purchase_order else ""
        return f"GRN #{self.grn_number}{po_info} ({self.get_status_display()})"

    def clean(self):
        super().clean()
        if self.pk:
            old_inst = GoodsReceivedNote.objects.filter(pk=self.pk).values("status").first()
            if old_inst:
                old_status = old_inst["status"]
                if old_status in ["POSTED", "REVERSED"] and self.status == old_status:
                    from django.core.exceptions import ValidationError
                    raise ValidationError(_("لا يمكن تعديل إذن استلام مرحل أو معكوس."))
                if old_status != self.status:
                    allowed = self.VALID_TRANSITIONS.get(old_status, [])
                    if self.status not in allowed:
                        from django.core.exceptions import ValidationError
                        raise ValidationError(_(f"انتقال غير مسموح من {old_status} إلى {self.status}."))

    def save(self, *args, **kwargs):
        if not self.currency:
            from financial.services.exchange_rate_service import ExchangeRateService
            func_curr = ExchangeRateService.get_functional_currency()
            if func_curr:
                self.currency = func_curr.code
        if self.pk:
            old_status = GoodsReceivedNote.objects.filter(pk=self.pk).values_list("status", flat=True).first()
            if old_status in ["POSTED", "REVERSED"] and self.status == old_status and not kwargs.get("update_fields"):
                from django.core.exceptions import ValidationError
                raise ValidationError(_("لا يمكن تعديل إذن استلام مرحل أو معكوس."))
        super().save(*args, **kwargs)


class GoodsReceivedNoteItem(models.Model):
    grn = models.ForeignKey(GoodsReceivedNote, on_delete=models.CASCADE, related_name="items")
    po_item = models.ForeignKey(PurchaseOrderItem, on_delete=models.PROTECT, null=True, blank=True, related_name="grn_items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)

    received_qty = models.DecimalField(_("الكمية المستلمة"), max_digits=15, decimal_places=4)
    billed_qty = models.DecimalField(_("الكمية المفوترة من هذا الإذن"), max_digits=15, decimal_places=4, default=Decimal("0.0000"))
    unit_price = models.DecimalField(_("تكلفة الاستلام للوحدة (PO Price)"), max_digits=15, decimal_places=4)
    total_cost = models.DecimalField(_("إجمالي تكلفة الاستلام"), max_digits=15, decimal_places=2)

    class Meta:
        verbose_name = _("بند إذن استلام GRN")
        verbose_name_plural = _("بنود أذون الاستلام GRN")


class SupplierBill(models.Model):
    """
    نموذج فاتورة المورد (Supplier Bill - FIN-PUR-004)
    يحسب الاستحقاق المحاسبي ذمم الموردين AP 20100 وإخلاء حـ/ GRNI 20150
    """
    INVOICE_TYPES = (
        ("GOODS", _("فاتورة بضائع ومخزون - تتطلب GRN معتمد")),
        ("SERVICE", _("فاتورة خدمات مباشرة")),
        ("EXPENSE", _("فاتورة مصاريف تشغيلية")),
    )
    BILL_TYPES = (
        ("INVENTORY_INVOICE", _("فاتورة بضائع ومخزون (GRN Mandatory)")),
        ("SERVICE_INVOICE", _("فاتورة خدمات ومصروفات")),
        ("ADVANCE_INVOICE", _("فاتورة دفعة مقدمة")),
    )
    STATUS_CHOICES = (
        ("DRAFT", _("مسودة")),
        ("POSTED", _("مرحلة ومرحلة للأستاذ")),
        ("PAID", _("مدفوعة ومسواة")),
        ("CANCELLED", _("ملغاة")),
    )

    bill_number = models.CharField(_("رقم الفاتورة في النظام"), max_length=50, unique=True)
    supplier = models.ForeignKey("supplier.Supplier", on_delete=models.PROTECT, related_name="supplier_bills")
    supplier_bill_number = models.CharField(_("رقم فاتورة المورد الأصلي"), max_length=100)

    invoice_type = models.CharField(_("نوع الفاتورة الحوكمي"), max_length=20, choices=INVOICE_TYPES, default="GOODS")
    bill_type = models.CharField(_("نوع الفاتورة"), max_length=30, choices=BILL_TYPES, default="INVENTORY_INVOICE")
    bill_date = models.DateField(_("تاريخ الفاتورة"))
    due_date = models.DateField(_("تاريخ الاستحقاق"))

    currency = models.CharField(_("العملة"), max_length=10, blank=True, null=True)
    exchange_rate = models.DecimalField(_("سعر الصرف"), max_digits=10, decimal_places=4, default=Decimal("1.0000"))

    total_amount = models.DecimalField(_("إجمالي الفاتورة بعملة المورد"), max_digits=15, decimal_places=2)
    functional_amount = models.DecimalField(_("إجمالي الفاتورة بالعملة الوظيفية"), max_digits=15, decimal_places=2)

    status = models.CharField(_("الحالة"), max_length=20, choices=STATUS_CHOICES, default="DRAFT")

    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, null=True, blank=True)
    idempotency_key = models.CharField(_("مفتاح منع التكرار"), max_length=100, db_index=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("فاتورة مورد")
        verbose_name_plural = _("فواتير الموردين")
        unique_together = ("supplier", "supplier_bill_number")
        ordering = ["-bill_date", "-id"]

    def __str__(self):
        return f"SupplierBill #{self.bill_number} (Ref: {self.supplier_bill_number}) - {self.supplier.name}"


class SupplierBillItem(models.Model):
    bill = models.ForeignKey(SupplierBill, on_delete=models.CASCADE, related_name="items")
    grn_item = models.ForeignKey(GoodsReceivedNoteItem, on_delete=models.PROTECT, null=True, blank=True, related_name="bill_items")
    po_item = models.ForeignKey(PurchaseOrderItem, on_delete=models.PROTECT, null=True, blank=True, related_name="bill_items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, null=True, blank=True)

    billed_qty = models.DecimalField(_("الكمية المفوترة"), max_digits=15, decimal_places=4)
    unit_price = models.DecimalField(_("سعر الوحدة في الفاتورة"), max_digits=15, decimal_places=4)
    total_amount = models.DecimalField(_("إجمالي مبلغ السطر"), max_digits=15, decimal_places=2)

    ppv_variance = models.DecimalField(_("مبلغ فروق أسعار الشراء (PPV Variance)"), max_digits=15, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        verbose_name = _("بند فاتورة مورد")
        verbose_name_plural = _("بنود فواتير الموردين")


class BillLineMatching(models.Model):
    """
    نموذج المطابقة الثلاثية الحاكمة على مستوى الأسطر (Line-Level 3-Way Matching Allocation - FIN-PUR-005)
    """
    bill_item = models.ForeignKey(SupplierBillItem, on_delete=models.CASCADE, related_name="line_matchings")
    grn_item = models.ForeignKey(GoodsReceivedNoteItem, on_delete=models.PROTECT, related_name="line_matchings")

    matched_qty = models.DecimalField(_("الكمية المطابقة"), max_digits=15, decimal_places=4)
    po_unit_price = models.DecimalField(_("سعر أمر الشراء الأصلي"), max_digits=15, decimal_places=4)
    bill_unit_price = models.DecimalField(_("سعر الفاتورة الفعلي"), max_digits=15, decimal_places=4)
    price_variance = models.DecimalField(_("فرق السعر الفعلي (PPV)"), max_digits=15, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("مطابقة سطر فاتورة مع إذن استلام")
        verbose_name_plural = _("مطابقات أسطر الفواتير")


class ApprovalRule(models.Model):
    rule_name = models.CharField(_("اسم القاعدة"), max_length=100)
    min_amount = models.DecimalField(_("الحد الأدنى للقيمة"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    max_amount = models.DecimalField(_("الحد الأقصى للقيمة"), max_digits=15, decimal_places=2, default=Decimal("999999999.00"))
    approver_role = models.CharField(_("دور المعتمد"), max_length=50)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("قاعدة اعتماد أمر شراء")
        verbose_name_plural = _("قواعد اعتماد أوامر الشراء")


class ApprovalRequest(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="approval_requests")
    rule = models.ForeignKey(ApprovalRule, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, default="PENDING")
    comments = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("طلب اعتماد أمر شراء")
        verbose_name_plural = _("طلبات اعتماد أوامر الشراء")
