"""
أمر تشخيصي للتحقق من استقطاعات الرواتب
"""
from django.core.management.base import BaseCommand
from django.db.models import Q
from hr.models import Employee, Contract, ContractSalaryComponent, SalaryComponent
from datetime import date


class Command(BaseCommand):
    help = 'تشخيص مشكلة استقطاعات الرواتب'

    def add_arguments(self, parser):
        parser.add_argument(
            '--employee-id',
            type=int,
            help='معرف الموظف للتحقق منه'
        )

    def handle(self, *args, **options):
        employee_id = options.get('employee_id')
        
        if employee_id:
            employees = Employee.objects.filter(id=employee_id)
        else:
            # جميع الموظفين النشطين
            employees = Employee.objects.filter(status='active')
        
        self.stdout.write(self.style.SUCCESS(f'\n=== تشخيص استقطاعات الرواتب ===\n'))
        self.stdout.write(f'عدد الموظفين: {employees.count()}\n')
        
        for employee in employees:
            self.diagnose_employee(employee)
    
    def diagnose_employee(self, employee):
        """تشخيص موظف واحد"""
        self.stdout.write(self.style.WARNING(f'\n--- الموظف: {employee.get_full_name_ar()} (#{employee.employee_number}) ---'))
        
        # 1. العقد النشط
        active_contract = employee.contracts.filter(status='active').first()
        if not active_contract:
            self.stdout.write(self.style.ERROR('  ❌ لا يوجد عقد نشط'))
            return
        
        self.stdout.write(self.style.SUCCESS(f'  ✓ العقد النشط: {active_contract.contract_number}'))
        
        # 2. بنود العقد (ContractSalaryComponent)
        contract_components = ContractSalaryComponent.objects.filter(contract=active_contract)
        contract_deductions = contract_components.filter(component_type='deduction')
        
        self.stdout.write(f'\n  بنود العقد (ContractSalaryComponent):')
        self.stdout.write(f'    - إجمالي: {contract_components.count()}')
        self.stdout.write(f'    - مستحقات: {contract_components.filter(component_type="earning").count()}')
        self.stdout.write(f'    - استقطاعات: {contract_deductions.count()}')
        
        if contract_deductions.exists():
            self.stdout.write(f'\n  تفاصيل الاستقطاعات في العقد:')
            for comp in contract_deductions:
                self.stdout.write(f'    • {comp.name} ({comp.code}): {comp.amount} ج.م')
        else:
            self.stdout.write(self.style.ERROR('    ⚠️  لا توجد استقطاعات في بنود العقد!'))
        
        # 3. بنود الموظف (SalaryComponent)
        today = date.today()
        employee_components = SalaryComponent.objects.filter(
            employee=employee,
            is_active=True
        ).filter(
            Q(effective_from__isnull=True) | Q(effective_from__lte=today)
        ).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gte=today)
        )
        
        employee_deductions = employee_components.filter(component_type='deduction')
        
        self.stdout.write(f'\n  بنود الموظف النشطة (SalaryComponent):')
        self.stdout.write(f'    - إجمالي: {employee_components.count()}')
        self.stdout.write(f'    - مستحقات: {employee_components.filter(component_type="earning").count()}')
        self.stdout.write(f'    - استقطاعات: {employee_deductions.count()}')
        
        if employee_deductions.exists():
            self.stdout.write(f'\n  تفاصيل الاستقطاعات النشطة:')
            for comp in employee_deductions:
                status = '✓' if comp.is_active else '✗'
                dates = f'من {comp.effective_from or "غير محدد"} إلى {comp.effective_to or "غير محدد"}'
                self.stdout.write(f'    {status} {comp.name} ({comp.code}): {comp.amount} ج.م - {dates}')
        else:
            self.stdout.write(self.style.ERROR('    ⚠️  لا توجد استقطاعات نشطة للموظف!'))
        
        # 4. التحقق من التطابق
        if contract_deductions.exists() and not employee_deductions.exists():
            self.stdout.write(self.style.ERROR('\n  ❌ مشكلة: الاستقطاعات موجودة في العقد لكن غير منسوخة للموظف!'))
            self.stdout.write('     الحل: أعد تفعيل العقد أو انسخ البنود يدوياً')
        elif contract_deductions.count() != employee_deductions.count():
            self.stdout.write(self.style.WARNING(f'\n  ⚠️  تحذير: عدد الاستقطاعات غير متطابق'))
            self.stdout.write(f'     في العقد: {contract_deductions.count()}')
            self.stdout.write(f'     للموظف: {employee_deductions.count()}')
        else:
            self.stdout.write(self.style.SUCCESS('\n  ✓ الاستقطاعات متطابقة'))
