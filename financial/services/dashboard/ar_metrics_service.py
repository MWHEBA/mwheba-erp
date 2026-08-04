import logging
from decimal import Decimal
from typing import Optional, Any
from django.db.models import Sum, Q
from django.utils import timezone

from client.models import CustomerTransaction, Customer
from presentation.dto.dashboard_dto import ARMetricsDTO

logger = logging.getLogger("financial.services.dashboard.ar_metrics_service")


class ARMetricsService:
    """
    FIN-EEL: Accounts Receivable Metrics Aggregation Sub-Service
    """

    @classmethod
    def get_ar_metrics(cls, as_of_date: Optional[Any] = None) -> ARMetricsDTO:
        ref_date = as_of_date or timezone.now().date()

        open_txs = CustomerTransaction.objects.filter(status="OPEN")
        total_open = open_txs.aggregate(total=Sum("open_amount"))["total"] or Decimal("0.00")

        overdue_txs = open_txs.filter(due_date__lt=ref_date)
        overdue_ar = overdue_txs.aggregate(total=Sum("open_amount"))["total"] or Decimal("0.00")

        cust_count = CustomerTransaction.objects.filter(status="OPEN").values("customer").distinct().count()

        b_0_30 = Decimal("0.00")
        b_31_60 = Decimal("0.00")
        b_61_90 = Decimal("0.00")
        b_90_plus = Decimal("0.00")

        for tx in open_txs:
            if tx.due_date:
                days_old = (ref_date - tx.due_date).days
                amt = tx.open_amount or Decimal("0.00")
                if days_old <= 30:
                    b_0_30 += amt
                elif days_old <= 60:
                    b_31_60 += amt
                elif days_old <= 90:
                    b_61_90 += amt
                else:
                    b_90_plus += amt

        return ARMetricsDTO(
            total_open_ar=total_open,
            overdue_ar=overdue_ar,
            customer_count_with_balance=cust_count,
            bucket_0_30=b_0_30,
            bucket_31_60=b_31_60,
            bucket_61_90=b_61_90,
            bucket_90_plus=b_90_plus,
            currency="EGP"
        )
