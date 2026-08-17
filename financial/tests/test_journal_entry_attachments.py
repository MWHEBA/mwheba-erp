import pytest
from decimal import Decimal
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from financial.models import (
    ChartOfAccounts,
    AccountType,
    AccountingPeriod,
    FiscalYear,
    JournalEntry,
    JournalEntryLine
)
from core.models import Attachment, AttachmentCategory, FileBlob, AttachmentAuditLog
from core.services.attachment_binding_service import AttachmentBindingService

User = get_user_model()


@pytest.mark.django_db
class TestJournalEntryAttachments:

    @pytest.fixture
    def setup_data(self):
        user = User.objects.create_user(username="att_user", password="password123", is_staff=True, is_superuser=True)
        today = timezone.now().date()

        fiscal_year = FiscalYear.objects.create(
            year_code=f"FY-{today.year}-ATT",
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

        asset_type, _ = AccountType.objects.get_or_create(code="AST_ATT", defaults={"name": "Asset Att", "category": "asset"})
        rev_type, _ = AccountType.objects.get_or_create(code="REV_ATT", defaults={"name": "Revenue Att", "category": "revenue"})

        cash_acc = ChartOfAccounts.objects.create(code="10100_ATT", name="Cash Att", account_type=asset_type, is_active=True)
        rev_acc = ChartOfAccounts.objects.create(code="40100_ATT", name="Revenue Att", account_type=rev_type, is_active=True)

        return user, fiscal_year, period, cash_acc, rev_acc

    def test_save_multiple_attachments_for_journal_entry(self, setup_data):
        """اختبار حفظ عدة مرفقات مختلفة لنفس القيد المحاسبي بنجاح"""
        user, fiscal_year, period, cash_acc, rev_acc = setup_data

        entry = JournalEntry.objects.create(
            date=timezone.now().date(),
            reference="JE-ATT-001",
            description="Entry with multi attachments",
            status="draft",
            created_by=user
        )

        file1 = SimpleUploadedFile("invoice.pdf", b"%PDF-1.4 Invoice Content", content_type="application/pdf")
        file2 = SimpleUploadedFile("receipt.png", b"\x89PNG\r\n\x1a\n Receipt Image", content_type="image/png")
        file3 = SimpleUploadedFile("details.xlsx", b"PK\x03\x04 Spreadsheet Content", content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        saved_atts = AttachmentBindingService.save_attachments_for_object(
            [file1, file2, file3],
            entry,
            user,
            category_code="JOURNAL_ENTRY",
            category_name="مرفقات القيود اليومية"
        )

        assert len(saved_atts) == 3
        ct = ContentType.objects.get_for_model(entry)
        entry_attachments = Attachment.objects.filter(content_type=ct, object_id=entry.pk, deleted_at__isnull=True)
        assert entry_attachments.count() == 3

        names = [a.original_name for a in entry_attachments]
        assert "invoice.pdf" in names
        assert "receipt.png" in names
        assert "details.xlsx" in names

    def test_journal_entry_create_view_with_multiple_attachments(self, setup_data, client):
        """اختبار إنشاء قيد ورفع عدة مرفقات عبر الـ View"""
        user, fiscal_year, period, cash_acc, rev_acc = setup_data
        client.force_login(user)

        file1 = SimpleUploadedFile("contract_doc.pdf", b"%PDF-1.4 Contract", content_type="application/pdf")
        file2 = SimpleUploadedFile("payment_proof.jpg", b"\xff\xd8\xff JPEG Proof", content_type="image/jpeg")

        post_data = {
            "date": timezone.now().date().strftime("%Y-%m-%d"),
            "reference": "JE-VIEW-001",
            "description": "Created via view with attachments",
            "status": "draft",
            "lines[0][account]": str(cash_acc.id),
            "lines[0][debit]": "500.00",
            "lines[0][credit]": "0.00",
            "lines[1][account]": str(rev_acc.id),
            "lines[1][debit]": "0.00",
            "lines[1][credit]": "500.00",
            "attachments": [file1, file2]
        }

        url = reverse("financial:journal_entries_create")
        response = client.post(url, data=post_data, follow=True)

        assert response.status_code == 200
        entry = JournalEntry.objects.get(reference="JE-VIEW-001")
        assert entry.lines.count() == 2

        ct = ContentType.objects.get_for_model(entry)
        atts = Attachment.objects.filter(content_type=ct, object_id=entry.pk, deleted_at__isnull=True)
        assert atts.count() == 2

    def test_journal_entry_edit_view_adds_new_attachments(self, setup_data, client):
        """اختبار تعديل قيد مسودة وإضافة مرفقات جديدة عليه"""
        user, fiscal_year, period, cash_acc, rev_acc = setup_data
        client.force_login(user)

        entry = JournalEntry.objects.create(
            date=timezone.now().date(),
            reference="JE-EDIT-ATT",
            description="Entry to be edited",
            status="draft",
            created_by=user
        )
        JournalEntryLine.objects.create(journal_entry=entry, account=cash_acc, debit=Decimal("100"), credit=Decimal("0"))
        JournalEntryLine.objects.create(journal_entry=entry, account=rev_acc, debit=Decimal("0"), credit=Decimal("100"))

        # إضافة مرفق أولي
        initial_file = SimpleUploadedFile("initial.pdf", b"%PDF-1.4 Initial", content_type="application/pdf")
        AttachmentBindingService.save_attachments_for_object([initial_file], entry, user)

        # التعديل عبر الـ View وإضافة مرفق إضافي
        new_file = SimpleUploadedFile("additional.png", b"\x89PNG\r\n\x1a\n Add", content_type="image/png")
        edit_data = {
            "date": entry.date.strftime("%Y-%m-%d"),
            "reference": entry.reference,
            "description": "Updated Description",
            "status": "draft",
            "lines[0][account]": str(cash_acc.id),
            "lines[0][debit]": "100.00",
            "lines[0][credit]": "0.00",
            "lines[1][account]": str(rev_acc.id),
            "lines[1][debit]": "0.00",
            "lines[1][credit]": "100.00",
            "attachments": [new_file]
        }

        edit_url = reverse("financial:journal_entries_edit", kwargs={"pk": entry.pk})
        response = client.post(edit_url, data=edit_data, follow=True)

        assert response.status_code == 200
        ct = ContentType.objects.get_for_model(entry)
        atts = Attachment.objects.filter(content_type=ct, object_id=entry.pk, deleted_at__isnull=True)
        assert atts.count() == 2

    def test_secure_attachment_delete_endpoint(self, setup_data, client):
        """اختبار حذف مرفق بأمان وتوثيق الحذف في سجلات التدقيق"""
        user, fiscal_year, period, cash_acc, rev_acc = setup_data
        client.force_login(user)

        entry = JournalEntry.objects.create(
            date=timezone.now().date(),
            reference="JE-DEL-ATT",
            status="draft",
            created_by=user
        )
        file_obj = SimpleUploadedFile("to_delete.pdf", b"%PDF-1.4 Delete Me", content_type="application/pdf")
        atts = AttachmentBindingService.save_attachments_for_object([file_obj], entry, user)
        att = atts[0]

        del_url = reverse("core:secure_attachment_delete", kwargs={"pk": att.pk})
        response = client.post(del_url, content_type="application/json")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        att.refresh_from_db()
        assert att.deleted_at is not None
        assert att.is_latest is False

        # التأكد من توثيق سجل التدقيق
        audit = AttachmentAuditLog.objects.filter(attachment=att, action="DELETED").first()
        assert audit is not None
        assert audit.performed_by == user
