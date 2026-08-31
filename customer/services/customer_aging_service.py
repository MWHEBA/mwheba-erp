import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional
from django.utils import timezone
from django.db.models import Sum, Q, Value, DecimalField, Subquery, OuterRef
from django.db.models.functions import Coalesce

from customer.models import Customer, CustomerPayment
from sale.models import Sale, SalePayment

logger = logging.getLogger("customer.customer_aging_service")


class CustomerAgingService:
    """
    محرك تقارير أعمار ديون العملاء المباشر الدقيق (Live Single-Source-of-Truth Aging Engine)
    يحسب شرائح الديون مباشرة من فواتير المبيعات المكتملة (Sale) والدفعات المقدمة غير المخصصة (CustomerPayment)
    بدون الاعتماد على جداول وسيطة أو مفاتيح خادعة.
    """

    @classmethod
    def get_customer_open_item_aging(cls, *args, **kwargs):
        """Alias for get_customer_aging_report for backward compatibility"""
        return cls.get_customer_aging_report(*args, **kwargs)

    @classmethod
    def get_customer_aging_report(
        cls,
        customer_ids: Optional[List[int]] = None,
        as_of_date: Optional[Any] = None
    ) -> Dict[str, Any]:
        ref_date = as_of_date or timezone.now().date()
        customers = Customer.objects.filter(is_active=True)
        if customer_ids:
            customers = customers.filter(pk__in=customer_ids)

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

        # 1. Subquery لحساب المبالغ المستخدمة من الدفعات المقدمة
        used_subq = (
            SalePayment.objects.filter(
                customer_payment=OuterRef("pk"), status="posted"
            )
            .values("customer_payment")
            .annotate(s=Sum("amount"))
            .values("s")
        )

        for customer in customers:
            # 2. جلب جميع الفواتير المؤكدة والمفتوحة للعميل مع حساب المدفوع آلياً (Single Query)
            open_sales = Sale.objects.filter(
                customer=customer,
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

            for sale in open_sales:
                amount_due = sale.total - sale.paid_sum
                if amount_due <= Decimal('0.00'):
                    continue

                days_old = (ref_date - sale.date).days
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

            # 3. حساب الرصيد الدائن المتاح (الدفعات المقدمة غير المخصصة)
            credit_bal = Decimal('0.00')
            payments = CustomerPayment.objects.filter(
                customer=customer,
                payment_date__lte=ref_date
            ).exclude(status="cancelled").annotate(
                used=Coalesce(
                    Subquery(used_subq, output_field=DecimalField()),
                    Value(Decimal('0.00'), output_field=DecimalField()),
                )
            )
            for cp in payments:
                credit_bal += max(Decimal('0.00'), cp.amount - cp.used)

            debit_total = bucket_current + bucket_0_30 + bucket_31_60 + bucket_61_90 + bucket_90_plus
            net_balance = debit_total - credit_bal

            report_rows.append({
                'customer_id': customer.id,
                'customer_code': customer.code,
                'customer_name': customer.name,
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
        توفير ملخص محفظة أعمار ديون العملاء الموحد لدعم التقارير المالية المركزية (FIN-REP-001)
        """
        report = cls.get_customer_aging_report(as_of_date=as_of_date)
        summary = report.get('summary', {})
        total_outstanding = summary.get('total_balance', Decimal('0.00'))
        return {
            'as_of_date': report.get('as_of_date'),
            'total_outstanding': total_outstanding,
            'summary': summary
        }
