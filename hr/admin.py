"""
إعدادات Admin لوحدة الموارد البشرية
"""
from django.contrib import admin
from .models import (
    Employee, Department, JobTitle,
    Shift, Attendance,
    LeaveType, LeaveBalance, Leave,
    Salary, Payroll, Advance,
    SalaryComponent, SalaryComponentTemplate
)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['code', 'name_ar', 'parent', 'manager', 'employees_count', 'is_active']
    list_filter = ['is_active', 'parent']
    search_fields = ['code', 'name_ar', 'name_en']
    ordering = ['code']


@admin.register(JobTitle)
class JobTitleAdmin(admin.ModelAdmin):
    list_display = ['code', 'title_ar', 'department', 'is_active']
    list_filter = ['is_active', 'department']
    search_fields = ['code', 'title_ar', 'title_en']
    ordering = ['code']


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ['employee_number', 'get_full_name_ar', 'department', 'job_title', 'status', 'hire_date']
    list_filter = ['status', 'department', 'employment_type', 'gender']
    search_fields = ['employee_number', 'first_name_ar', 'last_name_ar', 'national_id', 'work_email']
    ordering = ['employee_number']
    date_hierarchy = 'hire_date'
    
    fieldsets = (
        ('معلومات المستخدم', {
            'fields': ('user', 'employee_number', 'created_by')
        }),
        ('المعلومات الشخصية', {
            'fields': (
                ('first_name_ar', 'last_name_ar'),
                ('first_name_en', 'last_name_en'),
                'national_id', 'birth_date', 'gender',
                'nationality', 'marital_status', 'religion', 'military_status'
            )
        }),
        ('معلومات الاتصال', {
            'fields': (
                ('personal_email', 'work_email'),
                ('mobile_phone', 'home_phone'),
                'address', ('city', 'postal_code')
            )
        }),
        ('جهة اتصال الطوارئ', {
            'fields': ('emergency_contact_name', 'emergency_contact_relation', 'emergency_contact_phone')
        }),
        ('المعلومات الوظيفية', {
            'fields': (
                'department', 'job_title', 'direct_manager',
                'hire_date', 'employment_type'
            )
        }),
        ('الحالة', {
            'fields': ('status', 'termination_date', 'termination_reason')
        }),
        ('الصورة', {
            'fields': ('photo',)
        }),
    )


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ['name', 'shift_type', 'start_time', 'end_time', 'work_hours', 'is_active']
    list_filter = ['shift_type', 'is_active']
    search_fields = ['name']


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ['employee', 'date', 'check_in', 'check_out', 'work_hours', 'late_minutes', 'status']
    list_filter = ['status', 'date', 'shift']
    search_fields = ['employee__first_name_ar', 'employee__last_name_ar', 'employee__employee_number']
    date_hierarchy = 'date'
    ordering = ['-date']


@admin.register(LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = ['code', 'name_ar', 'max_days_per_year', 'is_paid', 'requires_approval', 'is_active']
    list_filter = ['is_paid', 'requires_approval', 'is_active']
    search_fields = ['code', 'name_ar', 'name_en']


@admin.register(LeaveBalance)
class LeaveBalanceAdmin(admin.ModelAdmin):
    list_display = ['employee', 'leave_type', 'year', 'total_days', 'used_days', 'remaining_days']
    list_filter = ['year', 'leave_type']
    search_fields = ['employee__first_name_ar', 'employee__last_name_ar']


@admin.register(Leave)
class LeaveAdmin(admin.ModelAdmin):
    list_display = ['employee', 'leave_type', 'start_date', 'end_date', 'days_count', 'status']
    list_filter = ['status', 'leave_type', 'start_date']
    search_fields = ['employee__first_name_ar', 'employee__last_name_ar']
    date_hierarchy = 'start_date'
    ordering = ['-requested_at']


@admin.register(Salary)
class SalaryAdmin(admin.ModelAdmin):
    list_display = ['employee', 'effective_date', 'basic_salary', 'gross_salary', 'net_salary', 'is_active']
    list_filter = ['is_active', 'effective_date']
    search_fields = ['employee__first_name_ar', 'employee__last_name_ar']
    date_hierarchy = 'effective_date'
    ordering = ['-effective_date']


@admin.register(Payroll)
class PayrollAdmin(admin.ModelAdmin):
    list_display = ['employee', 'month', 'gross_salary', 'total_deductions', 'net_salary', 'status']
    list_filter = ['status', 'month', 'payment_method']
    search_fields = ['employee__first_name_ar', 'employee__last_name_ar']
    date_hierarchy = 'month'
    ordering = ['-month']


@admin.register(Advance)
class AdvanceAdmin(admin.ModelAdmin):
    list_display = ['employee', 'amount', 'status', 'deducted', 'requested_at']
    list_filter = ['status', 'deducted']
    search_fields = ['employee__first_name_ar', 'employee__last_name_ar']
    date_hierarchy = 'requested_at'
    ordering = ['-requested_at']


@admin.register(SalaryComponentTemplate)
class SalaryComponentTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'component_type', 'formula', 'default_amount', 'order', 'is_active']
    list_filter = ['component_type', 'is_active']
    search_fields = ['name', 'description']
    ordering = ['component_type', 'order', 'name']
    list_editable = ['order', 'is_active']


@admin.register(SalaryComponent)
class SalaryComponentAdmin(admin.ModelAdmin):
    list_display = ['contract', 'component_type', 'name', 'formula', 'amount', 'order']
    list_filter = ['component_type', 'is_basic']
    search_fields = ['name', 'contract__contract_number']
    ordering = ['contract', 'component_type', 'order']
