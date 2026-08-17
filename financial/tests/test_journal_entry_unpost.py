import pytest
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.urls import reverse

from financial.models import (
    ChartOfAccounts,
    AccountType,
    AccountingPeriod,
    FiscalYear,
    JournalEntry,
    JournalEntryLine,
    FinancialPostingReference,
    AuditTrail
)
from financial.services import LedgerCoreService
from financial.exceptions import ImmutableLedgerError, FinancialCoreError

User = get_user_model()


@pytest.mark.django_db
class TestJournalEntryUnpost:

    @pytest.fixture
    def setup_data(self):
        user = User.objects.create_user(username="unpost_user", password="password123", is_staff=True, is_superuser=True)
        today = timezone.now().date()

        fiscal_year = FiscalYear.objects.create(
            year_code=f"FY-{today.year}-UNPOST",
            name=f"Fiscal Year {today.year}",
            start_date=today.replace(month=1, day=1),
            end_date=today.replace(month=12, day=31),
            status="open"
        )

        period, _ = AccountingPeriod.objects.get_or_create(
            fiscal_year=fiscal_year,
            period_number=today.month,
            defaults={
                "name": f"Period {today.month}",
                "start_date": today.replace(day=1),
                "end_date": today.replace(day=28),
                "status": "open"
            }
        )

        asset_type, _ = AccountType.objects.get_or_create(code="AST_UNP", defaults={"name": "Asset Unpost", "category": "asset"})
        revenue_type, _ = AccountType.objects.get_or_create(code="REV_UNP", defaults={"name": "Revenue Unpost", "category": "revenue"})

        cash_acc = ChartOfAccounts.objects.create(code="10100_UNP", name="Cash Unpost", account_type=asset_type, is_active=True)
        rev_acc = ChartOfAccounts.objects.create(code="40100_UNP", name="Revenue Unpost", account_type=revenue_type, is_active=True)

        return user, fiscal_year, period, cash_acc, rev_acc

    def test_unpost_manual_journal_entry_lifecycle(self, setup_data):
        """اختبار دورة حياة إلغاء ترحيل القيد اليدوي وإعادته لمسودة وتعديله ثم إعادة ترحيله"""
        user, fiscal_year, period, cash_acc, rev_acc = setup_data

        # 1. إنشاء قيد مسودة
        draft = LedgerCoreService.create_draft_entry(
            date=timezone.now().date(),
            description="Manual Entry for Unpost Test",
            reference="REF-MANUAL-001",
            entry_type="manual",
            created_by=user,
            lines_data=[
                {"account": cash_acc, "debit": Decimal("1500.00"), "credit": Decimal("0.00")},
                {"account": rev_acc, "debit": Decimal("0.00"), "credit": Decimal("1500.00")}
            ]
        )
        assert draft.status == "draft"

        # 2. ترحيل القيد
        posted_entry = LedgerCoreService.post_entry(draft.id, user, posting_source="MANUAL_JOURNAL")
        assert posted_entry.status == "posted"
        assert posted_entry.posted_at is not None
        assert posted_entry.posted_by == user

        # 3. التأكد من منع التعديل المباشر بدون إلغاء الترحيل (الحصانة المحاسبية)
        with pytest.raises(ImmutableLedgerError):
            posted_entry.status = "draft"
            posted_entry.save(update_fields=["status"])

        # 4. إلغاء الترحيل عبر الخدمة المحاسبية المركزية
        unposted_entry = LedgerCoreService.unpost_entry(posted_entry.id, user, reason="تصحيح مبالغ القيد")
        assert unposted_entry.status == "draft"
        assert unposted_entry.posted_at is None
        assert unposted_entry.posted_by is None

        # 5. التأكد من إمكانية تعديل بنود المسودة بعد إلغاء الترحيل
        line = unposted_entry.lines.filter(account=cash_acc).first()
        line.debit = Decimal("2000.00")
        line.save()

        line2 = unposted_entry.lines.filter(account=rev_acc).first()
        line2.credit = Decimal("2000.00")
        line2.save()

        unposted_entry.refresh_from_db()
        assert unposted_entry.total_debit == Decimal("2000.00")
        assert unposted_entry.total_credit == Decimal("2000.00")
        assert unposted_entry.is_balanced is True

        # 6. إعادة ترحيل القيد بعد التعديل
        re_posted = LedgerCoreService.post_entry(unposted_entry.id, user)
        assert re_posted.status == "posted"
        assert re_posted.total_amount == Decimal("2000.00")

    def test_unpost_via_model_method(self, setup_data):
        """اختبار استدعاء unpost مباشرة من النموذج"""
        user, fiscal_year, period, cash_acc, rev_acc = setup_data

        draft = LedgerCoreService.create_draft_entry(
            date=timezone.now().date(),
            description="Model Method Unpost Test",
            reference="REF-METHOD-001",
            entry_type="manual",
            created_by=user,
            lines_data=[
                {"account": cash_acc, "debit": Decimal("800.00"), "credit": Decimal("0.00")},
                {"account": rev_acc, "debit": Decimal("0.00"), "credit": Decimal("800.00")}
            ]
        )
        posted = LedgerCoreService.post_entry(draft.id, user)
        assert posted.status == "posted"

        unposted = posted.unpost(user=user, reason="اختبار الميثود")
        assert unposted.status == "draft"

    def test_unpost_guards_and_protections(self, setup_data):
        """اختبار حواجز الحوكمة عند محاولة إلغاء ترحيل قيود مقفلة أو معكوسة أو نظامية"""
        user, fiscal_year, period, cash_acc, rev_acc = setup_data

        draft = LedgerCoreService.create_draft_entry(
            date=timezone.now().date(),
            description="Guards Test Entry",
            reference="REF-GUARD-001",
            entry_type="manual",
            created_by=user,
            lines_data=[
                {"account": cash_acc, "debit": Decimal("500.00"), "credit": Decimal("0.00")},
                {"account": rev_acc, "debit": Decimal("0.00"), "credit": Decimal("500.00")}
            ]
        )
        posted = LedgerCoreService.post_entry(draft.id, user)

        # 1. منع إلغاء ترحيل قيد مقفل
        posted.is_locked = True
        posted._allow_lock_operation = True
        posted.save(update_fields=["is_locked"])

        with pytest.raises(FinancialCoreError):
            LedgerCoreService.unpost_entry(posted.id, user)

        posted.is_locked = False
        posted._allow_lock_operation = True
        posted.save(update_fields=["is_locked"])

        # 2. منع إلغاء ترحيل قيد معكوس
        reversal = LedgerCoreService.reverse_entry(posted.id, user, reversal_reason="عكس للاختبار")
        assert reversal.status == "posted"

        with pytest.raises(FinancialCoreError):
            LedgerCoreService.unpost_entry(posted.id, user)

        # 3. منع إلغاء ترحيل القيد العكسي نفسه
        with pytest.raises(FinancialCoreError):
            LedgerCoreService.unpost_entry(reversal.id, user)

    def test_unpost_view_ajax_endpoint(self, setup_data, client):
        """اختبار استدعاء endpoint إلغاء الترحيل عبر AJAX"""
        user, fiscal_year, period, cash_acc, rev_acc = setup_data
        client.force_login(user)

        draft = LedgerCoreService.create_draft_entry(
            date=timezone.now().date(),
            description="AJAX Unpost Test",
            reference="REF-AJAX-001",
            entry_type="manual",
            created_by=user,
            lines_data=[
                {"account": cash_acc, "debit": Decimal("300.00"), "credit": Decimal("0.00")},
                {"account": rev_acc, "debit": Decimal("0.00"), "credit": Decimal("300.00")}
            ]
        )
        posted = LedgerCoreService.post_entry(draft.id, user)

        url = reverse("financial:journal_entries_unpost", kwargs={"pk": posted.pk})
        response = client.post(url, data={"reason": "إلغاء عبر الواجهة"}, content_type="application/json")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "تم إلغاء ترحيل القيد" in data["message"]

        posted.refresh_from_db()
        assert posted.status == "draft"

    def test_post_view_ajax_endpoint(self, setup_data, client):
        """اختبار استدعاء endpoint الترحيل عبر AJAX"""
        user, fiscal_year, period, cash_acc, rev_acc = setup_data
        client.force_login(user)

        draft = LedgerCoreService.create_draft_entry(
            date=timezone.now().date(),
            description="AJAX Post Test",
            reference="REF-AJAX-POST",
            entry_type="manual",
            created_by=user,
            lines_data=[
                {"account": cash_acc, "debit": Decimal("400.00"), "credit": Decimal("0.00")},
                {"account": rev_acc, "debit": Decimal("0.00"), "credit": Decimal("400.00")}
            ]
        )

        url = reverse("financial:journal_entries_post", kwargs={"pk": draft.pk})
        response = client.post(url, content_type="application/json")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "تم ترحيل القيد" in data["message"]

        draft.refresh_from_db()
        assert draft.status == "posted"

    def test_direct_edit_on_posted_entry_auto_unposts(self, setup_data, client):
        """اختبار فتح صفحة التعديل لقيد مرحل حيث يقوم النظام تلقائياً بإلغاء الترحيل وفتحه للتعديل"""
        user, fiscal_year, period, cash_acc, rev_acc = setup_data
        client.force_login(user)

        draft = LedgerCoreService.create_draft_entry(
            date=timezone.now().date(),
            description="Direct Edit Test",
            reference="REF-DIRECT-EDIT",
            entry_type="manual",
            created_by=user,
            lines_data=[
                {"account": cash_acc, "debit": Decimal("600.00"), "credit": Decimal("0.00")},
                {"account": rev_acc, "debit": Decimal("0.00"), "credit": Decimal("600.00")}
            ]
        )
        posted = LedgerCoreService.post_entry(draft.id, user)
        assert posted.status == "posted"

        # طلب صفحة التعديل مباشرة
        edit_url = reverse("financial:journal_entries_edit", kwargs={"pk": posted.pk})
        response = client.get(edit_url)
        assert response.status_code == 200

        posted.refresh_from_db()
        assert posted.status == "draft"

    def test_direct_delete_on_posted_entry_auto_unposts_and_deletes(self, setup_data, client):
        """اختبار حذف قيد مرحل مباشرة حيث يتم إلغاء ترحيله أولاً ثم حذفه نهائياً"""
        user, fiscal_year, period, cash_acc, rev_acc = setup_data
        client.force_login(user)

        draft = LedgerCoreService.create_draft_entry(
            date=timezone.now().date(),
            description="Direct Delete Test",
            reference="REF-DIRECT-DEL",
            entry_type="manual",
            created_by=user,
            lines_data=[
                {"account": cash_acc, "debit": Decimal("750.00"), "credit": Decimal("0.00")},
                {"account": rev_acc, "debit": Decimal("0.00"), "credit": Decimal("750.00")}
            ]
        )
        posted = LedgerCoreService.post_entry(draft.id, user)
        assert posted.status == "posted"
        posted_id = posted.pk

        # طلب الحذف عبر AJAX
        del_url = reverse("financial:journal_entries_delete", kwargs={"pk": posted_id})
        response = client.post(del_url, content_type="application/json")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        assert not JournalEntry.objects.filter(pk=posted_id).exists()

