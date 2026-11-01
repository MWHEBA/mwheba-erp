# -*- coding: utf-8 -*-
"""
LandownerPartnership Models - نماذج مشاريع المشاركة مع أصحاب الأراضي وتوزيع الإيرادات والوحدات
MWHEBA ERP — Real Estate Landowner Joint Venture & Revenue-Sharing Engine
"""
import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from real_estate.models.unit import PropertyUnit


class LandownerPartnership(models.Model):
    """
    نموذج اتفاقية المشاركة مع مالك الأرض (Landowner Joint Venture):
    - يربط المشروع بمالك الأرض مع تحديد نوع المشاركة (اقتسام وحدات، اقتسام إيرادات، أو كلاهما).
    - يدير نسبة الإيراد التعاقدية وحساب الأستاذ المساعد للمستحقات (Landowner Payable Subledger).
    """

    class PartnershipType(models.TextChoices):
        UNIT_ALLOCATION = 'UNIT_ALLOCATION', _('اقتسام عيني للوحدات (Unit Allocation)')
        REVENUE_SHARING = 'REVENUE_SHARING', _('اقتسام نسبي للإيرادات (Revenue Sharing)')
        HYBRID = 'HYBRID', _('مختلط (وحدات عينية + نسبة إيرادات)')

    class PartnershipStatus(models.TextChoices):
        DRAFT = 'DRAFT', _('مسودة')
        ACTIVE = 'ACTIVE', _('سارية ونشطة')
        SUSPENDED = 'SUSPENDED', _('معلقة مؤقتاً')
        COMPLETED = 'COMPLETED', _('مكتملة ومسواة بالكامل')
        TERMINATED = 'TERMINATED', _('ملغاة / مفسوخة')

    partnership_number = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name=_('رقم اتفاقية المشاركة')
    )
    project = models.ForeignKey(
        'real_estate.RealEstateProject',
        on_delete=models.PROTECT,
        related_name='landowner_partnerships',
        verbose_name=_('المشروع العقاري')
    )
    partner_name = models.CharField(
        max_length=200,
        verbose_name=_('اسم مالك الأرض / الشريك')
    )
    partner_national_id = models.CharField(
        max_length=14,
        blank=True,
        default='',
        verbose_name=_('الرقم القومي لمالك الأرض')
    )
    partner_phone = models.CharField(
        max_length=30,
        blank=True,
        default='',
        verbose_name=_('رقم هاتف مالك الأرض')
    )
    customer = models.ForeignKey(
        'customer.Customer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='landowner_partnerships',
        verbose_name=_('ملف العميل المالي (إن وجد)')
    )
    supplier = models.ForeignKey(
        'supplier.Supplier',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='landowner_partnerships',
        verbose_name=_('ملف المورد/الدائن المالي (إن وجد)')
    )
    partnership_type = models.CharField(
        max_length=30,
        choices=PartnershipType.choices,
        default=PartnershipType.REVENUE_SHARING,
        db_index=True,
        verbose_name=_('نوع اتفاقية المشاركة')
    )
    revenue_share_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('نسبة مالك الأرض من الإيرادات (%)')
    )
    land_area_sqm = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي مساحة الأرض المساهم بها (م²)')
    )
    agreed_land_valuation = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('التقييم التعاقدي المعتمد للأرض')
    )
    payable_account = models.ForeignKey(
        'financial.ChartOfAccounts',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='landowner_partnerships',
        verbose_name=_('حساب أستاذ مالك الأرض المساعد')
    )
    status = models.CharField(
        max_length=30,
        choices=PartnershipStatus.choices,
        default=PartnershipStatus.DRAFT,
        db_index=True,
        verbose_name=_('حالة الاتفاقية')
    )
    contract_date = models.DateField(
        default=timezone.localdate,
        verbose_name=_('تاريخ إبرام عقد المشاركة')
    )
    terms_notes = models.TextField(
        blank=True,
        default='',
        verbose_name=_('الشروط والبنود التعاقدية الخاصة')
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_landowner_partnerships',
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
        verbose_name = _('اتفاقية مشاركة مع مالك أرض')
        verbose_name_plural = _('اتفاقيات المشاركة مع ملاك الأراضي')
        ordering = ['-contract_date', '-id']
        constraints = [
            models.CheckConstraint(
                check=models.Q(revenue_share_percentage__gte=0) & models.Q(revenue_share_percentage__lte=Decimal('100.00')),
                name='chk_landowner_rev_share_range'
            ),
            models.CheckConstraint(
                check=models.Q(land_area_sqm__gte=0),
                name='chk_landowner_area_non_negative'
            ),
        ]

    def clean(self):
        super().clean()
        if self.partnership_type in [self.PartnershipType.REVENUE_SHARING, self.PartnershipType.HYBRID]:
            if self.revenue_share_percentage <= Decimal('0.00'):
                raise ValidationError(_("يجب تحديد نسبة إيراد أكبر من الصفر لنظام اقتسام الإيرادات."))

    def save(self, *args, **kwargs):
        if not self.partnership_number:
            self.partnership_number = f"JV-{self.project.code}-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.partnership_number} - {self.partner_name} ({self.project.name})"


class LandownerUnitAllocation(models.Model):
    """
    نموذج تخصيص الوحدات العينية لمالك الأرض:
    - يربط الوحدة باتفاقية المشاركة ويقفل حالتها إلكترونياً على LANDOWNER_ALLOCATED.
    - يمنع الحجز أو البيع العرضي من قبل مسؤولي المبيعات.
    """

    class HandoverStatus(models.TextChoices):
        PENDING = 'PENDING', _('قيد الإنشاء والتجهيز')
        READY_FOR_HANDOVER = 'READY_FOR_HANDOVER', _('جاهزة للتسليم العيني')
        HANDED_OVER = 'HANDED_OVER', _('تم التسليم الفعلي لمالك الأرض')

    partnership = models.ForeignKey(
        LandownerPartnership,
        on_delete=models.CASCADE,
        related_name='unit_allocations',
        verbose_name=_('اتفاقية المشاركة')
    )
    unit = models.OneToOneField(
        PropertyUnit,
        on_delete=models.PROTECT,
        related_name='landowner_allocation',
        verbose_name=_('الوحدة المخصصة لمالك الأرض')
    )
    handover_status = models.CharField(
        max_length=30,
        choices=HandoverStatus.choices,
        default=HandoverStatus.PENDING,
        verbose_name=_('حالة تسليم الوحدة')
    )
    allocated_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('تاريخ التخصيص')
    )
    allocated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_landowner_unit_allocations',
        verbose_name=_('خصص بواسطة')
    )
    notes = models.TextField(
        blank=True,
        default='',
        verbose_name=_('ملاحظات التخصيص')
    )

    class Meta:
        verbose_name = _('تخصيص وحدة لمالك الأرض')
        verbose_name_plural = _('تخصيصات وحدات ملاك الأراضي')
        ordering = ['partnership', 'unit']

    def clean(self):
        super().clean()
        if self.unit_id and self.partnership_id and self.unit.project_id != self.partnership.project_id:
            raise ValidationError(_("الوحدة العقارية لا تنتمي إلى ذات مشروع اتفاقية المشاركة."))
        if self.unit_id and self.unit.status not in [PropertyUnit.UnitStatus.AVAILABLE, PropertyUnit.UnitStatus.LANDOWNER_ALLOCATED]:
            raise ValidationError(
                _("لا يمكن تخصيص الوحدة %(unit)s لمالك الأرض لأن حالتها الحالية '%(status)s' (ليست متاحة).") % {
                    'unit': self.unit.unit_code,
                    'status': self.unit.get_status_display()
                }
            )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
        # قفل حالة الوحدة على LANDOWNER_ALLOCATED
        if self.unit.status != PropertyUnit.UnitStatus.LANDOWNER_ALLOCATED:
            self.unit.status = PropertyUnit.UnitStatus.LANDOWNER_ALLOCATED
            self.unit.status_version += 1
            self.unit.save(update_fields=['status', 'status_version'])

    def delete(self, *args, **kwargs):
        unit = self.unit
        super().delete(*args, **kwargs)
        # إعادة الوحدة لحالة AVAILABLE عند إلغاء التخصيص
        if unit.status == PropertyUnit.UnitStatus.LANDOWNER_ALLOCATED:
            unit.status = PropertyUnit.UnitStatus.AVAILABLE
            unit.status_version += 1
            unit.save(update_fields=['status', 'status_version'])

    def __str__(self):
        return f"{self.partnership.partner_name} -> {self.unit.unit_code}"


class LandownerRevenueShareAccrual(models.Model):
    """
    نموذج استحقاق مالك الأرض من المتحصلات النقدية (Revenue Sharing Accrual):
    - يثبت الاستحقاق التناسبي في أستاذ مالك الأرض المساعد فور تحصيل أي دفعة حجز أو قسط.
    """

    class AccrualStatus(models.TextChoices):
        ACCRUED = 'ACCRUED', _('مستحق دفترياً')
        APPROVED_FOR_PAYMENT = 'APPROVED_FOR_PAYMENT', _('معتمد للصرف')
        DISBURSED = 'DISBURSED', _('تم الصرف الفعلي')
        REVERSED = 'REVERSED', _('معكوس / ملغي')

    accrual_number = models.CharField(
        max_length=60,
        unique=True,
        db_index=True,
        verbose_name=_('رقم استحقاق الإيراد')
    )
    partnership = models.ForeignKey(
        LandownerPartnership,
        on_delete=models.PROTECT,
        related_name='revenue_accruals',
        verbose_name=_('اتفاقية المشاركة')
    )
    contract = models.ForeignKey(
        'real_estate.PropertyContract',
        on_delete=models.PROTECT,
        related_name='landowner_accruals',
        verbose_name=_('العقد العقاري المحصل منه')
    )
    installment_item = models.ForeignKey(
        'sale.InstallmentItem',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='landowner_accruals',
        verbose_name=_('قسط الاستحقاق المحصل (إن وجد)')
    )
    collection_event = models.CharField(
        max_length=50,
        default='INSTALLMENT_COLLECTION',
        verbose_name=_('نوع حركة التحصيل')
    )
    collected_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name=_('المبلغ المحصل الفعلي')
    )
    share_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name=_('نسبة مالك الأرض المطبقة (%)')
    )
    accrued_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name=_('المبلغ المستحق لمالك الأرض')
    )
    accrual_date = models.DateField(
        default=timezone.localdate,
        verbose_name=_('تاريخ الاستحقاق')
    )
    status = models.CharField(
        max_length=30,
        choices=AccrualStatus.choices,
        default=AccrualStatus.ACCRUED,
        db_index=True,
        verbose_name=_('حالة الاستحقاق')
    )
    journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='landowner_accruals',
        verbose_name=_('قيد اليومية المثبت للاستحقاق')
    )
    notes = models.TextField(
        blank=True,
        default='',
        verbose_name=_('ملاحظات الاستحقاق')
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_landowner_accruals',
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
        verbose_name = _('استحقاق حصة مالك أرض')
        verbose_name_plural = _('استحقاقات حصص ملاك الأراضي')
        ordering = ['-accrual_date', '-id']

    def save(self, *args, **kwargs):
        if not self.accrual_number:
            self.accrual_number = f"ACR-{self.partnership.id}-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.accrual_number} - {self.partnership.partner_name} - {self.accrued_amount:,.2f}"
