"""
إعادة تعيين الوردية الحالية للموظفين على سجلات الحضور من تاريخ معين.

الاستخدام:
    # معاينة بدون تعديل (dry-run)
    python manage.py reassign_shift_from_date --date-from 2025-02-01 --dry-run

    # تنفيذ فعلي لكل الموظفين من فبراير 2025
    python manage.py reassign_shift_from_date --date-from 2025-02-01

    # موظف معين فقط
    python manage.py reassign_shift_from_date --date-from 2025-02-01 --employee-id 42
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.timezone import now

from hr.models import Attendance, Employee
from hr.services.attendance_service import AttendanceService


class Command(BaseCommand):
    help = 'إعادة تعيين الوردية الحالية للموظفين على سجلات الحضور من تاريخ معين وإعادة حساب التأخيرات'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date-from',
            type=str,
            required=True,
            help='من تاريخ (YYYY-MM-DD) - مطلوب'
        )
        parser.add_argument(
            '--date-to',
            type=str,
            default=None,
            help='إلى تاريخ (YYYY-MM-DD) - افتراضي: اليوم'
        )
        parser.add_argument(
            '--employee-id',
            type=int,
            default=None,
            help='معالجة موظف واحد فقط (اختياري)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='عرض ما سيتغير بدون تنفيذ فعلي'
        )

    def handle(self, *args, **options):
        date_from = options['date_from']
        date_to = options['date_to'] or now().date().isoformat()
        dry_run = options['dry_run']
        employee_id = options.get('employee_id')

        self.stdout.write(f'📅 الفترة: من {date_from} إلى {date_to}')
        if dry_run:
            self.stdout.write(self.style.WARNING('⚠️  وضع المعاينة (dry-run) - لن يتم أي تعديل'))

        # جلب الموظفين المستهدفين (لازم عندهم وردية حالية)
        employees_qs = Employee.objects.filter(
            status='active',
            shift__isnull=False
        ).select_related('shift')

        if employee_id:
            employees_qs = employees_qs.filter(pk=employee_id)
            if not employees_qs.exists():
                raise CommandError(f'الموظف رقم {employee_id} غير موجود أو ليس لديه وردية')

        total_employees = employees_qs.count()
        self.stdout.write(f'👥 عدد الموظفين: {total_employees}')

        stats = {
            'employees_processed': 0,
            'records_updated': 0,
            'records_skipped': 0,
            'errors': 0,
        }

        for employee in employees_qs.iterator(chunk_size=50):
            new_shift = employee.shift

            # جلب سجلات الحضور للموظف في الفترة المحددة
            attendances = Attendance.objects.filter(
                employee=employee,
                date__gte=date_from,
                date__lte=date_to,
                check_in__isnull=False,
            ).select_related('shift')

            if not attendances.exists():
                continue

            employee_updated = 0
            employee_skipped = 0

            for attendance in attendances:
                # لو الوردية نفسها مش محتاج نعمل حاجة
                if attendance.shift_id == new_shift.pk:
                    employee_skipped += 1
                    continue

                if dry_run:
                    old_shift_name = attendance.shift.name if attendance.shift else 'بدون وردية'
                    self.stdout.write(
                        f'  [{attendance.date}] {employee.get_full_name_ar()}: '
                        f'{old_shift_name} → {new_shift.name}'
                    )
                    employee_updated += 1
                    continue

                try:
                    with transaction.atomic():
                        # إعادة حساب بالوردية الجديدة
                        new_late = AttendanceService._calculate_late_minutes(
                            attendance.check_in, new_shift, attendance.date
                        )
                        new_early = 0
                        if attendance.check_out:
                            new_early = AttendanceService._calculate_early_leave(
                                attendance.check_out, new_shift, attendance.date
                            )

                        # تحديد الحالة
                        new_status = 'late' if new_late > new_shift.grace_period_in else 'present'

                        # إعادة حساب ساعات العمل الإضافي
                        new_overtime = 0
                        if attendance.check_out and attendance.check_in:
                            delta = attendance.check_out - attendance.check_in
                            work_hours = round(delta.total_seconds() / 3600, 2)
                            shift_hours = new_shift.calculate_work_hours()
                            new_overtime = round(max(0.0, work_hours - shift_hours), 2)

                        attendance.shift = new_shift
                        attendance.late_minutes = new_late
                        attendance.early_leave_minutes = new_early
                        attendance.status = new_status
                        attendance.overtime_hours = new_overtime
                        attendance.save(update_fields=[
                            'shift', 'late_minutes', 'early_leave_minutes',
                            'status', 'overtime_hours'
                        ])
                        employee_updated += 1

                except Exception as e:
                    stats['errors'] += 1
                    self.stderr.write(
                        self.style.ERROR(
                            f'خطأ: {employee.get_full_name_ar()} - {attendance.date}: {e}'
                        )
                    )

            stats['records_updated'] += employee_updated
            stats['records_skipped'] += employee_skipped
            stats['employees_processed'] += 1

            if employee_updated > 0:
                action = 'سيتم تحديث' if dry_run else 'تم تحديث'
                self.stdout.write(
                    f'✅ {employee.get_full_name_ar()} ({new_shift.name}): '
                    f'{action} {employee_updated} سجل، تخطي {employee_skipped}'
                )

        # ملخص نهائي
        self.stdout.write('\n' + '=' * 50)
        self.stdout.write(f'👥 موظفين معالجين: {stats["employees_processed"]}')
        self.stdout.write(f'📝 سجلات {"ستتحدث" if dry_run else "تم تحديثها"}: {stats["records_updated"]}')
        self.stdout.write(f'⏭️  سجلات تم تخطيها (نفس الوردية): {stats["records_skipped"]}')
        if stats['errors']:
            self.stdout.write(self.style.ERROR(f'❌ أخطاء: {stats["errors"]}'))
        else:
            self.stdout.write(self.style.SUCCESS('✔️  انتهى بدون أخطاء'))
