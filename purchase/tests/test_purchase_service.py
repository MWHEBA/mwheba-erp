"""
Tests for PurchaseService
اختبارات خدمة المشتريات الموحدة
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone

from purchase.services.purchase_service import PurchaseService
from purchase.models import Purchase, PurchaseItem, PurchasePayment, PurchaseReturn
from supplier.models import Supplier
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
def supplier(db, user, chart_of_accounts):
    """Create test supplier using SupplierService"""
    from supplier.services.supplier_service import SupplierService
    
    # استخدام SupplierService لإنشاء المورد بشكل صحيح
    supplier = SupplierService.create_supplier(
        name='Test Supplier',
        code='SUPP001',
        phone='01234567890',
        email='supplier@test.com',
        user=user,
        create_financial_account=True
    )
    
    return supplier


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
def product(db, user):
    """Create test product"""
    from product.models import Category, Unit
    
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
    
    # Create serial number for purchases
    SerialNumber.objects.get_or_create(
        document_type='purchase',
        year=current_year,
        defaults={
            'prefix': 'PURCH',
            'last_number': 0
        }
    )
    
    # Get or create account types
    cash_type, _ = AccountType.objects.get_or_create(
        code='CASH',
        defaults={'name': 'نقدية', 'nature': 'debit'}
    )
    
    asset_type, _ = AccountType.objects.get_or_create(
        code='ASSET',
        defaults={'name': 'أصول', 'nature': 'debit'}
    )
    
    liability_type, _ = AccountType.objects.get_or_create(
        code='LIABILITY',
        defaults={'name': 'خصوم', 'nature': 'credit'}
    )
    
    expense_type, _ = AccountType.objects.get_or_create(
        code='EXPENSE',
        defaults={'name': 'مصروفات', 'nature': 'debit'}
    )
    
    # Get or create accounts
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
        'suppliers': ChartOfAccounts.objects.get_or_create(
            code='20100',
            defaults={
                'name': 'الموردون',
                'account_type': liability_type,
                'is_active': True
            }
        )[0],
        'general_expenses': ChartOfAccounts.objects.get_or_create(
            code='50300',
            defaults={
                'name': 'مصروفات إدارية',
                'account_type': expense_type,
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
    
    return accounts


@pytest.mark.django_db
class TestPurchaseServiceCreatePurchase:
    """Test PurchaseService.create_purchase()"""
    
    def test_create_cash_purchase(self, user, supplier, warehouse, product, chart_of_accounts):
        """Test creating a cash purchase"""
        purchase_data = {
            'date': timezone.now().date(),
            'supplier_id': supplier.id,
            'warehouse_id': warehouse.id,
            'payment_method': 'cash',
            'discount': Decimal('0'),
            'tax': Decimal('0'),
            'notes': 'Test cash purchase',
            'items': [
                {
                    'product_id': product.id,
                    'quantity': Decimal('10'),
                    'unit_price': Decimal('60.00'),
                    'discount': Decimal('0'),
                }
            ]
        }
        
        purchase = PurchaseService.create_purchase(data=purchase_data, user=user)
        
        # Verify purchase created
        assert purchase is not None
        assert purchase.supplier == supplier
        assert purchase.warehouse == warehouse
        assert purchase.payment_method == 'cash'
        assert purchase.total == Decimal('600.00')
        
        # Verify items created
        assert purchase.items.count() == 1
        item = purchase.items.first()
        assert item.product == product
        assert item.quantity == 10
        
        # Verify journal entry created
        assert purchase.journal_entry is not None
        assert purchase.journal_entry.status == 'posted'
        
        # Verify stock movement created
        from product.models import StockMovement
        movements = StockMovement.objects.filter(
            reference_number__contains=f'PURCHASE-{purchase.number}'
        )
        assert movements.count() == 1
        assert movements.first().movement_type == 'in'
        assert movements.first().quantity == 10
    
    def test_create_credit_purchase(self, user, supplier, warehouse, product, chart_of_accounts):
        """Test creating a credit purchase"""
        purchase_data = {
            'date': timezone.now().date(),
            'supplier_id': supplier.id,
            'warehouse_id': warehouse.id,
            'payment_method': 'credit',
            'discount': Decimal('20'),
            'tax': Decimal('0'),
            'notes': 'Test credit purchase',
            'items': [
                {
                    'product_id': product.id,
                    'quantity': Decimal('5'),
                    'unit_price': Decimal('60.00'),
                    'discount': Decimal('0'),
                }
            ]
        }
        
        purchase = PurchaseService.create_purchase(data=purchase_data, user=user)
        
        # Refresh to get latest data
        purchase.refresh_from_db()
        
        assert purchase is not None
        assert purchase.payment_method == 'credit'
        assert purchase.subtotal == Decimal('300.00')
        assert purchase.total == Decimal('280.00')  # 300 - 20 discount
        assert purchase.payment_status == 'unpaid'


@pytest.mark.django_db
class TestPurchaseServiceProcessPayment:
    """Test PurchaseService.process_payment()"""
    
    def test_process_payment(self, user, supplier, warehouse, product, chart_of_accounts):
        """Test processing a payment on a purchase"""
        # Create a credit purchase first
        purchase_data = {
            'date': timezone.now().date(),
            'supplier_id': supplier.id,
            'warehouse_id': warehouse.id,
            'payment_method': 'credit',
            'discount': Decimal('0'),
            'tax': Decimal('0'),
            'notes': 'Test purchase',
            'items': [
                {
                    'product_id': product.id,
                    'quantity': Decimal('4'),
                    'unit_price': Decimal('60.00'),
                    'discount': Decimal('0'),
                }
            ]
        }
        purchase = PurchaseService.create_purchase(data=purchase_data, user=user)
        
        # Process payment
        payment_data = {
            'amount': Decimal('120.00'),
            'payment_method': '10100',  # Cash account
            'payment_date': timezone.now().date(),
            'notes': 'Partial payment'
        }
        
        payment = PurchaseService.process_payment(purchase, payment_data, user)
        
        # Verify payment created
        assert payment is not None
        assert payment.amount == Decimal('120.00')
        assert payment.status == 'posted'
        
        # Verify journal entry created
        assert payment.financial_transaction is not None
        
        # Verify purchase payment status updated
        purchase.refresh_from_db()
        assert purchase.payment_status == 'partially_paid'
        assert purchase.amount_paid == Decimal('120.00')
        assert purchase.amount_due == Decimal('120.00')


@pytest.mark.django_db
class TestPurchaseServiceCreateReturn:
    """Test PurchaseService.create_return()"""
    
    def test_create_full_return(self, user, supplier, warehouse, product, chart_of_accounts):
        """Test creating a full return"""
        # Create a purchase first
        purchase_data = {
            'date': timezone.now().date(),
            'supplier_id': supplier.id,
            'warehouse_id': warehouse.id,
            'payment_method': 'cash',
            'discount': Decimal('0'),
            'tax': Decimal('0'),
            'notes': 'Test purchase',
            'items': [
                {
                    'product_id': product.id,
                    'quantity': Decimal('8'),
                    'unit_price': Decimal('60.00'),
                    'discount': Decimal('0'),
                }
            ]
        }
        purchase = PurchaseService.create_purchase(data=purchase_data, user=user)
        purchase_item = purchase.items.first()
        
        # Create return
        return_data = {
            'return_date': timezone.now().date(),
            'reason': 'Defective product',
            'notes': 'Full return',
            'items': [
                {
                    'purchase_item_id': purchase_item.id,
                    'quantity': Decimal('8'),
                    'unit_price': Decimal('60.00'),
                }
            ]
        }
        
        purchase_return = PurchaseService.create_return(purchase, return_data, user)
        
        # Verify return created
        assert purchase_return is not None
        assert purchase_return.purchase == purchase
        assert purchase_return.total == Decimal('480.00')
        assert purchase_return.status == 'confirmed'
        
        # Verify return items
        assert purchase_return.items.count() == 1
        
        # Verify stock movement created (return from warehouse)
        from product.models import StockMovement
        movements = StockMovement.objects.filter(
            reference_number__contains=f'RETURN-{purchase_return.number}'
        )
        assert movements.count() == 1
        assert movements.first().movement_type == 'out'
        assert movements.first().quantity == 8  # Positive value, direction determined by movement_type


@pytest.mark.django_db
class TestPurchaseServiceDeletePurchase:
    """Test PurchaseService.delete_purchase()"""
    
    def test_delete_purchase(self, user, supplier, warehouse, product, chart_of_accounts):
        """Test deleting a purchase"""
        # Create a purchase first
        purchase_data = {
            'date': timezone.now().date(),
            'supplier_id': supplier.id,
            'warehouse_id': warehouse.id,
            'payment_method': 'cash',
            'discount': Decimal('0'),
            'tax': Decimal('0'),
            'notes': 'Test purchase',
            'items': [
                {
                    'product_id': product.id,
                    'quantity': Decimal('6'),
                    'unit_price': Decimal('60.00'),
                    'discount': Decimal('0'),
                }
            ]
        }
        purchase = PurchaseService.create_purchase(data=purchase_data, user=user)
        purchase_number = purchase.number
        journal_entry_id = purchase.journal_entry.id if purchase.journal_entry else None
        
        # Delete purchase
        PurchaseService.delete_purchase(purchase, user)
        
        # Verify purchase deleted
        assert not Purchase.objects.filter(number=purchase_number).exists()
        
        # Verify journal entry deleted
        if journal_entry_id:
            assert not JournalEntry.objects.filter(id=journal_entry_id).exists()
        
        # Verify stock movements deleted
        from product.models import StockMovement
        movements = StockMovement.objects.filter(
            reference_number__contains=f'PURCHASE-{purchase_number}'
        )
        assert movements.count() == 0


@pytest.mark.django_db
class TestPurchaseServiceStatistics:
    """Test PurchaseService.get_purchase_statistics()"""
    
    def test_get_statistics(self, user, supplier, warehouse, product, chart_of_accounts):
        """Test getting purchase statistics"""
        # Create a purchase
        purchase_data = {
            'date': timezone.now().date(),
            'supplier_id': supplier.id,
            'warehouse_id': warehouse.id,
            'payment_method': 'credit',
            'discount': Decimal('0'),
            'tax': Decimal('0'),
            'notes': 'Test purchase',
            'items': [
                {
                    'product_id': product.id,
                    'quantity': Decimal('7'),
                    'unit_price': Decimal('60.00'),
                    'discount': Decimal('0'),
                }
            ]
        }
        purchase = PurchaseService.create_purchase(data=purchase_data, user=user)
        
        # Get statistics
        stats = PurchaseService.get_purchase_statistics(purchase)
        
        # Verify statistics
        assert stats['total'] == Decimal('420.00')
        assert stats['amount_paid'] == Decimal('0')
        assert stats['amount_due'] == Decimal('420.00')
        assert stats['is_fully_paid'] is False
        assert stats['items_count'] == 1
        assert stats['returns_count'] == 0
