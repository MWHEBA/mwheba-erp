"""
خدمة إدارة الإجازات
"""
from django.db import transaction
from datetime import date
from ..models import Leave, LeaveBalance


class LeaveService:
    """خدمة إدارة الإجازات"""
    
    @staticmethod
    @transaction.atomic
    def request_leave(employee, leave_data):
        """
        طلب إجازة جديد
        
        Args:
            employee: الموظف
            leave_data: بيانات الإجازة
        
        Returns:
            Leave: طلب الإجازة
        """
        leave_type = leave_data['leave_type']
        start_date = leave_data['start_date']
        end_date = leave_data['end_date']
        
        # حساب عدد الأيام
        days_count = (end_date - start_date).days + 1
        
        # التحقق من الرصيد
        if not LeaveService._check_leave_balance(employee, leave_type, days_count):
            raise ValueError('رصيد الإجازات غير كافٍ')
        
        # إنشاء الطلب
        leave = Leave.objects.create(
            employee=employee,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            days_count=days_count,
            reason=leave_data['reason'],
            status='pending'
        )
        
        return leave
    
    @staticmethod
    def _check_leave_balance(employee, leave_type, days_count):
        """التحقق من رصيد الإجازات المستحق"""
        current_year = date.today().year
        
        try:
            balance = LeaveBalance.objects.get(
                employee=employee,
                leave_type=leave_type,
                year=current_year
            )
            # تحديث الاستحقاق قبل التحقق
            balance.update_accrued_days()
            
            # التحقق من الرصيد المتبقي (المستحق - المستخدم)
            return balance.remaining_days >= days_count
        except LeaveBalance.DoesNotExist:
            return False
    
    @staticmethod
    @transaction.atomic
    def approve_leave(leave, approver, review_notes=None):
        """
        اعتماد الإجازة
        
        Args:
            leave: الإجازة
            approver: المعتمد
            review_notes: ملاحظات المراجعة (اختياري)
        
        Returns:
            Leave: الإجازة المعتمدة
        """
        leave.status = 'approved'
        leave.approved_by = approver
        leave.approved_at = date.today()
        if review_notes:
            leave.review_notes = review_notes
        leave.save()
        
        # خصم من الرصيد
        LeaveService._deduct_from_balance(leave)
        
        return leave
    
    @staticmethod
    def _deduct_from_balance(leave):
        """خصم الإجازة من الرصيد"""
        current_year = date.today().year
        
        try:
            balance = LeaveBalance.objects.get(
                employee=leave.employee,
                leave_type=leave.leave_type,
                year=current_year
            )
            balance.used_days += leave.days_count
            balance.update_balance()
        except LeaveBalance.DoesNotExist:
            pass
    
    @staticmethod
    @transaction.atomic
    def reject_leave(leave, reviewer, notes):
        """
        رفض الإجازة
        
        Args:
            leave: الإجازة
            reviewer: المراجع
            notes: ملاحظات الرفض
        
        Returns:
            Leave: الإجازة المرفوضة
        """
        leave.status = 'rejected'
        leave.reviewed_by = reviewer
        leave.reviewed_at = date.today()
        leave.review_notes = notes
        leave.save()
        
        return leave
    
    @staticmethod
    def calculate_leave_balance(employee, leave_type):
        """
        حساب رصيد الإجازات
        
        Args:
            employee: الموظف
            leave_type: نوع الإجازة
        
        Returns:
            dict: معلومات الرصيد
        """
        current_year = date.today().year
        
        try:
            balance = LeaveBalance.objects.get(
                employee=employee,
                leave_type=leave_type,
                year=current_year
            )
            return {
                'total_days': balance.total_days,
                'used_days': balance.used_days,
                'remaining_days': balance.remaining_days,
            }
        except LeaveBalance.DoesNotExist:
            return {
                'total_days': 0,
                'used_days': 0,
                'remaining_days': 0,
            }
