"""
أمر إنشاء أرصدة الإجازات للموظفين
ينشئ أرصدة لجميع الموظفين النشطين لسنة محددة
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from datetime import date
from hr.models import Employee, LeaveBalance, LeaveType
from hr.services.leave_accrual_service import LeaveAccrualService
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'إنشاء أرصدة الإجازات لجميع الموظفين النشطين'

    def add_arguments(self, parser):
        parser.add_argument(
            '--year',
            type=int,
            default=None,
            help='السنة المراد إنشاء أرصدة لها (افتراضي: السنة الجديدة من دورة الإجازات)'
        )
        parser.add_argument(
            '--employee-id',
            type=int,
            help='إنشاء أرصدة لموظف محدد فقط'
        )
        parser.add_argument(
            '--overwrite',
            action='store_true',
            help='حذف الأرصدة الموجودة وإعادة إنشائها'
        )

    def handle(self, *args, **options):
        year = options['year']
        employee_id = options.get('employee_id')
        overwrite = options['overwrite']

        # لو لم يُحدَّد year، استخدم السنة الجديدة من دورة الإجازات
        if year is None:
            from hr.services.leave_accrual_service import LeaveAccrualService
            year = LeaveAccrualService.get_new_cycle_year()
        
        self.stdout.write(self.style.SUCCESS(f'\n{"="*60}'))
        self.stdout.write(self.style.SUCCESS(f'إنشاء أرصدة الإجازات - السنة: {year}'))
        self.stdout.write(self.style.SUCCESS(f'{"="*60}\n'))
        
        # جلب أنواع الإجازات النشطة
        leave_types = LeaveType.objects.filter(is_active=True, category__in=['annual', 'emergency'])
        if not leave_types.exists():
            self.stdout.write(self.style.ERROR('[X] لا توجد أنواع إجازات نشطة في النظام!'))
            self.stdout.write(self.style.WARNING('يرجى إضافة أنواع الإجازات أولاً من لوحة الإدارة.'))
            return
        
        self.stdout.write(f'أنواع الإجازات المتاحة: {leave_types.count()}')
        for leave_type in leave_types:
            self.stdout.write(f'  - {leave_type.name_ar} ({leave_type.max_days_per_year} يوم)')
        
        # جلب الموظفين
        if employee_id:
            employees = Employee.objects.filter(pk=employee_id, status='active')
            if not employees.exists():
                self.stdout.write(self.style.ERROR(f'[X] الموظف #{employee_id} غير موجود أو غير نشط!'))
                return
        else:
            employees = Employee.objects.filter(status='active')
        
        total_employees = employees.count()
        self.stdout.write(f'\nعدد الموظفين النشطين: {total_employees}\n')
        
        if total_employees == 0:
            self.stdout.write(self.style.WARNING('[!] لا يوجد موظفين نشطين!'))
            return
        
        created_count = 0
        updated_count = 0
        skipped_count = 0
        
        with transaction.atomic():
            for employee in employees:
                months_worked = LeaveAccrualService.calculate_months_worked(employee.hire_date)

                employee_created = 0
                employee_updated = 0

                for leave_type in leave_types:
                    existing_balance = LeaveBalance.objects.filter(
                        employee=employee,
                        leave_type=leave_type,
                        year=year
                    ).first()

                    if existing_balance and not overwrite:
                        skipped_count += 1
                        continue

                    # single source of truth
                    total_days = LeaveAccrualService.get_entitlement_for_employee(employee, leave_type)

                    if existing_balance and overwrite:
                        existing_balance.total_days    = total_days
                        existing_balance.accrued_days  = total_days
                        existing_balance.remaining_days = max(0, total_days - existing_balance.used_days)
                        existing_balance.accrual_start_date = employee.hire_date
                        existing_balance.last_accrual_date  = date.today()
                        existing_balance.save()
                        employee_updated += 1
                        updated_count += 1
                    else:
                        LeaveBalance.objects.create(
                            employee=employee,
                            leave_type=leave_type,
                            year=year,
                            total_days=total_days,
                            accrued_days=total_days,
                            used_days=0,
                            remaining_days=total_days,
                            accrual_start_date=employee.hire_date,
                            last_accrual_date=date.today()
                        )
                        employee_created += 1
                        created_count += 1

                status_icon = '[OK]' if (employee_created + employee_updated) > 0 else '[--]'
                status_text = []
                if employee_created > 0:
                    status_text.append(f'{employee_created} جديد')
                if employee_updated > 0:
                    status_text.append(f'{employee_updated} محدث')

                self.stdout.write(
                    f'{status_icon} {employee.get_full_name_ar()} - '
                    f'{months_worked} شهر - '
                    f'{", ".join(status_text) if status_text else "موجود مسبقاً"}'
                )
        
        # الملخص النهائي
        self.stdout.write(self.style.SUCCESS(f'\n{"="*60}'))
        self.stdout.write(self.style.SUCCESS('الملخص النهائي:'))
        self.stdout.write(self.style.SUCCESS(f'  - إجمالي الموظفين: {total_employees}'))
        self.stdout.write(self.style.SUCCESS(f'  - أرصدة جديدة: {created_count}'))
        if overwrite:
            self.stdout.write(self.style.SUCCESS(f'  - أرصدة محدثة: {updated_count}'))
        if skipped_count > 0:
            self.stdout.write(self.style.WARNING(f'  - أرصدة موجودة (تم تخطيها): {skipped_count}'))
        self.stdout.write(self.style.SUCCESS(f'{"="*60}\n'))
        
