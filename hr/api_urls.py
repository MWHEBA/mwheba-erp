"""
API URLs لوحدة الموارد البشرية
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api_views import (
    EmployeeViewSet, DepartmentViewSet, JobTitleViewSet,
    ShiftViewSet, AttendanceViewSet, LeaveTypeViewSet,
    LeaveBalanceViewSet, LeaveViewSet, SalaryViewSet,
    PayrollViewSet, AdvanceViewSet
)

app_name = 'hr_api'

# إنشاء Router
router = DefaultRouter()

# تسجيل ViewSets
router.register(r'employees', EmployeeViewSet, basename='employee')
router.register(r'departments', DepartmentViewSet, basename='department')
router.register(r'job-titles', JobTitleViewSet, basename='jobtitle')
router.register(r'shifts', ShiftViewSet, basename='shift')
router.register(r'attendance', AttendanceViewSet, basename='attendance')
router.register(r'leave-types', LeaveTypeViewSet, basename='leavetype')
router.register(r'leave-balances', LeaveBalanceViewSet, basename='leavebalance')
router.register(r'leaves', LeaveViewSet, basename='leave')
router.register(r'salaries', SalaryViewSet, basename='salary')
router.register(r'payroll', PayrollViewSet, basename='payroll')
router.register(r'advances', AdvanceViewSet, basename='advance')

urlpatterns = [
    path('', include(router.urls)),
]
