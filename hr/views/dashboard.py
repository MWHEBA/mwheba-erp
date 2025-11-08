"""
Dashboard الموارد البشرية
"""
from .base_imports import *
from ..models import Employee, Department, Leave, Attendance

__all__ = ['dashboard']


@login_required
def dashboard(request):
    """Dashboard الموارد البشرية"""
    context = {
        'page_title': 'لوحة تحكم الموارد البشرية',
        'page_subtitle': 'نظرة شاملة على إدارة الموظفين والحضور والرواتب',
        'page_icon': 'fas fa-users-cog',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'active': True},
        ],
        'total_employees': Employee.objects.filter(status='active').count(),
        'total_departments': Department.objects.filter(is_active=True).count(),
        'pending_leaves': Leave.objects.filter(status='pending').count(),
        'today_attendance': Attendance.objects.filter(date=date.today()).count(),
    }
    return render(request, 'hr/dashboard.html', context)
