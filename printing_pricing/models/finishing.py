"""
نماذج خدمات التشطيب والتغطية والتقفيل
printing_pricing/models/finishing.py
"""
from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _
from .base import BaseLookupModel


class CoatingType(BaseLookupModel):
    """نموذج أنواع التغطية (سلوفان لامع، سلوفان مط، ورنيش...)"""

    unit_rate = models.DecimalField(
        _("سعر الوحدة القياسي"),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )
    setup_cost = models.DecimalField(
        _("فتحة الماكينة / الإعداد"),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )
    minimum_charge = models.DecimalField(
        _("الحد الأدنى للتشغيل"),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )
    make_ready_waste_sheets = models.PositiveIntegerField(
        _("أفرخ هدر التظبيط"),
        default=15
    )

    class Meta:
        db_table = "printing_pricing_coatingtype"
        verbose_name = _("نوع التغطية")
        verbose_name_plural = _("أنواع التغطية")
        ordering = ["sort_order", "name"]


class FinishingType(BaseLookupModel):
    """نموذج أنواع خدمات التشطيب (قص، ريجة، تكسير، بصمة، UV)"""

    unit_rate = models.DecimalField(
        _("سعر الوحدة القياسي"),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )
    setup_cost = models.DecimalField(
        _("فتحة الماكينة / الإعداد"),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )
    minimum_charge = models.DecimalField(
        _("الحد الأدنى للتشغيل"),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )
    tooling_cost = models.DecimalField(
        _("تكلفة الفورمة / الكليشيه"),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )
    make_ready_waste_sheets = models.PositiveIntegerField(
        _("أفرخ هدر التظبيط"),
        default=10
    )

    class Meta:
        db_table = "printing_pricing_finishingtype"
        verbose_name = _("نوع خدمة الطباعة")
        verbose_name_plural = _("أنواع خدمات الطباعة")
        ordering = ["sort_order", "name"]


class PackagingType(BaseLookupModel):
    """نموذج أنواع خدمات التقفيل والتجليد (دبوس، بشر، سلك، تجليد)"""

    unit_rate = models.DecimalField(
        _("سعر الوحدة القياسي"),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )
    setup_cost = models.DecimalField(
        _("فتحة الماكينة / الإعداد"),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )
    minimum_charge = models.DecimalField(
        _("الحد الأدنى للتشغيل"),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )

    class Meta:
        db_table = "printing_pricing_packagingtype"
        verbose_name = _("نوع التقفيل")
        verbose_name_plural = _("أنواع التقفيل")
        ordering = ["sort_order", "name"]


__all__ = [
    'CoatingType',
    'FinishingType',
    'PackagingType'
]
