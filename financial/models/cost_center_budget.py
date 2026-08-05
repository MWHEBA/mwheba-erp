from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from decimal import Decimal


class CostCenterBudget(models.Model):
    """
    نموذج الميزانيات المعتمدة لمراكز التكلفة بـ الإصدارات وتتبع الانحرافات (CostCenterBudget Model)
    """
    STATUS_CHOICES = (
        ('DRAFT', _('مسودة')),
        ('APPROVED', _('معتمدة')),
        ('ARCHIVED', _('مؤرشفة')),
    )

    cost_center = models.ForeignKey(
        'financial.CostCenter',
        on_delete=models.CASCADE,
        related_name='budgets',
        verbose_name=_("مركز التكلفة")
    )
    fiscal_year = models.ForeignKey(
        'financial.FiscalYear',
        on_delete=models.PROTECT,
        related_name='cost_center_budgets',
        verbose_name=_("السنة المالية")
    )
    version = models.PositiveIntegerField(_("رقم الإصدار"), default=1)
    allocated_amount = models.DecimalField(_("الميزانية المعتمدة (ج.م)"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    revised_amount = models.DecimalField(_("الميزانية المعدلة (ج.م)"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(_("حالة الميزانية"), max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    notes = models.TextField(_("ملاحظات الميزانية"), blank=True, null=True)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)

    class Meta:
        verbose_name = _("ميزانية مركز تكلفة")
        verbose_name_plural = _("ميزانيات مراكز التكلفة")
        unique_together = ('cost_center', 'fiscal_year', 'version')
        ordering = ['-fiscal_year', 'cost_center', '-version']

    def __str__(self):
        return f"{self.cost_center.code} - {self.fiscal_year.name} (V{self.version})"

    @property
    def current_budget(self):
        """إجمالي الميزانية الحالية الفعالة"""
        return self.revised_amount if self.revised_amount > 0 else self.allocated_amount

    def clean(self):
        super().clean()
        if self.pk:
            old = CostCenterBudget.objects.get(pk=self.pk)
            if old.status == 'APPROVED' and self.status == 'APPROVED':
                # منع تعديل الميزانية المعتمدة إلا عبر إنشاء إصدار جديد (Versioning)
                if old.allocated_amount != self.allocated_amount:
                    raise ValidationError(_("حظر الحوكمة: الميزانية المعتمدة حصينة، يلزم إنشاء إصدار جديد (Version) للتعديل."))

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class CostCenterBalanceSnapshot(models.Model):
    """
    لقطات الأرصدة التجميعية لمراكز التكلفة مقسمة حسب السنة المالية والعملة (CostCenterBalanceSnapshot Model)
    """
    cost_center = models.ForeignKey(
        'financial.CostCenter',
        on_delete=models.CASCADE,
        related_name='balance_snapshots',
        verbose_name=_("مركز التكلفة")
    )
    fiscal_year = models.ForeignKey(
        'financial.FiscalYear',
        on_delete=models.CASCADE,
        related_name='cc_balance_snapshots',
        verbose_name=_("السنة المالية")
    )
    currency = models.CharField(_("العملة"), max_length=3, default="EGP")
    total_debit = models.DecimalField(_("إجمالي المدين"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    total_credit = models.DecimalField(_("إجمالي الدائن"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    net_balance = models.DecimalField(_("الرصيد الصافي"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    updated_at = models.DateTimeField(_("آخر تحديث"), auto_now=True)

    class Meta:
        verbose_name = _("لقطة رصيد مركز تكلفة")
        verbose_name_plural = _("لقطات أرصدة مراكز التكلفة")
        unique_together = ('cost_center', 'fiscal_year', 'currency')

    def __str__(self):
        return f"{self.cost_center.code} - {self.fiscal_year.name} [{self.currency}]: {self.net_balance}"

    def recalculate(self):
        """إعادة احتساب الأرصدة الإجمالية من أسطر القيود المرحّلة"""
        from financial.models.journal_entry import JournalEntryLine
        qs = JournalEntryLine.objects.filter(
            cost_center=self.cost_center,
            journal_entry__status='posted',
            journal_entry__accounting_period__fiscal_year=self.fiscal_year,
            currency=self.currency
        )
        debit_sum = sum(l.debit for l in qs) or Decimal("0.00")
        credit_sum = sum(l.credit for l in qs) or Decimal("0.00")
        self.total_debit = debit_sum
        self.total_credit = credit_sum
        self.net_balance = debit_sum - credit_sum
        self.save()
