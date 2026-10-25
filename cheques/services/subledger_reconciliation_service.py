# -*- coding: utf-8 -*-
import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional
from datetime import date

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from financial.models import ChartOfAccounts, JournalEntryLine
from cheques.models import (
    Cheque,
    ChequeType,
    ChequePurpose,
    ChequeStatus,
    ChequeActionLog,
    ChequeActionType,
    ChequeSettlementLine,
)

logger = logging.getLogger(__name__)


class ChequeSubledgerReconciliationService:
    """
    محرك مطابقة الأستاذ المساعد التاريخي اللحظي
    (Point-in-Time Subledger Reconciliation Engine)
    يعيد بناء الحالة والقيمة الدفترية التاريخية لأي تاريخ سابق (as_of_date) بدقة مطابقة للأستاذ العام بالسنت.
    """

    @classmethod
    def get_historical_status(cls, cheque: Cheque, as_of_date: date) -> str:
        """
        تحديد الحالة التاريخية للشيك في تاريخ محدد بالرجوع لسجل الحركات الزمني
        """
        last_log = cheque.action_logs.filter(
            action_date__lte=as_of_date
        ).order_by("-id").first()

        if last_log:
            return last_log.to_status

        # إذا لم تكن هناك حركات مسجلة قبل أو في ذلك التاريخ
        if cheque.issue_date and cheque.issue_date <= as_of_date and not cheque.action_logs.exists():
            return cheque.status
        return ChequeStatus.DRAFT

    @classmethod
    def compute_historical_carrying_value(cls, cheque: Cheque, as_of_date: date) -> Decimal:
        """
        إعادة بناء القيمة الدفترية التاريخية للشيك في as_of_date بدون قراءة القيمة اللحظية الحالية:
        Historical Carrying Value = Functional Amount - Net Settled Book Value at Date + Active FX at Date
        """
        base_functional = cheque.functional_amount or Decimal("0.00")

        # 1. صافي التسويات والتحصيلات في ذلك التاريخ
        # أ. التسويات القائمة التي تاريخها <= as_of_date
        settled_lines = ChequeSettlementLine.objects.filter(
            cheque=cheque,
            settlement_date__lte=as_of_date
        )
        net_settled_book_val = settled_lines.aggregate(
            total=models.Sum("book_value_functional")
        )["total"] or Decimal("0.00")

        # ب. التسويات التي تم عكسها لاحقاً ولكن بعد as_of_date (كانت سارية في as_of_date)
        collect_actions = cheque.action_logs.filter(
            action__in=[ChequeActionType.COLLECT, ChequeActionType.PARTIAL_COLLECT, ChequeActionType.CLEAR],
            action_date__lte=as_of_date,
            is_reversed=True
        )
        for act in collect_actions:
            rev_date = None
            if act.reversed_by_log:
                rev_date = act.reversed_by_log.action_date
            else:
                rev_log = cheque.action_logs.filter(
                    action=ChequeActionType.REVERSE_ACTION,
                    id__gt=act.id
                ).order_by("id").first()
                if rev_log:
                    rev_date = rev_log.action_date

            # إذا تم العكس بعد تاريخ التقرير، فإن الحركة كانت سارية في as_of_date
            if rev_date and rev_date > as_of_date:
                if cheque.amount and cheque.amount > Decimal("0.00"):
                    ratio = act.amount_processed / cheque.amount
                    part_book_val = (base_functional * ratio).quantize(Decimal("0.01"))
                else:
                    part_book_val = act.amount_processed
                net_settled_book_val += part_book_val

        # 2. قيود إعادة تقييم العملات الأجنبية السارية في ذلك التاريخ
        active_fx = Decimal("0.00")
        try:
            from financial.fx.models import FXRevaluationLine
            cheque_source_type = 'NOTES_RECEIVABLE' if cheque.cheque_type == ChequeType.RECEIVABLE else 'NOTES_PAYABLE'
            fx_lines = FXRevaluationLine.objects.filter(
                source_type=cheque_source_type,
                source_id=str(cheque.id),
                run__journal_entry__status="posted",
                run__journal_entry__date__lte=as_of_date,
            )
            for fl in fx_lines:
                # التحقق هل تم عكس هذا التقييم بتشغيل عكسي قبل أو في as_of_date؟
                is_reversed_at_date = fl.run.reversed_by_runs.filter(
                    journal_entry__status="posted",
                    journal_entry__date__lte=as_of_date
                ).exists()
                if is_reversed_at_date:
                    continue
                diff = getattr(fl, "unrealized_difference", None)
                if diff is None:
                    diff = getattr(fl, "unrealized_gain_loss", Decimal("0.00"))

                # في أوراق القبض (أصول): فرق التقييم الموجب (ربح) يزيد القيمة الدفترية للأصل
                # في أوراق الدفع (التزامات): فرق التقييم مسجل كـ (old_functional - closing_functional) حيث الخسارة سالبة
                # فإذا ارتفع سعر الصرف وتكبدت الشركة خسارة تقييم سالبة، فإن التزام ورقة الدفع يزداد (base - diff)
                if cheque.cheque_type == ChequeType.PAYABLE:
                    active_fx -= diff
                else:
                    active_fx += diff
        except Exception as e:
            logger.debug(f"FX revaluation check for cheque #{cheque.id}: {e}")

        carrying_val = base_functional - net_settled_book_val + active_fx
        return carrying_val if carrying_val >= Decimal("0.00") else Decimal("0.00")

    @classmethod
    def calculate_cheque_carrying_value_at_date(cls, cheque: Cheque, as_of_date: date) -> Decimal:
        """اسم بديل للتوافق مع استعلامات القيمة الدفترية في تاريخ محدد"""
        return cls.compute_historical_carrying_value(cheque, as_of_date)

    @classmethod
    def reconcile_at_date(cls, as_of_date: date) -> Dict[str, Any]:
        """
        مطابقة أرصدة حسابات أوراق القبض والدفع وبرسم التحصيل بالأستاذ العام في تاريخ سابق:
        1. حساب 11220 (أوراق القبض بالخزينة)
        2. حساب 11190 (شيكات برسم التحصيل بالبنوك)
        3. حساب 21120 (أوراق الدفع والتزامات الشيكات الصادرة)
        """
        results = {}

        # أ. مطابقة أوراق القبض (11220)
        rec_cheques = Cheque.objects.filter(
            cheque_type=ChequeType.RECEIVABLE,
            issue_date__lte=as_of_date
        ).exclude(purpose=ChequePurpose.SECURITY_GUARANTEE)

        subledger_rec_total = Decimal("0.00")
        for chq in rec_cheques:
            hist_status = cls.get_historical_status(chq, as_of_date)
            if hist_status == ChequeStatus.IN_PORTFOLIO:
                subledger_rec_total += cls.compute_historical_carrying_value(chq, as_of_date)

        gl_rec_lines = JournalEntryLine.objects.filter(
            account__code="11220",
            journal_entry__status="posted",
            journal_entry__date__lte=as_of_date
        ).aggregate(
            debit=models.Sum("debit"),
            credit=models.Sum("credit")
        )
        gl_rec_balance = (gl_rec_lines["debit"] or Decimal("0.00")) - (gl_rec_lines["credit"] or Decimal("0.00"))

        results["11220_notes_receivable"] = {
            "account_code": "11220",
            "account_name": _("أوراق القبض (في الخزينة)"),
            "subledger_balance": subledger_rec_total,
            "gl_balance": gl_rec_balance,
            "difference": abs(gl_rec_balance - subledger_rec_total),
            "is_matched": abs(gl_rec_balance - subledger_rec_total) <= Decimal("0.05"),
        }

        # ب. مطابقة شيكات برسم التحصيل (11190)
        subledger_coll_total = Decimal("0.00")
        for chq in rec_cheques:
            hist_status = cls.get_historical_status(chq, as_of_date)
            if hist_status in [ChequeStatus.UNDER_COLLECTION, ChequeStatus.PARTIALLY_COLLECTED]:
                subledger_coll_total += cls.compute_historical_carrying_value(chq, as_of_date)

        gl_coll_lines = JournalEntryLine.objects.filter(
            account__code="11190",
            journal_entry__status="posted",
            journal_entry__date__lte=as_of_date
        ).aggregate(
            debit=models.Sum("debit"),
            credit=models.Sum("credit")
        )
        gl_coll_balance = (gl_coll_lines["debit"] or Decimal("0.00")) - (gl_coll_lines["credit"] or Decimal("0.00"))

        results["11190_cheques_under_collection"] = {
            "account_code": "11190",
            "account_name": _("شيكات برسم التحصيل (لدى البنوك)"),
            "subledger_balance": subledger_coll_total,
            "gl_balance": gl_coll_balance,
            "difference": abs(gl_coll_balance - subledger_coll_total),
            "is_matched": abs(gl_coll_balance - subledger_coll_total) <= Decimal("0.05"),
        }

        # ج. مطابقة أوراق الدفع (21120)
        pay_cheques = Cheque.objects.filter(
            cheque_type=ChequeType.PAYABLE,
            issue_date__lte=as_of_date
        ).exclude(purpose=ChequePurpose.SECURITY_GUARANTEE)

        subledger_pay_total = Decimal("0.00")
        for chq in pay_cheques:
            hist_status = cls.get_historical_status(chq, as_of_date)
            if hist_status == ChequeStatus.ISSUED:
                subledger_pay_total += cls.compute_historical_carrying_value(chq, as_of_date)

        gl_pay_lines = JournalEntryLine.objects.filter(
            account__code="21120",
            journal_entry__status="posted",
            journal_entry__date__lte=as_of_date
        ).aggregate(
            debit=models.Sum("debit"),
            credit=models.Sum("credit")
        )
        gl_pay_balance = (gl_pay_lines["credit"] or Decimal("0.00")) - (gl_pay_lines["debit"] or Decimal("0.00"))

        results["21120_notes_payable"] = {
            "account_code": "21120",
            "account_name": _("أوراق الدفع (التزامات الشيكات الصادرة)"),
            "subledger_balance": subledger_pay_total,
            "gl_balance": gl_pay_balance,
            "difference": abs(gl_pay_balance - subledger_pay_total),
            "is_matched": abs(gl_pay_balance - subledger_pay_total) <= Decimal("0.05"),
        }

        results["overall_matched"] = all(item["is_matched"] for item in results.values())
        return results

    @classmethod
    def reconcile_with_details(cls, as_of_date: date) -> Dict[str, Any]:
        """
        تقرير مطابقة تفصيلي يتضمن أرصدة الأستاذ العام والأستاذ المساعد مع تفصيل الشيكات المشاركة
        """
        summary = cls.reconcile_at_date(as_of_date)

        # تفصيل أوراق القبض (11220)
        rec_cheques = Cheque.objects.filter(
            cheque_type=ChequeType.RECEIVABLE,
            issue_date__lte=as_of_date
        ).exclude(purpose=ChequePurpose.SECURITY_GUARANTEE).select_related("customer", "currency")

        rec_details: List[Dict[str, Any]] = []
        coll_details: List[Dict[str, Any]] = []

        for chq in rec_cheques:
            hist_status = cls.get_historical_status(chq, as_of_date)
            carrying_val = cls.compute_historical_carrying_value(chq, as_of_date)

            item = {
                "cheque": chq,
                "id": chq.id,
                "voucher_number": chq.voucher_number,
                "cheque_number": chq.cheque_number,
                "partner_name": chq.partner_name,
                "currency_code": chq.currency.code if chq.currency else "EGP",
                "amount": chq.amount,
                "carrying_value": carrying_val,
                "historical_status": hist_status,
                "historical_status_display": dict(ChequeStatus.choices).get(hist_status, hist_status),
                "issue_date": chq.issue_date,
                "due_date": chq.due_date,
                "bank_name": chq.deposit_bank_account.name if chq.deposit_bank_account else (chq.bank_name or "-"),
            }

            if hist_status == ChequeStatus.IN_PORTFOLIO:
                rec_details.append(item)
            elif hist_status in [ChequeStatus.UNDER_COLLECTION, ChequeStatus.PARTIALLY_COLLECTED]:
                coll_details.append(item)

        # تفصيل أوراق الدفع (21120)
        pay_cheques = Cheque.objects.filter(
            cheque_type=ChequeType.PAYABLE,
            issue_date__lte=as_of_date
        ).exclude(purpose=ChequePurpose.SECURITY_GUARANTEE).select_related("supplier", "currency", "deposit_bank_account")

        pay_details: List[Dict[str, Any]] = []
        for chq in pay_cheques:
            hist_status = cls.get_historical_status(chq, as_of_date)
            if hist_status == ChequeStatus.ISSUED:
                carrying_val = cls.compute_historical_carrying_value(chq, as_of_date)
                pay_details.append({
                    "cheque": chq,
                    "id": chq.id,
                    "voucher_number": chq.voucher_number,
                    "cheque_number": chq.cheque_number,
                    "partner_name": chq.partner_name,
                    "currency_code": chq.currency.code if chq.currency else "EGP",
                    "amount": chq.amount,
                    "carrying_value": carrying_val,
                    "historical_status": hist_status,
                    "historical_status_display": dict(ChequeStatus.choices).get(hist_status, hist_status),
                    "issue_date": chq.issue_date,
                    "due_date": chq.due_date,
                    "bank_name": chq.deposit_bank_account.name if chq.deposit_bank_account else (chq.bank_name or "-"),
                })

        summary["11220_notes_receivable"]["cheques"] = rec_details
        summary["11220_notes_receivable"]["count"] = len(rec_details)

        summary["11190_cheques_under_collection"]["cheques"] = coll_details
        summary["11190_cheques_under_collection"]["count"] = len(coll_details)

        summary["21120_notes_payable"]["cheques"] = pay_details
        summary["21120_notes_payable"]["count"] = len(pay_details)

        summary["as_of_date"] = as_of_date
        summary["total_cheques_count"] = len(rec_details) + len(coll_details) + len(pay_details)
        return summary
