# Backward compatibility
from hr.services.organization_service import OrganizationService
from hr.services.salary_component_service import SalaryComponentService
from hr.services.employee_service import EmployeeService
from hr.services.attendance_service import AttendanceService
from hr.services.leave_service import LeaveService
from hr.services.payroll_service import PayrollService

__all__ = [
    'OrganizationService',
    'SalaryComponentService',
    'EmployeeService',
    'AttendanceService',
    'LeaveService',
    'PayrollService',
]
