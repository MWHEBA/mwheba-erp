"""
Views إدارة الرواتب والسلف
"""
from .base_imports import *
from ..models import Payroll, Advance, Employee, Salary
from ..forms.payroll_forms import PayrollProcessForm
from ..services.payroll_service import PayrollService
from django.db.models import Count, Sum, Q
from datetime import date

__all__ = [
    'payroll_list',
    'payroll_run_list',
    'payroll_run_process',
    'payroll_run_detail',
    'payroll_detail',
    'advance_list',
    'advance_request',
    'advance_detail',
    'advance_approve',
    'advance_reject',
    'salary_settings',
]


@login_required
def payroll_list(request):
    """قائمة كشوف الرواتب"""
    payrolls = Payroll.objects.select_related('employee', 'salary').all()
    return render(request, 'hr/payroll/list.html', {'payrolls': payrolls})


@login_required
def payroll_run_list(request):
    """قائمة مسيرات الرواتب"""
    # جمع الرواتب حسب الشهر
    payroll_runs = Payroll.objects.values('month').annotate(
        total_employees=Count('id'),
        total_amount=Sum('net_salary'),
        paid_count=Count('id', filter=Q(status='paid'))
    ).order_by('-month')
    
    return render(request, 'hr/payroll/run_list.html', {'payroll_runs': payroll_runs})


@login_required
def payroll_run_process(request):
    """معالجة مسيرة رواتب جديدة"""
    if request.method == 'POST':
        form = PayrollProcessForm(request.POST)
        if form.is_valid():
            try:
                month_str = form.cleaned_data['month']
                department = form.cleaned_data.get('department')
                
                payrolls = PayrollService.process_monthly_payroll(
                    month_str,
                    department,
                    request.user
                )
                messages.success(request, f'تم معالجة {len(payrolls)} كشف راتب بنجاح')
                return redirect('hr:payroll_run_detail', month=month_str)
            except Exception as e:
                messages.error(request, f'خطأ: {str(e)}')
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء في النموذج')
    else:
        form = PayrollProcessForm()
    
    return render(request, 'hr/payroll/run_process.html', {'form': form})


@login_required
def payroll_run_detail(request, month):
    """تفاصيل مسيرة رواتب شهر محدد"""
    payrolls = Payroll.objects.filter(month=month).select_related('employee', 'salary')
    
    stats = payrolls.aggregate(
        total_employees=Count('id'),
        total_gross=Sum('gross_salary'),
        total_deductions=Sum('total_deductions'),
        total_net=Sum('net_salary'),
        paid_count=Count('id', filter=Q(status='paid'))
    )
    
    context = {
        'month': month,
        'payrolls': payrolls,
        'stats': stats,
    }
    return render(request, 'hr/payroll/run_detail.html', context)


@login_required
def payroll_detail(request, pk):
    """تفاصيل كشف الراتب"""
    payroll = get_object_or_404(Payroll, pk=pk)
    return render(request, 'hr/payroll/detail.html', {'payroll': payroll})


# ==================== السلف ====================

@login_required
def advance_list(request):
    """قائمة السلف"""
    advances = Advance.objects.select_related('employee').all()
    return render(request, 'hr/advance/list.html', {'advances': advances})


@login_required
def advance_request(request):
    """طلب سلفة جديدة"""
    if request.method == 'POST':
        # سيتم إضافة النموذج لاحقاً
        messages.success(request, 'تم تقديم طلب السلفة بنجاح')
        return redirect('hr:advance_list')
    return render(request, 'hr/advance/request.html')


@login_required
def advance_detail(request, pk):
    """تفاصيل السلفة"""
    advance = get_object_or_404(Advance, pk=pk)
    return render(request, 'hr/advance/detail.html', {'advance': advance})


@login_required
def advance_approve(request, pk):
    """اعتماد السلفة"""
    advance = get_object_or_404(Advance, pk=pk)
    if request.method == 'POST':
        advance.status = 'approved'
        advance.approved_by = request.user
        advance.approved_at = date.today()
        advance.save()
        messages.success(request, 'تم اعتماد السلفة بنجاح')
        return redirect('hr:advance_detail', pk=pk)
    return render(request, 'hr/advance/approve.html', {'advance': advance})


@login_required
def advance_reject(request, pk):
    """رفض السلفة"""
    advance = get_object_or_404(Advance, pk=pk)
    if request.method == 'POST':
        advance.status = 'rejected'
        advance.save()
        messages.success(request, 'تم رفض السلفة')
        return redirect('hr:advance_detail', pk=pk)
    return render(request, 'hr/advance/reject.html', {'advance': advance})


@login_required
def salary_settings(request):
    """إعدادات الرواتب"""
    salaries = Salary.objects.all()
    return render(request, 'hr/salary/settings.html', {'salaries': salaries})
