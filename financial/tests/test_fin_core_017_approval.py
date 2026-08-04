import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model

from financial.models.approval import (
    EnterpriseApprovalRule,
    EnterpriseApprovalRequest,
    EnterpriseApprovalStep,
    EnterpriseApprovalAuditLog,
)
from financial.services.approval_service import ApprovalService
from financial.exceptions import FinancialCoreError

User = get_user_model()


@pytest.mark.django_db(transaction=True)
class TestFINCORE017EnterpriseApprovalWorkflow:

    @pytest.fixture
    def setup_approval_data(self):
        user_req = User.objects.create_user(username="req_user17", email="req17@example.com", password="password123")
        user_appr = User.objects.create_user(username="appr_user17", email="appr17@example.com", password="password123")

        rule1 = EnterpriseApprovalRule.objects.create(
            module="SALES",
            rule_name="Level 1 Sales Approval",
            min_amount=Decimal("50000.00"),
            max_amount=Decimal("500000.00"),
            approver_role="MANAGER",
            approval_level=1
        )
        rule2 = EnterpriseApprovalRule.objects.create(
            module="SALES",
            rule_name="Level 2 Sales Approval",
            min_amount=Decimal("50000.00"),
            max_amount=Decimal("500000.00"),
            approver_role="CTO",
            approval_level=2
        )
        return user_req, user_appr, rule1, rule2

    def test_check_and_create_approval_request_multi_level(self, setup_approval_data):
        user_req, user_appr, rule1, rule2 = setup_approval_data

        app_req = ApprovalService.check_and_create_approval_request("SALES", "SO-100", Decimal("60000.00"), "EGP", user_req)
        assert app_req is not None
        assert app_req.status == "PENDING"
        assert app_req.steps.count() == 2

    def test_segregation_of_duties_enforcement(self, setup_approval_data):
        user_req, user_appr, rule1, rule2 = setup_approval_data

        app_req = ApprovalService.check_and_create_approval_request("SALES", "SO-101", Decimal("75000.00"), "EGP", user_req)

        # Requester cannot approve their own request
        with pytest.raises(FinancialCoreError, match="Segregation of Duties Violation"):
            ApprovalService.approve_request(app_req.id, user_req, "Self approval attempt")

        # Authorized non-requester can approve
        approved = ApprovalService.approve_request(app_req.id, user_appr, "Commercial terms verified")
        assert approved.steps.first().status == "APPROVED"
        assert EnterpriseApprovalAuditLog.objects.filter(approval_request=app_req).count() >= 2
