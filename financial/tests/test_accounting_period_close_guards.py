import pytest
import uuid
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from financial.models import AccountingPeriod, ChartOfAccounts, AccountType
from sale.services.sales_service import SalesService
from sale.services.sales_reversal_service import SalesReversalService
from financial.services.tax_service import TaxDeterminationService
from product.models import Product, Category, Unit, Warehouse, Stock
from client.models import Customer
from financial.exceptions import FinancialCoreError

User = get_user_model()


@pytest.mark.django_db(transaction=True)
class TestAccountingPeriodCloseGuards:

    @pytest.fixture
    def setup_closed_period_data(self):
        uid = uuid.uuid4().hex[:6]
        user = User.objects.create_user(username=f"close_user_{uid}", email=f"close_{uid}@example.com", password="password123")

        # Close all accounting periods
        AccountingPeriod.objects.all().update(status="closed")

        customer = Customer.objects.create(name=f"Closed Period Customer {uid}", code=f"CUST-CLOSE-{uid}", credit_limit=Decimal("500000.00"))

        asset_type, _ = AccountType.objects.get_or_create(code="ASSET", defaults={"name": "Assets", "category": "asset", "nature": "debit"})
        liab_type, _ = AccountType.objects.get_or_create(code="LIAB", defaults={"name": "Liabilities", "category": "liability", "nature": "credit"})
        rev_type, _ = AccountType.objects.get_or_create(code="REV", defaults={"name": "Revenues", "category": "revenue", "nature": "credit"})
        exp_type, _ = AccountType.objects.get_or_create(code="EXPENSE", defaults={"name": "Expenses", "category": "expense", "nature": "debit"})

        ChartOfAccounts.objects.get_or_create(code="10400", defaults={"name": "Inventory Asset", "account_type": asset_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="11010", defaults={"name": "Customer AR", "account_type": asset_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="22010", defaults={"name": "Output VAT Payable", "account_type": liab_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="40100", defaults={"name": "Sales Revenue Account", "account_type": rev_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="41100", defaults={"name": "Sales Returns Account", "account_type": rev_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="50100", defaults={"name": "COGS Control", "account_type": exp_type, "is_active": True})

        category = Category.objects.create(name=f"Close Category {uid}")
        unit = Unit.objects.create(name=f"PCS-{uid}")
        product = Product.objects.create(name=f"Close Product {uid}", category=category, unit=unit, cost_price=Decimal("100.00"), selling_price=Decimal("200.00"), created_by=user)
        warehouse = Warehouse.objects.create(code=f"WH-CLOSE-{uid}", name=f"Close Warehouse {uid}", is_active=True)
        Stock.objects.create(product=product, warehouse=warehouse, quantity=50)

        return user, customer, product, warehouse

    def test_credit_note_posting_blocks_on_closed_period(self, setup_closed_period_data):
        user, customer, product, warehouse = setup_closed_period_data
        from sale.models import CreditNote

        cn = CreditNote.objects.create(
            credit_note_number=f"CN-CLOSED-{uuid.uuid4().hex[:6]}",
            customer=customer,
            subtotal_amount=Decimal("1000.00"),
            tax_amount=Decimal("140.00"),
            total_amount=Decimal("1140.00"),
            currency="EGP",
            status="APPROVED"
        )

        with pytest.raises(FinancialCoreError, match="Period Close Guard"):
            SalesReversalService.post_credit_note(cn.id, user=user)
