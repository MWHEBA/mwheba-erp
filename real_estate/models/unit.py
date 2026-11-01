# -*- coding: utf-8 -*-
from decimal import Decimal
from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class PropertyUnit(models.Model):
    """
    نموذج الوحدة العقارية المفردة (Apartment / Villa / Office / Clinic / Shop)
    يدعم التحكم في التزامن المتفائل OCC عبر status_version وحسابات المساحات
    """
    class UnitType(models.TextChoices):
        APARTMENT = 'APARTMENT', _('شقة سكنية')
        DUPLEX = 'DUPLEX', _('دوبلكس')
        PENTHOUSE = 'PENTHOUSE', _('بنتهاوس')
        VILLA = 'VILLA', _('فيلا مستقلة')
        TOWNHOUSE = 'TOWNHOUSE', _('تاون هاوس')
        CHALET = 'CHALET', _('شاليه مصيفي')
        CLINIC = 'CLINIC', _('عيادة طبية')
        OFFICE = 'OFFICE', _('مكتب إداري')
        RETAIL_STORE = 'RETAIL_STORE', _('محل تجاري')
        STORAGE = 'STORAGE', _('مخزن بضائع')

    class UnitStatus(models.TextChoices):
        AVAILABLE = 'AVAILABLE', _('متاحة للبيع')
        RESERVED = 'RESERVED', _('محجوزة مؤقتاً')
        CONTRACTED = 'CONTRACTED', _('مباعة بموجب عقد')
        BLOCKED = 'BLOCKED', _('محظورة / موقوفة إدارياً')
        DELIVERED = 'DELIVERED', _('تم التسليم للعميل')
        LANDOWNER_ALLOCATED = 'LANDOWNER_ALLOCATED', _('مخصصة لمالك الأرض (مشاركة)')
        DELIVERED_DEEMED = 'DELIVERED_DEEMED', _('تم التسليم الحُكمي بقوة العقد')

    class Orientation(models.TextChoices):
        NORTH = 'NORTH', _('بحري')
        NORTH_EAST = 'NORTH_EAST', _('بحري شرقي')
        NORTH_WEST = 'NORTH_WEST', _('بحري غربي')
        EAST = 'EAST', _('شرقي')
        WEST = 'WEST', _('غربي')
        SOUTH = 'SOUTH', _('قبلي')
        SOUTH_EAST = 'SOUTH_EAST', _('قبلي شرقي')
        SOUTH_WEST = 'SOUTH_WEST', _('قبلي غربي')

    class ViewType(models.TextChoices):
        MAIN_STREET = 'MAIN_STREET', _('شارع رئيسي')
        SIDE_STREET = 'SIDE_STREET', _('شارع جانبي')
        GARDEN_PARK = 'GARDEN_PARK', _('حديقة / لاندسكيب')
        POOL_VIEW = 'POOL_VIEW', _('حمام سباحة / بحيرة')
        OPEN_VIEW = 'OPEN_VIEW', _('إطلالة مفتوحة')
        INTERNAL_COURT = 'INTERNAL_COURT', _('منور داخلي / واجهة خلفية')

    class FinishingType(models.TextChoices):
        CORE_AND_SHELL = 'CORE_AND_SHELL', _('طوب أحمر / هيكل خرساني')
        SEMI_FINISHED = 'SEMI_FINISHED', _('نصف تشطيب - محارة وحلوق')
        FULLY_FINISHED = 'FULLY_FINISHED', _('تشطيب كامل - سوبر لوكس')
        ULTRA_LUX = 'ULTRA_LUX', _('ألترا لوكس')

    project = models.ForeignKey(
        'real_estate.RealEstateProject',
        on_delete=models.PROTECT,
        related_name='units',
        verbose_name=_('المشروع')
    )
    block = models.ForeignKey(
        'real_estate.PropertyBlock',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='units',
        verbose_name=_('العمارة / المبنى')
    )
    floor = models.ForeignKey(
        'real_estate.PropertyFloor',
        on_delete=models.PROTECT,
        related_name='units',
        verbose_name=_('الطابق')
    )
    unit_code = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name=_('كود الوحدة الفريد')
    )
    unit_type = models.CharField(
        max_length=30,
        choices=UnitType.choices,
        default=UnitType.APARTMENT,
        db_index=True,
        verbose_name=_('نوع الوحدة')
    )
    net_area = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_('المساحة الصافية (م²)')
    )
    gross_area = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_('المساحة الإجمالية البيعية (م²)')
    )
    terrace_area = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('مساحة التراس / البلكونة (م²)')
    )
    garden_area = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('مساحة الحديقة الخاصة (م²)')
    )
    loading_ratio = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('نسبة التحميل (%)')
    )
    meter_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_('سعر المتر المربع')
    )
    base_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name=_('السعر الأساسي للوحدة')
    )
    total_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name=_('إجمالي سعر الوحدة النهائي')
    )
    orientation = models.CharField(
        max_length=30,
        choices=Orientation.choices,
        default=Orientation.NORTH,
        verbose_name=_('اتجاه الواجهة (بحري/قبلي/شرقي/غربي)')
    )
    view_type = models.CharField(
        max_length=30,
        choices=ViewType.choices,
        default=ViewType.MAIN_STREET,
        verbose_name=_('نوع الإطلالة والفيو')
    )
    is_corner = models.BooleanField(
        default=False,
        verbose_name=_('وحدة ناصية')
    )
    finishing_type = models.CharField(
        max_length=30,
        choices=FinishingType.choices,
        default=FinishingType.SEMI_FINISHED,
        verbose_name=_('مستوى التشطيب')
    )
    parking_slots_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_('عدد باكيات الجراج المخصصة للوحدة')
    )
    parking_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي سعر الجراج')
    )
    garden_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي سعر الحديقة الخاصة')
    )
    maintenance_deposit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('وديعة الصيانة القانونية')
    )
    pricing_breakdown = models.JSONField(
        null=True,
        blank=True,
        default=dict,
        verbose_name=_('تفصيل معادلة التسعير وعلاوات التميز')
    )
    status = models.CharField(
        max_length=30,
        choices=UnitStatus.choices,
        default=UnitStatus.AVAILABLE,
        db_index=True,
        verbose_name=_('حالة الوحدة')
    )
    current_booking = models.ForeignKey(
        'real_estate.UnitBooking',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
        verbose_name=_('الحجز النشط الحالي')
    )
    status_version = models.BigIntegerField(
        default=0,
        verbose_name=_('إصدار حالة الوحدة (OCC Lock Version)')
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('نشطة')
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
        verbose_name = _('وحدة عقارية')
        verbose_name_plural = _('الوحدات العقارية')
        ordering = ['project', 'unit_code']
        indexes = [
            models.Index(fields=['project', 'floor', 'status'], name='idx_re_proj_flr_stat'),
            models.Index(fields=['unit_code'], name='idx_re_unit_code'),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(gross_area__gte=models.F('net_area')),
                name='chk_unit_gross_gte_net'
            ),
            models.CheckConstraint(
                check=models.Q(meter_price__gte=0) & models.Q(total_price__gte=0),
                name='chk_unit_prices_positive'
            ),
        ]

    def clean(self):
        super().clean()
        if self.gross_area is not None and self.net_area is not None and self.gross_area < self.net_area:
            raise ValidationError(_("المساحة الإجمالية للوحدة يجب ألا تقل عن المساحة الصافية."))
        if self.floor and self.block and self.floor.block_id != self.block_id:
            raise ValidationError(_("الطابق المحدد لا ينتمي إلى العمارة/المبنى المختار."))

    def save(self, *args, **kwargs):
        if self.net_area is None and self.gross_area is not None:
            self.net_area = self.gross_area
        if not self.base_price and self.gross_area is not None and self.meter_price is not None:
            self.base_price = (self.gross_area * self.meter_price).quantize(Decimal('0.01'))
        if not self.total_price and self.base_price is not None:
            self.total_price = (self.base_price + (self.garden_price or Decimal('0.00')) + (self.parking_price or Decimal('0.00'))).quantize(Decimal('0.01'))
        if (
            self.gross_area is not None and self.net_area is not None and
            self.gross_area > 0 and self.net_area > 0 and
            (self.loading_ratio is None or self.loading_ratio == Decimal('0.00'))
        ):
            self.loading_ratio = (((self.gross_area - self.net_area) / self.net_area) * Decimal('100.00')).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.unit_code} - {self.get_unit_type_display()} ({self.get_status_display()})"
