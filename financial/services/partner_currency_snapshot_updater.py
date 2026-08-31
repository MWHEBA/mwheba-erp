import logging
from decimal import Decimal
from typing import Optional, Any
from django.db import transaction

logger = logging.getLogger("financial.services.partner_currency_snapshot_updater")


class PartnerCurrencySnapshotUpdater:
    """
    CQRS Read Model Snapshot Updater Event Consumer
    معالج تحديث لقطات الأرصدة المالية السريعة للشركاء (CQRS Read Model)
    يتم استدعاؤه عقب كل حدث مالي (Payment Posted, Allocation Applied, Reversal, Manual Adjustment)
    """

    @classmethod
    def handle_partner_balance_event(
        cls,
        partner_type: str,
        partner_id: int,
        currency_code: str = "EGP",
        event_type: str = "ALLOCATION_UPDATE"
    ) -> None:
        """
        تحديث لقطات الأرصدة المتاحة بالشريكة والمزامنة التلقائية مع محرك الأرصدة
        """
        try:
            from financial.services.partner_advance_service import PartnerAdvanceService
            if partner_type.lower() == "customer":
                from customer.models import Customer
                partner = Customer.objects.filter(pk=partner_id).first()
            else:
                from supplier.models import Supplier
                partner = Supplier.objects.filter(pk=partner_id).first()

            if partner:
                PartnerAdvanceService.rebuild_all_snapshots(partner)
                logger.info(f"CQRS Snapshot updated for {partner_type} #{partner_id} [{currency_code}] on event {event_type}.")
        except Exception as e:
            logger.error(f"Error updating Partner Currency Snapshot for {partner_type} #{partner_id}: {str(e)}")

    @classmethod
    def trigger_on_commit(
        cls,
        partner_type: str,
        partner_id: int,
        currency_code: str = "EGP",
        event_type: str = "ALLOCATION_UPDATE"
    ) -> None:
        """
        تسجيل حدث تحديث الـ Snapshot ليتم تنفيذه بأمان عقب اتمام الترانزاكشن (on_commit)
        """
        transaction.on_commit(
            lambda: cls.handle_partner_balance_event(
                partner_type=partner_type,
                partner_id=partner_id,
                currency_code=currency_code,
                event_type=event_type
            )
        )
