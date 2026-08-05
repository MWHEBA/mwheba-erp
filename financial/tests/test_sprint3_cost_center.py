import pytest
from decimal import Decimal
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from financial.models import (
    CostCenter, JournalEntry, JournalEntryLine, ChartOfAccounts, AccountType,
    FiscalYear, AccountingPeriod, EmployeeCostCenterAllocation, UserCostCenterPermission,
    CostCenterAuditLog, CostAllocationRuleAuditLog
)
from financial.services.payroll_posting_service import PayrollPostingService

User = get_user_model()


def get_or_create_open_period(target_date):
    year_str = target_date.year
    fy, _ = FiscalYear.objects.get_or_create(
        name=f"السنة المالية {year_str}",
        defaults={
            'start_date': f"{year_str}-01-01",
            'end_date': f"{year_str}-12-31",
            'status': 'open'
        }
    )
    period, _ = AccountingPeriod.objects.get_or_create(
        fiscal_year=fy,
        period_number=target_date.month,
        defaults={
            'name': f"فترة {target_date.month}-{year_str}",
            'start_date': f"{year_str}-{target_date.month:02d}-01",
            'end_date': f"{year_str}-{target_date.month:02d}-28",
            'status': 'open'
        }
    )
    return fy, period


@pytest.mark.django_db
def test_payroll_posting_service_100_percent_validation_and_posting():
    """اختبار خدمة تترحيل الرواتب واشتراط استيفاء 100% لنسب الموظف"""
    user = User.objects.create_user(username="payroll_admin")
    acc_type_exp = AccountType.objects.create(name="مصروفات رواتب", category="expense", code="EXP_PAY")
    acc_type_asset = AccountType.objects.create(name="أصول نقدية", category="asset", code="AST_PAY")

    acc_exp = ChartOfAccounts.objects.create(code="50401", name="مصروف الرواتب", account_type=acc_type_exp)
    acc_bank = ChartOfAccounts.objects.create(code="10201", name="البنك الأهلي", account_type=acc_type_asset)

    cc1 = CostCenter.objects.create(code="CC-ENG1", name="فريق الهندسة")
    cc2 = CostCenter.objects.create(code="CC-ENG2", name="فريق الدعم الفني")

    emp_id = "EMP-777"
    emp_name = "أحمد علي"

    # تخصيص 70% و 30% للموظف
    EmployeeCostCenterAllocation.objects.create(employee_id=emp_id, employee_name=emp_name, cost_center=cc1, percentage=Decimal("70.00"))
    EmployeeCostCenterAllocation.objects.create(employee_id=emp_id, employee_name=emp_name, cost_center=cc2, percentage=Decimal("30.00"))

    today = timezone.now().date()
    get_or_create_open_period(today)

    entry = PayrollPostingService.post_employee_payroll_entry(
        date=today,
        employee_id=emp_id,
        employee_name=emp_name,
        total_salary=Decimal("10000.00"),
        expense_account=acc_exp,
        bank_account=acc_bank,
        created_by=user
    )

    assert entry.status == 'posted'
    assert entry.lines.count() == 3


@pytest.mark.django_db
def test_user_cost_center_permissions_and_audit_logs():
    """اختبار صلاحيات مراكز التكلفة وسجلات التدقيق الحوكمية"""
    user = User.objects.create_user(username="audited_user")
    cc = CostCenter.objects.create(code="CC-AUD1", name="مركز خاضع للتدقيق")

    # إضافة صلاحية DENY
    perm = UserCostCenterPermission.objects.create(
        user=user,
        cost_center=cc,
        access_type='DENY',
        priority=1
    )

    assert perm.access_type == 'DENY'

    # إنشاء سجل تدقيق
    audit = CostCenterAuditLog.objects.create(
        cost_center=cc,
        action='CREATED',
        performed_by=user,
        user_name_snapshot=user.username,
        changes_json='{"code": "CC-AUD1"}'
    )

    assert audit.action == 'CREATED'
    assert cc.audit_logs.count() == 1
