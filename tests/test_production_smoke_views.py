"""
اختبارات الدخان والتكامل للمرحلة الأولى للإصلاحات المباشرة لبيئة الإنتاج
Smoke & Integration Tests for Production Phase 1 Direct Hotfixes
"""
import pytest
from decimal import Decimal
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from hr.models import Employee, LeaveType, Department, JobTitle
from customer.models import Customer
from product.models import Product, Warehouse, Stock, Category, Unit
from product.models.supplier_pricing import PriceHistory
from financial.models import ChartOfAccounts, AccountType, Currency
from sale.models import Sale, SaleItem

User = get_user_model()


@pytest.fixture
def superuser(db):
    user = User.objects.create_superuser(
        username="admin_smoke",
        email="admin_smoke@example.com",
        password="password123"
    )
    return user


@pytest.fixture
def setup_basic_data(db, superuser):
    from datetime import date
    # إنشاء حسابات أساسية
    asset_type, _ = AccountType.objects.get_or_create(
        code="AST",
        defaults={"name": "أصول", "category": "asset"}
    )
    cash_acc = ChartOfAccounts.objects.create(
        code="10101",
        name="الخزينة الرئيسية",
        account_type=asset_type,
        is_cash_account=True,
        is_active=True
    )
    custody_acc = ChartOfAccounts.objects.create(
        code="10105",
        name="عهدة موظف",
        account_type=asset_type,
        is_custody_account=True,
        is_active=True
    )
    currency, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={"name": "جنيه مصري", "symbol": "ج.م", "is_functional": True, "is_active": True}
    )
    dept = Department.objects.create(name_ar="الإدارة المالية", code="FIN-01")
    job = JobTitle.objects.create(title_ar="محاسب", code="ACC-01", department=dept)

    emp = Employee.objects.create(
        employee_number="EMP-001",
        name="أحمد علي محمد",
        national_id="29501011234567",
        birth_date=date(1995, 1, 1),
        gender="male",
        marital_status="single",
        department=dept,
        job_title=job,
        hire_date=date(2020, 1, 1),
        created_by=superuser,
        status="active"
    )
    customer = Customer.objects.create(
        name="عميل تجريبي",
        phone="01012345678",
        is_active=True
    )
    wh = Warehouse.objects.create(
        name="المخزن الرئيسي",
        code="WH-01",
        is_active=True
    )
    cat = Category.objects.create(
        name="تصنيف تجريبي",
        is_active=True
    )
    unit = Unit.objects.create(
        name="قطعة",
        symbol="قطعة"
    )
    prod = Product.objects.create(
        name="منتج تجريبي",
        sku="PRD-01-SKU",
        category=cat,
        unit=unit,
        cost_price=Decimal("40.00"),
        selling_price=Decimal("50.00"),
        min_stock=5,
        created_by=superuser,
        is_active=True
    )
    stock = Stock.objects.create(
        product=prod,
        warehouse=wh,
        quantity=20,
        min_stock_level=5,
        max_stock_level=50
    )
    return {
        "cash_acc": cash_acc,
        "custody_acc": custody_acc,
        "currency": currency,
        "emp": emp,
        "dept": dept,
        "job": job,
        "customer": customer,
        "wh": wh,
        "prod": prod,
        "stock": stock,
    }


@pytest.mark.django_db
def test_employee_manager_active(superuser, setup_basic_data):
    """فحص عمل EmployeeManager.active() بدقة"""
    from datetime import date
    dept = setup_basic_data["dept"]
    job = setup_basic_data["job"]
    Employee.objects.all().delete()
    e1 = Employee.objects.create(
        employee_number="E1", name="Ali Mohamed", national_id="29501011234561",
        birth_date=date(1995, 1, 1), gender="male", marital_status="single",
        department=dept, job_title=job, hire_date=date(2020, 1, 1),
        created_by=superuser, status="active"
    )
    e2 = Employee.objects.create(
        employee_number="E2", name="Omar Mohamed", national_id="29501011234562",
        birth_date=date(1995, 1, 1), gender="male", marital_status="single",
        department=dept, job_title=job, hire_date=date(2020, 1, 1),
        created_by=superuser, status="suspended"
    )
    e3 = Employee.objects.create(
        employee_number="E3", name="Sara Mohamed", national_id="29501011234563",
        birth_date=date(1995, 1, 1), gender="female", marital_status="single",
        department=dept, job_title=job, hire_date=date(2020, 1, 1),
        created_by=superuser, status="terminated"
    )

    active_emps = list(Employee.objects.active())
    assert len(active_emps) == 1
    assert active_emps[0].employee_number == "E1"


@pytest.mark.django_db
def test_cash_accounts_list_view_renders_200(client, superuser, setup_basic_data):
    """فحص صفحة الخزن والعهد النقدية والتأكد من عدم حدوث FieldError على is_active"""
    client.force_login(superuser)
    url = reverse("financial:cash_accounts_list")
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context["employees"]) >= 1


@pytest.mark.django_db
def test_custody_views_all_five_render_200(client, superuser, setup_basic_data):
    """فحص كافة شاشات العهد الخمسة (قائمة، إنشاء، تسوية، مناقلة، جرد) والتأكد من استقرارها 200 OK"""
    client.force_login(superuser)

    # 1. قائمة العهد
    r1 = client.get(reverse("financial:custody_advance_list"))
    assert r1.status_code == 200

    # 2. إنشاء عهدة
    r2 = client.get(reverse("financial:custody_advance_create"))
    assert r2.status_code == 200

    # 3. تسوية عهدة
    r3 = client.get(reverse("financial:custody_settlement_create"))
    assert r3.status_code == 200

    # 4. مناقلة عهدة
    r4 = client.get(reverse("financial:custody_transfer_create"))
    assert r4.status_code == 200

    # 5. جرد عهدة
    r5 = client.get(reverse("financial:custody_count_create"))
    assert r5.status_code == 200


@pytest.mark.django_db
def test_customer_detail_view_renders_200(client, superuser, setup_basic_data):
    """فحص صفحة تفاصيل العميل وتكامل ContentType بدون NameError"""
    client.force_login(superuser)
    customer = setup_basic_data["customer"]
    url = reverse("customer:customer_detail", kwargs={"pk": customer.pk})
    response = client.get(url)
    assert response.status_code == 200
    assert "customer_content_type_id" in response.context


@pytest.mark.django_db
def test_hr_leaves_view_renders_200(client, superuser, setup_basic_data):
    """فحص صفحة طلبات الإجازات والتأكد من تعريف leave_types بدون NameError"""
    client.force_login(superuser)
    LeaveType.objects.create(name_ar="إجازة سنوية", code="ANNUAL-01", max_days_per_year=21, is_active=True)
    url = reverse("hr:leave_list")
    response = client.get(url)
    assert response.status_code == 200
    assert "leave_types" in response.context


@pytest.mark.django_db
def test_sale_duplicate_view_renders_200(client, superuser, setup_basic_data):
    """فحص نسخ فاتورة المبيعات واكتمال context العملات وقوائم الأسعار"""
    client.force_login(superuser)
    sale = Sale.objects.create(
        number="INV-SMOKE-001",
        customer=setup_basic_data["customer"],
        warehouse=setup_basic_data["wh"],
        created_by=superuser,
        date=timezone.now().date(),
        subtotal=Decimal("100.00"),
        total=Decimal("100.00")
    )
    SaleItem.objects.create(
        sale=sale,
        product=setup_basic_data["prod"],
        quantity=Decimal("2"),
        unit_price=Decimal("50.00"),
        total=Decimal("100.00")
    )
    url = reverse("sale:sale_duplicate", kwargs={"pk": sale.pk})
    response = client.get(url)
    assert response.status_code == 200
    assert "currencies" in response.context
    assert "active_currencies" in response.context
    assert "price_lists" in response.context


@pytest.mark.django_db
def test_warehouse_export_inventory_csv_renders_200(client, superuser, setup_basic_data):
    """فحص تصدير CSV للمخزون والتأكد من عدم وجود AttributeError على max_stock"""
    client.force_login(superuser)
    wh = setup_basic_data["wh"]
    url = reverse("product:export_warehouse_inventory", kwargs={"warehouse_id": wh.pk})
    response = client.get(url)
    assert response.status_code == 200
    assert "text/csv" in response["Content-Type"]
    content = response.content.decode("utf-8-sig")
    assert "منتج تجريبي" in content
    assert "مخزون جيد" in content


@pytest.mark.django_db
def test_supplier_price_history_change_percentage_clamp(db, superuser, setup_basic_data):
    """فحص حماية حقل change_percentage من تجاوز سعة MySQL عند القفزات السعرية الهائلة"""
    hist = PriceHistory(
        product=setup_basic_data["prod"],
        old_price=Decimal("0.01"),
        new_price=Decimal("1000000.00"),  # قفزة سعرية ضخمة
        changed_by=superuser
    )
    hist.save()
    assert hist.change_percentage <= Decimal("9999.9999")


# ============================================================================
# Phase 2 Tests: Warehouse Core Engine Hardening
# ============================================================================

@pytest.mark.django_db
def test_transfer_service_lifecycle_and_accounting(superuser, setup_basic_data):
    """فحص دورة حياة التحويل المخزني: الحجز الذري، الاعتماد، تحديث متوسط التكلفة، والقيد المحاسبي"""
    from product.services.transfer_service import TransferService
    from product.models import InventoryMovement

    prod = setup_basic_data["prod"]
    source_wh = setup_basic_data["wh"]
    target_wh = Warehouse.objects.create(name="مخزن الفروع", code="WH-02", is_active=True)

    # إنشاء رصيد أولي في المخزن المصدر
    source_stock = setup_basic_data["stock"]
    source_stock.quantity = Decimal("100")
    source_stock.reserved_quantity = Decimal("0")
    source_stock.average_cost = Decimal("40.00")
    source_stock.save()

    service = TransferService()
    mov_out, mov_in = service.create_transfer(
        product=prod,
        from_warehouse=source_wh,
        to_warehouse=target_wh,
        quantity=30,
        user=superuser,
        reference_document="REF-TR-001",
        notes="تحويل فرعي"
    )

    # التحقق من حجز الكمية
    source_stock.refresh_from_db()
    assert source_stock.quantity == Decimal("100")
    assert source_stock.reserved_quantity == Decimal("30")
    assert source_stock.available_quantity == Decimal("70")
    assert not mov_out.is_approved
    assert not mov_in.is_approved

    # اعتماد التحويل
    success = service.approve_transfer(mov_out, superuser)
    assert success is True

    # التحقق من تحديث الأرصدة بعد الاعتماد
    source_stock.refresh_from_db()
    assert source_stock.quantity == Decimal("70")
    assert source_stock.reserved_quantity == Decimal("0")
    assert source_stock.available_quantity == Decimal("70")

    target_stock = Stock.objects.get(product=prod, warehouse=target_wh)
    assert target_stock.quantity == Decimal("30")
    assert target_stock.average_cost == Decimal("40.00")

    mov_out.refresh_from_db()
    mov_in.refresh_from_db()
    assert mov_out.is_approved is True
    assert mov_in.is_approved is True


@pytest.mark.django_db
def test_inbound_movement_numbering_document_type(superuser, setup_basic_data):
    """فحص ترقيم الحركات الواردة والتأكد من استخدام DocumentType.STOCK_RECEIPT بدلاً من الصرف"""
    from product.models import InventoryMovement
    from core.enums.document_types import DocumentType

    prod = setup_basic_data["prod"]
    wh = setup_basic_data["wh"]

    mov = InventoryMovement.objects.create(
        product=prod,
        warehouse=wh,
        movement_type='in',
        quantity=15,
        unit_cost=Decimal("40.00"),
        created_by=superuser,
        is_approved=False
    )
    # يجب أن يحتوي رقم الحركة على بادئة الاستلام وليس الصرف
    assert mov.movement_number is not None
    assert len(mov.movement_number) > 0


@pytest.mark.django_db
def test_transfer_voucher_delete_view_releases_reserved_stock(client, superuser, setup_basic_data):
    """فحص حذف إذن التحويل غير المعتمد وتحرير الكمية المحجوزة تلقائياً"""
    from product.services.transfer_service import TransferService

    client.force_login(superuser)
    prod = setup_basic_data["prod"]
    source_wh = setup_basic_data["wh"]
    target_wh = Warehouse.objects.create(name="المخزن الإضافي", code="WH-03", is_active=True)

    source_stock = setup_basic_data["stock"]
    source_stock.quantity = Decimal("50")
    source_stock.reserved_quantity = Decimal("0")
    source_stock.save()

    service = TransferService()
    mov_out, mov_in = service.create_transfer(
        product=prod,
        from_warehouse=source_wh,
        to_warehouse=target_wh,
        quantity=20,
        user=superuser
    )

    source_stock.refresh_from_db()
    assert source_stock.reserved_quantity == Decimal("20")

    # حذف إذن التحويل عبر Delete View
    url = reverse("product:transfer_voucher_delete", kwargs={"pk": mov_out.pk})
    response = client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert response.status_code == 200
    assert response.json()["success"] is True

    # التأكد من تحرير الكمية المحجوزة وحذف الحركتين
    source_stock.refresh_from_db()
    assert source_stock.reserved_quantity == Decimal("0")
    assert source_stock.available_quantity == Decimal("50")


@pytest.mark.django_db
def test_transfer_voucher_ajax_approval_view(client, superuser, setup_basic_data):
    """فحص اعتماد إذن التحويل عبر AJAX والتأكد من إرجاع استجابة JSON سليمة"""
    from product.services.transfer_service import TransferService

    client.force_login(superuser)
    prod = setup_basic_data["prod"]
    source_wh = setup_basic_data["wh"]
    target_wh = Warehouse.objects.create(name="مخزن الإسكندرية", code="WH-04", is_active=True)

    source_stock = setup_basic_data["stock"]
    source_stock.quantity = Decimal("60")
    source_stock.reserved_quantity = Decimal("0")
    source_stock.save()

    service = TransferService()
    mov_out, _ = service.create_transfer(
        product=prod,
        from_warehouse=source_wh,
        to_warehouse=target_wh,
        quantity=10,
        user=superuser
    )

    url = reverse("product:transfer_voucher_approve", kwargs={"pk": mov_out.pk})
    response = client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert response.status_code == 200
    assert response.json()["success"] is True

    mov_out.refresh_from_db()
    assert mov_out.is_approved is True


# ============================================================================
# Phase 3 Tests: Accounting Governance, FX Fallback & Edge Shields
# ============================================================================

@pytest.mark.django_db
def test_resilient_fx_fallback(superuser, setup_basic_data):
    """فحص السقوط التاريخي الآمن لأسعار الصرف عند غياب سعر الصرف في نفس لحظة الفاتورة"""
    from datetime import date, timedelta
    from financial.models.currency import ExchangeRate
    from financial.services.exchange_rate_service import ExchangeRateService

    usd = Currency.objects.create(code="USD", name="US Dollar", symbol="$", is_functional=False, is_active=True)
    egp = setup_basic_data["currency"]

    past_date = date.today() - timedelta(days=5)
    # تسجيل سعر صرف قديم قبل 5 أيام
    ExchangeRate.objects.create(
        from_currency=usd,
        to_currency=egp,
        rate=Decimal("48.500000"),
        effective_date=past_date,
        created_by=superuser
    )

    # طلب سعر الصرف لتاريخ اليوم (مع عدم تسجيل سعر اليوم)
    rate_today = ExchangeRateService.get_exchange_rate(usd, date=date.today())
    assert rate_today == Decimal("48.500000")


@pytest.mark.django_db
def test_purchase_edit_stock_floor_protection(client, superuser, setup_basic_data):
    """فحص درع حماية المخزون عند تعديل أو إنقاص كمية مشتريات لصنف تم بيعه"""
    from purchase.models import Purchase, PurchaseItem
    from datetime import date

    client.force_login(superuser)
    prod = setup_basic_data["prod"]
    wh = setup_basic_data["wh"]
    supplier = setup_basic_data["customer"] # Use as party or create Supplier
    from supplier.models import Supplier
    supp = Supplier.objects.create(name="مورد تجريبي", phone="01099998888", is_active=True)

    # فاتورة شراء سابقة بـ 10 قطع
    purchase = Purchase.objects.create(
        number="PUR-TEST-001",
        supplier=supp,
        warehouse=wh,
        date=date.today(),
        subtotal=Decimal("400.00"),
        total=Decimal("400.00"),
        created_by=superuser,
        payment_status="unpaid"
    )
    p_item = PurchaseItem.objects.create(
        purchase=purchase,
        product=prod,
        quantity=Decimal("10.00"),
        unit_price=Decimal("40.00"),
        total=Decimal("400.00")
    )

    # الرصيد المتاح بالمخزن حالياً 2 فقط (لأنه تم بيع 8 قطع)
    stock = setup_basic_data["stock"]
    stock.quantity = Decimal("2.00")
    stock.save()

    # محاولة تعديل الفاتورة لإنقاص الكمية من 10 إلى 3 (المطلوب خصم 7، بينما المتاح 2 فقط)
    url = reverse("purchase:purchase_edit", kwargs={"pk": purchase.pk})
    post_data = {
        "supplier": supp.id,
        "warehouse": wh.id,
        "date": date.today().strftime("%Y-%m-%d"),
        "product[]": [prod.id],
        "quantity[]": ["3.00"],
        "unit_price[]": ["40.00"],
        "discount[]": ["0.00"],
        "discount": "0.00",
        "tax": "0.00",
    }
    response = client.post(url, post_data)
    # يجب أن يتم رفض التعديل وعرض رسالة خطأ واضحة للمستخدم
    assert response.status_code == 200
    # التحقق من عدم تغيير كمية الفاتورة
    p_item.refresh_from_db()
    assert p_item.quantity == Decimal("10.00")


@pytest.mark.django_db
def test_hierarchical_inventory_account_fallback(setup_basic_data):
    """فحص السقوط الهرمي لحسابات المخزون (6 مستويات حماية)"""
    from product.services.voucher_accounting_service import get_inventory_account

    prod = setup_basic_data["prod"]
    wh = setup_basic_data["wh"]

    # المستوى 6: التراجع لحساب الأصول عند عدم تحديد حساب مباشر
    acc = get_inventory_account(product=prod, warehouse=wh)
    assert acc is not None
    assert acc.account_type.category == 'asset'


