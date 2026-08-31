from decimal import Decimal
from typing import Dict, Any, Optional, List
from django.db import transaction
from django.utils import timezone
from financial.models.approval import (
    EnterpriseApprovalRule,
    EnterpriseApprovalRequest,
    EnterpriseApprovalStep,
    EnterpriseApprovalAuditLog,
)
from financial.services.exchange_rate_service import ExchangeRateService
from financial.exceptions import FinancialCoreError


class ApprovalService:
    """
    FIN-CORE-017: Enterprise Approval Workflow Engine Service
    خدمة محرك الموافقات المركزية المحوكمة بتطبيق مبدأ فصل المهام SOD وتحويل أسعار الصرف للعملة الأجنبية
    """

    @classmethod
    def check_and_create_approval_request(
        cls,
        module: str,
        reference_id: str,
        amount: Decimal,
        currency: str = "EGP",
        user=None
    ) -> Optional[EnterpriseApprovalRequest]:
        """
        تقييم حدود القواعد بالعملة الوظيفية وإنشاء طلب الاعتماد وخطوات الاعتماد
        """
        # Convert amount to functional EGP using ExchangeRateService if foreign
        func_amount = amount
        if currency != "EGP":
            spot_rate = ExchangeRateService.get_rate(currency, "EGP")
            func_amount = (amount * spot_rate).quantize(Decimal("0.01"))

        rules = EnterpriseApprovalRule.objects.filter(
            module=module,
            min_amount__lte=func_amount,
            max_amount__gte=func_amount,
            is_active=True
        ).order_by("approval_level")

        if not rules.exists():
            return None

        primary_rule = rules.first()

        with transaction.atomic():
            app_req = EnterpriseApprovalRequest.objects.create(
                module=module,
                reference_id=str(reference_id),
                rule=primary_rule,
                requested_by=user,
                status="PENDING",
                comments=f"Requires approval for amount {amount} {currency} (Functional: {func_amount} EGP)"
            )

            # Create steps for each rule level
            for idx, r in enumerate(rules, start=1):
                EnterpriseApprovalStep.objects.create(
                    approval_request=app_req,
                    sequence=idx,
                    approver_role=r.approver_role,
                    status="PENDING"
                )

            EnterpriseApprovalAuditLog.objects.create(
                approval_request=app_req,
                old_status="DRAFT",
                new_status="PENDING",
                action_by=user,
                comments="Approval request submitted"
            )

            return app_req

    @classmethod
    def approve_request(cls, request_id: int, user, comments: str = "") -> EnterpriseApprovalRequest:
        """
        اعتماد الطلب مع التحقق من SOD (فصل المهام)
        """
        with transaction.atomic():
            req = EnterpriseApprovalRequest.objects.select_for_update().get(pk=request_id)

            # Segregation of Duties Enforcement (SOD)
            if user and req.requested_by_id and req.requested_by_id == user.id:
                raise FinancialCoreError("Segregation of Duties Violation: Requester cannot approve their own approval request.")

            if req.status != "PENDING":
                raise FinancialCoreError(f"Cannot approve request #{req.id} in status {req.status}.")

            old_stat = req.status

            # Advance current step
            pending_step = req.steps.filter(status="PENDING").order_by("sequence").first()
            if pending_step:
                pending_step.status = "APPROVED"
                pending_step.action_by = user
                pending_step.action_at = timezone.now()
                pending_step.comments = comments
                pending_step.save()

            # Check remaining steps
            remaining = req.steps.filter(status="PENDING").exists()
            if not remaining:
                req.status = "APPROVED"
                req.approved_by = user
                req.approved_at = timezone.now()
                req.comments = comments or req.comments
                req.save()
                cls._dispatch_approval_event(req, user)

            EnterpriseApprovalAuditLog.objects.create(
                approval_request=req,
                old_status=old_stat,
                new_status=req.status,
                action_by=user,
                comments=comments or "Step approved"
            )

            return req

    @classmethod
    def _dispatch_approval_event(cls, req: EnterpriseApprovalRequest, user) -> None:
        """تحديث المستند الأصلي آلياً عند اكتمال الاعتماد"""
        try:
            if req.module == "SALES" and req.reference_id:
                from sale.models.sales_order import SalesOrder
                from sale.services.inventory_reservation_service import InventoryReservationService
                so = SalesOrder.objects.filter(pk=int(req.reference_id)).first()
                if so and so.status == "PENDING_APPROVAL":
                    so.status = "APPROVED"
                    so.approved_by = user
                    so.approved_at = timezone.now()
                    so.save(update_fields=["status", "approved_by", "approved_at"])
                    # حجز المخزون تلقائياً
                    InventoryReservationService.reserve_sales_order_lines(so.id, user=user)

            elif req.module == "PURCHASE" and req.reference_id:
                from purchase.models.procurement_models import PurchaseOrder
                po = PurchaseOrder.objects.filter(pk=int(req.reference_id)).first()
                if po and po.status in ["SUBMITTED", "PENDING"]:
                    po.status = "APPROVED"
                    po.approved_by = user
                    po.approved_at = timezone.now()
                    po.save(update_fields=["status", "approved_by", "approved_at"])

            elif req.module == "CREDIT" and req.reference_id:
                from customer.models import CustomerCreditStatusHistory
                CustomerCreditStatusHistory.objects.create(
                    customer_id=int(req.reference_id),
                    old_status="OVER_LIMIT_PENDING",
                    new_status="ACTIVE_OVERRIDE",
                    reason=f"Enterprise Approval #{req.id}: {req.comments or 'Approved by management'}",
                    created_by=user
                )
        except Exception as e:
            logger.error(f"Failed to dispatch approval event for req #{req.id}: {e}", exc_info=True)

    @classmethod
    def reject_request(cls, request_id: int, user, comments: str = "") -> EnterpriseApprovalRequest:
        """
        رفض الطلب وإعادة تعيين الحالة لـ REJECTED
        """
        with transaction.atomic():
            req = EnterpriseApprovalRequest.objects.select_for_update().get(pk=request_id)

            if req.status != "PENDING":
                raise FinancialCoreError(f"Cannot reject request #{req.id} in status {req.status}.")

            old_stat = req.status
            req.status = "REJECTED"
            req.approved_by = user
            req.approved_at = timezone.now()
            req.comments = comments or req.comments
            req.save()

            # Mark remaining steps as REJECTED
            req.steps.filter(status="PENDING").update(
                status="REJECTED",
                action_by=user,
                action_at=timezone.now(),
                comments=comments
            )

            cls._dispatch_rejection_event(req, user)

            EnterpriseApprovalAuditLog.objects.create(
                approval_request=req,
                old_status=old_stat,
                new_status="REJECTED",
                action_by=user,
                comments=comments or "Approval request rejected"
            )

            return req

    @classmethod
    def _dispatch_rejection_event(cls, req: EnterpriseApprovalRequest, user) -> None:
        """تحديث المستند الأصلي آلياً عند رفض الطلب"""
        try:
            if req.module == "SALES" and req.reference_id:
                from sale.models.sales_order import SalesOrder
                so = SalesOrder.objects.filter(pk=int(req.reference_id)).first()
                if so and so.status == "PENDING_APPROVAL":
                    so.status = "REJECTED"
                    so.save(update_fields=["status"])

            elif req.module == "PURCHASE" and req.reference_id:
                from purchase.models.procurement_models import PurchaseOrder
                po = PurchaseOrder.objects.filter(pk=int(req.reference_id)).first()
                if po and po.status in ["SUBMITTED", "PENDING"]:
                    po.status = "REJECTED"
                    po.save(update_fields=["status"])
        except Exception as e:
            logger.error(f"Failed to dispatch rejection event for req #{req.id}: {e}", exc_info=True)

    @classmethod
    def is_approved(cls, module: str, reference_id: str) -> bool:
        """
        الاستعلام عن حالة موافقة مستند معين
        """
        req = EnterpriseApprovalRequest.objects.filter(module=module, reference_id=str(reference_id)).first()
        if not req:
            return True  # No approval rule was required
        return req.status == "APPROVED"
