import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from supplier.models import Supplier
from supplier.services.supplier_aging_service import SupplierAgingService
from financial.models import ChartOfAccounts, AccountType, FiscalYear, AccountingPeriod
from financial.services import LedgerCoreService, AllocationService

User = get_user_model()


@pytest.mark.django_db
class TestSupplierAgingService:

    @pytest.fixture
    def setup_supplier_aging(self):
        user = User.objects.create_user(username="supp_aging_user", password="password123")
        today = timezone.now().date()

        fiscal_year = FiscalYear.objects.create(
            year_code=f"FY-{today.year}-SAG",
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

        liability_type, _ = AccountType.objects.get_or_create(code="LIAB_SAG", defaults={"name": "Liability SAG", "category": "liability"})
        expense_type, _ = AccountType.objects.get_or_create(code="EXP_SAG", defaults={"name": "Expense SAG", "category": "expense"})

        supp_acc = ChartOfAccounts.objects.create(code="20101_SAG", name="Supplier Acc SAG", account_type=liability_type, is_active=True)
        exp_acc = ChartOfAccounts.objects.create(code="50100_SAG", name="Purchase Exp Acc SAG", account_type=expense_type, is_active=True)

        supplier = Supplier.objects.create(
            name="Vanguard Logistics",
            code="SUPP-SAG-01",
            financial_account=supp_acc,
            is_active=True
        )

        from purchase.models import Purchase
        Purchase.objects.create(
            number="PUR-SAG-001",
            supplier=supplier,
            subtotal=Decimal("5000.00"),
            total=Decimal("5000.00"),
            status="confirmed",
            payment_status="unpaid",
            date=today,
            created_by=user
        )

        # Post GL entry for supplier bill
        draft = LedgerCoreService.create_draft_entry(
            date=today,
            description="Bill #SAG-101",
            reference="BILL-SAG-101",
            entry_type="purchase",
            created_by=user,
            lines_data=[
                {"account": exp_acc, "debit": Decimal("5000.00"), "credit": Decimal("0.00")},
                {"account": supp_acc, "debit": Decimal("0.00"), "credit": Decimal("5000.00")}
            ]
        )
        LedgerCoreService.post_entry(draft.id, user, posting_source="PURCHASE_BILL")

        return user, supplier, supp_acc

    def test_supplier_open_item_aging(self, setup_supplier_aging):
        user, supplier, supp_acc = setup_supplier_aging
        today = timezone.now().date()

        aging_report = SupplierAgingService.get_supplier_open_item_aging(supplier_ids=[supplier.id], as_of_date=today)
        assert len(aging_report['rows']) == 1
        row = aging_report['rows'][0]
        assert row['net_balance'] == Decimal("5000.00")
        assert row['credit_balance'] == Decimal("0.00")
