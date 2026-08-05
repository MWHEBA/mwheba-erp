from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from decimal import Decimal


from django.conf import settings

class CostCenterBudget(models.Model):
    """
    نموذج الميزانيات المعتمدة لمراكز التكلفة بـ الإصدارات وتتبع الانحرافات (CostCenterBudget Model)
    """
    STATUS_CHOICES = (
        ('DRAFT', _('مسودة')),
        ('SUBMITTED', _('مقدمة للاعتماد')),
        ('APPROVED', _('معتمدة')),
        ('REVISED', _('معدلة')),
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
    budget_amount = models.DecimalField(_("الميزانية المعتمدة (ج.م)"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    budget_allocation_method = models.CharField(_("طريقة توزيع الميزانية"), max_length=20, default='EQUAL')
    cached_spent_amount = models.DecimalField(_("المبلغ المنفق المخزن كاش"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(_("حالة الميزانية"), max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    def __init__(self, *args, **kwargs):
        if 'allocated_amount' in kwargs:
            kwargs['budget_amount'] = kwargs.pop('allocated_amount')
        super().__init__(*args, **kwargs)

    @property
    def allocated_amount(self):
        return self.budget_amount

    @allocated_amount.setter
    def allocated_amount(self, value):
        self.budget_amount = value

    @property
    def current_budget(self):
        return self.budget_amount
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_cost_center_budgets')
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
        return self.budget_amount


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


class CostCenterBudgetLine(models.Model):
    """
    بنود الموازنة لكل حساب محاسبي وسياسات الرقابة الوقائية
    """
    CONTROL_POLICIES = (
        ('BLOCK', _('حظر ترحيل القيد عند التجاوز (BLOCK)')),
        ('WARN', _('تحذير فقط مع السماح بالترحيل (WARN)')),
        ('REQUIRES_APPROVAL', _('يتطلب موافقة استثنائية (REQUIRES_APPROVAL)')),
        ('ALLOW', _('سماح بدون قيود (ALLOW)')),
    )

    budget = models.ForeignKey(CostCenterBudget, on_delete=models.CASCADE, related_name='lines', verbose_name=_("الموازنة"))
    account = models.ForeignKey('financial.ChartOfAccounts', on_delete=models.PROTECT, related_name='cost_center_budget_lines', verbose_name=_("الحساب المحاسبي"))
    allocated_amount = models.DecimalField(_("المبلغ المخصص المعتمد"), max_digits=15, decimal_places=2, default=Decimal('0.00'))
    control_policy = models.CharField(_("سياسة الرقابة الوقائية"), max_length=30, choices=CONTROL_POLICIES, default='BLOCK')
    notes = models.TextField(_("ملاحظات البند"), blank=True, null=True, default="")


    class Meta:
        verbose_name = _("بند موازنة مركز تكلفة")
        verbose_name_plural = _("بنود موازنات مراكز التكلفة")
        unique_together = ('budget', 'account')

    def __str__(self):
        return f"{self.budget.cost_center.code} - {self.account.name}: {self.allocated_amount}"


class CostCenterBudgetPeriod(models.Model):
    """
    التوزيع التقديري للبند عبر الفترات المحاسبية
    """
    budget_line = models.ForeignKey(CostCenterBudgetLine, on_delete=models.CASCADE, related_name='periods')
    accounting_period = models.ForeignKey('financial.AccountingPeriod', on_delete=models.PROTECT)
    period_allocated_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        unique_together = ('budget_line', 'accounting_period')


class CostCenterActualSnapshot(models.Model):
    """
    لقطة الرصيد الفعلي والالتزامات السريعة (< 50ms)
    """
    cost_center = models.ForeignKey('financial.CostCenter', on_delete=models.CASCADE, related_name='actual_snapshots')
    account = models.ForeignKey('financial.ChartOfAccounts', on_delete=models.CASCADE, related_name='actual_snapshots')
    accounting_period = models.ForeignKey('financial.AccountingPeriod', on_delete=models.CASCADE, related_name='actual_snapshots')
    actual_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    committed_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('cost_center', 'account', 'accounting_period')


class BudgetOverrideRequest(models.Model):
    """
    طلبات الموافقة الاستثنائية لتجاوز سقف الموازنة
    """
    STATUS_CHOICES = (
        ('PENDING', _('قيد النظر')),
        ('APPROVED', _('مقبول استثنائياً')),
        ('REJECTED', _('مرفوض')),
    )

    document_type = models.CharField(max_length=50, blank=True, null=True)
    document_id = models.IntegerField(blank=True, null=True)
    cost_center = models.ForeignKey('financial.CostCenter', on_delete=models.CASCADE, related_name='override_requests')
    account = models.ForeignKey('financial.ChartOfAccounts', on_delete=models.CASCADE, related_name='override_requests')
    requested_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    budget_exceeded_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    reason = models.TextField(_("سبب التجاوز"))
    approval_comment = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='requested_budget_overrides')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_budget_overrides')
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)


