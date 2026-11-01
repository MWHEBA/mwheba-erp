# -*- coding: utf-8 -*-
from decimal import Decimal
from django.db import models, transaction
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class PropertyContract(models.Model):
    """
    نموذج العقد العقاري النهائي لبيع الوحدات (Sales & Purchase Agreement - SPA)
    يربط الوحدة بالعميل وخطة الأقساط المستقلة ويحدد معايير الاعتراف بالإيراد وفق IFRS 15
    """
    class ContractStatus(models.TextChoices):
        DRAFT = 'DRAFT', _('مسودة')
        UNDER_APPROVAL = 'UNDER_APPROVAL', _('قيد المراجعة والاعتماد')
        ACTIVE = 'ACTIVE', _('ساري ومبرم')
        SUSPENDED = 'SUSPENDED', _('معلق مؤقتاً')
        TERMINATED = 'TERMINATED', _('مفسوخ')
        COMPLETED = 'COMPLETED', _('منتهٍ بالتسليم والمخالصة التامة')

    class RevenueMethod(models.TextChoices):
        POINT_IN_TIME = 'POINT_IN_TIME', _('عند التسليم ونقل السيطرة الفورية (Point in Time)')
        OVER_TIME = 'OVER_TIME', _('على مدار مدة الإنشاء بنسبة الإنجاز (Over Time - POC)')

    contract_number = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name=_('رقم العقد')
    )
    project = models.ForeignKey(
        'real_estate.RealEstateProject',
        on_delete=models.PROTECT,
        related_name='contracts',
        verbose_name=_('المشروع')
    )
    unit = models.ForeignKey(
        'real_estate.PropertyUnit',
        on_delete=models.PROTECT,
        related_name='contracts',
        verbose_name=_('الوحدة العقارية')
    )
    customer = models.ForeignKey(
        'customer.Customer',
        on_delete=models.PROTECT,
        related_name='property_contracts',
        verbose_name=_('العميل المشتري الرئيسي')
    )
    installment_plan = models.OneToOneField(
        'sale.InstallmentPlan',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='property_contract',
        verbose_name=_('خطة الأقساط المرتبطة')
    )
    status = models.CharField(
        max_length=30,
        choices=ContractStatus.choices,
        default=ContractStatus.DRAFT,
        db_index=True,
        verbose_name=_('حالة العقد')
    )
    contract_date = models.DateField(
        verbose_name=_('تاريخ تحرير العقد')
    )
    delivery_date = models.DateField(
        verbose_name=_('تاريخ التسليم التعاقدي')
    )
    final_contract_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name=_('إجمالي القيمة البيعية التعاقدية')
    )
    down_payment = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('مقدم التعاقد المسدد')
    )
    currency = models.ForeignKey(
        'financial.Currency',
        on_delete=models.PROTECT,
        related_name='property_contracts',
        verbose_name=_('عملة العقد')
    )
    exchange_rate = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        default=Decimal('1.000000'),
        verbose_name=_('سعر صرف العملة')
    )
    revenue_recognition_method = models.CharField(
        max_length=30,
        choices=RevenueMethod.choices,
        default=RevenueMethod.POINT_IN_TIME,
        verbose_name=_('طريقة الاعتراف بالإيراد (IFRS 15)')
    )
    installments_settled = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name=_('تم سداد كافة الأقساط بالكامل')
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_property_contracts',
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
        verbose_name = _('عقد عقاري')
        verbose_name_plural = _('العقود العقارية')
        ordering = ['-contract_date', '-id']
        constraints = [
            models.CheckConstraint(
                check=models.Q(final_contract_price__gt=0),
                name='chk_contract_price_positive'
            ),
            models.CheckConstraint(
                check=models.Q(down_payment__gte=0) & models.Q(down_payment__lte=models.F('final_contract_price')),
                name='chk_contract_down_payment_valid'
            ),
            models.UniqueConstraint(
                fields=['unit'],
                condition=models.Q(status__in=['ACTIVE', 'COMPLETED', 'UNDER_APPROVAL']),
                name='uniq_active_contract_per_unit'
            ),
        ]

    def on_installments_completed(self):
        """
        يستدعى تلقائياً من محرك الأقساط عند إتمام سداد كامل قيمة الخطة
        """
        self.installments_settled = True
        self.save(update_fields=['installments_settled', 'updated_at'])

    def clean(self):
        super().clean()
        if self.unit_id and self.project_id and self.unit.project_id != self.project_id:
            raise ValidationError(_("الوحدة العقارية المحددة لا تنتمي إلى هذا المشروع."))

        if self.unit_id and self.unit.status == self.unit.UnitStatus.LANDOWNER_ALLOCATED:
            raise ValidationError(
                _("لا يمكن إبرام تعاقد بيع على هذه الوحدة نظراً لأنها مخصصة لمالك الأرض ضمن اتفاقية المشاركة (LANDOWNER_ALLOCATED).")
            )

        if self.unit_id and self.status in [
            self.ContractStatus.ACTIVE,
            self.ContractStatus.COMPLETED,
            self.ContractStatus.UNDER_APPROVAL
        ]:
            active_conflict = PropertyContract.objects.filter(
                unit_id=self.unit_id,
                status__in=[self.ContractStatus.ACTIVE, self.ContractStatus.COMPLETED, self.ContractStatus.UNDER_APPROVAL]
            ).exclude(pk=self.pk)
            if active_conflict.exists():
                conflict = active_conflict.first()
                raise ValidationError(
                    _("الوحدة العقارية %(unit_code)s مرتبطة بالفعل بعقد نشط آخر (عقد رقم %(contract_num)s).") % {
                        'unit_code': self.unit.unit_code,
                        'contract_num': conflict.contract_number
                    }
                )

        if self.installment_plan_id:
            from sale.services.contract_installment_binding_service import ContractInstallmentBindingService
            ContractInstallmentBindingService.validate_plan_ownership(
                contract=self,
                target_plan=self.installment_plan
            )

    @transaction.atomic
    def save(self, *args, **kwargs):
        # 1. التحقق الاستباقي الصارم من تطابق ملكية خطة التقسيط وحظر تبديل خطة سارية
        if self.pk:
            old_contract = PropertyContract.objects.filter(pk=self.pk).only('installment_plan_id').first()
            if old_contract:
                old_plan_id = old_contract.installment_plan_id
                new_plan_id = self.installment_plan_id
                if old_plan_id != new_plan_id:
                    from sale.services.contract_installment_binding_service import ContractInstallmentBindingService
                    ContractInstallmentBindingService.validate_plan_switch(
                        contract=self,
                        old_plan_id=old_plan_id,
                        new_plan=self.installment_plan
                    )
        elif self.installment_plan_id:
            from sale.services.contract_installment_binding_service import ContractInstallmentBindingService
            ContractInstallmentBindingService.validate_plan_ownership(
                contract=self,
                target_plan=self.installment_plan
            )

        # 2. قفل حقيقي للصف select_for_update().get(...) داخل المعاملة الذرية لحماية التزامن على كافة المحركات
        if self.status in [self.ContractStatus.ACTIVE, self.ContractStatus.COMPLETED, self.ContractStatus.UNDER_APPROVAL]:
            if self.unit_id:
                from real_estate.models.unit import PropertyUnit
                locked_unit = PropertyUnit.objects.select_for_update().get(id=self.unit_id)
                active_conflict = PropertyContract.objects.filter(
                    unit_id=self.unit_id,
                    status__in=[self.ContractStatus.ACTIVE, self.ContractStatus.COMPLETED, self.ContractStatus.UNDER_APPROVAL]
                ).exclude(pk=self.pk)
                if active_conflict.exists():
                    conflict = active_conflict.first()
                    raise ValidationError(
                        _("الوحدة العقارية %(unit_code)s مرتبطة بالفعل بعقد نشط آخر (عقد رقم %(contract_num)s).") % {
                            'unit_code': locked_unit.unit_code,
                            'contract_num': conflict.contract_number
                        }
                    )

        super().save(*args, **kwargs)

        # 3. ربط خطة التقسيط بالعقد بحوكمة تامة
        if self.installment_plan_id:
            from sale.services.contract_installment_binding_service import ContractInstallmentBindingService
            ContractInstallmentBindingService.bind_contract_to_plan(
                contract=self,
                target_plan=self.installment_plan,
                user=self.created_by
            )

        # 4. تحديث حالة الوحدة إلى CONTRACTED إذا أصبح العقد نشطاً
        if self.status == self.ContractStatus.ACTIVE and self.unit.status != self.unit.UnitStatus.CONTRACTED:
            self.unit.status = self.unit.UnitStatus.CONTRACTED
            self.unit.status_version += 1
            self.unit.save(update_fields=['status', 'status_version'])

    def __str__(self):
        return f"{self.contract_number} - {self.unit.unit_code} - {self.customer.name}"


class ContractCoOwner(models.Model):
    """
    نموذج الشركاء في ملكية الوحدة والضامنين المتضامنين في العقد (Co-Owners & Guarantors)
    """
    contract = models.ForeignKey(
        PropertyContract,
        on_delete=models.CASCADE,
        related_name='co_owners',
        verbose_name=_('العقد العقاري')
    )
    co_owner = models.ForeignKey(
        'customer.Customer',
        on_delete=models.PROTECT,
        related_name='co_owned_contracts',
        verbose_name=_('الشريك / المالك المتضامن')
    )
    share_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name=_('نسبة الملكية في الوحدة (%)')
    )
    is_joint_and_several_guarantor = models.BooleanField(
        default=True,
        verbose_name=_('ضامن متضامن في سداد كامل المستحقات')
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('تاريخ الإضافة')
    )

    class Meta:
        verbose_name = _('شريك في ملكية الوحدة')
        verbose_name_plural = _('الشركاء والضامنون في العقد')
        ordering = ['contract', '-share_percentage']
        constraints = [
            models.UniqueConstraint(
                fields=['contract', 'co_owner'],
                name='uniq_contract_co_owner'
            ),
            models.CheckConstraint(
                check=models.Q(share_percentage__gt=0) & models.Q(share_percentage__lte=Decimal('100.00')),
                name='chk_co_owner_share_range'
            )
        ]

    def __str__(self):
        return f"{self.contract.contract_number} - {self.co_owner.name} ({self.share_percentage}%)"


class ContractPaymentReceipt(models.Model):
    """
    سجل ربط إيصالات وسندات تحصيل العملاء بالعقد العقاري وقسط التقسيط
    (Loose Coupling Architecture: Real Estate module holds the foreign link to CustomerPayment)
    """
    contract = models.ForeignKey(
        'real_estate.PropertyContract',
        on_delete=models.CASCADE,
        related_name='payment_receipts',
        verbose_name=_('العقد العقاري')
    )
    customer_payment = models.ForeignKey(
        'customer.CustomerPayment',
        on_delete=models.CASCADE,
        related_name='contract_receipts',
        verbose_name=_('إيصال دفعة العميل')
    )
    installment_item = models.ForeignKey(
        'sale.InstallmentItem',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contract_receipts',
        verbose_name=_('قسط التقسيط')
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('تاريخ الإنشاء')
    )

    class Meta:
        verbose_name = _('إيصال سداد العقد العقاري')
        verbose_name_plural = _('إيصالات سداد العقود العقارية')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.contract.contract_number} - Payment #{self.customer_payment_id}"
