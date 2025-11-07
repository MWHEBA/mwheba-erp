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
from .models.contract import Contract, ContractAmendment, ContractDocument, ContractIncrease
from .models.salary_increase import (
    SalaryIncreaseTemplate, AnnualIncreasePlan,
    PlannedIncrease, EmployeeIncreaseCategory
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


class ContractDocumentInline(admin.TabularInline):
    model = ContractDocument
    extra = 0
    fields = ['document_type', 'title', 'file', 'uploaded_by', 'uploaded_at']
    readonly_fields = ['uploaded_by', 'uploaded_at']


class ContractAmendmentInline(admin.TabularInline):
    model = ContractAmendment
    extra = 0
    fields = ['amendment_number', 'amendment_type', 'effective_date', 'description']
    readonly_fields = ['amendment_number', 'created_at', 'created_by']


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ['contract_number', 'employee', 'contract_type', 'status', 'start_date', 'end_date', 'basic_salary']
    list_filter = ['status', 'contract_type', 'start_date']
    search_fields = ['contract_number', 'employee__first_name_ar', 'employee__last_name_ar']
    ordering = ['-start_date']
    inlines = [ContractDocumentInline, ContractAmendmentInline]
    readonly_fields = ['created_at', 'created_by']
    
    fieldsets = (
        ('معلومات العقد الأساسية', {
            'fields': ('contract_number', 'employee', 'contract_type', 'status')
        }),
        ('التواريخ', {
            'fields': ('start_date', 'end_date', 'probation_period_months', 'probation_end_date')
        }),
        ('الراتب', {
            'fields': ('basic_salary',)
        }),
        ('البنود والشروط', {
            'fields': ('terms_and_conditions', 'notes', 'auto_renew')
        }),
        ('معلومات النظام', {
            'fields': ('created_at', 'created_by'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ContractDocument)
class ContractDocumentAdmin(admin.ModelAdmin):
    list_display = ['contract', 'document_type', 'title', 'file_size_mb', 'uploaded_at', 'uploaded_by']
    list_filter = ['document_type', 'uploaded_at']
    search_fields = ['title', 'contract__contract_number']
    ordering = ['-uploaded_at']
    readonly_fields = ['uploaded_at', 'uploaded_by', 'file_size_mb']


@admin.register(ContractAmendment)
class ContractAmendmentAdmin(admin.ModelAdmin):
    list_display = ['amendment_number', 'contract', 'amendment_type', 'effective_date', 'created_by']
    list_filter = ['amendment_type', 'effective_date']
    search_fields = ['amendment_number', 'contract__contract_number', 'description']
    ordering = ['-effective_date']
    readonly_fields = ['created_at', 'created_by']


@admin.register(ContractIncrease)
class ContractIncreaseAdmin(admin.ModelAdmin):
    list_display = ['contract', 'increase_number', 'increase_type', 'get_increase_value', 'scheduled_date', 'status', 'applied_date']
    list_filter = ['status', 'increase_type', 'scheduled_date']
    search_fields = ['contract__contract_number', 'contract__employee__first_name_ar', 'contract__employee__last_name_ar']
    ordering = ['contract', 'increase_number']
    readonly_fields = ['created_at', 'created_by', 'updated_at', 'applied_date', 'applied_amount']
    
    fieldsets = (
        ('معلومات الزيادة', {
            'fields': ('contract', 'increase_number', 'increase_type')
        }),
        ('قيمة الزيادة', {
            'fields': ('increase_percentage', 'increase_amount')
        }),
        ('الجدولة', {
            'fields': ('months_from_start', 'scheduled_date')
        }),
        ('الحالة', {
            'fields': ('status', 'applied_date', 'applied_amount', 'amendment')
        }),
        ('ملاحظات', {
            'fields': ('notes',)
        }),
        ('معلومات النظام', {
            'fields': ('created_at', 'created_by', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_increase_value(self, obj):
        """عرض قيمة الزيادة"""
        if obj.increase_type == 'percentage':
            return f"{obj.increase_percentage}%"
        else:
            return f"{obj.increase_amount} جنيه"
    get_increase_value.short_description = 'قيمة الزيادة'


# ============================================
# نظام زيادات المرتبات من الإعدادات
# ============================================

@admin.register(SalaryIncreaseTemplate)
class SalaryIncreaseTemplateAdmin(admin.ModelAdmin):
    """إدارة قوالب زيادات المرتبات"""
    list_display = ['name', 'code', 'increase_type', 'get_default_value', 'frequency', 'is_active', 'is_default']
    list_filter = ['increase_type', 'frequency', 'is_active', 'is_default']
    search_fields = ['name', 'code', 'description']
    ordering = ['-is_default', 'name']
    readonly_fields = ['created_at', 'updated_at', 'created_by']
    
    fieldsets = (
        ('معلومات أساسية', {
            'fields': ('name', 'code', 'description')
        }),
        ('نوع الزيادة', {
            'fields': ('increase_type', 'default_percentage', 'default_amount', 'frequency')
        }),
        ('الشروط والقيود', {
            'fields': (
                'min_service_months', 'min_performance_rating',
                'max_increase_percentage', 'max_increase_amount'
            )
        }),
        ('الحالة', {
            'fields': ('is_active', 'is_default')
        }),
        ('معلومات النظام', {
            'fields': ('created_at', 'updated_at', 'created_by'),
            'classes': ('collapse',)
        }),
    )
    
    def get_default_value(self, obj):
        """عرض القيمة الافتراضية"""
        if obj.increase_type == 'percentage' and obj.default_percentage:
            return f"{obj.default_percentage}%"
        elif obj.default_amount:
            return f"{obj.default_amount} جنيه"
        return "-"
    get_default_value.short_description = 'القيمة الافتراضية'


@admin.register(AnnualIncreasePlan)
class AnnualIncreasePlanAdmin(admin.ModelAdmin):
    """إدارة خطط الزيادات السنوية"""
    list_display = ['name', 'year', 'template', 'status', 'effective_date', 'total_budget', 'allocated_amount']
    list_filter = ['year', 'status', 'template']
    search_fields = ['name', 'notes']
    ordering = ['-year', '-created_at']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'approved_by', 'approval_date', 'allocated_amount']
    date_hierarchy = 'effective_date'
    
    fieldsets = (
        ('معلومات الخطة', {
            'fields': ('name', 'year', 'template')
        }),
        ('التواريخ', {
            'fields': ('effective_date', 'approval_date')
        }),
        ('الميزانية', {
            'fields': ('total_budget', 'allocated_amount')
        }),
        ('الحالة', {
            'fields': ('status', 'notes')
        }),
        ('معلومات النظام', {
            'fields': ('created_at', 'updated_at', 'created_by', 'approved_by'),
            'classes': ('collapse',)
        }),
    )


@admin.register(PlannedIncrease)
class PlannedIncreaseAdmin(admin.ModelAdmin):
    """إدارة الزيادات المخططة"""
    list_display = ['employee', 'plan', 'current_salary', 'calculated_amount', 'new_salary', 'status', 'applied_date']
    list_filter = ['status', 'plan', 'applied_date']
    search_fields = [
        'employee__first_name_ar', 'employee__last_name_ar',
        'employee__employee_number', 'plan__name'
    ]
    ordering = ['plan', 'employee']
    readonly_fields = ['created_at', 'updated_at', 'approved_by', 'applied_date', 'contract_increase']
    date_hierarchy = 'applied_date'
    
    fieldsets = (
        ('الربط', {
            'fields': ('plan', 'employee', 'contract')
        }),
        ('القيم', {
            'fields': (
                'current_salary', 'increase_percentage', 'increase_amount',
                'calculated_amount', 'new_salary'
            )
        }),
        ('معلومات إضافية', {
            'fields': ('performance_rating', 'justification')
        }),
        ('الحالة', {
            'fields': ('status', 'applied_date', 'contract_increase')
        }),
        ('معلومات النظام', {
            'fields': ('created_at', 'updated_at', 'approved_by'),
            'classes': ('collapse',)
        }),
    )


@admin.register(EmployeeIncreaseCategory)
class EmployeeIncreaseCategoryAdmin(admin.ModelAdmin):
    """إدارة فئات الموظفين للزيادات"""
    list_display = ['name', 'code', 'default_template', 'is_active']
    list_filter = ['is_active', 'default_template']
    search_fields = ['name', 'code', 'description']
    ordering = ['name']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('معلومات الفئة', {
            'fields': ('name', 'code', 'description')
        }),
        ('القالب الافتراضي', {
            'fields': ('default_template',)
        }),
        ('الحالة', {
            'fields': ('is_active',)
        }),
        ('معلومات النظام', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
