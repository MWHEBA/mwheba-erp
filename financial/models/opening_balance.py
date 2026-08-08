import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.exceptions import ValidationError

from financial.models.fiscal_year import FiscalYear
from financial.exceptions import ImmutableLedgerError

User = settings.AUTH_USER_MODEL


class OpeningBalanceBatch(models.Model):
    """
    دفعة الأرصدة الافتتاحية للسنة المالية - المصدر المحاسبي المركزي الموحد
    """
    STATUS_CHOICES = [
        ('draft', _('مسودة')),
        ('validated', _('مفحوصة')),
        ('approved', _('معتمدة')),
        ('posted', _('مرحلة')),
        ('reversed', _('معكوسة')),
    ]

    company_code = models.CharField(_("كود الشركة"), max_length=50, default='DEFAULT')
    fiscal_year = models.ForeignKey(
        FiscalYear,
        on_delete=models.PROTECT,
        related_name='opening_batches',
        verbose_name=_("السنة المالية")
    )
    batch_number = models.CharField(_("رقم الدفعة"), max_length=50, unique=True, db_index=True)
    opening_date = models.DateField(_("تاريخ الرصيد الافتتاحي"), default=timezone.now)
    description = models.TextField(_("البيان"), blank=True)
    status = models.CharField(_("الحالة"), max_length=20, choices=STATUS_CHOICES, default='draft')
    posting_key = models.UUIDField(_("مفتاح الترحيل الفريد"), default=uuid.uuid4, null=True, blank=True, editable=False)

    journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='opening_balance_batches',
        verbose_name=_("قيد الأستاذ العام الافتتاحي")
    )
    reversal_journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='reversed_opening_balance_batches',
        verbose_name=_("قيد العكس الافتتاحي")
    )

    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='opening_batches_created')
    approved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='opening_batches_approved')
    posted_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='opening_batches_posted')
    reversed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='opening_batches_reversed')

    created_at = models.DateTimeField(default=timezone.now)
    approved_at = models.DateTimeField(null=True, blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    reversed_at = models.DateTimeField(null=True, blank=True)

    reversal_reason = models.TextField(_("سبب العكس"), blank=True)

    INVENTORY_SYNC_STATUS_CHOICES = [
        ('NONE', _('لا يوجد')),
        ('PENDING', _('قيد الانتظار')),
        ('PROCESSING', _('قيد المعالجة')),
        ('COMPLETED', _('مكتملة')),
        ('FAILED', _('فشلت')),
    ]

    inventory_sync_status = models.CharField(_("حالة مزامنة المخزون"), max_length=20, choices=INVENTORY_SYNC_STATUS_CHOICES, default='NONE')
    retry_count = models.PositiveIntegerField(_("عدد محاولات المزامنة"), default=0)
    last_error = models.TextField(_("تفاصيل آخر خطأ للمزامنة"), blank=True, null=True)
    last_attempt_at = models.DateTimeField(_("تاريخ آخر محاولة"), null=True, blank=True)
    last_attempt_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='inventory_sync_attempts', verbose_name=_("آخر محاول بواسطة"))
    inventory_sync_key = models.CharField(_("مفتاح فرادة المزامنة"), max_length=100, unique=True, null=True, blank=True)

    class Meta:
        verbose_name = _("دفعة أرصدة افتتاحية")
        verbose_name_plural = _("دفعات الأرصدة الافتتاحية")
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['fiscal_year'],
                condition=models.Q(status='posted'),
                name='unique_posted_opening_batch_per_fiscal_year'
            )
        ]

    def __str__(self):
        return f"{self.batch_number} ({self.get_status_display()})"

    def clean(self):
        super().clean()
        if self.fiscal_year and hasattr(self.fiscal_year, 'is_closed') and self.fiscal_year.is_closed:
            raise ValidationError(_("لا يمكن إنشاء أو تعديل دفعة افتتاحية على سنة مالية مغلقة."))

    def save(self, *args, **kwargs):
        if self.pk:
            old = OpeningBalanceBatch.objects.filter(pk=self.pk).first()
            if old and old.status in ['posted', 'reversed'] and self.status in ['posted', 'reversed'] and old.status == self.status:
                raise ImmutableLedgerError(_("دفعة الأرصدة الافتتاحية المرحلة أو المعكوسة حصينة ولا يمكن تعديلها مباشرة."))
        self.clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status in ['posted', 'reversed']:
            raise ImmutableLedgerError(_("لا يمكن حذف دفعة أرصدة افتتاحية مرحلة أو معكوسة."))
        super().delete(*args, **kwargs)


class ControlAccountOverrideRequest(models.Model):
    """
    طلب موافقة واستثناء محاسبي للإدخال المباشر على الحسابات الحاكمة (CFO Approval Override)
    """
    STATUS_CHOICES = [
        ('requested', _('مطلوبة')),
        ('approved', _('معتمدة')),
        ('rejected', _('مرفوضة')),
    ]
    opening_batch = models.ForeignKey(OpeningBalanceBatch, on_delete=models.CASCADE, related_name='override_requests', verbose_name=_("الدفعة الافتتاحية"))
    account = models.ForeignKey('financial.ChartOfAccounts', on_delete=models.CASCADE, verbose_name=_("الحساب الحاكم"))
    requested_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='control_overrides_requested', verbose_name=_("طالب الاستثناء"))
    approved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name='control_overrides_approved', verbose_name=_("المعتمد (CFO)"))
    reason = models.TextField(_("سبب الاستثناء المحاسبي"))
    approved_at = models.DateTimeField(_("تاريخ الاعتماد"), null=True, blank=True)
    status = models.CharField(_("الحالة"), max_length=20, choices=STATUS_CHOICES, default='requested')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("طلب استثناء حساب حاكم")
        verbose_name_plural = _("طلبات استثناء الحسابات الحاكمة")

    def __str__(self):
        return f"Override {self.account.code} for Batch {self.opening_batch.batch_number} ({self.get_status_display()})"

    def is_valid_for(self, batch, account):
        batch_id = batch.id if hasattr(batch, 'id') else batch
        account_id = account.id if hasattr(account, 'id') else account
        return (
            self.status == 'approved' and
            self.opening_batch_id == batch_id and
            self.account_id == account_id
        )


class OpeningBalanceImportBatch(models.Model):
    """
    سجل تدقيق استيراد ملفات الأرصدة الافتتاحية مجمعة
    """
    file_name = models.CharField(_("اسم الملف"), max_length=255)
    template_version = models.CharField(_("نسخة القالب"), max_length=20, default='v1.0')
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name=_("مرفوع بواسطة"))
    uploaded_at = models.DateTimeField(auto_now_add=True)
    total_rows = models.PositiveIntegerField(_("إجمالي الصفوف"), default=0)
    valid_rows = models.PositiveIntegerField(_("الصفوف الصحيحة"), default=0)
    invalid_rows = models.PositiveIntegerField(_("الصفوف الفاسدة"), default=0)

    class Meta:
        verbose_name = _("دفعة استيراد أرصدة افتتاحية")
        verbose_name_plural = _("دفعات استيراد الأرصدة الافتتاحية")


class OpeningBalanceLine(models.Model):
    """
    سطر رصيد افتتاحي لحساب محاسبي فرعي أو عام
    """
    LINE_TYPE_CHOICES = [
        ('GL', _('حساب عام')),
        ('AR', _('رصيد عميل')),
        ('AP', _('رصيد مورد')),
        ('TREASURY', _('خزينة/بنك')),
        ('INVENTORY', _('مخزون أول المدة')),
    ]

    batch = models.ForeignKey(OpeningBalanceBatch, related_name='lines', on_delete=models.CASCADE, verbose_name=_("الدفعة"))
    line_type = models.CharField(_("نوع السطر"), max_length=20, choices=LINE_TYPE_CHOICES, default='GL')
    account = models.ForeignKey('financial.ChartOfAccounts', on_delete=models.PROTECT, verbose_name=_("الحساب المحاسبي"))

    currency = models.ForeignKey('financial.Currency', null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_("العملة الأجنبية"))
    debit_foreign = models.DecimalField(_("مدين بالعملة الأجنبية"), max_digits=15, decimal_places=2, default=Decimal('0.00'))
    credit_foreign = models.DecimalField(_("دائن بالعملة الأجنبية"), max_digits=15, decimal_places=2, default=Decimal('0.00'))
    exchange_rate = models.DecimalField(_("سعر الصرف"), max_digits=12, decimal_places=6, default=Decimal('1.000000'))

    debit = models.DecimalField(_("مدين (عملة وظيفية)"), max_digits=15, decimal_places=2, default=Decimal('0.00'), help_text=_("المبلغ بالعملة الوظيفية النظامية"))
    credit = models.DecimalField(_("دائن (عملة وظيفية)"), max_digits=15, decimal_places=2, default=Decimal('0.00'), help_text=_("المبلغ بالعملة الوظيفية النظامية"))

    customer = models.ForeignKey('client.Customer', null=True, blank=True, on_delete=models.PROTECT, verbose_name=_("العميل"))
    supplier = models.ForeignKey('supplier.Supplier', null=True, blank=True, on_delete=models.PROTECT, verbose_name=_("المورد"))
    treasury_account = models.ForeignKey('financial.ChartOfAccounts', null=True, blank=True, on_delete=models.PROTECT, related_name='treasury_opening_lines', verbose_name=_("حساب الخزينة/البنك"))
    inventory_snapshot_id = models.CharField(_("معرف Snapshot التقييم للمخزون"), max_length=100, blank=True, null=True)

    class Meta:
        verbose_name = _("سطر رصيد افتتاحي")
        verbose_name_plural = _("أسطر الأرصدة الافتتاحية")

    def __str__(self):
        return f"[{self.get_line_type_display()}] {self.account.name}: Dr {self.debit} / Cr {self.credit}"

    def clean(self):
        super().clean()
        # 1. Validation based on line_type
        if self.line_type == 'AR' and not self.customer_id:
            raise ValidationError(_("يجب تحديد العميل عند اختيار نوع السطر رصيد عميل (AR)."))
        if self.line_type == 'AP' and not self.supplier_id:
            raise ValidationError(_("يجب تحديد المورد عند اختيار نوع السطر رصيد مورد (AP)."))
        if self.line_type == 'TREASURY' and not self.treasury_account_id:
            raise ValidationError(_("يجب تحديد حساب الخزينة/البنك عند اختيار نوع السطر (TREASURY)."))
        if self.line_type == 'GL':
            if self.customer_id or self.supplier_id or self.treasury_account_id:
                raise ValidationError(_("أسطر الحسابات العامة (GL) لا ترتبط بكائنات فرعية مباشرة."))
            # Control Account check for GL lines
            if self.account_id and hasattr(self.account, 'code'):
                from financial.services.role_registry import AccountRoleRegistry
                try:
                    control_codes = {
                        AccountRoleRegistry.resolve_role_code("AR_CONTROL_ACCOUNT"),
                        AccountRoleRegistry.resolve_role_code("AP_CONTROL_ACCOUNT"),
                        AccountRoleRegistry.resolve_role_code("DEFAULT_CASH_DRAWER"),
                        AccountRoleRegistry.resolve_role_code("DEFAULT_BANK_ACCOUNT"),
                        AccountRoleRegistry.resolve_role_code("INVENTORY_GENERAL"),
                    }
                    if self.account.code in control_codes:
                        # Check override
                        has_override = ControlAccountOverrideRequest.objects.filter(
                            opening_batch_id=self.batch_id,
                            account_id=self.account_id,
                            status='approved'
                        ).exists()
                        if not has_override:
                            raise ValidationError(_("لا يمكن الإدخال المباشر بنوع GL على الحساب الحاكم ({}) بدون موافقة استثناء معتمدة من CFO.").format(self.account.name))
                except ValidationError:
                    raise
                except Exception:
                    pass

        # 2. Validation for Foreign Currency
        if self.currency_id:
            if self.exchange_rate <= 0:
                raise ValidationError(_("سعر الصرف يجب أن يكون أكبر من الصفر."))
            
            foreign_amt = self.debit_foreign if self.debit_foreign > 0 else self.credit_foreign
            func_amt = self.debit if self.debit > 0 else self.credit
            
            if foreign_amt > 0 and func_amt > 0:
                expected_func = (foreign_amt * self.exchange_rate).quantize(Decimal('0.01'))
                if abs(expected_func - func_amt) > Decimal('0.05'):
                    raise ValidationError(_("المبلغ بالعملة الوظيفية ({}) لا يطابق حاصل ضرب المبلغ الأجنبي في سعر الصرف ({}).").format(func_amt, expected_func))

    def save(self, *args, **kwargs):
        if self.batch_id:
            batch_status = OpeningBalanceBatch.objects.filter(pk=self.batch_id).values_list('status', flat=True).first()
            if batch_status in ['posted', 'reversed']:
                raise ImmutableLedgerError(_("لا يمكن تعديل أسطر دفعة أرصدة افتتاحية مرحلة أو معكوسة."))
        self.clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.batch_id:
            batch_status = OpeningBalanceBatch.objects.filter(pk=self.batch_id).values_list('status', flat=True).first()
            if batch_status in ['posted', 'reversed']:
                raise ImmutableLedgerError(_("لا يمكن حذف أسطر دفعة أرصدة افتتاحية مرحلة أو معكوسة."))
        super().delete(*args, **kwargs)

