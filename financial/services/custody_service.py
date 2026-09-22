"""
Enterprise Custody Management Service (نظام إدارة وحوكمة عهد الموظفين الشامل)
-------------------------------------------------------------------------
Covers:
1. Cash Advances (صرف وتغذية العهد المؤقتة)
2. Petty Cash Settlements (اعتماد وترحيل التسويات المركبة متعددة البنود والضرائب)
3. Imprest Fund Replenishment (استعاضة العهد المستديمة)
4. Inter-Employee Custody Transfers (مناقلات العهد والأمانات)
5. Physical Cash Counting & Auditing (محاضر جرد العهد والفئات النقدية)
6. Safe Reversals (عكس التسويات مع الحفاظ على مسار المراجعة المحاسبي)
"""

from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any
import logging
from datetime import date

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from core.enums.document_types import DocumentType
from core.services.sequence_service import SequenceService
from financial.models.chart_of_accounts import ChartOfAccounts
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
from hr.models.employee import Employee
from hr.models.employee_asset_custody import (
    EmployeeAssetCustody,
    EmployeeAssetTransfer,
    AssetCustodyStatus,
)

logger = logging.getLogger(__name__)
User = get_user_model()


class CustodyManagementService:
    """
    محرك خدمات العهد والأمانات المالية والمحاسبية الموحد
    """

    DEFAULT_SYS_ACCOUNTS = {
        "custody_control": "11240",       # حساب مراقبة العهد النقدية للموظفين
        "main_treasury": "11110",         # الخزينة الرئيسية
        "input_vat": "11410",             # ضريبة القيمة المضافة على المدخلات
        "wht_payable": "21320",           # ضريبة الخصم والتحصيل من المنبع (نموذج 41)
        "cash_discount_earned": "42200",  # الخصم المكتسب من الموردين
        "custody_shortage_loss": "52910", # خسائر عجز العهد المعتمدة
        "fx_gain_loss": "52800",          # أرباح وخسائر فروق العملة المحققة
        "employee_receivable": "11230",   # سلف وذمم الموظفين (للتحميل على المرتب)
    }

    @classmethod
    def _get_account_by_code(cls, code: str) -> Optional[ChartOfAccounts]:
        """استرجاع الحساب من شجرة الحسابات بالكود"""
        return ChartOfAccounts.objects.filter(code=code, is_active=True).first()

    @classmethod
    def _get_open_period(cls, target_date: date) -> AccountingPeriod:
        """التحقق من وجود فترة محاسبية مفتوحة والتاريخ يقع ضمنها"""
        period = AccountingPeriod.objects.filter(
            start_date__lte=target_date,
            end_date__gte=target_date,
            status="open"
        ).first()
        if not period:
            period = AccountingPeriod.objects.filter(status="open").order_by("-start_date").first()
            if not period:
                raise ValidationError(f"لا توجد فترة محاسبية مفتوحة للتاريخ المالي {target_date}")
        return period

    @classmethod
    def _validate_self_approval(cls, employee: Employee, user: Any) -> None:
        """منع الصرف أو الاعتماد الذاتي إذا كان المستخدم هو الموظف المستفيد ذاته"""
        if not user or not user.is_authenticated:
            return
        user_emp = getattr(user, "employee_profile", None)
        if user_emp and user_emp.id == employee.id and not user.is_superuser:
            raise ValidationError("حظر الحوكمة: لا يجوز للموظف اعتماد أو صرف عهدة مالية لنفسه ذاتياً.")

    # -------------------------------------------------------------------------
    # 1. صرف وتغذية العهد النقدية (Disburse Advance)
    # -------------------------------------------------------------------------
    @classmethod
    def disburse_advance(
        cls,
        advance: EmployeeCustodyAdvance,
        disbursed_by_user: Any,
        notes: str = ""
    ) -> JournalEntry:
        """
        صرف العهدة النقدية وتوليد القيد المحاسبي وحفظ حركة الخزينة
        """
        if advance.status not in [CustodyAdvanceStatus.DRAFT, CustodyAdvanceStatus.PENDING_APPROVAL, CustodyAdvanceStatus.ACTIVE]:
            raise ValidationError(f"لا يمكن صرف عهدة في حالة {advance.get_status_display()}")

        cls._validate_self_approval(advance.employee, disbursed_by_user)

        with transaction.atomic():
            custody_acc = cls._get_account_by_code(cls.DEFAULT_SYS_ACCOUNTS["custody_control"])
            treasury_acc = advance.source_treasury or cls._get_account_by_code(cls.DEFAULT_SYS_ACCOUNTS["main_treasury"])

            if not custody_acc:
                raise ValidationError("حساب مراقبة العهد النقدية غير موجود في دليل الحسابات.")
            if not treasury_acc:
                raise ValidationError("خزينة الصرف غير محددة ولا يوجد حساب خزينة رئيسية.")

            period = cls._get_open_period(advance.issue_date)
            entry_number = f"CADV-{advance.advance_number}"
            curr_code = advance.currency.code if advance.currency else "EGP"

            journal_entry = JournalEntry.objects.create(
                number=entry_number,
                date=advance.issue_date,
                accounting_period=period,
                entry_type="cash_payment",
                status="posted",
                description=f"صرف عهدة نقدية - {advance.employee.name} - {advance.advance_number} - {advance.purpose}",
                source_module="financial",
                source_model="EmployeeCustodyAdvance",
                source_id=advance.id,
                created_by=disbursed_by_user if disbursed_by_user and disbursed_by_user.is_authenticated else None,
            )

            # مدين: عهدة الموظف
            JournalEntryLine.objects.create(
                journal_entry=journal_entry,
                account=custody_acc,
                debit=advance.amount,
                credit=Decimal("0.00"),
                currency=curr_code,
                exchange_rate=advance.exchange_rate,
                description=f"عهدة نقدية للموظف {advance.employee.name} - سند {advance.advance_number}",
            )

            # دائن: الخزينة المصدرة
            JournalEntryLine.objects.create(
                journal_entry=journal_entry,
                account=treasury_acc,
                debit=Decimal("0.00"),
                credit=advance.amount,
                currency=curr_code,
                exchange_rate=advance.exchange_rate,
                description=f"صرف عهدة نقدية للموظف {advance.employee.name} - سند {advance.advance_number}",
            )

            advance.status = CustodyAdvanceStatus.ACTIVE
            advance.current_balance = advance.amount
            advance.journal_entry = journal_entry
            advance.save(update_fields=["status", "current_balance", "journal_entry"])

            # تسجيل في السجل التاريخي
            CustodyAssignmentHistory.objects.create(
                account=custody_acc,
                employee=advance.employee,
                assigned_by=disbursed_by_user if disbursed_by_user and disbursed_by_user.is_authenticated else None,
                opening_balance_on_handover=advance.amount,
                notes=f"صرف عهدة نقدية برقم {advance.advance_number} بمبلغ {advance.amount} {curr_code}",
            )

            logger.info(f"تم صرف العهدة {advance.advance_number} بنجاح برقم قيد {entry_number}")
            return journal_entry

    # -------------------------------------------------------------------------
    # 2. اعتماد وترحيل تسوية العهدة (Post Settlement)
    # -------------------------------------------------------------------------
    @classmethod
    def post_settlement(
        cls,
        settlement: PettyCashSettlement,
        approved_by_user: Any,
        notes: str = ""
    ) -> JournalEntry:
        """
        اعتماد وترحيل تسوية العهدة وإنشاء القيد المحاسبي المركب الموحد والمتزن
        (Single Balanced Compound Entry)
        """
        if settlement.status in [SettlementStatus.POSTED, SettlementStatus.REVERSED]:
            raise ValidationError(f"لا يمكن ترحيل تسوية في حالة {settlement.get_status_display()}")

        lines = list(settlement.lines.select_related("expense_account", "cost_center", "supplier", "purchase_invoice").all())
        if not lines and settlement.total_settled_amount <= 0:
            raise ValidationError("لا يمكن ترحيل تسوية عهدة فارغة بدون بنود مصروفات.")

        cls._validate_self_approval(settlement.employee, approved_by_user)

        with transaction.atomic():
            period = cls._get_open_period(settlement.settlement_date)
            entry_number = f"CSET-{settlement.settlement_number}"

            custody_acc = settlement.custody_account
            if not custody_acc and settlement.custody_advance:
                custody_acc = cls._get_account_by_code(cls.DEFAULT_SYS_ACCOUNTS["custody_control"])
            if not custody_acc:
                custody_acc = cls._get_account_by_code(cls.DEFAULT_SYS_ACCOUNTS["custody_control"])

            if not custody_acc:
                raise ValidationError("لم يتم العثور على حساب العهدة المحاسبي للتسوية.")

            # تحديد رمز العملة
            curr_code = "EGP"
            if settlement.custody_advance and settlement.custody_advance.currency:
                curr_code = settlement.custody_advance.currency.code
            elif lines and lines[0].currency:
                curr_code = lines[0].currency.code

            journal_entry = JournalEntry.objects.create(
                number=entry_number,
                date=settlement.settlement_date,
                accounting_period=period,
                entry_type="settlement",
                status="posted",
                description=f"تسوية عهدة - {settlement.employee.name} - {settlement.settlement_number} - {settlement.notes or ''}",
                source_module="financial",
                source_model="PettyCashSettlement",
                source_id=settlement.id,
                created_by=approved_by_user if approved_by_user and approved_by_user.is_authenticated else None,
            )

            total_debit = Decimal("0.00")
            total_credit = Decimal("0.00")

            vat_acc = cls._get_account_by_code(cls.DEFAULT_SYS_ACCOUNTS["input_vat"])
            wht_acc = cls._get_account_by_code(cls.DEFAULT_SYS_ACCOUNTS["wht_payable"])
            discount_acc = cls._get_account_by_code(cls.DEFAULT_SYS_ACCOUNTS["cash_discount_earned"])

            for s_line in lines:
                line_acc = s_line.expense_account
                if not line_acc:
                    if s_line.supplier and s_line.supplier.account:
                        line_acc = s_line.supplier.account
                    elif s_line.line_type in [SettlementLineType.SUPPLIER_INVOICE, SettlementLineType.SUPPLIER_ADVANCE]:
                        line_acc = cls._get_account_by_code("21110")
                    else:
                        line_acc = cls._get_account_by_code("51100")

                net_line_amount = s_line.amount - s_line.tax_amount if s_line.tax_amount > 0 else s_line.amount

                # مدين: حساب المصروف
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=line_acc,
                    debit=net_line_amount,
                    credit=Decimal("0.00"),
                    cost_center=s_line.cost_center,
                    currency=curr_code,
                    description=f"{s_line.get_line_type_display()} - {s_line.description} - فاتورة {s_line.invoice_number or ''}",
                )
                total_debit += net_line_amount

                # مدين: ضريبة القيمة المضافة إن وجدت
                if s_line.tax_amount > 0:
                    if not vat_acc:
                        raise ValidationError("حساب ضريبة القيمة المضافة على المدخلات غير معرف في دليل الحسابات.")
                    JournalEntryLine.objects.create(
                        journal_entry=journal_entry,
                        account=vat_acc,
                        debit=s_line.tax_amount,
                        credit=Decimal("0.00"),
                        cost_center=s_line.cost_center,
                        currency=curr_code,
                        description=f"ضريبة مدخلات - تسوية {settlement.settlement_number}",
                    )
                    total_debit += s_line.tax_amount

                # دائن: ضريبة الخصم والتحصيل WHT إن وجدت
                if s_line.wht_amount > 0:
                    if not wht_acc:
                        raise ValidationError("حساب ضريبة الخصم من المنبع (نموذج 41) غير معرف في دليل الحسابات.")
                    JournalEntryLine.objects.create(
                        journal_entry=journal_entry,
                        account=wht_acc,
                        debit=Decimal("0.00"),
                        credit=s_line.wht_amount,
                        cost_center=s_line.cost_center,
                        currency=curr_code,
                        description=f"ضريبة خصم منبع {s_line.wht_rate}% - مورد {s_line.supplier.name if s_line.supplier else ''}",
                    )
                    total_credit += s_line.wht_amount

                # دائن: الخصم المكتسب إن وجد
                if s_line.discount_amount > 0:
                    if not discount_acc:
                        raise ValidationError("حساب الخصم المكتسب غير معرف في دليل الحسابات.")
                    JournalEntryLine.objects.create(
                        journal_entry=journal_entry,
                        account=discount_acc,
                        debit=Decimal("0.00"),
                        credit=s_line.discount_amount,
                        cost_center=s_line.cost_center,
                        currency=curr_code,
                        description=f"خصم مكتسب - تسوية {settlement.settlement_number}",
                    )
                    total_credit += s_line.discount_amount

            # معالجة النقدية الموردة للخزينة
            if settlement.cash_returned_to_treasury > 0:
                main_treasury_acc = cls._get_account_by_code(cls.DEFAULT_SYS_ACCOUNTS["main_treasury"])
                if main_treasury_acc:
                    JournalEntryLine.objects.create(
                        journal_entry=journal_entry,
                        account=main_treasury_acc,
                        debit=settlement.cash_returned_to_treasury,
                        credit=Decimal("0.00"),
                        currency=curr_code,
                        description=f"توريد متبقي عهدة نقدية للخزينة - سند {settlement.settlement_number}",
                    )
                    total_debit += settlement.cash_returned_to_treasury

            # الطرف الدائن الأساسي: تخفيض حساب العهدة
            custody_credit_amount = total_debit - total_credit
            if custody_credit_amount > 0:
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=custody_acc,
                    debit=Decimal("0.00"),
                    credit=custody_credit_amount,
                    currency=curr_code,
                    description=f"تخفيض عهدة الموظف {settlement.employee.name} بتسوية المستندات - سند {settlement.settlement_number}",
                )
                total_credit += custody_credit_amount

            # معالجة فروق التقريب
            if total_debit != total_credit:
                diff = total_debit - total_credit
                if abs(diff) <= Decimal("0.05"):
                    rounding_acc = cls._get_account_by_code("52990") or cls._get_account_by_code("42990")
                    if rounding_acc:
                        if diff > 0:
                            JournalEntryLine.objects.create(
                                journal_entry=journal_entry,
                                account=rounding_acc,
                                debit=Decimal("0.00"),
                                credit=diff,
                                currency=curr_code,
                                description="فروق تقريب كسور العملة بالتسوية",
                            )
                        else:
                            JournalEntryLine.objects.create(
                                journal_entry=journal_entry,
                                account=rounding_acc,
                                debit=abs(diff),
                                credit=Decimal("0.00"),
                                currency=curr_code,
                                description="فروق تقريب كسور العملة بالتسوية",
                            )
                else:
                    raise ValidationError(f"فشل اتزان القيد المحاسبي للتسوية: المدين ({total_debit}) لا يساوي الدائن ({total_credit}).")

            # تحديث حالة التسوية والعهدة المرتبطة
            settlement.status = SettlementStatus.POSTED
            settlement.approved_by = approved_by_user if approved_by_user and approved_by_user.is_authenticated else None
            settlement.approved_at = timezone.now()
            settlement.journal_entry = journal_entry
            settlement.save(update_fields=["status", "approved_by", "approved_at", "journal_entry"])

            if settlement.custody_advance:
                adv = settlement.custody_advance
                adv.settled_amount += settlement.total_settled_amount
                adv.returned_cash_amount += settlement.cash_returned_to_treasury
                adv.update_balance()

            logger.info(f"تم ترحيل تسوية العهدة {settlement.settlement_number} بنجاح وقيد رقم {entry_number}")
            return journal_entry

    # -------------------------------------------------------------------------
    # 3. مناقلة العهدة بين الموظفين (Custody Transfer)
    # -------------------------------------------------------------------------
    @classmethod
    def transfer_custody(
        cls,
        transfer: CustodyTransfer,
        approved_by_user: Any,
        notes: str = ""
    ) -> JournalEntry:
        """
        إجراء مناقلة عهدة نقدية بين موظفين وتوليد القيد المحاسبي
        """
        if transfer.from_employee == transfer.to_employee:
            raise ValidationError("لا يمكن عمل مناقلة عهدة لنفس الموظف.")

        cls._validate_self_approval(transfer.to_employee, approved_by_user)

        with transaction.atomic():
            custody_acc = cls._get_account_by_code(cls.DEFAULT_SYS_ACCOUNTS["custody_control"])
            if not custody_acc:
                raise ValidationError("حساب مراقبة العهد غير محدد.")

            period = cls._get_open_period(transfer.transfer_date)
            entry_number = f"CTRF-{transfer.transfer_number}"
            curr_code = transfer.currency.code if transfer.currency else "EGP"

            journal_entry = JournalEntry.objects.create(
                number=entry_number,
                date=transfer.transfer_date,
                accounting_period=period,
                entry_type="transfer",
                status="posted",
                description=f"مناقلة عهدة نقدية من {transfer.from_employee.name} إلى {transfer.to_employee.name} - سند {transfer.transfer_number} - {transfer.notes}",
                source_module="financial",
                source_model="CustodyTransfer",
                source_id=transfer.id,
                created_by=approved_by_user if approved_by_user and approved_by_user.is_authenticated else None,
            )

            # مدين: عهدة الموظف الجديد
            JournalEntryLine.objects.create(
                journal_entry=journal_entry,
                account=custody_acc,
                debit=transfer.amount,
                credit=Decimal("0.00"),
                currency=curr_code,
                description=f"استلام عهدة مناقلة من الموظف {transfer.from_employee.name} - سند {transfer.transfer_number}",
            )

            # دائن: عهدة الموظف السابق
            JournalEntryLine.objects.create(
                journal_entry=journal_entry,
                account=custody_acc,
                debit=Decimal("0.00"),
                credit=transfer.amount,
                currency=curr_code,
                description=f"تسليم عهدة مناقلة إلى الموظف {transfer.to_employee.name} - سند {transfer.transfer_number}",
            )

            transfer.status = CustodyAdvanceStatus.ACTIVE
            transfer.journal_entry = journal_entry
            transfer.save(update_fields=["status", "journal_entry"])

            # توثيق في سجل الإسناد التاريخي
            CustodyAssignmentHistory.objects.create(
                account=custody_acc,
                employee=transfer.to_employee,
                assigned_by=approved_by_user if approved_by_user and approved_by_user.is_authenticated else None,
                opening_balance_on_handover=transfer.amount,
                notes=f"مناقلة عهدة نقدية بمبلغ {transfer.amount} {curr_code} بسند {transfer.transfer_number} من الموظف {transfer.from_employee.name}",
            )

            logger.info(f"تم اعتماد مناقلة العهدة {transfer.transfer_number} بنجاح.")
            return journal_entry

    # -------------------------------------------------------------------------
    # 4. محضر جرد العهدة النقدية (Physical Cash Count)
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
                    total_cash_counted += (val * cnt)
                count_obj.actual_cash_amount = total_cash_counted

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
