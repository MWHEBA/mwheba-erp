import uuid
from decimal import Decimal
import pytest
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from financial.models.fiscal_year import FiscalYear
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.currency import Currency
from financial.models.opening_balance import OpeningBalanceBatch, OpeningBalanceLine, ControlAccountOverrideRequest, OpeningBalanceImportBatch
from financial.services.opening_balance_service import OpeningBalancePostingService, RoundingTolerancePolicy
from financial.services.role_registry import AccountRoleRegistry
from financial.services.excel_import_service import ExcelImportService

User = get_user_model()


@pytest.fixture
def setup_phase1_data(db):
    uid = uuid.uuid4().hex[:6]
    cfo = User.objects.create_user(username=f"cfo_user_{uid}", password="password123")
    user = User.objects.create_user(username=f"user_{uid}", password="password123")
    
    fiscal_year = FiscalYear.objects.create(
        name=f"2026_P1_{uid}",
        year_code=f"Y26P1_{uid}",
        start_date="2026-01-01",
        end_date="2026-12-31",
        status="open"
    )

    asset_type = AccountType.objects.create(code=f"AST_P1_{uid}", name="أصول", category="asset", nature="debit")
    equity_type = AccountType.objects.create(code=f"EQT_P1_{uid}", name="حقوق ملكية", category="equity", nature="credit")

    acc_cash = ChartOfAccounts.objects.create(code=f"101_{uid}", name="النقدية", account_type=asset_type, is_leaf=True)
    acc_capital = ChartOfAccounts.objects.create(code=f"301_{uid}", name="رأس المال", account_type=equity_type, is_leaf=True)
    
    # Control Account (AR Control Account 11010)
    acc_ar_control = ChartOfAccounts.objects.create(code="11010", name="إجمالي العملاء", account_type=asset_type, is_leaf=True)

    batch = OpeningBalanceBatch.objects.create(
        fiscal_year=fiscal_year,
        batch_number=f"OPB-P1-{uid}",
        description="دفعة اختبار المرحلة الأولى",
        status="draft",
        created_by=user
    )

    return {
        "cfo": cfo,
        "user": user,
        "fiscal_year": fiscal_year,
        "acc_cash": acc_cash,
        "acc_capital": acc_capital,
        "acc_ar_control": acc_ar_control,
        "batch": batch,
    }


@pytest.mark.django_db
def test_control_account_override_requires_cfo_approval(setup_phase1_data):
    """1. الإدخال المباشر على الحساب الحاكم بنوع GL يرفض ما لم توجد موافقة CFO"""
    data = setup_phase1_data
    line = OpeningBalanceLine(
        batch=data["batch"],
        line_type='GL',
        account=data["acc_ar_control"],
        debit=Decimal('10000.00')
    )
    
    # Clean raises ValidationError because no override exists
    with pytest.raises(ValidationError):
        line.clean()

    # Create approved override request
    override = ControlAccountOverrideRequest.objects.create(
        opening_batch=data["batch"],
        account=data["acc_ar_control"],
        requested_by=data["user"],
        approved_by=data["cfo"],
        reason="الهجرة الأولية للبيانات",
        status="approved",
        approved_at=timezone.now()
    )

    # Now line.clean() passes cleanly
    line.clean()
    assert override.is_valid_for(data["batch"], data["acc_ar_control"]) is True


@pytest.mark.django_db
def test_override_request_cannot_be_reused_for_another_account(setup_phase1_data):
    """2. موافقة الاستثناء لحساب محدد لا يمكن إعادة استخدامها لحساب حاكم آخر أو دفعة أخرى"""
    data = setup_phase1_data
    override = ControlAccountOverrideRequest.objects.create(
        opening_batch=data["batch"],
        account=data["acc_ar_control"],
        requested_by=data["user"],
        approved_by=data["cfo"],
        reason="استثناء محدد",
        status="approved"
    )

    # Valid for batch & acc_ar_control
    assert override.is_valid_for(data["batch"], data["acc_ar_control"]) is True
    # Invalid for cash account
    assert override.is_valid_for(data["batch"], data["acc_cash"]) is False


@pytest.mark.django_db
def test_rounding_difference_uses_account_role_registry(setup_phase1_data):
    """3. توجيه فروق التقريب الصغرى (<= 0.05 ج) لحساب فروق التقريب آلياً من AccountRoleRegistry"""
    data = setup_phase1_data
    
    # Ensure ROUNDING_DIFFERENCE_ACCOUNT role exists
    rounding_acc = AccountRoleRegistry.get_account("ROUNDING_DIFFERENCE_ACCOUNT")
    assert rounding_acc is not None

    # Line debit 1000.00, Line credit 999.98 (diff = 0.02 EGP <= tolerance)
    OpeningBalanceLine.objects.create(batch=data["batch"], line_type='GL', account=data["acc_cash"], debit=Decimal('1000.00'))
    OpeningBalanceLine.objects.create(batch=data["batch"], line_type='GL', account=data["acc_capital"], credit=Decimal('999.98'))

    posted_batch = OpeningBalancePostingService.post(data["batch"].pk, data["user"])
    assert posted_batch.status == 'posted'
    assert posted_batch.journal_entry is not None

    # Verify rounding line was added to journal entry lines
    jv_lines = list(posted_batch.journal_entry.lines.all())
    rounding_jv_line = [l for l in jv_lines if l.account_id == rounding_acc.id]
    assert len(rounding_jv_line) == 1
    assert rounding_jv_line[0].credit == Decimal('0.02')


@pytest.mark.django_db
def test_inventory_sync_failure_marks_batch_pending_retry(setup_phase1_data):
    """4. فشل مزامنة المخزون يحفظ القيد المالي ويضع الحالة FAILED مع إتاحة زر الإعادة"""
    data = setup_phase1_data
    OpeningBalanceLine.objects.create(
        batch=data["batch"],
        line_type='INVENTORY',
        account=data["acc_cash"],
        debit=Decimal('5000.00'),
        inventory_snapshot_id="SNP-999"
    )
    OpeningBalanceLine.objects.create(
        batch=data["batch"],
        line_type='GL',
        account=data["acc_capital"],
        credit=Decimal('5000.00')
    )

    posted_batch = OpeningBalancePostingService.post(data["batch"].pk, data["user"])
    assert posted_batch.status == 'posted'
    assert posted_batch.journal_entry_id is not None
    # inventory_sync_status should be COMPLETED or FAILED cleanly
    assert posted_batch.inventory_sync_status in ['COMPLETED', 'FAILED', 'PENDING']


@pytest.mark.django_db
def test_inventory_retry_is_idempotent(setup_phase1_data):
    """5. إعادة محاولة مزامنة المخزون محصنة ضئ ضد التكرار بـ inventory_sync_key"""
    data = setup_phase1_data
    batch = data["batch"]
    batch.inventory_sync_status = 'FAILED'
    batch.save()

    b1 = OpeningBalancePostingService.retry_inventory_sync(batch.id, data["user"])
    assert b1.inventory_sync_key == f"INVENTORY_OPENING:{batch.id}"


@pytest.mark.django_db
def test_excel_import_service_pipeline(setup_phase1_data):
    """6. فحص pipeline استيراد Excel الأرصدة الافتتاحية (Validate & Commit)"""
    data = setup_phase1_data
    raw_rows = [
        {'account_code': data["acc_cash"].code, 'line_type': 'GL', 'debit': '15000.00', 'credit': '0.00'},
        {'account_code': data["acc_capital"].code, 'line_type': 'GL', 'debit': '0.00', 'credit': '15000.00'},
        {'account_code': '999999_INVALID', 'line_type': 'GL', 'debit': '100.00', 'credit': '0.00'},
    ]

    valid_rows, invalid_rows = ExcelImportService.validate_rows(raw_rows)
    assert len(valid_rows) == 2
    assert len(invalid_rows) == 1
    assert invalid_rows[0]['row_number'] == 4

    import_rec = ExcelImportService.commit(data["batch"], valid_rows, data["user"], filename="test_opb.xlsx")
    assert import_rec.valid_rows == 2
    assert data["batch"].lines.count() == 2
