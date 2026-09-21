"""
Helper functions for flexible payroll cycle calculations, overtime policies,
weekly off days, and HR attendance system rules.

Supports:
- Flexible and standard payroll cycles.
- Weekly off days resolution with Shift / Department / SystemSetting fallback.
- Dynamic overtime settings and rates (regular, holiday, min minutes, max hours, late offset policy).
- Grace period calculation modes (partial deduction vs hard threshold).
- Missing check-out policies.
- Legal penalty caps.
"""
import json
from datetime import date
from decimal import Decimal
from typing import List, Tuple, Dict, Any, Optional
from dateutil.relativedelta import relativedelta


def _get_start_day() -> int:
    """Read payroll cycle start day from SystemSetting (default: 1)."""
    from core.models import SystemSetting
    start_day = int(SystemSetting.get_setting('payroll_cycle_start_day', 1))
    if not (1 <= start_day <= 28):
        raise ValueError(f'payroll_cycle_start_day must be between 1 and 28, got {start_day}')
    return start_day


def get_payroll_period(reference_date: date) -> Tuple[date, date, date]:
    """
    Calculate the payroll period for a given reference month.

    Args:
        reference_date: First day of the target month (e.g. date(2024, 3, 1))

    Returns:
        tuple: (period_start, period_end, payment_date)
    """
    start_day = _get_start_day()

    if start_day == 1:
        period_start = reference_date.replace(day=1)
        period_end = (period_start + relativedelta(months=1)) - relativedelta(days=1)
        payment_date = period_start + relativedelta(months=1)
        return period_start, period_end, payment_date

    prev_month = reference_date - relativedelta(months=1)
    period_start = prev_month.replace(day=start_day)
    period_end = reference_date.replace(day=start_day - 1)
    payment_date = reference_date.replace(day=start_day)
    return period_start, period_end, payment_date


def get_payroll_month_for_date(attendance_date: date) -> date:
    """
    Determine the payroll month (month field) for a given attendance/event date.
    """
    start_day = _get_start_day()

    if start_day == 1:
        return attendance_date.replace(day=1)

    if attendance_date.day >= start_day:
        next_month = attendance_date + relativedelta(months=1)
        return next_month.replace(day=1)
    else:
        return attendance_date.replace(day=1)


def calculate_cycle_days(period_start: date, period_end: date) -> int:
    """Return the number of days in a payroll cycle (inclusive)."""
    return (period_end - period_start).days + 1


def get_weekly_off_days(shift=None, department=None) -> List[int]:
    """
    الحصول على أيام الإجازة الأسبوعية (0=الاثنين, ..., 4=الجمعة, 5=السبت, 6=الأحد).
    الأولوية:
    1. إجازة الوردية المخصصة (shift.weekly_off_days)
    2. الإعداد العام للنظام (SystemSetting: hr_weekly_off_days - الافتراضي: [4] الجمعة)
    """
    if shift and getattr(shift, 'weekly_off_days', None):
        off = shift.weekly_off_days
        if isinstance(off, str):
            try:
                off = json.loads(off)
            except Exception:
                pass
        if isinstance(off, list) and len(off) > 0:
            return [int(d) for d in off]

    from core.models import SystemSetting
    val = SystemSetting.get_setting('hr_weekly_off_days', [4])
    if isinstance(val, str):
        try:
            val = json.loads(val)
        except Exception:
            val = [4]
    if isinstance(val, list):
        return [int(d) for d in val]
    return [4]


def get_overtime_settings() -> Dict[str, Any]:
    """
    قراءة إعدادات العمل الإضافي الديناميكية من SystemSetting.
    """
    from core.models import SystemSetting

    rate_regular = Decimal(str(SystemSetting.get_setting('hr_overtime_rate_regular', '1.5')))
    rate_holiday = Decimal(str(SystemSetting.get_setting('hr_overtime_rate_holiday', '2.0')))
    min_minutes = int(SystemSetting.get_setting('hr_overtime_min_minutes', 30))
    max_daily_hours = Decimal(str(SystemSetting.get_setting('hr_overtime_max_daily_hours', '4.0')))
    late_offset_policy = str(SystemSetting.get_setting('hr_overtime_late_offset_policy', 'independent'))
    late_offset_ratio = Decimal(str(SystemSetting.get_setting('hr_overtime_late_offset_ratio', '1.0')))

    return {
        'rate_regular': rate_regular,
        'rate_holiday': rate_holiday,
        'min_minutes': min_minutes,
        'max_daily_hours': max_daily_hours,
        'late_offset_policy': late_offset_policy,  # 'independent', 'offset_full', 'offset_ratio'
        'late_offset_ratio': late_offset_ratio,
    }


def get_penalty_cap_settings() -> Optional[int]:
    """
    قراءة السقف القانوني لخصومات التأخير الشهري (أيام).
    SystemSetting: hr_max_monthly_late_penalty_days (الافتراضي: 5 أيام أو None لو غير محدد).
    """
    from core.models import SystemSetting
    val = SystemSetting.get_setting('hr_max_monthly_late_penalty_days', None)
    if val is not None and str(val).strip() != '':
        try:
            return int(val)
        except (ValueError, TypeError):
            return None
    return None


def get_grace_period_mode() -> str:
    """
    قراءة فلسفة احتساب فترة السماح.
    - 'deduct_grace': خصم دقائق السماح واحتساب الزيادة فقط.
    - 'hard_threshold': فترة السماح حد فاصل؛ عند تجاوزها يُحسب كامل التأخير من أول دقيقة (الافتراضي).
    """
    from core.models import SystemSetting
    return str(SystemSetting.get_setting('hr_grace_period_mode', 'hard_threshold'))


def get_daily_wage_divisor(reference_date: Optional[date] = None) -> int:
    """
    قراءة قاسم الراتب اليومي (SystemSetting: hr_daily_wage_divisor).
    - '30': 30 يوم ثابت (الافتراضي).
    - 'calendar': عدد أيام الشهر الفعلي (28/29/30/31).
    - 'actual_working': عدد أيام العمل الصافية.
    """
    from core.models import SystemSetting
    mode = str(SystemSetting.get_setting('hr_daily_wage_divisor', '30'))

    if mode == 'calendar' and reference_date:
        import calendar
        return calendar.monthrange(reference_date.year, reference_date.month)[1]

    try:
        return int(mode)
    except ValueError:
        return 30


def get_missing_checkout_policy() -> str:
    """
    سياسة التعامل مع نسيان بصمة الانصراف:
    - 'notify_hr': تنبيه الـ HR والموظف للاعتماد اليدوي (الافتراضي).
    - 'count_regular_shift': احتساب ساعات الوردية الأساسية مع خصم جزاء نسيان البصمة.
    - 'zero_hours': عدم احتساب ساعات العمل لليوم لحين المراجعة اليدوية.
    """
    from core.models import SystemSetting
    return str(SystemSetting.get_setting('hr_missing_checkout_policy', 'notify_hr'))
