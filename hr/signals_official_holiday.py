"""
Signals الإجازات الرسمية

عند إضافة/تعديل إجازة رسمية:
  - حذف سجلات absent و present/late في أيام الإجازة
  - إلغاء اعتماد الملخصات المتأثرة

عند حذف/تعطيل إجازة رسمية:
  - إعادة إنشاء سجلات الغياب للأيام دي
  - إلغاء اعتماد الملخصات المتأثرة
"""
import logging
from datetime import date, timedelta
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _get_date_range(start_date, end_date):
    """يرجع list بجميع التواريخ من start_date إلى end_date شاملاً"""
    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current)
        current += timedelta(days=1)
    return dates


def _sync_holiday_attendance(holiday):
    """
    مزامنة سجلات الحضور مع الإجازة الرسمية.
    يُستدعى عند الإضافة أو التعديل.
    """
    from .models import Attendance, AttendanceSummary

    if not holiday.is_active:
        _restore_attendance_for_deleted_holiday(holiday)
        return

    holiday_dates = _get_date_range(holiday.start_date, holiday.end_date)

    try:
        # 1. حذف سجلات absent في أيام الإجازة
        absent_deleted, _ = Attendance.objects.filter(
            date__in=holiday_dates,
            status='absent'
        ).delete()

        # 2. حذف سجلات present/late (تجاهل البصمة — القرار المحسوم)
        #    لا نحذف on_leave — الموظف اللي عنده إجازة شخصية يفضل سجله
        present_deleted, _ = Attendance.objects.filter(
            date__in=holiday_dates,
            status__in=['present', 'late', 'half_day']
        ).delete()

        logger.info(
            f"OfficialHoliday '{holiday.name}': "
            f"حذف {absent_deleted} غياب + {present_deleted} حضور"
        )

        # 3. إلغاء اعتماد الملخصات المتأثرة
        affected_months = set(d.replace(day=1) for d in holiday_dates)
        updated = AttendanceSummary.objects.filter(
            month__in=affected_months,
            is_approved=True
        ).update(is_approved=False, approved_by=None, approved_at=None)

        if updated:
            logger.info(
                f"OfficialHoliday '{holiday.name}': "
                f"إلغاء اعتماد {updated} ملخص حضور"
            )

    except Exception as e:
        logger.error(f"خطأ في _sync_holiday_attendance للإجازة '{holiday.name}': {e}", exc_info=True)


def _restore_attendance_for_deleted_holiday(holiday):
    """
    إعادة إنشاء سجلات الغياب عند حذف أو تعطيل إجازة رسمية.
    """
    from .models import AttendanceSummary
    from .services.attendance_service import AttendanceService
    from core.models import SystemSetting
    import json

    try:
        holiday_dates = _get_date_range(holiday.start_date, holiday.end_date)

        # استثناء الإجازات الأسبوعية
        weekly_off = SystemSetting.get_setting('hr_weekly_off_days', [4])
        if isinstance(weekly_off, str):
            try:
                weekly_off = json.loads(weekly_off)
            except Exception:
                weekly_off = [4]

        # استثناء إجازات رسمية أخرى نشطة تغطي نفس الأيام
        from .models import OfficialHoliday
        other_holidays = OfficialHoliday.objects.filter(
            is_active=True,
            start_date__lte=holiday.end_date,
            end_date__gte=holiday.start_date
        ).exclude(pk=holiday.pk)

        other_holiday_dates = set()
        for h in other_holidays:
            other_holiday_dates.update(_get_date_range(h.start_date, h.end_date))

        today = date.today()
        dates_to_restore = [
            d for d in holiday_dates
            if d.weekday() not in weekly_off
            and d not in other_holiday_dates
            and d <= today
        ]

        if not dates_to_restore:
            return

        # إعادة إنشاء سجلات الغياب
        AttendanceService.generate_missing_attendances(
            min(dates_to_restore), max(dates_to_restore)
        )

        # إلغاء اعتماد الملخصات المتأثرة
        affected_months = set(d.replace(day=1) for d in dates_to_restore)
        updated = AttendanceSummary.objects.filter(
            month__in=affected_months,
            is_approved=True
        ).update(is_approved=False, approved_by=None, approved_at=None)

        logger.info(
            f"OfficialHoliday '{holiday.name}' (محذوفة/معطلة): "
            f"إعادة إنشاء غياب لـ {len(dates_to_restore)} يوم، "
            f"إلغاء اعتماد {updated} ملخص"
        )

    except Exception as e:
        logger.error(
            f"خطأ في _restore_attendance_for_deleted_holiday للإجازة '{holiday.name}': {e}",
            exc_info=True
        )


@receiver(post_save, sender='hr.OfficialHoliday')
def on_official_holiday_saved(sender, instance, **kwargs):
    """Signal عند حفظ إجازة رسمية (إضافة أو تعديل)"""
    _sync_holiday_attendance(instance)


@receiver(post_delete, sender='hr.OfficialHoliday')
def on_official_holiday_deleted(sender, instance, **kwargs):
    """Signal عند حذف إجازة رسمية"""
    _restore_attendance_for_deleted_holiday(instance)
