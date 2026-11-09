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


class BookingCancellationSettlement(models.Model):
    """
    قرار تسوية إلغاء حجز عقاري واحتساب المستحقات والمصادرات
    """
    class SettlementStatus(models.TextChoices):
        APPROVED_PENDING_PAYMENT = 'APPROVED_PENDING', _('معتمد بانتظار صرف المستحقات')
        PARTIALLY_DISBURSED = 'PARTIALLY_DISBURSED', _('تم صرف جزء من المستحقات')
        FULLY_DISBURSED = 'FULLY_DISBURSED', _('تم صرف كامل المستحقات للعميل')
        FORFEITED = 'FORFEITED', _('تمت المصادرة بالكامل كإيراد وغرامات')
        REINSTATED_CANCELLED = 'REINSTATED', _('ملغى للتراجع عن الإلغاء واستعادة الحجز')

    settlement_number = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name=_('رقم قرار التسوية')
    )
    booking = models.ForeignKey(
        'real_estate.UnitBooking',
        on_delete=models.PROTECT,
        related_name='cancellation_settlements',
        verbose_name=_('استمارة الحجز')
    )
    settlement_version = models.PositiveIntegerField(
        default=1,
        verbose_name=_('رقم إصدار التسوية')
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name=_('التسوية النشطة السارية')
    )
    status = models.CharField(
        max_length=30,
        choices=SettlementStatus.choices,
        default=SettlementStatus.APPROVED_PENDING_PAYMENT,
        db_index=True,
        verbose_name=_('حالة التسوية')
    )
    cancellation_reason = models.CharField(
        max_length=50,
        default='FINANCIAL_HARDSHIP',
        verbose_name=_('سبب إلغاء الحجز')
    )
    settlement_date = models.DateField(
        default=timezone.localdate,
        verbose_name=_('تاريخ التسوية')
    )
    currency = models.ForeignKey(
        'financial.Currency',
        on_delete=models.PROTECT,
        related_name='cancellation_settlements',
        verbose_name=_('عملة التسوية')
    )
    exchange_rate = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        default=Decimal('1.000000'),
        verbose_name=_('سعر صرف عملة التسوية مقابل العملة الوظيفية')
    )
    total_deposit_paid = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name=_('إجمالي جدية الحجز المسددة')
    )
    approved_deduction_fees = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('المصاريف الإدارية والغرامات المعتمدة')
    )
    net_refundable_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name=_('صافي المبلغ المستحق صرفه')
    )
    committed_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('المبلغ المحجوز بأدوات صرف قائمة')
    )
    cleared_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('المبلغ المنصرف والمسيل فعلياً')
    )
    remaining_disbursable_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('المتبقي المتاح لإصدار أدوات صرف')
    )
    forfeiture_journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='booking_forfeiture_entries',
        verbose_name=_('قيد إثبات مصادرة جدية الحجز')
    )
    notes = models.TextField(
        blank=True,
        default='',
        verbose_name=_('ملاحظات وسند التسوية')
    )
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='processed_cancellation_settlements',
        verbose_name=_('تمت المعالجة بواسطة')
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
        verbose_name = _('قرار تسوية إلغاء حجز عقاري')
        verbose_name_plural = _('قرارات تسوية إلغاء الحجوزات العقارية')
        ordering = ['-settlement_date', '-id']

    def clean(self):
        super().clean()
        if self.is_active and self.booking_id:
            active_ptr = self.booking.active_cancellation_settlement_id
            if active_ptr and active_ptr != self.id:
                raise ValidationError(_("يوجد بالفعل قرار تسوية نشط مسجل لهذا الحجز."))

    def save(self, *args, **kwargs):
        if not self.settlement_number:
            from core.services.sequence_service import SequenceService
            from core.enums.document_types import DocumentType
            self.settlement_number = SequenceService.get_next_number(
                document_type=DocumentType.BOOKING_CANCELLATION_SETTLEMENT,
                date=self.settlement_date,
                user=self.processed_by
            )
        super().save(*args, **kwargs)

    def recalculate_balances(self):
        """إعادة احتساب الأرصدة بالمعادلة الصارمة: remaining = net - committed - cleared"""
        committed = self.disbursements.filter(status='ISSUED').aggregate(
            s=models.Sum('settlement_currency_equivalent')
        )['s'] or Decimal('0.00')
        cleared = self.disbursements.filter(status='CLEARED').aggregate(
            s=models.Sum('settlement_currency_equivalent')
        )['s'] or Decimal('0.00')
        self.committed_amount = committed
        self.cleared_amount = cleared
        self.remaining_disbursable_amount = max(
            Decimal('0.00'),
            (self.net_refundable_amount - committed - cleared).quantize(Decimal('0.01'))
        )
        if self.cleared_amount >= self.net_refundable_amount and self.net_refundable_amount > Decimal('0.00'):
            self.status = self.SettlementStatus.FULLY_DISBURSED
        elif self.cleared_amount > Decimal('0.00') or self.committed_amount > Decimal('0.00'):
            self.status = self.SettlementStatus.PARTIALLY_DISBURSED
        elif self.is_active:
            self.status = self.SettlementStatus.APPROVED_PENDING_PAYMENT
        self.save(update_fields=['committed_amount', 'cleared_amount', 'remaining_disbursable_amount', 'status', 'updated_at'])

    def __str__(self):
        curr_code = self.currency.code if self.currency else ''
        return f"{self.settlement_number} - {self.booking.booking_number} ({self.net_refundable_amount} {curr_code})"


class RefundDisbursementPayment(models.Model):
    """
    سند صرف استرداد حجز عقاري (نقد / بنك / شيكات)
    """
    class DisbursementMethod(models.TextChoices):
        CASH = 'CASH', _('نقداً من الخزينة')
        BANK_TRANSFER = 'BANK_TRANSFER', _('تحويل بنكي مباشر')
        CHEQUE = 'CHEQUE', _('شيك صادر (أوراق دفع)')

    class PaymentStatus(models.TextChoices):
        ISSUED = 'ISSUED', _('تم الإصدار / تحرير الشيك')
        CLEARED = 'CLEARED', _('تم الصرف والتسييل بنكياً')
        CANCELLED = 'CANCELLED', _('ملغى / شيك مسترد')
        BOUNCED = 'BOUNCED', _('مرتد / مرفوض بالبنك')

    payment_number = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name=_('رقم سند صرف الاسترداد')
    )
    idempotency_key = models.CharField(
        max_length=120,
        unique=True,
        db_index=True,
        verbose_name=_('مفتاح منع تكرار الطلب المالي الإلزامي')
    )
    settlement = models.ForeignKey(
        BookingCancellationSettlement,
        on_delete=models.PROTECT,
        related_name='disbursements',
        verbose_name=_('قرار التسوية')
    )
    method = models.CharField(
        max_length=20,
        choices=DisbursementMethod.choices,
        default=DisbursementMethod.CHEQUE,
        verbose_name=_('طريقة الصرف')
    )
    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.ISSUED,
        db_index=True,
        verbose_name=_('حالة الصرف')
    )
    payment_date = models.DateField(
        default=timezone.localdate,
        verbose_name=_('تاريخ الصرف')
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name=_('مبلغ الصرف الفعلي بعملة الصرف')
    )
    payout_currency = models.ForeignKey(
        'financial.Currency',
        on_delete=models.PROTECT,
        related_name='refund_disbursements_payout',
        verbose_name=_('عملة الصرف')
    )
    payout_exchange_rate = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        default=Decimal('1.000000'),
        verbose_name=_('سعر صرف عملة الصرف مقابل العملة الوظيفية')
    )
    settlement_currency_equivalent = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name=_('المعادل بعملة التسوية المقيدة')
    )
    functional_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('المعادل بالعملة الوظيفية (EGP)')
    )
    realized_fx_gain_loss = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('أرباح/خسائر فروق العملة المحققة الصافية')
    )
    rounding_difference = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        default=Decimal('0.0000'),
        verbose_name=_('فرق التقريب المحاسبي الموجه للأستاذ')
    )
    cheque = models.ForeignKey(
        'cheques.Cheque',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='booking_refund_disbursements',
        verbose_name=_('الشيك الصادر من منظومة الشيكات المركزية')
    )
    payment_account = models.ForeignKey(
        'financial.ChartOfAccounts',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='refund_disbursement_payments',
        verbose_name=_('حساب السداد (الخزينة/البنك)')
    )
    journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='refund_disbursement_entries',
        verbose_name=_('قيد إثبات الصرف')
    )
    clearing_journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='refund_clearing_entries',
        verbose_name=_('قيد تسييل الشيك البنكي')
    )
    reversal_journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='refund_reversal_entries',
        verbose_name=_('قيد إلغاء أو ارتداد الصرف')
    )
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='processed_refund_disbursements',
        verbose_name=_('تم الصرف بواسطة')
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
        verbose_name = _('سند صرف استرداد حجز عقاري')
        verbose_name_plural = _('سندات صرف استرداد الحجوزات العقارية')
        ordering = ['-payment_date', '-id']

    def save(self, *args, **kwargs):
        if not self.payment_number:
            from core.services.sequence_service import SequenceService
            from core.enums.document_types import DocumentType
            self.payment_number = SequenceService.get_next_number(
                document_type=DocumentType.BOOKING_REFUND_PAYMENT,
                date=self.payment_date,
                user=self.processed_by
            )
        super().save(*args, **kwargs)

    def __str__(self):
        curr_code = self.payout_currency.code if self.payout_currency else ''
        return f"{self.payment_number} - {self.settlement.settlement_number} ({self.amount} {curr_code} - {self.get_method_display()})"
