"""
AccountBalancePeriod - نموذج الأرصدة التجميعية لكل حساب وفترة محاسبية
يحدث تلقائياً مع كل قيد يرحل لحساب الأرصدة بسرعة فائقة (< 50ms) لميزان المراجعة والتقارير المالية.
"""

from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _
from financial.models.chart_of_accounts import ChartOfAccounts


class AccountBalancePeriod(models.Model):
    """
    سجل الأرصدة التجميعية للحساب حسب السنة والشهر والعملة (Fast Balances Snapshot)
    """
    account = models.ForeignKey(
        ChartOfAccounts,
        on_delete=models.CASCADE,
        related_name="period_balances",
        verbose_name=_("الحساب المحاسبي")
    )
    year = models.IntegerField(_("السنة المالية"), db_index=True)
    month = models.IntegerField(_("الشهر"), db_index=True)
    currency_code = models.CharField(_("رمز العملة"), max_length=10, default="EGP", db_index=True)

    beginning_debit = models.DecimalField(_("رصيد بداية الفترة مدين"), max_digits=18, decimal_places=2, default=Decimal("0.00"))
    beginning_credit = models.DecimalField(_("رصيد بداية الفترة دائن"), max_digits=18, decimal_places=2, default=Decimal("0.00"))

    period_debit = models.DecimalField(_("حركة الفترة مدين"), max_digits=18, decimal_places=2, default=Decimal("0.00"))
    period_credit = models.DecimalField(_("حركة الفترة دائن"), max_digits=18, decimal_places=2, default=Decimal("0.00"))

    ending_debit = models.DecimalField(_("رصيد نهاية الفترة مدين"), max_digits=18, decimal_places=2, default=Decimal("0.00"))
    ending_credit = models.DecimalField(_("رصيد نهاية الفترة دائن"), max_digits=18, decimal_places=2, default=Decimal("0.00"))

    net_balance = models.DecimalField(_("صافي الرصيد النهائي"), max_digits=18, decimal_places=2, default=Decimal("0.00"))

    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)

    class Meta:
        verbose_name = _("رصيد تجميعي لفترة محاسبية")
        verbose_name_plural = _("الأرصدة التجميعية للفترات المحاسبية")
        unique_together = ("account", "year", "month", "currency_code")
        indexes = [
            models.Index(fields=["year", "month", "account"]),
            models.Index(fields=["account", "currency_code"]),
        ]

    def __str__(self):
        return f"{self.account.code} - {self.year}/{self.month:02d} ({self.currency_code}): Net={self.net_balance}"

    def recalculate_totals(self):
        """إعادة إحساب رصيد النهاية والصافي"""
        total_debit = self.beginning_debit + self.period_debit
        total_credit = self.beginning_credit + self.period_credit

        if total_debit >= total_credit:
            self.ending_debit = total_debit - total_credit
            self.ending_credit = Decimal("0.00")
            self.net_balance = self.ending_debit
        else:
            self.ending_debit = Decimal("0.00")
            self.ending_credit = total_credit - total_debit
            self.net_balance = -self.ending_credit
