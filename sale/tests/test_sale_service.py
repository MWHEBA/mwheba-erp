"""
Tests for SaleService
اختبارات خدمة المبيعات الموحدة
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone

from sale.services import SaleService
from sale.models import Sale, SaleItem, SalePayment, SaleReturn
from client.models import Customer
from product.models import Product, Warehouse, Stock
from financial.models import JournalEntry, ChartOfAccounts

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
def customer(db, user, chart_of_accounts):
    """Create test customer using CustomerService"""
    from client.services import CustomerService
    
    # استخدام CustomerService لإنشاء العميل بشكل صحيح
    customer_service = CustomerService()
    customer = customer_service.create_customer(
        name='Test Customer',
        code='CUST001',
        phone='01234567890',
        email='customer@test.com',
        client_type='individual',
        user=user,
        create_financial_account=True
    )
    
    return customer


@pytest.fixture
def warehouse(db):
    """Create test warehouse using existing system method"""
    # استخدام get_or_create للحصول على المخزن الرئيسي أو إنشائه
    warehouse, created = Warehouse.objects.get_or_create(
        code='WH001',
        defaults={
            'name': 'Main Warehouse',
            'is_active': True
        }
    )
    return warehouse


@pytest.fixture
def product(db, warehouse, user):
    """Create test product with stock using InventoryService"""
    from product.models import Category, Unit
    from product.services.inventory_service import InventoryService
    
    # Create or get category
    category, _ = Category.objects.get_or_create(
        name='Test Category',
        defaults={'is_active': True}
    )
    
    # Create or get unit
    unit, _ = Unit.objects.get_or_create(
        symbol='pc',
        defaults={'name': 'قطعة', 'is_active': True}
    )
    
    # Create product
    product = Product.objects.create(
        name='Test Product',
        sku='TEST001',
        category=category,
        unit=unit,
        selling_price=Decimal('100.00'),
        cost_price=Decimal('60.00'),
        is_active=True,
        created_by=user
    )
    
    # Add stock using InventoryService (يستخدم MovementService داخلياً)
    InventoryService.record_movement(
        product=product,
        movement_type='in',
        quantity=Decimal('100'),
        warehouse=warehouse,
        source='initial_stock',
        unit_cost=product.cost_price,
        reference_number='INIT-001',
        notes='Initial stock for testing',
        user=user
    )
    
    return product


@pytest.fixture
def chart_of_accounts(db):
    """Setup necessary chart of accounts using get_or_create"""
    from financial.models import AccountType, AccountingPeriod
    from product.models import SerialNumber
    
    # Create accounting period for current year
    current_year = timezone.now().year
    AccountingPeriod.objects.get_or_create(
        name=f'السنة المالية {current_year}',
        start_date=timezone.datetime(current_year, 1, 1).date(),
        end_date=timezone.datetime(current_year, 12, 31).date(),
        defaults={
            'status': 'open'
        }
    )
    
    # Create serial number for sales
    SerialNumber.objects.get_or_create(
        document_type='sale',
        year=current_year,
        defaults={
            'prefix': 'SALE',
            'last_number': 0
        }
    )
    
    # Get or create account types (استخدام get_or_create بدلاً من إعادة الإنشاء)
    cash_type, _ = AccountType.objects.get_or_create(
        code='CASH',
        defaults={'name': 'نقدية', 'nature': 'debit'}
    )
    
    asset_type, _ = AccountType.objects.get_or_create(
        code='ASSET',
        defaults={'name': 'أصول', 'nature': 'debit'}
    )
    
    revenue_type, _ = AccountType.objects.get_or_create(
        code='REVENUE',
        defaults={'name': 'إيرادات', 'nature': 'credit'}
    )
    
    expense_type, _ = AccountType.objects.get_or_create(
        code='EXPENSE',
        defaults={'name': 'مصروفات', 'nature': 'debit'}
    )
    
    # Get or create accounts (استخدام get_or_create بدلاً من إعادة الإنشاء)
    accounts = {
        'cash': ChartOfAccounts.objects.get_or_create(
            code='10100',
            defaults={
                'name': 'الخزينة',
                'account_type': cash_type,
                'is_active': True
            }
        )[0],
        'bank': ChartOfAccounts.objects.get_or_create(
            code='10200',
            defaults={
                'name': 'البنك',
                'account_type': cash_type,
                'is_active': True
            }
        )[0],
        'inventory': ChartOfAccounts.objects.get_or_create(
            code='10400',
            defaults={
                'name': 'المخزون',
                'account_type': asset_type,
                'is_active': True
            }
        )[0],
        'inventory_goods': ChartOfAccounts.objects.get_or_create(
            code='10400',
            defaults={
                'name': 'مخزون البضاعة',
                'account_type': asset_type,
                'is_active': True
            }
        )[0],
        'inventory_goods_movement': ChartOfAccounts.objects.get_or_create(
            code='2010001',
            defaults={
                'name': 'مخزون البضاعة - حركة',
                'account_type': asset_type,
                'is_active': True
            }
        )[0],
        'sales_revenue': ChartOfAccounts.objects.get_or_create(
            code='40100',
            defaults={
                'name': 'إيرادات المبيعات',
                'account_type': revenue_type,
                'is_active': True
            }
        )[0],
        'cogs': ChartOfAccounts.objects.get_or_create(
            code='50100',
            defaults={
                'name': 'تكلفة البضاعة المباعة',
                'account_type': expense_type,
                'is_active': True
            }
        )[0],
    }
    
    # Create customers parent account (10300) - مطلوب للـ fallback في SaleService
    ChartOfAccounts.objects.get_or_create(
        code='10300',
        defaults={
            'name': 'مدينو العملاء',
            'account_type': asset_type,
            'is_active': True
        }
    )
    
    return accounts


@pytest.mark.django_db
class TestSaleServiceCreateSale:
    """Test SaleService.create_sale()"""
    
    def test_create_cash_sale(self, user, customer, warehouse, product, chart_of_accounts):
        """Test creating a cash sale"""
        sale_data = {
            'date': timezone.now().date(),
            'customer_id': customer.id,
            'warehouse_id': warehouse.id,
            'payment_method': 'cash',
            'discount': Decimal('0'),
            'tax': Decimal('0'),
            'notes': 'Test cash sale',
            'items': [
                {
                    'product_id': product.id,
                    'quantity': Decimal('5'),
                    'unit_price': Decimal('100.00'),
                    'discount': Decimal('0'),
                }
            ]
        }
        
        sale = SaleService.create_sale(data=sale_data, user=user)
        
        # Verify sale created
        assert sale is not None
        assert sale.customer == customer
        assert sale.warehouse == warehouse
        assert sale.payment_method == 'cash'
        assert sale.total == Decimal('500.00')
        
        # Verify items created
        assert sale.items.count() == 1
        item = sale.items.first()
        assert item.product == product
        assert item.quantity == 5
        
        # Verify journal entry created
        assert sale.journal_entry is not None
        assert sale.journal_entry.status == 'posted'
        
        # Verify stock movement created
        from product.models import StockMovement
        movements = StockMovement.objects.filter(
            reference_number__contains=f'SALE-{sale.number}'
        )
        assert movements.count() == 1
        assert movements.first().movement_type == 'out'
        assert movements.first().quantity == 5
    
    def test_create_credit_sale(self, user, customer, warehouse, product, chart_of_accounts):
        """Test creating a credit sale"""
        sale_data = {
            'date': timezone.now().date(),
            'customer_id': customer.id,
            'warehouse_id': warehouse.id,
            'payment_method': 'credit',
            'discount': Decimal('10'),
            'tax': Decimal('0'),
            'notes': 'Test credit sale',
            'items': [
                {
                    'product_id': product.id,
                    'quantity': Decimal('3'),
                    'unit_price': Decimal('100.00'),
                    'discount': Decimal('0'),
                }
            ]
        }
        
        sale = SaleService.create_sale(data=sale_data, user=user)
        
        # Refresh to get latest data
        sale.refresh_from_db()
        
        assert sale is not None
        assert sale.payment_method == 'credit'
        assert sale.subtotal == Decimal('300.00')
        assert sale.total == Decimal('290.00')  # 300 - 10 discount
        assert sale.payment_status == 'unpaid', f"Expected 'unpaid' but got '{sale.payment_status}', amount_paid={sale.amount_paid}, amount_due={sale.amount_due}"


@pytest.mark.django_db
class TestSaleServiceProcessPayment:
    """Test SaleService.process_payment()"""
    
    def test_process_payment(self, user, customer, warehouse, product, chart_of_accounts):
        """Test processing a payment on a sale"""
        # Create a credit sale first
        sale_data = {
            'date': timezone.now().date(),
            'customer_id': customer.id,
            'warehouse_id': warehouse.id,
            'payment_method': 'credit',
            'discount': Decimal('0'),
            'tax': Decimal('0'),
            'notes': 'Test sale',
            'items': [
                {
                    'product_id': product.id,
                    'quantity': Decimal('2'),
                    'unit_price': Decimal('100.00'),
                    'discount': Decimal('0'),
                }
            ]
        }
        sale = SaleService.create_sale(data=sale_data, user=user)
        
        # Process payment
        payment_data = {
            'amount': Decimal('100.00'),
            'payment_method': '10100',  # Cash account
            'payment_date': timezone.now().date(),
            'notes': 'Partial payment'
        }
        
        payment = SaleService.process_payment(sale, payment_data, user)
        
        # Verify payment created
        assert payment is not None
        assert payment.amount == Decimal('100.00')
        assert payment.status == 'posted'
        
        # Verify journal entry created
        assert payment.financial_transaction is not None
        
        # Verify sale payment status updated
        sale.refresh_from_db()
        assert sale.payment_status == 'partially_paid'
        assert sale.amount_paid == Decimal('100.00')
        assert sale.amount_due == Decimal('100.00')


@pytest.mark.django_db
class TestSaleServiceCreateReturn:
    """Test SaleService.create_return()"""
    
    def test_create_full_return(self, user, customer, warehouse, product, chart_of_accounts):
        """Test creating a full return"""
        # Create a sale first
        sale_data = {
            'date': timezone.now().date(),
            'customer_id': customer.id,
            'warehouse_id': warehouse.id,
            'payment_method': 'cash',
            'discount': Decimal('0'),
            'tax': Decimal('0'),
            'notes': 'Test sale',
            'items': [
                {
                    'product_id': product.id,
                    'quantity': Decimal('5'),
                    'unit_price': Decimal('100.00'),
                    'discount': Decimal('0'),
                }
            ]
        }
        sale = SaleService.create_sale(data=sale_data, user=user)
        sale_item = sale.items.first()
        
        # Create return
        return_data = {
            'return_date': timezone.now().date(),
            'reason': 'Defective product',
            'notes': 'Full return',
            'items': [
                {
                    'sale_item_id': sale_item.id,
                    'quantity': Decimal('5'),
                    'unit_price': Decimal('100.00'),
                }
            ]
        }
        
        sale_return = SaleService.create_return(sale, return_data, user)
        
        # Verify return created
        assert sale_return is not None
        assert sale_return.sale == sale
        assert sale_return.total == Decimal('500.00')
        assert sale_return.status == 'confirmed'
        
        # Verify return items
        assert sale_return.items.count() == 1
        
        # Verify journal entry created (reverse entry)
        assert sale_return.journal_entry is not None
        
        # Verify stock movement created (return to warehouse)
        from product.models import StockMovement
        movements = StockMovement.objects.filter(
            reference_number__contains=f'RETURN-{sale_return.number}'
        )
        assert movements.count() == 1
        assert movements.first().movement_type == 'in'
        assert movements.first().quantity == 5


@pytest.mark.django_db
class TestSaleServiceDeleteSale:
    """Test SaleService.delete_sale()"""
    
    def test_delete_sale(self, user, customer, warehouse, product, chart_of_accounts):
        """Test deleting a sale"""
        # Create a sale first
        sale_data = {
            'date': timezone.now().date(),
            'customer_id': customer.id,
            'warehouse_id': warehouse.id,
            'payment_method': 'cash',
            'discount': Decimal('0'),
            'tax': Decimal('0'),
            'notes': 'Test sale',
            'items': [
                {
                    'product_id': product.id,
                    'quantity': Decimal('3'),
                    'unit_price': Decimal('100.00'),
                    'discount': Decimal('0'),
                }
            ]
        }
        sale = SaleService.create_sale(data=sale_data, user=user)
        sale_number = sale.number
        journal_entry_id = sale.journal_entry.id if sale.journal_entry else None
        
        # Delete sale
        SaleService.delete_sale(sale, user)
        
        # Verify sale deleted
        assert not Sale.objects.filter(number=sale_number).exists()
        
        # Verify journal entry deleted
        if journal_entry_id:
            assert not JournalEntry.objects.filter(id=journal_entry_id).exists()
        
        # Verify stock movements deleted
        from product.models import StockMovement
        movements = StockMovement.objects.filter(
            reference_number__contains=f'SALE-{sale_number}'
        )
        assert movements.count() == 0


@pytest.mark.django_db
class TestSaleServiceStatistics:
    """Test SaleService.get_sale_statistics()"""
    
    def test_get_statistics(self, user, customer, warehouse, product, chart_of_accounts):
        """Test getting sale statistics"""
        # Create a sale
        sale_data = {
            'date': timezone.now().date(),
            'customer_id': customer.id,
            'warehouse_id': warehouse.id,
            'payment_method': 'credit',
            'discount': Decimal('0'),
            'tax': Decimal('0'),
            'notes': 'Test sale',
            'items': [
                {
                    'product_id': product.id,
                    'quantity': Decimal('4'),
                    'unit_price': Decimal('100.00'),
                    'discount': Decimal('0'),
                }
            ]
        }
        sale = SaleService.create_sale(data=sale_data, user=user)
        
        # Get statistics
        stats = SaleService.get_sale_statistics(sale)
        
        # Verify statistics
        assert stats['total'] == Decimal('400.00')
        assert stats['amount_paid'] == Decimal('0')
        assert stats['amount_due'] == Decimal('400.00')
        assert stats['is_fully_paid'] is False
        assert stats['items_count'] == 1
        assert stats['returns_count'] == 0
