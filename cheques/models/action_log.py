# -*- coding: utf-8 -*-
from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings


class ChequeActionType(models.TextChoices):
    RECEIVE = 'RECEIVE', _('استلام شيك')
    ISSUE = 'ISSUE', _('إصدار شيك')
    DEPOSIT = 'DEPOSIT', _('إيداع برسم التحصيل')
    COLLECT = 'COLLECT', _('تحصيل كلي')
    PARTIAL_COLLECT = 'PARTIAL_COLLECT', _('تحصيل جزئي')
    BOUNCE = 'BOUNCE', _('ارتداد الشيك')
    CLEAR = 'CLEAR', _('صرف بنكي (أوراق دفع)')
    ENDORSE = 'ENDORSE', _('تظهير لمورد')
    ENDORSED_BOUNCED = 'ENDORSED_BOUNCED', _('ارتداد شيك مظهر')
    RETURN_TO_DRAWER = 'RETURN_TO_DRAWER', _('رد إلى الساحب')
    LEGAL_ACTION = 'LEGAL_ACTION', _('إجراء قانوني')
    LEGAL_REFERRAL = 'LEGAL_REFERRAL', _('تحويل للشؤون القانونية')
    LEGAL_SETTLEMENT = 'LEGAL_SETTLEMENT', _('تسوية قضائية')
    CANCEL = 'CANCEL', _('إلغاء الشيك')
    REVERSE_ACTION = 'REVERSE_ACTION', _('تراجع عن حركة سابقة')
    REPLACE_LEAF = 'REPLACE_LEAF', _('استبدال ورقة تالفة')
    CONVERT_GUARANTEE = 'CONVERT_GUARANTEE', _('تحويل شيك ضمان إلى تشغيلي')


class ChequeActionLog(models.Model):
    """
    سجل حركات وتدقيق الشيكات مع دعم التراجع ومنع التكرار
    """
    cheque = models.ForeignKey(
        'cheques.Cheque',
        on_delete=models.PROTECT,
        related_name='action_logs',
        verbose_name=_('الشيك')
    )
    action = models.CharField(
        max_length=50,
        choices=ChequeActionType.choices,
        db_index=True,
        verbose_name=_('نوع الإجراء')
    )
    from_status = models.CharField(max_length=30, verbose_name=_('الحالة السابقة'))
    to_status = models.CharField(max_length=30, verbose_name=_('الحالة الجديدة'))
    action_date = models.DateField(db_index=True, verbose_name=_('تاريخ أثر الحركة'))

    journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='cheque_action_logs',
        verbose_name=_('قيد اليومية')
    )
    reversal_entry = models.ForeignKey(
        'financial.JournalEntry',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='reversed_cheque_actions',
        verbose_name=_('القيد العكسي')
    )

    idempotency_key = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        verbose_name=_('مفتاح منع التكرار')
    )
    request_payload_hash = models.CharField(
        max_length=64,
        db_index=True,
        verbose_name=_('بصمة المعلمات المشفرة')
    )

    is_reversed = models.BooleanField(default=False, db_index=True, verbose_name=_('معكوسة'))
    reversed_by_log = models.OneToOneField(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='reverses_log',
        verbose_name=_('حركة العكس المرتبطة')
    )

    amount_processed = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('المبلغ المعالج')
    )
    bank_charges = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('العمولات والمصاريف')
    )
    reason = models.TextField(blank=True, verbose_name=_('السبب أو البيان'))
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_('البيانات الوصفية المنظمة للحركة')
    )
    previous_issuer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
        verbose_name=_('المُصدر السابق المستعاد')
    )
    previous_issued_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ ووقت الإصدار السابق المستعاد')
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='cheque_actions_executed',
        verbose_name=_('المستخدم المنفذ')
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ ووقت التنفيذ'))

    class Meta:
        verbose_name = _('سجل حركة شيك')
        verbose_name_plural = _('سجلات حركات الشيكات')
        ordering = ['-action_date', '-id']

    def __str__(self):
        return f"{self.cheque.voucher_number} - {self.action} ({self.from_status} -> {self.to_status}) at {self.action_date}"
