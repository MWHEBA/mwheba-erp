import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional
from django.utils import timezone
from django.db.models import Sum, Q, Value, DecimalField
from django.db.models.functions import Coalesce

from supplier.models import Supplier, SupplierAdvancePayment
from purchase.models import Purchase

logger = logging.getLogger("supplier.supplier_aging_service")


class SupplierAgingService:
    """
    محرك تقارير أعمار ديون الموردين المباشر الدقيق (Live Single-Source-of-Truth Aging Engine)
    يحسب شرائح الديون مباشرة من فواتير المشتريات المؤكدة (Purchase) والدفعات المقدمة غير المخصصة (SupplierAdvancePayment)
    بدون الاعتماد على جداول وسيطة أو مفاتيح خادعة.
    """

    @classmethod
    def get_supplier_open_item_aging(
        cls,
        supplier_ids: Optional[List[int]] = None,
        as_of_date: Optional[Any] = None
    ) -> Dict[str, Any]:
        return cls.get_supplier_aging_report(supplier_ids=supplier_ids, as_of_date=as_of_date)

    @classmethod
    def get_supplier_aging_report(
        cls,
        supplier_ids: Optional[List[int]] = None,
        as_of_date: Optional[Any] = None
    ) -> Dict[str, Any]:
        ref_date = as_of_date or timezone.now().date()
        suppliers = Supplier.objects.filter(is_active=True)
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

        for supplier in suppliers:
            # 1. جلب فواتير المشتريات المؤكدة والمفتوحة مع حساب المدفوع آلياً في query واحد
            open_bills = Purchase.objects.filter(
                supplier=supplier,
                status='confirmed',
                payment_status__in=['unpaid', 'partially_paid'],
                date__lte=ref_date
            ).annotate(
                paid_sum=Coalesce(
                    Sum('payments__amount', filter=Q(payments__status='posted')),
                    Value(Decimal('0.00'), output_field=DecimalField())
                )
            )

            bucket_current = Decimal('0.00')
            bucket_0_30 = Decimal('0.00')
            bucket_31_60 = Decimal('0.00')
            bucket_61_90 = Decimal('0.00')
            bucket_90_plus = Decimal('0.00')

            for bill in open_bills:
                amount_due = bill.total - bill.paid_sum
                if amount_due <= Decimal('0.00'):
                    continue

                days_old = (ref_date - bill.date).days
                if days_old <= 0:
                    bucket_current += amount_due
                elif days_old <= 30:
                    bucket_0_30 += amount_due
                elif days_old <= 60:
                    bucket_31_60 += amount_due
                elif days_old <= 90:
                    bucket_61_90 += amount_due
                else:
                    bucket_90_plus += amount_due

            # 2. حساب الرصيد الدائن المتاح (الدفعات المقدمة غير المخصصة للمورد)
            credit_bal = Decimal('0.00')
            advances = SupplierAdvancePayment.objects.filter(
                supplier=supplier,
                payment_date__lte=ref_date
            )
            for adv in advances:
                credit_bal += adv.remaining_amount

            debit_total = bucket_current + bucket_0_30 + bucket_31_60 + bucket_61_90 + bucket_90_plus
            net_balance = debit_total - credit_bal

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
                'net_balance': net_balance,
                'total_balance': net_balance
            })

            summary['bucket_current'] += bucket_current
            summary['bucket_0_30'] += bucket_0_30
            summary['bucket_31_60'] += bucket_31_60
            summary['bucket_61_90'] += bucket_61_90
            summary['bucket_90_plus'] += bucket_90_plus
            summary['credit_balance'] += credit_bal
            summary['total_balance'] += net_balance

        return {
            'as_of_date': ref_date,
            'rows': report_rows,
            'summary': summary
        }

    @classmethod
    def get_portfolio_aging_summary(cls, as_of_date: Optional[Any] = None) -> Dict[str, Any]:
        """
        توفير ملخص محفظة أعمار ديون الموردين الموحد لدعم التقارير المالية المركزية (FIN-REP-001)
        """
        report = cls.get_supplier_aging_report(as_of_date=as_of_date)
        summary = report.get('summary', {})
        total_outstanding = summary.get('total_balance', Decimal('0.00'))
        return {
            'as_of_date': report.get('as_of_date'),
            'total_outstanding': total_outstanding,
            'summary': summary
        }
