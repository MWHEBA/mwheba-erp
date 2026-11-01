# -*- coding: utf-8 -*-
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

    @property
    def is_expired(self) -> bool:
        """فحص انتهاء صلاحية الحجز مقارنة باليوم الحالي"""
        return timezone.localdate() > self.expiry_date

    def __str__(self):
        return f"{self.booking_number} - {self.unit.unit_code} - {self.customer.name} ({self.get_status_display()})"
