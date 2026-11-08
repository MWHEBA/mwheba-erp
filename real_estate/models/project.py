# -*- coding: utf-8 -*-
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class RealEstateProject(models.Model):
    """
    نموذج المشروع العقاري الرئيسي (Compound / Mall / Tower / Mixed-use)
    """
    class ProjectType(models.TextChoices):
        RESIDENTIAL = 'RESIDENTIAL', _('سكني')
        COMMERCIAL = 'COMMERCIAL', _('تجاري')
        ADMINISTRATIVE = 'ADMINISTRATIVE', _('إداري')
        MIXED_USE = 'MIXED_USE', _('متعدد الاستخدامات')
        INDUSTRIAL = 'INDUSTRIAL', _('صناعي / لوجستي')

    class ProjectStatus(models.TextChoices):
        PLANNING = 'PLANNING', _('مرحلة التخطيط والترخيص')
        UNDER_CONSTRUCTION = 'UNDER_CONSTRUCTION', _('تحت الإنشاء')
        COMPLETED = 'COMPLETED', _('مكتمل البناء')
        DELIVERED = 'DELIVERED', _('تم التسليم بالكامل')
        ON_HOLD = 'ON_HOLD', _('معلق مؤقتاً')

    class RevenueRecognitionMethod(models.TextChoices):
        POINT_IN_TIME_HANDOVER = 'POINT_IN_TIME_HANDOVER', _('الاعتراف بالإيراد عند التسليم الفعلي/الحُكمي (Point in Time)')
        OVER_TIME_POC = 'OVER_TIME_POC', _('الاعتراف بالإيراد على مدار فترة البناء وفق نسبة الإنجاز (IFRS 15 Over Time POC)')

    code = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name=_('كود المشروع')
    )
    name = models.CharField(
        max_length=200,
        verbose_name=_('اسم المشروع')
    )
    project_type = models.CharField(
        max_length=30,
        choices=ProjectType.choices,
        default=ProjectType.RESIDENTIAL,
        db_index=True,
        verbose_name=_('نوع المشروع')
    )
    status = models.CharField(
        max_length=30,
        choices=ProjectStatus.choices,
        default=ProjectStatus.PLANNING,
        db_index=True,
        verbose_name=_('حالة المشروع')
    )
    revenue_recognition_method = models.CharField(
        max_length=30,
        choices=RevenueRecognitionMethod.choices,
        default=RevenueRecognitionMethod.POINT_IN_TIME_HANDOVER,
        db_index=True,
        verbose_name=_('طريقة الاعتراف بالإيراد (IFRS 15)')
    )
    construction_progress_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        db_index=True,
        verbose_name=_('نسبة الإنجاز الإنشائي الموزونة للمشروع %')
    )
    total_budget_cost = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي الموازنة التقديرية المعتمدة للمشروع (BAC)')
    )
    escrow_account = models.ForeignKey(
        'financial.ChartOfAccounts',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='escrow_real_estate_projects',
        verbose_name=_('حساب الضمان البنكي (Escrow Account)')
    )
    total_land_area = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي مساحة الأرض (م²)')
    )
    gross_built_area = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي المساحة البنائية (GBA) (م²)')
    )
    start_date = models.DateField(
        verbose_name=_('تاريخ بدء المشروع')
    )
    expected_completion_date = models.DateField(
        verbose_name=_('تاريخ الإنجاز المتوقع')
    )
    actual_completion_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ الإنجاز الفعلي')
    )
    is_archived = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name=_('مؤرشف')
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_real_estate_projects',
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
        verbose_name = _('مشروع عقاري')
        verbose_name_plural = _('المشاريع العقارية')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.code} - {self.name}"
