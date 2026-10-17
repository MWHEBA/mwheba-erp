import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.urls import reverse

from core.models import SystemSetting, SystemModule
from core.forms import OperationsSettingsForm
from customer.models import Customer
from product.models import Product, Warehouse, Unit, Stock, Category
from sale.models import Sale, SaleItem, Quotation, QuotationItem
from sale.models.sales_models import SalesOrder, SalesOrderItem
from purchase.models import Purchase, PurchaseItem
from supplier.models import Supplier
from purchase.models.procurement_models import PurchaseOrder, PurchaseOrderItem
from financial.models import AccountType, ChartOfAccounts, AccountingPeriod

User = get_user_model()


@pytest.fixture
def auth_user(db):
    user = User.objects.create_superuser(
        username="phase3_admin",
        email="phase3_admin@example.com",
        password="password123"
    )
    return user


@pytest.fixture
def setup_master_data(db, auth_user):
    # Enable all relevant submodules
    SystemModule.objects.all().update(is_enabled=True)
    SystemSetting.objects.update_or_create(key="enable_quotations", defaults={"value": "true", "data_type": "boolean"})
    SystemSetting.objects.update_or_create(key="enable_sales_orders", defaults={"value": "true", "data_type": "boolean"})
    SystemSetting.objects.update_or_create(key="enable_purchase_orders", defaults={"value": "true", "data_type": "boolean"})
    SystemSetting.invalidate_all_system_caches()

    current_year = timezone.now().year
    AccountingPeriod.objects.get_or_create(
        start_date=timezone.datetime(current_year, 1, 1).date(),
        end_date=timezone.datetime(current_year, 12, 31).date(),
        defaults={'name': f'السنة المالية {current_year}', 'status': 'open'}
    )

    cash_type, _ = AccountType.objects.get_or_create(code='CASH', defaults={'name': 'نقدية', 'nature': 'debit'})
    asset_type, _ = AccountType.objects.get_or_create(code='ASSET', defaults={'name': 'أصول', 'nature': 'debit'})
    revenue_type, _ = AccountType.objects.get_or_create(code='REVENUE', defaults={'name': 'إيرادات', 'nature': 'credit'})
    expense_type, _ = AccountType.objects.get_or_create(code='EXPENSE', defaults={'name': 'مصروفات', 'nature': 'debit'})

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
    customer = Customer.objects.create(name="Customer A", is_active=True)
    supplier = Supplier.objects.create(name="Supplier X", is_active=True)
    cat = Category.objects.create(name="General Category")

    product = Product.objects.create(
        name="Engine Filter",
        sku="ENG-001",
        category=cat,
        unit=unit,
        selling_price=Decimal("150.00"),
        cost_price=Decimal("100.00"),
        is_active=True,
        created_by=auth_user,
    )
    Stock.objects.create(product=product, warehouse=wh1, quantity=Decimal("50.00"))

    return {
        "user": auth_user,
        "product": product,
        "warehouse": wh1,
        "customer": customer,
        "supplier": supplier,
    }


@pytest.mark.django_db
class TestOperationsSettingsFormAndAliases:
    def test_form_has_all_five_line_detail_fields(self):
        form = OperationsSettingsForm()
        fields = [
            'show_quotation_line_details',
            'show_sales_order_line_details',
            'show_sale_invoice_line_details',
            'show_purchase_order_line_details',
            'show_purchase_invoice_line_details',
        ]
        for field in fields:
            assert field in form.fields
            assert form.fields[field].required is False

    def test_post_operations_settings_syncs_aliases_and_invalidates_cache(self, client, auth_user):
        client.force_login(auth_user)
        url = reverse('core:operations_settings')

        post_data = {
            'sale_invoice_item_types': 'both',
            'purchase_invoice_item_types': 'both',
            'invoice_product_code_display': 'sku',
            'custom_fields_display_mode': 'expanded',
            'default_quotation_validity_days': 15,
            'default_print_language': 'ar',
            'receipt_paper_width': '80',
            'show_quotation_line_details': 'on',
            'show_sales_order_line_details': 'on',
            'show_sale_invoice_line_details': 'on',
            'show_purchase_order_line_details': 'on',
            'show_purchase_invoice_line_details': 'on',
        }
        response = client.post(url, post_data)
        assert response.status_code in [200, 302]

        # Verify SystemSettings were saved and cached
        assert SystemSetting.get_bool('show_quotation_line_details') is True
        assert SystemSetting.get_bool('show_sales_order_line_details') is True
        assert SystemSetting.get_bool('show_sale_invoice_line_details') is True
        assert SystemSetting.get_bool('show_purchase_order_line_details') is True
        assert SystemSetting.get_bool('show_purchase_invoice_line_details') is True

        # Verify aliases were synchronized
        assert SystemSetting.get_bool('show_sale_line_details') is True
        assert SystemSetting.get_bool('show_purchase_line_details') is True


@pytest.mark.django_db
class TestViewContextDelivery:
    def test_quotation_view_context_show_line_details(self, client, setup_master_data):
        client.force_login(setup_master_data["user"])
        SystemSetting.objects.update_or_create(
            key='show_quotation_line_details', defaults={'value': 'true', 'data_type': 'boolean'}
        )
        SystemSetting.invalidate_all_system_caches()

        res = client.get(reverse('sale:quotation_create'))
        assert res.status_code == 200
        assert res.context['show_line_details'] is True

        SystemSetting.objects.update_or_create(
            key='show_quotation_line_details', defaults={'value': 'false', 'data_type': 'boolean'}
        )
        SystemSetting.invalidate_all_system_caches()
        res = client.get(reverse('sale:quotation_create'))
        assert res.context['show_line_details'] is False

    def test_sales_order_view_context_show_line_details(self, client, setup_master_data):
        client.force_login(setup_master_data["user"])
        SystemSetting.objects.update_or_create(
            key='show_sales_order_line_details', defaults={'value': 'true', 'data_type': 'boolean'}
        )
        SystemSetting.invalidate_all_system_caches()

        res = client.get(reverse('sale:sales_order_create'))
        assert res.status_code == 200
        assert res.context['show_line_details'] is True

        SystemSetting.objects.update_or_create(
            key='show_sales_order_line_details', defaults={'value': 'false', 'data_type': 'boolean'}
        )
        SystemSetting.invalidate_all_system_caches()
        res = client.get(reverse('sale:sales_order_create'))
        assert res.context['show_line_details'] is False

    def test_sale_invoice_view_context_show_line_details(self, client, setup_master_data):
        client.force_login(setup_master_data["user"])
        SystemSetting.objects.update_or_create(
            key='show_sale_invoice_line_details', defaults={'value': 'true', 'data_type': 'boolean'}
        )
        SystemSetting.objects.update_or_create(
            key='show_sale_line_details', defaults={'value': 'true', 'data_type': 'boolean'}
        )
        SystemSetting.invalidate_all_system_caches()

        res = client.get(reverse('sale:sale_create'))
        assert res.status_code == 200
        assert res.context['show_line_details'] is True

        SystemSetting.objects.update_or_create(
            key='show_sale_invoice_line_details', defaults={'value': 'false', 'data_type': 'boolean'}
        )
        SystemSetting.objects.update_or_create(
            key='show_sale_line_details', defaults={'value': 'false', 'data_type': 'boolean'}
        )
        SystemSetting.invalidate_all_system_caches()
        res = client.get(reverse('sale:sale_create'))
        assert res.context['show_line_details'] is False

    def test_purchase_order_view_context_show_line_details(self, client, setup_master_data):
        client.force_login(setup_master_data["user"])
        SystemSetting.objects.update_or_create(
            key='show_purchase_order_line_details', defaults={'value': 'true', 'data_type': 'boolean'}
        )
        SystemSetting.invalidate_all_system_caches()

        res = client.get(reverse('purchase:po_create'))
        assert res.status_code == 200
        assert res.context['show_line_details'] is True

        SystemSetting.objects.update_or_create(
            key='show_purchase_order_line_details', defaults={'value': 'false', 'data_type': 'boolean'}
        )
        SystemSetting.invalidate_all_system_caches()
        res = client.get(reverse('purchase:po_create'))
        assert res.context['show_line_details'] is False

    def test_purchase_invoice_view_context_show_line_details(self, client, setup_master_data):
        client.force_login(setup_master_data["user"])
        SystemSetting.objects.update_or_create(
            key='show_purchase_invoice_line_details', defaults={'value': 'true', 'data_type': 'boolean'}
        )
        SystemSetting.objects.update_or_create(
            key='show_purchase_line_details', defaults={'value': 'true', 'data_type': 'boolean'}
        )
        SystemSetting.invalidate_all_system_caches()

        res = client.get(reverse('purchase:purchase_create'))
        assert res.status_code == 200
        assert res.context['show_line_details'] is True

        SystemSetting.objects.update_or_create(
            key='show_purchase_invoice_line_details', defaults={'value': 'false', 'data_type': 'boolean'}
        )
        SystemSetting.objects.update_or_create(
            key='show_purchase_line_details', defaults={'value': 'false', 'data_type': 'boolean'}
        )
        SystemSetting.invalidate_all_system_caches()
        res = client.get(reverse('purchase:purchase_create'))
        assert res.context['show_line_details'] is False


@pytest.mark.django_db
class TestPoViewsLineDetailsAndPreDeleteShield:
    def test_po_create_captures_details_and_sets_flag(self, client, setup_master_data):
        data = setup_master_data
        client.force_login(data["user"])

        post_data = {
            'supplier': data["supplier"].id,
            'warehouse': data["warehouse"].id,
            'order_date': timezone.now().strftime('%Y-%m-%d'),
            'delivery_date': (timezone.now() + timezone.timedelta(days=7)).strftime('%Y-%m-%d'),
            'payment_terms': 'due_on_receipt',
            'product[]': [data["product"].id],
            'quantity[]': ['5'],
            'unit_price[]': ['100.00'],
            'discount[]': ['0'],
            'details[]': ['Special high-flow specs for unit A'],
        }

        response = client.post(reverse('purchase:po_create'), post_data)
        assert response.status_code in [200, 302]

        po = PurchaseOrder.objects.latest('id')
        assert po.show_line_details is True
        item = po.items.first()
        assert item.details == 'Special high-flow specs for unit A'

    def test_po_edit_preserves_details_via_snapshot_shield_when_omitted(self, client, setup_master_data):
        data = setup_master_data
        client.force_login(data["user"])

        # Create PO with details
        po = PurchaseOrder.objects.create(
            order_number="PO-SNAP-001",
            supplier=data["supplier"],
            warehouse=data["warehouse"],
            order_date=timezone.now().date(),
            delivery_due_date=(timezone.now() + timezone.timedelta(days=7)).date(),
            show_line_details=True,
            created_by=data["user"],
        )
        item = PurchaseOrderItem.objects.create(
            purchase_order=po,
            product=data["product"],
            ordered_qty=Decimal("10"),
            unit_price=Decimal("100"),
            total_price=Decimal("1000"),
            details="Original critical PO specification note",
        )

        # Edit PO: send item_id but omit details[]
        edit_data = {
            'supplier': data["supplier"].id,
            'warehouse': data["warehouse"].id,
            'order_date': po.order_date.strftime('%Y-%m-%d'),
            'delivery_due_date': po.delivery_due_date.strftime('%Y-%m-%d'),
            'payment_terms': 'due_on_receipt',
            'item_id[]': [item.id],
            'product[]': [data["product"].id],
            'quantity[]': ['12'],  # Updated qty
            'unit_price[]': ['100.00'],
            'discount[]': ['0'],
            # details[] completely omitted
        }

        response = client.post(reverse('purchase:po_edit', args=[po.id]), edit_data)
        assert response.status_code in [200, 302]

        po.refresh_from_db()
        updated_item = po.items.first()
        assert updated_item.ordered_qty == Decimal("12")
        # Assert pre-delete snapshot shield restored the details!
        assert updated_item.details == "Original critical PO specification note"


@pytest.mark.django_db
class TestSalesOrderViewsLineDetailsAndPreDeleteShield:
    def test_sales_order_create_captures_details(self, client, setup_master_data):
        data = setup_master_data
        client.force_login(data["user"])

        post_data = {
            'customer': data["customer"].id,
            'warehouse': data["warehouse"].id,
            'order_date': timezone.now().strftime('%Y-%m-%d'),
            'product[]': [data["product"].id],
            'quantity[]': ['3'],
            'unit_price[]': ['150.00'],
            'discount[]': ['0'],
            'details[]': ['Customer requested extra packaging and inspection cert'],
        }

        response = client.post(reverse('sale:sales_order_create'), post_data)
        assert response.status_code in [200, 302]

        so = SalesOrder.objects.latest('id')
        item = so.items.first()
        assert item.details == 'Customer requested extra packaging and inspection cert'

    def test_sales_order_edit_preserves_details_via_snapshot_shield_when_omitted(self, client, setup_master_data):
        data = setup_master_data
        client.force_login(data["user"])

        so = SalesOrder.objects.create(
            order_number="SO-SNAP-001",
            customer=data["customer"],
            warehouse=data["warehouse"],
            order_date=timezone.now().date(),
            created_by=data["user"],
        )
        item = SalesOrderItem.objects.create(
            sales_order=so,
            product=data["product"],
            ordered_qty=Decimal("5"),
            unit_price=Decimal("150"),
            line_total=Decimal("750"),
            details="Preserved SO line details note",
        )

        # Edit SO: provide item_id but omit details[]
        edit_data = {
            'customer': data["customer"].id,
            'warehouse': data["warehouse"].id,
            'order_date': so.order_date.strftime('%Y-%m-%d'),
            'item_id[]': [item.id],
            'product[]': [data["product"].id],
            'quantity[]': ['7'],
            'unit_price[]': ['150.00'],
            'discount[]': ['0'],
            # details[] omitted
        }

        response = client.post(reverse('sale:sales_order_edit', args=[so.id]), edit_data)
        assert response.status_code in [200, 302]

        so.refresh_from_db()
        updated_item = so.items.first()
        assert updated_item.ordered_qty == Decimal("7")
        # Assert pre-delete snapshot shield restored the details!
        assert updated_item.details == "Preserved SO line details note"
