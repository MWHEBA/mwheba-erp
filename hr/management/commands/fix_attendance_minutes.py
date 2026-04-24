"""
إصلاح دقائق التأخير والانصراف المبكر في سجلات الحضور القديمة.

المشكلة: كان calculate_work_hours() يعمل self.save() قبل حساب early_leave_minutes،
فكانت قيمة early_leave_minutes تتحفظ كـ 0 حتى لو الموظف انصرف مبكراً.

الحل: إعادة حساب late_minutes و early_leave_minutes لكل سجلات الحضور
التي عندها check_in أو check_out.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from hr.models import Attendance
from hr.services.attendance_service import AttendanceService


class Command(BaseCommand):
    help = 'إصلاح دقائق التأخير والانصراف المبكر في سجلات الحضور القديمة'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='عرض الإحصائيات فقط بدون تعديل'
        )
        parser.add_argument(
            '--date-from',
            type=str,
            help='من تاريخ (YYYY-MM-DD)'
        )
        parser.add_argument(
            '--date-to',
            type=str,
            help='إلى تاريخ (YYYY-MM-DD)'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        date_from = options.get('date_from')
        date_to = options.get('date_to')

        # جلب السجلات المتضررة: عندها check_in وعندها shift
        qs = Attendance.objects.filter(
            check_in__isnull=False,
            shift__isnull=False,
        ).select_related('employee', 'shift')

        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)

        total = qs.count()
        self.stdout.write(f'إجمالي السجلات: {total}')

        if dry_run:
            # حساب كم سجل عنده early_leave_minutes = 0 بس المفروض يكون > 0
            affected = qs.filter(check_out__isnull=False, early_leave_minutes=0).count()
            self.stdout.write(f'سجلات مشكوك فيها (check_out موجود و early_leave=0): {affected}')
            self.stdout.write(self.style.WARNING('dry-run: لم يتم أي تعديل'))
            return

        fixed = 0
        errors = 0

        for attendance in qs.iterator(chunk_size=200):
            try:
                with transaction.atomic():
                    changed = False

                    # إعادة حساب late_minutes
                    new_late = AttendanceService._calculate_late_minutes(
                        attendance.check_in, attendance.shift, attendance.date
                    )
                    if new_late != attendance.late_minutes:
                        attendance.late_minutes = new_late
                        changed = True

                    # إعادة حساب early_leave_minutes لو في check_out
                    if attendance.check_out:
                        new_early = AttendanceService._calculate_early_leave(
                            attendance.check_out, attendance.shift, attendance.date
                        )
                        if new_early != attendance.early_leave_minutes:
                            attendance.early_leave_minutes = new_early
                            changed = True

                    if changed:
                        attendance.save(update_fields=['late_minutes', 'early_leave_minutes'])
                        fixed += 1

            except Exception as e:
                errors += 1
                self.stderr.write(
                    f'خطأ في سجل {attendance.pk} ({attendance.employee} - {attendance.date}): {e}'
                )

        self.stdout.write(self.style.SUCCESS(f'تم إصلاح: {fixed} سجل'))
        if errors:
            self.stdout.write(self.style.ERROR(f'أخطاء: {errors} سجل'))
