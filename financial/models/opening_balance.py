from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _

from financial.exceptions import ImmutableLedgerError
from financial.models.fiscal_year import FiscalYear
from financial.models.chart_of_accounts import ChartOfAccounts


class OpeningBalanceBatch(models.Model):
    """
    دفتر الأرصدة الافتتاحية (Opening Balance Batch)
    """
    STATUS_CHOICES = [
        ('draft', _('مسودة')),
        ('validated', _('مفحوصة')),
        ('posted', _('مرحلة')),
    ]

    fiscal_year = models.ForeignKey(
        FiscalYear,
        on_delete=models.PROTECT,
        related_name='opening_balance_batches',
        verbose_name=_("السنة المالية")
    )
    batch_number = models.CharField(max_length=50, unique=True, verbose_name=_("رقم الدفعة"))
    description = models.TextField(blank=True, verbose_name=_("الوصف"))
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        verbose_name=_("الحالة")
    )
    journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='opening_balance_batch',
        verbose_name=_("القيد المحاسبي المتربط")
    )

    class Meta:
        verbose_name = _("دفعة أرصدة افتتاحية")
        verbose_name_plural = _("دفوعات الأرصدة الافتتاحية")

    def __str__(self):
        return f"{self.batch_number} - {self.fiscal_year.name}"

    def save(self, *args, **kwargs):
        if self.pk:
            old_status = OpeningBalanceBatch.objects.filter(pk=self.pk).values_list('status', flat=True).first()
            if old_status == 'posted':
                raise ImmutableLedgerError("Posted opening balance batch is strictly immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status == 'posted':
            raise ImmutableLedgerError("Posted opening balance batch cannot be deleted.")
        super().delete(*args, **kwargs)


class OpeningBalanceLine(models.Model):
    """
    بنود الأرصدة الافتتاحية (Opening Balance Line)
    """
    batch = models.ForeignKey(
        OpeningBalanceBatch,
        related_name='lines',
        on_delete=models.CASCADE,
        verbose_name=_("الدفعة")
    )
    account = models.ForeignKey(
        ChartOfAccounts,
        on_delete=models.PROTECT,
        verbose_name=_("الحساب المحاسبي")
    )
    debit = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'), verbose_name=_("مدين"))
    credit = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'), verbose_name=_("دائن"))

    class Meta:
        verbose_name = _("سطر رصيد افتتاحي")
        verbose_name_plural = _("سطور الأرصدة الافتتاحية")

    def __str__(self):
        return f"{self.account.code} - Debit: {self.debit}, Credit: {self.credit}"

    def save(self, *args, **kwargs):
        if self.batch_id:
            batch_status = OpeningBalanceBatch.objects.filter(pk=self.batch_id).values_list('status', flat=True).first()
            if batch_status == 'posted':
                raise ImmutableLedgerError("Line belonging to a posted opening balance batch cannot be saved.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.batch_id:
            batch_status = OpeningBalanceBatch.objects.filter(pk=self.batch_id).values_list('status', flat=True).first()
            if batch_status == 'posted':
                raise ImmutableLedgerError("Line belonging to a posted opening balance batch cannot be deleted.")
        super().delete(*args, **kwargs)
