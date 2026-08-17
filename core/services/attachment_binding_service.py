from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils.translation import gettext_lazy as _

from core.models import Attachment, DraftAttachment, AttachmentAuditLog
from core.services.file_blob_reference_service import FileBlobReferenceService


class AttachmentBindingService:
    """
    خدمة ربط المسودات وتطبيق المسار المزدوج للإصدارات (AttachmentBindingService)
    """

    @classmethod
    def bind_draft_attachments(cls, draft_tokens: list, target_object, user) -> list:
        """
        ربط قائمة المسودات المؤقتة برمز draft_tokens مع الكائن النهائي بـ Generic Foreign Key
        """
        clean_tokens = [str(t).strip() for t in draft_tokens if t and str(t).strip()]
        if not clean_tokens or not target_object:
            return []

        content_type = ContentType.objects.get_for_model(target_object)
        object_id = target_object.pk
        bound_attachments = []

        with transaction.atomic():
            drafts = DraftAttachment.objects.filter(draft_token__in=clean_tokens)
            for draft in drafts:
                # العزل الأمني للشركات
                company_id = getattr(target_object, 'company_id', 1) or 1
                if draft.file_blob.company_id != company_id:
                    raise PermissionDenied(_("حظر الحوكمة: لا يمكن ربط مرفق تابع لشركة مختلفة."))

                # تطبيق المسار المزدوج للإصدارات (Two-Path Versioning Creation Flow)
                existing_latest = Attachment.objects.select_for_update().filter(
                    content_type=content_type,
                    object_id=object_id,
                    category=draft.category,
                    is_latest=True,
                    deleted_at__isnull=True
                ).first()

                new_version = 1
                if existing_latest:
                    new_version = existing_latest.version + 1
                    existing_latest.is_latest = False
                    existing_latest.save(update_fields=['is_latest'])

                # إنشاء كائن الـ Attachment النهائي
                attachment = Attachment.objects.create(
                    content_type=content_type,
                    object_id=object_id,
                    category=draft.category,
                    file_blob=draft.file_blob,
                    original_name=draft.original_name,
                    version=new_version,
                    is_latest=True,
                    uploaded_by=user
                )

                # زيادة العداد الذري
                FileBlobReferenceService.increment(draft.file_blob_id)

                # إنشاء سجل التدقيق
                AttachmentAuditLog.objects.create(
                    attachment=attachment,
                    action='UPLOADED' if new_version == 1 else 'REPLACED',
                    performed_by=user,
                    user_name_snapshot=user.username if user else 'SYSTEM',
                    user_email_snapshot=getattr(user, 'email', '')
                )

                bound_attachments.append(attachment)
                draft.delete()

        return bound_attachments

    @classmethod
    def save_attachments_for_object(
        cls,
        files_list: list,
        target_object,
        user,
        category_code: str = 'JOURNAL_ENTRY',
        category_name: str = 'مرفقات القيود اليومية'
    ) -> list:
        """
        حفظ قائمة من الملفات المرفوعة وربطها بالكائن مباشرة مع الفحص الأمني وحساب البصمة الرقمية
        """
        if not files_list or not target_object:
            return []

        from core.models import AttachmentCategory, FileBlob, Attachment, AttachmentAuditLog
        from core.services.file_security_service import FileSecurityValidator
        from core.services.file_blob_reference_service import FileBlobReferenceService

        content_type = ContentType.objects.get_for_model(target_object)
        object_id = target_object.pk
        bound_attachments = []

        category, _ = AttachmentCategory.objects.get_or_create(
            code=category_code,
            defaults={
                'name': category_name,
                'retention_days': 0,
                'allowed_extensions': 'pdf,png,jpg,jpeg,docx,xlsx,csv'
            }
        )

        with transaction.atomic():
            for uploaded_file in files_list:
                if not uploaded_file or not hasattr(uploaded_file, 'read'):
                    continue

                # 1. الفحص الأمني للبايتات واحتساب SHA-256
                sha256_hash = FileSecurityValidator.validate_file_security(uploaded_file)

                # 2. فحص الامتداد
                ext = uploaded_file.name.split('.')[-1].lower() if '.' in uploaded_file.name else ''
                allowed = category.get_allowed_extensions_list()
                if allowed and ext not in allowed:
                    raise ValidationError(_("نوع الملف '.%(ext)s' غير مسموح به. الأنواع المسموح بها: %(allowed)s") % {'ext': ext, 'allowed': category.allowed_extensions})

                # 3. إيجاد أو إنشاء FileBlob
                file_blob = FileBlob.objects.filter(sha256_hash=sha256_hash).first()
                if not file_blob:
                    file_blob = FileBlob.objects.create(
                        sha256_hash=sha256_hash,
                        file=uploaded_file,
                        file_size=uploaded_file.size,
                        content_type=getattr(uploaded_file, 'content_type', 'application/octet-stream'),
                        company_id=getattr(target_object, 'company_id', 1) or 1,
                        reference_count=0,
                        security_status='CLEAN'
                    )

                # 4. إنشاء كائن Attachment
                attachment = Attachment.objects.create(
                    content_type=content_type,
                    object_id=object_id,
                    category=category,
                    file_blob=file_blob,
                    original_name=uploaded_file.name,
                    version=1,
                    is_latest=True,
                    uploaded_by=user if user and getattr(user, 'is_authenticated', False) else None
                )

                # 5. زيادة العداد الذري وسجل التدقيق
                FileBlobReferenceService.increment(file_blob.id)

                AttachmentAuditLog.objects.create(
                    attachment=attachment,
                    action='UPLOADED',
                    performed_by=user if user and getattr(user, 'is_authenticated', False) else None,
                    user_name_snapshot=user.username if user and getattr(user, 'is_authenticated', False) else 'SYSTEM',
                    user_email_snapshot=getattr(user, 'email', '')
                )

                bound_attachments.append(attachment)

        return bound_attachments
