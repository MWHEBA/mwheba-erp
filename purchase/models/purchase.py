from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.utils import timezone
from django.urls import reverse


class Purchase(models.Model):
    """
    نموذج فاتورة المشتريات
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
    )

    number = models.CharField(_("رقم الفاتورة"), max_length=20, unique=True)
    date = models.DateField(_("تاريخ الفاتورة"))
    status = models.CharField(
        _("الحالة"), max_length=20, choices=STATUS_CHOICES, default="confirmed"
    )
    supplier = models.ForeignKey(
        "supplier.Supplier",
        on_delete=models.PROTECT,
        verbose_name=_("المورد"),
        related_name="purchases",
    )
    warehouse = models.ForeignKey(
        "product.Warehouse",
        on_delete=models.PROTECT,
        verbose_name=_("المخزن"),
        related_name="purchases",
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
        related_name="purchases",
    )

    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_("أنشئ بواسطة"),
        related_name="purchases_created",
    )

    class Meta:
        verbose_name = _("فاتورة مشتريات")
        verbose_name_plural = _("فواتير المشتريات")
        ordering = ["-date", "-number"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # حفظ القيم الأصلية عند تحميل الكائن
        if self.pk:
            self._original_payment_method = self.payment_method
            self._original_total = self.total
            self._original_payment_status = self.payment_status

    def __str__(self):
        return f"{self.number} - {self.supplier} - {self.date}"


    def save(self, *args, **kwargs):
        if not self.number:
            # الحصول على الرقم التسلسلي
            from product.models import SerialNumber

            # البحث عن آخر رقم مستخدم
            last_purchase = Purchase.objects.order_by("-number").first()
            if last_purchase:
                try:
                    last_number = int(last_purchase.number.replace("PUR", ""))
                except ValueError:
                    last_number = 0
            else:
                last_number = 0

            # إنشاء أو تحديث الرقم التسلسلي
            serial = SerialNumber.objects.get_or_create(
                document_type="purchase",
                year=timezone.now().year,
                defaults={"prefix": "PUR", "last_number": last_number},
            )[0]

            # تحديث آخر رقم إذا كان أقل من الرقم الحالي
            if serial.last_number <= last_number:
                serial.last_number = last_number
                serial.save()

            next_number = serial.get_next_number()
            self.number = f"{serial.prefix}{next_number:04d}"

        # حفظ الفاتورة أولاً
        is_new = self.pk is None
        super().save(*args, **kwargs)

        # تحديث حالة الدفع بعد الحفظ
        self.update_payment_status()

        # إنشاء قيد محاسبي تلقائياً (فقط للفواتير الجديدة المؤكدة وبدون قيد)
        if is_new and self.status == "confirmed" and not self.journal_entry:
            self._create_journal_entry()

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

    def update_payment_status(self):
        """
        تحديث حالة الدفع
        """
        old_status = self.payment_status
        old_method = getattr(self, "_original_payment_method", self.payment_method)
        old_total = getattr(self, "_original_total", self.total)

        if self.is_fully_paid:
            new_status = "paid"
        elif self.amount_paid > 0:
            new_status = "partially_paid"
        else:
            new_status = "unpaid"

        # تحديث مديونية المورد بناءً على تغييرات حالة الدفع أو طريقة الدفع أو المبلغ الإجمالي
        supplier = self.supplier
        if supplier:
            # إذا تغيرت طريقة الدفع من آجل إلى نقدي
            if old_method == "credit" and self.payment_method == "cash":
                # إلغاء المديونية القديمة (المبلغ الكامل للفاتورة الآجلة)
                supplier.balance -= old_total

                # إضافة المديونية الجديدة فقط إذا كانت الفاتورة النقدية غير مدفوعة بالكامل
                if new_status != "paid":
                    supplier.balance += self.amount_due

                supplier.save(update_fields=["balance"])

            # إذا تغيرت طريقة الدفع من نقدي إلى آجل
            elif old_method == "cash" and self.payment_method == "credit":
                # إلغاء المديونية القديمة (قد تكون صفر إذا كانت مدفوعة بالكامل)
                if old_status != "paid":
                    amount_was_due = old_total - self.amount_paid
                    supplier.balance -= amount_was_due

                # إضافة المديونية الجديدة (المبلغ الكامل للفاتورة الآجلة)
                supplier.balance += self.total
                supplier.save(update_fields=["balance"])

            # إذا تغير المبلغ الإجمالي (مع بقاء نفس طريقة الدفع)
            elif old_total != self.total:
                # للفواتير الآجلة
                if self.payment_method == "credit":
                    # إلغاء المديونية القديمة وإضافة المديونية الجديدة
                    supplier.balance -= old_total
                    supplier.balance += self.total
                    supplier.save(update_fields=["balance"])
                # للفواتير النقدية غير المدفوعة بالكامل
                elif self.payment_method == "cash" and new_status != "paid":
                    # إلغاء المديونية القديمة (إذا كانت موجودة)
                    if old_status != "paid":
                        amount_was_due = old_total - self.amount_paid
                        supplier.balance -= amount_was_due

                    # إضافة المديونية الجديدة
                    supplier.balance += self.amount_due
                    supplier.save(update_fields=["balance"])

            # إذا تغيرت حالة الدفع فقط، بدون تغيير طريقة الدفع أو المبلغ
            elif old_status != new_status:
                # للفواتير النقدية فقط (الآجلة تظل مديونية كاملة بغض النظر عن حالة الدفع)
                if self.payment_method == "cash":
                    if old_status == "unpaid" and new_status == "partially_paid":
                        # إذا تغيرت من غير مدفوعة إلى مدفوعة جزئياً
                        # نضيف المبلغ المتبقي لمديونية المورد
                        supplier.balance += self.amount_due
                        supplier.save(update_fields=["balance"])
                    elif old_status == "partially_paid" and new_status == "paid":
                        # إذا تغيرت من مدفوعة جزئياً إلى مدفوعة بالكامل
                        # نلغي المديونية المتبقية
                        amount_was_due = old_total - self.amount_paid
                        supplier.balance -= amount_was_due
                        supplier.save(update_fields=["balance"])
                    elif old_status == "paid" and new_status in [
                        "partially_paid",
                        "unpaid",
                    ]:
                        # إذا تغيرت من مدفوعة بالكامل إلى غير مدفوعة بالكامل
                        # نضيف المبلغ المتبقي لمديونية المورد
                        supplier.balance += self.amount_due
                        supplier.save(update_fields=["balance"])

        # تحديث حالة الدفع في قاعدة البيانات
        if old_status != new_status:
            Purchase.objects.filter(pk=self.pk).update(payment_status=new_status)

        # احفظ القيم الحالية للاستخدام في المرة التالية
        self._original_payment_method = self.payment_method
        self._original_total = self.total

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

        # حساب إجمالي الكميات المشتراة
        purchased_quantities = {}
        for item in self.items.all():
            purchased_quantities[item.id] = item.quantity

        # حساب إجمالي الكميات المرتجعة
        returned_quantities = {}
        for ret in confirmed_returns:
            for item in ret.items.all():
                purchase_item_id = item.purchase_item.id
                if purchase_item_id in returned_quantities:
                    returned_quantities[purchase_item_id] += item.quantity
                else:
                    returned_quantities[purchase_item_id] = item.quantity

        # فحص إذا كانت كل المنتجات مرتجعة بالكامل
        for item_id, purchased_qty in purchased_quantities.items():
            returned_qty = returned_quantities.get(item_id, 0)
            if returned_qty < purchased_qty:
                return "partial"

        # إذا وصلنا إلى هنا فكل المنتجات مرتجعة بالكامل
        return "full"

    def get_absolute_url(self):
        """
        ترجع URL لعرض تفاصيل فاتورة المشتريات
        """
        return reverse("purchase:purchase_detail", kwargs={"pk": self.pk})
