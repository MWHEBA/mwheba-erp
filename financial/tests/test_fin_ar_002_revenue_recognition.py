import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from financial.models import (
    RevenueRecognitionPolicy,
    RevenueRecognitionSchedule,
    RevenueRecognitionEntry,
    RevenueRecognitionReversal,
    ChartOfAccounts,
    AccountType
)
from financial.services.revenue_recognition_service import RevenueRecognitionService
from product.models import Product, Category, Unit, Warehouse, Stock
from client.models import Customer
from sale.services.sales_service import SalesService
from financial.exceptions import FinancialCoreError

User = get_user_model()


@pytest.mark.django_db(transaction=True)
class TestFINAR002RevenueRecognition:

    @pytest.fixture
    def setup_rev_rec_data(self):
        user = User.objects.create_user(username="rev_user1", email="rev1@example.com", password="password123")
        customer = Customer.objects.create(name="Apex Solutions", code="CUST-REV-001", credit_limit=Decimal("500000.00"))

        asset_type, _ = AccountType.objects.get_or_create(code="ASSET", name="Assets", category="ASSET")
        liab_type, _ = AccountType.objects.get_or_create(code="LIAB", name="Liabilities", category="LIABILITY")
        rev_type, _ = AccountType.objects.get_or_create(code="REV", name="Revenues", category="REVENUE")
        exp_type, _ = AccountType.objects.get_or_create(code="EXPENSE", name="Expenses", category="EXPENSE")

        ChartOfAccounts.objects.get_or_create(code="10400", defaults={"name": "Inventory Asset", "account_type": asset_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="11010", defaults={"name": "Customer AR", "account_type": asset_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="11040", defaults={"name": "Contract Asset Account", "account_type": asset_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="21000", defaults={"name": "Deferred Revenue Liability Account", "account_type": liab_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="22010", defaults={"name": "Output VAT Payable", "account_type": liab_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="40100", defaults={"name": "Sales Revenue Account", "account_type": rev_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="50100", defaults={"name": "COGS Control", "account_type": exp_type, "is_active": True})

        category = Category.objects.create(name="Software Subscription")
        unit = Unit.objects.create(name="LIC")
        product = Product.objects.create(name="Enterprise ERP License", category=category, unit=unit, cost_price=Decimal("1000.00"), selling_price=Decimal("5000.00"), created_by=user)
        warehouse = Warehouse.objects.create(code="WH-REV-01", name="Digital Delivery Warehouse", is_active=True)
        Stock.objects.create(product=product, warehouse=warehouse, quantity=50)

        # Create Revenue Policy
        policy = RevenueRecognitionPolicy.objects.create(
            name="Delivery Trigger Policy",
            code="POL-DELIVERY-01",
            version=1,
            trigger_event="DELIVERY_CONFIRMED",
            allocation_method="DIRECT_LINE_VALUE",
            fx_treatment_type="INVOICE_RATE",
            is_active=True
        )

        return user, customer, product, warehouse, policy

    def test_schedule_creation_on_invoice_issuance(self, setup_rev_rec_data):
        user, customer, product, warehouse, policy = setup_rev_rec_data

        items_data = [{"product": product, "ordered_qty": Decimal("2.0000"), "unit_price": Decimal("5000.00")}]
        result = SalesService.create_fast_sale(customer=customer, warehouse=warehouse, order_date=timezone.now().date(), items_data=items_data, user=user)

        inv = result["sales_invoice"]
        inv_item = inv.items.first()

        # Schedule created automatically for invoice item
        schedule = RevenueRecognitionSchedule.objects.get(invoice_item=inv_item)
        assert schedule.allocated_transaction_price == Decimal("10000.00")
        assert schedule.deferred_amount == Decimal("10000.00")
        assert schedule.status == "ACTIVE"

    def test_process_recognition_event_and_canonical_sha256_audit_hash(self, setup_rev_rec_data):
        user, customer, product, warehouse, policy = setup_rev_rec_data

        items_data = [{"product": product, "ordered_qty": Decimal("1.0000"), "unit_price": Decimal("5000.00")}]
        result = SalesService.create_fast_sale(customer=customer, warehouse=warehouse, order_date=timezone.now().date(), items_data=items_data, user=user)

        inv_item = result["sales_invoice"].items.first()
        schedule = RevenueRecognitionSchedule.objects.get(invoice_item=inv_item)

        # Process recognition event for delivery confirmation
        entry = RevenueRecognitionService.process_recognition_event(
            event_id="EVT-DELIV-001",
            schedule_id=schedule.id,
            recognition_event="DELIVERY_CONFIRMED",
            user=user
        )

        assert entry.entry_status == "POSTED"
        assert entry.audit_hash is not None

        # Verify Canonical SHA256 audit integrity
        is_valid = RevenueRecognitionService.verify_audit_integrity(entry.id)
        assert is_valid is True

        # Verify Schedule updated
        schedule.refresh_from_db()
        assert schedule.recognized_amount == Decimal("5000.00")
        assert schedule.status == "FULLY_RECOGNIZED"

    def test_event_idempotency_guard(self, setup_rev_rec_data):
        user, customer, product, warehouse, policy = setup_rev_rec_data

        items_data = [{"product": product, "ordered_qty": Decimal("1.0000"), "unit_price": Decimal("5000.00")}]
        result = SalesService.create_fast_sale(customer=customer, warehouse=warehouse, order_date=timezone.now().date(), items_data=items_data, user=user)

        inv_item = result["sales_invoice"].items.first()
        schedule = RevenueRecognitionSchedule.objects.get(invoice_item=inv_item)

        # First call processes event
        entry1 = RevenueRecognitionService.process_recognition_event("EVT-IDEMP-999", schedule.id, user=user)

        # Duplicate event processing returns existing entry without duplicate GL entries
        entry2 = RevenueRecognitionService.process_recognition_event("EVT-IDEMP-999", schedule.id, user=user)
        assert entry1.id == entry2.id

    def test_amount_integrity_control_guard(self, setup_rev_rec_data):
        user, customer, product, warehouse, policy = setup_rev_rec_data

        items_data = [{"product": product, "ordered_qty": Decimal("1.0000"), "unit_price": Decimal("5000.00")}]
        result = SalesService.create_fast_sale(customer=customer, warehouse=warehouse, order_date=timezone.now().date(), items_data=items_data, user=user)

        inv_item = result["sales_invoice"].items.first()
        schedule = RevenueRecognitionSchedule.objects.get(invoice_item=inv_item)

        # First recognition of 5000 EGP
        RevenueRecognitionService.process_recognition_event("EVT-OVER-1", schedule.id, user=user)

        # Attempting second recognition exceeding allocated price must raise FinancialCoreError
        with pytest.raises(FinancialCoreError, match="Amount Integrity Guard"):
            RevenueRecognitionService.process_recognition_event("EVT-OVER-2", schedule.id, user=user)

    def test_reversal_cap_validation_guard(self, setup_rev_rec_data):
        user, customer, product, warehouse, policy = setup_rev_rec_data

        items_data = [{"product": product, "ordered_qty": Decimal("1.0000"), "unit_price": Decimal("5000.00")}]
        result = SalesService.create_fast_sale(customer=customer, warehouse=warehouse, order_date=timezone.now().date(), items_data=items_data, user=user)

        inv_item = result["sales_invoice"].items.first()
        schedule = RevenueRecognitionSchedule.objects.get(invoice_item=inv_item)
        entry = RevenueRecognitionService.process_recognition_event("EVT-REV-CAP-1", schedule.id, user=user)

        # Attempting reversal greater than cumulative recognized balance (6000 > 5000) must raise FinancialCoreError
        with pytest.raises(FinancialCoreError, match="Reversal Cap Guard"):
            RevenueRecognitionService.process_revenue_reversal(entry.id, reversal_amount=Decimal("6000.00"), reason="Excess Reversal", user=user)

        # Reversal of 5000 EGP succeeds
        reversal = RevenueRecognitionService.process_revenue_reversal(entry.id, reversal_amount=Decimal("5000.00"), reason="Contract Cancellation", user=user)
        assert reversal.reversal_amount == Decimal("5000.00")

    def test_entry_immutability_protection(self, setup_rev_rec_data):
        user, customer, product, warehouse, policy = setup_rev_rec_data

        items_data = [{"product": product, "ordered_qty": Decimal("1.0000"), "unit_price": Decimal("5000.00")}]
        result = SalesService.create_fast_sale(customer=customer, warehouse=warehouse, order_date=timezone.now().date(), items_data=items_data, user=user)

        inv_item = result["sales_invoice"].items.first()
        schedule = RevenueRecognitionSchedule.objects.get(invoice_item=inv_item)
        entry = RevenueRecognitionService.process_recognition_event("EVT-IMMUT-1", schedule.id, user=user)

        # Attempting to edit entry must raise ValueError
        with pytest.raises(ValueError, match="INSERT-ONLY"):
            entry.entry_status = "REVERSED"
            entry.save()

        # Attempting to delete entry must raise ValueError
        with pytest.raises(ValueError, match="cannot be deleted"):
            entry.delete()
