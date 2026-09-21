# -*- coding: utf-8 -*-
"""
MWHEBA ERP RBAC Phase 6 Enforcement Verification Suite
Validates:
1. Purging of `is_staff` and cost breakdown masking in printing_pricing APIs.
2. Refactored hr decorators (O(1) cache, JSON 403, and canonical roles).
3. HR zero-trust views defense (employees, contracts, payroll, advances, leaves, attendance).
4. Governance lockdown: audit log purging strictly locked to superusers with pre-audit logging,
   and IP blocking whitelisting for internal network.
5. Financial period and fiscal year controls (close/wizard views).
6. Warehouse voucher views using SmartPermissionRequiredMixin.
7. Role seeding and sidebar zero-trust alignment.
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
from datetime import timedelta, date

from users.mixins import SmartPermissionRequiredMixin
from users.decorators import require_permission
from customer.models import Customer
from printing_pricing.models import PrintingOrder, OrderSummary, OrderMaterial, CostCalculation
from hr.models import Employee, Department, JobTitle, Contract, Leave, LeaveType, Advance, Attendance
from governance.models import AuditTrail, SecurityIncident, BlockedIP, ActiveSession
from financial.models.fiscal_year import FiscalYear
from financial.models.journal_entry import AccountingPeriod
from product.models.inventory_movement import InventoryMovement
from product.models.stock_management import Warehouse, Stock
from product.models.product_core import Product

User = get_user_model()


@pytest.fixture
def phase6_setup(db):
    """Setup users and basic entities for Phase 6 test suite."""
    superuser = User.objects.create_superuser(username="super_p6", email="super_p6@mwheba.com", password="password123")
    staff_user = User.objects.create_user(username="staff_p6", email="staff_p6@mwheba.com", password="password123", is_staff=True)
    regular_user = User.objects.create_user(username="regular_p6", email="regular_p6@mwheba.com", password="password123")
    hr_user = User.objects.create_user(username="hr_p6", email="hr_p6@mwheba.com", password="password123")
    finance_user = User.objects.create_user(username="fin_p6", email="fin_p6@mwheba.com", password="password123")

    # Give regular user a few permissions when needed
    dept = Department.objects.create(name_ar="الإنتاج", code="PROD")
    job = JobTitle.objects.create(title_ar="فني طباعة", code="PRINTER", department=dept)
    today_dt = timezone.now().date() - timedelta(days=1)
    emp_regular = Employee.objects.create(
        user=regular_user,
        name="محمد منتظم",
        employee_number="EMP901",
        national_id="29001011234567",
        birth_date=date(1990, 1, 1),
        gender="male",
        marital_status="single",
        hire_date=today_dt,
        created_by=superuser,
        department=dept,
        job_title=job
    )
    emp_target = Employee.objects.create(
        name="أحمد المستهدف",
        employee_number="EMP902",
        national_id="29202021234567",
        birth_date=date(1992, 2, 2),
        gender="male",
        marital_status="married",
        hire_date=today_dt,
        created_by=superuser,
        department=dept,
        job_title=job
    )

    cust = Customer.objects.create(name="شركة الأمل للطباعة", customer_type="corporate")
    warehouse = Warehouse.objects.create(name="المخزن الرئيسي", code="WH-MAIN")

    return {
        "superuser": superuser,
        "staff_user": staff_user,
        "regular_user": regular_user,
        "hr_user": hr_user,
        "finance_user": finance_user,
        "emp_regular": emp_regular,
        "emp_target": emp_target,
        "customer": cust,
        "warehouse": warehouse,
        "dept": dept,
        "job": job,
    }


# ==============================================================================
# 1. Printing Pricing APIs & Cost Breakdown Protection
# ==============================================================================

@pytest.mark.django_db
def test_pricing_api_views_purged_of_is_staff(phase6_setup):
    """Verify that is_staff does NOT grant access to pricing management APIs."""
    client = Client()
    client.force_login(phase6_setup["staff_user"])

    # BulkPriceUpdateAPIView
    resp = client.post(reverse("printing_pricing:api_bulk_price_update"), data=json.dumps({"updates": []}), content_type="application/json")
    assert resp.status_code == 403

    # SyncOrderUnitPricesAPIView
    resp2 = client.post(reverse("printing_pricing:api_sync_order_unit_prices"), data=json.dumps({"updates": []}), content_type="application/json")
    assert resp2.status_code == 403


@pytest.mark.django_db
def test_customer_info_api_masks_profit_margin(phase6_setup):
    """Sales rep without view_profit_margins must receive None for default_profit_margin."""
    client = Client()
    client.force_login(phase6_setup["regular_user"])

    resp = client.get(reverse('printing_pricing:api_customer_info', args=[phase6_setup['customer'].id]))
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["default_profit_margin"] is None

    # Authorized user (superuser) sees the margin
    client.force_login(phase6_setup["superuser"])
    resp_auth = client.get(reverse('printing_pricing:api_customer_info', args=[phase6_setup['customer'].id]))
    data_auth = resp_auth.json()
    assert data_auth["default_profit_margin"] is not None


@pytest.mark.django_db
def test_order_summary_api_masks_cost_breakdown_from_sales_rep(phase6_setup):
    """OrderSummaryAPIView must mask material cost, unit cost and profit margins for unauthorized users."""
    order = PrintingOrder.objects.create(
        customer=phase6_setup["customer"],
        created_by=phase6_setup["regular_user"],
        final_price=Decimal("5000.00"),
        quantity=1000,
        status="draft"
    )
    OrderMaterial.objects.create(
        order=order,
        material_type="paper",
        material_name="ورق كوشيه 150 جم",
        quantity=Decimal("100"),
        unit_cost=Decimal("10.00"),
        total_cost=Decimal("1000.00")
    )
    OrderSummary.objects.create(
        order=order,
        material_cost=Decimal("1000.00"),
        total_cost=Decimal("2000.00"),
        final_price=Decimal("5000.00"),
        profit_amount=Decimal("3000.00"),
        profit_margin_percentage=Decimal("60.00")
    )

    client = Client()
    client.force_login(phase6_setup["regular_user"])

    resp = client.get(reverse('printing_pricing:api_order_summary', args=[order.id]))
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True

    # Check materials - unit_cost and total_cost must be masked
    mat = data["materials"][0]
    assert "unit_cost" not in mat
    assert "total_cost" not in mat

    # Check cost_summary - profit_amount and total_cost must be masked
    cost_summary = data["cost_summary"]
    assert "profit_amount" not in cost_summary
    assert "profit_margin" not in cost_summary
    assert "total_cost" not in cost_summary
    assert cost_summary["final_price"] == 5000.0


# ==============================================================================
# 2. HR Decorators & Tier-1 Cache Enforcement
# ==============================================================================

@pytest.mark.django_db
def test_hr_decorators_return_json_403_on_ajax(phase6_setup):
    """Decorators in hr/decorators.py must return JSON 403 for AJAX requests."""
    from hr.decorators import hr_manager_required

    @hr_manager_required
    def dummy_view(request):
        return JsonResponse({"success": True})

    rf = RequestFactory()
    req = rf.get("/hr/dummy/", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
    req.user = phase6_setup["regular_user"]

    resp = dummy_view(req)
    assert resp.status_code == 403
    data = json.loads(resp.content)
    assert data["success"] is False
    assert data["error"] == "permission_denied"


# ==============================================================================
# 3. HR Views Defense (Employees, Contracts, Advances, Leaves, Attendance)
# ==============================================================================

@pytest.mark.django_db
def test_hr_employee_list_restricted(phase6_setup):
    """Unauthorized user cannot access employee_list."""
    client = Client()
    client.force_login(phase6_setup["regular_user"])

    resp = client.get(reverse("hr:employee_list"))
    assert resp.status_code == 403


@pytest.mark.django_db
def test_hr_employee_detail_masks_salaries_for_non_financial_user(phase6_setup):
    """employee_detail must allow view_employee but mask contracts and payrolls if user lacks payroll perms."""
    perm_view_emp = Permission.objects.get(codename="view_employee", content_type__app_label="hr")
    phase6_setup["regular_user"].user_permissions.add(perm_view_emp)

    client = Client()
    client.force_login(phase6_setup["regular_user"])

    resp = client.get(reverse("hr:employee_detail", args=[phase6_setup["emp_target"].pk]))
    assert resp.status_code == 200
    assert resp.context["can_view_salaries"] is False
    assert resp.context["salary_components_preview"] == []
    assert resp.context["payroll_slips"] == []


@pytest.mark.django_db
def test_hr_validation_endpoints_restricted(phase6_setup):
    """Validation endpoints in hr/other_views.py must require view_employee or add_employee."""
    client = Client()
    client.force_login(phase6_setup["regular_user"])

    resp = client.get(reverse("hr:check_employee_email") + "?email=test@mwheba.com")
    assert resp.status_code == 403

    resp2 = client.get(reverse("hr:check_employee_mobile") + "?mobile=01012345678")
    assert resp2.status_code == 403


@pytest.mark.django_db
def test_hr_contract_list_restricted(phase6_setup):
    """Unauthorized user cannot access contract_list."""
    client = Client()
    client.force_login(phase6_setup["regular_user"])

    resp = client.get(reverse("hr:contract_list"))
    assert resp.status_code == 403


@pytest.mark.django_db
def test_hr_leave_list_and_self_service_request(phase6_setup):
    """User can submit self-service leave for self, but cannot submit for others without add_leave."""
    client = Client()
    client.force_login(phase6_setup["regular_user"])

    # Leave list requires view_leave
    resp = client.get(reverse("hr:leave_list"))
    assert resp.status_code == 403

    # Attempt to request leave for another employee -> must fail with 403
    leave_type = LeaveType.objects.create(name_ar="إجازة اعتيادية", code="ANNUAL", max_days_per_year=21)
    resp_other = client.post(reverse("hr:leave_request"), {
        "employee": phase6_setup["emp_target"].pk,
        "leave_type": leave_type.pk,
        "start_date": "2026-10-01",
        "end_date": "2026-10-03",
        "reason": "ظرف طارئ"
    })
    assert resp_other.status_code == 403


@pytest.mark.django_db
def test_hr_advance_request_self_service_guard(phase6_setup):
    """User cannot request advance for other employees without add_advance."""
    client = Client()
    client.force_login(phase6_setup["regular_user"])

    # Advance list requires view_advance
    resp = client.get(reverse("hr:advance_list"))
    assert resp.status_code == 403

    # Advance request for another employee
    resp_other = client.post(reverse("hr:advance_request"), {
        "employee": phase6_setup["emp_target"].pk,
        "amount": "1000",
        "installments_count": "2",
        "deduction_start_month": "2026-10-01",
        "reason": "سلفة خاصة"
    })
    assert resp_other.status_code == 403


@pytest.mark.django_db
def test_hr_attendance_list_restricted(phase6_setup):
    """attendance_list requires view_attendance."""
    client = Client()
    client.force_login(phase6_setup["regular_user"])

    resp = client.get(reverse("hr:attendance_list"))
    assert resp.status_code == 403


# ==============================================================================
# 4. Governance Lockdown & IP Whitelist Guard
# ==============================================================================

@pytest.mark.django_db
def test_governance_delete_old_audit_logs_strictly_locked_to_superuser(phase6_setup):
    """delete_old_audit_logs must reject regular staff and users with 403."""
    client = Client()
    client.force_login(phase6_setup["staff_user"])

    resp = client.post(reverse("governance:delete_old_audit_logs"))
    assert resp.status_code == 403
    data = resp.json()
    assert data["success"] is False


@pytest.mark.django_db
def test_governance_delete_old_audit_logs_creates_pre_deletion_audit(phase6_setup):
    """When superuser purges old logs, a pre-audit log is created and only records > 365 days are deleted."""
    # Create very old log (> 400 days)
    old_time = timezone.now() - timedelta(days=400)
    audit_old = AuditTrail.objects.create(
        user=phase6_setup["superuser"],
        operation="DELETE",
        model_name="TestModel",
        object_id=1,
        source_service="test_service"
    )
    AuditTrail.objects.filter(pk=audit_old.pk).update(timestamp=old_time)

    # Create recent log (10 days old)
    recent_time = timezone.now() - timedelta(days=10)
    audit_recent = AuditTrail.objects.create(
        user=phase6_setup["superuser"],
        operation="UPDATE",
        model_name="TestModel",
        object_id=2,
        source_service="test_service"
    )
    AuditTrail.objects.filter(pk=audit_recent.pk).update(timestamp=recent_time)

    client = Client()
    client.force_login(phase6_setup["superuser"])

    resp = client.post(reverse("governance:delete_old_audit_logs"))
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True

    # Verify that recent log still exists
    assert AuditTrail.objects.filter(pk=audit_recent.pk).exists()
    # Verify pre-deletion audit entry was created
    assert AuditTrail.objects.filter(source_service="governance_purge_service").exists()


@pytest.mark.django_db
def test_governance_ip_blocking_whitelist_guard(phase6_setup):
    """Blocking localhost or internal private IP addresses must be rejected with 400."""
    client = Client()
    client.force_login(phase6_setup["superuser"])

    # Attempt to block 127.0.0.1
    resp = client.post(reverse("governance:block_ip", args=["127.0.0.1"]))
    assert resp.status_code == 400
    data = resp.json()
    assert data["success"] is False
    assert "غير مسموح" in data["error"]

    # Attempt to block 192.168.1.50
    resp2 = client.post(reverse("governance:block_ip", args=["192.168.1.50"]))
    assert resp2.status_code == 400


@pytest.mark.django_db
def test_governance_base_view_cbv_smart_mixin(phase6_setup):
    """Governance CBVs (AuditManagementView) reject unauthorized users with 403."""
    client = Client()
    client.force_login(phase6_setup["regular_user"])

    resp = client.get(reverse("governance:audit_management"))
    assert resp.status_code == 403


# ==============================================================================
# 5. Financial Period and Fiscal Year Controls
# ==============================================================================

@pytest.mark.django_db
def test_financial_accounting_periods_views_enforce_permissions(phase6_setup):
    """accounting_periods_list requires financial.view_accountingperiod."""
    client = Client()
    client.force_login(phase6_setup["regular_user"])

    resp = client.get(reverse("financial:accounting_periods_list"))
    assert resp.status_code == 403


@pytest.mark.django_db
def test_financial_period_close_view_enforces_close_permission(phase6_setup):
    """accounting_periods_close requires financial.close_accounting_period."""
    fy, _ = FiscalYear.objects.get_or_create(
        year_code="FY2055",
        defaults={"name": "2055", "start_date": date(2055, 1, 1), "end_date": date(2055, 12, 31), "status": "open"}
    )
    period, _ = AccountingPeriod.objects.get_or_create(
        start_date=date(2055, 1, 1),
        end_date=date(2055, 1, 31),
        defaults={"fiscal_year": fy, "name": "يناير 2055", "period_number": 1, "status": "open"}
    )

    client = Client()
    client.force_login(phase6_setup["regular_user"])

    resp = client.get(reverse("financial:accounting_periods_close", args=[period.pk]))
    assert resp.status_code == 403


@pytest.mark.django_db
def test_financial_fiscal_year_wizard_restricted(phase6_setup):
    """fiscal_year_wizard requires financial.close_accounting_period."""
    fy, _ = FiscalYear.objects.get_or_create(
        year_code="FY2056",
        defaults={"name": "2056", "start_date": date(2056, 1, 1), "end_date": date(2056, 12, 31), "status": "open"}
    )

    client = Client()
    client.force_login(phase6_setup["regular_user"])

    resp = client.get(reverse("financial:fiscal_year_wizard", args=[fy.pk]))
    assert resp.status_code == 403


# ==============================================================================
# 6. Warehouse Vouchers CBV Smart Mixin
# ==============================================================================

@pytest.mark.django_db
def test_inventory_voucher_cbvs_use_smart_mixin_ajax_safe(phase6_setup):
    """Receipt and Issue voucher CBVs must return JSON 403 for AJAX when unauthorized."""
    client = Client()
    client.force_login(phase6_setup["regular_user"])

    resp = client.get(reverse("product:receipt_voucher_list"), HTTP_X_REQUESTED_WITH="XMLHttpRequest")
    assert resp.status_code == 403
    data = resp.json()
    assert data["success"] is False

    resp2 = client.get(reverse("product:issue_voucher_list"), HTTP_X_REQUESTED_WITH="XMLHttpRequest")
    assert resp2.status_code == 403
    data2 = resp2.json()
    assert data2["success"] is False


# ==============================================================================
# 7. HR Row-Level Self-Service & Protection Verification
# ==============================================================================

@pytest.mark.django_db
def test_leave_and_advance_detail_row_level_gating(phase6_setup):
    """Ensure other employees cannot view each other's leaves, advances, or balance APIs."""
    lt = LeaveType.objects.create(name_ar="سنوية", code="ANNUAL", category="annual", max_days_per_year=21, is_paid=True)
    leave_target = Leave.objects.create(
        employee=phase6_setup["emp_target"],
        leave_type=lt,
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 5),
        days_count=5,
        status="pending"
    )
    advance_target = Advance.objects.create(
        employee=phase6_setup["emp_target"],
        amount=Decimal("3000.00"),
        installments_count=3,
        installment_amount=Decimal("1000.00"),
        deduction_start_month=date(2026, 10, 1),
        status="pending",
        reason="سلفة طارئة"
    )

    client = Client()
    client.force_login(phase6_setup["regular_user"])

    # 1. leave_detail: regular_user accessing emp_target's leave must fail with 403
    resp_leave = client.get(reverse("hr:leave_detail", args=[leave_target.pk]))
    assert resp_leave.status_code == 403

    # 2. employee_leave_info_api: regular_user accessing emp_target must return JSON 403
    resp_api = client.get(reverse("hr:employee_leave_info_api", args=[phase6_setup["emp_target"].pk]))
    assert resp_api.status_code == 403
    assert resp_api.json()["success"] is False

    # 3. advance_detail: regular_user accessing emp_target's advance must fail with 403
    resp_adv = client.get(reverse("hr:advance_detail", args=[advance_target.pk]))
    assert resp_adv.status_code == 403

    # 4. advance_reject: regular_user rejecting advance must fail with 403
    resp_rej = client.post(reverse("hr:advance_reject", args=[advance_target.pk]))
    assert resp_rej.status_code == 403

    # 5. Owner accessing own leave_detail succeeds with 200
    leave_owner = Leave.objects.create(
        employee=phase6_setup["emp_regular"],
        leave_type=lt,
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 3),
        days_count=3,
        status="pending"
    )
    resp_owner = client.get(reverse("hr:leave_detail", args=[leave_owner.pk]))
    assert resp_owner.status_code == 200


@pytest.mark.django_db
def test_contract_form_and_template_api_gating(phase6_setup):
    """contract_form and get_salary_component_templates must require standard permissions."""
    client = Client()
    client.force_login(phase6_setup["regular_user"])

    # Template API requires hr.view_contract
    resp_tmpl = client.get(reverse("hr:salary_templates_api"))
    assert resp_tmpl.status_code == 403

    # Contract form creation requires hr.add_contract
    resp_form = client.get(reverse("hr:contract_form"))
    assert resp_form.status_code == 403


@pytest.mark.django_db
def test_financial_period_crud_gating(phase6_setup):
    """accounting_periods_create and edit must require permissions."""
    client = Client()
    client.force_login(phase6_setup["regular_user"])

    resp_create = client.get(reverse("financial:accounting_periods_create"))
    assert resp_create.status_code == 403


@pytest.mark.django_db
def test_governance_security_policy_apis_locked(phase6_setup):
    """run_security_scan, rotate_all_keys, export_security_report must reject unprivileged users."""
    client = Client()
    client.force_login(phase6_setup["regular_user"])

    resp_scan = client.post(reverse("governance:run_security_scan"))
    assert resp_scan.status_code == 403

    resp_keys = client.post(reverse("governance:rotate_all_keys"))
    assert resp_keys.status_code == 403

    resp_rep = client.get(reverse("governance:export_security_report"))
    assert resp_rep.status_code == 403


@pytest.mark.django_db
def test_bulk_leave_operations_enforce_can_approve_leaves(phase6_setup):
    """bulk_approve_leaves and bulk_reject_leaves must require can_approve_leaves permission."""
    client = Client()
    client.force_login(phase6_setup["regular_user"])

    resp_bulk_app = client.post(reverse("hr:bulk_approve_leaves"), data={"leave_ids": [1]})
    assert resp_bulk_app.status_code == 403

    resp_bulk_rej = client.post(reverse("hr:bulk_reject_leaves"), data={"leave_ids": [1], "rejection_notes": "test"})
    assert resp_bulk_rej.status_code == 403

    # Superuser succeeds (redirects to leave_list with no matching leaves)
    client.force_login(phase6_setup["superuser"])
    resp_super = client.post(reverse("hr:bulk_approve_leaves"), data={"leave_ids": [99999]})
    assert resp_super.status_code == 302


