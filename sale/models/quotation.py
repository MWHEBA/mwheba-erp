from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.utils import timezone


from sale.managers import QuotationManager


class Quotation(models.Model):
    """
    نموذج عرض السعر
    """
    objects = QuotationManager()
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
    custom_fields = models.JSONField(_("الحقول الإضافية"), default=list, blank=True, help_text=_("مصفوفة الحقول الإضافية المخصصة"))
    
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
    salesman = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("مسؤول المبيعات"),
        related_name="quotations_assigned",
        help_text=_("المستخدم أو مسؤول المبيعات الخاص بعرض السعر"),
    )
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)

    @property
    def salesman_display_name(self):
        user = self.salesman or self.created_by
        if user:
            return user.get_full_name() or user.username
        return ""

    class Meta:
        verbose_name = _("عرض سعر")
        verbose_name_plural = _("عروض الأسعار")
        ordering = ["-date", "-number"]
        permissions = [
            ("convert_quotation", _("تحويل عروض الأسعار إلى فواتير")),
        ]
        indexes = [
            models.Index(fields=["-date", "-number"]),
            models.Index(fields=["customer", "-date"]),
            models.Index(fields=["status", "-date"]),
        ]

    def __str__(self):
        return f"{self.number} - {self.customer} - {self.date}"

    def save(self, *args, **kwargs):
        if not self.number:
            from core.services.sequence_service import SequenceService
            from core.enums.document_types import DocumentType
            self.number = SequenceService.get_next_number(DocumentType.SALES_ORDER, date=self.date)

        super().save(*args, **kwargs)

    @property
    def has_item_discounts(self):
        """
        فحص ما إذا كان هناك أي خصم على أي بند من بنود عرض السعر
        """
        return any(item.discount and item.discount > 0 for item in self.items.all())

    @property
    def merged_custom_fields(self):
        """
        دمج الحقول المخصصة مع إعدادات التعاريف الحديثة (بما فيها show_in_header و show_on_print)
        """
        from sale.services.sale_service import SaleService
        return SaleService.smart_merge_custom_fields("quotation", self.custom_fields)

    @property
    def has_header_custom_fields(self):
        """هل توجد حقول مخصصة للهيدر تحتوي على قيم حقيقية؟"""
        return any(f.get('show_in_header') and f.get('show_on_print') and f.get('value') for f in (self.merged_custom_fields or []))

    @property
    def has_body_custom_fields(self):
        """هل توجد حقول مخصصة في التفاصيل تحتوي على قيم حقيقية؟"""
        return any(not f.get('show_in_header') and f.get('value') for f in (self.merged_custom_fields or []))
