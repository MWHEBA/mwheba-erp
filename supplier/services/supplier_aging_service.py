import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional
from django.utils import timezone

from supplier.models import Supplier, SupplierTransaction
from financial.services.ledger_query_service import LedgerQueryService

logger = logging.getLogger("supplier.supplier_aging_service")


class SupplierAgingService:
    """
    محرك تقارير اعمار ديون الموردين المحصن (Sprint 3 Due-Date Aging Engine)
    يحسب فترات الاستحقاق بناءً على تواريخ استحقاق فواتير الشراء والأرصدة المفتوحة المتبقية والتسويات
    ويفصل الأرصدة الدائنة/المدينة المسبقة صراحة
    """

    @classmethod
    def get_supplier_aging_report(
        cls,
        supplier_ids: Optional[List[int]] = None,
        as_of_date: Optional[Any] = None
    ) -> Dict[str, Any]:
        ref_date = as_of_date or timezone.now().date()
        suppliers = Supplier.objects.filter(is_active=True).select_related('financial_account')
        if supplier_ids:
            suppliers = suppliers.filter(pk__in=supplier_ids)

        report_rows = []
        summary = {
            'bucket_current': Decimal('0.00'),
            'bucket_0_30': Decimal('0.00'),
            'bucket_31_60': Decimal('0.00'),
            'bucket_61_90': Decimal('0.00'),
            'bucket_90_plus': Decimal('0.00'),
            'credit_balance': Decimal('0.00'),
            'total_balance': Decimal('0.00')
        }

        # FIN-CORE-015: Single-pass Batch Allocation Aggregation to eliminate N+1 queries
        from financial.models.allocation import PaymentAllocation
        from django.db.models import Sum

        alloc_totals = {
            item['target_document_id']: item['total']
            for item in PaymentAllocation.objects.filter(
                allocation_status='APPLIED'
            ).values('target_document_id').annotate(total=Sum('allocated_amount'))
        }

        for supplier in suppliers:
            if not supplier.financial_account:
                continue

            gl_data = LedgerQueryService.get_account_balance(supplier.financial_account, as_of_date=ref_date)
            net_balance = gl_data['balance']

            open_txns = SupplierTransaction.objects.filter(
                supplier=supplier,
                status__in=['OPEN', 'PARTIAL'],
                issue_date__lte=ref_date
            )

            bucket_current = Decimal('0.00')
            bucket_0_30 = Decimal('0.00')
            bucket_31_60 = Decimal('0.00')
            bucket_61_90 = Decimal('0.00')
            bucket_90_plus = Decimal('0.00')
            credit_bal = Decimal('0.00')

            for txn in open_txns:
                amt = txn.open_amount
                if txn.transaction_type in ['PAYMENT', 'DEBIT_NOTE', 'ADVANCE']:
                    credit_bal += amt
                    continue

                if txn.due_date > ref_date:
                    bucket_current += amt
                else:
                    overdue_days = (ref_date - txn.due_date).days
                    if overdue_days <= 30:
                        bucket_0_30 += amt
                    elif overdue_days <= 60:
                        bucket_31_60 += amt
                    elif overdue_days <= 90:
                        bucket_61_90 += amt
                    else:
                        bucket_90_plus += amt

            row_total = bucket_current + bucket_0_30 + bucket_31_60 + bucket_61_90 + bucket_90_plus - credit_bal

            report_rows.append({
                'supplier_id': supplier.id,
                'supplier_code': supplier.code,
                'supplier_name': supplier.name,
                'bucket_current': bucket_current,
                'bucket_0_30': bucket_0_30,
                'bucket_31_60': bucket_31_60,
                'bucket_61_90': bucket_61_90,
                'bucket_90_plus': bucket_90_plus,
                'credit_balance': credit_bal,
                'total_balance': net_balance or row_total
            })

            summary['bucket_current'] += bucket_current
            summary['bucket_0_30'] += bucket_0_30
            summary['bucket_31_60'] += bucket_31_60
            summary['bucket_61_90'] += bucket_61_90
            summary['bucket_90_plus'] += bucket_90_plus
            summary['credit_balance'] += credit_bal
            summary['total_balance'] += (net_balance or row_total)

        return {
            'as_of_date': ref_date,
            'rows': report_rows,
            'summary': summary
        }
