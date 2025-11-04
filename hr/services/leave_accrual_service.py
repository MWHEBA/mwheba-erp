"""
خدمة الاستحقاق التدريجي للإجازات
"""
from django.db import transaction
from datetime import date
from dateutil.relativedelta import relativedelta
from ..models import Employee, LeaveBalance, LeaveType


class LeaveAccrualService:
    """خدمة حساب وتحديث الاستحقاق التدريجي للإجازات"""
    
    @staticmethod
    def get_accrual_percentage(months_worked):
        """
        حساب نسبة الاستحقاق بناءً على أشهر العمل
        يستخدم الإعدادات من SystemSetting
        
        Args:
            months_worked: عدد الأشهر منذ التعيين
        
        Returns:
            float: نسبة الاستحقاق (0.0 إلى 1.0)
        """
        from core.models import SystemSetting
        
        # جلب الإعدادات (مع قيم افتراضية)
        probation_months = SystemSetting.get_setting('leave_accrual_probation_months', 3)
        partial_percentage = SystemSetting.get_setting('leave_accrual_partial_percentage', 25)
        full_months = SystemSetting.get_setting('leave_accrual_full_months', 6)
        
        if months_worked < probation_months:
            return 0.0  # لا يستحق شيء
        elif months_worked < full_months:
            return partial_percentage / 100.0  # يستحق النسبة الجزئية
        else:
            return 1.0  # يستحق الرصيد كاملاً
    
    @staticmethod
    def calculate_months_worked(hire_date, reference_date=None):
        """
        حساب عدد الأشهر منذ التعيين
        
        Args:
            hire_date: تاريخ التعيين
            reference_date: تاريخ المرجع (افتراضي: اليوم)
        
        Returns:
            int: عدد الأشهر
        """
        if reference_date is None:
            reference_date = date.today()
        
        delta = relativedelta(reference_date, hire_date)
        return delta.months + (delta.years * 12)
    
    @staticmethod
    @transaction.atomic
    def update_employee_accrual(employee, year=None):
        """
        تحديث استحقاق إجازات موظف محدد
        
        Args:
            employee: الموظف
            year: السنة (افتراضي: السنة الحالية)
        
        Returns:
            dict: ملخص التحديثات
        """
        if year is None:
            year = date.today().year
        
        # جلب جميع أرصدة الموظف للسنة المحددة
        balances = LeaveBalance.objects.filter(
            employee=employee,
            year=year
        )
        
        updated_count = 0
        summary = []
        
        for balance in balances:
            old_accrued = balance.accrued_days
            balance.update_accrued_days()
            
            if balance.accrued_days != old_accrued:
                updated_count += 1
                summary.append({
                    'leave_type': balance.leave_type.name_ar,
                    'old_accrued': old_accrued,
                    'new_accrued': balance.accrued_days,
                    'remaining': balance.remaining_days
                })
        
        return {
            'employee': employee.get_full_name_ar(),
            'updated_count': updated_count,
            'summary': summary
        }
    
    @staticmethod
    @transaction.atomic
    def update_all_accruals(year=None):
        """
        تحديث استحقاق جميع الموظفين النشطين
        
        Args:
            year: السنة (افتراضي: السنة الحالية)
        
        Returns:
            dict: ملخص شامل للتحديثات
        """
        if year is None:
            year = date.today().year
        
        employees = Employee.objects.filter(status='active')
        total_updated = 0
        employees_updated = []
        
        for employee in employees:
            result = LeaveAccrualService.update_employee_accrual(employee, year)
            if result['updated_count'] > 0:
                total_updated += result['updated_count']
                employees_updated.append(result)
        
        return {
            'year': year,
            'total_employees': employees.count(),
            'employees_with_updates': len(employees_updated),
            'total_balances_updated': total_updated,
            'details': employees_updated
        }
    
    @staticmethod
    def get_employee_accrual_status(employee, year=None):
        """
        الحصول على حالة استحقاق موظف
        
        Args:
            employee: الموظف
            year: السنة (افتراضي: السنة الحالية)
        
        Returns:
            dict: معلومات الاستحقاق
        """
        if year is None:
            year = date.today().year
        
        months_worked = LeaveAccrualService.calculate_months_worked(employee.hire_date)
        accrual_percentage = LeaveAccrualService.get_accrual_percentage(months_worked)
        
        balances = LeaveBalance.objects.filter(
            employee=employee,
            year=year
        ).select_related('leave_type')
        
        balances_info = []
        for balance in balances:
            balances_info.append({
                'leave_type': balance.leave_type.name_ar,
                'total_days': balance.total_days,
                'accrued_days': balance.accrued_days,
                'used_days': balance.used_days,
                'remaining_days': balance.remaining_days,
                'accrual_percentage': f"{int(accrual_percentage * 100)}%"
            })
        
        # جلب الإعدادات لتحديد المرحلة
        from core.models import SystemSetting
        probation_months = SystemSetting.get_setting('leave_accrual_probation_months', 3)
        partial_percentage = SystemSetting.get_setting('leave_accrual_partial_percentage', 25)
        full_months = SystemSetting.get_setting('leave_accrual_full_months', 6)
        
        # تحديد المرحلة
        if months_worked < probation_months:
            stage = "فترة تجريبية - لا يستحق إجازات بعد"
            next_milestone = f"سيستحق {partial_percentage}% من الرصيد بعد {probation_months - months_worked} شهر"
        elif months_worked < full_months:
            stage = f"يستحق {partial_percentage}% من الرصيد"
            next_milestone = f"سيستحق الرصيد كاملاً بعد {full_months - months_worked} شهر"
        else:
            stage = "يستحق الرصيد كاملاً"
            next_milestone = "تم استحقاق الرصيد بالكامل"
        
        return {
            'employee': employee.get_full_name_ar(),
            'hire_date': employee.hire_date,
            'months_worked': months_worked,
            'accrual_percentage': f"{int(accrual_percentage * 100)}%",
            'stage': stage,
            'next_milestone': next_milestone,
            'balances': balances_info
        }
