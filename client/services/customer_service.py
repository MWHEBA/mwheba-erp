"""
CustomerService - Unified Service for Customer Operations

This service provides a centralized interface for all customer-related operations
with full governance compliance using AccountingGateway.

Key Features:
- Customer creation and management
- Automatic financial account creation through AccountingGateway
- Balance calculations and statements
- Thread-safe operations with proper validation
- Full audit trail integration

Usage:
    service = CustomerService()
    customer = service.create_customer(
        name="Customer Name",
        code="CUST001",
        user=request.user
    )
"""

import logging
from decimal import Decimal
from typing import Optional, Dict, Any, List
from datetime import datetime

from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from ..models import Customer
from financial.models import ChartOfAccounts
from governance.services.accounting_gateway import AccountingGateway, JournalEntryLineData
from governance.services.audit_service import AuditService
from governance.models import GovernanceContext

User = get_user_model()
logger = logging.getLogger(__name__)


class CustomerService:
    """
    Unified service for customer operations with governance compliance.
    """
    
    def __init__(self):
        """Initialize the CustomerService with required services"""
        self.accounting_gateway = AccountingGateway()
        self.audit_service = AuditService
    
    def create_customer(
        self,
        name: str,
        code: str,
        user: User,
        phone: str = '',
        email: str = '',
        address: str = '',
        city: str = '',
        company_name: str = '',
        client_type: str = 'individual',
        credit_limit: Decimal = Decimal('0'),
        tax_number: str = '',
        notes: str = ''
    ) -> Customer:
        """
        Create a new customer.
        
        Financial account creation is handled automatically by the post_save signal.
        
        Args:
            name: Customer name
            code: Customer code (must be unique)
            user: User creating the customer
            phone: Phone number
            email: Email address
            address: Address
            city: City
            company_name: Company name (if applicable)
            client_type: Type of client (individual, company, government, vip)
            credit_limit: Credit limit
            tax_number: Tax number
            notes: Additional notes
            
        Returns:
            Customer: The created customer instance
            
        Raises:
            ValidationError: If validation fails
        """
        operation_start = timezone.now()
        
        try:
            with transaction.atomic():
                # Set governance context
                GovernanceContext.set_context(
                    user=user,
                    service='CustomerService',
                    operation='create_customer'
                )
                
                # Validate customer code uniqueness
                if Customer.objects.filter(code=code).exists():
                    raise ValidationError(f"Customer code '{code}' already exists")
                
                # Create customer (signal will create financial account automatically)
                customer = Customer(
                    name=name,
                    code=code,
                    phone=phone,
                    email=email,
                    address=address,
                    city=city,
                    company_name=company_name,
                    client_type=client_type,
                    credit_limit=credit_limit,
                    tax_number=tax_number,
                    notes=notes,
                    created_by=user,
                    is_active=True
                )
                customer.save()
                
                # Refresh to get the financial_account created by signal
                customer.refresh_from_db()
                
                # Create audit trail
                self.audit_service.log_operation(
                    model_name='Customer',
                    object_id=customer.id,
                    operation='CREATE',
                    user=user,
                    source_service='CustomerService',
                    after_data={
                        'name': customer.name,
                        'code': customer.code,
                        'client_type': customer.client_type,
                        'financial_account_code': customer.financial_account.code if customer.financial_account else None
                    },
                    operation_duration=(timezone.now() - operation_start).total_seconds()
                )
                
                logger.info(f"Customer created successfully: {customer.code} - {customer.name}")
                
                return customer
                
        except Exception as e:
            logger.error(f"Failed to create customer: {str(e)}")
            raise
        
        finally:
            GovernanceContext.clear_context()
    
    @transaction.atomic
    def create_financial_account_for_customer(
        self,
        customer: Customer,
        user: User
    ) -> ChartOfAccounts:
        """
        Create financial account for customer using proper account structure.
        
        This method creates a sub-account under the main Customers account (10300)
        following the proper chart of accounts hierarchy.
        
        Uses idempotency to prevent duplicate account creation.
        
        Args:
            customer: Customer instance
            user: User creating the account
            
        Returns:
            ChartOfAccounts: The created financial account
            
        Raises:
            ValidationError: If account creation fails
        """
        from governance.services.idempotency_service import IdempotencyService
        
        # Generate idempotency key for this operation
        idempotency_key = IdempotencyService.generate_key(
            'CUSTOMER_ACCOUNT',
            customer.id,
            customer.code
        )
        
        # Check if account already created
        exists, record, result_data = IdempotencyService.check_operation_exists(
            operation_type='create_customer_account',
            idempotency_key=idempotency_key
        )
        
        if exists and result_data:
            # Account already created, return existing account
            account_id = result_data.get('account_id')
            if account_id:
                try:
                    account = ChartOfAccounts.objects.get(id=account_id)
                    logger.info(
                        f"✅ Idempotency: Returning existing account {account.code} "
                        f"for customer {customer.code}"
                    )
                    return account
                except ChartOfAccounts.DoesNotExist:
                    # Account was deleted, continue to create new one
                    logger.warning(
                        f"⚠️ Idempotency record exists but account {account_id} not found. "
                        f"Creating new account."
                    )
        
        try:
            from financial.models import AccountType
            
            # Get or create the main customers account (10300)
            customers_parent = ChartOfAccounts.objects.filter(code='10300').first()
            
            if not customers_parent:
                # Create main customers account if not exists
                asset_type = AccountType.objects.filter(code='RECEIVABLES').first()
                if not asset_type:
                    asset_type = AccountType.objects.filter(code='ASSET').first()
                
                customers_parent = ChartOfAccounts.objects.create(
                    code='10300',
                    name='مدينو العملاء',
                    name_en='Customers Receivables',
                    account_type=asset_type,
                    is_active=True,
                    is_leaf=False
                )
                logger.info(f"Created main customers account: {customers_parent.code}")
            
            # Generate account code under 10300
            last_customer_account = ChartOfAccounts.objects.filter(
                code__startswith='1030',
                parent=customers_parent
            ).exclude(code='10300').order_by('-code').first()
            
            if last_customer_account:
                try:
                    last_number = int(last_customer_account.code[4:])
                    new_number = last_number + 1
                except (ValueError, AttributeError, IndexError):
                    new_number = 1
            else:
                new_number = 1
            
            # Generate new code (1030 + 4 digits)
            next_code = f"1030{new_number:04d}"
            
            # Ensure code uniqueness
            while ChartOfAccounts.objects.filter(code=next_code).exists():
                new_number += 1
                next_code = f"1030{new_number:04d}"
            
            # Create the account
            account = ChartOfAccounts.objects.create(
                code=next_code,
                name=f"{customer.name} - {customer.code}",
                name_en=f"{customer.name} - {customer.code}",
                parent=customers_parent,
                account_type=customers_parent.account_type,
                is_active=True,
                is_leaf=True,
                description=f"Customer account for {customer.name}"
            )
            
            # Record idempotency to prevent future duplicates
            IdempotencyService.check_and_record_operation(
                operation_type='create_customer_account',
                idempotency_key=idempotency_key,
                result_data={
                    'account_id': account.id,
                    'account_code': account.code,
                    'customer_id': customer.id,
                    'customer_code': customer.code
                },
                user=user,
                expires_in_hours=720  # 30 days
            )
            
            logger.info(
                f"✅ Financial account created for customer {customer.code}: "
                f"{account.code} - {account.name}"
            )
            
            return account
            
        except Exception as e:
            logger.error(
                f"Failed to create financial account for customer {customer.code}: {str(e)}"
            )
            raise ValidationError(f"Failed to create financial account: {str(e)}")
    
    def update_customer(
        self,
        customer: Customer,
        user: User,
        **update_fields
    ) -> Customer:
        """
        Update customer information.
        
        Args:
            customer: Customer instance to update
            user: User performing the update
            **update_fields: Fields to update
            
        Returns:
            Customer: Updated customer instance
        """
        operation_start = timezone.now()
        
        try:
            # Set governance context
            GovernanceContext.set_context(
                user=user,
                service='CustomerService',
                operation='update_customer'
            )
            
            # Store old values for audit
            old_values = {
                field: getattr(customer, field)
                for field in update_fields.keys()
                if hasattr(customer, field)
            }
            
            # Update fields
            for field, value in update_fields.items():
                if hasattr(customer, field):
                    setattr(customer, field, value)
            
            customer.save()
            
            # Create audit trail
            self.audit_service.log_operation(
                model_name='Customer',
                object_id=customer.id,
                operation='UPDATE',
                user=user,
                source_service='CustomerService',
                before_data=old_values,
                after_data=update_fields,
                operation_duration=(timezone.now() - operation_start).total_seconds()
            )
            
            logger.info(f"Customer updated successfully: {customer.code}")
            
            return customer
            
        except Exception as e:
            logger.error(f"Failed to update customer {customer.code}: {str(e)}")
            raise
        
        finally:
            GovernanceContext.clear_context()
    
    def calculate_balance(self, customer: Customer) -> Decimal:
        """
        Calculate customer's actual balance from sales and payments.
        
        Args:
            customer: Customer instance
            
        Returns:
            Decimal: Actual balance (positive = customer owes us)
        """
        from django.db.models import Sum
        
        # Total sales
        total_sales = customer.sales.aggregate(
            total=Sum('total')
        )['total'] or Decimal('0')
        
        # Total payments on sales
        from sale.models import SalePayment
        total_payments = SalePayment.objects.filter(
            sale__customer=customer,
            status='posted'
        ).aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')
        
        # Balance = Sales - Payments
        return total_sales - total_payments
    
    def get_customer_statement(
        self,
        customer: Customer,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get customer statement with all transactions.
        
        Args:
            customer: Customer instance
            start_date: Start date for statement (optional)
            end_date: End date for statement (optional)
            
        Returns:
            List of transaction dictionaries with running balance
        """
        from sale.models import SalePayment
        
        transactions = []
        
        # Get sales
        sales_query = customer.sales.all()
        if start_date:
            sales_query = sales_query.filter(date__gte=start_date)
        if end_date:
            sales_query = sales_query.filter(date__lte=end_date)
        
        for sale in sales_query:
            transactions.append({
                'date': sale.created_at,
                'type': 'sale',
                'reference': sale.number,
                'description': f'Sale Invoice {sale.number}',
                'debit': sale.total,
                'credit': Decimal('0'),
                'balance': Decimal('0')  # Will be calculated
            })
        
        # Get payments
        payments_query = SalePayment.objects.filter(
            sale__customer=customer,
            status='posted'
        )
        if start_date:
            payments_query = payments_query.filter(payment_date__gte=start_date)
        if end_date:
            payments_query = payments_query.filter(payment_date__lte=end_date)
        
        for payment in payments_query:
            transactions.append({
                'date': payment.created_at,
                'type': 'payment',
                'reference': payment.reference_number or f'PAY-{payment.id}',
                'description': f'Payment on {payment.sale.number}',
                'debit': Decimal('0'),
                'credit': payment.amount,
                'balance': Decimal('0')  # Will be calculated
            })
        
        # Sort by date
        transactions.sort(key=lambda x: x['date'])
        
        # Calculate running balance
        running_balance = Decimal('0')
        for transaction in transactions:
            running_balance += transaction['debit'] - transaction['credit']
            transaction['balance'] = running_balance
        
        return transactions
    
    def get_customer_statistics(self, customer: Customer) -> Dict[str, Any]:
        """
        Get comprehensive statistics for a customer.
        
        Args:
            customer: Customer instance
            
        Returns:
            Dictionary with customer statistics
        """
        from django.db.models import Sum, Count
        from sale.models import SalePayment
        
        # Sales statistics
        sales_stats = customer.sales.aggregate(
            total_sales=Sum('total'),
            count=Count('id')
        )
        
        # Payment statistics
        payment_stats = SalePayment.objects.filter(
            sale__customer=customer,
            status='posted'
        ).aggregate(
            total_payments=Sum('amount'),
            count=Count('id')
        )
        
        # Calculate balance
        actual_balance = self.calculate_balance(customer)
        
        # Available credit
        available_credit = customer.credit_limit - actual_balance if customer.credit_limit else Decimal('0')
        
        return {
            'total_sales': sales_stats['total_sales'] or Decimal('0'),
            'sales_count': sales_stats['count'] or 0,
            'total_payments': payment_stats['total_payments'] or Decimal('0'),
            'payments_count': payment_stats['count'] or 0,
            'actual_balance': actual_balance,
            'credit_limit': customer.credit_limit,
            'available_credit': available_credit,
            'is_over_limit': actual_balance > customer.credit_limit if customer.credit_limit else False
        }
