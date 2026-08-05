import os
import tempfile
import pytest
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError, PermissionDenied
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType

from core.models import (
    AttachmentCategory, FileBlob, Attachment, DraftAttachment, AttachmentAuditLog
)
from core.services.file_security_service import FileSecurityValidator
from core.services.file_blob_reference_service import FileBlobReferenceService
from core.services.attachment_retention_service import AttachmentRetentionService
from core.services.attachment_binding_service import AttachmentBindingService

User = get_user_model()


@pytest.mark.django_db
def test_file_security_validator_blocks_disguised_executables():
    """اختبار فحص التوقيع الرقمي للبايتات الحقيقية ورفض الملفات التنفيذية الضارة MZ"""
    fake_exe_content = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00"
    uploaded_file = SimpleUploadedFile("invoice.pdf", fake_exe_content, content_type="application/pdf")

    with pytest.raises(ValidationError) as exc_info:
        FileSecurityValidator.validate_file_security(uploaded_file)

    assert "ملف تنفيذي ضار" in str(exc_info.value) or "حظر أمني" in str(exc_info.value)


@pytest.mark.django_db
def test_file_blob_reference_service_atomic_locks():
    """اختبار التحكم الذري لعداد الإشارات المرجعية reference_count"""
    blob = FileBlob.objects.create(
        sha256_hash="1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        file_size=1024,
        content_type="text/plain",
        company_id=1,
        reference_count=0
    )

    assert blob.reference_count == 0

    new_count = FileBlobReferenceService.increment(blob.id)
    assert new_count == 1

    dec_count = FileBlobReferenceService.decrement(blob.id)
    assert dec_count == 0


@pytest.mark.django_db
def test_attachment_retention_policy_enforcement():
    """اختبار حظر حوكمة الحذف قبل انقضاء مدة الاستبقاء القانونية retention_days"""
    category = AttachmentCategory.objects.create(
        code="CONTRACT",
        name="عقود رسمية",
        retention_days=365
    )

    blob = FileBlob.objects.create(
        sha256_hash="abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        file_size=2048,
        content_type="application/pdf",
        company_id=1
    )

    user = User.objects.create_user(username="retention_user")
    content_type = ContentType.objects.get_for_model(user)

    attachment = Attachment.objects.create(
        content_type=content_type,
        object_id=user.id,
        category=category,
        file_blob=blob,
        original_name="employee_contract.pdf",
        uploaded_by=user
    )

    # محاولة الحذف وتوقع خطأ حوكمة الاستبقاء
    with pytest.raises(ValidationError) as exc_info:
        AttachmentRetentionService.can_delete_attachment(attachment)

    assert "سياسة استبقاء قانونية" in str(exc_info.value) or "حظر الحوكمة" in str(exc_info.value)


@pytest.mark.django_db
def test_attachment_binding_service_and_two_path_versioning():
    """اختبار ربط المسودات وتحديث الإصدارات النسخية Two-Path Versioning"""
    category = AttachmentCategory.objects.create(code="INVOICE", name="فواتير", retention_days=0)
    blob1 = FileBlob.objects.create(sha256_hash="hash1", file_size=100, content_type="pdf", company_id=1)
    blob2 = FileBlob.objects.create(sha256_hash="hash2", file_size=200, content_type="pdf", company_id=1)

    user = User.objects.create_user(username="binding_user")
    content_type = ContentType.objects.get_for_model(user)

    draft1 = DraftAttachment.objects.create(
        session_key="session1",
        file_blob=blob1,
        category=category,
        original_name="inv_v1.pdf",
        expires_at=timezone.now()
    )

    # 1. ربط النسخة الأولى Version 1
    bound1 = AttachmentBindingService.bind_draft_attachments([draft1.draft_token], user, user)
    assert len(bound1) == 1
    att1 = bound1[0]
    assert att1.version == 1
    assert att1.is_latest is True
    assert blob1.reload().reference_count == 1 if hasattr(blob1, 'reload') else FileBlob.objects.get(id=blob1.id).reference_count == 1

    # 2. ربط النسخة الثانية Version 2
    draft2 = DraftAttachment.objects.create(
        session_key="session1",
        file_blob=blob2,
        category=category,
        original_name="inv_v2.pdf",
        expires_at=timezone.now()
    )
    bound2 = AttachmentBindingService.bind_draft_attachments([draft2.draft_token], user, user)
    att2 = bound2[0]

    assert att2.version == 2
    assert att2.is_latest is True

    # التأكد من تحديث النسخة القديمة لتصبح غير الأخيرة
    att1_updated = Attachment.objects.get(id=att1.id)
    assert att1_updated.is_latest is False
