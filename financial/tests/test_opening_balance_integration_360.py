import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from financial.models import (
    ChartOfAccounts,
    AccountType,
    Currency,
    OpeningBalanceBatch,
    OpeningBalanceLine,
)
from client.models import Customer, CustomerTransaction
from supplier.models import Supplier, SupplierTransaction
from financial.services.opening_balance_service import OpeningBalancePostingService
from financial.services.partner_exposure_service import BusinessPartnerExposureService
from sale.models import Sale


@pytest.fixture
def setup_360_data(db):
    User = get_user_model()
    user = User.objects.create_user(username="auditor_360", email="auditor_360@mwheba.com", password="password123")

    egp, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={"name": "Egyptian Pound", "symbol": "ج.م", "is_functional": True, "is_active": True}
    )
    usd, _ = Currency.objects.get_or_create(
        code="USD",
        defaults={"name": "US Dollar", "symbol": "$", "is_functional": False, "is_active": True}
    )

    from financial.models import FiscalYear
    fiscal_year, _ = FiscalYear.objects.get_or_create(
        year_code="FY2026_360",
        defaults={"name": "FY 2026 360", "start_date": "2026-01-01", "end_date": "2026-12-31", "status": "open"}
    )

    asset_type, _ = AccountType.objects.get_or_create(code="AST_360", defaults={"name": "Current Assets", "category": "asset", "nature": "debit"})
    liability_type, _ = AccountType.objects.get_or_create(code="LIA_360", defaults={"name": "Current Liabilities", "category": "liability", "nature": "credit"})
    equity_type, _ = AccountType.objects.get_or_create(code="EQT_360", defaults={"name": "Equity", "category": "equity", "nature": "credit"})

    acc_ar_ofq, _ = ChartOfAccounts.objects.get_or_create(
        code="11210001_360",
        defaults={"name": "حساب مؤسسة الأفق", "account_type": asset_type, "currency": egp, "is_active": True, "is_leaf": True}
    )
    acc_ar_glf, _ = ChartOfAccounts.objects.get_or_create(
        code="11210002_360",
        defaults={"name": "حساب شركة الخليج", "account_type": asset_type, "currency": usd, "is_active": True, "is_leaf": True}
    )
    acc_ap, _ = ChartOfAccounts.objects.get_or_create(
        code="21110001_360",
        defaults={"name": "Accounts Payable 360", "account_type": liability_type, "currency": egp, "is_active": True, "is_leaf": True}
    )
    acc_equity, _ = ChartOfAccounts.objects.get_or_create(
        code="31010001_360",
        defaults={"name": "Opening Balance Equity 360", "account_type": equity_type, "currency": egp, "is_active": True, "is_leaf": True}
    )

    from product.models import Warehouse
    warehouse, _ = Warehouse.objects.get_or_create(name="المخزن الرئيسي 360", defaults={"code": "WH_360"})

    # Customer 1 (EGP): مؤسسة الأفق
    cust_egp = Customer.objects.create(name="مؤسسة الأفق", code="CUST-OFQ-01", financial_account=acc_ar_ofq)
    # Customer 2 (USD): شركة الخليج العالمية
    cust_usd = Customer.objects.create(name="شركة الخليج العالمية", code="CUST-GLF-01", financial_account=acc_ar_glf, default_currency=usd)
    # Supplier 1 (USD): مورد عالمي
    supp_usd = Supplier.objects.create(name="مورد عالمي", code="SUPP-INT-01", financial_account=acc_ap, default_currency=usd)

    return {
        "user": user,
        "fiscal_year": fiscal_year,
        "warehouse": warehouse,
        "egp": egp,
        "usd": usd,
        "acc_ar_ofq": acc_ar_ofq,
        "acc_ar_glf": acc_ar_glf,
        "acc_ap": acc_ap,
        "acc_equity": acc_equity,
        "cust_egp": cust_egp,
        "cust_usd": cust_usd,
        "supp_usd": supp_usd,
    }


@pytest.mark.django_db
def test_full_opening_balance_subledger_exposure_reconciliation(setup_360_data):
    """اختبار شامل 360° يضمن مزامنة الأستاذ المساعد، الانكشاف المالي، ومنع الازدواجية"""
    data = setup_360_data

    batch = OpeningBalanceBatch.objects.create(
        fiscal_year=data["fiscal_year"],
        batch_number="OPB-360-TEST",
        opening_date=timezone.now().date(),
        description="دفعة أرصدة افتتاحية اختبارية شاملة 360",
        created_by=data["user"],
    )

    # 1. سطر مؤسسة الأفق: 15,000 ج.م مدين
    OpeningBalanceLine.objects.create(
        batch=batch,
        account=data["acc_ar_ofq"],
        line_type="AR",
        customer=data["cust_egp"],
        currency=data["egp"],
        exchange_rate=Decimal("1.000000"),
        debit=Decimal("15000.00"),
        credit=Decimal("0.00"),
        debit_foreign=Decimal("0.00"),
        credit_foreign=Decimal("0.00"),
    )

    # 2. سطر شركة الخليج: 2,000 USD مدين @ 50.0 = 100,000 EGP
    OpeningBalanceLine.objects.create(
        batch=batch,
        account=data["acc_ar_glf"],
        line_type="AR",
        customer=data["cust_usd"],
        currency=data["usd"],
        exchange_rate=Decimal("50.000000"),
        debit=Decimal("100000.00"),
        credit=Decimal("0.00"),
        debit_foreign=Decimal("2000.00"),
        credit_foreign=Decimal("0.00"),
    )

    # 3. سطر المورد: 1,000 USD دائن @ 50.0 = 50,000 EGP
    OpeningBalanceLine.objects.create(
        batch=batch,
        account=data["acc_ap"],
        line_type="AP",
        supplier=data["supp_usd"],
        currency=data["usd"],
        exchange_rate=Decimal("50.000000"),
        debit=Decimal("0.00"),
        credit=Decimal("50000.00"),
        debit_foreign=Decimal("0.00"),
        credit_foreign=Decimal("1000.00"),
    )

    # 4. موازنة القيد الافتتاحي بحساب رأس المال / الأرباح المبقاة (65,000 EGP دائن)
    OpeningBalanceLine.objects.create(
        batch=batch,
        account=data["acc_equity"],
        line_type="GL",
        currency=data["egp"],
        exchange_rate=Decimal("1.000000"),
        debit=Decimal("0.00"),
        credit=Decimal("65000.00"),
        debit_foreign=Decimal("0.00"),
        credit_foreign=Decimal("0.00"),
    )

    # ترحيل الدفعة
    posted_batch = OpeningBalancePostingService.post(batch.id, data["user"])
    assert posted_batch.status == "posted"

    # ==========================
    # فحص الأستاذ المساعد CustomerTransaction
    # ==========================
    # مؤسسة الأفق (EGP)
    tx_ofq = CustomerTransaction.objects.filter(customer=data["cust_egp"], reference_type="OPENING_BALANCE").first()
    assert tx_ofq is not None
    assert tx_ofq.transaction_type == "INVOICE"
    assert tx_ofq.open_amount_functional == Decimal("15000.00")
    assert tx_ofq.open_amount_foreign == Decimal("15000.00")
    assert tx_ofq.status == "OPEN"

    # شركة الخليج (USD)
    tx_glf = CustomerTransaction.objects.filter(customer=data["cust_usd"], reference_type="OPENING_BALANCE").first()
    assert tx_glf is not None
    assert tx_glf.currency == "USD"
    assert tx_glf.foreign_amount == Decimal("2000.00")
    assert tx_glf.open_amount_foreign == Decimal("2000.00")
    assert tx_glf.functional_amount == Decimal("100000.00")
    assert tx_glf.open_amount_functional == Decimal("100000.00")

    # ==========================
    # فحص محرك الانكشاف المالي BusinessPartnerExposureService
    # ==========================
    cust_exposures = BusinessPartnerExposureService.get_open_balances(
        "customer", [data["cust_egp"].id, data["cust_usd"].id]
    )
    # 1. مؤسسة الأفق يجب أن تظهر بـ 15,000 ج.م
    exp_ofq = cust_exposures[data["cust_egp"].id]
    assert len(exp_ofq) == 1
    assert exp_ofq[0].currency == "EGP"
    assert exp_ofq[0].net_balance == Decimal("15000.00")
    assert exp_ofq[0].nature == "RECEIVABLE"

    # 2. شركة الخليج يجب أن تظهر بـ 2,000 $
    exp_glf = cust_exposures[data["cust_usd"].id]
    assert len(exp_glf) == 1
    assert exp_glf[0].currency == "USD"
    assert exp_glf[0].net_balance == Decimal("2000.00")
    assert exp_glf[0].functional_net_balance == Decimal("100000.00")

    # 3. المورد يجب أن يظهر بـ 1,000 $ مطلوب للمورد
    supp_exposures = BusinessPartnerExposureService.get_open_balances(
        "supplier", [data["supp_usd"].id]
    )
    exp_supp = supp_exposures[data["supp_usd"].id]
    assert len(exp_supp) == 1
    assert exp_supp[0].currency == "USD"
    assert exp_supp[0].net_balance == Decimal("1000.00")
    assert exp_supp[0].functional_net_balance == Decimal("50000.00")
    assert exp_supp[0].nature == "PAYABLE"

    # ==========================
    # فحص منع الازدواجية (Deduplication Check)
    # ==========================
    # إنشاء فاتورة بيع جديدة للعميل مؤسسة الأفق بقيمة 5,000 ج.م
    Sale.objects.create(
        customer=data["cust_egp"],
        warehouse=data["warehouse"],
        number="INV-360-001",
        date=timezone.now().date(),
        subtotal=Decimal("5000.00"),
        total=Decimal("5000.00"),
        total_functional=Decimal("5000.00"),
        payment_status="unpaid",
        status="confirmed",
        currency=data["egp"],
        exchange_rate=Decimal("1.000000"),
        created_by=data["user"],
    )

    # التحقق من أن الانكشاف المالي يجمع: 15,000 (افتتاحي) + 5,000 (فاتورة) = 20,000 ج.م بالضبط
    cust_exposures_after = BusinessPartnerExposureService.get_open_balances(
        "customer", [data["cust_egp"].id]
    )
    exp_ofq_after = cust_exposures_after[data["cust_egp"].id]
    assert len(exp_ofq_after) == 1
    assert exp_ofq_after[0].net_balance == Decimal("20000.00")

    # ==========================
    # فحص العكس الآمن
    # ==========================
    rev_batch = OpeningBalancePostingService.reverse(batch.id, data["user"], reason="اختبار العكس 360")
    assert rev_batch.status == "reversed"

    # بعد العكس، الأرصدة الافتتاحية تغلق تماماً وتصبح صفر
    tx_ofq.refresh_from_db()
    assert tx_ofq.status == "CLOSED"
    assert tx_ofq.open_amount == Decimal("0.00")
    assert tx_ofq.open_amount_functional == Decimal("0.00")
    assert tx_ofq.open_amount_foreign == Decimal("0.00")
