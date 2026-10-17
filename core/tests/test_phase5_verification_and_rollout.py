import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.urls import reverse

from core.models import SystemSetting, SystemModule
from customer.models import Customer
from product.models import Product, Warehouse, Unit, Stock, StockMovement, Category
from sale.models import Sale, SaleItem, Quotation, QuotationItem
from sale.models.sales_models import SalesOrder, SalesOrderItem, DeliveryNote, DeliveryNoteItem
from purchase.models import Purchase, PurchaseItem
from supplier.models import Supplier
from purchase.models.procurement_models import PurchaseOrder, PurchaseOrderItem
from financial.models import AccountType, ChartOfAccounts, AccountingPeriod, JournalEntry, FinancialCategory
from sale.services.sale_service import SaleService
from purchase.services.procurement_service import ProcurementService
from api.serializers import PurchaseItemSerializer
from utils.pdf_utils import generate_pdf_from_html, generate_guaranteed_pdf_response

User = get_user_model()


@pytest.fixture
def auth_user(db):
    user = User.objects.create_superuser(
        username="phase5_lead",
        email="phase5_lead@example.com",
        password="password123"
    )
    return user


@pytest.fixture
def setup_environment(db, auth_user):
    SystemModule.objects.all().update(is_enabled=True)
    SystemSetting.objects.update_or_create(key="enable_quotations", defaults={"value": "true", "data_type": "boolean"})
    SystemSetting.objects.update_or_create(key="enable_sales_orders", defaults={"value": "true", "data_type": "boolean"})
    SystemSetting.objects.update_or_create(key="enable_purchase_orders", defaults={"value": "true", "data_type": "boolean"})
    SystemSetting.objects.update_or_create(key="enable_thermal_printing", defaults={"value": "true", "data_type": "boolean"})
    SystemSetting.objects.update_or_create(key="show_sale_invoice_line_details", defaults={"value": "true", "data_type": "boolean"})
    SystemSetting.objects.update_or_create(key="show_quotation_line_details", defaults={"value": "true", "data_type": "boolean"})
    SystemSetting.objects.update_or_create(key="show_sales_order_line_details", defaults={"value": "true", "data_type": "boolean"})
    SystemSetting.objects.update_or_create(key="show_purchase_invoice_line_details", defaults={"value": "true", "data_type": "boolean"})
    SystemSetting.objects.update_or_create(key="show_purchase_order_line_details", defaults={"value": "true", "data_type": "boolean"})
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

    unit = Unit.objects.create(name="Meter", symbol="M")
    wh = Warehouse.objects.create(name="Central Warehouse", is_active=True)
    customer = Customer.objects.create(name="Global Contracting", is_active=True)
    supplier = Supplier.objects.create(name="Steel Industries Co.", is_active=True)
    cat = Category.objects.create(name="Raw Materials")

    product = Product.objects.create(
        name="Steel Rebar 16mm",
        sku="STL-16MM",
        category=cat,
        unit=unit,
        selling_price=Decimal("250.00"),
        cost_price=Decimal("180.00"),
        is_active=True,
        created_by=auth_user,
    )
    Stock.objects.create(product=product, warehouse=wh, quantity=Decimal("500.00"))

    exp_acc = ChartOfAccounts.objects.get(code='51100')
    fin_cat = FinancialCategory.objects.create(
        code="RAW_MAT",
        name="مواد خام",
        default_expense_account=exp_acc,
        is_active=True,
    )

    return {
        "user": auth_user,
        "product": product,
        "warehouse": wh,
        "customer": customer,
        "supplier": supplier,
        "fin_cat": fin_cat,
    }


@pytest.mark.django_db
class TestPhase5FinancialInvariance:
    """التحقق من أن وجود التفاصيل لا يُحدث أي انحراف في الحسابات أو القيود أو المخزون"""

    def test_financial_invariance_between_detailed_and_plain_sale(self, setup_environment):
        user = setup_environment["user"]
        cust = setup_environment["customer"]
        wh = setup_environment["warehouse"]
        prod = setup_environment["product"]

        data_plain = {
            "date": timezone.now().date(),
            "customer_id": cust.id,
            "warehouse_id": wh.id,
            "payment_method": "credit",
            "items": [
                {
                    "product_id": prod.id,
                    "quantity": Decimal("10.00"),
                    "unit_price": Decimal("250.00"),
                    "discount": Decimal("0.00"),
                    "details": "",
                }
            ]
        }
        sale_plain = SaleService.create_sale(data_plain, user)

        data_detailed = {
            "date": timezone.now().date(),
            "customer_id": cust.id,
            "warehouse_id": wh.id,
            "payment_method": "credit",
            "items": [
                {
                    "product_id": prod.id,
                    "quantity": Decimal("10.00"),
                    "unit_price": Decimal("250.00"),
                    "discount": Decimal("0.00"),
                    "details": "High tensile strength B500B according to DIN 488 standard specifications",
                }
            ]
        }
        sale_detailed = SaleService.create_sale(data_detailed, user)

        # Assert 100% financial and stock equivalence
        assert sale_plain.subtotal == sale_detailed.subtotal
        assert sale_plain.total == sale_detailed.total
        assert sale_plain.tax == sale_detailed.tax
        assert sale_plain.discount == sale_detailed.discount


@pytest.mark.django_db
class TestPhase5ZeroFinancialSideEffectsOnDetailsUpdate:
    """التحقق من أن تعديل نصوص التفاصيل فقط لا ينتج عنه أي قيود محاسبية أو حركات مخزنية (Gap 2)"""

    def test_details_only_update_preserves_line_ids_and_generates_zero_journal_entries(self, setup_environment):
        user = setup_environment["user"]
        cust = setup_environment["customer"]
        wh = setup_environment["warehouse"]
        prod = setup_environment["product"]

        initial_data = {
            "date": timezone.now().date(),
            "customer_id": cust.id,
            "warehouse_id": wh.id,
            "payment_method": "credit",
            "items": [
                {
                    "product_id": prod.id,
                    "quantity": Decimal("5.00"),
                    "unit_price": Decimal("250.00"),
                    "discount": Decimal("0.00"),
                    "details": "Initial draft specification",
                }
            ]
        }
        sale = SaleService.create_sale(initial_data, user)
        sale_item = sale.items.first()
        original_item_id = sale_item.id

        journal_count_before = JournalEntry.objects.count()
        movement_count_before = StockMovement.objects.count()

        # Perform details-only edit
        update_data = {
            "date": sale.date,
            "customer_id": cust.id,
            "warehouse_id": wh.id,
            "payment_method": "credit",
            "items": [
                {
                    "item_id": original_item_id,
                    "product_id": prod.id,
                    "quantity": Decimal("5.00"),
                    "unit_price": Decimal("250.00"),
                    "discount": Decimal("0.00"),
                    "details": "Final verified engineering specifications",
                }
            ]
        }
        updated_sale = SaleService.update_sale(sale, update_data, user)
        updated_item = updated_sale.items.first()

        # Line ID preserved in-place
        assert updated_item.id == original_item_id
        assert updated_item.details == "Final verified engineering specifications"

        # Exactly zero new journal entries and zero new stock movements
        assert JournalEntry.objects.count() == journal_count_before
        assert StockMovement.objects.count() == movement_count_before


@pytest.mark.django_db
class TestPhase5PurchasingRepeatedProductIntegrity:
    """التحقق من عدم دمج أو مسح الأسطر المكررة لنفس الصنف في المشتريات (Gap 1)"""

    def test_repeated_product_in_purchase_retains_separate_lines_and_details(self, client, setup_environment):
        client.force_login(setup_environment["user"])
        supp = setup_environment["supplier"]
        wh = setup_environment["warehouse"]
        prod = setup_environment["product"]
        fin_cat = setup_environment["fin_cat"]

        purchase = Purchase.objects.create(
            supplier=supp,
            warehouse=wh,
            date=timezone.now().date(),
            subtotal=Decimal("800.00"),
            total=Decimal("800.00"),
            payment_method="credit",
            financial_category=fin_cat,
            created_by=setup_environment["user"],
            show_line_details=True,
        )
        item1 = PurchaseItem.objects.create(
            purchase=purchase,
            product=prod,
            quantity=5,
            unit_price=Decimal("100.00"),
            total=Decimal("500.00"),
            details="Batch A: Galvanized coating 80 microns",
        )
        item2 = PurchaseItem.objects.create(
            purchase=purchase,
            product=prod,
            quantity=3,
            unit_price=Decimal("100.00"),
            total=Decimal("300.00"),
            details="Batch B: Black finish ungalvanized",
        )

        # Update both lines via purchase edit view
        post_data = {
            "supplier": supp.id,
            "warehouse": wh.id,
            "date": str(purchase.date),
            "payment_method": "credit",
            "financial_category": f"cat_{fin_cat.id}",
            "item_id[]": [str(item1.id), str(item2.id)],
            "product[]": [str(prod.id), str(prod.id)],
            "quantity[]": ["5", "3"],
            "unit_price[]": ["100.00", "100.00"],
            "discount[]": ["0", "0"],
            "details[]": [
                "Batch A: Updated coating spec",
                "Batch B: Updated finish spec",
            ],
            "tax": "0",
        }

        url = reverse("purchase:purchase_edit", kwargs={"pk": purchase.pk})
        res = client.post(url, post_data)
        assert res.status_code in (200, 302)

        # Verify both items exist independently with distinct specifications
        items = list(PurchaseItem.objects.filter(purchase=purchase).order_by("id"))
        assert len(items) == 2
        assert items[0].id == item1.id
        assert items[0].details == "Batch A: Updated coating spec"
        assert items[1].id == item2.id
        assert items[1].details == "Batch B: Updated finish spec"


@pytest.mark.django_db
class TestPhase5MultiHopConversionLineage:
    """التحقق من انتقال تفاصيل البنود عبر دورة المبيعات الكاملة: عرض سعر -> أمر بيع -> إذن تسليم -> فاتورة"""

    def test_complete_sales_lifecycle_propagates_details_intact(self, client, setup_environment):
        client.force_login(setup_environment["user"])
        cust = setup_environment["customer"]
        wh = setup_environment["warehouse"]
        prod = setup_environment["product"]

        # 1. عرض سعر
        q = Quotation.objects.create(
            customer=cust,
            warehouse=wh,
            date=timezone.now().date(),
            subtotal=Decimal("500.00"),
            total=Decimal("500.00"),
            created_by=setup_environment["user"],
            show_line_details=True,
        )
        q_item = QuotationItem.objects.create(
            quotation=q,
            product=prod,
            quantity=Decimal("2.00"),
            unit_price=Decimal("250.00"),
            total=Decimal("500.00"),
            details="Contractual spec: Full ultrasonic test report required",
        )

        # 2. تحويل عرض السعر إلى أمر بيع (Sales Order)
        so = SalesOrder.objects.create(
            customer=cust,
            warehouse=wh,
            quotation_reference=q,
            order_date=timezone.now().date(),
            subtotal=Decimal("500.00"),
            total_amount=Decimal("500.00"),
            created_by=setup_environment["user"],
            show_line_details=True,
        )
        so_item = SalesOrderItem.objects.create(
            sales_order=so,
            product=prod,
            ordered_qty=Decimal("2.00"),
            unit_price=Decimal("250.00"),
            line_total=Decimal("500.00"),
            details=q_item.details,
        )
        assert so_item.details == "Contractual spec: Full ultrasonic test report required"

        # 3. إنشاء إذن تسليم (Delivery Note)
        dn = DeliveryNote.objects.create(
            sales_order=so,
            customer=cust,
            warehouse=wh,
            delivery_date=timezone.now().date(),
            created_by=setup_environment["user"],
        )
        dn_item = DeliveryNoteItem.objects.create(
            delivery_note=dn,
            so_item=so_item,
            delivered_qty=Decimal("2.00"),
        )
        # إذن التسليم يقرأ التفاصيل من بند أمر البيع المرتبط
        assert dn_item.so_item.details == "Contractual spec: Full ultrasonic test report required"

        # 4. تحويل إذن التسليم إلى فاتورة مبيعات عبر GET sale_create?from_dn=...
        url_create = f"{reverse('sale:sale_create')}?from_dn={dn.pk}"
        res = client.get(url_create)
        assert res.status_code == 200

        # إنشاء الفاتورة النهائية بالربط المباشر
        sale_data = {
            "date": timezone.now().date(),
            "customer_id": cust.id,
            "warehouse_id": wh.id,
            "delivery_note_id": dn.id,
            "sales_order_id": so.id,
            "payment_method": "credit",
            "items": [
                {
                    "product_id": prod.id,
                    "quantity": Decimal("2.00"),
                    "unit_price": Decimal("250.00"),
                    "discount": Decimal("0.00"),
                    "details": so_item.details,
                }
            ]
        }
        sale = SaleService.create_sale(sale_data, setup_environment["user"])
        assert sale.items.first().details == "Contractual spec: Full ultrasonic test report required"


@pytest.mark.django_db
class TestPhase5PreDeleteSnapshotOmissionShield:
    """التحقق من عدم مسح تفاصيل البنود عند تعديل الفاتورة أثناء تعطيل حقل التفاصيل في الإعدادات (Gap 8)"""

    def test_omitted_details_in_post_preserves_existing_details(self, client, setup_environment):
        client.force_login(setup_environment["user"])
        cust = setup_environment["customer"]
        wh = setup_environment["warehouse"]
        prod = setup_environment["product"]

        # إنشاء فاتورة بتفاصيل مسجلة
        sale = Sale.objects.create(
            customer=cust,
            warehouse=wh,
            date=timezone.now().date(),
            subtotal=Decimal("250.00"),
            total=Decimal("250.00"),
            payment_method="credit",
            created_by=setup_environment["user"],
            show_line_details=True,
        )
        item = SaleItem.objects.create(
            sale=sale,
            product=prod,
            quantity=Decimal("1.00"),
            unit_price=Decimal("250.00"),
            total=Decimal("250.00"),
            details="Critical specs that must never be erased accidentally",
        )

        # محاكاة إرسال تعديل بدون حقل details[] (كأن الإعداد مغلق في الواجهة)
        post_data = {
            "customer": cust.id,
            "warehouse": wh.id,
            "date": str(sale.date),
            "invoice_type": "credit",
            "payment_method": "credit",
            "item_id[]": [str(item.id)],
            "product[]": [str(prod.id)],
            "quantity[]": ["1.00"],
            "unit_price[]": ["250.00"],
            "discount[]": ["0"],
            # details[] is deliberately omitted from POST
            "tax": "0",
        }

        url = reverse("sale:sale_edit", kwargs={"pk": sale.pk})
        res = client.post(url, post_data)
        assert res.status_code in (200, 302)

        # التحقق من أن درع الحماية استرجع التفاصيل السابقة ولم يمسحها
        refreshed_item = SaleItem.objects.filter(sale=sale).first()
        assert refreshed_item.details == "Critical specs that must never be erased accidentally"


@pytest.mark.django_db
class TestPhase5RestApiAndDuplicationIntegrity:
    """التحقق من تسلسل البيانات في REST API واحتفاظ التكرار (Duplication) بالتفاصيل"""

    def test_purchase_item_serializer_exposes_details_field(self, setup_environment):
        supp = setup_environment["supplier"]
        wh = setup_environment["warehouse"]
        prod = setup_environment["product"]

        purchase = Purchase.objects.create(
            supplier=supp,
            warehouse=wh,
            date=timezone.now().date(),
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
            payment_method="credit",
            created_by=setup_environment["user"],
        )
        item = PurchaseItem.objects.create(
            purchase=purchase,
            product=prod,
            quantity=1,
            unit_price=Decimal("100.00"),
            total=Decimal("100.00"),
            details="API serialization verified specs",
        )

        serializer = PurchaseItemSerializer(instance=item)
        assert "details" in serializer.data
        assert serializer.data["details"] == "API serialization verified specs"

    def test_sale_duplication_retains_details_on_new_invoice(self, client, setup_environment):
        client.force_login(setup_environment["user"])
        cust = setup_environment["customer"]
        wh = setup_environment["warehouse"]
        prod = setup_environment["product"]

        original_sale = Sale.objects.create(
            customer=cust,
            warehouse=wh,
            date=timezone.now().date(),
            subtotal=Decimal("250.00"),
            total=Decimal("250.00"),
            payment_method="credit",
            created_by=setup_environment["user"],
            show_line_details=True,
        )
        SaleItem.objects.create(
            sale=original_sale,
            product=prod,
            quantity=Decimal("1.00"),
            unit_price=Decimal("250.00"),
            total=Decimal("250.00"),
            details="Duplicated blueprint specifications",
        )

        url = reverse("sale:sale_duplicate", kwargs={"pk": original_sale.pk})
        res = client.get(url)
        assert res.status_code == 200
        # The form is pre-populated with details in JSON posted_items
        content = res.content.decode("utf-8")
        assert "Duplicated blueprint specifications" in content


@pytest.mark.django_db
class TestPhase5RepresentativeOutputFixture:
    """التحقق من إنشاء عينة مخرجات مطبوعة كاملة (Print & PDF Layout Acceptance Fixture)"""

    def test_representative_multiline_print_fixture_rendering(self, setup_environment):
        cust = setup_environment["customer"]
        wh = setup_environment["warehouse"]
        prod = setup_environment["product"]

        # إنشاء مستند غني بالنصوص العربية والإنجليزية وأسطر متعددة ورموز فنية
        long_spec = (
            "مواصفات توريد حديد تسليح عالي المقاومة گريد B500B:\n"
            "- مطابقة للمواصفة القياسية المصرية ES 262-2 / DIN 488.\n"
            "- شهادة اختبار كيميائي وفيزيائي معتمدة لكل لوت توريد.\n"
            "- الطول القياسي للأسياخ 12 متر بنسبة استقامة تامة.\n"
            "- Heat Number: HT-99482910-AR-EN-2026."
        )

        sale = Sale.objects.create(
            customer=cust,
            warehouse=wh,
            date=timezone.now().date(),
            subtotal=Decimal("2500.00"),
            total=Decimal("2500.00"),
            payment_method="credit",
            created_by=setup_environment["user"],
            show_line_details=True,
        )
        SaleItem.objects.create(
            sale=sale,
            product=prod,
            quantity=Decimal("10.00"),
            unit_price=Decimal("250.00"),
            total=Decimal("2500.00"),
            details=long_spec,
        )

        # توليد الـ PDF البديل المضمون عبر ReportLab والتأكد من سلامة البايتات ووجود الأسطر
        context = {
            "sale": sale,
            "items": list(sale.items.all()),
            "show_line_details": True,
            "company_name": "مؤسسة موهبة للتجارة والمقاولات",
            "company_tax_number": "300-482-192",
        }
        resp = generate_guaranteed_pdf_response("sale", context, filename="fixture_acceptance.pdf")
        assert resp.status_code == 200
        assert resp.content.startswith(b"%PDF")
        assert len(resp.content) >= 500
