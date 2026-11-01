# -*- coding: utf-8 -*-
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class AsBuiltSurveyAdjustment(models.Model):
    """
    ملحق تسوية فروق الرفع المساحي الفعلي المعتمد للوحدة (As-Built Survey Area Adjustment)
    يقارن المساحة الفعلية بالتعاقدية ويطبق نسبة التفاوت المسموحة (±3%) ويولد التسوية المالية
    """
    class AdjustmentType(models.TextChoices):
        SURPLUS_CHARGE = 'SURPLUS_CHARGE', _('زيادة مساحة مشروعة (إضافة قسط تسوية ختامي)')
        DEFICIT_CREDIT = 'DEFICIT_CREDIT', _('عجز مساحة (تخفيض من الأقساط الأخيرة أو إشعار دائن)')
        WITHIN_TOLERANCE = 'WITHIN_TOLERANCE', _('ضمن نسبة التفاوت المسموحة تعاقدياً (لا أثر مالي)')

    class AdjustmentStatus(models.TextChoices):
        DRAFT = 'DRAFT', _('مسودة')
        APPROVED = 'APPROVED', _('معتمد')
        EXECUTED = 'EXECUTED', _('منفذ ومرحل دفترياً')
        CANCELLED = 'CANCELLED', _('ملغي')

    adjustment_number = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name=_('رقم ملحق التسوية المساحية')
    )
    contract = models.ForeignKey(
        'real_estate.PropertyContract',
        on_delete=models.PROTECT,
        related_name='survey_adjustments',
        verbose_name=_('العقد العقاري')
    )
    unit = models.ForeignKey(
        'real_estate.PropertyUnit',
        on_delete=models.PROTECT,
        related_name='survey_adjustments',
        verbose_name=_('الوحدة العقارية')
    )
    contract_gross_area = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_('المساحة الإجمالية التعاقدية (م²)')
    )
    surveyed_gross_area = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_('المساحة الفعلية المعتمدة بالرفع المساحي (م²)')
    )
    area_variance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('فارق المساحة (م²)')
    )
    area_variance_percentage = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('نسبة فارق المساحة (%)')
    )
    contract_meter_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_('سعر المتر المربع التعاقدي الأصلي')
    )
    financial_variance = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('القيمة المالية لفارق المساحة (ج.م)')
    )
    contractual_tolerance_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('3.00'),
        verbose_name=_('نسبة التفاوت المسموحة تعاقدياً (±%)')
    )
    adjustment_type = models.CharField(
        max_length=30,
        choices=AdjustmentType.choices,
        default=AdjustmentType.WITHIN_TOLERANCE,
        verbose_name=_('نوع التسوية المساحية')
    )
    status = models.CharField(
        max_length=30,
        choices=AdjustmentStatus.choices,
        default=AdjustmentStatus.DRAFT,
        db_index=True,
        verbose_name=_('حالة ملحق التسوية')
    )
    notes = models.TextField(blank=True, verbose_name=_('ملاحظات تقرير الرفع المساحي الهندسي'))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_survey_adjustments',
        verbose_name=_('أنشئ بواسطة')
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_survey_adjustments',
        verbose_name=_('معتمد من')
    )
    executed_at = models.DateTimeField(null=True, blank=True, verbose_name=_('تاريخ التنفيذ'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ الإنشاء'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('تاريخ التحديث'))

    class Meta:
        verbose_name = _('ملحق تسوية رفع مساحي فعلي')
        verbose_name_plural = _('ملاحق تسوية فروق الرفع المساحي')
        ordering = ['-created_at']

    def clean(self):
        super().clean()
        if self.contract_id and self.unit_id and self.contract.unit_id != self.unit_id:
            raise ValidationError(_("الوحدة المحددة لا تطابق الوحدة المقيدة بالعقد العقاري."))

    def save(self, *args, **kwargs):
        if self.surveyed_gross_area is not None and self.contract_gross_area is not None:
            self.area_variance = self.surveyed_gross_area - self.contract_gross_area
            if self.contract_gross_area > Decimal('0.00'):
                self.area_variance_percentage = (
                    (self.area_variance / self.contract_gross_area) * Decimal('100.00')
                ).quantize(Decimal('0.01'))
            if self.contract_meter_price is not None:
                self.financial_variance = (self.area_variance * self.contract_meter_price).quantize(Decimal('0.01'))

            tol = self.contractual_tolerance_percentage or Decimal('3.00')
            if abs(self.area_variance_percentage) <= tol:
                self.adjustment_type = self.AdjustmentType.WITHIN_TOLERANCE
            elif self.area_variance > Decimal('0.00'):
                self.adjustment_type = self.AdjustmentType.SURPLUS_CHARGE
            else:
                self.adjustment_type = self.AdjustmentType.DEFICIT_CREDIT

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.adjustment_number} - {self.unit.unit_code} (Δ {self.area_variance} m²)"
