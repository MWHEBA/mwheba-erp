from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from client.models import Customer
from product.models.product_core import Product, Unit
from product.models.stock_management import Warehouse
from financial.models.journal_entry import JournalEntry
from sale.models.pricing import PriceList


class SalesOrder(models.Model):
    """
    FIN-SAL-001: Sales Order Model
    أمر البيع التجاري الحاكم بدورة العمل والاعتمادات
    """
    STATUS_CHOICES = (
        ("DRAFT", _("مسودة")),
        ("PENDING_APPROVAL", _("معلق الاعتماد")),
        ("APPROVED", _("معتمد")),
        ("CONFIRMED", _("مؤكد")),
        ("PARTIALLY_DELIVERED", _("مسلم جزئياً")),
        ("FULLY_DELIVERED", _("مسلم بالكامل")),
        ("PARTIALLY_INVOICED", _("مفوتر جزئياً")),
        ("INVOICED", _("مفوتر بالكامل")),
        ("CANCELLED", _("ملغى")),
    )

    order_number = models.CharField(_("رقم أمر البيع"), max_length=50, unique=True)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="sales_orders", verbose_name=_("العميل"))
    quotation_reference = models.ForeignKey("sale.Quotation", on_delete=models.SET_NULL, null=True, blank=True, related_name="sales_orders", verbose_name=_("عرض السعر المرتبط"))
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="sales_orders", verbose_name=_("المخزن"))
    order_date = models.DateField(_("تاريخ أمر البيع"))
    price_list = models.ForeignKey(PriceList, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("قائمة الأسعار"))
    approval_request = models.ForeignKey("financial.EnterpriseApprovalRequest", on_delete=models.SET_NULL, null=True, blank=True, related_name="sales_orders", verbose_name=_("طلب الاعتماد المؤسسي"))

    # Multi-Currency Foundation (IAS 21)
    currency = models.CharField(_("العملة"), max_length=3, default="EGP")
    exchange_rate = models.DecimalField(_("سعر الصرف"), max_digits=12, decimal_places=6, default=Decimal("1.000000"))

    status = models.CharField(_("الحالة"), max_length=30, choices=STATUS_CHOICES, default="DRAFT")
    total_amount = models.DecimalField(_("الإجمالي بعملة الفاتورة"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    functional_amount = models.DecimalField(_("الإجمالي بالعملة الوظيفية"), max_digits=15, decimal_places=2, default=Decimal("0.00"))

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sales_orders_created", verbose_name=_("أنشئ بواسطة"))
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        verbose_name = _("أمر بيع")
        verbose_name_plural = _("أوامر البيع")
        ordering = ["-order_date", "-id"]

    def __str__(self):
        return f"{self.order_number} - {self.customer.name} ({self.status})"


class SalesOrderItem(models.Model):
    """
    FIN-SAL-001: Sales Order Line Item Model
    """
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name="items", verbose_name=_("أمر البيع"))
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="sales_order_items", verbose_name=_("المنتج"))
    ordered_qty = models.DecimalField(_("الكمية المطلوبة"), max_digits=15, decimal_places=4)
    delivered_qty = models.DecimalField(_("الكمية المسلمة"), max_digits=15, decimal_places=4, default=Decimal("0.0000"))
    invoiced_qty = models.DecimalField(_("الكمية المفوترة"), max_digits=15, decimal_places=4, default=Decimal("0.0000"))
    unit_price = models.DecimalField(_("سعر الوحدة الأصلي"), max_digits=15, decimal_places=2)
    discount_percentage = models.DecimalField(_("نسبة الخصم %"), max_digits=5, decimal_places=2, default=Decimal("0.00"))
    line_total = models.DecimalField(_("إجمالي السطر"), max_digits=15, decimal_places=2)
    price_snapshot = models.JSONField(_("لقطة التسعير المحوكمة"), default=dict, blank=True)

    class Meta:
        verbose_name = _("بند أمر بيع")
        verbose_name_plural = _("بنود أوامر البيع")

    def __str__(self):
        return f"{self.product.name} x {self.ordered_qty}"


class DeliveryNote(models.Model):
    """
    FIN-SAL-001: Delivery Note Model (إذن التسليم المخزني)
    حدث تسليم البضاعة الفعلي وتوليد قيد التكلفة (Dr. COGS / Cr. Inventory)
    """
    STATUS_CHOICES = (
        ("DRAFT", _("مسودة")),
        ("DELIVERED", _("تم التسليم")),
        ("CANCELLED", _("ملغى")),
    )

    delivery_number = models.CharField(_("رقم إذن التسليم"), max_length=50, unique=True)
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.PROTECT, related_name="delivery_notes", verbose_name=_("أمر البيع"))
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="delivery_notes", verbose_name=_("العميل"))
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="delivery_notes", verbose_name=_("المخزن"))
    delivery_date = models.DateField(_("تاريخ التسليم"))

    status = models.CharField(_("الحالة"), max_length=20, choices=STATUS_CHOICES, default="DRAFT")
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("قيد التكلفة (COGS)"))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_("أنشئ بواسطة"))
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        verbose_name = _("إذن تسليم مخزني")
        verbose_name_plural = _("أذون التسليم المخزنية")
        ordering = ["-delivery_date", "-id"]

    def __str__(self):
        return f"{self.delivery_number} - {self.customer.name}"


class DeliveryNoteItem(models.Model):
    """
    FIN-SAL-001: Delivery Note Item Model
    """
    delivery_note = models.ForeignKey(DeliveryNote, on_delete=models.CASCADE, related_name="items", verbose_name=_("إذن التسليم"))
    so_item = models.ForeignKey(SalesOrderItem, on_delete=models.PROTECT, related_name="delivery_items", verbose_name=_("بند أمر البيع الأصلي"))
    delivered_qty = models.DecimalField(_("الكمية المسلمة"), max_digits=15, decimal_places=4)
    unit_cost = models.DecimalField(_("سعر التكلفة (FIFO)"), max_digits=15, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        verbose_name = _("بند إذن تسليم")
        verbose_name_plural = _("بنود أذون التسليم")

    def __str__(self):
        return f"{self.so_item.product.name} x {self.delivered_qty}"


class SalesInvoice(models.Model):
    """
    FIN-SAL-001: Sales Invoice Model
    فاتورة المبيعات المالية وتوليد قيد الإيراد (Dr. AR / Cr. Sales Revenue)
    """
    STATUS_CHOICES = (
        ("DRAFT", _("مسودة")),
        ("POSTED", _("مرحلة")),
        ("PAID", _("مسددة بالكامل")),
        ("CANCELLED", _("ملغاة")),
    )

    invoice_number = models.CharField(_("رقم فاتورة المبيعات"), max_length=50, unique=True)
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.PROTECT, related_name="invoices", verbose_name=_("أمر البيع"))
    delivery_note = models.ForeignKey(DeliveryNote, on_delete=models.SET_NULL, null=True, blank=True, related_name="invoices", verbose_name=_("إذن التسليم المرتبط"))
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="sales_invoices", verbose_name=_("العميل"))
    invoice_date = models.DateField(_("تاريخ الفاتورة"))
    due_date = models.DateField(_("تاريخ الاستحقاق"))

    currency = models.CharField(_("العملة"), max_length=3, default="EGP")
    exchange_rate = models.DecimalField(_("سعر الصرف"), max_digits=12, decimal_places=6, default=Decimal("1.000000"))

    status = models.CharField(_("الحالة"), max_length=20, choices=STATUS_CHOICES, default="DRAFT")
    total_amount = models.DecimalField(_("الإجمالي بالعملة المخصصة"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    functional_amount = models.DecimalField(_("الإجمالي بالعملة الوظيفية"), max_digits=15, decimal_places=2, default=Decimal("0.00"))

    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("القيد المحاسبي للإيراد"))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_("أنشئ بواسطة"))
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        verbose_name = _("فاتورة مبيعات")
        verbose_name_plural = _("فواتير المبيعات")
        unique_together = ("customer", "invoice_number")

    def __str__(self):
        return f"{self.invoice_number} - {self.customer.name} ({self.total_amount} {self.currency})"


class SalesInvoiceItem(models.Model):
    """
    FIN-SAL-001: Sales Invoice Item Model with Full Source Line Traceability
    """
    sales_invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE, related_name="items", verbose_name=_("فاتورة المبيعات"))
    dn_item = models.ForeignKey(DeliveryNoteItem, on_delete=models.PROTECT, null=True, blank=True, related_name="invoice_items", verbose_name=_("بند إذن التسليم"))
    so_item = models.ForeignKey(SalesOrderItem, on_delete=models.PROTECT, related_name="invoice_items", verbose_name=_("بند أمر البيع"))
    billed_qty = models.DecimalField(_("الكمية المفوترة"), max_digits=15, decimal_places=4)
    unit_price = models.DecimalField(_("سعر الوحدة"), max_digits=15, decimal_places=2)
    line_total = models.DecimalField(_("إجمالي السطر"), max_digits=15, decimal_places=2)

    class Meta:
        verbose_name = _("بند فاتورة مبيعات")
        verbose_name_plural = _("بنود فواتير المبيعات")

    def __str__(self):
        return f"{self.so_item.product.name} x {self.billed_qty} @ {self.unit_price}"
