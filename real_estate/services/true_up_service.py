# -*- coding: utf-8 -*-
"""
ProjectCostTrueUpService - محرك تسوية فروق تكاليف المشروعات المكتملة وتكلفة المبيعات
MWHEBA ERP — Real Estate Wave 3 (Phase 10: Handover & WIP Costing True-Up)
"""
import logging
from decimal import Decimal
from typing import Dict, Any, Optional

from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from real_estate.models.project import RealEstateProject
from real_estate.models.handover import PropertyHandoverReceipt
from real_estate.services.accounting_service import RealEstateAccountingService

logger = logging.getLogger(__name__)


class ProjectCostTrueUpService:
    """
    محرك تسوية فروق التكاليف الفعلية لمشروعات التطوير العقاري المكتملة:
    Variance = Total Actual WIP Incurred - Sum(Recognized Interim COGS)
    - تسوية الفروق آلياً عبر قيود محاسبية متوازنة بين (تكلفة المبيعات 51100) و(مشروعات تحت التنفيذ 12101)
    - حماية رصيد مشروعات تحت التنفيذ من التراكم أو الإقفال الخاطئ بعد تسليم الوحدات
    """

    @classmethod
    def calculate_project_cost_variance(
        cls,
        project: RealEstateProject,
        actual_wip_incurred: Decimal
    ) -> Dict[str, Any]:
        """
        احتساب فرق التكلفة الختامي بين التكاليف الفعلية المنفذة وتكلفة المبيعات المحملة مرحلياً
        """
        actual_wip = Decimal(str(actual_wip_incurred))
        if actual_wip < Decimal("0.00"):
            raise ValidationError(_("إجمالي تكاليف مشروعات تحت التنفيذ الفعلية لا يمكن أن يكون سالباً."))

        # تجميع تكلفة المبيعات التقديرية لكافة محاضر التسليم المعتمدة
        handovers = PropertyHandoverReceipt.objects.filter(
            contract__project=project,
            status=PropertyHandoverReceipt.HandoverStatus.EXECUTED
        )
        total_interim_cogs = handovers.aggregate(
            total=models.Sum('interim_cogs_amount')
        )['total'] or Decimal("0.00")

        delivered_units_count = handovers.count()
        variance = actual_wip - total_interim_cogs

        return {
            'project_id': project.id,
            'project_code': project.code,
            'project_name': project.name,
            'actual_wip_incurred': actual_wip,
            'total_interim_cogs_recognized': total_interim_cogs,
            'variance_amount': variance,
            'delivered_units_count': delivered_units_count,
            'is_overrun': variance > Decimal("0.00"),
            'is_saving': variance < Decimal("0.00"),
            'is_balanced': variance == Decimal("0.00")
        }

    @classmethod
    @transaction.atomic
    def execute_project_cost_true_up(
        cls,
        project: RealEstateProject,
        actual_wip_incurred: Decimal,
        user=None
    ) -> Dict[str, Any]:
        """
        اعتماد وترحيل قيد التسوية الختامية لفروق التكلفة عبر بوابة المحاسبة
        """
        analysis = cls.calculate_project_cost_variance(
            project=project,
            actual_wip_incurred=actual_wip_incurred
        )
        variance = analysis['variance_amount']

        entry = None
        if variance != Decimal("0.00"):
            entry = RealEstateAccountingService.post_project_cost_true_up(
                project=project,
                variance_amount=variance,
                user=user,
                reference=f"TRUEUP-{project.code}"
            )

        analysis['journal_entry'] = entry
        analysis['journal_entry_number'] = entry.number if entry else None

        logger.info(
            f"Executed project cost true-up for {project.code}: Actual WIP={analysis['actual_wip_incurred']}, "
            f"Interim COGS={analysis['total_interim_cogs_recognized']}, Variance={variance}, "
            f"Journal Entry={analysis['journal_entry_number']}"
        )
        return analysis
