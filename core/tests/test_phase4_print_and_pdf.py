import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.test import RequestFactory

from core.models import SystemSetting, SystemModule
from customer.models import Customer
from product.models import Product, Warehouse, Unit, Stock, Category
from sale.models import Sale, SaleItem, Quotation, QuotationItem
from sale.models.sales_models import SalesOrder, SalesOrderItem, DeliveryNote, DeliveryNoteItem
from purchase.models import Purchase, PurchaseItem
from supplier.models import Supplier
from purchase.models.procurement_models import PurchaseOrder, PurchaseOrderItem
from financial.models import AccountType, ChartOfAccounts, AccountingPeriod
from utils.pdf_utils import generate_guaranteed_pdf_response
from core.services.document_dispatcher import DocumentDispatcher

User = get_user_model()


@pytest.fixture
def auth_user(db):
    user = User.objects.create_superuser(
        username="phase4_admin",
        email="phase4_admin@example.com",
        password="password123"
    )
    return user


@pytest.fixture
def limited_user(db):
    """User without financial or pricing view permissions"""
    user = User.objects.create_user(
        username="warehouse_keeper",
        email="warehouse@example.com",
        password="password123"
    )
    return user


@pytest.fixture
def master_data(db, auth_user):
    SystemModule.objects.all().update(is_enabled=True)
    SystemSetting.objects.update_or_create(key="enable_quotations", defaults={"value": "true", "data_type": "boolean"})
    SystemSetting.objects.update_or_create(key="enable_sales_orders", defaults={"value": "true", "data_type": "boolean"})
    SystemSetting.objects.update_or_create(key="enable_purchase_orders", defaults={"value": "true", "data_type": "boolean"})
    SystemSetting.objects.update_or_create(key="show_sale_invoice_line_details", defaults={"value": "true", "data_type": "boolean"})
    SystemSetting.objects.update_or_create(key="show_quotation_line_details", defaults={"value": "true", "data_type": "boolean"})
    SystemSetting.objects.update_or_create(key="show_sales_order_line_details", defaults={"value": "true", "data_type": "boolean"})
    SystemSetting.objects.update_or_create(key="show_purchase_invoice_line_details", defaults={"value": "true", "data_type": "boolean"})
    SystemSetting.objects.update_or_create(key="show_purchase_order_line_details", defaults={"value": "true", "data_type": "boolean"})
    SystemSetting.objects.update_or_create(key="enable_thermal_printing", defaults={"value": "true", "data_type": "boolean"})
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
    customer = Customer.objects.create(name="Customer Test", is_active=True)
    supplier = Supplier.objects.create(name="Supplier Test", is_active=True)
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
    Stock.objects.create(product=product, warehouse=wh1, quantity=Decimal("100.00"))

    return {
        "user": auth_user,
        "product": product,
        "warehouse": wh1,
        "customer": customer,
        "supplier": supplier,
    }


@pytest.mark.django_db
class TestA4PrintTemplatesLineDetailsRendering:
    """تحقق من رندرة تفاصيل البند في جميع قوالب الطباعة الرسمية A4"""

    def test_sale_print_renders_line_details_when_enabled(self, client, master_data):
        client.force_login(master_data["user"])
        sale = Sale.objects.create(
            customer=master_data["customer"],
            warehouse=master_data["warehouse"],
            date=timezone.now().date(),
            subtotal=Decimal("150.00"),
            total=Decimal("150.00"),
            payment_method="credit",
            created_by=master_data["user"],
            show_line_details=True,
        )
        SaleItem.objects.create(
            sale=sale,
            product=master_data["product"],
            quantity=Decimal("1.00"),
            unit_price=Decimal("150.00"),
            total=Decimal("150.00"),
            details="Specification: Aluminum alloy 2mm thickness",
        )

        res = client.get(reverse("sale:sale_print", kwargs={"pk": sale.pk}))
        assert res.status_code == 200
        content = res.content.decode("utf-8")
        assert "item-line-details" in content
        assert "Aluminum alloy 2mm thickness" in content

    def test_sale_print_hides_line_details_when_disabled(self, client, master_data):
        client.force_login(master_data["user"])
        sale = Sale.objects.create(
            customer=master_data["customer"],
            warehouse=master_data["warehouse"],
            date=timezone.now().date(),
            subtotal=Decimal("150.00"),
            total=Decimal("150.00"),
            payment_method="credit",
            created_by=master_data["user"],
            show_line_details=False,
        )
        SaleItem.objects.create(
            sale=sale,
            product=master_data["product"],
            quantity=Decimal("1.00"),
            unit_price=Decimal("150.00"),
            total=Decimal("150.00"),
            details="Confidential internal spec",
        )

        res = client.get(reverse("sale:sale_print", kwargs={"pk": sale.pk}))
        assert res.status_code == 200
        content = res.content.decode("utf-8")
        assert "Confidential internal spec" not in content

    def test_quotation_print_renders_line_details(self, client, master_data):
        client.force_login(master_data["user"])
        q = Quotation.objects.create(
            customer=master_data["customer"],
            date=timezone.now().date(),
            subtotal=Decimal("150.00"),
            total=Decimal("150.00"),
            created_by=master_data["user"],
            show_line_details=True,
        )
        QuotationItem.objects.create(
            quotation=q,
            product=master_data["product"],
            quantity=Decimal("1.00"),
            unit_price=Decimal("150.00"),
            total=Decimal("150.00"),
            details="Quotation note: Delivery within 5 business days",
        )

        res = client.get(reverse("sale:quotation_print", kwargs={"pk": q.pk}))
        assert res.status_code == 200
        content = res.content.decode("utf-8")
        assert "item-line-details" in content
        assert "Delivery within 5 business days" in content

    def test_sales_order_print_renders_line_details(self, client, master_data):
        client.force_login(master_data["user"])
        so = SalesOrder.objects.create(
            customer=master_data["customer"],
            warehouse=master_data["warehouse"],
            order_date=timezone.now().date(),
            total_amount=Decimal("150.00"),
            created_by=master_data["user"],
            show_line_details=True,
        )
        SalesOrderItem.objects.create(
            sales_order=so,
            product=master_data["product"],
            ordered_qty=Decimal("1.00"),
            unit_price=Decimal("150.00"),
            line_total=Decimal("150.00"),
            details="SO Note: Fragile handling required",
        )

        res = client.get(reverse("sale:sales_order_print", kwargs={"pk": so.pk}))
        assert res.status_code == 200
        content = res.content.decode("utf-8")
        assert "item-line-details" in content
        assert "Fragile handling required" in content

    def test_delivery_note_print_renders_so_item_details_for_warehouse(self, client, master_data):
        client.force_login(master_data["user"])
        so = SalesOrder.objects.create(
            customer=master_data["customer"],
            warehouse=master_data["warehouse"],
            order_date=timezone.now().date(),
            total_amount=Decimal("150.00"),
            created_by=master_data["user"],
            show_line_details=True,
        )
        so_item = SalesOrderItem.objects.create(
            sales_order=so,
            product=master_data["product"],
            ordered_qty=Decimal("10.00"),
            unit_price=Decimal("150.00"),
            line_total=Decimal("1500.00"),
            details="Warehouse Instruction: Heavy crate pallet #4",
        )
        dn = DeliveryNote.objects.create(
            sales_order=so,
            customer=master_data["customer"],
            warehouse=master_data["warehouse"],
            delivery_date=timezone.now().date(),
            created_by=master_data["user"],
        )
        DeliveryNoteItem.objects.create(
            delivery_note=dn,
            so_item=so_item,
            delivered_qty=Decimal("5.00"),
        )

        res = client.get(reverse("sale:delivery_note_print", kwargs={"pk": dn.pk}))
        assert res.status_code == 200
        content = res.content.decode("utf-8")
        assert "item-line-details" in content
        assert "Heavy crate pallet #4" in content

    def test_purchase_print_renders_line_details(self, client, master_data):
        client.force_login(master_data["user"])
        po_purchase = Purchase.objects.create(
            supplier=master_data["supplier"],
            warehouse=master_data["warehouse"],
            date=timezone.now().date(),
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
            payment_method="credit",
            created_by=master_data["user"],
            show_line_details=True,
        )
        PurchaseItem.objects.create(
            purchase=po_purchase,
            product=master_data["product"],
            quantity=1,
            unit_price=Decimal("100.00"),
            total=Decimal("100.00"),
            details="Supplier batch #99238 certification enclosed",
        )

        res = client.get(reverse("purchase:purchase_print", kwargs={"pk": po_purchase.pk}))
        assert res.status_code == 200
        content = res.content.decode("utf-8")
        assert "item-line-details" in content
        assert "Supplier batch #99238" in content

    def test_purchase_order_print_renders_line_details(self, client, master_data):
        client.force_login(master_data["user"])
        po = PurchaseOrder.objects.create(
            supplier=master_data["supplier"],
            warehouse=master_data["warehouse"],
            order_date=timezone.now().date(),
            total_amount=Decimal("100.00"),
            created_by=master_data["user"],
            show_line_details=True,
        )
        PurchaseOrderItem.objects.create(
            purchase_order=po,
            product=master_data["product"],
            ordered_qty=Decimal("1.00"),
            unit_price=Decimal("100.00"),
            total_price=Decimal("100.00"),
            details="PO Specs: Grade A Stainless Steel",
        )

        res = client.get(reverse("purchase:po_print", kwargs={"pk": po.pk}))
        assert res.status_code == 200
        content = res.content.decode("utf-8")
        assert "item-line-details" in content
        assert "Grade A Stainless Steel" in content


@pytest.mark.django_db
class TestThermalReceiptRendering:
    """تحقق من رندرة الإيصال الحراري بدون كسر تخطيط flexbox (Gap 17)"""

    def test_thermal_receipt_renders_spec_note_inside_item_name(self, client, master_data):
        client.force_login(master_data["user"])
        sale = Sale.objects.create(
            customer=master_data["customer"],
            warehouse=master_data["warehouse"],
            date=timezone.now().date(),
            subtotal=Decimal("150.00"),
            total=Decimal("150.00"),
            payment_method="credit",
            created_by=master_data["user"],
            show_line_details=True,
        )
        SaleItem.objects.create(
            sale=sale,
            product=master_data["product"],
            quantity=Decimal("2.00"),
            unit_price=Decimal("75.00"),
            total=Decimal("150.00"),
            details="Custom blend: Extra crispy",
        )

        res = client.get(reverse("sale:sale_print_thermal", kwargs={"pk": sale.pk}))
        assert res.status_code == 200
        content = res.content.decode("utf-8")
        # Ensure item-spec-note div is present with text
        assert 'class="item-spec-note' in content
        assert "Custom blend: Extra crispy" in content
        # Ensure item-details (flexbox row) remains intact with quantity and calculation
        assert "item-details" in content
        assert "item-calc" in content
        assert "item-total" in content

    def test_thermal_receipt_hides_spec_note_when_disabled(self, client, master_data):
        client.force_login(master_data["user"])
        sale = Sale.objects.create(
            customer=master_data["customer"],
            warehouse=master_data["warehouse"],
            date=timezone.now().date(),
            subtotal=Decimal("150.00"),
            total=Decimal("150.00"),
            payment_method="credit",
            created_by=master_data["user"],
            show_line_details=False,
        )
        SaleItem.objects.create(
            sale=sale,
            product=master_data["product"],
            quantity=Decimal("1.00"),
            unit_price=Decimal("150.00"),
            total=Decimal("150.00"),
            details="Secret thermal sauce recipe",
        )

        res = client.get(reverse("sale:sale_print_thermal", kwargs={"pk": sale.pk}))
        assert res.status_code == 200
        content = res.content.decode("utf-8")
        assert 'class="item-spec-note' not in content
        assert "Secret thermal sauce recipe" not in content


@pytest.mark.django_db
class TestReportLabGuaranteedFallbackPdf:
    """تحقق من مولد الجداول البديل في ReportLab ومطابقة تفاصيل البنود (Gap 11)"""

    def test_reportlab_fallback_generates_valid_pdf_with_item_details(self, master_data):
        sale = Sale.objects.create(
            customer=master_data["customer"],
            warehouse=master_data["warehouse"],
            date=timezone.now().date(),
            subtotal=Decimal("150.00"),
            total=Decimal("150.00"),
            payment_method="credit",
            created_by=master_data["user"],
            show_line_details=True,
        )
        SaleItem.objects.create(
            sale=sale,
            product=master_data["product"],
            quantity=Decimal("1.00"),
            unit_price=Decimal("150.00"),
            total=Decimal("150.00"),
            details="Fallback line spec note",
        )

        context = {
            "sale": sale,
            "items": [
                type("DummyItem", (), {
                    "product": master_data["product"],
                    "quantity": Decimal("1.00"),
                    "unit_price": Decimal("150.00"),
                    "total": Decimal("150.00"),
                    "details": "Fallback line spec note",
                })()
            ],
            "show_line_details": True,
            "company_name": "مؤسسة موهبة للتجارة",
        }

        resp = generate_guaranteed_pdf_response("sale", context, filename="test_fallback.pdf")
        assert resp.status_code == 200
        assert resp["Content-Type"] == "application/pdf"
        assert resp.content.startswith(b"%PDF")
        assert len(resp.content) >= 500


@pytest.mark.django_db
class TestDocumentDispatcherPdfExtractionAndReliability:
    """تحقق من رفض ملفات PDF الهيكلية/الفارغة وتجهيز سياق الإرسال التلقائي"""

    def test_extract_valid_pdf_rejects_empty_and_skeletal_responses(self):
        # Empty response or None
        assert DocumentDispatcher._extract_valid_pdf(None) is None

        # Skeletal response (< 500 bytes)
        small_resp = type("DummyResp", (), {"content": b"%PDF-1.4 truncated small"})()
        assert DocumentDispatcher._extract_valid_pdf(small_resp) is None

        # Missing %PDF header even if length >= 500
        invalid_header_resp = type("DummyResp", (), {"content": b"<html>Error 500</html>" + b" " * 600})()
        assert DocumentDispatcher._extract_valid_pdf(invalid_header_resp) is None

    def test_extract_valid_pdf_accepts_healthy_pdf(self):
        healthy_content = b"%PDF-1.4\n" + b"0" * 800 + b"\n%%EOF"
        healthy_resp = type("DummyResp", (), {"content": healthy_content})()
        extracted = DocumentDispatcher._extract_valid_pdf(healthy_resp)
        assert extracted == healthy_content

    def test_dispatcher_build_context_resolves_show_line_details(self, master_data):
        sale = Sale.objects.create(
            customer=master_data["customer"],
            warehouse=master_data["warehouse"],
            date=timezone.now().date(),
            subtotal=Decimal("150.00"),
            total=Decimal("150.00"),
            payment_method="credit",
            created_by=master_data["user"],
            show_line_details=True,
        )
        ctx = DocumentDispatcher._build_full_document_context(sale)
        assert ctx.get("show_line_details") is True

        sale_disabled = Sale.objects.create(
            customer=master_data["customer"],
            warehouse=master_data["warehouse"],
            date=timezone.now().date(),
            subtotal=Decimal("150.00"),
            total=Decimal("150.00"),
            payment_method="credit",
            created_by=master_data["user"],
            show_line_details=False,
        )
        ctx_disabled = DocumentDispatcher._build_full_document_context(sale_disabled)
        assert ctx_disabled.get("show_line_details") is False


@pytest.mark.django_db
class TestHistoricalSnapshotInvarianceAndDecoupling:
    """تحقق من استقلالية تفاصيل البنود عن إعدادات النظام المستقبلية وعن صلاحيات الأسعار"""

    def test_historical_document_retains_details_even_if_global_setting_disabled(self, client, master_data):
        client.force_login(master_data["user"])
        # Document created with show_line_details=True
        sale = Sale.objects.create(
            customer=master_data["customer"],
            warehouse=master_data["warehouse"],
            date=timezone.now().date(),
            subtotal=Decimal("150.00"),
            total=Decimal("150.00"),
            payment_method="credit",
            created_by=master_data["user"],
            show_line_details=True,
        )
        SaleItem.objects.create(
            sale=sale,
            product=master_data["product"],
            quantity=Decimal("1.00"),
            unit_price=Decimal("150.00"),
            total=Decimal("150.00"),
            details="Immutable Historical Spec",
        )

        # Later, global system setting is toggled to False
        SystemSetting.objects.update_or_create(
            key="show_sale_invoice_line_details", defaults={"value": "false", "data_type": "boolean"}
        )
        SystemSetting.objects.update_or_create(
            key="show_sale_line_details", defaults={"value": "false", "data_type": "boolean"}
        )
        SystemSetting.invalidate_all_system_caches()

        res = client.get(reverse("sale:sale_print", kwargs={"pk": sale.pk}))
        assert res.status_code == 200
        content = res.content.decode("utf-8")
        # Snapshot on the sale object takes precedence and renders the details
        assert "item-line-details" in content
        assert "Immutable Historical Spec" in content
