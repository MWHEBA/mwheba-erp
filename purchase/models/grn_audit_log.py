from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from .procurement_models import GoodsReceivedNote


class GRNAuditLog(models.Model):
    """
    سجل تتبع الحوكمة والاعتماد لإذن الاستلام (GRN Audit Log)
    """
    grn = models.ForeignKey(
        GoodsReceivedNote,
        on_delete=models.CASCADE,
        related_name="audit_logs",
        verbose_name=_("إذن الاستلام")
    )
    old_status = models.CharField(_("الحالة السابقة"), max_length=20, blank=True, null=True)
    new_status = models.CharField(_("الحالة الجديدة"), max_length=20)
    action_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_("تم بواسطة"),
        null=True,
        blank=True
    )
    reason = models.CharField(_("السبب / التبرير"), max_length=255, blank=True, null=True)
    comment = models.TextField(_("ملاحظات إضافية"), blank=True, null=True)
    ip_address = models.GenericIPAddressField(_("عنوان IP"), blank=True, null=True)
    created_at = models.DateTimeField(_("تاريخ التسجيل"), auto_now_add=True)

    class Meta:
        verbose_name = _("سجل تتبع إذن استلام")
        verbose_name_plural = _("سجلات تتبع أذون الاستلام")
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"GRN Audit #{self.grn.grn_number}: {self.old_status} -> {self.new_status}"
