import uuid
from decimal import Decimal
import pytest
from django.utils import timezone
from django.contrib.auth import get_user_model

from financial.models.fiscal_year import FiscalYear
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.currency import Currency
from financial.models.opening_balance import OpeningBalanceBatch, OpeningBalanceLine
from financial.services.opening_balance_service import OpeningBalancePostingService
from financial.services.excel_import_service import ExcelImportService
from client.models import Customer, CustomerTransaction
from supplier.models import Supplier, SupplierTransaction

User = get_user_model()


@pytest.fixture
def setup_mc_data(db):
    uid = uuid.uuid4().hex[:6]
    cfo = User.objects.create_user(username=f"cfo_{uid}", email=f"cfo_{uid}@test.com", password="password123")
    user = User.objects.create_user(username=f"usr_{uid}", email=f"usr_{uid}@test.com", password="password123")
    
    fiscal_year = FiscalYear.objects.create(
        name=f"FY26_{uid}",
        year_code=f"FY_{uid}",
        start_date="2026-01-01",
        end_date="2026-12-31",
        status="open"
    )

    asset_type = AccountType.objects.create(code=f"AST_{uid}", name="أصول", category="asset", nature="debit")
    liability_type = AccountType.objects.create(code=f"LIA_{uid}", name="خصوم", category="liability", nature="credit")
    equity_type = AccountType.objects.create(code=f"EQT_{uid}", name="حقوق ملكية", category="equity", nature="credit")

    acc_ar = ChartOfAccounts.objects.create(code=f"1101_{uid}", name="العملاء", account_type=asset_type, is_leaf=True)
    acc_ap = ChartOfAccounts.objects.create(code=f"2101_{uid}", name="الموردين", account_type=liability_type, is_leaf=True)
    acc_capital = ChartOfAccounts.objects.create(code=f"3001_{uid}", name="رأس المال", account_type=equity_type, is_leaf=True)

    usd_curr, _ = Currency.objects.get_or_create(code="USD", defaults={"name": "US Dollar", "symbol": "$", "is_functional": False})

    customer = Customer.objects.create(name=f"Customer USD {uid}")
    supplier = Supplier.objects.create(name=f"Supplier USD {uid}")

    batch = OpeningBalanceBatch.objects.create(
        fiscal_year=fiscal_year,
        batch_number=f"OPB-MC-{uid}",
        description="دفعة اختبار العملات الأجنبية والأستاذ المساعد",
        status="draft",
        created_by=user
    )

    return {
        "cfo": cfo,
        "user": user,
        "batch": batch,
        "acc_ar": acc_ar,
        "acc_ap": acc_ap,
        "acc_capital": acc_capital,
        "usd_curr": usd_curr,
        "customer": customer,
        "supplier": supplier,
    }


@pytest.mark.django_db
def test_customer_foreign_currency_subledger_posting(setup_mc_data):
    """التحقق من إنشاء حركة CustomerTransaction بالعملة الأجنبية وقيمها الصحيحة عند الترحيل"""
    data = setup_mc_data
    batch = data["batch"]
    rate = Decimal("50.000000")
    usd_amount = Decimal("10000.00")
    egp_amount = Decimal("500000.00")

    # 1. سطر عميل مدين 10,000 USD @ 50.0 = 500,000 EGP
    OpeningBalanceLine.objects.create(
        batch=batch,
        account=data["acc_ar"],
        line_type="AR",
        customer=data["customer"],
        currency=data["usd_curr"],
        exchange_rate=rate,
        debit_foreign=usd_amount,
        credit_foreign=Decimal("0.00"),
        debit=egp_amount,
        credit=Decimal("0.00")
    )

    # 2. سطر رأس مال دائن 500,000 EGP للاتزان
    OpeningBalanceLine.objects.create(
        batch=batch,
        account=data["acc_capital"],
        line_type="GL",
        debit=Decimal("0.00"),
        credit=egp_amount
    )

    # 3. ترحيل الدفعة
    posted_batch = OpeningBalancePostingService.post(batch.id, data["user"])
    assert posted_batch.status == "posted"

    # 4. فحص CustomerTransaction
    txn = CustomerTransaction.objects.filter(customer=data["customer"], reference_type="OPENING_BALANCE").first()
    assert txn is not None
    assert txn.currency == "USD"
    assert txn.foreign_amount == usd_amount
    assert txn.open_amount_foreign == usd_amount
    assert txn.functional_amount == egp_amount
    assert txn.open_amount == egp_amount
    assert txn.status == "OPEN"

    # 5. عكس الدفعة
    rev_batch = OpeningBalancePostingService.reverse(batch.id, data["user"], reason="اختبار العكس")
    assert rev_batch.status == "reversed"
    
    rev_txn = CustomerTransaction.objects.filter(customer=data["customer"], reference_type="OPENING_BALANCE_REVERSAL").first()
    assert rev_txn is not None
    assert rev_txn.foreign_amount == usd_amount
    assert rev_txn.status == "CLOSED"
    assert rev_txn.open_amount_foreign == Decimal("0.00")

    txn.refresh_from_db()
    assert txn.status == "CLOSED"
    assert txn.open_amount_foreign == Decimal("0.00")
    assert txn.open_amount_functional == Decimal("0.00")


@pytest.mark.django_db
def test_supplier_foreign_currency_subledger_posting(setup_mc_data):
    """التحقق من إنشاء حركة SupplierTransaction بالعملة الأجنبية وبدون أخطاء حقول"""
    data = setup_mc_data
    batch = data["batch"]
    rate = Decimal("50.000000")
    usd_amount = Decimal("5000.00")
    egp_amount = Decimal("250000.00")

    # 1. سطر مورد دائن 5,000 USD @ 50.0 = 250,000 EGP
    OpeningBalanceLine.objects.create(
        batch=batch,
        account=data["acc_ap"],
        line_type="AP",
        supplier=data["supplier"],
        currency=data["usd_curr"],
        exchange_rate=rate,
        debit_foreign=Decimal("0.00"),
        credit_foreign=usd_amount,
        debit=Decimal("0.00"),
        credit=egp_amount
    )

    # 2. سطر مدين للاتزان
    OpeningBalanceLine.objects.create(
        batch=batch,
        account=data["acc_ar"],
        line_type="GL",
        debit=egp_amount,
        credit=Decimal("0.00")
    )

    # 3. ترحيل الدفعة
    posted_batch = OpeningBalancePostingService.post(batch.id, data["user"])
    assert posted_batch.status == "posted"

    # 4. فحص SupplierTransaction
    txn = SupplierTransaction.objects.filter(supplier=data["supplier"]).first()
    assert txn is not None
    assert txn.currency == "USD"
    assert txn.foreign_amount == usd_amount
    assert txn.open_amount_foreign == usd_amount
    assert txn.functional_amount == egp_amount
    assert txn.open_amount == egp_amount
    assert txn.status == "OPEN"


@pytest.mark.django_db
def test_excel_import_with_currency_and_rate(setup_mc_data):
    """التحقق من صحة قراءة العملة وسعر الصرف من شيت الإكسيل واحتساب المعادل"""
    data = setup_mc_data
    batch = data["batch"]

    raw_rows = [
        {
            "account_code": data["acc_ar"].code,
            "line_type": "GL",
            "debit": "1000.00",
            "credit": "0.00",
            "currency": "USD",
            "exchange_rate": "50.00"
        }
    ]

    valid_rows, invalid_rows = ExcelImportService.validate_rows(raw_rows, batch=batch)
    assert len(invalid_rows) == 0
    assert len(valid_rows) == 1

    row = valid_rows[0]
    assert row["currency"].code == "USD"
    assert row["exchange_rate"] == Decimal("50.00")
    assert row["debit_foreign"] == Decimal("1000.00")
    assert row["debit"] == Decimal("50000.00")
