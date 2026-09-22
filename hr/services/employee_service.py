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
        name_parts = data.get('name', '').split(maxsplit=1) if data.get('name') else ['', '']
        user = User.objects.create_user(
            username=data['employee_number'],
            email=data['work_email'],
            first_name=name_parts[0] if len(name_parts) > 0 else '',
            last_name=name_parts[1] if len(name_parts) > 1 else '',
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
        from .leave_accrual_service import LeaveAccrualService

        current_year = date.today().year
        leave_types  = LeaveType.objects.filter(is_active=True, category__in=['annual', 'emergency'])

        for leave_type in leave_types:
            # single source of truth لحساب total_days
            total_days = LeaveAccrualService.get_entitlement_for_employee(employee, leave_type)

            LeaveBalance.objects.create(
                employee=employee,
                leave_type=leave_type,
                year=current_year,
                total_days=total_days,
                accrued_days=total_days,
                used_days=0,
                remaining_days=total_days,
                accrual_start_date=employee.hire_date,
            )
    
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
    def reinstate_employee(employee, reinstated_by):
        """
        إعادة الموظف للخدمة بعد إنهائها
        
        Args:
            employee: الموظف
            reinstated_by: المستخدم الذي أعاد التفعيل
        """
        employee.status = 'active'
        employee.termination_date = None
        employee.termination_reason = ''
        employee.save()
        
        # إعادة تفعيل حساب المستخدم
        if employee.user and not employee.user.is_active:
            from users.services.user_management_service import UserManagementService
            UserManagementService.toggle_user_status(employee.user, current_user=reinstated_by, target_active=True)
        
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
        if employee.user and employee.user.is_active:
            from users.services.user_management_service import UserManagementService
            UserManagementService.toggle_user_status(employee.user, current_user=terminated_by, target_active=False)
        
        return employee
    
    @staticmethod
    def check_custody_clearance(employee):
        """
        فحص وتدقيق إخلاء طرف الموظف من العهد النقدية والعينية والأمانات
        """
        from decimal import Decimal
        from django.db.models import Sum

        # 1. فحص العهد النقدية
        cash_advances_qs = employee.custody_advances.filter(status__in=['active', 'partially_settled', 'overdue'])
        pending_cash_balance = cash_advances_qs.aggregate(tot=Sum('current_balance'))['tot'] or Decimal('0.00')

        # 2. فحص صناديق وبطاقات العهد المسندة
        assigned_accounts_count = employee.assigned_custody_accounts.filter(is_active=True).count()

        # 3. فحص الأجهزة والعهد العينية
        active_assets_qs = employee.asset_custodies.filter(status='active')
        active_assets_count = active_assets_qs.count()

        is_cleared = (pending_cash_balance == Decimal('0.00') and assigned_accounts_count == 0 and active_assets_count == 0)

        return {
            'is_cleared': is_cleared,
            'pending_cash_balance': pending_cash_balance,
            'unsettled_advances_count': cash_advances_qs.count(),
            'assigned_accounts_count': assigned_accounts_count,
            'active_assets_count': active_assets_count,
            'active_assets': list(active_assets_qs.values('item_name', 'serial_number', 'estimated_value')),
            'clearance_status_text': 'تم إخلاء الطرف بالكامل' if is_cleared else 'معلق بانتظار تسوية واسترداد العهد',
        }
