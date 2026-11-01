# -*- coding: utf-8 -*-
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class UnitPricingMatrixConfig(models.Model):
    """
    نموذج إعدادات مصفوفة التسعير الآلي لمشروع أو مبنى عقاري
    (Wave 2 Phase 4: Unit Pricing Matrix Engine)
    يحسب أسعار الوحدات تلقائياً استناداً إلى سعر المتر الأساسي وعلاوات الأدوار والاتجاهات والإطلالات.
    """
    project = models.ForeignKey(
        'real_estate.RealEstateProject',
        on_delete=models.CASCADE,
        related_name='pricing_configs',
        verbose_name=_('المشروع العقاري')
    )
    block = models.ForeignKey(
        'real_estate.PropertyBlock',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='pricing_configs',
        verbose_name=_('العمارة / المبنى (اختياري - لتسعير خاص بعمارة)')
    )
    name = models.CharField(
        max_length=150,
        verbose_name=_('اسم لائحة التسعير')
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('لائحة التسعير النشطة المعتمدة')
    )

    # 1. سعر المتر الأساسي والدور المرجعي
    base_meter_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_('سعر المتر المربع الأساسي (ج.م)')
    )
    base_floor_number = models.IntegerField(
        default=1,
        verbose_name=_('رقم الطابق الأساسي المرجعي (Base Floor)')
    )
    floor_rise_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('1.50'),
        verbose_name=_('علاوة تدرج الأدوار لكل طابق أعلى الأساسي (%)')
    )

    # 2. علاوات الاتجاهات والواجهات (Orientation Premiums)
    north_orientation_premium = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.00'),
        verbose_name=_('علاوة الواجهة البحرية (%)')
    )
    north_east_premium = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('4.00'),
        verbose_name=_('علاوة واجهة بحري شرقي (%)')
    )
    north_west_premium = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('3.00'),
        verbose_name=_('علاوة واجهة بحري غربي (%)')
    )
    east_orientation_premium = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('2.00'),
        verbose_name=_('علاوة الواجهة الشرقية (%)')
    )
    west_orientation_premium = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('علاوة الواجهة الغربية (%)')
    )
    south_orientation_premium = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('علاوة الواجهة القبلية (%)')
    )

    # 3. علاوات الإطلالة والفيو (View Premiums & Discounts)
    main_street_view_premium = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('6.00'),
        verbose_name=_('علاوة إطلالة على شارع رئيسي (%)')
    )
    garden_park_view_premium = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.00'),
        verbose_name=_('علاوة إطلالة على حديقة أو لاندسكيب (%)')
    )
    pool_water_view_premium = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('7.00'),
        verbose_name=_('علاوة إطلالة على بحيرة أو حمام سباحة (%)')
    )
    open_view_premium = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('3.00'),
        verbose_name=_('علاوة إطلالة مفتوحة غير مجروحة (%)')
    )
    side_street_view_premium = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('علاوة إطلالة على شارع جانبي (%)')
    )
    internal_court_discount = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.00'),
        verbose_name=_('خصم الواجهة الخلفية / المنور الداخلي (%)')
    )

    # 4. علاوة الناصية والمساحات الخاصة
    corner_unit_premium = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('4.00'),
        verbose_name=_('علاوة الوحدة الناصية (%)')
    )
    garden_meter_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('5000.00'),
        verbose_name=_('سعر متر الحديقة الخاصة (ج.م)')
    )
    parking_slot_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('150000.00'),
        verbose_name=_('سعر باكية الجراج / الموقف (ج.م)')
    )

    # 5. فروق التشطيب ومصاريف الصيانة
    fully_finished_meter_addon = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('4000.00'),
        verbose_name=_('تكلفة إضافية للمتر للتشطيب الكامل (ج.م/م²)')
    )
    ultra_lux_meter_addon = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('7000.00'),
        verbose_name=_('تكلفة إضافية للمتر للألترا لوكس (ج.م/م²)')
    )
    maintenance_deposit_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('8.00'),
        verbose_name=_('نسبة وديعة الصيانة القانونية (%)')
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_pricing_configs',
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
        verbose_name = _('إعداد مصفوفة تسعير الوحدات')
        verbose_name_plural = _('إعدادات مصفوفات تسعير الوحدات')
        ordering = ['project', '-is_active', '-id']

    def clean(self):
        super().clean()
        if self.base_meter_price <= Decimal('0.00'):
            raise ValidationError(_("سعر المتر الأساسي يجب أن يكون أكبر من الصفر."))
        if self.block and self.block.project_id != self.project_id:
            raise ValidationError(_("العمارة المختارة لا تتبع المشروع المحدد."))

    def save(self, *args, **kwargs):
        if self.is_active:
            # إلغاء تفعيل اللوائح السابقة لنفس المشروع/العمارة
            qs = UnitPricingMatrixConfig.objects.filter(project=self.project, block=self.block, is_active=True)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            qs.update(is_active=False)
        super().save(*args, **kwargs)

    def __str__(self):
        target = f"{self.project.name} - {self.block.name}" if self.block else self.project.name
        return f"{self.name} ({target}) - {self.base_meter_price} ج.م/م²"
