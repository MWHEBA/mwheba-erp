import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from client.models import Customer
from client.services.customer_aging_service import CustomerAgingService
from sale.models import Sale
from financial.models import ChartOfAccounts, AccountType, FiscalYear, AccountingPeriod
from financial.services import LedgerCoreService, AllocationService

User = get_user_model()


@pytest.mark.django_db
class TestCustomerAgingService:

    @pytest.fixture
    def setup_customer_aging(self):
        user = User.objects.create_user(username="cust_aging_user", password="password123")
        today = timezone.now().date()

        fiscal_year = FiscalYear.objects.create(
            year_code=f"FY-{today.year}-CAG",
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

        asset_type, _ = AccountType.objects.get_or_create(code="AST_CAG", defaults={"name": "Asset CAG", "category": "asset"})
        revenue_type, _ = AccountType.objects.get_or_create(code="REV_CAG", defaults={"name": "Revenue CAG", "category": "revenue"})

        cust_acc = ChartOfAccounts.objects.create(code="11010_CAG", name="Customer Acc CAG", account_type=asset_type, is_active=True)
        rev_acc = ChartOfAccounts.objects.create(code="40100_CAG", name="Sales Rev Acc CAG", account_type=revenue_type, is_active=True)

        customer = Customer.objects.create(
            name="Apex Dynamics",
            code="CUST-CAG-01",
            financial_account=cust_acc,
            is_active=True
        )

        from product.models import Warehouse
        wh, _ = Warehouse.objects.get_or_create(code="WH_CAG", defaults={"name": "Main WH"})

        sale = Sale.objects.create(
            customer=customer,
            warehouse=wh,
            number="INV-CAG-01",
            date=today,
            subtotal=Decimal("3000.00"),
            total=Decimal("3000.00"),
            status="confirmed",
            created_by=user
        )

        # Post GL entry for the sale
        draft = LedgerCoreService.create_draft_entry(
            date=today,
            description=f"Invoice {sale.number}",
            reference=sale.number,
            entry_type="sale",
            created_by=user,
            lines_data=[
                {"account": cust_acc, "debit": Decimal("3000.00"), "credit": Decimal("0.00")},
                {"account": rev_acc, "debit": Decimal("0.00"), "credit": Decimal("3000.00")}
            ]
        )
        LedgerCoreService.post_entry(draft.id, user, posting_source="SALE_INVOICE")

        return user, customer, sale, cust_acc

    def test_customer_open_item_aging_with_allocations(self, setup_customer_aging):
        user, customer, sale, cust_acc = setup_customer_aging
        today = timezone.now().date()

        # Partial allocation of 1000
        AllocationService.create_allocation(
            debit_document_type="SALE_INVOICE",
            debit_document_id=str(sale.id),
            credit_document_type="CUSTOMER_PAYMENT",
            credit_document_id="PAY-CAG-01",
            subledger_type="customer",
            entity_id=customer.id,
            amount_to_allocate=Decimal("1000.00"),
            debit_doc_total_amount=Decimal("3000.00"),
            credit_doc_total_amount=Decimal("1000.00"),
            user=user
        )

        aging_report = CustomerAgingService.get_customer_open_item_aging(customer_ids=[customer.id], as_of_date=today)
        assert len(aging_report['rows']) == 1
        row = aging_report['rows'][0]

        # Remaining unpaid outstanding balance is 2000
        assert row['net_balance'] == Decimal("3000.00")
        assert row['credit_balance'] == Decimal("0.00")
