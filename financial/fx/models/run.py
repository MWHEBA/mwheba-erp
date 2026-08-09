from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings


class FXRevaluationRun(models.Model):
    STATUS_CHOICES = (
        ('DRAFT', _('مسودة')),
        ('CALCULATED', _('محسوب')),
        ('VALIDATED', _('معتمد البنود')),
        ('POSTED', _('مرحل بالدفتر')),
        ('REVERSED', _('معكوس')),
        ('FAILED', _('فشل')),
    )

    VALUATION_TYPE_CHOICES = (
        ('PERIOD_END', _('تقييم نهاية الفترة')),
        ('AD_HOC', _('تقييم استثنائي')),
    )

    VALUATION_METHOD_CHOICES = (
        ('OPEN_ITEMS', _('البنود المفتوحة')),
        ('BALANCE_ACCOUNT', _('رصيد الحساب')),
        ('MONETARY_ITEMS', _('البنود النقدية فقط')),
    )

    CURRENCY_SCOPE_CHOICES = (
        ('ALL_CURRENCIES', _('جميع العملات الأجنبية')),
        ('SPECIFIC', _('عملة محددة')),
    )

    ACCOUNTING_BOOK_CHOICES = (
        ('PRIMARY', _('الدفتر الرئيسي')),
        ('IFRS', _('دفتر المعايير الدولية')),
        ('TAX', _('الدفتر الضريبي')),
    )

    company_code = models.CharField(_("رمز الشركة / الكيان"), max_length=50, default="DEFAULT")
    period = models.ForeignKey('financial.AccountingPeriod', on_delete=models.CASCADE, verbose_name=_("الفترة المحاسبية"))
    accounting_book = models.CharField(_("الكتاب المحاسبي"), max_length=20, choices=ACCOUNTING_BOOK_CHOICES, default='PRIMARY')
    valuation_type = models.CharField(_("نوع التقييم"), max_length=30, choices=VALUATION_TYPE_CHOICES, default='PERIOD_END')
    valuation_method = models.CharField(_("طريقة التقييم"), max_length=30, choices=VALUATION_METHOD_CHOICES, default='OPEN_ITEMS')
    currency_scope = models.CharField(_("نطاق العملات"), max_length=30, choices=CURRENCY_SCOPE_CHOICES, default='ALL_CURRENCIES')
    target_currency = models.ForeignKey('financial.Currency', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("العملة المستهدفة"))

    status = models.CharField(_("الحالة"), max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    run_date = models.DateField(_("تاريخ التقييم"), null=True, blank=True)
    rate_source = models.CharField(_("مصدر سعر الصرف"), max_length=100, default="CBE_OFFICIAL")

    journal_entry = models.ForeignKey('financial.JournalEntry', on_delete=models.SET_NULL, null=True, blank=True, related_name='fx_revaluation_runs', verbose_name=_("قيد التقييم المرحل"))
    reversal_of_run = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='reversed_by_runs', verbose_name=_("معكوس عن تشغيل سابق"))

    total_unrealized_gain_loss = models.DecimalField(_("إجمالي أرباح/خسائر التقييم"), max_digits=18, decimal_places=2, default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("تم التشغيل بواسطة"))
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("تشغيل تقييم العملات")
        verbose_name_plural = _("تشغيلات تقييم العملات")
        constraints = [
            models.UniqueConstraint(
                fields=['company_code', 'period', 'valuation_type', 'currency_scope', 'accounting_book'],
                condition=models.Q(status__in=['VALIDATED', 'POSTED']),
                name='unique_active_fx_revaluation_run'
            )
        ]

    def __str__(self):
        return f"FXRun #{self.id} - {self.period.name} [{self.get_status_display()}]"
