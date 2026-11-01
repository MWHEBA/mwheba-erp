# -*- coding: utf-8 -*-
"""
VariationOrderService - محرك أوامر التعديلات المعمارية وفرملة مراحل التنفيذ
MWHEBA ERP — Real Estate Architectural Variation Orders & Milestone Cut-Off Guard
"""
import logging
from decimal import Decimal
from datetime import date
from typing import Dict, Any, Optional

from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from real_estate.models.unit import PropertyUnit
from real_estate.models.contract import PropertyContract
from real_estate.models.engineering import ClientVariationOrder
from sale.models.installments import InstallmentItem

logger = logging.getLogger(__name__)


class VariationOrderService:
    """
    محرك أوامر التعديلات المعمارية وفرملة مراحل التنفيذ:
    - فحص الجدوى الهندسية ومطابقة مرحلة البناء (Structural Milestone Cut-off Guard).
    - احتساب تكلفة التكسير وإعادة البناء والمصنعيات والإشراف الهندسي.
    - جدولة قيمة أمر التعديل كقسط ملحق إضافي (is_supplemental=True) داخل خطة التقسيط.
    """

    @classmethod
    def validate_and_create_variation_order(
        cls,
        contract: PropertyContract,
        variation_type: str,
        stage_at_request: str,
        title: str,
        description: str,
        demolition_rework_cost: Decimal = Decimal('0.00'),
        material_cost: Decimal = Decimal('0.00'),
        labor_cost: Decimal = Decimal('0.00'),
        supervision_fee: Decimal = Decimal('0.00'),
        user: Any = None
    ) -> ClientVariationOrder:
        """
        إنشاء وتدقيق أمر التعديل المعماري مع تطبيق فرملة مراحل البناء الصارمة
        """
        unit = contract.unit

        order = ClientVariationOrder(
            contract=contract,
            unit=unit,
            variation_type=variation_type,
            stage_at_request=stage_at_request,
            title=title,
            description=description,
            demolition_rework_cost=demolition_rework_cost,
            material_cost=material_cost,
            labor_cost=labor_cost,
            supervision_fee=supervision_fee,
            status=ClientVariationOrder.OrderStatus.ENGINEERING_REVIEW,
            created_by=user
        )
        # تشغيل التحقق وفرملة المراحل
        order.clean()
        order.save()
        logger.info(f"🏗️ تم تسجيل أمر التعديل {order.order_number} للوحدة {unit.unit_code} بإجمالي {order.total_cost:,.2f}.")
        return order

    @classmethod
    @transaction.atomic
    def approve_and_schedule_variation_order(
        cls,
        order: ClientVariationOrder,
        approver_user: Any,
        due_date: Optional[date] = None
    ) -> InstallmentItem:
        """
        اعتماد أمر التعديل وجدولة قيمته كقسط ملحق إضافي على خطة أقساط العقد
        """
        if order.status == ClientVariationOrder.OrderStatus.APPROVED:
            raise ValidationError(_("أمر التعديل معتمد مسبقاً."))

        contract = order.contract
        plan = contract.installment_plan
        if not plan:
            raise ValidationError(_("العقد العقاري غير مرتبط بخطة تقسيط لجدولة ملحق التعديلات."))

        # التحقق النهائي من القواعد الهندسية
        order.clean()
        order.status = ClientVariationOrder.OrderStatus.APPROVED
        order.approved_by = approver_user

        # تحديد موعد سداد قسط التعديل (افتراضياً تاريخ التسليم أو التاريخ المحدد)
        target_due_date = due_date or contract.delivery_date

        next_inst_number = (plan.items.count() or 0) + 1

        supplemental_item = InstallmentItem.objects.create(
            plan=plan,
            installment_number=next_inst_number,
            due_date=target_due_date,
            principal_amount=order.total_cost,
            total_amount=order.total_cost,
            paid_amount=Decimal('0.00'),
            is_supplemental=True,
            cash_status=InstallmentItem.CashStatus.PENDING,
            notes=f"ملحق أمر تعديل رقم {order.order_number} ({order.title})"
        )

        # تحديث إجمالي خطة التقسيط
        plan.total_principal = (plan.total_principal or Decimal('0.00')) + order.total_cost
        plan.total_amount = (plan.total_amount or Decimal('0.00')) + order.total_cost
        plan.number_of_installments = plan.items.count()
        plan.save(update_fields=['total_principal', 'total_amount', 'number_of_installments'])

        order.supplemental_installment_item = supplemental_item
        order.save(update_fields=['status', 'approved_by', 'supplemental_installment_item', 'updated_at'])

        logger.info(
            f"✅ تم اعتماد أمر التعديل {order.order_number} وتوليد قسط ملحق رقم {supplemental_item.installment_number} "
            f"بمبلغ {order.total_cost:,.2f} مستحق في {target_due_date}."
        )
        return supplemental_item
