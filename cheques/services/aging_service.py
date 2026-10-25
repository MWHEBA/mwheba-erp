# -*- coding: utf-8 -*-
import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional
from datetime import date

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from cheques.models import (
    Cheque,
    ChequeType,
    ChequePurpose,
    ChequeStatus,
)

logger = logging.getLogger(__name__)


class ChequeAgingService:
    """
    خدمة تحليل وميزان أعمار أوراق القبض وأوراق الدفع
    (Cheque Aging Analysis & Schedule Engine)
    تقوم بتبويب الشيكات بحسب تاريخ الاستحقاق وفترات التأخير لتقدير السيولة النقدية والمخاطر الائتمانية.
    """

    OVERDUE_BRACKETS = [
        {"key": "current", "label": _("غير متأخر (ساري)"), "min_days": None, "max_days": 0},
        {"key": "1_30", "label": _("متأخر 1 - 30 يوم"), "min_days": 1, "max_days": 30},
        {"key": "31_60", "label": _("متأخر 31 - 60 يوم"), "min_days": 31, "max_days": 60},
        {"key": "61_90", "label": _("متأخر 61 - 90 يوم"), "min_days": 61, "max_days": 90},
        {"key": "91_120", "label": _("متأخر 91 - 120 يوم"), "min_days": 91, "max_days": 120},
        {"key": "120_plus", "label": _("متأخر أكثر من 120 يوم"), "min_days": 121, "max_days": None},
    ]

    FUTURE_BRACKETS = [
        {"key": "due_0_7", "label": _("يستحق خلال 7 أيام"), "min_days": 0, "max_days": 7},
        {"key": "due_8_30", "label": _("يستحق خلال 8 - 30 يوم"), "min_days": 8, "max_days": 30},
        {"key": "due_31_60", "label": _("يستحق خلال 31 - 60 يوم"), "min_days": 31, "max_days": 60},
        {"key": "due_61_90", "label": _("يستحق خلال 61 - 90 يوم"), "min_days": 61, "max_days": 90},
        {"key": "due_90_plus", "label": _("يستحق بعد أكثر من 90 يوم"), "min_days": 91, "max_days": None},
    ]

    @classmethod
    def get_aging_bracket(cls, days_overdue: int) -> Dict[str, Any]:
        """
        تحديد شريحة التأخير للشيك استناداً لعدد أيام تجاوز تاريخ الاستحقاق
        """
        if days_overdue <= 0:
            return cls.OVERDUE_BRACKETS[0]
        elif 1 <= days_overdue <= 30:
            return cls.OVERDUE_BRACKETS[1]
        elif 31 <= days_overdue <= 60:
            return cls.OVERDUE_BRACKETS[2]
        elif 61 <= days_overdue <= 90:
            return cls.OVERDUE_BRACKETS[3]
        elif 91 <= days_overdue <= 120:
            return cls.OVERDUE_BRACKETS[4]
        else:
            return cls.OVERDUE_BRACKETS[5]

    @classmethod
    def get_aging_report(
        cls,
        as_of_date: Optional[date] = None,
        cheque_type: str = ChequeType.RECEIVABLE,
        partner_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        توليد تقرير ميزان أعمار الشيكات الشامل:
        - التبويب الزمني للمتأخرات
        - التبويب بحسب الشريك (العميل / المورد)
        - التفصيل الدقيق لكل شيك
        """
        if not as_of_date:
            as_of_date = timezone.now().date()

        # الحالات النشطة المعتبرة في التحليل
        if cheque_type == ChequeType.RECEIVABLE:
            active_statuses = [
                ChequeStatus.IN_PORTFOLIO,
                ChequeStatus.UNDER_COLLECTION,
                ChequeStatus.PARTIALLY_COLLECTED,
                ChequeStatus.BOUNCED,
                ChequeStatus.LEGAL_ACTION,
            ]
        else:
            active_statuses = [
                ChequeStatus.ISSUED,
                ChequeStatus.BOUNCED,
            ]

        qs = Cheque.objects.filter(
            cheque_type=cheque_type,
            status__in=active_statuses,
        ).exclude(purpose=ChequePurpose.SECURITY_GUARANTEE).select_related(
            "customer", "supplier", "currency", "deposit_bank_account"
        )

        if partner_id:
            if cheque_type == ChequeType.RECEIVABLE:
                qs = qs.filter(customer_id=partner_id)
            else:
                qs = qs.filter(supplier_id=partner_id)

        # مجاميع الشرائح
        bracket_totals = {
            "current": {"label": str(_("ساري (غير متأخر)")), "amount": Decimal("0.00"), "count": 0},
            "1_30": {"label": str(_("متأخر 1 - 30 يوم")), "amount": Decimal("0.00"), "count": 0},
            "31_60": {"label": str(_("متأخر 31 - 60 يوم")), "amount": Decimal("0.00"), "count": 0},
            "61_90": {"label": str(_("متأخر 61 - 90 يوم")), "amount": Decimal("0.00"), "count": 0},
            "91_120": {"label": str(_("متأخر 91 - 120 يوم")), "amount": Decimal("0.00"), "count": 0},
            "120_plus": {"label": str(_("متأخر أكثر من 120 يوم")), "amount": Decimal("0.00"), "count": 0},
        }

        # مجاميع الشركاء
        partners_data: Dict[str, Dict[str, Any]] = {}
        cheques_list: List[Dict[str, Any]] = []

        total_amount = Decimal("0.00")
        total_overdue = Decimal("0.00")
        total_current = Decimal("0.00")

        for chq in qs:
            rem_amount = chq.remaining_functional or chq.functional_amount or chq.amount or Decimal("0.00")
            due = chq.due_date or chq.issue_date
            days_overdue = (as_of_date - due).days if due else 0
            is_overdue = days_overdue > 0

            bracket = cls.get_aging_bracket(days_overdue)
            b_key = bracket["key"]

            bracket_totals[b_key]["amount"] += rem_amount
            bracket_totals[b_key]["count"] += 1

            total_amount += rem_amount
            if is_overdue:
                total_overdue += rem_amount
            else:
                total_current += rem_amount

            # تجميع الشريك
            p_name = chq.partner_name or str(_("غير محدد"))
            if p_name not in partners_data:
                partners_data[p_name] = {
                    "partner_name": p_name,
                    "cheques_count": 0,
                    "total_amount": Decimal("0.00"),
                    "current": Decimal("0.00"),
                    "overdue_1_30": Decimal("0.00"),
                    "overdue_31_60": Decimal("0.00"),
                    "overdue_61_90": Decimal("0.00"),
                    "overdue_91_plus": Decimal("0.00"),
                }

            partners_data[p_name]["cheques_count"] += 1
            partners_data[p_name]["total_amount"] += rem_amount

            if not is_overdue:
                partners_data[p_name]["current"] += rem_amount
            elif 1 <= days_overdue <= 30:
                partners_data[p_name]["overdue_1_30"] += rem_amount
            elif 31 <= days_overdue <= 60:
                partners_data[p_name]["overdue_31_60"] += rem_amount
            elif 61 <= days_overdue <= 90:
                partners_data[p_name]["overdue_61_90"] += rem_amount
            else:
                partners_data[p_name]["overdue_91_plus"] += rem_amount

            # تفصيل الشيك
            cheques_list.append({
                "cheque": chq,
                "id": chq.id,
                "voucher_number": chq.voucher_number,
                "cheque_number": chq.cheque_number,
                "partner_name": p_name,
                "issue_date": chq.issue_date,
                "due_date": chq.due_date,
                "days_overdue": days_overdue,
                "is_overdue": is_overdue,
                "bracket_key": b_key,
                "bracket_label": bracket["label"],
                "amount": chq.amount,
                "remaining_amount": rem_amount,
                "currency_code": chq.currency.code if chq.currency else "EGP",
                "status_display": chq.get_status_display(),
                "bank_name": chq.deposit_bank_account.name if chq.deposit_bank_account else (chq.bank_name or "-"),
            })

        # فرز الشركاء بالأكثر مديونية
        sorted_partners = sorted(partners_data.values(), key=lambda x: x["total_amount"], reverse=True)
        # فرز الشيكات بالأكثر تأخيراً
        sorted_cheques = sorted(cheques_list, key=lambda x: x["days_overdue"], reverse=True)

        overdue_ratio = (total_overdue / total_amount * Decimal("100.00")).quantize(Decimal("0.1")) if total_amount > 0 else Decimal("0.0")

        return {
            "as_of_date": as_of_date,
            "cheque_type": cheque_type,
            "cheque_type_display": dict(ChequeType.choices).get(cheque_type, cheque_type),
            "total_cheques_count": len(cheques_list),
            "total_amount": total_amount,
            "total_overdue": total_overdue,
            "total_current": total_current,
            "overdue_ratio": overdue_ratio,
            "bracket_totals": bracket_totals,
            "partners_summary": sorted_partners,
            "cheques_list": sorted_cheques,
        }
