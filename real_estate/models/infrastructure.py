# -*- coding: utf-8 -*-
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class SharedInfrastructureAsset(models.Model):
    """
    نموذج أصل البنية التحتية المركزية المشتركة (Shared Central Infrastructure Asset)
    (محطات التكييف المركزي، محولات الكهرباء، محطات معالجة المياه، الجراجات الهيدروليكية المركزية)
    """
    class InfrastructureType(models.TextChoices):
        CENTRAL_CHILLERS = 'CENTRAL_CHILLERS', _('محطة تكييف مركزي (Chillers)')
        ELECTRICAL_SUBSTATION = 'ELECTRICAL_SUBSTATION', _('محطة محولات كهربائية موحدة')
        WATER_TREATMENT = 'WATER_TREATMENT', _('محطة تحلية ومعالجة مياه')
        BASEMENT_PARKING = 'BASEMENT_PARKING', _('مجمع جراجات هيدروليكية مركزي')
        POWER_GENERATORS = 'POWER_GENERATORS', _('محطة مولدات طوارئ مركزية')
        OTHER = 'OTHER', _('بنية تحتية خدمية أخرى')

    code = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name=_('كود المحطة / الأصل')
    )
    name = models.CharField(
        max_length=200,
        verbose_name=_('اسم المحطة المركزية')
    )
    compound_name = models.CharField(
        max_length=200,
        blank=True,
        verbose_name=_('اسم المجمع / الكمبوند المشترك')
    )
    infrastructure_type = models.CharField(
        max_length=30,
        choices=InfrastructureType.choices,
        default=InfrastructureType.CENTRAL_CHILLERS,
        verbose_name=_('نوع أصل البنية التحتية')
    )
    total_capacity_load = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي الحمل التصميمي للمحطة')
    )
    capacity_unit = models.CharField(
        max_length=30,
        default='TR',
        verbose_name=_('وحدة القياس (TR / kVA / m³)')
    )
    accumulated_wip_cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي تكاليف الإنشاء المتراكمة (WIP Asset)')
    )
    apportioned_wip_cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('التكاليف الموزعة دفترياً على المشروعات')
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('نشط')
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_infrastructure_assets',
        verbose_name=_('أنشئ بواسطة')
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ الإنشاء'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('تاريخ التحديث'))

    class Meta:
        verbose_name = _('أصل بنية تحتية مشتركة')
        verbose_name_plural = _('أصول البنية التحتية المشتركة')
        ordering = ['code']

    @property
    def remaining_wip_cost(self) -> Decimal:
        """الرصيد المتبقي غير الموزع من تكاليف المحطة"""
        return max(Decimal('0.00'), self.accumulated_wip_cost - self.apportioned_wip_cost)

    def __str__(self):
        return f"{self.code} - {self.name} ({self.get_infrastructure_type_display()})"


class SharedInfrastructureApportionment(models.Model):
    """
    محضر توزيع تكاليف البنية التحتية المركزية على الأبراج والمشروعات المستفيدة
    """
    class AllocationBasis(models.TextChoices):
        SELLABLE_AREA = 'SELLABLE_AREA', _('نسبة المسطحات البيعية (Sellable Area %)')
        CAPACITY_LOAD = 'CAPACITY_LOAD', _('الأحمال التصميمية الهندسية (Capacity Loads %)')

    class ApportionmentStatus(models.TextChoices):
        DRAFT = 'DRAFT', _('مسودة')
        POSTED = 'POSTED', _('مرحل بالدفاتر')
        CANCELLED = 'CANCELLED', _('ملغي')

    apportionment_number = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name=_('رقم محضر التوزيع')
    )
    infrastructure_asset = models.ForeignKey(
        SharedInfrastructureAsset,
        on_delete=models.PROTECT,
        related_name='apportionments',
        verbose_name=_('أصل البنية التحتية')
    )
    apportionment_date = models.DateField(
        default=timezone.now,
        verbose_name=_('تاريخ التوزيع الدفتري')
    )
    allocation_basis = models.CharField(
        max_length=30,
        choices=AllocationBasis.choices,
        default=AllocationBasis.SELLABLE_AREA,
        verbose_name=_('معيار التوزيع المعتمد')
    )
    total_apportioned_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name=_('إجمالي المبلغ الموزع في هذا المحضر')
    )
    status = models.CharField(
        max_length=30,
        choices=ApportionmentStatus.choices,
        default=ApportionmentStatus.DRAFT,
        db_index=True,
        verbose_name=_('حالة المحضر')
    )
    notes = models.TextField(blank=True, verbose_name=_('ملاحظات وتفاصيل التوزيع'))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_infrastructure_apportionments',
        verbose_name=_('أنشئ بواسطة')
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ الإنشاء'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('تاريخ التحديث'))

    class Meta:
        verbose_name = _('محضر توزيع تكاليف بنية تحتية')
        verbose_name_plural = _('محاضر توزيع تكاليف البنية التحتية')
        ordering = ['-apportionment_date', '-id']

    def __str__(self):
        return f"{self.apportionment_number} - {self.infrastructure_asset.name} ({self.total_apportioned_amount} EGP)"


class InfrastructureApportionmentLine(models.Model):
    """
    سطر تفصيلي لتوزيع حصة كل مشروع/برج مستفيد من تكاليف المحطة
    """
    apportionment = models.ForeignKey(
        SharedInfrastructureApportionment,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name=_('محضر التوزيع')
    )
    beneficiary_project = models.ForeignKey(
        'real_estate.RealEstateProject',
        on_delete=models.PROTECT,
        related_name='infrastructure_apportionment_lines',
        verbose_name=_('المشروع / البرج المستفيد')
    )
    metric_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_('قيمة المعيار المعتمد للمشروع (المساحة البيعية م² أو الحمل التصميمي)')
    )
    allocation_percentage = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        verbose_name=_('النسبة المئوية من إجمالي التوزيع (%)')
    )
    allocated_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name=_('المبلغ الموزع على المشروع (ج.م)')
    )

    class Meta:
        verbose_name = _('بند توزيع تكلفة لمشروع')
        verbose_name_plural = _('بنود توزيع التكاليف للمشروعات')
        unique_together = ('apportionment', 'beneficiary_project')

    def __str__(self):
        return f"{self.beneficiary_project.name}: {self.allocated_amount} ({self.allocation_percentage}%)"
