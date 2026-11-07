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
from product.models import (
    StockMovement,
    StockLedgerEntry,
    InventoryCostLayer,
    InventoryCostConsumption,
)

logger = logging.getLogger(__name__)


def get_or_create_open_period(entry_date: date, user=None) -> AccountingPeriod:
    """الحصول على أو إنشاء الفترة المحاسبية المفتوحة للتاريخ المحدد"""
    # 1. التحقق من أي فترة محاسبية معتمدة تغطي هذا التاريخ وفق سياسة الترحيل المركزية
    existing_period = AccountingPeriod.objects.filter(
        start_date__lte=entry_date,
        end_date__gte=entry_date
    ).first()
    if existing_period and not existing_period.can_post_entries():
        raise ValidationError(_(f"الفترة المحاسبية لهذا التاريخ ({entry_date}) مقفلة ولا يمكن الترحيل فيها (الحالة: {existing_period.status})."))

    # فحص أي فترات أخرى غير مفتوحة تغطي هذا التاريخ (مثل soft_closed, closed, hard_closed)
    if AccountingPeriod.objects.filter(start_date__lte=entry_date, end_date__gte=entry_date).exclude(status='open').exists():
        raise ValidationError(_(f"الفترة المحاسبية لهذا التاريخ ({entry_date}) مقفلة ولا يمكن الترحيل فيها."))

    # 2. البحث عن فترة مفتوحة
    period = AccountingPeriod.objects.filter(
        status='open',
        start_date__lte=entry_date,
        end_date__gte=entry_date
    ).first()
    if not period:
        first_day = entry_date.replace(day=1)
        _weekday, last_day_num = calendar.monthrange(entry_date.year, entry_date.month)
        last_day = entry_date.replace(day=last_day_num)

        # التأكد من عدم وجود أي تداخل مع فترات غير مفتوحة
        overlapping_non_open = AccountingPeriod.objects.filter(
            start_date__lte=last_day,
            end_date__gte=first_day
        ).exclude(status='open').exists()
        if overlapping_non_open:
            raise ValidationError(_("لا يمكن إنشاء فترة محاسبية مفتوحة لوجود تداخل مع فترة مالية مقفلة."))

        period, _created = AccountingPeriod.objects.get_or_create(
            name=f"فترة {entry_date.month}/{entry_date.year}",
            period_number=entry_date.month,
            start_date=first_day,
            end_date=last_day,
            defaults={'status': 'open', 'created_by': user}
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
    def calculate_approved_debt_breakdown(cls, order: UnitFinishingOrder) -> Dict[str, Decimal]:
        """
        احتساب المديونية المعتمدة للعميل كمرجع موحد وحيد (Single Source of Truth):
        - إذا كان قد تم إنشاء قيد استحقاق مالي للطلب، فإن المديونية تُشتق حصرياً من سطور القيد الدفتري المرحل.
        - الإيراد الصافي = إجمالي المقايسة - الخصم المعتمد (أو صافي السعر المعتمد).
        - ضريبة الجدول 5% كود T2.
        - إجمالي المديونية = الإيراد الصافي + الضريبة.
        """
        if order.accrual_journal_entry:
            debit_lines = order.accrual_journal_entry.lines.filter(debit__gt=Decimal('0.00'))
            total_posted_debt = sum(l.debit for l in debit_lines)
            net_revenue = order.net_finishing_price or (total_posted_debt / (Decimal('1.00') + cls.TABLE_TAX_RATE)).quantize(Decimal('0.01'))
            tax_amount = total_posted_debt - net_revenue
            return {
                'net_revenue': net_revenue,
                'tax_amount': tax_amount,
                'total_debt': total_posted_debt,
            }

        if order.net_finishing_price and order.net_finishing_price > Decimal('0.00'):
            net_revenue = order.net_finishing_price
        elif order.promotional_discount and order.promotional_discount > Decimal('0.00'):
            net_revenue = max(Decimal('0.00'), order.gross_finishing_amount - order.promotional_discount)
        else:
            net_revenue = order.gross_finishing_amount

        table_tax_amount = (net_revenue * cls.TABLE_TAX_RATE).quantize(Decimal('0.01'))
        total_customer_debit = (net_revenue + table_tax_amount).quantize(Decimal('0.01'))

        return {
            'net_revenue': net_revenue,
            'tax_amount': table_tax_amount,
            'total_debt': total_customer_debit,
        }

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
        breakdown = cls.calculate_approved_debt_breakdown(order)
        net_finishing_revenue = breakdown['net_revenue']
        table_tax_amount = breakdown['tax_amount']
        total_customer_debit = breakdown['total_debt']

        if order.accrual_journal_entry:
            return order.accrual_journal_entry, table_tax_amount

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
            status='draft',
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

        # ترحيل القيد عبر مسار الترحيل المحاسبي المعتمد
        journal_entry.post(user=user or order.created_by)

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
            status='draft',
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

        # ترحيل القيد عبر مسار الترحيل المحاسبي المعتمد
        je.post(user=user or order.created_by)

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

        breakdown = cls.calculate_approved_debt_breakdown(order)
        total_finishing = breakdown['total_debt']

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
        صرف خامات من المخزن للوحدة مع فحص الكوتة الهندسية وتجميد الموقع وصمامات نقاط التوقف
        """
        if quantity_to_issue <= Decimal('0.00'):
            raise ValidationError(_("كمية الصرف يجب أن تكون أكبر من الصفر."))

        # قفل سجل البند لمنع التجاوز المتزامن لكوتة المقايسة المعتمدة
        order_item = UnitFinishingOrderItem.objects.select_for_update().get(pk=order_item.pk)

        if getattr(order_item.order, 'is_site_work_frozen', False):
            raise ValidationError(_("الأعمال الميدانية وصرف الخامات مجمدة لأمر التشطيب هذا."))

        # فحص صمامات نقاط التوقف (Hold Points) حسب فئة البند
        if order_item.category in ['WALL_FINISH', 'PAINTING']:
            if order_item.workspace:
                from real_estate.services.finishing_inspection_service import FinishingHoldPointEngine
                can_issue, err = FinishingHoldPointEngine.can_issue_painting_materials(order_item.order, order_item.workspace)
                if not can_issue:
                    raise ValidationError(err)

        if order_item.category in ['FLOORING', 'TILING', 'CERAMIC']:
            if order_item.workspace:
                from real_estate.services.finishing_inspection_service import FinishingHoldPointEngine
                can_issue, err = FinishingHoldPointEngine.can_issue_flooring_materials(order_item.order, order_item.workspace)
                if not can_issue:
                    raise ValidationError(err)

        current_issued = order_item.issued_quantity_from_store or Decimal('0.00')
        max_allowed = order_item.gross_quantity

        if current_issued + quantity_to_issue > max_allowed:
            raise ValidationError(
                _(f"لا يمكن صرف الكمية المطلوبة ({quantity_to_issue}). إجمالي المنصرف ({current_issued}) سيتجاوز كوتة البند المعتمدة ({max_allowed} {order_item.measuring_unit}).")
            )

        # 1. التحقق من وجود طبقات تكلفة مفتوحة ورصيد متاح فعلياً عبر نظام FIFO
        layers = list(InventoryCostLayer.objects.filter(
            product=product,
            warehouse=warehouse,
            status='OPEN',
            remaining_qty__gt=Decimal('0.00')
        ).order_by('receipt_date', 'id').select_for_update())

        if not layers:
            raise ValidationError(_("لا يوجد رصيد مخزني متاح أو طبقات تكلفة مفتوحة لهذا الصنف في المخزن المحدد."))

        total_available = sum(l.remaining_qty for l in layers)
        if total_available < quantity_to_issue:
            raise ValidationError(
                _(f"إجمالي الرصيد المتاح في طبقات التكلفة ({total_available}) غير كافٍ لصرف الكمية المطلوبة ({quantity_to_issue}).")
            )

        # استهلاك طبقات التكلفة بنظام FIFO
        remaining_needed = quantity_to_issue
        consumed_layers_info = []
        for layer in layers:
            if remaining_needed <= Decimal('0.00'):
                break
            consume_qty = min(layer.remaining_qty, remaining_needed)
            layer.remaining_qty = (layer.remaining_qty - consume_qty).quantize(Decimal('0.0001'))
            if layer.remaining_qty == Decimal('0.0000'):
                layer.status = 'DEPLETED'
            layer.save(update_fields=['remaining_qty', 'status'])
            consumed_layers_info.append((layer, consume_qty, layer.unit_cost))
            remaining_needed -= consume_qty

        total_consumed_cost = sum(qty * cost for _, qty, cost in consumed_layers_info)
        weighted_unit_cost = (total_consumed_cost / quantity_to_issue).quantize(Decimal('0.01')) if quantity_to_issue > 0 else Decimal('0.00')

        req_num = f"REQ-MAT-{order_item.order.order_number}-{order_item.id}-{uuid.uuid4().hex[:8]}"

        # 2. تسجيل حركة مخزنية فعلية صادر بالكمية الدقيقة
        stock_movement = StockMovement.objects.create(
            product=product,
            warehouse=warehouse,
            movement_type="out",
            quantity=quantity_to_issue,
            unit_cost=weighted_unit_cost,
            reference_number=req_num,
            document_type="other",
            document_number=order_item.order.order_number,
            notes=f"صرف خامات تشطيب للوحدة {order_item.order.unit.unit_code}",
            created_by=user or order_item.order.created_by
        )

        # 3. إنشاء سطور أستاذ المخزون وتتبع استهلاك الطبقات
        primary_consumption = None
        for layer, qty, cost in consumed_layers_info:
            sle_num = f"SLE-{uuid.uuid4().hex[:12]}"
            sle = StockLedgerEntry.objects.create(
                entry_number=sle_num,
                movement_service_ref=f"FIN-REQ-{req_num}",
                product=product,
                warehouse=warehouse,
                movement_type='ISSUE',
                quantity=-qty,
                unit_cost=cost,
                total_cost=round(-qty * cost, 2)
            )

            consumption = InventoryCostConsumption.objects.create(
                consumption_number=f"CONS-{uuid.uuid4().hex[:12]}",
                cost_layer=layer,
                stock_ledger_entry=sle,
                consumed_qty=qty,
                unit_cost=cost,
                total_cost=round(qty * cost, 2)
            )
            if primary_consumption is None:
                primary_consumption = consumption

        # تحديث بيانات الحركة المخزنية بعد ترحيل القيد التلقائي
        stock_movement.refresh_from_db()
        if not stock_movement.journal_entry_id:
            raise ValidationError(_("فشل الترحيل المحاسبي لحركة صرف الخامات؛ تم إلغاء العملية لحماية الأرصدة والقيود الدفترية."))

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
            stock_movement=stock_movement,
            cost_consumption=primary_consumption,
            created_by=user or order_item.order.created_by
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
        إثبات إذن ارتجاع خامات سليمة للمخزن وعكس كوتة المنصرف واستعادة رصيد طبقات التكلفة الأصلية
        مع إنشاء وترحيل قيد عكس التكلفة المحاسبي المتطابق مع حسابات وتكلفة الصرف
        """
        if quantity_to_return <= Decimal('0.00'):
            raise ValidationError(_("كمية الارتجاع يجب أن تكون أكبر من الصفر."))

        order_item = UnitFinishingOrderItem.objects.select_for_update().get(pk=order_item.pk)
        current_issued = order_item.issued_quantity_from_store or Decimal('0.00')

        if quantity_to_return > current_issued:
            raise ValidationError(
                _(f"الكمية المراد ارتجاعها ({quantity_to_return}) تتجاوز إجمالي المنصرف فعلياً للوحدة ({current_issued}).")
            )

        # 1. التحقق من أن هذا الصنف تم صرفه مسبقاً لهذا البند وتتبع أصل الصرف
        item_has_requisitions = FinishingMaterialRequisition.objects.filter(order_item=order_item).exists()
        previous_issues = FinishingMaterialRequisition.objects.filter(
            order_item=order_item,
            product=product,
            transaction_type='ISSUE'
        ).order_by('-id')

        if item_has_requisitions and not previous_issues.exists():
            raise ValidationError(_("لا يمكن إرجاع صنف لم يتم صرفه مسبقاً لهذا البند."))

        if previous_issues.exists():
            total_prod_issued = previous_issues.aggregate(t=models.Sum('quantity_issued'))['t'] or Decimal('0.00')
            total_prod_returned = FinishingMaterialRequisition.objects.filter(
                order_item=order_item,
                product=product,
                transaction_type='RETURN'
            ).aggregate(t=models.Sum('quantity_issued'))['t'] or Decimal('0.00')

            net_prod_issued = total_prod_issued - total_prod_returned
            if quantity_to_return > net_prod_issued:
                raise ValidationError(
                    _(f"الكمية المراد ارتجاعها ({quantity_to_return}) تتجاوز صافي المنصرف من هذا الصنف ({net_prod_issued}).")
                )

        # استعادة الكمية لطبقات التكلفة الأصلية التي تم الصرف منها بنظام العكس التنازلي LIFO
        issue_req_numbers = list(previous_issues.values_list('requisition_number', flat=True))
        req_refs = [f"FIN-REQ-{rn}" for rn in issue_req_numbers]
        legacy_ref = f"FINISHING-{order_item.order.order_number}"

        consumptions = list(InventoryCostConsumption.objects.filter(
            models.Q(stock_ledger_entry__movement_service_ref__in=req_refs) |
            models.Q(stock_ledger_entry__movement_service_ref=legacy_ref, stock_ledger_entry__product=product)
        ).select_related('cost_layer').order_by('-id'))

        remaining_to_return = quantity_to_return
        returned_allocations = []  # list of (consumption, layer, restore_qty, unit_cost)
        layers_by_id = {}

        if consumptions:
            for consumption in consumptions:
                if remaining_to_return <= Decimal('0.00'):
                    break
                # حساب الكمية المرتجعة سابقاً من هذا الاستهلاك الميداني تحديداً
                already_returned = StockLedgerEntry.objects.filter(
                    movement_service_ref__startswith=f"FIN-RET-{consumption.id}-",
                    movement_type='RECEIPT'
                ).aggregate(s=models.Sum('quantity'))['s'] or Decimal('0.0000')

                outstanding = consumption.consumed_qty - already_returned
                if outstanding > Decimal('0.0000'):
                    restore_qty = min(remaining_to_return, outstanding)
                    layer_id = consumption.cost_layer_id
                    if layer_id not in layers_by_id:
                        layers_by_id[layer_id] = InventoryCostLayer.objects.select_for_update().get(id=layer_id)
                    layer = layers_by_id[layer_id]
                    if layer.warehouse_id == warehouse.id:
                        layer.remaining_qty = (layer.remaining_qty + restore_qty).quantize(Decimal('0.0001'))
                        if layer.status == 'DEPLETED' and layer.remaining_qty > Decimal('0.0000'):
                            layer.status = 'OPEN'
                        layer.save(update_fields=['remaining_qty', 'status'])
                    remaining_to_return -= restore_qty
                    returned_allocations.append((consumption, layer, restore_qty, layer.unit_cost))

        if remaining_to_return > Decimal('0.00'):
            fallback_layer = InventoryCostLayer.objects.filter(
                product=product,
                warehouse=warehouse
            ).select_for_update().order_by('receipt_date', 'id').first()
            if fallback_layer:
                if fallback_layer.id in layers_by_id:
                    fallback_layer = layers_by_id[fallback_layer.id]
                else:
                    layers_by_id[fallback_layer.id] = fallback_layer
                fallback_layer.remaining_qty = (fallback_layer.remaining_qty + remaining_to_return).quantize(Decimal('0.0001'))
                if fallback_layer.status == 'DEPLETED':
                    fallback_layer.status = 'OPEN'
                fallback_layer.save(update_fields=['remaining_qty', 'status'])
                returned_allocations.append((None, fallback_layer, remaining_to_return, fallback_layer.unit_cost))
            else:
                unit_cost = getattr(product, 'cost_price', Decimal('100.00')) or Decimal('100.00')
                returned_allocations.append((None, None, remaining_to_return, unit_cost))

        total_return_cost = sum(qty * cost for _, _, qty, cost in returned_allocations)
        weighted_unit_cost = (total_return_cost / quantity_to_return).quantize(Decimal('0.0001')) if quantity_to_return > 0 else Decimal('0.00')

        req_num = f"RET-MAT-{order_item.order.order_number}-{order_item.id}-{uuid.uuid4().hex[:8]}"
        return_date = timezone.now().date()
        period = get_or_create_open_period(return_date, user)

        # 2. حركة مخزنية مرتجع وارد بتكلفة التخصيص الأصلية
        stock_movement = StockMovement.objects.create(
            product=product,
            warehouse=warehouse,
            movement_type="return_in",
            quantity=quantity_to_return,
            unit_cost=weighted_unit_cost,
            reference_number=req_num,
            document_type="other",
            document_number=order_item.order.order_number,
            notes=f"ارتجاع خامات تشطيب للوحدة {order_item.order.unit.unit_code}",
            created_by=user or order_item.order.created_by
        )

        # 3. سطور أستاذ المخزون موجب للوارد لكل طبقة مربوطة برقم الاستهلاك
        for consumption, layer, qty, cost in returned_allocations:
            sle_num = f"SLE-RET-{uuid.uuid4().hex[:12]}"
            ref = f"FIN-RET-{consumption.id}-{req_num}" if consumption else f"FIN-RET-{req_num}"
            sle = StockLedgerEntry.objects.create(
                entry_number=sle_num,
                movement_service_ref=ref,
                product=product,
                warehouse=warehouse,
                movement_type='RECEIPT',
                quantity=qty,
                unit_cost=cost,
                total_cost=round(qty * cost, 2)
            )
            # إذا كان الارتجاع لمخزن مختلف عن مخزن الطبقة الأصلية (أو لا توجد طبقة سابقة في هذا المخزن)
            if layer is None or layer.warehouse_id != warehouse.id:
                InventoryCostLayer.objects.create(
                    product=product,
                    warehouse=warehouse,
                    receipt_date=timezone.now(),
                    stock_ledger_entry=sle,
                    original_qty=qty,
                    remaining_qty=qty,
                    base_unit_cost=cost,
                    landed_cost_unit=Decimal("0.0000"),
                    unit_cost=cost,
                    status="OPEN"
                )

        # تحديث بيانات الحركة المخزنية بعد ترحيل القيد التلقائي
        stock_movement.refresh_from_db()
        if not stock_movement.journal_entry_id:
            raise ValidationError(_("فشل الترحيل المحاسبي لحركة ارتجاع الخامات؛ تم إلغاء العملية لحماية الأرصدة والقيود الدفترية."))

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
            issue_date=return_date,
            return_reason=return_reason,
            is_cost_reversed=True,
            stock_movement=stock_movement,
            created_by=user or order_item.order.created_by
        )

        order_item.issued_quantity_from_store = current_issued - quantity_to_return
        order_item.save(update_fields=['issued_quantity_from_store'])

        return ret
