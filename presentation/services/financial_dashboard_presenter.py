import logging
from typing import Dict, Any, Optional
from financial.services.dashboard.executive_dashboard_service import ExecutiveDashboardService
from presentation.dto.dashboard_dto import ExecutiveDashboardDTO

logger = logging.getLogger("presentation.services.financial_dashboard_presenter")


class FinancialDashboardPresenter:
    """
    FIN-EEL: Executive Financial Dashboard Presenter Service
    """

    @classmethod
    def get_executive_dashboard_presentation(cls, as_of_date: Optional[Any] = None) -> ExecutiveDashboardDTO:
        return ExecutiveDashboardService.get_executive_dashboard(as_of_date=as_of_date)
