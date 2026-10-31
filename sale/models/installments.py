# -*- coding: utf-8 -*-
from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.conf import settings


class InstallmentPlan(models.Model):
    """
    جدول التقسيط الرئيسي المرتبط بفاتورة المبيعات
    """
    class PlanStatus(models.TextChoices):
        DRAFT = 'DRAFT', _('مسودة')
        ACTIVE = 'ACTIVE', _('ساري ونشط')
        COMPLETED = 'COMPLETED', _('مسدد بالكامل')
        CURTAILED = 'CURTAILED', _('منتهية بالتقليص الرضائي')
        INSOLVENCY_MORATORIUM = 'INSOLVENCY_MORATORIUM', _('مجمدة للتصفية والإفلاس قضائياً')
        DEFAULTED = 'DEFAULTED', _('متعثر')
        DISPUTED = 'DISPUTED', _('متنازع عليها / معلقة لجودة')
        CANCELLED = 'CANCELLED', _('ملغي')

    class PlanType(models.TextChoices):
        ASSET_FINANCING = 'ASSET_FINANCING', _('تمويل أصول ومعدات (زمني ثابت)')
        SUPPLY_CONTRACT = 'SUPPLY_CONTRACT', _('عقد توريد مطبوعات (مرتبط بالتسليم)')

    sale = models.OneToOneField(
        'sale.Sale',
        on_delete=models.PROTECT,
        related_name='installment_plan',
        verbose_name=_('فاتورة المبيعات')
    )
    customer = models.ForeignKey(
        'customer.Customer',
        on_delete=models.PROTECT,
        related_name='installment_plans',
        verbose_name=_('العميل')
    )
    plan_type = models.CharField(
        max_length=30,
        choices=PlanType.choices,
        default=PlanType.ASSET_FINANCING,
        verbose_name=_('نوع خطة التقسيط')
    )
    total_principal = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name=_('أصل المبلغ المقسط بعد خصم المقدم')
    )
    markup_rate = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        default=Decimal('0.000'),
        verbose_name=_('نسبة أرباح التقسيط (%)')
    )
    total_markup = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي أرباح التقسيط الصافية')
    )
    total_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name=_('إجمالي خطة التقسيط (أصل + أرباح)')
    )
    down_payment = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('الدفعة المقدمة المسددة')
    )
    number_of_installments = models.PositiveIntegerField(
        verbose_name=_('عدد الأقساط')
    )
    frequency = models.CharField(
        max_length=20,
        choices=[
            ('MONTHLY', _('شهري')),
            ('QUARTERLY', _('ربع سنوي')),
            ('BIWEEKLY', _('كل أسبوعين')),
            ('CUSTOM', _('مخصص / دفعات تسليم')),
        ],
        default='MONTHLY',
        verbose_name=_('دورية الأقساط')
    )
    max_tolerance_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.00'),
        verbose_name=_('نسبة التفاوت المسموحة بالزيادة/النقص (%)')
    )
    start_date = models.DateField(verbose_name=_('تاريخ أول قسط'))
    status = models.CharField(
        max_length=30,
        choices=PlanStatus.choices,
        default=PlanStatus.DRAFT,
        db_index=True,
        verbose_name=_('حالة الخطة')
    )
    collateral_cheque = models.ForeignKey(
        'cheques.Cheque',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='secured_installment_plans',
        verbose_name=_('شيك الضمان المرهون للخطة')
    )
    collateral_lg_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_('رقم خطاب الضمان البنكي المرهون')
    )
    collateral_lg_expiry_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ انتهاء صلاحية خطاب الضمان البنكي')
    )
    collateral_lg_bank = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        verbose_name=_('البنك المصدر لخطاب الضمان')
    )
    payment_term = models.ForeignKey(
        'customer.PaymentTerm',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('شرط الدفع المرجعي')
    )
    unearned_revenue_account = models.ForeignKey(
        'financial.ChartOfAccounts',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='installment_unearned_revenues',
        verbose_name=_('حساب أرباح تقسيط غير محققة (21400)')
    )
    is_accelerated = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name=_('سقوط الأجل وحلول الأقساط الجبري')
    )
    accelerated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ سقوط الأجل الجبري')
    )
    accelerated_reason = models.TextField(
        blank=True,
        verbose_name=_('سبب إسقاط الأجل الجبري')
    )
    guarantor_name = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name=_('اسم الكفيل الغارم المتضامن')
    )
    guarantor_national_id = models.CharField(
        max_length=14,
        blank=True,
        null=True,
        verbose_name=_('الرقم القومي للكفيل المتضامن')
    )
    guarantor_phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name=_('هاتف الكفيل المتضامن')
    )
    guarantor_address = models.TextField(
        blank=True,
        null=True,
        verbose_name=_('الموطن المختار للكفيل المتضامن')
    )
    is_escalation_adjusted = models.BooleanField(
        default=False,
        verbose_name=_('خضعت لتعديل أسعار الخامات التضخمي')
    )
    cost_center = models.ForeignKey(
        'financial.CostCenter',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='installment_plans',
        verbose_name=_('مركز التكلفة / الفرع')
    )
    assigned_collector = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_installment_plans',
        verbose_name=_('المحصل المسؤول')
    )
    notes = models.TextField(blank=True, verbose_name=_('شروط وملاحظات الجدولة'))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_installment_plans',
        verbose_name=_('أنشئ بواسطة')
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ الإنشاء'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('تاريخ التحديث'))

    class Meta:
        verbose_name = _('خطة تقسيط مبيعات')
        verbose_name_plural = _('خطط تقسيط المبيعات')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.sale.number} - {self.customer.name} ({self.get_status_display()})"


class InstallmentItem(models.Model):
    """
    القسط الفردي (Maturity Tranche)
    """
    class PaperCoverage(models.TextChoices):
        UNCOVERED = 'UNCOVERED', _('مكشوف بدون ورقة')
        PORTFOLIO_CHEQUE = 'PORTFOLIO_CHEQUE', _('مغطى بشيك في الخزينة')
        BANK_DEPOSITED = 'BANK_DEPOSITED', _('مغطى بشيك مودع بالبنك')
        ENDORSED_TO_SUPPLIER = 'ENDORSED_TO_SUPPLIER', _('مغطى بشيك مظهر لمورد خامات')
        BANK_LETTER_OF_GUARANTEE = 'BANK_LG', _('مغطى بخطاب ضمان بنكي')
        CHEQUE_SIGNATURE_PENDING = 'CHEQUE_SIGNATURE_PENDING', _('شيك معلق لاستيفاء التوقيع الثاني')
        CHEQUE_EXCEEDS_DUE = 'CHEQUE_EXCEEDS_DUE', _('شيك فائض القيمة بعد مرتجع')
        PARTIALLY_COVERED = 'PARTIALLY_COVERED', _('مغطى جزئياً بورقة')
        HYBRID = 'HYBRID', _('تغطية مركبة (كاش + شيك)')
        DIRECT_CASH = 'DIRECT_CASH', _('مسدد بسند قبض نقدي')

    class CashStatus(models.TextChoices):
        PENDING = 'PENDING', _('في انتظار الاستحقاق')
        PARTIALLY_PAID = 'PARTIALLY_PAID', _('مسدد جزئياً')
        COLLECTED = 'COLLECTED', _('محصل نقداً بالكامل')
        COLLECTED_IN_TRANSIT = 'COLLECTED_IN_TRANSIT', _('محصل نقداً بعهدة المحصل بالطريق')
        COLLECTED_CONTRA = 'COLLECTED_CONTRA', _('مسدد بمقاصة حسابات شركاء')
        OVERDUE = 'OVERDUE', _('متأخر عن السداد')
        HOLD_REWORK = 'HOLD_REWORK', _('معلق لإعادة التشغيل / عيب طباعة')
        TRANSIT_DAMAGE_CLAIM = 'TRANSIT_DAMAGE_CLAIM', _('معلق لمطالبة تلف نقل وشحن')
        BOUNCED = 'BOUNCED', _('شيك مرتد')
        LEGAL_ACTION = 'LEGAL_ACTION', _('محال للشؤون القانونية / دعوى قضائية')
        LEGAL_SETTLEMENT = 'LEGAL_SETTLEMENT', _('تسوية وتصالح قضائي')
        WAIVED = 'WAIVED', _('مسقط بسداد معجل / مرتجع')

    class TriggerType(models.TextChoices):
        DATE_BASED = 'DATE_BASED', _('استحقاق زمني محدد')
        DELIVERY_LINKED = 'DELIVERY_LINKED', _('مرتبط باعتماد إذن التسليم')

    plan = models.ForeignKey(
        InstallmentPlan,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name=_('جدول التقسيط')
    )
    installment_number = models.PositiveIntegerField(verbose_name=_('رقم القسط'))
    trigger_type = models.CharField(
        max_length=20,
        choices=TriggerType.choices,
        default=TriggerType.DATE_BASED,
        verbose_name=_('نوع محفز الاستحقاق')
    )
    linked_delivery_note = models.ForeignKey(
        'sale.DeliveryNote',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='linked_installments',
        verbose_name=_('إذن التسليم المرتبط')
    )
    linked_delivery_notes = models.ManyToManyField(
        'sale.DeliveryNote',
        blank=True,
        related_name='linked_periodic_installments',
        verbose_name=_('أذون التسليم المرتبطة بالاستدعاء (Call-Off)')
    )
    due_date = models.DateField(db_index=True, verbose_name=_('تاريخ الاستحقاق'))
    original_due_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ الاستحقاق الأصلي قبل الترحيل')
    )
    principal_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name=_('أصل القسط')
    )
    interest_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('فائدة القسط')
    )
    total_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name=_('إجمالي قيمة القسط')
    )
    paid_principal = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('أصل القسط المسدد فعلياً')
    )
    paid_interest = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('فائدة القسط المسددة فعلياً')
    )
    paid_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('المسدد فعلياً (أصل + فائدة)')
    )
    settled_principal = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('أصل القسط المسوى بخصومات/تسويات تعاقدية')
    )
    waived_interest = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('فائدة القسط المسقطة/الملغاة بتسويات')
    )
    rebated_interest = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('فائدة مدفوعة مقدماً مردودة للعميل')
    )
    recognized_interest = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('الفائدة المعترف بها كإيراد')
    )
    is_interest_recognized = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name=_('تم الاعتراف بإيراد الفائدة في 42200')
    )
    interest_recognized_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ وتوقيت الاعتراف بالإيراد')
    )
    coverage_cash_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('المغطى نقداً')
    )
    coverage_cheque_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('المغطى بشيكات')
    )
    paper_coverage = models.CharField(
        max_length=30,
        choices=PaperCoverage.choices,
        default=PaperCoverage.UNCOVERED,
        db_index=True,
        verbose_name=_('حالة التغطية الورقية')
    )
    cash_status = models.CharField(
        max_length=30,
        choices=CashStatus.choices,
        default=CashStatus.PENDING,
        db_index=True,
        verbose_name=_('حالة التسييل النقدي')
    )
    paid_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ التسييل الفعلي')
    )
    grace_period_days = models.PositiveIntegerField(
        default=3,
        verbose_name=_('أيام السماح')
    )
    penalty_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('غرامة التأخير')
    )
    is_retention_guarantee = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name=_('قسط ضمان أعمال / تأمين حسن تنفيذ')
    )
    is_overrun_adjusted = models.BooleanField(
        default=False,
        verbose_name=_('تم تعديل القسط بزيادة التفاوت المشروعة')
    )
    is_supplemental = models.BooleanField(
        default=False,
        verbose_name=_('قسط ملحق بإشعار مدين')
    )
    fx_residual_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('رصيد متبقي فروق العملة للقسط')
    )
    wht_withheld_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('المبلغ المقابل لضريبة الخصم المحجوزة لدى الغير')
    )
    wht_form41_received = models.BooleanField(
        default=False,
        verbose_name=_('تم استلام إشعار نموذج 41 ضرائب الورقي')
    )
    volume_rebate_discount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('خصم بونص الكميات السنوي')
    )
    transit_damage_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('قيمة التالف في النقل المعلق للمطالبة')
    )
    contra_settlement_reference = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_('رقم سند مقاصة الحسابات المتقابلة')
    )
    warranty_release_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ الإفراج المعتمد عن ضمان الأعمال')
    )
    last_reminder_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ آخر إشعار تذكير مرسل')
    )
    reminder_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_('عدد إشعارات التذكير المرسلة')
    )
    court_case_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_('رقم الدعوى القضائية / المحضر')
    )
    court_name = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        verbose_name=_('المحكمة المختصة / الدائرة')
    )
    legal_referral_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ الإحالة للشؤون القانونية')
    )
    notes = models.TextField(
        blank=True,
        default="",
        verbose_name=_('ملاحظات القسط')
    )
    recognized_interest_entry = models.ForeignKey(
        'financial.JournalEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('قيد الاعتراف بالإيراد المحقق (42200)')
    )
    cheques = models.ManyToManyField(
        'cheques.Cheque',
        blank=True,
        related_name='installment_items',
        verbose_name=_('الشيكات المرتبطة')
    )

    @property
    def remaining_principal(self):
        """أصل القسط المتبقي بعد المدفوع والتسويات التعاقدية"""
        return max(Decimal('0.00'), self.principal_amount - self.paid_principal - self.settled_principal)

    @property
    def remaining_interest(self):
        """فائدة القسط المتبقية بعد المدفوع والفوائد المسقطة"""
        return max(Decimal('0.00'), self.interest_amount - self.paid_interest - self.waived_interest)

    @property
    def unearned_interest_balance(self):
        """الرصيد الدفتري الفعلي القائم للفوائد المؤجلة بحساب 21400 بعد استبعاد المعترف به والمسقط والمردود"""
        return max(Decimal('0.00'), self.interest_amount - self.recognized_interest - self.waived_interest - self.rebated_interest)

    @property
    def remaining_balance(self):
        """إجمالي رصيد القسط المتبقي الحقيقي المطالب به"""
        return self.remaining_principal + self.remaining_interest

    @property
    def total_remaining_balance(self):
        """الاسم المعتمد للرصيد المتبقي الإجمالي المطالب به للقسط"""
        return self.remaining_balance

    class Meta:
        verbose_name = _('قسط مجدول')
        verbose_name_plural = _('الأقساط المجدولة')
        ordering = ['due_date', 'installment_number']
        unique_together = ('plan', 'installment_number')
        indexes = [
            models.Index(fields=['cash_status', 'due_date']),
            models.Index(fields=['paper_coverage', 'due_date']),
            models.Index(fields=['plan', 'installment_number']),
            models.Index(fields=['trigger_type', 'cash_status']),
        ]

    def __str__(self):
        return f"{self.plan.sale.number} - قسط #{self.installment_number} ({self.total_amount})"


class InstallmentRescheduleLog(models.Model):
    """
    سجل تدقيق وحوكمة ترحيل وإعادة جدولة الأقساط
    """
    installment = models.ForeignKey(
        InstallmentItem,
        on_delete=models.CASCADE,
        related_name='reschedule_logs',
        verbose_name=_('القسط')
    )
    old_due_date = models.DateField(verbose_name=_('تاريخ الاستحقاق السابق'))
    new_due_date = models.DateField(verbose_name=_('تاريخ الاستحقاق الجديد'))
    penalty_action = models.CharField(
        max_length=20,
        choices=[
            ('MAINTAINED', _('إبقاء الغرامة')),
            ('WAIVED', _('إسقاط الغرامة بتصريح')),
            ('ADDED', _('إضافة رسوم إعادة جدولة')),
        ],
        default='MAINTAINED',
        verbose_name=_('إجراء الغرامة')
    )
    reason = models.TextField(verbose_name=_('سبب إعادة الجدولة والترحيل'))
    collateral_renewed = models.BooleanField(
        default=False,
        verbose_name=_('تم تجديد شيك الضمان/السند الإذني لمد الجدولة')
    )
    renewed_collateral_cheque = models.ForeignKey(
        'cheques.Cheque',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('شيك الضمان المجدد')
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_('المسؤول المعتمد')
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ التسجيل'))

    class Meta:
        verbose_name = _('سجل ترحيل قسط')
        verbose_name_plural = _('سجلات ترحيل الأقساط')
        ordering = ['-created_at']

    def __str__(self):
        return f"ترحيل قسط #{self.installment.installment_number} إلى {self.new_due_date}"


class InstallmentOperationAudit(models.Model):
    """
    سجل تدقيق ومنع تكرار العمليات المالية للأقساط (Idempotency Audit)
    """
    idempotency_key = models.CharField(
        max_length=120,
        unique=True,
        db_index=True,
        verbose_name=_('مفتاح عدم التكرار')
    )
    plan = models.ForeignKey(
        InstallmentPlan,
        on_delete=models.CASCADE,
        related_name='operation_audits',
        verbose_name=_('خطة التقسيط')
    )
    action = models.CharField(max_length=50, verbose_name=_('نوع العملية'))
    payload = models.JSONField(default=dict, verbose_name=_('بيانات العملية والرد'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ العملية'))

    class Meta:
        verbose_name = _('سجل تدقيق عملية تقسيط')
        verbose_name_plural = _('سجلات تدقيق عمليات التقسيط')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.action} - {self.idempotency_key}"


class InstallmentSettlement(models.Model):
    """
    سجل التسويات والخصومات الدائمة لفواتير وخطط التقسيط
    (خصم تعجيل سداد، إسقاط فوائد، مقاصة موردين، إشعار دائن تقليص، إعدام دين)
    لتدخل محاسبياً في حساب Sale.amount_due وكشف الحساب وميزان المراجعة
    """
    class SettlementStatus(models.TextChoices):
        POSTED = 'POSTED', _('مرحلة ونافذة')
        REVERSED = 'REVERSED', _('معكوسة وملغاة')

    class SettlementType(models.TextChoices):
        EARLY_SETTLEMENT_DISCOUNT = 'EARLY_SETTLEMENT_DISCOUNT', _('خصم تعجيل سداد تمويلي')
        INTEREST_WAIVER = 'INTEREST_WAIVER', _('إسقاط فوائد غير مكتسبة / ملغاة')
        PREPAID_INTEREST_REBATE = 'PREPAID_INTEREST_REBATE', _('رد فائدة مدفوعة مقدماً مخصومة من أصل الدين')
        CONTRA_SETTLEMENT = 'CONTRA_SETTLEMENT', _('تسوية مقاصة موردين')
        BAD_DEBT_WRITE_OFF = 'BAD_DEBT_WRITE_OFF', _('إعدام دين قضائي معتمد')
        CURTAILMENT_INTEREST_WAIVER = 'CURTAILMENT_INTEREST_WAIVER', _('إلغاء فوائد مستقبلية لتقليص العقد')
        PENALTY_WAIVER = 'PENALTY_WAIVER', _('إسقاط غرامات تأخير تشغيلية')

    sale = models.ForeignKey(
        'sale.Sale',
        on_delete=models.PROTECT,
        related_name='settlements',
        verbose_name=_('فاتورة المبيعات')
    )
    plan = models.ForeignKey(
        InstallmentPlan,
        on_delete=models.PROTECT,
        related_name='settlements',
        null=True,
        blank=True,
        verbose_name=_('خطة التقسيط')
    )
    installment_item = models.ForeignKey(
        InstallmentItem,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='settlements',
        verbose_name=_('القسط المرتبط (اختياري)')
    )
    settlement_type = models.CharField(
        max_length=40,
        choices=SettlementType.choices,
        verbose_name=_('نوع التسوية')
    )
    status = models.CharField(
        max_length=20,
        choices=SettlementStatus.choices,
        default=SettlementStatus.POSTED,
        db_index=True,
        verbose_name=_('حالة التسوية')
    )
    affects_invoice_due = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name=_('يؤثر على رصيد الفاتورة التعاقدي')
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name=_('مبلغ التسوية')
    )
    date = models.DateField(
        default=timezone.now,
        verbose_name=_('تاريخ التسوية')
    )
    journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='installment_settlements',
        verbose_name=_('القيد المحاسبي المرتبط')
    )
    batch_id = models.CharField(
        max_length=120,
        blank=True,
        null=True,
        db_index=True,
        verbose_name=_('معرف حزمة العملية المركبة')
    )
    operation_type = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name=_('نوع العملية الأم')
    )
    is_reversed = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name=_('تم عكس التسوية')
    )
    reversed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ وتوقيت العكس')
    )
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='reversed_installment_settlements',
        verbose_name=_('المسؤول الذي قام بالعكس')
    )
    reversal_entry = models.ForeignKey(
        'financial.JournalEntry',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='reversed_installment_settlements_entries',
        verbose_name=_('القيد المحاسبي العكسي')
    )
    reversal_settlement = models.OneToOneField(
        'self',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='reversed_original',
        verbose_name=_('سجل التسوية العكسية المتبادل')
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_('المسؤول المعتمد للتسوية')
    )
    notes = models.TextField(blank=True, verbose_name=_('ملاحظات وسند التسوية'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ التسجيل'))

    class Meta:
        verbose_name = _('تسوية تقسيط دائمة')
        verbose_name_plural = _('تسويات التقسيط الدائمة')
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.get_settlement_type_display()} - {self.amount} ({self.sale.number})"


class CollectionRadarSnapshot(models.Model):
    """
    لقطة الرادار الصباحية المجمعة مسبقاً (6:00 صباحاً عبر Celery Cron)
    لتسريع استجابة لوحة الرادار لأقل من 5ms ومنع اختناق الخادم أوقات الذروة الصباحية
    """
    snapshot_date = models.DateField(db_index=True, verbose_name=_('تاريخ اللقطة'))
    cost_center = models.ForeignKey(
        'financial.CostCenter',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_('مركز التكلفة / الفرع (فارغ للإجمالي العام)')
    )
    total_uncovered_overdue = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('متأخرات مكشوفة')
    )
    total_cheques_under_collection = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('شيكات برسم التحصيل')
    )
    total_due_today = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('مستحق اليوم')
    )
    expected_cashflow_30d = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('تدفق متوقع 30 يوماً')
    )
    metrics_payload = models.JSONField(
        default=dict,
        verbose_name=_('حمولة المؤشرات والقوائم المعالجة مسبقاً')
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ اللقطة'))

    class Meta:
        verbose_name = _('لقطة مؤشرات رادار التحصيل')
        verbose_name_plural = _('لقطات مؤشرات رادار التحصيل')
        unique_together = ('snapshot_date', 'cost_center')
        ordering = ['-snapshot_date', '-created_at']

    def __str__(self):
        cc_str = f" - {self.cost_center.name}" if self.cost_center else " (الإجمالي العام)"
        return f"لقطة رادار {self.snapshot_date}{cc_str}"


# Module-level convenience aliases
PlanStatus = InstallmentPlan.PlanStatus
PlanType = InstallmentPlan.PlanType
PaperCoverage = InstallmentItem.PaperCoverage
CashStatus = InstallmentItem.CashStatus
InstallmentCashStatus = InstallmentItem.CashStatus
SettlementType = InstallmentSettlement.SettlementType

