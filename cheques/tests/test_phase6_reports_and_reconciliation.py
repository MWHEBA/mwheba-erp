# -*- coding: utf-8 -*-
"""
FIN-CHQ-PHASE6: Comprehensive Test Suite for Phase 6 Reports and Reconciliation
- SCN-09: Point-in-Time Subledger Reconciliation for Cheques Collected Later
- SCN-34: Historical Reconciliation for Partially Collected Cheques with FX Rates
- SCN-39 & SCN-47: LIFO Reversal Historical Accuracy (Reversal After As-Of-Date)
- SCN-42 & SCN-53: Period-End FX Revaluation Inclusion & Reversal
- SCN-02 & SCN-31: Detailed Subledger Reconciliation Breakdown
- Cheque Aging Analysis & Schedule Service (Brackets & Partner Grouping)
- Cheque Upcoming Due & Maturity Alert Service
- Report Views Integration (HTTP 200, Permissions & Filtering)
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from financial.models import (
    ChartOfAccounts,
    Currency,
    AccountType,
    JournalEntry,
    UserTreasuryAccess,
)
from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
from customer.models import Customer
from supplier.models import Supplier
from cheques.models import (
    Cheque,
    ChequeType,
    ChequePurpose,
    ChequeStatus,
    ChequeActionType,
    ChequeSettlementLine,
)
from cheques.services.accounting_service import ChequeAccountingService
from cheques.services.reversal_service import ChequeReversalService
from cheques.services.subledger_reconciliation_service import ChequeSubledgerReconciliationService
from cheques.services.aging_service import ChequeAgingService
from cheques.services.alert_service import ChequeAlertService

User = get_user_model()


@pytest.fixture
def test_user(db):
    user = User.objects.filter(username="phase6_auditor").first()
    if not user:
        user = User.objects.create_user(
            username="phase6_auditor",
            email="phase6@mwheba.com",
            password="Password123!"
        )
    return user


@pytest.fixture
def account_types(db):
    asset_type, _ = AccountType.objects.get_or_create(
        code="asset", defaults={"name": "أصول", "category": "asset", "nature": "debit"}
    )
    liability_type, _ = AccountType.objects.get_or_create(
        code="liability", defaults={"name": "خصوم", "category": "liability", "nature": "credit"}
    )
    expense_type, _ = AccountType.objects.get_or_create(
        code="expense", defaults={"name": "مصروفات", "category": "expense", "nature": "debit"}
    )
    revenue_type, _ = AccountType.objects.get_or_create(
        code="revenue", defaults={"name": "إيرادات", "category": "revenue", "nature": "credit"}
    )
    return {
        "asset": asset_type,
        "liability": liability_type,
        "expense": expense_type,
        "revenue": revenue_type,
    }


@pytest.fixture
def financial_accounts(db, account_types, test_user):
    egp, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={"name": "جنيه مصري", "symbol": "ج.م", "is_functional": True, "is_active": True}
    )
    usd, _ = Currency.objects.get_or_create(
        code="USD",
        defaults={"name": "دولار أمريكي", "symbol": "$", "is_functional": False, "is_active": True}
    )

    bank, _ = ChartOfAccounts.objects.get_or_create(
        code="11160001",
        defaults={
            "name": "البنك الأهلي المصري",
            "account_type": account_types["asset"],
            "level": 4,
            "is_leaf": True,
            "is_active": True,
            "currency": egp,
        }
    )

    notes_rec, _ = ChartOfAccounts.objects.get_or_create(
        code="11220",
        defaults={
            "name": "أوراق القبض (في الخزينة)",
            "account_type": account_types["asset"],
            "level": 4,
            "is_leaf": True,
            "is_active": True,
            "currency": egp,
        }
    )

    under_coll, _ = ChartOfAccounts.objects.get_or_create(
        code="11190",
        defaults={
            "name": "نقدية في الطريق وشيكات برسم التحصيل",
            "account_type": account_types["asset"],
            "level": 4,
            "is_leaf": True,
            "is_active": True,
            "currency": egp,
        }
    )

    notes_pay, _ = ChartOfAccounts.objects.get_or_create(
        code="21120",
        defaults={
            "name": "أوراق الدفع (شيكات صادرة)",
            "account_type": account_types["liability"],
            "level": 4,
            "is_leaf": True,
            "is_active": True,
            "currency": egp,
        }
    )

    bank_charges, _ = ChartOfAccounts.objects.get_or_create(
        code="54100",
        defaults={
            "name": "عمولات ومصاريف بنكية",
            "account_type": account_types["expense"],
            "level": 4,
            "is_leaf": True,
            "is_active": True,
            "currency": egp,
        }
    )

    UserTreasuryAccess.objects.get_or_create(
        user=test_user,
        treasury=bank,
        defaults={
            "can_deposit": True,
            "can_disburse": True,
            "max_single_disbursement_limit": Decimal("1000000.00"),
            "daily_disbursement_limit": Decimal("5000000.00"),
        }
    )

    return {
        "egp": egp,
        "usd": usd,
        "bank": bank,
        "notes_rec": notes_rec,
        "under_coll": under_coll,
        "notes_pay": notes_pay,
        "bank_charges": bank_charges,
    }


@pytest.fixture
def test_customer(db, financial_accounts, account_types):
    cust_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="11310001",
        defaults={
            "name": "العميل شركة النيل للمقاولات",
            "account_type": account_types["asset"],
            "level": 4,
            "is_leaf": True,
            "is_active": True,
            "currency": financial_accounts["egp"],
        }
    )
    customer, _ = Customer.objects.get_or_create(
        code="CUST-P6-001",
        defaults={
            "name": "شركة النيل للمقاولات",
            "financial_account": cust_acc,
            "is_active": True,
        }
    )
    return customer


@pytest.fixture
def test_supplier(db, financial_accounts, account_types):
    supp_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="21110001",
        defaults={
            "name": "المورد شركة السويس للصلب",
            "account_type": account_types["liability"],
            "level": 4,
            "is_leaf": True,
            "is_active": True,
            "currency": financial_accounts["egp"],
        }
    )
    supplier, _ = Supplier.objects.get_or_create(
        code="SUPP-P6-001",
        defaults={
            "name": "شركة السويس للصلب",
            "financial_account": supp_acc,
            "is_active": True,
        }
    )
    return supplier


# ==============================================================================
# TESTS
# ==============================================================================

@pytest.mark.django_db
def test_subledger_reconciliation_point_in_time_scn_09(
    test_user, financial_accounts, test_customer
):
    """
    SCN-09: استخراج تقرير مطابقة الأستاذ المساعد بتاريخ سابق (as_of_date) لشيك تم تحصيله لاحقاً
    - استلام شيك وإيداعه في البنك برسم التحصيل بتاريخ 5 أكتوبر
    - تحصيل الشيك بالبنك بتاريخ 12 أكتوبر
    - عند طلب المطابقة بتاريخ 8 أكتوبر (قبل التحصيل): يظهر الشيك كـ UNDER_COLLECTION ويتطابق رصيده مع الأستاذ العام
    - عند طلب المطابقة بتاريخ 15 أكتوبر (بعد التحصيل): يكون قد صرف ولا يظهر ضمن الشيكات برسم التحصيل
    """
    cheque = Cheque.objects.create(
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        voucher_number="CHQR-P6-001",
        cheque_number="998877",
        amount=Decimal("15000.00"),
        functional_amount=Decimal("15000.00"),
        book_value_functional=Decimal("15000.00"),
        remaining_amount=Decimal("15000.00"),
        remaining_functional=Decimal("15000.00"),
        currency=financial_accounts["egp"],
        customer=test_customer,
        drawer_name="شركة النيل",
        payee_name="MWHEBA ERP",
        issue_date=date(2026, 10, 5),
        due_date=date(2026, 10, 20),
        status=ChequeStatus.DRAFT,
    )

    # 1. استلام الشيك في الخزينة بتاريخ 5 أكتوبر
    ChequeAccountingService.receive_cheque(
        cheque_id=cheque.id,
        user=test_user,
        idempotency_key="JE:cheques:ChequeActionLog:P6_1:RECEIVE",
        value_date=date(2026, 10, 5)
    )

    # 2. إيداع الشيك برسم التحصيل بالبنك بتاريخ 7 أكتوبر
    ChequeAccountingService.deposit_cheque(
        cheque_id=cheque.id,
        user=test_user,
        bank_account_id=financial_accounts["bank"].id,
        idempotency_key="JE:cheques:ChequeActionLog:P6_2:DEPOSIT",
        value_date=date(2026, 10, 7)
    )

    # 3. تحصيل الشيك بالكامل بالبنك بتاريخ 12 أكتوبر
    ChequeAccountingService.collect_cheque(
        cheque_id=cheque.id,
        user=test_user,
        amount_collected=Decimal("15000.00"),
        deposit_bank_account_id=financial_accounts["bank"].id,
        idempotency_key="JE:cheques:ChequeActionLog:P6_3:COLLECT",
        value_date=date(2026, 10, 12)
    )

    # اختبار المطابقة بتاريخ 6 أكتوبر (بعد الاستلام وقبل الإيداع)
    rec_oct_6 = ChequeSubledgerReconciliationService.reconcile_at_date(date(2026, 10, 6))
    assert rec_oct_6["11220_notes_receivable"]["is_matched"] is True
    assert rec_oct_6["11220_notes_receivable"]["subledger_balance"] == Decimal("15000.00")
    assert rec_oct_6["11190_cheques_under_collection"]["subledger_balance"] == Decimal("0.00")

    # اختبار المطابقة بتاريخ 8 أكتوبر (بعد الإيداع وقبل التحصيل بالبنك)
    rec_oct_8 = ChequeSubledgerReconciliationService.reconcile_at_date(date(2026, 10, 8))
    assert rec_oct_8["11190_cheques_under_collection"]["is_matched"] is True
    assert rec_oct_8["11190_cheques_under_collection"]["subledger_balance"] == Decimal("15000.00")
    assert rec_oct_8["11220_notes_receivable"]["subledger_balance"] == Decimal("0.00")

    # اختبار المطابقة بتاريخ 15 أكتوبر (بعد التحصيل بالبنك)
    rec_oct_15 = ChequeSubledgerReconciliationService.reconcile_at_date(date(2026, 10, 15))
    assert rec_oct_15["11190_cheques_under_collection"]["is_matched"] is True
    assert rec_oct_15["11190_cheques_under_collection"]["subledger_balance"] == Decimal("0.00")
    assert rec_oct_15["11220_notes_receivable"]["subledger_balance"] == Decimal("0.00")
    assert rec_oct_15["overall_matched"] is True


@pytest.mark.django_db
def test_subledger_reconciliation_reversal_lifo_scn_39_scn_47(
    test_user, financial_accounts, test_customer
):
    """
    SCN-39 & SCN-47: استخراج تقرير مطابقة تاريخي في تاريخ يسبق تاريخ عكس التحصيل
    - تحصيل شيك في 10 أكتوبر
    - عكس التحصيل في 20 أكتوبر
    - تقرير 15 أكتوبر يُثبت سريان التحصيل في ذلك التاريخ ويطابق الأستاذ العام بالسنت (0.00)
    - تقرير 25 أكتوبر يُثبت سريان العكس وعودة الشيك كرصيد برسم التحصيل (10,000.00)
    """
    cheque = Cheque.objects.create(
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        voucher_number="CHQR-P6-REV",
        cheque_number="776655",
        amount=Decimal("10000.00"),
        functional_amount=Decimal("10000.00"),
        book_value_functional=Decimal("10000.00"),
        remaining_amount=Decimal("10000.00"),
        remaining_functional=Decimal("10000.00"),
        currency=financial_accounts["egp"],
        customer=test_customer,
        drawer_name="شركة النيل",
        payee_name="MWHEBA ERP",
        issue_date=date(2026, 10, 1),
        due_date=date(2026, 10, 15),
        status=ChequeStatus.DRAFT,
    )

    # استلام وإيداع في 1 و 3 أكتوبر
    ChequeAccountingService.receive_cheque(
        cheque_id=cheque.id,
        user=test_user,
        idempotency_key="JE:cheques:ChequeActionLog:P6_REV_1:RECEIVE",
        value_date=date(2026, 10, 1)
    )
    ChequeAccountingService.deposit_cheque(
        cheque_id=cheque.id,
        user=test_user,
        bank_account_id=financial_accounts["bank"].id,
        idempotency_key="JE:cheques:ChequeActionLog:P6_REV_2:DEPOSIT",
        value_date=date(2026, 10, 3)
    )

    # تحصيل الشيك في 10 أكتوبر
    ChequeAccountingService.collect_cheque(
        cheque_id=cheque.id,
        user=test_user,
        amount_collected=Decimal("10000.00"),
        deposit_bank_account_id=financial_accounts["bank"].id,
        idempotency_key="JE:cheques:ChequeActionLog:P6_REV_3:COLLECT",
        value_date=date(2026, 10, 10)
    )

    # عكس التحصيل في 20 أكتوبر
    # نحدد تاريخ حركة العكس في 20 أكتوبر
    rev_res = ChequeReversalService.reverse_last_action(
        cheque_id=cheque.id,
        user=test_user,
        reason="خطأ في قيد الإيداع من قبل البنك وتم تصحيحه",
        idempotency_key="JE:cheques:ChequeActionLog:P6_REV_4:REVERSE_ACTION"
    )
    reversal_log = rev_res["reversal_log"]
    reversal_log.action_date = date(2026, 10, 20)
    reversal_log.save(update_fields=["action_date"])

    if reversal_log.journal_entry:
        JournalEntry.objects.filter(id=reversal_log.journal_entry_id).update(date=date(2026, 10, 20))

    # فحص 1: تقرير المطابقة في 15 أكتوبر (يسبق تاريخ العكس)
    # التحصيل كان سارياً في 15 أكتوبر -> الرصيد برسم التحصيل 0.00
    rec_oct_15 = ChequeSubledgerReconciliationService.reconcile_at_date(date(2026, 10, 15))
    assert rec_oct_15["11190_cheques_under_collection"]["subledger_balance"] == Decimal("0.00")
    assert rec_oct_15["11190_cheques_under_collection"]["gl_balance"] == Decimal("0.00")
    assert rec_oct_15["11190_cheques_under_collection"]["is_matched"] is True

    # فحص 2: تقرير المطابقة في 25 أكتوبر (بعد تاريخ العكس)
    # العكس سارٍ في 25 أكتوبر -> عاد الشيك لرصيد برسم التحصيل (10,000.00)
    rec_oct_25 = ChequeSubledgerReconciliationService.reconcile_at_date(date(2026, 10, 25))
    assert rec_oct_25["11190_cheques_under_collection"]["subledger_balance"] == Decimal("10000.00")
    assert rec_oct_25["11190_cheques_under_collection"]["gl_balance"] == Decimal("10000.00")
    assert rec_oct_25["11190_cheques_under_collection"]["is_matched"] is True


@pytest.mark.django_db
def test_subledger_reconciliation_partial_collection_fx_scn_34(
    test_user, financial_accounts, test_customer
):
    """
    SCN-34: مطابقة الأستاذ المساعد لشيك محصل جزئياً بفرق سعر صرف بتاريخ سابق
    شيك بقيمة 1,000 USD بسعر صرف 50 = 50,000 EGP
    تحصيل جزئي 600 USD بسعر صرف 52 = 31,200 EGP (القيمة الدفترية للحصة المسددة 30,000 EGP)
    يجب أن يتطابق رصيد الأستاذ المساعد مع رصيد حساب 11190 بالأستاذ العام (20,000 EGP) بالسنت
    """
    cheque = Cheque.objects.create(
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        voucher_number="CHQR-P6-USD",
        cheque_number="443322",
        amount=Decimal("1000.00"),
        currency=financial_accounts["usd"],
        original_exchange_rate=Decimal("50.000000"),
        functional_amount=Decimal("50000.00"),
        book_value_functional=Decimal("50000.00"),
        remaining_amount=Decimal("1000.00"),
        remaining_functional=Decimal("50000.00"),
        customer=test_customer,
        drawer_name="شركة النيل",
        payee_name="MWHEBA ERP",
        issue_date=date(2026, 10, 1),
        due_date=date(2026, 10, 30),
        status=ChequeStatus.DRAFT,
    )

    ChequeAccountingService.receive_cheque(
        cheque_id=cheque.id,
        user=test_user,
        idempotency_key="JE:cheques:ChequeActionLog:P6_USD_1:RECEIVE",
        value_date=date(2026, 10, 1)
    )
    ChequeAccountingService.deposit_cheque(
        cheque_id=cheque.id,
        user=test_user,
        bank_account_id=financial_accounts["bank"].id,
        idempotency_key="JE:cheques:ChequeActionLog:P6_USD_2:DEPOSIT",
        value_date=date(2026, 10, 5)
    )

    # تحصيل جزئي 600 USD بسعر 52
    ChequeAccountingService.collect_cheque(
        cheque_id=cheque.id,
        user=test_user,
        amount_collected=Decimal("600.00"),
        exchange_rate=Decimal("52.000000"),
        deposit_bank_account_id=financial_accounts["bank"].id,
        idempotency_key="JE:cheques:ChequeActionLog:P6_USD_3:COLLECT",
        value_date=date(2026, 10, 10)
    )

    # تقرير المطابقة في 15 أكتوبر
    rec = ChequeSubledgerReconciliationService.reconcile_at_date(date(2026, 10, 15))
    coll_info = rec["11190_cheques_under_collection"]

    assert coll_info["subledger_balance"] == Decimal("20000.00")
    assert coll_info["gl_balance"] == Decimal("20000.00")
    assert coll_info["is_matched"] is True
    assert coll_info["difference"] == Decimal("0.00")


@pytest.mark.django_db
def test_subledger_reconciliation_service_with_details(
    test_user, financial_accounts, test_customer, test_supplier
):
    """
    اختبار دالة reconcile_with_details وإرجاع القوائم التفصيلية للثلاثة حسابات الرقابية
    """
    today = timezone.now().date()

    # 1. شيك قبض في المحفظة (11220)
    Cheque.objects.create(
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        voucher_number="CHQR-DET-001",
        cheque_number="1111",
        amount=Decimal("5000.00"),
        functional_amount=Decimal("5000.00"),
        book_value_functional=Decimal("5000.00"),
        remaining_amount=Decimal("5000.00"),
        remaining_functional=Decimal("5000.00"),
        currency=financial_accounts["egp"],
        customer=test_customer,
        issue_date=today,
        due_date=today + timedelta(days=10),
        status=ChequeStatus.IN_PORTFOLIO,
    )

    # 2. شيك دفع صادر (21120)
    Cheque.objects.create(
        cheque_type=ChequeType.PAYABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        voucher_number="CHQP-DET-001",
        cheque_number="2222",
        amount=Decimal("8000.00"),
        functional_amount=Decimal("8000.00"),
        book_value_functional=Decimal("8000.00"),
        remaining_amount=Decimal("8000.00"),
        remaining_functional=Decimal("8000.00"),
        currency=financial_accounts["egp"],
        supplier=test_supplier,
        deposit_bank_account=financial_accounts["bank"],
        issue_date=today,
        due_date=today + timedelta(days=15),
        status=ChequeStatus.ISSUED,
    )

    details = ChequeSubledgerReconciliationService.reconcile_with_details(today)

    assert details["11220_notes_receivable"]["count"] >= 1
    assert any(c["voucher_number"] == "CHQR-DET-001" for c in details["11220_notes_receivable"]["cheques"])
    assert details["21120_notes_payable"]["count"] >= 1
    assert any(c["voucher_number"] == "CHQP-DET-001" for c in details["21120_notes_payable"]["cheques"])
    assert details["total_cheques_count"] >= 2


@pytest.mark.django_db
def test_cheque_aging_service_calculation(
    financial_accounts, test_customer
):
    """
    اختبار ChequeAgingService وتقسيم الشيكات عبر الشرائح الزمنية وحساب مجاميع الشركاء
    """
    today = timezone.now().date()

    # شيك 1: ساري (غير متأخر) - يستحق بعد 10 أيام
    Cheque.objects.create(
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        voucher_number="CHQ-AGE-1",
        cheque_number="A1",
        amount=Decimal("10000.00"),
        remaining_functional=Decimal("10000.00"),
        currency=financial_accounts["egp"],
        customer=test_customer,
        issue_date=today - timedelta(days=20),
        due_date=today + timedelta(days=10),
        status=ChequeStatus.UNDER_COLLECTION,
    )

    # شيك 2: متأخر 15 يوماً (شريحة 1 - 30 يوم)
    Cheque.objects.create(
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        voucher_number="CHQ-AGE-2",
        cheque_number="A2",
        amount=Decimal("4000.00"),
        remaining_functional=Decimal("4000.00"),
        currency=financial_accounts["egp"],
        customer=test_customer,
        issue_date=today - timedelta(days=40),
        due_date=today - timedelta(days=15),
        status=ChequeStatus.UNDER_COLLECTION,
    )

    # شيك 3: متأخر 70 يوماً (شريحة 61 - 90 يوم)
    Cheque.objects.create(
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        voucher_number="CHQ-AGE-3",
        cheque_number="A3",
        amount=Decimal("6000.00"),
        remaining_functional=Decimal("6000.00"),
        currency=financial_accounts["egp"],
        customer=test_customer,
        issue_date=today - timedelta(days=90),
        due_date=today - timedelta(days=70),
        status=ChequeStatus.BOUNCED,
    )

    report = ChequeAgingService.get_aging_report(as_of_date=today, cheque_type=ChequeType.RECEIVABLE)

    assert report["total_amount"] == Decimal("20000.00")
    assert report["total_current"] == Decimal("10000.00")
    assert report["total_overdue"] == Decimal("10000.00")
    assert report["overdue_ratio"] == Decimal("50.0")

    assert report["bracket_totals"]["current"]["amount"] == Decimal("10000.00")
    assert report["bracket_totals"]["1_30"]["amount"] == Decimal("4000.00")
    assert report["bracket_totals"]["61_90"]["amount"] == Decimal("6000.00")

    # فحص تجميع الشريك
    partner_row = next(p for p in report["partners_summary"] if p["partner_name"] == test_customer.name)
    assert partner_row["total_amount"] == Decimal("20000.00")
    assert partner_row["current"] == Decimal("10000.00")
    assert partner_row["overdue_1_30"] == Decimal("4000.00")
    assert partner_row["overdue_61_90"] == Decimal("6000.00")


@pytest.mark.django_db
def test_cheque_alert_service_due_dates(
    financial_accounts, test_customer, test_supplier
):
    """
    اختبار ChequeAlertService وتصنيف الشيكات (اليوم، الأسبوع، المتأخرات، المرتدة)
    """
    today = timezone.now().date()

    # 1. شيك يستحق اليوم
    Cheque.objects.create(
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        voucher_number="CHQ-ALT-1",
        cheque_number="T1",
        amount=Decimal("3000.00"),
        remaining_functional=Decimal("3000.00"),
        currency=financial_accounts["egp"],
        customer=test_customer,
        issue_date=today - timedelta(days=5),
        due_date=today,
        status=ChequeStatus.UNDER_COLLECTION,
    )

    # 2. شيك يستحق بعد 4 أيام (خلال الأسبوع)
    Cheque.objects.create(
        cheque_type=ChequeType.PAYABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        voucher_number="CHQ-ALT-2",
        cheque_number="T2",
        amount=Decimal("7000.00"),
        remaining_functional=Decimal("7000.00"),
        currency=financial_accounts["egp"],
        supplier=test_supplier,
        issue_date=today - timedelta(days=2),
        due_date=today + timedelta(days=4),
        status=ChequeStatus.ISSUED,
    )

    # 3. شيك متأخر
    Cheque.objects.create(
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        voucher_number="CHQ-ALT-3",
        cheque_number="T3",
        amount=Decimal("2500.00"),
        remaining_functional=Decimal("2500.00"),
        currency=financial_accounts["egp"],
        customer=test_customer,
        issue_date=today - timedelta(days=20),
        due_date=today - timedelta(days=5),
        status=ChequeStatus.IN_PORTFOLIO,
    )

    # 4. شيك مرتد
    Cheque.objects.create(
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        voucher_number="CHQ-ALT-4",
        cheque_number="T4",
        amount=Decimal("4000.00"),
        remaining_functional=Decimal("4000.00"),
        currency=financial_accounts["egp"],
        customer=test_customer,
        issue_date=today - timedelta(days=30),
        due_date=today - timedelta(days=10),
        status=ChequeStatus.BOUNCED,
    )

    stats = ChequeAlertService.get_due_alerts_summary()
    assert stats["today_rec_count"] == 1
    assert stats["today_rec_amount"] == Decimal("3000.00")
    assert stats["week_pay_count"] == 1
    assert stats["week_pay_amount"] == Decimal("7000.00")
    assert stats["overdue_rec_count"] == 1
    assert stats["overdue_rec_amount"] == Decimal("2500.00")
    assert stats["bounced_count"] == 1
    assert stats["bounced_amount"] == Decimal("4000.00")

    # تقرير الفلترة
    rep_today = ChequeAlertService.get_upcoming_due_report(period_filter="today")
    assert rep_today["total_count"] == 1
    assert rep_today["cheques"][0]["voucher_number"] == "CHQ-ALT-1"

    rep_week = ChequeAlertService.get_upcoming_due_report(period_filter="7")
    assert rep_week["total_count"] == 2  # today + week

    rep_overdue = ChequeAlertService.get_upcoming_due_report(period_filter="overdue")
    assert rep_overdue["total_count"] == 1
    assert rep_overdue["cheques"][0]["voucher_number"] == "CHQ-ALT-3"


@pytest.mark.django_db
def test_report_views_render(test_user, financial_accounts):
    """
    اختبار مسارات وعرض الـ Views للتقارير الثلاثة (Subledger Rec, Aging, Upcoming Due)
    """
    from django.contrib.auth.models import Permission

    # إضافة الصلاحية view_cheque للمستخدم
    perm = Permission.objects.get(codename="view_cheque", content_type__app_label="cheques")
    test_user.user_permissions.add(perm)

    client = Client()
    client.force_login(test_user)

    # 1. تقرير مطابقة الأستاذ المساعد
    rec_url = reverse("cheques:subledger_reconciliation")
    res_rec = client.get(rec_url, {"as_of_date": date.today().isoformat()})
    assert res_rec.status_code == 200
    assert "reconciliation" in res_rec.context
    assert "11220_notes_receivable" in res_rec.context["reconciliation"]

    # 2. تقرير ميزان الأعمار
    aging_url = reverse("cheques:cheque_aging")
    res_aging = client.get(aging_url, {"cheque_type": "RECEIVABLE"})
    assert res_aging.status_code == 200
    assert "report" in res_aging.context
    assert "bracket_totals" in res_aging.context["report"]

    # 3. تقرير الشيكات المستحقة والتنبيهات
    due_url = reverse("cheques:upcoming_due")
    res_due = client.get(due_url, {"period": "7"})
    assert res_due.status_code == 200
    assert "report" in res_due.context
    assert "summary_stats" in res_due.context["report"]


@pytest.mark.django_db
def test_subledger_reconciliation_fx_revaluation_inclusion_scn_42_scn_53(
    test_user, financial_accounts, test_customer
):
    """
    SCN-42 & SCN-53: تقييم فروق أسعار الصرف بنهاية الفترة وإعادة ضبط القيمة الدفترية في اليوم الأول وفق IAS 21
    - شيك بالدولار 1,000 USD تم استلامه وإيداعه برسم التحصيل (50,000 EGP)
    - تقييم فروق عملة في 31 ديسمبر بربح غير محقق 2,000 EGP (تاريخ القيد 31 ديسمبر)
    - تقرير 31 ديسمبر يتضمن ربح التقييم وتصبح القيمة الدفترية التاريخية 52,000 EGP
    - عكس قيد التقييم في 1 يناير (-2,000 EGP)
    - تقرير 5 يناير يستبعد التقييم لأن قيد العكس رُحل في 1 يناير، وتعود القيمة لتكلفتها التاريخية الأصلية 50,000 EGP
    """
    from financial.models import AccountingPeriod, FiscalYear
    from financial.fx.models import FXRevaluationRun, FXRevaluationLine

    fy, _ = FiscalYear.objects.get_or_create(
        year_code="2026",
        defaults={"name": "السنة المالية 2026", "start_date": date(2026, 1, 1), "end_date": date(2026, 12, 31)}
    )
    period, _ = AccountingPeriod.objects.get_or_create(
        fiscal_year=fy,
        period_number=12,
        defaults={"name": "فترة ديسمبر 2026", "start_date": date(2026, 12, 1), "end_date": date(2026, 12, 31), "status": "open"}
    )

    cheque = Cheque.objects.create(
        cheque_type=ChequeType.RECEIVABLE,
        purpose=ChequePurpose.INVOICE_SETTLEMENT,
        voucher_number="CHQR-P6-FX",
        cheque_number="889900",
        amount=Decimal("1000.00"),
        currency=financial_accounts["usd"],
        original_exchange_rate=Decimal("50.000000"),
        functional_amount=Decimal("50000.00"),
        book_value_functional=Decimal("50000.00"),
        remaining_amount=Decimal("1000.00"),
        remaining_functional=Decimal("50000.00"),
        customer=test_customer,
        issue_date=date(2026, 12, 1),
        due_date=date(2026, 12, 25),
        status=ChequeStatus.DRAFT,
    )

    ChequeAccountingService.receive_cheque(
        cheque_id=cheque.id,
        user=test_user,
        idempotency_key="JE:cheques:ChequeActionLog:P6_FX_1:RECEIVE",
        value_date=date(2026, 12, 1)
    )
    ChequeAccountingService.deposit_cheque(
        cheque_id=cheque.id,
        user=test_user,
        bank_account_id=financial_accounts["bank"].id,
        idempotency_key="JE:cheques:ChequeActionLog:P6_FX_2:DEPOSIT",
        value_date=date(2026, 12, 5)
    )

    # إنشاء قيد تقييم مرحل في 31 ديسمبر
    fx_entry = JournalEntry.objects.create(
        number="JE-FX-2026-001",
        date=date(2026, 12, 31),
        status="posted",
        description="تقييم فروق عملة نهاية الفترة 2026",
        created_by=test_user,
    )
    run = FXRevaluationRun.objects.create(
        period=period,
        status="POSTED",
        run_date=date(2026, 12, 31),
        journal_entry=fx_entry,
        total_unrealized_gain_loss=Decimal("2000.00"),
        created_by=test_user,
    )
    FXRevaluationLine.objects.create(
        run=run,
        source_type="NOTES_RECEIVABLE",
        source_id=str(cheque.id),
        account=financial_accounts["under_coll"],
        currency=financial_accounts["usd"],
        open_foreign_amount=Decimal("1000.00"),
        old_rate=Decimal("50.000000"),
        new_rate=Decimal("52.000000"),
        old_functional_value=Decimal("50000.00"),
        new_functional_value=Decimal("52000.00"),
        unrealized_difference=Decimal("2000.00"),
    )

    # فحص 1: في 31 ديسمبر، القيمة الدفترية التاريخية تتضمن الـ 2000 EGP وتصبح 52,000 EGP
    val_dec_31 = ChequeSubledgerReconciliationService.compute_historical_carrying_value(cheque, date(2026, 12, 31))
    assert val_dec_31 == Decimal("52000.00")

    # محاكاة عكس قيد التقييم في 1 يناير 2027
    reversal_entry = JournalEntry.objects.create(
        number="JE-FX-REV-2027-001",
        date=date(2027, 1, 1),
        status="posted",
        description="عكس قيد تقييم فروق العملة تلقائياً في أول يوم",
        created_by=test_user,
    )
    FXRevaluationRun.objects.create(
        period=period,
        status="REVERSED",
        run_date=date(2027, 1, 1),
        journal_entry=reversal_entry,
        reversal_of_run=run,
        total_unrealized_gain_loss=Decimal("-2000.00"),
        created_by=test_user,
    )

    # فحص 2: في 5 يناير 2027، بعد ترحيل قيد العكس في 1 يناير، تعود القيمة لتكلفتها التاريخية الأصلية 50,000 EGP
    val_jan_5 = ChequeSubledgerReconciliationService.compute_historical_carrying_value(cheque, date(2027, 1, 5))
    assert val_jan_5 == Decimal("50000.00")
