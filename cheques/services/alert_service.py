# -*- coding: utf-8 -*-
import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional
from datetime import date, timedelta

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


class ChequeAlertService:
    """
    خدمة التنبيهات وإشعارات استحقاق الشيكات
    (Cheque Due Alert & Maturity Notification Service)
    ترصد الشيكات المستحقة اليوم، وخلال الفترات القادمة، والشيكات المتأخرة لتنبيه الإدارة المالية وأمناء الخزائن.
    """

    ACTIVE_RECEIVABLE_STATUSES = [
        ChequeStatus.IN_PORTFOLIO,
        ChequeStatus.UNDER_COLLECTION,
        ChequeStatus.PARTIALLY_COLLECTED,
    ]

    ACTIVE_PAYABLE_STATUSES = [
        ChequeStatus.ISSUED,
    ]

    @classmethod
    def get_due_alerts_summary(cls) -> Dict[str, Any]:
        """
        ملخص إحصائيات التنبيهات المالية السريعة للـ Dashboard والشاشات
        """
        today = timezone.localdate()
        next_week = today + timedelta(days=7)

        # 1. شيكات تستحق اليوم
        today_qs = Cheque.objects.filter(
            due_date=today,
            status__in=cls.ACTIVE_RECEIVABLE_STATUSES + cls.ACTIVE_PAYABLE_STATUSES,
        ).exclude(purpose=ChequePurpose.SECURITY_GUARANTEE)

        today_rec = today_qs.filter(cheque_type=ChequeType.RECEIVABLE).aggregate(
            total=models.Sum("remaining_functional"), count=models.Count("id")
        )
        today_pay = today_qs.filter(cheque_type=ChequeType.PAYABLE).aggregate(
            total=models.Sum("remaining_functional"), count=models.Count("id")
        )

        # 2. شيكات تستحق خلال 7 أيام قادمة (تلي اليوم وحتى أسبوع)
        week_qs = Cheque.objects.filter(
            due_date__gt=today,
            due_date__lte=next_week,
            status__in=cls.ACTIVE_RECEIVABLE_STATUSES + cls.ACTIVE_PAYABLE_STATUSES,
        ).exclude(purpose=ChequePurpose.SECURITY_GUARANTEE)

        week_rec = week_qs.filter(cheque_type=ChequeType.RECEIVABLE).aggregate(
            total=models.Sum("remaining_functional"), count=models.Count("id")
        )
        week_pay = week_qs.filter(cheque_type=ChequeType.PAYABLE).aggregate(
            total=models.Sum("remaining_functional"), count=models.Count("id")
        )

        # 3. شيكات متأخرة تجاوزت تاريخ الاستحقاق
        overdue_qs = Cheque.objects.filter(
            due_date__lt=today,
            status__in=cls.ACTIVE_RECEIVABLE_STATUSES + cls.ACTIVE_PAYABLE_STATUSES,
        ).exclude(purpose=ChequePurpose.SECURITY_GUARANTEE)

        overdue_rec = overdue_qs.filter(cheque_type=ChequeType.RECEIVABLE).aggregate(
            total=models.Sum("remaining_functional"), count=models.Count("id")
        )
        overdue_pay = overdue_qs.filter(cheque_type=ChequeType.PAYABLE).aggregate(
            total=models.Sum("remaining_functional"), count=models.Count("id")
        )

        # 4. شيكات مرتدة تحتاج متابعة
        bounced_qs = Cheque.objects.filter(
            status__in=[ChequeStatus.BOUNCED, ChequeStatus.ENDORSED_BOUNCED]
        ).exclude(purpose=ChequePurpose.SECURITY_GUARANTEE)

        bounced_stat = bounced_qs.aggregate(
            total=models.Sum("remaining_functional"), count=models.Count("id")
        )

        # 5. شيكات ضمان سارية
        guarantee_qs = Cheque.objects.filter(
            purpose=ChequePurpose.SECURITY_GUARANTEE
        ).exclude(status__in=[ChequeStatus.RETURNED_TO_DRAWER, ChequeStatus.CANCELLED])

        guarantee_stat = guarantee_qs.aggregate(
            total=models.Sum("functional_amount"), count=models.Count("id")
        )

        return {
            "today_rec_count": today_rec["count"] or 0,
            "today_rec_amount": today_rec["total"] or Decimal("0.00"),
            "today_pay_count": today_pay["count"] or 0,
            "today_pay_amount": today_pay["total"] or Decimal("0.00"),
            "week_rec_count": week_rec["count"] or 0,
            "week_rec_amount": week_rec["total"] or Decimal("0.00"),
            "week_pay_count": week_pay["count"] or 0,
            "week_pay_amount": week_pay["total"] or Decimal("0.00"),
            "overdue_rec_count": overdue_rec["count"] or 0,
            "overdue_rec_amount": overdue_rec["total"] or Decimal("0.00"),
            "overdue_pay_count": overdue_pay["count"] or 0,
            "overdue_pay_amount": overdue_pay["total"] or Decimal("0.00"),
            "bounced_count": bounced_stat["count"] or 0,
            "bounced_amount": bounced_stat["total"] or Decimal("0.00"),
            "guarantee_count": guarantee_stat["count"] or 0,
            "guarantee_amount": guarantee_stat["total"] or Decimal("0.00"),
            "total_action_needed_count": (
                (today_rec["count"] or 0) + (today_pay["count"] or 0) +
                (overdue_rec["count"] or 0) + (overdue_pay["count"] or 0) +
                (bounced_stat["count"] or 0)
            )
        }

    @classmethod
    def get_upcoming_due_report(
        cls,
        period_filter: str = "7",
        cheque_type: Optional[str] = None,
        bank_account_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        تقرير تفصيلي بالشيكات المستحقة والمتأخرة بحسب الفترة المختارة:
        - 'today': يستحق اليوم
        - '7': يستحق خلال 7 أيام (شاملاً اليوم)
        - '30': يستحق خلال 30 يوماً
        - 'overdue': متأخرات الاستحقاق السابقة
        - 'all_active': كافة الشيكات النشطة
        """
        today = timezone.localdate()
        qs = Cheque.objects.filter(
            status__in=cls.ACTIVE_RECEIVABLE_STATUSES + cls.ACTIVE_PAYABLE_STATUSES,
        ).exclude(purpose=ChequePurpose.SECURITY_GUARANTEE).select_related(
            "customer", "supplier", "currency", "deposit_bank_account"
        )

        if cheque_type:
            qs = qs.filter(cheque_type=cheque_type)

        if bank_account_id:
            qs = qs.filter(deposit_bank_account_id=bank_account_id)

        period_title = _("خلال 7 أيام")
        if period_filter == "today":
            qs = qs.filter(due_date=today)
            period_title = _("المستحقة اليوم")
        elif period_filter == "7":
            qs = qs.filter(due_date__gte=today, due_date__lte=today + timedelta(days=7))
            period_title = _("المستحقة خلال 7 أيام")
        elif period_filter == "30":
            qs = qs.filter(due_date__gte=today, due_date__lte=today + timedelta(days=30))
            period_title = _("المستحقة خلال 30 يوماً")
        elif period_filter == "overdue":
            qs = qs.filter(due_date__lt=today)
            period_title = _("الشيكات المتأخرة عن الاستحقاق")

        qs = qs.order_by("due_date", "id")

        total_amount = Decimal("0.00")
        cheques_items: List[Dict[str, Any]] = []

        for chq in qs:
            rem = chq.remaining_functional or chq.functional_amount or chq.amount or Decimal("0.00")
            total_amount += rem
            days_diff = (today - chq.due_date).days if chq.due_date else 0

            cheques_items.append({
                "cheque": chq,
                "id": chq.id,
                "voucher_number": chq.voucher_number,
                "cheque_number": chq.cheque_number,
                "cheque_type": chq.cheque_type,
                "cheque_type_display": chq.get_cheque_type_display(),
                "partner_name": chq.partner_name,
                "issue_date": chq.issue_date,
                "due_date": chq.due_date,
                "days_diff": days_diff,
                "is_overdue": days_diff > 0,
                "amount": chq.amount,
                "remaining_amount": rem,
                "currency_code": chq.currency.code if chq.currency else "EGP",
                "status": chq.status,
                "status_display": chq.get_status_display(),
                "bank_name": chq.deposit_bank_account.name if chq.deposit_bank_account else (chq.bank_name or "-"),
            })

        summary_stats = cls.get_due_alerts_summary()

        return {
            "period_filter": period_filter,
            "period_title": str(period_title),
            "cheque_type": cheque_type,
            "bank_account_id": bank_account_id,
            "total_count": len(cheques_items),
            "total_amount": total_amount,
            "cheques": cheques_items,
            "summary_stats": summary_stats,
        }
