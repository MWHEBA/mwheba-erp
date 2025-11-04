"""
أمر لتحديث الاستحقاق التدريجي لأرصدة الإجازات
يُنفذ يومياً أو أسبوعياً عبر Cron Job
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from hr.services.leave_accrual_service import LeaveAccrualService


class Command(BaseCommand):
    help = 'تحديث الاستحقاق التدريجي لأرصدة الإجازات لجميع الموظفين النشطين'

    def add_arguments(self, parser):
        parser.add_argument(
            '--year',
            type=int,
            help='السنة المراد تحديث أرصدتها (افتراضي: السنة الحالية)',
        )
        parser.add_argument(
            '--employee-id',
            type=int,
            help='معرف موظف محدد (اختياري - لتحديث موظف واحد فقط)',
        )

    def handle(self, *args, **options):
        year = options.get('year')
        employee_id = options.get('employee_id')
        
        self.stdout.write(self.style.SUCCESS('🔄 بدء تحديث أرصدة الإجازات...'))
        self.stdout.write(f'⏰ الوقت: {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}')
        
        if employee_id:
            # تحديث موظف محدد
            from hr.models import Employee
            try:
                employee = Employee.objects.get(pk=employee_id)
                result = LeaveAccrualService.update_employee_accrual(employee, year)
                
                self.stdout.write(self.style.SUCCESS(f'\n✅ تم تحديث أرصدة: {result["employee"]}'))
                self.stdout.write(f'   عدد الأرصدة المحدثة: {result["updated_count"]}')
                
                if result['summary']:
                    self.stdout.write('\n   التفاصيل:')
                    for item in result['summary']:
                        self.stdout.write(
                            f'   • {item["leave_type"]}: '
                            f'{item["old_accrued"]} → {item["new_accrued"]} يوم '
                            f'(متبقي: {item["remaining"]})'
                        )
                else:
                    self.stdout.write('   لا توجد تحديثات مطلوبة')
                    
            except Employee.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'❌ الموظف #{employee_id} غير موجود'))
                return
        else:
            # تحديث جميع الموظفين
            result = LeaveAccrualService.update_all_accruals(year)
            
            self.stdout.write(self.style.SUCCESS(f'\n✅ اكتمل التحديث بنجاح!'))
            self.stdout.write(f'   السنة: {result["year"]}')
            self.stdout.write(f'   إجمالي الموظفين: {result["total_employees"]}')
            self.stdout.write(f'   الموظفين المحدثين: {result["employees_with_updates"]}')
            self.stdout.write(f'   إجمالي الأرصدة المحدثة: {result["total_balances_updated"]}')
            
            if result['details'] and self.verbosity >= 2:
                self.stdout.write('\n📋 التفاصيل:')
                for emp_result in result['details']:
                    self.stdout.write(f'\n   {emp_result["employee"]}:')
                    for item in emp_result['summary']:
                        self.stdout.write(
                            f'     • {item["leave_type"]}: '
                            f'{item["old_accrued"]} → {item["new_accrued"]} يوم '
                            f'(متبقي: {item["remaining"]})'
                        )
        
        self.stdout.write(self.style.SUCCESS('\n✨ تم الانتهاء من التحديث'))
