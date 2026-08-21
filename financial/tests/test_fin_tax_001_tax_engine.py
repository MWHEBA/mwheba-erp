import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from financial.models import (
    TaxCode,
    TaxRateHistory,
    TaxRule,
    TaxRuleEvaluationLog,
    TaxExemptionCertificate,
    TaxEvent,
    TaxDeterminationAudit,
    TaxReversal,
    ChartOfAccounts,
    AccountType
)
from financial.services.tax_service import TaxDeterminationService
from financial.services.tax_decision import TaxCalculationResult
from product.models import Product, Category, Unit, Warehouse, Stock
from client.models import Customer
from sale.services.sales_service import SalesService
from financial.exceptions import FinancialCoreError

User = get_user_model()


@pytest.mark.django_db(transaction=True)
class TestFINTAX001TaxEngineV3:

    @pytest.fixture
    def setup_tax_engine_data(self):
        user = User.objects.create_user(username="tax_v3_user", email="taxv3@example.com", password="password123")
        from financial.models import AccountingPeriod
        from django.utils import timezone
        today = timezone.now().date()
        AccountingPeriod.objects.get_or_create(
            name=f"TaxPeriod_{today.year}_{today.month}",
            start_date=today.replace(day=1),
            end_date=today.replace(day=28),
            defaults={"status": "open"}
        )
        customer = Customer.objects.create(name="Pharos Pharma", code="CUST-TAX-V3-001", credit_limit=Decimal("500000.00"))

        asset_type = AccountType.objects.filter(category="ASSET").first() or AccountType.objects.create(code="ASSET_TAX", name="Assets", category="ASSET")
        liab_type = AccountType.objects.filter(category="LIABILITY").first() or AccountType.objects.create(code="LIAB_TAX", name="Liabilities", category="LIABILITY")
        rev_type = AccountType.objects.filter(category="REVENUE").first() or AccountType.objects.create(code="REV_TAX", name="Revenues", category="REVENUE")
        exp_type = AccountType.objects.filter(category="EXPENSE").first() or AccountType.objects.create(code="EXP_TAX", name="Expenses", category="EXPENSE")

        ChartOfAccounts.objects.get_or_create(code="10400", defaults={"name": "Inventory Asset Legacy", "account_type": asset_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="11310", defaults={"name": "Inventory Asset Standard", "account_type": asset_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="11010", defaults={"name": "Customer AR Legacy", "account_type": asset_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="11210", defaults={"name": "Customer AR Standard", "account_type": asset_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="11050", defaults={"name": "Input VAT Recoverable", "account_type": asset_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="22010", defaults={"name": "Output VAT Payable Legacy", "account_type": liab_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="21310", defaults={"name": "Output VAT Payable Standard", "account_type": liab_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="21000", defaults={"name": "Deferred Revenue Legacy", "account_type": liab_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="21510", defaults={"name": "Deferred Revenue Standard", "account_type": liab_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="40100", defaults={"name": "Sales Revenue Account Legacy", "account_type": rev_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="41100", defaults={"name": "Sales Revenue Account Standard", "account_type": rev_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="50100", defaults={"name": "COGS Control Legacy", "account_type": exp_type, "is_active": True})
        ChartOfAccounts.objects.get_or_create(code="51100", defaults={"name": "COGS Control Standard", "account_type": exp_type, "is_active": True})

        category = Category.objects.create(name="Pharmaceuticals")
        unit = Unit.objects.create(name="BOX")
        product = Product.objects.create(name="Medicinal Box", category=category, unit=unit, cost_price=Decimal("100.00"), selling_price=Decimal("200.00"), created_by=user)
        warehouse = Warehouse.objects.create(code="WH-TAX-V3", name="Pharma Warehouse V3", is_active=True)
        Stock.objects.create(product=product, warehouse=warehouse, quantity=100)

        # Create or Get Tax Code VAT 14% with 100% recoverability
        tax_code, _ = TaxCode.objects.get_or_create(
            code="VAT14",
            defaults={
                "name": "Value Added Tax 14%",
                "version": 1,
                "tax_type": "VAT",
                "tax_nature": "OUTPUT",
                "rate": Decimal("14.0000"),
                "recoverability_percentage": Decimal("100.00"),
                "is_active": True
            }
        )

        tax_rule = TaxRule.objects.create(
            code="RUL-VAT14-MAIN",
            name="Standard 14% VAT Rule",
            version=1,
            priority=100,
            tax_code=tax_code,
            is_active=True
        )

        return user, customer, product, warehouse, tax_code, tax_rule

    def test_tax_calculation_result_object_and_rule_evaluation_log(self, setup_tax_engine_data):
        user, customer, product, warehouse, tax_code, tax_rule = setup_tax_engine_data

        lines = [{"line_id": 1, "amount": Decimal("1000.00")}, {"line_id": 2, "amount": Decimal("2000.00")}]
        calc_result = TaxDeterminationService.calculate_tax("SalesInvoice", 999, customer=customer, lines=lines)

        assert isinstance(calc_result, TaxCalculationResult)
        assert calc_result.subtotal == Decimal("3000.00")
        assert calc_result.tax_amount == Decimal("420.00")
        assert calc_result.total_amount == Decimal("3420.00")

        # Verify TaxRuleEvaluationLog recorded
        eval_log = TaxRuleEvaluationLog.objects.filter(document_number="SalesInvoice-999").first()
        assert eval_log is not None
        assert eval_log.selected_rule == "RUL-VAT14-MAIN"

    def test_tax_rate_history_and_recoverability(self, setup_tax_engine_data):
        user, customer, product, warehouse, tax_code, tax_rule = setup_tax_engine_data

        # Update Tax Rate and log history
        old_rate = tax_code.rate
        new_rate = Decimal("15.0000")
        tax_code.rate = new_rate
        tax_code.version = 2
        tax_code.save()

        TaxRateHistory.objects.create(
            tax_code=tax_code,
            old_rate=old_rate,
            new_rate=new_rate,
            effective_date=timezone.now().date(),
            created_by=user
        )

        assert tax_code.recoverability_percentage == Decimal("100.00")
        assert TaxRateHistory.objects.filter(tax_code=tax_code).count() == 1

    def test_end_to_end_sales_invoice_tax_event_pipeline(self, setup_tax_engine_data):
        user, customer, product, warehouse, tax_code, tax_rule = setup_tax_engine_data

        items_data = [{"product": product, "ordered_qty": Decimal("10.0000"), "unit_price": Decimal("200.00")}]
        result = SalesService.create_fast_sale(customer=customer, warehouse=warehouse, order_date=timezone.now().date(), items_data=items_data, user=user)

        inv = result["sales_invoice"]

        # Audit recorded during sales invoice creation
        audit = TaxDeterminationAudit.objects.get(document_number=inv.invoice_number)
        assert audit.taxable_amount == Decimal("2000.00")
        assert audit.tax_amount == Decimal("280.00")
        assert audit.audit_status == "POSTED"
        assert audit.audit_hash is not None

        # Verify Independent TaxEvent logged
        tax_event = TaxEvent.objects.filter(document_number=inv.invoice_number).first()
        assert tax_event is not None
        assert tax_event.event_type == "TAX_POSTING_APPLIED"

        # Verify Canonical SHA256 integrity
        is_valid = TaxDeterminationService.verify_audit_integrity(audit.id)
        assert is_valid is True

    def test_event_idempotency_guard(self, setup_tax_engine_data):
        user, customer, product, warehouse, tax_code, tax_rule = setup_tax_engine_data

        lines = [{"line_id": 1, "amount": Decimal("1000.00")}]
        audit1 = TaxDeterminationService.apply_tax_posting("TestDoc", 777, "DOC-777", customer=customer, lines=lines, user=user)

        # Re-applying duplicate event returns exact same audit instance
        audit2 = TaxDeterminationService.apply_tax_posting("TestDoc", 777, "DOC-777", customer=customer, lines=lines, user=user)
        assert audit1.id == audit2.id

    def test_tax_reversal_cap_and_execution(self, setup_tax_engine_data):
        user, customer, product, warehouse, tax_code, tax_rule = setup_tax_engine_data

        lines = [{"line_id": 1, "amount": Decimal("2000.00")}]
        audit = TaxDeterminationService.apply_tax_posting("TestDoc", 666, "DOC-666", customer=customer, lines=lines, user=user)

        # Reversal attempt exceeding tax_amount must raise FinancialCoreError
        with pytest.raises(FinancialCoreError, match="Reversal Cap Guard"):
            TaxDeterminationService.process_tax_reversal(audit.id, reversal_amount=Decimal("500.00"), reason="Excess Reversal", user=user)

        # Full reversal of 280 EGP succeeds
        reversal = TaxDeterminationService.process_tax_reversal(audit.id, reversal_amount=Decimal("280.00"), reason="Sales Return", user=user)
        assert reversal.reversal_amount == Decimal("280.00")

    def test_audit_immutability_protection(self, setup_tax_engine_data):
        user, customer, product, warehouse, tax_code, tax_rule = setup_tax_engine_data

        lines = [{"line_id": 1, "amount": Decimal("1000.00")}]
        audit = TaxDeterminationService.apply_tax_posting("TestDoc", 555, "DOC-555", customer=customer, lines=lines, user=user)

        # Attempt to modify audit record must raise ValueError
        with pytest.raises(ValueError, match="INSERT-ONLY"):
            audit.audit_status = "REVERSED"
            audit.save()

        # Attempt to delete audit record must raise ValueError
        with pytest.raises(ValueError, match="cannot be deleted"):
            audit.delete()

    def test_tax_transaction_snapshot_and_exemption_certificate_v2(self, setup_tax_engine_data):
        user, customer, product, warehouse, tax_code, tax_rule = setup_tax_engine_data
        from financial.models import TaxTransactionSnapshot, TaxExemptionSnapshot, TaxAdjustment

        # 1. Test Exemption Certificate handling
        ex_cert = TaxExemptionCertificate.objects.create(
            customer=customer,
            certificate_number="EX-CERT-999",
            tax_code=tax_code,
            valid_from=timezone.now().date() - timezone.timedelta(days=10),
            valid_to=timezone.now().date() + timezone.timedelta(days=30),
            exemption_reason="Governmental Tax Free Status",
            status="ACTIVE"
        )

        lines = [{"line_id": 1, "amount": Decimal("5000.00")}]
        audit = TaxDeterminationService.apply_tax_posting("SalesInvoice", 888, "INV-EX-888", customer=customer, lines=lines, user=user)

        assert audit.tax_amount == Decimal("0.00")
        assert audit.audit_status == "CALCULATED"

        # Verify Snapshots created
        snap = TaxTransactionSnapshot.objects.get(audit=audit)
        assert snap.customer_name == customer.name
        assert snap.applied_rule_code == "EXEMPT"

        ex_snap = TaxExemptionSnapshot.objects.get(audit=audit)
        assert ex_snap.certificate_number == "EX-CERT-999"

        # Test TaxAdjustment creation
        adj = TaxAdjustment.objects.create(
            original_audit=audit,
            adjustment_type="INCREASE",
            adjustment_amount=Decimal("100.00"),
            reason="Tax Inspection Adjustment"
        )
        assert adj.adjustment_amount == Decimal("100.00")
