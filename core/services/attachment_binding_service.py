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
        if not draft_tokens or not target_object:
            return []

        content_type = ContentType.objects.get_for_model(target_object)
        object_id = target_object.pk
        bound_attachments = []

        with transaction.atomic():
            drafts = DraftAttachment.objects.filter(draft_token__in=draft_tokens)
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
