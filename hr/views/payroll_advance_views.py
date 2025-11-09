"""
Views إدارة الرواتب والسلف
"""
from .base_imports import *
from ..models import Payroll, Advance, Employee, Salary
from ..forms.payroll_forms import PayrollProcessForm
from ..services.payroll_service import PayrollService
from ..decorators import can_view_salaries, can_process_payroll, hr_manager_required
from django.core.paginator import Paginator
from django.db.models import Count, Sum, Q
from datetime import date
import logging

logger = logging.getLogger(__name__)

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
@can_view_salaries
def payroll_list(request):
    """قائمة كشوف الرواتب"""
    # Query Optimization
    payrolls = Payroll.objects.select_related(
        'employee',
        'employee__department',
        'employee__job_title',
        'salary'
    ).all()
    
    # Pagination - 50 راتب لكل صفحة
    paginator = Paginator(payrolls, 50)
    page = request.GET.get('page', 1)
    payrolls_page = paginator.get_page(page)
    
    context = {
        'payrolls': payrolls_page,
        
        # بيانات الهيدر الموحد
        'page_title': 'كشوف الرواتب',
        'page_subtitle': 'إدارة ومعالجة رواتب الموظفين',
        'page_icon': 'fas fa-money-bill-wave',
        'header_buttons': [
            {
                'url': '#',
                'icon': 'fa-calculator',
                'text': 'معالجة رواتب شهر',
                'class': 'btn-primary',
                'toggle': 'modal',
                'target': '#processPayrollModal',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'كشوف الرواتب', 'active': True},
        ],
    }
    return render(request, 'hr/payroll/list.html', context)


@login_required
def payroll_run_list(request):
    """قائمة مسيرات الرواتب"""
    # جمع الرواتب حسب الشهر
    payroll_runs = Payroll.objects.values('month').annotate(
        total_employees=Count('id'),
        total_amount=Sum('net_salary'),
        paid_count=Count('id', filter=Q(status='paid'))
    ).order_by('-month')
    
    context = {
        'payroll_runs': payroll_runs,
        'page_title': 'مسيرات الرواتب',
        'page_subtitle': 'متابعة مسيرات الرواتب الشهرية',
        'page_icon': 'fas fa-money-check-alt',
        'header_buttons': [
            {
                'url': reverse('hr:payroll_run_process'),
                'icon': 'fa-calculator',
                'text': 'معالجة رواتب شهر',
                'class': 'btn-primary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'مسيرات الرواتب', 'active': True},
        ],
    }
    return render(request, 'hr/payroll/run_list.html', context)


@login_required
@can_process_payroll
def payroll_run_process(request):
    """معالجة مسيرة رواتب جديدة"""
    if request.method == 'POST':
        form = PayrollProcessForm(request.POST)
        if form.is_valid():
            try:
                month_str = form.cleaned_data['month']
                department = form.cleaned_data.get('department')
                
                logger.info(f"بدء معالجة رواتب شهر {month_str} بواسطة {request.user.username}")
                
                results = PayrollService.process_monthly_payroll(
                    month_str,
                    request.user
                )
                
                # حساب النتائج
                success_count = sum(1 for r in results if r['success'])
                fail_count = len(results) - success_count
                
                # رسائل النجاح والفشل
                if success_count > 0:
                    messages.success(request, f'تم معالجة {success_count} راتب بنجاح')
                
                if fail_count > 0:
                    messages.warning(request, f'فشلت معالجة {fail_count} راتب')
                    # عرض تفاصيل الأخطاء
                    for result in results:
                        if not result['success']:
                            messages.error(
                                request,
                                f"{result['employee'].get_full_name_ar()}: {result['error']}"
                            )
                
                logger.info(f"انتهت معالجة الرواتب - النجاح: {success_count}, الفشل: {fail_count}")
                return redirect('hr:payroll_run_detail', month=month_str)
                
            except ValueError as e:
                logger.error(f"خطأ في البيانات عند معالجة الرواتب: {str(e)}")
                messages.error(request, f'خطأ في البيانات: {str(e)}')
            except Exception as e:
                logger.exception(f"خطأ غير متوقع في معالجة الرواتب: {str(e)}")
                messages.error(request, f'حدث خطأ غير متوقع: {str(e)}')
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء في النموذج')
    else:
        form = PayrollProcessForm()
    
    context = {
        'form': form,
        'page_title': 'معالجة رواتب شهر',
        'page_subtitle': 'إنشاء مسيرة رواتب جديدة',
        'page_icon': 'fas fa-calculator',
        'header_buttons': [
            {
                'url': reverse('hr:payroll_run_list'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'مسيرات الرواتب', 'url': reverse('hr:payroll_run_list'), 'icon': 'fas fa-money-check-alt'},
            {'title': 'معالجة رواتب', 'active': True},
        ],
    }
    return render(request, 'hr/payroll/run_process.html', context)


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
        'page_title': f'مسيرة رواتب {month}',
        'page_subtitle': f'تفاصيل رواتب شهر {month}',
        'page_icon': 'fas fa-file-invoice-dollar',
        'header_buttons': [
            {
                'url': reverse('hr:payroll_run_list'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'مسيرات الرواتب', 'url': reverse('hr:payroll_run_list'), 'icon': 'fas fa-money-check-alt'},
            {'title': f'مسيرة {month}', 'active': True},
        ],
    }
    return render(request, 'hr/payroll/run_detail.html', context)


@login_required
def payroll_detail(request, pk):
    """تفاصيل كشف الراتب"""
    payroll = get_object_or_404(Payroll, pk=pk)
    
    # إعداد الأزرار
    header_buttons = []
    
    if payroll.status == 'calculated':
        header_buttons.append({
            'url': '#',
            'icon': 'fa-check',
            'text': 'اعتماد',
            'class': 'btn-success',
        })
    
    header_buttons.extend([
        {
            'onclick': 'window.print()',
            'icon': 'fa-print',
            'text': 'طباعة',
            'class': 'btn-info',
        },
        {
            'url': reverse('hr:payroll_list'),
            'icon': 'fa-arrow-right',
            'text': 'رجوع',
            'class': 'btn-secondary',
        },
    ])
    
    context = {
        'payroll': payroll,
        
        # بيانات الهيدر الموحد
        'page_title': f'كشف راتب - {payroll.month.strftime("%Y-%m")}',
        'page_subtitle': 'تفاصيل كشف الراتب',
        'page_icon': 'fas fa-money-bill-wave',
        'header_buttons': header_buttons,
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'كشوف الرواتب', 'url': reverse('hr:payroll_list'), 'icon': 'fas fa-money-bill-wave'},
            {'title': 'تفاصيل', 'active': True},
        ],
    }
    return render(request, 'hr/payroll/detail.html', context)


# ==================== السلف ====================

@login_required
def advance_list(request):
    """قائمة السلف"""
    advances = Advance.objects.select_related('employee').all()
    
    # إحصائيات
    total_advances = advances.count()
    pending_advances = advances.filter(status='pending').count()
    approved_advances = advances.filter(status='approved').count()
    deducted_advances = advances.filter(status='deducted').count()
    
    context = {
        'advances': advances,
        'total_advances': total_advances,
        'pending_advances': pending_advances,
        'approved_advances': approved_advances,
        'deducted_advances': deducted_advances,
        
        # بيانات الهيدر الموحد
        'page_title': 'السلف',
        'page_subtitle': 'إدارة سلف الموظفين والخصومات',
        'page_icon': 'fas fa-hand-holding-usd',
        'header_buttons': [
            {
                'url': reverse('hr:advance_request'),
                'icon': 'fa-plus',
                'text': 'طلب سلفة',
                'class': 'btn-primary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'السلف', 'active': True},
        ],
    }
    return render(request, 'hr/advance/list.html', context)


@login_required
def advance_request(request):
    """طلب سلفة جديدة"""
    if request.method == 'POST':
        try:
            # الحصول على البيانات من الفورم
            employee_id = request.POST.get('employee')
            amount = request.POST.get('amount')
            reason = request.POST.get('reason')
            
            # التحقق من البيانات
            if not employee_id or not amount or not reason:
                messages.error(request, 'جميع الحقول مطلوبة')
                return redirect('hr:advance_request')
            
            # إنشاء السلفة
            employee = Employee.objects.get(pk=employee_id)
            advance = Advance.objects.create(
                employee=employee,
                amount=amount,
                reason=reason,
                status='pending'
            )
            
            messages.success(request, f'تم تقديم طلب السلفة بنجاح - المبلغ: {amount} جنيه')
            return redirect('hr:advance_list')
            
        except Employee.DoesNotExist:
            messages.error(request, 'الموظف غير موجود')
            return redirect('hr:advance_request')
        except Exception as e:
            messages.error(request, f'حدث خطأ: {str(e)}')
            return redirect('hr:advance_request')
    
    # الحصول على قائمة الموظفين النشطين
    employees = Employee.objects.filter(status='active').order_by('first_name_ar')
    
    context = {
        'employees': employees,
        
        # بيانات الهيدر الموحد
        'page_title': 'طلب سلفة جديدة',
        'page_subtitle': 'تقديم طلب سلفة للموظف',
        'page_icon': 'fas fa-hand-holding-usd',
        'header_buttons': [
            {
                'url': reverse('hr:advance_list'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'السلف', 'url': reverse('hr:advance_list'), 'icon': 'fas fa-hand-holding-usd'},
            {'title': 'طلب سلفة', 'active': True},
        ],
    }
    return render(request, 'hr/advance/request.html', context)


@login_required
def advance_detail(request, pk):
    """تفاصيل السلفة"""
    advance = get_object_or_404(Advance, pk=pk)
    
    context = {
        'advance': advance,
        
        # بيانات الهيدر الموحد
        'page_title': 'تفاصيل السلفة',
        'page_subtitle': f'{advance.employee.get_full_name_ar()} - {advance.amount} جنيه',
        'page_icon': 'fas fa-hand-holding-usd',
        'header_buttons': [
            {
                'url': reverse('hr:advance_list'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'السلف', 'url': reverse('hr:advance_list'), 'icon': 'fas fa-hand-holding-usd'},
            {'title': 'تفاصيل السلفة', 'active': True},
        ],
    }
    return render(request, 'hr/advance/detail.html', context)


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
