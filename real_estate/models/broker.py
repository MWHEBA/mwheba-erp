# -*- coding: utf-8 -*-
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class RealEstateBroker(models.Model):
    """
    نموذج شركة التسويق العقاري أو الوسيط العقاري المستقل (Brokerage Agency / Independent Broker)
    (Wave 2 Phase 5: Broker Management Engine)
    """
    class BrokerType(models.TextChoices):
        AGENCY = 'AGENCY', _('شركة وساطة وتسويق عقاري')
        INDIVIDUAL = 'INDIVIDUAL', _('مسوق حر / وسيط مستقل')
        EMPLOYEE_REFERRAL = 'EMPLOYEE_REFERRAL', _('مندوب / ترشيح موظف داخلي')

    code = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name=_('كود الوسيط')
    )
    name = models.CharField(
        max_length=200,
        verbose_name=_('اسم الشركة / الوسيط')
    )
    broker_type = models.CharField(
        max_length=30,
        choices=BrokerType.choices,
        default=BrokerType.AGENCY,
        verbose_name=_('نوع الوسيط')
    )
    commercial_registration = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_('رقم السجل التجاري')
    )
    tax_id = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_('رقم البطاقة الضريبية')
    )
    phone = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_('رقم الهاتف')
    )
    email = models.EmailField(
        blank=True,
        verbose_name=_('البريد الإلكتروني')
    )
    contact_person = models.CharField(
        max_length=150,
        blank=True,
        verbose_name=_('الشخص المسؤول للتنسيق')
    )
    default_commission_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('2.50'),
        verbose_name=_('نسبة العمولة الافتراضية (%)')
    )
    financial_account = models.ForeignKey(
        'financial.ChartOfAccounts',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='estate_brokers',
        verbose_name=_('حساب الأستاذ المساعد للوسيط (Broker Payable)')
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('نشط ومعتمد')
    )
    notes = models.TextField(
        blank=True,
        verbose_name=_('ملاحظات وسجل التعاملات')
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_real_estate_brokers',
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
        verbose_name = _('وسيط عقاري')
        verbose_name_plural = _('الوسطاء وشركات التسويق العقاري')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code}) - {self.get_broker_type_display()}"


class BrokerCommission(models.Model):
    """
    نموذج استحقاق وصرف عمولة الوسيط العقاري المرتبطة بالعقد (Staged 50/50 Release & Clawback)
    """
    class TrancheStatus(models.TextChoices):
        PENDING = 'PENDING', _('معلقة لحين استيفاء شرط الصرف')
        ELIGIBLE = 'ELIGIBLE', _('مستحقة الصرف وجاهزة للاعتماد')
        PAID = 'PAID', _('تم الصرف الفعلي')
        CANCELLED = 'CANCELLED', _('ملغاة')

    class ClawbackStatus(models.TextChoices):
        NONE = 'NONE', _('لا يوجد استرداد')
        PENDING = 'PENDING', _('استرداد معلق قيد التسوية')
        CLAWED_BACK = 'CLAWED_BACK', _('تم استرداد العمولة أو حجزها')

    contract = models.ForeignKey(
        'real_estate.PropertyContract',
        on_delete=models.PROTECT,
        related_name='broker_commissions',
        verbose_name=_('العقد العقاري المرتبط')
    )
    broker = models.ForeignKey(
        RealEstateBroker,
        on_delete=models.PROTECT,
        related_name='commissions',
        verbose_name=_('الوسيط المستحق')
    )
    commission_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name=_('نسبة العمولة المطبقة (%)')
    )
    total_commission_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_('إجمالي مبلغ العمولة المستحقة')
    )

    # الشريحة الأولى (50% عند تحصيل الدفعة المقدمة >= 10%)
    staged_tranche_1_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_('مبلغ الشريحة الأولى (50% مقدم تعاقد)')
    )
    tranche_1_status = models.CharField(
        max_length=20,
        choices=TrancheStatus.choices,
        default=TrancheStatus.PENDING,
        verbose_name=_('حالة الشريحة الأولى')
    )
    tranche_1_paid_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ صرف الشريحة الأولى')
    )
    tranche_1_paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
        verbose_name=_('المسؤول المعتمد لصرف الشريحة الأولى')
    )
    tranche_1_journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
        verbose_name=_('قيد صرف الشريحة الأولى')
    )

    # الشريحة الثانية (50% بعد تحصيل أول قسطين دوريين)
    staged_tranche_2_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_('مبلغ الشريحة الثانية (50% بعد قسطين)')
    )
    tranche_2_status = models.CharField(
        max_length=20,
        choices=TrancheStatus.choices,
        default=TrancheStatus.PENDING,
        verbose_name=_('حالة الشريحة الثانية')
    )
    tranche_2_paid_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ صرف الشريحة الثانية')
    )
    tranche_2_paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
        verbose_name=_('المسؤول المعتمد لصرف الشريحة الثانية')
    )
    tranche_2_journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
        verbose_name=_('قيد صرف الشريحة الثانية')
    )

    # منظومة الاسترداد الآلي (Commission Clawback)
    clawback_status = models.CharField(
        max_length=20,
        choices=ClawbackStatus.choices,
        default=ClawbackStatus.NONE,
        verbose_name=_('حالة استرداد العمولة')
    )
    clawback_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('المبلغ المسترد / المحجوز')
    )
    clawback_reason = models.TextField(
        blank=True,
        verbose_name=_('سبب الاسترداد (فسخ عقد / ارتداد شيك)')
    )
    clawback_journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
        verbose_name=_('قيد استرداد العمولة')
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
        verbose_name = _('عمولة وسيط عقاري')
        verbose_name_plural = _('عمولات الوسطاء العقاريين')
        ordering = ['-created_at']

    def __str__(self):
        return f"عمولة {self.broker.name} - عقد {self.contract.contract_number} ({self.total_commission_amount} ج.م)"


class BrokerAttributionAudit(models.Model):
    """
    نموذج توثيق بصمة أسبقية ومصدر العميل (Lead Attribution Lock)
    يحمي الشركة من التواطؤ الداخلي لسرقة العمولات على عملاء الإعلانات المباشرة
    """
    class LeadSource(models.TextChoices):
        DIRECT_WALK_IN = 'DIRECT_WALK_IN', _('زيارة مباشرة للمقر (Direct Walk-in)')
        COMPANY_CAMPAIGN = 'COMPANY_CAMPAIGN', _('حملات إعلانات الشركة الرقمية المباشرة')
        WEBSITE_INQUIRY = 'WEBSITE_INQUIRY', _('موقع الشركة الإلكتروني الرسمي')
        BROKER_REFERRAL = 'BROKER_REFERRAL', _('إحالة وسيط / شركة تسويق خارجية')
        EXHIBITION = 'EXHIBITION', _('معرض عقاري رسمي')

    customer = models.OneToOneField(
        'customer.Customer',
        on_delete=models.CASCADE,
        related_name='broker_attribution',
        verbose_name=_('العميل')
    )
    first_touch_source = models.CharField(
        max_length=50,
        choices=LeadSource.choices,
        default=LeadSource.DIRECT_WALK_IN,
        verbose_name=_('مصدر العميل الأولي (First-Touch Source)')
    )
    referring_broker = models.ForeignKey(
        RealEstateBroker,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='referred_customers',
        verbose_name=_('الوسيط المحيل إن وُجد')
    )
    is_locked = models.BooleanField(
        default=True,
        verbose_name=_('بصمة المصدر مقفلة ومحمية من التغيير')
    )
    ceo_override_used = models.BooleanField(
        default=False,
        verbose_name=_('تم استخدام تفويض استثنائي من العضو المنتدب (CEO Override)')
    )
    ceo_override_reason = models.TextField(
        blank=True,
        verbose_name=_('مبرر وتفاصيل تفويض العضو المنتدب')
    )
    ceo_override_hash = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_('البصمة الرقمية المشفرة للتفويض')
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('تاريخ التسجيل الأولي')
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('تاريخ التحديث')
    )

    class Meta:
        verbose_name = _('بصمة أسبقية مصدر العميل')
        verbose_name_plural = _('سجلات أسبقية مصادر العملاء (Lead Attribution)')

    def __str__(self):
        return f"{self.customer.name} - {self.get_first_touch_source_display()}"
