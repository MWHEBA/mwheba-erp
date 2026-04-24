"""
Tests for CustomerService
اختبارات خدمة العملاء الموحدة
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import override_settings

from client.services import CustomerService
from client.models import Customer
from financial.models import ChartOfAccounts, AccountType

User = get_user_model()


@pytest.fixture
def user(db):
    """Create test user"""
    return User.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='testpass123'
    )


@pytest.fixture
def chart_of_accounts(db):
    """Create necessary chart of accounts"""
    # Create asset account type if not exists
    asset_type, _ = AccountType.objects.get_or_create(
        name='أصول',
        defaults={'code': 'ASSET', 'nature': 'debit'}
    )
    
    # Create main customers account (10300)
    main_account, _ = ChartOfAccounts.objects.get_or_create(
        code='10300',
        defaults={
            'name': 'مدينو العملاء',
            'account_type': asset_type,
            'is_active': True,
            'parent': None
        }
    )
    
    return main_account


@pytest.fixture
def customer_service():
    """Create CustomerService instance"""
    return CustomerService()


@pytest.mark.django_db
class TestCustomerServiceCreateCustomer:
    """Test CustomerService.create_customer()"""
    
    def test_create_customer_with_financial_account(self, user, chart_of_accounts, customer_service):
        """Test creating a customer - financial account created automatically by signal"""
        customer = customer_service.create_customer(
            name='Test Customer',
            code='CUST001',
            phone='01234567890',
            email='customer@test.com',
            client_type='individual',
            user=user
        )
        
        # Verify customer created
        assert customer is not None
        assert customer.name == 'Test Customer'
        assert customer.code == 'CUST001'
        assert customer.phone == '01234567890'
        assert customer.email == 'customer@test.com'
        
        # Verify financial account created automatically by signal
        assert customer.financial_account is not None
        assert customer.financial_account.is_active is True
        assert customer.financial_account.code.startswith('1103')  # Sub-account of main customers account
    
    def test_create_customer_without_financial_account(self, user, chart_of_accounts, customer_service):
        """Test creating a customer with signal disabled"""
        with override_settings(AUTO_CREATE_CUSTOMER_ACCOUNTS=False):
            customer = customer_service.create_customer(
                name='Test Customer 2',
                code='CUST002',
                phone='01234567891',
                user=user
            )
        
        assert customer is not None
        assert customer.code == 'CUST002'
        assert customer.name == 'Test Customer 2'
        # Signal was disabled, so no financial account should be created
        assert customer.financial_account is None
    
    def test_create_customer_duplicate_code(self, user, chart_of_accounts, customer_service):
        """Test creating a customer with duplicate code raises error"""
        # Create first customer
        customer_service.create_customer(
            name='First Customer',
            code='CUST003',
            phone='01234567892',
            user=user
        )
        
        # Try to create second customer with same code
        with pytest.raises(ValidationError):
            customer_service.create_customer(
                name='Second Customer',
                code='CUST003',  # Duplicate code
                phone='01234567893',
                user=user
            )


@pytest.mark.django_db
class TestCustomerServiceUpdateCustomer:
    """Test CustomerService.update_customer()"""
    
    def test_update_customer(self, user, chart_of_accounts, customer_service):
        """Test updating customer information"""
        # Create customer first
        customer = customer_service.create_customer(
            name='Original Name',
            code='CUST004',
            phone='01234567894',
            user=user
        )
        
        # Update customer
        updated_customer = customer_service.update_customer(
            customer=customer,
            name='Updated Name',
            email='updated@test.com',
            user=user
        )
        
        assert updated_customer.name == 'Updated Name'
        assert updated_customer.email == 'updated@test.com'
        assert updated_customer.code == 'CUST004'  # Code unchanged


@pytest.mark.django_db
class TestCustomerServiceFinancialAccount:
    """Test financial account creation via signal (Single Source of Truth)"""
    
    def test_financial_account_created_automatically_by_signal(self, user, chart_of_accounts, customer_service):
        """Test that financial account is created automatically by post_save signal"""
        # Create customer - signal should create financial account automatically
        customer = Customer.objects.create(
            name='Test Customer',
            code='CUST005',
            phone='01234567895',
            created_by=user
        )
        
        # Refresh to get the account created by signal
        customer.refresh_from_db()
        
        # Verify account was created by signal
        assert customer.financial_account is not None
        assert customer.financial_account.is_active is True
        assert customer.financial_account.code.startswith('1030')
        assert customer.financial_account.parent.code == '10300'
        assert customer.name in customer.financial_account.name


@pytest.mark.django_db
class TestCustomerServiceStatistics:
    """Test CustomerService.get_customer_statistics()"""
    
    def test_get_customer_statistics(self, user, chart_of_accounts, customer_service):
        """Test getting customer statistics"""
        customer = customer_service.create_customer(
            name='Test Customer',
            code='CUST006',
            phone='01234567896',
            user=user
        )
        
        # Get statistics
        stats = customer_service.get_customer_statistics(customer)
        
        assert 'total_sales' in stats
        assert 'total_payments' in stats
        assert 'actual_balance' in stats  # Changed from 'balance' to 'actual_balance'
        assert stats['total_sales'] == Decimal('0')
        assert stats['total_payments'] == Decimal('0')
        assert stats['actual_balance'] == Decimal('0')


@pytest.mark.django_db
class TestCustomerServiceBalance:
    """Test CustomerService.calculate_balance()"""
    
    def test_calculate_balance_new_customer(self, user, chart_of_accounts, customer_service):
        """Test calculating balance for new customer with no transactions"""
        customer = customer_service.create_customer(
            name='Test Customer',
            code='CUST007',
            phone='01234567897',
            user=user
        )
        
        balance = customer_service.calculate_balance(customer)
        
        assert balance == Decimal('0')
