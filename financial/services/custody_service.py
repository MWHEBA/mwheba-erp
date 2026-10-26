"""
Enterprise Custody Management Service (نظام إدارة وحوكمة عهد الموظفين الشامل)
-------------------------------------------------------------------------
Covers:
1. Cash Advances (صرف وتغذية العهد المؤقتة مع فحص كفاية الخزينة وحوكمة بدل السفر)
2. Petty Cash Settlements (اعتماد وترحيل التسويات المركبة متعددة البنود والضرائب والموردين ومحرك تسوية فواتير المشتريات)
3. Imprest Fund Replenishment (استعاضة العهد المستديمة بالشروط الستة)
4. Inter-Employee Custody Transfers (مناقلات العهد والأمانات المحكومة)
5. Physical Cash Counting & Auditing (محاضر جرد العهد والفئات النقدية)
6. Safe Reversals (عكس التسويات مع الحفاظ على مسار المراجعة المحاسبي)
"""

from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any
import logging
from datetime import date, timedelta
from collections import defaultdict

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from core.enums.document_types import DocumentType
from core.services.sequence_service import SequenceService
from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.currency import Currency
from financial.models.cost_center import CostCenter
from financial.models.journal_entry import JournalEntry, JournalEntryLine, AccountingPeriod
from financial.models.custody import (
    EmployeeCustodyAdvance,
    CustodyAdvanceStatus,
    SettlementLineType,
    PettyCashSettlement,
    SettlementStatus,
    PettyCashSettlementLine,
    SettlementLineStatus,
    CustodyTransfer,
    PettyCashCount,
)
from financial.models.custody_history import CustodyAssignmentHistory
from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
from financial.services.ledger_core_service import LedgerCoreService
from financial.services.exchange_rate_service import ExchangeRateService
from financial.services.budget_control_service import BudgetControlService
from financial.services.partner_balance_service import PartnerBalanceService
from financial.services.partner_subledger_service import PartnerSubledgerService
from hr.models.employee import Employee
from purchase.models.payment import PurchasePayment

logger = logging.getLogger(__name__)
User = get_user_model()


class CustodyManagementService:
    """
    محرك خدمات العهد والأمانات المالية والمحاسبية الموحد
    """

    @classmethod
    def _get_open_period(cls, target_date: date) -> AccountingPeriod:
        """التحقق من وجود فترة محاسبية مفتوحة والتاريخ يقع ضمنها حصراً"""
        period = AccountingPeriod.objects.filter(
            start_date__lte=target_date,
            end_date__gte=target_date,
            status="open"
        ).first()
        if not period:
            raise ValidationError(f"التاريخ المالي {target_date} يقع خارج أي فترة محاسبية مفتوحة.")
        return period

    @classmethod
    def _validate_self_approval(cls, employee: Employee, user: Any) -> None:
        """منع الصرف أو الاعتماد الذاتي إذا كان المستخدم هو الموظف المستفيد ذاته"""
        if not user or not user.is_authenticated:
            return
        user_emp = getattr(user, "employee_profile", None)
        if user_emp and user_emp.id == employee.id and not user.is_superuser:
            raise ValidationError("حظر الحوكمة: لا يجوز للموظف اعتماد أو صرف عهدة مالية لنفسه ذاتياً.")

    @classmethod
    def _get_role_account_safe(cls, role: AccountRoleNames, default_code: Optional[str] = None) -> Optional[ChartOfAccounts]:
        """الحصول الآمن على الحساب المحاسبي المرتبط بالدور مع تراجع لكود الحساب الافتراضي"""
        try:
            return AccountRoleRegistry.get_account(role)
        except Exception:
            if default_code:
                return ChartOfAccounts.objects.filter(code=default_code, is_active=True).first()
            return None

    @classmethod
    def _check_treasury_sufficiency(
        cls,
        treasury_account: ChartOfAccounts,
        advance_amount: Decimal,
        advance_currency: Optional[Currency] = None,
        exchange_rate: Optional[Decimal] = None,
        target_date: Optional[date] = None,
    ) -> None:
        """
        FIN-CORE-CUST-3.6 & 3.9: فحص كفاية رصيد الخزينة بالدالة القياسية تحت القفل الذري
        بناءً على الحالات الأربع للعملات (EGP/EGP, Foreign/Foreign, EGP/Foreign, Cross-Foreign)
        """
        func_curr = ExchangeRateService.get_functional_currency()
        func_code = getattr(func_curr, "code", "EGP") or "EGP"

        adv_code = getattr(advance_currency, "code", str(advance_currency or func_code)) if advance_currency else func_code
        treasury_curr_code = getattr(treasury_account, "currency_code", None)
        if not treasury_curr_code and hasattr(treasury_account, "currency") and treasury_account.currency:
            treasury_curr_code = getattr(treasury_account.currency, "code", func_code)
        if not treasury_curr_code:
            treasury_curr_code = func_code

        local_balance = treasury_account.get_balance(date_to=target_date, currency_type="local")
        foreign_balance = treasury_account.get_balance(date_to=target_date, currency_type="foreign")

        # الحالة 1 (EGP / EGP): خزينة محلية وسلفة محلية
        if treasury_curr_code == func_code and adv_code == func_code:
            if local_balance < advance_amount:
                raise ValidationError(
                    f"رصيد الخزينة ({treasury_account.name}) غير كافٍ لصرف العهدة. "
                    f"الرصيد المتاح: {local_balance} {func_code}، المبلغ المطلوب: {advance_amount} {func_code}."
                )
        # الحالة 2 (USD / USD): خزينة وسلفة بنفس العملة الأجنبية
        elif treasury_curr_code == adv_code and treasury_curr_code != func_code:
            if foreign_balance < advance_amount:
                raise ValidationError(
                    f"رصيد الخزينة الأجنبية ({treasury_account.name}) غير كافٍ. "
                    f"الرصيد المتاح: {foreign_balance} {adv_code}، المبلغ المطلوب: {advance_amount} {adv_code}."
                )
        # الحالة 3 (خزينة محلية EGP / سلفة أجنبية USD):
        elif treasury_curr_code == func_code and adv_code != func_code:
            rate = exchange_rate or Decimal("1.000000")
            if rate <= Decimal("0.000000") or rate == Decimal("1.000000"):
                try:
                    official = ExchangeRateService.get_rate(adv_code, func_code, date=target_date)
                    if official and official > Decimal("0.000000") and official != Decimal("1.000000"):
                        rate = official
                except Exception:
                    pass
            if not rate or rate == Decimal("1.000000"):
                raise ValidationError(
                    f"لا يمكن صرف عهدة بالعملة الأجنبية ({adv_code}) من خزينة محلية بسعر صرف 1.000000. "
                    f"يرجى تسجيل سعر الصرف المعتمد بتاريخ {target_date or timezone.localdate()}."
                )
            required_local = (advance_amount * rate).quantize(Decimal("0.01"))
            if local_balance < required_local:
                raise ValidationError(
                    f"رصيد الخزينة المحلية ({treasury_account.name}) غير كافٍ لتغطية المعادل الوظيفي للعهدة الأجنبية. "
                    f"الرصيد المتاح: {local_balance} {func_code}، المعادل المطلوب: {required_local} {func_code}."
                )
        # الحالة 4 (تقاطع عملتين أجنبيتين: خزينة EUR / سلفة USD):
        else:
            raise ValidationError(
                f"حظر حوكمة: لا يمكن صرف عهدة بالعملة ({adv_code}) مباشرة من خزينة بعملة ({treasury_curr_code}). "
                f"يجب إجراء تحويل عملة مسبق عبر خدمة التحويلات النقدية (CashTransferService)."
            )

    # -------------------------------------------------------------------------
    # 1. صرف وتغذية العهد النقدية (Disburse Advance)
    # -------------------------------------------------------------------------
    @classmethod
    def disburse_advance(
        cls,
        advance: EmployeeCustodyAdvance,
        disbursed_by_user: Any,
        notes: str = "",
        skip_treasury_sufficiency: bool = False,
    ) -> JournalEntry:
        """
        صرف العهدة النقدية وتوليد القيد المحاسبي وحفظ حركة الخزينة وتثبيت أصل التمويل
        """
        if advance.status not in [CustodyAdvanceStatus.PENDING_APPROVAL, CustodyAdvanceStatus.DRAFT]:
            raise ValidationError(
                f"حظر حوكمة: لا يمكن إعادة صرف عهدة تم صرفها مسبقاً (حالتها الحالية: {advance.get_status_display()})."
            )

        cls._validate_self_approval(advance.employee, disbursed_by_user)

        with transaction.atomic():
            adv = EmployeeCustodyAdvance.objects.select_for_update().get(id=advance.id)
            if adv.status not in [CustodyAdvanceStatus.PENDING_APPROVAL, CustodyAdvanceStatus.DRAFT]:
                raise ValidationError(
                    f"حظر حوكمة: لا يمكن إعادة صرف عهدة تم صرفها مسبقاً (حالتها الحالية: {adv.get_status_display()})."
                )
            if adv.journal_entry_id or (adv.transferred_in_amount and adv.transferred_in_amount > 0):
                raise ValidationError(
                    "حظر حوكمة: لا يمكن إعادة صرف عهدة تم تمويلها أو استلامها بمناقلة مسبقاً."
                )
            custody_acc = getattr(adv, "custody_account", None) or AccountRoleRegistry.get_account(AccountRoleNames.CUSTODY_TEMPORARY_CONTROL)
            treasury_acc = adv.source_treasury or AccountRoleRegistry.get_account(AccountRoleNames.DEFAULT_CASH_DRAWER)

            if not custody_acc:
                raise ValidationError("حساب مراقبة العهد النقدية غير موجود في دليل الحسابات.")
            if not treasury_acc:
                raise ValidationError("خزينة الصرف غير محددة ولا يوجد حساب خزينة رئيسية.")

            treasury_locked = ChartOfAccounts.objects.select_for_update().get(id=treasury_acc.id)

            rate = adv.exchange_rate or Decimal("1.000000")
            curr_code = adv.currency.code if adv.currency else "EGP"
            is_foreign = (curr_code != "EGP")
            if is_foreign and rate <= Decimal("1.000000"):
                from financial.services.exchange_rate_service import ExchangeRateService
                db_rate = ExchangeRateService.get_exchange_rate(adv.currency, date=adv.issue_date)
                if db_rate > Decimal("1.000000"):
                    rate = db_rate
                    adv.exchange_rate = rate
                    adv.save(update_fields=["exchange_rate"])
            func_amount = (adv.amount * rate).quantize(Decimal("0.01"))

            # التحقق الأمني من صلاحيات الصرف وسقف الخزينة (F05)
            if disbursed_by_user and getattr(disbursed_by_user, "is_authenticated", False):
                from financial.services.treasury_security_service import TreasurySecurityService
                allowed, sec_msg = TreasurySecurityService.can_user_disburse(
                    user=disbursed_by_user,
                    treasury_id=treasury_locked.id,
                    amount=func_amount,
                    target_date=adv.issue_date,
                )
                if not allowed:
                    raise ValidationError(f"حظر أمني: {sec_msg}")

            if not skip_treasury_sufficiency:
                cls._check_treasury_sufficiency(
                    treasury_account=treasury_locked,
                    advance_amount=adv.amount,
                    advance_currency=adv.currency,
                    exchange_rate=adv.exchange_rate,
                    target_date=adv.issue_date,
                )

            period = cls._get_open_period(adv.issue_date)

            # 3.9: المعالجة المحاسبية لبدل السفر المقطوع المركب وتثبيت أصل التمويل
            lines_data = []
            if adv.is_per_diem_split and adv.per_diem_amount > Decimal("0.00"):
                if adv.per_diem_amount >= adv.amount:
                    raise ValidationError("مبلغ بدل السفر المقطوع يجب أن يكون أقل من إجمالي مبلغ العهدة.")
                
                custody_principal = adv.amount - adv.per_diem_amount
                func_per_diem = (adv.per_diem_amount * rate).quantize(Decimal("0.01"))
                func_principal = func_amount - func_per_diem
                travel_expense_acc = AccountRoleRegistry.get_account(AccountRoleNames.COGS_EXPENSE)
                if not travel_expense_acc:
                    travel_expense_acc = ChartOfAccounts.objects.filter(code="51100", is_active=True).first()

                lines_data.append({
                    "account": travel_expense_acc,
                    "debit": func_per_diem,
                    "credit": Decimal("0.00"),
                    "foreign_debit": adv.per_diem_amount if is_foreign else Decimal("0.00"),
                    "cost_center": adv.cost_center,
                    "currency": curr_code,
                    "exchange_rate": rate,
                    "description": f"بدل سفر وانتقال مقطوع - {adv.employee.name} - سند {adv.advance_number}",
                })
                lines_data.append({
                    "account": custody_acc,
                    "debit": func_principal,
                    "credit": Decimal("0.00"),
                    "foreign_debit": custody_principal if is_foreign else Decimal("0.00"),
                    "currency": curr_code,
                    "exchange_rate": rate,
                    "description": f"عهدة نقدية خاضعة للتسوية - {adv.employee.name} - سند {adv.advance_number}",
                })
            else:
                custody_principal = adv.amount
                lines_data.append({
                    "account": custody_acc,
                    "debit": func_amount,
                    "credit": Decimal("0.00"),
                    "foreign_debit": adv.amount if is_foreign else Decimal("0.00"),
                    "currency": curr_code,
                    "exchange_rate": rate,
                    "description": f"عهدة نقدية للموظف {adv.employee.name} - سند {adv.advance_number}",
                })

            # دائن: الخزينة المصدرة بكامل المبلغ بالمعادل المحلي
            lines_data.append({
                "account": treasury_locked,
                "debit": Decimal("0.00"),
                "credit": func_amount,
                "foreign_credit": adv.amount if is_foreign else Decimal("0.00"),
                "currency": curr_code,
                "exchange_rate": rate,
                "description": f"صرف عهدة نقدية للموظف {adv.employee.name} - سند {adv.advance_number}",
            })

            draft_entry = LedgerCoreService.create_draft_entry(
                date=adv.issue_date,
                description=f"صرف عهدة نقدية - {adv.employee.name} - {adv.advance_number} - {adv.purpose or ''}",
                reference=f"CADV-{adv.advance_number}",
                entry_type="cash_payment",
                created_by=disbursed_by_user if disbursed_by_user and disbursed_by_user.is_authenticated else None,
                lines_data=lines_data,
                source_module="financial",
                source_model="EmployeeCustodyAdvance",
                source_id=adv.id,
            )

            journal_entry = LedgerCoreService.post_entry(
                entry_id=draft_entry.id,
                user=disbursed_by_user if disbursed_by_user and disbursed_by_user.is_authenticated else None,
                source_type="EmployeeCustodyAdvance",
                source_id=str(adv.id),
            )
            journal_entry.is_locked = True
            journal_entry.save(update_fields=["is_locked"])

            adv.status = CustodyAdvanceStatus.ACTIVE
            adv.settlement_principal_amount = custody_principal
            adv.current_balance = custody_principal
            adv.journal_entry = journal_entry
            adv.save(update_fields=["status", "settlement_principal_amount", "current_balance", "journal_entry"])

            advance.status = adv.status
            advance.settlement_principal_amount = adv.settlement_principal_amount
            advance.current_balance = adv.current_balance
            advance.journal_entry = adv.journal_entry

            # توثيق في سجل الإسناد التاريخي
            CustodyAssignmentHistory.objects.filter(account=custody_acc, is_active=True).update(
                is_active=False,
                end_date=adv.issue_date,
            )
            CustodyAssignmentHistory.objects.create(
                account=custody_acc,
                employee=adv.employee,
                assigned_by=disbursed_by_user if disbursed_by_user and disbursed_by_user.is_authenticated else None,
                start_date=adv.issue_date,
                is_active=True,
                opening_balance_on_handover=custody_principal,
                notes=f"صرف عهدة نقدية برقم {adv.advance_number} بمبلغ خاضع للتسوية {custody_principal} {curr_code}",
            )

            logger.info(f"تم صرف العهدة {adv.advance_number} بنجاح وقيد رقم {journal_entry.number}")
            return journal_entry

    # -------------------------------------------------------------------------
    # 2. تعزيز وتغذية العهدة القائمة (Top-up Advance)
    # -------------------------------------------------------------------------
    @classmethod
    def top_up_advance(
        cls,
        advance: EmployeeCustodyAdvance,
        amount: Decimal,
        treasury_account: ChartOfAccounts,
        user: Any,
        notes: str = "",
        skip_treasury_sufficiency: bool = False,
        topup_id: Optional[str] = None,
        **kwargs,
    ) -> JournalEntry:
        """
        FIN-CORE-CUST-3.10: دورة التغذية والتعزيز الإضافي للعهدة القائمة وقيد الصرف التعزيزي
        """
        if advance.status not in [CustodyAdvanceStatus.ACTIVE, CustodyAdvanceStatus.PARTIALLY_SETTLED]:
            raise ValidationError(f"لا يمكن تعزيز عهدة بحالة {advance.get_status_display()}. التعزيز متاح فقط للعهد النشطة.")
        if amount <= Decimal("0.00"):
            raise ValidationError("مبلغ التعزيز يجب أن يكون أكبر من الصفر.")

        cls._validate_self_approval(advance.employee, user)

        with transaction.atomic():
            adv = EmployeeCustodyAdvance.objects.select_for_update().get(id=advance.id)
            treasury_locked = ChartOfAccounts.objects.select_for_update().get(id=treasury_account.id)

            curr_code = adv.currency.code if adv.currency else "EGP"
            rate = adv.exchange_rate or Decimal("1.000000")
            func_amount = (amount * rate).quantize(Decimal("0.01"))
            is_foreign = (curr_code != "EGP")

            # التحقق الأمني من صلاحيات الصرف وسقف الخزينة (F05)
            if user and getattr(user, "is_authenticated", False):
                from financial.services.treasury_security_service import TreasurySecurityService
                allowed, sec_msg = TreasurySecurityService.can_user_disburse(
                    user=user,
                    treasury_id=treasury_locked.id,
                    amount=func_amount,
                    target_date=timezone.localdate(),
                )
                if not allowed:
                    raise ValidationError(f"حظر أمني: {sec_msg}")

            if not skip_treasury_sufficiency:
                cls._check_treasury_sufficiency(
                    treasury_account=treasury_locked,
                    advance_amount=amount,
                    advance_currency=adv.currency,
                    exchange_rate=adv.exchange_rate,
                    target_date=timezone.localdate(),
                )

            custody_acc = getattr(adv, "custody_account", None) or AccountRoleRegistry.get_account(AccountRoleNames.CUSTODY_TEMPORARY_CONTROL)
            if not custody_acc:
                raise ValidationError("حساب مراقبة العهد النقدية غير موجود في دليل الحسابات.")

            lines_data = [
                {
                    "account": custody_acc,
                    "debit": func_amount,
                    "credit": Decimal("0.00"),
                    "foreign_debit": amount if is_foreign else Decimal("0.00"),
                    "currency": curr_code,
                    "exchange_rate": rate,
                    "description": f"تعزيز عهدة نقدية للموظف {adv.employee.name} - سند {adv.advance_number}",
                },
                {
                    "account": treasury_locked,
                    "debit": Decimal("0.00"),
                    "credit": func_amount,
                    "foreign_credit": amount if is_foreign else Decimal("0.00"),
                    "currency": curr_code,
                    "exchange_rate": rate,
                    "description": f"صرف تعزيز عهدة نقدية للموظف {adv.employee.name} - سند {adv.advance_number}",
                }
            ]

            import uuid
            topup_uid = (topup_id or kwargs.get("topup_id") or "").strip()
            if topup_uid:
                from financial.models import FinancialPostingReference
                source_id_key = f"{adv.id}-{topup_uid}"
                if FinancialPostingReference.objects.filter(
                    source_type="EmployeeCustodyAdvanceTopUp",
                    source_id=source_id_key,
                ).exists():
                    raise ValidationError(f"حظر حوكمة: طلب التعزيز رقم '{topup_uid}' تم صرفه مسبقاً لهذه العهدة.")
            else:
                topup_uid = uuid.uuid4().hex[:8]

            draft_entry = LedgerCoreService.create_draft_entry(
                date=timezone.localdate(),
                description=f"تعزيز عهدة نقدية - {adv.employee.name} - {adv.advance_number} - {notes or ''}",
                reference=f"CTOP-{adv.advance_number}-{timezone.now().strftime('%y%m%d%H%M')}",
                entry_type="cash_payment",
                created_by=user if user and user.is_authenticated else None,
                lines_data=lines_data,
                source_module="financial",
                source_model="EmployeeCustodyAdvance",
                source_id=adv.id,
            )

            journal_entry = LedgerCoreService.post_entry(
                entry_id=draft_entry.id,
                user=user if user and user.is_authenticated else None,
                source_type="EmployeeCustodyAdvanceTopUp",
                source_id=f"{adv.id}-{topup_uid}",
            )
            journal_entry.is_locked = True
            journal_entry.save(update_fields=["is_locked"])

            adv.top_up_amount = (adv.top_up_amount or Decimal("0.00")) + amount
            adv.update_balance()
            adv.save(update_fields=["top_up_amount", "current_balance", "status"])

            logger.info(f"تم تعزيز العهدة {adv.advance_number} بمبلغ {amount} بنجاح")
            return journal_entry

    # -------------------------------------------------------------------------
    # 3. محرك حسابات التسوية الموحد (Calculate Settlement Totals)
    # -------------------------------------------------------------------------
    @classmethod
    def calculate_settlement_totals(
        cls,
        settlement: PettyCashSettlement,
        lines: Optional[List[PettyCashSettlementLine]] = None
    ) -> Dict[str, Any]:
        """
        FIN-CORE-CUST-3.3: محرك الحسابات الموحد وإجماليات النقدية بوحدة عملة موحدة
        يعالج الشيكات والمرتجعات والخصومات والضرائب بدقة
        """
        if lines is None:
            lines = list(settlement.lines.all())

        # تحديد رمز عملة نقدية العهدة (float_currency_code)
        float_currency_code = "EGP"
        if settlement.currency:
            float_currency_code = settlement.currency.code
        elif settlement.custody_advance and settlement.custody_advance.currency:
            float_currency_code = settlement.custody_advance.currency.code
        elif settlement.custody_account and settlement.custody_account.currency:
            float_currency_code = settlement.custody_account.currency.code
        elif settlement.custody_account:
            float_currency_code = getattr(settlement.custody_account, "currency_code", "EGP") or "EGP"

        gross_net_expenses = Decimal("0.00")
        total_gross_expenses = Decimal("0.00")
        refunds_collected = Decimal("0.00")
        total_wht = Decimal("0.00")
        total_vat = Decimal("0.00")
        total_discounts = Decimal("0.00")
        processed_lines = []

        for s_line in lines:
            if s_line.status in [SettlementLineStatus.REJECTED, SettlementLineStatus.PENDING]:
                continue

            # 1. تسليم شيك مصدر مسبقاً (Handover Milestone) لا يسحب نقدية من العهدة
            if s_line.line_type == SettlementLineType.CHECK_DELIVERY:
                continue

            # 2. مرتجع نقدي مقبوض من المورد (يزيد نقدية العهدة بعد تحويله لعملة العهدة)
            if s_line.line_type == SettlementLineType.PURCHASE_REFUND:
                ref_amt = s_line.approved_amount if s_line.approved_amount is not None else s_line.amount
                if ref_amt > Decimal("0.00"):
                    line_curr_code = s_line.currency.code if s_line.currency else float_currency_code
                    line_rate = s_line.exchange_rate or Decimal("1.000000")
                    if line_curr_code != float_currency_code:
                        from financial.services.exchange_rate_service import ExchangeRateService
                        func_curr = ExchangeRateService.get_functional_currency()
                        func_code = getattr(func_curr, "code", "EGP") or "EGP"
                        if line_curr_code != func_code and float_currency_code == func_code:
                            ref_in_custody = (ref_amt * line_rate).quantize(Decimal("0.01"))
                        elif line_curr_code == func_code and float_currency_code != func_code:
                            ref_in_custody = (ref_amt / line_rate).quantize(Decimal("0.01")) if line_rate > 0 else ref_amt
                        else:
                            ref_in_custody = ref_amt
                    else:
                        ref_in_custody = ref_amt

                    refunds_collected += ref_in_custody
                    processed_lines.append({
                        "line": s_line,
                        "approved_amount": ref_amt,
                        "ref_in_custody": ref_in_custody,
                        "net_expense": Decimal("0.00"),
                        "effective_discount": Decimal("0.00"),
                        "effective_wht": Decimal("0.00"),
                        "effective_vat": Decimal("0.00"),
                        "is_refund": True,
                    })
                continue

            # 3. السطور النقدية المعتمدة (نفقات، سداد فواتير مشتريات، سداد أوراق دفع نقداً)
            approved = s_line.approved_amount if s_line.approved_amount is not None else s_line.amount
            if approved <= Decimal("0.00"):
                continue

            ratio = (approved / s_line.amount) if s_line.amount > Decimal("0.00") else Decimal("1.00")
            eff_discount = (s_line.discount_amount * ratio).quantize(Decimal("0.01"))
            eff_wht = (s_line.wht_amount * ratio).quantize(Decimal("0.01"))
            eff_vat = (s_line.tax_amount * ratio).quantize(Decimal("0.01"))

            line_net_expense = approved - eff_discount - eff_wht

            # تحويل كافة مكونات السطر إلى عملة نقدية العهدة بدقة وتناسق
            line_curr_code = s_line.currency.code if s_line.currency else float_currency_code
            line_rate = s_line.exchange_rate or Decimal("1.000000")
            if line_curr_code != float_currency_code:
                from financial.services.exchange_rate_service import ExchangeRateService
                func_curr = ExchangeRateService.get_functional_currency()
                func_code = getattr(func_curr, "code", "EGP") or "EGP"
                if line_curr_code != func_code and float_currency_code == func_code:
                    net_in_custody = (line_net_expense * line_rate).quantize(Decimal("0.01"))
                    discount_in_custody = (eff_discount * line_rate).quantize(Decimal("0.01"))
                    wht_in_custody = (eff_wht * line_rate).quantize(Decimal("0.01"))
                    vat_in_custody = (eff_vat * line_rate).quantize(Decimal("0.01"))
                    approved_in_custody = (approved * line_rate).quantize(Decimal("0.01"))
                elif line_curr_code == func_code and float_currency_code != func_code:
                    net_in_custody = (line_net_expense / line_rate).quantize(Decimal("0.01")) if line_rate > 0 else line_net_expense
                    discount_in_custody = (eff_discount / line_rate).quantize(Decimal("0.01")) if line_rate > 0 else eff_discount
                    wht_in_custody = (eff_wht / line_rate).quantize(Decimal("0.01")) if line_rate > 0 else eff_wht
                    vat_in_custody = (eff_vat / line_rate).quantize(Decimal("0.01")) if line_rate > 0 else eff_vat
                    approved_in_custody = (approved / line_rate).quantize(Decimal("0.01")) if line_rate > 0 else approved
                else:
                    net_in_custody = line_net_expense
                    discount_in_custody = eff_discount
                    wht_in_custody = eff_wht
                    vat_in_custody = eff_vat
                    approved_in_custody = approved
            else:
                net_in_custody = line_net_expense
                discount_in_custody = eff_discount
                wht_in_custody = eff_wht
                vat_in_custody = eff_vat
                approved_in_custody = approved

            total_gross_expenses += approved_in_custody
            gross_net_expenses += net_in_custody
            total_discounts += discount_in_custody
            total_wht += wht_in_custody
            total_vat += vat_in_custody

            processed_lines.append({
                "line": s_line,
                "approved_amount": approved,
                "net_expense": line_net_expense,
                "net_in_custody": net_in_custody,
                "effective_discount": eff_discount,
                "effective_wht": eff_wht,
                "effective_vat": eff_vat,
                "approved_in_custody": approved_in_custody,
                "discount_in_custody": discount_in_custody,
                "wht_in_custody": wht_in_custody,
                "vat_in_custody": vat_in_custody,
                "line_rate": line_rate,
                "is_refund": False,
            })

        # قراءة رصيد العهدة الفعلي بوحدة عملة موحدة
        current_balance = Decimal("0.00")
        if settlement.custody_advance:
            current_balance = settlement.custody_advance.current_balance or Decimal("0.00")
        elif settlement.custody_account:
            acc = settlement.custody_account
            curr_type = "foreign" if (acc.currency and not getattr(acc.currency, "is_functional", True)) else "local"
            current_balance = acc.get_balance(date_to=settlement.settlement_date, currency_type=curr_type) or Decimal("0.00")

        total_cash_in_hand = current_balance + refunds_collected
        submitted_returned = settlement.cash_returned_to_treasury or Decimal("0.00")
        cash_returned = min(submitted_returned, total_cash_in_hand) if submitted_returned > 0 else Decimal("0.00")
        available_cash_for_expenses = max(Decimal("0.00"), total_cash_in_hand - cash_returned)

        expenses_absorbed = min(gross_net_expenses, available_cash_for_expenses)
        overrun_payable = max(Decimal("0.00"), gross_net_expenses - expenses_absorbed)
        eligible_replenishment_amount = max(Decimal("0.00"), expenses_absorbed - refunds_collected)
        shortage_amount = settlement.shortage_amount or Decimal("0.00")

        return {
            "float_currency_code": float_currency_code,
            "current_balance": current_balance,
            "total_gross_expenses": total_gross_expenses,
            "gross_net_expenses": gross_net_expenses,
            "refunds_collected": refunds_collected,
            "total_cash_in_hand": total_cash_in_hand,
            "cash_returned": cash_returned,
            "available_cash_for_expenses": available_cash_for_expenses,
            "expenses_absorbed": expenses_absorbed,
            "overrun_payable": overrun_payable,
            "eligible_replenishment_amount": eligible_replenishment_amount,
            "shortage_amount": shortage_amount,
            "total_wht": total_wht,
            "total_vat": total_vat,
            "total_discounts": total_discounts,
            "processed_lines": processed_lines,
        }

    # -------------------------------------------------------------------------
    # 4. بناء بنود القيد المحاسبي المقترح (Build Settlement Journal Lines)
    # -------------------------------------------------------------------------
    @classmethod
    def build_settlement_journal_lines(
        cls,
        settlement: PettyCashSettlement,
        totals: Dict[str, Any],
        custody_acc: ChartOfAccounts,
        curr_code: str,
    ) -> List[Dict[str, Any]]:
        """
        FIN-CORE-CUST-3.3 & 3.5: بناء بنود القيد المحاسبي المركب المتزن بالكامل
        مع تطبيق حوكمة الضرائب (ETA Tax Guard)
        """
        from financial.services.exchange_rate_service import ExchangeRateService
        lines_data = []
        vat_acc = cls._get_role_account_safe(AccountRoleNames.VAT_INPUT, "11510")
        wht_acc = cls._get_role_account_safe(AccountRoleNames.WITHHOLDING_TAX_PAYABLE, "21330")
        discount_acc = cls._get_role_account_safe(AccountRoleNames.PURCHASE_DISCOUNTS, "51930")
        notes_payable_acc = cls._get_role_account_safe(AccountRoleNames.NOTES_PAYABLE_CONTROL, "21120")
        supplier_payable_acc = cls._get_role_account_safe(AccountRoleNames.SUPPLIER_PAYABLE_CONTROL, "21110")
        shortage_hr_acc = cls._get_role_account_safe(AccountRoleNames.EMPLOYEE_ADVANCE, "11230")
        overrun_payable_acc = cls._get_role_account_safe(AccountRoleNames.CUSTODY_OVERRUN_PAYABLES, "21230")
        main_treasury_acc = cls._get_role_account_safe(AccountRoleNames.DEFAULT_CASH_DRAWER, "11110")

        # R1 & R3: تحديد سعر الصرف للعهدة للتحويل الدفتري الموحد بالعملة المحلية
        custody_rate = Decimal("1.000000")
        if settlement.custody_advance and settlement.custody_advance.exchange_rate:
            custody_rate = settlement.custody_advance.exchange_rate
        else:
            line_with_rate = settlement.lines.exclude(status=SettlementLineStatus.REJECTED).filter(exchange_rate__gt=1).first()
            if line_with_rate and line_with_rate.exchange_rate:
                custody_rate = line_with_rate.exchange_rate
            elif curr_code != "EGP":
                from financial.services.exchange_rate_service import ExchangeRateService
                custody_curr = settlement.currency or (settlement.custody_account.currency if settlement.custody_account else None)
                custody_rate = ExchangeRateService.get_exchange_rate(custody_curr or curr_code, date=settlement.settlement_date)

            if (not custody_rate or custody_rate <= Decimal("1.000000")) and curr_code != "EGP" and settlement.custody_account:
                last_line = JournalEntryLine.objects.filter(
                    account=settlement.custody_account,
                    exchange_rate__gt=1
                ).order_by("-journal_entry__date", "-id").first()
                if last_line and last_line.exchange_rate:
                    custody_rate = last_line.exchange_rate

        if not custody_rate or custody_rate <= Decimal("0.000000"):
            custody_rate = Decimal("1.000000")

        is_custody_foreign = (curr_code != "EGP")

        for p_item in totals["processed_lines"]:
            s_line = p_item["line"]
            if p_item.get("is_refund", False):
                continue

            approved = p_item["approved_amount"]
            eff_vat = p_item["effective_vat"]
            eff_wht = p_item["effective_wht"]
            eff_discount = p_item["effective_discount"]
            approved_in_custody = p_item.get("approved_in_custody", approved)
            discount_in_custody = p_item.get("discount_in_custody", eff_discount)
            wht_in_custody = p_item.get("wht_in_custody", eff_wht)
            vat_in_custody = p_item.get("vat_in_custody", eff_vat)
            line_curr_code = s_line.currency.code if s_line.currency else curr_code

            # تحديد حساب السطر (F06: سداد المورد أو الفاتورة يوجه حصراً لحساب ذمة المورد وليس للمصروف)
            if s_line.line_type in [SettlementLineType.SUPPLIER_INVOICE, SettlementLineType.SUPPLIER_ADVANCE]:
                sup = s_line.supplier or (s_line.purchase_invoice.supplier if s_line.purchase_invoice else None)
                sup_acc = getattr(sup, "financial_account", None) or getattr(sup, "account", None)
                if sup_acc and sup_acc.can_post_entries():
                    line_acc = sup_acc
                elif supplier_payable_acc and supplier_payable_acc.can_post_entries():
                    line_acc = supplier_payable_acc
                elif supplier_payable_acc and not supplier_payable_acc.can_post_entries():
                    child = supplier_payable_acc.children.filter(is_active=True).first()
                    line_acc = child or sup_acc or supplier_payable_acc
                elif sup_acc:
                    line_acc = sup_acc
                else:
                    line_acc = supplier_payable_acc or AccountRoleRegistry.get_account(AccountRoleNames.SUPPLIER_PAYABLE_CONTROL)
            elif s_line.line_type == SettlementLineType.NOTES_PAYABLE:
                line_acc = notes_payable_acc or AccountRoleRegistry.get_account(AccountRoleNames.NOTES_PAYABLE_CONTROL)
            else:
                line_acc = s_line.expense_account or AccountRoleRegistry.get_account(AccountRoleNames.COGS_EXPENSE)

            if not line_acc:
                raise ValidationError(f"لم يتم تحديد الحساب المحاسبي للسطر رقم {s_line.line_number}.")

            # حالة خاصة: سداد فاتورة مشتريات (SUPPLIER_INVOICE مع purchase_invoice)
            if s_line.purchase_invoice:
                inv = s_line.purchase_invoice
                inv_currency_code = getattr(inv.currency, "code", str(inv.currency or "EGP"))
                inv_rate = getattr(inv, "exchange_rate", Decimal("1.000000")) or Decimal("1.000000")
                pmt_currency_code = curr_code
                pmt_rate = Decimal("1.000000")
                if settlement.custody_advance:
                    pmt_rate = settlement.custody_advance.exchange_rate or Decimal("1.000000")
                elif settlement.custody_account:
                    pmt_rate = getattr(settlement.custody_account, "exchange_rate", Decimal("1.000000")) or Decimal("1.000000")

                line_rate = getattr(s_line, "exchange_rate", None)
                if pmt_currency_code == inv_currency_code:
                    settlement_rate_param = pmt_rate
                elif pmt_currency_code == "EGP" and inv_currency_code != "EGP":
                    settlement_rate_param = line_rate or inv_rate
                else:
                    settlement_rate_param = pmt_rate

                fx_res = ExchangeRateService.calculate_payment_settlement(
                    invoice_amount=approved,
                    invoice_currency_code=inv_currency_code,
                    invoice_rate=inv_rate,
                    payment_currency_code=pmt_currency_code,
                    settlement_rate=settlement_rate_param,
                )
                inv_book_func = fx_res.get("invoice_book_functional") or fx_res.get("inv_book_functional")
                realized_fx = fx_res["realized_fx_difference"]

                # مدين: حساب المورد بالمعادل الوظيفي الدفتري للفاتورة المقفولة
                lines_data.append({
                    "account": line_acc,
                    "debit": inv_book_func,
                    "credit": Decimal("0.00"),
                    "foreign_debit": approved if inv_currency_code != curr_code else Decimal("0.00"),
                    "cost_center": s_line.cost_center,
                    "currency": inv_currency_code,
                    "exchange_rate": inv_rate,
                    "description": f"سداد فاتورة مشتريات {inv.number} - {s_line.description}",
                })

                # فروق العملة المحققة
                if realized_fx > Decimal("0.00"):
                    fx_loss_acc = AccountRoleRegistry.get_account(AccountRoleNames.FX_REALIZED_LOSS) or ChartOfAccounts.objects.filter(code="54300", is_active=True).first()
                    if not fx_loss_acc:
                        raise ValidationError("حساب خسائر فروق أسعار الصرف (54300) غير معرف في دليل الحسابات.")
                    lines_data.append({
                        "account": fx_loss_acc,
                        "debit": realized_fx,
                        "credit": Decimal("0.00"),
                        "cost_center": s_line.cost_center,
                        "currency": "EGP",
                        "exchange_rate": Decimal("1.000000"),
                        "description": f"خسائر فروق أسعار صرف لسداد فاتورة {inv.number}",
                    })
                elif realized_fx < Decimal("0.00"):
                    fx_gain_acc = AccountRoleRegistry.get_account(AccountRoleNames.FX_REALIZED_GAIN) or ChartOfAccounts.objects.filter(code="43100", is_active=True).first()
                    if not fx_gain_acc:
                        raise ValidationError("حساب أرباح فروق أسعار الصرف (43100) غير معرف في دليل الحسابات.")
                    lines_data.append({
                        "account": fx_gain_acc,
                        "debit": Decimal("0.00"),
                        "credit": abs(realized_fx),
                        "cost_center": s_line.cost_center,
                        "currency": "EGP",
                        "exchange_rate": Decimal("1.000000"),
                        "description": f"أرباح فروق أسعار صرف لسداد فاتورة {inv.number}",
                    })
            else:
                # 3.3: ETA Tax Guard: هل الفاتورة مستوفاة ضريبياً لخصم VAT في 11510؟
                tax_id = getattr(s_line, "supplier_tax_id", None) or (s_line.supplier.tax_number if s_line.supplier else "")
                is_tax_compliant = (
                    s_line.line_type != SettlementLineType.UNVOUCHERED_PETTY
                    and not getattr(s_line, "is_unvouchered", False)
                    and not getattr(s_line, "is_lost_receipt_affidavit", False)
                    and tax_id
                    and len(str(tax_id).strip()) == 9
                )

                net_in_custody = p_item.get("net_in_custody", approved)
                approved_in_custody = p_item.get("approved_in_custody", approved)
                discount_in_custody = p_item.get("discount_in_custody", eff_discount)
                wht_in_custody = p_item.get("wht_in_custody", eff_wht)
                vat_in_custody = p_item.get("vat_in_custody", eff_vat)
                line_curr_code = s_line.currency.code if s_line.currency else curr_code

                if is_custody_foreign:
                    func_line_amount = (approved_in_custody * custody_rate).quantize(Decimal("0.01"))
                    func_vat = (vat_in_custody * custody_rate).quantize(Decimal("0.01"))
                    func_wht = (wht_in_custody * custody_rate).quantize(Decimal("0.01"))
                    func_discount = (discount_in_custody * custody_rate).quantize(Decimal("0.01"))
                else:
                    func_line_amount = approved_in_custody
                    func_vat = vat_in_custody
                    func_wht = wht_in_custody
                    func_discount = discount_in_custody

                if is_tax_compliant and eff_vat > Decimal("0.00"):
                    if not vat_acc:
                        raise ValidationError("حساب ضريبة القيمة المضافة على المدخلات (11510) غير معرف في دليل الحسابات.")
                    # مدين: حساب المصروف الصافي من الضريبة
                    func_net_cost = func_line_amount - func_vat
                    net_cost = approved - eff_vat
                    lines_data.append({
                        "account": line_acc,
                        "debit": func_net_cost,
                        "credit": Decimal("0.00"),
                        "foreign_debit": net_cost if (line_curr_code != "EGP" or is_custody_foreign) else Decimal("0.00"),
                        "cost_center": s_line.cost_center,
                        "currency": curr_code,
                        "exchange_rate": custody_rate,
                        "description": f"{s_line.get_line_type_display()} - {s_line.description}",
                    })
                    # مدين: ضريبة القيمة المضافة (11510)
                    lines_data.append({
                        "account": vat_acc,
                        "debit": func_vat,
                        "credit": Decimal("0.00"),
                        "foreign_debit": eff_vat if (line_curr_code != "EGP" or is_custody_foreign) else Decimal("0.00"),
                        "cost_center": s_line.cost_center,
                        "currency": curr_code,
                        "exchange_rate": custody_rate,
                        "description": f"ضريبة مدخلات رسمية - تسوية {settlement.settlement_number} - مورد ضريبي {tax_id}",
                    })
                else:
                    # دمج الضريبة بالكامل ضمن تكلفة المصروف (Gross Expense) لعدم استيفاء الشروط الضريبية
                    lines_data.append({
                        "account": line_acc,
                        "debit": func_line_amount,
                        "credit": Decimal("0.00"),
                        "foreign_debit": approved if (line_curr_code != "EGP" or is_custody_foreign) else Decimal("0.00"),
                        "cost_center": s_line.cost_center,
                        "currency": curr_code,
                        "exchange_rate": custody_rate,
                        "description": f"{s_line.get_line_type_display()} - {s_line.description}",
                    })

            # دائن: ضريبة الخصم والتحصيل WHT إن وجدت
            if eff_wht > Decimal("0.00") or wht_in_custody > Decimal("0.00"):
                if not wht_acc:
                    raise ValidationError("حساب ضريبة الخصم من المنبع (21330) غير معرف في دليل الحسابات.")
                lines_data.append({
                    "account": wht_acc,
                    "debit": Decimal("0.00"),
                    "credit": func_wht,
                    "foreign_credit": eff_wht if (line_curr_code != "EGP" or is_custody_foreign) else Decimal("0.00"),
                    "cost_center": s_line.cost_center,
                    "currency": curr_code,
                    "exchange_rate": custody_rate,
                    "description": f"ضريبة خصم منبع - تسوية {settlement.settlement_number}",
                })

            # دائن: الخصم المكتسب إن وجد
            if eff_discount > Decimal("0.00") or discount_in_custody > Decimal("0.00"):
                if not discount_acc:
                    raise ValidationError("حساب الخصم المكتسب (51930) غير معرف في دليل الحسابات.")
                lines_data.append({
                    "account": discount_acc,
                    "debit": Decimal("0.00"),
                    "credit": func_discount,
                    "foreign_credit": eff_discount if (line_curr_code != "EGP" or is_custody_foreign) else Decimal("0.00"),
                    "cost_center": s_line.cost_center,
                    "currency": curr_code,
                    "exchange_rate": custody_rate,
                    "description": f"خصم مكتسب - تسوية {settlement.settlement_number}",
                })

        # مدين: الخزينة الرئيسية بالنقدية المردودة
        if totals["cash_returned"] > Decimal("0.00"):
            if not main_treasury_acc:
                main_treasury_acc = ChartOfAccounts.objects.filter(code="11110", is_active=True).first()
            func_returned = (totals["cash_returned"] * custody_rate).quantize(Decimal("0.01")) if is_custody_foreign else totals["cash_returned"]
            lines_data.append({
                "account": main_treasury_acc,
                "debit": func_returned,
                "credit": Decimal("0.00"),
                "foreign_debit": totals["cash_returned"] if is_custody_foreign else Decimal("0.00"),
                "currency": curr_code,
                "exchange_rate": custody_rate,
                "description": f"توريد متبقي عهدة نقدية للخزينة - سند {settlement.settlement_number}",
            })

        # مدين: عهد الموظفين بالمقبوضات النقدية من المرتجعات (تزيد نقدية العهدة)
        if totals["refunds_collected"] > Decimal("0.00"):
            func_refunds = (totals["refunds_collected"] * custody_rate).quantize(Decimal("0.01")) if is_custody_foreign else totals["refunds_collected"]
            lines_data.append({
                "account": custody_acc,
                "debit": func_refunds,
                "credit": Decimal("0.00"),
                "foreign_debit": totals["refunds_collected"] if is_custody_foreign else Decimal("0.00"),
                "currency": curr_code,
                "exchange_rate": custody_rate,
                "description": f"استرداد نقدي من مورد (مرتجع) مودع بالعهدة - سند {settlement.settlement_number}",
            })
            # دائن: المورد بالمبلغ المرتجع
            refund_sup_line = settlement.lines.filter(line_type=SettlementLineType.PURCHASE_REFUND, supplier__isnull=False).first()
            sup_obj = refund_sup_line.supplier if refund_sup_line else None
            sup_acc = getattr(sup_obj, "financial_account", None) or getattr(sup_obj, "account", None) if sup_obj else None
            sup_refund_acc = sup_acc or supplier_payable_acc or AccountRoleRegistry.get_account(AccountRoleNames.SUPPLIER_PAYABLE_CONTROL)
            if sup_refund_acc and not sup_refund_acc.can_post_entries():
                child = sup_refund_acc.children.filter(is_active=True).first()
                if child:
                    sup_refund_acc = child
            lines_data.append({
                "account": sup_refund_acc,
                "debit": Decimal("0.00"),
                "credit": func_refunds,
                "foreign_credit": totals["refunds_collected"] if is_custody_foreign else Decimal("0.00"),
                "currency": curr_code,
                "exchange_rate": custody_rate,
                "description": f"تسجيل مردودات مشتريات نقدية مستردة - سند {settlement.settlement_number}",
            })

        # مدين: معالجة العجز حسب مسار التوجيه المعتمد (F14)
        if totals["shortage_amount"] > Decimal("0.00"):
            func_shortage = (totals["shortage_amount"] * custody_rate).quantize(Decimal("0.01")) if is_custody_foreign else totals["shortage_amount"]
            routing = getattr(settlement, "variance_routing", None) or "hr_deduction"
            if routing == "expense_loss":
                loss_acc = AccountRoleRegistry.get_account(AccountRoleNames.CUSTODY_SHORTAGE_LOSS) or ChartOfAccounts.objects.filter(code="54900", is_active=True).first()
                if not loss_acc:
                    loss_acc = AccountRoleRegistry.get_account(AccountRoleNames.COGS_EXPENSE) or ChartOfAccounts.objects.filter(code="51100", is_active=True).first()
                lines_data.append({
                    "account": loss_acc,
                    "debit": func_shortage,
                    "credit": Decimal("0.00"),
                    "foreign_debit": totals["shortage_amount"] if is_custody_foreign else Decimal("0.00"),
                    "currency": curr_code,
                    "exchange_rate": custody_rate,
                    "description": f"خسائر وفروقات عجز تسوية عهدة معتمدة - سند {settlement.settlement_number}",
                })
            else:
                if not shortage_hr_acc:
                    shortage_hr_acc = AccountRoleRegistry.get_account(AccountRoleNames.CUSTODY_SHORTAGE_RECEIVABLE) or ChartOfAccounts.objects.filter(code="11230", is_active=True).first()
                lines_data.append({
                    "account": shortage_hr_acc,
                    "debit": func_shortage,
                    "credit": Decimal("0.00"),
                    "foreign_debit": totals["shortage_amount"] if is_custody_foreign else Decimal("0.00"),
                    "currency": curr_code,
                    "exchange_rate": custody_rate,
                    "description": f"عجز عهدة محمل على راتب الموظف {settlement.employee.name} - سند {settlement.settlement_number}",
                })

        # دائن: تخفيض حساب العهدة بالمصروفات الممتصة
        if totals["expenses_absorbed"] > Decimal("0.00"):
            func_absorbed = (totals["expenses_absorbed"] * custody_rate).quantize(Decimal("0.01")) if is_custody_foreign else totals["expenses_absorbed"]
            lines_data.append({
                "account": custody_acc,
                "debit": Decimal("0.00"),
                "credit": func_absorbed,
                "foreign_credit": totals["expenses_absorbed"] if is_custody_foreign else Decimal("0.00"),
                "currency": curr_code,
                "exchange_rate": custody_rate,
                "description": f"تخفيض عهدة الموظف {settlement.employee.name} بمصروفات التسوية - سند {settlement.settlement_number}",
            })

        # دائن: تخفيض حساب العهدة بالنقدية المردودة للخزينة
        if totals["cash_returned"] > Decimal("0.00"):
            func_returned = (totals["cash_returned"] * custody_rate).quantize(Decimal("0.01")) if is_custody_foreign else totals["cash_returned"]
            lines_data.append({
                "account": custody_acc,
                "debit": Decimal("0.00"),
                "credit": func_returned,
                "foreign_credit": totals["cash_returned"] if is_custody_foreign else Decimal("0.00"),
                "currency": curr_code,
                "exchange_rate": custody_rate,
                "description": f"تخفيض عهدة الموظف {settlement.employee.name} بالنقدية الموردة - سند {settlement.settlement_number}",
            })

        # دائن: تخفيض حساب العهدة بالعجز المحمل على الموظف
        if totals["shortage_amount"] > Decimal("0.00"):
            func_shortage = (totals["shortage_amount"] * custody_rate).quantize(Decimal("0.01")) if is_custody_foreign else totals["shortage_amount"]
            lines_data.append({
                "account": custody_acc,
                "debit": Decimal("0.00"),
                "credit": func_shortage,
                "foreign_credit": totals["shortage_amount"] if is_custody_foreign else Decimal("0.00"),
                "currency": curr_code,
                "exchange_rate": custody_rate,
                "description": f"إبراء ذمة صندوق العهدة بالعجز المحول لذمة الموظف - سند {settlement.settlement_number}",
            })

        # دائن: مستحقات عهد الموظفين بالفائض المسدد من جيب الموظف (Overrun)
        if totals["overrun_payable"] > Decimal("0.00"):
            if not overrun_payable_acc:
                overrun_payable_acc = ChartOfAccounts.objects.filter(code="21230", is_active=True).first()
            func_overrun = (totals["overrun_payable"] * custody_rate).quantize(Decimal("0.01")) if is_custody_foreign else totals["overrun_payable"]
            lines_data.append({
                "account": overrun_payable_acc,
                "debit": Decimal("0.00"),
                "credit": func_overrun,
                "foreign_credit": totals["overrun_payable"] if is_custody_foreign else Decimal("0.00"),
                "currency": curr_code,
                "exchange_rate": custody_rate,
                "description": f"فائض مصروفات مسدد من الموظف {settlement.employee.name} يستحق السداد له - سند {settlement.settlement_number}",
            })

        return lines_data

    # -------------------------------------------------------------------------
    # 5. ترحيل تسوية العهدة (Post Settlement)
    # -------------------------------------------------------------------------
    @classmethod
    def post_settlement(
        cls,
        settlement: PettyCashSettlement,
        approved_by_user: Any,
        notes: str = ""
    ) -> JournalEntry:
        """
        FIN-CORE-CUST-3.2, 3.4, 3.5, 3.8: اعتماد وترحيل تسوية العهدة
        مع القفل الذري وإعادة التحقق الداخلي والموازنة والربط المحكم بالمشتريات
        """
        if settlement.status in [SettlementStatus.POSTED, SettlementStatus.REVERSED, SettlementStatus.REJECTED]:
            raise ValidationError(f"لا يمكن ترحيل تسوية في حالة {settlement.get_status_display()}")

        lines = list(settlement.lines.select_related("expense_account", "cost_center", "supplier", "purchase_invoice", "currency").all())
        if not lines and (settlement.total_settled_amount or Decimal("0.00")) <= 0:
            raise ValidationError("لا يمكن ترحيل تسوية عهدة فارغة بدون بنود مصروفات.")

        if any(line.status == SettlementLineStatus.PENDING for line in lines):
            raise ValidationError("لا يمكن ترحيل تسوية تحتوي على بنود قيد المراجعة. يجب اعتماد أو رفض جميع البنود أولاً.")

        cls._validate_self_approval(settlement.employee, approved_by_user)

        with transaction.atomic():
            settlement_locked = PettyCashSettlement.objects.select_for_update().get(id=settlement.id)
            if settlement_locked.status in [SettlementStatus.POSTED, SettlementStatus.REVERSED, SettlementStatus.REJECTED]:
                raise ValidationError(f"لا يمكن ترحيل تسوية في حالة {settlement_locked.get_status_display()}")

            adv_locked = None
            if settlement_locked.custody_advance_id:
                adv_locked = EmployeeCustodyAdvance.objects.select_for_update().get(id=settlement_locked.custody_advance_id)
                # F09: التحقق من تطابق الموظف بين التسوية والعهدة
                if settlement_locked.employee_id != adv_locked.employee_id:
                    raise ValidationError(
                        f"حظر حوكمة: لا يمكن ترحيل تسوية تخص الموظف ({settlement_locked.employee.name}) "
                        f"على سلفة تخص موظفاً آخر ({adv_locked.employee.name})."
                    )
                settlement_locked.custody_advance = adv_locked

            period = cls._get_open_period(settlement_locked.settlement_date)

            # تحديد حساب العهدة والتحقق من التطابق مع السلفة (R4)
            if adv_locked:
                expected_custody_acc = getattr(adv_locked, "custody_account", None) or AccountRoleRegistry.get_account(AccountRoleNames.CUSTODY_TEMPORARY_CONTROL)
                if settlement_locked.custody_account_id and expected_custody_acc and settlement_locked.custody_account_id != expected_custody_acc.id:
                    raise ValidationError(
                        f"حظر حوكمة: حساب العهدة المحدد في التسوية ({settlement_locked.custody_account.name}) "
                        f"لا يطابق حساب السلفة المرتبطة ({expected_custody_acc.name})."
                    )
                custody_acc = expected_custody_acc
                settlement_locked.custody_account = custody_acc
            else:
                custody_acc = settlement_locked.custody_account
            if not custody_acc:
                custody_acc = AccountRoleRegistry.get_account(AccountRoleNames.CUSTODY_TEMPORARY_CONTROL)
            if not custody_acc:
                raise ValidationError("لم يتم العثور على حساب العهدة المحاسبي للتسوية.")

            # حساب الإجماليات بالمحرك الموحد
            totals = cls.calculate_settlement_totals(settlement_locked, lines=lines)
            curr_code = totals["float_currency_code"]

            # F01: احتساب التدفقات الخارجة الفعلية من totals حصراً دون الاعتماد على الحقول المخزنة
            computed_expenses = totals["gross_net_expenses"]
            computed_returned = totals["cash_returned"]
            computed_shortage = totals["shortage_amount"]
            computed_outflow = computed_expenses + computed_returned + computed_shortage
            refunds = totals["refunds_collected"]

            if adv_locked:
                total_available = adv_locked.current_balance + refunds
                if computed_outflow > total_available:
                    raise ValidationError(
                        f"تعارض تزامن: إجمالي التدفقات النقدية الخارجة من العهدة ({computed_outflow}) "
                        f"يتجاوز الرصيد المتاح تحت القفل ({total_available}). يرجى إعادة مراجعة التسوية."
                    )
            elif settlement_locked.custody_account_id:
                acc = ChartOfAccounts.objects.select_for_update().get(id=settlement_locked.custody_account_id)
                curr_type = "foreign" if (acc.currency and not getattr(acc.currency, "is_functional", True)) else "local"
                acc_balance = acc.get_balance(date_to=settlement_locked.settlement_date, currency_type=curr_type) or Decimal("0.00")
                total_available = acc_balance + refunds
                if computed_outflow > total_available:
                    raise ValidationError(
                        f"تعارض تزامن: إجمالي التدفقات الخارجة من الصندوق المستديم ({computed_outflow}) "
                        f"يتجاوز رصيد العهدة المستديمة المتاح دفترياً بعملة الحساب ({total_available})."
                    )

            # بناء بنود القيد المقترح
            lines_data = cls.build_settlement_journal_lines(
                settlement=settlement,
                totals=totals,
                custody_acc=custody_acc,
                curr_code=curr_code,
            )

            # 3.5: الفحص التجميعي المسبق للموازنة المشتق مباشرة من بنود القيد المحاسبي المقترح
            budget_aggregates = defaultdict(Decimal)
            for line_item in lines_data:
                debit_amt = line_item.get("debit", Decimal("0.00"))
                if debit_amt > Decimal("0.00"):
                    acc_obj = line_item.get("account")
                    cc_obj = line_item.get("cost_center")
                    if (
                        acc_obj
                        and cc_obj
                        and getattr(acc_obj, "account_type", None)
                        and getattr(acc_obj.account_type, "category", "") == "expense"
                    ):
                        budget_aggregates[(cc_obj.id, acc_obj.id)] += debit_amt.quantize(Decimal("0.01"))

            if budget_aggregates:
                cc_map = {cc.id: cc for cc in CostCenter.objects.filter(id__in=[k[0] for k in budget_aggregates.keys()])}
                acc_map = {acc.id: acc for acc in ChartOfAccounts.objects.filter(id__in=[k[1] for k in budget_aggregates.keys()])}
                for (c_id, a_id), total_functional_amount in budget_aggregates.items():
                    c_model = cc_map.get(c_id)
                    a_model = acc_map.get(a_id)
                    if c_model and a_model:
                        BudgetControlService.validate_budget_limit(
                            cost_center=c_model,
                            account=a_model,
                            accounting_period=period,
                            amount=total_functional_amount,
                            user=approved_by_user,
                        )

            # إنشاء القيد كمسودة وترحيله عبر محرك القيود المركزي
            draft_entry = LedgerCoreService.create_draft_entry(
                date=settlement.settlement_date,
                description=f"تسوية عهدة - {settlement.employee.name} - {settlement.settlement_number} - {settlement.notes or ''}",
                reference=f"CSET-{settlement.settlement_number}",
                entry_type="settlement",
                created_by=approved_by_user if approved_by_user and approved_by_user.is_authenticated else None,
                lines_data=lines_data,
                source_module="financial",
                source_model="PettyCashSettlement",
                source_id=settlement.id,
            )

            journal_entry = LedgerCoreService.post_entry(
                entry_id=draft_entry.id,
                user=approved_by_user if approved_by_user and approved_by_user.is_authenticated else None,
                source_type="PettyCashSettlement",
                source_id=str(settlement.id),
            )
            journal_entry.is_locked = True
            journal_entry.save(update_fields=["is_locked"])

            # 3.4: الربط المتكامل مع فواتير المشتريات وتحصين دفعة المشتريات (PurchasePayment Shield)
            for p_item in totals["processed_lines"]:
                s_line = p_item["line"]
                if s_line.line_type == SettlementLineType.SUPPLIER_INVOICE and s_line.purchase_invoice:
                    from purchase.models.purchase import Purchase
                    inv = Purchase.objects.select_for_update().get(id=s_line.purchase_invoice_id)
                    approved_gross_inv = p_item["approved_amount"]
                    if approved_gross_inv > Decimal("0.00"):
                        # F07: التحقق من عدم تجاوز المبلغ المستحق على الفاتورة
                        if approved_gross_inv > inv.amount_due:
                            raise ValidationError(
                                f"حظر حوكمة: قيمة سداد الفاتورة {inv.number} ({approved_gross_inv}) "
                                f"تتجاوز المبلغ المستحق المتبقي عليها ({inv.amount_due})."
                            )
                        inv_currency_code = getattr(inv.currency, "code", str(inv.currency or "EGP"))
                        inv_rate = getattr(inv, "exchange_rate", Decimal("1.000000")) or Decimal("1.000000")

                        effective_discount = p_item["effective_discount"]
                        effective_wht = p_item["effective_wht"]
                        net_cash_inv = approved_gross_inv - effective_discount - effective_wht

                        pmt_currency_code = curr_code
                        if settlement.custody_advance:
                            pmt_rate = settlement.custody_advance.exchange_rate or Decimal("1.000000")
                        elif settlement.custody_account:
                            pmt_rate = getattr(settlement.custody_account, "exchange_rate", Decimal("1.000000")) or Decimal("1.000000")
                        else:
                            pmt_rate = Decimal("1.000000")

                        func_curr = ExchangeRateService.get_functional_currency()
                        func_code = getattr(func_curr, "code", "EGP") or "EGP"

                        if pmt_currency_code == func_code:
                            payment_exchange_rate_field = Decimal("1.000000")
                        else:
                            payment_exchange_rate_field = pmt_rate

                        # تحديد وسيط محرك التسوية المركزي
                        if pmt_currency_code == inv_currency_code:
                            settlement_rate_param = pmt_rate
                        elif pmt_currency_code == func_code and inv_currency_code != func_code:
                            line_rate = getattr(s_line, "exchange_rate", None)
                            if line_rate and line_rate > Decimal("0.000000") and line_rate != Decimal("1.000000"):
                                conversion_rate = line_rate
                            else:
                                conversion_rate = None
                                try:
                                    official = ExchangeRateService.get_rate(inv_currency_code, func_code, date=settlement.settlement_date)
                                    if official and official > Decimal("0.000000") and official != Decimal("1.000000"):
                                        conversion_rate = official
                                except Exception:
                                    pass
                                if not conversion_rate and inv_rate and inv_rate != Decimal("1.000000"):
                                    conversion_rate = inv_rate

                            if not conversion_rate or conversion_rate == Decimal("1.000000"):
                                raise ValidationError(
                                    f"لا يمكن سداد فاتورة بالعملة الأجنبية ({inv_currency_code}) بنقدية محلية بسعر صرف 1.000000. "
                                    f"يرجى تسجيل سعر الصرف المعتمد بتاريخ {settlement.settlement_date} أو تحديده في سطر التسوية."
                                )
                            settlement_rate_param = conversion_rate
                        else:
                            settlement_rate_param = pmt_rate

                        fx_calc_gross = ExchangeRateService.calculate_payment_settlement(
                            invoice_amount=approved_gross_inv,
                            invoice_currency_code=inv_currency_code,
                            invoice_rate=inv_rate,
                            payment_currency_code=pmt_currency_code,
                            settlement_rate=settlement_rate_param,
                        )

                        fx_calc_net = ExchangeRateService.calculate_payment_settlement(
                            invoice_amount=net_cash_inv,
                            invoice_currency_code=inv_currency_code,
                            invoice_rate=inv_rate,
                            payment_currency_code=pmt_currency_code,
                            settlement_rate=settlement_rate_param,
                        )

                        amount_settled_invoice = fx_calc_gross["settled_invoice_amt"]
                        amount_paid_curr = fx_calc_net["amount_paid_currency"]
                        amount_functional = fx_calc_net["amount_functional"]
                        realized_fx = fx_calc_gross["realized_fx_difference"]

                        payment_currency_obj = Currency.objects.filter(code=pmt_currency_code).first()

                        payment = PurchasePayment.objects.create(
                            purchase=inv,
                            amount=amount_settled_invoice,
                            payment_date=settlement.settlement_date,
                            payment_method="custody",
                            financial_account=custody_acc,
                            financial_transaction=journal_entry,
                            source_type="CUSTODY",
                            status="posted",
                            financial_status="synced",
                            posted_at=timezone.now(),
                            posted_by=approved_by_user if approved_by_user and approved_by_user.is_authenticated else None,
                            created_by=approved_by_user if approved_by_user and approved_by_user.is_authenticated else None,
                            reference_number=settlement.settlement_number,
                            payment_currency=payment_currency_obj,
                            payment_exchange_rate=payment_exchange_rate_field,
                            amount_paid_currency=amount_paid_curr,
                            amount_settled_invoice_currency=amount_settled_invoice,
                            amount_functional=amount_functional,
                            discount_amount=effective_discount,
                            withholding_tax_amount=effective_wht,
                            realized_fx_difference=realized_fx,
                            notes=f"سداد عبر تسوية العهدة {settlement.settlement_number} - الموظف {settlement.employee.name}",
                        )
                        inv.update_payment_status()

                        PartnerBalanceService.apply_settlement_delta(
                            partner_type="supplier",
                            partner_id=inv.supplier_id,
                            settled_invoice_amount=amount_settled_invoice,
                            invoice_rate=inv_rate,
                            is_addition=False,
                        )

                        PartnerSubledgerService.record_payment_settlement(
                            payment=payment,
                            partner_type="supplier",
                            user=approved_by_user if approved_by_user and approved_by_user.is_authenticated else None,
                        )

            # تحديث حقول الأثر الفعلي الصريحة بنموذج التسوية
            settlement_locked.currency = Currency.objects.filter(code=curr_code).first()
            settlement_locked.status = SettlementStatus.POSTED
            settlement_locked.approved_by = approved_by_user if approved_by_user and approved_by_user.is_authenticated else None
            settlement_locked.approved_at = timezone.now()
            settlement_locked.journal_entry = journal_entry
            settlement_locked.expenses_absorbed = totals["expenses_absorbed"]
            settlement_locked.refunds_collected = totals["refunds_collected"]
            settlement_locked.cash_returned_to_treasury = totals["cash_returned"]
            settlement_locked.shortage_amount = totals["shortage_amount"]
            settlement_locked.overrun_amount = totals["overrun_payable"]
            settlement_locked.eligible_replenishment_amount = totals["eligible_replenishment_amount"]
            settlement_locked.save(update_fields=[
                "currency", "status", "approved_by", "approved_at", "journal_entry",
                "expenses_absorbed", "refunds_collected", "cash_returned_to_treasury",
                "shortage_amount", "overrun_amount", "eligible_replenishment_amount"
            ])

            # F01: تحديث سجل السلفة النقدية المقفولة حصراً
            if adv_locked:
                adv_locked.settled_amount = (adv_locked.settled_amount or Decimal("0.00")) + totals["expenses_absorbed"]
                adv_locked.refunds_collected_amount = (adv_locked.refunds_collected_amount or Decimal("0.00")) + totals["refunds_collected"]
                adv_locked.returned_cash_amount = (adv_locked.returned_cash_amount or Decimal("0.00")) + totals["cash_returned"]
                adv_locked.shortage_amount = (adv_locked.shortage_amount or Decimal("0.00")) + totals["shortage_amount"]
                adv_locked.update_balance()
                adv_locked.save(update_fields=[
                    "settled_amount", "refunds_collected_amount", "returned_cash_amount",
                    "shortage_amount", "current_balance", "status"
                ])
                settlement_locked.custody_advance = adv_locked
                settlement.custody_advance = adv_locked

            settlement.status = settlement_locked.status
            settlement.journal_entry = journal_entry
            settlement.expenses_absorbed = settlement_locked.expenses_absorbed
            settlement.refunds_collected = settlement_locked.refunds_collected
            settlement.cash_returned_to_treasury = settlement_locked.cash_returned_to_treasury
            settlement.shortage_amount = settlement_locked.shortage_amount
            settlement.overrun_amount = settlement_locked.overrun_amount
            settlement.eligible_replenishment_amount = settlement_locked.eligible_replenishment_amount

            logger.info(f"تم ترحيل تسوية العهدة {settlement.settlement_number} بنجاح وقيد رقم {journal_entry.number}")
            return journal_entry

    # -------------------------------------------------------------------------
    # 6. مناقلة العهدة بين الموظفين (Custody Transfer)
    # -------------------------------------------------------------------------
    @classmethod
    def transfer_custody(
        cls,
        transfer: CustodyTransfer,
        approved_by_user: Any,
        notes: str = ""
    ) -> JournalEntry:
        """
        FIN-CORE-CUST-3.7 & 3.10: إجراء مناقلة عهدة نقدية بين موظفين وتوليد القيد المحاسبي
        مع قفل السلف ذرياً وتحديث سجلات المسلّم والمستلم بدقة
        """
        if transfer.amount is None or transfer.amount <= Decimal("0.00"):
            raise ValidationError("مبلغ المناقلة يجب أن يكون أكبر من الصفر.")
        if transfer.from_employee_id == transfer.to_employee_id:
            raise ValidationError("لا يمكن عمل مناقلة عهدة لنفس الموظف.")

        # F04: التحقق من صلاحية اعتماد المناقلة
        if approved_by_user and getattr(approved_by_user, "is_authenticated", False):
            if not approved_by_user.is_superuser and not (
                approved_by_user.has_perm("financial.can_disburse_custody")
                or approved_by_user.has_perm("financial.can_transfer_custody")
            ):
                raise ValidationError("المستخدم غير مصرح له باعتماد مناقلة العهد النقدية.")

        cls._validate_self_approval(transfer.to_employee, approved_by_user)

        with transaction.atomic():
            custody_acc = AccountRoleRegistry.get_account(AccountRoleNames.CUSTODY_TEMPORARY_CONTROL)
            if not custody_acc:
                raise ValidationError("حساب مراقبة العهد غير محدد.")

            # القفل الذري لسلفة المسلّم والتحقق من كفاية الرصيد
            from_adv = None
            if transfer.from_advance_id:
                from_adv = EmployeeCustodyAdvance.objects.select_for_update().get(id=transfer.from_advance_id)
                if from_adv.employee_id != transfer.from_employee_id:
                    raise ValidationError(
                        f"حظر حوكمة: السلفة المختارة ({from_adv.advance_number}) لا تعود للموظف المسلّم ({transfer.from_employee.name})."
                    )
                if transfer.currency_id and from_adv.currency_id != transfer.currency_id:
                    raise ValidationError("حظر حوكمة: عملة المناقلة لا تطابق عملة سلفة المسلّم.")
                if from_adv.status not in [
                    CustodyAdvanceStatus.ACTIVE,
                    CustodyAdvanceStatus.PARTIALLY_SETTLED,
                    CustodyAdvanceStatus.OVERDUE,
                ]:
                    raise ValidationError(f"حظر حوكمة: سلفة المسلّم ليست نشطة (حالتها: {from_adv.get_status_display()}).")
            else:
                from_adv = EmployeeCustodyAdvance.objects.select_for_update().filter(
                    employee=transfer.from_employee,
                    status__in=[
                        CustodyAdvanceStatus.ACTIVE,
                        CustodyAdvanceStatus.PARTIALLY_SETTLED,
                        CustodyAdvanceStatus.OVERDUE,
                    ]
                ).order_by("-id").first()

            # F19: حظر المناقلة بدون عهدة مصدرية صالحة
            if not from_adv:
                raise ValidationError(
                    f"حظر حوكمة: لا توجد عهدة نقدية نشطة للموظف المسلّم ({transfer.from_employee.name}) للتحويل منها."
                )

            if from_adv.current_balance < transfer.amount:
                raise ValidationError(
                    f"رصيد عهدة الموظف المسلّم ({from_adv.current_balance}) غير كافٍ لتحويل ({transfer.amount})."
                )
            from_adv.transferred_out_amount = (from_adv.transferred_out_amount or Decimal("0.00")) + transfer.amount
            from_adv.update_balance()
            from_adv.save(update_fields=["transferred_out_amount", "current_balance", "status"])
            transfer.from_advance = from_adv

            # سلفة المستلم: تحديث سلفة قائمة أو إنشاء سلفة نشطة جديدة تلقائياً
            to_adv = None
            if transfer.to_advance_id:
                to_adv = EmployeeCustodyAdvance.objects.select_for_update().get(id=transfer.to_advance_id)
                if to_adv.employee_id != transfer.to_employee_id:
                    raise ValidationError(
                        f"حظر حوكمة: السلفة المستقبلة المختارة ({to_adv.advance_number}) لا تعود للموظف المستلم ({transfer.to_employee.name})."
                    )
                if transfer.currency_id and to_adv.currency_id != transfer.currency_id:
                    raise ValidationError("حظر حوكمة: عملة المناقلة لا تطابق عملة سلفة المستلم.")
                if to_adv.status not in [
                    CustodyAdvanceStatus.ACTIVE,
                    CustodyAdvanceStatus.PARTIALLY_SETTLED,
                    CustodyAdvanceStatus.OVERDUE,
                ]:
                    raise ValidationError(f"حظر حوكمة: سلفة المستلم ليست نشطة (حالتها: {to_adv.get_status_display()}).")
                to_adv.transferred_in_amount = (to_adv.transferred_in_amount or Decimal("0.00")) + transfer.amount
                to_adv.update_balance()
                to_adv.save(update_fields=["transferred_in_amount", "current_balance", "status"])
            else:
                to_adv = EmployeeCustodyAdvance.objects.select_for_update().filter(
                    employee=transfer.to_employee,
                    status__in=[
                        CustodyAdvanceStatus.ACTIVE,
                        CustodyAdvanceStatus.PARTIALLY_SETTLED,
                        CustodyAdvanceStatus.OVERDUE,
                    ]
                ).order_by("-id").first()
                if to_adv:
                    to_adv.transferred_in_amount = (to_adv.transferred_in_amount or Decimal("0.00")) + transfer.amount
                    to_adv.update_balance()
                    to_adv.save(update_fields=["transferred_in_amount", "current_balance", "status"])
                elif from_adv:
                    adv_num = SequenceService.get_next_number(DocumentType.CUSTODY_ADVANCE)
                    to_adv = EmployeeCustodyAdvance.objects.create(
                        advance_number=adv_num,
                        employee=transfer.to_employee,
                        user=approved_by_user if approved_by_user and approved_by_user.is_authenticated else None,
                        source_treasury=from_adv.source_treasury,
                        amount=transfer.amount,
                        settlement_principal_amount=transfer.amount,
                        current_balance=transfer.amount,
                        currency=transfer.currency or from_adv.currency,
                        exchange_rate=from_adv.exchange_rate,
                        issue_date=transfer.transfer_date,
                        due_date=transfer.transfer_date + timedelta(days=30),
                        purpose=f"استلام عهدة مناقلة من الموظف {transfer.from_employee.name} - سند {transfer.transfer_number}",
                        status=CustodyAdvanceStatus.ACTIVE,
                    )
            if not to_adv:
                raise ValidationError(
                    f"تعذر تحديد أو إنشاء عهدة نقدية للموظف المستلم ({transfer.to_employee.name})."
                )
            transfer.to_advance = to_adv

            period = cls._get_open_period(transfer.transfer_date)
            curr_code = transfer.currency.code if transfer.currency else "EGP"
            rate = getattr(transfer, "exchange_rate", None) or getattr(from_adv, "exchange_rate", Decimal("1.000000")) or Decimal("1.000000")
            func_amount = (transfer.amount * rate).quantize(Decimal("0.01"))
            is_foreign = (curr_code != "EGP")

            lines_data = [
                {
                    "account": custody_acc,
                    "debit": func_amount,
                    "credit": Decimal("0.00"),
                    "foreign_debit": transfer.amount if is_foreign else Decimal("0.00"),
                    "currency": curr_code,
                    "exchange_rate": rate,
                    "description": f"استلام عهدة مناقلة من الموظف {transfer.from_employee.name} - سند {transfer.transfer_number}",
                },
                {
                    "account": custody_acc,
                    "debit": Decimal("0.00"),
                    "credit": func_amount,
                    "foreign_credit": transfer.amount if is_foreign else Decimal("0.00"),
                    "currency": curr_code,
                    "exchange_rate": rate,
                    "description": f"تسليم عهدة مناقلة إلى الموظف {transfer.to_employee.name} - سند {transfer.transfer_number}",
                }
            ]

            draft_entry = LedgerCoreService.create_draft_entry(
                date=transfer.transfer_date,
                description=f"مناقلة عهدة نقدية من {transfer.from_employee.name} إلى {transfer.to_employee.name} - سند {transfer.transfer_number} - {transfer.notes or ''}",
                reference=f"CTRF-{transfer.transfer_number}",
                entry_type="transfer",
                created_by=approved_by_user if approved_by_user and approved_by_user.is_authenticated else None,
                lines_data=lines_data,
                source_module="financial",
                source_model="CustodyTransfer",
                source_id=transfer.id,
            )

            journal_entry = LedgerCoreService.post_entry(
                entry_id=draft_entry.id,
                user=approved_by_user if approved_by_user and approved_by_user.is_authenticated else None,
                source_type="CustodyTransfer",
                source_id=str(transfer.id),
            )
            journal_entry.is_locked = True
            journal_entry.save(update_fields=["is_locked"])

            transfer.status = CustodyAdvanceStatus.ACTIVE
            transfer.journal_entry = journal_entry
            transfer.save(update_fields=["status", "from_advance", "to_advance", "journal_entry"])

            # توثيق في سجل الإسناد التاريخي
            CustodyAssignmentHistory.objects.create(
                account=custody_acc,
                employee=transfer.to_employee,
                assigned_by=approved_by_user if approved_by_user and approved_by_user.is_authenticated else None,
                start_date=transfer.transfer_date,
                is_active=True,
                opening_balance_on_handover=transfer.amount,
                notes=f"مناقلة عهدة نقدية بمبلغ {transfer.amount} {curr_code} بسند {transfer.transfer_number} من الموظف {transfer.from_employee.name}",
            )

            logger.info(f"تم اعتماد مناقلة العهدة {transfer.transfer_number} بنجاح.")
            return journal_entry

    # -------------------------------------------------------------------------
    # 7. محضر جرد العهدة النقدية (Physical Cash Count)
    # -------------------------------------------------------------------------
    @classmethod
    def record_petty_cash_count(
        cls,
        count_obj: PettyCashCount,
        denominations_data: Optional[Dict[str, int]] = None
    ) -> PettyCashCount:
        """
        تسجيل محضر جرد العهدة النقدية وتفصيل فئات النقدية وحساب الفارق
        """
        with transaction.atomic():
            total_cash_counted = Decimal("0.00")

            if denominations_data:
                count_obj.denomination_breakdown = denominations_data
                for denom_str, count_val in denominations_data.items():
                    val = Decimal(str(denom_str))
                    cnt = int(count_val)
                    if cnt < 0:
                        raise ValidationError("عدد الفئات النقدية لا يمكن أن يكون سالباً.")
                    if val <= Decimal("0.00"):
                        raise ValidationError("قيمة الفئة النقدية يجب أن تكون موجبة.")
                    total_cash_counted += (val * cnt)
                count_obj.actual_cash_amount = total_cash_counted

            if count_obj.actual_cash_amount < Decimal("0.00"):
                raise ValidationError("مبلغ النقدية الفعلي لا يمكن أن يكون سالباً.")
            if count_obj.pending_vouchers_amount < Decimal("0.00"):
                raise ValidationError("مبلغ السندات المعلقة لا يمكن أن يكون سالباً.")

            total_actual = count_obj.actual_cash_amount + count_obj.pending_vouchers_amount
            count_obj.variance_amount = total_actual - count_obj.gl_balance

            if count_obj.variance_amount == Decimal("0.00"):
                count_obj.variance_type = "matched"
            elif count_obj.variance_amount < Decimal("0.00"):
                count_obj.variance_type = "shortage"
            else:
                count_obj.variance_type = "overage"

            count_obj.save()
            return count_obj

    # -------------------------------------------------------------------------
    # 8. محرك العكس المحاسبي الصارم للتسوية (Reverse Settlement)
    # -------------------------------------------------------------------------
    @classmethod
    def reverse_settlement(
        cls,
        settlement: PettyCashSettlement,
        approved_by_user: Any = None,
        reason: str = "",
        reversal_date: Optional[date] = None,
        **kwargs,
    ) -> JournalEntry:
        """
        FIN-CORE-CUST-4.1 & 3.4: عكس تسوية العهدة بدقة متناظرة 100% مع الترحيل
        مع استرجاع رصيد السلفة، وعكس دفعات المشتريات وتحديث الأستاذ المساعد للموردين
        """
        approved_by_user = approved_by_user or kwargs.get("reversed_by") or kwargs.get("user")
        if settlement.status != SettlementStatus.POSTED:
            raise ValidationError("حظر حوكمة: لا يمكن عكس تسوية غير مرحلة محاسبياً.")

        if getattr(settlement, "is_replenished", False):
            raise ValidationError("حظر حوكمة: لا يمكن عكس تسوية مستعاضة قبل عكس قيد الاستعاضة أولاً.")

        if not settlement.journal_entry_id:
            raise ValidationError("لا يوجد قيد محاسبي مرتبط بالتسوية لعكسه.")

        with transaction.atomic():
            settlement_locked = PettyCashSettlement.objects.select_for_update().get(id=settlement.id)
            if settlement_locked.status != SettlementStatus.POSTED:
                raise ValidationError("حظر حوكمة: لا يمكن عكس تسوية غير مرحلة محاسبياً.")
            if getattr(settlement_locked, "is_replenished", False):
                raise ValidationError("حظر حوكمة: لا يمكن عكس تسوية مستعاضة قبل عكس قيد الاستعاضة أولاً.")
            if not settlement_locked.journal_entry_id:
                raise ValidationError("لا يوجد قيد محاسبي مرتبط بالتسوية لعكسه.")

            rev_date = reversal_date or timezone.localdate()
            # 1. عكس قيد اليومية عبر المحرك المركزي
            reversal_entry = LedgerCoreService.reverse_entry(
                entry_id=settlement_locked.journal_entry_id,
                user=approved_by_user,
                reversal_reason=reason or f"عكس تسوية عهدة {settlement_locked.settlement_number}",
                reversal_date=rev_date,
            )
            reversal_entry.is_locked = True
            reversal_entry.save(update_fields=["is_locked"])

            # 2. استرجاع رصيد السلفة بدقة متناظرة 100%
            if settlement_locked.custody_advance_id:
                adv = EmployeeCustodyAdvance.objects.select_for_update().get(id=settlement_locked.custody_advance_id)
                adv.settled_amount -= (settlement_locked.expenses_absorbed or Decimal("0.00"))
                adv.refunds_collected_amount -= (settlement_locked.refunds_collected or Decimal("0.00"))
                adv.returned_cash_amount -= (settlement_locked.cash_returned_to_treasury or Decimal("0.00"))
                adv.shortage_amount -= (settlement_locked.shortage_amount or Decimal("0.00"))
                adv.update_balance()
                if adv.settled_amount <= Decimal("0.00"):
                    adv.status = CustodyAdvanceStatus.ACTIVE
                elif adv.current_balance > Decimal("0.00"):
                    adv.status = CustodyAdvanceStatus.PARTIALLY_SETTLED
                else:
                    adv.status = CustodyAdvanceStatus.SETTLED
                adv.save()

            # 3. عكس دفعات المشتريات المرتبطة وتحديث الأستاذ المساعد للموردين
            from purchase.models.payment import PurchasePayment
            from financial.services.partner_balance_service import PartnerBalanceService
            from financial.services.partner_subledger_service import PartnerSubledgerService

            payments = PurchasePayment.objects.filter(
                reference_number=settlement_locked.settlement_number,
                source_type="CUSTODY",
                status="posted",
            )
            for payment in payments:
                payment._allow_custody_reversal = True
                payment.status = "cancelled"
                payment.financial_status = "reversed"
                payment.save(update_fields=["status", "financial_status"])
                if payment.purchase:
                    payment.purchase.update_payment_status()
                    if payment.purchase.supplier_id:
                        # استعادة رصيد المورد الإجمالي (إعادة فتح الذمة المدينة للمورد)
                        PartnerBalanceService.apply_settlement_delta(
                            partner_type="supplier",
                            partner_id=payment.purchase.supplier_id,
                            settled_invoice_amount=payment.amount_settled_invoice_currency or payment.amount,
                            invoice_rate=payment.purchase.exchange_rate or Decimal("1.000000"),
                            is_addition=True,
                        )
                        # F08: استعادة وتحديث الأستاذ المساعد للمورد بعد إلغاء الدفعة واستعادة المبلغ المستحق
                        PartnerSubledgerService.reverse_payment_settlement(
                            payment=payment,
                            partner_type="supplier",
                            user=approved_by_user,
                        )

            # 4. تحديث حالة التسوية وتثبيت بيانات العكس
            settlement_locked.status = SettlementStatus.REVERSED
            settlement_locked.reversal_entry = reversal_entry
            settlement_locked._allow_custody_reversal = True
            settlement_locked.save(update_fields=["status", "reversal_entry"])

            settlement.status = SettlementStatus.REVERSED
            settlement.reversal_entry = reversal_entry
            settlement._allow_custody_reversal = True

            logger.info(f"تم عكس تسوية العهدة {settlement_locked.settlement_number} بنجاح بقيد عكسي {reversal_entry.number}.")
            return reversal_entry

    # -------------------------------------------------------------------------
    # 9. استعاضة العهدة المستديمة بالشروط الستة (Imprest Replenishment)
    # -------------------------------------------------------------------------
    @classmethod
    def replenish_settlement(
        cls,
        settlement: PettyCashSettlement,
        treasury_account: ChartOfAccounts,
        approved_by_user: Any = None,
        notes: str = "",
        **kwargs,
    ) -> JournalEntry:
        """
        FIN-CORE-CUST-4.2 & 3.7: استعاضة صندوق العهدة المستديمة بالشروط الستة الإلزامية
        """
        approved_by_user = approved_by_user or kwargs.get("created_by") or kwargs.get("user")
        # شرط 1: حالة التسوية مرحلة
        if settlement.status != SettlementStatus.POSTED:
            raise ValidationError("حظر حوكمة: لا يمكن استعاضة تسوية غير مرحلة محاسبياً.")

        # شرط 2: المسار المستديم حصراً
        if settlement.custody_account_id is None or settlement.custody_advance_id is not None:
            raise ValidationError("حظر حوكمة: الاستعاضة مقصورة حصرياً على تسويات صناديق العهد المستديمة.")

        # شرط 3: منع التكرار
        if getattr(settlement, "is_replenished", False):
            raise ValidationError("حظر حوكمة: تمت استعاضة هذه التسوية مسبقاً ولا يجوز تكرار الصرف.")

        # شرط 4: وجود مبلغ مؤهل
        replenish_amount = settlement.eligible_replenishment_amount or Decimal("0.00")
        if replenish_amount <= Decimal("0.00"):
            raise ValidationError("حظر حوكمة: لا يوجد مبلغ مؤهل للاستعاضة في هذه التسوية.")

        with transaction.atomic():
            settlement_locked = PettyCashSettlement.objects.select_for_update().get(id=settlement.id)
            if settlement_locked.status != SettlementStatus.POSTED:
                raise ValidationError("حظر حوكمة: لا يمكن استعاضة تسوية غير مرحلة محاسبياً.")
            if getattr(settlement_locked, "is_replenished", False):
                raise ValidationError("حظر حوكمة: تمت استعاضة هذه التسوية مسبقاً ولا يجوز تكرار الصرف.")

            custody_acc = ChartOfAccounts.objects.select_for_update().get(id=settlement_locked.custody_account_id)
            treasury_locked = ChartOfAccounts.objects.select_for_update().get(id=treasury_account.id)

            # شرط 5: فحص كفاية الخزينة وتحديد سعر الصرف المعتمد
            curr = settlement_locked.currency or (custody_acc.currency if custody_acc else None)
            curr_code = curr.code if curr else "EGP"
            is_foreign = (curr_code != "EGP")

            # استنتاج سعر الصرف المعتمد للعملة الأجنبية
            rate = kwargs.get("exchange_rate")
            if not rate or Decimal(str(rate)) <= Decimal("0.000000"):
                if settlement_locked.custody_advance and settlement_locked.custody_advance.exchange_rate:
                    rate = settlement_locked.custody_advance.exchange_rate
                elif settlement_locked.journal_entry:
                    je_line = settlement_locked.journal_entry.lines.filter(account=custody_acc, exchange_rate__gt=1).first()
                    if not je_line:
                        je_line = settlement_locked.journal_entry.lines.filter(exchange_rate__gt=1).first()
                    if je_line and je_line.exchange_rate:
                        rate = je_line.exchange_rate

                if (not rate or Decimal(str(rate)) <= Decimal("1.000000")) and is_foreign:
                    line_with_rate = settlement_locked.lines.exclude(status=SettlementLineStatus.REJECTED).filter(exchange_rate__gt=1).first()
                    if line_with_rate and line_with_rate.exchange_rate:
                        rate = line_with_rate.exchange_rate

                if (not rate or Decimal(str(rate)) <= Decimal("1.000000")) and is_foreign:
                    from financial.services.exchange_rate_service import ExchangeRateService
                    rate = ExchangeRateService.get_exchange_rate(curr or curr_code, date=settlement_locked.settlement_date or timezone.localdate())

                if (not rate or Decimal(str(rate)) <= Decimal("1.000000")) and is_foreign:
                    last_line = JournalEntryLine.objects.filter(
                        account=custody_acc,
                        exchange_rate__gt=1
                    ).order_by("-journal_entry__date", "-id").first()
                    if last_line and last_line.exchange_rate:
                        rate = last_line.exchange_rate

            if not rate or Decimal(str(rate)) <= Decimal("0.000000"):
                rate = Decimal("1.000000")
            else:
                rate = Decimal(str(rate))

            func_replenish = (replenish_amount * rate).quantize(Decimal("0.01"))
            # التحقق الأمني من صلاحيات الصرف وسقف الخزينة (R3)
            if approved_by_user and getattr(approved_by_user, "is_authenticated", False):
                from financial.services.treasury_security_service import TreasurySecurityService
                allowed, sec_msg = TreasurySecurityService.can_user_disburse(
                    user=approved_by_user,
                    treasury_id=treasury_locked.id,
                    amount=func_replenish,
                    target_date=timezone.localdate(),
                )
                if not allowed:
                    raise ValidationError(f"حظر أمني: {sec_msg}")

            cls._check_treasury_sufficiency(
                treasury_account=treasury_locked,
                advance_amount=replenish_amount,
                advance_currency=curr,
                target_date=timezone.localdate(),
                exchange_rate=rate,
            )

            # شرط 6: قيد الصرف التعويضي (من حـ/ العهدة المستديمة إلى حـ/ الخزينة)
            period = cls._get_open_period(timezone.localdate())

            lines_data = [
                {
                    "account": custody_acc,
                    "debit": func_replenish,
                    "credit": Decimal("0.00"),
                    "foreign_debit": replenish_amount if is_foreign else Decimal("0.00"),
                    "currency": curr_code,
                    "exchange_rate": rate,
                    "description": f"استعاضة صندوق عهدة مستديمة {custody_acc.name} - تسوية {settlement_locked.settlement_number}",
                },
                {
                    "account": treasury_locked,
                    "debit": Decimal("0.00"),
                    "credit": func_replenish,
                    "foreign_credit": replenish_amount if is_foreign else Decimal("0.00"),
                    "currency": curr_code,
                    "exchange_rate": rate,
                    "description": f"صرف نقدية استعاضة عهدة {custody_acc.name} - تسوية {settlement_locked.settlement_number}",
                },
            ]

            draft_entry = LedgerCoreService.create_draft_entry(
                date=timezone.localdate(),
                accounting_period=period,
                entry_type="custody_replenishment",
                description=f"استعاضة عهدة مستديمة {custody_acc.name} بموجب تسوية {settlement_locked.settlement_number} - {notes}",
                reference=f"CREPL-{settlement_locked.settlement_number}",
                lines_data=lines_data,
                created_by=approved_by_user,
                source_module="financial",
                source_model="PettyCashSettlementReplenishment",
                source_id=settlement_locked.id,
            )
            journal_entry = LedgerCoreService.post_entry(
                entry_id=draft_entry.id,
                user=approved_by_user,
                source_type="PettyCashSettlementReplenishment",
                source_id=str(settlement_locked.id),
            )
            journal_entry.is_locked = True
            journal_entry.save(update_fields=["is_locked"])

            settlement_locked.is_replenished = True
            settlement_locked.replenishment_entry = journal_entry
            settlement_locked.save(update_fields=["is_replenished", "replenishment_entry"])
            settlement.is_replenished = True
            settlement.replenishment_entry = journal_entry

            logger.info(f"تم صرف استعاضة التسوية {settlement_locked.settlement_number} بقيد {journal_entry.number}.")
            return journal_entry

    # -------------------------------------------------------------------------
    # 10. تسوية فروق الجرد الفعلي (Physical Count Adjustment)
    # -------------------------------------------------------------------------
    @classmethod
    def adjust_count(
        cls,
        count_obj: PettyCashCount = None,
        variance_routing: str = "hr_deduction",
        approved_by_user: Any = None,
        notes: str = "",
        **kwargs,
    ) -> Optional[JournalEntry]:
        """
        FIN-CORE-CUST-4.3 & 3.11: تسوية فروق الجرد الفعلي وترحيل قيود العجز أو الزيادة
        """
        count_obj = count_obj or kwargs.get("count")
        variance_routing = kwargs.get("adjustment_type") or variance_routing
        approved_by_user = approved_by_user or kwargs.get("user")
        if not count_obj:
            raise ValidationError("محضر الجرد غير محدد.")

        with transaction.atomic():
            count_locked = PettyCashCount.objects.select_for_update().get(pk=count_obj.pk)
            if count_locked.status == "adjusted":
                raise ValidationError("تمت تسوية فروق هذا المحضر مسبقاً.")

            diff_amt = abs(count_locked.variance_amount or Decimal("0.00"))
            if count_locked.variance_type == "matched" or diff_amt == Decimal("0.00"):
                count_locked.status = "adjusted"
                count_locked.save(update_fields=["status"])
                count_obj.status = "adjusted"
                return None

            custody_acc = count_locked.custody_account or AccountRoleRegistry.get_account(AccountRoleNames.CUSTODY_PERMANENT_CONTROL)
            if not custody_acc:
                custody_acc = ChartOfAccounts.objects.filter(code="11230", is_active=True).first()
            if not custody_acc:
                raise ValidationError("حساب العهدة غير محدد في محضر الجرد.")

            period = cls._get_open_period(count_locked.count_date.date() if hasattr(count_locked.count_date, "date") else timezone.localdate())
            curr_code = getattr(custody_acc.currency, "code", "EGP") if custody_acc.currency else "EGP"

            lines_data = []
            if count_locked.variance_type == "shortage":
                # عجز: دائن للعهدة لتخفيضها للرصيد الفعلي، ومدين حسب مسار المعالجة
                if variance_routing == "hr_deduction":
                    hr_acc = AccountRoleRegistry.get_account(AccountRoleNames.EMPLOYEE_ADVANCE) or ChartOfAccounts.objects.filter(code="11230", is_active=True).first()
                    if not hr_acc:
                        raise ValidationError("حساب سلف الموظفين (11230) غير معرف.")
                    debit_acc = hr_acc
                    desc = f"عجز جرد عهدة محمل على راتب الموظف {count_locked.employee.name if count_locked.employee else ''} - محضر {count_locked.count_number}"
                elif variance_routing == "expense_loss":
                    loss_acc = AccountRoleRegistry.get_account(AccountRoleNames.CUSTODY_SHORTAGE_LOSS) or ChartOfAccounts.objects.filter(code="54900", is_active=True).first()
                    debit_acc = loss_acc
                    desc = f"خسائر عجز جرد عهدة معتمد - محضر {count_locked.count_number}"
                else:
                    debit_acc = ChartOfAccounts.objects.filter(code="11230", is_active=True).first()
                    desc = f"تسوية عجز جرد عهدة - محضر {count_locked.count_number}"

                lines_data = [
                    {
                        "account": debit_acc,
                        "debit": diff_amt,
                        "credit": Decimal("0.00"),
                        "currency": curr_code,
                        "description": desc,
                    },
                    {
                        "account": custody_acc,
                        "debit": Decimal("0.00"),
                        "credit": diff_amt,
                        "currency": curr_code,
                        "description": f"إبراء ذمة صندوق العهدة بالعجز الفعلي - محضر {count_locked.count_number}",
                    },
                ]
            elif count_locked.variance_type == "overage":
                # زيادة: مدين للعهدة لرفعها للرصيد الفعلي، ودائن لإيرادات متنوعة
                rev_acc = ChartOfAccounts.objects.filter(code="42990", is_active=True).first() or AccountRoleRegistry.get_account(AccountRoleNames.GENERAL_SALES_REVENUE)
                lines_data = [
                    {
                        "account": custody_acc,
                        "debit": diff_amt,
                        "credit": Decimal("0.00"),
                        "currency": curr_code,
                        "description": f"إثبات زيادة نقدية فعلية بالعهدة - محضر {count_locked.count_number}",
                    },
                    {
                        "account": rev_acc,
                        "debit": Decimal("0.00"),
                        "credit": diff_amt,
                        "currency": curr_code,
                        "description": f"أرباح وإيرادات زيادة نقدية بجرد العهدة - محضر {count_locked.count_number}",
                    },
                ]

            entry_date = count_locked.count_date.date() if hasattr(count_locked.count_date, "date") else timezone.localdate()
            draft_entry = LedgerCoreService.create_draft_entry(
                date=entry_date,
                accounting_period=period,
                entry_type="adjustment",
                description=f"تسوية فروق جرد عهدة {custody_acc.name} - محضر {count_locked.count_number} - {notes}",
                reference=count_locked.count_number,
                lines_data=lines_data,
                created_by=approved_by_user,
                source_module="financial",
                source_model="PettyCashCountAdjustment",
                source_id=count_locked.id,
            )
            journal_entry = LedgerCoreService.post_entry(
                entry_id=draft_entry.id,
                user=approved_by_user,
                source_type="PettyCashCountAdjustment",
                source_id=str(count_locked.id),
            )
            journal_entry.is_locked = True
            journal_entry.save(update_fields=["is_locked"])

            count_locked.status = "adjusted"
            count_locked.save(update_fields=["status"])
            count_obj.status = "adjusted"

            logger.info(f"تمت تسوية فروق محضر الجرد {count_locked.count_number} بقيد {journal_entry.number}.")
            return journal_entry
