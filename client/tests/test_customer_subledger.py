import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from client.models import Customer
from client.services.customer_subledger_service import CustomerSubledgerService
from financial.models import ChartOfAccounts, AccountType, FiscalYear, AccountingPeriod
from financial.services import LedgerCoreService

User = get_user_model()


@pytest.mark.django_db
class TestCustomerSubledgerService:

    @pytest.fixture
    def setup_customer_subledger(self):
        user = User.objects.create_user(username="cust_sub_user", password="password123")
        today = timezone.now().date()

        fiscal_year = FiscalYear.objects.create(
            year_code=f"FY-{today.year}-CUST",
            name=f"Fiscal Year {today.year}",
            start_date=today.replace(month=1, day=1),
            end_date=today.replace(month=12, day=31),
            status="open"
        )

        period, _ = AccountingPeriod.objects.get_or_create(
            fiscal_year=fiscal_year,
            period_number=today.month,
            defaults={
                "name": f"Period {today.month}",
                "start_date": today.replace(day=1),
                "end_date": today.replace(day=28),
                "status": "open"
            }
        )

        asset_type, _ = AccountType.objects.get_or_create(code="AST_CUST", defaults={"name": "Asset Cust", "category": "asset"})
        revenue_type, _ = AccountType.objects.get_or_create(code="REV_CUST", defaults={"name": "Revenue Cust", "category": "revenue"})

        cust_acc = ChartOfAccounts.objects.create(code="11010_CUST", name="Customer Acc 1", account_type=asset_type, is_active=True)
        rev_acc = ChartOfAccounts.objects.create(code="40100_CUST", name="Sales Rev Acc", account_type=revenue_type, is_active=True)

        customer = Customer.objects.create(
            name="ACME Corp",
            code="CUST-001",
            financial_account=cust_acc,
            is_active=True
        )

        return user, customer, cust_acc, rev_acc

    def test_customer_balance_and_statement(self, setup_customer_subledger):
        user, customer, cust_acc, rev_acc = setup_customer_subledger

        draft = LedgerCoreService.create_draft_entry(
            date=timezone.now().date(),
            description="Invoice Sale #1",
            reference="INV-001",
            entry_type="sale",
            created_by=user,
            lines_data=[
                {"account": cust_acc, "debit": Decimal("1500.00"), "credit": Decimal("0.00")},
                {"account": rev_acc, "debit": Decimal("0.00"), "credit": Decimal("1500.00")}
            ]
        )
        LedgerCoreService.post_entry(draft.id, user, posting_source="SALE_INVOICE")

        bal = CustomerSubledgerService.get_customer_balance(customer.id)
        assert bal['balance'] == Decimal("1500.00")
        assert bal['customer_name'] == "ACME Corp"

        stmt = CustomerSubledgerService.get_customer_statement(customer.id)
        assert stmt['closing_balance'] == Decimal("1500.00")
        assert len(stmt['transactions']) == 1

    def test_customer_aging_report(self, setup_customer_subledger):
        user, customer, cust_acc, rev_acc = setup_customer_subledger

        draft = LedgerCoreService.create_draft_entry(
            date=timezone.now().date(),
            description="Recent Sale Invoice",
            reference="INV-002",
            entry_type="sale",
            created_by=user,
            lines_data=[
                {"account": cust_acc, "debit": Decimal("2000.00"), "credit": Decimal("0.00")},
                {"account": rev_acc, "debit": Decimal("0.00"), "credit": Decimal("2000.00")}
            ]
        )
        LedgerCoreService.post_entry(draft.id, user, posting_source="SALE_INVOICE")

        aging = CustomerSubledgerService.get_customer_aging_report(customer_ids=[customer.id])
        assert len(aging['rows']) == 1
        assert aging['rows'][0]['bucket_0_30'] == Decimal("2000.00")
        assert aging['summary']['total_balance'] == Decimal("2000.00")
