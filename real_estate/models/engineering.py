# -*- coding: utf-8 -*-
"""
Engineering Models - نماذج أوامر التعديل المعمارية وقوائم ملاحظات الموقع الميدانية
MWHEBA ERP — Real Estate Engineering, Variation Orders & Field Snagging
"""
import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class ClientVariationOrder(models.Model):
    """
    نموذج أمر التعديل المعماري للعميل (Client Variation Order):
    - يتيح للعميل طلب تعديل معماري أو تشطيبي مع مقايسة التكاليف (هدم، مواد، عمالة، إشراف).
    - يطبق فرملة مراحل التنفيذ هندسياً (Milestone Cut-off Guard):
      * في مرحلة الهيكل المفتوح (UNDER_CONSTRUCTION): يُسمح بالتعديل الإنشائي مع احتساب تكلفة التكسير.
      * في مرحلة ما بعد تمديد السباكة والعزل (POST_ROUGH_IN وما بعدها): يُحظر التعديل الإنشائي نهائياً لحماية العزل.
    """

    class VariationType(models.TextChoices):
        STRUCTURAL = 'STRUCTURAL', _('تعديل إنشائي ومعماري (إزالة/نقل قواطع وحوائط)')
        PLUMBING_HVAC = 'PLUMBING_HVAC', _('تعديل كهروميكانيكي وسباكة وتكييف')
        ELECTRICAL = 'ELECTRICAL', _('تعديل تمديدات كهربائية وإنارة')
        FINISHING_COSMETIC = 'FINISHING_COSMETIC', _('تعديل تشطيبات ودهانات وديكور سطحي')

    class ProjectStage(models.TextChoices):
        UNDER_CONSTRUCTION = 'UNDER_CONSTRUCTION', _('مرحلة الهيكل الإنشائي المفتوح')
        POST_ROUGH_IN = 'POST_ROUGH_IN', _('مرحلة ما بعد تمديد السباكة والعزل والتأسيس')
        FINAL_FINISHING = 'FINAL_FINISHING', _('مرحلة التشطيبات النهائية')

    class OrderStatus(models.TextChoices):
        DRAFT = 'DRAFT', _('مسودة')
        ENGINEERING_REVIEW = 'ENGINEERING_REVIEW', _('قيد المراجعة الهندسية')
        APPROVED = 'APPROVED', _('معتمد هندسياً ومالياً')
        IN_PROGRESS = 'IN_PROGRESS', _('قيد التنفيذ الميداني')
        COMPLETED = 'COMPLETED', _('مكتمل التنفيذ')
        REJECTED = 'REJECTED', _('مرفوض لمخالفة المعايير الهندسية')

    order_number = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name=_('رقم أمر التعديل')
    )
    contract = models.ForeignKey(
        'real_estate.PropertyContract',
        on_delete=models.PROTECT,
        related_name='variation_orders',
        verbose_name=_('العقد العقاري')
    )
    unit = models.ForeignKey(
        'real_estate.PropertyUnit',
        on_delete=models.PROTECT,
        related_name='variation_orders',
        verbose_name=_('الوحدة العقارية')
    )
    variation_type = models.CharField(
        max_length=30,
        choices=VariationType.choices,
        default=VariationType.FINISHING_COSMETIC,
        db_index=True,
        verbose_name=_('نوع التعديل المطلوب')
    )
    stage_at_request = models.CharField(
        max_length=30,
        choices=ProjectStage.choices,
        default=ProjectStage.UNDER_CONSTRUCTION,
        db_index=True,
        verbose_name=_('مرحلة تنفيذ المبنى عند تقديم الطلب')
    )
    title = models.CharField(
        max_length=200,
        verbose_name=_('عنوان طلب التعديل')
    )
    description = models.TextField(
        verbose_name=_('التوصيف التفصيلي للتعديلات المطلوبة')
    )
    demolition_rework_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('تكلفة التكسير وإعادة البناء (Demolition & Rework)')
    )
    material_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('تكلفة المواد والمستلزمات')
    )
    labor_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('تكلفة المصنعيات والعمالة')
    )
    supervision_fee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('أتعاب الإشراف والتنسيق الهندسي')
    )
    total_cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي تكلفة أمر التعديل')
    )
    status = models.CharField(
        max_length=30,
        choices=OrderStatus.choices,
        default=OrderStatus.DRAFT,
        db_index=True,
        verbose_name=_('حالة أمر التعديل')
    )
    rejection_reason = models.TextField(
        blank=True,
        default='',
        verbose_name=_('سبب الرفض الهندسي')
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_real_estate_variation_orders',
        verbose_name=_('اعتمد هندسياً بواسطة')
    )
    supplemental_installment_item = models.ForeignKey(
        'sale.InstallmentItem',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='variation_orders',
        verbose_name=_('قسط ملحق التسوية المالي')
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_real_estate_variation_orders',
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
        verbose_name = _('أمر تعديل معماري للعميل')
        verbose_name_plural = _('أوامر التعديلات المعمارية')
        ordering = ['-created_at', '-id']

    def calculate_total_cost(self) -> Decimal:
        """احتساب التكلفة الإجمالية لأمر التعديل"""
        return (
            (self.demolition_rework_cost or Decimal('0.00')) +
            (self.material_cost or Decimal('0.00')) +
            (self.labor_cost or Decimal('0.00')) +
            (self.supervision_fee or Decimal('0.00'))
        )

    def clean(self):
        super().clean()
        if self.unit_id and self.contract_id and self.contract.unit_id != self.unit_id:
            raise ValidationError(_("الوحدة المحددة لا تتطابق مع وحدة العقد المبرم."))

        # 🛡️ فرملة التعديلات هندسياً (Structural Milestone Cut-off Guard)
        if self.stage_at_request in [self.ProjectStage.POST_ROUGH_IN, self.ProjectStage.FINAL_FINISHING]:
            if self.variation_type in [self.VariationType.STRUCTURAL, self.VariationType.PLUMBING_HVAC]:
                raise ValidationError(
                    _("يُحظر إجراء أي تعديلات إنشائية أو كهروميكانيكية تمس العزل بعد مرحلة التأسيس وتمديد السباكة "
                      "(POST_ROUGH_IN) حفاظاً على سلامة العزل المائي للخرسانات ومطابقة اللوائح الهندسية. "
                      "يقتصر السماح في هذه المرحلة حصراً على التشطيبات السطحية والديكور (FINISHING_COSMETIC).")
                )

        self.total_cost = self.calculate_total_cost()

    def save(self, *args, **kwargs):
        self.clean()
        if not self.order_number:
            try:
                from core.services.sequence_service import SequenceService
                from core.enums.document_types import DocumentType
                self.order_number = SequenceService.get_next_number(
                    document_type=DocumentType.VARIATION_ORDER,
                    date=timezone.localdate()
                )
            except Exception:
                self.order_number = f"VO-{self.unit.unit_code}-{uuid.uuid4().hex[:6].upper()}"

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order_number} ({self.get_variation_type_display()}) - {self.unit.unit_code}"


class UnitSnagItem(models.Model):
    """
    نموذج ملاحظة معاينة الموقع الميدانية (Unit Snag Item):
    - يدعم بروتوكول العمل دون اتصال (Offline-First) عبر client_snag_uuid المولد من IndexedDB.
    - يدعم تخزين الصور المصغرة المعالجة بتقنية WebP (< 150KB).
    - يصنف خطورة الملاحظة ويمنع التسليم النهائي في حال وجود ملاحظات مانعة (CRITICAL_BLOCKER).
    """

    class SnagCategory(models.TextChoices):
        PLUMBING = 'PLUMBING', _('سباكة وأدوات صحية')
        ELECTRICAL = 'ELECTRICAL', _('كهرباء وإنارة')
        PAINTING = 'PAINTING', _('دهانات وتشطيبات حوائط')
        CARPENTRY = 'CARPENTRY', _('نجارة وأبواب وشبابيك')
        ALUMINUM_GLASS = 'ALUMINUM_GLASS', _('ألوميتال وزجاج')
        FLOORING = 'FLOORING', _('سيراميك وبورسلين وأرضيات')
        HVAC = 'HVAC', _('تكييف وتهوية')
        OTHER = 'OTHER', _('أخرى')

    class SnagSeverity(models.TextChoices):
        MINOR = 'MINOR', _('بسيطة (Cosmetic Snag)')
        MAJOR = 'MAJOR', _('جوهرية (Major Defect)')
        CRITICAL_BLOCKER = 'CRITICAL_BLOCKER', _('حرجة مانعة للتسليم (Handover Blocker)')

    class SnagStatus(models.TextChoices):
        OPEN = 'OPEN', _('مفتوحة - قيد الملاحظة')
        IN_PROGRESS = 'IN_PROGRESS', _('قيد الإصلاح والمعالجة')
        RESOLVED = 'RESOLVED', _('تم الإصلاح من المقاول')
        VERIFIED_BY_ENGINEER = 'VERIFIED_BY_ENGINEER', _('معتمدة ومغلقة من مهندس الموقع')

    snag_code = models.CharField(
        max_length=60,
        unique=True,
        db_index=True,
        verbose_name=_('كود الملاحظة الفنية')
    )
    client_snag_uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        db_index=True,
        verbose_name=_('معرف الملاحظة المحلي (IndexedDB UUID)')
    )
    unit = models.ForeignKey(
        'real_estate.PropertyUnit',
        on_delete=models.PROTECT,
        related_name='snag_items',
        verbose_name=_('الوحدة العقارية')
    )
    contract = models.ForeignKey(
        'real_estate.PropertyContract',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='snag_items',
        verbose_name=_('العقد العقاري المرتبط')
    )
    room_location = models.CharField(
        max_length=100,
        verbose_name=_('موقع الملاحظة / الغرفة (Location)')
    )
    category = models.CharField(
        max_length=30,
        choices=SnagCategory.choices,
        default=SnagCategory.PAINTING,
        db_index=True,
        verbose_name=_('تصنيف العيب الفني')
    )
    severity = models.CharField(
        max_length=30,
        choices=SnagSeverity.choices,
        default=SnagSeverity.MINOR,
        db_index=True,
        verbose_name=_('درجة خطورة الملاحظة')
    )
    description = models.TextField(
        verbose_name=_('توصيف الملاحظة الفنية')
    )
    photo_thumbnail_webp = models.TextField(
        blank=True,
        default='',
        verbose_name=_('صورة الملاحظة المصغرة (WebP Base64)')
    )
    status = models.CharField(
        max_length=30,
        choices=SnagStatus.choices,
        default=SnagStatus.OPEN,
        db_index=True,
        verbose_name=_('حالة معالجة الملاحظة')
    )
    contractor = models.ForeignKey(
        'supplier.Supplier',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='assigned_snags',
        verbose_name=_('المقاول المكلف بالإصلاح')
    )
    resolution_notes = models.TextField(
        blank=True,
        default='',
        verbose_name=_('ملاحظات الإصلاح والمعالجة')
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_snag_items',
        verbose_name=_('مهندس المعاينة')
    )
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ إتمام الإصلاح')
    )
    verified_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ اعتماد وإغلاق المهندس')
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('تاريخ التسجيل')
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('تاريخ التحديث')
    )

    class Meta:
        verbose_name = _('ملاحظة معاينة موقع (Snag)')
        verbose_name_plural = _('ملاحظات معاينات الموقع (Snags)')
        ordering = ['unit', '-severity', '-created_at']

    def mark_resolved(self, engineer=None, resolution_notes: str = ""):
        """
        تعليم الملاحظة كتم الإصلاح والاعتماد الهندسي
        """
        self.resolved_at = timezone.now()
        if resolution_notes:
            self.resolution_notes = resolution_notes
        if engineer:
            self.verified_at = timezone.now()
            self.status = self.SnagStatus.VERIFIED_BY_ENGINEER
        else:
            self.status = self.SnagStatus.RESOLVED
        self.save(update_fields=['status', 'resolved_at', 'verified_at', 'resolution_notes', 'updated_at'])

    def save(self, *args, **kwargs):
        if not self.snag_code:
            self.snag_code = f"SNG-{self.unit.unit_code}-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.snag_code} ({self.get_severity_display()}) - {self.room_location}"


# ==============================================================================
# نماذج Track 3: شجرة أنشطة مقايسة المشروع WBS وسجلات الموقع ومصفوفة البنود المعمارية
# ==============================================================================

class ProjectActivity(models.Model):
    """
    شجرة أنشطة مقايسة المشروع الإنشائية والمعمارية (WBS Tree):
    - تمثل مستويات مقايسة المشروع الهرمية (Parent / Sub-activities).
    - ترتبط اختيارياً بعمارة/بلوك محدد، وببند المقايسة التقديرية العام MasterBOQItem.
    - تدعم محطات التسليم الرئيسية (Milestones) التي تفعل استحقاق أقساط المبيعات.
    - تدعم خط الأساس الزمني (Baseline) واحتساب انحرافات الجدول الزمني.
    - تدعم جسر الربط الهيكلي بين حزم WBS ومراحل التشطيب الميدانية للوحدات (Unit-to-WBS Bridge).
    """

    class ActivityType(models.TextChoices):
        GENERAL = 'GENERAL', _('عام / إنشائي وموقع وهيكل')
        ALL_UNIT_FINISHES = 'ALL_UNIT_FINISHES', _('تشطيبات كافة الوحدات السكنية (إجمالي الشقق)')
        TRADE_CATEGORY = 'TRADE_CATEGORY', _('مجموعة أعمال معمارية متخصصة (مباني/سباكة/سيراميك/نقاشة)')
        SPECIFIC_TRADE = 'SPECIFIC_TRADE', _('بند معماري تفصيلي محدد (من مصفوفة الـ 32 بند)')

    class TradeCategory(models.TextChoices):
        MASONRY = 'MASONRY', _('أعمال المباني والحوائط')
        ELECTRICAL = 'ELECTRICAL', _('أعمال تأسيس الكهرباء')
        PLASTER = 'PLASTER', _('أعمال البياض والمحارة')
        PLUMBING = 'PLUMBING', _('أعمال السباكة والعزل الداخلي')
        CERAMIC = 'CERAMIC', _('أعمال الأرضيات والسيراميك')
        PAINT = 'PAINT', _('أعمال الدهانات والنقاشة')
        CARPENTRY_ALUMINUM = 'CARPENTRY_ALUMINUM', _('أعمال النجارة والألوميتال')
        ROOF = 'ROOF', _('أعمال عزل وتشطيب الأسطح')
        BASEMENT = 'BASEMENT', _('أعمال أرضيات وحريق البدروم')

    project = models.ForeignKey(
        'real_estate.RealEstateProject',
        on_delete=models.CASCADE,
        related_name='wbs_activities',
        verbose_name=_('المشروع العقاري')
    )
    block = models.ForeignKey(
        'real_estate.PropertyBlock',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='wbs_activities',
        verbose_name=_('المبنى / البلوك المحدد (اختياري)')
    )
    parent_activity = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='sub_activities',
        verbose_name=_('النشاط الرئيسي (WBS Parent)')
    )
    master_boq_item = models.ForeignKey(
        'real_estate.ProjectMasterBOQItem',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='wbs_activities',
        verbose_name=_('بند المقايسة التقديرية المربوط (Master BOQ)')
    )
    code = models.CharField(
        max_length=50,
        verbose_name=_('كود النشاط (WBS Code)')
    )
    name = models.CharField(
        max_length=255,
        verbose_name=_('اسم النشاط / حزمة الأعمال')
    )
    weight_percentage = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0000')), MaxValueValidator(Decimal('100.0000'))],
        verbose_name=_('وزن النشاط النسبي من المشروع %')
    )
    progress_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        verbose_name=_('نسبة الإنجاز الميداني للنشاط %')
    )
    is_milestone = models.BooleanField(
        default=False,
        verbose_name=_('محطة تسليم رئيسية (Milestone تستحق أقساط مبيعات)')
    )
    baseline_start_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ البدء المخطط (Baseline Start)')
    )
    baseline_end_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ الانتهاء المخطط (Baseline End)')
    )
    is_baseline_locked = models.BooleanField(
        default=False,
        verbose_name=_('تجميد خط الأساس الزمني (Baseline Locked)')
    )
    actual_start_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ البدء الفعلي')
    )
    actual_end_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ الانتهاء الفعلي المعتمد')
    )

    # حقول جسر الربط الهيكلي مع سجلات ومراحل تنفيذ الوحدات (Unit-to-WBS Bridge)
    activity_type = models.CharField(
        max_length=30,
        choices=ActivityType.choices,
        default=ActivityType.GENERAL,
        verbose_name=_('نوع النشاط / حزمة الأعمال')
    )
    trade_category = models.CharField(
        max_length=30,
        choices=TradeCategory.choices,
        blank=True,
        default='',
        verbose_name=_('مجموعة الأعمال المعمارية المربوطة')
    )
    trade_stage = models.CharField(
        max_length=40,
        blank=True,
        default='',
        verbose_name=_('بند التنفيذ الميداني المحدد (مصفوفة الـ 32 بند)')
    )
    auto_sync_progress = models.BooleanField(
        default=False,
        verbose_name=_('مزامنة الإنجاز تلقائياً من واقع سجلات الموقع الميدانية')
    )

    # حقول إدارة القيمة المكتسبة ومؤشرات الأداء المالي والتكلفة (EVM: BAC & AC)
    budget_cost = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('الموازنة التقديرية المعتمدة للنشاط (BAC)')
    )
    actual_cost = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('التكلفة الفعلية المنصرفة حتى تاريخه (AC)')
    )

    class Meta:
        verbose_name = _('نشاط مقايسة مشروع (WBS)')
        verbose_name_plural = _('أنشطة مقايسة المشروع (WBS Tree)')
        ordering = ['code', 'id']
        constraints = [
            models.UniqueConstraint(fields=['project', 'code'], name='unique_wbs_activity_per_project')
        ]
        permissions = [
            ('can_manage_wbs', _('إمكانية إدارة وتعديل شجرة مقايسة المشروع WBS')),
        ]

    def get_level(self) -> int:
        """مستوى النشاط في الشجرة الهرمية (1 للجذر، 2 للأبناء، إلخ)"""
        level = 1
        curr = self.parent_activity
        visited = set()
        while curr:
            if curr.pk in visited:
                break
            visited.add(curr.pk)
            level += 1
            curr = curr.parent_activity
        return level

    @property
    def is_leaf(self) -> bool:
        """هل النشاط نشاط ورقي (بدون أنشطة فرعية)"""
        if self.pk:
            return not self.sub_activities.exists()
        return True

    def get_ancestors(self) -> list:
        """استرجاع قائمة الأنشطة الأب تصاعدياً حتى الجذر"""
        ancestors = []
        curr = self.parent_activity
        visited = set()
        while curr:
            if curr.pk in visited:
                break
            visited.add(curr.pk)
            ancestors.append(curr)
            curr = curr.parent_activity
        return ancestors

    def get_all_descendants(self) -> list:
        """استرجاع كافة الأنشطة التابعة هرمياً بشكل تكراري"""
        descendants = []
        if not self.pk:
            return descendants
        for child in self.sub_activities.all():
            descendants.append(child)
            descendants.extend(child.get_all_descendants())
        return descendants

    def clean(self):
        super().clean()
        # 1. التحقق من علاقة النشاط الأب ومنع الدورات الهرمية
        if self.parent_activity_id:
            if self.pk and self.parent_activity_id == self.pk:
                raise ValidationError({
                    'parent_activity': _('لا يمكن تعيين النشاط كنشاط رئيسي لنفسه.')
                })
            if self.pk:
                descendants_pks = [d.pk for d in self.get_all_descendants()]
                if self.parent_activity_id in descendants_pks:
                    raise ValidationError({
                        'parent_activity': _('لا يمكن تعيين أحد الأنشطة التابعة كنشاط رئيسي (دورة هرمية محظورة).')
                    })
            if self.parent_activity.project_id != self.project_id:
                raise ValidationError({
                    'parent_activity': _('يجب أن ينتمي النشاط الرئيسي لنفس المشروع العقاري.')
                })
            if self.parent_activity.block_id and self.block_id and self.parent_activity.block_id != self.block_id:
                raise ValidationError({
                    'block': _('لا يمكن تعيين عمارة تختلف عن عمارة النشاط الرئيسي.')
                })

        # 2. التحقق من تواريخ خط الأساس والتواريخ الفعلية
        if self.baseline_start_date and self.baseline_end_date and self.baseline_end_date < self.baseline_start_date:
            raise ValidationError({
                'baseline_end_date': _('تاريخ انتهاء خط الأساس لا يمكن أن يسبق تاريخ البدء المخطط.')
            })
        if self.actual_start_date and self.actual_end_date and self.actual_end_date < self.actual_start_date:
            raise ValidationError({
                'actual_end_date': _('تاريخ الانتهاء الفعلي لا يمكن أن يسبق تاريخ البدء الفعلي.')
            })

        # 3. التحقق من تطابق نوع النشاط وحقول الربط
        if self.activity_type == self.ActivityType.SPECIFIC_TRADE and not self.trade_stage:
            raise ValidationError({
                'trade_stage': _('يجب تحديد بند التنفيذ الميداني عند اختيار نشاط بند معماري تفصيلي.')
            })
        if self.activity_type == self.ActivityType.TRADE_CATEGORY and not self.trade_category:
            raise ValidationError({
                'trade_category': _('يجب تحديد مجموعة الأعمال المعمارية عند اختيار نشاط مجموعة أعمال.')
            })

        # 4. تجميد خط الأساس الزمني
        if self.pk:
            orig = ProjectActivity.objects.filter(pk=self.pk).values(
                'is_baseline_locked', 'baseline_start_date', 'baseline_end_date'
            ).first()
            if orig and orig['is_baseline_locked']:
                if not self.is_baseline_locked:
                    raise ValidationError({
                        'is_baseline_locked': _('لا يمكن إلغاء تجميد خط الأساس الزمني لنشاط مجمد (Baseline Freeze Immutable).')
                    })
                if (self.baseline_start_date != orig['baseline_start_date'] or 
                    self.baseline_end_date != orig['baseline_end_date']):
                    raise ValidationError({
                        'baseline_end_date': _('لا يمكن تعديل تواريخ خط الأساس الزمني لنشاط مجمد (Baseline Locked).')
                    })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} - {self.name} ({self.weight_percentage}%)"


class SiteDailyLog(models.Model):
    """سجل يومية الموقع الميدانية للأعمال والطقس والعمالة (FIDIC Standard)"""
    class WeatherCondition(models.TextChoices):
        SUNNY = 'SUNNY', _('مشمس ومناسب للعمل')
        HOT_EXTREME = 'HOT_EXTREME', _('حرارة شديدة مؤثرة على صب الخرسانات')
        RAIN_HEAVY = 'RAIN_HEAVY', _('أمطار غزيرة معطلة للموقع')
        DUST_STORM = 'DUST_STORM', _('عواصف ترابية ورياح شديدة')

    class StoppageReason(models.TextChoices):
        NONE = 'NONE', _('لا يوجد توقف - العمل سارٍ بصورة طبيعية')
        WEATHER = 'WEATHER', _('توقف بسبب ظروف جوية قاهرة')
        MATERIAL_SHORTAGE = 'MATERIAL_SHORTAGE', _('تأخر توريد خامات أساسية من المخازن')
        AUTHORITY_STOP = 'AUTHORITY_STOP', _('إيقاف إداري أو معاينة جهاز المدينة')
        CONTRACTOR_DELAY = 'CONTRACTOR_DELAY', _('تغيب أو تقاعس عمالة مقاول الباطن')

    project = models.ForeignKey(
        'real_estate.RealEstateProject',
        on_delete=models.CASCADE,
        related_name='daily_logs',
        verbose_name=_('المشروع العقاري')
    )
    log_date = models.DateField(
        verbose_name=_('تاريخ اليومية الميدانية')
    )
    weather = models.CharField(
        max_length=20,
        choices=WeatherCondition.choices,
        default=WeatherCondition.SUNNY,
        verbose_name=_('حالة الطقس الميداني')
    )
    total_manpower_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_('إجمالي عدد العمالة والفنيين المتواجدين بالموقع')
    )
    contractor_manpower_breakdown = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_('بيان تفصيلي لعمالة كل مقاول باطن بالموقع')
    )
    stoppage_reason = models.CharField(
        max_length=30,
        choices=StoppageReason.choices,
        default=StoppageReason.NONE,
        verbose_name=_('سبب توقف الأعمال إن وجد')
    )
    delays_recorded_hours = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=Decimal('0.0'),
        verbose_name=_('ساعات التعطيل الموثقة لفرق الأسعار والتمديد الزمني')
    )
    notes = models.TextField(
        blank=True,
        default='',
        verbose_name=_('ملاحظات الموقع والزيارات الاستشارية')
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_('مهندس الموقع المسجل لليومية')
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('يومية موقع ميدانية')
        verbose_name_plural = _('يوميات الموقع الميدانية')
        ordering = ['-log_date', '-id']
        constraints = [
            models.UniqueConstraint(fields=['project', 'log_date'], name='unique_site_daily_log_per_project_date')
        ]
        permissions = [
            ('can_record_site_log', _('إمكانية تسجيل وتوثيق يوميات الموقع الميدانية')),
        ]

    def __str__(self):
        return f"{self.project.name} - {self.log_date} ({self.get_weather_display()})"


class UnitSiteProgressRecord(models.Model):
    """
    سجل متابعة تنفيذ الشقة بنداً بنداً (مصفوفة الـ 32 بنداً المعمارية والتأسيسية):
    - يغطي كافة المراحل من القد والمباني إلى التشطيب والتسليم.
    - يرتبط بمقاول المصنعية المنفذ لحفظ المسؤولية القانونية وتوجيه الضمانات والخصومات.
    - يرتبط بمستخلص مقاول الباطن مع قفل is_billed لمنع تخفيض النسب بعد الصرف.
    - يدعم التحكم في التزامن المتفائل OCC عبر حقل version لمنع تعارض المعاينات.
    """

    class InspectionTrade(models.TextChoices):
        # 1. أعمال المباني والحوائط
        MASONRY_QADD = 'MASONRY_QADD', _('1.1 قد وتحديد حوائط الشقة وفتح الأبواب')
        MASONRY_FULL = 'MASONRY_FULL', _('1.2 إتمام بناء الحوائط والسواقط والشحط')
        # 2. أعمال تأسيس الكهرباء
        ELEC_PIPES = 'ELEC_PIPES', _('2.1 تكسير ودق مواسير وخراطيم الكهرباء بالحوائط')
        ELEC_BOXES = 'ELEC_BOXES', _('2.2 تثبيت ووزن علب الماجيك وميزان الشرب')
        ELEC_WIRING = 'ELEC_WIRING', _('2.3 سحب وتوزيع الأسلاك والكابلات بالقنوات')
        ELEC_FITTING = 'ELEC_FITTING', _('2.4 تركيب الشاسيهات والمفاتيح ولوحة القواطع')
        # 3. أعمال البياض والمحارة
        PLASTER_SPATTER = 'PLASTER_SPATTER', _('3.1 طرطشة حوائط وأسقف الشقة بالكامل')
        PLASTER_STRINGS = 'PLASTER_STRINGS', _('3.2 شد الأوتار وضبط البؤج وتثبيت الشبك')
        PLASTER_FILLING = 'PLASTER_FILLING', _('3.3 ملو الحوائط وتدريع المسطحات بالقدة')
        PLASTER_EDGES = 'PLASTER_EDGES', _('3.4 تركيب زوايا الفلكس وتأكيس النواصي')
        PLASTER_FINISH = 'PLASTER_FINISH', _('3.5 مس وتمشيط بياض المحارة وتسليم الشرب')
        # 4. أعمال السباكة والعزل الداخلي
        PLUMB_WATERPROOF = 'PLUMB_WATERPROOF', _('4.1 عزل حمامات ومطابخ الشقة واختبار الغمر 48 س')
        PLUMB_FEEDING = 'PLUMB_FEEDING', _('4.2 تمديد شبكة تغذية المياه واختبار الكبس بالبار')
        PLUMB_DRAINAGE = 'PLUMB_DRAINAGE', _('4.3 تمديد شبكة الصرف وتثبيت المزاريب والميول')
        PLUMB_TUB_FIX = 'PLUMB_TUB_FIX', _('4.4 تثبيت البانيو / الشاور وبناء الجلسات')
        PLUMB_FITTING = 'PLUMB_FITTING', _('4.5 تركيب الأطقم الصحية والخلاطات والفنش')
        # 5. أعمال الأرضيات والسيراميك
        CERAMIC_FLOORS = 'CERAMIC_FLOORS', _('5.1 ردم وفرش الرمل وتركيب سيراميك/بورسلين الأرضيات')
        CERAMIC_WALLS = 'CERAMIC_WALLS', _('5.2 تركيب سيراميك حوائط المطابخ والحمامات والسقية')
        # 6. أعمال الدهانات والنقاشة
        PAINT_SEALER = 'PAINT_SEALER', _('6.1 تنظيف الحوائط وتطبيق السيلر المائي العازل')
        PAINT_PUTTY_1 = 'PAINT_PUTTY_1', _('6.2 سحب سكينة المعجون الأولى وصنفرتها')
        PAINT_PUTTY_2 = 'PAINT_PUTTY_2', _('6.3 سحب سكينة المعجون الثانية ومعالجة الفواصل')
        PAINT_PRIMER = 'PAINT_PRIMER', _('6.4 تطبيق البطانة واللون التمهيدي وضبط الإضاءة')
        PAINT_FINAL = 'PAINT_FINAL', _('6.5 الوجه النهائي للدهان (الفنش) والتشطيب')
        # 7. النجارة والألوميتال
        CARPENTRY_FRAMES = 'CARPENTRY_FRAMES', _('7.1 تركيب وتثبيت الحلوق الزفرة للأبواب والشبابيك')
        CARPENTRY_DOORS = 'CARPENTRY_DOORS', _('7.2 تركيب ضلف الأبواب والكوالين والإكسسوارات')
        ALUMINUM_WINDOWS = 'ALUMINUM_WINDOWS', _('7.3 تركيب قطاعات الألوميتال والزجاج وسد السيليكون')
        # 8. بنود إضافية مخصصة للأدوار الحاكمة (الأسطح والبدرومات والخدمات)
        ROOF_WATERPROOF_FLOOD_TEST = 'ROOF_WATERPROOF_FLOOD_TEST', _('8.1 عزل السطح المائي والحراري واختبار الغمر 72 ساعة')
        ROOF_TILES_SCREED = 'ROOF_TILES_SCREED', _('8.2 صب خرسانة الميول وتركيب بلاط الأسطح والفواصل')
        BASEMENT_EPOXY_FIRE = 'BASEMENT_EPOXY_FIRE', _('8.3 أرضيات إيبوكسي البدروم وتأسيس شبكة الحريق')

    class StageStatus(models.TextChoices):
        NOT_STARTED = 'NOT_STARTED', _('لم يبدأ العمل بعد (0%)')
        IN_PROGRESS = 'IN_PROGRESS', _('جاري العمل والتنفيذ بالموقع')
        PENDING_INSPECTION = 'PENDING_INSPECTION', _('منجز وبانتظار معاينة واستلام الاستشاري')
        APPROVED_WITH_COMMENTS = 'APPROVED_WITH_COMMENTS', _('اعتماد مشروط مع وجود ملاحظات جاري تلافيها')
        PASSED_AND_VERIFIED = 'PASSED_AND_VERIFIED', _('معتمد ومستلم رسمياً بموجب تقرير فحص (100%)')
        REJECTED_DEFECT = 'REJECTED_DEFECT', _('مرفوض لوجود عيوب بصنعة المقاول (فتح Snag)')
        NOT_APPLICABLE = 'NOT_APPLICABLE', _('غير خاضع للبند تعاقدياً (نصف تشطيب / مستثنى)')

    unit = models.ForeignKey(
        'real_estate.PropertyUnit',
        on_delete=models.CASCADE,
        related_name='site_progress_records',
        verbose_name=_('الوحدة العقارية')
    )
    trade_stage = models.CharField(
        max_length=40,
        choices=InspectionTrade.choices,
        verbose_name=_('بند ومرحلة التنفيذ المعمارية')
    )
    is_applicable = models.BooleanField(
        default=True,
        verbose_name=_('خاضع للبند (تُستثنى بنود التشطيب للوحدات النصف تشطيب)')
    )
    status = models.CharField(
        max_length=30,
        choices=StageStatus.choices,
        default=StageStatus.NOT_STARTED,
        verbose_name=_('حالة المعاينة والاعتماد')
    )
    completion_percentage = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_('نسبة إنجاز البند %')
    )
    contractor = models.ForeignKey(
        'supplier.Supplier',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='trade_site_records',
        verbose_name=_('مقاول المصنعية المسؤول عن التنفيذ')
    )
    subcontractor_certificate_item = models.ForeignKey(
        'real_estate.ContractorCertificateItem',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='site_progress_records',
        verbose_name=_('بند مستخلص مقاول الباطن المرتبط')
    )
    is_billed = models.BooleanField(
        default=False,
        verbose_name=_('تم الصرف في مستخلص مقاول معتمد (قفل تخفيض النسبة)')
    )
    rfi_number = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name=_('رقم طلب الفحص الاستشاري المعتمد (RFI No.)')
    )
    inspection_photo = models.ImageField(
        upload_to='site_inspections/%Y/%m/',
        null=True,
        blank=True,
        verbose_name=_('صورة المعاينة الحية الموثقة (مضغوطة بصيغة WebP)')
    )
    linked_snag = models.ForeignKey(
        'real_estate.UnitSnagItem',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='site_progress_records',
        verbose_name=_('ملاحظة العيب المرتبطة إن وجدت')
    )
    notes = models.TextField(
        blank=True,
        default='',
        verbose_name=_('ملاحظات الاستشاري ومهندس الجودة')
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_site_stages',
        verbose_name=_('مهندس الاستشاري / الجودة القائم بالاعتماد')
    )
    verified_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ وتوقيت الاعتماد الميداني')
    )
    version = models.PositiveIntegerField(
        default=1,
        verbose_name=_('رقم الإصدار لمنع تعارض التحديثات المتزامنة (OCC Lock)')
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('سجل تنفيذ بند وحدة ميداني')
        verbose_name_plural = _('سجلات تنفيذ بنود الوحدات الميدانية')
        ordering = ['unit', 'trade_stage']
        constraints = [
            models.UniqueConstraint(fields=['unit', 'trade_stage'], name='unique_unit_trade_stage_record')
        ]
        permissions = [
            ('can_verify_site_stages', _('إمكانية اعتماد واستلام مراحل التنفيذ الميدانية')),
        ]

    def __str__(self):
        return f"{self.unit.unit_code} - {self.get_trade_stage_display()} ({self.completion_percentage}%)"


class SiteProgressAuditLog(models.Model):
    """سجل تدقيق تاريخي غير قابل للحذف لحركات وتعديلات بنود الموقع"""
    unit = models.ForeignKey(
        'real_estate.PropertyUnit',
        on_delete=models.PROTECT,
        related_name='site_audit_logs',
        verbose_name=_('الوحدة العقارية')
    )
    unit_code_snapshot = models.CharField(
        max_length=50,
        verbose_name=_('لقطة كود الوحدة المجمدة')
    )
    trade_stage = models.CharField(
        max_length=40,
        verbose_name=_('بند التنفيذ')
    )
    previous_percentage = models.PositiveSmallIntegerField(
        verbose_name=_('النسبة السابقة %')
    )
    new_percentage = models.PositiveSmallIntegerField(
        verbose_name=_('النسبة الجديدة %')
    )
    previous_status = models.CharField(
        max_length=30,
        verbose_name=_('الحالة السابقة')
    )
    new_status = models.CharField(
        max_length=30,
        verbose_name=_('الحالة الجديدة')
    )
    defect_notes = models.TextField(
        blank=True,
        default='',
        verbose_name=_('ملاحظات العيوب المسجلة')
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_('المستخدم القائم بالتحديث')
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('تاريخ وتوقيت الحركة')
    )

    class Meta:
        verbose_name = _('سجل تدقيق متابعة موقع')
        verbose_name_plural = _('سجلات تدقيق متابعة الموقع')
        ordering = ['-timestamp', '-id']

    def delete(self, *args, **kwargs):
        raise ValidationError(_('سجلات تدقيق متابعة الموقع غير قابلة للحذف نهائياً (Audit Trail Immutable).'))

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError(_('سجلات تدقيق متابعة الموقع غير قابلة للتعديل بعد إنشائها.'))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.unit_code_snapshot} - {self.trade_stage} [{self.previous_percentage}% -> {self.new_percentage}%]"

