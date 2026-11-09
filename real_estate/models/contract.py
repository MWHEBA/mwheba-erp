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

    class ContractTaxStructure(models.TextChoices):
        UNIFIED_SPA = 'UNIFIED_SPA', _('عقد موحد شامل التشطيب (خاضع لضريبة التصرفات 2.5%)')
        SPLIT_SPA_FINISHING_ANNEX = 'SPLIT_SPA_FINISHING_ANNEX', _('عقد نصف تشطيب + ملحق أعمال تشطيب مستقل (معفى قانونياً من الـ 2.5%)')

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
    recognized_revenue_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي الإيراد المعترف به تراكمياً')
    )
    installments_settled = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name=_('تم سداد كافة الأقساط بالكامل')
    )

    # الهيكلة الضريبية والتعاقدية للتشطيب والملحقات
    contract_tax_structure = models.CharField(
        max_length=35,
        choices=ContractTaxStructure.choices,
        default=ContractTaxStructure.UNIFIED_SPA,
        verbose_name=_('الهيكلة الضريبية والتعاقدية للتشطيب')
    )
    primary_owner_share = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('100.00'),
        verbose_name=_('نسبة ملكية العميل الرئيسي (%)')
    )
    has_decoupled_finishing = models.BooleanField(
        default=False,
        verbose_name=_('فصل مالي وتعاقدي لأعمال التشطيب')
    )
    base_unit_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('القيمة البيعية للوحدة بدون تشطيب')
    )
    finishing_meter_rate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('سعر متر التشطيب')
    )
    finishing_total_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي سعر التشطيب')
    )
    utilities_deposit_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('أمانات رسوم المرافق والصيانة')
    )
    parking_slot_code = models.CharField(
        max_length=50,
        blank=True,
        default='',
        verbose_name=_('كود بايكة الجراج')
    )
    parking_slot_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('سعر الجراج')
    )
    storage_locker_code = models.CharField(
        max_length=50,
        blank=True,
        default='',
        verbose_name=_('كود المخزن السريع')
    )
    storage_locker_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('سعر المخزن')
    )
    call_specialist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='contracts_as_call_rep',
        verbose_name=_('مسئول الاتصال')
    )
    visit_specialist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='contracts_as_visit_rep',
        verbose_name=_('مسئول المقابلة/الزيارة')
    )
    site_specialist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='contracts_as_site_rep',
        verbose_name=_('مسئول الموقع/المعرض')
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'revenue_recognition_method' not in kwargs and not self.pk and self.project_id:
            try:
                from real_estate.models.project import RealEstateProject
                if self.project.revenue_recognition_method == RealEstateProject.RevenueRecognitionMethod.OVER_TIME_POC:
                    self.revenue_recognition_method = self.RevenueMethod.OVER_TIME
            except Exception:
                pass

    def validate_ownership_integrity(self):
        """التحقق من أن مجموع نسب الملكية للعميل الرئيسي والشركاء يساوي 100% بالضبط"""
        if not self.pk:
            return
        co_owners_total = self.co_owners.aggregate(total=models.Sum('share_percentage'))['total'] or Decimal('0.00')
        total_share = self.primary_owner_share + co_owners_total
        if total_share != Decimal('100.00'):
            raise ValidationError(
                _("إجمالي نسب الملكية في العقد يجب أن يساوي 100.00%% بالضبط (المالك الرئيسي: %(p)s%% + الشركاء: %(c)s%% = %(t)s%%).") % {
                    'p': self.primary_owner_share,
                    'c': co_owners_total,
                    't': total_share
                }
            )

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

        if self.pk and (self.co_owners.exists() or self.primary_owner_share != Decimal('100.00')):
            self.validate_ownership_integrity()

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
    class RelationshipType(models.TextChoices):
        SPOUSE = 'SPOUSE', _('زوج / زوجة')
        SIBLING = 'SIBLING', _('أخ / أخت')
        PARENT_CHILD = 'PARENT_CHILD', _('أب / أم / ابن')
        BUSINESS_PARTNER = 'BUSINESS_PARTNER', _('شريك تجاري / استثماري')
        LEGAL_AGENT = 'LEGAL_AGENT', _('وكيل قانوني مفوض')
        OTHER = 'OTHER', _('أخرى')

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
    relationship = models.CharField(
        max_length=30,
        choices=RelationshipType.choices,
        default=RelationshipType.BUSINESS_PARTNER,
        verbose_name=_('صلة القرابة / الصفة التعاقدية')
    )
    notes = models.TextField(
        blank=True,
        default='',
        verbose_name=_('ملاحظات الشريك المتضامن')
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

    def save(self, *args, **kwargs):
        skip_integrity_check = kwargs.pop('skip_integrity_check', False)
        super().save(*args, **kwargs)
        if not skip_integrity_check and self.contract_id:
            contract = self.contract
            co_owners_total = contract.co_owners.aggregate(total=models.Sum('share_percentage'))['total'] or Decimal('0.00')
            if contract.primary_owner_share == Decimal('100.00') and co_owners_total <= Decimal('100.00'):
                contract.primary_owner_share = Decimal('100.00') - co_owners_total
                contract.save(update_fields=['primary_owner_share'])
            contract.validate_ownership_integrity()

    def delete(self, *args, **kwargs):
        skip_integrity_check = kwargs.pop('skip_integrity_check', False)
        contract = self.contract
        super().delete(*args, **kwargs)
        if not skip_integrity_check and contract:
            co_owners_total = contract.co_owners.aggregate(total=models.Sum('share_percentage'))['total'] or Decimal('0.00')
            if co_owners_total == Decimal('0.00'):
                contract.primary_owner_share = Decimal('100.00')
                contract.save(update_fields=['primary_owner_share'])
            contract.validate_ownership_integrity()

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


class MilestoneInstallmentLink(models.Model):
    """
    جسر ربط أقساط عقود بيع الوحدات بمحطات الإنجاز الميدانية (Milestone Installment Link)
    يربط قسط محدد في خطة تقسيط العقد بنشاط محطة رئيسية (Milestone) في مقايسة المشروع WBS.
    """
    contract = models.ForeignKey(
        PropertyContract,
        on_delete=models.CASCADE,
        related_name='milestone_installment_links',
        verbose_name=_('العقد العقاري')
    )
    installment_item = models.ForeignKey(
        'sale.InstallmentItem',
        on_delete=models.CASCADE,
        related_name='milestone_links',
        verbose_name=_('قسط التقسيط المربوط')
    )
    milestone_activity = models.ForeignKey(
        'real_estate.ProjectActivity',
        on_delete=models.PROTECT,
        related_name='milestone_installment_links',
        verbose_name=_('محطة الإنجاز الهندسية (Milestone)')
    )
    is_triggered = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name=_('تم استحقاق القسط بتحقيق المحطة')
    )
    triggered_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ وتوقيت تفعيل الاستحقاق')
    )
    notes = models.TextField(
        blank=True,
        default='',
        verbose_name=_('ملاحظات الربط الهندسي والتعاقدي')
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
        verbose_name = _('رابط قسط بمحطة إنجاز')
        verbose_name_plural = _('روابط أقساط محطات الإنجاز')
        ordering = ['contract', 'installment_item__installment_number', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['contract', 'installment_item', 'milestone_activity'],
                name='uniq_milestone_installment_link'
            )
        ]

    def clean(self):
        super().clean()
        if self.milestone_activity_id and not self.milestone_activity.is_milestone:
            raise ValidationError(_("النشاط المحدد ليس محطة تسليم رئيسية (Milestone)."))
        if self.contract_id and self.milestone_activity_id:
            if self.milestone_activity.project_id != self.contract.project_id:
                raise ValidationError(_("محطة الإنجاز المحددة تنتمي إلى مشروع مختلف عن مشروع العقد."))
        if self.contract_id and self.installment_item_id:
            if self.contract.installment_plan_id != self.installment_item.plan_id:
                raise ValidationError(_("القسط المحدد لا ينتمي إلى خطة التقسيط المعتمدة لهذا العقد."))

    def __str__(self):
        return f"{self.contract.contract_number} - قسط #{self.installment_item.installment_number} -> {self.milestone_activity.name}"


class MilestoneCollectionAlert(models.Model):
    """
    إشعار ومتابعة تحصيل قسط محطة إنجاز (Milestone Collection Alert)
    ينشأ تلقائياً فور وصول محطة الإنجاز الهندسية إلى نسبة 100% لتنبيه فريق التحصيل والمبيعات.
    """
    class AlertStatus(models.TextChoices):
        PENDING = 'PENDING', _('بانتظار المتابعة والتحصيل')
        CONTACTED = 'CONTACTED', _('تم التواصل مع العميل')
        COLLECTED = 'COLLECTED', _('تم التحصيل بنجاح')
        DISPUTED = 'DISPUTED', _('اعتراض من العميل')

    milestone_link = models.ForeignKey(
        MilestoneInstallmentLink,
        on_delete=models.CASCADE,
        related_name='alerts',
        verbose_name=_('رابط القسط والمحطة')
    )
    contract = models.ForeignKey(
        PropertyContract,
        on_delete=models.CASCADE,
        related_name='milestone_alerts',
        verbose_name=_('العقد العقاري')
    )
    customer = models.ForeignKey(
        'customer.Customer',
        on_delete=models.PROTECT,
        related_name='milestone_collection_alerts',
        verbose_name=_('العميل')
    )
    milestone_activity = models.ForeignKey(
        'real_estate.ProjectActivity',
        on_delete=models.PROTECT,
        related_name='collection_alerts',
        verbose_name=_('محطة الإنجاز المحققة')
    )
    installment_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name=_('قيمة القسط المطالب بها')
    )
    due_date = models.DateField(
        verbose_name=_('تاريخ الاستحقاق التعاقدي')
    )
    status = models.CharField(
        max_length=20,
        choices=AlertStatus.choices,
        default=AlertStatus.PENDING,
        db_index=True,
        verbose_name=_('حالة المتابعة والتحصيل')
    )
    action_notes = models.TextField(
        blank=True,
        default='',
        verbose_name=_('ملاحظات وإجراءات فريق التحصيل')
    )
    notified_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('تاريخ وتوقيت إطلاق التنبيه')
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('تاريخ آخر تحديث')
    )

    class Meta:
        verbose_name = _('إشعار تحصيل قسط محطة إنجاز')
        verbose_name_plural = _('إشعارات تحصيل أقساط محطات الإنجاز')
        ordering = ['-notified_at']
        indexes = [
            models.Index(fields=['status', 'notified_at']),
        ]

    def __str__(self):
        return f"تنبيه تحصيل: {self.contract.contract_number} - {self.customer.name} ({self.installment_amount})"

