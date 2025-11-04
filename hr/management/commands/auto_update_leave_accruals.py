"""
أمر تحديث تلقائي لأرصدة الإجازات
يُشغل يومياً عبر Cron Job أو Task Scheduler
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from datetime import date
from hr.models import Employee, LeaveBalance
from hr.services.leave_accrual_service import LeaveAccrualService
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'تحديث تلقائي لأرصدة الإجازات بناءً على مدة الخدمة'

    def add_arguments(self, parser):
        parser.add_argument(
            '--year',
            type=int,
            default=date.today().year,
            help='السنة المراد تحديث أرصدتها (افتراضي: السنة الحالية)'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='تحديث جميع الموظفين حتى لو لم يتغير شيء'
        )
        parser.add_argument(
            '--check-milestones',
            action='store_true',
            help='التحقق من الموظفين الذين وصلوا لـ 3 أو 6 شهور اليوم'
        )

    def handle(self, *args, **options):
        year = options['year']
        force = options['force']
        check_milestones = options['check_milestones']
        
        self.stdout.write(self.style.SUCCESS(f'\n{"="*60}'))
        self.stdout.write(self.style.SUCCESS(f'تحديث أرصدة الإجازات - السنة: {year}'))
        self.stdout.write(self.style.SUCCESS(f'{"="*60}\n'))
        
        if check_milestones:
            self._check_milestones(year)
        else:
            self._update_all_accruals(year, force)
    
    def _check_milestones(self, year):
        """
        التحقق من الموظفين الذين وصلوا لـ milestones (حسب الإعدادات)
        وتحديث أرصدتهم فقط
        """
        from core.models import SystemSetting
        
        # جلب الإعدادات
        probation_months = SystemSetting.get_setting('leave_accrual_probation_months', 3)
        partial_percentage = SystemSetting.get_setting('leave_accrual_partial_percentage', 25)
        full_months = SystemSetting.get_setting('leave_accrual_full_months', 6)
        
        today = date.today()
        employees = Employee.objects.filter(status='active')
        
        updated_count = 0
        milestone_employees = []
        
        for employee in employees:
            months_worked = LeaveAccrualService.calculate_months_worked(
                employee.hire_date, today
            )
            
            # التحقق من الوصول لـ milestone اليوم (حسب الإعدادات)
            if months_worked == probation_months or months_worked == full_months:
                # تحديث الأرصدة
                result = LeaveAccrualService.update_employee_accrual(employee, year)
                
                if result['updated_count'] > 0:
                    updated_count += 1
                    if months_worked == probation_months:
                        milestone_type = f"{probation_months} شهور ({partial_percentage}%)"
                    else:
                        milestone_type = f"{full_months} شهور (100%)"
                    
                    milestone_employees.append({
                        'name': employee.get_full_name_ar(),
                        'milestone': milestone_type,
                        'hire_date': employee.hire_date
                    })
                    
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✓ {employee.get_full_name_ar()} - وصل لـ {milestone_type}'
                        )
                    )
        
        # الملخص
        self.stdout.write(self.style.SUCCESS(f'\n{"="*60}'))
        self.stdout.write(self.style.SUCCESS(f'الملخص:'))
        self.stdout.write(self.style.SUCCESS(f'  - عدد الموظفين الذين وصلوا لـ milestone: {updated_count}'))
        self.stdout.write(self.style.SUCCESS(f'{"="*60}\n'))
    
    def _update_all_accruals(self, year, force):
        """تحديث جميع الأرصدة"""
        employees = Employee.objects.filter(status='active')
        total_employees = employees.count()
        
        self.stdout.write(f'عدد الموظفين النشطين: {total_employees}\n')
        
        updated_count = 0
        employees_with_changes = []
        
        with transaction.atomic():
            for employee in employees:
                months_worked = LeaveAccrualService.calculate_months_worked(employee.hire_date)
                old_percentage = LeaveAccrualService.get_accrual_percentage(months_worked)
                
                # تحديث الأرصدة
                result = LeaveAccrualService.update_employee_accrual(employee, year)
                
                if result['updated_count'] > 0 or force:
                    updated_count += 1
                    employees_with_changes.append({
                        'name': result['employee'],
                        'months_worked': months_worked,
                        'percentage': f"{int(old_percentage * 100)}%",
                        'updates': result['updated_count']
                    })
                    
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✓ {result["employee"]} - '
                            f'{months_worked} شهر - '
                            f'{int(old_percentage * 100)}% - '
                            f'{result["updated_count"]} رصيد محدث'
                        )
                    )
        
        # الملخص النهائي
        self.stdout.write(self.style.SUCCESS(f'\n{"="*60}'))
        self.stdout.write(self.style.SUCCESS(f'الملخص النهائي:'))
        self.stdout.write(self.style.SUCCESS(f'  - إجمالي الموظفين: {total_employees}'))
        self.stdout.write(self.style.SUCCESS(f'  - الموظفين المحدثين: {updated_count}'))
        self.stdout.write(self.style.SUCCESS(f'{"="*60}\n'))
        
        logger.info(
            f'تم تحديث أرصدة الإجازات: {updated_count} من {total_employees} موظف'
        )
