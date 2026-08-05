import pytest
from decimal import Decimal
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from financial.models import (
    CostCenter, JournalEntry, JournalEntryLine, ChartOfAccounts, AccountType,
    FiscalYear, AccountingPeriod, CostCenterBudget, CostCenterBalanceSnapshot
)
from financial.services.cost_allocation_service import CostAllocationService
from financial.services.ledger_core_service import LedgerCoreService

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
def test_cost_allocation_service_and_100_percent_rule():
    """اختبار محرك التوزيع المالي واشتراط نسبة 100% بالكامل"""
    user = User.objects.create_user(username="alloc_user")
    acc_type = AccountType.objects.create(name="مصروفات", category="expense")
    acc = ChartOfAccounts.objects.create(code="50201", name="مصاريف تسويق", account_type=acc_type)

    cc1 = CostCenter.objects.create(code="CC-MKT1", name="فريق القاهرة")
    cc2 = CostCenter.objects.create(code="CC-MKT2", name="فريق الإسكندرية")

    today = timezone.now().date()
    get_or_create_open_period(today)

    entry = JournalEntry.objects.create(date=today, description="توزيع التسويق", created_by=user, status="draft")
    line = JournalEntryLine.objects.create(journal_entry=entry, account=acc, debit=Decimal("1000.00"), credit=Decimal("0.00"))

    # توزيع 60% و 40%
    allocs = CostAllocationService.allocate_journal_line(
        line=line,
        allocations=[
            {'cost_center': cc1, 'percentage': Decimal("60.00")},
            {'cost_center': cc2, 'percentage': Decimal("40.00")},
        ]
    )

    assert len(allocs) == 2
    assert line.cost_allocations.count() == 2

    # محاولة توزيع غير مكتمل بنسبة 80% وتوقع خطأ حوكمة
    with pytest.raises(ValidationError) as exc_info:
        CostAllocationService.allocate_journal_line(
            line=line,
            allocations=[
                {'cost_center': cc1, 'percentage': Decimal("50.00")},
                {'cost_center': cc2, 'percentage': Decimal("30.00")},
            ]
        )
    assert "100%" in str(exc_info.value) or "حظر الحوكمة" in str(exc_info.value)


@pytest.mark.django_db
def test_cost_center_budget_versioning_and_immutability():
    """اختبار حصانة الميزانية المعتمدة والـ Versioning"""
    cc = CostCenter.objects.create(code="CC-DEV1", name="فريق التطوير")
    today = timezone.now().date()
    fy, _ = get_or_create_open_period(today)

    budget_v1 = CostCenterBudget.objects.create(
        cost_center=cc,
        fiscal_year=fy,
        version=1,
        allocated_amount=Decimal("50000.00"),
        status='APPROVED'
    )

    assert budget_v1.current_budget == Decimal("50000.00")

    # محاولة تعديل المبلغ المعتمد مباشرة بدون إنشاء إصدار جديد وتوقع الفشل
    budget_v1.allocated_amount = Decimal("60000.00")
    with pytest.raises(ValidationError) as exc_info:
        budget_v1.clean()

    assert "الميزانية المعتمدة حصينة" in str(exc_info.value) or "حظر الحوكمة" in str(exc_info.value)


@pytest.mark.django_db
def test_cost_center_balance_snapshot_recalculation():
    """اختبار إعادة احتساب لقطات أرصدة مراكز التكلفة"""
    user = User.objects.create_user(username="snapshot_user")
    acc_type = AccountType.objects.create(name="مصروفات", category="expense")
    acc1 = ChartOfAccounts.objects.create(code="50301", name="إيجار", account_type=acc_type)
    acc2 = ChartOfAccounts.objects.create(code="10101", name="الصندوق", account_type=acc_type)

    cc = CostCenter.objects.create(code="CC-HQ", name="المقر الرئيسي")
    today = timezone.now().date()
    fy, _ = get_or_create_open_period(today)

    entry = JournalEntry.objects.create(date=today, description="إيجار المقر", created_by=user, status="draft")
    JournalEntryLine.objects.create(journal_entry=entry, account=acc1, debit=Decimal("12000.00"), credit=Decimal("0.00"), cost_center=cc)
    JournalEntryLine.objects.create(journal_entry=entry, account=acc2, debit=Decimal("0.00"), credit=Decimal("12000.00"), cost_center=cc)

    LedgerCoreService.post_entry(entry.id, user)

    snapshot, _ = CostCenterBalanceSnapshot.objects.get_or_create(cost_center=cc, fiscal_year=fy, currency="EGP")
    snapshot.recalculate()

    assert snapshot.total_debit == Decimal("12000.00")
    assert snapshot.total_credit == Decimal("12000.00")
    assert snapshot.net_balance == Decimal("0.00")
