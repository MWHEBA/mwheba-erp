from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from printing_pricing.models.order import PrintingOrder, QCSignoff


class QCSignoffService:
    """
    خدمة بوابة فحص ومراقبة الجودة الرقمية (QC Sign-off Gateway Service)
    """

    @classmethod
    @transaction.atomic
    def record_inspection(
        cls,
        order: PrintingOrder,
        inspector_name: str,
        bleed_verified: bool,
        barcode_scannable: bool,
        color_registration_passed: bool,
        physical_swatch_matched: bool,
        lamination_adhesion_passed: bool,
        ncr_sequence_verified: bool,
        sample_vault_archived: bool,
        net_quantity_approved: int,
        sample_vault_ref: str = None,
        defect_count: int = 0,
        status: str = QCSignoff.QCStatus.PASSED,
        notes: str = None,
        inspected_at=None
    ) -> QCSignoff:
        """
        تسجيل تقرير فحص الجودة الشامل
        """
        if net_quantity_approved < 0:
            raise ValidationError(str(_("الكمية الصافية المعتمدة لا يمكن أن تكون سالبة.")))

        if sample_vault_archived and not sample_vault_ref:
            # توليد رقم حرز تلقائي إذا لم يتم تمريره
            today_str = timezone.now().strftime('%y%m%d')
            sample_vault_ref = f"VLT-{today_str}-{order.id}"

        qc_obj, created = QCSignoff.objects.update_or_create(
            order=order,
            defaults={
                'inspector_name': inspector_name,
                'inspected_at': inspected_at or timezone.now(),
                'bleed_verified': bleed_verified,
                'barcode_scannable': barcode_scannable,
                'color_registration_passed': color_registration_passed,
                'physical_swatch_matched': physical_swatch_matched,
                'lamination_adhesion_passed': lamination_adhesion_passed,
                'ncr_sequence_verified': ncr_sequence_verified,
                'sample_vault_archived': sample_vault_archived,
                'sample_vault_ref': sample_vault_ref,
                'net_quantity_approved': net_quantity_approved,
                'defect_count': defect_count,
                'status': status,
                'notes': notes,
            }
        )
        return qc_obj

    @classmethod
    def get_order_qc(cls, order: PrintingOrder):
        """جلب تقرير فحص الجودة الخاص بأمر التسعير"""
        return getattr(order, 'qc_signoff', None)
