import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from supplier.models import Supplier
from supplier.services.supplier_subledger_service import SupplierSubledgerService
from financial.models import ChartOfAccounts, AccountType, FiscalYear, AccountingPeriod
from financial.services import LedgerCoreService

User = get_user_model()


@pytest.mark.django_db
class TestSupplierSubledgerService:

    @pytest.fixture
    def setup_supplier_subledger(self):
        user = User.objects.create_user(username="supp_sub_user", password="password123")
        today = timezone.now().date()

        fiscal_year = FiscalYear.objects.create(
            year_code=f"FY-{today.year}-SUPP",
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

        liability_type, _ = AccountType.objects.get_or_create(code="LIAB_SUPP", defaults={"name": "Liability Supp", "category": "liability"})
        expense_type, _ = AccountType.objects.get_or_create(code="EXP_SUPP", defaults={"name": "Expense Supp", "category": "expense"})

        supp_acc = ChartOfAccounts.objects.create(code="20101_SUPP", name="Supplier Acc 1", account_type=liability_type, is_active=True)
        exp_acc = ChartOfAccounts.objects.create(code="50100_SUPP", name="Purchase Exp Acc", account_type=expense_type, is_active=True)

        supplier = Supplier.objects.create(
            name="Global Materials Ltd",
            code="SUPP-001",
            financial_account=supp_acc,
            is_active=True
        )

        return user, supplier, supp_acc, exp_acc

    def test_supplier_balance_and_statement(self, setup_supplier_subledger):
        user, supplier, supp_acc, exp_acc = setup_supplier_subledger

        draft = LedgerCoreService.create_draft_entry(
            date=timezone.now().date(),
            description="Purchase Bill #1",
            reference="BILL-001",
            entry_type="purchase",
            created_by=user,
            lines_data=[
                {"account": exp_acc, "debit": Decimal("4000.00"), "credit": Decimal("0.00")},
                {"account": supp_acc, "debit": Decimal("0.00"), "credit": Decimal("4000.00")}
            ]
        )
        LedgerCoreService.post_entry(draft.id, user, posting_source="PURCHASE_BILL")

        bal = SupplierSubledgerService.get_supplier_balance(supplier.id)
        assert bal['balance'] == Decimal("4000.00")
        assert bal['supplier_name'] == "Global Materials Ltd"

        stmt = SupplierSubledgerService.get_supplier_statement(supplier.id)
        assert stmt['closing_balance'] == Decimal("4000.00")
        assert len(stmt['transactions']) == 1

    def test_supplier_aging_report(self, setup_supplier_subledger):
        user, supplier, supp_acc, exp_acc = setup_supplier_subledger

        draft = LedgerCoreService.create_draft_entry(
            date=timezone.now().date(),
            description="Recent Purchase Bill",
            reference="BILL-002",
            entry_type="purchase",
            created_by=user,
            lines_data=[
                {"account": exp_acc, "debit": Decimal("1200.00"), "credit": Decimal("0.00")},
                {"account": supp_acc, "debit": Decimal("0.00"), "credit": Decimal("1200.00")}
            ]
        )
        LedgerCoreService.post_entry(draft.id, user, posting_source="PURCHASE_BILL")

        aging = SupplierSubledgerService.get_supplier_aging_report(supplier_ids=[supplier.id])
        assert len(aging['rows']) == 1
        assert aging['rows'][0]['bucket_0_30'] == Decimal("1200.00")
        assert aging['summary']['total_balance'] == Decimal("1200.00")
