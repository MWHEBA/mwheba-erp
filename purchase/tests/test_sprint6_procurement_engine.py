import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from supplier.models import Supplier
from product.models.product_core import Product, Category, Unit
from product.models.stock_management import Warehouse
from financial.models import ChartOfAccounts, AccountType, AccountingPeriod, FiscalYear
from purchase.models.procurement_models import (
    PurchaseOrder,
    PurchaseOrderItem,
    GoodsReceivedNote,
    GoodsReceivedNoteItem,
    SupplierBill,
    SupplierBillItem,
    BillLineMatching
)
from purchase.services.procurement_service import ProcurementService
from purchase.services.grni_subledger_service import GRNISubledgerService
from financial.exceptions import FinancialCoreError

User = get_user_model()


@pytest.mark.django_db(transaction=True)
class TestSprint6ProcurementEngine:

    @pytest.fixture
    def setup_procurement_data(self):
        user = User.objects.create_user(username="pur_user6", password="password123")

        asset_type, _ = AccountType.objects.get_or_create(code="ASSET", defaults={"name": "Asset", "category": "ASSET"})
        liability_type, _ = AccountType.objects.get_or_create(code="LIABILITY", defaults={"name": "Liability", "category": "LIABILITY"})
        expense_type, _ = AccountType.objects.get_or_create(code="EXPENSE", defaults={"name": "Expense", "category": "EXPENSE"})

        inv_acc = ChartOfAccounts.objects.create(code="10400", name="Inventory Control", account_type=asset_type, is_active=True)
        ap_acc = ChartOfAccounts.objects.create(code="20100", name="Accounts Payable Control", account_type=liability_type, is_active=True)
        grni_acc = ChartOfAccounts.objects.create(code="20150_GRNI", name="GRNI Payable", account_type=liability_type, is_active=True)
        ppv_acc = ChartOfAccounts.objects.create(code="50120_PPV", name="PPV Variance", account_type=expense_type, is_active=True)
        cogs_acc = ChartOfAccounts.objects.create(code="50100", name="COGS Control", account_type=expense_type, is_active=True)

        fiscal_year = FiscalYear.objects.create(name="FY2026", start_date="2026-01-01", end_date="2026-12-31")
        period = AccountingPeriod.objects.create(fiscal_year=fiscal_year, name="AUG2026", period_number=8, start_date="2026-08-01", end_date="2026-08-31", status="open")

        supplier = Supplier.objects.create(code="SUP-001", name="El-Gomhouria Chemicals", is_active=True)
        warehouse = Warehouse.objects.create(code="WH-MAIN", name="Main Central Warehouse", is_active=True)

        category = Category.objects.create(name="Raw Materials")
        unit = Unit.objects.create(name="KG")
        product = Product.objects.create(name="Industrial Solvent", category=category, unit=unit, cost_price=Decimal("50.00"), selling_price=Decimal("75.00"), created_by=user)

        return user, supplier, warehouse, product

    def test_fin_pur_001_approval_workflow_enforcement(self, setup_procurement_data):
        user, supplier, warehouse, product = setup_procurement_data

        items_data = [{"product": product, "ordered_qty": Decimal("100.0000"), "unit_price": Decimal("50.00")}]
        po = ProcurementService.create_purchase_order(
            supplier=supplier,
            warehouse=warehouse,
            order_date=timezone.now().date(),
            items_data=items_data,
            user=user
        )
        assert po.status == "DRAFT"

        # Cannot issue GRN for unapproved PO
        items_rec = [{"po_item_id": po.items.first().id, "received_qty": Decimal("40.0000")}]
        with pytest.raises(FinancialCoreError, match="Cannot issue GRN"):
            ProcurementService.receive_goods_grn(po_id=po.id, delivery_note_ref="DN-001", items_data=items_rec, user=user)

        # Approve PO
        po_app = ProcurementService.approve_purchase_order(po_id=po.id, user=user)
        assert po_app.status == "APPROVED"

    def test_fin_pur_002_grn_receipt_and_gl_postings(self, setup_procurement_data):
        user, supplier, warehouse, product = setup_procurement_data

        items_data = [{"product": product, "ordered_qty": Decimal("100.0000"), "unit_price": Decimal("50.00")}]
        po = ProcurementService.create_purchase_order(supplier=supplier, warehouse=warehouse, order_date=timezone.now().date(), items_data=items_data, user=user)
        ProcurementService.approve_purchase_order(po_id=po.id, user=user)

        items_rec = [{"po_item_id": po.items.first().id, "received_qty": Decimal("40.0000")}]
        grn = ProcurementService.receive_goods_grn(po_id=po.id, delivery_note_ref="DN-001", items_data=items_rec, user=user)

        assert grn.status == "RECEIVED"
        assert grn.journal_entry is not None
        assert grn.journal_entry.status == "posted"

        po.refresh_from_db()
        assert po.status == "PARTIALLY_RECEIVED"

    def test_fin_pur_003_supplier_bill_and_3way_matching(self, setup_procurement_data):
        user, supplier, warehouse, product = setup_procurement_data

        items_data = [{"product": product, "ordered_qty": Decimal("100.0000"), "unit_price": Decimal("50.00")}]
        po = ProcurementService.create_purchase_order(supplier=supplier, warehouse=warehouse, order_date=timezone.now().date(), items_data=items_data, user=user)
        ProcurementService.approve_purchase_order(po_id=po.id, user=user)

        items_rec = [{"po_item_id": po.items.first().id, "received_qty": Decimal("40.0000")}]
        grn = ProcurementService.receive_goods_grn(po_id=po.id, delivery_note_ref="DN-001", items_data=items_rec, user=user)

        grn_item = grn.items.first()
        bill_items = [{"grn_item_id": grn_item.id, "billed_qty": Decimal("40.0000"), "unit_price": Decimal("52.00")}]

        bill = ProcurementService.create_supplier_bill(
            supplier=supplier,
            supplier_bill_number="INV-SUPP-99",
            bill_date=timezone.now().date(),
            due_date=timezone.now().date(),
            items_data=bill_items,
            user=user
        )

        assert bill.status == "POSTED"
        assert bill.total_amount == Decimal("2080.00")  # 40 * 52
        assert bill.journal_entry is not None

        # Check line matching
        matching = BillLineMatching.objects.get(bill_item__bill=bill)
        assert matching.matched_qty == Decimal("40.0000")
        assert matching.price_variance == Decimal("80.00")  # (52 - 50) * 40

    def test_fin_pur_004_grni_aging_and_reconciliation(self, setup_procurement_data):
        user, supplier, warehouse, product = setup_procurement_data

        items_data = [{"product": product, "ordered_qty": Decimal("100.0000"), "unit_price": Decimal("50.00")}]
        po = ProcurementService.create_purchase_order(supplier=supplier, warehouse=warehouse, order_date=timezone.now().date(), items_data=items_data, user=user)
        ProcurementService.approve_purchase_order(po_id=po.id, user=user)

        items_rec = [{"po_item_id": po.items.first().id, "received_qty": Decimal("40.0000")}]
        grn = ProcurementService.receive_goods_grn(po_id=po.id, delivery_note_ref="DN-001", items_data=items_rec, user=user)

        grni_summary = GRNISubledgerService.get_open_grni_summary()
        assert grni_summary["total_open_grni_value"] == Decimal("2000.00")  # 40 * 50

        reconciliation = GRNISubledgerService.reconcile_grni_control_account()
        assert reconciliation["subledger_grni_value"] == Decimal("2000.00")
        assert reconciliation["gl_grni_balance"] == Decimal("2000.00")
        assert reconciliation["is_reconciled"] is True

    def test_fin_pur_005_grni_clearing_workflow(self, setup_procurement_data):
        user, supplier, warehouse, product = setup_procurement_data

        items_data = [{"product": product, "ordered_qty": Decimal("100.0000"), "unit_price": Decimal("50.00")}]
        po = ProcurementService.create_purchase_order(supplier=supplier, warehouse=warehouse, order_date=timezone.now().date(), items_data=items_data, user=user)
        ProcurementService.approve_purchase_order(po_id=po.id, user=user)

        items_rec = [{"po_item_id": po.items.first().id, "received_qty": Decimal("40.0000")}]
        grn = ProcurementService.receive_goods_grn(po_id=po.id, delivery_note_ref="DN-001", items_data=items_rec, user=user)

        grn_item = grn.items.first()
        clearing_res = GRNISubledgerService.create_grni_clearing_entry(
            grn_item_id=grn_item.id,
            reason="Un-invoiced stale write-off after 60 days",
            user=user
        )

        assert clearing_res["cleared_value"] == Decimal("2000.00")
        grn_item.refresh_from_db()
        assert grn_item.billed_qty == Decimal("40.0000")

    def test_fin_pur_006_pre_invoice_grn_return(self, setup_procurement_data):
        user, supplier, warehouse, product = setup_procurement_data

        items_data = [{"product": product, "ordered_qty": Decimal("100.0000"), "unit_price": Decimal("50.00")}]
        po = ProcurementService.create_purchase_order(supplier=supplier, warehouse=warehouse, order_date=timezone.now().date(), items_data=items_data, user=user)
        ProcurementService.approve_purchase_order(po_id=po.id, user=user)

        items_rec = [{"po_item_id": po.items.first().id, "received_qty": Decimal("40.0000")}]
        grn = ProcurementService.receive_goods_grn(po_id=po.id, delivery_note_ref="DN-001", items_data=items_rec, user=user)

        grn_item = grn.items.first()
        ret_res = ProcurementService.process_pre_invoice_grn_return(
            grn_item_id=grn_item.id,
            return_qty=Decimal("10.0000"),
            user=user
        )

        assert ret_res["return_value"] == Decimal("500.00")  # 10 * 50
        grn_item.refresh_from_db()
        assert grn_item.received_qty == Decimal("30.0000")

    def test_fin_pur_007_approval_rule_and_idempotency_governance(self, setup_procurement_data):
        user, supplier, warehouse, product = setup_procurement_data
        from purchase.models.procurement_models import ApprovalRule, ApprovalRequest

        # Create approval rule
        rule = ApprovalRule.objects.create(rule_name="High Value Approval", min_amount=Decimal("1000.00"), approver_role="CTO")
        assert rule.is_active is True

        items_data = [{"product": product, "ordered_qty": Decimal("100.0000"), "unit_price": Decimal("50.00")}]
        po = ProcurementService.create_purchase_order(supplier=supplier, warehouse=warehouse, order_date=timezone.now().date(), items_data=items_data, user=user)

        app_req = ApprovalRequest.objects.create(purchase_order=po, rule=rule, status="PENDING", comments="Requires CTO approval")
        assert app_req.status == "PENDING"

        ProcurementService.approve_purchase_order(po.id, user=user)
        po.refresh_from_db()
        assert po.status == "APPROVED"
