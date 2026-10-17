# -*- coding: utf-8 -*-
"""
Tests for Phase 1: Opening Balance Backfill Migration and Rollback
اختبارات شاملة ومحوكمة لمعالج هجرة الأرصدة الافتتاحية والأستاذ المساعد والتراجع العكسي
"""

import pytest
from decimal import Decimal
from datetime import date
from django.core.management import call_command
from django.contrib.auth import get_user_model

from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.currency import Currency
from financial.models.journal_entry import JournalEntry, JournalEntryLine
from customer.models import Customer, CustomerTransaction
from supplier.models import Supplier, SupplierTransaction

User = get_user_model()


@pytest.fixture
def migration_setup(db):
    user = User.objects.create_superuser(
        username="cfo_user",
        email="cfo@mwheba.com",
        password="password123"
    )

    usd_currency, _ = Currency.objects.get_or_create(
        code="USD",
        defaults={"name": "US Dollar", "is_active": True}
    )

    # 1. إعداد أنواع الحسابات
    asset_type, _ = AccountType.objects.get_or_create(
        code="TEST_ASSET",
        defaults={"name": "أصول تجريبية", "category": "asset", "nature": "debit"}
    )
    liability_type, _ = AccountType.objects.get_or_create(
        code="TEST_LIAB",
        defaults={"name": "التزامات تجريبية", "category": "liability", "nature": "credit"}
    )
    equity_type, _ = AccountType.objects.get_or_create(
        code="TEST_EQUITY",
        defaults={"name": "حقوق ملكية تجريبية", "category": "equity", "nature": "credit"}
    )

    # 2. حساب وسيط الأرصدة الافتتاحية 31010
    equity_clearing, _ = ChartOfAccounts.objects.get_or_create(
        code="31010",
        defaults={
            "name": "الأرصدة الافتتاحية",
            "account_type": equity_type,
            "is_leaf": True,
            "is_active": True,
        }
    )

    # 3. حساب خزانة عادي رصيد موجب (مدين 15,000)
    cash_acc = ChartOfAccounts.objects.create(
        code="1119001",
        name="خزينة الفرع أ",
        account_type=asset_type,
        opening_balance=Decimal("15000.00"),
        opening_balance_date=date(2026, 1, 1),
        is_leaf=True,
        is_active=True,
        is_cash_account=True,
    )

    # 4. حساب بنك مكشوف رصيد سالب (سحب على المكشوف -5,000)
    bank_overdraft = ChartOfAccounts.objects.create(
        code="1119002",
        name="بنك مكشوف سحب جاري",
        account_type=asset_type,
        opening_balance=Decimal("-5000.00"),
        opening_balance_date=date(2026, 1, 1),
        is_leaf=True,
        is_active=True,
        is_bank_account=True,
    )

    # 5. حساب عميل يتيم (مدين 8,000)
    customer_acc = ChartOfAccounts.objects.create(
        code="1129001",
        name="ذمة العميل مروان",
        account_type=asset_type,
        opening_balance=Decimal("8000.00"),
        opening_balance_date=date(2026, 1, 1),
        is_leaf=True,
        is_active=True,
    )
    customer = Customer.objects.create(
        name="مروان التجاري",
        code="CUST-MIG-01",
        financial_account=customer_acc,
    )

    # 6. حساب مورد بعملة أجنبية (دائن 12,000 ج.م تعادل 240 دولار بسعر صرف 50.0)
    supplier_acc = ChartOfAccounts.objects.create(
        code="2119001",
        name="مورد التوريدات المتحدة",
        account_type=liability_type,
        opening_balance=Decimal("12000.00"),
        opening_balance_date=date(2026, 1, 1),
        currency=usd_currency,
        opening_balance_foreign=Decimal("240.00"),
        opening_balance_rate=Decimal("50.000000"),
        is_leaf=True,
        is_active=True,
    )
    supplier = Supplier.objects.create(
        name="شركة التوريدات المتحدة",
        code="SUPP-MIG-01",
        financial_account=supplier_acc,
    )

    return {
        "user": user,
        "cash_acc": cash_acc,
        "bank_overdraft": bank_overdraft,
        "customer_acc": customer_acc,
        "customer": customer,
        "supplier_acc": supplier_acc,
        "supplier": supplier,
        "equity_clearing": equity_clearing,
    }


@pytest.mark.django_db
def test_backfill_and_rollback_full_lifecycle(migration_setup):
    """
    اختبار دورة الحياة الكاملة للمرحلة 1:
    - فحص المحاكاة Dry Run
    - تنفيذ الترحيل الفعلي Apply
    - التحقق من اتزان القيود وتوجيه السحب على المكشوف
    - التحقق من مزامنة الأستاذ المساعد للعميل
    - التحقق من أمر التراجع العكسي الشامل Rollback
    """
    # 1. المحاكاة (Dry Run)
    call_command("backfill_opening_balances")
    assert JournalEntry.objects.filter(reference__startswith="MIG-OPB-").count() == 0

    # 2. التنفيذ الفعلي (Apply)
    call_command("backfill_opening_balances", apply=True)

    # التحقق من توليد 4 قيود هجرة
    mig_jes = JournalEntry.objects.filter(reference__startswith="MIG-OPB-", status="posted")
    assert mig_jes.count() == 4

    # التحقق من قيد الخزينة العادية (مدين 15,000 للخزينة، دائن 15,000 لحقوق الملكية)
    je_cash = mig_jes.get(reference=f"MIG-OPB-{migration_setup['cash_acc'].code}")
    lines_cash = je_cash.lines.all()
    cash_line = lines_cash.get(account=migration_setup["cash_acc"])
    equity_line_cash = lines_cash.get(account=migration_setup["equity_clearing"])
    assert cash_line.debit == Decimal("15000.00")
    assert cash_line.credit == Decimal("0.00")
    assert equity_line_cash.credit == Decimal("15000.00")

    # التحقق من قيد البنك المكشوف (سحب على المكشوف سالب: دائن 5,000 للبنك، مدين 5,000 لحقوق الملكية)
    je_bank = mig_jes.get(reference=f"MIG-OPB-{migration_setup['bank_overdraft'].code}")
    lines_bank = je_bank.lines.all()
    bank_line = lines_bank.get(account=migration_setup["bank_overdraft"])
    equity_line_bank = lines_bank.get(account=migration_setup["equity_clearing"])
    assert bank_line.credit == Decimal("5000.00"), "البنك المكشوف يجب أن يكون في الجانب الدائن"
    assert bank_line.debit == Decimal("0.00")
    assert equity_line_bank.debit == Decimal("5000.00")

    # التحقق من قيد المورد بالعملة الأجنبية (دائن 12,000 للمورد، مدين 12,000 لحقوق الملكية مع 240 USD)
    je_supp = mig_jes.get(reference=f"MIG-OPB-{migration_setup['supplier_acc'].code}")
    lines_supp = je_supp.lines.all()
    supp_line = lines_supp.get(account=migration_setup["supplier_acc"])
    equity_line_supp = lines_supp.get(account=migration_setup["equity_clearing"])
    assert supp_line.credit == Decimal("12000.00")
    assert supp_line.currency == "USD"
    assert supp_line.foreign_credit == Decimal("240.00")
    assert equity_line_supp.debit == Decimal("12000.00")

    # التحقق من مزامنة الأستاذ المساعد للعميل (CustomerTransaction)
    cust_tx = CustomerTransaction.objects.filter(
        customer=migration_setup["customer"],
        reference_type="OPENING_BALANCE"
    ).first()
    assert cust_tx is not None
    assert cust_tx.transaction_type == "INVOICE"
    assert cust_tx.functional_amount == Decimal("8000.00")
    assert cust_tx.status == "OPEN"

    # التحقق من مزامنة الأستاذ المساعد للمورد (SupplierTransaction)
    supp_tx = SupplierTransaction.objects.filter(
        supplier=migration_setup["supplier"],
        transaction_number=f"OPN-SUPP-{migration_setup['supplier_acc'].code}"
    ).first()
    assert supp_tx is not None
    assert supp_tx.transaction_type == "BILL"
    assert supp_tx.functional_amount == Decimal("12000.00")
    assert supp_tx.foreign_amount == Decimal("240.00")
    assert supp_tx.status == "OPEN"

    # التحقق من عدم التكرار (Idempotency): تشغيل الأمر مرة أخرى لا يولد قيوداً جديدة
    call_command("backfill_opening_balances", apply=True)
    assert JournalEntry.objects.filter(reference__startswith="MIG-OPB-", status="posted").count() == 4

    # 3. اختبار التراجع العكسي الشامل (Rollback)
    call_command("rollback_opening_migration", apply=True)

    # يجب أن تصبح القيود الأصلية معكوسة وتوليد قيود عكسية مرحلة
    rev_jes = JournalEntry.objects.filter(is_reversal=True, status="posted")
    assert rev_jes.count() == 4

    # الأستاذ المساعد للعميل والمورد يتم تنظيفهما
    assert CustomerTransaction.objects.filter(customer=migration_setup["customer"], reference_type="OPENING_BALANCE").count() == 0
    assert SupplierTransaction.objects.filter(supplier=migration_setup["supplier"], transaction_number=f"OPN-SUPP-{migration_setup['supplier_acc'].code}").count() == 0
