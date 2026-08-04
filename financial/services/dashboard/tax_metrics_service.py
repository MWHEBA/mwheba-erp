import logging
from decimal import Decimal
from django.db.models import Sum
from financial.models import TaxDeterminationAudit
from presentation.dto.dashboard_dto import TaxMetricsDTO

logger = logging.getLogger("financial.services.dashboard.tax_metrics_service")


class TaxMetricsService:
    """
    FIN-EEL: Statutory Tax Metrics Aggregation Sub-Service
    """

    @classmethod
    def get_tax_metrics(cls) -> TaxMetricsDTO:
        audits = TaxDeterminationAudit.objects.filter(audit_status="POSTED")

        out_vat = audits.filter(tax_code__tax_nature="OUTPUT").aggregate(total=Sum("functional_tax_amount"))["total"] or Decimal("0.00")
        in_vat = audits.filter(tax_code__tax_nature="INPUT").aggregate(total=Sum("functional_tax_amount"))["total"] or Decimal("0.00")

        net_vat = out_vat - in_vat

        total_audits = TaxDeterminationAudit.objects.count()
        valid_audits = TaxDeterminationAudit.objects.filter(audit_status__in=["CALCULATED", "POSTED"]).count()
        pass_rate = (valid_audits / total_audits * 100.0) if total_audits > 0 else 100.0

        return TaxMetricsDTO(
            output_vat_total=out_vat,
            input_vat_total=in_vat,
            net_vat_liability=net_vat,
            audit_verification_pass_rate=pass_rate,
            currency="EGP"
        )
