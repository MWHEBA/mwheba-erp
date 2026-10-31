# -*- coding: utf-8 -*-
"""
Raw Material Price Escalation Service - محرك تعديل أسعار الورق والخامات التضخمي
مسؤول عن:
1. تطبيق شروط مراجعة الأسعار التضخمية في عقود توريد الكرتون المقسطة طويلة الأجل.
2. تعديل أصل وفائدة الأقساط المستقبلية المتبقية فقط (Future Tranches Only).
3. الحفاظ التام على الأقساط المسددة السابقة دون أي مساس دفتري.
4. إعادة موازنة رصيد الفاتورة ومجموع خطة الأقساط بالمليم وتوسيم الخطة بـ is_escalation_adjusted=True.
"""
import logging
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from sale.models.installments import InstallmentPlan, InstallmentItem

logger = logging.getLogger(__name__)


class RawMaterialEscalationService:
    """
    خدمة تعديل الأقساط اللاحقة لقفزات أسعار الخامات التضخمية
    """

    @classmethod
    @transaction.atomic
    def apply_raw_material_escalation(
        cls,
        plan: InstallmentPlan,
        escalation_percentage: Decimal,
        reason: str,
        user,
    ) -> dict:
        """
        تطبيق زيادة تضخمية بنسبة مئوية على أصل الأقساط المستقبلية المتبقية فقط
        """
        if escalation_percentage <= Decimal('0.00'):
            raise ValidationError(_("نسبة الزيادة التضخمية يجب أن تكون أكبر من الصفر."))

        if plan.status != InstallmentPlan.PlanStatus.ACTIVE:
            raise ValidationError(_("لا يمكن تعديل خطة تقسيط غير نشطة."))

        # جلب الأقساط غير المسددة التي لم يحن أجلها بعد
        future_items = plan.items.filter(
            cash_status__in=[InstallmentItem.CashStatus.PENDING, InstallmentItem.CashStatus.PARTIALLY_PAID],
        ).select_for_update().order_by('installment_number')

        if not future_items.exists():
            raise ValidationError(_("لا توجد أقساط مستقبلية متبقية قابلة للتعديل."))

        multiplier = Decimal('1.00') + (escalation_percentage / Decimal('100.00'))
        total_principal_increase = Decimal('0.00')
        total_interest_increase = Decimal('0.00')

        rate = plan.markup_rate / Decimal('100.000')

        for item in future_items:
            old_principal = item.principal_amount
            old_interest = item.interest_amount

            # تعديل أصل القسط
            new_principal = (old_principal * multiplier).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            p_diff = new_principal - old_principal

            # تعديل الفائدة التناسبية للأصل الجديد
            new_interest = (new_principal * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) if rate > 0 else old_interest
            i_diff = new_interest - old_interest

            item.principal_amount = new_principal
            item.interest_amount = new_interest
            item.total_amount = new_principal + new_interest
            item.save(update_fields=['principal_amount', 'interest_amount', 'total_amount'])

            total_principal_increase += p_diff
            total_interest_increase += i_diff

        # تحديث الخطة والفاتورة
        plan.total_principal += total_principal_increase
        plan.total_markup += total_interest_increase
        plan.total_amount += (total_principal_increase + total_interest_increase)
        plan.is_escalation_adjusted = True
        plan.save(update_fields=['total_principal', 'total_markup', 'total_amount', 'is_escalation_adjusted'])

        # تحديث الفاتورة الأم
        sale = plan.sale
        sale.markup_amount += total_interest_increase
        sale.contract_total += (total_principal_increase + total_interest_increase)
        ex_rate = Decimal(str(sale.exchange_rate or '1.000000'))
        sale.contract_total_functional = (sale.contract_total * ex_rate).quantize(Decimal('0.01'))
        sale.save(update_fields=['markup_amount', 'contract_total', 'contract_total_functional'])

        logger.info(
            f"✅ تم تطبيق الزيادة التضخمية {escalation_percentage}% على الخطة {plan.id} "
            f"بزيادة أصل {total_principal_increase} وفائدة {total_interest_increase}"
        )

        return {
            'plan_id': plan.id,
            'modified_items_count': future_items.count(),
            'total_principal_increase': total_principal_increase,
            'total_interest_increase': total_interest_increase,
            'new_contract_total': sale.contract_total,
        }
