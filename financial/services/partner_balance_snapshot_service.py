import logging
from decimal import Decimal
from typing import List
from financial.models.partner_currency_balance_snapshot import PartnerCurrencyBalanceSnapshot
from financial.services.partner_exposure_service import PartnerExposureService

logger = logging.getLogger(__name__)


class PartnerBalanceSnapshotService:
    """
    خدمة تحديث وبناء لقطات الانكشاف المالي للشركاء مع التزامن الآلي (Snapshot Service)
    """

    @classmethod
    def update_snapshot(cls, partner_type: str, partner_id: int):
        """
        تحديث لقطة الشريك لشخص واحد
        """
        exposure_map = PartnerExposureService.get_open_balances(partner_type, [partner_id])
        dtos = exposure_map.get(partner_id, [])

        # حذف القديم للتحديث الموحد
        PartnerCurrencyBalanceSnapshot.objects.filter(
            partner_type=partner_type,
            partner_id=partner_id
        ).delete()

        snapshots = []
        for dto in dtos:
            snapshots.append(
                PartnerCurrencyBalanceSnapshot(
                    partner_type=partner_type,
                    partner_id=partner_id,
                    currency=dto.currency,
                    debit_amount=dto.debit,
                    credit_amount=dto.credit,
                    net_balance=dto.net_balance,
                    functional_net_balance=dto.functional_net_balance,
                    nature=dto.nature
                )
            )

        if snapshots:
            PartnerCurrencyBalanceSnapshot.objects.bulk_create(snapshots)

    @classmethod
    def update_bulk_snapshots(cls, partner_type: str, partner_ids: List[int]):
        """
        تحديث دفعة لقطات
        """
        for pid in partner_ids:
            cls.update_snapshot(partner_type, pid)
