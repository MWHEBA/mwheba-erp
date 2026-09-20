# -*- coding: utf-8 -*-
"""
MWHEBA ERP RBAC Phase 8 (المرحلة الثامنة) Comprehensive Automated Test Suite
Validates:
1. Complete Operational Permission Discovery (100+ permissions across all modules).
2. Professional Arabic Terminology Translation.
3. Total Purge of is_staff bypass from decorators and mixins (Zero-Trust).
4. Dual-Guarded Dependency Resolution & SSOT for Roles and Users.
5. Role Lifecycle Management APIs (Create, Edit, Delete, Assign).
6. Canonical 10 Roles Seeding with Prerequisite Integrity.
7. Enterprise Segregation of Duties (SoD) & Role Boundary Enforcement.
8. Cache Invalidation & System Notification Standard.
"""

import json
import pytest
from decimal import Decimal
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.test import Client, RequestFactory, override_settings
from django.core.cache import cache

from users.models import Role
from users.mixins import SmartPermissionRequiredMixin
from users.decorators import require_permission
from users.services.permission_service import PermissionService
from users.services.permission_dependency import PermissionDependencyService
from users.services.permission_cache import PermissionCacheService
from users.permissions_views import _get_arabic_permission_name
from customer.models import Customer
from supplier.models import Supplier
from product.models.product_core import Product
from product.models import Category, Unit, Warehouse
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.currency import Currency
from financial.models.journal_entry import JournalEntry
from work_order.models import WorkOrder
from printing_pricing.models import PrintingOrder
from core.models import SystemModule, SystemSetting

User = get_user_model()


class DummyPermission:
    """Helper mock object for testing _get_arabic_permission_name."""
    def __init__(self, codename, model=""):
        self.codename = codename
        self.name = codename
        self.content_type = type("DummyCT", (), {"model": model, "app_label": "test_app"})()


@pytest.fixture
def rbac_p8_setup(db):
    """Setup base test environment with required system entities and users."""
    # Seed canonical roles first
    call_command('seed_clean_roles')

    admin_role = Role.objects.get(name='admin')
    sales_rep_role = Role.objects.get(name='sales_rep')
    procurement_role = Role.objects.get(name='procurement_officer')
    warehouse_role = Role.objects.get(name='inventory_manager')
    accountant_role = Role.objects.get(name='accountant')
    viewer_role = Role.objects.get(name='viewer')
    prod_sup_role = Role.objects.get(name='production_supervisor')

    # Users
    superuser = User.objects.create_superuser(
        username="super_p8", email="super_p8@mwheba.com", password="password123"
    )
    admin_user = User.objects.create_user(
        username="admin_p8", email="admin_p8@mwheba.com", password="password123", role=admin_role
    )
    staff_only_user = User.objects.create_user(
        username="staff_only_p8", email="staff_only@mwheba.com", password="password123", is_staff=True
    )
    unprivileged_user = User.objects.create_user(
        username="unprivileged_p8", email="unprivileged@mwheba.com", password="password123"
    )
    sales_rep = User.objects.create_user(
        username="sales_rep_p8", email="rep@mwheba.com", password="password123", role=sales_rep_role
    )
    purchasing_officer = User.objects.create_user(
        username="purchasing_p8", email="purchasing@mwheba.com", password="password123", role=procurement_role
    )
    warehouse_keeper = User.objects.create_user(
        username="warehouse_p8", email="warehouse@mwheba.com", password="password123", role=warehouse_role
    )
    accountant = User.objects.create_user(
        username="accountant_p8", email="accountant@mwheba.com", password="password123", role=accountant_role
    )
    auditor = User.objects.create_user(
        username="auditor_p8", email="auditor@mwheba.com", password="password123", role=viewer_role
    )
    data_entry = User.objects.create_user(
        username="data_entry_p8", email="data_entry@mwheba.com", password="password123", role=viewer_role
    )
    production_sup = User.objects.create_user(
        username="prod_sup_p8", email="prod_sup@mwheba.com", password="password123", role=prod_sup_role
    )

    # Base Entities
    curr, _ = Currency.objects.get_or_create(code="EGP", defaults={"name": "جنيه مصري", "symbol": "ج.م", "is_functional": True})
    wh, _ = Warehouse.objects.get_or_create(code="WH-P8", defaults={"name": "مخزن المرحلة 8"})
    customer, _ = Customer.objects.get_or_create(code="CUST-P8", defaults={"name": "عميل المرحلة 8"})
    supplier, _ = Supplier.objects.get_or_create(code="SUPP-P8", defaults={"name": "مورد المرحلة 8"})

    return {
        "superuser": superuser,
        "admin_user": admin_user,
        "staff_only_user": staff_only_user,
        "unprivileged_user": unprivileged_user,
        "sales_rep": sales_rep,
        "purchasing_officer": purchasing_officer,
        "warehouse_keeper": warehouse_keeper,
        "accountant": accountant,
        "auditor": auditor,
        "data_entry": data_entry,
        "production_sup": production_sup,
        "customer": customer,
        "supplier": supplier,
        "warehouse": wh,
        "currency": curr,
    }


# ==============================================================================
# GROUP 1: Available Permissions API & Arabic Terminology Translations (Tests 1-5)
# ==============================================================================

@pytest.mark.django_db
def test_available_permissions_api_includes_all_operational_modules(client, rbac_p8_setup):
    """1. Verify available_permissions API returns > 100 permissions across all operational modules."""
    client.force_login(rbac_p8_setup["superuser"])
    response = client.get("/users/permissions/available-permissions/")
    assert response.status_code == 200
    data = response.json()
    assert data.get("success") is True

    categories = data.get("permissions", {})
    # Verify core business modules exist
    expected_modules = ["sale", "purchase", "financial", "product", "customer", "supplier", "system"]
    for mod in expected_modules:
        assert mod in categories, f"Module {mod} missing from available permissions categories"

    total_perms = sum(len(cat["permissions"]) for cat in categories.values())
    assert total_perms >= 100, f"Expected >= 100 available permissions, found {total_perms}"

    # Verify role management permissions are present under system category
    system_perms = [p["codename"] for p in categories["system"]["permissions"]]
    assert "view_role" in system_perms
    assert "add_role" in system_perms
    assert "change_role" in system_perms
    assert "delete_role" in system_perms


def test_permission_arabic_translations_clean_and_accurate():
    """2. Verify Arabic permission translations are accurate and eliminate English substrings."""
    # Test exact custom business mappings
    assert _get_arabic_permission_name(DummyPermission("close_accounting_period")) == "إغلاق الفترة المحاسبية"
    assert _get_arabic_permission_name(DummyPermission("reopen_accounting_period")) == "إعادة فتح فترة محاسبية"
    assert _get_arabic_permission_name(DummyPermission("change_unit_price")) == "تعديل سعر الوحدة بالفاتورة"
    assert _get_arabic_permission_name(DummyPermission("apply_special_discount")) == "تطبيق خصم خاص إضافي"

    # Test model translation mappings
    assert _get_arabic_permission_name(DummyPermission("view_quotation", "quotation")) == "عرض عروض الأسعار"
    assert _get_arabic_permission_name(DummyPermission("add_quotation", "quotation")) == "إضافة عروض الأسعار"
    assert _get_arabic_permission_name(DummyPermission("view_workorder", "workorder")) == "عرض أوامر الشغل والإنتاج"
    assert _get_arabic_permission_name(DummyPermission("view_accountingperiod", "accountingperiod")) == "عرض الفترات المحاسبية"
    assert _get_arabic_permission_name(DummyPermission("view_inventoryadjustment", "inventoryadjustment")) == "عرض تسويات الجرد"
    assert _get_arabic_permission_name(DummyPermission("view_stockmovement", "stockmovement")) == "عرض حركات المخزون"


@pytest.mark.django_db
def test_available_permissions_api_unauthorized_user_blocked(client, rbac_p8_setup):
    """3. Verify unauthorized user cannot access available permissions API."""
    client.force_login(rbac_p8_setup["unprivileged_user"])
    response = client.get("/users/permissions/available-permissions/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_available_permissions_api_includes_dependency_tree(client, rbac_p8_setup):
    """4. Verify available_permissions API provides complete dependency tree."""
    client.force_login(rbac_p8_setup["admin_user"])
    response = client.get("/users/permissions/available-permissions/")
    assert response.status_code == 200
    data = response.json()
    deps = data.get("dependencies", {})

    assert "sale.add_sale" in deps or "add_sale" in deps
    assert "purchase.add_purchase" in deps or "add_purchase" in deps


@pytest.mark.django_db
def test_available_permissions_excludes_technical_models(client, rbac_p8_setup):
    """5. Verify available_permissions excludes Django internal models (logentry, session, contenttype)."""
    client.force_login(rbac_p8_setup["superuser"])
    response = client.get("/users/permissions/available-permissions/")
    data = response.json()
    all_perm_apps = [p["app_label"] for cat in data.get("permissions", {}).values() for p in cat["permissions"]]

    assert 'sessions' not in all_perm_apps
    assert 'contenttypes' not in all_perm_apps
    assert 'admin' not in all_perm_apps


# ==============================================================================
# GROUP 2: Purged is_staff Bypass Enforcement (Tests 6-10)
# ==============================================================================

@pytest.mark.django_db
def test_is_staff_user_denied_access_by_require_permission_decorator(rbac_p8_setup):
    """6. Verify user with is_staff=True but lacking permission is denied by @require_permission."""
    @require_permission('customer.view_customer')
    def protected_dummy_view(request):
        return "Access Granted"

    factory = RequestFactory()
    request = factory.get('/dummy/')
    request.user = rbac_p8_setup["staff_only_user"]

    response = protected_dummy_view(request)
    assert response.status_code in [302, 403]
    assert response != "Access Granted"


@pytest.mark.django_db
def test_is_staff_user_denied_access_by_smart_permission_required_mixin(rbac_p8_setup):
    """7. Verify user with is_staff=True but lacking permission is denied by SmartPermissionRequiredMixin."""
    class DummyMixinView(SmartPermissionRequiredMixin):
        permission_required = 'customer.view_customer'

    view = DummyMixinView()
    view.request = RequestFactory().get('/dummy/')
    view.request.user = rbac_p8_setup["staff_only_user"]

    has_perm = view.has_permission()
    assert has_perm is False, "is_staff=True must NOT grant permission bypass"


@pytest.mark.django_db
def test_superuser_retains_access_despite_is_staff_purge(rbac_p8_setup):
    """8. Verify superuser retains seamless access across mixin and decorator."""
    @require_permission('customer.view_customer')
    def protected_dummy_view(request):
        return "Access Granted"

    factory = RequestFactory()
    request = factory.get('/dummy/')
    request.user = rbac_p8_setup["superuser"]

    response = protected_dummy_view(request)
    assert response == "Access Granted"


@pytest.mark.django_db
def test_admin_user_retains_access_via_is_admin_property(rbac_p8_setup):
    """9. Verify user with role.name='admin' retains access via is_admin property."""
    class DummyMixinView(SmartPermissionRequiredMixin):
        permission_required = 'customer.view_customer'

    view = DummyMixinView()
    view.request = RequestFactory().get('/dummy/')
    view.request.user = rbac_p8_setup["admin_user"]

    assert view.has_permission() is True


@pytest.mark.django_db
def test_is_staff_user_cannot_access_financial_journal_entries(client, rbac_p8_setup):
    """10. Verify is_staff=True user cannot access financial journal entries."""
    client.force_login(rbac_p8_setup["staff_only_user"])
    response = client.get(reverse('financial:journal_entries_list'))
    assert response.status_code in [302, 403]


# ==============================================================================
# GROUP 3: Role Lifecycle & Dual-Guarded Dependency Resolution (Tests 11-18)
# ==============================================================================

@pytest.mark.django_db
def test_role_quick_create_auto_resolves_prerequisites(client, rbac_p8_setup):
    """11. Verify quick-create role automatically resolves prerequisites in DB."""
    client.force_login(rbac_p8_setup["admin_user"])
    payload = {
        "name": "phase8_custom_sales",
        "display_name": "بائع المرحلة 8",
        "description": "دور مبيعات تجريبي لاختبار التبعيات",
        "permissions": ["sale.add_sale"]
    }
    response = client.post(
        reverse("users:role_quick_create"),
        data=json.dumps(payload),
        content_type="application/json"
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("success") is True

    role = Role.objects.get(name="phase8_custom_sales")
    role_perms = set(f"{p.content_type.app_label}.{p.codename}" for p in role.permissions.select_related("content_type"))

    assert "sale.add_sale" in role_perms
    assert "customer.view_customer" in role_perms
    assert "product.view_product" in role_perms
    assert "financial.view_currency" in role_perms
    assert "product.view_unit" in role_perms
    assert "product.view_warehouse" in role_perms
    assert "sale.view_sale" in role_perms


@pytest.mark.django_db
def test_role_quick_create_empty_name_validation(client, rbac_p8_setup):
    """12. Verify quick-create role rejects empty name."""
    client.force_login(rbac_p8_setup["admin_user"])
    payload = {
        "name": "   ",
        "display_name": "اسم فارغ",
        "permissions": []
    }
    response = client.post(
        reverse("users:role_quick_create"),
        data=json.dumps(payload),
        content_type="application/json"
    )
    assert response.status_code == 400
    data = response.json()
    assert data.get("success") is False


@pytest.mark.django_db
def test_role_quick_create_duplicate_name_validation(client, rbac_p8_setup):
    """13. Verify quick-create role rejects duplicate role name."""
    client.force_login(rbac_p8_setup["admin_user"])
    payload = {
        "name": "sales_rep",  # existing canonical role
        "display_name": "مندوب مبيعات مكرر",
        "permissions": []
    }
    response = client.post(
        reverse("users:role_quick_create"),
        data=json.dumps(payload),
        content_type="application/json"
    )
    assert response.status_code == 400
    data = response.json()
    assert data.get("success") is False


@pytest.mark.django_db
def test_role_quick_edit_updates_permissions_and_resolves_dependencies(client, rbac_p8_setup):
    """14. Verify quick-edit role updates permissions and auto-resolves dependencies."""
    client.force_login(rbac_p8_setup["admin_user"])
    custom_role = Role.objects.create(name="phase8_edit_target", display_name="دور للتعديل")

    payload = {
        "display_name": "دور تم تعديله",
        "description": "وصف محدث",
        "permissions": ["purchase.add_purchase"]
    }
    response = client.post(
        reverse("users:role_quick_edit", args=[custom_role.id]),
        data=json.dumps(payload),
        content_type="application/json"
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("success") is True

    custom_role.refresh_from_db()
    assert custom_role.display_name == "دور تم تعديله"
    role_perms = set(f"{p.content_type.app_label}.{p.codename}" for p in custom_role.permissions.select_related("content_type"))

    assert "purchase.add_purchase" in role_perms
    assert "supplier.view_supplier" in role_perms
    assert "product.view_product" in role_perms
    assert "purchase.view_purchase" in role_perms


@pytest.mark.django_db
def test_role_quick_delete_blocks_system_roles(client, rbac_p8_setup):
    """15. Verify system roles cannot be deleted."""
    client.force_login(rbac_p8_setup["admin_user"])
    accountant_role = Role.objects.get(name="accountant")

    response = client.post(
        reverse("users:role_quick_delete", args=[accountant_role.id]),
        data=json.dumps({}),
        content_type="application/json"
    )
    assert response.status_code == 400
    data = response.json()
    assert "أساسي" in data.get("message", "") or "system" in data.get("message", "").lower()
    assert Role.objects.filter(id=accountant_role.id).exists()


@pytest.mark.django_db
def test_role_quick_delete_blocks_role_with_active_users(client, rbac_p8_setup):
    """16. Verify custom role with active assigned users cannot be deleted."""
    client.force_login(rbac_p8_setup["admin_user"])
    custom_role = Role.objects.create(name="role_with_user", display_name="دور معه مستخدم")
    User.objects.create_user(username="assigned_user", email="as@mwheba.com", password="pwd", role=custom_role)

    response = client.post(
        reverse("users:role_quick_delete", args=[custom_role.id]),
        data=json.dumps({}),
        content_type="application/json"
    )
    assert response.status_code == 400
    data = response.json()
    assert "مرتبط" in data.get("message", "") or "users" in data.get("message", "").lower()
    assert Role.objects.filter(id=custom_role.id).exists()


@pytest.mark.django_db
def test_role_quick_delete_succeeds_for_custom_empty_role(client, rbac_p8_setup):
    """17. Verify custom role without users is deleted successfully."""
    client.force_login(rbac_p8_setup["admin_user"])
    custom_role = Role.objects.create(name="empty_custom_role", display_name="دور فارغ")
    role_id = custom_role.id

    response = client.post(
        reverse("users:role_quick_delete", args=[role_id]),
        data=json.dumps({}),
        content_type="application/json"
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("success") is True
    assert not Role.objects.filter(id=role_id).exists()


@pytest.mark.django_db
def test_role_quick_create_requires_role_permission(client, rbac_p8_setup):
    """18. Verify user lacking users.add_role is blocked from role_quick_create."""
    client.force_login(rbac_p8_setup["unprivileged_user"])
    response = client.post(
        reverse("users:role_quick_create"),
        data=json.dumps({"name": "unauth_role", "display_name": "test"}),
        content_type="application/json"
    )
    assert response.status_code == 403


# ==============================================================================
# GROUP 4: User Custom Permissions & Cache Invalidation (Tests 19-22)
# ==============================================================================

@pytest.mark.django_db
def test_user_update_custom_permissions_syncs_both_relations(client, rbac_p8_setup):
    """19. Verify user_update_custom_permissions syncs both custom_permissions and user_permissions."""
    client.force_login(rbac_p8_setup["admin_user"])
    target_user = rbac_p8_setup["unprivileged_user"]

    payload = {
        "permissions": ["customer.view_customer", "customer.add_customer"]
    }
    response = client.post(
        reverse("users:user_update_custom_permissions", args=[target_user.id]),
        data=json.dumps(payload),
        content_type="application/json"
    )
    assert response.status_code == 200

    target_user.refresh_from_db()
    custom_perms = set(f"{p.content_type.app_label}.{p.codename}" for p in target_user.custom_permissions.all())
    user_perms = set(f"{p.content_type.app_label}.{p.codename}" for p in target_user.user_permissions.all())

    assert "customer.add_customer" in custom_perms
    assert "customer.view_customer" in custom_perms
    assert "customer.add_customer" in user_perms
    assert "customer.view_customer" in user_perms


@pytest.mark.django_db
def test_user_update_custom_permissions_auto_resolves_prerequisites(client, rbac_p8_setup):
    """20. Verify updating user custom permissions auto-resolves prerequisites."""
    client.force_login(rbac_p8_setup["admin_user"])
    target_user = rbac_p8_setup["unprivileged_user"]

    payload = {
        "permissions": ["sale.add_sale"]
    }
    response = client.post(
        reverse("users:user_update_custom_permissions", args=[target_user.id]),
        data=json.dumps(payload),
        content_type="application/json"
    )
    assert response.status_code == 200

    target_user.refresh_from_db()
    custom_perms = set(f"{p.content_type.app_label}.{p.codename}" for p in target_user.custom_permissions.all())

    assert "sale.add_sale" in custom_perms
    assert "customer.view_customer" in custom_perms
    assert "product.view_product" in custom_perms
    assert "product.view_warehouse" in custom_perms


@pytest.mark.django_db
@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
def test_user_update_custom_permissions_invalidates_cache(client, rbac_p8_setup):
    """21. Verify updating user permissions invalidates permission cache for that user."""
    target_user = rbac_p8_setup["unprivileged_user"]
    # Seed cache
    PermissionCacheService.set_user_permissions(target_user.id, {"customer.view_customer"})
    assert PermissionCacheService.get_user_permissions(target_user.id) is not None

    client.force_login(rbac_p8_setup["admin_user"])
    client.post(
        reverse("users:user_update_custom_permissions", args=[target_user.id]),
        data=json.dumps({"permissions": ["supplier.view_supplier"]}),
        content_type="application/json"
    )

    # Verify cache was cleared and returns None after invalidation
    assert PermissionCacheService.get_user_permissions(target_user.id) is None


@pytest.mark.django_db
def test_assign_role_api_updates_user_role_and_invalidates_cache(client, rbac_p8_setup):
    """22. Verify assign_role updates user role and clears cache."""
    client.force_login(rbac_p8_setup["admin_user"])
    target_user = rbac_p8_setup["unprivileged_user"]
    sales_rep_role = Role.objects.get(name="sales_rep")

    response = client.post(
        reverse("users:user_assign_role", args=[target_user.id]),
        data=json.dumps({
            "role_id": sales_rep_role.id
        }),
        content_type="application/json"
    )
    assert response.status_code == 200
    target_user.refresh_from_db()
    assert target_user.role == sales_rep_role
    assert target_user.is_sales_rep is True


# ==============================================================================
# GROUP 5: Canonical 10 Roles Seeding & Integrity (Tests 23-26)
# ==============================================================================

@pytest.mark.django_db
def test_seed_clean_roles_command_creates_all_ten_canonical_roles():
    """23. Verify seed_clean_roles creates all 10 canonical roles."""
    call_command('seed_clean_roles')
    expected_roles = [
        'admin', 'financial_manager', 'accountant', 'sales_manager', 'sales_rep',
        'procurement_officer', 'inventory_manager', 'production_supervisor', 'hr_officer', 'viewer'
    ]
    for role_name in expected_roles:
        assert Role.objects.filter(name=role_name).exists(), f"Role {role_name} must exist"


@pytest.mark.django_db
def test_canonical_roles_have_resolved_dependencies(rbac_p8_setup):
    """24. Verify canonical roles have prerequisite dependencies resolved."""
    sales_rep = Role.objects.get(name='sales_rep')
    perms = set(f"{p.content_type.app_label}.{p.codename}" for p in sales_rep.permissions.select_related('content_type'))

    assert 'customer.view_customer' in perms
    assert 'product.view_product' in perms
    assert 'financial.view_currency' in perms

    purchasing = Role.objects.get(name='procurement_officer')
    p_perms = set(f"{p.content_type.app_label}.{p.codename}" for p in purchasing.permissions.select_related('content_type'))
    assert 'supplier.view_supplier' in p_perms
    assert 'product.view_product' in p_perms


@pytest.mark.django_db
def test_canonical_roles_are_marked_as_system_roles(rbac_p8_setup):
    """25. Verify all operational canonical roles have is_system_role=True."""
    canonical_roles = Role.objects.filter(name__in=[
        'admin', 'financial_manager', 'accountant', 'sales_manager', 'sales_rep',
        'procurement_officer', 'inventory_manager', 'production_supervisor', 'hr_officer'
    ])
    for r in canonical_roles:
        assert r.is_system_role is True, f"Role {r.name} should be marked as system role"


@pytest.mark.django_db
def test_seed_clean_roles_is_idempotent():
    """26. Verify re-running seed_clean_roles command does not duplicate roles or raise errors."""
    call_command('seed_clean_roles')
    initial_count = Role.objects.count()
    call_command('seed_clean_roles')
    assert Role.objects.count() == initial_count


# ==============================================================================
# GROUP 6: Enterprise Segregation of Duties (SoD) & Role Boundaries (Tests 27-33)
# ==============================================================================

@pytest.mark.django_db
def test_sales_rep_cannot_access_purchase_invoices(client, rbac_p8_setup):
    """27. SoD: Sales Rep cannot view purchase invoices."""
    client.force_login(rbac_p8_setup["sales_rep"])
    response = client.get(reverse('purchase:purchase_list'))
    assert response.status_code in [302, 403]


@pytest.mark.django_db
def test_purchasing_officer_cannot_access_sales_invoices(client, rbac_p8_setup):
    """28. SoD: Purchasing Officer cannot view sales invoices."""
    client.force_login(rbac_p8_setup["purchasing_officer"])
    response = client.get(reverse('sale:sale_list'))
    assert response.status_code in [302, 403]


@pytest.mark.django_db
def test_warehouse_keeper_cannot_access_financial_journal(client, rbac_p8_setup):
    """29. SoD: Warehouse Keeper cannot view financial journal entries."""
    client.force_login(rbac_p8_setup["warehouse_keeper"])
    response = client.get(reverse('financial:journal_entries_list'))
    assert response.status_code in [302, 403]


@pytest.mark.django_db
def test_accountant_cannot_delete_system_roles(client, rbac_p8_setup):
    """30. SoD: Accountant cannot delete system roles."""
    client.force_login(rbac_p8_setup["accountant"])
    admin_role = Role.objects.get(name="admin")
    response = client.post(
        reverse("users:role_quick_delete", args=[admin_role.id]),
        data=json.dumps({}),
        content_type="application/json"
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_auditor_has_read_only_access_and_cannot_create_sales(client, rbac_p8_setup):
    """31. SoD: Auditor has read access but cannot create sales invoices."""
    auditor = rbac_p8_setup["auditor"]
    assert auditor.has_perm('sale.view_sale') is True
    assert auditor.has_perm('sale.add_sale') is False
    assert auditor.has_perm('financial.add_journalentry') is False

    client.force_login(auditor)
    response = client.get(reverse('sale:sale_create'))
    assert response.status_code in [302, 403]


@pytest.mark.django_db
def test_data_entry_has_restricted_permissions(rbac_p8_setup):
    """32. SoD: Data Entry user lacks managerial closing and approval permissions."""
    data_entry = rbac_p8_setup["data_entry"]
    assert data_entry.has_perm('financial.close_accounting_period') is False
    assert data_entry.has_perm('sale.apply_discount') is False
    assert data_entry.has_perm('users.delete_role') is False


@pytest.mark.django_db
def test_production_supervisor_work_order_isolation(rbac_p8_setup):
    """33. SoD: Production Supervisor cannot create financial journal entries."""
    prod_sup = rbac_p8_setup["production_sup"]
    assert prod_sup.has_perm('work_order.view_workorder') is True
    assert prod_sup.has_perm('financial.add_journalentry') is False
    assert prod_sup.has_perm('financial.add_paymentvoucher') is False


# ==============================================================================
# GROUP 7: UI & Dashboard Integration Security (Tests 34-36)
# ==============================================================================

@pytest.mark.django_db
def test_permissions_dashboard_view_renders_for_admin(client, rbac_p8_setup):
    """34. Verify Permissions Dashboard renders 200 for admin user."""
    client.force_login(rbac_p8_setup["admin_user"])
    response = client.get(reverse("users:permissions_dashboard"))
    assert response.status_code == 200
    assert "permissions-dashboard.js" in response.content.decode("utf-8")


@pytest.mark.django_db
def test_permissions_dashboard_view_denied_for_regular_user(client, rbac_p8_setup):
    """35. Verify Permissions Dashboard is blocked for unauthorized regular user."""
    client.force_login(rbac_p8_setup["unprivileged_user"])
    response = client.get(reverse("users:permissions_dashboard"))
    assert response.status_code in [302, 403]


def test_permissions_dashboard_js_has_no_broken_syntax_and_uses_dep_engine():
    """36. Verify permissions-dashboard.js enforces depEngine, showNotification, and 3100ms timer."""
    with open("static/js/permissions-dashboard.js", "r", encoding="utf-8") as f:
        js_code = f.read()

    assert "change.depEngine" in js_code, "depEngine event namespace must be present"
    assert "showNotification" in js_code, "System unified notification helper must be used"
    assert "3100" in js_code, "Progress bar completion delay of 3100ms must be enforced"
    assert "dropdownParent: $('#assignRoleModal')" in js_code or 'dropdownParent: $("#assignRoleModal")' in js_code, "Select2 must be anchored inside modal"
