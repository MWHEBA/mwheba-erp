import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from core.models import SystemSetting
from customer.models import Customer
from product.models import Product, Warehouse, Unit, Stock, Category
from sale.models import Sale, SaleItem, Quotation, QuotationItem
from sale.models.sales_models import SalesOrder, SalesOrderItem, DeliveryNote, DeliveryNoteItem
from purchase.models import Purchase, PurchaseItem
from supplier.models import Supplier
from purchase.models.procurement_models import (
    PurchaseOrder,
    PurchaseOrderItem,
    SupplierBill,
    SupplierBillItem,
    GoodsReceivedNote,
    GoodsReceivedNoteItem,
)
from sale.services.sale_service import SaleService
from purchase.services.procurement_service import ProcurementService
from financial.models import AccountType, ChartOfAccounts, AccountingPeriod

User = get_user_model()


@pytest.fixture
def auth_user(db):
    user = User.objects.create_superuser(
        username="phase2_admin",
        email="phase2_admin@example.com",
        password="password123"
    )
    return user


@pytest.fixture
def setup_master_data(db, auth_user):
    # Setup Accounting Period
    current_year = timezone.now().year
    AccountingPeriod.objects.get_or_create(
        start_date=timezone.datetime(current_year, 1, 1).date(),
        end_date=timezone.datetime(current_year, 12, 31).date(),
        defaults={'name': f'السنة المالية {current_year}', 'status': 'open'}
    )

    # Setup Account Types
    cash_type, _ = AccountType.objects.get_or_create(code='CASH', defaults={'name': 'نقدية', 'nature': 'debit'})
    asset_type, _ = AccountType.objects.get_or_create(code='ASSET', defaults={'name': 'أصول', 'nature': 'debit'})
    revenue_type, _ = AccountType.objects.get_or_create(code='REVENUE', defaults={'name': 'إيرادات', 'nature': 'credit'})
    expense_type, _ = AccountType.objects.get_or_create(code='EXPENSE', defaults={'name': 'مصروفات', 'nature': 'debit'})

    # Setup Standard Chart of Accounts required by SaleService & AccountingGateway
    ChartOfAccounts.objects.get_or_create(code='11110', defaults={'name': 'الخزينة', 'account_type': cash_type, 'is_active': True})
    ChartOfAccounts.objects.get_or_create(code='11160', defaults={'name': 'البنك', 'account_type': cash_type, 'is_active': True})
    ChartOfAccounts.objects.get_or_create(code='11310', defaults={'name': 'المخزون', 'account_type': asset_type, 'is_active': True})
    ChartOfAccounts.objects.get_or_create(code='11210', defaults={'name': 'مراقبة العملاء', 'account_type': asset_type, 'is_active': True})
    ChartOfAccounts.objects.get_or_create(code='41100', defaults={'name': 'إيرادات المبيعات', 'account_type': revenue_type, 'is_active': True})
    ChartOfAccounts.objects.get_or_create(code='51100', defaults={'name': 'تكلفة البضاعة المباعة', 'account_type': expense_type, 'is_active': True})
    ChartOfAccounts.objects.get_or_create(code='21110', defaults={'name': 'الموردين', 'account_type': asset_type, 'is_active': True})
    ChartOfAccounts.objects.get_or_create(code='21210', defaults={'name': 'وسيط استلام البضائع GRNI', 'account_type': asset_type, 'is_active': True})
    ChartOfAccounts.objects.get_or_create(code='21510', defaults={'name': 'ضريبة القيمة المضافة', 'account_type': asset_type, 'is_active': True})

    unit = Unit.objects.create(name="Piece", symbol="PCS")
    wh1 = Warehouse.objects.create(name="Main Warehouse", is_active=True)
    wh2 = Warehouse.objects.create(name="Secondary Warehouse", is_active=True)
    customer = Customer.objects.create(name="Customer A", is_active=True)
    supplier = Supplier.objects.create(name="Supplier X", is_active=True)
    cat = Category.objects.create(name="General Category")
    product = Product.objects.create(
        name="Steel Bar 12mm",
        sku="ST-12MM",
        category=cat,
        unit=unit,
        selling_price=Decimal("100.00"),
        cost_price=Decimal("70.00"),
        is_active=True,
        is_service=False,
        created_by=auth_user
    )
    # Stock setup
    Stock.objects.create(product=product, warehouse=wh1, quantity=Decimal("50.00"))
    return {
        "unit": unit,
        "wh1": wh1,
        "wh2": wh2,
        "customer": customer,
        "supplier": supplier,
        "product": product,
        "user": auth_user,
    }


@pytest.mark.django_db
def test_sale_service_update_sale_details_only_in_place(setup_master_data):
    """
    Test Gap 2 & Gap 14: Details-only update executes in-place without stock movements or new journal entries.
    """
    data = setup_master_data
    user = data["user"]
    product = data["product"]
    customer = data["customer"]
    wh = data["wh1"]

    sale_data = {
        'date': timezone.now().date(),
        'customer_id': customer.id,
        'warehouse_id': wh.id,
        'discount': Decimal('0.00'),
        'discount_type': 'fixed',
        'tax': Decimal('0.00'),
        'notes': 'Original notes',
        'items': [
            {
                'product_id': product.id,
                'quantity': Decimal('2.00'),
                'unit_price': Decimal('100.00'),
                'discount': Decimal('0.00'),
                'details': 'Original Specs - Batch A',
            }
        ]
    }

    sale = SaleService.create_sale(data=sale_data, user=user)
    assert sale.items.count() == 1
    orig_item = sale.items.first()
    orig_item_id = orig_item.id
    assert orig_item.details == 'Original Specs - Batch A'
    orig_journal_entry_id = getattr(sale.journal_entry, 'id', None)

    # Now perform details-only update
    update_data = {
        'date': sale.date,
        'customer_id': customer.id,
        'warehouse_id': wh.id,
        'discount': Decimal('0.00'),
        'discount_type': 'fixed',
        'tax': Decimal('0.00'),
        'notes': 'Updated notes only',
        'items': [
            {
                'item_id': orig_item_id,
                'product_id': product.id,
                'quantity': Decimal('2.00'),
                'unit_price': Decimal('100.00'),
                'discount': Decimal('0.00'),
                'details': 'Modified Specs - Batch A Corrected',
            }
        ]
    }

    updated_sale = SaleService.update_sale(sale=sale, data=update_data, user=user)
    
    # Assert item ID is unchanged (strictly in-place update)
    updated_item = updated_sale.items.first()
    assert updated_item.id == orig_item_id
    assert updated_item.details == 'Modified Specs - Batch A Corrected'
    assert updated_sale.notes == 'Updated notes only'

    # Assert journal entry was NOT recreated
    assert getattr(updated_sale.journal_entry, 'id', None) == orig_journal_entry_id


@pytest.mark.django_db
def test_sale_service_update_sale_preserve_on_omission(setup_master_data):
    """
    Test Gap 8: Server-Side Pre-Delete Snapshot Shield restores details if omitted in POST.
    """
    data = setup_master_data
    user = data["user"]
    product = data["product"]
    customer = data["customer"]
    wh = data["wh1"]

    sale_data = {
        'date': timezone.now().date(),
        'customer_id': customer.id,
        'warehouse_id': wh.id,
        'discount': Decimal('0.00'),
        'discount_type': 'fixed',
        'tax': Decimal('0.00'),
        'notes': 'Initial sale',
        'items': [
            {
                'product_id': product.id,
                'quantity': Decimal('2.00'),
                'unit_price': Decimal('100.00'),
                'discount': Decimal('0.00'),
                'details': 'Important Technical Specs 2026',
            }
        ]
    }

    sale = SaleService.create_sale(data=sale_data, user=user)
    orig_item = sale.items.first()
    orig_item_id = orig_item.id

    # Financial update (changing quantity to 3) where details is completely omitted (None or '')
    update_data = {
        'date': sale.date,
        'customer_id': customer.id,
        'warehouse_id': wh.id,
        'discount': Decimal('0.00'),
        'discount_type': 'fixed',
        'tax': Decimal('0.00'),
        'items': [
            {
                'item_id': orig_item_id,
                'product_id': product.id,
                'quantity': Decimal('3.00'),  # Changed quantity triggers standard update
                'unit_price': Decimal('100.00'),
                'discount': Decimal('0.00'),
                'details': '',  # Omitted details from form submission
            }
        ]
    }

    updated_sale = SaleService.update_sale(sale=sale, data=update_data, user=user)
    assert updated_sale.items.count() == 1
    new_item = updated_sale.items.first()
    assert new_item.quantity == Decimal('3.00')
    # Details MUST be restored from the pre-delete snapshot shield
    assert new_item.details == 'Important Technical Specs 2026'


@pytest.mark.django_db
def test_quotation_convert_to_sale_propagates_details(setup_master_data):
    """
    Test Gap 9 (Gateway 1): Quotation to Sale conversion propagates line details intact.
    """
    data = setup_master_data
    user = data["user"]
    product = data["product"]
    customer = data["customer"]
    wh = data["wh1"]

    quotation = Quotation.objects.create(
        number="QT-TEST-001",
        customer=customer,
        date=timezone.now().date(),
        created_by=user,
        discount=Decimal("0.00"),
        tax=Decimal("0.00"),
        total=Decimal("100.00")
    )
    q_item = QuotationItem.objects.create(
        quotation=quotation,
        product=product,
        quantity=Decimal("1.00"),
        unit_price=Decimal("100.00"),
        discount=Decimal("0.00"),
        total=Decimal("100.00"),
        details="Special Coating Specs"
    )

    sale_data = {
        'date': timezone.now().date(),
        'customer_id': customer.id,
        'warehouse_id': wh.id,
        'discount': quotation.discount,
        'discount_type': 'fixed',
        'tax': quotation.tax,
        'notes': quotation.notes or '',
        'items': [
            {
                'product_id': q_item.product.id,
                'warehouse_id': wh.id,
                'quantity': q_item.quantity,
                'unit_price': q_item.unit_price,
                'discount': q_item.discount,
                'details': q_item.details or "",
            }
        ]
    }

    sale = SaleService.create_sale(data=sale_data, user=user)
    assert sale.items.count() == 1
    assert sale.items.first().details == "Special Coating Specs"


@pytest.mark.django_db
def test_sales_service_create_sales_order_and_invoice_details(setup_master_data):
    """
    Test Gap 10 & Gap 18: SalesOrder and SalesInvoice propagate details correctly.
    """
    data = setup_master_data
    user = data["user"]
    product = data["product"]
    customer = data["customer"]
    wh = data["wh1"]

    from sale.services.sales_service import SalesService

    items_data = [
        {
            "product": product,
            "ordered_qty": Decimal("5.00"),
            "unit_price": Decimal("100.00"),
            "discount_percentage": Decimal("0.00"),
            "details": "Order Line Specification Grade A",
        }
    ]

    so = SalesService.create_sales_order(
        customer=customer,
        warehouse=wh,
        order_date=timezone.now().date(),
        items_data=items_data,
        user=user
    )

    assert so.items.count() == 1
    so_item = so.items.first()
    assert so_item.details == "Order Line Specification Grade A"

    # Now create enterprise sales invoice from this sales order line
    inv = SalesService.create_sales_invoice(
        so_id=so.id,
        delivery_note_id=None,
        invoice_date=timezone.now().date(),
        due_date=timezone.now().date(),
        items_data=[
            {
                "so_item_id": so_item.id,
                "billed_qty": Decimal("5.00"),
                "unit_price": Decimal("100.00"),
            }
        ],
        user=user
    )

    assert inv.items.count() == 1
    inv_item = inv.items.first()
    # Details should automatically inherit from so_item
    assert inv_item.details == "Order Line Specification Grade A"


@pytest.mark.django_db
def test_procurement_service_creates_po_and_bill_with_details(setup_master_data):
    """
    Test Gap 18: ProcurementService saves details on PurchaseOrderItem and inherits to SupplierBillItem.
    """
    data = setup_master_data
    user = data["user"]
    product = data["product"]
    supplier = data["supplier"]
    wh = data["wh1"]

    items_data = [
        {
            "product": product,
            "ordered_qty": Decimal("10.00"),
            "unit_price": Decimal("70.00"),
            "discount": Decimal("0.00"),
            "details": "Raw Steel Material Certificate 3.1",
        }
    ]

    po = ProcurementService.create_purchase_order(
        supplier=supplier,
        warehouse=wh,
        order_date=timezone.now().date(),
        items_data=items_data,
        user=user
    )

    assert po.items.count() == 1
    po_item = po.items.first()
    assert po_item.details == "Raw Steel Material Certificate 3.1"

    # Create GRN
    grn = GoodsReceivedNote.objects.create(
        grn_number="GRN-001",
        purchase_order=po,
        supplier=supplier,
        warehouse=wh
    )
    grn_item = GoodsReceivedNoteItem.objects.create(
        grn=grn,
        po_item=po_item,
        product=product,
        received_qty=Decimal("10.00"),
        unit_price=Decimal("70.00"),
        total_cost=Decimal("700.00"),
    )

    # Create Supplier Bill
    bill = ProcurementService.create_supplier_bill(
        supplier=supplier,
        supplier_bill_number="BILL-SUPP-999",
        bill_date=timezone.now().date(),
        due_date=timezone.now().date(),
        items_data=[
            {
                "grn_item_id": grn_item.id,
                "billed_qty": Decimal("10.00"),
                "unit_price": Decimal("70.00"),
            }
        ],
        user=user
    )

    assert bill.items.count() == 1
    bill_item = bill.items.first()
    # Details should inherit from po_item
    assert bill_item.details == "Raw Steel Material Certificate 3.1"
