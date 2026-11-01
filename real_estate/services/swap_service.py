# -*- coding: utf-8 -*-
"""
UnitSwapService - محرك استبدال وترقية الوحدات العقارية وإعادة جدولة الأقساط
(Wave 3 Phase 13 - Unit Swap & Rescheduling Engine)
"""

import logging
from decimal import Decimal
from typing import Optional, Dict, Any

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from core.enums.document_types import DocumentType
from core.services.sequence_service import SequenceService
from real_estate.models.contract import PropertyContract
from real_estate.models.unit import PropertyUnit
from real_estate.models.resale import UnitSwapRecord
from real_estate.services.accounting_service import RealEstateAccountingService

logger = logging.getLogger(__name__)


class UnitSwapService:
    """
    خدمة الرقابة والأتمتة لمحاضر استبدال وترقية/تخفيض الوحدات العقارية:
    - التحقق الصارم من أهلية الاستبدال وحالة الوحدات
    - الانتقال الذري لحالة الوحدات (قديمة: AVAILABLE / جديدة: CONTRACTED) في عملية واحدة
    - ترحيل رصيد العقد وسعر الوحدة الجديدة
    - إعادة جدولة الفارق السعري (Re-amortization) على الأقساط المستقبلية المتبقية
    - إثبات رسوم الاستبدال الإدارية وإصدار القيد المالي عبر بوابة الحوكمة
    """

    @classmethod
    def validate_swap_eligibility(
        cls,
        contract: PropertyContract,
        old_unit: PropertyUnit,
        new_unit: PropertyUnit
    ) -> None:
        """
        التحقق من أهلية الوحدة والعقد للاستبدال
        """
        if contract.status != PropertyContract.ContractStatus.ACTIVE:
            raise ValidationError(
                _("لا يمكن إجراء استبدال لوحدة تابعة لعقد غير سارٍ (الحالة الحالية: %(status)s).") % {
                    'status': contract.get_status_display()
                }
            )

        if contract.unit_id != old_unit.id:
            raise ValidationError(
                _("الوحدة الحالية بالعقد (%(curr)s) لا تطابق الوحدة القديمة المراد استبدالها (%(old)s).") % {
                    'curr': contract.unit.unit_code,
                    'old': old_unit.unit_code
                }
            )

        # حظر استبدال الوحدات التي تم تسليمها بالفعل للعميل
        if old_unit.status in [PropertyUnit.UnitStatus.DELIVERED, PropertyUnit.UnitStatus.DELIVERED_DEEMED]:
            raise ValidationError(
                _("لا يمكن استبدال الوحدة %(code)s نظراً لأنه تم تسليمها للعميل مسبقاً بمحضر استلام معتمد.") % {
                    'code': old_unit.unit_code
                }
            )

        if new_unit.id == old_unit.id:
            raise ValidationError(_("لا يجوز اختيار نفس الوحدة الحالية كبديل."))

        if new_unit.status != PropertyUnit.UnitStatus.AVAILABLE:
            raise ValidationError(
                _("الوحدة الجديدة المراد الترقية/التبديل إليها ليست متاحة للبيع (الحالة: %(status)s).") % {
                    'status': new_unit.get_status_display()
                }
            )

        if new_unit.status == PropertyUnit.UnitStatus.LANDOWNER_ALLOCATED:
            raise ValidationError(
                _("الوحدة الجديدة مخصصة لمالك الأرض ضمن اتفاقية المشاركة ولا يجوز التعاقد عليها.")
            )

    @classmethod
    def create_swap_record(
        cls,
        contract: PropertyContract,
        new_unit: PropertyUnit,
        administrative_fee: Decimal = Decimal('0.00'),
        settlement_method: str = UnitSwapRecord.SettlementMethod.RE_AMORTIZE_EXISTING,
        notes: str = "",
        user=None
    ) -> UnitSwapRecord:
        """
        إنشاء محضر استبدال جديد في حالة مسودة
        """
        old_unit = contract.unit
        cls.validate_swap_eligibility(contract, old_unit, new_unit)

        try:
            swap_number = SequenceService.get_next_number(
                document_type=DocumentType.UNIT_SWAP,
                date=timezone.localdate()
            )
        except Exception as exc:
            logger.warning(f"Failed to generate sequence via SequenceService: {exc}")
            swap_number = f"SWP-{timezone.now().strftime('%Y%m%d%H%M%S')}-{contract.id}"

        old_price = Decimal(str(contract.final_contract_price))
        new_price = Decimal(str(getattr(new_unit, 'total_price', getattr(new_unit, 'final_price', Decimal('0.00')))))
        admin_fee = Decimal(str(administrative_fee or Decimal('0.00')))

        swap_record = UnitSwapRecord.objects.create(
            swap_number=swap_number,
            contract=contract,
            customer=contract.customer,
            old_unit=old_unit,
            new_unit=new_unit,
            old_unit_price=old_price,
            new_unit_price=new_price,
            price_difference=new_price - old_price,
            administrative_fee=admin_fee,
            settlement_method=settlement_method,
            notes=notes,
            created_by=user,
            status=UnitSwapRecord.SwapStatus.DRAFT
        )
        return swap_record

    @classmethod
    def execute_unit_swap(
        cls,
        swap_record: UnitSwapRecord,
        user,
        payment_account=None
    ) -> UnitSwapRecord:
        """
        تنفيذ محضر الاستبدال ذرياً:
        1. قفل السجلات لمنع تضارب العمليات المتزامنة
        2. قلب حالات الوحدات (القديمة -> AVAILABLE، الجديدة -> CONTRACTED)
        3. تحديث بيانات العقد وسعر الوحدة
        4. إعادة جدولة الفارق السعري وتوزيعه على الأقساط المتبقية
        5. إثبات رسوم الاستبدال الإدارية دفترياً
        """
        with transaction.atomic():
            locked_swap = UnitSwapRecord.objects.select_for_update().get(pk=swap_record.pk)
            if locked_swap.status == UnitSwapRecord.SwapStatus.EXECUTED:
                raise ValidationError(_("محضر الاستبدال تم تنفيذه وترحيله مسبقاً."))

            if locked_swap.status == UnitSwapRecord.SwapStatus.CANCELLED:
                raise ValidationError(_("محضر الاستبدال ملغي ولا يمكن تنفيذه."))

            locked_contract = PropertyContract.objects.select_for_update().get(pk=locked_swap.contract_id)
            locked_old = PropertyUnit.objects.select_for_update().get(pk=locked_swap.old_unit_id)
            locked_new = PropertyUnit.objects.select_for_update().get(pk=locked_swap.new_unit_id)

            cls.validate_swap_eligibility(locked_contract, locked_old, locked_new)

            # 1. التبديل الذري لحالات الوحدات
            locked_old.status = PropertyUnit.UnitStatus.AVAILABLE
            locked_old.status_version += 1
            locked_old.save(update_fields=['status', 'status_version'])

            locked_new.status = PropertyUnit.UnitStatus.CONTRACTED
            locked_new.status_version += 1
            locked_new.save(update_fields=['status', 'status_version'])

            # 2. تحديث العقد العقاري بالوحدة الجديدة والسعر الجديد
            locked_contract.unit = locked_new
            locked_contract.final_contract_price = locked_swap.new_unit_price
            locked_contract.save(update_fields=['unit', 'final_contract_price', 'updated_at'])

            # 3. إعادة جدولة الأقساط المتبقية إذا وجدت خطة تقسيط
            diff = locked_swap.price_difference
            plan = locked_contract.installment_plan
            if plan and diff != Decimal("0.00"):
                from sale.models.installments import InstallmentItem
                unpaid_items = list(plan.items.exclude(cash_status=InstallmentItem.CashStatus.COLLECTED).order_by('due_date'))
                if unpaid_items:
                    num_items = Decimal(str(len(unpaid_items)))
                    per_item_diff = (diff / num_items).quantize(Decimal("0.01"))
                    allocated_diff = Decimal("0.00")

                    for idx, item in enumerate(unpaid_items):
                        if idx == len(unpaid_items) - 1:
                            item_adj = diff - allocated_diff
                        else:
                            item_adj = per_item_diff
                            allocated_diff += item_adj

                        item.principal_amount = max(Decimal("0.00"), item.principal_amount + item_adj)
                        item.total_amount = item.principal_amount + item.interest_amount
                        item.save(update_fields=['principal_amount', 'total_amount'])

                    # تحديث مجاميع الخطة
                    plan.total_principal = max(Decimal("0.00"), plan.total_principal + diff)
                    plan.total_amount = plan.total_principal + plan.total_markup
                    plan.save(update_fields=['total_principal', 'total_amount'])

            # 4. إثبات رسوم الاستبدال الإدارية محاسبياً
            if locked_swap.administrative_fee > Decimal("0.00") and payment_account:
                RealEstateAccountingService.post_unit_swap_administrative_fee(
                    swap_record=locked_swap,
                    payment_account=payment_account,
                    user=user,
                    reference=locked_swap.swap_number
                )

            # 5. اعتماد وتنفيذ محضر الاستبدال
            locked_swap.status = UnitSwapRecord.SwapStatus.EXECUTED
            locked_swap.executed_at = timezone.now()
            locked_swap.save(update_fields=['status', 'executed_at', 'updated_at'])

            logger.info(
                f"Unit swap executed successfully: Contract {locked_contract.contract_number} "
                f"swapped from {locked_old.unit_code} to {locked_new.unit_code} by {user.username}"
            )
            return locked_swap
