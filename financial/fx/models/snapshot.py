from django.db import models
from django.utils.translation import gettext_lazy as _


class FXRateSnapshot(models.Model):
    RATE_TYPE_CHOICES = (
        ('CLOSING', _('سعر الإقفال الرسمي')),
        ('AVERAGE', _('المتوسط الشهري/الفصلي')),
        ('HISTORICAL', _('السعر التاريخي')),
        ('TRANSACTION', _('سعر المعاملة')),
    )

    run = models.ForeignKey('financial.FXRevaluationRun', on_delete=models.CASCADE, related_name='rate_snapshots', verbose_name=_("تشغيل التقييم"))
    currency = models.ForeignKey('financial.Currency', on_delete=models.PROTECT, verbose_name=_("العملة"))
    rate_type = models.CharField(_("نوع سعر الصرف"), max_length=20, choices=RATE_TYPE_CHOICES, default='CLOSING')
    rate_date = models.DateField(_("تاريخ سعر الصرف المعتمد"))
    rate = models.DecimalField(_("سعر الصرف المجمّد"), max_digits=18, decimal_places=6)
    source = models.CharField(_("مصدر السعر"), max_length=100, default="CBE_OFFICIAL")
    captured_at = models.DateTimeField(_("وقت التجميد والتقاط الصورة"), auto_now_add=True)

    class Meta:
        verbose_name = _("صورة سعر الصرف المجمّدة")
        verbose_name_plural = _("صور أسعار الصرف المجمّدة")

    def __str__(self):
        return f"Snapshot {self.currency.code} = {self.rate} ({self.rate_date})"
