"""
Django management command to simulate realistic biometric attendance
محاكاة واقعية لحركات البصمة لجميع الموظفين
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from datetime import datetime, timedelta, time
import random
from decimal import Decimal

from hr.models import (
    Employee, Shift, BiometricDevice, BiometricLog, 
    BiometricUserMapping, Attendance
)


class Command(BaseCommand):
    help = 'Simulate realistic biometric attendance for all employees'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=5,
            help='Number of days to simulate (default: 5)'
        )
        parser.add_argument(
            '--date',
            type=str,
            help='Start date (YYYY-MM-DD format)'
        )
    
    def handle(self, *args, **options):
        days = options['days']
        start_date_str = options.get('date')
        
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        else:
            # Start from first day of current month
            today = timezone.now().date()
            start_date = today.replace(day=1)
            # Calculate days from start of month to today
            days = (today - start_date).days + 1
        
        self.stdout.write(self.style.SUCCESS(
            f'\n🚀 بدء محاكاة البصمة لمدة {days} أيام من {start_date}\n'
        ))
        
        # Setup
        device = self.get_or_create_device()
        shifts = self.get_or_create_shifts()
        employees = self.get_active_employees()
        
        if not employees:
            self.stdout.write(self.style.ERROR('❌ لا يوجد موظفين نشطين'))
            return
        
        self.stdout.write(f'📊 عدد الموظفين: {len(employees)}')
        self.stdout.write(f'⏰ عدد الورديات: {len(shifts)}\n')
        
        # Assign shifts to employees
        self.assign_shifts_to_employees(employees, shifts)
        
        # Simulate attendance
        total_logs = 0
        for day_offset in range(days):
            current_date = start_date + timedelta(days=day_offset)
            
            # Skip Fridays (weekend)
            if current_date.weekday() == 4:
                self.stdout.write(f'⏭️  {current_date} (جمعة - عطلة)')
                continue
            
            self.stdout.write(f'\n📅 {current_date.strftime("%Y-%m-%d (%A)")}')
            self.stdout.write('─' * 60)
            
            day_logs = self.simulate_day_attendance(
                device, employees, current_date
            )
            total_logs += day_logs
            
            self.stdout.write(f'✅ تم تسجيل {day_logs} بصمة')
        
        self.stdout.write(self.style.SUCCESS(
            f'\n\n🎉 اكتمل! إجمالي البصمات: {total_logs}'
        ))
        self.print_summary(start_date, days)

    
    def get_or_create_device(self):
        """Get or create biometric device"""
        device, created = BiometricDevice.objects.get_or_create(
            device_code='SIM-001',
            defaults={
                'device_name': 'Main Office Simulator',
                'device_type': 'fingerprint',
                'serial_number': 'SIM-2024-001',
                'ip_address': '192.168.1.100',
                'port': 4370,
                'location': 'Main Entrance',
                'status': 'active',
                'is_active': True,
                'created_by_id': 1
            }
        )
        
        if created:
            self.stdout.write('✨ تم إنشاء جهاز بصمة محاكي')
        
        return device
    
    def get_or_create_shifts(self):
        """Get or create work shifts"""
        shifts_data = [
            {
                'name': 'الوردية الصباحية',
                'shift_type': 'morning',
                'start_time': time(8, 0),
                'end_time': time(16, 0),
                'work_hours': Decimal('8.00'),
                'grace_period_in': 15,
                'grace_period_out': 15,
            },
            {
                'name': 'الوردية المسائية',
                'shift_type': 'evening',
                'start_time': time(14, 0),
                'end_time': time(22, 0),
                'work_hours': Decimal('8.00'),
                'grace_period_in': 15,
                'grace_period_out': 15,
            },
            {
                'name': 'الوردية الليلية',
                'shift_type': 'night',
                'start_time': time(22, 0),
                'end_time': time(6, 0),
                'work_hours': Decimal('8.00'),
                'grace_period_in': 15,
                'grace_period_out': 15,
            },
        ]
        
        shifts = []
        for shift_data in shifts_data:
            shift, created = Shift.objects.get_or_create(
                name=shift_data['name'],
                defaults=shift_data
            )
            shifts.append(shift)
            
            if created:
                self.stdout.write(f'✨ تم إنشاء وردية: {shift.name}')
        
        return shifts
    
    def get_active_employees(self):
        """Get all active employees"""
        return list(Employee.objects.filter(status='active'))
    
    def assign_shifts_to_employees(self, employees, shifts):
        """Assign shifts to employees randomly"""
        for employee in employees:
            if not hasattr(employee, 'shift') or not employee.shift:
                # Assign random shift (80% morning, 15% evening, 5% night)
                rand = random.random()
                if rand < 0.80:
                    shift = shifts[0]  # Morning
                elif rand < 0.95:
                    shift = shifts[1]  # Evening
                else:
                    shift = shifts[2]  # Night
                
                employee.shift = shift
                employee.save(update_fields=['shift'])

    
    def simulate_day_attendance(self, device, employees, date):
        """Simulate attendance for one day"""
        logs_created = 0
        
        for employee in employees:
            # Get or create biometric mapping
            mapping, _ = BiometricUserMapping.objects.get_or_create(
                employee=employee,
                defaults={
                    'biometric_user_id': employee.employee_number,
                    'device': device,
                    'is_active': True
                }
            )
            
            # Determine attendance scenario
            scenario = self.get_attendance_scenario()
            
            if scenario == 'absent':
                # Employee is absent - no logs
                self.stdout.write(f'  ❌ {employee.name[:30]:30} - غائب')
                continue
            
            shift = employee.shift
            if not shift:
                continue
            
            # Generate check-in time
            check_in_time = self.generate_check_in_time(
                date, shift, scenario
            )
            
            # Create check-in log
            check_in_log = self.create_biometric_log(
                device=device,
                user_id=mapping.biometric_user_id,
                timestamp=check_in_time,
                log_type='check_in',
                employee=employee
            )
            
            if check_in_log:
                logs_created += 1
            
            # Generate check-out time (if not half_day)
            if scenario != 'half_day':
                check_out_time = self.generate_check_out_time(
                    date, shift, scenario, check_in_time
                )
                
                # Create check-out log
                check_out_log = self.create_biometric_log(
                    device=device,
                    user_id=mapping.biometric_user_id,
                    timestamp=check_out_time,
                    log_type='check_out',
                    employee=employee
                )
                
                if check_out_log:
                    logs_created += 1
            
            # Print status
            status_icon = self.get_status_icon(scenario)
            late_info = self.get_late_info(check_in_time, shift)
            self.stdout.write(
                f'  {status_icon} {employee.name[:30]:30} - '
                f'{check_in_time.strftime("%H:%M")} {late_info}'
            )
        
        return logs_created

    
    def get_attendance_scenario(self):
        """
        Determine attendance scenario with realistic probabilities
        
        Scenarios:
        - on_time: 60% - حضور في الوقت
        - late: 25% - تأخير
        - early: 5% - حضور مبكر
        - overtime: 5% - عمل إضافي
        - half_day: 3% - نصف يوم
        - absent: 2% - غياب
        """
        rand = random.random()
        
        if rand < 0.60:
            return 'on_time'
        elif rand < 0.85:
            return 'late'
        elif rand < 0.90:
            return 'early'
        elif rand < 0.95:
            return 'overtime'
        elif rand < 0.98:
            return 'half_day'
        else:
            return 'absent'
    
    def generate_check_in_time(self, date, shift, scenario):
        """Generate realistic check-in time"""
        base_time = datetime.combine(date, shift.start_time)
        
        if scenario == 'on_time':
            # Within grace period (-5 to +10 minutes)
            delta = random.randint(-5, 10)
        elif scenario == 'late':
            # Late (15 to 60 minutes)
            delta = random.randint(15, 60)
        elif scenario == 'early':
            # Early (10 to 30 minutes before)
            delta = random.randint(-30, -10)
        elif scenario == 'overtime':
            # Normal time
            delta = random.randint(-5, 5)
        elif scenario == 'half_day':
            # Late arrival for half day
            delta = random.randint(120, 240)
        else:
            delta = 0
        
        check_in = base_time + timedelta(minutes=delta)
        return timezone.make_aware(check_in)
    
    def generate_check_out_time(self, date, shift, scenario, check_in_time):
        """Generate realistic check-out time"""
        base_time = datetime.combine(date, shift.end_time)
        
        # Handle night shift (crosses midnight)
        if shift.end_time < shift.start_time:
            base_time += timedelta(days=1)
        
        if scenario == 'on_time':
            # Normal time (-10 to +10 minutes)
            delta = random.randint(-10, 10)
        elif scenario == 'late':
            # Normal checkout
            delta = random.randint(-5, 10)
        elif scenario == 'early':
            # Early checkout (leave early 10-30 min)
            delta = random.randint(-30, -10)
        elif scenario == 'overtime':
            # Overtime (1 to 3 hours extra)
            delta = random.randint(60, 180)
        else:
            delta = 0
        
        check_out = base_time + timedelta(minutes=delta)
        
        # Make timezone-aware
        check_out = timezone.make_aware(check_out) if timezone.is_naive(check_out) else check_out
        
        # Ensure check-out is after check-in
        if check_out <= check_in_time:
            check_out = check_in_time + timedelta(hours=4)
        
        return check_out

    
    def create_biometric_log(self, device, user_id, timestamp, log_type, employee):
        """Create biometric log entry"""
        try:
            log, created = BiometricLog.objects.get_or_create(
                device=device,
                user_id=user_id,
                timestamp=timestamp,
                defaults={
                    'log_type': log_type,
                    'employee': employee,
                    'is_processed': False,
                    'raw_data': {
                        'user_id': user_id,
                        'timestamp': timestamp.isoformat(),
                        'punch': 0 if log_type == 'check_in' else 1,
                        'simulated': True
                    }
                }
            )
            return log if created else None
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error creating log: {e}'))
            return None
    
    def get_status_icon(self, scenario):
        """Get emoji icon for scenario"""
        icons = {
            'on_time': '✅',
            'late': '⏰',
            'early': '🌅',
            'overtime': '💪',
            'half_day': '🕐',
            'absent': '❌'
        }
        return icons.get(scenario, '❓')
    
    def get_late_info(self, check_in_time, shift):
        """Get late information string"""
        shift_start = datetime.combine(
            check_in_time.date(), 
            shift.start_time
        )
        shift_start = timezone.make_aware(shift_start)
        
        if check_in_time > shift_start:
            delta = check_in_time - shift_start
            minutes = int(delta.total_seconds() / 60)
            if minutes > shift.grace_period_in:
                return f'(متأخر {minutes} دقيقة)'
        
        return ''
    
    def print_summary(self, start_date, days):
        """Print summary statistics"""
        end_date = start_date + timedelta(days=days)
        
        total_logs = BiometricLog.objects.filter(
            timestamp__date__gte=start_date,
            timestamp__date__lt=end_date
        ).count()
        
        check_ins = BiometricLog.objects.filter(
            timestamp__date__gte=start_date,
            timestamp__date__lt=end_date,
            log_type='check_in'
        ).count()
        
        check_outs = BiometricLog.objects.filter(
            timestamp__date__gte=start_date,
            timestamp__date__lt=end_date,
            log_type='check_out'
        ).count()
        
        unique_employees = BiometricLog.objects.filter(
            timestamp__date__gte=start_date,
            timestamp__date__lt=end_date
        ).values('employee').distinct().count()
        
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('📊 ملخص المحاكاة'))
        self.stdout.write('=' * 60)
        self.stdout.write(f'📅 الفترة: {start_date} إلى {end_date}')
        self.stdout.write(f'👥 عدد الموظفين: {unique_employees}')
        self.stdout.write(f'📝 إجمالي البصمات: {total_logs}')
        self.stdout.write(f'  ├─ دخول: {check_ins}')
        self.stdout.write(f'  └─ خروج: {check_outs}')
        self.stdout.write('=' * 60)
        self.stdout.write('\n💡 لمعالجة البصمات وإنشاء سجلات الحضور:')
        self.stdout.write('   python manage.py process_biometric_logs')
        self.stdout.write('')
