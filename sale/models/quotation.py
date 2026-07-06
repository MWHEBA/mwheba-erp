from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.utils import timezone


class Quotation(models.Model):
    """
    نموذج عرض السعر
    """
    STATUS_CHOICES = (
        ("draft", _("مسودة")),
        ("sent", _("تم الإرسال")),
        ("accepted", _("مقبول")),
        ("rejected", _("مرفوض")),
        ("expired", _("منتهي الصلاحية")),
    )

    number = models.CharField(_("رقم عرض السعر"), max_length=20, unique=True)
    customer = models.ForeignKey(
        "client.Customer",
        on_delete=models.CASCADE,
        verbose_name=_("العميل"),
        related_name="quotations",
    )
    warehouse = models.ForeignKey(
        "product.Warehouse",
        on_delete=models.PROTECT,
        verbose_name=_("المخزن"),
        related_name="quotations",
        null=True,
        blank=True,
    )
    date = models.DateField(_("تاريخ عرض السعر"), default=timezone.now)
    valid_until = models.DateField(_("تاريخ انتهاء الصلاحية"), null=True, blank=True)
    status = models.CharField(
        _("الحالة"), max_length=20, choices=STATUS_CHOICES, default="draft"
    )
    subtotal = models.DecimalField(_("المجموع الفرعي"), max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(_("الخصم"), max_digits=12, decimal_places=2, default=0)
    tax = models.DecimalField(_("الضريبة"), max_digits=12, decimal_places=2, default=0)
    tax_active = models.BooleanField(_("الضريبة نشطة"), default=True)
    total = models.DecimalField(_("الإجمالي"), max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(_("ملاحظات وشروط"), blank=True, null=True)
    
    # ربط بالفاتورة الناتجة
    converted_to_sale = models.ForeignKey(
        "sale.Sale",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("الفاتورة الناتجة"),
        related_name="quotations_converted",
    )

    # ربط بأمر الشغل
    work_order = models.ForeignKey(
        "work_order.WorkOrder",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("أمر الشغل المرتبط"),
        related_name="quotations",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_("أنشئ بواسطة"),
        related_name="quotations_created",
    )
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)

    class Meta:
        verbose_name = _("عرض سعر")
        verbose_name_plural = _("عروض الأسعار")
        ordering = ["-date", "-number"]
        permissions = [
            ("convert_quotation", _("تحويل عروض الأسعار إلى فواتير")),
        ]

    def __str__(self):
        return f"{self.number} - {self.customer} - {self.date}"

    def save(self, *args, **kwargs):
        if not self.number:
            from product.models import SerialNumber
            # البحث عن آخر رقم مستخدم
            last_quotation = Quotation.objects.order_by("-id").first()
            last_number = 0
            if last_quotation and last_quotation.number:
                try:
                    last_number = int(last_quotation.number.replace("QT", ""))
                except (ValueError, AttributeError):
                    pass

            serial, created = SerialNumber.objects.get_or_create(
                document_type="quotation",
                year=timezone.now().year,
                defaults={"prefix": "QT", "last_number": last_number},
            )

            if serial.last_number <= last_number:
                serial.last_number = last_number
                serial.save()

            next_number = serial.get_next_number()
            self.number = f"{serial.prefix}{next_number:04d}"

        super().save(*args, **kwargs)
