# -*- coding: utf-8 -*-
"""
LandownerPartnershipService - خدمة إدارة شراكات ملاك الأراضي وحصص الإيرادات والوحدات
MWHEBA ERP — Real Estate Landowner Joint Venture Service
"""
import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from real_estate.models.unit import PropertyUnit
from real_estate.models.contract import PropertyContract
from real_estate.models.partnership import (
    LandownerPartnership,
    LandownerUnitAllocation,
    LandownerRevenueShareAccrual
)

logger = logging.getLogger(__name__)


class LandownerPartnershipService:
    """
    محرك إدارة مشاريع المشاركة مع ملاك الأراضي:
    - حظر وحجز الوحدات العينية لمالك الأرض إلكترونياً (LANDOWNER_ALLOCATED).
    - حساب الاستحقاق التناسبي لمالك الأرض فور كل تحصيل نقدي (Revenue Sharing Subledger).
    - متابعة رصيد الأستاذ المساعد ومطالبات الصرف.
    """

    @classmethod
    @transaction.atomic
    def allocate_units_to_landowner(
        cls,
        partnership: LandownerPartnership,
        units: List[PropertyUnit],
        user: Any = None
    ) -> List[LandownerUnitAllocation]:
        """
        تخصيص وحدات عقارية عينية لمالك الأرض وقفلها إلكترونياً أمام مسؤولي المبيعات
        """
        if partnership.status not in [LandownerPartnership.PartnershipStatus.DRAFT, LandownerPartnership.PartnershipStatus.ACTIVE]:
            raise ValidationError(_("اتفاقية المشاركة ليست في حالة نشطة أو مسودة تسمح بتخصيص الوحدات."))

        created_allocations = []
        for unit in units:
            # قفل الوحدة في قاعدة البيانات لمنع أي تداخل متزامن
            locked_unit = PropertyUnit.objects.select_for_update().get(pk=unit.pk)

            if locked_unit.project_id != partnership.project_id:
                raise ValidationError(
                    _("الوحدة %(unit)s تتبع مشروعاً مختلفاً عن مشروع اتفاقية المشاركة.") % {'unit': locked_unit.unit_code}
                )

            if locked_unit.status != PropertyUnit.UnitStatus.AVAILABLE:
                raise ValidationError(
                    _("الوحدة %(unit)s غير متاحة للتخصيص (حالتها الحالية: %(status)s).") % {
                        'unit': locked_unit.unit_code,
                        'status': locked_unit.get_status_display()
                    }
                )

            allocation = LandownerUnitAllocation.objects.create(
                partnership=partnership,
                unit=locked_unit,
                allocated_by=user,
                notes=f"تخصيص عيني لمالك الأرض {partnership.partner_name}"
            )
            created_allocations.append(allocation)
            logger.info(f"🔒 تم قفل الوحدة {locked_unit.unit_code} وتخصيصها لمالك الأرض {partnership.partner_name}.")

        return created_allocations

    @classmethod
    @transaction.atomic
    def deallocate_unit(cls, allocation: LandownerUnitAllocation, user: Any = None):
        """
        إلغاء تخصيص وحدة لمالك الأرض وإعادتها لحالة AVAILABLE
        """
        unit_code = allocation.unit.unit_code
        allocation.delete()
        logger.info(f"🔓 تم إلغاء تخصيص الوحدة {unit_code} وإعادتها متاحة للبيع (AVAILABLE).")

    @classmethod
    @transaction.atomic
    def calculate_and_accrue_revenue_share(
        cls,
        partnership: LandownerPartnership,
        contract: PropertyContract,
        collected_amount: Decimal,
        installment_item: Any = None,
        collection_event: str = 'INSTALLMENT_COLLECTION',
        user: Any = None
    ) -> LandownerRevenueShareAccrual:
        """
        حساب وقيد الاستحقاق التناسبي لمالك الأرض من المتحصلات النقدية فور تحصيلها
        """
        if partnership.status != LandownerPartnership.PartnershipStatus.ACTIVE:
            raise ValidationError(_("اتفاقية المشاركة غير نشطة حالياً."))

        if partnership.partnership_type not in [
            LandownerPartnership.PartnershipType.REVENUE_SHARING,
            LandownerPartnership.PartnershipType.HYBRID
        ]:
            raise ValidationError(_("نوع اتفاقية المشاركة لا يتضمن اقتسام الإيرادات النقدية."))

        collected_decimal = Decimal(str(collected_amount))
        if collected_decimal <= Decimal('0.00'):
            raise ValidationError(_("يجب أن يكون المبلغ المحصل أكبر من الصفر لاحتساب استحقاق الشريك."))

        share_pct = partnership.revenue_share_percentage
        accrued = (collected_decimal * share_pct / Decimal('100.00')).quantize(Decimal('0.01'))

        accrual = LandownerRevenueShareAccrual.objects.create(
            partnership=partnership,
            contract=contract,
            installment_item=installment_item,
            collection_event=collection_event,
            collected_amount=collected_decimal,
            share_percentage=share_pct,
            accrued_amount=accrued,
            accrual_date=timezone.localdate(),
            status=LandownerRevenueShareAccrual.AccrualStatus.ACCRUED,
            created_by=user,
            notes=f"استحقاق نسبة {share_pct}% من تحصيل {collected_decimal:,.2f} على العقد {contract.contract_number}"
        )

        logger.info(
            f"💰 تم إثبات استحقاق مالك الأرض {partnership.partner_name}: "
            f"{accrued:,.2f} جنيه ({share_pct}%) من تحصيل مبلغ {collected_decimal:,.2f}."
        )
        return accrual

    @classmethod
    def get_landowner_subledger_summary(cls, partnership: LandownerPartnership) -> Dict[str, Any]:
        """
        استخراج كشف الحساب المالي التحليلي لأستاذ مالك الأرض المساعد (Landowner Payable Subledger)
        """
        accruals = partnership.revenue_accruals.all()
        total_collected = sum((a.collected_amount for a in accruals), Decimal('0.00'))
        total_accrued = sum(
            (a.accrued_amount for a in accruals if a.status != LandownerRevenueShareAccrual.AccrualStatus.REVERSED),
            Decimal('0.00')
        )
        total_disbursed = sum(
            (a.accrued_amount for a in accruals if a.status == LandownerRevenueShareAccrual.AccrualStatus.DISBURSED),
            Decimal('0.00')
        )
        pending_payable = total_accrued - total_disbursed

        allocated_units = list(partnership.unit_allocations.select_related('unit').all())
        total_allocated_units = len(allocated_units)
        handed_over_units = len([u for u in allocated_units if u.handover_status == LandownerUnitAllocation.HandoverStatus.HANDED_OVER])

        return {
            'partnership_number': partnership.partnership_number,
            'partner_name': partnership.partner_name,
            'project_name': partnership.project.name,
            'partnership_type': partnership.get_partnership_type_display(),
            'revenue_share_percentage': partnership.revenue_share_percentage,
            'total_collected_base': total_collected,
            'total_accrued_share': total_accrued,
            'total_disbursed': total_disbursed,
            'net_payable_balance': pending_payable,
            'total_allocated_units': total_allocated_units,
            'handed_over_units': handed_over_units,
            'active_units_list': [a.unit.unit_code for a in allocated_units]
        }
