# -*- coding: utf-8 -*-
"""
FIN-SAL-CMD-002: generate_morning_radar_snapshot
أمر إدارة وتشغيل لقطة الرادار الصباحية (Celery / Cron في تمام 6:00 صباحاً)
يولد ويسجل لقطة سريعة في نموذج CollectionRadarSnapshot لضمان فتح رادار التحصيل في أقل من 5ms
"""
from decimal import Decimal
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Sum, Q

from sale.models.installments import (
    InstallmentItem,
    InstallmentCashStatus,
    PaperCoverage,
    CollectionRadarSnapshot,
)
from cheques.models.cheque import Cheque
from financial.models.cost_center import CostCenter


class Command(BaseCommand):
    help = "توليد لقطة مؤشرات رادار التحصيل الصباحية لتسريع استجابة لوحة المتابعة"

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=str,
            help="تاريخ اللقطة المراد احتسابها بتنسيق YYYY-MM-DD (الافتراضي: اليوم)",
        )

    def handle(self, *args, **options):
        date_str = options.get("date")
        if date_str:
            target_date = timezone.datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            target_date = timezone.localdate()

        self.stdout.write(f"بدء احتساب لقطة رادار التحصيل لتاريخ: {target_date}")

        # 1. توليد اللقطة الإجمالية العامة (Global Snapshot: cost_center=None)
        global_snapshot = self._compute_and_save_snapshot(target_date, cost_center=None)
        self.stdout.write(
            self.style.SUCCESS(
                f"[✓] تم حفظ اللقطة العامة: متأخرات مكشوفة={global_snapshot.total_uncovered_overdue:,.2f} ج.م، "
                f"شيكات بالبنوك={global_snapshot.total_cheques_under_collection:,.2f} ج.م، "
                f"تدفق 30 يوم={global_snapshot.expected_cashflow_30d:,.2f} ج.م"
            )
        )

        # 2. توليد لقطة مخصصة لكل مركز تكلفة نشط (Regional / Cost Center Isolation)
        active_ccs = CostCenter.objects.filter(is_active=True)
        cc_count = 0
        for cc in active_ccs:
            self._compute_and_save_snapshot(target_date, cost_center=cc)
            cc_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"اكتملت مهمة لقطة الرادار بنجاح. تم تحديث اللقطة العامة و {cc_count} مركز تكلفة."
            )
        )

    def _compute_and_save_snapshot(self, target_date, cost_center=None) -> CollectionRadarSnapshot:
        """احتساب وحفظ مؤشرات اللقطة لمركز تكلفة محدد أو للعام"""
        items_qs = InstallmentItem.objects.select_related('plan', 'plan__sale').all()
        cheques_qs = Cheque.objects.filter(cheque_type="RECEIVABLE")

        if cost_center:
            items_qs = items_qs.filter(plan__sale__cost_center=cost_center)
            cheques_qs = cheques_qs.filter(cost_center=cost_center)

        # 1. أقساط مكشوفة متأخرة تجاوزت فترة السماح (Overdue Uncovered)
        overdue_uncovered = Decimal("0.00")
        for it in items_qs:
            if it.paper_coverage == PaperCoverage.UNCOVERED:
                grace_end = it.due_date + timedelta(days=it.grace_period_days or 0)
                if target_date > grace_end and it.remaining_balance > Decimal("0.00"):
                    if it.cash_status not in [InstallmentCashStatus.COLLECTED, InstallmentCashStatus.WAIVED, InstallmentCashStatus.HOLD_REWORK]:
                        overdue_uncovered += it.remaining_balance

        # 2. شيكات بالبنوك برسم التحصيل (Under Collection)
        under_collection = cheques_qs.filter(
            status="BANK_DEPOSITED"
        ).aggregate(total=Sum('amount'))['total'] or Decimal("0.00")

        # 3. مستحق اليوم (Due Today)
        due_today_items = sum(
            it.remaining_balance for it in items_qs
            if it.due_date == target_date and it.remaining_balance > Decimal("0.00")
            and it.cash_status not in [InstallmentCashStatus.COLLECTED, InstallmentCashStatus.WAIVED]
        )

        # 4. التدفق النقدي المتوقع 30 يوماً (Conservative 30-Day Cash Flow)
        # يستبعد صراحةً الأقساط المعلقة HOLD_REWORK والشيكات المرتدة BOUNCED والنزاع القضائي LEGAL_ACTION
        date_30d = target_date + timedelta(days=30)
        expected_30d = Decimal("0.00")
        for it in items_qs:
            if target_date <= it.due_date <= date_30d:
                if it.cash_status in [InstallmentCashStatus.HOLD_REWORK, InstallmentCashStatus.LEGAL_ACTION, InstallmentCashStatus.BOUNCED, InstallmentCashStatus.WAIVED, InstallmentCashStatus.COLLECTED]:
                    continue
                expected_30d += it.remaining_balance

        # حفظ أو تحديث اللقطة
        snapshot, _ = CollectionRadarSnapshot.objects.update_or_create(
            snapshot_date=target_date,
            cost_center=cost_center,
            defaults={
                "total_uncovered_overdue": overdue_uncovered,
                "total_cheques_under_collection": under_collection,
                "total_due_today": due_today_items,
                "expected_cashflow_30d": expected_30d,
                "metrics_payload": {
                    "calculated_at": timezone.now().isoformat(),
                    "uncovered_overdue": str(overdue_uncovered),
                    "under_collection": str(under_collection),
                    "due_today": str(due_today_items),
                    "expected_30d": str(expected_30d),
                }
            }
        )

        return snapshot
