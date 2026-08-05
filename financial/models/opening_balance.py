from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from decimal import Decimal
from financial.models.fiscal_year import FiscalYear
from financial.exceptions import ImmutableLedgerError


from django.utils import timezone

class OpeningBalanceBatch(models.Model):
    """
    دفعة الأرصدة الافتتاحية للسنة المالية
    """
    STATUS_CHOICES = [
        ('draft', _('مسودة')),
        ('validated', _('مفحوصة')),
        ('posted', _('مرحلة')),
    ]

    fiscal_year = models.ForeignKey(FiscalYear, on_delete=models.PROTECT, related_name='opening_batches', verbose_name=_("السنة المالية"))
    batch_number = models.CharField(max_length=50, unique=True, db_index=True, verbose_name=_("رقم الدفعة"))
    description = models.TextField(blank=True, verbose_name=_("البيان"))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name=_("الحالة"))
    journal_entry = models.ForeignKey('financial.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL, related_name='opening_balance_batches', verbose_name=_("قيد الأستاذ العام"))

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = _("دفعة أرصدة افتتاحية")
        verbose_name_plural = _("دفعات الأرصدة الافتتاحية")
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.batch_number} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if self.pk:
            old = OpeningBalanceBatch.objects.get(pk=self.pk)
            if old.status == 'posted' and self.status == 'posted':
                raise ImmutableLedgerError(_("دفعة الأرصدة الافتتاحية المرحلة حصينة ولا يمكن تعديلها."))
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status == 'posted':
            raise ImmutableLedgerError(_("لا يمكن حذف دفعة أرصدة افتتاحية مرحلة."))
        super().delete(*args, **kwargs)


class OpeningBalanceLine(models.Model):
    """
    سطر رصيد افتتاحي لحساب محاسبي فرعي
    """
    batch = models.ForeignKey(OpeningBalanceBatch, related_name='lines', on_delete=models.CASCADE, verbose_name=_("الدفعة"))
    account = models.ForeignKey('financial.ChartOfAccounts', on_delete=models.PROTECT, verbose_name=_("الحساب المحاسبي"))
    debit = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'), verbose_name=_("مدين"))
    credit = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'), verbose_name=_("دائن"))

    class Meta:
        verbose_name = _("سطر رصيد افتتاحي")
        verbose_name_plural = _("أسطر الأرصدة الافتتاحية")

    def __str__(self):
        return f"{self.account.name}: Dr {self.debit} / Cr {self.credit}"

    def save(self, *args, **kwargs):
        if self.batch_id:
            batch_status = OpeningBalanceBatch.objects.filter(pk=self.batch_id).values_list('status', flat=True).first()
            if batch_status == 'posted':
                raise ImmutableLedgerError(_("لا يمكن تعديل أسطر دفعة أرصدة افتتاحية مرحلة."))
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.batch_id:
            batch_status = OpeningBalanceBatch.objects.filter(pk=self.batch_id).values_list('status', flat=True).first()
            if batch_status == 'posted':
                raise ImmutableLedgerError(_("لا يمكن حذف أسطر دفعة أرصدة افتتاحية مرحلة."))
        super().delete(*args, **kwargs)
