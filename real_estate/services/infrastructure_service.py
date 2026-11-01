# -*- coding: utf-8 -*-
"""
InfrastructureApportionmentService - محرك توزيع تكاليف محطات البنية التحتية المركزية المشتركة
(Wave 3 Phase 14 - Shared Central Infrastructure Cost Apportionment)
"""

import logging
from decimal import Decimal
from typing import List, Dict, Any

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from core.enums.document_types import DocumentType
from core.services.sequence_service import SequenceService
from real_estate.models.infrastructure import (
    SharedInfrastructureAsset,
    SharedInfrastructureApportionment,
    InfrastructureApportionmentLine,
)
from real_estate.services.accounting_service import RealEstateAccountingService

logger = logging.getLogger(__name__)


class InfrastructureApportionmentService:
    """
    خدمة توزيع تكاليف أصول البنية التحتية المركزية (محطات تكييف مركزي، محولات، جراجات)
    على الأبراج والمشروعات المستفيدة وفق نسبة المسطحات البيعية أو الأحمال التصميمية
    """

    @classmethod
    def create_apportionment(
        cls,
        infrastructure_asset: SharedInfrastructureAsset,
        total_amount: Decimal,
        beneficiary_metrics: List[Dict[str, Any]],
        allocation_basis: str = SharedInfrastructureApportionment.AllocationBasis.SELLABLE_AREA,
        notes: str = "",
        user=None
    ) -> SharedInfrastructureApportionment:
        """
        إنشاء محضر توزيع جديد واحتساب نسب التوزيع ومبالغ المشروعات المستفيدة
        beneficiary_metrics: قائمة بالقواميس [{"project": project_obj, "metric_value": Decimal('...')}]
        """
        total_dec = Decimal(str(total_amount))
        if total_dec <= Decimal('0.00'):
            raise ValidationError(_("إجمالي المبلغ المراد توزيعه يجب أن يكون أكبر من الصفر."))

        if not beneficiary_metrics:
            raise ValidationError(_("يجب تحديد المشروعات المستفيدة من البنية التحتية وقيم معايير التوزيع."))

        remaining_asset_wip = infrastructure_asset.remaining_wip_cost
        if total_dec > remaining_asset_wip:
            raise ValidationError(
                _("المبلغ المطلوب توزيعه (%(req).2f ج.م) يتجاوز الرصيد المتبقي المتاح بمحطة البنية التحتية (%(avail).2f ج.م).") % {
                    'req': total_dec,
                    'avail': remaining_asset_wip
                }
            )

        total_metric = sum(Decimal(str(item["metric_value"])) for item in beneficiary_metrics)
        if total_metric <= Decimal('0.00'):
            raise ValidationError(_("إجمالي قيم معايير التوزيع للمشروعات المستفيدة يجب أن يكون أكبر من الصفر."))

        try:
            apportionment_number = SequenceService.get_next_number(
                document_type=DocumentType.INFRASTRUCTURE_APPORTIONMENT,
                date=timezone.localdate()
            )
        except Exception as exc:
            logger.warning(f"Failed to generate sequence via SequenceService: {exc}")
            apportionment_number = f"INF-{timezone.now().strftime('%Y%m%d%H%M%S')}-{infrastructure_asset.id}"

        with transaction.atomic():
            apportionment = SharedInfrastructureApportionment.objects.create(
                apportionment_number=apportionment_number,
                infrastructure_asset=infrastructure_asset,
                apportionment_date=timezone.localdate(),
                allocation_basis=allocation_basis,
                total_apportioned_amount=total_dec,
                status=SharedInfrastructureApportionment.ApportionmentStatus.DRAFT,
                notes=notes,
                created_by=user
            )

            allocated_running = Decimal('0.00')
            for idx, item in enumerate(beneficiary_metrics):
                proj = item["project"]
                metric_val = Decimal(str(item["metric_value"]))
                alloc_pct = ((metric_val / total_metric) * Decimal('100.00')).quantize(Decimal('0.0001'))

                if idx == len(beneficiary_metrics) - 1:
                    alloc_amt = total_dec - allocated_running
                else:
                    alloc_amt = ((total_dec * alloc_pct) / Decimal('100.00')).quantize(Decimal('0.01'))
                    allocated_running += alloc_amt

                InfrastructureApportionmentLine.objects.create(
                    apportionment=apportionment,
                    beneficiary_project=proj,
                    metric_value=metric_val,
                    allocation_percentage=alloc_pct,
                    allocated_amount=alloc_amt
                )

        return apportionment

    @classmethod
    def post_apportionment(
        cls,
        apportionment: SharedInfrastructureApportionment,
        user
    ) -> SharedInfrastructureApportionment:
        """
        ترحيل محضر التوزيع وإصدار القيد الدفتري لنقل التكاليف إلى حسابات WIP المشروعات المستفيدة
        """
        if apportionment.status == SharedInfrastructureApportionment.ApportionmentStatus.POSTED:
            raise ValidationError(_("محضر التوزيع مرحل بالدفاتر مسبقاً."))

        with transaction.atomic():
            locked_app = SharedInfrastructureApportionment.objects.select_for_update().get(pk=apportionment.pk)
            if locked_app.status == SharedInfrastructureApportionment.ApportionmentStatus.POSTED:
                raise ValidationError(_("محضر التوزيع مرحل بالدفاتر مسبقاً."))

            locked_asset = SharedInfrastructureAsset.objects.select_for_update().get(pk=locked_app.infrastructure_asset_id)

            # تحديث التكاليف الموزعة على الأصل المركزي
            locked_asset.apportioned_wip_cost += locked_app.total_apportioned_amount
            locked_asset.save(update_fields=['apportioned_wip_cost', 'updated_at'])

            # إصدار القيد المحاسبي
            RealEstateAccountingService.post_infrastructure_cost_apportionment(
                apportionment=locked_app,
                user=user,
                reference=locked_app.apportionment_number
            )

            locked_app.status = SharedInfrastructureApportionment.ApportionmentStatus.POSTED
            locked_app.save(update_fields=['status', 'updated_at'])

            logger.info(
                f"Infrastructure apportionment {locked_app.apportionment_number} posted successfully "
                f"for asset {locked_asset.name} with amount {locked_app.total_apportioned_amount}"
            )
            return locked_app
