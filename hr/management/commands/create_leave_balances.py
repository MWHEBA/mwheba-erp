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
            default=date.today().year,
            help='السنة المراد إنشاء أرصدة لها (افتراضي: السنة الحالية)'
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
        
        self.stdout.write(self.style.SUCCESS(f'\n{"="*60}'))
        self.stdout.write(self.style.SUCCESS(f'إنشاء أرصدة الإجازات - السنة: {year}'))
        self.stdout.write(self.style.SUCCESS(f'{"="*60}\n'))
        
        # جلب أنواع الإجازات النشطة
        leave_types = LeaveType.objects.filter(is_active=True)
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
                # حساب مدة الخدمة ونسبة الاستحقاق
                months_worked = LeaveAccrualService.calculate_months_worked(employee.hire_date)
                accrual_percentage = LeaveAccrualService.get_accrual_percentage(months_worked)
                
                employee_created = 0
                employee_updated = 0
                
                for leave_type in leave_types:
                    # التحقق من وجود رصيد
                    existing_balance = LeaveBalance.objects.filter(
                        employee=employee,
                        leave_type=leave_type,
                        year=year
                    ).first()
                    
                    if existing_balance and not overwrite:
                        skipped_count += 1
                        continue
                    
                    # حساب الأيام المستحقة
                    total_days = leave_type.max_days_per_year
                    accrued_days = int(total_days * accrual_percentage)
                    
                    if existing_balance and overwrite:
                        # تحديث الرصيد الموجود
                        existing_balance.total_days = total_days
                        existing_balance.accrued_days = accrued_days
                        existing_balance.remaining_days = accrued_days - existing_balance.used_days
                        existing_balance.accrual_start_date = employee.hire_date
                        existing_balance.last_accrual_date = date.today()
                        existing_balance.save()
                        employee_updated += 1
                        updated_count += 1
                    else:
                        # إنشاء رصيد جديد
                        LeaveBalance.objects.create(
                            employee=employee,
                            leave_type=leave_type,
                            year=year,
                            total_days=total_days,
                            accrued_days=accrued_days,
                            used_days=0,
                            remaining_days=accrued_days,
                            accrual_start_date=employee.hire_date,
                            last_accrual_date=date.today()
                        )
                        employee_created += 1
                        created_count += 1
                
                # عرض معلومات الموظف
                status_icon = '[OK]' if (employee_created + employee_updated) > 0 else '[--]'
                status_text = []
                if employee_created > 0:
                    status_text.append(f'{employee_created} جديد')
                if employee_updated > 0:
                    status_text.append(f'{employee_updated} محدث')
                
                self.stdout.write(
                    f'{status_icon} {employee.get_full_name_ar()} - '
                    f'{months_worked} شهر - '
                    f'{int(accrual_percentage*100)}% - '
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
        
        logger.info(
            f'تم إنشاء أرصدة الإجازات: {created_count} رصيد جديد، '
            f'{updated_count} محدث، {skipped_count} موجود مسبقاً'
        )
