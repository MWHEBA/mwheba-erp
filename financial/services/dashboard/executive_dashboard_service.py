import logging
from decimal import Decimal
from typing import Optional, Any
from django.utils import timezone
from django.db.models import Sum

from financial.services.dashboard.ar_metrics_service import ARMetricsService
from financial.services.dashboard.inventory_metrics_service import InventoryMetricsService
from financial.services.dashboard.tax_metrics_service import TaxMetricsService
from presentation.dto.dashboard_dto import ExecutiveDashboardDTO
from financial.models.approval import EnterpriseApprovalRequest
from sale.models import SalesInvoice

logger = logging.getLogger("financial.services.dashboard.executive_dashboard_service")


class ExecutiveDashboardService:
    """
    FIN-EEL: Executive Dashboard Orchestrator Service
    """

    @classmethod
    def get_executive_dashboard(cls, as_of_date: Optional[Any] = None) -> ExecutiveDashboardDTO:
        ref_date = as_of_date or timezone.now().date()

        ar_metrics = ARMetricsService.get_ar_metrics(as_of_date=ref_date)
        inv_metrics = InventoryMetricsService.get_inventory_metrics()
        tax_metrics = TaxMetricsService.get_tax_metrics()

        pending_approvals = EnterpriseApprovalRequest.objects.filter(status="PENDING").count()

        first_day_of_month = ref_date.replace(day=1)
        mtd_invoices = SalesInvoice.objects.filter(invoice_date__gte=first_day_of_month, invoice_date__lte=ref_date, status="POSTED")

        rev_mtd = mtd_invoices.aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")
        cogs_mtd = (rev_mtd * Decimal("0.50")).quantize(Decimal("0.01"))  # 50% estimated COGS
        gp_mtd = rev_mtd - cogs_mtd

        return ExecutiveDashboardDTO(
            as_of_date=ref_date.isoformat(),
            ar_metrics=ar_metrics,
            inventory_metrics=inv_metrics,
            tax_metrics=tax_metrics,
            pending_approvals_count=pending_approvals,
            total_revenue_mtd=rev_mtd,
            total_cogs_mtd=cogs_mtd,
            gross_profit_mtd=gp_mtd,
            currency="EGP"
        )
