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
        from django.core.exceptions import ValidationError
        # التحقق من إخلاء طرف الموظف من العهد والذمم المالية والعينية
        if not termination_data.get('force_override', False):
            clearance = EmployeeService.check_custody_clearance(employee)
            if not clearance['is_cleared']:
                raise ValidationError(f"لا يمكن إنهاء خدمة الموظف لوجود ذمم أو عهد معلقة: {clearance['status_text']}")

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

        # 1.1 فحص التسويات المقدمة قيد المراجعة والاعتماد
        under_review_settlements_qs = employee.custody_settlements.filter(status='submitted')
        under_review_amount = under_review_settlements_qs.aggregate(tot=Sum('total_settled_amount'))['tot'] or Decimal('0.00')
        net_unsettled_exposure = max(Decimal('0.00'), pending_cash_balance - under_review_amount)

        # 2. فحص صناديق وبطاقات العهد المسندة
        assigned_accounts_count = employee.assigned_custody_accounts.filter(is_active=True).count()

        # 3. فحص الأجهزة والعهد العينية (العهد غير المستردة أو المعلقة أو تحت التحقيق تعطل إخلاء الطرف)
        from hr.models.employee_asset_custody import AssetCustodyStatus
        resolved_statuses = [
            AssetCustodyStatus.RETURNED,
            AssetCustodyStatus.CONSUMED,
            AssetCustodyStatus.SCRAPPED,
        ]
        unresolved_assets_qs = employee.asset_custodies.exclude(status__in=resolved_statuses)
        unresolved_assets_count = unresolved_assets_qs.count()

        has_under_review = under_review_settlements_qs.exists()
        is_cleared = (
            pending_cash_balance == Decimal('0.00')
            and not has_under_review
            and assigned_accounts_count == 0
            and unresolved_assets_count == 0
        )

        if is_cleared:
            status_text = 'تم إخلاء الطرف بالكامل'
        elif has_under_review:
            status_text = 'معلق لوجود تسويات قيد المراجعة والاعتماد'
        else:
            status_text = 'معلق بانتظار تسوية واسترداد العهد'

        return {
            'is_cleared': is_cleared,
            'pending_cash_balance': pending_cash_balance,
            'under_review_amount': under_review_amount,
            'under_review_count': under_review_settlements_qs.count(),
            'net_unsettled_exposure': net_unsettled_exposure,
            'unsettled_advances_count': cash_advances_qs.count(),
            'assigned_accounts_count': assigned_accounts_count,
            'active_assets_count': unresolved_assets_count,
            'pending_assets_count': unresolved_assets_count,
            'active_assets': list(unresolved_assets_qs.values('item_name', 'serial_number', 'estimated_value')),
            'clearance_status_text': status_text,
            'status_text': status_text,
        }
