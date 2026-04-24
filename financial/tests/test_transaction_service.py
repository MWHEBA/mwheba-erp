"""
Tests for TransactionService
"""
import pytest
from decimal import Decimal
from datetime import date
from django.contrib.auth import get_user_model
from financial.models import FinancialTransaction, ChartOfAccounts, JournalEntry, AccountType

User = get_user_model()


@pytest.fixture
def test_user(db):
    """Create test user"""
    return User.objects.create_user(
        username='testuser',
        email='test@test.com',
        password='testpass123',
        is_staff=True
    )


@pytest.fixture
def cash_account(db):
    """Get or create cash account"""
    account = ChartOfAccounts.objects.filter(code='10100').first()
    if not account:
        # Create account type if needed
        account_type, _ = AccountType.objects.get_or_create(
            name='Cash',
            defaults={'category': 'asset', 'code': '10100'}
        )
        account = ChartOfAccounts.objects.create(
            code='10100',
            name='Cash',
            account_type=account_type,
            is_active=True
        )
    return account


@pytest.fixture
def revenue_account(db):
    """Get or create revenue account"""
    account = ChartOfAccounts.objects.filter(code='40000').first()
    if not account:
        account_type, _ = AccountType.objects.get_or_create(
            name='Revenue',
            defaults={'category': 'revenue', 'code': '40000'}
        )
        account = ChartOfAccounts.objects.create(
            code='40000',
            name='Revenue',
            account_type=account_type,
            is_active=True
        )
    return account


@pytest.fixture
def accounting_period(db):
    """Get or create accounting period for current year"""
    from financial.models import AccountingPeriod
    from datetime import date
    
    current_year = date.today().year
    start_date = date(current_year, 1, 1)
    end_date = date(current_year, 12, 31)
    
    period, _ = AccountingPeriod.objects.get_or_create(
        start_date=start_date,
        end_date=end_date,
        defaults={
            'name': f'Fiscal Year {current_year}',
            'status': 'open'
        }
    )
    return period


@pytest.mark.django_db
class TestTransactionService:
    """Test TransactionService functionality"""
    
    def test_create_income_transaction_entry(self, test_user, cash_account, revenue_account, accounting_period):
        """Test creating journal entry for income transaction"""
        from financial.services.transaction_service import TransactionService
        
        # Create transaction
        txn = FinancialTransaction.objects.create(
            transaction_type='income',
            account=cash_account,
            amount=Decimal('1000.00'),
            date=date.today(),
            title='Test Income',
            description='Testing service',
            status='approved',
            created_by=test_user
        )
        
        # Test service
        entry = TransactionService.create_transaction_entry(txn, test_user)
        
        # Assertions
        assert entry is not None, "Service should return journal entry"
        assert entry.lines.count() == 2, "Entry should have 2 lines"
        
        total_debit = sum(line.debit for line in entry.lines.all())
        total_credit = sum(line.credit for line in entry.lines.all())
        assert total_debit == total_credit, "Entry should be balanced"
        assert total_debit == Decimal('1000.00'), "Total should match transaction amount"
        
        # Check idempotency key
        assert entry.idempotency_key is not None
        assert 'financial:FinancialTransaction' in entry.idempotency_key
        
        # Check source linkage
        assert entry.source_module == 'financial'
        assert entry.source_model == 'FinancialTransaction'
        assert entry.source_id == txn.id
    
    def test_model_calls_service(self, test_user, cash_account, revenue_account, accounting_period):
        """Test that Transaction model can call service through create_journal_entry"""
        # Create transaction
        txn = FinancialTransaction.objects.create(
            transaction_type='income',
            account=cash_account,
            amount=Decimal('750.00'),
            date=date.today(),
            title='Test Model Integration',
            status='approved',
            created_by=test_user
        )
        
        # Test model method
        entry = txn.create_journal_entry()
        
        # Assertions
        assert entry is not None, "Model method should return journal entry"
        assert entry.source_id == txn.id

