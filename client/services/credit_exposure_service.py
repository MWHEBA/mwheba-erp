import logging
from decimal import Decimal
from typing import Dict, Any, Optional
from django.db import models, transaction
from django.utils import timezone

from client.models import Customer, CustomerCreditProfile, CustomerCreditStatusHistory, CreditAuditLog
from client.services.customer_subledger_service import CustomerSubledgerService
from client.services.credit_decision import CreditDecision, CreditDecisionType
from sale.models.sales_models import SalesOrder
from financial.services.exchange_rate_service import ExchangeRateService

logger = logging.getLogger("client.services.credit_exposure_service")


class CreditExposureService:
    """
    FIN-AR-001: Customer Credit Governance Engine Service (v6.0 Locked Master Authority)
    سلطة فحص وتدقيق حدود الائتمان المحوكمة بالربط الحصري مع واجهة CustomerSubledgerService API
    """

    @classmethod
    def calculate_customer_exposure(cls, customer_id: int) -> Dict[str, Any]:
        """
        Subledger API Boundary Enforcement:
        احتساب التعرض الائتماني الكلي بالاستعلام الحصري للرصيد المفتوح عبر CustomerSubledgerService.get_customer_open_balance
        Formula: Total Exposure = CustomerSubledgerService.get_customer_open_balance + Pending Approved Sales Orders
        """
        customer = Customer.objects.get(pk=customer_id)

        # 1. Open Subledger Balance via API (NO direct ORM calls to CustomerTransaction outside Subledger API)
        open_ar_amount = CustomerSubledgerService.get_customer_open_balance(customer_id)

        # 2. Pending & Approved Uninvoiced Sales Orders
        pending_orders = SalesOrder.objects.filter(
            customer_id=customer_id,
            status__in=["DRAFT", "PENDING_APPROVAL", "APPROVED", "CONFIRMED", "PARTIALLY_DELIVERED", "PARTIALLY_INVOICED"]
        )
        pending_orders_amount = pending_orders.aggregate(total=models.Sum("functional_amount"))["total"] or Decimal("0.00")

        total_exposure = open_ar_amount + pending_orders_amount

        # Get or create default Credit Profile
        profile, _ = CustomerCreditProfile.objects.get_or_create(
            customer=customer,
            defaults={"credit_limit": customer.credit_limit or Decimal("0.00")}
        )

        limit_func = profile.credit_limit
        if profile.currency != "EGP":
            spot_rate = ExchangeRateService.get_rate(profile.currency, "EGP")
            limit_func = (profile.credit_limit * spot_rate).quantize(Decimal("0.01"))

        avail_credit = limit_func - total_exposure

        return {
            "customer_id": customer_id,
            "credit_limit": profile.credit_limit,
            "credit_limit_functional": limit_func,
            "currency": profile.currency,
            "open_ar_amount": open_ar_amount,
            "pending_orders_amount": pending_orders_amount,
            "total_exposure": total_exposure,
            "available_credit": avail_credit,
            "credit_status": profile.credit_status,
            "risk_category": profile.risk_category
        }

    @classmethod
    def evaluate_credit_check(
        cls,
        customer_id: int,
        requested_amount: Decimal,
        currency: str = "EGP"
    ) -> CreditDecision:
        """
        Transactional Scoped Row Locking Credit Decision Engine:
        تنفيذ قرار الائتمان الحاكم بقفل الصفوف `select_for_update` وإرجاع كائن CreditDecision المحوكم
        """
        with transaction.atomic():
            customer = Customer.objects.select_for_update().get(pk=customer_id)

            func_req_amount = requested_amount
            if currency != "EGP":
                spot_rate = ExchangeRateService.get_rate(currency, "EGP")
                func_req_amount = (requested_amount * spot_rate).quantize(Decimal("0.01"))

            exposure = cls.calculate_customer_exposure(customer_id)
            status = exposure["credit_status"]
            limit_func = exposure["credit_limit_functional"]
            avail_credit = exposure["available_credit"]
            current_exp = exposure["total_exposure"]

            # 1. Hard Hold or Blocked Status Check
            if status in ["ON_HOLD", "BLOCKED"]:
                return CreditDecision(
                    decision=CreditDecisionType.BLOCKED,
                    reason=f"Customer '{customer.name}' is on credit status '{status}'. Operations are blocked.",
                    current_exposure=current_exp,
                    available_credit=avail_credit,
                    credit_limit=limit_func,
                    requested_amount=func_req_amount,
                    requires_approval=False
                )

            # 2. Credit Limit Exceeded Check
            new_total = current_exp + func_req_amount
            if new_total > limit_func:
                return CreditDecision(
                    decision=CreditDecisionType.REQUIRES_APPROVAL,
                    reason=f"New exposure ({new_total} EGP) exceeds authorized limit ({limit_func} EGP). Requires Credit Approval.",
                    current_exposure=current_exp,
                    available_credit=avail_credit,
                    credit_limit=limit_func,
                    requested_amount=func_req_amount,
                    requires_approval=True,
                    approval_type="CREDIT"
                )

            # 3. Approved
            return CreditDecision(
                decision=CreditDecisionType.APPROVED,
                reason="Credit check passed.",
                current_exposure=current_exp,
                available_credit=avail_credit,
                credit_limit=limit_func,
                requested_amount=func_req_amount,
                requires_approval=False
            )

    @classmethod
    def check_credit_limit(
        cls,
        customer_id: int,
        new_order_amount: Decimal,
        currency: str = "EGP"
    ) -> Dict[str, Any]:
        """
        Legacy dictionary adapter wrapping evaluate_credit_check for backward compatibility
        """
        decision = cls.evaluate_credit_check(customer_id, new_order_amount, currency)
        return {
            "is_allowed": decision.is_allowed,
            "is_blocked": decision.is_blocked,
            "requires_approval": decision.requires_approval,
            "reason": decision.reason,
            "decision_type": decision.decision.value,
            "exposure": {
                "total_exposure": decision.current_exposure,
                "credit_limit_functional": decision.credit_limit,
                "available_credit": decision.available_credit
            }
        }

    @classmethod
    def update_credit_status(
        cls,
        customer_id: int,
        new_status: str,
        reason: str,
        user=None,
        related_document: Optional[str] = None
    ) -> CustomerCreditProfile:
        """
        تحديث حالة الائتمان وتسجيل سجل التحول التاريخي والتدقيق
        """
        with transaction.atomic():
            profile, _ = CustomerCreditProfile.objects.select_for_update().get_or_create(customer_id=customer_id)
            old_stat = profile.credit_status
            profile.credit_status = new_status
            profile.save()

            try:
                CustomerCreditStatusHistory.objects.create(
                    customer_id=customer_id,
                    old_status=old_stat,
                    new_status=new_status,
                    reason=reason,
                    created_by=user
                )
            except Exception as history_err:
                logger.warning(f"Could not log CustomerCreditStatusHistory: {history_err}")

            CreditAuditLog.objects.create(
                customer_id=customer_id,
                old_status=old_stat,
                new_status=new_status,
                reason=reason,
                user=user,
                related_document=related_document
            )

            logger.info(f"Credit status updated for customer {customer_id}: {old_stat} -> {new_status}.")
            return profile
