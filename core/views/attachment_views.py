import os
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _

from core.models import Attachment, AttachmentAuditLog
from core.services.file_security_service import FileSecurityValidator


@login_required
def secure_attachment_download_view(request, pk):
    """
    بوابة التنزيل التدفقية المباشرة والمحمية بالصلاحيات (Secure Streamed Download Gateway)
    /core/attachments/<pk>/download/
    """
    attachment = get_object_or_404(Attachment, pk=pk, deleted_at__isnull=True)
    category = attachment.category

    # 1. فحص الصلاحية الخاصة بالفئة إن وجدت
    if category.permission_required:
        if not request.user.has_perm(category.permission_required):
            return HttpResponseForbidden(_("ليس لديك الصلاحية المطلوبة لتنزيل هذا المستند."))

    blob = attachment.file_blob
    file_path = blob.file.path

    if not os.path.exists(file_path):
        raise Http404(_("الملف الفيزيائي غير موجود على خادم التخزين."))

    # 2. فحص سلامة SHA-256 إن كانت الفئة تشترط ذلك
    if category.requires_integrity_check:
        if not FileSecurityValidator.verify_file_integrity(file_path, blob.sha256_hash):
            return HttpResponseForbidden(_("فشل فحص سلامة البصمة الرقمية للمستند (SHA-256 Mismatch)."))

    # 3. توثيق حركة التنزيل في سجلات التدقيق
    AttachmentAuditLog.objects.create(
        attachment=attachment,
        action='DOWNLOADED',
        performed_by=request.user,
        user_name_snapshot=request.user.username,
        user_email_snapshot=getattr(request.user, 'email', ''),
        ip_address=request.META.get('REMOTE_ADDR')
    )

    # 4. بث الملف المباشر لعدم استهلاك ذاكرة الخادم
    response = FileResponse(
        open(file_path, 'rb'),
        as_attachment=True,
        filename=attachment.original_name
    )
    return response
