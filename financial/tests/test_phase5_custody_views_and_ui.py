from decimal import Decimal
from datetime import date
import pytest
from django.utils import timezone
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission

from core.enums.document_types import DocumentType
from core.services.sequence_service import SequenceService
from financial.models.fiscal_year import FiscalYear
from financial.models.currency import Currency
from financial.models.chart_of_accounts import ChartOfAccounts, AccountType
from financial.models.journal_entry import AccountingPeriod, JournalEntry, JournalEntryLine
from financial.models.cost_center import CostCenter
from financial.models.custody import (
    EmployeeCustodyAdvance,
    CustodyAdvanceStatus,
    SettlementLineType,
    PettyCashSettlement,
    SettlementStatus,
    PettyCashSettlementLine,
    CustodyTransfer,
    PettyCashCount,
)
from hr.models import Employee, Department, JobTitle, WorkLocation
from hr.services.employee_service import EmployeeService
from supplier.models import Supplier
from purchase.models.purchase import Purchase

User = get_user_model()


def _fund_account(account, amount, currency, period, asset_type):
    """إيداع رصيد مثبت في الأستاذ العام"""
    entry = JournalEntry.objects.create(
        number=f"FUND-{account.code}-{timezone.now().strftime('%f')}",
        date=date(2026, 1, 1),
        accounting_period=period,
        entry_type="opening",
        status="posted",
        description=f"تغذية رصيد {account.name}",
    )
    eq_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="31010",
        defaults={"name": "رأس المال / الأرصدة الافتتاحية", "account_type": asset_type, "is_active": True}
    )
    JournalEntryLine.objects.create(
        journal_entry=entry,
        account=account,
        debit=amount,
        credit=Decimal("0.00"),
        transaction_debit=amount,
        currency=currency.code,
        exchange_rate=Decimal("1.000000"),
    )
    JournalEntryLine.objects.create(
        journal_entry=entry,
        account=eq_acc,
        debit=Decimal("0.00"),
        credit=amount,
        transaction_credit=amount,
        currency=currency.code,
        exchange_rate=Decimal("1.000000"),
    )
    return entry


@pytest.fixture
def custody_setup(db):
    user = User.objects.create_superuser(
        username=f"admin_p5_{timezone.now().strftime('%f')}",
        password="adminpassword123",
        email="admin_p5@mwheba.com",
    )

    egp, _ = Currency.objects.get_or_create(code="EGP", defaults={"name": "جنيه مصري", "is_functional": True})
    usd, _ = Currency.objects.get_or_create(code="USD", defaults={"name": "دولار أمريكي", "is_functional": False})

    fy, _ = FiscalYear.objects.get_or_create(
        year_code="FY2026",
        defaults={"name": "2026", "start_date": date(2026, 1, 1), "end_date": date(2026, 12, 31), "status": "open"}
    )
    period, _ = AccountingPeriod.objects.get_or_create(
        name="2026-P01",
        defaults={
            "fiscal_year": fy,
            "start_date": date(2026, 1, 1),
            "end_date": date(2026, 12, 31),
            "status": "open",
            "created_by": user,
        }
    )

    asset_type, _ = AccountType.objects.get_or_create(
        code="ASSET_P5",
        defaults={"name": "أصول متداولة", "category": "asset", "nature": "debit"}
    )
    expense_type, _ = AccountType.objects.get_or_create(
        code="EXP_P5",
        defaults={"name": "مصروفات عمومية", "category": "expense", "nature": "debit"}
    )
    liab_type, _ = AccountType.objects.get_or_create(
        code="LIAB_P5",
        defaults={"name": "خصوم متداولة", "category": "liability", "nature": "credit"}
    )

    treasury_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="11110",
        defaults={"name": "الخزينة المركزية", "account_type": asset_type, "is_cash_account": True, "currency": egp, "is_active": True}
    )
    custody_control, _ = ChartOfAccounts.objects.get_or_create(
        code="11130",
        defaults={"name": "حساب مراقبة العهد النقدية المؤقتة", "account_type": asset_type, "is_custody_account": True, "currency": egp, "is_active": True}
    )
    imprest_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="11135",
        defaults={"name": "صندوق النثريات المستديمة", "account_type": asset_type, "is_custody_account": True, "currency": egp, "is_active": True}
    )
    vat_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="11140",
        defaults={"name": "ضريبة القيمة المضافة المستردة", "account_type": asset_type, "currency": egp, "is_active": True}
    )
    wht_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="21110",
        defaults={"name": "مصلحة الضرائب - ضريبة الخصم والتحصيل WHT", "account_type": liab_type, "currency": egp, "is_active": True}
    )
    general_exp, _ = ChartOfAccounts.objects.get_or_create(
        code="51110",
        defaults={"name": "مصروفات إدارية وعمومية ونثريات", "account_type": expense_type, "currency": egp, "is_active": True}
    )
    discount_acc, _ = ChartOfAccounts.objects.get_or_create(
        code="41120",
        defaults={"name": "خصومات مكتسبة", "account_type": AccountType.objects.get_or_create(code="REV_P5", defaults={"name": "إيرادات", "category": "revenue", "nature": "credit"})[0], "currency": egp, "is_active": True}
    )

    _fund_account(treasury_acc, Decimal("500000.00"), egp, period, asset_type)

    dept, _ = Department.objects.get_or_create(name_ar="العمليات التشغيلية والمواقع")
    job, _ = JobTitle.objects.get_or_create(title_ar="مشرف مالي وميداني", defaults={"department": dept})
    loc, _ = WorkLocation.objects.get_or_create(
        name_ar="المقر الرئيسي - القاهرة",
        defaults={"latitude": Decimal("30.0444"), "longitude": Decimal("31.2357")}
    )

    emp1, _ = Employee.objects.get_or_create(
        employee_number=f"EMP-P5-01-{timezone.now().strftime('%f')[:4]}",
        defaults={
            "name": "أحمد محمود الميداني",
            "national_id": "29001010101011",
            "birth_date": date(1990, 1, 1),
            "gender": "male",
            "marital_status": "single",
            "hire_date": date(2023, 1, 1),
            "department": dept,
            "job_title": job,
            "created_by": user,
        }
    )
    emp2, _ = Employee.objects.get_or_create(
        employee_number=f"EMP-P5-02-{timezone.now().strftime('%f')[:4]}",
        defaults={
            "name": "محمود سامي الموقع",
            "national_id": "29001010101022",
            "birth_date": date(1992, 1, 1),
            "gender": "male",
            "marital_status": "single",
            "hire_date": date(2023, 1, 1),
            "department": dept,
            "job_title": job,
            "created_by": user,
        }
    )

    cost_cntr, _ = CostCenter.objects.get_or_create(name="مشاريع القاهرة الكبرى", defaults={"is_active": True})
    sup, _ = Supplier.objects.get_or_create(name="شركة الأمل للوازم المكتبية", defaults={"tax_number": "123456789", "is_active": True})



    return {
        "user": user,
        "egp": egp,
        "usd": usd,
        "treasury_acc": treasury_acc,
        "custody_control": custody_control,
        "imprest_acc": imprest_acc,
        "vat_acc": vat_acc,
        "wht_acc": wht_acc,
        "general_exp": general_exp,
        "discount_acc": discount_acc,
        "emp1": emp1,
        "emp2": emp2,
        "cost_cntr": cost_cntr,
        "sup": sup,
        "period": period,
        "loc": loc,
    }


@pytest.mark.django_db
class TestPhase5CustodyViewsAndUI:
    """اختبارات المرحلة 5 الشاملة: الروابط، الواجهات، الجزئيات، الأجاكس، والعمليات"""

    def test_5_1_advance_list_and_ajax_search(self, client, custody_setup):
        """اختبار قائمة العهد النقدية ودعم طلبات AJAX الجزئية طبقاً لـ Rule 6"""
        s = custody_setup
        client.force_login(s["user"])

        # إنشاء عهدة تجريبية
        adv = EmployeeCustodyAdvance.objects.create(
            advance_number=SequenceService.get_next_number(DocumentType.CUSTODY_ADVANCE),
            employee=s["emp1"],
            amount=Decimal("15000.00"),
            currency=s["egp"],
            issue_date=timezone.localdate(),
            due_date=date(2026, 12, 31),
            source_treasury=s["treasury_acc"],
            purpose="عهدة شراء مستلزمات ميدانية للموقع",
            status=CustodyAdvanceStatus.ACTIVE,
        )

        url = reverse("financial:custody_advance_list")
        resp = client.get(url)
        assert resp.status_code == 200
        assert adv.advance_number in resp.content.decode("utf-8")

        # طلب AJAX
        ajax_resp = client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        assert ajax_resp.status_code == 200
        data = ajax_resp.json()
        assert "table_html" in data
        assert "pagination_html" in data
        assert "summary_html" in data
        assert adv.advance_number in data["table_html"]

    def test_5_2_advance_detail_and_actions(self, client, custody_setup):
        """اختبار شاشة تفاصيل العهدة، وإجراءات التعزيز والإلغاء"""
        s = custody_setup
        client.force_login(s["user"])

        adv = EmployeeCustodyAdvance.objects.create(
            advance_number=SequenceService.get_next_number(DocumentType.CUSTODY_ADVANCE),
            employee=s["emp1"],
            amount=Decimal("20000.00"),
            currency=s["egp"],
            issue_date=timezone.localdate(),
            due_date=date(2026, 12, 31),
            source_treasury=s["treasury_acc"],
            purpose="سلفة مأمورية عمل",
            status=CustodyAdvanceStatus.ACTIVE,
        )
        adv.update_balance()

        # 1. عرض التفاصيل
        detail_url = reverse("financial:custody_advance_detail", kwargs={"pk": adv.id})
        resp = client.get(detail_url)
        assert resp.status_code == 200
        assert adv.advance_number in resp.content.decode("utf-8")

        # 2. تعزيز الرصيد Top-up
        top_up_url = reverse("financial:custody_advance_top_up", kwargs={"pk": adv.id})
        top_token = resp.context.get("topup_id_token", "TOP-TEST-1")
        top_resp = client.post(top_up_url, {"additional_amount": "5000.00", "notes": "تمويل إضافي معتمد", "topup_id": top_token})
        assert top_resp.status_code == 200
        adv.refresh_from_db()
        assert adv.top_up_amount == Decimal("5000.00")
        assert adv.current_balance == Decimal("25000.00")

        # 3. اختبار الإلغاء لعهدة في حالة مسودة
        draft_adv = EmployeeCustodyAdvance.objects.create(
            advance_number=SequenceService.get_next_number(DocumentType.CUSTODY_ADVANCE),
            employee=s["emp2"],
            amount=Decimal("8000.00"),
            currency=s["egp"],
            issue_date=timezone.localdate(),
            due_date=date(2026, 12, 31),
            source_treasury=s["treasury_acc"],
            purpose="عهدة ملغاة قبل الصرف",
            status=CustodyAdvanceStatus.DRAFT,
        )
        cancel_url = reverse("financial:custody_advance_cancel", kwargs={"pk": draft_adv.id})
        cancel_resp = client.post(cancel_url)
        assert cancel_resp.status_code == 200
        draft_adv.refresh_from_db()
        assert draft_adv.status == CustodyAdvanceStatus.CANCELLED

    def test_5_3_settlement_list_and_ajax_search(self, client, custody_setup):
        """اختبار قائمة سندات التسوية ودعم AJAX الجزئي"""
        s = custody_setup
        client.force_login(s["user"])

        st = PettyCashSettlement.objects.create(
            settlement_number=SequenceService.get_next_number(DocumentType.CUSTODY_SETTLEMENT),
            employee=s["emp1"],
            settlement_date=timezone.localdate(),
            status=SettlementStatus.SUBMITTED,
            total_expenses=Decimal("3500.00"),
            total_settled_amount=Decimal("3500.00"),
        )

        url = reverse("financial:custody_settlement_list")
        resp = client.get(url)
        assert resp.status_code == 200
        assert st.settlement_number in resp.content.decode("utf-8")

        ajax_resp = client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        assert ajax_resp.status_code == 200
        data = ajax_resp.json()
        assert "table_html" in data
        assert "summary_html" in data
        assert st.settlement_number in data["table_html"]

    def test_5_4_settlement_detail_and_rejection(self, client, custody_setup):
        """اختبار تفاصيل التسوية ومودال الرفض المسبب"""
        s = custody_setup
        client.force_login(s["user"])

        st = PettyCashSettlement.objects.create(
            settlement_number=SequenceService.get_next_number(DocumentType.CUSTODY_SETTLEMENT),
            employee=s["emp1"],
            settlement_date=timezone.localdate(),
            status=SettlementStatus.SUBMITTED,
            total_expenses=Decimal("2000.00"),
            total_settled_amount=Decimal("2000.00"),
        )

        detail_url = reverse("financial:custody_settlement_detail", kwargs={"pk": st.id})
        resp = client.get(detail_url)
        assert resp.status_code == 200

        # رفض بدون سبب -> يجب أن يرفض 400
        reject_url = reverse("financial:custody_settlement_reject", kwargs={"pk": st.id})
        rej_fail = client.post(reject_url, {"rejection_reason": ""})
        assert rej_fail.status_code == 400

        # رفض مسبب صحيح
        rej_success = client.post(reject_url, {"rejection_reason": "فواتير غير مختومة رسمياً ومرفوضة ضريبياً"})
        assert rej_success.status_code == 200
        st.refresh_from_db()
        assert st.status == SettlementStatus.REJECTED
        assert "فواتير غير مختومة" in st.rejection_reason

    def test_5_5_settlement_form_creation_and_safe_decimal(self, client, custody_setup):
        """اختبار إنشاء تسوية متعددة البنود مع فحص المتانة ضد InvalidOperation"""
        s = custody_setup
        client.force_login(s["user"])

        url = reverse("financial:custody_settlement_create")
        get_resp = client.get(url)
        assert get_resp.status_code == 200
        assert "purchases" in get_resp.context

        # إنشاء تسوية عبر POST مع بنود متعددة وأرقام ضريبية وموردين
        post_data = {
            "employee_id": s["emp1"].id,
            "settlement_date": str(timezone.localdate()),
            "cash_returned_to_treasury": "150.00",
            "notes": "تسوية نثريات وضيافة موقع",
            "line_type[]": [SettlementLineType.DIRECT_EXPENSE, SettlementLineType.SUPPLIER_INVOICE],
            "expense_account_id[]": [s["general_exp"].id, s["general_exp"].id],
            "supplier_id[]": ["", str(s["sup"].id)],
            "supplier_name[]": ["كافتيريا الأهرام", ""],
            "supplier_tax_id[]": ["", "987654321"],
            "purchase_invoice_id[]": ["", ""],
            "amount[]": ["1200.00", "3400.00"],
            "tax_amount[]": ["168.00", "0.00"],
            "wht_rate[]": ["1", "3"],
            "wht_amount[]": ["10.32", "102.00"],
            "discount_amount[]": ["0.00", "50.00"],
            "invoice_number[]": ["INV-9901", "SUP-441"],
            "invoice_date[]": [str(timezone.localdate()), str(timezone.localdate())],
            "description[]": ["ضيافة اجتماع خارجي", "دفعة لوازم مكتبية للموقع"],
            "cost_center_id[]": [s["cost_cntr"].id, s["cost_cntr"].id],
            "action": "save_draft",
        }

        resp = client.post(url, post_data)
        assert resp.status_code == 302
        new_set = PettyCashSettlement.objects.filter(employee=s["emp1"]).latest("id")
        assert new_set.lines.count() == 2
        assert new_set.total_expenses == Decimal("4600.00")
        assert new_set.total_tax == Decimal("168.00")
        assert new_set.cash_returned_to_treasury == Decimal("150.00")

    def test_5_6_transfer_views_and_advance_currency(self, client, custody_setup):
        """اختبار مناقلة العهد مع تحديد سلفة المُسلّم والعملة والمرفق"""
        s = custody_setup
        client.force_login(s["user"])

        adv_sender = EmployeeCustodyAdvance.objects.create(
            advance_number=SequenceService.get_next_number(DocumentType.CUSTODY_ADVANCE),
            employee=s["emp1"],
            amount=Decimal("30000.00"),
            currency=s["egp"],
            issue_date=timezone.localdate(),
            due_date=date(2026, 12, 31),
            source_treasury=s["treasury_acc"],
            purpose="عهدة موقع للمناقلة",
            status=CustodyAdvanceStatus.ACTIVE,
        )
        adv_sender.update_balance()

        url = reverse("financial:custody_transfer_create")
        get_resp = client.get(url)
        assert get_resp.status_code == 200

        post_data = {
            "from_employee_id": s["emp1"].id,
            "to_employee_id": s["emp2"].id,
            "from_advance_id": adv_sender.id,
            "currency_id": s["egp"].id,
            "amount": "10000.00",
            "notes": "مناقلة رسمية بالموقع بناء على أمر التشغيل",
        }
        post_resp = client.post(url, post_data)
        assert post_resp.status_code == 302

        adv_sender.refresh_from_db()
        assert adv_sender.transferred_out_amount == Decimal("10000.00")
        assert adv_sender.current_balance == Decimal("20000.00")

        list_resp = client.get(reverse("financial:custody_transfer_list"))
        assert list_resp.status_code == 200

    def test_5_7_official_print_views(self, client, custody_setup):
        """اختبار شاشات وقوالب الطباعة لسندات الصرف والتسوية A4 والحراري"""
        s = custody_setup
        client.force_login(s["user"])

        adv = EmployeeCustodyAdvance.objects.create(
            advance_number=SequenceService.get_next_number(DocumentType.CUSTODY_ADVANCE),
            employee=s["emp1"],
            amount=Decimal("12000.00"),
            currency=s["egp"],
            issue_date=timezone.localdate(),
            due_date=date(2026, 12, 31),
            source_treasury=s["treasury_acc"],
            purpose="سلفة مأمورية عمل",
            status=CustodyAdvanceStatus.ACTIVE,
        )

        st = PettyCashSettlement.objects.create(
            settlement_number=SequenceService.get_next_number(DocumentType.CUSTODY_SETTLEMENT),
            employee=s["emp1"],
            settlement_date=timezone.localdate(),
            status=SettlementStatus.POSTED,
            total_expenses=Decimal("8000.00"),
            total_settled_amount=Decimal("8000.00"),
        )

        # 1. طباعة السلفة A4
        print_adv_a4 = client.get(reverse("financial:custody_advance_print", kwargs={"pk": adv.id}))
        assert print_adv_a4.status_code == 200
        assert adv.advance_number in print_adv_a4.content.decode("utf-8")

        # 2. طباعة السلفة حراري
        print_adv_thermal = client.get(reverse("financial:custody_advance_print", kwargs={"pk": adv.id}) + "?format=thermal")
        assert print_adv_thermal.status_code == 200
        assert "thermal-format" in print_adv_thermal.content.decode("utf-8")

        # 3. طباعة التسوية A4 وحراري
        print_st_a4 = client.get(reverse("financial:custody_settlement_print", kwargs={"pk": st.id}))
        assert print_st_a4.status_code == 200
        assert st.settlement_number in print_st_a4.content.decode("utf-8")

        print_st_thermal = client.get(reverse("financial:custody_settlement_print", kwargs={"pk": st.id}) + "?format=thermal")
        assert print_st_thermal.status_code == 200
        assert "thermal-format" in print_st_thermal.content.decode("utf-8")
