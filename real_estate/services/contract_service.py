# -*- coding: utf-8 -*-
"""
PropertyContractService - خدمة إدارة ومزامنة العقود العقارية وحصص الملكية
"""
import logging
from decimal import Decimal
from typing import List, Dict, Any, Optional

from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from real_estate.models.contract import PropertyContract, ContractCoOwner

logger = logging.getLogger(__name__)


class PropertyContractService:
    """
    محرك حوكمة العقود العقارية ومزامنة حصص الملكية للشركاء
    """

    @classmethod
    def sync_contract_ownership(
        cls,
        contract_id: int,
        primary_owner_share: Decimal,
        co_owners_data: List[Dict[str, Any]],
        user=None
    ) -> PropertyContract:
        """
        مزامنة حصص الملكية للمشتري الرئيسي والشركاء المتضامنين داخل معاملة ذرية مع قفل العقد
        """
        with transaction.atomic():
            contract = PropertyContract.objects.select_for_update().get(pk=contract_id)

            primary_share = Decimal(str(primary_owner_share)).quantize(Decimal('0.01'))
            if primary_share < Decimal('0.00') or primary_share > Decimal('100.00'):
                raise ValidationError(
                    _("نسبة ملكية العميل الرئيسي يجب أن تكون بين 0.00%% و 100.00%% (القيمة الحالية: %(p)s%%).") % {
                        'p': primary_share
                    }
                )

            for item in co_owners_data:
                share = Decimal(str(item.get('share_percentage', '0'))).quantize(Decimal('0.01'))
                if share <= Decimal('0.00') or share > Decimal('100.00'):
                    raise ValidationError(
                        _("نسبة ملكية الشريك يجب أن تكون أكبر من 0%% وحتى 100.00%% (القيمة المدخلة: %(c)s%%).") % {
                            'c': share
                        }
                    )

            co_owners_total = sum(
                Decimal(str(item.get('share_percentage', '0'))).quantize(Decimal('0.01'))
                for item in co_owners_data
            )
            total_share = primary_share + co_owners_total
            if total_share != Decimal('100.00'):
                raise ValidationError(
                    _("إجمالي نسب الملكية في العقد يجب أن يساوي 100.00%% بالضبط (المالك الرئيسي: %(p)s%% + الشركاء: %(c)s%% = %(t)s%%).") % {
                        'p': primary_share,
                        'c': co_owners_total,
                        't': total_share
                    }
                )

            contract.primary_owner_share = primary_share
            contract.save(update_fields=['primary_owner_share', 'updated_at'])

            existing_co_owners = {co.co_owner_id: co for co in contract.co_owners.all()}
            processed_customer_ids = set()

            for item in co_owners_data:
                customer = item.get('co_owner') or item.get('customer')
                cust_id = getattr(customer, 'id', None) or item.get('co_owner_id') or item.get('customer_id')
                if not cust_id:
                    raise ValidationError(_("يجب تحديد العميل الشريك لكل سطر ملكية."))

                processed_customer_ids.add(cust_id)
                share = Decimal(str(item.get('share_percentage', '0'))).quantize(Decimal('0.01'))
                is_guarantor = item.get('is_joint_and_several_guarantor', True)
                relationship = item.get('relationship', ContractCoOwner.RelationshipType.BUSINESS_PARTNER)
                poa_number = str(item.get('power_of_attorney_number', '') or '').strip()
                reg_office = str(item.get('issuing_registry_office', '') or '').strip()
                rep_capacity = str(item.get('representation_capacity', '') or '').strip()
                notes = item.get('notes', '')

                if cust_id in existing_co_owners:
                    co_owner_obj = existing_co_owners[cust_id]
                    co_owner_obj.share_percentage = share
                    co_owner_obj.is_joint_and_several_guarantor = is_guarantor
                    co_owner_obj.relationship = relationship
                    co_owner_obj.power_of_attorney_number = poa_number
                    co_owner_obj.issuing_registry_office = reg_office
                    co_owner_obj.representation_capacity = rep_capacity
                    co_owner_obj.notes = notes
                    co_owner_obj.save(skip_integrity_check=True)
                else:
                    new_co = ContractCoOwner(
                        contract=contract,
                        co_owner_id=cust_id,
                        share_percentage=share,
                        is_joint_and_several_guarantor=is_guarantor,
                        relationship=relationship,
                        power_of_attorney_number=poa_number,
                        issuing_registry_office=reg_office,
                        representation_capacity=rep_capacity,
                        notes=notes,
                    )
                    new_co.save(skip_integrity_check=True)

            for cust_id, co_owner_obj in existing_co_owners.items():
                if cust_id not in processed_customer_ids:
                    co_owner_obj.delete(skip_integrity_check=True)

            contract.validate_ownership_integrity()
            logger.info(
                f"✅ [OwnershipSync] تم تحديث ملكية العقد {contract.contract_number}: "
                f"الرئيسي={primary_share}%، الشركاء={len(processed_customer_ids)}"
            )
            return contract

    @classmethod
    def terminate_contract(
        cls,
        contract_id: int,
        reason: str,
        penalty_amount: Decimal = Decimal('0.00'),
        refund_now: bool = False,
        payment_account=None,
        user=None
    ) -> Dict[str, Any]:
        """
        فسخ العقد العقاري وإعادة طرح الوحدة للبيع (Contract Rescission & Resale Lifecycle):
        1. التحقق من حالة العقد وصلاحيات المستخدم وقفل السجلات ذرياً.
        2. عكس أي إيرادات معترف بها سابقاً وفق معيار IFRS 15.
        3. إلغاء خطة الأقساط والأقساط غير المسددة.
        4. احتساب المبالغ المسددة، وتحديد الغرامة وصافي المستحق.
        5. إنشاء مطالبة مستحقات رد معلقة لإعادة الطرح (ResaleContingentRefund) أو الصرف الفوري.
        6. ترحيل قيد فسخ العقد وتصفية الالتزامات واسترداد عمولة الوسيط (Clawback).
        7. تحرير الوحدة العقارية وإعادتها لحالة متاح (AVAILABLE) وزيادة إصدار الحالة.
        8. تحديث حالة العقد إلى مفسوخ (TERMINATED).
        """
        if not reason:
            raise ValidationError(_("يجب توضيح سبب فسخ العقد."))

        if user and hasattr(user, 'has_perm') and not (user.is_superuser or getattr(user, 'is_admin', False)):
            if not user.has_perm('real_estate.change_propertycontract'):
                from django.core.exceptions import PermissionDenied
                raise PermissionDenied(_("غير مصرح لك بفسخ العقود العقارية (real_estate.change_propertycontract)."))

        from real_estate.models.unit import PropertyUnit
        from real_estate.services.accounting_service import RealEstateAccountingService
        from real_estate.services.resale_refund_service import ResaleContingentRefundService
        from sale.models.installments import PlanStatus
        from django.utils import timezone
        from django.db import models

        with transaction.atomic():
            try:
                contract = PropertyContract.objects.select_for_update().get(pk=contract_id)
            except PropertyContract.DoesNotExist:
                raise ValidationError(_("العقد العقاري المطلوب غير موجود."))

            unit = PropertyUnit.objects.select_for_update().get(pk=contract.unit_id)

            if contract.status not in [PropertyContract.ContractStatus.ACTIVE, PropertyContract.ContractStatus.UNDER_APPROVAL]:
                raise ValidationError(
                    _("لا يمكن فسخ عقد غير سارٍ (الحالة الحالية: %(status)s).") % {
                        'status': contract.get_status_display()
                    }
                )

            # 1. عكس أي إيرادات تم الاعتراف بها مسبقاً (IFRS 15 Revenue Reversal)
            rec_rev = getattr(contract, 'recognized_revenue_amount', Decimal('0.00')) or Decimal('0.00')
            if rec_rev > Decimal('0.00'):
                RealEstateAccountingService.post_revenue_reversal(
                    contract=contract,
                    amount=rec_rev,
                    user=user,
                    reference=f"TERM-REV-{contract.contract_number}"
                )
                contract.recognized_revenue_amount = Decimal('0.00')

            # 2. احتساب إجمالي ما سدده العميل فعلياً بموجب السجلات المحاسبية والتحصيل المثبت
            total_paid = Decimal('0.00')
            if contract.installment_plan_id:
                collected_dp = Decimal('0.00')
                if contract.down_payment and contract.down_payment > Decimal('0.00'):
                    from financial.models import JournalEntry, JournalEntryLine
                    from real_estate.models.booking import UnitBooking
                    dp_entries = JournalEntry.objects.filter(
                        source_module='real_estate',
                        source_model='PropertyContract',
                        source_id=contract.pk
                    ).filter(
                        models.Q(idempotency_key__contains='direct_down_payment') |
                        models.Q(idempotency_key__contains='contract_booking_deposit_transfer') |
                        models.Q(reference__icontains='DP-') |
                        models.Q(description__icontains='مقدم') |
                        models.Q(lines__description__icontains='مقدم')
                    ).filter(
                        reversed_by_entry__isnull=True,
                        is_reversal=False,
                        reversal_entries__isnull=True
                    ).exclude(
                        models.Q(idempotency_key__contains='revenue') |
                        models.Q(idempotency_key__contains='survey') |
                        models.Q(reference__icontains='REV-') |
                        models.Q(reference__icontains='TERM-REV-') |
                        models.Q(status='reversed')
                    ).distinct()

                    curr = getattr(contract, 'currency', None)
                    is_foreign = bool(curr and not getattr(curr, 'is_functional', False) and getattr(curr, 'code', 'EGP') != 'EGP')

                    if dp_entries.exists():
                        # احتساب المبلغ المحصل فعلياً بعملة العقد من القيود المحاسبية الدائنة لالتزام العقد 21102
                        dp_lines = JournalEntryLine.objects.filter(
                            journal_entry__in=dp_entries,
                            credit__gt=Decimal('0.00')
                        ).filter(
                            models.Q(account__code='21102') |
                            models.Q(account__code__startswith='21102') |
                            models.Q(description__icontains='مقدم') |
                            models.Q(description__icontains='down_payment')
                        )
                        if dp_lines.exists():
                            if is_foreign:
                                f_sum = dp_lines.aggregate(s=models.Sum('foreign_credit'))['s'] or Decimal('0.00')
                                if f_sum > Decimal('0.00'):
                                    collected_dp = f_sum
                                else:
                                    rate = Decimal(str(getattr(contract, 'exchange_rate', '1.000000') or '1.000000'))
                                    c_sum = dp_lines.aggregate(s=models.Sum('credit'))['s'] or Decimal('0.00')
                                    collected_dp = (c_sum / rate).quantize(Decimal('0.01')) if rate > Decimal('0.00') else c_sum
                            else:
                                collected_dp = dp_lines.aggregate(s=models.Sum('credit'))['s'] or Decimal('0.00')
                        else:
                            debit_lines = JournalEntryLine.objects.filter(
                                journal_entry__in=dp_entries,
                                debit__gt=Decimal('0.00')
                            )
                            if is_foreign:
                                f_deb = debit_lines.aggregate(s=models.Sum('foreign_debit'))['s'] or Decimal('0.00')
                                if f_deb > Decimal('0.00'):
                                    collected_dp = f_deb
                                else:
                                    rate = Decimal(str(getattr(contract, 'exchange_rate', '1.000000') or '1.000000'))
                                    d_sum = debit_lines.aggregate(s=models.Sum('debit'))['s'] or Decimal('0.00')
                                    collected_dp = (d_sum / rate).quantize(Decimal('0.01')) if rate > Decimal('0.00') else d_sum
                            else:
                                collected_dp = debit_lines.aggregate(s=models.Sum('debit'))['s'] or Decimal('0.00')
                    else:
                        booking_entry = UnitBooking.objects.filter(
                            unit=contract.unit,
                            customer=contract.customer,
                            status=UnitBooking.BookingStatus.CONVERTED_TO_CONTRACT,
                            is_deposit_collected=True
                        ).first()
                        if booking_entry:
                            b_je = getattr(booking_entry, 'journal_entry', None)
                            if b_je:
                                is_reversed = (
                                    getattr(b_je, 'reversed_by_entry_id', None) is not None or
                                    getattr(b_je, 'is_reversal', False) or
                                    b_je.reversal_entries.exists() or
                                    getattr(b_je, 'status', None) == 'cancelled'
                                )
                                if not is_reversed and getattr(b_je, 'status', None) == 'posted':
                                    collected_dp = Decimal(str(booking_entry.holding_deposit or Decimal('0.00')))
                                else:
                                    collected_dp = Decimal('0.00')
                            else:
                                collected_dp = Decimal('0.00')

                total_paid += collected_dp
            else:
                total_paid += Decimal(str(contract.down_payment or Decimal('0.00')))

            if contract.installment_plan:
                plan = contract.installment_plan
                paid_sum = plan.items.aggregate(s=models.Sum('paid_amount'))['s'] or Decimal('0.00')
                total_paid += Decimal(str(paid_sum))

                # إلغاء خطة الأقساط
                plan.status = PlanStatus.CANCELLED
                plan.save(update_fields=['status', 'updated_at'])

            # 3. احتساب الغرامة وصافي المبلغ
            penalty_dec = min(Decimal(str(penalty_amount or '0.00')), total_paid)
            net_refundable = max(Decimal('0.00'), total_paid - penalty_dec)

            refund_record = None
            refund_amount = Decimal('0.00')
            forfeited_pending_resale = Decimal('0.00')

            if refund_now and payment_account and net_refundable > Decimal('0.00'):
                refund_amount = net_refundable
            elif net_refundable > Decimal('0.00'):
                forfeited_pending_resale = net_refundable
                refund_record = ResaleContingentRefundService.create_contingent_refund(
                    cancelled_contract=contract,
                    cancellation_penalty_amount=penalty_dec,
                    notes=f"فسخ تعاقد: {reason}",
                    user=user,
                    total_paid_amount=total_paid
                )

            # 4. ترحيل قيد فسخ العقد وتصفية الالتزامات
            cancel_entry = None
            if total_paid > Decimal('0.00'):
                cancel_entry = RealEstateAccountingService.post_contract_cancellation(
                    contract=contract,
                    penalty_amount=penalty_dec,
                    refund_amount=refund_amount,
                    uncashed_cheques_amount=Decimal('0.00'),
                    refund_account=payment_account if (refund_now and refund_amount > Decimal('0.00')) else None,
                    forfeited_pending_resale=forfeited_pending_resale,
                    user=user,
                    reference=f"TERM-{contract.contract_number}"
                )

            # 5. تحرير الوحدة العقارية وإعادتها لحالة متاح (AVAILABLE)
            unit.status = PropertyUnit.UnitStatus.AVAILABLE
            unit.status_version += 1
            unit.save(update_fields=['status', 'status_version'])

            # 6. تحديث حالة العقد
            contract.status = PropertyContract.ContractStatus.TERMINATED
            contract.save(update_fields=['status', 'recognized_revenue_amount', 'updated_at'])

            logger.info(
                f"🛑 [ContractTermination] تم فسخ العقد {contract.contract_number} بنجاح، "
                f"وتحرير الوحدة {unit.unit_code} للبيع، وصافي المستحق={net_refundable}."
            )

            return {
                'contract': contract,
                'unit': unit,
                'refund_record': refund_record,
                'journal_entry': cancel_entry,
                'total_paid': total_paid,
                'penalty_amount': penalty_dec,
                'net_refundable': net_refundable,
            }
