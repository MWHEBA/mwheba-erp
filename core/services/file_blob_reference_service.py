from django.db import transaction
from core.models import FileBlob


class FileBlobReferenceService:
    """
    خدمة التحكم الذري لعداد الإشارات المرجعية المعتمدة على select_for_update (FileBlobReferenceService)
    """

    @staticmethod
    def increment(blob_id: int) -> int:
        with transaction.atomic():
            blob = FileBlob.objects.select_for_update().get(id=blob_id)
            blob.reference_count += 1
            blob.save(update_fields=['reference_count'])
            return blob.reference_count

    @staticmethod
    def decrement(blob_id: int) -> int:
        with transaction.atomic():
            blob = FileBlob.objects.select_for_update().get(id=blob_id)
            if blob.reference_count > 0:
                blob.reference_count -= 1
                blob.save(update_fields=['reference_count'])
            return blob.reference_count
