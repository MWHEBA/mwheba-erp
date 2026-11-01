# -*- coding: utf-8 -*-
"""
OfflineSnaggingSyncService - محرك مزامنة ملاحظات الموقع الميدانية دون اتصال
MWHEBA ERP — Real Estate Offline-First Field Snagging Protocol
"""
import uuid
import logging
from typing import Dict, Any, List, Optional
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from real_estate.models.unit import PropertyUnit
from real_estate.models.engineering import UnitSnagItem

logger = logging.getLogger(__name__)


class OfflineSnaggingSyncService:
    """
    محرك المزامنة الذرية لملاحظات المعاينة الميدانية المسجلة دون اتصال (Offline IndexedDB):
    - يستقبل حزم الملاحظات المجمعة مع الصور المضغوطة بصيغة WebP (< 150KB).
    - يطبق التحديث أو الإدراج الذري غير القابل للتكرار (Idempotent Upsert) عبر client_snag_uuid.
    - يتحقق من الملاحظات الحرجة المانعة للتسليم (Handover Blockers).
    """

    MAX_PHOTO_SIZE_BYTES = 150 * 1024  # 150KB

    @classmethod
    @transaction.atomic
    def sync_batch_snags(
        cls,
        snags_payload: List[Dict[str, Any]],
        user: Any = None
    ) -> Dict[str, Any]:
        """
        مزامنة دفعة ملاحظات مجمعة مسجلة محلياً في جهاز المهندس الميداني
        """
        if not snags_payload:
            return {'total_received': 0, 'created_count': 0, 'updated_count': 0, 'snags': []}

        created_count = 0
        updated_count = 0
        synced_snags = []

        for item in snags_payload:
            client_uuid_str = item.get('client_snag_uuid')
            if not client_uuid_str:
                client_uuid = uuid.uuid4()
            else:
                try:
                    client_uuid = uuid.UUID(str(client_uuid_str))
                except ValueError:
                    client_uuid = uuid.uuid4()

            unit_id = item.get('unit_id')
            unit_code = item.get('unit_code')

            unit = None
            if unit_id:
                unit = PropertyUnit.objects.filter(pk=unit_id).first()
            elif unit_code:
                unit = PropertyUnit.objects.filter(unit_code=unit_code).first()

            if not unit:
                raise ValidationError(_("الوحدة العقارية المحددة للملاحظة %(uuid)s غير موجودة.") % {'uuid': client_uuid})

            # فحص حجم الصورة المضغوطة (WebP Base64) ألا يتجاوز 150KB
            photo_data = item.get('photo_thumbnail_webp', '')
            if photo_data and len(photo_data.encode('utf-8')) > cls.MAX_PHOTO_SIZE_BYTES * 2:
                logger.warning(f"حجم صورة الملاحظة {client_uuid} كبير، سيتم حفظها مع التنبيه.")

            defaults = {
                'unit': unit,
                'room_location': item.get('room_location', 'الموقع العام للوحدة'),
                'category': item.get('category', UnitSnagItem.SnagCategory.PAINTING),
                'severity': item.get('severity', UnitSnagItem.SnagSeverity.MINOR),
                'description': item.get('description', ''),
                'photo_thumbnail_webp': photo_data,
                'status': item.get('status', UnitSnagItem.SnagStatus.OPEN),
                'created_by': user,
            }

            snag_obj, created = UnitSnagItem.objects.update_or_create(
                client_snag_uuid=client_uuid,
                defaults=defaults
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

            synced_snags.append(snag_obj)

        logger.info(
            f"🔄 [SnagSync] تم مزامنة {len(snags_payload)} ملاحظة: "
            f"{created_count} جديدة، {updated_count} محدثة بنجاح."
        )

        return {
            'total_received': len(snags_payload),
            'created_count': created_count,
            'updated_count': updated_count,
            'synced_codes': [s.snag_code for s in synced_snags]
        }

    @classmethod
    def verify_snag_resolution(
        cls,
        snag_item: UnitSnagItem,
        engineer_user: Any,
        resolution_notes: str = ''
    ) -> UnitSnagItem:
        """
        اعتماد وإغلاق الملاحظة الميدانية رسمياً بعد إتمام الإصلاحات
        """
        snag_item.status = UnitSnagItem.SnagStatus.VERIFIED_BY_ENGINEER
        snag_item.verified_at = timezone.now()
        if resolution_notes:
            snag_item.resolution_notes = resolution_notes
        snag_item.save(update_fields=['status', 'verified_at', 'resolution_notes', 'updated_at'])
        return snag_item

    @classmethod
    def check_unit_handover_blockers(cls, unit: PropertyUnit) -> Dict[str, Any]:
        """
        فحص هل توجد ملاحظات حرجة مانعة لاستلام وتسليم الوحدة (Handover Blockers)
        """
        blockers = list(
            unit.snag_items.filter(
                severity=UnitSnagItem.SnagSeverity.CRITICAL_BLOCKER,
                status__in=[UnitSnagItem.SnagStatus.OPEN, UnitSnagItem.SnagStatus.IN_PROGRESS]
            )
        )

        is_blocked = len(blockers) > 0
        return {
            'is_blocked': is_blocked,
            'blockers_count': len(blockers),
            'blocker_codes': [b.snag_code for b in blockers],
            'can_issue_handover': not is_blocked
        }

    @classmethod
    def check_unit_handover_readiness(cls, unit: PropertyUnit) -> Dict[str, Any]:
        """
        فحص هل الوحدة جاهزة للتسليم النهائي وخالية من الملاحظات الفنية الحرجة
        """
        res = cls.check_unit_handover_blockers(unit)
        res['is_ready_for_handover'] = res['can_issue_handover']
        return res
