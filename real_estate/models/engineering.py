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
