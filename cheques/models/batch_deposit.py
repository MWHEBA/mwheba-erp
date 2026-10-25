# -*- coding: utf-8 -*-
from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings


class BatchDepositStatus(models.TextChoices):
    DRAFT = 'DRAFT', _('مسودة')
    DEPOSITED = 'DEPOSITED', _('مودعة بالبنك')
    PARTIALLY_CLEARED = 'PARTIALLY_CLEARED', _('محصلة جزئياً')
    CLOSED = 'CLOSED', _('مغلقة بالكامل')
    CANCELLED = 'CANCELLED', _('ملغاة')


class ChequeBatchDeposit(models.Model):
    """
    حافظة إيداع الشيكات المجمعة بالبنك
    """
    batch_number = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name=_('رقم الحافظة التسلسلي')
    )
    deposit_date = models.DateField(db_index=True, verbose_name=_('تاريخ تسليم الحافظة'))
    bank_account = models.ForeignKey(
        'financial.ChartOfAccounts',
        on_delete=models.PROTECT,
        related_name='deposit_batches',
        verbose_name=_('الحساب البنكي المودع به')
    )
    cheques = models.ManyToManyField(
        'cheques.Cheque',
        related_name='batch_deposits',
        verbose_name=_('الشيكات المودعة بالحافظة')
    )
    total_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي مبلغ الحافظة')
    )
    status = models.CharField(
        max_length=30,
        choices=BatchDepositStatus.choices,
        default=BatchDepositStatus.DRAFT,
        db_index=True,
        verbose_name=_('حالة الحافظة')
    )
    deposit_journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='cheque_batch_deposits',
        verbose_name=_('قيد إيداع الحافظة المجمع')
    )
    notes = models.TextField(blank=True, verbose_name=_('ملاحظات'))

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_cheque_batches',
        verbose_name=_('مسجل الحافظة')
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ الإنشاء'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('تاريخ التحديث'))

    class Meta:
        verbose_name = _('حافظة إيداع شيكات')
        verbose_name_plural = _('حوافظ إيداع الشيكات')
        ordering = ['-deposit_date', '-id']

    def __str__(self):
        return f"{self.batch_number} - {self.bank_account.name} ({self.total_amount})"

    def recalculate_total(self):
        """إعادة احتساب إجمالي مبلغ الحافظة من الشيكات التابعة"""
        total = self.cheques.aggregate(models.Sum('amount'))['amount__sum'] or Decimal('0.00')
        self.total_amount = total
        self.save(update_fields=['total_amount'])
        return total
