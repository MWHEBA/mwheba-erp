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
    def get_or_create_active_fiscal_year(cls) -> FiscalYear:
        """
        الحصول على السنة المالية النشطة المفتوحة أو إنشاؤها وتفعيل فتراتها تلقائياً للسنة التالية
        """
        active_fy = FiscalYear.objects.filter(status='open').first()
        if active_fy:
            return active_fy

        latest_fy = FiscalYear.objects.order_by('-end_date').first()
        if latest_fy:
            if latest_fy.status != 'closed':
                latest_fy.status = 'open'
                latest_fy.save()
                latest_fy.periods.filter(status='closed').update(status='open')
                return latest_fy

            next_start = latest_fy.end_date + timedelta(days=1)
            next_end = date(next_start.year, 12, 31)
            y_code = str(next_start.year)
            if FiscalYear.objects.filter(year_code=y_code).exists():
                import uuid
                y_code = f"FY{next_start.year}-{uuid.uuid4().hex[:4]}"

            return cls.create_fiscal_year_with_periods(
                year_code=y_code,
                name=f"السنة المالية {next_start.year}",
                start_date=next_start,
                end_date=next_end
            )

        today = timezone.now().date()
        start_d = date(today.year, 1, 1)
        end_d = date(today.year, 12, 31)
        return cls.create_fiscal_year_with_periods(
            year_code=str(today.year),
            name=f"السنة المالية {today.year}",
            start_date=start_d,
            end_date=end_d
        )

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

        # 1. أتمتة مزامنة أسعار الصرف الرسمية
        try:
            from financial.services.exchange_rate_sync_service import ExchangeRateSyncService
            ExchangeRateSyncService.sync_official_cbe_rates(user=user)
        except Exception as sync_err:
            logger.warning(f"ملاحظة أثناء مزامنة أسعار الصرف عند إغلاق الفترة {period.name}: {sync_err}")

        # 2. تشغيل واعتماد وترحيل تقييم أسعار الصرف غير المحققة (IAS 21) تلقائياً بالمسار المحوكم
        try:
            from financial.fx.services import FXCalculationService, FXValidationService, FXPostingService
            fx_run = FXCalculationService.calculate_and_create_run(period=period, user=user)
            FXValidationService.validate_run(fx_run, user=user)
            FXPostingService.post_run(fx_run, user=user)
        except Exception as fx_err:
            logger.warning(f"ملاحظة أثناء أتمتة تقييم العملات IAS 21 عند إغلاق الفترة {period.name}: {fx_err}")

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
        إعادة فتح فترة محاسبية مغلقة (مخولة للمدير المالي) مع ترحيل قيد التقييم العكسي
        """
        period = AccountingPeriod.objects.select_for_update().get(pk=period_id)

        if period.status != 'closed':
            logger.info(f"الفترة المحاسبية {period.name} ليست مغلقة.")
            return period

        # ترحيل القيد العكسي للتشغيلات المـرحلة سابقاً لتوثيق الحركة بسلامة في سجل التدقيق
        try:
            from financial.fx.models import FXRevaluationRun
            from financial.fx.services import FXReversalService
            posted_runs = FXRevaluationRun.objects.filter(period=period, status='POSTED')
            for run in posted_runs:
                FXReversalService.reverse_run(run, user=user, reason=f"إعادة فتح الفترة المحاسبية {period.name}")
        except Exception as rev_err:
            logger.warning(f"ملاحظة أثناء ترحيل القيد العكسي لتقييم العملات عند إعادة فتح الفترة: {rev_err}")

        period.status = 'open'
        period.closed_at = None
        period.closed_by = None
        period.save()

        logger.info(f"🔓 تم إعادة فتح الفترة المحاسبية: {period.name}")
        return period
