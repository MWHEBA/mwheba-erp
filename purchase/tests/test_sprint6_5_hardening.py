import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from supplier.models import Supplier
from product.models.product_core import Product, Category, Unit
from product.models.stock_management import Warehouse
from financial.models import ChartOfAccounts, AccountType, AccountingPeriod, FiscalYear
from purchase.models.procurement_models import PurchaseOrder, GoodsReceivedNote, SupplierBill
from purchase.services.procurement_service import ProcurementService
from purchase.services.grni_subledger_service import GRNISubledgerService
from supplier.services.supplier_subledger_service import SupplierSubledgerService

User = get_user_model()


@pytest.mark.django_db(transaction=True)
class TestSprint65ProcurementHardening:

    @pytest.fixture
    def setup_hardening_data(self):
        user = User.objects.create_user(username="pur_hard_user65", password="password123")

        asset_type, _ = AccountType.objects.get_or_create(code="ASSET", defaults={"name": "Asset", "category": "ASSET"})
        liability_type, _ = AccountType.objects.get_or_create(code="LIABILITY", defaults={"name": "Liability", "category": "LIABILITY"})
        expense_type, _ = AccountType.objects.get_or_create(code="EXPENSE", defaults={"name": "Expense", "category": "EXPENSE"})

        inv_acc, _ = ChartOfAccounts.objects.get_or_create(code="11310", defaults={"name": "Inventory Control", "account_type": asset_type, "is_active": True})
        ap_acc, _ = ChartOfAccounts.objects.get_or_create(code="21110", defaults={"name": "Accounts Payable Control", "account_type": liability_type, "is_active": True})
        grni_acc, _ = ChartOfAccounts.objects.get_or_create(code="21210", defaults={"name": "GRNI Payable", "account_type": liability_type, "is_active": True})
        ppv_acc, _ = ChartOfAccounts.objects.get_or_create(code="50120_PPV", defaults={"name": "PPV Variance", "account_type": expense_type, "is_active": True})
        cogs_acc, _ = ChartOfAccounts.objects.get_or_create(code="51100", defaults={"name": "COGS Control", "account_type": expense_type, "is_active": True})

        fiscal_year = FiscalYear.objects.create(name="FY2026", start_date="2026-01-01", end_date="2026-12-31")
        period = AccountingPeriod.objects.create(fiscal_year=fiscal_year, name="AUG2026", period_number=8, start_date="2026-08-01", end_date="2026-08-31", status="open")

        supplier = Supplier.objects.create(code="SUP-HARD-01", name="Suez Chemicals Ltd", is_active=True)
        warehouse = Warehouse.objects.create(code="WH-HARD", name="Harbor Central Warehouse", is_active=True)

        category = Category.objects.create(name="Raw Polymers")
        unit = Unit.objects.create(name="TON")
        product = Product.objects.create(name="Polyethylene Resin", category=category, unit=unit, cost_price=Decimal("100.00"), selling_price=Decimal("150.00"), created_by=user)

        return user, supplier, warehouse, product

    def test_fin_pur_010_grni_reconciliation_and_write_off(self, setup_hardening_data):
        user, supplier, warehouse, product = setup_hardening_data

        items_data = [{"product": product, "ordered_qty": Decimal("50.0000"), "unit_price": Decimal("100.00")}]
        po = ProcurementService.create_purchase_order(supplier=supplier, warehouse=warehouse, order_date=timezone.now().date(), items_data=items_data, user=user)
        ProcurementService.approve_purchase_order(po.id, user=user)

        items_rec = [{"po_item_id": po.items.first().id, "received_qty": Decimal("50.0000")}]
        grn = ProcurementService.receive_goods_grn(po_id=po.id, delivery_note_ref="DN-HARD-10", items_data=items_rec, user=user)

        grn_item = grn.items.first()
        res = GRNISubledgerService.write_off_stale_grni(grn_item_id=grn_item.id, reason="Stale un-invoiced writeoff", user=user)
        assert res["cleared_value"] == Decimal("5000.00")

    def test_fin_pur_011_pre_vs_post_invoice_returns_governance(self, setup_hardening_data):
        user, supplier, warehouse, product = setup_hardening_data

        items_data = [{"product": product, "ordered_qty": Decimal("20.0000"), "unit_price": Decimal("100.00")}]
        po = ProcurementService.create_purchase_order(supplier=supplier, warehouse=warehouse, order_date=timezone.now().date(), items_data=items_data, user=user)
        ProcurementService.approve_purchase_order(po.id, user=user)

        items_rec = [{"po_item_id": po.items.first().id, "received_qty": Decimal("20.0000")}]
        grn = ProcurementService.receive_goods_grn(po_id=po.id, delivery_note_ref="DN-HARD-11", items_data=items_rec, user=user)

        grn_item = grn.items.first()
        ret = ProcurementService.process_pre_invoice_grn_return(grn_item_id=grn_item.id, return_qty=Decimal("5.0000"), user=user)
        assert ret["return_value"] == Decimal("500.00")

    def test_fin_pur_014_multi_currency_and_ias21_spot_rate(self, setup_hardening_data):
        user, supplier, warehouse, product = setup_hardening_data

        items_data = [{"product": product, "ordered_qty": Decimal("10.0000"), "unit_price": Decimal("100.00")}]
        po = ProcurementService.create_purchase_order(
            supplier=supplier,
            warehouse=warehouse,
            order_date=timezone.now().date(),
            items_data=items_data,
            user=user,
            currency="USD",
            exchange_rate=Decimal("48.5000")
        )
        assert po.currency.code == "USD"
        assert po.functional_amount == Decimal("48500.00")  # 1000 * 48.50

    def test_fin_pur_016_audit_trail_and_subledger_reconciliations(self, setup_hardening_data):
        user, supplier, warehouse, product = setup_hardening_data

        reconciliation = GRNISubledgerService.reconcile_grni_control_account()
        assert "subledger_grni_value" in reconciliation
        assert "gl_grni_balance" in reconciliation
