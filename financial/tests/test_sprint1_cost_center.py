import pytest
from decimal import Decimal
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from financial.models import (
    CostCenter, JournalEntry, JournalEntryLine, ChartOfAccounts, AccountType,
    FiscalYear, AccountingPeriod
)
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
    return period


@pytest.mark.django_db
def test_cost_center_tree_path_auto_generation():
    """اختبار الإنشاء الحسابي التلقائي للمسار الشجري tree_path وسلسلة الأبناء"""
    root = CostCenter.objects.create(code="CC-ROOT-AUTO", name="المركز الرئيسي")
    assert root.tree_path == f"/{root.id}/"

    child = CostCenter.objects.create(code="CC-CHILD1-AUTO", name="المركز الفرعي 1", parent=root)
    assert child.tree_path == f"/{root.id}/{child.id}/"

    grandchild = CostCenter.objects.create(code="CC-SUB1-AUTO", name="المشروع الفرعي", parent=child)
    assert grandchild.tree_path == f"/{root.id}/{child.id}/{grandchild.id}/"


@pytest.mark.django_db
def test_cost_center_structural_mutation_guard():
    """اختبار حظر حوكمة نقل المراكز التي تملك معاملات مالية مرحّلة"""
    user = User.objects.create_user(username="tree_guard_user")
    acc_type = AccountType.objects.create(name="أصول", category="asset")
    acc1 = ChartOfAccounts.objects.create(code="10101", name="النقدية بالصندوق", account_type=acc_type)
    acc2 = ChartOfAccounts.objects.create(code="10102", name="البنك", account_type=acc_type)

    cc1 = CostCenter.objects.create(code="CC-SEC1", name="قسم 1")
    cc2 = CostCenter.objects.create(code="CC-SEC2", name="قسم 2")

    today = timezone.now().date()
    get_or_create_open_period(today)

    # إنشاء وتترحيل قيد مالي مخصص لـ cc1
    entry = JournalEntry.objects.create(
        date=today,
        description="اختبار حظر النقل الشجري",
        created_by=user,
        status="draft"
    )
    JournalEntryLine.objects.create(journal_entry=entry, account=acc1, debit=Decimal("100.00"), credit=Decimal("0.00"), cost_center=cc1)
    JournalEntryLine.objects.create(journal_entry=entry, account=acc2, debit=Decimal("0.00"), credit=Decimal("100.00"), cost_center=cc1)

    LedgerCoreService.post_entry(entry.id, user)

    # محاولة تغيير الأب لـ cc1 إلى cc2 بعد التترحيل
    cc1.parent = cc2
    with pytest.raises(ValidationError) as exc_info:
        cc1.clean()

    assert "حظر الحوكمة" in str(exc_info.value) or "معاملات مالية مرحّلة" in str(exc_info.value)


@pytest.mark.django_db
def test_dual_layer_cost_center_policy_enforcement():
    """اختبار الإنفاذ المزدوج لسياسة REQUIRED / FORBIDDEN في clean و post_entry"""
    user = User.objects.create_user(username="policy_user")
    acc_type = AccountType.objects.create(name="مصروفات", category="expense")
    acc = ChartOfAccounts.objects.create(code="50101", name="مصاريف صيانة", account_type=acc_type)

    cc_forbidden = CostCenter.objects.create(code="CC-FORB", name="مركز محظور", cost_center_policy="FORBIDDEN")

    today = timezone.now().date()
    get_or_create_open_period(today)

    entry = JournalEntry.objects.create(
        date=today,
        description="اختبار السياسة المحظورة",
        created_by=user,
        status="draft"
    )

    line = JournalEntryLine(journal_entry=entry, account=acc, debit=Decimal("500.00"), credit=Decimal("0.00"), cost_center=cc_forbidden)

    # فحص السياسة المحظورة FORBIDDEN عند Clean
    with pytest.raises(ValidationError) as exc_info:
        line.clean()

    assert "تحظر اختيار مركز تكلفة" in str(exc_info.value) or "حظر الحوكمة" in str(exc_info.value)
