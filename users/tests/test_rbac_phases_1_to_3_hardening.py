import pytest
import uuid
from decimal import Decimal
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from rest_framework.test import APIClient

from customer.models import Customer
from product.models.product_core import Product
from product.models.stock_management import Warehouse
from sale.models.sales_models import SalesOrder, SalesOrderItem, DeliveryNote, DeliveryNoteItem
from sale.models import Quotation, Sale
from work_order.models import WorkOrder
from financial.models.approval import EnterpriseApprovalRequest
from hr.permissions import CanApproveLeave
from core.context_processors import global_settings

User = get_user_model()


def make_sales_order(customer, warehouse, created_by, **kwargs):
    defaults = {
        "order_number": f"SO-{uuid.uuid4().hex[:8].upper()}",
        "customer": customer,
        "warehouse": warehouse,
        "order_date": timezone.now().date(),
        "total_amount": Decimal("1000.00"),
        "status": "DRAFT",
        "created_by": created_by,
    }
    defaults.update(kwargs)
    return SalesOrder.objects.create(**defaults)


def make_delivery_note(sales_order, customer, warehouse, created_by, **kwargs):
    defaults = {
        "delivery_number": f"DN-{uuid.uuid4().hex[:8].upper()}",
        "sales_order": sales_order,
        "customer": customer,
        "warehouse": warehouse,
        "delivery_date": timezone.now().date(),
        "status": "DELIVERED",
        "created_by": created_by,
    }
    defaults.update(kwargs)
    return DeliveryNote.objects.create(**defaults)


@pytest.fixture
def test_setup(db, users_fixture):
    """Setup base test entities: customer, warehouse, product."""
    from product.models import Category, Unit
    from core.models import SystemSetting
    SystemSetting.set_setting('enable_sales_orders', 'true')
    SystemSetting.set_setting('enable_quotations', 'true')
    customer = Customer.objects.create(name="شركة الأهرام للتغليف", phone="01011111111")
    warehouse = Warehouse.objects.create(name="مخزن الورق الرئيسي", code="WH-PAPER-01")
    category = Category.objects.create(name="أوراق وخامات")
    unit = Unit.objects.create(name="قطعة")
    admin = users_fixture["admin"]
    product = Product.objects.create(
        name="ورق كوشيه 150 جرام",
        sku="PAPER-COUCH-150",
        category=category,
        unit=unit,
        created_by=admin,
        selling_price=Decimal("500.00"),
        cost_price=Decimal("350.00")
    )
    return {
        "customer": customer,
        "warehouse": warehouse,
        "product": product,
    }


@pytest.fixture
def users_fixture(db):
    """Setup testing users with distinct roles/permissions."""
    admin = User.objects.create_superuser(username="admin_user", email="admin@mwheba.com", password="password123")
    
    rep1 = User.objects.create_user(username="rep_ahmed", email="ahmed@mwheba.com", password="password123")
    rep2 = User.objects.create_user(username="rep_mahmoud", email="mahmoud@mwheba.com", password="password123")
    
    supervisor = User.objects.create_user(username="sales_supervisor", email="supervisor@mwheba.com", password="password123")
    accountant = User.objects.create_user(username="accountant_user", email="acc@mwheba.com", password="password123")
    warehouseman = User.objects.create_user(username="warehouse_user", email="wh@mwheba.com", password="password123")
    production_sup = User.objects.create_user(username="prod_supervisor", email="prod@mwheba.com", password="password123")
    it_staff = User.objects.create_user(username="it_staff_user", email="it@mwheba.com", password="password123", is_staff=True)
    viewer = User.objects.create_user(username="viewer_user", email="view@mwheba.com", password="password123")

    # Standard rep permissions
    for rep in [rep1, rep2]:
        for codename in [
            'view_salesorder', 'add_salesorder', 'change_salesorder',
            'view_sale', 'add_sale', 'change_sale',
            'view_quotation', 'add_quotation', 'change_quotation', 'delete_quotation'
        ]:
            perm = Permission.objects.filter(codename=codename).first()
            if perm:
                rep.user_permissions.add(perm)

    # Supervisor permissions
    for codename in [
        'view_salesorder', 'add_salesorder', 'change_salesorder', 'approve_sales_order',
        'view_all_salesorders', 'view_all_sales', 'view_all_quotations',
        'view_sale', 'add_sale', 'change_sale', 'delete_sale', 'change_approved_sale',
        'view_quotation', 'add_quotation', 'change_quotation', 'delete_quotation'
    ]:
        perm = Permission.objects.filter(codename=codename).first()
        if perm:
            supervisor.user_permissions.add(perm)

    # Accountant permissions
    for codename in ['view_salesorder', 'add_salepayment']:
        perm = Permission.objects.filter(codename=codename).first()
        if perm:
            accountant.user_permissions.add(perm)
    fin_perm = Permission.objects.filter(codename='add_financialtransaction').first()
    if fin_perm:
        accountant.user_permissions.add(fin_perm)

    # Warehouseman permissions
    for codename in ['view_salesorder', 'view_deliverynote', 'add_deliverynote', 'change_deliverynote']:
        perm = Permission.objects.filter(codename=codename).first()
        if perm:
            warehouseman.user_permissions.add(perm)

    # Production supervisor permissions
    for codename in ['view_salesorder', 'view_workorder', 'add_workorder', 'change_approved_sale']:
        perm = Permission.objects.filter(codename=codename).first()
        if perm:
            production_sup.user_permissions.add(perm)

    return {
        "admin": admin,
        "rep1": rep1,
        "rep2": rep2,
        "supervisor": supervisor,
        "accountant": accountant,
        "warehouseman": warehouseman,
        "production_sup": production_sup,
        "it_staff": it_staff,
        "viewer": viewer,
    }


# ==================== Phase 1: Governance & Dead Models ====================

def test_governance_services_purged_of_deleted_models():
    """1. التحقق من خلو خدمات الحوكمة من مراجع الموديلات المحذوفة"""
    from governance.services.accounting_gateway import AccountingGateway
    from governance.services.source_linkage_service import SourceLinkageService

    forbidden_models = [
        'qr_applications.QRApplication',
        'courses.CourseEnrollment',
        'activities.ActivityExpense',
        'transportation.TransportationFee'
    ]

    for model_name in forbidden_models:
        assert model_name not in AccountingGateway.ALLOWED_SOURCES, f"{model_name} found in AccountingGateway.ALLOWED_SOURCES"
        assert model_name not in SourceLinkageService.ALLOWED_SOURCES, f"{model_name} found in SourceLinkageService.ALLOWED_SOURCES"


# ==================== Phase 2: SalesOrder & DeliveryNote Hardening ====================

def test_sales_order_confirm_requires_approve_permission(client, users_fixture, test_setup):
    """2. التحقق من اشتراط صلاحية sale.approve_sales_order لاعتماد أمر البيع"""
    rep = users_fixture["rep1"]
    supervisor = users_fixture["supervisor"]
    
    so = make_sales_order(
        customer=test_setup["customer"],
        warehouse=test_setup["warehouse"],
        created_by=rep,
        salesman=rep,
        status="DRAFT"
    )

    # Standard rep without approve_sales_order
    client.force_login(rep)
    url = reverse("sale:sales_order_confirm", kwargs={"pk": so.pk})
    resp = client.post(url)
    assert resp.status_code in [403, 302]
    so.refresh_from_db()
    assert so.status == "DRAFT"  # Not approved!

    # Supervisor with approve_sales_order
    client.force_login(supervisor)
    resp = client.post(url)
    assert resp.status_code == 302
    so.refresh_from_db()
    assert so.status == "APPROVED"


def test_sales_order_cancel_requires_change_permission(client, users_fixture, test_setup):
    """3. التحقق من اشتراط صلاحية sale.change_salesorder لإلغاء أمر البيع"""
    viewer = users_fixture["viewer"]
    supervisor = users_fixture["supervisor"]

    so = make_sales_order(
        customer=test_setup["customer"],
        warehouse=test_setup["warehouse"],
        created_by=supervisor,
        status="DRAFT"
    )

    client.force_login(viewer)
    url = reverse("sale:sales_order_cancel", kwargs={"pk": so.pk})
    resp = client.post(url)
    assert resp.status_code in [403, 302]
    so.refresh_from_db()
    assert so.status == "DRAFT"

    client.force_login(supervisor)
    resp = client.post(url)
    assert resp.status_code == 302
    so.refresh_from_db()
    assert so.status == "CANCELLED"


def test_sales_order_override_down_payment_requires_approval_perm(client, users_fixture, test_setup):
    """4. التحقق من قصر التجاوز الإداري للدفعة المقدمة على صلاحية الاعتماد وحظره على المندوب العادي"""
    rep = users_fixture["rep1"]
    supervisor = users_fixture["supervisor"]

    so = make_sales_order(
        customer=test_setup["customer"],
        warehouse=test_setup["warehouse"],
        created_by=rep,
        salesman=rep,
        status="DRAFT"
    )

    url = reverse("sale:sales_order_override_down_payment", kwargs={"pk": so.pk})

    # Standard rep has change_salesorder, but NOT approve_sales_order
    client.force_login(rep)
    resp = client.post(url, {"override_reason": "تجاوز شخصي من المندوب"})
    so.refresh_from_db()
    assert so.down_payment_override is False

    # Supervisor has approve_sales_order
    client.force_login(supervisor)
    resp = client.post(url, {"override_reason": "اعتماد مدير المبيعات"})
    so.refresh_from_db()
    assert so.down_payment_override is True
    assert so.down_payment_override_by == supervisor


def test_sales_order_collect_down_payment_denies_staff_without_perm(client, users_fixture, test_setup):
    """5. التحقق من منع موظف الـ IT/Staff من تسجيل سندات القبض دون صلاحية مالية"""
    it_staff = users_fixture["it_staff"]
    accountant = users_fixture["accountant"]

    so = make_sales_order(
        customer=test_setup["customer"],
        warehouse=test_setup["warehouse"],
        created_by=accountant,
        status="APPROVED"
    )

    url = reverse("sale:sales_order_collect_down_payment", kwargs={"pk": so.pk})

    # IT Staff has is_staff=True but no financial permission
    client.force_login(it_staff)
    resp = client.post(url, {"amount": "1000"})
    so.refresh_from_db()
    assert so.down_payments.count() == 0


def test_delivery_note_cancel_requires_permission_and_auth(client, users_fixture, test_setup):
    """6. التحقق من تأمين إلغاء إذن التسليم واشتراط تسجيل الدخول وصلاحية change_deliverynote"""
    viewer = users_fixture["viewer"]
    warehouseman = users_fixture["warehouseman"]

    so = make_sales_order(
        customer=test_setup["customer"],
        warehouse=test_setup["warehouse"],
        created_by=warehouseman,
        status="APPROVED"
    )
    dn = make_delivery_note(
        sales_order=so,
        customer=test_setup["customer"],
        warehouse=test_setup["warehouse"],
        created_by=warehouseman,
        status="DELIVERED"
    )

    url = reverse("sale:delivery_note_cancel", kwargs={"pk": dn.pk})

    # Anonymous user
    client.logout()
    resp = client.post(url)
    assert resp.status_code in [403, 302]
    dn.refresh_from_db()
    assert dn.status == "DELIVERED"

    # Viewer without permission
    client.force_login(viewer)
    resp = client.post(url)
    assert resp.status_code in [403, 302]
    dn.refresh_from_db()
    assert dn.status == "DELIVERED"

    # Warehouseman with change_deliverynote
    client.force_login(warehouseman)
    resp = client.post(url)
    assert resp.status_code == 302
    dn.refresh_from_db()
    assert dn.status == "CANCELLED"


def test_delivery_note_create_and_views_require_permissions(client, users_fixture):
    """7. التحقق من حماية مسارات إنشاء وعرض إذون التسليم بالصلاحيات المعيارية"""
    viewer = users_fixture["viewer"]
    warehouseman = users_fixture["warehouseman"]

    create_url = reverse("sale:delivery_note_create")
    list_url = reverse("sale:delivery_note_list")

    client.force_login(viewer)
    assert client.get(create_url).status_code in [403, 302]
    assert client.get(list_url).status_code in [403, 302]

    client.force_login(warehouseman)
    assert client.get(list_url).status_code == 200
    assert client.get(create_url).status_code == 200


def test_pricing_settings_view_blocks_staff_without_permission(client, users_fixture):
    """8. التحقق من حظر وصول موظف IT/Staff لإعدادات التسعير بدون امتلاك manage_pricing_settings"""
    it_staff = users_fixture["it_staff"]
    supervisor = users_fixture["supervisor"]

    perm = Permission.objects.filter(codename="manage_pricing_settings").first()
    if perm:
        supervisor.user_permissions.add(perm)

    url = reverse("printing_pricing:paper_type_list")

    client.force_login(it_staff)
    resp = client.get(url)
    assert resp.status_code == 403

    client.force_login(supervisor)
    resp = client.get(url)
    assert resp.status_code == 200


def test_sales_order_detail_rep_isolation(client, users_fixture, test_setup):
    """9. التحقق من عزل أوامر البيع وإرجاع 404 للمندوب المنافس عند محاولة فتح أمر بيع زميله"""
    rep1 = users_fixture["rep1"]
    rep2 = users_fixture["rep2"]
    supervisor = users_fixture["supervisor"]

    so_rep1 = make_sales_order(
        customer=test_setup["customer"],
        warehouse=test_setup["warehouse"],
        created_by=rep1,
        salesman=rep1,
        status="DRAFT"
    )

    url = reverse("sale:sales_order_detail", kwargs={"pk": so_rep1.pk})

    # Rep 1 can view his own order
    client.force_login(rep1)
    assert client.get(url).status_code == 200

    # Rep 2 receives 404
    client.force_login(rep2)
    assert client.get(url).status_code == 404

    # Supervisor with view_all_salesorders can view
    client.force_login(supervisor)
    assert client.get(url).status_code == 200


def test_sales_order_detail_accessible_to_accountant_and_inventory(client, users_fixture, test_setup):
    """10. التحقق من تمكن المحاسب وأمين المخزن ومشرف الإنتاج من فتح أمر البيع لإتمام دورة العمل"""
    rep1 = users_fixture["rep1"]
    accountant = users_fixture["accountant"]
    warehouseman = users_fixture["warehouseman"]
    prod_sup = users_fixture["production_sup"]

    so = make_sales_order(
        customer=test_setup["customer"],
        warehouse=test_setup["warehouse"],
        created_by=rep1,
        salesman=rep1,
        status="APPROVED"
    )

    url = reverse("sale:sales_order_detail", kwargs={"pk": so.pk})

    client.force_login(accountant)
    assert client.get(url).status_code == 200

    client.force_login(warehouseman)
    assert client.get(url).status_code == 200

    client.force_login(prod_sup)
    assert client.get(url).status_code == 200


def test_sales_order_print_rep_isolation(client, users_fixture, test_setup):
    """11. التحقق من حظر المندوب من طباعة أمر بيع زميله بإرجاع 404"""
    rep1 = users_fixture["rep1"]
    rep2 = users_fixture["rep2"]

    so = make_sales_order(
        customer=test_setup["customer"],
        warehouse=test_setup["warehouse"],
        created_by=rep1,
        salesman=rep1,
        status="APPROVED"
    )

    url = reverse("sale:sales_order_print", kwargs={"pk": so.pk})

    client.force_login(rep1)
    assert client.get(url).status_code == 200

    client.force_login(rep2)
    assert client.get(url).status_code == 404


def test_sales_order_convert_to_sale_requires_permission_and_isolation(client, users_fixture, test_setup):
    """12. التحقق من اشتراط صلاحية sale.add_sale وعزل الملكية عند تحويل أمر البيع لفاتورة"""
    rep1 = users_fixture["rep1"]
    rep2 = users_fixture["rep2"]
    viewer = users_fixture["viewer"]

    so = make_sales_order(
        customer=test_setup["customer"],
        warehouse=test_setup["warehouse"],
        created_by=rep1,
        salesman=rep1,
        status="APPROVED"
    )

    url = reverse("sale:sales_order_convert_to_sale", kwargs={"pk": so.pk})

    # Viewer has no add_sale
    client.force_login(viewer)
    assert client.get(url).status_code == 403

    # Rep2 is not owner
    client.force_login(rep2)
    assert client.get(url).status_code == 404

    # Rep1 is owner and has add_sale
    client.force_login(rep1)
    resp = client.get(url)
    assert resp.status_code == 302
    assert "from_so=" in resp.url


def test_quotation_detail_rep_isolation(client, users_fixture, test_setup):
    """13. التحقق من عزل عروض الأسعار للمناديب في شاشات التفاصيل والطباعة"""
    rep1 = users_fixture["rep1"]
    rep2 = users_fixture["rep2"]

    quote = Quotation.objects.create(
        customer=test_setup["customer"],
        created_by=rep1,
        salesman=rep1,
        date="2026-09-08",
        status="draft"
    )

    detail_url = reverse("sale:quotation_detail", kwargs={"pk": quote.pk})
    print_url = reverse("sale:quotation_print", kwargs={"pk": quote.pk})

    client.force_login(rep1)
    assert client.get(detail_url).status_code == 200
    assert client.get(print_url).status_code == 200

    client.force_login(rep2)
    assert client.get(detail_url).status_code == 404
    assert client.get(print_url).status_code == 404


def test_quotation_delete_rep_isolation(client, users_fixture, test_setup):
    """14. التحقق من حظر المندوب من حذف عروض أسعار زملائه"""
    rep1 = users_fixture["rep1"]
    rep2 = users_fixture["rep2"]

    quote = Quotation.objects.create(
        customer=test_setup["customer"],
        created_by=rep1,
        salesman=rep1,
        date="2026-09-08",
        status="draft"
    )

    url = reverse("sale:quotation_delete", kwargs={"pk": quote.pk})

    client.force_login(rep2)
    resp = client.post(url)
    assert resp.status_code == 200  # Renders permission_denied
    assert Quotation.objects.filter(pk=quote.pk).exists()

    client.force_login(rep1)
    resp = client.post(url)
    assert resp.status_code == 302
    assert not Quotation.objects.filter(pk=quote.pk).exists()


def test_production_in_progress_lock_on_sales_and_quotations(client, users_fixture, test_setup):
    """15. التحقق من قفل تعديل الفواتير وأوامر البيع وعروض الأسعار عند حالة in_progress في صالة الإنتاج"""
    rep = users_fixture["rep1"]
    prod_sup = users_fixture["production_sup"]

    wo = WorkOrder.objects.create(
        number="WO-2026-TEST-99",
        customer=test_setup["customer"],
        created_by=prod_sup,
        status="in_progress"  # Real production status
    )

    # 1. Sale linked to WorkOrder
    sale = Sale.objects.create(
        customer=test_setup["customer"],
        warehouse=test_setup["warehouse"],
        work_order=wo,
        created_by=rep,
        salesman=rep,
        date=timezone.now().date(),
        subtotal=Decimal("500.00"),
        total=Decimal("500.00"),
        status="completed"
    )

    # 2. Quotation linked to WorkOrder
    quote = Quotation.objects.create(
        customer=test_setup["customer"],
        work_order=wo,
        created_by=rep,
        salesman=rep,
        date="2026-09-08",
        status="draft"
    )

    # 3. SalesOrder linked via Quotation
    so = make_sales_order(
        customer=test_setup["customer"],
        warehouse=test_setup["warehouse"],
        quotation_reference=quote,
        created_by=rep,
        salesman=rep,
        status="DRAFT"
    )

    client.force_login(rep)

    # Attempt to edit Sale
    resp_sale = client.get(reverse("sale:sale_edit", kwargs={"pk": sale.pk}))
    assert resp_sale.status_code == 302  # Blocked and redirected

    # Attempt to edit Quotation
    resp_quote = client.get(reverse("sale:quotation_edit", kwargs={"pk": quote.pk}))
    assert resp_quote.status_code == 302  # Blocked and redirected

    # Attempt to edit SalesOrder
    resp_so = client.get(reverse("sale:sales_order_edit", kwargs={"pk": so.pk}))
    assert resp_so.status_code == 302  # Blocked and redirected


# ==================== Phase 3: REST API & HR Hardening ====================

def test_api_endpoints_enforce_role_based_permissions(client, users_fixture):
    """16. التحقق من تطبيق RoleBasedModelPermissions على مسارات الـ API الحساسة"""
    viewer = users_fixture["viewer"]
    api_client = APIClient()
    api_client.force_authenticate(user=viewer)

    # Viewer lacks supplier.view_supplier and purchase.view_purchase
    assert api_client.get("/api/suppliers/").status_code == 403
    assert api_client.get("/api/purchases/").status_code == 403
    assert api_client.get("/api/stocks/").status_code == 403
    assert api_client.get("/api/stock-movements/").status_code == 403
    assert api_client.get("/api/users/").status_code == 403


def test_api_user_salesmen_lookup_accessible_without_full_user_view_perm(users_fixture):
    """17. التحقق من عمل مسار المناديب salesmen للمستخدمين دون كشف تفاصيل إدارة المستخدمين"""
    rep = users_fixture["rep1"]
    api_client = APIClient()
    api_client.force_authenticate(user=rep)

    # Full users list is blocked
    assert api_client.get("/api/users/").status_code == 403

    # Salesmen endpoint is accessible
    resp = api_client.get("/api/users/salesmen/")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert any(item["username"] == rep.username for item in data)
    assert "email" not in data[0]  # Secure, only id/name/username


def test_hr_leave_approval_permission_unified(users_fixture):
    """18. التحقق من دعم CanApproveLeave لكلا المسميين hr.approve_leave و can_approve_leaves"""
    user = users_fixture["rep1"]
    ct = ContentType.objects.filter(app_label="hr").first()
    p1, _ = Permission.objects.get_or_create(codename="can_approve_leaves", defaults={"name": "Can approve leaves", "content_type": ct})
    user.user_permissions.add(p1)
    user = User.objects.get(pk=user.pk)

    class DummyRequest:
        def __init__(self, u):
            self.user = u

    req = DummyRequest(user)
    assert CanApproveLeave().has_permission(req, None) is True

    # Also test approve_leave
    user2 = User.objects.create_user(username="leave_test_user2", password="password")
    p2, _ = Permission.objects.get_or_create(codename="approve_leave", defaults={"name": "Approve leave", "content_type": ct})
    user2.user_permissions.add(p2)
    user2 = User.objects.get(pk=user2.pk)
    req2 = DummyRequest(user2)
    assert CanApproveLeave().has_permission(req2, None) is True


def test_context_processor_clean_permissions(rf, users_fixture):
    """19. التحقق من انضباط Context Processor وعدم اعتماده على صفات هجينة"""
    supervisor = users_fixture["supervisor"]
    perm = Permission.objects.filter(codename="approve_workflow").first()
    if perm:
        supervisor.user_permissions.add(perm)

    req = rf.get("/")
    req.user = supervisor

    context = global_settings(req)
    assert "pending_approvals_count" in context
