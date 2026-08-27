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


SHIPPING_METHOD_CHOICES = (
    ("PICKUP", _("استلام من المخزن")),
    ("COMPANY_FLEET", _("أسطول سيارات الشركة")),
    ("COURIER", _("شركة شحن خارجية")),
)


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
    salesman = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="sales_orders_assigned", verbose_name=_("مسؤول المبيعات"))
    cost_center = models.ForeignKey("financial.CostCenter", on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("مركز التكلفة"))
    approval_request = models.ForeignKey("financial.EnterpriseApprovalRequest", on_delete=models.SET_NULL, null=True, blank=True, related_name="sales_orders", verbose_name=_("طلب الاعتماد المؤسسي"))

    # اللوجستيات والشحن
    expected_delivery_date = models.DateField(_("تاريخ التسليم المتوقع"), null=True, blank=True)
    reservation_expiry_date = models.DateField(_("تاريخ انتهاء مهلة الحجز"), null=True, blank=True)
    shipping_method = models.CharField(_("طريقة التوصيل"), max_length=20, choices=SHIPPING_METHOD_CHOICES, default="PICKUP")
    shipping_address = models.TextField(_("عنوان التسليم الفعلي"), blank=True, null=True)

    # Multi-Currency Foundation (IAS 21)
    currency = models.CharField(_("العملة"), max_length=3, default="EGP")
    exchange_rate = models.DecimalField(_("سعر الصرف"), max_digits=12, decimal_places=6, default=Decimal("1.000000"))

    # التفصيل المالي
    subtotal = models.DecimalField(_("المجموع الفرعي"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    discount_amount = models.DecimalField(_("قيمة الخصم"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    discount_type = models.CharField(_("نوع الخصم"), max_length=10, default="fixed")
    adjustment_name = models.CharField(_("اسم التسوية"), max_length=100, blank=True, null=True)
    adjustment_amount = models.DecimalField(_("مبلغ التسوية"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    tax_amount = models.DecimalField(_("الضريبة التقديرية (VAT)"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    vat_rate = models.DecimalField(_("نسبة القيمة المضافة %"), max_digits=5, decimal_places=2, default=Decimal("14.00"))
    wht_active = models.BooleanField(_("خصم المنبع نشط"), default=False)
    wht_rate = models.DecimalField(_("نسبة خصم المنبع %"), max_digits=5, decimal_places=2, default=Decimal("1.00"))
    wht_amount = models.DecimalField(_("مبلغ خصم المنبع"), max_digits=15, decimal_places=2, default=Decimal("0.00"))

    status = models.CharField(_("الحالة"), max_length=30, choices=STATUS_CHOICES, default="DRAFT")
    total_amount = models.DecimalField(_("الإجمالي بعملة الفاتورة"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    functional_amount = models.DecimalField(_("الإجمالي بالعملة الوظيفية"), max_digits=15, decimal_places=2, default=Decimal("0.00"))

    # الشروط والدفعة المقدمة والحقول المخصصة
    required_down_payment = models.DecimalField(_("الدفعة المقدمة المطلوبة"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    down_payment_type = models.CharField(_("نوع الدفعة المقدمة"), max_length=15, choices=(("fixed", _("مبلغ ثابت")), ("percentage", _("نسبة مئوية"))), default="fixed")
    down_payment_override = models.BooleanField(_("تجاوز شرط الدفعة المقدمة إدارياً"), default=False)
    down_payment_override_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="sales_orders_overridden", verbose_name=_("تم التجاوز بواسطة"))
    down_payment_override_reason = models.TextField(_("سبب التجاوز الإداري"), blank=True, null=True)
    notes = models.TextField(_("الشروط والملاحظات"), blank=True, null=True)
    custom_fields = models.JSONField(_("الحقول الإضافية"), default=list, blank=True)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sales_orders_created", verbose_name=_("أنشئ بواسطة"))
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        verbose_name = _("أمر بيع")
        verbose_name_plural = _("أوامر البيع")
        ordering = ["-order_date", "-id"]

    @property
    def currency_code(self) -> str:
        """كود العملة القياسي (ديناميكي 100% من جدول العملات)"""
        from financial.models import Currency
        raw = str(self.currency or "").strip()
        if raw.isdigit():
            c = Currency.objects.filter(id=int(raw)).first()
            if c:
                return c.code
        elif raw:
            c = Currency.objects.filter(code__iexact=raw).first()
            if c:
                return c.code
        func_curr = Currency.objects.filter(is_functional=True).first() or Currency.objects.first()
        return func_curr.code if func_curr else raw

    @property
    def currency_symbol(self) -> str:
        """رمز العملة الرسمي (ديناميكي 100% من جدول العملات)"""
        from financial.models import Currency
        raw = str(self.currency or "").strip()
        if raw.isdigit():
            c = Currency.objects.filter(id=int(raw)).first()
            if c:
                return c.symbol or c.code
        elif raw:
            c = Currency.objects.filter(code__iexact=raw).first()
            if c:
                return c.symbol or c.code
        func_curr = Currency.objects.filter(is_functional=True).first() or Currency.objects.first()
        if func_curr:
            return func_curr.symbol or func_curr.code
        return raw

    @property
    def currency_display(self) -> str:
        """عرض العملة في الواجهات والقوالب"""
        return self.currency_symbol

    @property
    def effective_required_down_payment(self) -> Decimal:
        """
        القيمة الفعلية للدفعة المقدمة المشترطة بالعملة سواء كانت نسبة مئوية أو مبلغاً ثابتاً
        """
        if self.down_payment_type == "percentage":
            return (self.total_amount * (self.required_down_payment / Decimal("100.00"))).quantize(Decimal("0.01"))
        return self.required_down_payment or Decimal("0.00")

    @property
    def paid_down_payment(self) -> Decimal:
        """
        مجموع المبالغ المسددة فعلياً من سندات القبض المعتمدة المربوطة بأمر البيع
        """
        from django.db.models import Sum
        val = self.down_payments.filter(status="posted").aggregate(s=Sum("amount"))["s"]
        return Decimal(str(val)) if val is not None else Decimal("0.00")

    @property
    def is_down_payment_satisfied(self) -> bool:
        """
        التحقق من استيفاء شرط الدفعة المقدمة (سواء بالسداد أو بالتجاوز الإداري)
        """
        if self.down_payment_override:
            return True
        if self.effective_required_down_payment <= Decimal("0.00"):
            return True
        return self.paid_down_payment >= self.effective_required_down_payment

    @property
    def remaining_down_payment(self) -> Decimal:
        """
        المتبقي من الدفعة المقدمة المشترطة
        """
        return max(Decimal("0.00"), self.effective_required_down_payment - self.paid_down_payment)

    @property
    def down_payment_status(self) -> str:
        """
        حالة سداد الدفعة المقدمة:
        - NO_DOWN_PAYMENT: لا يشترط
        - OVERRIDDEN: تم التجاوز الإداري
        - SATISFIED: مستوفى بالكامل
        - PARTIALLY_PAID: مسدد جزئياً
        - PENDING: معلق بانتظار التحصيل
        """
        if self.effective_required_down_payment <= Decimal("0.00"):
            return "NO_DOWN_PAYMENT"
        if self.down_payment_override:
            return "OVERRIDDEN"
        if self.paid_down_payment >= self.effective_required_down_payment:
            return "SATISFIED"
        if self.paid_down_payment > Decimal("0.00"):
            return "PARTIALLY_PAID"
        return "PENDING"

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
    tax_rate = models.DecimalField(_("نسبة الضريبة"), max_digits=6, decimal_places=2, default=Decimal("0.00"))
    tax_amount = models.DecimalField(_("مبلغ الضريبة"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    is_taxable = models.BooleanField(_("خاضع للضريبة"), default=True)
    table_tax_rate = models.DecimalField(_("نسبة ضريبة الجدول"), max_digits=6, decimal_places=2, default=Decimal("0.00"))
    table_tax_amount = models.DecimalField(_("مبلغ ضريبة الجدول"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
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

    # بيانات السائق والأسطول
    driver_name = models.CharField(_("اسم السائق"), max_length=100, blank=True, null=True)
    truck_plate_number = models.CharField(_("رقم لوحة الشاحنة"), max_length=50, blank=True, null=True)
    driver_phone = models.CharField(_("هاتف السائق"), max_length=30, blank=True, null=True)
    delivery_notes = models.TextField(_("ملاحظات التسليم والبوابة"), blank=True, null=True)

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
