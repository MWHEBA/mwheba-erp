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
    from django.urls import reverse
    
    context = {
        'page_title': 'التقارير',
        'page_subtitle': 'تقارير نظام الموارد البشرية',
        'page_icon': 'fas fa-chart-bar',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users'},
            {'title': 'التقارير', 'active': True},
        ],
    }
    
    return render(request, 'hr/reports/home.html', context)


@login_required
def attendance_report(request):
    """تقرير الحضور"""
    from django.urls import reverse
    
    context = {
        'page_title': 'تقرير الحضور',
        'page_subtitle': 'تقرير شامل للحضور والانصراف',
        'page_icon': 'fas fa-clock',
        'header_buttons': [
            {
                'onclick': "window.location.href='?export=excel'",
                'icon': 'fa-file-excel',
                'text': 'تصدير Excel',
                'class': 'btn-success',
            },
            {
                'url': reverse('hr:reports_home'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users'},
            {'title': 'التقارير', 'url': reverse('hr:reports_home'), 'icon': 'fas fa-chart-bar'},
            {'title': 'تقرير الحضور', 'active': True},
        ],
    }
    
    return render(request, 'hr/reports/attendance.html', context)


@login_required
def leave_report(request):
    """تقرير الإجازات"""
    from django.urls import reverse
    
    context = {
        'page_title': 'تقرير الإجازات',
        'page_subtitle': 'تقرير شامل للإجازات',
        'page_icon': 'fas fa-calendar-alt',
        'header_buttons': [
            {
                'onclick': "window.location.href='?export=excel'",
                'icon': 'fa-file-excel',
                'text': 'تصدير Excel',
                'class': 'btn-success',
            },
            {
                'url': reverse('hr:reports_home'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users'},
            {'title': 'التقارير', 'url': reverse('hr:reports_home'), 'icon': 'fas fa-chart-bar'},
            {'title': 'تقرير الإجازات', 'active': True},
        ],
    }
    
    return render(request, 'hr/reports/leave.html', context)


@login_required
def payroll_report(request):
    """تقرير الرواتب"""
    from django.urls import reverse
    
    context = {
        'page_title': 'تقرير الرواتب',
        'page_subtitle': 'تقرير شامل للرواتب',
        'page_icon': 'fas fa-money-bill-wave',
        'header_buttons': [
            {
                'onclick': "window.location.href='?export=excel'",
                'icon': 'fa-file-excel',
                'text': 'تصدير Excel',
                'class': 'btn-success',
            },
            {
                'url': reverse('hr:reports_home'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users'},
            {'title': 'التقارير', 'url': reverse('hr:reports_home'), 'icon': 'fas fa-chart-bar'},
            {'title': 'تقرير الرواتب', 'active': True},
        ],
    }
    
    return render(request, 'hr/reports/payroll.html', context)


@login_required
def employee_report(request):
    """تقرير الموظفين"""
    from django.urls import reverse
    
    context = {
        'page_title': 'تقرير الموظفين',
        'page_subtitle': 'تقرير شامل لبيانات الموظفين',
        'page_icon': 'fas fa-users',
        'header_buttons': [
            {
                'onclick': "window.location.href='?export=excel'",
                'icon': 'fa-file-excel',
                'text': 'تصدير Excel',
                'class': 'btn-success',
            },
            {
                'url': reverse('hr:reports_home'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users'},
            {'title': 'التقارير', 'url': reverse('hr:reports_home'), 'icon': 'fas fa-chart-bar'},
            {'title': 'تقرير الموظفين', 'active': True},
        ],
    }
    
    return render(request, 'hr/reports/employee.html', context)
