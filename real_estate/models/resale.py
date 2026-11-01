# -*- coding: utf-8 -*-
import hashlib
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class UnitSwapRecord(models.Model):
    """
    سجل ومحضر استبدال وترقية/تخفيض الوحدة العقارية (Unit Swap Record)
    يوثق الانتقال من الوحدة القديمة إلى الجديدة، فارق السعر، رسوم الاستبدال الإدارية، وإعادة جدولة الأقساط
    """
    class SwapStatus(models.TextChoices):
        DRAFT = 'DRAFT', _('مسودة')
        UNDER_APPROVAL = 'UNDER_APPROVAL', _('قيد المراجعة والاعتماد')
        EXECUTED = 'EXECUTED', _('منفذ ومرحل دفترياً')
        CANCELLED = 'CANCELLED', _('ملغي')

    class SettlementMethod(models.TextChoices):
        RE_AMORTIZE_EXISTING = 'RE_AMORTIZE_EXISTING', _('إعادة جدولة الفارق على الأقساط المتبقية')
        NEW_INSTALLMENT_PLAN = 'NEW_INSTALLMENT_PLAN', _('إصدار خطة أقساط جديدة مستقلة')
        CASH_SETTLEMENT = 'CASH_SETTLEMENT', _('سداد الفارق نقداً / دفعة واحدة')

    swap_number = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name=_('رقم محضر الاستبدال')
    )
    contract = models.ForeignKey(
        'real_estate.PropertyContract',
        on_delete=models.PROTECT,
        related_name='swap_records',
        verbose_name=_('العقد العقاري')
    )
    customer = models.ForeignKey(
        'customer.Customer',
        on_delete=models.PROTECT,
        related_name='unit_swaps',
        verbose_name=_('العميل')
    )
    old_unit = models.ForeignKey(
        'real_estate.PropertyUnit',
        on_delete=models.PROTECT,
        related_name='swaps_as_old_unit',
        verbose_name=_('الوحدة السابقة المستبدلة')
    )
    new_unit = models.ForeignKey(
        'real_estate.PropertyUnit',
        on_delete=models.PROTECT,
        related_name='swaps_as_new_unit',
        verbose_name=_('الوحدة الجديدة البديلة')
    )
    swap_date = models.DateField(
        default=timezone.now,
        verbose_name=_('تاريخ الاستبدال')
    )
    status = models.CharField(
        max_length=30,
        choices=SwapStatus.choices,
        default=SwapStatus.DRAFT,
        db_index=True,
        verbose_name=_('حالة محضر الاستبدال')
    )
    old_unit_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name=_('سعر الوحدة القديمة')
    )
    new_unit_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name=_('سعر الوحدة الجديدة البديلة')
    )
    price_difference = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('فارق السعر (ترقية / تخفيض)')
    )
    administrative_fee = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('رسوم الاستبدال الإدارية')
    )
    settlement_method = models.CharField(
        max_length=30,
        choices=SettlementMethod.choices,
        default=SettlementMethod.RE_AMORTIZE_EXISTING,
        verbose_name=_('طريقة تسوية الفارق المالي')
    )
    notes = models.TextField(
        blank=True,
        verbose_name=_('ملاحظات وأسباب الاستبدال')
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_unit_swaps',
        verbose_name=_('أنشئ بواسطة')
    )
    executed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ وساعة التنفيذ')
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
        verbose_name = _('محضر استبدال وترقية وحدة')
        verbose_name_plural = _('محاضر استبدال وترقية الوحدات')
        ordering = ['-swap_date', '-id']

    def clean(self):
        super().clean()
        if self.old_unit_id and self.new_unit_id and self.old_unit_id == self.new_unit_id:
            raise ValidationError(_("لا يمكن استبدال الوحدة بنفسها."))

        if self.contract_id and self.old_unit_id and self.contract.unit_id != self.old_unit_id:
            raise ValidationError(_("الوحدة السابقة المحددة لا تطابق الوحدة المربوطة بالعقد العقاري."))

    def save(self, *args, **kwargs):
        if self.new_unit_price is not None and self.old_unit_price is not None:
            self.price_difference = self.new_unit_price - self.old_unit_price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.swap_number} - {self.old_unit.unit_code} ➔ {self.new_unit.unit_code} ({self.get_status_display()})"


class ContractAssignmentEndorsement(models.Model):
    """
    ملحق تنازل ونقل ملكية العقد العقاري للغير (Contract Assignment Endorsement)
    يوثق التنازل الرسمي، نقل الالتزامات والأقساط، رسوم التنازل الإدارية، وبصمة التحقق القانونية SHA-256
    """
    class AssignmentStatus(models.TextChoices):
        DRAFT = 'DRAFT', _('مسودة')
        UNDER_APPROVAL = 'UNDER_APPROVAL', _('قيد المراجعة القانونية والمالية')
        APPROVED = 'APPROVED', _('معتمد')
        EXECUTED = 'EXECUTED', _('منفذ ومرحل دفترياً')
        REJECTED = 'REJECTED', _('مرفوض')
        CANCELLED = 'CANCELLED', _('ملغي')

    class FeePayer(models.TextChoices):
        ASSIGNOR = 'ASSIGNOR', _('المتنازل (العميل الأصلي)')
        ASSIGNEE = 'ASSIGNEE', _('المتنازل إليه (المشتري الجديد)')
        SHARED_EQUAL = 'SHARED_EQUAL', _('مناصفة بين الطرفين')

    assignment_number = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name=_('رقم ملحق التنازل')
    )
    contract = models.ForeignKey(
        'real_estate.PropertyContract',
        on_delete=models.PROTECT,
        related_name='assignment_endorsements',
        verbose_name=_('العقد العقاري')
    )
    assignor_customer = models.ForeignKey(
        'customer.Customer',
        on_delete=models.PROTECT,
        related_name='assignments_as_assignor',
        verbose_name=_('العميل المتنازل (البائع الأصلي)')
    )
    assignee_customer = models.ForeignKey(
        'customer.Customer',
        on_delete=models.PROTECT,
        related_name='assignments_as_assignee',
        verbose_name=_('العميل المتنازل إليه (المشتري الجديد)')
    )
    assignment_date = models.DateField(
        default=timezone.now,
        verbose_name=_('تاريخ التنازل')
    )
    status = models.CharField(
        max_length=30,
        choices=AssignmentStatus.choices,
        default=AssignmentStatus.DRAFT,
        db_index=True,
        verbose_name=_('حالة طلب التنازل')
    )
    original_contract_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name=_('القيمة الإجمالية للعقد الأصلي')
    )
    paid_amount_at_assignment = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي المبالغ المسددة المنقولة للمتنازل إليه')
    )
    remaining_balance_at_assignment = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('الرصيد المتبقي على المتنازل إليه')
    )
    resale_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_('سعر التنازل المتفق عليه بين الطرفين')
    )
    administrative_fee_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('2.50'),
        verbose_name=_('نسبة رسوم التنازل الإدارية (%)')
    )
    administrative_fee = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('قيمة رسوم التنازل الإدارية')
    )
    fee_payer = models.CharField(
        max_length=20,
        choices=FeePayer.choices,
        default=FeePayer.ASSIGNOR,
        verbose_name=_('الطرف الملزم برسوم التنازل')
    )
    verification_token = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        verbose_name=_('رمز البصمة الرقمية للتحقق (SHA-256)')
    )
    notes = models.TextField(
        blank=True,
        verbose_name=_('ملاحظات واعتمادات الشؤون القانونية')
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_contract_assignments',
        verbose_name=_('أنشئ بواسطة')
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_contract_assignments',
        verbose_name=_('معتمد من')
    )
    executed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ وساعة التنفيذ')
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
        verbose_name = _('ملحق تنازل ونقل ملكية')
        verbose_name_plural = _('ملاحق التنازل ونقل الملكية')
        ordering = ['-assignment_date', '-id']

    def clean(self):
        super().clean()
        if self.assignor_customer_id and self.assignee_customer_id and self.assignor_customer_id == self.assignee_customer_id:
            raise ValidationError(_("لا يجوز التنازل لنفس العميل المشتري الأصلي."))

        if self.contract_id and self.assignor_customer_id and self.contract.customer_id != self.assignor_customer_id:
            raise ValidationError(_("العميل المتنازل لا يطابق المشتري الأصلي المقيد بالعقد."))

    def generate_verification_token(self) -> str:
        """توليد بصمة SHA-256 فريدة مانعة للتزوير"""
        raw = f"{self.contract_id}:{self.assignor_customer_id}:{self.assignee_customer_id}:{self.paid_amount_at_assignment}:{self.administrative_fee}:{self.assignment_date}"
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()

    def save(self, *args, **kwargs):
        if not self.verification_token:
            self.verification_token = self.generate_verification_token()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.assignment_number} - {self.contract.contract_number} ({self.assignor_customer.name} ➔ {self.assignee_customer.name})"
