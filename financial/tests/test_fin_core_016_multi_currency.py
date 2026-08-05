import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from financial.models.currency import Currency, ExchangeRate
from financial.services.exchange_rate_service import ExchangeRateService
from financial.models import ChartOfAccounts, AccountType, AccountingPeriod, FiscalYear, JournalEntry, JournalEntryLine

User = get_user_model()


@pytest.mark.django_db(transaction=True)
class TestFINCORE016MultiCurrencyFoundation:

    @pytest.fixture
    def setup_currency_data(self):
        user = User.objects.create_user(username="curr_user16", password="password123")

        base_curr, _ = Currency.objects.get_or_create(code="EGP", defaults={"name": "Egyptian Pound", "symbol": "EGP", "is_functional": True})
        usd_curr, _ = Currency.objects.get_or_create(code="USD", defaults={"name": "US Dollar", "symbol": "$", "is_functional": False})

        ExchangeRateService.set_rate(from_code="USD", to_code="EGP", rate=Decimal("48.500000"), date=timezone.now().date(), user=user)

        asset_type, _ = AccountType.objects.get_or_create(code="ASSET", defaults={"name": "Asset", "category": "ASSET"})
        revenue_type, _ = AccountType.objects.get_or_create(code="REVENUE", defaults={"name": "Revenue", "category": "REVENUE"})

        ar_acc, _ = ChartOfAccounts.objects.get_or_create(code="11010_USD", defaults={"name": "Customer AR Foreign", "account_type": asset_type, "is_active": True})
        sales_acc, _ = ChartOfAccounts.objects.get_or_create(code="40100_USD", defaults={"name": "Sales Revenue Foreign", "account_type": revenue_type, "is_active": True})

        today = timezone.now().date()
        AccountingPeriod.objects.get_or_create(
            name=f"Period_{today.year}_{today.month}",
            start_date=today.replace(day=1),
            end_date=today.replace(day=28),
            defaults={"status": "open"}
        )

        return user, base_curr, usd_curr, ar_acc, sales_acc

    def test_currency_and_exchange_rate_service(self, setup_currency_data):
        user, base_curr, usd_curr, ar_acc, sales_acc = setup_currency_data

        rate = ExchangeRateService.get_rate("USD", "EGP")
        assert rate == Decimal("48.500000")

        conversion = ExchangeRateService.convert_amount(Decimal("1000.00"), "USD", "EGP")
        assert conversion["foreign_amount"] == Decimal("1000.00")
        assert conversion["exchange_rate"] == Decimal("48.500000")
        assert conversion["functional_amount"] == Decimal("48500.00")

    def test_journal_entry_line_foreign_currency_dimension(self, setup_currency_data):
        user, base_curr, usd_curr, ar_acc, sales_acc = setup_currency_data

        je = JournalEntry.objects.create(
            date=timezone.now().date(),
            entry_type="manual",
            status="draft",
            description="Foreign Currency Sale Entry",
            created_by=user
        )

        # Dr. AR Foreign 1,000 USD @ 48.50 = 48,500 EGP
        line1 = JournalEntryLine.objects.create(
            journal_entry=je,
            account=ar_acc,
            debit=Decimal("48500.00"),
            credit=Decimal("0.00"),
            currency="USD",
            foreign_debit=Decimal("1000.00"),
            foreign_credit=Decimal("0.00"),
            exchange_rate=Decimal("48.500000"),
            description="USD Invoice AR Debit"
        )

        # Cr. Sales Foreign 1,000 USD @ 48.50 = 48,500 EGP
        line2 = JournalEntryLine.objects.create(
            journal_entry=je,
            account=sales_acc,
            debit=Decimal("0.00"),
            credit=Decimal("48500.00"),
            currency="USD",
            foreign_debit=Decimal("0.00"),
            foreign_credit=Decimal("1000.00"),
            exchange_rate=Decimal("48.500000"),
            description="USD Invoice Sales Credit"
        )

        assert line1.currency == "USD"
        assert line1.foreign_debit == Decimal("1000.00")
        assert line1.exchange_rate == Decimal("48.500000")
        assert line1.debit == Decimal("48500.00")

        assert je.is_balanced is True
