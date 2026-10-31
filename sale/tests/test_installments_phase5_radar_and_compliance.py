# -*- coding: utf-8 -*-
"""
Suite for Phase 5 (Sprint 5) - Collection Radar UI, Aging Reports, Filters, & Excel/PDF Export Packs
اختبارات شاملة لشاشات رادار التحصيل، كروت المؤشرات KPI، التحصيل الميداني السريع،
السند لأمر، محرك حوافز المحصلين، شهادات المخالصة، حزمة مطابقة مراقب الحسابات، ولقطة الرادار الصباحية.
"""
from decimal import Decimal
from datetime import timedelta
import io
import pytest
import openpyxl
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.management import call_command

from customer.models import Customer
from sale.models import Sale, SalePayment
from sale.models.installments import (
    InstallmentPlan,
    InstallmentItem,
    InstallmentCashStatus,
    PaperCoverage,
    PlanStatus,
    CollectionRadarSnapshot,
)
from cheques.models.cheque import Cheque
from financial.models import Currency, CostCenter, ChartOfAccounts, AccountType
from sale.services.collector_incentive_service import CollectorIncentiveService
from sale.services.debt_clearance_service import DebtClearanceCertificateService
from sale.services.compliance_pack_service import CompliancePackService

User = get_user_model()


@pytest.fixture
def auth_user(db):
    return User.objects.create_user(
        username="phase5_auditor",
        email="p5@mwheba.com",
        password="password123",
        first_name="Ahmed",
        last_name="Radar",
        is_staff=True,
        is_superuser=True
    )


@pytest.fixture
def auth_client(client, auth_user):
    client.force_login(auth_user)
    return client


@pytest.fixture
def base_financial_setup(db):
    curr, _ = Currency.objects.get_or_create(
        code="EGP",
        defaults={
            "name": "جنيه مصري",
            "symbol": "ج.م",
            "is_active": True,
            "is_functional": True
        }
    )

    asset_type, _ = AccountType.objects.get_or_create(
        code="ASSET",
        defaults={"name": "أصول", "nature": "debit"}
    )
    liability_type, _ = AccountType.objects.get_or_create(
        code="LIABILITY",
        defaults={"name": "خصوم", "nature": "credit"}
    )
    revenue_type, _ = AccountType.objects.get_or_create(
        code="REVENUE",
        defaults={"name": "إيرادات", "nature": "credit"}
    )

    cash_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="11010",
        defaults={"name": "الخزينة الرئيسية", "account_type": asset_type, "is_active": True}
    )
    unearned_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="21400",
        defaults={"name": "أرباح تقسيط غير محققة", "account_type": liability_type, "is_active": True}
    )
    interest_income_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="42200",
        defaults={"name": "إيرادات فوائد تقسيط محققة", "account_type": revenue_type, "is_active": True}
    )

    cc, _ = CostCenter.objects.get_or_create(
        code="CC-CAIRO",
        defaults={"name": "فرع القاهرة الكبرى", "is_active": True}
    )

    return {
        "currency": curr,
        "cash_acc": cash_acc,
        "unearned_acc": unearned_acc,
        "interest_income_acc": interest_income_acc,
        "cost_center": cc,
    }


@pytest.fixture
def radar_test_dataset(db, auth_user, base_financial_setup):
    """تجهيز باقة بيانات متكاملة لرادار التحصيل: أقساط عادية، مكشوفة متأخرة، شيكات بالخزينة، ونزاع تشغيل"""
    curr = base_financial_setup["currency"]
    cc = base_financial_setup["cost_center"]
    today = timezone.localdate()

    cust1 = Customer.objects.create(name="شركة الأمل للتجارة", code="CUST-P5-001", balance=Decimal("45000.00"), is_active=True, created_by=auth_user)
    cust2 = Customer.objects.create(name="مؤسسة النور الحديثة", code="CUST-P5-002", balance=Decimal("120000.00"), is_active=True, created_by=auth_user)

    sale1 = Sale.objects.create(
        number="INV-RADAR-001",
        customer=cust1,
        date=today - timedelta(days=60),
        currency=curr,
        exchange_rate=Decimal("1.000000"),
        subtotal=Decimal("60000.00"),
        tax=Decimal("0.00"),
        total=Decimal("60000.00"),
        contract_total=Decimal("66000.00"),
        payment_status="partially_paid",
        status="confirmed",
        cost_center=cc,
        salesman=auth_user,
        created_by=auth_user,
    )

    plan1 = InstallmentPlan.objects.create(
        sale=sale1,
        customer=sale1.customer,
        plan_type=InstallmentPlan.PlanType.ASSET_FINANCING,
        number_of_installments=3,
        frequency="MONTHLY",
        total_principal=Decimal("60000.00"),
        total_markup=Decimal("6000.00"),
        total_amount=Decimal("66000.00"),
        status=PlanStatus.ACTIVE,
        start_date=today - timedelta(days=60),
        guarantor_name="محمد سالم المنوفي",
        guarantor_national_id="28501011234567",
        guarantor_phone="01012345678",
        guarantor_address="العاشر من رمضان - الشرقية",
        created_by=auth_user,
    )

    # قسط 1: محصل سابقاً
    it1 = InstallmentItem.objects.create(
        plan=plan1,
        installment_number=1,
        due_date=today - timedelta(days=30),
        principal_amount=Decimal("20000.00"),
        interest_amount=Decimal("2000.00"),
        total_amount=Decimal("22000.00"),
        paid_principal=Decimal("20000.00"),
        paid_interest=Decimal("2000.00"),
        paid_amount=Decimal("22000.00"),
        cash_status=InstallmentCashStatus.COLLECTED,
        paper_coverage=PaperCoverage.DIRECT_CASH,
        paid_date=today - timedelta(days=30),
    )

    # قسط 2: مكشوف متأخر تجاوز فترة السماح (3 أيام)
    it2 = InstallmentItem.objects.create(
        plan=plan1,
        installment_number=2,
        due_date=today - timedelta(days=10),
        grace_period_days=3,
        principal_amount=Decimal("20000.00"),
        interest_amount=Decimal("2000.00"),
        total_amount=Decimal("22000.00"),
        cash_status=InstallmentCashStatus.OVERDUE,
        paper_coverage=PaperCoverage.UNCOVERED,
    )

    # قسط 3: يستحق خلال 15 يوماً ومغطى بشيك بالخزينة
    it3 = InstallmentItem.objects.create(
        plan=plan1,
        installment_number=3,
        due_date=today + timedelta(days=15),
        principal_amount=Decimal("20000.00"),
        interest_amount=Decimal("2000.00"),
        total_amount=Decimal("22000.00"),
        cash_status=InstallmentCashStatus.PENDING,
        paper_coverage=PaperCoverage.PORTFOLIO_CHEQUE,
    )

    # شيك بالخزينة مستحق اليوم
    cheque_due_today = Cheque.objects.create(
        cheque_number="CHQ-RADAR-DUE-01",
        customer=cust1,
        amount=Decimal("25000.00"),
        due_date=today,
        issue_date=today - timedelta(days=30),
        status="IN_SAFE",
        cheque_type="RECEIVABLE",
        currency=curr,
        cost_center=cc,
    )

    # شيك مودع بالبنك برسم التحصيل
    cheque_deposited = Cheque.objects.create(
        cheque_number="CHQ-RADAR-DEP-01",
        customer=cust2,
        amount=Decimal("40000.00"),
        due_date=today + timedelta(days=5),
        issue_date=today - timedelta(days=20),
        status="BANK_DEPOSITED",
        cheque_type="RECEIVABLE",
        currency=curr,
        cost_center=cc,
    )

    # قسط معلق لنزاع جودة تشغيل (HOLD_REWORK) لمؤسسة النور
    sale2 = Sale.objects.create(
        number="INV-RADAR-002",
        customer=cust2,
        date=today - timedelta(days=15),
        currency=curr,
        exchange_rate=Decimal("1.000000"),
        subtotal=Decimal("50000.00"),
        tax=Decimal("0.00"),
        total=Decimal("50000.00"),
        contract_total=Decimal("50000.00"),
        payment_status="unpaid",
        status="confirmed",
        cost_center=cc,
        created_by=auth_user,
    )
    plan2 = InstallmentPlan.objects.create(
        sale=sale2,
        customer=sale2.customer,
        plan_type=InstallmentPlan.PlanType.ASSET_FINANCING,
        number_of_installments=1,
        frequency="MONTHLY",
        total_principal=Decimal("50000.00"),
        total_markup=Decimal("0.00"),
        total_amount=Decimal("50000.00"),
        status=PlanStatus.DISPUTED,
        start_date=today - timedelta(days=15),
        created_by=auth_user,
    )
    it_rework = InstallmentItem.objects.create(
        plan=plan2,
        installment_number=1,
        due_date=today + timedelta(days=10),
        principal_amount=Decimal("50000.00"),
        interest_amount=Decimal("0.00"),
        total_amount=Decimal("50000.00"),
        cash_status=InstallmentCashStatus.HOLD_REWORK,
        paper_coverage=PaperCoverage.UNCOVERED,
    )

    return {
        "cust1": cust1,
        "cust2": cust2,
        "sale1": sale1,
        "sale2": sale2,
        "plan1": plan1,
        "plan2": plan2,
        "items": [it1, it2, it3, it_rework],
        "cheque_due_today": cheque_due_today,
        "cheque_deposited": cheque_deposited,
        "cost_center": cc,
    }


@pytest.mark.django_db
class TestCollectionRadarUI:
    """اختبارات شاشات رادار التحصيل، كروت الـ KPI، الفلاتر المتطورة، والـ AJAX"""

    def test_radar_view_loads_successfully_with_kpi_cards(self, auth_client, radar_test_dataset):
        url = reverse("sale:installment_radar")
        response = auth_client.get(url)
        assert response.status_code == 200

        content = response.content.decode("utf-8")
        assert "رادار التحصيل وجدولة الأقساط" in content
        assert "شيكات بالخزينة مستحقة الإيداع" in content
        assert "أقساط مكشوفة تجاوزت السماح" in content
        assert "شيكات بالبنوك برسم التحصيل" in content
        assert "تدفق نقدي متوقع" in content

        # التحقق من قيم الـ KPI المحسوبة
        # 1. شيك بالخزينة مستحق اليوم = 25,000
        assert "25,000.00" in content or "25000.00" in content
        # 2. قسط مكشوف متأخر = 22,000
        assert "22,000.00" in content or "22000.00" in content
        # 3. شيكات برسم التحصيل = 40,000
        assert "40,000.00" in content or "40000.00" in content

    def test_radar_conservative_cashflow_kpi_excludes_rework_items(self, auth_client, radar_test_dataset):
        """التحقق من أن مؤشر التدفق النقدي المتوقع 30 يوماً يستبعد أقساط نزاعات الجودة HOLD_REWORK"""
        url = reverse("sale:installment_radar")
        response = auth_client.get(url)
        assert response.status_code == 200

        # القسط 3 (22,000) يستحق خلال 15 يوماً وهو سليم -> يدخل في التدفق المتوقع.
        # قسط الـ rework (50,000) يستحق خلال 10 أيام لكنه HOLD_REWORK -> يستبعد بمبدأ الحيطة والحذر.
        expected_cf = response.context["expected_cashflow_30d"]
        assert expected_cf == Decimal("22000.00")

    def test_radar_ajax_filtering_returns_json_table(self, auth_client, radar_test_dataset):
        """اختبار تصفية الرادار بالـ AJAX وتحديث الجدول ومؤشرات الـ KPI لحظياً"""
        url = reverse("sale:installment_radar")
        response = auth_client.get(
            url,
            {"cash_status": InstallmentCashStatus.OVERDUE, "ajax": "1"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        assert response.status_code == 200
        data = response.json()
        assert "table_html" in data
        assert "pagination_html" in data
        assert "INV-RADAR-001" in data["table_html"]
        assert "متأخر" in data["table_html"]


@pytest.mark.django_db
class TestQuickCollectionWorkflow:
    """اختبارات التحصيل الميداني والسريع للأقساط عبر Modal الرادار"""

    def test_quick_collection_action_posts_payment_and_updates_balances(self, auth_client, radar_test_dataset):
        it2 = radar_test_dataset["items"][1]  # قسط 2 بمبلغ 22,000
        url = reverse("sale:quick_collect_action", kwargs={"pk": it2.pk})

        payload = {
            "amount": "22000.00",
            "payment_method": "cash",
            "receipt_reference": "RCV-TEST-9988",
            "notes": "تحصيل نقدي بالخزينة من مندوب الشركة",
        }

        res = auth_client.post(url, payload, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert "تم تسجيل تحصيل" in data["message"]

        it2.refresh_from_db()
        assert it2.paid_amount == Decimal("22000.00")
        assert it2.paid_principal == Decimal("20000.00")
        assert it2.paid_interest == Decimal("2000.00")
        assert it2.cash_status == InstallmentCashStatus.COLLECTED
        assert it2.remaining_balance == Decimal("0.00")

        # التحقق من وجود سند النقدية
        payment = SalePayment.objects.filter(reference_number="RCV-TEST-9988").first()
        assert payment is not None
        assert payment.amount == Decimal("22000.00")
        assert payment.source_type == "INSTALLMENT"


@pytest.mark.django_db
class TestPromissoryNotePrintView:
    """اختبارات طباعة السند لأمر المحصن وإقرار المديونية الموحد (A4 Print Layout)"""

    def test_promissory_note_print_contains_tafqeet_guarantor_and_legal_clauses(self, auth_client, radar_test_dataset):
        sale1 = radar_test_dataset["sale1"]
        url = reverse("sale:promissory_note_print", kwargs={"pk": sale1.pk})
        res = auth_client.get(url)
        assert res.status_code == 200

        content = res.content.decode("utf-8")
        # التحقق من التفقيط العربي
        assert "فقط" in content and "لا غير" in content
        # التحقق من بيانات الكفيل المتضامن
        assert "محمد سالم المنوفي" in content
        assert "28501011234567" in content
        # التحقق من بنود المادة 232 والموطن المختار وسقوط الأجل الجبري
        assert "سقوط الأجل الجبري" in content
        assert "المادة 232" in content
        assert "الموطن المختار" in content
        assert "الحلول التأميني" in content


@pytest.mark.django_db
class TestCollectorIncentivesEngine:
    """اختبارات محرك حوافز التحصيل المتدرجة المتناقصة للمحصلين (CollectorIncentiveService)"""

    def test_collector_incentive_early_acceleration_bonus(self, radar_test_dataset):
        it = radar_test_dataset["items"][2]  # استحقاق بعد 15 يوماً
        today = timezone.localdate()

        # تحصيل اليوم (قبل الاستحقاق بـ 15 يوماً >= 5 أيام)
        res = CollectorIncentiveService.calculate_incentive(
            installment_item=it,
            payment_date=today,
            base_rate=Decimal("0.02")
        )

        assert res["early_bonus_applied"] is True
        # النسبة المطبقة = 2% أساسية + 0.5% بونص تسريع = 2.5%
        assert res["effective_rate"] == Decimal("0.025")
        # الحافز على أصل الـ 20,000 = 500 ج.م
        assert res["incentive_amount"] == Decimal("500.00")

    def test_collector_incentive_decaying_decay_factor_on_delay(self, radar_test_dataset):
        it = radar_test_dataset["items"][1]  # قسط استحق قبل 10 أيام مع سماح 3 أيام -> متأخر 7 أيام (أسبوع كامل)
        today = timezone.localdate()

        res = CollectorIncentiveService.calculate_incentive(
            installment_item=it,
            payment_date=today,
            base_rate=Decimal("0.02")
        )

        assert res["early_bonus_applied"] is False
        assert res["weeks_overdue"] == 1
        # تناقص 20% للأسبوع الأول -> معامل الجدارة 0.80
        assert res["decay_factor"] == Decimal("0.80")
        # النسبة = 0.02 * 0.80 = 0.016 (1.6%)
        assert res["effective_rate"] == Decimal("0.0160")
        assert res["incentive_amount"] == Decimal("320.00")


@pytest.mark.django_db
class TestDebtClearanceCertificateService:
    """اختبارات حوكمة وإصدار شهادات المخالصة وإبراء الذمة الرسمية (DebtClearanceCertificateService)"""

    def test_clearance_blocked_by_open_balance_and_unsettled_installments(self, radar_test_dataset):
        cust1 = radar_test_dataset["cust1"]
        check = DebtClearanceCertificateService.verify_clearance_eligibility(cust1)
        assert check["eligible"] is False
        assert any("مدين برصيد تجاري قائم" in r for r in check["blocking_reasons"])
        assert any("قسط غير مسدد" in r for r in check["blocking_reasons"])

        # محاولة الإصدار القسري يجب أن ترفع ValidationError
        with pytest.raises(ValidationError) as exc:
            DebtClearanceCertificateService.issue_clearance_certificate(cust1)
        assert "لا يمكن استخراج شهادة المخالصة" in str(exc.value)

    def test_clearance_succeeds_when_all_obligations_cleared_and_cheque_float_passed(self, auth_user, base_financial_setup):
        """التحقق من نجاح إصدار المخالصة عند تصفير الرصيد ومرور مهلة مقاصة الشيكات"""
        curr = base_financial_setup["currency"]
        cust_clean = Customer.objects.create(name="شركة الصفوة الملتزمة", code="CUST-P5-003", balance=Decimal("0.00"), is_active=True, created_by=auth_user)

        # شيك مسدد بالكامل قبل 10 أيام
        past_date = timezone.localdate() - timedelta(days=10)
        Cheque.objects.create(
            cheque_number="CHQ-CLEAN-01",
            customer=cust_clean,
            amount=Decimal("30000.00"),
            due_date=past_date,
            issue_date=past_date - timedelta(days=30),
            collection_date=past_date,
            status="COLLECTED",
            cheque_type="RECEIVABLE",
            currency=curr,
        )

        check = DebtClearanceCertificateService.verify_clearance_eligibility(cust_clean)
        assert check["eligible"] is True
        assert len(check["blocking_reasons"]) == 0

        cert = DebtClearanceCertificateService.issue_clearance_certificate(cust_clean, issued_by=auth_user)
        assert cert["verified_zero_balance"] is True
        assert cert["certificate_number"].startswith("CERT-CLR-")


@pytest.mark.django_db
class TestCompliancePackAndMorningSnapshot:
    """اختبارات حزمة مطابقة مراقب الحسابات وأمر إدارة لقطة الرادار الصباحية"""

    def test_compliance_pack_reconciliation_and_excel_generation(self, radar_test_dataset):
        summary = CompliancePackService.generate_reconciliation_summary()
        assert "schedule_unearned_interest" in summary
        assert "aging" in summary
        assert summary["total_plans_count"] >= 2

        # تصدير ملف الإكسيل والتحقق من صحة بنيته عبر openpyxl
        excel_stream = CompliancePackService.export_excel_pack()
        assert isinstance(excel_stream, io.BytesIO)

        wb = openpyxl.load_workbook(excel_stream)
        assert "مطابقة الأستاذ العام" in wb.sheetnames
        ws = wb["مطابقة الأستاذ العام"]
        assert "حزمة مطابقة مراقب الحسابات" in str(ws["A1"].value)

    def test_generate_morning_radar_snapshot_management_command(self, radar_test_dataset):
        """اختبار أمر الإدارة generate_morning_radar_snapshot وتحديث مؤشرات اللقطة"""
        call_command("generate_morning_radar_snapshot")

        today = timezone.localdate()
        global_snapshot = CollectionRadarSnapshot.objects.filter(snapshot_date=today, cost_center=None).first()
        assert global_snapshot is not None
        assert global_snapshot.total_uncovered_overdue == Decimal("22000.00")
        assert global_snapshot.total_cheques_under_collection == Decimal("40000.00")
        assert global_snapshot.expected_cashflow_30d == Decimal("22000.00")


@pytest.mark.django_db
class TestCustomerDetailInstallmentsTabIntegration:
    """اختبارات تكامل كشف حساب وبروفايل العميل مع جدول الأقساط والشيكات"""

    def test_customer_detail_view_includes_installments_and_cheques(self, auth_client, radar_test_dataset):
        cust1 = radar_test_dataset["cust1"]
        url = reverse("customer:customer_detail", kwargs={"pk": cust1.pk})
        res = auth_client.get(url)
        assert res.status_code == 200

        content = res.content.decode("utf-8")
        assert "الأقساط والشيكات" in content
        assert "مديونية الأقساط المتبقية" in content
        assert "INV-RADAR-001" in content
        assert "CHQ-RADAR-DUE-01" in content
