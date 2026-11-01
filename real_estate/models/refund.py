# -*- coding: utf-8 -*-
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class ResaleContingentRefund(models.Model):
    """
    سجل ومطالبة مستحقات العملاء لعقود مفسوخة معلقة لإعادة الطرح (Resale-Contingent Refund)
    لحماية سيولة المطور، تعلق المستحقات في حساب 21701 لحين إعادة التعاقد على الوحدة وسداد مقدم المشتري الجديد
    """
    class RefundStatus(models.TextChoices):
        PENDING_RESALE = 'PENDING_RESALE', _('معلق لإعادة الطرح والتعاقد مع مشتري جديد')
        DISBURSEMENT_AUTHORIZED = 'DISBURSEMENT_AUTHORIZED', _('مصرح بالصرف بعد سداد مقدم المشتري الجديد')
        DISBURSED = 'DISBURSED', _('تم الصرف وسداد المستحقات بالكامل')
        CANCELLED = 'CANCELLED', _('ملغي')

    refund_number = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name=_('رقم سند استحقاق الرد')
    )
    original_contract = models.ForeignKey(
        'real_estate.PropertyContract',
        on_delete=models.PROTECT,
        related_name='resale_refunds',
        verbose_name=_('العقد الأصلي المفسوخ')
    )
    unit = models.ForeignKey(
        'real_estate.PropertyUnit',
        on_delete=models.PROTECT,
        related_name='resale_refunds',
        verbose_name=_('الوحدة العقارية المعاد طرحها')
    )
    customer = models.ForeignKey(
        'customer.Customer',
        on_delete=models.PROTECT,
        related_name='resale_refunds',
        verbose_name=_('العميل صاحب المستحقات المعلقة')
    )
    total_paid_before_cancellation = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name=_('إجمالي ما سدده العميل قبل الفسخ')
    )
    cancellation_penalty_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('قيمة غرامة الفسخ الإدارية المخصومة')
    )
    net_refundable_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name=_('صافي المبلغ المستحق رده للعميل المعلق لحين إعادة البيع')
    )
    status = models.CharField(
        max_length=30,
        choices=RefundStatus.choices,
        default=RefundStatus.PENDING_RESALE,
        db_index=True,
        verbose_name=_('حالة المستحقات المعلقة')
    )
    resale_contract = models.ForeignKey(
        'real_estate.PropertyContract',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='incoming_resale_refunds',
        verbose_name=_('عقد المشتري الجديد بعد إعادة الطرح')
    )
    disbursement_entry = models.ForeignKey(
        'financial.JournalEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resale_refund_disbursements',
        verbose_name=_('قيد صرف المستحقات دفترياً')
    )
    notes = models.TextField(blank=True, verbose_name=_('ملاحظات وسند الفسخ'))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_resale_refunds',
        verbose_name=_('أنشئ بواسطة')
    )
    authorized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='authorized_resale_refunds',
        verbose_name=_('صرح بالصرف بواسطة')
    )
    disbursed_at = models.DateTimeField(null=True, blank=True, verbose_name=_('تاريخ وساعة الصرف الفعلي'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ الإنشاء'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('تاريخ التحديث'))

    class Meta:
        verbose_name = _('مستحق رد معلق لإعادة الطرح')
        verbose_name_plural = _('مستحقات العملاء المعلقة لإعادة الطرح')
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if self.total_paid_before_cancellation is not None and self.cancellation_penalty_amount is not None:
            self.net_refundable_amount = max(
                Decimal('0.00'),
                self.total_paid_before_cancellation - self.cancellation_penalty_amount
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.refund_number} - {self.customer.name} ({self.net_refundable_amount} EGP - {self.get_status_display()})"
