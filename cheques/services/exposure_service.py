# -*- coding: utf-8 -*-
import logging
from decimal import Decimal
from django.db import models

from cheques.models import (
    Cheque,
    ChequeType,
    ChequePurpose,
    ChequeStatus,
    ChequeInvoiceAllocation,
)

logger = logging.getLogger(__name__)


class ChequeExposureService:
    """
    خدمة احتساب أثر الشيكات غير المحصلة على الانكشاف وسقف الائتمان للعملاء
    (Credit Exposure & Uncollected Cheques Governance)
    """

    @classmethod
    def get_uncollected_cheques_exposure(cls, customer_id: int) -> Decimal:
        """
        احتساب أثر الشيكات غير المحصلة في الانكشاف الائتماني للعميل بدقة رياضية:
        Uncollected Invoiced Cheques = Direct Invoiced Cheques + Allocated Uncollected Advance Cheques

        1. شيكات سداد الفواتير المباشرة (purpose=INVOICE_SETTLEMENT) بحالات (IN_PORTFOLIO, UNDER_COLLECTION, PARTIALLY_COLLECTED):
           تُحسب بالكامل برصيدها الدفتري المتبقي remaining_functional.
        2. شيكات الدفعات المقدمة (purpose=ADVANCE_PAYMENT) المخصصة لفواتير عبر ChequeInvoiceAllocation:
           تُحسب الحصة غير المحصلة فقط من التخصيص الساري (allocation_status='APPLIED'):
           allocated_amount_functional * (cheque.remaining_amount / cheque.amount)
        3. استثناء شيكات الضمان (purpose=SECURITY_GUARANTEE) والدفعات المقدمة غير المخصصة تماماً.
        """
        if not customer_id:
            return Decimal("0.00")

        # 1. شيكات سداد الفواتير المباشرة
        direct_cheques = Cheque.objects.filter(
            customer_id=customer_id,
            cheque_type=ChequeType.RECEIVABLE,
            purpose=ChequePurpose.INVOICE_SETTLEMENT,
            status__in=[
                ChequeStatus.IN_PORTFOLIO,
                ChequeStatus.UNDER_COLLECTION,
                ChequeStatus.PARTIALLY_COLLECTED,
            ],
        )
        direct_exposure = direct_cheques.aggregate(
            total=models.Sum("remaining_functional")
        )["total"] or Decimal("0.00")

        # 2. شيكات الدفعات المقدمة المخصصة لفواتير (حصة التخصيص غير المحصلة فقط Pro-rata)
        allocated_advance_exposure = Decimal("0.00")
        advance_allocations = ChequeInvoiceAllocation.objects.filter(
            cheque__customer_id=customer_id,
            cheque__cheque_type=ChequeType.RECEIVABLE,
            cheque__purpose=ChequePurpose.ADVANCE_PAYMENT,
            cheque__status__in=[
                ChequeStatus.IN_PORTFOLIO,
                ChequeStatus.UNDER_COLLECTION,
                ChequeStatus.PARTIALLY_COLLECTED,
            ],
            allocation_status="APPLIED",
        ).select_related("cheque")

        for alloc in advance_allocations:
            chq = alloc.cheque
            if chq.amount and chq.amount > Decimal("0.00") and chq.remaining_amount and chq.remaining_amount > Decimal("0.00"):
                ratio = chq.remaining_amount / chq.amount
                uncollected_portion = (alloc.allocated_amount_functional * ratio).quantize(Decimal("0.01"))
                allocated_advance_exposure += uncollected_portion

        return (direct_exposure + allocated_advance_exposure).quantize(Decimal("0.01"))
