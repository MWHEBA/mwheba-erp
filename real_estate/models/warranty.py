# -*- coding: utf-8 -*-
"""
WarrantyTicket - نموذج تذاكر الضمان وخدمات ما بعد التسليم
MWHEBA ERP — Real Estate Wave 3 (Phase 12: Warranty Claims & Contractor Retention Debits)
"""
import uuid
from decimal import Decimal
from datetime import timedelta
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from real_estate.models.unit import PropertyUnit


class WarrantyTicket(models.Model):
    """
    نموذج تذكرة الضمان وخدمة ما بعد التسليم للوحدات العقارية:
    - استقبال شكاوى عيوب التشطيب (ضمان سنة) أو السلامة الإنشائية (الضمان العشري 10 سنوات)
    - ربط المسؤولية بمقاول الباطن المنفذ (Responsible Contractor)
    - خصم تكلفة الإصلاح الفعلي آلياً من حساب تأمين ضمان أعمال المقاول (Contractor Retention 21310) في حال تقاعسه
    - حماية تامة لقائمة دخل المطور (Zero P&L Impact) حيث يتم تحميل التكلفة بالكامل على تأمين المقاول
    """

    class TicketCategory(models.TextChoices):
        FINISHING_PLUMBING = 'FINISHING_PLUMBING', _('سباكة وتغذية وصرف')
        FINISHING_ELECTRICAL = 'FINISHING_ELECTRICAL', _('كهرباء وإنارة وقواطع')
        FINISHING_PAINTING = 'FINISHING_PAINTING', _('دهانات ونقاشة ومحارة')
        FINISHING_CARPENTRY = 'FINISHING_CARPENTRY', _('أبواب وشبابيك وأعمال نجارة')
        FINISHING_HVAC = 'FINISHING_HVAC', _('تكييف وتهوية')
        WATERPROOFING = 'WATERPROOFING', _('عزل مائي وحراري (حمامات/أسطح)')
        STRUCTURAL_DECENNIAL = 'STRUCTURAL_DECENNIAL', _('سلامة إنشائية وهيكل خرساني (ضمان عشري)')
        OTHER = 'OTHER', _('أعمال تشطيبات أخرى')

    class TicketPriority(models.TextChoices):
        LOW = 'LOW', _('منخفضة')
        MEDIUM = 'MEDIUM', _('متوسطة')
        HIGH = 'HIGH', _('عالية')
        EMERGENCY = 'EMERGENCY', _('طارئة / تسريب مياه أو ماس كهربائي')

    class TicketStatus(models.TextChoices):
        REPORTED = 'REPORTED', _('بلاغ وارد')
        INSPECTED = 'INSPECTED', _('تمت المعاينة وتحديد المسؤولية')
        CONTRACTOR_NOTIFIED = 'CONTRACTOR_NOTIFIED', _('تم إخطار المقاول بالإصلاح')
        RESOLVED_BY_CONTRACTOR = 'RESOLVED_BY_CONTRACTOR', _('تم الإصلاح بواسطة المقاول')
        DEFAULTED_TO_DEVELOPER = 'DEFAULTED_TO_DEVELOPER', _('تقاعس المقاول - تحويل للإصلاح المباشر')
        CLOSED_DEBITED = 'CLOSED_DEBITED', _('مغلقة بعد خصم تكلفة الإصلاح من تأمين المقاول')
        REJECTED = 'REJECTED', _('مرفوضة / سوء استخدام أو خارج الضمان')

    class WarrantyType(models.TextChoices):
        FINISHING_ONE_YEAR = 'FINISHING_ONE_YEAR', _('ضمان تشطيبات ومرافق (سنة واحدة)')
        STRUCTURAL_TEN_YEARS = 'STRUCTURAL_TEN_YEARS', _('ضمان هيكل وسلامة إنشائية (10 سنوات)')

    ticket_number = models.CharField(
        max_length=60,
        unique=True,
        db_index=True,
        blank=True,
        verbose_name=_('رقم تذكرة الضمان')
    )
    unit = models.ForeignKey(
        'real_estate.PropertyUnit',
        on_delete=models.PROTECT,
        related_name='warranty_tickets',
        verbose_name=_('الوحدة العقارية')
    )
    contract = models.ForeignKey(
        'real_estate.PropertyContract',
        on_delete=models.PROTECT,
        related_name='warranty_tickets',
        verbose_name=_('العقد العقاري')
    )
    customer = models.ForeignKey(
        'customer.Customer',
        on_delete=models.PROTECT,
        related_name='real_estate_warranty_tickets',
        verbose_name=_('العميل الشاغل')
    )
    category = models.CharField(
        max_length=35,
        choices=TicketCategory.choices,
        verbose_name=_('تصنيف العيب الفني')
    )
    warranty_type = models.CharField(
        max_length=30,
        choices=WarrantyType.choices,
        default=WarrantyType.FINISHING_ONE_YEAR,
        verbose_name=_('نوع فترة الضمان')
    )
    priority = models.CharField(
        max_length=20,
        choices=TicketPriority.choices,
        default=TicketPriority.MEDIUM,
        verbose_name=_('درجة الأولوية')
    )
    status = models.CharField(
        max_length=30,
        choices=TicketStatus.choices,
        default=TicketStatus.REPORTED,
        db_index=True,
        verbose_name=_('حالة التذكرة')
    )
    title = models.CharField(
        max_length=200,
        verbose_name=_('عنوان البلاغ / وصف مختصر')
    )
    description = models.TextField(
        verbose_name=_('تفاصيل العيب وموقع الظهور بالوحدة')
    )
    responsible_contractor = models.ForeignKey(
        'supplier.Supplier',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='assigned_warranty_tickets',
        verbose_name=_('المقاول المنفذ المسؤول عن البند')
    )
    contractor_notification_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ إخطار المقاول')
    )
    contractor_sla_deadline = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('المهلة المحددة للمقاول للإصلاح (SLA)')
    )
    actual_repair_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('تكلفة الإصلاح الفعلي المنفذة')
    )
    retention_journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='warranty_retention_debits',
        verbose_name=_('قيد خصم التكلفة من تأمين المقاول')
    )
    settlement_account = models.ForeignKey(
        'financial.ChartOfAccounts',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='warranty_settlement_accounts',
        verbose_name=_('حساب سداد تكلفة الإصلاح (خزينة/بنك/مورد صيانة)')
    )
    engineer_notes = models.TextField(
        blank=True,
        verbose_name=_('تقرير مهندس المعاينة الفنية')
    )
    closure_notes = models.TextField(
        blank=True,
        verbose_name=_('ملاحظات الإغلاق والتسوية')
    )
    inspected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='inspected_warranty_tickets',
        verbose_name=_('مهندس المعاينة')
    )
    inspected_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ المعاينة')
    )
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='closed_warranty_tickets',
        verbose_name=_('أغلق واعتمد بواسطة')
    )
    closed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ الإغلاق')
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_warranty_tickets',
        verbose_name=_('سجل البلاغ بواسطة')
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('تاريخ التسجيل')
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('تاريخ التحديث')
    )

    class Meta:
        verbose_name = _('تذكرة ضمان وصيانة ما بعد التسليم')
        verbose_name_plural = _('تذاكر ضمان وصيانة ما بعد التسليم')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.ticket_number or 'WRN-DRAFT'} - {self.unit.unit_code} ({self.get_status_display()})"

    def clean(self):
        super().clean()
        # 1. التحقق من أن الوحدة قد تم تسليمها بالفعل للمشتري
        if self.unit_id:
            if self.unit.status not in [PropertyUnit.UnitStatus.DELIVERED, PropertyUnit.UnitStatus.DELIVERED_DEEMED]:
                raise ValidationError({
                    'unit': _('لا يمكن فتح تذكرة ضمان لوحدة لم يتم تسليمها للعميل بعد (الحالة الحالية: %(status)s).') % {
                        'status': self.unit.get_status_display()
                    }
                })

        # 2. التحقق من سريان فترة الضمان القانوني
        if self.unit_id:
            last_handover = self.unit.handover_receipts.filter(status='EXECUTED').order_by('-handover_date').first()
            if last_handover:
                handover_date = last_handover.handover_date
                today = timezone.localdate()
                days_since_handover = (today - handover_date).days

                if self.warranty_type == self.WarrantyType.FINISHING_ONE_YEAR and days_since_handover > 365:
                    raise ValidationError({
                        'warranty_type': _(
                            'انتهت فترة ضمان التشطيبات المحددة بسنة واحدة (مر %(days)s يوماً على التسليم بتاريخ %(date)s).'
                        ) % {'days': days_since_handover, 'date': handover_date}
                    })
                elif self.warranty_type == self.WarrantyType.STRUCTURAL_TEN_YEARS and days_since_handover > 3650:
                    raise ValidationError({
                        'warranty_type': _(
                            'انتهت فترة الضمان العشري للهيكل الإنشائي المحددة بـ 10 سنوات (مر %(days)s يوماً على التسليم).'
                        ) % {'days': days_since_handover}
                    })

    def save(self, *args, **kwargs):
        if not self.ticket_number:
            self.ticket_number = f"WRN-{self.unit.unit_code}-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)
