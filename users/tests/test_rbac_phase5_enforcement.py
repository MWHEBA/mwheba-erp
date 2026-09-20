# -*- coding: utf-8 -*-
"""
Jules/Antigravity Sovereign RBAC Overhaul - Phase 5 Enforcement Verification Suite
This module validates full zero-trust module enforcement across product, customer,
supplier, financial, printing_pricing, work_order, and users modules.
"""

import pytest
import json
from decimal import Decimal
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, RequestFactory
from django.http import JsonResponse

from users.mixins import SmartPermissionRequiredMixin
from users.decorators import require_permission
from users.services.permission_dependency import PermissionDependencyService
from customer.models import Customer
from supplier.models import Supplier
from product.models.product_core import Product
from product.models import Category, Unit
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.currency import Currency
from financial.models.fiscal_year import FiscalYear
from financial.models.journal_entry import JournalEntry, JournalEntryLine
from financial.models.opening_balance import OpeningBalanceBatch, OpeningBalanceLine
from work_order.models import WorkOrder
from printing_pricing.models import PrintingOrder
from core.models import SystemModule, SystemSetting

User = get_user_model()


@pytest.fixture
def rbac_users(db):
    """Setup testing users with fine-grained roles and permissions."""
    admin = User.objects.create_superuser(username="admin_p5", email="admin_p5@mwheba.com", password="password123")
    unauth_user = User.objects.create_user(username="unauth_p5", email="unauth_p5@mwheba.com", password="password123")
    staff_user = User.objects.create_user(username="staff_p5", email="staff_p5@mwheba.com", password="password123", is_staff=True)
    custom_user = User.objects.create_user(username="custom_p5", email="custom_p5@mwheba.com", password="password123")

    return {
        "admin": admin,
        "unauth": unauth_user,
        "staff": staff_user,
        "custom": custom_user,
    }


@pytest.fixture
def rbac_entities(db, rbac_users):
    """Setup base entities across modules."""
    admin = rbac_users["admin"]

    # System modules
    SystemModule.objects.update_or_create(code="printing_pricing", defaults={"is_enabled": True, "name": "التسعير"})
    SystemModule.objects.update_or_create(code="work_orders", defaults={"is_enabled": True, "name": "أوامر العمل"})
    SystemSetting.set_setting("enable_work_orders", "true")

    # Currency
    curr, _ = Currency.objects.get_or_create(code="EGP", defaults={"name": "Egyptian Pound", "symbol": "ج.م", "is_functional": True})

    # Account Type & Accounts
    acc_type, _ = AccountType.objects.get_or_create(code="current_asset", defaults={"name": "أصول متداولة", "category": "asset"})
    parent_acc, _ = ChartOfAccounts.objects.get_or_create(code="11000", defaults={"name": "الأصول المتداولة", "account_type": acc_type})
    acc, _ = ChartOfAccounts.objects.get_or_create(code="11010", defaults={"name": "الخزينة الرئيسية", "account_type": acc_type, "parent": parent_acc, "is_leaf": True, "currency": curr, "is_cash_account": True})

    # Customer & Supplier
    cust = Customer.objects.create(name="عميل اختبار المرحلة 5", phone="01099999999", financial_account=acc)
    supp = Supplier.objects.create(name="مورد اختبار المرحلة 5", phone="01188888888", default_currency=curr, financial_account=acc)

    # Product
    cat, _ = Category.objects.get_or_create(name="خامات")
    unit, _ = Unit.objects.get_or_create(name="قطعة")
    prod = Product.objects.create(name="ورق كوشيه 300 جرام", sku="COUCH-300", category=cat, unit=unit, selling_price=Decimal("100.00"), cost_price=Decimal("70.00"), created_by=admin)

    # Fiscal Year
    fy, _ = FiscalYear.objects.get_or_create(
        year_code="2026",
        defaults={
            "name": "السنة المالية 2026",
            "start_date": timezone.now().date(),
            "end_date": timezone.now().date() + timezone.timedelta(days=365),
            "status": "open",
        }
    )

    # Printing Order
    order = PrintingOrder.objects.create(
        customer=cust,
        title="طلب تسعير تجريبي 5",
        quantity=1000,
        order_type="book",
        created_by=admin
    )

    return {
        "currency": curr,
        "account": acc,
        "customer": cust,
        "supplier": supp,
        "product": prod,
        "fiscal_year": fy,
        "order": order,
    }


def grant_perms(user, codenames):
    """Utility to grant list of permission codenames to a user."""
    for codename in codenames:
        perm = Permission.objects.filter(codename=codename).first()
        if perm:
            user.user_permissions.add(perm)
    # Clear cached permissions
    if hasattr(user, '_perm_cache'):
        delattr(user, '_perm_cache')


# =====================================================================
# 1. SMART PERMISSION REQUIRED MIXIN & DECORATOR TESTS
# =====================================================================

@pytest.mark.django_db
def test_smart_permission_required_mixin_ajax_403(rbac_users):
    """Test SmartPermissionRequiredMixin returns JSON 403 on AJAX request."""
    from django.views.generic import View

    class DummyView(SmartPermissionRequiredMixin, View):
        permission_required = 'customer.view_customer'

        def get(self, request):
            return JsonResponse({'success': True})

    factory = RequestFactory()
    req = factory.get('/dummy/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    req.user = rbac_users["unauth"]

    view = DummyView.as_view()
    resp = view(req)
    assert resp.status_code == 403
    data = json.loads(resp.content)
    assert data["success"] is False
    assert data["error"] == "permission_denied"


@pytest.mark.django_db
def test_require_permission_decorator_ajax_403(rbac_users):
    """Test require_permission decorator returns JSON 403 for precheck / AJAX."""
    @require_permission('product.delete_product')
    def dummy_func(request):
        return JsonResponse({'success': True})

    factory = RequestFactory()
    req = factory.get('/dummy/?precheck=1')
    req.user = rbac_users["unauth"]

    resp = dummy_func(req)
    assert resp.status_code == 403
    data = json.loads(resp.content)
    assert data["success"] is False
    assert data["error"] == "permission_denied"


# =====================================================================
# 2. SIDEBAR ZERO-TRUST RBAC VISIBILITY
# =====================================================================

@pytest.mark.django_db
def test_sidebar_strict_rbac_visibility(client, rbac_users):
    """Ensure unauthorized user sees no financial or admin links in sidebar."""
    unauth = rbac_users["unauth"]
    client.force_login(unauth)

    resp = client.get(reverse('core:dashboard'))
    content = resp.content.decode('utf-8')

    # Financial modules must not be visible without permissions
    assert 'الخزينة والمالية' not in content or 'can_access_enhanced_financial' not in content
    assert reverse('financial:chart_of_accounts_list') not in content


# =====================================================================
# 3. PRINTING PRICING ORDERS SECURITY
# =====================================================================

@pytest.mark.django_db
def test_printing_pricing_order_views_enforcement(client, rbac_users, rbac_entities):
    """Ensure OrderListView is guarded by printing_pricing.view_printingorder."""
    client.force_login(rbac_users["unauth"])
    resp = client.get(reverse('printing_pricing:order_list'))
    # Unauth should be rejected (redirect or 403)
    assert resp.status_code in [302, 403]

    # Grant permission
    grant_perms(rbac_users["unauth"], ['view_printingorder'])
    resp = client.get(reverse('printing_pricing:order_list'))
    assert resp.status_code == 200


# =====================================================================
# 4. WORK ORDERS SECURITY
# =====================================================================

@pytest.mark.django_db
def test_work_order_views_enforcement(client, rbac_users, rbac_entities):
    """Ensure work_order views require work_order.view_workorder and add_workorder."""
    client.force_login(rbac_users["unauth"])
    resp = client.get(reverse('work_order:work_order_list'))
    assert resp.status_code in [302, 403]

    grant_perms(rbac_users["unauth"], ['view_workorder'])
    resp = client.get(reverse('work_order:work_order_list'))
    assert resp.status_code == 200


# =====================================================================
# 5. PRODUCT & MULTI-TIER BULK EDIT SECURITY
# =====================================================================

@pytest.mark.django_db
def test_product_views_enforcement(client, rbac_users, rbac_entities):
    """Ensure product_list and product_delete enforce RBAC and AJAX 403."""
    prod = rbac_entities["product"]
    client.force_login(rbac_users["unauth"])

    # List view
    resp = client.get(reverse('product:product_list'))
    assert resp.status_code in [302, 403]

    # Delete view AJAX precheck
    resp = client.get(reverse('product:product_delete', args=[prod.pk]), {'precheck': '1'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert resp.status_code == 403
    data = resp.json()
    assert data["success"] is False


@pytest.mark.django_db
def test_product_bulk_edit_multi_tier_check(client, rbac_users, rbac_entities):
    """Ensure product_bulk_edit strictly requires product.change_product, and checks sale/purchase perms for prices."""
    prod = rbac_entities["product"]
    user = rbac_users["custom"]
    client.force_login(user)

    url = reverse('product:product_bulk_edit')
    payload = json.dumps({'products': [{'id': prod.id, 'selling_price': 150.00}]})

    # 1. No permissions at all -> 403
    resp = client.post(url, payload, content_type='application/json', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert resp.status_code == 403

    # 2. Grant only change_product, attempt to update selling_price without change_unit_price -> 403
    grant_perms(user, ['change_product'])
    resp = client.post(url, payload, content_type='application/json', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert resp.status_code == 403

    # 3. Grant change_unit_price -> 200
    grant_perms(user, ['change_unit_price'])
    resp = client.post(url, payload, content_type='application/json', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert resp.status_code == 200
    prod.refresh_from_db()
    assert prod.selling_price == Decimal('150.00')


# =====================================================================
# 6. CUSTOMER VIEWS & PREPAID ENFORCEMENT
# =====================================================================

@pytest.mark.django_db
def test_customer_views_enforcement(client, rbac_users, rbac_entities):
    """Ensure customer views require customer permissions."""
    cust = rbac_entities["customer"]
    client.force_login(rbac_users["unauth"])

    resp = client.get(reverse('customer:customer_list'))
    assert resp.status_code in [302, 403]

    resp = client.get(reverse('customer:customer_delete', args=[cust.pk]), {'precheck': '1'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert resp.status_code == 403


@pytest.mark.django_db
def test_customer_advance_and_prepaid_enforcement(client, rbac_users, rbac_entities):
    """Ensure add_customer_advance requires receipt voucher permission."""
    cust = rbac_entities["customer"]
    client.force_login(rbac_users["unauth"])

    url = reverse('customer:add_customer_advance', args=[cust.pk])
    resp = client.post(url, {'amount': '500.00'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert resp.status_code == 403


@pytest.mark.django_db
def test_customer_account_change_enforcement(client, rbac_users, rbac_entities):
    """Ensure customer account change requires financial.change_chartofaccounts."""
    cust = rbac_entities["customer"]
    client.force_login(rbac_users["unauth"])

    url = reverse('customer:customer_change_account', args=[cust.pk])
    resp = client.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert resp.status_code == 403


# =====================================================================
# 7. SUPPLIER VIEWS & ACTIONS ENFORCEMENT
# =====================================================================

@pytest.mark.django_db
def test_supplier_views_enforcement(client, rbac_users, rbac_entities):
    """Ensure supplier views require supplier permissions."""
    supp = rbac_entities["supplier"]
    client.force_login(rbac_users["unauth"])

    resp = client.get(reverse('supplier:supplier_list'))
    assert resp.status_code in [302, 403]

    resp = client.get(reverse('supplier:supplier_delete', args=[supp.pk]), {'precheck': '1'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert resp.status_code == 403


@pytest.mark.django_db
def test_supplier_advance_and_prepaid_enforcement(client, rbac_users, rbac_entities):
    """Ensure add_supplier_advance requires payment voucher permission."""
    supp = rbac_entities["supplier"]
    client.force_login(rbac_users["unauth"])

    url = reverse('supplier:add_supplier_advance', args=[supp.pk])
    resp = client.post(url, {'amount': '500.00'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert resp.status_code == 403


@pytest.mark.django_db
def test_supplier_account_change_enforcement(client, rbac_users, rbac_entities):
    """Ensure supplier account creation requires change_chartofaccounts."""
    supp = rbac_entities["supplier"]
    client.force_login(rbac_users["unauth"])

    url = reverse('supplier:supplier_create_account', args=[supp.pk])
    resp = client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert resp.status_code == 403


# =====================================================================
# 8. FINANCIAL & GENERAL LEDGER ENFORCEMENT
# =====================================================================

@pytest.mark.django_db
def test_chart_of_accounts_list_enforcement(client, rbac_users):
    """Ensure chart_of_accounts_list requires financial.view_chartofaccounts."""
    client.force_login(rbac_users["unauth"])
    resp = client.get(reverse('financial:chart_of_accounts_list'))
    assert resp.status_code in [302, 403]

    grant_perms(rbac_users["unauth"], ['view_chartofaccounts'])
    resp = client.get(reverse('financial:chart_of_accounts_list'))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_journal_entries_views_enforcement(client, rbac_users, rbac_entities):
    """Ensure journal entries list, create, and detail enforce permissions."""
    client.force_login(rbac_users["unauth"])

    # List
    resp = client.get(reverse('financial:journal_entries_list'))
    assert resp.status_code in [302, 403]

    # Create
    resp = client.get(reverse('financial:journal_entries_create'))
    assert resp.status_code in [302, 403]

    # Grant view perm
    grant_perms(rbac_users["unauth"], ['view_journalentry'])
    resp = client.get(reverse('financial:journal_entries_list'))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_opening_balance_views_enforcement(client, rbac_users):
    """Ensure opening balance list and wizard enforce view and add journal entry permissions."""
    client.force_login(rbac_users["unauth"])

    resp = client.get(reverse('financial:opening_balance_list'))
    assert resp.status_code in [302, 403]

    grant_perms(rbac_users["unauth"], ['view_journalentry'])
    resp = client.get(reverse('financial:opening_balance_list'))
    assert resp.status_code == 200


# =====================================================================
# 9. INTERACTIVE DELETE MODAL & BUTTON SYNCHRONIZATION
# =====================================================================

@pytest.mark.django_db
def test_interactive_delete_archive_modal_403_resilience(client, rbac_users, rbac_entities):
    """Test that delete precheck returns proper 403 JSON containing error message for UI modal."""
    cust = rbac_entities["customer"]
    client.force_login(rbac_users["unauth"])

    resp = client.get(reverse('customer:customer_delete', args=[cust.pk]), {'precheck': '1'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert resp.status_code == 403
    data = resp.json()
    assert 'message' in data or 'error' in data


@pytest.mark.django_db
def test_header_and_action_buttons_rbac_sync(client, rbac_users):
    """Verify that action_buttons and header_buttons in supplier_list are hidden for users without add/delete perms."""
    user = rbac_users["unauth"]
    grant_perms(user, ['view_supplier'])
    client.force_login(user)

    resp = client.get(reverse('supplier:supplier_list'))
    assert resp.status_code == 200
    header_buttons = resp.context.get('header_buttons', [])
    action_buttons = resp.context.get('action_buttons', [])

    # 'إضافة مورد' button must not be present
    assert not any(btn.get('text') == 'إضافة مورد' for btn in header_buttons)
    # Delete action must not be present
    assert not any(btn.get('class') == 'action-delete text-danger' for btn in action_buttons)


# =====================================================================
# 10. DEPENDENCY MAP & SUPERUSER FULL ACCESS
# =====================================================================

def test_permission_dependency_map_completeness():
    """Verify PermissionDependencyService provides valid dependency mappings."""
    dep_map = PermissionDependencyService.DEPENDENCY_MAP
    assert isinstance(dep_map, dict)
    assert 'change_customer' in dep_map
    assert 'view_customer' in dep_map['change_customer']
    assert 'delete_supplier' in dep_map
    assert 'view_supplier' in dep_map['delete_supplier']


@pytest.mark.django_db
def test_superuser_full_bypass(client, rbac_users, rbac_entities):
    """Verify superuser has seamless bypass on all views without permission errors."""
    client.force_login(rbac_users["admin"])

    assert client.get(reverse('customer:customer_list')).status_code == 200
    assert client.get(reverse('supplier:supplier_list')).status_code == 200
    assert client.get(reverse('product:product_list')).status_code == 200
    assert client.get(reverse('financial:chart_of_accounts_list')).status_code == 200
    assert client.get(reverse('financial:journal_entries_list')).status_code == 200


@pytest.mark.django_db
def test_smart_permission_required_mixin_unauth_ajax(rbac_users):
    """Test SmartPermissionRequiredMixin returns 401 JSON for unauthenticated AJAX requests."""
    from django.views.generic import View
    from django.contrib.auth.models import AnonymousUser

    class DummyView(SmartPermissionRequiredMixin, View):
        permission_required = 'customer.view_customer'

        def get(self, request):
            return JsonResponse({'success': True})

    factory = RequestFactory()
    req = factory.get('/dummy/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    req.user = AnonymousUser()

    view = DummyView.as_view()
    resp = view(req)
    assert resp.status_code == 401
    data = json.loads(resp.content)
    assert data["success"] is False
    assert data["error"] == "unauthenticated"


@pytest.mark.django_db
def test_sidebar_printing_and_hr_strict_guards(client, rbac_users):
    """Ensure unauthorized user does not see printing_pricing or hr menu links."""
    client.force_login(rbac_users["unauth"])
    resp = client.get(reverse('core:dashboard'))
    content = resp.content.decode('utf-8')

    assert reverse('printing_pricing:order_list') not in content
    assert reverse('hr:employee_list') not in content


@pytest.mark.django_db
def test_pricing_apis_zero_trust_guards(client, rbac_users, rbac_entities):
    """Ensure sensitive pricing APIs strictly reject unauthorized users with 403."""
    client.force_login(rbac_users["unauth"])
    
    # 1. Bulk price update
    resp_bulk = client.post(
        reverse('printing_pricing:api_bulk_price_update'),
        data=json.dumps({"updates": []}),
        content_type="application/json"
    )
    assert resp_bulk.status_code == 403
    assert json.loads(resp_bulk.content)["success"] is False

    # 2. Approved orders
    resp_approved = client.get(reverse('printing_pricing:api_approved_orders'))
    assert resp_approved.status_code == 403
    assert json.loads(resp_approved.content)["success"] is False

    # 3. Generate vendor POs
    order = rbac_entities["order"]
    resp_po = client.post(
        reverse('printing_pricing:api_generate_vendor_pos', kwargs={'order_id': order.pk}),
        data=json.dumps({}),
        content_type="application/json"
    )
    assert resp_po.status_code == 403
    assert json.loads(resp_po.content)["success"] is False


@pytest.mark.django_db
def test_order_detail_view_hides_buttons_for_view_only_user(client, rbac_users, rbac_entities):
    """Ensure a user with only view_printingorder cannot see edit/copy/approve buttons."""
    user = rbac_users["custom"]
    perm = Permission.objects.get(codename="view_printingorder")
    user.user_permissions.add(perm)
    client.force_login(user)

    order = rbac_entities["order"]
    order.created_by = user
    order.save()
    resp = client.get(reverse('printing_pricing:order_detail', kwargs={'pk': order.pk}))
    assert resp.status_code == 200
    
    # Verify header_buttons in context do NOT include edit or duplicate
    header_buttons = resp.context.get('header_buttons', [])
    button_urls = [b.get('url') for b in header_buttons if b.get('url')]
    button_ids = [b.get('id') for b in header_buttons if b.get('id')]

    assert reverse('printing_pricing:order_update', kwargs={'pk': order.pk}) not in button_urls
    assert reverse('printing_pricing:duplicate_order', kwargs={'pk': order.pk}) not in button_urls
    assert 'btn_approve_order' not in button_ids

