import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone

from sale.services import SaleService
from sale.models import Sale, SaleItem
from client.models import Customer
from product.models import Product, Warehouse, Stock
from financial.models import JournalEntry, ChartOfAccounts, AccountType, AccountingPeriod

User = get_user_model()

@pytest.fixture
def test_setup(db):
    # 1. Create User
    user = User.objects.create_user(
        username='testserviceuser',
        email='testservice@example.com',
        password='testpass123'
    )

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

    from product.models import SerialNumber
    SerialNumber.objects.get_or_create(
        document_type='sale',
        year=current_year,
        defaults={
            'prefix': 'SALE',
            'last_number': 0
        }
    )

    # 2. Create Account Types
    cash_type, _ = AccountType.objects.get_or_create(code='CASH', defaults={'name': 'Cash', 'nature': 'debit'})
    asset_type, _ = AccountType.objects.get_or_create(code='ASSET', defaults={'name': 'Asset', 'nature': 'debit'})
    revenue_type, _ = AccountType.objects.get_or_create(code='REVENUE', defaults={'name': 'Revenue', 'nature': 'credit'})
    expense_type, _ = AccountType.objects.get_or_create(code='EXPENSE', defaults={'name': 'Expense', 'nature': 'debit'})

    # 3. Create Accounts
    ChartOfAccounts.objects.get_or_create(code='10100', defaults={'name': 'Cash', 'account_type': cash_type, 'is_active': True})
    ChartOfAccounts.objects.get_or_create(code='10300', defaults={'name': 'Accounts Receivable', 'account_type': asset_type, 'is_active': True})
    ChartOfAccounts.objects.get_or_create(code='10400', defaults={'name': 'Inventory', 'account_type': asset_type, 'is_active': True})
    ChartOfAccounts.objects.get_or_create(code='40100', defaults={'name': 'Sales Revenue', 'account_type': revenue_type, 'is_active': True})
    ChartOfAccounts.objects.get_or_create(code='40200', defaults={'name': 'Services Revenue', 'account_type': revenue_type, 'is_active': True})
    ChartOfAccounts.objects.get_or_create(code='50100', defaults={'name': 'COGS', 'account_type': expense_type, 'is_active': True})

    # 4. Create Customer
    customer = Customer.objects.create(
        name='Mixed Test Customer',
        code='CUST_MIXED',
        phone='01112223334',
        client_type='individual',
        created_by=user
    )

    # 5. Create Warehouse
    warehouse = Warehouse.objects.create(
        name='Mixed Test Warehouse',
        code='WH_MIXED',
        is_active=True
    )

    # 6. Create Products
    from product.models import Category, Unit
    category, _ = Category.objects.get_or_create(name='Test Category', defaults={'is_active': True})
    unit, _ = Unit.objects.get_or_create(symbol='pc', defaults={'name': 'قطعة', 'is_active': True})

    physical_product = Product.objects.create(
        name='Physical Product',
        sku='TESTPHYS01',
        category=category,
        unit=unit,
        cost_price=Decimal('50.00'),
        selling_price=Decimal('100.00'),
        is_service=False,
        is_active=True,
        created_by=user
    )

    service_product = Product.objects.create(
        name='Service Product',
        sku='TESTSERV01',
        category=category,
        unit=unit,
        cost_price=Decimal('0.00'),
        selling_price=Decimal('150.00'),
        is_service=True,
        is_active=True,
        created_by=user
    )

    # Add stock using InventoryService (which creates movement properly)
    from product.services.inventory_service import InventoryService
    InventoryService.record_movement(
        product=physical_product,
        movement_type='in',
        quantity=Decimal('10'),
        warehouse=warehouse,
        source='initial_stock',
        unit_cost=physical_product.cost_price,
        reference_number='INIT-MIXED',
        notes='Initial stock for test',
        user=user
    )

    return {
        'user': user,
        'customer': customer,
        'warehouse': warehouse,
        'physical_product': physical_product,
        'service_product': service_product
    }

@pytest.mark.django_db
def test_create_mixed_sale_invoice(test_setup):
    """
    اختبار إنشاء فاتورة مبيعات تحتوي على منتج مادي وخدمة معاً.
    يجب أن:
    1. يتم حفظ الفاتورة بنجاح.
    2. توليد حركة مخزن للمنتج المادي فقط (وتخطي الخدمة).
    3. توليد قيد محاسبي يوزع الإيرادات بالتناسب ولا يحسب تكلفة (COGS) للخدمة.
    """
    user = test_setup['user']
    customer = test_setup['customer']
    warehouse = test_setup['warehouse']
    physical_product = test_setup['physical_product']
    service_product = test_setup['service_product']

    sale_data = {
        'date': timezone.now().date(),
        'customer_id': customer.id,
        'warehouse_id': warehouse.id,
        'payment_method': 'cash',
        'discount': Decimal('50.00'), # خصم بقيمة 50 جنيه
        'tax': Decimal('0'),
        'notes': 'Mixed sale test',
        'items': [
            {
                'product_id': physical_product.id,
                'quantity': Decimal('2'), # الإجمالي قبل الخصم: 200
                'unit_price': Decimal('100.00'),
                'discount': Decimal('0'),
            },
            {
                'product_id': service_product.id,
                'quantity': Decimal('1'), # الإجمالي قبل الخصم: 150
                'unit_price': Decimal('150.00'),
                'discount': Decimal('0'),
            }
        ]
    }

    # 1. إنشاء الفاتورة
    sale = SaleService.create_sale(data=sale_data, user=user)
    assert sale is not None
    assert sale.subtotal == Decimal('350.00')
    assert sale.total == Decimal('300.00') # 350 - 50 discount

    # 2. التحقق من حركات المخزن
    from product.models import StockMovement
    # يجب أن تكون حركة المخزن للمنتج المادي فقط
    # Note: StockMovement uses source_reference, reference_number might be SALE_ITEM_{id}
    movements = StockMovement.objects.filter(product=physical_product, warehouse=warehouse, movement_type='out')
    assert movements.count() == 1
    assert movements.first().quantity == Decimal('2')

    # يجب ألا توجد أي حركة مخزنية للمنتج الخدمي
    service_movements = StockMovement.objects.filter(product=service_product)
    assert service_movements.count() == 0

    # 3. التحقق من القيد المحاسبي وتوزيع الإيرادات والتكاليف
    assert sale.journal_entry is not None
    lines = sale.journal_entry.lines.all()
    
    # قيد النقدية (مدين بـ 300)
    cash_line = lines.filter(account__code='10100').first()
    assert cash_line is not None
    assert cash_line.debit == Decimal('300.00')

    # حساب توزيع الإيرادات بالتناسب:
    # نسبة المادي = 200 / 350 = 57.1428% -> الإيراد = 300 * 57.1428% = 171.43
    # نسبة الخدمة = 150 / 350 = 42.8571% -> الإيراد = 300 * 42.8571% = 128.57
    physical_rev_line = lines.filter(account__code='40100').first()
    assert physical_rev_line is not None
    assert physical_rev_line.credit == Decimal('171.43')

    service_rev_line = lines.filter(account__code='40200').first()
    assert service_rev_line is not None
    assert service_rev_line.credit == Decimal('128.57')

    # قيد التكلفة والمخزن (فقط للمنتج المادي: 2 * 50 = 100)
    cogs_line = lines.filter(account__code='50100').first()
    assert cogs_line is not None
    assert cogs_line.debit == Decimal('100.00')

    inventory_line = lines.filter(account__code='10400').first()
    assert inventory_line is not None
    assert inventory_line.credit == Decimal('100.00')
