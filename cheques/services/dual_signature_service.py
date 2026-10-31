# -*- coding: utf-8 -*-
"""
FIN-CHQ-DUAL-SIG: Dual Signature Verification Service
خدمة حوكمة التوقيع الثنائي للشيكات والتحقق الرقابي للشيكات ذات القيمة الكبرى
"""
import logging
from decimal import Decimal
from typing import Optional, Dict, Any

from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from cheques.models import Cheque, ChequeActionLog, ChequeActionType

logger = logging.getLogger(__name__)


class DualSignatureService:
    """
    خدمة التحقق من التوقيع الثنائي للشيكات:
    - فحص سقف القيمة أو شروط الشركة التي تتطلب توقيعاً ثنائياً
    - تعليق الشيك وحظر تداوله (CHEQUE_SIGNATURE_PENDING) لحين توثيق التوقيع الثاني
    - توثيق اعتماد المفوض الثاني بالسجلات الرقابية
    """

    DEFAULT_DUAL_SIG_THRESHOLD = Decimal("100000.00")  # الشيكات التي تتجاوز 100 ألف ج.م

    @classmethod
    def check_signature_requirements(cls, cheque: Cheque) -> Dict[str, Any]:
        """
        فحص هل يتطلب الشيك توقيعاً ثنائياً معتمداً
        """
        # إذا تم توثيق التوقيع الثاني مسبقاً في الملاحظات أو البيانات الوصفية
        is_verified = "[DUAL_SIG_VERIFIED]" in (cheque.notes or "")
        needs_dual = False

        if cheque.amount >= cls.DEFAULT_DUAL_SIG_THRESHOLD:
            needs_dual = True

        customer = getattr(cheque, "customer", None)
        if customer and getattr(customer, "requires_dual_signature", False):
            needs_dual = True

        is_pending = needs_dual and not is_verified

        return {
            "cheque_id": cheque.id,
            "amount": cheque.amount,
            "requires_dual_signature": needs_dual,
            "is_verified": is_verified,
            "is_pending": is_pending,
            "status_label": "CHEQUE_SIGNATURE_PENDING" if is_pending else "AUTHORIZED",
        }

    @classmethod
    def verify_second_signature(
        cls,
        cheque: Cheque,
        user=None,
        signer_name: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Cheque:
        """
        توثيق التوقيع الثاني للشيك واعتماده رسمياً
        """
        if not user and not signer_name:
            raise ValidationError(_("يجب تحديد المفوض بالتوقيع الثاني أو المستخدم المعتمد."))

        with transaction.atomic():
            locked_cheque = Cheque.objects.select_for_update().get(pk=cheque.pk)

            sig_tag = "[DUAL_SIG_VERIFIED]"
            if sig_tag in (locked_cheque.notes or ""):
                raise ValidationError(_("تم اعتماد التوقيع الثاني لهذا الشيك مسبقاً."))

            signer_info = signer_name or (user.get_full_name() if hasattr(user, "get_full_name") else str(user))
            tag_note = f"{sig_tag} [Signer: {signer_info} at {timezone.now().strftime('%Y-%m-%d %H:%M')}]"
            locked_cheque.notes = f"{locked_cheque.notes or ''} {tag_note} {notes or ''}".strip()
            locked_cheque.save(update_fields=['notes'])

            import uuid, hashlib
            idemp = f"DUAL-SIG-{locked_cheque.id}-{uuid.uuid4().hex[:10]}"
            payload_hash = hashlib.sha256(idemp.encode('utf-8')).hexdigest()

            ChequeActionLog.objects.create(
                cheque=locked_cheque,
                action=ChequeActionType.RECEIVE,
                action_date=timezone.localdate(),
                from_status=locked_cheque.status,
                to_status=locked_cheque.status,
                idempotency_key=idemp,
                request_payload_hash=payload_hash,
                reason=f"اعتماد التوقيع الثنائي للشيك بواسطة: {signer_info}",
                created_by=user,
            )

            logger.info(f"✅ تم اعتماد التوقيع الثاني للشيك #{locked_cheque.voucher_number} بواسطة {signer_info}")
            return locked_cheque
