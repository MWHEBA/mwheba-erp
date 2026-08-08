import hashlib
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.journal_entry import JournalEntryLine


class BankStatementBatch(models.Model):
    """
    دفعة استيراد كشف الحساب البنكي (FIN-BANK-001)
    """
    STATUS_CHOICES = [
        ('imported', _('مستورد')),
        ('reconciling', _('قيد التسوية')),
        ('partially_matched', _('مطابق جزئياً')),
        ('completed', _('مكتمل والتسوية معتمدة')),
        ('reopened', _('أعيد فتحه')),
        ('failed', _('فشل التسوية')),
    ]

    batch_number = models.CharField(_("رقم الدفعة"), max_length=64, unique=True)
    bank_account = models.ForeignKey(
        ChartOfAccounts,
        on_delete=models.PROTECT,
        verbose_name=_("حساب البنك المحاسبي")
    )
    statement_date = models.DateField(_("تاريخ كشف الحساب"))
    opening_balance = models.DecimalField(_("رصيد البداية"), max_digits=15, decimal_places=2, default=Decimal('0.00'))
    closing_balance = models.DecimalField(_("رصيد النهاية"), max_digits=15, decimal_places=2, default=Decimal('0.00'))
    status = models.CharField(_("الحالة"), max_length=20, choices=STATUS_CHOICES, default='imported')
    created_at = models.DateTimeField(_("تاريخ الاستيراد"), auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_("مستورد الكشف"),
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = _("دفعة كشف حساب بنكي")
        verbose_name_plural = _("دفوعات كشوف الحسابات البنكية")

    @property
    def reconciliation_date(self):
        return self.statement_date

    @property
    def account(self):
        return self.bank_account

    @property
    def system_balance(self):
        return self.opening_balance

    @property
    def bank_balance(self):
        return self.closing_balance

    @property
    def difference(self):
        return Decimal(str(self.closing_balance)) - Decimal(str(self.opening_balance))

    def __str__(self):
        return f"Statement Batch {self.batch_number} ({self.bank_account.name})"


class BankStatementLine(models.Model):
    """
    سطر كشف الحساب البنكي الخارجي (FIN-BANK-001 & FIN-BANK-002 Line Hash Guard)
    """
    batch = models.ForeignKey(
        BankStatementBatch,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name=_("دفعة الكشف")
    )
    transaction_date = models.DateField(_("تاريخ المعاملة"))
    value_date = models.DateField(_("تاريخ الاستحقاق / القيمة"), null=True, blank=True)
    reference_number = models.CharField(_("الرقم المرجعي"), max_length=128, blank=True, default="")
    description = models.TextField(_("البيان / الوصف"), blank=True, default="")
    debit = models.DecimalField(_("مدين (إيداع)"), max_digits=15, decimal_places=2, default=Decimal('0.00'))
    credit = models.DecimalField(_("دائن (سحب)"), max_digits=15, decimal_places=2, default=Decimal('0.00'))
    
    # FIN-BANK-002: SHA-256 Line Hash Guard لمنع التكرار
    line_hash = models.CharField(_("البصمة التشفيرية للسطر"), max_length=64, unique=True, default='')
    is_matched = models.BooleanField(_("تمت المطابقة"), default=False)

    class Meta:
        verbose_name = _("سطر كشف حساب بنكي")
        verbose_name_plural = _("سطور كشف الحساب البنكي")
        indexes = [
            models.Index(fields=["batch", "is_matched"]),
            models.Index(fields=["transaction_date"]),
            models.Index(fields=["reference_number"]),
        ]

    def save(self, *args, **kwargs):
        if not self.line_hash:
            bank_id = self.batch.bank_account_id if self.batch_id else '0'
            raw_data = f"{bank_id}_{self.transaction_date}_{self.reference_number}_{self.debit}_{self.credit}_{self.description[:30]}"
            self.line_hash = hashlib.sha256(raw_data.encode('utf-8')).hexdigest()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Line {self.reference_number} ({self.debit}/{self.credit})"


class BankReconciliationMatch(models.Model):
    """
    موديل مطابقة السطور البنكية مع بنود الأستاذ العام N:M Junction Model (FIN-BANK-001 & FIN-BANK-005)
    """
    MATCH_TYPES = [
        ('EXACT', _('مطابقة تامة')),
        ('PROBABLE', _('مطابقة مرجحة')),
        ('MANUAL', _('مطابقة يدوية')),
    ]
    MATCH_STATUSES = [
        ('MATCHED', _('مطابق')),
        ('UNMATCHED', _('ملغى المطابقة')),
    ]

    statement_line = models.ForeignKey(
        BankStatementLine,
        on_delete=models.PROTECT,
        related_name='matches',
        verbose_name=_("سطر كشف البنك")
    )
    journal_line = models.ForeignKey(
        JournalEntryLine,
        on_delete=models.PROTECT,
        related_name='bank_matches',
        verbose_name=_("بند قيد الأستاذ العام")
    )
    matched_amount = models.DecimalField(_("المبلغ المطابق"), max_digits=15, decimal_places=2)
    match_type = models.CharField(_("نوع المطابقة"), max_length=20, choices=MATCH_TYPES, default='EXACT')
    status = models.CharField(_("حالة المطابقة"), max_length=20, choices=MATCH_STATUSES, default='MATCHED')
    matched_at = models.DateTimeField(_("تاريخ المطابقة"), auto_now_add=True)
    matched_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_("تم بواسطة"),
        null=True,
        blank=True
    )
    unmatched_at = models.DateTimeField(_("تاريخ فك المطابقة"), null=True, blank=True)
    unmatched_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='unmatched_bank_matches',
        verbose_name=_("فك بواسطة"),
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = _("مطابقة بنكية")
        verbose_name_plural = _("المطابقات البنكية")
        indexes = [
            models.Index(fields=["statement_line", "status"]),
            models.Index(fields=["journal_line", "status"]),
        ]

    def __str__(self):
        return f"Match {self.statement_line_id} <-> {self.journal_line_id} ({self.matched_amount})"


class BankMatchAllocation(models.Model):
    """
    نموذج تخصيص ومطابقة بنود كشف البنك مع حركات الأستاذ العام (Phase 1 Allocation Model)
    """
    ALLOCATION_STATUSES = [
        ('ACTIVE', _('نشط ومطابق')),
        ('REVIEW_REQUIRED', _('تحت المراجعة')),
        ('REVERSED', _('ملغى / مكسور')),
    ]

    statement_line = models.ForeignKey(
        BankStatementLine,
        on_delete=models.CASCADE,
        related_name='allocations',
        verbose_name=_("سطر كشف البنك")
    )
    journal_line = models.ForeignKey(
        JournalEntryLine,
        on_delete=models.PROTECT,
        related_name='bank_allocations',
        verbose_name=_("قيد الأستاذ العام المطابق"),
        null=True,
        blank=True
    )
    allocated_amount = models.DecimalField(
        _("المبلغ المخصص للمطابقة"),
        max_digits=15,
        decimal_places=2
    )
    status = models.CharField(
        _("حالة التخصيص"),
        max_length=20,
        choices=ALLOCATION_STATUSES,
        default='ACTIVE'
    )
    created_at = models.DateTimeField(_("تاريخ التخصيص"), auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("خصص بواسطة")
    )

    class Meta:
        verbose_name = _("تخصيص مطابقة بنكية")
        verbose_name_plural = _("تخصيصات المطابقات البنكية")
        indexes = [
            models.Index(fields=["statement_line", "status"]),
            models.Index(fields=["journal_line", "status"]),
        ]

    def __str__(self):
        return f"Allocation {self.statement_line_id} <-> {self.journal_line_id} ({self.allocated_amount})"

