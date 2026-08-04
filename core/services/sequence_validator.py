# -*- coding: utf-8 -*-
"""
MWHEBA ERP - Sequence Validator Service
Validates sequence immutability and guards against manual modifications.
"""
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class SequenceValidator:
    """
    متحقق الأرقام وحامي ثبات الأرقام المرحّلة من التعديل اليدوي
    """

    @classmethod
    def validate_number_immutability(cls, instance, field_name: str, old_number: str, new_number: str, user=None):
        """
        التحقق من عدم تعديل رقم المستند المعتمد أو المرحّل
        """
        if old_number and new_number and old_number != new_number:
            # Check if document is posted / immutable
            status = getattr(instance, 'status', '').lower() if hasattr(instance, 'status') else ''
            if status in ['posted', 'confirmed', 'completed', 'approved']:
                # Audit blocked attempt
                from core.models import DocumentSequenceAudit
                from core.enums.document_types import DocumentType
                doc_type = getattr(instance, 'DOCUMENT_TYPE', DocumentType.JOURNAL_ENTRY)
                company_code = getattr(instance, 'company_code', 'DEFAULT')
                warehouse = getattr(instance, 'warehouse', None)

                DocumentSequenceAudit.objects.create(
                    event_type="MANUAL_EDIT_BLOCKED",
                    document_type=doc_type,
                    document_number=old_number,
                    company_code=company_code,
                    warehouse=warehouse,
                    user=user if (user and user.is_authenticated) else None,
                    source_type="USER" if (user and user.is_authenticated) else "SYSTEM",
                    old_value=old_number,
                    new_value=new_number,
                    reason=_("محاولة تعديل يدوية محظورة لرقم مستند معتمد أو مرحّل")
                )

                raise ValidationError(
                    _("لا يجوز تعديل رقم المستند المعتمد/المرحّل %(old)s إلى %(new)s لأسباب حوكمة الحسابات.") % {
                        'old': old_number,
                        'new': new_number,
                    }
                )
