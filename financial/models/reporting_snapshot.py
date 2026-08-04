from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from financial.models.journal_entry import AccountingPeriod


class FinancialStatementSnapshot(models.Model):
    """
    نموذج تجميد وحفظ لقطات القوائم المالية الفترية والتاريخية (FIN-REP-003)
    يضمن تجميد الميزانيات وقوائم الدخل بعد إغلاق الفترات المحاسبية لمنع أي تغير في التقارير التاريخية
    """
    STATEMENT_TYPES = (
        ("TRIAL_BALANCE", _("ميزان المراجعة")),
        ("INCOME_STATEMENT", _("قائمة الدخل / الأرباح والخسائر")),
        ("BALANCE_SHEET", _("الميزانية العمومية / المركز المالي")),
        ("CASH_FLOW", _("قائمة التدفقات النقدية")),
    )

    snapshot_number = models.CharField(_("رقم لقطة التقرير"), max_length=50, unique=True)
    period = models.ForeignKey(
        AccountingPeriod,
        on_delete=models.PROTECT,
        verbose_name=_("الفترة المحاسبية"),
        related_name="financial_snapshots"
    )
    statement_type = models.CharField(_("نوع القائمة المالية"), max_length=30, choices=STATEMENT_TYPES)
    as_of_date = models.DateField(_("تاريخ اللقطة / حتى تاريخ"))

    statement_data = models.JSONField(_("بيانات التقرير المالية المجمدة (JSON Tree)"))
    is_closed_period = models.BooleanField(_("هل الفترة مغلقة بصفة نهائية؟"), default=False)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_("أنشئ بواسطة")
    )
    created_at = models.DateTimeField(_("تاريخ الإنشاء والتجميد"), auto_now_add=True)

    class Meta:
        verbose_name = _("لقطة قائمة مالية مجمدة")
        verbose_name_plural = _("لقطات القوائم المالية المجمدة")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["period", "statement_type"]),
            models.Index(fields=["as_of_date"]),
        ]

    def __str__(self):
        return f"Snapshot #{self.snapshot_number}: {self.get_statement_type_display()} ({self.as_of_date})"
