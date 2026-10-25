# -*- coding: utf-8 -*-
from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _


class ChequeSettlementLine(models.Model):
    """
    سجل تسويات الشيك للوفاء الجزئي وتعدد أسعار الصرف
    """
    cheque = models.ForeignKey(
        'cheques.Cheque',
        on_delete=models.PROTECT,
        related_name='settlement_lines',
        verbose_name=_('الشيك')
    )
    action_log = models.OneToOneField(
        'cheques.ChequeActionLog',
        on_delete=models.PROTECT,
        related_name='settlement_line',
        verbose_name=_('سجل الحركة المرتبط')
    )
    settlement_date = models.DateField(db_index=True, verbose_name=_('تاريخ التسوية البنكية'))
    settled_amount_currency = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name=_('المبلغ المسدد بعملة الشيك')
    )
    exchange_rate = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        default=Decimal('1.000000'),
        verbose_name=_('سعر صرف التسوية')
    )
    settled_amount_functional = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name=_('المسدد بالعملة المحلية')
    )
    book_value_functional = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name=_('القيمة الدفترية للحصة المسددة')
    )
    realized_fx_gain_loss = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('فروق العملة المحققة')
    )
    bank_charges = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('المصاريف البنكية')
    )
    net_bank_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name=_('صافي المبلغ بالبنك')
    )
    deposit_bank_account = models.ForeignKey(
        'financial.ChartOfAccounts',
        on_delete=models.PROTECT,
        related_name='cheque_settlement_lines',
        verbose_name=_('حساب البنك')
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ الإنشاء'))

    class Meta:
        verbose_name = _('سطر تسوية شيك')
        verbose_name_plural = _('أسطر تسويات الشيكات')
        ordering = ['-settlement_date', '-id']

    def __str__(self):
        return f"{self.cheque.voucher_number} - {self.settled_amount_currency} ({self.settlement_date})"
