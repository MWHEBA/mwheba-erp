from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from datetime import timedelta
from core.models import Attachment


class AttachmentRetentionService:
    """
    خدمة حوكمة الاستبقاء القانوني للمستندات (AttachmentRetentionService)
    """

    @staticmethod
    def can_delete_attachment(attachment: Attachment) -> bool:
        """
        فحص هل يمكن حذف المستند نهائياً أم أنه ما زال داخل مدة الاستبقاء القانونية
        """
        category = attachment.category
        if not category or category.retention_days == 0:
            return True

        retention_days = category.retention_days
        uploaded_at = attachment.created_at
        expiry_date = uploaded_at + timedelta(days=retention_days)

        if timezone.now() < expiry_date:
            days_left = (expiry_date - timezone.now()).days
            raise ValidationError(
                _("حظر الحوكمة: المستند خاضع لسياسة استبقاء قانونية (%(days)s يوماً)، متبقي %(left)s يوماً قبل السماح بالحذف النهائي.")
                % {'days': retention_days, 'left': days_left}
            )

        return True
