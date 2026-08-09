from django.db import models
from django.utils.translation import gettext_lazy as _


class FXRevaluationLine(models.Model):
    SOURCE_TYPE_CHOICES = (
        ('AR_INVOICE', _('عقد/فاتورة مبيعات عميل (AR)')),
        ('AP_INVOICE', _('فاتورة مشتريات مورد (AP)')),
        ('CASH_ACCOUNT', _('حساب خزينة/بنك أجنبي')),
    )

    run = models.ForeignKey('financial.FXRevaluationRun', on_delete=models.CASCADE, related_name='lines', verbose_name=_("تشغيل التقييم"))
    source_type = models.CharField(_("نوع المصدر"), max_length=20, choices=SOURCE_TYPE_CHOICES)
    source_id = models.CharField(_("معرف المصدر / المستند"), max_length=100)
    source_hash = models.CharField(_("بصمة التحقق من التعديل (Source Hash)"), max_length=64, blank=True, default='')
    source_updated_at = models.DateTimeField(_("تاريخ آخر تعديل للمصدر"), null=True, blank=True)

    account = models.ForeignKey('financial.ChartOfAccounts', on_delete=models.PROTECT, related_name='fx_revaluation_lines', verbose_name=_("الحساب المحاسبي"))
    partner_name = models.CharField(_("اسم العميل / المورد / الجهة"), max_length=255, blank=True, default='')
    currency = models.ForeignKey('financial.Currency', on_delete=models.PROTECT, verbose_name=_("العملة"))

    open_foreign_amount = models.DecimalField(_("الرصيد الأجنبي المفتوح الصافي"), max_digits=18, decimal_places=4)
    old_rate = models.DecimalField(_("سعر الصرف السابق/التاريخي"), max_digits=18, decimal_places=6)
    new_rate = models.DecimalField(_("سعر الإقفال/الجديد"), max_digits=18, decimal_places=6)

    old_functional_value = models.DecimalField(_("القيمة السابقة بالجنيه"), max_digits=18, decimal_places=2)
    new_functional_value = models.DecimalField(_("القيمة الجديدة بالجنيه"), max_digits=18, decimal_places=2)
    unrealized_difference = models.DecimalField(_("فرق التقييم غير المحقق"), max_digits=18, decimal_places=2)

    gain_loss_account = models.ForeignKey(
        'financial.ChartOfAccounts',
        on_delete=models.PROTECT,
        related_name='fx_gain_loss_lines',
        null=True,
        blank=True,
        verbose_name=_("حساب أرباح/خسائر التقييم")
    )

    class Meta:
        verbose_name = _("بند تقييم العملات التفصيلي")
        verbose_name_plural = _("بنود تقييم العملات التفصيلية")
        ordering = ['id']

    def __str__(self):
        return f"Line #{self.id} [{self.source_type}:{self.source_id}] Diff: {self.unrealized_difference}"
