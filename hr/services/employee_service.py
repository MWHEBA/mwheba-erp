"""
خدمة إدارة الموظفين
"""
from django.db import transaction
from django.contrib.auth import get_user_model
from ..models import Employee, LeaveBalance, LeaveType

User = get_user_model()


class EmployeeService:
    """خدمة إدارة الموظفين"""
    
    @staticmethod
    @transaction.atomic
    def create_employee(data, created_by):
        """
        إنشاء موظف جديد
        
        Args:
            data: بيانات الموظف
            created_by: المستخدم الذي أنشأ السجل
        
        Returns:
            Employee: الموظف المنشأ
        """
        # إنشاء حساب مستخدم
        user = User.objects.create_user(
            username=data['employee_number'],
            email=data['work_email'],
            first_name=data['first_name_ar'],
            last_name=data['last_name_ar'],
        )
        
        # إنشاء ملف الموظف
        employee = Employee.objects.create(
            user=user,
            created_by=created_by,
            **data
        )
        
        # إنشاء أرصدة الإجازات
        EmployeeService._create_leave_balances(employee)
        
        return employee
    
    @staticmethod
    def _create_leave_balances(employee):
        """إنشاء أرصدة الإجازات للموظف الجديد"""
        from datetime import date
        current_year = date.today().year
        
        leave_types = LeaveType.objects.filter(is_active=True)
        for leave_type in leave_types:
            balance = LeaveBalance.objects.create(
                employee=employee,
                leave_type=leave_type,
                year=current_year,
                total_days=leave_type.max_days_per_year,
                accrued_days=0,  # يبدأ بصفر - سيستحق تدريجياً
                used_days=0,
                remaining_days=0,  # صفر في البداية
                accrual_start_date=employee.hire_date  # تاريخ بداية الاستحقاق
            )
            # حساب الاستحقاق الحالي (في حالة الموظف ليس جديد تماماً)
            balance.update_accrued_days()
    
    @staticmethod
    @transaction.atomic
    def update_employee(employee, data, updated_by):
        """تحديث بيانات الموظف"""
        for key, value in data.items():
            setattr(employee, key, value)
        employee.save()
        
        return employee
    
    @staticmethod
    @transaction.atomic
    def terminate_employee(employee, termination_data, terminated_by):
        """
        إنهاء خدمة موظف
        
        Args:
            employee: الموظف
            termination_data: بيانات إنهاء الخدمة
            terminated_by: المستخدم الذي أنهى الخدمة
        """
        # تحديث حالة الموظف
        employee.status = 'terminated'
        employee.termination_date = termination_data['termination_date']
        employee.termination_reason = termination_data['reason']
        employee.save()
        
        # تعطيل حساب المستخدم
        employee.user.is_active = False
        employee.user.save()
        
        return employee
    
    @staticmethod
    def get_employee_summary(employee):
        """الحصول على ملخص شامل للموظف"""
        from datetime import date
        current_year = date.today().year
        current_month = date.today().replace(day=1)
        
        return {
            'personal_info': {
                'name': employee.get_full_name_ar(),
                'employee_number': employee.employee_number,
                'department': employee.department.name_ar,
                'job_title': employee.job_title.title_ar,
                'hire_date': employee.hire_date,
                'years_of_service': employee.years_of_service,
            },
            'leave_balances': LeaveBalance.objects.filter(
                employee=employee,
                year=current_year
            ),
        }
