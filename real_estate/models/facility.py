# -*- coding: utf-8 -*-
"""
BuildingFacilitySubledger - دفتر أستاذ مساعد صندوق صيانة المرافق واتحاد الشاغلين
MWHEBA ERP — Real Estate Wave 3 (Phase 11: HOA Maintenance Escrow & Tax-Free Yields)
"""
import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class BuildingFacilitySubledger(models.Model):
    """
    دفتر أستاذ مساعد مخصص لكل مشروع/برج لإدارة صندوق صيانة اتحاد الشاغلين (HOA Trust Fund):
    - عزل كامل لأموال الصيانة في حساب بنكي مقيد (Restricted Cash 11170)
    - إدارة أمانات الملاك المحتجزة (Escrow Trust Liability 21520)
    - عزل تام لعوائد الشهادات البنكية عن قائمة الدخل (Zero P&L Impact) حماية من ضريبة الدخل 22.5%
    """

    project = models.OneToOneField(
        'real_estate.RealEstateProject',
        on_delete=models.PROTECT,
        related_name='facility_subledger',
        verbose_name=_('المشروع العقاري')
    )
    restricted_cash_account = models.ForeignKey(
        'financial.ChartOfAccounts',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='facility_restricted_cash_subledgers',
        verbose_name=_('حساب البنك المقيد لوديعة الصيانة (Restricted Cash)')
    )
    maintenance_escrow_account = models.ForeignKey(
        'financial.ChartOfAccounts',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='facility_escrow_subledgers',
        verbose_name=_('حساب أمانات صندوق الصيانة (Escrow Liability)')
    )

    # أرصدة الصندوق التراكمية
    total_collected_deposits = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي ودائع الصيانة المحصلة من الملاك')
    )
    total_yield_accumulated = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي عوائد الشهادات البنكية المعفاة')
    )
    total_expenses_disbursed = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي مصروفات الصيانة والتشغيل المنصرفة')
    )
    current_fund_balance = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('الرصيد الفعلي الحالي لصندوق الصيانة')
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('نشط')
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_facility_subledgers',
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
        verbose_name = _('دفتر أستاذ صندوق صيانة المشروع')
        verbose_name_plural = _('دفاتر أستاذ صناديق صيانة المشروعات')
        ordering = ['project__code']

    def __str__(self):
        return f"صندوق صيانة {self.project.name} ({self.project.code}) - رصيد: {self.current_fund_balance} ج.م"

    def recalculate_balances(self):
        """
        إعادة احتساب الأرصدة التراكمية والرصيد الصافي المتاح لصندوق الصيانة
        """
        self.current_fund_balance = (
            self.total_collected_deposits
            + self.total_yield_accumulated
            - self.total_expenses_disbursed
        )
        self.save(update_fields=[
            'total_collected_deposits',
            'total_yield_accumulated',
            'total_expenses_disbursed',
            'current_fund_balance',
            'updated_at'
        ])


class MaintenanceFundOperation(models.Model):
    """
    حركات وعمليات صندوق صيانة المرافق واتحاد الشاغلين
    """

    class OperationType(models.TextChoices):
        DEPOSIT_COLLECTION = 'DEPOSIT_COLLECTION', _('تحصيل وديعة صيانة تعاقدية من مشتري')
        BANK_YIELD = 'BANK_YIELD', _('عائد شهادات وودائع بنكية معفاة (أمانات)')
        FACILITY_EXPENSE = 'FACILITY_EXPENSE', _('مصروف تشغيلي وصيانة مرافق')
        SUPPLEMENTAL_LEVY = 'SUPPLEMENTAL_LEVY', _('مطالبة فروق صيانة سنوية استثنائية (عجز)')

    class ExpenseCategory(models.TextChoices):
        ELEVATOR = 'ELEVATOR', _('صيانة دورية وإصلاح المصاعد')
        SECURITY = 'SECURITY', _('خدمات الحراسة والأمن والمراقبة')
        CLEANING = 'CLEANING', _('خدمات النظافة وإدارة المخلفات')
        ELECTRICITY = 'ELECTRICITY', _('كهرباء وإنارة المداخل والممرات العامة')
        LANDSCAPING = 'LANDSCAPING', _('صيانة المساحات الخضراء والري')
        FACILITY_MANAGEMENT = 'FACILITY_MANAGEMENT', _('أتعاب شركة إدارة المرافق')
        OTHER = 'OTHER', _('مصروفات ومستلزمات صيانة أخرى')

    operation_number = models.CharField(
        max_length=60,
        unique=True,
        db_index=True,
        blank=True,
        verbose_name=_('رقم حركة الصيانة')
    )
    subledger = models.ForeignKey(
        BuildingFacilitySubledger,
        on_delete=models.PROTECT,
        related_name='operations',
        verbose_name=_('دفتر أستاذ الصيانة')
    )
    operation_type = models.CharField(
        max_length=30,
        choices=OperationType.choices,
        db_index=True,
        verbose_name=_('نوع العملية')
    )
    operation_date = models.DateField(
        default=timezone.localdate,
        verbose_name=_('تاريخ العملية')
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name=_('المبلغ')
    )
    contract = models.ForeignKey(
        'real_estate.PropertyContract',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='maintenance_operations',
        verbose_name=_('عقد الوحدة المرتبط (إن وجد)')
    )
    unit = models.ForeignKey(
        'real_estate.PropertyUnit',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='maintenance_operations',
        verbose_name=_('الوحدة العقارية (إن وجدت)')
    )
    expense_category = models.CharField(
        max_length=50,
        blank=True,
        choices=ExpenseCategory.choices,
        verbose_name=_('تصنيف المصروف التشغيلي')
    )
    bank_certificate_number = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_('رقم الشهادة / الوديعة البنكية')
    )
    yield_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('نسبة العائد السنوي (%)')
    )
    period_start = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('بداية الفترة')
    )
    period_end = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('نهاية الفترة')
    )
    description = models.TextField(
        blank=True,
        verbose_name=_('البيان والتفاصيل')
    )
    journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='facility_operations',
        verbose_name=_('القيد المحاسبي')
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_facility_operations',
        verbose_name=_('سجل بواسطة')
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
        verbose_name = _('حركة صندوق صيانة')
        verbose_name_plural = _('حركات صندوق الصيانة')
        ordering = ['-operation_date', '-id']

    def __str__(self):
        return f"{self.operation_number or 'MNT-DRAFT'} ({self.get_operation_type_display()}): {self.amount} ج.م"

    def save(self, *args, **kwargs):
        if not self.operation_number:
            prefix = "MNT"
            if self.operation_type == self.OperationType.BANK_YIELD:
                prefix = "YLD"
            elif self.operation_type == self.OperationType.FACILITY_EXPENSE:
                prefix = "EXP"
            elif self.operation_type == self.OperationType.SUPPLEMENTAL_LEVY:
                prefix = "LVY"
            self.operation_number = f"{prefix}-{self.subledger.project.code}-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)


class SupplementalLevyApportionment(models.Model):
    """
    توزيع ومطالبة فروق الصيانة السنوية (العجز) على ملاك الوحدات بنسبة المساحة
    """

    operation = models.ForeignKey(
        MaintenanceFundOperation,
        on_delete=models.CASCADE,
        related_name='apportionments',
        verbose_name=_('حركة العجز السنوي')
    )
    unit = models.ForeignKey(
        'real_estate.PropertyUnit',
        on_delete=models.PROTECT,
        related_name='maintenance_levy_apportionments',
        verbose_name=_('الوحدة العقارية')
    )
    contract = models.ForeignKey(
        'real_estate.PropertyContract',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='maintenance_levy_apportionments',
        verbose_name=_('العقد العقاري')
    )
    customer = models.ForeignKey(
        'customer.Customer',
        on_delete=models.PROTECT,
        related_name='maintenance_levy_apportionments',
        verbose_name=_('المالك / الشاغل')
    )
    unit_gross_area = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_('المساحة الإجمالية للوحدة (م²)')
    )
    share_percentage = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        verbose_name=_('نسبة المساهمة في العجز (%)')
    )
    apportioned_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_('المبلغ المطالب به')
    )
    is_settled = models.BooleanField(
        default=False,
        verbose_name=_('تم السداد')
    )
    settled_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ السداد')
    )
    receipt_reference = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_('رقم سند التحصيل')
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
        verbose_name = _('توزيع مطالبة فروق صيانة')
        verbose_name_plural = _('توزيعات مطالبات فروق الصيانة')
        ordering = ['-operation__operation_date', 'unit__unit_code']

    def __str__(self):
        return f"مطالبة {self.unit.unit_code} - {self.customer.name}: {self.apportioned_amount} ج.م"
