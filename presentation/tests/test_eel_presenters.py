import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from customer.models import Customer, CustomerCreditProfile
from financial.models import ChartOfAccounts, AccountType
from presentation.services.customer_dashboard_presenter import CustomerDashboardPresenter
from presentation.services.financial_dashboard_presenter import FinancialDashboardPresenter
from presentation.services.document_financial_presenter import DocumentFinancialPresenter
from presentation.dto import (
    ExecutiveDashboardDTO,
    ARMetricsDTO,
    InventoryMetricsDTO,
    TaxMetricsDTO,
    DocumentFinancialBreakdownDTO,
)

User = get_user_model()


@pytest.mark.django_db(transaction=True)
class TestEELPresenters:

    @pytest.fixture
    def setup_eel_data(self):
        import uuid
        uid = uuid.uuid4().hex[:6]
        user = User.objects.create_user(username=f"eel_user_{uid}", email=f"eel_{uid}@example.com", password="password123")
        asset_type = AccountType.objects.filter(code="ASSET").first() or AccountType.objects.create(code=f"ASSET_{uid}", name="Assets", category="ASSET")
        acc, _ = ChartOfAccounts.objects.get_or_create(code=f"11010_{uid}", defaults={"name": f"Cust Account {uid}", "account_type": asset_type, "is_active": True})

        customer = Customer.objects.create(
            name=f"Alexandria Commercial Corp {uid}",
            code=f"CUST-EEL-{uid}",
            credit_limit=Decimal("200000.00"),
            financial_account=acc
        )
        CustomerCreditProfile.objects.create(
            customer=customer,
            credit_limit=Decimal("200000.00"),
            credit_status="ACTIVE",
            risk_category="LOW"
        )
        return user, customer

    def test_customer_presenter_returns_correct_credit_data(self, setup_eel_data):
        user, customer = setup_eel_data

        dash_data = CustomerDashboardPresenter.get_customer_dashboard_data(customer.id)

        assert dash_data["customer_name"].startswith("Alexandria Commercial Corp")
        assert dash_data["credit_limit"] == Decimal("200000.00")
        assert dash_data["open_balance"] == Decimal("0.00")
        assert dash_data["available_credit"] == Decimal("200000.00")
        assert dash_data["status_code"] == "ACTIVE"
        assert dash_data["risk_level"] == "LOW"

    def test_executive_financial_dashboard_presenter_structure(self, setup_eel_data):
        user, customer = setup_eel_data

        exec_dto = FinancialDashboardPresenter.get_executive_dashboard_presentation()

        assert isinstance(exec_dto, ExecutiveDashboardDTO)
        assert isinstance(exec_dto.ar_metrics, ARMetricsDTO)
        assert isinstance(exec_dto.inventory_metrics, InventoryMetricsDTO)
        assert isinstance(exec_dto.tax_metrics, TaxMetricsDTO)
        assert exec_dto.currency == "EGP"

    def test_document_financial_presenter_breakdown(self):
        subtotal = Decimal("1000.00")
        tax = Decimal("140.00")
        total = Decimal("1140.00")
        discount = Decimal("100.00")

        breakdown = DocumentFinancialPresenter.get_breakdown(
            subtotal=subtotal,
            tax_amount=tax,
            total_amount=total,
            discount_amount=discount,
            currency="USD",
            exchange_rate=Decimal("50.000000")
        )

        assert isinstance(breakdown, DocumentFinancialBreakdownDTO)
        assert breakdown.subtotal == Decimal("1000.00")
        assert breakdown.discount_amount == Decimal("100.00")
        assert breakdown.taxable_amount == Decimal("900.00")
        assert breakdown.tax_amount == Decimal("140.00")
        assert breakdown.total_amount == Decimal("1140.00")
        assert breakdown.functional_total_egp == Decimal("57000.00") # 1140 * 50
