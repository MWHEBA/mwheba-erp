"""
نموذج سجل التدقيق للفواتير (Invoice Audit Log)

يسجل جميع التعديلات على الفواتير المرحّلة مع:
- القيم القديمة والجديدة
- المستخدم الذي قام بالتعديل
- التاريخ والوقت
- سبب التعديل
- القيد التصحيحي المرتبط
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from decimal import Decimal


class InvoiceAuditLog(models.Model):
    """
    سجل تدقيق شامل لتعديلات الفواتير المرحّلة
    """

    INVOICE_TYPE_CHOICES = (
        ("sale", _("فاتورة مبيعات")),
        ("purchase", _("فاتورة مشتريات")),
    )

    ACTION_TYPE_CHOICES = (
        ("edit", _("تعديل")),
        ("adjustment", _("قيد تصحيحي")),
    )

    # معلومات الفاتورة
    invoice_type = models.CharField(
        _("نوع الفاتورة"),
        max_length=20,
        choices=INVOICE_TYPE_CHOICES,
    )
    invoice_id = models.IntegerField(_("رقم الفاتورة في قاعدة البيانات"))
    invoice_number = models.CharField(_("رقم الفاتورة"), max_length=50)

    # نوع الإجراء
    action_type = models.CharField(
        _("نوع الإجراء"),
        max_length=20,
        choices=ACTION_TYPE_CHOICES,
        default="edit",
    )

    # القيم القديمة
    old_total = models.DecimalField(
        _("الإجمالي القديم"),
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    old_cost = models.DecimalField(
        _("التكلفة القديمة"),
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
        null=True,
        blank=True,
    )

    # القيم الجديدة
    new_total = models.DecimalField(
        _("الإجمالي الجديد"),
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    new_cost = models.DecimalField(
        _("التكلفة الجديدة"),
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
        null=True,
        blank=True,
    )

    # الفروقات
    total_difference = models.DecimalField(
        _("فرق الإجمالي"),
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    cost_difference = models.DecimalField(
        _("فرق التكلفة"),
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
        null=True,
        blank=True,
    )

    # القيد التصحيحي المرتبط
    adjustment_entry = models.ForeignKey(
        "financial.JournalEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("القيد التصحيحي"),
        related_name="invoice_audit_logs",
    )

    # سبب التعديل
    reason = models.TextField(
        _("سبب التعديل"),
        blank=True,
        help_text=_("اختياري - يمكن إضافة سبب التعديل"),
    )

    # ملاحظات إضافية
    notes = models.TextField(
        _("ملاحظات"),
        blank=True,
    )

    # معلومات التتبع
    created_at = models.DateTimeField(_("تاريخ التعديل"), auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_("المستخدم"),
        related_name="invoice_audit_logs",
    )

    class Meta:
        verbose_name = _("سجل تدقيق الفاتورة")
        verbose_name_plural = _("سجلات تدقيق الفواتير")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["invoice_type", "invoice_id"]),
            models.Index(fields=["invoice_number"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.get_invoice_type_display()} {self.invoice_number} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"

    @property
    def has_difference(self):
        """هل يوجد فرق في القيم؟"""
        return self.total_difference != 0 or (
            self.cost_difference and self.cost_difference != 0
        )

    @property
    def difference_direction(self):
        """اتجاه الفرق (زيادة أو نقص)"""
        if self.total_difference > 0:
            return "increase"
        elif self.total_difference < 0:
            return "decrease"
        return "no_change"

    @property
    def difference_direction_display(self):
        """عرض اتجاه الفرق بالعربية"""
        direction = self.difference_direction
        if direction == "increase":
            return "زيادة"
        elif direction == "decrease":
            return "نقص"
        return "لا يوجد تغيير"
