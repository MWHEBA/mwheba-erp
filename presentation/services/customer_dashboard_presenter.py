import logging
from decimal import Decimal
from typing import Dict, Any, Optional
from client.models import Customer, CustomerTransaction, CustomerCreditProfile
from client.services.customer_subledger_service import CustomerSubledgerService
from presentation.dto.dashboard_dto import ARMetricsDTO

logger = logging.getLogger("presentation.services.customer_dashboard_presenter")


class CustomerDashboardPresenter:
    """
    FIN-EEL: Customer UI Presentation Service
    تحضير سقف الائتمان ومؤشرات مخاطر العملاء للشاشات المؤسسية
    """

    @classmethod
    def get_customer_dashboard_data(cls, customer_id: int) -> Dict[str, Any]:
        customer = Customer.objects.get(pk=customer_id)
        bal_data = CustomerSubledgerService.get_customer_balance(customer_id)
        open_balance = bal_data.get("balance", Decimal("0.00"))

        credit_limit = customer.credit_limit or Decimal("0.00")
        available_credit = max(Decimal("0.00"), credit_limit - open_balance)

        utilization_pct = (open_balance / credit_limit * Decimal("100.0")) if credit_limit > Decimal("0.00") else Decimal("0.0")

        profile = CustomerCreditProfile.objects.filter(customer=customer).first()
        status_code = profile.credit_status if profile else "ACTIVE"
        risk_level = profile.risk_category if profile else "MEDIUM"
        is_on_hold = getattr(customer, "is_on_hold", status_code == "ON_HOLD")

        return {
            "customer_id": customer.id,
            "customer_name": customer.name,
            "customer_code": customer.code,
            "credit_limit": credit_limit,
            "open_balance": open_balance,
            "available_credit": available_credit,
            "utilization_percentage": utilization_pct.quantize(Decimal("0.1")),
            "status_code": status_code,
            "risk_level": risk_level,
            "is_on_hold": is_on_hold,
            "currency": "EGP"
        }
