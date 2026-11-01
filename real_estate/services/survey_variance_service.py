# -*- coding: utf-8 -*-
"""
SurveyVarianceService - محرك تسوية فروق الرفع المساحي الفعلي المعتمد بعد البناء
(Wave 3 Phase 14 - As-Built Survey Variance & Tolerance Adjustment)
"""

import logging
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from core.enums.document_types import DocumentType
from core.services.sequence_service import SequenceService
from real_estate.models.contract import PropertyContract
from real_estate.models.unit import PropertyUnit
from real_estate.models.survey import AsBuiltSurveyAdjustment
from sale.models.installments import InstallmentItem

logger = logging.getLogger(__name__)


class SurveyVarianceService:
    """
    خدمة احتساب وتسوية فروق المساحة الفعلية المعتمدة بعد انتهاء البناء (As-Built Survey)
    ومقارنتها بالمساحة التعاقدية وتطبيق نسبة التفاوت التعاقدي (±3%)
    """

    @classmethod
    def calculate_and_create_adjustment(
        cls,
        contract: PropertyContract,
        surveyed_gross_area: Decimal,
        tolerance_percentage: Decimal = Decimal('3.00'),
        notes: str = "",
        user=None
    ) -> AsBuiltSurveyAdjustment:
        """
        إنشاء ملحق تسوية مساحية ومقارنة المساحات واحتساب الفارق المالي
        """
        if contract.status not in [
            PropertyContract.ContractStatus.ACTIVE,
            PropertyContract.ContractStatus.UNDER_APPROVAL
        ]:
            raise ValidationError(
                _("لا يمكن إجراء تسوية رفع مساحي لعقد غير سارٍ (الحالة: %(status)s).") % {
                    'status': contract.get_status_display()
                }
            )

        unit = contract.unit
        surveyed_dec = Decimal(str(surveyed_gross_area))
        contract_area = Decimal(str(unit.gross_area))

        if surveyed_dec <= Decimal('0.00'):
            raise ValidationError(_("المساحة الفعلية المعتمدة بالرفع المساحي يجب أن تكون أكبر من الصفر."))

        # احتساب سعر المتر التعاقدي الفعلي
        if unit.meter_price and unit.meter_price > Decimal('0.00'):
            meter_price = unit.meter_price
        elif contract_area > Decimal('0.00'):
            meter_price = (contract.final_contract_price / contract_area).quantize(Decimal('0.01'))
        else:
            meter_price = Decimal('0.00')

        try:
            adjustment_number = SequenceService.get_next_number(
                document_type=DocumentType.SURVEY_ADJUSTMENT,
                date=timezone.localdate()
            )
        except Exception as exc:
            logger.warning(f"Failed to generate sequence via SequenceService: {exc}")
            adjustment_number = f"SRV-{timezone.now().strftime('%Y%m%d%H%M%S')}-{unit.id}"

        adjustment = AsBuiltSurveyAdjustment.objects.create(
            adjustment_number=adjustment_number,
            contract=contract,
            unit=unit,
            contract_gross_area=contract_area,
            surveyed_gross_area=surveyed_dec,
            contract_meter_price=meter_price,
            contractual_tolerance_percentage=tolerance_percentage,
            status=AsBuiltSurveyAdjustment.AdjustmentStatus.DRAFT,
            notes=notes,
            created_by=user
        )
        return adjustment

    @classmethod
    def approve_adjustment(
        cls,
        adjustment: AsBuiltSurveyAdjustment,
        approver_user
    ) -> AsBuiltSurveyAdjustment:
        """
        اعتماد ملحق التسوية المساحية هندسياً وقانونياً
        """
        if adjustment.status != AsBuiltSurveyAdjustment.AdjustmentStatus.DRAFT:
            raise ValidationError(_("ملحق التسوية ليس في حالة مسودة للاعتماد."))

        adjustment.status = AsBuiltSurveyAdjustment.AdjustmentStatus.APPROVED
        adjustment.approved_by = approver_user
        adjustment.save(update_fields=['status', 'approved_by', 'updated_at'])
        return adjustment

    @classmethod
    def execute_adjustment(
        cls,
        adjustment: AsBuiltSurveyAdjustment,
        user
    ) -> AsBuiltSurveyAdjustment:
        """
        تنفيذ التسوية المساحية:
        1. تحديث مساحة الوحدة العقارية للمساحة الفعلية المعتمدة
        2. في حالة الزيادة (+Δ Area): إضافة قسط تسوية ختامي بجدول الأقساط وزيادة قيمة العقد
        3. في حالة العجز (-Δ Area): تخفيض قيمة الأقساط الأخيرة غير المسددة وتخفيض قيمة العقد
        """
        with transaction.atomic():
            locked_adj = AsBuiltSurveyAdjustment.objects.select_for_update().get(pk=adjustment.pk)
            if locked_adj.status == AsBuiltSurveyAdjustment.AdjustmentStatus.EXECUTED:
                raise ValidationError(_("ملحق التسوية المساحية تم تنفيذه مسبقاً."))

            locked_contract = PropertyContract.objects.select_for_update().get(pk=locked_adj.contract_id)
            locked_unit = PropertyUnit.objects.select_for_update().get(pk=locked_adj.unit_id)

            # 1. تحديث مساحة الوحدة
            locked_unit.gross_area = locked_adj.surveyed_gross_area
            locked_unit.status_version += 1
            locked_unit.save(update_fields=['gross_area', 'status_version'])

            plan = locked_contract.installment_plan

            # 2. معالجة الأثر المالي في حال تجاوز نسبة التفاوت
            if locked_adj.adjustment_type == AsBuiltSurveyAdjustment.AdjustmentType.SURPLUS_CHARGE:
                fin_var = locked_adj.financial_variance

                if plan:
                    next_num = plan.items.count() + 1
                    InstallmentItem.objects.create(
                        plan=plan,
                        installment_number=next_num,
                        due_date=locked_contract.delivery_date,
                        principal_amount=fin_var,
                        interest_amount=Decimal('0.00'),
                        total_amount=fin_var,
                        paid_amount=Decimal('0.00'),
                        paid_principal=Decimal('0.00'),
                        cash_status=InstallmentItem.CashStatus.PENDING,
                        is_overrun_adjusted=True,
                        is_supplemental=True,
                        notes=f"قسط تسوية زيادة مساحة الرفع المساحي الفعلي ({locked_adj.area_variance} م²)"
                    )
                    plan.total_principal += fin_var
                    plan.total_amount += fin_var
                    plan.number_of_installments = next_num
                    plan.save(update_fields=['total_principal', 'total_amount', 'number_of_installments'])

                locked_contract.final_contract_price += fin_var
                locked_contract.save(update_fields=['final_contract_price', 'updated_at'])

            elif locked_adj.adjustment_type == AsBuiltSurveyAdjustment.AdjustmentType.DEFICIT_CREDIT:
                abs_var = abs(locked_adj.financial_variance)

                if plan:
                    unpaid_items = list(
                        plan.items.exclude(cash_status=InstallmentItem.CashStatus.COLLECTED).order_by('-due_date')
                    )
                    remaining_credit = abs_var
                    for item in unpaid_items:
                        if remaining_credit <= Decimal('0.00'):
                            break
                        deduct = min(item.principal_amount, remaining_credit)
                        item.principal_amount -= deduct
                        item.total_amount = item.principal_amount + item.interest_amount
                        item.save(update_fields=['principal_amount', 'total_amount'])
                        remaining_credit -= deduct

                    plan.total_principal = max(Decimal('0.00'), plan.total_principal - abs_var)
                    plan.total_amount = max(Decimal('0.00'), plan.total_amount - abs_var)
                    plan.save(update_fields=['total_principal', 'total_amount'])

                locked_contract.final_contract_price = max(
                    Decimal('0.00'),
                    locked_contract.final_contract_price - abs_var
                )
                locked_contract.save(update_fields=['final_contract_price', 'updated_at'])

            locked_adj.status = AsBuiltSurveyAdjustment.AdjustmentStatus.EXECUTED
            locked_adj.executed_at = timezone.now()
            locked_adj.save(update_fields=['status', 'executed_at', 'updated_at'])

            logger.info(
                f"As-built survey adjustment {locked_adj.adjustment_number} executed for unit {locked_unit.unit_code}: "
                f"type={locked_adj.adjustment_type}, financial_variance={locked_adj.financial_variance}"
            )
            return locked_adj
