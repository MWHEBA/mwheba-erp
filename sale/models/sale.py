from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.utils import timezone


class Sale(models.Model):
    """
    نموذج فاتورة المبيعات
    """

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
    tax = models.DecimalField(_("الضريبة"), max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(_("الإجمالي"), max_digits=12, decimal_places=2)
    payment_method = models.CharField(
        _("طريقة الدفع"), max_length=20, choices=PAYMENT_METHODS
    )
    payment_status = models.CharField(
        _("حالة الدفع"), max_length=20, choices=PAYMENT_STATUSES, default="unpaid"
    )
    notes = models.TextField(_("ملاحظات"), blank=True, null=True)

    # ربط محاسبي
    journal_entry = models.ForeignKey(
        "financial.JournalEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("القيد المحاسبي"),
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

    class Meta:
        verbose_name = _("فاتورة مبيعات")
        verbose_name_plural = _("فواتير المبيعات")
        ordering = ["-date", "-number"]

    def __str__(self):
        return f"{self.number} - {self.customer} - {self.date}"

    def save(self, *args, **kwargs):
        # حفظ الفاتورة
        if not self.number:
            # الحصول على الرقم التسلسلي
            from product.models import SerialNumber

            # البحث عن آخر رقم مستخدم
            last_sale = Sale.objects.order_by("-number").first()
            if last_sale:
                try:
                    last_number = int(last_sale.number.replace("SALE", ""))
                except ValueError:
                    last_number = 0
            else:
                last_number = 0

            # إنشاء أو تحديث الرقم التسلسلي
            serial = SerialNumber.objects.get_or_create(
                document_type="sale",
                year=timezone.now().year,
                defaults={"prefix": "SALE", "last_number": last_number},
            )[0]

            # تحديث آخر رقم إذا كان أقل من الرقم الحالي
            if serial.last_number <= last_number:
                serial.last_number = last_number
                serial.save()

            next_number = serial.get_next_number()
            self.number = f"{serial.prefix}{next_number:04d}"

        super().save(*args, **kwargs)

        # تحديث حالة الدفع بعد الحفظ
        self.update_payment_status()

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

    def update_payment_status(self):
        """
        تحديث حالة الدفع
        """
        old_status = self.payment_status

        if self.is_fully_paid:
            new_status = "paid"
        elif self.amount_paid > 0:
            new_status = "partially_paid"
        else:
            new_status = "unpaid"

        # تحديث فقط إذا تغيرت الحالة لتجنب التكرار اللانهائي
        if old_status != new_status:
            Sale.objects.filter(pk=self.pk).update(payment_status=new_status)

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
