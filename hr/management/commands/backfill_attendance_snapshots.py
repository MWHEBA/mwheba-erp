"""
Management command to backfill snapshots for already-approved attendance summaries.

Usage:
    python manage.py backfill_attendance_snapshots
    python manage.py backfill_attendance_snapshots --month 2024-01
    python manage.py backfill_attendance_snapshots --dry-run
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from hr.models import AttendanceSummary, Attendance, AttendancePenalty
from hr.utils.payroll_helpers import get_payroll_period
from core.models import SystemSetting
from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta
import json
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Backfill snapshots for already-approved attendance summaries'

    def add_arguments(self, parser):
        parser.add_argument(
            '--month',
            type=str,
            help='Specific month to process (YYYY-MM format)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without actually doing it',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force re-generation even if snapshot already exists',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        force = options.get('force', False)
        month_filter = options.get('month')

        self.stdout.write(self.style.WARNING('بدء عملية backfill للـ snapshots...'))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('وضع التجربة (Dry Run) - لن يتم حفظ أي تغييرات'))

        # Get approved summaries without snapshots
        summaries = AttendanceSummary.objects.filter(is_approved=True)
        
        if month_filter:
            from datetime import datetime
            try:
                month_date = datetime.strptime(month_filter, '%Y-%m').date()
                summaries = summaries.filter(month=month_date)
                self.stdout.write(f'تصفية حسب الشهر: {month_filter}')
            except ValueError:
                self.stdout.write(self.style.ERROR('صيغة الشهر غير صحيحة. استخدم YYYY-MM'))
                return

        if not force:
            # Only process summaries without snapshots
            summaries_to_process = []
            for summary in summaries:
                if not summary.calculation_details or \
                   'absence_snapshot' not in summary.calculation_details or \
                   'late_deduction_snapshot' not in summary.calculation_details:
                    summaries_to_process.append(summary)
            summaries = summaries_to_process
        else:
            summaries = list(summaries)

        total = len(summaries)
        
        if total == 0:
            self.stdout.write(self.style.SUCCESS('لا توجد ملخصات تحتاج backfill'))
            return

        self.stdout.write(f'عدد الملخصات المطلوب معالجتها: {total}')
        
        success_count = 0
        error_count = 0
        
        for idx, summary in enumerate(summaries, 1):
            try:
                self.stdout.write(
                    f'\n[{idx}/{total}] معالجة: {summary.employee.get_full_name_ar()} - '
                    f'{summary.month.strftime("%Y-%m")}'
                )
                
                if not dry_run:
                    with transaction.atomic():
                        self._generate_snapshot(summary)
                        summary.save()
                    self.stdout.write(self.style.SUCCESS('  تم بنجاح'))
                else:
                    self._generate_snapshot(summary)  # Just validate, don't save
                    self.stdout.write(self.style.SUCCESS('  سيتم المعالجة (dry-run)'))
                
                success_count += 1
                
            except Exception as e:
                error_count += 1
                self.stdout.write(self.style.ERROR(f'  خطأ: {str(e)}'))
                logger.exception(f"Error backfilling snapshot for summary {summary.id}")

        # Summary
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS(f'نجح: {success_count}'))
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f'فشل: {error_count}'))
        self.stdout.write('='*60)

    def _generate_snapshot(self, summary):
        """Generate snapshot for an attendance summary"""
        
        # Get payroll period
        start_date, end_date, _ = get_payroll_period(summary.month)
        
        # Get active contract
        contract = summary.employee.contracts.filter(
            status='active',
            start_date__lte=end_date
        ).order_by('-start_date').first()
        
        if not contract:
            raise ValueError(f'لا يوجد عقد نشط للموظف {summary.employee.get_full_name_ar()}')
        
        daily_salary = (Decimal(str(contract.basic_salary)) / Decimal('30')).quantize(
            Decimal('0.01'),
            rounding=ROUND_HALF_UP
        )
        
        # Initialize calculation_details if needed
        if not summary.calculation_details:
            summary.calculation_details = {}
        
        # Generate absence snapshot
        if summary.absent_days > 0:
            self._generate_absence_snapshot(summary, start_date, end_date, daily_salary)
        
        # Generate late deduction snapshot
        if summary.net_penalizable_minutes > 0:
            self._generate_late_snapshot(summary, daily_salary)

    def _generate_absence_snapshot(self, summary, start_date, end_date, daily_salary):
        """Generate absence snapshot"""
        
        # Get absent records
        absent_records = Attendance.objects.filter(
            employee=summary.employee,
            date__gte=start_date,
            date__lte=end_date,
            status='absent'
        )
        
        # Exclude weekly off days and official holidays
        from hr.services.attendance_service import AttendanceService
        off_days = SystemSetting.get_setting('hr_weekly_off_days', [4])
        if isinstance(off_days, str):
            off_days = json.loads(off_days)
        
        holidays = AttendanceService.get_official_holiday_dates(start_date, end_date)
        excl = set()
        cur = start_date
        while cur <= end_date:
            if cur.weekday() in off_days or cur in holidays:
                excl.add(cur)
            cur += timedelta(days=1)
        
        absent_records = absent_records.exclude(date__in=excl)
        
        # Exclude approved leave dates
        from hr.models import Leave
        approved_leave_dates = set()
        for lv in Leave.objects.filter(
            employee=summary.employee,
            status='approved',
            start_date__lte=end_date,
            end_date__gte=start_date
        ):
            cur = max(lv.start_date, start_date)
            while cur <= min(lv.end_date, end_date):
                approved_leave_dates.add(cur)
                cur += timedelta(days=1)
        
        if approved_leave_dates:
            absent_records = absent_records.exclude(date__in=approved_leave_dates)
        
        # Build snapshot
        absence_details = []
        total_deduction = Decimal('0')
        
        for record in absent_records:
            day_deduction = daily_salary * record.absence_multiplier
            total_deduction += day_deduction
            absence_details.append({
                'date': record.date.isoformat(),
                'multiplier': str(record.absence_multiplier),
                'deduction': str(day_deduction.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
            })
        
        summary.calculation_details['absence_snapshot'] = {
            'absent_days': len(absence_details),
            'daily_salary': str(daily_salary),
            'total_deduction': str(total_deduction.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
            'details': absence_details,
            'backfilled': True  # Mark as backfilled
        }
        
        self.stdout.write(f'  Absence snapshot: {len(absence_details)} days')

    def _generate_late_snapshot(self, summary, daily_salary):
        """Generate late deduction snapshot"""
        
        # Find applicable penalty
        penalty = AttendancePenalty.objects.filter(
            is_active=True,
            max_minutes__gte=summary.net_penalizable_minutes
        ).order_by('max_minutes').first()
        
        if not penalty:
            penalty = AttendancePenalty.objects.filter(
                is_active=True,
                max_minutes=0
            ).first()
        
        if penalty:
            late_deduction = (penalty.penalty_days * daily_salary).quantize(
                Decimal('0.01'),
                rounding=ROUND_HALF_UP
            )
            
            summary.calculation_details['late_deduction_snapshot'] = {
                'net_penalizable_minutes': summary.net_penalizable_minutes,
                'penalty_id': penalty.id,
                'penalty_name': penalty.name,
                'penalty_days': str(penalty.penalty_days),
                'penalty_max_minutes': penalty.max_minutes,
                'daily_salary': str(daily_salary),
                'total_deduction': str(late_deduction),
                'backfilled': True  # Mark as backfilled
            }
            
            self.stdout.write(f'  Late snapshot: {summary.net_penalizable_minutes} minutes')
