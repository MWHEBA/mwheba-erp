# -*- coding: utf-8 -*-
"""
Evaluate Installment Dues Command - أمر التقييم اليومي لاستحقاقات ورادار الأقساط
مسؤول عن:
1. فحص مواعيد استحقاق الأقساط ومراعاة فترات السماح والعطلات المصرفية (Next Business Day).
2. تحويل الأقساط المتجاوزة لفترة السماح إلى OVERDUE.
3. احتساب غرامات التأخير اليومية على أصل الدين غير المسدد فقط (طبقاً للمادة 232 مدني مصري).
4. تفعيل حظر الصرف المخزني للتعثر (delivery_blocked_on_overdue).
"""
import logging
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from sale.models.installments import InstallmentPlan, InstallmentItem
from sale.services.installment_engine import InstallmentEngine

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "تقييم استحقاقات الأقساط اليومية، تحديث المتأخرات، واحتساب غرامات التأخير المشروعة"

    def handle(self, *args, **options):
        today = timezone.now().date()
        self.stdout.write(self.style.NOTICE(f"بدء تقييم استحقاقات الأقساط لتاريخ: {today}"))

        # جلب الأقساط المعلقة أو المسددة جزئياً والتي لم تقفل بعد
        active_items = InstallmentItem.objects.filter(
            cash_status__in=[
                InstallmentItem.CashStatus.PENDING,
                InstallmentItem.CashStatus.PARTIALLY_PAID,
                InstallmentItem.CashStatus.OVERDUE,
            ]
        ).select_related('plan__sale', 'plan__customer')

        overdue_count = 0
        penalties_updated = 0

        for item in active_items:
            # تخطي الأقساط المعلقة لنزاع تشغيلي أو المعفاة
            if item.cash_status in [
                InstallmentItem.CashStatus.HOLD_REWORK,
                InstallmentItem.CashStatus.WAIVED,
                InstallmentItem.CashStatus.TRANSIT_DAMAGE_CLAIM,
            ]:
                continue

            due_date = item.due_date
            adjusted_due_date = InstallmentEngine.adjust_for_banking_calendar(due_date)
            grace_days = item.grace_period_days or 3
            grace_end_date = adjusted_due_date + timezone.timedelta(days=grace_days)

            # إذا انقضت فترة السماح
            if today > grace_end_date and item.remaining_balance > Decimal('0.00'):
                if item.cash_status != InstallmentItem.CashStatus.OVERDUE:
                    item.cash_status = InstallmentItem.CashStatus.OVERDUE
                    item.save(update_fields=['cash_status'])
                    overdue_count += 1

                # تفعيل حظر الصرف المخزني على الفاتورة
                sale = item.plan.sale
                if not sale.delivery_blocked_on_overdue:
                    sale.delivery_blocked_on_overdue = True
                    sale.save(update_fields=['delivery_blocked_on_overdue'])

                # احتساب وتحديث غرامة التأخير المشروعة على أصل الدين فقط
                penalty = InstallmentEngine.calculate_article_232_penalty(item, current_date=today)
                if penalty != item.penalty_amount:
                    item.penalty_amount = penalty
                    item.save(update_fields=['penalty_amount'])
                    penalties_updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"✅ اكتمل التقييم: تم تحويل {overdue_count} قسط إلى متأخر (OVERDUE)، وتحديث غرامات {penalties_updated} قسط."
            )
        )
