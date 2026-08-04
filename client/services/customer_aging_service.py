"""
CustomerAgingService - محرك اعمار ديون العملاء المتقدم (Sprint 3 Due-Date Aging Engine)
يحسب شرائح الديون المستحقة بناءً على تواريخ استحقاق الفواتير (due_date) والرصيد غير المسدد صراحة (FIN-SUB-001)
يعزل الأرصدة الدائنة (credit_balance) والمبالغ المقدمة بشكل مستقل عن شرائح التأخير الموجبة.
"""

import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional
from django.utils import timezone

from client.models import Customer
from sale.models import Sale
from financial.services.allocation_service import AllocationService
from financial.services.ledger_query_service import LedgerQueryService

logger = logging.getLogger("client.customer_aging_service")


class CustomerAgingService:
    """
    خدمة حساب تقرير أعمار ديون العملاء المعيارية (Open-Item Due-Date Aging)
    """

    @classmethod
    def get_customer_open_item_aging(
        cls,
        customer_ids: Optional[List[int]] = None,
        as_of_date: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        توليد تقرير أعمار الديون التفصيلي الموزع حسب تواريخ الاستحقاق وعزل المبالغ الدائنة
        """
        ref_date = as_of_date or timezone.now().date()
        customers = Customer.objects.filter(is_active=True).select_related('financial_account')
        if customer_ids:
            customers = customers.filter(pk__in=customer_ids)

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

        # (FIN-CORE-015 Batch Query Optimization): Query all allocation totals in a single batch aggregate
        from financial.models import PaymentAllocation
        from django.db.models import Sum

        alloc_map = dict(
            PaymentAllocation.objects.filter(
                debit_document_type="SALE_INVOICE"
            ).values('debit_document_id').annotate(
                total_allocated=Sum('allocated_amount')
            ).values_list('debit_document_id', 'total_allocated')
        )

        for customer in customers:
            # حساب الرصيد الإجمالي من دفتر الأستاذ العام أو مديونية العميل
            if customer.financial_account:
                bal_data = LedgerQueryService.get_account_balance(customer.financial_account, as_of_date=ref_date)
                net_balance = bal_data.get('balance', getattr(customer, 'balance', Decimal('0.00')))
            else:
                net_balance = getattr(customer, 'balance', Decimal('0.00')) or Decimal('0.00')

            # استعلام فواتير العميل غير المسددة بالكامل حتى تاريخ التقرير
            sales = Sale.objects.filter(
                customer=customer,
                created_at__date__lte=ref_date
            ).exclude(status="cancelled")

            not_due = Decimal('0.00')
            days_1_30 = Decimal('0.00')
            days_31_60 = Decimal('0.00')
            days_61_90 = Decimal('0.00')
            days_90_plus = Decimal('0.00')
            total_unpaid_invoices = Decimal('0.00')

            from datetime import timedelta

            for sale in sales:
                # الفواتير المدفوعة بالكامل يتم تجاوزها
                if sale.payment_status == "paid" or getattr(sale, "is_fully_paid", False):
                    continue

                doc_total = sale.total or Decimal('0.00')
                amount_paid = Decimal('0.00')
                try:
                    amount_paid = sale.amount_paid or Decimal('0.00')
                except Exception:
                    pass

                total_allocated = alloc_map.get(str(sale.id), Decimal('0.00'))
                effective_paid = max(amount_paid, total_allocated)
                outstanding = max(Decimal('0.00'), doc_total - effective_paid)

                if outstanding <= Decimal('0.00'):
                    continue

                total_unpaid_invoices += outstanding

                # احتساب تاريخ الاستحقاق بناءً على شروط الدفع للعميل
                due_date = getattr(sale, 'due_date', None)
                if not due_date:
                    payment_term = getattr(customer, 'payment_term', None)
                    term_days = getattr(payment_term, 'days', 0) if payment_term else 0
                    sale_date = getattr(sale, 'date', None) or sale.created_at.date()
                    if term_days > 0:
                        due_date = sale_date + timedelta(days=term_days)
                    else:
                        due_date = sale_date

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

            # عزل الرصيد الدائن المتبقي (Unapplied Credit Balance / Prepayments)
            credit_balance = Decimal('0.00')
            if net_balance < total_unpaid_invoices:
                credit_balance = total_unpaid_invoices - net_balance
            elif net_balance < Decimal('0.00'):
                credit_balance = abs(net_balance)

            report_rows.append({
                'customer_id': customer.id,
                'customer_code': getattr(customer, 'code', str(customer.id)),
                'customer_name': customer.name,
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
