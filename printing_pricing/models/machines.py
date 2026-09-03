"""
نماذج ماكينات الطباعة ومقاسات التشغيل والزنكات
printing_pricing/models/machines.py
"""
from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _
from .base import BaseLookupModel


class OffsetMachineManager(models.Manager):
    """مدير استعلام ماكينات الأوفست"""
    def get_queryset(self):
        return super().get_queryset().filter(machine_category='offset')


class DigitalMachineManager(models.Manager):
    """مدير استعلام ماكينات الديجيتال"""
    def get_queryset(self):
        return super().get_queryset().filter(machine_category='digital')


class PrintingMachine(BaseLookupModel):
    """
    النموذج الموحد لماكينات الطباعة (أوفست وديجيتال)
    """
    CATEGORY_CHOICES = [
        ('offset', _('ماكينة أوفست')),
        ('digital', _('ماكينة ديجيتال')),
    ]

    machine_category = models.CharField(
        _("نوع وتقنية الماكينة"),
        max_length=20,
        choices=CATEGORY_CHOICES,
        default='offset',
        help_text=_("تقنية الطباعة (أوفست / ديجيتال)")
    )
    code = models.CharField(
        _("رمز الماكينة"),
        max_length=50,
        unique=True,
        blank=True,
        null=True,
        help_text=_("رمز كودي فريد لتعريف الماكينة")
    )
    manufacturer = models.CharField(
        _("الشركة المصنعة"),
        max_length=100,
        blank=True,
        help_text=_("مثل: هايدلبرج، كوموري، زيروكس، كانون")
    )
    max_sheet_size = models.CharField(
        _("أقصى مقاس فرخ"),
        max_length=50,
        blank=True,
        help_text=_("أقصى أبعاد فرخ تستوعبها الماكينة (سم)")
    )
    colors_capacity = models.PositiveIntegerField(
        _("عدد الألوان"),
        default=4,
        help_text=_("عدد أبراج الطباعة لماكينات الأوفست")
    )
    print_quality = models.CharField(
        _("جودة الطباعة"),
        max_length=50,
        blank=True,
        help_text=_("مواصفات دقة الطباعة للديجيتال (DPI)")
    )
    is_color = models.BooleanField(
        _("طباعة ملونة"),
        default=True,
        help_text=_("هل تدعم الطباعة بالألوان أم أبيض وأسود فقط")
    )

    class Meta:
        db_table = 'printing_pricing_printingmachine'
        verbose_name = _("ماكينة طباعة")
        verbose_name_plural = _("ماكينات الطباعة")
        ordering = ['sort_order', 'name']

    def __str__(self):
        cat_display = self.get_machine_category_display()
        return f"{self.name} ({cat_display})"

    @property
    def is_offset(self):
        return self.machine_category == 'offset'

    @property
    def is_digital(self):
        return self.machine_category == 'digital'

    @property
    def default_plate(self):
        """استرجاع زنكة CTP الافتراضية المرتبطة بالماكينة"""
        return self.dimensions.filter(dimension_type='plate', is_active=True).first()


class SheetDimensionManager(models.Manager):
    """مدير استعلام كافة شيتات تشغيل الماكينات"""
    def get_queryset(self):
        return super().get_queryset().filter(dimension_type__in=['offset_sheet', 'digital_sheet', 'sheet'])


class OffsetSheetDimensionManager(models.Manager):
    """مدير استعلام شيتات تشغيل ماكينات الأوفست"""
    def get_queryset(self):
        return super().get_queryset().filter(
            models.Q(dimension_type='offset_sheet') |
            models.Q(dimension_type='sheet', machine__machine_category='offset') |
            models.Q(dimension_type='sheet', machine__isnull=True, code__in=['quarter_sheet', 'half_sheet', 'full_sheet'])
        )


class DigitalSheetDimensionManager(models.Manager):
    """مدير استعلام شيتات تشغيل ماكينات الديجيتال"""
    def get_queryset(self):
        return super().get_queryset().filter(
            models.Q(dimension_type='digital_sheet') |
            models.Q(dimension_type='sheet', machine__machine_category='digital') |
            models.Q(dimension_type='sheet', machine__isnull=True, code__startswith='digital_')
        )


class PlateDimensionManager(models.Manager):
    """مدير استعلام زنكات CTP"""
    def get_queryset(self):
        return super().get_queryset().filter(dimension_type='plate')


class MachineDimension(BaseLookupModel):
    """
    جدول المقاسات الموحد للماكينات: يشمل شيتات التشغيل وزنكات CTP
    """
    DIMENSION_TYPE_CHOICES = [
        ('offset_sheet', _('شيت تشغيل أوفست')),
        ('digital_sheet', _('شيت تشغيل ديجيتال')),
        ('sheet', _('شيت تشغيل عام')),
        ('plate', _('زنكة CTP')),
    ]

    dimension_type = models.CharField(
        _("نوع المقاس"),
        max_length=20,
        choices=DIMENSION_TYPE_CHOICES,
        default='sheet',
        help_text=_("شيت تشغيل للورق أو زنكة ألومنيوم CTP")
    )
    width = models.DecimalField(
        _("العرض (سم)"),
        max_digits=8,
        decimal_places=2,
        help_text=_("عرض المقاس بالسنتيمتر")
    )
    height = models.DecimalField(
        _("الطول (سم)"),
        max_digits=8,
        decimal_places=2,
        help_text=_("طول المقاس بالسنتيمتر")
    )
    code = models.CharField(
        _("رمز المقاس"),
        max_length=50,
        blank=True,
        null=True
    )
    machine = models.ForeignKey(
        PrintingMachine,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='dimensions',
        verbose_name=_("الماكينة المرتبطة"),
        help_text=_("ربط مقاس الشيت أو الزنكة بالماكينة التابعة لها")
    )
    is_custom_size = models.BooleanField(
        _("مقاس مخصص"),
        default=False
    )

    objects = models.Manager()
    sheets = SheetDimensionManager()
    plates = PlateDimensionManager()

    class Meta:
        db_table = 'printing_pricing_machinedimension'
        verbose_name = _("مقاس تشغيل / زنكة")
        verbose_name_plural = _("مقاسات التشغيل والزنكات")
        ordering = ['sort_order', 'name']

    def __str__(self):
        from core.templatetags.pricing_filters import remove_trailing_zeros
        w_clean = remove_trailing_zeros(self.width)
        h_clean = remove_trailing_zeros(self.height)
        return f"{self.name} ({w_clean}×{h_clean} سم)"

    def get_area(self):
        """حساب المساحة بالسنتيمتر المربع"""
        if self.width and self.height:
            return float(self.width * self.height)
        return 0.0

    def get_area_display(self):
        """عرض المساحة بشكل مقروء"""
        return f"{self.get_area():.2f} سم²"

    # توافق عكسي مع الخصائص القديمة
    @property
    def width_cm(self):
        return self.width

    @width_cm.setter
    def width_cm(self, val):
        self.width = val

    @property
    def height_cm(self):
        return self.height

    @height_cm.setter
    def height_cm(self, val):
        self.height = val

    @property
    def machine_type(self):
        return self.machine

    @machine_type.setter
    def machine_type(self, val):
        self.machine = val


# ==============================================================================
# نماذج التوافق العكسي (Backward-Compatibility Proxy Models & Aliases)
# ==============================================================================

class OffsetMachineType(PrintingMachine):
    """Proxy لتمثيل ماكينات الأوفست للتوافق العكسي الكامل"""
    objects = OffsetMachineManager()

    class Meta:
        proxy = True
        verbose_name = _("نوع ماكينة أوفست")
        verbose_name_plural = _("أنواع ماكينات الأوفست")

    def save(self, *args, **kwargs):
        self.machine_category = 'offset'
        super().save(*args, **kwargs)


class DigitalMachineType(PrintingMachine):
    """Proxy لتمثيل ماكينات الديجيتال للتوافق العكسي الكامل"""
    objects = DigitalMachineManager()

    class Meta:
        proxy = True
        verbose_name = _("نوع ماكينة ديجيتال")
        verbose_name_plural = _("أنواع ماكينات الديجيتال")

    def save(self, *args, **kwargs):
        self.machine_category = 'digital'
        super().save(*args, **kwargs)


class OffsetSheetSize(MachineDimension):
    """Proxy لتمثيل مقاسات ماكينات الأوفست للتوافق العكسي الكامل"""
    objects = OffsetSheetDimensionManager()

    class Meta:
        proxy = True
        verbose_name = _("مقاس ماكينة أوفست")
        verbose_name_plural = _("مقاسات ماكينات الأوفست")

    def save(self, *args, **kwargs):
        self.dimension_type = 'offset_sheet'
        super().save(*args, **kwargs)


class DigitalSheetSize(MachineDimension):
    """Proxy لتمثيل مقاسات ماكينات الديجيتال للتوافق العكسي الكامل"""
    objects = DigitalSheetDimensionManager()

    class Meta:
        proxy = True
        verbose_name = _("مقاس ماكينة ديجيتال")
        verbose_name_plural = _("مقاسات ماكينات الديجيتال")

    def save(self, *args, **kwargs):
        self.dimension_type = 'digital_sheet'
        super().save(*args, **kwargs)


class PlateSize(MachineDimension):
    """Proxy لتمثيل مقاسات الزنكات CTP للتوافق العكسي الكامل"""
    objects = PlateDimensionManager()

    class Meta:
        proxy = True
        verbose_name = _("مقاس الزنك")
        verbose_name_plural = _("مقاسات الزنكات")

    def save(self, *args, **kwargs):
        self.dimension_type = 'plate'
        super().save(*args, **kwargs)


__all__ = [
    'PrintingMachine',
    'MachineDimension',
    'OffsetMachineType',
    'DigitalMachineType',
    'OffsetSheetSize',
    'DigitalSheetSize',
    'PlateSize'
]
