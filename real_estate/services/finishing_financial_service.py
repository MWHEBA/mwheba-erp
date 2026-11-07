# -*- coding: utf-8 -*-
"""
Finishing Financial & IFRS 15 Revenue Service
MWHEBA ERP — Track 2: Financial Governance, Escrow Accounting & Subcontractor Netting

Handles:
- IFRS 15 independent accrual journal entry generation (11220 / 41200 / 21320 Table Tax 5% code T2).
- Segregated legal installment plan generation (FinishingInstallmentPlan).
- Advance deposit collection into Project Escrow Bank Sub-Account.
- Subcontractor final certificate penalty netting & 5% warranty retention deduction.
- Cancellation sunk costs settlement (demolition + non-returnable materials + labor + supervision).
- As-built true-up reconciliation & variance settlement.
- Store material requisition with strict quota controls.
- Store material returns with cost reversal.
"""
import calendar
import logging
import uuid
from decimal import Decimal
from datetime import date, timedelta
from typing import Dict, Any, Optional, Tuple, List

from django.db import transaction, models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from real_estate.models.finishing import (
    FinishingWorkspace,
    FinishingItemSpec,
    UnitFinishingOrder,
    UnitFinishingOrderItem,
    FinishingAdvanceDeposit,
    FinishingInstallmentPlan,
    FinishingInstallmentItem,
    SubcontractorPenaltySettlementRecord,
    FinishingCancellationSettlement,
    FinishingAsBuiltReconciliation,
    FinishingMaterialRequisition,
)
from financial.models import (
    ChartOfAccounts,
    AccountType,
    AccountingPeriod,
    JournalEntry,
    JournalEntryLine,
)

logger = logging.getLogger(__name__)


def get_or_create_open_period(entry_date: date, user=None) -> AccountingPeriod:
    """الحصول على أو إنشاء الفترة المحاسبية المفتوحة للتاريخ المحدد"""
    period = AccountingPeriod.objects.filter(
        status='OPEN',
        start_date__lte=entry_date,
        end_date__gte=entry_date
    ).first()
    if not period:
        first_day = entry_date.replace(day=1)
        _, last_day_num = calendar.monthrange(entry_date.year, entry_date.month)
        last_day = entry_date.replace(day=last_day_num)
        period, _ = AccountingPeriod.objects.get_or_create(
            name=f"فترة {entry_date.month}/{entry_date.year}",
            period_number=entry_date.month,
            start_date=first_day,
            end_date=last_day,
            defaults={'status': 'OPEN', 'created_by': user}
        )
    return period


def get_or_create_chart_account(code: str, name: str, type_code: str, user=None) -> ChartOfAccounts:
    """الحصول على أو إنشاء حساب في شجرة الحسابات"""
    account = ChartOfAccounts.objects.filter(code=code).first()
    if not account:
        account_type, _ = AccountType.objects.get_or_create(
            code=type_code,
            defaults={'name': type_code, 'name_en': type_code, 'is_active': True}
        )
        account = ChartOfAccounts.objects.create(
            code=code,
            name=name,
            account_type=account_type,
            is_active=True,
            created_by=user
        )
    return account


class FinishingEscrowAccountSyncService:
    """
    خدمة حوكمة حساب الضمان المصرفي للمشروع (Escrow Account):
    تضمن توجيه كافة التدفقات النقدية الخاصة بأوامر التشطيب حصرياً إلى الحساب المصرفي الفرعي لضمان المشروع.
    """

    @classmethod
    def validate_escrow_routing(cls, project, target_bank_account_number: Optional[str] = None) -> bool:
        """
        التحقق من توجيه الإيداع لحساب الضمان المصرفي للمشروع
        """
        # إذا كان المشروع يحدد حساب ضمان مصرفي
        if hasattr(project, 'escrow_account_number') and project.escrow_account_number:
            if target_bank_account_number and target_bank_account_number != project.escrow_account_number:
                raise ValidationError(
                    _(f"محظور إيداع متحصلات التشطيب خارج حساب الضمان المصرفي للمشروع '{project.name}' (الحساب المعتمد: {project.escrow_account_number}).")
                )
        return True


class FinishingFinancialService:
    """
    خدمة التوليد المالي المستقل IFRS 15:
    - توليد قيود الاستحقاق المحاسبي وضريبة الجدول 5% كود T2.
    - تسجيل الدفعة المقدمة 35% بحساب الضمان.
    - توليد خطة أقساط التشطيب المستقلة قانونياً.
    """

    TABLE_TAX_RATE = Decimal('0.05')  # ضريبة الجدول 5% كود T2

    @classmethod
    @transaction.atomic
    def create_accrual_journal_entry(
        cls,
        order: UnitFinishingOrder,
        user=None
    ) -> Tuple[JournalEntry, Decimal]:
        """
        توليد قيد الاستحقاق المحاسبي المستقل لمعيار IFRS 15:
        - مدين: عملاء تشطيبات وتعديلات وحدات (11220) بقيمة الإجمالي شامل الضريبة
        - دائن: إيرادات أعمال تشطيب وتعديلات عملاء (41200) بصافي القيمة
        - دائن: مصلحة الضرائب - ضريبة الجدول 5% كود T2 (21320)
        """
        if order.accrual_journal_entry:
            return order.accrual_journal_entry, round(order.gross_finishing_amount * cls.TABLE_TAX_RATE, 2)

        net_finishing_revenue = order.gross_finishing_amount
        table_tax_amount = round(net_finishing_revenue * cls.TABLE_TAX_RATE, 2)
        total_customer_debit = net_finishing_revenue + table_tax_amount

        entry_date = timezone.now().date()
        period = get_or_create_open_period(entry_date, user)

        # الحسابات الدفترية
        receivable_account = get_or_create_chart_account(
            code='11220',
            name='عملاء تشطيبات وتعديلات وحدات',
            type_code='ASSET',
            user=user
        )
        revenue_account = get_or_create_chart_account(
            code='41200',
            name='إيرادات أعمال تشطيب وتعديلات عملاء',
            type_code='REVENUE',
            user=user
        )
        table_tax_account = get_or_create_chart_account(
            code='21320',
            name='مصلحة الضرائب - ضريبة الجدول 5% كود T2',
            type_code='LIABILITY',
            user=user
        )

        entry_number = f"JE-FIN-{order.order_number}-{timezone.now().strftime('%Y%m%d%H%M%S')}"
        journal_entry = JournalEntry.objects.create(
            number=entry_number,
            date=entry_date,
            entry_type='STANDARD',
            status='POSTED',
            description=f"قيد استحقاق إيرادات وضريبة مقايسة تشطيب الوحدة {order.unit.unit_code} للعميل {order.customer.name}",
            source_module='REAL_ESTATE',
            source_model='UnitFinishingOrder',
            source_id=order.id,
            accounting_period=period,
            created_by=user or order.created_by
        )

        # 1. طرف المدين: العميل
        JournalEntryLine.objects.create(
            journal_entry=journal_entry,
            account=receivable_account,
            debit=total_customer_debit,
            credit=Decimal('0.00'),
            description=f"إثبات مديونية التشطيب وضريبة الجدول على العميل {order.customer.name}"
        )

        # 2. طرف الدائن: الإيراد
        JournalEntryLine.objects.create(
            journal_entry=journal_entry,
            account=revenue_account,
            debit=Decimal('0.00'),
            credit=net_finishing_revenue,
            description=f"إيرادات تشطيب وتعديل للوحدة {order.unit.unit_code}"
        )

        # 3. طرف الدائن: ضريبة الجدول 5%
        JournalEntryLine.objects.create(
            journal_entry=journal_entry,
            account=table_tax_account,
            debit=Decimal('0.00'),
            credit=table_tax_amount,
            description="ضريبة الجدول المقررة 5% كود T2 لصالح مصلحة الضرائب المصرية"
        )

        order.accrual_journal_entry = journal_entry
        order.save(update_fields=['accrual_journal_entry', 'updated_at'])

        logger.info(f"Accrual Journal Entry created: {journal_entry.number} for Order {order.order_number}")
        return journal_entry, table_tax_amount

    @classmethod
    @transaction.atomic
    def record_advance_deposit(
        cls,
        order: UnitFinishingOrder,
        payment_amount: Decimal,
        receipt_date: Optional[date] = None,
        target_bank_account_number: Optional[str] = None,
        user=None,
        notes: str = ""
    ) -> FinishingAdvanceDeposit:
        """
        تسجيل تحصيل الدفعة المقدمة وتوجيهها لحساب الضمان المصرفي للمشروع:
        - تحديث إجمالي الدفعة المسددة بالطلب.
        - إنشاء سند الدفعة وحفظ القيد المحاسبي.
        """
        # التحقق من حساب الضمان
        FinishingEscrowAccountSyncService.validate_escrow_routing(order.unit.project, target_bank_account_number)

        payment_date = receipt_date or timezone.now().date()
        period = get_or_create_open_period(payment_date, user)

        # الحسابات
        escrow_bank_account = get_or_create_chart_account(
            code='11120',
            name='حساب الضمان المصرفي للمشروع - البنك',
            type_code='ASSET',
            user=user
        )
        advance_liability_account = get_or_create_chart_account(
            code='21410',
            name='دفعات مقدمة من العملاء - تشطيبات',
            type_code='LIABILITY',
            user=user
        )

        entry_number = f"JE-DEP-{order.order_number}-{timezone.now().strftime('%Y%m%d%H%M%S')}"
        je = JournalEntry.objects.create(
            number=entry_number,
            date=payment_date,
            entry_type='STANDARD',
            status='POSTED',
            description=f"تحصيل دفعة مقدمة تشطيب للوحدة {order.unit.unit_code} بحساب الضمان",
            source_module='REAL_ESTATE',
            source_model='FinishingAdvanceDeposit',
            accounting_period=period,
            created_by=user or order.created_by
        )

        # مدين: بنك الضمان
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=escrow_bank_account,
            debit=payment_amount,
            credit=Decimal('0.00'),
            description=f"إيداع دفعة تشطيب الوحدة {order.unit.unit_code} بحساب الضمان"
        )
        # دائن: التزام دفعات مقدمة
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=advance_liability_account,
            debit=Decimal('0.00'),
            credit=payment_amount,
            description=f"دفعة مقدمة تشطيب محصلة من العميل {order.customer.name}"
        )

        deposit_count = order.deposits.count() + 1
        deposit_record = FinishingAdvanceDeposit.objects.create(
            order=order,
            receipt_number=f"DEP-{order.order_number}-{deposit_count:02d}",
            amount=payment_amount,
            receipt_date=payment_date,
            allocation_target='ADVANCE_35_PCT',
            journal_entry=je,
            notes=notes,
            created_by=user or order.created_by
        )

        order.total_deposit_paid = (order.total_deposit_paid or Decimal('0.00')) + payment_amount
        order.save(update_fields=['total_deposit_paid', 'updated_at'])

        return deposit_record

    @classmethod
    @transaction.atomic
    def generate_segregated_installment_plan(
        cls,
        order: UnitFinishingOrder,
        number_of_installments: int,
        start_date: date,
        frequency_months: int = 3,
        user=None
    ) -> FinishingInstallmentPlan:
        """
        توليد خطة أقساط التشطيب المستقلة قانونياً عن عقد الوحدة:
        - حساب الرصيد المجدول = (إجمالي التشطيب - المسدد مقدماً).
        - توزيع الأقساط بالتساوي وتعديل الفروق الكسرية في القسط الأخير.
        """
        if order.finishing_installment_plan:
            return order.finishing_installment_plan

        total_finishing = order.gross_finishing_amount
        deposit_paid = order.total_deposit_paid or Decimal('0.00')
        scheduled_balance = total_finishing - deposit_paid

        if scheduled_balance <= Decimal('0.00'):
            raise ValidationError(_("لا يوجد رصيد متبقٍ لجدولته بعد سداد الدفعة المقدمة بالكامل."))

        if number_of_installments < 1:
            raise ValidationError(_("عدد الأقساط يجب ألا يقل عن قسط واحد."))

        plan = FinishingInstallmentPlan.objects.create(
            plan_number=f"FPLN-{order.order_number}",
            customer=order.customer,
            unit=order.unit,
            total_finishing_amount=total_finishing,
            down_payment_paid=deposit_paid,
            scheduled_balance=scheduled_balance,
            number_of_installments=number_of_installments,
            start_date=start_date,
            status='ACTIVE',
            created_by=user or order.created_by
        )

        base_installment = (scheduled_balance / Decimal(number_of_installments)).quantize(Decimal('0.01'))
        running_total = Decimal('0.00')

        current_date = start_date
        for i in range(1, number_of_installments + 1):
            if i == number_of_installments:
                installment_amount = scheduled_balance - running_total
            else:
                installment_amount = base_installment
                running_total += installment_amount

            FinishingInstallmentItem.objects.create(
                plan=plan,
                installment_number=i,
                due_date=current_date,
                amount=installment_amount,
                paid_amount=Decimal('0.00'),
                is_settled=False,
                milestone_trigger_name=f"قسط تشطيب رقم {i}"
            )
            # إضافة الشهور للتاريخ
            # بسيطة وآمنة
            year = current_date.year + (current_date.month + frequency_months - 1) // 12
            month = (current_date.month + frequency_months - 1) % 12 + 1
            day = min(current_date.day, calendar.monthrange(year, month)[1])
            current_date = date(year, month, day)

        order.finishing_installment_plan = plan
        order.save(update_fields=['finishing_installment_plan', 'updated_at'])

        logger.info(f"Finishing Installment Plan generated: {plan.plan_number} with {number_of_installments} installments.")
        return plan


class FinishingSubcontractorPenaltyNettingService:
    """
    خدمة مقاصة غرامات مقاولي الباطن واستقطاع تأمين الضمان 5% بالمستخلص الختامي
    """

    WARRANTY_RETENTION_RATE = Decimal('0.05')  # 5% تأمين ضمان أعمال

    @classmethod
    @transaction.atomic
    def net_subcontractor_final_certificate(
        cls,
        order: UnitFinishingOrder,
        contractor,
        gross_final_certificate_amount: Decimal,
        delay_penalties: Decimal = Decimal('0.00'),
        safety_violations: Decimal = Decimal('0.00'),
        debris_and_damages: Decimal = Decimal('0.00'),
        user=None
    ) -> SubcontractorPenaltySettlementRecord:
        """
        إجراء المقاصة الختامية وتوليد كشف التسوية:
        - استقطاع 5% تأمين ضمان أعمال.
        - خصم غرامات التأخير ومخالفات السلامة وتلفيات المرافق المشتركة.
        - استخراج صافي المستحق للصرف.
        """
        warranty_retention = round(gross_final_certificate_amount * cls.WARRANTY_RETENTION_RATE, 2)
        total_penalties = delay_penalties + safety_violations + debris_and_damages

        net_payable = gross_final_certificate_amount - warranty_retention - total_penalties
        if net_payable < Decimal('0.00'):
            net_payable = Decimal('0.00')

        record = SubcontractorPenaltySettlementRecord.objects.create(
            contractor=contractor,
            order=order,
            gross_final_certificate_amount=gross_final_certificate_amount,
            delay_penalties_amount=delay_penalties,
            safety_violations_amount=safety_violations,
            debris_and_damages_amount=debris_and_damages,
            total_penalties_netted=total_penalties,
            net_payable_amount=net_payable,
            settlement_approved_by=user,
            settled_at=timezone.now()
        )

        logger.info(f"Subcontractor settlement: Gross={gross_final_certificate_amount}, Retention={warranty_retention}, Penalties={total_penalties}, Net={net_payable}")
        return record


class FinishingCancellationService:
    """
    خدمة تصفية الإلغاء وحساب التكاليف الغارقة (Sunk Costs):
    - حساب الهدم الميداني المنفذ.
    - حساب الخامات المخصوصة المقطعة غير القابلة للارتجاع.
    - حساب أجور العمالة المستهلكة.
    - حساب أتعاب الإشراف الهندسي المستحقة.
    - إجراء المقاصة مع الدفعة المسددة وتحديد المسترد أو المطالبة.
    """

    @classmethod
    @transaction.atomic
    def settle_order_cancellation(
        cls,
        order: UnitFinishingOrder,
        executed_demolition_cost: Decimal,
        custom_materials_scrap_cost: Decimal,
        labor_costs_incurred: Decimal,
        earned_supervision_fee: Decimal,
        cancellation_reason: str,
        user=None
    ) -> FinishingCancellationSettlement:
        """
        تصفية إلغاء أمر التشطيب وإغلاق الملف
        """
        total_sunk_costs = (
            executed_demolition_cost +
            custom_materials_scrap_cost +
            labor_costs_incurred +
            earned_supervision_fee
        )
        deposit_paid = order.total_deposit_paid or Decimal('0.00')

        if deposit_paid >= total_sunk_costs:
            net_refundable = deposit_paid - total_sunk_costs
            shortfall = Decimal('0.00')
        else:
            net_refundable = Decimal('0.00')
            shortfall = total_sunk_costs - deposit_paid

        settlement_num = f"CANC-SETTL-{order.order_number}"
        settlement = FinishingCancellationSettlement.objects.create(
            order=order,
            settlement_number=settlement_num,
            cancellation_date=timezone.now().date(),
            cancellation_reason=cancellation_reason,
            executed_demolition_cost=executed_demolition_cost,
            custom_materials_scrap_cost=custom_materials_scrap_cost,
            labor_costs_incurred=labor_costs_incurred,
            earned_supervision_fee=earned_supervision_fee,
            total_sunk_costs=total_sunk_costs,
            deposit_paid=deposit_paid,
            net_refundable_to_client=net_refundable,
            shortfall_due_from_client=shortfall,
            is_settled_and_closed=True,
            approved_by=user
        )

        order.current_stage = 'CANCELLED'
        order.save(update_fields=['current_stage', 'updated_at'])

        logger.info(f"Finishing cancellation settled: Sunk={total_sunk_costs}, Deposit={deposit_paid}, Refund={net_refundable}, Shortfall={shortfall}")
        return settlement


class FinishingAsBuiltTrueUpService:
    """
    خدمة تسوية وتصفية الحصر الميداني الفعلي (As-Built True-Up):
    مقارنة التقديري بالفعلي وتوليد فروق التسوية
    """

    @classmethod
    @transaction.atomic
    def reconcile_as_built_quantities(
        cls,
        order: UnitFinishingOrder,
        actual_as_built_total: Decimal,
        user=None
    ) -> FinishingAsBuiltReconciliation:
        """
        إجراء تسوية الحصر الفعلي الختامي للطلب
        """
        estimated_total = order.gross_finishing_amount
        variance = actual_as_built_total - estimated_total

        if variance > Decimal('0.00'):
            action = 'CLIENT_ADDITIONAL_INVOICE'
        elif variance < Decimal('0.00'):
            action = 'CLIENT_CREDIT_REFUND'
        else:
            action = 'ZERO_VARIANCE'

        reconciliation, _ = FinishingAsBuiltReconciliation.objects.update_or_create(
            order=order,
            defaults={
                'reconciliation_number': f"RECON-{order.order_number}",
                'reconciliation_date': timezone.now().date(),
                'estimated_boq_total': estimated_total,
                'actual_as_built_total': actual_as_built_total,
                'variance_amount': variance,
                'balancing_action': action,
                'is_finalized': True,
                'approved_by': user
            }
        )
        return reconciliation


class FinishingStoreRequisitionService:
    """
    خدمة صرف الخامات واستهلاك كوتة المقايسة المعتمدة:
    تمنع صرف كميات من المخزن تتجاوز كوتة البند المعتمدة في المقايسة.
    """

    @classmethod
    @transaction.atomic
    def issue_materials_from_store(
        cls,
        order_item: UnitFinishingOrderItem,
        product,
        warehouse,
        contractor,
        quantity_to_issue: Decimal,
        user=None
    ) -> FinishingMaterialRequisition:
        """
        صرف خامات من المخزن للوحدة مع فحص الكوتة الهندسية
        """
        current_issued = order_item.issued_quantity_from_store or Decimal('0.00')
        max_allowed = order_item.gross_quantity

        if current_issued + quantity_to_issue > max_allowed:
            raise ValidationError(
                _(f"لا يمكن صرف الكمية المطلوبة ({quantity_to_issue}). إجمالي المنصرف ({current_issued}) سيتجاوز كوتة البند المعتمدة ({max_allowed} {order_item.measuring_unit}).")
            )

        req_num = f"REQ-MAT-{order_item.order.order_number}-{order_item.id}-{uuid.uuid4().hex[:8]}"
        req = FinishingMaterialRequisition.objects.create(
            requisition_number=req_num,
            order=order_item.order,
            order_item=order_item,
            product=product,
            warehouse=warehouse,
            contractor=contractor,
            transaction_type='ISSUE',
            quantity_requested=quantity_to_issue,
            quantity_issued=quantity_to_issue,
            issue_date=timezone.now().date(),
            is_cost_reversed=False,
            created_by=user
        )

        order_item.issued_quantity_from_store = current_issued + quantity_to_issue
        order_item.save(update_fields=['issued_quantity_from_store'])

        return req


class FinishingMaterialReturnService:
    """
    خدمة ارتجاع الفائض السليم للمخزن وعكس التكلفة
    """

    @classmethod
    @transaction.atomic
    def return_materials_to_store(
        cls,
        order_item: UnitFinishingOrderItem,
        product,
        warehouse,
        contractor,
        quantity_to_return: Decimal,
        return_reason: str = "",
        user=None
    ) -> FinishingMaterialRequisition:
        """
        إثبات إذن ارتجاع خامات سليمة للمخزن وعكس كوتة المنصرف
        """
        current_issued = order_item.issued_quantity_from_store or Decimal('0.00')

        if quantity_to_return > current_issued:
            raise ValidationError(
                _(f"الكمية المراد ارتجاعها ({quantity_to_return}) تتجاوز إجمالي المنصرف فعلياً للوحدة ({current_issued}).")
            )

        req_num = f"RET-MAT-{order_item.order.order_number}-{order_item.id}-{uuid.uuid4().hex[:8]}"
        ret = FinishingMaterialRequisition.objects.create(
            requisition_number=req_num,
            order=order_item.order,
            order_item=order_item,
            product=product,
            warehouse=warehouse,
            contractor=contractor,
            transaction_type='RETURN',
            quantity_requested=quantity_to_return,
            quantity_issued=quantity_to_return,
            issue_date=timezone.now().date(),
            return_reason=return_reason,
            is_cost_reversed=True,
            created_by=user
        )

        order_item.issued_quantity_from_store = current_issued - quantity_to_return
        order_item.save(update_fields=['issued_quantity_from_store'])

        return ret
