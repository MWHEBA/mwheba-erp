"""
Serializers لـ API وحدة الموارد البشرية
"""
from rest_framework import serializers
from .models import (
    Employee, Department, JobTitle, Shift, Attendance,
    LeaveType, LeaveBalance, Leave, Salary, Payroll, Advance
)


class DepartmentSerializer(serializers.ModelSerializer):
    """Serializer للأقسام"""
    
    class Meta:
        model = Department
        fields = [
            'id', 'code', 'name_ar', 'name_en', 'description',
            'parent', 'manager', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class JobTitleSerializer(serializers.ModelSerializer):
    """Serializer للمسميات الوظيفية"""
    department_name = serializers.CharField(source='department.name_ar', read_only=True)
    
    class Meta:
        model = JobTitle
        fields = [
            'id', 'code', 'title_ar', 'title_en', 'description',
            'department', 'department_name', 'responsibilities',
            'requirements', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class EmployeeSerializer(serializers.ModelSerializer):
    """Serializer للموظفين"""
    department_name = serializers.CharField(source='department.name_ar', read_only=True)
    job_title_name = serializers.CharField(source='job_title.title_ar', read_only=True)
    full_name_ar = serializers.CharField(source='get_full_name_ar', read_only=True)
    age = serializers.IntegerField(read_only=True)
    years_of_service = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Employee
        fields = [
            'id', 'user', 'employee_number', 'first_name_ar', 'last_name_ar',
            'first_name_en', 'last_name_en', 'full_name_ar', 'national_id',
            'birth_date', 'age', 'gender', 'nationality', 'marital_status',
            'religion', 'military_status', 'personal_email', 'work_email',
            'mobile_phone', 'home_phone', 'address', 'city', 'postal_code',
            'emergency_contact_name', 'emergency_contact_relation',
            'emergency_contact_phone', 'department', 'department_name',
            'job_title', 'job_title_name', 'direct_manager', 'hire_date',
            'years_of_service', 'employment_type', 'status', 'termination_date',
            'termination_reason', 'photo', 'created_by', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'age', 'years_of_service', 'full_name_ar']


class ShiftSerializer(serializers.ModelSerializer):
    """Serializer للورديات"""
    
    class Meta:
        model = Shift
        fields = [
            'id', 'name', 'shift_type', 'start_time', 'end_time',
            'grace_period_in', 'grace_period_out', 'work_hours',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class AttendanceSerializer(serializers.ModelSerializer):
    """Serializer للحضور"""
    employee_name = serializers.CharField(source='employee.get_full_name_ar', read_only=True)
    shift_name = serializers.CharField(source='shift.name', read_only=True)
    
    class Meta:
        model = Attendance
        fields = [
            'id', 'employee', 'employee_name', 'date', 'shift', 'shift_name',
            'check_in', 'check_out', 'work_hours', 'overtime_hours',
            'late_minutes', 'early_leave_minutes', 'status', 'notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'work_hours', 'overtime_hours']


class LeaveTypeSerializer(serializers.ModelSerializer):
    """Serializer لأنواع الإجازات"""
    
    class Meta:
        model = LeaveType
        fields = [
            'id', 'name_ar', 'name_en', 'code', 'max_days_per_year',
            'is_paid', 'requires_approval', 'requires_document',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class LeaveBalanceSerializer(serializers.ModelSerializer):
    """Serializer لرصيد الإجازات"""
    employee_name = serializers.CharField(source='employee.get_full_name_ar', read_only=True)
    leave_type_name = serializers.CharField(source='leave_type.name_ar', read_only=True)
    
    class Meta:
        model = LeaveBalance
        fields = [
            'id', 'employee', 'employee_name', 'leave_type', 'leave_type_name',
            'year', 'total_days', 'used_days', 'remaining_days',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'remaining_days']


class LeaveSerializer(serializers.ModelSerializer):
    """Serializer للإجازات"""
    employee_name = serializers.CharField(source='employee.get_full_name_ar', read_only=True)
    leave_type_name = serializers.CharField(source='leave_type.name_ar', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.get_full_name', read_only=True)
    
    class Meta:
        model = Leave
        fields = [
            'id', 'employee', 'employee_name', 'leave_type', 'leave_type_name',
            'start_date', 'end_date', 'days_count', 'reason', 'attachment',
            'status', 'requested_at', 'approved_by', 'approved_by_name',
            'approved_at', 'reviewed_by', 'reviewed_at', 'review_notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'requested_at', 'days_count']


class SalarySerializer(serializers.ModelSerializer):
    """Serializer للرواتب"""
    employee_name = serializers.CharField(source='employee.get_full_name_ar', read_only=True)
    
    class Meta:
        model = Salary
        fields = [
            'id', 'employee', 'employee_name', 'basic_salary',
            'housing_allowance', 'transport_allowance', 'food_allowance',
            'other_allowances', 'gross_salary', 'social_insurance_rate',
            'tax_rate', 'effective_date', 'end_date', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'gross_salary']


class PayrollSerializer(serializers.ModelSerializer):
    """Serializer لكشوف الرواتب"""
    employee_name = serializers.CharField(source='employee.get_full_name_ar', read_only=True)
    processed_by_name = serializers.CharField(source='processed_by.get_full_name', read_only=True)
    
    class Meta:
        model = Payroll
        fields = [
            'id', 'employee', 'employee_name', 'month', 'salary',
            'basic_salary', 'allowances', 'bonus', 'overtime_hours',
            'overtime_rate', 'overtime_amount', 'total_additions',
            'absence_days', 'absence_deduction', 'late_deduction',
            'social_insurance', 'tax', 'advance_deduction',
            'other_deductions', 'total_deductions', 'gross_salary',
            'net_salary', 'payment_method', 'payment_date', 'status',
            'processed_by', 'processed_by_name', 'processed_at',
            'approved_by', 'approved_at', 'journal_entry', 'notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'created_at', 'updated_at', 'processed_at',
            'total_additions', 'total_deductions', 'gross_salary', 'net_salary'
        ]


class AdvanceSerializer(serializers.ModelSerializer):
    """Serializer للسلف"""
    employee_name = serializers.CharField(source='employee.get_full_name_ar', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.get_full_name', read_only=True)
    
    class Meta:
        model = Advance
        fields = [
            'id', 'employee', 'employee_name', 'amount', 'reason',
            'request_date', 'status', 'approved_by', 'approved_by_name',
            'payment_date', 'deducted', 'deduction_month', 'notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
