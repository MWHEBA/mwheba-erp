from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.utils import timezone
from sale.managers import SaleManager


class Sale(models.Model):
    """
    نموذج فاتورة المبيعات
    """
    objects = SaleManager()

    STATUS_CHOICES = (
        ("draft", _("مسودة")),
        ("confirmed", _("مؤكدة")),
        ("cancelled", _("ملغية")),
    )

    PAYMENT_STATUSES = (
        ("paid", _("مدفوعة")),
        ("partially_paid", _("مدفوعة جزئياً")),
        ("unpaid", _("غير مدفوعة")),
    )
    PAYMENT_METHODS = (
        ("cash", _("نقدي")),
        ("credit", _("آجل")),
        ("bank_transfer", _("تحويل بنكي")),
    )

    number = models.CharField(_("رقم الفاتورة"), max_length=20, unique=True)
    date = models.DateField(_("تاريخ الفاتورة"))
    status = models.CharField(
        _("الحالة"), max_length=20, choices=STATUS_CHOICES, default="confirmed"
    )
    customer = models.ForeignKey(
        "client.Customer",
        on_delete=models.PROTECT,
        verbose_name=_("العميل"),
        related_name="sales",
    )
    warehouse = models.ForeignKey(
        "product.Warehouse",
        on_delete=models.PROTECT,
        verbose_name=_("المخزن"),
        related_name="sales",
    )
    subtotal = models.DecimalField(_("المجموع الفرعي"), max_digits=12, decimal_places=2)
    discount = models.DecimalField(
        _("الخصم"), max_digits=12, decimal_places=2, default=0
    )
    discount_type = models.CharField(
        _("نوع الخصم"),
        max_length=10,
        choices=[("fixed", _("مبلغ ثابت")), ("percentage", _("نسبة مئوية"))],
        default="fixed",
    )
    adjustment_name = models.CharField(
        _("اسم التسوية"), max_length=100, blank=True, null=True
    )
    adjustment_amount = models.DecimalField(
        _("مبلغ التسوية"), max_digits=12, decimal_places=2, default=0
    )
    tax = models.DecimalField(_("الضريبة"), max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(_("الإجمالي"), max_digits=12, decimal_places=2)
    payment_method = models.CharField(
        _("طريقة الدفع"), 
        max_length=50,  # زودنا الطول عشان يستوعب account codes
        help_text=_("طريقة الدفع أو كود الحساب المالي")
    )
    payment_status = models.CharField(
        _("حالة الدفع"), max_length=20, choices=PAYMENT_STATUSES, default="unpaid"
    )
    notes = models.TextField(_("ملاحظات"), blank=True, null=True)
    custom_fields = models.JSONField(_("الحقول الإضافية"), default=list, blank=True, help_text=_("مصفوفة الحقول الإضافية المخصصة"))

    # التصنيف المالي
    financial_category = models.ForeignKey(
        'financial.FinancialCategory',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("التصنيف المالي"),
        related_name="sales",
        help_text=_("التصنيف المالي للإيراد (يحدد الحساب المحاسبي تلقائياً)")
    )

    # ربط محاسبي
    journal_entry = models.ForeignKey(
        "financial.JournalEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("القيد المحاسبي"),
        related_name="sales",
    )

    # ربط بعرض السعر الأصلي
    quotation = models.ForeignKey(
        "sale.Quotation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("عرض السعر المرتبط"),
        related_name="sales_associated",
    )

    # ربط بأمر الشغل
    work_order = models.ForeignKey(
        "work_order.WorkOrder",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("أمر الشغل المرتبط"),
        related_name="sales",
    )

    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_("أنشئ بواسطة"),
        related_name="sales_created",
    )
    salesman = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("مسؤول المبيعات"),
        related_name="sales_assigned",
        help_text=_("المستخدم أو مسؤول المبيعات الخاص بالفاتورة"),
    )

    @property
    def salesman_display_name(self):
        user = self.salesman or self.created_by
        if user:
            return user.get_full_name() or user.username
        return ""

    class Meta:
        verbose_name = _("فاتورة مبيعات")
        verbose_name_plural = _("فواتير المبيعات")
        ordering = ["-date", "-number"]
        permissions = [
            ("change_sale_salesman", "تغيير مسؤول المبيعات في الفواتير وعروض الأسعار"),
            ("manage_custom_fields", "إدارة وتعديل الحقول الإضافية المخصصة"),
        ]
        indexes = [
            models.Index(fields=["-date", "-number"]),
            models.Index(fields=["customer", "-date"]),
            models.Index(fields=["warehouse", "-date"]),
            models.Index(fields=["payment_status", "-date"]),
            models.Index(fields=["status", "-date"]),
        ]

    def __str__(self):
        return f"{self.number} - {self.customer} - {self.date}"

    def get_payment_method_display(self):
        """عرض طريقة الدفع بشكل مناسب"""
        # القيم القديمة
        payment_method_map = {
            'cash': _("نقدي"),
            'bank_transfer': _("تحويل بنكي"),
            'check': _("شيك"),
            'credit': _("آجل"),
            'credit_with_downpayment': _("آجل مع دفعة مقدمة"),
            'credit_card': _("بطاقة ائتمان"),
            'debit_card': _("بطاقة خصم"),
        }

        if self.payment_method in payment_method_map:
            return payment_method_map[self.payment_method]

        # محاولة جلب الحساب من الكود
        try:
            from financial.models import ChartOfAccounts
            account = ChartOfAccounts.objects.filter(code=self.payment_method).first()
            if account:
                return account.name
        except:
            pass

        # إرجاع القيمة كما هي
        return self.payment_method or _("غير محدد")


    def save(self, *args, **kwargs):
        # حفظ الفاتورة
        if not self.number:
            from product.models import SerialNumber
            sale_year = self.date.year if self.date else timezone.now().year
            self.number = SerialNumber.get_next_sequence("sale", prefix="SALE-", year=sale_year)

        super().save(*args, **kwargs)

        # تحديث حالة الدفع بعد الحفظ
        self.update_payment_status()

        # ملاحظة: القيود المحاسبية للفواتير تُنشأ عبر:
        # - AccountingIntegrationService.create_sale_journal_entry()
        # - يتم استدعاؤها من sale/views.py عند إنشاء الفاتورة

    @property
    def amount_paid(self):
        """
        حساب المبلغ المدفوع - فقط الدفعات المرحّلة
        """
        return (
            self.payments.filter(status="posted").aggregate(models.Sum("amount"))[
                "amount__sum"
            ]
            or 0
        )

    @property
    def amount_due(self):
        """
        حساب المبلغ المتبقي
        """
        return self.total - self.amount_paid

    @property
    def is_fully_paid(self):
        """
        هل الفاتورة مدفوعة بالكامل
        """
        return self.amount_due <= 0

    @property
    def has_posted_payments(self):
        """
        هل الفاتورة تحتوي على دفعات مرحلة
        """
        return self.payments.filter(status="posted").exists()

    @property
    def merged_custom_fields(self):
        """
        دمج الحقول المخصصة مع إعدادات التعاريف الحديثة (بما فيها show_in_header و show_on_print)
        """
        from sale.services.sale_service import SaleService
        return SaleService.smart_merge_custom_fields("sale", self.custom_fields)

    @property
    def has_header_custom_fields(self):
        """هل توجد حقول مخصصة للهيدر تحتوي على قيم حقيقية؟"""
        return any(f.get('show_in_header') and f.get('show_on_print') and f.get('value') for f in (self.merged_custom_fields or []))

    @property
    def has_body_custom_fields(self):
        """هل توجد حقول مخصصة في التفاصيل تحتوي على قيم حقيقية؟"""
        return any(not f.get('show_in_header') and f.get('value') for f in (self.merged_custom_fields or []))

    def update_payment_status(self):
        """
        تحديث حالة الدفع
        """
        if self.is_fully_paid:
            new_status = "paid"
        elif self.amount_paid > 0:
            new_status = "partially_paid"
        else:
            new_status = "unpaid"

        # تحديث الخاصة في الذاكرة لضمان عدم حفظ القيمة القديمة لاحقاً عند calling save()
        self.payment_status = new_status

        # تحديث قاعدة البيانات مباشرة
        Sale.objects.filter(pk=self.pk).update(payment_status=new_status)

    @property
    def has_item_discounts(self):
        """
        فحص ما إذا كان هناك أي خصم على أي بند من بنود الفاتورة
        """
        return any(item.discount and item.discount > 0 for item in self.items.all())

    @property
    def is_returned(self):
        """
        فحص إذا كانت الفاتورة مرتجعة (كليًا أو جزئيًا)
        """
        confirmed_returns = self.returns.filter(status="confirmed")
        return confirmed_returns.exists()

    @property
    def return_status(self):
        """
        حالة الإرجاع للفاتورة (كلي، جزئي، غير مرتجع)
        """
        confirmed_returns = self.returns.filter(status="confirmed")

        if not confirmed_returns.exists():
            return None

        # حساب إجمالي الكميات المباعة
        sold_quantities = {}
        for item in self.items.all():
            sold_quantities[item.id] = item.quantity

        # حساب إجمالي الكميات المرتجعة
        returned_quantities = {}
        for ret in confirmed_returns:
            for item in ret.items.all():
                sale_item_id = item.sale_item.id
                if sale_item_id in returned_quantities:
                    returned_quantities[sale_item_id] += item.quantity
                else:
                    returned_quantities[sale_item_id] = item.quantity

        # فحص إذا كانت كل المنتجات مرتجعة بالكامل
        for item_id, sold_qty in sold_quantities.items():
            returned_qty = returned_quantities.get(item_id, 0)
            if returned_qty < sold_qty:
                return "partial"

        # إذا وصلنا إلى هنا فكل المنتجات مرتجعة بالكامل
        return "full"
