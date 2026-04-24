"""
Serializers لـ API وحدة الموارد البشرية
Phase 3: Enhanced with data masking for sensitive fields
"""
from rest_framework import serializers
from .models import (
    Employee, Department, JobTitle, Shift, Attendance,
    LeaveType, LeaveBalance, Leave, Payroll, Advance
)
from .permissions import CanViewSensitiveData


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
    """
    Serializer للموظفين مع Data Masking للبيانات الحساسة
    Issue #4: Exposed sensitive data
    """
    department_name = serializers.CharField(source='department.name_ar', read_only=True)
    job_title_name = serializers.CharField(source='job_title.title_ar', read_only=True)
    full_name_ar = serializers.CharField(source='get_full_name_ar', read_only=True)
    age = serializers.IntegerField(read_only=True)
    years_of_service = serializers.IntegerField(read_only=True)
    biometric_user_id = serializers.SerializerMethodField()
    shift = serializers.SerializerMethodField()
    
    # Sensitive fields with masking
    national_id = serializers.SerializerMethodField()
    mobile_phone = serializers.SerializerMethodField()
    personal_email = serializers.SerializerMethodField()
    
    def get_biometric_user_id(self, obj):
        """جلب رقم البصمة من BiometricUserMapping"""
        try:
            from .models import BiometricUserMapping
            mapping = BiometricUserMapping.objects.filter(employee=obj, is_active=True).first()
            return mapping.biometric_user_id if mapping else None
        except:
            return None

    def get_shift(self, obj):
        """جلب بيانات الوردية مع مراعاة أوقات رمضان بناءً على تاريخ الإذن"""
        if not obj.shift:
            return None
        try:
            from .models.attendance import RamadanSettings
            from datetime import date
            # استخدام تاريخ الإذن إن وُجد، وإلا اليوم
            request = self.context.get('request')
            perm_date_str = request.query_params.get('perm_date') if request else None
            if perm_date_str:
                from datetime import datetime
                target_date = datetime.strptime(perm_date_str, '%Y-%m-%d').date()
            else:
                target_date = date.today()

            ramadan = RamadanSettings.objects.filter(
                start_date__lte=target_date,
                end_date__gte=target_date
            ).first()
            if ramadan and obj.shift.ramadan_start_time and obj.shift.ramadan_end_time:
                start = obj.shift.ramadan_start_time.strftime('%H:%M')
                end = obj.shift.ramadan_end_time.strftime('%H:%M')
            else:
                start = obj.shift.start_time.strftime('%H:%M')
                end = obj.shift.end_time.strftime('%H:%M')
            return {
                'id': obj.shift.id,
                'name': obj.shift.name,
                'start_time': start,
                'end_time': end,
            }
        except Exception:
            return None
    
    def _can_view_sensitive_data(self, obj):
        """Check if user can view full sensitive data"""
        request = self.context.get('request')
        if not request:
            return False
        
        user = request.user
        
        # Employee viewing their own data
        if hasattr(user, 'employee') and obj == user.employee:
            return True
        
        # Superuser or HR managers
        if user.is_superuser:
            return True
        
        if hasattr(user, 'employee'):
            return user.employee.job_title.code in ['HR-MGR', 'HR-DIR']
        
        return False
    
    def get_national_id(self, obj):
        """Mask national ID: 12345678901234 → 1234****1234"""
        if not obj.national_id:
            return None
        
        if self._can_view_sensitive_data(obj):
            return obj.national_id
        
        # Mask middle digits
        if len(obj.national_id) >= 8:
            return f"{obj.national_id[:4]}****{obj.national_id[-4:]}"
        return "****"
    
    def get_mobile_phone(self, obj):
        """Mask mobile: 01234567890 → 0123***7890"""
        if not obj.mobile_phone:
            return None
        
        if self._can_view_sensitive_data(obj):
            return obj.mobile_phone
        
        # Mask middle digits
        if len(obj.mobile_phone) >= 8:
            return f"{obj.mobile_phone[:4]}***{obj.mobile_phone[-4:]}"
        return "***"
    
    def get_personal_email(self, obj):
        """Mask email: user@example.com → u***@example.com"""
        if not obj.personal_email:
            return None
        
        if self._can_view_sensitive_data(obj):
            return obj.personal_email
        
        # Mask username part
        if '@' in obj.personal_email:
            username, domain = obj.personal_email.split('@', 1)
            if len(username) > 1:
                return f"{username[0]}***@{domain}"
        return "***"
    
    class Meta:
        model = Employee
        fields = [
            'id', 'user', 'employee_number', 'name', 'full_name_ar', 'national_id',
            'birth_date', 'age', 'gender', 'marital_status',
            'military_status', 'personal_email', 'work_email',
            'mobile_phone', 'home_phone', 'address', 'city', 'postal_code',
            'emergency_contact_name', 'emergency_contact_relation',
            'emergency_contact_phone', 'department', 'department_name',
            'job_title', 'job_title_name', 'direct_manager', 'hire_date',
            'years_of_service', 'employment_type', 'status', 'termination_date',
            'termination_reason', 'biometric_user_id', 'photo', 'created_by', 'created_at', 'updated_at',
            'shift'
        ]
        read_only_fields = ['created_at', 'updated_at', 'age', 'years_of_service', 'full_name_ar']


class ShiftSerializer(serializers.ModelSerializer):
    """Serializer للورديات"""
    
    class Meta:
        model = Shift
        fields = [
            'id', 'name', 'shift_type', 'start_time', 'end_time',
            'grace_period_in', 'grace_period_out', 'work_hours',
            'is_active'
        ]
        read_only_fields = []


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


class PayrollSerializer(serializers.ModelSerializer):
    """Serializer لقسائم الرواتب"""
    employee_name = serializers.CharField(source='employee.get_full_name_ar', read_only=True)
    processed_by_name = serializers.CharField(source='processed_by.get_full_name', read_only=True)
    
    class Meta:
        model = Payroll
        fields = [
            'id', 'employee', 'employee_name', 'month', 'contract',
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
