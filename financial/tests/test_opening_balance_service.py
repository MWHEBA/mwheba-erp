import uuid
from decimal import Decimal
import pytest
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from financial.models.fiscal_year import FiscalYear
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.currency import Currency
from financial.models.opening_balance import OpeningBalanceBatch, OpeningBalanceLine
from financial.services.opening_balance_service import OpeningBalancePostingService
from financial.exceptions import ImmutableLedgerError
from client.models import Customer, CustomerTransaction

User = get_user_model()


@pytest.fixture
def setup_data(db):
    uid = uuid.uuid4().hex[:6]
    user = User.objects.create_user(username=f"cfo_{uid}", email=f"cfo_{uid}@example.com", password="password123")
    fiscal_year = FiscalYear.objects.create(
        name=f"2026_{uid}",
        year_code=f"Y26_{uid}",
        start_date="2026-01-01",
        end_date="2026-12-31",
        status="open"
    )

    asset_type = AccountType.objects.create(code=f"AST_{uid}", name="أصول", category="asset", nature="debit")
    equity_type = AccountType.objects.create(code=f"EQT_{uid}", name="حقوق ملكية", category="equity", nature="credit")

    acc_cash = ChartOfAccounts.objects.create(code=f"101_{uid}", name="النقدية", account_type=asset_type, is_leaf=True)
    acc_capital = ChartOfAccounts.objects.create(code=f"301_{uid}", name="رأس المال", account_type=equity_type, is_leaf=True)

    batch = OpeningBalanceBatch.objects.create(
        fiscal_year=fiscal_year,
        batch_number=f"OPB-{uid}",
        description="اختبار ترحيل الأرصدة",
        status="draft",
        created_by=user
    )

    return {
        "user": user,
        "fiscal_year": fiscal_year,
        "acc_cash": acc_cash,
        "acc_capital": acc_capital,
        "batch": batch,
    }


@pytest.mark.django_db
def test_unbalanced_batch_rejected(setup_data):
    """1. التعديل/الترحيل لدفعة غير متوازنة يترتب عليه رفض الترحيل"""
    data = setup_data
    OpeningBalanceLine.objects.create(
        batch=data["batch"], line_type='GL', account=data["acc_cash"], debit=Decimal('1000.00'), credit=Decimal('0.00')
    )
    OpeningBalanceLine.objects.create(
        batch=data["batch"], line_type='GL', account=data["acc_capital"], debit=Decimal('0.00'), credit=Decimal('800.00')
    )

    with pytest.raises(ValidationError):
        OpeningBalancePostingService.post(data["batch"].pk, data["user"])


@pytest.mark.django_db
def test_closed_period_rejected(setup_data):
    """2. رفض إنشاء أو ترحيل أية دفعة على سنة مالية مغلقة"""
    data = setup_data
    uid = uuid.uuid4().hex[:6]
    closed_fy = FiscalYear.objects.create(
        name=f"2025_CL_{uid}",
        year_code=f"Y25_{uid}",
        start_date="2025-01-01",
        end_date="2025-12-31",
        status="closed"
    )
    with pytest.raises(ValidationError):
        OpeningBalanceBatch.objects.create(
            fiscal_year=closed_fy, batch_number=f"OPC-{uid}", status="draft", created_by=data["user"]
        )


@pytest.mark.django_db
def test_double_post_idempotency(setup_data):
    """3. الترحيل المزدوج لدفعة مرحلة يرفض ويحصن النظام ضد التعديل (Idempotency)"""
    data = setup_data
    OpeningBalanceLine.objects.create(batch=data["batch"], line_type='GL', account=data["acc_cash"], debit=Decimal('5000.00'))
    OpeningBalanceLine.objects.create(batch=data["batch"], line_type='GL', account=data["acc_capital"], credit=Decimal('5000.00'))

    b1 = OpeningBalancePostingService.post(data["batch"].pk, data["user"])
    assert b1.status == 'posted'
    assert b1.journal_entry_id is not None

    with pytest.raises(ImmutableLedgerError):
        OpeningBalancePostingService.post(data["batch"].pk, data["user"])


@pytest.mark.django_db
def test_posted_batch_immutability(setup_data):
    """4. رفض أي تعديل أو حذف لدفعة حالتها POSTED"""
    data = setup_data
    OpeningBalanceLine.objects.create(batch=data["batch"], line_type='GL', account=data["acc_cash"], debit=Decimal('1000.00'))
    OpeningBalanceLine.objects.create(batch=data["batch"], line_type='GL', account=data["acc_capital"], credit=Decimal('1000.00'))
    
    OpeningBalancePostingService.post(data["batch"].pk, data["user"])
    
    data["batch"].refresh_from_db()
    with pytest.raises(ImmutableLedgerError):
        data["batch"].description = "تعديل مرفوض"
        data["batch"].save()


@pytest.mark.django_db
def test_double_reversal_rejected(setup_data):
    """5. رفض إجراء عكس ثانٍ لدفعة معكوسة بالفعل"""
    data = setup_data
    OpeningBalanceLine.objects.create(batch=data["batch"], line_type='GL', account=data["acc_cash"], debit=Decimal('2000.00'))
    OpeningBalanceLine.objects.create(batch=data["batch"], line_type='GL', account=data["acc_capital"], credit=Decimal('2000.00'))
    
    OpeningBalancePostingService.post(data["batch"].pk, data["user"])
    OpeningBalancePostingService.reverse(data["batch"].pk, data["user"], reason="إلغاء أولي")

    with pytest.raises((ValidationError, ImmutableLedgerError)):
        OpeningBalancePostingService.reverse(data["batch"].pk, data["user"], reason="إلغاء ثانٍ")


@pytest.mark.django_db
def test_reversal_creates_reversal_items(setup_data):
    """6. عكس الدفعة يولد قيد يومية عكسي وبنود عكس فرعية للعملاء"""
    data = setup_data
    uid = uuid.uuid4().hex[:6]
    customer = Customer.objects.create(name="عميل اختبار العكس", code=f"CST_{uid}")
    OpeningBalanceLine.objects.create(
        batch=data["batch"], line_type='AR', account=data["acc_cash"], debit=Decimal('3000.00'), customer=customer
    )
    OpeningBalanceLine.objects.create(
        batch=data["batch"], line_type='GL', account=data["acc_capital"], credit=Decimal('3000.00')
    )

    OpeningBalancePostingService.post(data["batch"].pk, data["user"])
    b_rev = OpeningBalancePostingService.reverse(data["batch"].pk, data["user"], reason="تعديل حسابات")

    assert b_rev.status == 'reversed'
    assert b_rev.reversal_journal_entry is not None
    
    # التأكد من إنشاء حركة عكسية (CREDIT_NOTE) في السجل الفرعي للعميل
    rev_tx = CustomerTransaction.objects.filter(customer=customer, transaction_type='CREDIT_NOTE').first()
    assert rev_tx is not None
    assert rev_tx.functional_amount == Decimal('3000.00')


@pytest.mark.django_db
def test_line_type_strict_validation(setup_data):
    """7. رفض سطر AR بدون عميل"""
    data = setup_data
    line = OpeningBalanceLine(batch=data["batch"], line_type='AR', account=data["acc_cash"], debit=Decimal('1000.00'), customer=None)
    with pytest.raises(ValidationError):
        line.full_clean()


@pytest.mark.django_db
def test_foreign_currency_amount_and_rate_validation(setup_data):
    """8. التأكد من رفض سطر العملة الأجنبية إذا كان هناك انحراف بين حاصل الضرب والمبلغ الوظيفي"""
    data = setup_data
    uid = uuid.uuid4().hex[:2]
    curr_code = f"U{uid[:2]}".upper()[:3]
    usd = Currency.objects.create(code=curr_code, name="US Dollar", symbol="$", is_active=True)
    line = OpeningBalanceLine(
        batch=data["batch"],
        line_type='GL',
        account=data["acc_cash"],
        currency=usd,
        debit_foreign=Decimal('100.00'),
        exchange_rate=Decimal('50.000000'),
        debit=Decimal('4000.00')  # 100 * 50 = 5000, not 4000
    )
    with pytest.raises(ValidationError):
        line.full_clean()
