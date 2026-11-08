# -*- coding: utf-8 -*-
"""
HandoverExecutionService - محرك إدارة وتنفيذ محاضر استلام وتسليم الوحدات العقارية
MWHEBA ERP — Real Estate Wave 3 (Phase 10: Handover & IFRS 15 Revenue Recognition)
"""
import logging
from decimal import Decimal
from typing import Optional, Dict, Any

from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from real_estate.models.unit import PropertyUnit
from real_estate.models.contract import PropertyContract
from real_estate.models.handover import PropertyHandoverReceipt
from real_estate.models.legal import LegalNotice
from real_estate.services.accounting_service import RealEstateAccountingService
from real_estate.services.snagging_service import OfflineSnaggingSyncService

logger = logging.getLogger(__name__)


class HandoverExecutionService:
    """
    محرك تسليم الوحدات العقارية والاعتراف بالإيراد وفق معيار IFRS 15:
    - التحقق الصارم من انتهاء الملاحظات الفنية الحرجة (Snagging Blocker Guard)
    - تنفيذ التسليم الفعلي (Physical Handover) أو التسليم الحُكمي بقوة العقد (Deemed Handover Protocol)
    - ترحيل قيود استحقاق الإيراد المحقق (Dr: 21102 / Cr: 41101) وتكلفة المبيعات التقديرية (Interim COGS)
    - توليد بصمة التوثيق المشفرة SHA-256 لمنع التلاعب
    """

    @classmethod
    @transaction.atomic
    def create_handover_receipt(
        cls,
        contract: PropertyContract,
        handover_type: str = PropertyHandoverReceipt.HandoverType.PHYSICAL,
        created_by=None,
        site_engineer=None,
        handover_date=None,
        legal_notice: Optional[LegalNotice] = None,
        client_signatory_name: str = "",
        client_signatory_national_id: str = "",
        power_of_attorney_number: str = "",
        electric_meter_reading: Decimal = Decimal("0.00"),
        water_meter_reading: Decimal = Decimal("0.00"),
        gas_meter_reading: Decimal = Decimal("0.00"),
        keys_handed_over_count: int = 0,
        access_cards_count: int = 0,
        notes: str = ""
    ) -> PropertyHandoverReceipt:
        """
        إنشاء مسودة محضر استلام وتسليم لوحدة عقارية
        """
        if contract.status not in [PropertyContract.ContractStatus.ACTIVE, PropertyContract.ContractStatus.COMPLETED]:
            raise ValidationError(
                _("لا يمكن إنشاء محضر تسليم لعقد غير سارٍ (الحالة الحالية: %(status)s).") % {
                    'status': contract.get_status_display()
                }
            )

        unit = contract.unit
        if unit.status in [PropertyUnit.UnitStatus.DELIVERED, PropertyUnit.UnitStatus.DELIVERED_DEEMED]:
            raise ValidationError(
                _("الوحدة %(code)s مسلّمة بالفعل ولا يجوز إنشاء محضر تسليم جديد لها.") % {
                    'code': unit.unit_code
                }
            )

        if handover_type == PropertyHandoverReceipt.HandoverType.DEEMED and not legal_notice:
            raise ValidationError(
                _("التسليم الحُكمي يتطلب ربط إخطار قانوني رسمي معتمد بالاستلام.")
            )

        receipt = PropertyHandoverReceipt(
            contract=contract,
            unit=unit,
            handover_type=handover_type,
            status=PropertyHandoverReceipt.HandoverStatus.DRAFT,
            handover_date=handover_date or timezone.localdate(),
            legal_notice=legal_notice,
            site_engineer=site_engineer,
            client_signatory_name=client_signatory_name,
            client_signatory_national_id=client_signatory_national_id,
            power_of_attorney_number=power_of_attorney_number,
            electric_meter_reading=electric_meter_reading,
            water_meter_reading=water_meter_reading,
            gas_meter_reading=gas_meter_reading,
            keys_handed_over_count=keys_handed_over_count,
            access_cards_count=access_cards_count,
            notes=notes,
            created_by=created_by
        )
        receipt.full_clean()
        receipt.save()

        logger.info(
            f"Created handover receipt {receipt.receipt_number} for unit {unit.unit_code} "
            f"under contract {contract.contract_number} (Type: {handover_type})"
        )
        return receipt

    @classmethod
    @transaction.atomic
    def execute_physical_handover(
        cls,
        receipt: PropertyHandoverReceipt,
        executed_by,
        recognized_revenue_amount: Optional[Decimal] = None,
        budgeted_cost_per_meter: Optional[Decimal] = None
    ) -> PropertyHandoverReceipt:
        """
        اعتماد وتنفيذ التسليم الفعلي للوحدة:
        1. فحص حارس الملاحظات الحرجة (Critical Snagging Blocker Guard)
        2. قيد الاعتراف بالإيراد وفق IFRS 15 (Dr: 21102 / Cr: 41101)
        3. قيد تكلفة المبيعات التقديرية (Interim Unit COGS: Dr: 51100 / Cr: 12101)
        4. تحويل حالة الوحدة إلى DELIVERED وتوليد الهاش المشفر SHA-256
        """
        # قفل وإعادة تحميل أحدث حالة من قاعدة البيانات داخل المعاملة الذرية لمنع تعارض الحالات المتقادمة
        receipt.refresh_from_db()
        PropertyHandoverReceipt.objects.select_for_update().filter(pk=receipt.pk).exists()
        contract = PropertyContract.objects.select_for_update().get(pk=receipt.contract_id)
        unit = PropertyUnit.objects.select_for_update().get(pk=receipt.unit_id)

        if receipt.status == PropertyHandoverReceipt.HandoverStatus.EXECUTED:
            raise ValidationError(_("محضر التسليم معتمد ومنفذ بالفعل."))

        # التحقق الرقابي من عدم وجود محضر تسليم آخر معتمد ومنفذ لنفس العقد
        if PropertyHandoverReceipt.objects.filter(
            contract=contract,
            status=PropertyHandoverReceipt.HandoverStatus.EXECUTED
        ).exclude(pk=receipt.pk).exists():
            raise ValidationError(_("يوجد بالفعل محضر تسليم معتمد ومنفذ لهذا العقد العقاري."))

        if unit.status in [PropertyUnit.UnitStatus.DELIVERED, PropertyUnit.UnitStatus.DELIVERED_DEEMED]:
            raise ValidationError(_("الوحدة العقارية مسلّمة بالفعل بموجب محضر استلام سابق."))

        if receipt.handover_type != PropertyHandoverReceipt.HandoverType.PHYSICAL:
            raise ValidationError(_("هذا المحضر مخصص للتسليم الحُكمي وليس التسليم الفعلي."))

        if not receipt.client_signatory_name:
            raise ValidationError(_("يلزم تسجيل اسم المستلم أو الوكيل الحاضر للتسليم الفعلي."))

        # 1. فحص حارس العيوب والملاحظات الفنية الحرجة
        readiness = OfflineSnaggingSyncService.check_unit_handover_readiness(receipt.unit)
        if not readiness['is_ready_for_handover']:
            raise ValidationError(
                _("لا يمكن إتمام التسليم لوجود عدد %(count)s ملاحظة فنية حرجة (Blockers) قيد المعالجة للوحدة %(unit)s.") % {
                    'count': readiness['blockers_count'],
                    'unit': receipt.unit.unit_code
                }
            )

        contract = receipt.contract
        prior_recognized = getattr(contract, 'recognized_revenue_amount', Decimal('0.00')) or Decimal('0.00')
        remaining_balance = max(Decimal('0.00'), contract.final_contract_price - prior_recognized)

        if recognized_revenue_amount is not None:
            revenue_amount = max(Decimal('0.00'), min(recognized_revenue_amount, remaining_balance))
        elif contract.revenue_recognition_method == PropertyContract.RevenueMethod.OVER_TIME or prior_recognized > Decimal('0.00'):
            revenue_amount = remaining_balance
        else:
            revenue_amount = remaining_balance

        # 2. ترحيل قيد الاعتراف بالإيراد المحقق IFRS 15 عبر بوابة المحاسبة
        revenue_entry = None
        if revenue_amount > Decimal("0.00"):
            post_kwargs = {
                'contract': contract,
                'amount': revenue_amount,
                'is_handover': True,
                'user': executed_by,
                'reference': f"REV-REC-{receipt.receipt_number}",
            }
            if contract.revenue_recognition_method == PropertyContract.RevenueMethod.OVER_TIME:
                post_kwargs['poc_percentage'] = Decimal('100.00')
            revenue_entry = RealEstateAccountingService.post_revenue_recognition(**post_kwargs)

            # تحديث إجمالي الإيراد التراكمي المعترف به بالعقد بناءً على القيد الفعلي بعملة العقد
            posted_contract_revenue = revenue_amount
            if revenue_entry:
                from django.db.models import Sum
                if contract.currency and not getattr(contract.currency, 'is_functional', True):
                    fc_total = revenue_entry.lines.filter(foreign_credit__gt=0).aggregate(total=Sum('foreign_credit'))['total']
                    if fc_total is not None:
                        posted_contract_revenue = fc_total
                else:
                    lc_total = revenue_entry.lines.filter(credit__gt=0).aggregate(total=Sum('credit'))['total']
                    if lc_total is not None:
                        posted_contract_revenue = lc_total

            contract.recognized_revenue_amount = prior_recognized + posted_contract_revenue
            contract.save(update_fields=['recognized_revenue_amount', 'updated_at'])
            receipt.recognized_revenue_amount = posted_contract_revenue

        # 3. ترحيل قيد تكلفة المبيعات التقديرية للوحدة (Interim COGS Allocation)
        cogs_entry = None
        cogs_amount = Decimal("0.00")
        if budgeted_cost_per_meter and budgeted_cost_per_meter > Decimal("0.00"):
            cogs_amount = budgeted_cost_per_meter * receipt.unit.gross_area
            cogs_entry = RealEstateAccountingService.post_handover_interim_cogs(
                receipt=receipt,
                cogs_amount=cogs_amount,
                user=executed_by,
                reference=f"COGS-{receipt.receipt_number}"
            )

        # 4. تحديث حالة الوحدة والمحضر وتوليد البصمة المشفرة
        receipt.status = PropertyHandoverReceipt.HandoverStatus.EXECUTED
        receipt.recognized_revenue_amount = revenue_amount
        receipt.interim_cogs_amount = cogs_amount
        receipt.revenue_journal_entry = revenue_entry
        receipt.cogs_journal_entry = cogs_entry
        receipt.executed_by = executed_by
        receipt.executed_at = timezone.now()
        receipt.verification_hash = receipt.generate_verification_hash()
        receipt.save()

        # تحديث حالة الوحدة
        receipt.unit.status = PropertyUnit.UnitStatus.DELIVERED
        receipt.unit.save(update_fields=['status'])

        logger.info(
            f"Successfully executed physical handover {receipt.receipt_number} for unit {receipt.unit.unit_code}. "
            f"Revenue: {revenue_amount} EGP, COGS: {cogs_amount} EGP."
        )
        return receipt

    @classmethod
    @transaction.atomic
    def execute_deemed_handover(
        cls,
        receipt: PropertyHandoverReceipt,
        executed_by,
        recognized_revenue_amount: Optional[Decimal] = None,
        budgeted_cost_per_meter: Optional[Decimal] = None
    ) -> PropertyHandoverReceipt:
        """
        اعتماد وتنفيذ التسليم الحُكمي بقوة العقد وقانون البناء (Deemed Handover Protocol):
        - يُطبق عند امتناع أو تخلف المشتري عن الحضور بعد إعلانه رسمياً بإنذار قانوني مع انقضاء مهلة التسليم
        - لا يتطلب توقيع المشتري
        - يرحل استحقاق الإيراد وتكلفة المبيعات ويحول حالة الوحدة إلى DELIVERED_DEEMED
        """
        # قفل وإعادة تحميل أحدث حالة من قاعدة البيانات داخل المعاملة الذرية لمنع تعارض الحالات المتقادمة
        receipt.refresh_from_db()
        PropertyHandoverReceipt.objects.select_for_update().filter(pk=receipt.pk).exists()
        contract = PropertyContract.objects.select_for_update().get(pk=receipt.contract_id)
        unit = PropertyUnit.objects.select_for_update().get(pk=receipt.unit_id)

        if receipt.status == PropertyHandoverReceipt.HandoverStatus.EXECUTED:
            raise ValidationError(_("محضر التسليم معتمد ومنفذ بالفعل."))

        # التحقق الرقابي من عدم وجود محضر تسليم آخر معتمد ومنفذ لنفس العقد
        if PropertyHandoverReceipt.objects.filter(
            contract=contract,
            status=PropertyHandoverReceipt.HandoverStatus.EXECUTED
        ).exclude(pk=receipt.pk).exists():
            raise ValidationError(_("يوجد بالفعل محضر تسليم معتمد ومنفذ لهذا العقد العقاري."))

        if unit.status in [PropertyUnit.UnitStatus.DELIVERED, PropertyUnit.UnitStatus.DELIVERED_DEEMED]:
            raise ValidationError(_("الوحدة العقارية مسلّمة بالفعل بموجب محضر استلام سابق."))

        if receipt.handover_type != PropertyHandoverReceipt.HandoverType.DEEMED:
            raise ValidationError(_("هذا المحضر مخصص للتسليم الفعلي وليس التسليم الحُكمي."))

        if not receipt.legal_notice:
            raise ValidationError(_("التسليم الحُكمي يستلزم وجود إخطار قانوني رسمي معتمد بالاستلام."))

        # التحقق من أن الإنذار تم إرساله أو تسليمه بالفعل
        if receipt.legal_notice.status not in [
            LegalNotice.NoticeStatus.SERVED,
            LegalNotice.NoticeStatus.SENT,
            LegalNotice.NoticeStatus.DELIVERED
        ]:
            raise ValidationError(
                _("لا يجوز تنفيذ التسليم الحُكمي بموجب إخطار لم يتم إرساله أو تسليمه رسمياً (الحالة: %(status)s).") % {
                    'status': receipt.legal_notice.get_status_display()
                }
            )

        contract = receipt.contract
        prior_recognized = getattr(contract, 'recognized_revenue_amount', Decimal('0.00')) or Decimal('0.00')
        remaining_balance = max(Decimal('0.00'), contract.final_contract_price - prior_recognized)

        if recognized_revenue_amount is not None:
            revenue_amount = max(Decimal('0.00'), min(recognized_revenue_amount, remaining_balance))
        elif contract.revenue_recognition_method == PropertyContract.RevenueMethod.OVER_TIME or prior_recognized > Decimal('0.00'):
            revenue_amount = remaining_balance
        else:
            revenue_amount = remaining_balance

        # ترحيل قيد الاعتراف بالإيراد المحقق IFRS 15
        revenue_entry = None
        if revenue_amount > Decimal("0.00"):
            post_kwargs = {
                'contract': contract,
                'amount': revenue_amount,
                'is_handover': True,
                'user': executed_by,
                'reference': f"REV-REC-DEEMED-{receipt.receipt_number}",
            }
            if contract.revenue_recognition_method == PropertyContract.RevenueMethod.OVER_TIME:
                post_kwargs['poc_percentage'] = Decimal('100.00')
            revenue_entry = RealEstateAccountingService.post_revenue_recognition(**post_kwargs)

            # تحديث إجمالي الإيراد التراكمي المعترف به بالعقد بناءً على القيد الفعلي بعملة العقد
            posted_contract_revenue = revenue_amount
            if revenue_entry:
                from django.db.models import Sum
                if contract.currency and not getattr(contract.currency, 'is_functional', True):
                    fc_total = revenue_entry.lines.filter(foreign_credit__gt=0).aggregate(total=Sum('foreign_credit'))['total']
                    if fc_total is not None:
                        posted_contract_revenue = fc_total
                else:
                    lc_total = revenue_entry.lines.filter(credit__gt=0).aggregate(total=Sum('credit'))['total']
                    if lc_total is not None:
                        posted_contract_revenue = lc_total

            contract.recognized_revenue_amount = prior_recognized + posted_contract_revenue
            contract.save(update_fields=['recognized_revenue_amount', 'updated_at'])
            receipt.recognized_revenue_amount = posted_contract_revenue

        # ترحيل قيد تكلفة المبيعات التقديرية (Interim COGS)
        cogs_entry = None
        cogs_amount = Decimal("0.00")
        if budgeted_cost_per_meter and budgeted_cost_per_meter > Decimal("0.00"):
            cogs_amount = budgeted_cost_per_meter * receipt.unit.gross_area
            cogs_entry = RealEstateAccountingService.post_handover_interim_cogs(
                receipt=receipt,
                cogs_amount=cogs_amount,
                user=executed_by,
                reference=f"COGS-DEEMED-{receipt.receipt_number}"
            )

        # تحديث حالة الوحدة إلى DELIVERED_DEEMED
        receipt.status = PropertyHandoverReceipt.HandoverStatus.EXECUTED
        receipt.recognized_revenue_amount = revenue_amount
        receipt.interim_cogs_amount = cogs_amount
        receipt.revenue_journal_entry = revenue_entry
        receipt.cogs_journal_entry = cogs_entry
        receipt.executed_by = executed_by
        receipt.executed_at = timezone.now()
        receipt.verification_hash = receipt.generate_verification_hash()
        receipt.save()

        receipt.unit.status = PropertyUnit.UnitStatus.DELIVERED_DEEMED
        receipt.unit.save(update_fields=['status'])

        logger.info(
            f"Successfully executed deemed handover {receipt.receipt_number} for unit {receipt.unit.unit_code} "
            f"via legal notice {receipt.legal_notice.notice_number}."
        )
        return receipt
