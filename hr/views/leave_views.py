"""
Views إدارة الإجازات
"""
from .base_imports import *
from ..models import Leave, LeaveBalance, Employee, LeaveType
from ..forms.leave_forms import LeaveRequestForm
from ..services.leave_service import LeaveService
from datetime import date

__all__ = [
    'leave_list',
    'leave_request',
    'leave_detail',
    'leave_approve',
    'leave_reject',
]


@login_required
def leave_list(request):
    """قائمة الإجازات"""
    leaves = Leave.objects.select_related('employee', 'leave_type').all()
    
    # الإحصائيات
    total_leaves = leaves.count()
    pending_leaves = leaves.filter(status='pending').count()
    approved_leaves = leaves.filter(status='approved').count()
    rejected_leaves = leaves.filter(status='rejected').count()
    
    # جلب الموظفين وأنواع الإجازات للفلاتر
    employees = Employee.objects.filter(status='active')
    leave_types = LeaveType.objects.filter(is_active=True)
    
    context = {
        'leaves': leaves,
        'employees': employees,
        'leave_types': leave_types,
        'total_leaves': total_leaves,
        'pending_leaves': pending_leaves,
        'approved_leaves': approved_leaves,
        'rejected_leaves': rejected_leaves,
        'show_stats': True,
        
        # بيانات الهيدر
        'page_title': 'قائمة الإجازات',
        'page_subtitle': 'إدارة ومتابعة طلبات الإجازات للموظفين',
        'page_icon': 'fas fa-calendar-alt',
        
        # أزرار الهيدر
        'header_buttons': [
            {
                'url': reverse('hr:leave_request'),
                'icon': 'fa-plus',
                'text': 'طلب إجازة جديد',
                'class': 'btn-primary',
            },
        ],
        
        # البريدكرمب
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'قائمة الإجازات', 'active': True},
        ],
    }
    
    return render(request, 'hr/leave/list.html', context)


@login_required
def leave_request(request):
    """طلب إجازة جديد"""
    
    # جلب الموظف الحالي
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, 'لا يوجد حساب موظف مرتبط بحسابك')
        return redirect('hr:dashboard')
    
    # جلب أرصدة الإجازات للموظف
    current_year = date.today().year
    balances = LeaveBalance.objects.filter(
        employee=employee,
        year=current_year
    ).select_related('leave_type')
    
    # تحديث الأرصدة المستحقة
    for balance in balances:
        balance.update_accrued_days()
    
    if request.method == 'POST':
        form = LeaveRequestForm(request.POST, request.FILES)
        if form.is_valid():
            leave = form.save(commit=False)
            leave.employee = employee
            leave.requested_by = request.user
            
            # حساب عدد الأيام
            days_count = (leave.end_date - leave.start_date).days + 1
            leave.days_count = days_count
            
            # التحقق من الرصيد المتاح
            balance = balances.filter(leave_type=leave.leave_type).first()
            if balance and balance.remaining_days < days_count:
                messages.error(request, f'رصيدك غير كافٍ. المتبقي: {balance.remaining_days} يوم، المطلوب: {days_count} يوم')
            else:
                leave.save()
                messages.success(request, 'تم تقديم طلب الإجازة بنجاح')
                return redirect('hr:leave_detail', pk=leave.pk)
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء في النموذج')
    else:
        form = LeaveRequestForm()
    
    context = {
        'form': form,
        'employee': employee,
        'balances': balances,
        'current_year': current_year,
        'page_title': 'طلب إجازة جديد',
        'page_subtitle': 'تقديم طلب إجازة جديد',
        'page_icon': 'fas fa-calendar-plus',
        'header_buttons': [
            {
                'url': '/hr/leaves/',
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': '/dashboard/', 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': '/hr/', 'icon': 'fas fa-users-cog'},
            {'title': 'الإجازات', 'url': '/hr/leaves/', 'icon': 'fas fa-calendar-alt'},
            {'title': 'طلب إجازة', 'active': True},
        ],
    }
    return render(request, 'hr/leave/request.html', context)


@login_required
def leave_detail(request, pk):
    """تفاصيل الإجازة"""
    leave = get_object_or_404(Leave, pk=pk)
    
    # تحديد الأزرار حسب حالة الإجازة
    header_buttons = []
    if leave.status == 'pending':
        header_buttons.extend([
            {
                'url': f'/hr/leaves/{leave.pk}/approve/',
                'icon': 'fa-check',
                'text': 'اعتماد',
                'class': 'btn-success',
            },
            {
                'url': f'/hr/leaves/{leave.pk}/reject/',
                'icon': 'fa-times',
                'text': 'رفض',
                'class': 'btn-danger',
            },
        ])
    header_buttons.append({
        'url': '/hr/leaves/',
        'icon': 'fa-arrow-right',
        'text': 'رجوع',
        'class': 'btn-secondary',
    })
    
    context = {
        'leave': leave,
        'page_title': 'تفاصيل الإجازة',
        'page_subtitle': f'{leave.employee.get_full_name_ar()} - {leave.leave_type.name_ar}',
        'page_icon': 'fas fa-calendar-alt',
        'header_buttons': header_buttons,
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': '/dashboard/', 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': '/hr/', 'icon': 'fas fa-users-cog'},
            {'title': 'الإجازات', 'url': '/hr/leaves/', 'icon': 'fas fa-calendar-alt'},
            {'title': 'تفاصيل الإجازة', 'active': True},
        ],
    }
    return render(request, 'hr/leave/detail.html', context)


@login_required
def leave_approve(request, pk):
    """اعتماد الإجازة"""
    leave = get_object_or_404(Leave, pk=pk)
    if request.method == 'POST':
        review_notes = request.POST.get('review_notes', '')
        try:
            LeaveService.approve_leave(leave, request.user, review_notes)
            messages.success(request, 'تم اعتماد الإجازة بنجاح')
            return redirect('hr:leave_detail', pk=pk)
        except Exception as e:
            messages.error(request, f'خطأ: {str(e)}')
    
    context = {
        'leave': leave,
        'page_title': 'اعتماد طلب إجازة',
        'page_subtitle': 'مراجعة واعتماد طلب الإجازة',
        'page_icon': 'fas fa-check-circle',
        'header_buttons': [
            {
                'url': '/hr/leaves/',
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': '/dashboard/', 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': '/hr/', 'icon': 'fas fa-users'},
            {'title': 'الإجازات', 'url': '/hr/leaves/', 'icon': 'fas fa-calendar-alt'},
            {'title': 'اعتماد إجازة', 'active': True},
        ],
    }
    return render(request, 'hr/leave/approve.html', context)


@login_required
def leave_reject(request, pk):
    """رفض الإجازة"""
    leave = get_object_or_404(Leave, pk=pk)
    if request.method == 'POST':
        review_notes = request.POST.get('review_notes', '')
        try:
            LeaveService.reject_leave(leave, request.user, review_notes)
            messages.success(request, 'تم رفض الإجازة')
            return redirect('hr:leave_detail', pk=pk)
        except Exception as e:
            messages.error(request, f'خطأ: {str(e)}')
    
    context = {
        'leave': leave,
        'page_title': 'رفض طلب إجازة',
        'page_subtitle': 'مراجعة ورفض طلب الإجازة',
        'page_icon': 'fas fa-times-circle',
        'header_buttons': [
            {
                'url': '/hr/leaves/',
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': '/dashboard/', 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': '/hr/', 'icon': 'fas fa-users'},
            {'title': 'الإجازات', 'url': '/hr/leaves/', 'icon': 'fas fa-calendar-alt'},
            {'title': 'رفض إجازة', 'active': True},
        ],
    }
    return render(request, 'hr/leave/reject.html', context)
