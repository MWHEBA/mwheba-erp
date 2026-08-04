"""
SupplierAgingService - محرك اعمار ديون الموردين المتقدم (Sprint 3 Due-Date Aging Engine)
يحسب شرائح الديون المستحقة للموردين بناءً على تواريخ استحقاق فواتير الشراء (due_date) والرصيد غير المسدد صراحة (FIN-SUB-001)
يعزل الأرصدة الدائنة (credit_balance) والمدفوعات المقدمة للمورد بشكل مستقل عن شرائح التخلف عن السداد.
"""

import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional
from django.utils import timezone

from supplier.models import Supplier
from financial.services.allocation_service import AllocationService
from financial.services.ledger_query_service import LedgerQueryService

logger = logging.getLogger("supplier.supplier_aging_service")


class SupplierAgingService:
    """
    خدمة حساب تقرير أعمار ديون الموردين المعيارية (Open-Item Due-Date Aging)
    """

    @classmethod
    def get_supplier_open_item_aging(
        cls,
        supplier_ids: Optional[List[int]] = None,
        as_of_date: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        توليد تقرير أعمار مستحقات الموردين التفصيلي الموزع حسب تواريخ الاستحقاق وعزل المبالغ الدائنة
        """
        ref_date = as_of_date or timezone.now().date()
        suppliers = Supplier.objects.filter(is_active=True).select_related('financial_account')
        if supplier_ids:
            suppliers = suppliers.filter(pk__in=supplier_ids)

        report_rows = []
        grand_total = {
            'not_due': Decimal('0.00'),
            'days_1_30': Decimal('0.00'),
            'days_31_60': Decimal('0.00'),
            'days_61_90': Decimal('0.00'),
            'days_90_plus': Decimal('0.00'),
            'credit_balance': Decimal('0.00'),
            'net_balance': Decimal('0.00')
        }

        # محاولة الاستيراد الآمن لموديل المشتريات
        try:
            from purchase.models import Purchase
        except Exception:
            Purchase = None

        # (FIN-CORE-015 Batch Query Optimization): Query all allocation totals in a single batch aggregate
        from financial.models import PaymentAllocation
        from django.db.models import Sum

        alloc_map = dict(
            PaymentAllocation.objects.filter(
                debit_document_type="PURCHASE_BILL"
            ).values('debit_document_id').annotate(
                total_allocated=Sum('allocated_amount')
            ).values_list('debit_document_id', 'total_allocated')
        )

        for supplier in suppliers:
            if supplier.financial_account:
                bal_data = LedgerQueryService.get_account_balance(supplier.financial_account, as_of_date=ref_date)
                net_balance = bal_data.get('balance', getattr(supplier, 'balance', Decimal('0.00')))
            else:
                net_balance = getattr(supplier, 'balance', Decimal('0.00')) or Decimal('0.00')

            not_due = Decimal('0.00')
            days_1_30 = Decimal('0.00')
            days_31_60 = Decimal('0.00')
            days_61_90 = Decimal('0.00')
            days_90_plus = Decimal('0.00')
            total_unpaid_bills = Decimal('0.00')

            from datetime import timedelta

            if Purchase:
                purchases = Purchase.objects.filter(
                    supplier=supplier,
                    created_at__date__lte=ref_date
                ).exclude(status="cancelled")

                for pur in purchases:
                    payment_status = getattr(pur, 'payment_status', '')
                    if payment_status == "paid":
                        continue

                    doc_total = getattr(pur, 'total', Decimal('0.00')) or getattr(pur, 'grand_total', Decimal('0.00'))
                    amount_paid = getattr(pur, 'paid_amount', Decimal('0.00')) or getattr(pur, 'amount_paid', Decimal('0.00'))
                    total_allocated = alloc_map.get(str(pur.id), Decimal('0.00'))
                    effective_paid = max(amount_paid, total_allocated)
                    outstanding = max(Decimal('0.00'), doc_total - effective_paid)

                    if outstanding <= Decimal('0.00'):
                        continue

                    total_unpaid_bills += outstanding

                    due_date = getattr(pur, 'due_date', None)
                    if not due_date:
                        pur_date = getattr(pur, 'date', None) or pur.created_at.date()
                        due_date = pur_date

                    if due_date > ref_date:
                        not_due += outstanding
                    else:
                        overdue_days = (ref_date - due_date).days
                        if overdue_days <= 30:
                            days_1_30 += outstanding
                        elif overdue_days <= 60:
                            days_31_60 += outstanding
                        elif overdue_days <= 90:
                            days_61_90 += outstanding
                        else:
                            days_90_plus += outstanding

            credit_balance = Decimal('0.00')
            if net_balance < total_unpaid_bills:
                credit_balance = total_unpaid_bills - net_balance
            elif net_balance < Decimal('0.00'):
                credit_balance = abs(net_balance)

            report_rows.append({
                'supplier_id': supplier.id,
                'supplier_code': getattr(supplier, 'code', str(supplier.id)),
                'supplier_name': supplier.name,
                'not_due': not_due,
                'days_1_30': days_1_30,
                'days_31_60': days_31_60,
                'days_61_90': days_61_90,
                'days_90_plus': days_90_plus,
                'credit_balance': credit_balance,
                'net_balance': net_balance
            })

            grand_total['not_due'] += not_due
            grand_total['days_1_30'] += days_1_30
            grand_total['days_31_60'] += days_31_60
            grand_total['days_61_90'] += days_61_90
            grand_total['days_90_plus'] += days_90_plus
            grand_total['credit_balance'] += credit_balance
            grand_total['net_balance'] += net_balance

        return {
            'as_of_date': ref_date,
            'rows': report_rows,
            'summary': grand_total
        }
