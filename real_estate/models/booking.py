# -*- coding: utf-8 -*-
import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class UnitBooking(models.Model):
    """
    نموذج حجز الوحدة العقارية وسداد دفعة جدية الحجز (Reservation & Holding Fee)
    يدعم إدارة فترات السماح وإلغاء الحجز والتحويل إلى تعاقد نهائي
    """
    class BookingStatus(models.TextChoices):
        ACTIVE = 'ACTIVE', _('حجز نشط وساري')
        CONVERTED_TO_CONTRACT = 'CONVERTED_TO_CONTRACT', _('تم التحويل لتعاقد رسمي')
        EXPIRED_RELEASED = 'EXPIRED_RELEASED', _('منتهي ومحرر تلقائياً')
        CANCELLED_PENDING_REFUND = 'CANCELLED_PENDING_REFUND', _('ملغي وبانتظار رد جدية الحجز')
        CANCELLED_REFUNDED = 'CANCELLED_REFUNDED', _('ملغي مع استرداد جدية الحجز')
        CANCELLED_FORFEITED = 'CANCELLED_FORFEITED', _('ملغي مع مصادرة جدية الحجز')

    booking_number = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name=_('رقم استمارة الحجز')
    )
    unit = models.ForeignKey(
        'real_estate.PropertyUnit',
        on_delete=models.PROTECT,
        related_name='bookings',
        verbose_name=_('الوحدة المحجوزة')
    )
    customer = models.ForeignKey(
        'customer.Customer',
        on_delete=models.PROTECT,
        related_name='unit_bookings',
        verbose_name=_('العميل الحاجز')
    )
    booking_date = models.DateField(
        default=timezone.localdate,
        verbose_name=_('تاريخ الحجز')
    )
    expiry_date = models.DateField(
        verbose_name=_('تاريخ انتهاء مهلة الحجز')
    )
    holding_deposit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('مبلغ جدية الحجز المسدد')
    )
    currency = models.ForeignKey(
        'financial.Currency',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_('عملة جدية الحجز')
    )
    exchange_rate = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        default=Decimal('1.000000'),
        verbose_name=_('سعر الصرف لجدية الحجز')
    )
    status = models.CharField(
        max_length=30,
        choices=BookingStatus.choices,
        default=BookingStatus.ACTIVE,
        db_index=True,
        verbose_name=_('حالة الحجز')
    )
    journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='unit_bookings',
        verbose_name=_('قيد تحصيل جدية الحجز')
    )
    is_deposit_collected = models.BooleanField(
        default=False,
        verbose_name=_('تم إثبات تحصيل جدية الحجز')
    )
    active_cancellation_settlement = models.ForeignKey(
        'real_estate.BookingCancellationSettlement',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
        verbose_name=_('قرار تسوية الإلغاء الساري حالياً')
    )

    # منظومة الاعتماد المالي والرقابي الثنائي (Dual Financial & Audit Control)
    is_reviewed_sales = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name=_('تمت مراجعة المبيعات والحسابات')
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='bookings_reviewed',
        verbose_name=_('المراجع للمبيعات')
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ مراجعة المبيعات')
    )

    is_confirmed_audit = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name=_('تم الاعتماد المالي والرقابي')
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='bookings_confirmed',
        verbose_name=_('المعتمد رقابياً')
    )
    confirmed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ الاعتماد الرقابي')
    )

    audit_bypassed = models.BooleanField(
        default=False,
        verbose_name=_('تم التجاوز الإداري الموثق')
    )
    audit_bypass_reason = models.TextField(
        blank=True,
        default='',
        verbose_name=_('سبب التجاوز الإداري')
    )
    audit_bypassed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='bookings_audit_bypassed',
        verbose_name=_('المسؤول المتجاوز إدارياً')
    )

    is_legacy_pre_audit = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name=_('حجز سابق لمنظومة الاعتماد الثنائي')
    )

    # باقات التشطيب والملحقات (Finishing Packages & Accessories)
    finishing_package = models.ForeignKey(
        'real_estate.FinishingPackageTemplate',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='bookings',
        verbose_name=_('باقة التشطيب')
    )
    finishing_meter_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('سعر متر التشطيب')
    )
    total_finishing_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي مبلغ التشطيب')
    )
    utilities_deposit_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('أمانات رسوم المرافق')
    )

    parking_slot_code = models.CharField(
        max_length=50,
        blank=True,
        default='',
        db_index=True,
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
        db_index=True,
        verbose_name=_('كود المخزن السريع')
    )
    storage_locker_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('سعر المخزن')
    )

    # هيكلة الشراكة وفريق البيع (Landowner Partnership & Sales Attribution)
    partner = models.ForeignKey(
        'real_estate.LandownerPartnership',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='bookings',
        verbose_name=_('شريك الأرض')
    )
    company_share_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('100.00'),
        verbose_name=_('حصة الشركة (%)')
    )
    partner_share_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('حصة الشريك (%)')
    )

    sales_channel = models.CharField(
        max_length=50,
        blank=True,
        default='',
        verbose_name=_('قناة البيع')
    )
    marketing_lead_source = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name=_('مصدر الحملة التسويقية')
    )
    call_specialist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='bookings_as_call_rep',
        verbose_name=_('مسئول الاتصال')
    )
    visit_specialist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='bookings_as_visit_rep',
        verbose_name=_('مسئول المقابلة')
    )
    site_specialist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='bookings_as_site_rep',
        verbose_name=_('مسئول المعاينة/الموقع')
    )
    broker = models.ForeignKey(
        'real_estate.RealEstateBroker',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='bookings',
        verbose_name=_('الوسيط العقاري')
    )

    # المعرف التشفيري العام للتحقق الحي عبر QR Code
    verification_uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
        verbose_name=_('المعرف التشفيري للتحقق الحي')
    )
    notes = models.TextField(
        blank=True,
        verbose_name=_('ملاحظات وشروط الحجز')
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_unit_bookings',
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
        verbose_name = _('حجز وحدة عقارية')
        verbose_name_plural = _('حجوزات الوحدات العقارية')
        ordering = ['-booking_date', '-id']
        permissions = [
            ('refund_unitbooking', _('Can refund unit booking / صلاحية صرف واسترداد جدية الحجز')),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(holding_deposit__gte=0),
                name='chk_booking_deposit_non_negative'
            )
        ]

    def clean(self):
        super().clean()
        if self.unit_id and self.unit.status == self.unit.UnitStatus.LANDOWNER_ALLOCATED:
            raise ValidationError(
                _("لا يمكن حجز هذه الوحدة نظراً لأنها مخصصة لمالك الأرض ضمن اتفاقية المشاركة (LANDOWNER_ALLOCATED).")
            )

        if not self.is_deposit_collected and self.status == self.BookingStatus.ACTIVE and self.customer_id:
            project_id = self.unit.project_id if self.unit else None
            unpaid_count = UnitBooking.objects.filter(
                customer_id=self.customer_id,
                unit__project_id=project_id,
                is_deposit_collected=False,
                status=self.BookingStatus.ACTIVE
            ).exclude(pk=self.pk).count()
            if unpaid_count >= 2:
                raise ValidationError(_("لا يمكن للعميل حجز أكثر من وحدتين دون سداد جدية الحجز لحماية مخزون المشروع."))

        if (self.company_share_percentage + self.partner_share_percentage) != Decimal('100.00'):
            raise ValidationError(_("مجموع حصة الشركة وحصة الشريك يجب أن يساوي 100.00% بالضبط."))

        # قيد الفصل الرقابي واكتمال أدلة الاعتماد الثنائي (Segregation of Duties - SoD)
        if not (self.is_legacy_pre_audit or self.audit_bypassed):
            if self.is_reviewed_sales:
                if not self.reviewed_by_id:
                    raise ValidationError(_("لا يجوز تفعيل علامة مراجعة المبيعات دون توثيق المراجع المسؤول (reviewed_by)."))
                if not self.reviewed_at:
                    raise ValidationError(_("لا يجوز تفعيل علامة مراجعة المبيعات دون توثيق تاريخ المراجعة (reviewed_at)."))
                if self.created_by_id and self.reviewed_by_id == self.created_by_id:
                    raise ValidationError(_("قيد الفصل الرقابي (Segregation of Duties): لا يجوز لمنشئ الحجز مراجعة حجزه بنفسه."))

            if self.is_confirmed_audit:
                if not self.confirmed_by_id:
                    raise ValidationError(_("لا يجوز تفعيل علامة الاعتماد الرقابي دون توثيق المعتمد المسؤول (confirmed_by)."))
                if not self.confirmed_at:
                    raise ValidationError(_("لا يجوز تفعيل علامة الاعتماد الرقابي دون توثيق تاريخ الاعتماد (confirmed_at)."))
                if not self.is_reviewed_sales:
                    raise ValidationError(_("لا يجوز الاعتماد الرقابي لحجز لم تستوفَ فيه مراجعة المبيعات أولاً."))
                if self.reviewed_by_id and self.confirmed_by_id == self.reviewed_by_id:
                    raise ValidationError(_("قيد الفصل الرقابي (Segregation of Duties): لا يجوز لنفس المستخدم تسجيل مراجعة المبيعات والاعتماد الرقابي معاً."))

        if self.active_cancellation_settlement_id:
            if self.active_cancellation_settlement.booking_id != self.id:
                raise ValidationError(_("مؤشر التسوية النشطة يشير إلى قرار تسوية لا ينتمي لهذا الحجز."))
            if not self.active_cancellation_settlement.is_active:
                raise ValidationError(_("لا يمكن تعيين قرار تسوية مؤرشف أو غير نشط كمؤشر سارٍ للحجز."))

    def save(self, *args, **kwargs):
        force_audit_update = kwargs.pop('force_audit_update', False)

        if not self.booking_number:
            from core.services.sequence_service import SequenceService
            from core.enums.document_types import DocumentType
            self.booking_number = SequenceService.get_next_number(
                document_type=DocumentType.UNIT_BOOKING,
                date=self.booking_date,
                user=self.created_by
            )
        if not self.verification_uuid:
            self.verification_uuid = uuid.uuid4()

        self.full_clean()

        if self.pk:
            persisted = UnitBooking.objects.filter(pk=self.pk).first()
            if persisted and persisted.is_confirmed_audit and not force_audit_update:
                ALLOWED_TRANSITION_FIELDS = {
                    'status', 'status_version', 'notes', 'updated_at',
                    'active_cancellation_settlement', 'active_cancellation_settlement_id'
                }
                changed_fields = []
                for field in self._meta.fields:
                    f_name = field.name
                    if f_name not in ALLOWED_TRANSITION_FIELDS:
                        if getattr(persisted, f_name) != getattr(self, f_name):
                            changed_fields.append(f_name)
                if changed_fields:
                    raise ValidationError(
                        _("حظر تعديل الحجز المعتمد رقابياً: الحقول التالية مجمدة ولا تقبل التعديل: %(fields)s") % {
                            'fields': ', '.join(changed_fields)
                        }
                    )

        super().save(*args, **kwargs)

    @property
    def is_expired(self) -> bool:
        """فحص انتهاء صلاحية الحجز مقارنة باليوم الحالي"""
        return timezone.localdate() > self.expiry_date

    def __str__(self):
        return f"{self.booking_number} - {self.unit.unit_code} - {self.customer.name} ({self.get_status_display()})"
