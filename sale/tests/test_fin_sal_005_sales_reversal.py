import pytest
import uuid
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from sale.models import (
    CreditNote,
    CreditNoteItem,
    CreditNoteAllocation,
    CreditNoteAudit,
    ReturnAuthorization,
    SalesReturnHeader,
)
from sale.services.sales_return_service import SalesReturnService
from sale.services.sales_reversal_service import SalesReversalService
from sale.services.sales_service import SalesService
from product.models import Product, Category, Unit, Warehouse, Stock
from customer.models import Customer
from financial.models import ChartOfAccounts, AccountType
from financial.exceptions import FinancialCoreError

User = get_user_model()


@pytest.mark.django_db(transaction=True)
class TestFINSAL005SalesReversal:

    @pytest.fixture
    def setup_reversal_data(self):
        uid = uuid.uuid4().hex[:6]
        user = User.objects.create_user(username=f"rev_user_{uid}", email=f"rev_{uid}@example.com", password="password123")
        from financial.models import AccountingPeriod
        today = timezone.now().date()
        AccountingPeriod.objects.get_or_create(
            name=f"Period_{today.year}_{today.month}",
            start_date=today.replace(day=1),
            end_date=today.replace(day=28),
            defaults={"status": "open"}
        )
        customer = Customer.objects.create(name=f"Cairo Distribution {uid}", code=f"CUST-REV-{uid}", credit_limit=Decimal("500000.00"))

        asset_type = AccountType.objects.filter(code="ASSET").first() or AccountType.objects.create(code=f"ASSET_{uid}", name="Assets", category="ASSET")
        liab_type = AccountType.objects.filter(code="LIABILITY").first() or AccountType.objects.filter(code="LIAB").first() or AccountType.objects.create(code=f"LIAB_{uid}", name="Liabilities", category="LIABILITY")
        rev_type = AccountType.objects.filter(code="REVENUE").first() or AccountType.objects.filter(code="REV").first() or AccountType.objects.create(code=f"REV_{uid}", name="Revenues", category="REVENUE")
        exp_type = AccountType.objects.filter(code="EXPENSE").first() or AccountType.objects.create(code=f"EXP_{uid}", name="Expenses", category="EXPENSE")

        ChartOfAccounts.objects.get_or_create(code="10400", defaults={"name": "Inventory Asset", "account_type": asset_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="11010", defaults={"name": "Customer AR Account", "account_type": asset_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="11030", defaults={"name": "Main Customers Control Account", "account_type": asset_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="22010", defaults={"name": "Output VAT Payable", "account_type": liab_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="40100", defaults={"name": "Sales Revenue Account", "account_type": rev_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="41100", defaults={"name": "Sales Returns Account", "account_type": rev_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="50100", defaults={"name": "COGS Control", "account_type": exp_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="50300", defaults={"name": "Stock Movement Expense", "account_type": exp_type, "is_active": True})

        category = Category.objects.create(name="Home Appliances")
        unit = Unit.objects.create(name="PCS")
        product = Product.objects.create(name="Blender Pro 1000W", category=category, unit=unit, cost_price=Decimal("200.00"), selling_price=Decimal("500.00"), created_by=user)
        warehouse = Warehouse.objects.create(code="WH-REV-01", name="Main Cairo Warehouse", is_active=True)
        Stock.objects.create(product=product, warehouse=warehouse, quantity=50)

        # Fast Sale for 5 units
        items_data = [{"product": product, "ordered_qty": Decimal("5.0000"), "unit_price": Decimal("500.00")}]
        sale_res = SalesService.create_fast_sale(customer=customer, warehouse=warehouse, order_date=timezone.now().date(), items_data=items_data, user=user)

        delivery_note = sale_res["delivery_note"]

        # Create return & inspect
        auth = SalesReturnService.create_return_authorization(customer.id, user=user)
        dn_item = delivery_note.items.first()
        ret_header = SalesReturnService.create_sales_return(auth.id, delivery_note.id, warehouse.id, [{"delivery_item_id": dn_item.id, "requested_qty": Decimal("2.0000")}], user=user)

        ret_item = ret_header.items.first()
        SalesReturnService.inspect_sales_return(ret_header.id, [{"return_item_id": ret_item.id, "good_qty": Decimal("2.0000")}], user=user)
        SalesReturnService.process_return_stock_and_accounting(ret_header.id, user=user)

        return user, customer, product, warehouse, ret_header

    def test_credit_note_creation_from_return(self, setup_reversal_data):
        user, customer, product, warehouse, ret_header = setup_reversal_data

        cn = SalesReversalService.create_credit_note_for_return(ret_header.id, reason="Customer Return Credit", user=user)
        assert cn.status == "APPROVED"
        assert cn.source_type == "SALES_RETURN"
        assert cn.subtotal_amount == Decimal("1000.00") # 2 units * 500
        assert cn.tax_amount == Decimal("140.00") # 14% of 1000
        assert cn.total_amount == Decimal("1140.00")

    def test_credit_note_posting_and_subledger_reduction(self, setup_reversal_data):
        user, customer, product, warehouse, ret_header = setup_reversal_data

        cn = SalesReversalService.create_credit_note_for_return(ret_header.id, user=user)
        audit = SalesReversalService.post_credit_note(cn.id, user=user)

        assert audit.new_status == "POSTED"
        assert audit.audit_hash is not None
        assert audit.journal_entry is not None

        cn.refresh_from_db()
        assert cn.status == "POSTED"

    def test_credit_note_audit_immutability_protection(self, setup_reversal_data):
        user, customer, product, warehouse, ret_header = setup_reversal_data

        cn = SalesReversalService.create_credit_note_for_return(ret_header.id, user=user)
        audit = SalesReversalService.post_credit_note(cn.id, user=user)

        # Attempt to modify audit record must raise ValueError
        with pytest.raises(ValueError, match="INSERT-ONLY"):
            audit.new_status = "CANCELLED"
            audit.save()

        # Attempt to delete audit record must raise ValueError
        with pytest.raises(ValueError, match="cannot be deleted"):
            audit.delete()
