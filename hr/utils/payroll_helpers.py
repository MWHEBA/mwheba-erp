"""
Helper functions for flexible payroll cycle calculations.

Supports both standard (day 1) and flexible (e.g. day 26) payroll cycles.
All functions read `payroll_cycle_start_day` from SystemSetting at runtime.
"""
from datetime import date
from dateutil.relativedelta import relativedelta


def _get_start_day() -> int:
    """Read payroll cycle start day from SystemSetting (default: 1)."""
    from core.models import SystemSetting
    start_day = int(SystemSetting.get_setting('payroll_cycle_start_day', 1))
    if not (1 <= start_day <= 28):
        raise ValueError(f'payroll_cycle_start_day must be between 1 and 28, got {start_day}')
    return start_day


def get_payroll_period(reference_date: date):
    """
    Calculate the payroll period for a given reference month.

    Args:
        reference_date: First day of the target month (e.g. date(2024, 3, 1))

    Returns:
        tuple: (period_start, period_end, payment_date)

    Examples:
        >>> # start_day = 1  (standard)
        >>> get_payroll_period(date(2024, 3, 1))
        (date(2024, 3, 1), date(2024, 3, 31), date(2024, 4, 1))

        >>> # start_day = 26
        >>> get_payroll_period(date(2024, 3, 1))
        (date(2024, 2, 26), date(2024, 3, 25), date(2024, 3, 26))
    """
    start_day = _get_start_day()

    if start_day == 1:
        # Standard: full calendar month
        period_start = reference_date.replace(day=1)
        period_end = (period_start + relativedelta(months=1)) - relativedelta(days=1)
        payment_date = period_start + relativedelta(months=1)
        return period_start, period_end, payment_date

    # Flexible cycle:
    # period_start = start_day of the PREVIOUS month
    # period_end   = (start_day - 1) of the CURRENT month
    prev_month = reference_date - relativedelta(months=1)
    period_start = prev_month.replace(day=start_day)
    period_end = reference_date.replace(day=start_day - 1)
    payment_date = reference_date.replace(day=start_day)
    return period_start, period_end, payment_date


def get_payroll_month_for_date(attendance_date: date) -> date:
    """
    Determine the payroll month (month field) for a given attendance/event date.

    Args:
        attendance_date: The date of the attendance record or event.

    Returns:
        date: First day of the payroll month that owns this date.

    Examples:
        >>> # start_day = 1
        >>> get_payroll_month_for_date(date(2024, 3, 15))
        date(2024, 3, 1)

        >>> # start_day = 26
        >>> get_payroll_month_for_date(date(2024, 2, 28))
        date(2024, 3, 1)   # 28 Feb belongs to March payroll

        >>> get_payroll_month_for_date(date(2024, 3, 10))
        date(2024, 3, 1)   # 10 Mar belongs to March payroll

        >>> get_payroll_month_for_date(date(2024, 3, 26))
        date(2024, 4, 1)   # 26 Mar belongs to April payroll
    """
    start_day = _get_start_day()

    if start_day == 1:
        return attendance_date.replace(day=1)

    # day >= start_day → belongs to NEXT month's payroll
    if attendance_date.day >= start_day:
        next_month = attendance_date + relativedelta(months=1)
        return next_month.replace(day=1)
    else:
        # day < start_day → belongs to CURRENT month's payroll
        return attendance_date.replace(day=1)


def calculate_cycle_days(period_start: date, period_end: date) -> int:
    """Return the number of days in a payroll cycle (inclusive)."""
    return (period_end - period_start).days + 1
