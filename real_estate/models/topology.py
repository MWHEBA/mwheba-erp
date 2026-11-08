# -*- coding: utf-8 -*-
from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _


class PropertyBlock(models.Model):
    """
    نموذج العمارة / البلوك / المبنى داخل المشروع (Building / Block / Sector)
    """
    project = models.ForeignKey(
        'real_estate.RealEstateProject',
        on_delete=models.CASCADE,
        related_name='blocks',
        verbose_name=_('المشروع')
    )
    code = models.CharField(
        max_length=50,
        verbose_name=_('كود العمارة/البلوك')
    )
    name = models.CharField(
        max_length=100,
        verbose_name=_('اسم العمارة/المبنى')
    )
    total_floors = models.PositiveIntegerField(
        default=1,
        verbose_name=_('عدد الطوابق')
    )
    construction_progress_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        db_index=True,
        verbose_name=_('نسبة الإنجاز الإنشائي للبلوك/المبنى %')
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('نشط')
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
        verbose_name = _('عمارة / مبنى عقاري')
        verbose_name_plural = _('العمارات والمباني العقارية')
        ordering = ['project', 'code']
        constraints = [
            models.UniqueConstraint(
                fields=['project', 'code'],
                name='uniq_project_block_code'
            )
        ]

    def __str__(self):
        return f"{self.project.name} - {self.name} ({self.code})"


class PropertyFloor(models.Model):
    """
    نموذج الطابق / المستوى داخل المبنى (Floor)
    """
    class FloorType(models.TextChoices):
        BASEMENT = 'BASEMENT', _('بدروم / جراج')
        GROUND = 'GROUND', _('أرضي')
        MEZZANINE = 'MEZZANINE', _('ميزانين')
        TYPICAL = 'TYPICAL', _('متكرر')
        ROOF = 'ROOF', _('رووف / سطح')
        PENTHOUSE = 'PENTHOUSE', _('بنتهاوس')

    block = models.ForeignKey(
        PropertyBlock,
        on_delete=models.CASCADE,
        related_name='floors',
        verbose_name=_('العمارة/المبنى')
    )
    floor_number = models.IntegerField(
        verbose_name=_('رقم الطابق (0 للأرضي، سالب للبدروم)')
    )
    floor_type = models.CharField(
        max_length=30,
        choices=FloorType.choices,
        default=FloorType.TYPICAL,
        verbose_name=_('نوع الطابق')
    )
    name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_('اسم أو توصيف الطابق')
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('تاريخ الإنشاء')
    )

    class Meta:
        verbose_name = _('طابق عقاري')
        verbose_name_plural = _('الطوابق العقارية')
        ordering = ['block', 'floor_number']
        constraints = [
            models.UniqueConstraint(
                fields=['block', 'floor_number'],
                name='uniq_block_floor_number'
            )
        ]

    def save(self, *args, **kwargs):
        if not self.name:
            self.name = f"{self.get_floor_type_display()} ({self.floor_number})"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.block.name} - {self.name}"
