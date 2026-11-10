# -*- coding: utf-8 -*-
"""
Contractor Contracts, BOQ Items & Progress Certificates Models (Track 1)
منظومة عقود المقاولين ومقايسات التنفيذ المسعرة والمستخلصات التفصيلية التراكمية
تغطي: حوكمة مقاولي الباطن، مقايسات BOQ، أوامر التغيير، خطابات الضمان LGs،
دورة صرف واسترداد الدفعة المقدمة، الحوالات المصرفية، الحجوزات القضائية،
المطابقة الثلاثية للخرسانة الجاهزة وهادر الصب، نسب الإنجاز التراكمية،
تشوينات الموقع (MOS) ونقل الملكية وحظر البوابة، ضبط هالك حديد التسليح BBS وتفاوت الدرفلة،
عقود النزح الجوفي، الاتفاقيات الثلاثية لموردي الخامات، والطباعة الهندسية المعتمدة.
"""
from decimal import Decimal
import hashlib
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class ProjectMasterBOQItem(models.Model):
    """
    بند المقايسة التقديرية العامة للمشروع (Master Project BOQ Item)
    يحدد السقف التقديري للكميات وفئات دراسة الجدوى لمنع تجاوز الموازنة العامة للمشروع
    عند تجزئة البند الواحد على عدة مقاولي باطن.
    """
    project = models.ForeignKey(
        'real_estate.RealEstateProject',
        on_delete=models.PROTECT,
        related_name='master_boq_items',
        verbose_name=_('المشروع العقاري')
    )
    block = models.ForeignKey(
        'real_estate.PropertyBlock',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='master_boq_items',
        verbose_name=_('العمارة / البرج المستهدف (اختياري)')
    )
    item_code = models.CharField(
        max_length=50,
        verbose_name=_('كود البند بالمقايسة العامة')
    )
    wbs_group = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name=_('مجموعة الأعمال (حفر، خرسانات، مباني، تشطيبات)')
    )
    wbs_budget_code = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name=_('كود بند موازنة WBS')
    )
    description = models.TextField(
        verbose_name=_('توصيف البند بالمقايسة العامة')
    )
    unit = models.CharField(
        max_length=20,
        verbose_name=_('الوحدة الهندسية (م3، م2، م.ط، كجم، عدد)')
    )
    master_budget_quantity = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        verbose_name=_('إجمالي الكمية التقديرية المعتمدة للمشروع دراسة الجدوى')
    )
    unit_rate_estimate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_('فئة الموازنة التقديرية لدراسة الجدوى')
    )
    total_budget_cost = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي تكلفة موازنة البند')
    )
    overrun_tolerance_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.00'),
        verbose_name=_('نسبة سماحية التجاوز الهندسي المسموحة (%)')
    )
    allocated_quantity_to_contracts = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=Decimal('0.000'),
        verbose_name=_('إجمالي الكميات المسندة لعقود المقاولين حتى تاريخه')
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('بند مقايسة عامة للمشروع')
        verbose_name_plural = _('مقايسة المشروع التقديرية العامة')
        unique_together = ('project', 'item_code')
        ordering = ['project', 'item_code']

    def __str__(self):
        return f"{self.project.name} - {self.item_code}: {self.description[:40]}"

    def clean(self):
        super().clean()
        if self.master_budget_quantity and self.unit_rate_estimate:
            self.total_budget_cost = (self.master_budget_quantity * self.unit_rate_estimate).quantize(Decimal('0.01'))


class ContractorContract(models.Model):
    """
    عقد مقاولة باطن أو توريد خرسانة لمشروع عقاري
    """
    class ContractType(models.TextChoices):
        MEASURED_BOQ = 'MEASURED_BOQ', _('مقايسة بالكميات والأسعار (مصنعيات / توريد ومصنعية)')
        LUMP_SUM = 'LUMP_SUM', _('مقطوعية إجمالية (Lump Sum)')
        READY_MIX_SUPPLY = 'READY_MIX_SUPPLY', _('توريد خرسانة جاهزة ومضخات من محطة خلط')
        TIME_AND_MATERIALS = 'TIME_AND_MATERIALS', _('مصنعيات ومواد مستردة')

    class GuaranteeType(models.TextChoices):
        CASH_RETENTION = 'CASH_RETENTION', _('استقطاع تأمين نقدي من المستخلصات')
        BANK_LETTER_OF_GUARANTEE = 'BANK_LETTER_OF_GUARANTEE', _('خطاب ضمان بنكي نهائي (LG)')

    class MaterialDeductionPolicy(models.TextChoices):
        DIRECT_CHARGE = 'DIRECT_CHARGE', _('خصم مباشر لكامل المسحوبات من المخزن')
        STANDARD_QUOTA_AND_SCRAP = 'STANDARD_QUOTA_AND_SCRAP', _('كوتة استهلاك نمطية ومحاسبة على زيادة الهالك')

    class TaxRegime(models.TextChoices):
        TABLE_TAX_5 = 'TABLE_TAX_5', _('ضريبة جدول 5% (مقاولات وإنشاءات - قانون 67 لسنة 2016)')
        STANDARD_VAT_14 = 'STANDARD_VAT_14', _('ضريبة قيمة مضافة عامة 14% (عقود توريد خامات وخرسانة)')
        EXEMPT = 'EXEMPT', _('معفى من الضريبة')

    class ContractStatus(models.TextChoices):
        DRAFT = 'DRAFT', _('مسودة')
        UNDER_REVIEW = 'UNDER_REVIEW', _('قيد المراجعة الفنية')
        ACTIVE = 'ACTIVE', _('ساري ومعتمد')
        SUSPENDED = 'SUSPENDED', _('معلق مؤقتاً')
        COMPLETED = 'COMPLETED', _('مكتمل الأعمال')
        TERMINATED = 'TERMINATED', _('مفسوخ')

    contract_number = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name=_('رقم العقد')
    )
    title = models.CharField(
        max_length=200,
        verbose_name=_('عنوان العقد / موضوع المقاولة')
    )
    project = models.ForeignKey(
        'real_estate.RealEstateProject',
        on_delete=models.PROTECT,
        related_name='contractor_contracts',
        verbose_name=_('المشروع العقاري')
    )
    block = models.ForeignKey(
        'real_estate.PropertyBlock',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='contractor_contracts',
        verbose_name=_('العمارة / البرج المستهدف (اختياري)')
    )
    contractor = models.ForeignKey(
        'supplier.Supplier',
        on_delete=models.PROTECT,
        related_name='real_estate_contracts',
        verbose_name=_('المقاول / محطة الخلط')
    )
    contract_type = models.CharField(
        max_length=30,
        choices=ContractType.choices,
        default=ContractType.MEASURED_BOQ,
        verbose_name=_('نوع العقد')
    )
    tax_regime = models.CharField(
        max_length=30,
        choices=TaxRegime.choices,
        default=TaxRegime.TABLE_TAX_5,
        verbose_name=_('النظام الضريبي المصري للعقد')
    )
    currency = models.ForeignKey(
        'financial.Currency',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='contractor_contracts',
        verbose_name=_('العملة')
    )
    exchange_rate = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        default=Decimal('1.000000'),
        verbose_name=_('سعر الصرف المعتمد')
    )

    # القيم المالية وسقف المقايسة
    initial_contract_value = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('القيمة التعاقدية الأصلية')
    )
    revised_contract_value = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('القيمة التعاقدية المعدلة بعد أوامر التغيير')
    )
    total_certified_work = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي الأعمال المعتمدة تراكمياً حتى تاريخه')
    )

    # الدفعة المقدمة وصرفها المالي
    advance_payment_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('نسبة الدفعة المقدمة التعاقدية (%)')
    )
    advance_payment_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('مبلغ الدفعة المقدمة المستحق')
    )
    advance_payment_disbursed = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('الدفعة المقدمة المصروفة فعلياً')
    )
    advance_payment_recovered = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('الدفعة المقدمة المستردة حتى تاريخه')
    )
    advance_recovery_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('10.00'),
        verbose_name=_('نسبة استقطاع الدفعة المقدمة من المستخلصات (%)')
    )
    dynamic_advance_recalibration = models.BooleanField(
        default=True,
        verbose_name=_('إعادة المعايرة الديناميكية لمعدل الاسترداد عند أوامر التغيير')
    )

    # الضمانات وحسن التنفيذ
    guarantee_type = models.CharField(
        max_length=30,
        choices=GuaranteeType.choices,
        default=GuaranteeType.CASH_RETENTION,
        verbose_name=_('نوع تأمين حسن التنفيذ')
    )
    retention_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.00'),
        verbose_name=_('نسبة استقطاع تأمين حسن التنفيذ النقدي (%)')
    )
    retention_cap_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('سقف استقطاع تأمين حسن التنفيذ')
    )
    total_retention_retained = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي التأمين المحتجز حتى تاريخه')
    )
    total_retention_released = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي التأمين المفرج عنه حتى تاريخه')
    )
    bank_lg_number = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name=_('رقم خطاب الضمان البنكي النهائي (LG)')
    )
    bank_lg_issuing_bank = models.CharField(
        max_length=150,
        blank=True,
        default='',
        verbose_name=_('البنك المصدر لخطاب الضمان')
    )
    bank_lg_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('قيمة خطاب الضمان البنكي')
    )
    bank_lg_expiry_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ انتهاء سريان خطاب الضمان')
    )
    lg_pay_or_extend_triggered = models.BooleanField(
        default=False,
        verbose_name=_('تم تفعيل إنذار التمديد أو التسييل لخطاب الضمان')
    )

    # التنازل البنكي والحجز القضائي
    is_assigned_to_bank = models.BooleanField(
        default=False,
        verbose_name=_('تم التنازل رسمياً عن مستحقات العقد لصالح بنك (Assignment of Proceeds)')
    )
    assigned_bank_name = models.CharField(
        max_length=150,
        blank=True,
        default='',
        verbose_name=_('اسم البنك المحال إليه المستحقات')
    )
    assigned_bank_iban = models.CharField(
        max_length=50,
        blank=True,
        default='',
        verbose_name=_('رقم IBAN المحال إليه الصرف')
    )
    is_garnished_by_court = models.BooleanField(
        default=False,
        verbose_name=_('خاضع لحجز قضائي أو تحفظي تنفيذي ما للمدين لدى الغير')
    )
    garnishment_case_number = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name=_('رقم الدعوى / أمر الحجز القضائي')
    )
    garnishment_creditor_name = models.CharField(
        max_length=150,
        blank=True,
        default='',
        verbose_name=_('اسم الحاجز (مصلحة الضرائب / دائن قضائي)')
    )
    garnishment_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('مبلغ الحجز المجنب بأمانات المحكمة')
    )

    # التأمين CAR والمرافق وفروق الأسعار
    car_insurance_policy_number = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name=_('رقم وثيقة تأمين أخطار المقاولين (CAR Policy)')
    )
    car_insurance_expiry_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ انتهاء وثيقة تأمين أخطار المقاولين')
    )
    car_insurance_deduction_rate = models.DecimalField(
        max_digits=5,
        decimal_places=3,
        default=Decimal('0.300'),
        verbose_name=_('نسبة قسط تأمين أخطار المقاولين المقتطع (%)')
    )
    site_utilities_deduction_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.50'),
        verbose_name=_('نسبة استقطاع مياه وإنارة الموقع (%)')
    )
    is_price_escalation_eligible = models.BooleanField(
        default=False,
        verbose_name=_('خاضع لمعادلة فروق وتغير أسعار الخامات (FIDIC / قانون 182)')
    )
    price_escalation_baseline_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ خط الأساس لأسعار الخامات')
    )

    # الضرائب والدمغات وسماحية التجاوز
    wht_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('1.00'),
        verbose_name=_('نسبة ضريبة الخصم والإضافة (%)')
    )
    social_insurance_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('نسبة تأمينات المقاولات النمطية (%)')
    )
    syndicate_stamp_rate = models.DecimalField(
        max_digits=5,
        decimal_places=3,
        default=Decimal('0.450'),
        verbose_name=_('نسبة دمغة نقابة المهندسين والتطبيقيين (%)')
    )
    overrun_tolerance_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.00'),
        verbose_name=_('نسبة السماحية بالزيادة الهندسية (%)')
    )
    mos_advance_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('75.00'),
        verbose_name=_('نسبة تمويل تشوينات الموقع المعتمدة MOS (%)')
    )
    material_deduction_policy = models.CharField(
        max_length=30,
        choices=MaterialDeductionPolicy.choices,
        default=MaterialDeductionPolicy.DIRECT_CHARGE,
        verbose_name=_('سياسة خصم مسحوبات المخزن')
    )

    # مقاولو الباطن المعينون (Nominated Subcontractors)
    is_nominated_subcontractor = models.BooleanField(
        default=False,
        verbose_name=_('مقاول باطن معين (Nominated Subcontractor)')
    )
    main_contractor = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='nominated_subcontracts',
        verbose_name=_('المقاول العام الرئيسي المسند إليه المشروع')
    )
    direct_payment_allowed = models.BooleanField(
        default=False,
        verbose_name=_('السماح بالدفع المباشر لمقاول الباطن المعين مع المقاصة من المقاول العام')
    )

    # التعاقدات الحرفية والقائمة البيضاء للحساب البنكي
    is_unregistered_individual_craftsman = models.BooleanField(
        default=False,
        verbose_name=_('مقاول فردي / أسطى حرفي غير مسجل ضريبياً')
    )
    approved_bank_account_iban = models.CharField(
        max_length=50,
        blank=True,
        default='',
        verbose_name=_('رقم IBAN الحساب البنكي الرسمي المعتمد للكيان')
    )
    approved_bank_account_title = models.CharField(
        max_length=150,
        blank=True,
        default='',
        verbose_name=_('اسم المستفيد الرسمي المعتمد بالبنك')
    )

    # المجمعة العشرية وصلاحية الإشغال
    decennial_liability_insurance_policy = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name=_('رقم وثيقة تأمين المسؤولية العشرية (المجمعة العشرية)')
    )
    syndicate_supervision_clearance = models.BooleanField(
        default=False,
        verbose_name=_('شهادة الإشراف الهندسي المعتمدة من نقابة المهندسين')
    )
    certificate_of_occupancy_number = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name=_('رقم شهادة صلاحية المبنى للإشغال (ترخيص الحي/الجهاز)')
    )

    # التواريخ والحالة
    start_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ بدء الأعمال التعاقدي')
    )
    completion_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ نهو الأعمال التعاقدي')
    )
    actual_completion_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ نهو الأعمال الفعلي')
    )
    defect_liability_period_months = models.PositiveIntegerField(
        default=12,
        verbose_name=_('فترة الصيانة وضمان العيوب الخفية (شهور)')
    )
    status = models.CharField(
        max_length=30,
        choices=ContractStatus.choices,
        default=ContractStatus.DRAFT,
        db_index=True,
        verbose_name=_('حالة العقد')
    )
    cost_center = models.ForeignKey(
        'financial.CostCenter',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        verbose_name=_('مركز التكلفة')
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        verbose_name=_('أنشئ بواسطة')
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('عقد مقاول باطن')
        verbose_name_plural = _('عقود مقاولي الباطن والخرسانة')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.contract_number} - {self.contractor.name} ({self.project.name})"

    def clean(self):
        super().clean()
        if self.start_date and self.completion_date and self.completion_date < self.start_date:
            raise ValidationError(_("تاريخ نهو الأعمال لا يمكن أن يكون قبل تاريخ بدء الأعمال التعاقدي."))
        if self.initial_contract_value and not self.revised_contract_value:
            self.revised_contract_value = self.initial_contract_value
        if self.advance_payment_rate and self.initial_contract_value and not self.advance_payment_amount:
            self.advance_payment_amount = (self.initial_contract_value * self.advance_payment_rate / Decimal('100')).quantize(Decimal('0.01'))


class SectionalHandoverRecord(models.Model):
    """
    سجل الاستلام الجزئي المرحلي وتعدد عدادات سنة الضمان (Sectional Handover Record)
    لتتبع استلام الأدوار والمراحل المستقلة (مثل الأدوار التجارية بالمول) وبدء عداد ضمان مستقل لكل مرحلة.
    """
    contract = models.ForeignKey(
        ContractorContract,
        on_delete=models.CASCADE,
        related_name='sectional_handovers',
        verbose_name=_('عقد المقاولة')
    )
    section_name = models.CharField(
        max_length=150,
        verbose_name=_('اسم المرحلة أو القسم المسلم جزئياً (مثال: محلات الدور الأرضي)')
    )
    handover_date = models.DateField(
        verbose_name=_('تاريخ محضر الاستلام الابتدائي للمرحلة')
    )
    warranty_start_date = models.DateField(
        verbose_name=_('تاريخ بدء فترة الضمان والصيانة للقسم')
    )
    warranty_end_date = models.DateField(
        verbose_name=_('تاريخ انتهاء فترة الضمان والصيانة للقسم')
    )
    consultant_approval_ref = models.CharField(
        max_length=100,
        verbose_name=_('رقم محضر اعتماد الاستشاري للاستلام الجزئي')
    )
    is_warranty_completed = models.BooleanField(
        default=False,
        verbose_name=_('تم انقضاء فترة الضمان والمخالصة النهائية للقسم')
    )
    notes = models.TextField(blank=True, default='')

    class Meta:
        verbose_name = _('سجل استلام جزئي ومرحلي')
        verbose_name_plural = _('سجلات الاستلام الجزئي المرحلي')
        ordering = ['handover_date']

    def __str__(self):
        return f"{self.contract.contract_number} - {self.section_name} ({self.handover_date})"


class ContractorContractItem(models.Model):
    """
    بنود مقايسة عقد المقاولة الأصلية وربط موازنة WBS والمقايسة العامة وصمام الفئات
    """
    contract = models.ForeignKey(
        ContractorContract,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name=_('عقد المقاولة')
    )
    master_boq_item = models.ForeignKey(
        ProjectMasterBOQItem,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='subcontract_allocations',
        verbose_name=_('بند المقايسة العامة للمشروع')
    )
    block = models.ForeignKey(
        'real_estate.PropertyBlock',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='contract_items',
        verbose_name=_('العمارة / البرج المستهدف')
    )
    wbs_group = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name=_('مجموعة الأعمال / المرحلة')
    )
    wbs_budget_code = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name=_('كود بند موازنة WBS')
    )
    item_code = models.CharField(
        max_length=50,
        verbose_name=_('كود البند بالعقد')
    )
    description = models.TextField(
        verbose_name=_('توصيف البند التعاقدي')
    )
    unit = models.CharField(
        max_length=20,
        verbose_name=_('الوحدة الهندسية')
    )
    contracted_quantity = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        verbose_name=_('الكمية التعاقدية الأصلية')
    )
    revised_quantity = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=Decimal('0.000'),
        blank=True,
        verbose_name=_('الكمية المعدلة بعد أوامر التغيير')
    )
    unit_rate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_('فئة التعاقد')
    )
    is_budget_rate_overrun = models.BooleanField(
        default=False,
        verbose_name=_('فئة التعاقد تتجاوز فئة الموازنة التقديرية')
    )
    total_budget_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name=_('إجمالي تكلفة البند')
    )
    tax_regime_override = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        choices=ContractorContract.TaxRegime.choices,
        verbose_name=_('تخصيص نظام ضريبي خاص للبند (عقود مختلطة 14% توريد / 5% مصنعية)')
    )

    # حوكمة بنود المكون الأجنبي الهجين وسقف مخاطر الصرف
    has_foreign_component = models.BooleanField(
        default=False,
        verbose_name=_('بند له مكون أجنبي مستورد')
    )
    foreign_component_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('نسبة المكون الأجنبي (%)')
    )
    foreign_currency = models.ForeignKey(
        'financial.Currency',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='hybrid_contract_items',
        verbose_name=_('عملة المكون الأجنبي')
    )
    fx_baseline_rate = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        default=Decimal('1.000000'),
        verbose_name=_('سعر الصرف الأساسي بالتعاقد')
    )
    fx_volatility_collar_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('15.00'),
        verbose_name=_('سقف تحمل تقلبات سعر الصرف (Collar %)')
    )
    customs_form4_number = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name=_('رقم نموذج 4 البنكي للإفراج الجمركي')
    )

    # خوازيق الأساسات العميقة ومعامل الانتفاخ
    is_deep_foundation_pile = models.BooleanField(
        default=False,
        verbose_name=_('بند خوازيق وأساسات عميقة')
    )
    pile_bulbing_factor_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('12.00'),
        verbose_name=_('معامل انتفاخ خرسانة الخازوق في التربة (%)')
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = _('بند مقايسة عقد المقاولة')
        verbose_name_plural = _('بنود مقايسة عقد المقاولة')
        unique_together = ('contract', 'item_code')

    def __str__(self):
        return f"{self.contract.contract_number} - {self.item_code}: {self.description[:30]}"

    def clean(self):
        super().clean()
        if not self.revised_quantity and self.contracted_quantity:
            self.revised_quantity = self.contracted_quantity
        if self.contracted_quantity and self.unit_rate and not self.total_budget_amount:
            self.total_budget_amount = (self.contracted_quantity * self.unit_rate).quantize(Decimal('0.01'))
        if self.master_boq_item and self.master_boq_item.unit_rate_estimate:
            self.is_budget_rate_overrun = (self.unit_rate > self.master_boq_item.unit_rate_estimate)

    def save(self, *args, **kwargs):
        if not self.revised_quantity and self.contracted_quantity:
            self.revised_quantity = self.contracted_quantity
        if self.contracted_quantity and self.unit_rate and not self.total_budget_amount:
            self.total_budget_amount = (self.contracted_quantity * self.unit_rate).quantize(Decimal('0.01'))
        if self.master_boq_item and self.master_boq_item.unit_rate_estimate:
            self.is_budget_rate_overrun = (self.unit_rate > self.master_boq_item.unit_rate_estimate)
        super().save(*args, **kwargs)


class ContractVariationOrder(models.Model):
    """
    أمر تغيير معتمد لعقد مقاولة (Contract Variation Order - VO)
    """
    class VariationType(models.TextChoices):
        QUANTITY_INCREASE = 'QUANTITY_INCREASE', _('زيادة كميات بنود قائمة')
        SCOPE_ADDITION = 'SCOPE_ADDITION', _('إضافة بنود أعمال مستجدة')
        PRICE_ADJUSTMENT = 'PRICE_ADJUSTMENT', _('تعديل فئة تعاقدية / فرق أسعار')
        SCOPE_DELETION = 'SCOPE_DELETION', _('تقليص نطاق أعمال وحذف كميات')

    class VariationStatus(models.TextChoices):
        DRAFT = 'DRAFT', _('مسودة')
        UNDER_REVIEW = 'UNDER_REVIEW', _('قيد المراجعة الفنية للاستشاري')
        APPROVED = 'APPROVED', _('معتمد نهائياً')
        REJECTED = 'REJECTED', _('مرفوض')

    order_number = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_('رقم أمر التغيير')
    )
    contract = models.ForeignKey(
        ContractorContract,
        on_delete=models.PROTECT,
        related_name='variation_orders',
        verbose_name=_('عقد المقاولة')
    )
    variation_type = models.CharField(
        max_length=30,
        choices=VariationType.choices,
        default=VariationType.QUANTITY_INCREASE,
        verbose_name=_('نوع أمر التغيير')
    )
    description = models.TextField(
        verbose_name=_('مبررات وتفاصيل أمر التغيير الفنية والهندسية')
    )
    net_value_impact = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('الأثر المالي لصافي أمر التغيير (+/-)')
    )
    approved_additional_days = models.PositiveIntegerField(
        default=0,
        verbose_name=_('المدة الزمنية الإضافية المعتمدة (أيام)')
    )
    consultant_approval_ref = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name=_('رقم مذكرة اعتماد الاستشاري')
    )
    status = models.CharField(
        max_length=20,
        choices=VariationStatus.choices,
        default=VariationStatus.DRAFT,
        verbose_name=_('حالة أمر التغيير')
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        verbose_name=_('أنشئ بواسطة')
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('أمر تغيير عقد مقاولة')
        verbose_name_plural = _('أوامر تغيير عقود المقاولين')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.order_number} ({self.contract.contract_number}) - {self.net_value_impact}"


class ContractVariationOrderItem(models.Model):
    """
    بند تفصيلي في أمر تغيير عقد المقاولة
    """
    variation_order = models.ForeignKey(
        ContractVariationOrder,
        on_delete=models.CASCADE,
        related_name='items'
    )
    contract_item = models.ForeignKey(
        ContractorContractItem,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='variation_modifications',
        verbose_name=_('بند العقد القائم (في حال التعديل)')
    )
    item_code = models.CharField(max_length=50)
    description = models.TextField()
    unit = models.CharField(max_length=20)
    additional_quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unit_rate = models.DecimalField(max_digits=12, decimal_places=2)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        verbose_name = _('بند تفصيلي بأمر التغيير')
        verbose_name_plural = _('بنود تفصيلية بأوامر التغيير')

    def __str__(self):
        return f"{self.variation_order.order_number} - {self.item_code}"


class ContractorDefaultNotice(models.Model):
    """
    إخطار إنذار مخالفة ميدانية للمقاول مع مهلة الـ 48 ساعة القانونية
    (Contractual Default Notice & Cure Period)
    لا يجوز توقيع أي خصم أو تكليف مقاول بديل إلا بعد انقضاء الـ 48 ساعة تحصيناً للشركة قضائياً.
    """
    contract = models.ForeignKey(
        ContractorContract,
        on_delete=models.PROTECT,
        related_name='default_notices',
        verbose_name=_('عقد المقاولة')
    )
    notice_number = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_('رقم إخطار المخالفة الرسمي')
    )
    notice_date = models.DateTimeField(
        verbose_name=_('تاريخ ووقت توجيه الإخطار رسمياً')
    )
    cure_deadline = models.DateTimeField(
        verbose_name=_('موعد انقضاء مهلة العلاج (48 ساعة)')
    )
    violation_description = models.TextField(
        verbose_name=_('توصيف المخالفة أو التلفيات أو التباطؤ الميداني')
    )
    is_cured = models.BooleanField(
        default=False,
        verbose_name=_('تم تلافي المخالفة من قبل المقاول خلال المهلة')
    )
    is_penalty_authorized = models.BooleanField(
        default=False,
        verbose_name=_('تم انقضاء المهلة واعتماد التنفيذ على حساب المقاول')
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('إخطار إنذار مخالفة ميدانية (48 ساعة)')
        verbose_name_plural = _('إخطارات المخالفات ومهلة الـ 48 ساعة')
        ordering = ['-notice_date']

    def __str__(self):
        return f"{self.notice_number} - {self.contract.contractor.name} ({self.notice_date})"


class ContractorProgressCertificate(models.Model):
    """
    نموذج مستخلص مقاول الباطن التراكمي (Contractor Progress Certificate)
    يدعم الحصر التراكمي، التشوينات MOS، مكعبات الخرسانة، بونات الرتش، الأوناش،
    تسلسل الاستقطاعات ومنع الازدواج الضريبي لنموذج 41، والربط مع الاعتمادات المؤسسية.
    """
    class CertificateStatus(models.TextChoices):
        DRAFT = 'DRAFT', _('مسودة قيد الإعداد')
        PENDING_APPROVAL = 'PENDING_APPROVAL', _('قيد المراجعة والاعتماد المؤسسي')
        APPROVED = 'APPROVED', _('معتمد نهائياً وجاهز للصرف')
        REJECTED = 'REJECTED', _('مرفوض')
        PAID = 'PAID', _('تم الصرف المالي')
        CANCELLED = 'CANCELLED', _('ملغى')

    class CertificateType(models.TextChoices):
        STANDARD_PROGRESS = 'STANDARD_PROGRESS', _('مستخلص جاري تفصيلي (أعمال وتشوينات)')
        READY_MIX_CONCRETE = 'READY_MIX_CONCRETE', _('مستخلص توريد خرسانة جاهزة ومضخات')
        SUBSTANTIAL_RETENTION_RELEASE = 'SUBSTANTIAL_RETENTION_RELEASE', _('إفراج جزئي عن تأمين حسن التنفيذ (50% استلام ابتدائي)')
        FINAL_RETENTION_RELEASE = 'FINAL_RETENTION_RELEASE', _('رد التأمين النهائي ومخالصة الضمان بعد سنة الصيانة (50%)')
        FINAL_SETTLEMENT = 'FINAL_SETTLEMENT', _('مستخلص ختامي للأعمال وتصفية العقد')

    class PaymentStatus(models.TextChoices):
        UNPAID = 'UNPAID', _('غير مسدد')
        PARTIALLY_PAID = 'PARTIALLY_PAID', _('مسدد جزئياً')
        PAID = 'PAID', _('مسدد بالكامل')

    class ETAInvoiceStatus(models.TextChoices):
        PENDING = 'PENDING', _('قيد انتظار الفاتورة الإلكترونية')
        VERIFIED = 'VERIFIED', _('تم التحقق والمطابقة بمصلحة الضرائب')
        EXEMPT = 'EXEMPT', _('حرفي / مقاول فردي معفى ضريبياً')

    certificate_number = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name=_('رقم المستخلص')
    )
    contract = models.ForeignKey(
        ContractorContract,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='certificates',
        verbose_name=_('عقد المقاولة')
    )
    contract_reference = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name=_('رقم عقد المقاولة / أمر الشغل (توافق رجعي)')
    )
    sequence_order = models.PositiveIntegerField(
        default=1,
        verbose_name=_('رقم تسلسل المستخلص للعقد (مستخلص رقم 1، 2..)')
    )
    project = models.ForeignKey(
        'real_estate.RealEstateProject',
        on_delete=models.PROTECT,
        related_name='contractor_certificates',
        verbose_name=_('المشروع العقاري')
    )
    block = models.ForeignKey(
        'real_estate.PropertyBlock',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='contractor_certificates',
        verbose_name=_('العمارة / البرج المحدد')
    )
    contractor = models.ForeignKey(
        'supplier.Supplier',
        on_delete=models.PROTECT,
        related_name='real_estate_certificates',
        verbose_name=_('المقاول / محطة الخلط')
    )
    certificate_type = models.CharField(
        max_length=35,
        choices=CertificateType.choices,
        default=CertificateType.STANDARD_PROGRESS,
        verbose_name=_('نوع المستخلص')
    )
    period_start = models.DateField(
        verbose_name=_('بداية فترة المستخلص')
    )
    period_end = models.DateField(
        verbose_name=_('نهاية فترة المستخلص')
    )

    # العملة وسعر الصرف
    currency = models.ForeignKey(
        'financial.Currency',
        on_delete=models.PROTECT,
        related_name='contractor_certificates',
        verbose_name=_('العملة')
    )
    exchange_rate = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        default=Decimal('1.000000'),
        verbose_name=_('سعر الصرف المعتمد')
    )

    # الأعمال المنفذة وتشوينات الموقع وفروق الأسعار
    gross_certified_work = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي الأعمال المنفذة تراكمياً حتى تاريخه')
    )
    previous_certified_work = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي الأعمال المعتمدة في المستخلصات السابقة')
    )
    current_period_work = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('أعمال الفترة الحالية المعتمدة')
    )
    price_escalation_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('مبلغ فروق أسعار الخامات المعتمدة بالفترة')
    )
    unverified_work_holdback = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('استقطاع أعمال غير معتمدة استشارياً لحين اكتمال RFI')
    )

    # تشوينات الموقع (MOS)
    materials_on_site = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('تشوينات المواد بالموقع المعتمدة (توافق رجعي)')
    )
    current_mos_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('قيمة تشوينات الموقع الجديدة المعتمدة بالفترة')
    )
    previous_recovered_mos_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('المسترد من تشوينات سابقة بعد تركيبها')
    )
    net_materials_on_site = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('صافي حركة تشوينات الموقع للفترة')
    )

    # الضرائب والدمغات والاستقطاعات التعاقدية
    vat_schedule_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.00'),
        verbose_name=_('نسبة ضريبة الجدول أو القيمة المضافة (%)')
    )
    vat_schedule_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('مبلغ ضريبة الجدول / القيمة المضافة')
    )
    retention_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.00'),
        verbose_name=_('نسبة تأمين حسن التنفيذ (%)')
    )
    retention_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('مبلغ تأمين حسن التنفيذ المحتجز بالفترة')
    )
    released_retention_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('مبلغ التأمين المفرج عنه في المستخلص')
    )
    advance_payment_recovery = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('استقطاع استرداد الدفعة المقدمة')
    )
    site_utilities_deduction_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.50'),
        verbose_name=_('نسبة استقطاع مياه وإنارة الموقع (%)')
    )
    site_utilities_deduction_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('مبلغ استقطاع مياه وإنارة الموقع')
    )
    syndicate_stamp_rate = models.DecimalField(
        max_digits=5,
        decimal_places=3,
        default=Decimal('0.450'),
        verbose_name=_('نسبة دمغة نقابة المهندسين (%)')
    )
    syndicate_stamp_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('مبلغ دمغة نقابة المهندسين')
    )
    car_insurance_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('مبلغ قسط تأمين أخطار المقاولين CAR المقتطع')
    )

    # تسلسل الاستقطاعات ومنع الازدواج الضريبي لنموذج 41
    taxable_base_form41 = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('الوعاء الضريبي لنموذج 41 (أعمال الفترة - الدفعة المقدمة المستردة)')
    )
    wht_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('1.00'),
        verbose_name=_('نسبة ضريبة الخصم والإضافة (%)')
    )
    wht_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('مبلغ ضريبة الخصم والإضافة')
    )
    social_insurance_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('نسبة تأمينات المقاولات النمطية (%)')
    )
    social_insurance_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('مبلغ تأمينات المقاولات المستقطع')
    )

    # الاستدعاءات التلقائية والتكاليف الميدانية والخصومات
    interim_on_account_payments = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('سلف ودفعات تحت الحساب مسددة خلال فترة المستخلص')
    )
    direct_labor_advances_deduction = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('استقطاع سلف العمالة النقدية الطارئة')
    )
    pending_cube_test_hold_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('أمانة معلقة لصبات مشكوك في نتائج كسر مكعباتها 28 يوم')
    )
    released_cube_test_hold_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('رد أمانة كسر مكعبات خرسانة 28 يوم ناجحة')
    )
    equipment_hoisting_charges = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('تكاليف ساعات تشغيل أوناش الأبراج والمعدات')
    )
    debris_clearance_charges = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('تكاليف سيارات ولودر رفع الرتش والمخلفات')
    )
    hse_medical_and_incident_costs = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('تكاليف علاج وإسعاف حوادث عمالة المقاول وغرامات السلامة')
    )
    store_materials_deduction = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('خصم مواد منصرفة من مخازن الشركة')
    )
    total_backcharges = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي الخصومات البينية وتكاليف العيوب بعد إخطار 48 ساعة')
    )
    defect_rectification_costs = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('تكاليف إصلاح العيوب المخصومة من رد التأمين')
    )

    # مقاصة مقاولي الباطن المعينين وتلفيات الشدات والنزح والاتفاقيات الثلاثية
    nominated_subcontractor_setoff = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('مقاصة سداد مباشر لمقاول باطن معين مخصوم من المقاول العام')
    )
    scaffolding_damage_deduction = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('استقطاع إهلاك وتلفيات الشدات والمعدات المعارة')
    )
    disputed_items_holdback_total = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي مبالغ البنود المتنازع عليها والمحجوزة مؤقتاً')
    )
    tripartite_supplier_liens_deduction = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('استقطاعات التعهدات الثلاثية لصالح موردي الخامات')
    )
    dewatering_fuel_and_stoppage_charges = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('تكاليف محروقات وأعطال طلمبات النزح الجوفي')
    )
    third_party_lab_charges = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('استقطاع فواتير المعامل المستقلة لرسوب العينات')
    )
    approved_suspension_standby_claims = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('تعويضات التوقف القسري المعتمدة للمقاول')
    )

    # المستخلص الاستثنائي المعجل (الأعياد)
    is_fast_track_provisional = models.BooleanField(
        default=False,
        verbose_name=_('مستخلص استثنائي معجل تحت التسوية (أعياد وطوارئ)')
    )
    provisional_safety_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('75.00'),
        verbose_name=_('نسبة أمان الصرف المعجل المعتمدة (%)')
    )

    # متطلبات الإغلاق الختامي والمجمعة العشرية
    decennial_liability_insurance_policy = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name=_('رقم وثيقة تأمين المسؤولية العشرية (المجمعة العشرية)')
    )
    syndicate_supervision_clearance = models.BooleanField(
        default=False,
        verbose_name=_('شهادة الإشراف الهندسي المعتمدة من نقابة المهندسين')
    )
    certificate_of_occupancy_number = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name=_('رقم شهادة صلاحية المبنى للإشغال (ترخيص الحي/الجهاز)')
    )

    # مصفوفة الغرامات
    delay_penalties = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('غرامات تأخير الجدول الزمني')
    )
    refundable_milestone_penalties = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('غرامات تأخير مرحلية محتجزة قابلة للاسترداد')
    )
    recovered_milestone_penalties = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('غرامات تأخير مرحلية مستردة ومردودة للمقاول بالفترة')
    )
    concrete_quality_penalties = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('غرامات جودة وكسر مكعبات الخرسانة')
    )
    hse_safety_penalties = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('غرامات أمن صناعي وسلامة وصحة مهنية')
    )
    excess_material_waste_penalties = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('غرامات تجاوز هالك المواد والمخازن')
    )
    punch_list_penalties = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('خصومات استشاري وعيوب مصنعيات')
    )
    penalty_deductions = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي الغرامات المستقطعة')
    )

    # الصافي وحالة السداد والفاتورة الإلكترونية
    net_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('صافي المستحق للصرف')
    )
    paid_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي المسدد فعلياً بشيكات/سندات صرف')
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.UNPAID,
        verbose_name=_('حالة السداد الفعلي')
    )
    eta_invoice_uuid = models.CharField(
        max_length=64,
        blank=True,
        default='',
        verbose_name=_('رقم الفاتورة الإلكترونية بمصلحة الضرائب (ETA UUID)')
    )
    eta_status = models.CharField(
        max_length=20,
        choices=ETAInvoiceStatus.choices,
        default=ETAInvoiceStatus.PENDING,
        verbose_name=_('حالة الفاتورة الإلكترونية')
    )
    status = models.CharField(
        max_length=20,
        choices=CertificateStatus.choices,
        default=CertificateStatus.DRAFT,
        db_index=True,
        verbose_name=_('حالة المستخلص')
    )

    # تسوية استمارة 19 تأمينات
    social_insurance_cleared = models.BooleanField(
        default=False,
        verbose_name=_('تم استلام شهادة مخالصة استمارة 19 تأمينات مقاولات')
    )
    social_insurance_clearance_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ مخالصة استمارة 19')
    )

    # الربط المحوكم والاعتمادات المؤسسية
    approval_request = models.ForeignKey(
        'financial.EnterpriseApprovalRequest',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='real_estate_certificates',
        verbose_name=_('طلب الاعتماد المؤسسي المرتبط')
    )
    approval_snapshot_hash = models.CharField(
        max_length=64,
        blank=True,
        default='',
        verbose_name=_('البصمة الرقمية المشفرة لبيانات الاعتماد (Merkle Lock)')
    )
    version = models.PositiveIntegerField(
        default=1,
        verbose_name=_('إصدار المستخلص')
    )
    journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contractor_certificates',
        verbose_name=_('قيد استحقاق المستخلص')
    )
    reversal_entry = models.ForeignKey(
        'financial.JournalEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reversed_contractor_certificates',
        verbose_name=_('قيد الإلغاء العكسي (Storno Reversal)')
    )
    notes = models.TextField(
        blank=True,
        default='',
        verbose_name=_('ملاحظات وتفاصيل الأعمال')
    )
    consultant_waiver_approved = models.BooleanField(
        default=False,
        verbose_name=_('موافقة الاستشاري على تجاوز الملاحظات الحرجة')
    )
    consultant_waiver_reference = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name=_('رقم/مرجع خطاب موافقة الاستشاري على التجاوز')
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='created_contractor_certificates',
        verbose_name=_('أنشئ بواسطة')
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('تاريخ الإنشاء')
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('تاريخ التحديث')
    )

    class Meta:
        verbose_name = _('مستخلص مقاول باطن')
        verbose_name_plural = _('مستخلصات مقاولي الباطن والخرسانة')
        ordering = ['-period_end', '-created_at']

    def __str__(self):
        return f"{self.certificate_number} - {self.contractor.name} ({self.net_amount} {self.currency.code})"

    def compute_amounts(self):
        """
        الحساب الرياضي والهندسي الدقيق لمبالغ المستخلص مع دعم التوافق الرجعي 100%:
        إذا كان المستخلص مربوطاً بعقد مقاولة جديد، تُطبق خوارزمية الاستقطاعات المتسلسلة ومنع الازدواج الضريبي.
        وإذا كان من البيانات القديمة أو المستخلصات المقطوعة، يُطبق الحساب المعياري القديم بدقة.
        """
        if self.gross_certified_work < self.previous_certified_work:
            raise ValidationError(_("إجمالي الأعمال المنفذة تراكمياً لا يمكن أن يكون أقل من أعمال المستخلصات السابقة."))

        self.current_period_work = (self.gross_certified_work - self.previous_certified_work).quantize(Decimal('0.01'))

        # حساب حركة تشوينات الموقع
        if self.current_mos_amount or self.previous_recovered_mos_amount:
            self.net_materials_on_site = (self.current_mos_amount - self.previous_recovered_mos_amount).quantize(Decimal('0.01'))
            base_for_retention = self.current_period_work + self.current_mos_amount
        else:
            base_for_retention = self.current_period_work + self.materials_on_site

        # حساب التأمين
        self.retention_amount = (base_for_retention * self.retention_rate / Decimal('100')).quantize(Decimal('0.01'))

        # التحقق من سقف تأمين العقد
        if self.contract and self.contract.retention_cap_amount > Decimal('0.00'):
            total_held = self.contract.total_retention_retained + self.retention_amount
            if total_held > self.contract.retention_cap_amount:
                excess = total_held - self.contract.retention_cap_amount
                self.retention_amount = max(Decimal('0.00'), self.retention_amount - excess)

        # حساب ضريبة الخصم والإضافة مع منع الازدواج الضريبي عند وجود عقد
        if self.contract_id:
            self.taxable_base_form41 = max(Decimal('0.00'), self.current_period_work - self.advance_payment_recovery)
            self.wht_amount = (self.taxable_base_form41 * self.wht_rate / Decimal('100')).quantize(Decimal('0.01'))
            self.syndicate_stamp_amount = (self.current_period_work * self.syndicate_stamp_rate / Decimal('100')).quantize(Decimal('0.01'))
            self.site_utilities_deduction_amount = (self.current_period_work * self.site_utilities_deduction_rate / Decimal('100')).quantize(Decimal('0.01'))
            if self.social_insurance_rate > Decimal('0.00'):
                self.social_insurance_amount = (self.current_period_work * self.social_insurance_rate / Decimal('100')).quantize(Decimal('0.01'))
        else:
            # الحساب التوافقي القديم للمستخلصات السابقة
            self.wht_amount = (self.current_period_work * self.wht_rate / Decimal('100')).quantize(Decimal('0.01'))

        # التحقق من سقف استرداد الدفعة المقدمة لمنع التجاوز بالسالب
        if self.contract:
            advance_pool = (
                self.contract.advance_payment_disbursed
                if self.contract.advance_payment_disbursed > Decimal('0.00')
                else self.contract.advance_payment_amount
            )
            if advance_pool > Decimal('0.00'):
                available_advance = max(Decimal('0.00'), advance_pool - self.contract.advance_payment_recovered)
                if self.advance_payment_recovery > available_advance:
                    self.advance_payment_recovery = available_advance

        # حساب ضريبة الجدول (5%) أو ضريبة القيمة المضافة (14%) المصرية إذا كان العقد خاضعاً
        if self.contract:
            if self.contract.tax_regime == ContractorContract.TaxRegime.TABLE_TAX_5:
                self.vat_schedule_rate = Decimal("5.00")
                self.vat_schedule_amount = (self.current_period_work * Decimal("0.05")).quantize(Decimal("0.01"))
            elif self.contract.tax_regime == ContractorContract.TaxRegime.STANDARD_VAT_14:
                self.vat_schedule_rate = Decimal("14.00")
                self.vat_schedule_amount = (self.current_period_work * Decimal("0.14")).quantize(Decimal("0.01"))
            else:
                self.vat_schedule_rate = Decimal("0.00")
                self.vat_schedule_amount = Decimal("0.00")

        # حساب صافي المستحق
        if self.contract_id:
            # تجميع مبالغ البنود المتنازع عليها تلقائياً إن وجدت ولم تحدد يدوياً
            if self.id and (not self.disputed_items_holdback_total or self.disputed_items_holdback_total == Decimal("0.00")):
                disputed_items = self.items.filter(is_disputed_holdback=True)
                if disputed_items.exists():
                    self.disputed_items_holdback_total = sum(i.current_work_value for i in disputed_items)

            gross_period_additions = (
                self.current_period_work +
                self.vat_schedule_amount +
                self.net_materials_on_site +
                self.price_escalation_amount +
                self.approved_suspension_standby_claims +
                self.released_retention_amount +
                self.released_cube_test_hold_amount
            )
            total_operational_penalties = (
                self.delay_penalties +
                self.concrete_quality_penalties +
                self.hse_safety_penalties +
                self.excess_material_waste_penalties +
                self.punch_list_penalties +
                self.penalty_deductions
            )
            total_deductions_sum = (
                self.retention_amount +
                self.advance_payment_recovery +
                self.wht_amount +
                self.social_insurance_amount +
                self.syndicate_stamp_amount +
                self.car_insurance_amount +
                self.site_utilities_deduction_amount +
                self.interim_on_account_payments +
                self.direct_labor_advances_deduction +
                self.pending_cube_test_hold_amount +
                self.unverified_work_holdback +
                self.equipment_hoisting_charges +
                self.debris_clearance_charges +
                self.hse_medical_and_incident_costs +
                self.store_materials_deduction +
                self.total_backcharges +
                self.defect_rectification_costs +
                self.nominated_subcontractor_setoff +
                self.scaffolding_damage_deduction +
                self.disputed_items_holdback_total +
                self.tripartite_supplier_liens_deduction +
                self.dewatering_fuel_and_stoppage_charges +
                self.third_party_lab_charges +
                total_operational_penalties -
                self.recovered_milestone_penalties
            )
            self.net_amount = (gross_period_additions - total_deductions_sum).quantize(Decimal('0.01'))
        else:
            # المعادلة المعيارية القديمة لحفظ التوافق التام مع الاختبارات القائمة
            self.net_amount = (
                self.current_period_work +
                self.materials_on_site -
                self.retention_amount -
                self.advance_payment_recovery -
                self.wht_amount -
                self.penalty_deductions
            ).quantize(Decimal('0.01'))

    calculate_deductions = compute_amounts

    def compute_financial_hash(self) -> str:
        """
        توليد البصمة الرقمية المشفرة لحماية البيانات المالية من التعديل بعد الاعتماد
        (تتوافق مع شجرة ميركل وتغطي البنود وكافة مدخلات القيد المالي)
        """
        items_payload = ""
        if self.id:
            items_data = list(self.items.order_by('id').values_list(
                'id', 'item_code', 'current_quantity', 'unit_rate', 'current_period_amount', 'is_disputed_holdback'
            ))
            items_payload = "|".join(f"{i[0]}:{i[1]}:{i[2]}:{i[3]}:{i[4]}:{i[5]}" for i in items_data)

        payload = (
            f"{self.id or 0}:{self.contractor_id}:{self.contract_id}:{self.project_id}:"
            f"{self.currency_id}:{self.gross_certified_work}:{self.retention_amount}:"
            f"{self.advance_payment_recovery}:{self.wht_amount}:{self.materials_on_site}:"
            f"{self.penalty_deductions}:{self.net_amount}:{self.vat_schedule_amount}:"
            f"{self.disputed_items_holdback_total}:{self.total_backcharges}:"
            f"{self.scaffolding_damage_deduction}:{self.third_party_lab_charges}:"
            f"{self.defect_rectification_costs}:{self.unverified_work_holdback}:"
            f"{self.released_cube_test_hold_amount}:{self.price_escalation_amount}:"
            f"{self.version}#{items_payload}"
        )
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    def clean(self):
        super().clean()
        if self.contract:
            advance_pool = (
                self.contract.advance_payment_disbursed
                if self.contract.advance_payment_disbursed > Decimal('0.00')
                else self.contract.advance_payment_amount
            )
            if advance_pool > Decimal('0.00'):
                available_advance = max(Decimal('0.00'), advance_pool - self.contract.advance_payment_recovered)
                if self.advance_payment_recovery > available_advance:
                    raise ValidationError(_("مبلغ استرداد الدفعة المقدمة (%(rec)s) يتجاوز الرصيد المتبقي الفعلي للدفعة المقدمة بالعقد (%(avail)s).") % {
                        'rec': self.advance_payment_recovery,
                        'avail': available_advance
                    })

        # حراسة رد أمانات كسر المكعبات الخرسانية: التحقق من الرصيد المحتجز مسبقاً ونتائج الفحص المعملي
        if self.released_cube_test_hold_amount and self.released_cube_test_hold_amount > Decimal('0.00'):
            prev_certs = ContractorProgressCertificate.objects.filter(
                contract_id=self.contract_id,
                status=ContractorProgressCertificate.CertificateStatus.APPROVED
            )
            if self.pk:
                prev_certs = prev_certs.exclude(pk=self.pk)
            total_held = sum((c.pending_cube_test_hold_amount for c in prev_certs), Decimal('0.00'))
            total_rel = sum((c.released_cube_test_hold_amount for c in prev_certs), Decimal('0.00'))
            available_cube = max(Decimal('0.00'), total_held - total_rel)
            if self.released_cube_test_hold_amount > available_cube:
                raise ValidationError(
                    _("مبلغ رد أمانة كسر المكعبات (%(amt)s) يتجاوز رصيد الأمانات المحتجزة مسبقاً بالعقد (%(avail)s).") % {
                        'amt': self.released_cube_test_hold_amount,
                        'avail': available_cube
                    }
                )

            from real_estate.models.contractor import ThirdPartyLabTestLog, ConcreteBatchDelivery
            concrete_q = (
                models.Q(test_type__icontains='cube') |
                models.Q(test_type__icontains='مكعب') |
                models.Q(test_type__icontains='concrete') |
                models.Q(test_type__icontains='خرسان') |
                models.Q(test_type__icontains='core') |
                models.Q(tested_element__icontains='cube') |
                models.Q(tested_element__icontains='مكعب') |
                models.Q(tested_element__icontains='concrete') |
                models.Q(tested_element__icontains='خرسان')
            )
            early_test_q = (
                models.Q(test_type__icontains='7-day') |
                models.Q(test_type__icontains='7 day') |
                models.Q(test_type__icontains='7 days') |
                models.Q(test_type__icontains='7 أيام') |
                models.Q(test_type__icontains='7 يوم') |
                models.Q(tested_element__icontains='7-day') |
                models.Q(tested_element__icontains='7 day') |
                models.Q(tested_element__icontains='7 days') |
                models.Q(tested_element__icontains='7 أيام') |
                models.Q(tested_element__icontains='7 يوم')
            )
            maturity_q = (
                models.Q(test_type__icontains='28') |
                models.Q(test_type__icontains='core') |
                models.Q(test_type__icontains='قلب') |
                models.Q(tested_element__icontains='28') |
                models.Q(tested_element__icontains='core') |
                models.Q(tested_element__icontains='قلب')
            )
            has_passed_lab = ThirdPartyLabTestLog.objects.filter(
                contract_id=self.contract_id,
                is_test_passed=True
            ).filter(concrete_q).filter(maturity_q).exclude(early_test_q).exists()
            has_passed_batch = ConcreteBatchDelivery.objects.filter(
                models.Q(supplier_contract_id=self.contract_id) | (models.Q(project_id=self.project_id) & models.Q(supplier_contract__isnull=True)),
                is_sample_passed=True,
                cube_test_28days_kg_cm2__isnull=False
            ).exists()
            if not (has_passed_lab or has_passed_batch):
                raise ValidationError(
                    _("لا يمكن رد أمانة كسر المكعبات دون وجود نتائج اختبارات معملية معتمدة وناجحة لكسر 28 يوماً.")
                )

        self.compute_amounts()
        if self.net_amount < Decimal('0.00'):
            raise ValidationError(_("صافي مبلغ المستخلص لا يمكن أن يكون سالباً."))


class ContractorCertificateItem(models.Model):
    """
    بند تفصيلي في مستخلص المقاول التراكمي
    """
    certificate = models.ForeignKey(
        ContractorProgressCertificate,
        on_delete=models.CASCADE,
        related_name='items'
    )
    contract_item = models.ForeignKey(
        ContractorContractItem,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='certified_items'
    )
    variation_item = models.ForeignKey(
        ContractVariationOrderItem,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='certified_items'
    )
    block = models.ForeignKey(
        'real_estate.PropertyBlock',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='certificate_items',
        verbose_name=_('العمارة / البرج المحمل عليه التكلفة')
    )
    sub_stage_description = models.CharField(
        max_length=150,
        blank=True,
        default='',
        verbose_name=_('توصيف المرحلة المنفذة (مثال: طرطشة وأوتار)')
    )
    item_code = models.CharField(max_length=50)
    description = models.TextField()
    unit = models.CharField(max_length=20)

    # الحصر الكمي
    previous_quantity = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal('0.000'))
    current_quantity = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal('0.000'))
    is_negative_survey_correction = models.BooleanField(default=False)
    survey_correction_reason = models.TextField(blank=True, default='')
    total_cumulative_quantity = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal('0.000'))

    # نسب الإنجاز التراكمية للبند (Cumulative Progress % Model)
    current_cumulative_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('نسبة الإنجاز التراكمية المعتمدة للبند (%)')
    )
    previous_cumulative_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('نسبة الإنجاز في المستخلصات السابقة (%)')
    )
    equivalent_period_quantity = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=Decimal('0.000'),
        verbose_name=_('الكمية المكافئة المنفذة خلال الفترة')
    )

    # المبالغ المالية
    unit_rate = models.DecimalField(max_digits=12, decimal_places=2)
    total_cumulative_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    current_period_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))

    is_overrun_within_tolerance = models.BooleanField(default=False)
    site_survey_variance = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal('0.000'))

    # حجر البنود المتنازع عليها مؤقتاً والاعتماد الجزئي
    is_disputed_holdback = models.BooleanField(default=False, verbose_name=_('بند محجوز عليه مؤقتاً لوجود نزاع فني'))
    dispute_reason = models.TextField(blank=True, default='', verbose_name=_('أسباب النزاع الفني أو ملاحظات الاستشاري المعلقة'))
    disputed_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'), verbose_name=_('قيمة المبلغ المحجوز عن البند'))

    # ربط محاضر استلام الأعمال ومحاضر فحص الخامات الميدانية
    wir_reference = models.CharField(max_length=100, blank=True, default='', verbose_name=_('رقم محضر استلام الأعمال الميداني المعتمد (WIR)'))
    mir_reference = models.CharField(max_length=100, blank=True, default='', verbose_name=_('رقم محضر فحص واعتماد المواد (MIR)'))

    notes = models.TextField(blank=True, default='')

    class Meta:
        verbose_name = _('بند مستخلص مقاول باطن')
        verbose_name_plural = _('بنود مستخلص مقاول باطن')

    def __str__(self):
        return f"{self.certificate.certificate_number} - {self.item_code}"

    @property
    def current_work_value(self):
        return self.current_period_amount or (self.current_quantity * self.unit_rate)

    @property
    def cumulative_work_value(self):
        return self.total_cumulative_amount or ((self.previous_quantity + self.current_quantity) * self.unit_rate)

    @property
    def cumulative_quantity(self):
        return self.total_cumulative_quantity or (self.previous_quantity + self.current_quantity)

    def save(self, *args, **kwargs):
        if self.current_quantity is not None and self.previous_quantity is not None:
            self.total_cumulative_quantity = self.previous_quantity + self.current_quantity
        if self.current_quantity is not None and self.unit_rate is not None:
            self.current_period_amount = self.current_quantity * self.unit_rate
        if self.total_cumulative_quantity is not None and self.unit_rate is not None:
            self.total_cumulative_amount = self.total_cumulative_quantity * self.unit_rate
        super().save(*args, **kwargs)


class EquipmentHoistingLog(models.Model):
    """
    سجل تشغيل أوناش الأبراج والمعدات المشتركة بالموقع وتحميل ساعات التشغيل
    """
    certificate = models.ForeignKey(
        ContractorProgressCertificate,
        on_delete=models.CASCADE,
        related_name='hoisting_charges'
    )
    equipment_code = models.CharField(max_length=50, verbose_name=_('كود ونش البرج / المعدة'))
    equipment_name = models.CharField(max_length=150, verbose_name=_('اسم ووصف المعدة المشتركة'))
    operating_date = models.DateField(verbose_name=_('تاريخ يومية التشغيل'))
    operating_hours = models.DecimalField(max_digits=6, decimal_places=2, verbose_name=_('ساعات الرفع والتشغيل'))
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_('فئة تشغيل الساعة'))
    total_charge = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('إجمالي تكلفة التشغيل'))
    diesel_liters_charged = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'), verbose_name=_('لترات السولار المستهلكة'))
    diesel_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name=_('تكلفة السولار'))
    consultant_supervisor = models.CharField(max_length=100, blank=True, default='', verbose_name=_('مشرف الموقع المعتمد'))

    class Meta:
        verbose_name = _('سجل تشغيل ونش برج / معدات مشتركة')
        verbose_name_plural = _('سجلات تشغيل أوناش الأبراج والمعدات المشتركة')


class SiteDebrisClearanceLog(models.Model):
    """
    سجل بونات نقل الرتش ومخلفات الهدم والتكسير والنظافة الميدانية
    """
    certificate = models.ForeignKey(
        ContractorProgressCertificate,
        on_delete=models.CASCADE,
        related_name='debris_charges'
    )
    trip_ticket_number = models.CharField(max_length=50, verbose_name=_('رقم بون نقل الرتش / النقلة'))
    clearance_date = models.DateField(verbose_name=_('تاريخ النقل والنظافة'))
    truck_capacity_m3 = models.DecimalField(max_digits=6, decimal_places=2, verbose_name=_('سعة عربة النقل (م3)'))
    trip_cost = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_('تكلفة النقلة والتعتيق'))
    loader_hours = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), verbose_name=_('ساعات اللودر المحملة'))
    loader_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name=_('تكلفة اللودر'))
    total_clearance_charge = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('إجمالي تكلفة إخلاء الرتش المقتطعة'))
    site_engineer_notes = models.TextField(blank=True, default='')

    class Meta:
        verbose_name = _('بون رفع رتش ومخلفات تكسير')
        verbose_name_plural = _('بونات رفع الرتش ومخلفات التكسير')


class ContractorMaterialOnSite(models.Model):
    """
    تشوينات المواد بالموقع المعتمدة واستردادها التلقائي (Materials on Site - MOS)
    """
    certificate = models.ForeignKey(
        ContractorProgressCertificate,
        on_delete=models.CASCADE,
        related_name='mos_details'
    )
    item_name = models.CharField(max_length=150, verbose_name=_('اسم المادة المشونة'))
    unit = models.CharField(max_length=20)
    surveyed_quantity = models.DecimalField(max_digits=12, decimal_places=3, verbose_name=_('الكمية المشونة المحصورة بالموقع'))
    invoice_unit_cost = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('سعر شراء الوحدة بالفاتورة المعتمدة'))
    total_material_value = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_('إجمالي قيمة المواد المشونة'))
    advance_financing_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('75.00'), verbose_name=_('نسبة تمويل التشوين التعاقدية (%)'))
    approved_advance_amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_('المبلغ المعتمد للصرف (75%)'))
    installed_recovered_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal('0.000'), verbose_name=_('الكمية التي تم تركيبها واستردادها'))
    recovered_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'), verbose_name=_('المبلغ المسترد بعد التركيب'))
    is_fully_unwound = models.BooleanField(default=False, verbose_name=_('تم استرداد تمويل التشوين بالكامل'))

    class Meta:
        verbose_name = _('تشوين مواد بالموقع')
        verbose_name_plural = _('تشوينات المواد بالموقع (MOS)')


class ContractorMOSCustodyReceipt(models.Model):
    """
    محضر إثبات حيازة وتنازل ملكية مشونات الموقع وحظر البوابة الأمنية (Vesting Receipt)
    سنداً للمادة 658 مدني وفيدك بند 70 بنقل ملكية المشونات لرب العمل فور صرف تمويل الـ 75%.
    """
    mos_item = models.ForeignKey(
        ContractorMaterialOnSite,
        on_delete=models.CASCADE,
        related_name='custody_receipts'
    )
    receipt_number = models.CharField(max_length=50, unique=True, verbose_name=_('رقم محضر نقل الملكية والحيازة'))
    vesting_date = models.DateField(verbose_name=_('تاريخ نقل الملكية لرب العمل'))
    is_vested_in_employer = models.BooleanField(default=True, verbose_name=_('أصبحت ملكاً خالصاً للشركة طبقاً للمادة 658 مدني'))
    gate_exit_locked = models.BooleanField(default=True, verbose_name=_('حظر أمني مشدد على البوابة لمنع خروج الخامات من الموقع'))
    consultant_engineer_approval = models.BooleanField(default=False, verbose_name=_('اعتماد مهندس استشاري المالك'))
    notes = models.TextField(blank=True, default='')

    class Meta:
        verbose_name = _('محضر حيازة وتنازل ملكية مشونات الموقع')
        verbose_name_plural = _('محاضر حيازة وتنازل ملكية مشونات الموقع')


class ContractorBackcharge(models.Model):
    """
    الخصومات البينية وتكاليف إصلاح العيوب (مربوطة مع UnitSnagItem ومهلة إخطار 48 ساعة)
    """
    class SettlementMethod(models.TextChoices):
        CERTIFICATE = 'CERTIFICATE', _('خصم من مستخلص جاري')
        RETENTION_LIQUIDATION = 'RETENTION_LIQUIDATION', _('تسييل مباشر من حساب التأمين 21310')
        PENDING = 'PENDING', _('معلق بمحفظة الخصومات')

    # Alias for backward compatibility
    SettlementMethod.CERTIFICATE_DEDUCTION = SettlementMethod.CERTIFICATE

    certificate = models.ForeignKey(
        ContractorProgressCertificate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='backcharges',
        verbose_name=_('المستخلص المخصوم منه')
    )
    contractor = models.ForeignKey(
        'supplier.Supplier',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='contractor_backcharges',
        verbose_name=_('المقاول المحمل عليه الخصم')
    )
    contract = models.ForeignKey(
        ContractorContract,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='backcharges',
        verbose_name=_('عقد المقاولة المرتبط')
    )
    beneficiary_contractor = models.ForeignKey(
        'supplier.Supplier',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='beneficiary_backcharges',
        verbose_name=_('المقاول المستفيد من التعويض (أو فارغ للشركة)')
    )
    snag_item = models.ForeignKey(
        'real_estate.UnitSnagItem',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='backcharges',
        verbose_name=_('ملاحظة العيب المعماري الميداني المرتبطة')
    )
    default_notice = models.ForeignKey(
        ContractorDefaultNotice,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='authorized_backcharges',
        verbose_name=_('إخطار إنذار الـ 48 ساعة المنقضي')
    )
    reason = models.TextField(verbose_name=_('سبب الخصم البيني وتوصيف التلفيات أو الخدمة'))
    memo_reference = models.CharField(max_length=100, blank=True, default='', verbose_name=_('رقم مذكرة الاستشاري / أمر الشغل للإصلاح'))
    amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_('مبلغ الخصم البيني'))
    is_settled = models.BooleanField(default=False, verbose_name=_('تمت تسوية الخصم'))
    settlement_method = models.CharField(
        max_length=30,
        choices=SettlementMethod.choices,
        default=SettlementMethod.PENDING,
        verbose_name=_('طريقة التسوية')
    )
    settlement_journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='settled_backcharges',
        verbose_name=_('قيد تسوية الخصم')
    )
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True, verbose_name=_('تاريخ إنشاء الخصم'))

    class Meta:
        verbose_name = _('خصم بيني / تكلفة إصلاح عيوب')
        verbose_name_plural = _('الخصومات البينية وتكاليف العيوب')
        ordering = ['-created_at', '-id']

    def clean(self):
        super().clean()
        if self.certificate_id:
            if self.certificate.status in [
                ContractorProgressCertificate.CertificateStatus.APPROVED,
                ContractorProgressCertificate.CertificateStatus.PAID
            ]:
                raise ValidationError(_("لا يمكن ربط خصم بمستخلص معتمد أو مسدد مسبقاً."))
            if not self.contractor_id:
                self.contractor_id = self.certificate.contractor_id
            if not self.contract_id and self.certificate.contract_id:
                self.contract_id = self.certificate.contract_id
        elif self.contract_id and not self.contractor_id:
            self.contractor_id = self.contract.contractor_id


class ConcreteBatchDelivery(models.Model):
    """
    سجل بون توريد خرسانة جاهزة ملحق بمستخلص الخرسانة أو موقع المشروع
    """
    certificate = models.ForeignKey(
        ContractorProgressCertificate,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='concrete_batches'
    )
    project = models.ForeignKey(
        'real_estate.RealEstateProject',
        on_delete=models.PROTECT,
        related_name='concrete_deliveries'
    )
    block = models.ForeignKey(
        'real_estate.PropertyBlock',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='concrete_deliveries',
        verbose_name=_('العمارة / البرج')
    )
    supplier_contract = models.ForeignKey(
        ContractorContract,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='concrete_batches'
    )
    delivery_note_number = models.CharField(max_length=50, verbose_name=_('رقم بون التوريد الورقي/الإلكتروني'))
    delivery_date = models.DateField(verbose_name=_('تاريخ الصب والتوريد'))
    casting_location = models.CharField(max_length=150, verbose_name=_('مكان الصب (أعمدة الدور الأول، لبشة)'))
    concrete_grade = models.CharField(max_length=50, verbose_name=_('رتبة الخرسانة (C30, C35, C40)'))
    cement_type = models.CharField(max_length=50, default='SRC', verbose_name=_('نوع الأسمنت (مقاوم، بورتلاندي)'))
    slump_test = models.DecimalField(max_digits=4, decimal_places=1, default=Decimal('10.0'), verbose_name=_('نتيجة اختبار الهبوط Slump (سم)'))
    batch_volume_m3 = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_('حجم الخرسانة بالبون (م3)'))
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), blank=True, verbose_name=_('سعر المتر المكعب'))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), blank=True, verbose_name=_('إجمالي قيمة البون'))
    cube_test_7days_kg_cm2 = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, verbose_name=_('إجهاد كسر مكعبات 7 أيام'))
    cube_test_28days_kg_cm2 = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, verbose_name=_('إجهاد كسر مكعبات 28 يوم'))
    is_sample_passed = models.BooleanField(default=True, verbose_name=_('اجتاز اختبار المقاومة'))

    # فحص الطقس الحار ومطابقة القوام ورفض الشاحنات
    concrete_temperature_celsius = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, verbose_name=_('درجة حرارة الخرسانة عند الوصول (°م)'))
    slump_test_cm = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, verbose_name=_('نتيجة اختبار الهبوط Slump (سم)'))
    is_batch_rejected = models.BooleanField(default=False, verbose_name=_('شاحنة خرسانة مرفوضة ومطرودة'))
    rejection_reason = models.CharField(max_length=200, blank=True, default='', verbose_name=_('سبب الرفض (حرارة > 32°م، فاقد هبوط، إضافة مياه)'))
    penalty_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name=_('غرامة الجودة المطبقة'))

    def save(self, *args, **kwargs):
        if not self.total_amount and self.batch_volume_m3 and self.unit_price:
            self.total_amount = (self.batch_volume_m3 * self.unit_price).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = _('بون توريد خرسانة جاهزة')
        verbose_name_plural = _('بونات توريد الخرسانة الجاهزة')


class ConcreteBatchReconciliation(models.Model):
    """
    المطابقة الثلاثية لحصر وصب الخرسانة الجاهزة واحتساب هادر الصب الزائد على مقاول المصنعيات
    """
    certificate = models.ForeignKey(
        ContractorProgressCertificate,
        on_delete=models.CASCADE,
        related_name='concrete_reconciliations'
    )
    casting_subcontractor = models.ForeignKey(
        ContractorContract,
        on_delete=models.PROTECT,
        related_name='concrete_waste_reconciliations',
        verbose_name=_('عقد مقاول مصنعيات الصب والنجارة المسلحة')
    )
    element_description = models.CharField(max_length=150, verbose_name=_('العنصر المصبوب (سقف، لبشة، أعمدة)'))
    surveyed_as_built_volume_m3 = models.DecimalField(max_digits=12, decimal_places=3, verbose_name=_('الحجم الهندسي المحصور هندسياً (As-Built)'))
    actual_batch_delivered_volume_m3 = models.DecimalField(max_digits=12, decimal_places=3, verbose_name=_('الكمية الفعلية الموردة من محطة الخلط (م3)'))
    contractual_waste_tolerance_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('2.00'), verbose_name=_('نسبة هالك الصب المسموحة تعاقدياً (%)'))
    allowed_waste_volume_m3 = models.DecimalField(max_digits=12, decimal_places=3, verbose_name=_('حجم الهالك المسموح تعاقدياً'))
    excess_waste_volume_m3 = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal('0.000'), verbose_name=_('حجم الهادر الزائد عن المسموح المحمل على المقاول'))
    concrete_unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_('سعر متر الخرسانة للخصم'))
    excess_waste_backcharge_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'), verbose_name=_('قيمة الخصم المالي لهادر الخرسانة الزائد'))

    class Meta:
        verbose_name = _('تسوية ومطابقة هادر صب الخرسانة الجاهزة')
        verbose_name_plural = _('تسويات هادر صب الخرسانة الجاهزة')


class ContractorMaterialDeduction(models.Model):
    """
    تسوية خصم مواد منصرفة من مخزن المشروع للمقاول
    """
    class PricingPolicy(models.TextChoices):
        CONTRACTUAL_FIXED = 'CONTRACTUAL_FIXED', _('سعر تعاقدي ثابت')
        STORE_ACTUAL_COST = 'STORE_ACTUAL_COST', _('متوسط تكلفة المخزن الفعلي')

    certificate = models.ForeignKey(
        ContractorProgressCertificate,
        on_delete=models.CASCADE,
        related_name='store_deductions'
    )
    store_issue_voucher = models.CharField(max_length=100, verbose_name=_('رقم إذن صرف المخزن'))
    issue_date = models.DateField(verbose_name=_('تاريخ إذن الصرف'))
    item_name = models.CharField(max_length=150, verbose_name=_('اسم الصنف المنصرف'))
    quantity = models.DecimalField(max_digits=12, decimal_places=3, verbose_name=_('الكمية المنصرفة'))
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('سعر الوحدة المعتمد'))
    total_deduction = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_('إجمالي مبلغ الخصم'))
    pricing_policy = models.CharField(
        max_length=30,
        choices=PricingPolicy.choices,
        default=PricingPolicy.CONTRACTUAL_FIXED,
        verbose_name=_('سياسة تسعير المادة المنصرفة')
    )
    contractual_unit_rate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_('السعر التعاقدي للخصم')
    )
    store_unit_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_('تكلفة الوحدة الفعلية من المخزن')
    )
    material_price_variance_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('فرق السعر المحمل على تكلفة المشروع')
    )
    is_excess_scrap_penalty = models.BooleanField(
        default=False,
        verbose_name=_('غرامة تجاوز نسبة هالك المخزن المسموحة')
    )

    class Meta:
        verbose_name = _('تسوية مواد منصرفة من المخزن')
        verbose_name_plural = _('تسويات المواد المنصرفة من المخازن')


class RebarConsumptionLog(models.Model):
    """
    سجل حركة حديد التسليح وتفريد الحدادة (Bar Bending Schedule - BBS)
    """
    project = models.ForeignKey('real_estate.RealEstateProject', on_delete=models.PROTECT, related_name='rebar_logs')
    block = models.ForeignKey('real_estate.PropertyBlock', null=True, blank=True, on_delete=models.PROTECT, related_name='rebar_logs')
    contractor = models.ForeignKey('supplier.Supplier', on_delete=models.PROTECT, related_name='rebar_logs')
    contract = models.ForeignKey(ContractorContract, on_delete=models.PROTECT, related_name='rebar_logs')
    element_name = models.CharField(max_length=150, verbose_name=_('العنصر الإنشائي (أعمدة، قواعد، سقف الدور الأول)'))
    rebar_diameter_mm = models.PositiveIntegerField(verbose_name=_('قطر حديد التسليح (مم)'))
    bbs_theoretical_weight_tons = models.DecimalField(max_digits=12, decimal_places=3, verbose_name=_('الوزن النظري لجدول التفريد BBS (طن)'))
    actual_delivered_weight_tons = models.DecimalField(max_digits=12, decimal_places=3, verbose_name=_('الوزن الفعلي المنصرف من المخزن (طن)'))
    allowed_waste_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('2.50'), verbose_name=_('نسبة الهالك المسموحة تعاقدياً (%)'))
    scrap_returned_weight_tons = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal('0.000'), verbose_name=_('وزن فضل الحديد الخردة المسلمة للمخزن (طن)'))
    excess_waste_weight_tons = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal('0.000'), verbose_name=_('الوزن الزائد عن الهالك المسموح (طن)'))
    rolling_margin_tolerance_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('2.50'), verbose_name=_('سماحية تفاوت درفلة مصنع الحديد (%)'))
    adjusted_net_waste_weight_tons = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal('0.000'), verbose_name=_('صافي وزن الهالك الفعلي بعد استبعاد تفاوت الدرفلة (طن)'))
    steel_market_price_per_ton = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('سعر طن الحديد في السوق للخصم'))
    excess_waste_backcharge_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'), verbose_name=_('قيمة الخصم المالي لهالك الحديد الزائد'))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('سجل مطابقة حديد التسليح BBS')
        verbose_name_plural = _('سجلات مطابقة حديد التسليح BBS')


class ContractorScaffoldingLog(models.Model):
    """
    سجل حركة وعهد الشدات المعدنية والمعدات المعارة لمقاول المصنعية وحساب التلفيات
    """
    contract = models.ForeignKey(ContractorContract, on_delete=models.PROTECT, related_name='scaffolding_logs')
    certificate = models.ForeignKey(ContractorProgressCertificate, null=True, blank=True, on_delete=models.SET_NULL, related_name='scaffolding_logs')
    equipment_type = models.CharField(max_length=150, verbose_name=_('نوع الشدة / المعدة (Acrow Props, Dokas, H20, Plywood)'))
    delivered_quantity = models.PositiveIntegerField(verbose_name=_('الكمية المسلمة للمقاول عهدة'))
    returned_good_quantity = models.PositiveIntegerField(default=0, verbose_name=_('الكمية المرتجعة بحالة سليمة'))
    damaged_quantity = models.PositiveIntegerField(default=0, verbose_name=_('الكمية التالفة'))
    missing_quantity = models.PositiveIntegerField(default=0, verbose_name=_('الكمية المفقودة / العجز'))
    unit_repair_or_replacement_cost = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('تكلفة إصلاح أو استعواض الوحدة'))
    total_damage_deduction = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'), verbose_name=_('إجمالي استقطاع التلفيات من المستخلص'))
    log_date = models.DateField(verbose_name=_('تاريخ فحص واستلام الشدة'))

    class Meta:
        verbose_name = _('سجل عهدة شدات ومعدات معارة')
        verbose_name_plural = _('سجلات عهد الشدات والمعدات المعارة')


class DewateringPumpingLog(models.Model):
    """
    سجل تشغيل ومتابعة طلمبات النزح الجوفي واحتساب الأعطال والمحروقات
    """
    contract = models.ForeignKey(ContractorContract, on_delete=models.PROTECT, related_name='dewatering_logs')
    certificate = models.ForeignKey(ContractorProgressCertificate, null=True, blank=True, on_delete=models.SET_NULL, related_name='dewatering_logs')
    log_date = models.DateField(verbose_name=_('تاريخ يومية التشغيل'))
    pumps_operating_count = models.PositiveIntegerField(verbose_name=_('عدد الطلمبات العاملة'))
    daily_running_hours = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('24.00'), verbose_name=_('ساعات التشغيل الفعلية'))
    breakdown_hours = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), verbose_name=_('ساعات التوقف والأعطال'))
    stoppage_penalty_rate_per_hour = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('500.00'), verbose_name=_('غرامة ساعة التوقف التعاقدية'))
    total_stoppage_penalty = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_('إجمالي غرامة الأعطال والتوقف'))
    diesel_liters_supplied_by_owner = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name=_('لترات ديزل منصرفة من الشركة للطلمبات'))
    diesel_price_per_liter = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('15.00'), verbose_name=_('سعر لتر السولار للخصم'))
    diesel_total_backcharge = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_('إجمالي خصم المحروقات المستردة'))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('سجل تشغيل ومحروقات طلمبات النزح الجوفي')
        verbose_name_plural = _('سجلات تشغيل ومحروقات طلمبات النزح الجوفي')


class ContractorSupplierLienAssignment(models.Model):
    """
    تعهدات السداد الثلاثية لصالح موردي خامات مقاولي المصنعيات (Tripartite Lien)
    """
    contract = models.ForeignKey(ContractorContract, on_delete=models.PROTECT, related_name='supplier_liens')
    contractor = models.ForeignKey('supplier.Supplier', on_delete=models.PROTECT, related_name='contractor_assigned_liens', verbose_name=_('مقاول المصنعية'))
    material_supplier = models.ForeignKey('supplier.Supplier', on_delete=models.PROTECT, related_name='supplier_guaranteed_liens', verbose_name=_('مورد الخامات المستفيد'))
    agreement_reference = models.CharField(max_length=100, unique=True, verbose_name=_('رقم اتفاقية التعهد الثلاثي'))
    material_description = models.CharField(max_length=200, verbose_name=_('بيان الخامات الموردة (سيراميك، بويات، مواسير)'))
    total_lien_amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_('إجمالي المبلغ المتعهد بسداده للمورد'))
    deducted_to_date = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'), verbose_name=_('المسدد للمورد والمخصوم من المقاول حتى تاريخه'))
    remaining_balance = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_('الرصيد المتبقي تحت التعهد'))
    is_active = models.BooleanField(default=True, verbose_name=_('تعهد ساري وملزم للخصم'))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('تعهد سداد ثلاثي لمورد خامات')
        verbose_name_plural = _('تعهدات السداد الثلاثية لموردي الخامات')


class ThirdPartyLabTestLog(models.Model):
    """
    سجل اختبارات المعامل المستقلة الخارجية وتحميل مصاريف الفحوص الفاشلة
    """
    certificate = models.ForeignKey(ContractorProgressCertificate, null=True, blank=True, on_delete=models.SET_NULL, related_name='lab_test_logs')
    contract = models.ForeignKey(ContractorContract, on_delete=models.PROTECT, related_name='lab_test_logs')
    lab_name = models.CharField(max_length=150, verbose_name=_('اسم المعمل المعتمد (هندسة القاهرة، HBRC)'))
    invoice_number = models.CharField(max_length=100, verbose_name=_('رقم فاتورة المعمل المستقل'))
    test_type = models.CharField(max_length=150, verbose_name=_('نوع الفحص (قلب خرساني، مطرقة شميدت، شد حديد، تحميل خوازيق)'))
    test_date = models.DateField(verbose_name=_('تاريخ إجراء الفحص'))
    tested_element = models.CharField(max_length=150, verbose_name=_('العنصر المختبر'))
    is_test_passed = models.BooleanField(default=True, verbose_name=_('هل اجتاز الاختبار المواصفات'))
    total_invoice_amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('قيمة فاتورة المعمل'))
    is_backcharged_to_contractor = models.BooleanField(default=False, verbose_name=_('تم تحميل الفاتورة كخصم على المقاول لرسوب الفحص'))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('سجل فحص معمل مستقل خارجي')
        verbose_name_plural = _('سجلات فحوصات المعامل المستقلة الخارجية')


class ContractorSuspensionClaim(models.Model):
    """
    مطالبات تعويض التوقف القسري للأعمال وحراسة الموقع بقرارات المالك (FIDIC 8.8)
    """
    contract = models.ForeignKey(ContractorContract, on_delete=models.PROTECT, related_name='suspension_claims')
    certificate = models.ForeignKey(ContractorProgressCertificate, null=True, blank=True, on_delete=models.SET_NULL, related_name='suspension_claims')
    suspension_order_reference = models.CharField(max_length=100, verbose_name=_('رقم أمر إيقاف العمل الصادر من المالك/الجهاز'))
    start_date = models.DateField(verbose_name=_('تاريخ بدء التوقف القسري'))
    end_date = models.DateField(verbose_name=_('تاريخ استئناف العمل'))
    idle_days_count = models.PositiveIntegerField(verbose_name=_('عدد أيام التوقف'))
    idle_scaffolding_cost = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'), verbose_name=_('تعويض إيجار الشدات المعطلة'))
    idle_equipment_cost = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'), verbose_name=_('تعويض المعدات المتوقفة'))
    site_overhead_and_security = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'), verbose_name=_('تكاليف حراسة ومصاريف الموقع الإدارية'))
    total_approved_claim_amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_('إجمالي مبلغ التعويض المعتمد للصرف'))
    is_approved_by_cfo = models.BooleanField(default=False, verbose_name=_('موافقة واعتماد المدير المالي'))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('مطالبة تعويض توقف قسري للأعمال')
        verbose_name_plural = _('مطالبات تعويض التوقف القسري للأعمال')


class JointTerminationSurveyProtocol(models.Model):
    """
    محضر الحصر المشترك وإثبات حالة التوقف عند فسخ العقد لتحصين المطور قضائياً
    """
    contract = models.OneToOneField(ContractorContract, on_delete=models.PROTECT, related_name='termination_protocol')
    protocol_reference = models.CharField(max_length=100, unique=True, verbose_name=_('رقم محضر إثبات الحالة والحصر المشترك'))
    survey_date = models.DateField(verbose_name=_('تاريخ الحصر المشترك بالموقع'))
    consultant_representative = models.CharField(max_length=150, verbose_name=_('ممثل الاستشاري المشرف'))
    employer_representative = models.CharField(max_length=150, verbose_name=_('ممثل شركة التطوير'))
    contractor_representative = models.CharField(max_length=150, verbose_name=_('ممثل المقاول (أو خبير إثبات الحالة القضائي)'))
    as_built_completed_value = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_('قيمة الأعمال المنجزة المقبولة هندسياً حتى تاريخ الفسخ'))
    uninstalled_materials_value = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'), verbose_name=_('قيمة التشوينات المحصورة بالموقع'))
    snag_and_remedial_costs = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'), verbose_name=_('تكاليف إزالة ومعالجة العيوب المصنعية القائمة'))
    court_expert_minutes_number = models.CharField(max_length=100, blank=True, default='', verbose_name=_('رقم محضر إثبات الحالة بمحكمة الأمور المستعجلة إن وجد'))
    site_vacated_and_handed_over = models.BooleanField(default=True, verbose_name=_('تم إخلاء الموقع واستلام الحيازة لصالح المطور رسمياً'))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('محضر حصر مشترك وإثبات حالة الفسخ')
        verbose_name_plural = _('محاضر الحصر المشترك وإثبات حالة الفسخ')


class RockExcavationSurveyLog(models.Model):
    """
    محضر حصر وتحديد طبقات الصخر بالميزانية الشبكية وساعات تشغيل الشواكيش الهيدروليكية
    """
    contract = models.ForeignKey(ContractorContract, on_delete=models.PROTECT, related_name='rock_excavation_logs')
    certificate = models.ForeignKey(ContractorProgressCertificate, null=True, blank=True, on_delete=models.SET_NULL, related_name='rock_excavation_logs')
    grid_location_reference = models.CharField(max_length=150, verbose_name=_('رقم ورشة/محور الميزانية الشبكية'))
    survey_date = models.DateField(verbose_name=_('تاريخ الرفع المساحي المشترك'))
    top_rock_elevation_m = models.DecimalField(max_digits=8, decimal_places=3, verbose_name=_('منسوب ظهر طبقة الصخر (م)'))
    bottom_excavation_elevation_m = models.DecimalField(max_digits=8, decimal_places=3, verbose_name=_('منسوب قاع الحفر النهائي (م)'))
    solid_rock_volume_m3 = models.DecimalField(max_digits=12, decimal_places=3, verbose_name=_('مكعب الصخر المحصور هندسياً (م3)'))
    breaker_operating_hours = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0.00'), verbose_name=_('ساعات تشغيل الشاكوش الهيدروليكي'))
    surveyor_consultant_approval = models.BooleanField(default=False, verbose_name=_('اعتماد مهندس المساحة والاستشاري'))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('محضر حصر حفر صخور بالميزانية الشبكية')
        verbose_name_plural = _('محاضر حصر حفر الصخور بالميزانية الشبكية')


class HydrostaticTestFailureLog(models.Model):
    """
    سجل فشل اختبارات الضغط الهيدروستاتيكي وتلفيات التكسير وإعادة العزل والصب
    """
    contract = models.ForeignKey(ContractorContract, on_delete=models.PROTECT, related_name='hydrostatic_failures')
    certificate = models.ForeignKey(ContractorProgressCertificate, null=True, blank=True, on_delete=models.SET_NULL, related_name='hydrostatic_failures')
    network_segment = models.CharField(max_length=150, verbose_name=_('قطاع الشبكة المختبر (مياه/صرف/ري/إطفاء)'))
    test_date = models.DateField(verbose_name=_('تاريخ إجراء اختبار الضغط'))
    tested_pressure_bar = models.DecimalField(max_digits=5, decimal_places=2, verbose_name=_('ضغط الاختبار المستهدف (بار)'))
    pressure_drop_bar = models.DecimalField(max_digits=5, decimal_places=2, verbose_name=_('مقدار هبوط الضغط المسجل (بار)'))
    leak_location = models.CharField(max_length=200, verbose_name=_('مكان التسريب والعيب المكتشف'))
    concrete_breaking_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_('تكلفة تكسير الخرسانة والردم للوصول للعيب'))
    re_casting_and_waterproofing_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_('تكلفة إعادة العزل والصب'))
    total_remedial_backcharge = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_('إجمالي الخصم الفني على مقاول السباكة'))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('سجل فشل اختبار ضغط وتلفيات تكسير')
        verbose_name_plural = _('سجلات فشل اختبارات الضغط والتلفيات')


class CertificatePaymentInstallmentSchedule(models.Model):
    """
    بروتوكول جدولة سداد المستخلص على دفعات بتعهد رسمي لمواجهة ضغط السيولة
    """
    class PaymentMethod(models.TextChoices):
        PDC_CHEQUE = 'PDC_CHEQUE', _('شيك بنكي آجل')
        BANK_TRANSFER = 'BANK_TRANSFER', _('تحويل بنكي في الموعد')

    certificate = models.ForeignKey(
        ContractorProgressCertificate,
        on_delete=models.CASCADE,
        related_name='installment_schedules'
    )
    installment_number = models.PositiveIntegerField(verbose_name=_('رقم الدفعة المجدولة'))
    due_date = models.DateField(verbose_name=_('تاريخ استحقاق الدفعة'))
    amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_('مبلغ الدفعة'))
    payment_method = models.CharField(
        max_length=30,
        default=PaymentMethod.PDC_CHEQUE,
        choices=PaymentMethod.choices,
        verbose_name=_('طريقة السداد المتفق عليها')
    )
    pdc_cheque = models.ForeignKey(
        'cheques.Cheque',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='contractor_installments',
        verbose_name=_('الشيك البنكي الآجل المرتبط')
    )
    is_settled = models.BooleanField(default=False, verbose_name=_('تم السداد الفعلي'))
    contractor_agreement_signed = models.BooleanField(default=True, verbose_name=_('تعهد المقاول باستمرار العمل بالموقع وعدم الإيقاف'))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('دفعة مجدولة لسداد المستخلص')
        verbose_name_plural = _('جدولة سداد المستخلصات على دفعات')
        ordering = ['certificate', 'installment_number']
