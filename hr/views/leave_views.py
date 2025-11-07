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
    return render(request, 'hr/leave/list.html', {'leaves': leaves})


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
    }
    return render(request, 'hr/leave/request.html', context)


@login_required
def leave_detail(request, pk):
    """تفاصيل الإجازة"""
    leave = get_object_or_404(Leave, pk=pk)
    return render(request, 'hr/leave/detail.html', {'leave': leave})


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
    return render(request, 'hr/leave/approve.html', {'leave': leave})


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
    return render(request, 'hr/leave/reject.html', {'leave': leave})
