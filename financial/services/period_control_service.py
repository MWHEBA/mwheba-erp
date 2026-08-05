import logging
from datetime import date, timedelta
from calendar import monthrange
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from financial.models.fiscal_year import FiscalYear
from financial.models.journal_entry import AccountingPeriod, JournalEntry
from financial.exceptions import FinancialCoreError, PeriodClosedError

logger = logging.getLogger("financial.period_control_service")


class PeriodControlService:
    """
    خدمة التحكم بالفترات المحاسبية والسنة المالية
    """

    @classmethod
    def validate_period_open(cls, target_date: date):
        """
        فحص هل التاريخ يقع ضمن فترة محاسبية مفتوحة
        """
        period = AccountingPeriod.objects.filter(
            start_date__lte=target_date,
            end_date__gte=target_date
        ).first()

        if not period:
            return False, None

        if period.status in ['closed', 'hard_closed']:
            return False, period

        return True, period

    @classmethod
    @transaction.atomic
    def create_fiscal_year_with_periods(
        cls,
        year_code: str,
        name: str,
        start_date: date,
        end_date: date
    ) -> FiscalYear:
        """
        إنشاء سنة مالية جديدة وتوليد 12 فترة محاسبية شهرية تلقائياً
        """
        fiscal_year = FiscalYear.objects.create(
            year_code=year_code,
            name=name,
            start_date=start_date,
            end_date=end_date,
            status='open'
        )

        curr_start = start_date
        for month_idx in range(1, 13):
            # حساب تاريخ نهاية الشهر
            _, last_day = monthrange(curr_start.year, curr_start.month)
            curr_end = date(curr_start.year, curr_start.month, last_day)

            if curr_end > end_date:
                curr_end = end_date

            period_name = f"{fiscal_year.name} - فترة {month_idx}"
            AccountingPeriod.objects.create(
                fiscal_year=fiscal_year,
                name=period_name,
                period_number=month_idx,
                start_date=curr_start,
                end_date=curr_end,
                status='open'
            )

            # الانتقال لليوم الأول من الشهر التالي
            if curr_end >= end_date:
                break
            curr_start = curr_end + timedelta(days=1)

        logger.info(f"✅ تم إنشاء السنة المالية {year_code} مع الفترات المحاسبية التابعة.")
        return fiscal_year

    @classmethod
    @transaction.atomic
    def close_period(cls, period_id: int, user=None, force: bool = False) -> AccountingPeriod:
        """
        إغلاق فترة محاسبية مع حماية القيود المسودة (Draft Guard)
        """
        period = AccountingPeriod.objects.select_for_update().get(pk=period_id)

        if period.status in ['closed', 'hard_closed']:
            logger.info(f"الفترة المحاسبية {period.name} مغلقة بالفعل.")
            return period

        # فحص وجود مسودات قيود غير منشورة في الفترة
        draft_entries = JournalEntry.objects.filter(
            accounting_period=period,
            status='draft'
        )

        if draft_entries.exists() and not force:
            draft_count = draft_entries.count()
            raise PeriodClosedError(
                f"لا يمكن إغلاق الفترة المحاسبية {period.name}: يوجد {draft_count} قيد مسودة غير مرحل."
            )

        period.status = 'closed'
        period.closed_at = timezone.now()
        period.closed_by = user
        period.save()

        logger.info(f"🔒 تم إغلاق الفترة المحاسبية: {period.name}")
        return period

    @classmethod
    @transaction.atomic
    def reopen_period(cls, period_id: int, user=None) -> AccountingPeriod:
        """
        إعادة فتح فترة محاسبية مغلقة (مخولة للمدير المالي)
        """
        period = AccountingPeriod.objects.select_for_update().get(pk=period_id)
        if period.status == 'hard_closed':
            raise PeriodClosedError(_("لا يمكن إعادة فتح فترة محاسبية مقفلة إقفالاً نهائياً."))

        period.status = 'open'
        period.save()

        logger.info(f"🔓 تم إعادة فتح الفترة المحاسبية: {period.name}")
        return period
