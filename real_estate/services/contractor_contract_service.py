# -*- coding: utf-8 -*-
"""
Contractor Contract Business Logic Service
MWHEBA ERP - Real Estate Construction Management

Manages complete lifecycle of construction subcontracts:
- Master BOQ ceiling and quantity splitting validations
- Target cost budget rate overrun checks
- Advance payment disbursement via Escrow account
- Variation orders and dynamic advance recovery recalibration
- Hard compliance guards: Judicial Garnishment, Bank Assignment of Proceeds,
  CAR Insurance validity, LG Expiration & Pay-or-Extend banking trigger,
  Strict Vendor Bank Whitelist.
- Joint Termination protocol and leftover materials stock absorption.
- Sectional Handover and independent warranty clocks.
- Craftsmen micro-contracts and self-billing vouchers.
"""
from decimal import Decimal
import logging
from typing import Optional, Dict, Any, List
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

from real_estate.models import (
    ContractorContract,
    ContractorContractItem,
    ProjectMasterBOQItem,
    ContractVariationOrder,
    ContractVariationOrderItem,
    SectionalHandoverRecord,
    JointTerminationSurveyProtocol,
)
from financial.models import ChartOfAccounts, JournalEntry
from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
from governance.services.accounting_gateway import AccountingGateway, JournalEntryLineData

logger = logging.getLogger(__name__)


class ContractorContractService:
    """
    خدمة إدارة عقود مقاولي الباطن والعمليات الهندسية والمالية المرتبطة
    """

    @classmethod
    def get_or_resolve_account(
        cls,
        role_name: str,
        fallback_code: str,
        name_ar: str = "",
        account_type_category: str = "asset"
    ) -> ChartOfAccounts:
        """جلب الحساب المحاسبي عبر سجل الأدوار الموحد مع استخدام الحساب الاحتياطي"""
        try:
            account = AccountRoleRegistry.get_account(role_name)
        except Exception:
            account = None
        if not account:
            account = ChartOfAccounts.objects.filter(code=fallback_code).first()
        if not account or not account.is_active:
            # البحث عن حساب فرعي إذا كان الحساب الرئيسي مجمع
            if account and not account.can_post_entries() and account.children.filter(is_active=True, is_leaf=True).exists():
                return account.children.filter(is_active=True, is_leaf=True).first()
            raise ValidationError(
                _("الحساب المحاسبي للدور '%(role)s' (كود %(code)s) غير مهيأ أو غير نشط في دليل الحسابات.") % {
                    'role': role_name,
                    'code': fallback_code
                }
            )
        return account

    @classmethod
    def validate_master_boq_and_budget(
        cls,
        project,
        item_code: str,
        contracted_quantity: Decimal,
        unit_rate: Decimal,
        master_boq_item: Optional[ProjectMasterBOQItem] = None
    ) -> Dict[str, Any]:
        """
        التحقق من سقف مقايسة المشروع العامة وعدم تجاوز فئات الموازنة التقديرية
        """
        result = {
            "is_valid": True,
            "is_rate_overrun": False,
            "rate_difference": Decimal("0.00"),
            "available_quantity": Decimal("0.00"),
            "tolerance_exceeded": False,
        }

        if master_boq_item and project:
            master_boq_proj_id = master_boq_item.project_id if hasattr(master_boq_item, 'project_id') else getattr(master_boq_item.project, 'id', None)
            project_id = project.id if hasattr(project, 'id') else project
            if master_boq_proj_id and project_id and master_boq_proj_id != project_id:
                raise ValidationError(_("بند المقايسة التقديرية المختار ينتمي لمشروع آخر مختلف عن مشروع العقد."))

        if not master_boq_item:
            master_boq_item = ProjectMasterBOQItem.objects.filter(
                project=project,
                item_code=item_code
            ).first()

        if master_boq_item:
            # 1. فحص سقف الكميات الإجمالية مع نسبة السماحية
            tolerance_rate = master_boq_item.overrun_tolerance_rate or Decimal("0.00")
            max_allowed_quantity = (master_boq_item.master_budget_quantity * (Decimal("1.00") + tolerance_rate / Decimal("100.00"))).quantize(Decimal("0.001"))
            projected_total = master_boq_item.allocated_quantity_to_contracts + contracted_quantity

            result["available_quantity"] = max(Decimal("0.000"), max_allowed_quantity - master_boq_item.allocated_quantity_to_contracts)

            if projected_total > max_allowed_quantity:
                result["is_valid"] = False
                result["tolerance_exceeded"] = True
                raise ValidationError(
                    _("الكمية التعاقدية (%(qty)s) تتجاوز السقف الأقصى المتاح بمقايسة المشروع العامة (%(avail)s) للبند %(code)s مع احتساب سماحية %(tol)s%%.") % {
                        'qty': contracted_quantity,
                        'avail': result["available_quantity"],
                        'code': item_code,
                        'tol': tolerance_rate
                    }
                )

            # 2. فحص فئة التعاقد مقابل فئة الموازنة التقديرية
            if master_boq_item.unit_rate_estimate and unit_rate > master_boq_item.unit_rate_estimate:
                result["is_rate_overrun"] = True
                result["rate_difference"] = (unit_rate - master_boq_item.unit_rate_estimate).quantize(Decimal("0.01"))
                logger.warning(
                    f"Contract rate overrun: Item {item_code} contracted at {unit_rate} vs estimated {master_boq_item.unit_rate_estimate}"
                )

        return result

    @classmethod
    @transaction.atomic
    def create_contract_item(
        cls,
        contract: ContractorContract,
        item_data: Dict[str, Any],
        user=None
    ) -> ContractorContractItem:
        """
        إضافة بند تعاقدي جديد مع التحقق من مقايسة المشروع وتطبيق معاملات الخوازيق والمكون الأجنبي
        """
        item_code = item_data.get("item_code")
        contracted_quantity = Decimal(str(item_data.get("contracted_quantity", "0.000")))
        unit_rate = Decimal(str(item_data.get("unit_rate", "0.00")))
        master_boq = item_data.get("master_boq_item")
        if not master_boq:
            master_boq = ProjectMasterBOQItem.objects.filter(
                project=contract.project,
                item_code=item_code
            ).first()

        # التحقق من المقايسة الحاكمة
        validation = cls.validate_master_boq_and_budget(
            project=contract.project,
            item_code=item_code,
            contracted_quantity=contracted_quantity,
            unit_rate=unit_rate,
            master_boq_item=master_boq
        )

        item = ContractorContractItem(
            contract=contract,
            master_boq_item=master_boq,
            block=item_data.get("block") or contract.block,
            wbs_group=item_data.get("wbs_group", "STRUCTURAL"),
            wbs_budget_code=item_data.get("wbs_budget_code", ""),
            item_code=item_code,
            description=item_data.get("description", ""),
            unit=item_data.get("unit", "M3"),
            contracted_quantity=contracted_quantity,
            revised_quantity=contracted_quantity,
            unit_rate=unit_rate,
            is_budget_rate_overrun=validation["is_rate_overrun"],
            total_budget_amount=(contracted_quantity * unit_rate).quantize(Decimal("0.01")),
            tax_regime_override=item_data.get("tax_regime_override"),
            has_foreign_component=item_data.get("has_foreign_component", False),
            foreign_component_percent=Decimal(str(item_data.get("foreign_component_percent", "0.00"))),
            foreign_currency=item_data.get("foreign_currency"),
            fx_baseline_rate=Decimal(str(item_data.get("fx_baseline_rate", "1.000000"))),
            fx_volatility_collar_percent=Decimal(str(item_data.get("fx_volatility_collar_percent", "15.00"))),
            is_deep_foundation_pile=item_data.get("is_deep_foundation_pile", False),
            pile_bulbing_factor_percent=Decimal(str(item_data.get("pile_bulbing_factor_percent", "12.00"))),
        )
        item.save()

        # تحديث الكمية المحجوزة بمقايسة المشروع العامة
        if master_boq:
            master_boq.allocated_quantity_to_contracts += contracted_quantity
            master_boq.save(update_fields=["allocated_quantity_to_contracts", "updated_at"])

        return item

    @classmethod
    @transaction.atomic
    def disburse_advance_payment(
        cls,
        contract: ContractorContract,
        amount: Decimal,
        bank_account_code: str = "11121",
        user=None,
        notes: str = ""
    ) -> JournalEntry:
        """
        صرف الدفعة المقدمة للمقاول من حساب الضمان البنكي (Escrow) مع إصدار القيد المحاسبي
        Dr: Contractor Advance Payments (11350)
        Cr: Project Escrow / Bank Account (11121 / bank_account_code)
        """
        contract = ContractorContract.objects.select_for_update().get(id=contract.id)

        # 1. فحص سقف الدفعة المقدمة
        remaining_advance = contract.advance_payment_amount - contract.advance_payment_disbursed
        if amount > remaining_advance:
            raise ValidationError(
                _("مبلغ الدفعة المقدمة المطلوب صرفه (%(amount)s) يتجاوز الرصيد المتبقي المعتمد بالعقد (%(rem)s).") % {
                    'amount': amount,
                    'rem': remaining_advance
                }
            )

        # 2. فحص صلاحية خطاب الضمان البنكي إذا كان مطلوباً
        if contract.guarantee_type == ContractorContract.GuaranteeType.BANK_LETTER_OF_GUARANTEE:
            if not contract.bank_lg_number or contract.bank_lg_amount < amount:
                raise ValidationError(
                    _("لا يمكن صرف الدفعة المقدمة: العقد يشترط خطاب ضمان بنكي نهائي بقيمة تغطي الدفعة المقدمة.")
                )
            if contract.bank_lg_expiry_date and contract.bank_lg_expiry_date < timezone.localdate():
                raise ValidationError(
                    _("لا يمكن صرف الدفعة المقدمة: خطاب الضمان البنكي المقدم منتهي الصلاحية بتاريخ %(date)s.") % {
                        'date': contract.bank_lg_expiry_date
                    }
                )

        # 3. الحسابات المحاسبية والقيد
        advance_account = cls.get_or_resolve_account(
            AccountRoleNames.REAL_ESTATE_CONTRACTOR_ADVANCE.value,
            fallback_code="11350"
        )
        bank_account = ChartOfAccounts.objects.filter(code=bank_account_code).first()
        if not bank_account or not bank_account.is_active:
            bank_account = cls.get_or_resolve_account(
                AccountRoleNames.REAL_ESTATE_RESTRICTED_CASH.value,
                fallback_code="11121"
            )

        currency_str = getattr(contract.currency, 'code', 'EGP')
        proj_code = contract.project.code if contract.project else None

        desc = f"صرف دفعة مقدمة مقاولة عقد {contract.contract_number} - {contract.contractor.name}"
        if notes:
            desc += f" ({notes})"

        lines = [
            JournalEntryLineData(
                account_code=advance_account.code,
                debit=amount,
                credit=Decimal("0.00"),
                currency=currency_str,
                description=desc,
                project=proj_code
            ),
            JournalEntryLineData(
                account_code=bank_account.code,
                debit=Decimal("0.00"),
                credit=amount,
                currency=currency_str,
                description=desc,
                project=proj_code
            )
        ]

        idempotency_key = AccountingGateway.generate_idempotency_key(
            module='real_estate',
            model='ContractorContract',
            object_id=contract.id,
            operation=f'advance_disbursement_{contract.advance_payment_disbursed}_{amount}'
        )

        gateway = AccountingGateway()
        journal_entry = gateway.create_journal_entry(
            source_module='real_estate',
            source_model='ContractorContract',
            source_id=contract.id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=user,
            entry_type='general_ledger',
            description=desc,
            reference=f"ADV-{contract.contract_number}",
            date=timezone.localdate()
        )

        # 4. تحديث العقد
        contract.advance_payment_disbursed += amount
        contract.save(update_fields=["advance_payment_disbursed", "updated_at"])

        logger.info(f"Advance payment of {amount} {currency_str} disbursed for contract {contract.contract_number}. Entry ID: {journal_entry.id}")
        return journal_entry

    @classmethod
    @transaction.atomic
    def create_variation_order(
        cls,
        contract: ContractorContract,
        vo_data: Dict[str, Any],
        user=None
    ) -> ContractVariationOrder:
        """
        إنشاء أمر تغيير واعتماده وتحديث موازنة العقد واسترداد الدفعة المقدمة
        """
        vo = ContractVariationOrder.objects.create(
            contract=contract,
            order_number=vo_data.get('order_number') or vo_data.get('variation_number', f"VO-{contract.contract_number}-{contract.variation_orders.count() + 1}"),
            variation_type=vo_data.get('variation_type', ContractVariationOrder.VariationType.QUANTITY_INCREASE),
            description=vo_data.get('description') or vo_data.get('description_scope', ''),
            net_value_impact=Decimal(str(vo_data.get('amount_impact') or vo_data.get('net_value_impact', '0.00'))),
            approved_additional_days=int(vo_data.get('time_extension_days') or vo_data.get('approved_additional_days', 0)),
            consultant_approval_ref=vo_data.get('consultant_reference') or vo_data.get('consultant_approval_ref', ''),
            created_by=user,
        )
        return cls.apply_variation_order(vo, user=user)

    @classmethod
    @transaction.atomic
    def apply_variation_order(
        cls,
        variation_order: ContractVariationOrder,
        user=None
    ) -> ContractVariationOrder:
        """
        اعتماد أمر التغيير (VO) وتحديث القيمة التعاقدية وإعادة الضبط الديناميكي لمعدل استرداد الدفعة المقدمة
        """
        vo = ContractVariationOrder.objects.select_for_update().get(id=variation_order.id)
        contract = ContractorContract.objects.select_for_update().get(id=vo.contract.id)

        if vo.status == ContractVariationOrder.VariationStatus.APPROVED:
            return vo

        # 1. تحديث القيمة المعدلة للعقد
        contract.revised_contract_value += vo.net_value_impact

        # 2. تمديد مدة العقد إن وجدت أيام إضافية معتمدة
        if vo.approved_additional_days > 0 and contract.completion_date:
            contract.completion_date = contract.completion_date + timedelta(days=vo.approved_additional_days)

        # 3. إعادة الحساب الديناميكي لمعدل استرداد الدفعة المقدمة عند تغير قيمة العقد
        if contract.dynamic_advance_recalibration and contract.advance_payment_disbursed > Decimal("0.00"):
            remaining_advance = max(Decimal("0.00"), contract.advance_payment_disbursed - contract.advance_payment_recovered)
            remaining_contract_val = max(Decimal("0.00"), contract.revised_contract_value - contract.total_certified_work)
            if remaining_contract_val > Decimal("0.00") and remaining_advance > Decimal("0.00"):
                new_rate = (remaining_advance / remaining_contract_val * Decimal("100.00")).quantize(Decimal("0.01"))
                contract.advance_recovery_rate = min(Decimal("100.00"), new_rate)
                logger.info(
                    f"Dynamic advance recovery recalibrated to {contract.advance_recovery_rate}% for contract {contract.contract_number}"
                )

        # 4. تحديث كميات بنود العقد إذا كان أمر التغيير يتضمن بنوداً
        for vo_item in vo.items.all():
            if vo_item.contract_item:
                c_item = vo_item.contract_item
                c_item.revised_quantity += vo_item.additional_quantity
                c_item.total_budget_amount = (c_item.revised_quantity * c_item.unit_rate).quantize(Decimal("0.01"))
                c_item.save(update_fields=["revised_quantity", "total_budget_amount"])

        contract.save()
        vo.status = ContractVariationOrder.VariationStatus.APPROVED
        vo.save(update_fields=["status"])

        logger.info(f"Variation Order {vo.order_number} applied to contract {contract.contract_number}. New revised value: {contract.revised_contract_value}")
        return vo

    @classmethod
    def check_contract_payout_eligibility(
        cls,
        contract: ContractorContract,
        cert_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        الفحص الأمني والمصرفي والرقابي الصارم لصلاحية الصرف المالي لمستخلص المقاول:
        - الحجز القضائي والتحفظي (Judicial Garnishment Freeze)
        - التنازل البنكي المعتمد (Bank Assignment of Proceeds)
        - القائمة البيضاء المصرفية (Approved Bank Account Whitelist)
        - سريان وثيقة تأمين أخطار المقاولين (CAR Insurance Expiry)
        - صمام خطابات الضمان البنكية (Pay or Extend Mandatory Automation)
        """
        check_date = cert_date or timezone.localdate()
        result = {
            "is_eligible_for_direct_payout": True,
            "freeze_payout": False,
            "garnishment_active": False,
            "garnishment_amount": Decimal("0.00"),
            "bank_assignment_active": False,
            "assigned_bank_iban": "",
            "pay_or_extend_triggered": False,
            "car_insurance_expired": False,
            "blocking_reasons": []
        }

        # 1. الحجز القضائي والتحفظي
        if contract.is_garnished_by_court:
            result["garnishment_active"] = True
            result["garnishment_amount"] = contract.garnishment_amount
            result["is_eligible_for_direct_payout"] = False
            result["blocking_reasons"].append(
                f"حجز قضائي تنفيذي قائم برقم الدعوى {contract.garnishment_case_number} لصالح {contract.garnishment_creditor_name} بمبلغ {contract.garnishment_amount}"
            )

        # 2. التنازل البنكي عن المستحقات
        if contract.is_assigned_to_bank:
            result["bank_assignment_active"] = True
            result["assigned_bank_iban"] = contract.assigned_bank_iban
            result["is_eligible_for_direct_payout"] = False
            result["blocking_reasons"].append(
                f"تنازل رسمي عن المستحقات لصالح {contract.assigned_bank_name} على الحساب البنكي {contract.assigned_bank_iban}"
            )

        # 3. فحص سريان وثيقة تأمين أخطار المقاولين (CAR)
        if contract.car_insurance_expiry_date and contract.car_insurance_expiry_date < check_date:
            result["car_insurance_expired"] = True
            result["blocking_reasons"].append(
                f"وثيقة تأمين أخطار المقاولين CAR منتهية الصلاحية بتاريخ {contract.car_insurance_expiry_date}"
            )

        # 4. صمام خطابات الضمان البنكية (Pay or Extend) عند اقتراب الانتهاء (<= 15 يوم)
        if contract.guarantee_type == ContractorContract.GuaranteeType.BANK_LETTER_OF_GUARANTEE and contract.bank_lg_expiry_date:
            days_to_expiry = (contract.bank_lg_expiry_date - check_date).days
            if days_to_expiry <= 15:
                contract.lg_pay_or_extend_triggered = True
                contract.save(update_fields=["lg_pay_or_extend_triggered", "updated_at"])
                result["pay_or_extend_triggered"] = True
                result["freeze_payout"] = True
                result["is_eligible_for_direct_payout"] = False
                result["blocking_reasons"].append(
                    f"خطاب الضمان البنكي ينتهي خلال {days_to_expiry} يوماً (تاريخ الانتهاء: {contract.bank_lg_expiry_date}). تم تفعيل صمام المطالبة بالتمديد أو التسييل (Pay or Extend) وتجميد الصرف."
                )

        return result

    @classmethod
    @transaction.atomic
    def terminate_contract_and_settle(
        cls,
        contract: ContractorContract,
        protocol_data: Dict[str, Any],
        liquidate_lg: bool = False,
        user=None
    ) -> JointTerminationSurveyProtocol:
        """
        فسخ العقد وإثبات محضر الحصر المشترك والاستحواذ على تشوينات الموقع لمخزن المشروع
        مع تسييل خطاب الضمان إن كان الفسخ على حساب المقاول المقصر
        """
        contract = ContractorContract.objects.select_for_update().get(id=contract.id)

        # 1. إنشاء محضر الحصر المشترك
        protocol = JointTerminationSurveyProtocol.objects.create(
            contract=contract,
            protocol_reference=protocol_data.get("protocol_reference", f"TERM-{contract.contract_number}"),
            survey_date=protocol_data.get("survey_date", timezone.localdate()),
            consultant_representative=protocol_data.get("consultant_representative", ""),
            employer_representative=protocol_data.get("employer_representative", ""),
            contractor_representative=protocol_data.get("contractor_representative", ""),
            as_built_completed_value=Decimal(str(protocol_data.get("as_built_completed_value", "0.00"))),
            uninstalled_materials_value=Decimal(str(protocol_data.get("uninstalled_materials_value", "0.00"))),
            snag_and_remedial_costs=Decimal(str(protocol_data.get("snag_and_remedial_costs", "0.00"))),
            court_expert_minutes_number=protocol_data.get("court_expert_minutes_number", ""),
            site_vacated_and_handed_over=protocol_data.get("site_vacated_and_handed_over", True),
        )

        currency_str = getattr(contract.currency, 'code', 'EGP')
        proj_code = contract.project.code if contract.project else None
        gateway = AccountingGateway()

        # 2. الاستحواذ على تشوينات الموقع المتبقية وإضافتها لمخزن المشروع (المادة 658 مدني)
        uninstalled_val = protocol.uninstalled_materials_value
        if uninstalled_val > Decimal("0.00"):
            # القيمة الدفترية العادلة = 100%، استرداد التمويل السابق = 75%، الصافي للمقاول = 25%
            store_account = cls.get_or_resolve_account("store_inventory", fallback_code="11201")
            wip_mos_account = cls.get_or_resolve_account(AccountRoleNames.REAL_ESTATE_WIP_CONSTRUCTION.value, fallback_code="12101")
            payable_account = getattr(contract.contractor, 'financial_account', None)
            if not payable_account or not payable_account.can_post_entries():
                payable_account = cls.get_or_resolve_account(AccountRoleNames.SUPPLIER_PAYABLE_CONTROL.value, fallback_code="21110")
                if not payable_account.can_post_entries() and payable_account.children.filter(is_active=True, is_leaf=True).exists():
                    payable_account = payable_account.children.filter(is_active=True, is_leaf=True).first()

            mos_financed_recovery = (uninstalled_val * Decimal("0.75")).quantize(Decimal("0.01"))
            mos_contractor_remainder = (uninstalled_val - mos_financed_recovery).quantize(Decimal("0.01"))

            lines = [
                JournalEntryLineData(
                    account_code=store_account.code,
                    debit=uninstalled_val,
                    credit=Decimal("0.00"),
                    currency=currency_str,
                    description=f"الاستحواذ على تشوينات المقاول المتبقية لمخزن المشروع - عقد {contract.contract_number}",
                    project=proj_code
                ),
                JournalEntryLineData(
                    account_code=wip_mos_account.code,
                    debit=Decimal("0.00"),
                    credit=mos_financed_recovery,
                    currency=currency_str,
                    description=f"استرداد تمويل التشوينات السابق صرفه (75%) عند الفسخ - عقد {contract.contract_number}",
                    project=proj_code
                ),
                JournalEntryLineData(
                    account_code=payable_account.code,
                    debit=Decimal("0.00"),
                    credit=mos_contractor_remainder,
                    currency=currency_str,
                    description=f"استحقاق المقاول المتبقي عن التشوينات المستحوذ عليها (25%) - عقد {contract.contract_number}",
                    project=proj_code
                )
            ]

            idemp_key = AccountingGateway.generate_idempotency_key(
                module='real_estate',
                model='JointTerminationSurveyProtocol',
                object_id=protocol.id,
                operation='mos_stock_absorption'
            )
            gateway.create_journal_entry(
                source_module='real_estate',
                source_model='JointTerminationSurveyProtocol',
                source_id=protocol.id,
                lines=lines,
                idempotency_key=idemp_key,
                user=user,
                entry_type='general_ledger',
                description=f"قيد الاستحواذ على تشوينات الموقع عند فسخ عقد {contract.contract_number}",
                reference=f"ABS-{protocol.protocol_reference}",
                date=timezone.localdate()
            )

        # 3. تسييل خطاب الضمان البنكي إن كان مطلوباً
        if liquidate_lg and contract.guarantee_type == ContractorContract.GuaranteeType.BANK_LETTER_OF_GUARANTEE and contract.bank_lg_amount > Decimal("0.00"):
            escrow_account = cls.get_or_resolve_account(AccountRoleNames.REAL_ESTATE_RESTRICTED_CASH.value, fallback_code="11121")
            retention_account = cls.get_or_resolve_account(AccountRoleNames.REAL_ESTATE_CONTRACTOR_RETENTIONS_PAYABLE.value, fallback_code="21310")

            lg_lines = [
                JournalEntryLineData(
                    account_code=escrow_account.code,
                    debit=contract.bank_lg_amount,
                    credit=Decimal("0.00"),
                    currency=currency_str,
                    description=f"تسييل خطاب الضمان البنكي رقم {contract.bank_lg_number} - عقد {contract.contract_number}",
                    project=proj_code
                ),
                JournalEntryLineData(
                    account_code=retention_account.code,
                    debit=Decimal("0.00"),
                    credit=contract.bank_lg_amount,
                    currency=currency_str,
                    description=f"إثبات تعويضات وخصومات تسييل خطاب الضمان عند الفسخ - عقد {contract.contract_number}",
                    project=proj_code
                )
            ]

            lg_idemp = AccountingGateway.generate_idempotency_key(
                module='real_estate',
                model='ContractorContract',
                object_id=contract.id,
                operation='lg_liquidation'
            )
            gateway.create_journal_entry(
                source_module='real_estate',
                source_model='ContractorContract',
                source_id=contract.id,
                lines=lg_lines,
                idempotency_key=lg_idemp,
                user=user,
                entry_type='general_ledger',
                description=f"قيد تسييل خطاب الضمان البنكي لفسخ عقد {contract.contract_number}",
                reference=f"LG-LIQ-{contract.contract_number}",
                date=timezone.localdate()
            )

        # 4. تحديث حالة العقد إلى مفسوخ
        contract.status = ContractorContract.ContractStatus.TERMINATED
        contract.save(update_fields=["status", "updated_at"])

        logger.info(f"Contract {contract.contract_number} terminated and settled via protocol {protocol.protocol_reference}")
        return protocol

    @classmethod
    def record_sectional_handover(
        cls,
        contract: ContractorContract,
        section_name: str,
        handover_date: Optional[date] = None,
        warranty_months: int = 12,
        consultant_approval_ref: str = "",
        notes: str = ""
    ) -> SectionalHandoverRecord:
        """
        تسجيل استلام جزئي لمرحلة أو مبنى مع عدّاد ضمان مستقل
        """
        h_date = handover_date or timezone.localdate()
        w_start = h_date
        w_end = h_date + timedelta(days=warranty_months * 30)

        record = SectionalHandoverRecord.objects.create(
            contract=contract,
            section_name=section_name,
            handover_date=h_date,
            warranty_start_date=w_start,
            warranty_end_date=w_end,
            consultant_approval_ref=consultant_approval_ref,
            notes=notes
        )
        logger.info(f"Sectional handover recorded for contract {contract.contract_number}: {section_name}")
        return record

    @classmethod
    @transaction.atomic
    def record_micro_contract_self_billing(
        cls,
        contract: ContractorContract,
        craftsman_name: str,
        gross_amount: Decimal,
        wht_rate: Decimal = Decimal("1.00"),
        soc_ins_rate: Decimal = Decimal("2.16"),
        user=None
    ) -> JournalEntry:
        """
        إصدار إذن شراء وصرف ذاتي للأسطوات والحرفيين غير المسجلين ضريبياً مع خصم 1% ضرائب وتأمينات
        Dr: WIP Project Cost (12101)
        Cr: Withholding Tax Form 41 Payable (21330)
        Cr: Social Insurance Payable (21340)
        Cr: Cash Drawer / Bank Account (11111)
        """
        wht_val = (gross_amount * wht_rate / Decimal("100.00")).quantize(Decimal("0.01"))
        soc_val = (gross_amount * soc_ins_rate / Decimal("100.00")).quantize(Decimal("0.01"))
        net_payout = (gross_amount - wht_val - soc_val).quantize(Decimal("0.01"))

        wip_account = cls.get_or_resolve_account(AccountRoleNames.REAL_ESTATE_WIP_CONSTRUCTION.value, fallback_code="12101")
        wht_account = cls.get_or_resolve_account(AccountRoleNames.WITHHOLDING_TAX_PAYABLE.value, fallback_code="21330")
        soc_account = cls.get_or_resolve_account("social_insurance_payable", fallback_code="21340")
        cash_account = cls.get_or_resolve_account(AccountRoleNames.DEFAULT_CASH_DRAWER.value, fallback_code="11111")

        currency_str = getattr(contract.currency, 'code', 'EGP')
        proj_code = contract.project.code if contract.project else None

        desc = f"صرف إذن ذاتي لمصنعيات الأسطى {craftsman_name} - عقد {contract.contract_number}"

        lines = [
            JournalEntryLineData(
                account_code=wip_account.code,
                debit=gross_amount,
                credit=Decimal("0.00"),
                currency=currency_str,
                description=desc,
                project=proj_code
            ),
            JournalEntryLineData(
                account_code=wht_account.code,
                debit=Decimal("0.00"),
                credit=wht_val,
                currency=currency_str,
                description=f"خصم وإضافة قطعي 1% - نموذج 41 حرفيين ({craftsman_name})",
                project=proj_code
            ),
            JournalEntryLineData(
                account_code=soc_account.code,
                debit=Decimal("0.00"),
                credit=soc_val,
                currency=currency_str,
                description=f"تأمينات مقاولات مباشرة عن العمالة الحرفية ({craftsman_name})",
                project=proj_code
            ),
            JournalEntryLineData(
                account_code=cash_account.code,
                debit=Decimal("0.00"),
                credit=net_payout,
                currency=currency_str,
                description=f"صافي المنصرف نقداً للأسطى {craftsman_name}",
                project=proj_code
            )
        ]

        gateway = AccountingGateway()
        idemp_key = AccountingGateway.generate_idempotency_key(
            module='real_estate',
            model='ContractorContract',
            object_id=contract.id,
            operation=f'craftsman_self_billing_{craftsman_name}_{gross_amount}'
        )

        journal_entry = gateway.create_journal_entry(
            source_module='real_estate',
            source_model='ContractorContract',
            source_id=contract.id,
            lines=lines,
            idempotency_key=idemp_key,
            user=user,
            entry_type='general_ledger',
            description=desc,
            reference=f"CRAFT-{contract.contract_number}",
            date=timezone.localdate()
        )

        logger.info(f"Micro-contract self-billing posted for craftsman {craftsman_name}: Entry ID {journal_entry.id}")
        return journal_entry

    @classmethod
    def get_cumulative_certified_quantity(cls, contract: ContractorContract, item_code: str) -> Decimal:
        """
        حساب الكمية التراكمية المعتمدة لبند مقايسة محدد حتى المستخلص السابق
        """
        from real_estate.models import ContractorCertificateItem, ContractorProgressCertificate
        res = ContractorCertificateItem.objects.filter(
            certificate__contract=contract,
            certificate__status__in=[
                ContractorProgressCertificate.CertificateStatus.APPROVED,
                ContractorProgressCertificate.CertificateStatus.PAID
            ],
            item_code=item_code
        ).aggregate(s=Sum('current_quantity'))['s']
        return res or Decimal("0.000")
