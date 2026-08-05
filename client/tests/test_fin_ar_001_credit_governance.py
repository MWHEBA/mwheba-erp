import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from client.models import Customer, CustomerCreditProfile, CreditAuditLog
from client.services.credit_exposure_service import CreditExposureService
from client.services.customer_subledger_service import CustomerSubledgerService
from product.models.product_core import Product, Category, Unit
from product.models.stock_management import Warehouse
from sale.services.sales_service import SalesService

User = get_user_model()


@pytest.mark.django_db(transaction=True)
class TestFINAR001CustomerCreditGovernance:

    @pytest.fixture
    def setup_credit_governance_data(self):
        user = User.objects.create_user(username="cred_user1", email="cred1@example.com", password="password123")
        customer = Customer.objects.create(name="Apex Distribution", code="CUST-CR-001", credit_limit=Decimal("50000.00"))
        customer.refresh_from_db()

        profile, _ = CustomerCreditProfile.objects.get_or_create(
            customer=customer,
            defaults={"credit_limit": Decimal("50000.00"), "credit_status": "ACTIVE"}
        )

        from financial.models.approval import EnterpriseApprovalRule
        EnterpriseApprovalRule.objects.create(
            module="CREDIT",
            rule_name="Credit Override Approval",
            min_amount=Decimal("0.00"),
            max_amount=Decimal("99999999.00"),
            approver_role="CREDIT_MANAGER"
        )

        category = Category.objects.create(name="Hardware")
        unit = Unit.objects.create(name="PCS")
        product = Product.objects.create(name="Server Rack 42U", category=category, unit=unit, cost_price=Decimal("1000.00"), selling_price=Decimal("1500.00"), created_by=user)
        warehouse = Warehouse.objects.create(code="WH-CREDIT", name="Credit Test Warehouse", is_active=True)

        return user, customer, profile, product, warehouse

    def test_credit_exposure_calculation(self, setup_credit_governance_data):
        user, customer, profile, product, warehouse = setup_credit_governance_data

        # Register open invoice of 20,000 EGP
        CustomerSubledgerService.register_open_item_transaction(
            customer=customer,
            transaction_type="INVOICE",
            transaction_number="INV-CR-001",
            issue_date=timezone.now().date(),
            due_date=timezone.now().date(),
            functional_amount=Decimal("20000.00")
        )

        exposure = CreditExposureService.calculate_customer_exposure(customer.id)
        assert exposure["open_ar_amount"] == Decimal("20000.00")
        assert exposure["total_exposure"] == Decimal("20000.00")
        assert exposure["available_credit"] == Decimal("30000.00")

    def test_sales_order_credit_check_blocking(self, setup_credit_governance_data):
        user, customer, profile, product, warehouse = setup_credit_governance_data

        # Attempt SO of 60,000 EGP (Exceeds 50,000 limit)
        items_data = [{"product": product, "ordered_qty": Decimal("40.0000"), "unit_price": Decimal("1500.00")}]
        so = SalesService.create_sales_order(customer=customer, warehouse=warehouse, order_date=timezone.now().date(), items_data=items_data, user=user)

        assert so.status == "PENDING_APPROVAL"
        assert so.approval_request is not None
        assert so.approval_request.module == "CREDIT"

    def test_credit_status_update_audit_log(self, setup_credit_governance_data):
        user, customer, profile, product, warehouse = setup_credit_governance_data

        updated = CreditExposureService.update_credit_status(
            customer_id=customer.id,
            new_status="ON_HOLD",
            reason="High risk overdue balance",
            user=user
        )

        assert updated.credit_status == "ON_HOLD"
        assert CreditAuditLog.objects.filter(customer=customer).count() == 1
