"""
نماذج (Forms) وحدة الموارد البشرية
"""
from .salary_component_forms import UnifiedSalaryComponentForm
from .attendance_forms import AttendanceForm
from .leave_forms import LeaveRequestForm
from .payroll_forms import PayrollForm
from .contract_forms import ContractForm

__all__ = [
    'UnifiedSalaryComponentForm',
    'EmployeeForm',
    'DepartmentForm',
    'JobTitleForm',
    'AttendanceForm',
    'LeaveRequestForm',
    'PayrollForm',
    'ContractForm',
]
