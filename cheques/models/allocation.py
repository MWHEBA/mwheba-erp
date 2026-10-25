# -*- coding: utf-8 -*-
from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _


class AllocationStatus(models.TextChoices):
    APPLIED = 'APPLIED', _('مطبق وساري')
    REVERSED = 'REVERSED', _('معكوس')


class ChequeInvoiceAllocation(models.Model):
    """
    تخصيصات الشيك على فواتير المبيعات المتعددة
    """
    cheque = models.ForeignKey(
        'cheques.Cheque',
        on_delete=models.CASCADE,
        related_name='invoice_allocations',
        verbose_name=_('الشيك')
    )
    sale = models.ForeignKey(
        'sale.Sale',
        on_delete=models.PROTECT,
        related_name='cheque_allocations',
        verbose_name=_('فاتورة المبيعات')
    )
    allocated_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name=_('المبلغ المخصص (بعملة الشيك)')
    )
    allocated_amount_functional = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name=_('المبلغ المخصص بالعملة المحلية')
    )
    allocation_status = models.CharField(
        max_length=20,
        choices=AllocationStatus.choices,
        default=AllocationStatus.APPLIED,
        db_index=True,
        verbose_name=_('حالة التخصيص')
    )
    allocation_date = models.DateField(db_index=True, verbose_name=_('تاريخ إجراء التخصيص'))
    journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cheque_invoice_allocations',
        verbose_name=_('قيد اليومية المرتبط بالتسوية')
    )
    sale_payment = models.ForeignKey(
        'sale.SalePayment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cheque_allocations',
        verbose_name=_('دفعة الفاتورة المرتبطة')
    )
    allocation_audit = models.ForeignKey(
        'customer.CustomerAllocationAudit',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cheque_allocations',
        verbose_name=_('سجل تدقيق التخصيص')
    )
    notes = models.CharField(max_length=255, blank=True, verbose_name=_('ملاحظات'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ الإنشاء'))

    class Meta:
        verbose_name = _('تخصيص شيك على فاتورة')
        verbose_name_plural = _('تخصيصات الشيكات على الفواتير')
        ordering = ['-allocation_date', '-id']

    def __str__(self):
        return f"{self.cheque.voucher_number} -> {self.sale.number} ({self.allocated_amount})"
