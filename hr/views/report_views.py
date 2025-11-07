"""
دوال عرض التقارير - HR Reports Views
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render


__all__ = [
    'reports_home',
    'attendance_report',
    'leave_report',
    'payroll_report',
    'employee_report',
]


# ==================== التقارير ====================

@login_required
def reports_home(request):
    """الصفحة الرئيسية للتقارير"""
    return render(request, 'hr/reports/home.html')


@login_required
def attendance_report(request):
    """تقرير الحضور"""
    return render(request, 'hr/reports/attendance.html')


@login_required
def leave_report(request):
    """تقرير الإجازات"""
    return render(request, 'hr/reports/leave.html')


@login_required
def payroll_report(request):
    """تقرير الرواتب"""
    return render(request, 'hr/reports/payroll.html')


@login_required
def employee_report(request):
    """تقرير الموظفين"""
    return render(request, 'hr/reports/employee.html')
