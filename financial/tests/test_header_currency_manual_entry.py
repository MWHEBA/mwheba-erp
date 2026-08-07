import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.currency import Currency, ExchangeRate
from financial.models.cost_center import CostCenter
from financial.models.fiscal_year import FiscalYear
from financial.models.journal_entry import JournalEntry, JournalEntryLine, AccountingPeriod
from financial.services.ledger_core_service import LedgerCoreService

User = get_user_model()

@pytest.mark.django_db
class TestHeaderCurrencyManualEntry:

    @pytest.fixture(autouse=True)
    def setup_data(self):
        self.user, _ = User.objects.get_or_create(username='admin', defaults={'is_superuser': True})
        
        # Currencies
        self.egp, _ = Currency.objects.get_or_create(code='EGP', defaults={'name': 'جنيه مصري', 'symbol': 'ج.م', 'is_functional': True, 'is_active': True})
        self.usd, _ = Currency.objects.get_or_create(code='USD', defaults={'name': 'دولار أمريكي', 'symbol': '$', 'is_functional': False, 'is_active': True})
        
        ExchangeRate.objects.get_or_create(
            from_currency=self.usd,
            to_currency=self.egp,
            defaults={'rate': Decimal('50.123456'), 'effective_date': timezone.now().date()}
        )

        # Account types
        self.asset_type, _ = AccountType.objects.get_or_create(code='ASSET', defaults={'name': 'أصول', 'nature': 'DEBIT', 'category': 'asset'})
        self.expense_type, _ = AccountType.objects.get_or_create(code='EXPENSE', defaults={'name': 'مصروفات', 'nature': 'DEBIT', 'category': 'expense'})
        
        # Accounts
        self.cash_account, _ = ChartOfAccounts.objects.get_or_create(code='10100', defaults={'name': 'النقدية بالخزينة', 'account_type': self.asset_type, 'is_active': True, 'is_leaf': True})
        self.rent_account, _ = ChartOfAccounts.objects.get_or_create(code='50100', defaults={'name': 'مصروف الإيجار', 'account_type': self.expense_type, 'is_active': True, 'is_leaf': True})
        
        today = timezone.now().date()
        self.fiscal_year, _ = FiscalYear.objects.get_or_create(
            name=f"السنة المالية {today.year}",
            defaults={
                'start_date': today.replace(month=1, day=1),
                'end_date': today.replace(month=12, day=31),
                'status': 'open'
            }
        )
        
        self.period, _ = AccountingPeriod.objects.get_or_create(
            fiscal_year=self.fiscal_year,
            period_number=today.month,
            defaults={
                'name': f"فترة {today.month}",
                'start_date': today.replace(day=1),
                'end_date': today.replace(day=28),
                'status': 'open'
            }
        )

    def test_create_foreign_currency_journal_entry(self):
        """اختبار إنشاء قيد يدوي بالدولار (USD @ 50.123456) والتحقق من تحويل المبالغ المحلية والأجنبية"""
        rate = Decimal("50.123456")
        foreign_amount = Decimal("100.00")
        expected_func_debit = (foreign_amount * rate).quantize(Decimal("0.01"))  # 5012.35 EGP

        lines_data = [
            {
                "account_code": self.rent_account.code,
                "debit": expected_func_debit,
                "credit": Decimal("0.00"),
                "foreign_debit": foreign_amount,
                "foreign_credit": Decimal("0.00"),
                "currency": "USD",
                "exchange_rate": rate,
                "description": "إيجار بالدولار"
            },
            {
                "account_code": self.cash_account.code,
                "debit": Decimal("0.00"),
                "credit": expected_func_debit,
                "foreign_debit": Decimal("0.00"),
                "foreign_credit": foreign_amount,
                "currency": "USD",
                "exchange_rate": rate,
                "description": "سداد بالدولار"
            }
        ]

        draft_entry = LedgerCoreService.create_draft_entry(
            date=timezone.now().date(),
            description='قيد إيجار بالعملة الأجنبية',
            reference='REF-USD-001',
            entry_type='manual',
            created_by=self.user,
            lines_data=lines_data
        )

        assert draft_entry.status == 'draft'
        assert draft_entry.lines.count() == 2

        rent_line = draft_entry.lines.get(account=self.rent_account)
        assert rent_line.currency == "USD"
        assert rent_line.exchange_rate == rate
        assert rent_line.debit == expected_func_debit
        assert rent_line.transaction_debit == foreign_amount
