"""
Views إدارة الرواتب والسلف
"""
from .base_imports import *
from ..models import Payroll, Advance, Employee, Contract
from ..forms.payroll_forms import PayrollProcessForm
from ..services.payroll_service import PayrollService
from ..decorators import can_view_salaries, can_process_payroll, can_pay_payroll
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.http import JsonResponse
from django.utils.translation import gettext_lazy as _
from django.db import transaction
from django.db.models import Q
from django.core.paginator import Paginator
from datetime import datetime
import logging
from core.templatetags.pricing_filters import remove_trailing_zeros

# استيراد view تعديل البنود
from .payroll_edit_lines_view import payroll_edit_lines

logger = logging.getLogger(__name__)

__all__ = [
    'payroll_list',
    'payroll_run_list',
    'payroll_run_process',
    'payroll_run_detail',
    'payroll_run_delete',
    'payroll_detail',
    'payroll_edit_lines',
    'payroll_approve',
    'payroll_delete',
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
    """قائمة قسائم الرواتب"""
    from datetime import datetime, date
    
    # الحصول على السنة المختارة من الـ GET request
    selected_year = request.GET.get('year', date.today().year)
    try:
        selected_year = int(selected_year)
    except ValueError:
        selected_year = date.today().year
    
    # Query Optimization
    payrolls = Payroll.objects.select_related(
        'employee',
        'employee__department',
        'employee__job_title',
        'contract'
    ).filter(month__year=selected_year)
    
    # الحصول على جميع السنوات المتاحة (فريدة ومرتبة)
    available_years = Payroll.objects.dates('month', 'year').order_by('-month')
    # تحويل إلى قائمة سنوات فريدة
    unique_years = []
    seen_years = set()
    for date_obj in available_years:
        if date_obj.year not in seen_years:
            unique_years.append(date_obj.year)
            seen_years.add(date_obj.year)
    
    # الفلترة حسب الشهر
    month_filter = request.GET.get('month', '')
    if month_filter:
        try:
            # فلترة حسب رقم الشهر فقط (01-12)
            month_number = int(month_filter)
            payrolls = payrolls.filter(month__month=month_number)
        except ValueError:
            pass
    
    # الفلترة حسب الحالة
    status_filter = request.GET.get('status', '')
    if status_filter:
        payrolls = payrolls.filter(status=status_filter)
    
    # البحث
    search = request.GET.get('search', '')
    if search:
        payrolls = payrolls.filter(
            Q(employee__first_name_ar__icontains=search) |
            Q(employee__last_name_ar__icontains=search) |
            Q(employee__employee_number__icontains=search)
        )
    
    # تعريف رؤوس الجدول
    table_headers = [
        {'key': 'employee_name', 'label': 'الموظف', 'sortable': True, 'class': 'text-center fw-bold'},
        {'key': 'employee_number', 'label': 'رقم الموظف', 'sortable': True, 'class': 'text-center'},
        {'key': 'month_display', 'label': 'الشهر', 'sortable': True, 'class': 'text-center'},
        {'key': 'basic_salary', 'label': 'الأساسي', 'format': 'number', 'class': 'text-end'},
        {'key': 'total_earnings_display', 'label': 'المستحقات', 'format': 'number', 'class': 'text-end'},
        {'key': 'total_deductions', 'label': 'الخصومات', 'format': 'number', 'class': 'text-end'},
        {'key': 'net_salary', 'label': 'صافي الراتب', 'format': 'currency', 'class': 'text-end fw-bold'},
        {'key': 'status_display', 'label': 'الحالة', 'format': 'html', 'class': 'text-center'},
    ]
    
    # تعريف أزرار الإجراءات
    table_actions = [
        {'url': 'hr:payroll_detail', 'icon': 'fa-eye', 'label': 'عرض', 'class': 'action-view'},
        {'url': 'hr:payroll_approve', 'icon': 'fa-check', 'label': 'اعتماد', 'class': 'action-approve', 'modal': True, 'condition': 'status != \'approved\' and status != \'paid\''},
        {'url': 'hr:payroll_pay', 'icon': 'fa-money-bill-wave', 'label': 'دفع', 'class': 'action-pay', 'modal': True, 'condition': 'status == \'approved\''},
        {'url': 'hr:payroll_delete', 'icon': 'fa-trash-alt', 'label': 'حذف', 'class': 'action-delete', 'modal': True, 'condition': 'status != \'approved\' and status != \'paid\''},
    ]
    
    # إضافة بيانات إضافية للعرض
    for payroll in payrolls:
        payroll.employee_name = payroll.employee.get_full_name_ar()
        payroll.employee_number = payroll.employee.employee_number
        
        # تنسيق الشهر (بدون اليوم)
        payroll.month_display = payroll.month.strftime('%Y-%m')
        
        # تطبيق فلتر الأرقام على الأساسي والمستحقات والخصومات
        payroll.basic_salary = remove_trailing_zeros(payroll.basic_salary)
        payroll.total_earnings_display = remove_trailing_zeros(payroll.total_earnings)
        payroll.total_deductions = remove_trailing_zeros(payroll.total_deductions)
        
        # عرض الحالة
        status_badges = {
            'draft': '<span class="badge bg-secondary">مسودة</span>',
            'calculated': '<span class="badge bg-info">محسوب</span>',
            'approved': '<span class="badge bg-primary">معتمد</span>',
            'paid': '<span class="badge bg-success">مدفوع</span>',
        }
        payroll.status_display = status_badges.get(payroll.status, '<span class="badge bg-secondary">غير محدد</span>')
    
    # Pagination - 50 راتب لكل صفحة
    paginator = Paginator(payrolls, 50)
    page = request.GET.get('page', 1)
    payrolls_page = paginator.get_page(page)
    
    context = {
        'payrolls': payrolls_page,
        'table_headers': table_headers,
        'table_actions': table_actions,
        'currency_symbol': 'ج.م',
        'available_years': unique_years,
        'selected_year': selected_year,
        
        # بيانات الهيدر الموحد
        'page_title': 'قسائم الرواتب',
        'page_subtitle': 'إدارة قسائم رواتب الموظفين',
        'page_icon': 'fas fa-money-bill-wave',
        'header_buttons': [
            {
                'url': reverse('hr:payroll_run_list'),
                'icon': 'fa-list',
                'text': 'مسيرات الرواتب',
                'class': 'btn-primary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'قسائم الرواتب', 'active': True},
        ],
    }
    return render(request, 'hr/payroll/list.html', context)


@login_required
def payroll_run_list(request):
    """قائمة مسيرات الرواتب"""
    from datetime import datetime
    
    # الحصول على السنة المختارة من الفلتر
    selected_year = request.GET.get('year')
    if selected_year:
        selected_year = int(selected_year)
        # جمع الرواتب حسب الشهر مع فلترة بالسنة
        payroll_runs = Payroll.objects.filter(
            month__year=selected_year
        ).values('month').annotate(
            total_employees=Count('id'),
            total_amount=Sum('net_salary'),
            paid_count=Count('id', filter=Q(status='paid'))
        ).order_by('-month')
    else:
        # عرض جميع السنوات
        selected_year = None
        payroll_runs = Payroll.objects.values('month').annotate(
            total_employees=Count('id'),
            total_amount=Sum('net_salary'),
            paid_count=Count('id', filter=Q(status='paid'))
        ).order_by('-month')
    
    # الحصول على قائمة السنوات المتاحة
    available_years = Payroll.objects.dates('month', 'year', order='DESC')
    
    # تحويل QuerySet لقائمة من الـ dictionaries مع إضافة حقل status و month_str
    runs_list = []
    for run in payroll_runs:
        run_dict = dict(run)
        # إضافة حقل status بناءً على paid_count
        if run['paid_count'] == run['total_employees']:
            run_dict['status'] = 'completed'
        elif run['paid_count'] > 0:
            run_dict['status'] = 'partial'
        else:
            run_dict['status'] = 'pending'
        # إضافة month_str للاستخدام في URLs
        run_dict['month_str'] = run['month'].strftime('%Y-%m')
        # إضافة حقل can_delete للتحكم في ظهور زر الحذف
        run_dict['can_delete'] = run['paid_count'] == 0
        runs_list.append(run_dict)
    
    # إعداد headers للجدول الموحد
    runs_headers = [
        {'key': 'month_str', 'label': 'الشهر', 'sortable': True},
        {'key': 'total_employees', 'label': 'عدد الموظفين', 'sortable': True},
        {'key': 'total_amount', 'label': 'إجمالي المبلغ', 'format': 'currency', 'sortable': True},
        {'key': 'paid_count', 'label': 'المدفوع', 'template': 'components/cells/payroll_paid_count.html', 'sortable': True},
        {'key': 'status', 'label': 'الحالة', 'format': 'status', 'sortable': True},
    ]
    
    # أزرار الإجراءات
    runs_action_buttons = [
        {'url': 'hr:payroll_run_detail', 'icon': 'fa-eye', 'label': 'عرض', 'class': 'action-view'},
        {
            'url': 'hr:payroll_run_delete', 
            'icon': 'fa-trash-alt', 
            'label': 'حذف', 
            'class': 'action-delete',
            'condition': 'can_delete'  # يظهر فقط إذا can_delete = True
        },
    ]
    
    # حساب الإحصائيات
    total_runs = len(runs_list)
    completed_runs = sum(1 for run in runs_list if run['status'] == 'completed')
    partial_runs = sum(1 for run in runs_list if run['status'] == 'partial')
    total_amount = sum(run['total_amount'] or 0 for run in runs_list)
    
    context = {
        'payroll_runs': runs_list,
        'runs_headers': runs_headers,
        'runs_action_buttons': runs_action_buttons,
        'available_years': available_years,
        'selected_year': selected_year,
        'total_runs': total_runs,
        'completed_runs': completed_runs,
        'partial_runs': partial_runs,
        'total_amount': total_amount,
        'page_title': 'مسيرات الرواتب',
        'page_subtitle': 'متابعة مسيرات الرواتب الشهرية',
        'page_icon': 'fas fa-money-check-alt',
        'header_buttons': [
            {
                'url': reverse('hr:payroll_run_process'),
                'icon': 'fa-plus-circle',
                'text': 'إنشاء مسيرة رواتب',
                'class': 'btn-primary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'مسيرات الرواتب', 'active': True},
        ],
        'currency_symbol': 'ج.م',
    }
    return render(request, 'hr/payroll/run_list.html', context)


@login_required
@can_process_payroll
def payroll_run_process(request):
    """معالجة مسيرة رواتب جديدة مع معاينة"""
    if request.method == 'POST':
        action = request.POST.get('action', 'preview')
        form = PayrollProcessForm(request.POST)
        
        if form.is_valid():
            month_str = form.cleaned_data['month']
            department = form.cleaned_data.get('department')
            
            # الحصول على الموظفين
            from datetime import datetime
            
            # تحويل month_str (YYYY-MM) إلى تاريخ (أول يوم في الشهر)
            month_date = datetime.strptime(month_str, '%Y-%m').date()
            
            employees = Employee.objects.filter(status='active')
            if department:
                employees = employees.filter(department=department)
            
            # استبعاد الموظفين اللي عندهم راتب في نفس الشهر
            from ..models import Payroll
            processed_employee_ids = Payroll.objects.filter(
                month=month_date
            ).values_list('employee_id', flat=True)
            
            employees = employees.exclude(id__in=processed_employee_ids)
            
            # فلترة الموظفين: فقط من لديهم عقد نشط وبنود راتب نشطة
            # يدعم الموظفين المعينين في منتصف الشهر (راتب جزئي)
            valid_employee_ids = []
            
            # حساب آخر يوم في الشهر
            from calendar import monthrange
            last_day = monthrange(month_date.year, month_date.month)[1]
            month_end_date = month_date.replace(day=last_day)
            
            for emp in employees:
                contract = emp.contracts.filter(status='active').first()
                if contract:
                    # البحث عن بنود نشطة تبدأ في أي وقت خلال الشهر
                    components = emp.salary_components.filter(
                        is_active=True,
                        effective_from__lte=month_end_date  # بدأ قبل أو خلال الشهر
                    ).filter(
                        Q(effective_to__isnull=True) | Q(effective_to__gte=month_date)  # لم ينتهي أو ينتهي بعد بداية الشهر
                    )
                    
                    # تشخيص: طباعة معلومات الموظف
                    logger.info(f"🔍 فحص موظف: {emp.get_full_name_ar()} (ID={emp.id})")
                    logger.info(f"   عقد نشط: {contract.contract_number}")
                    logger.info(f"   عدد بنود الراتب النشطة: {components.count()}")
                    if components.count() == 0:
                        # فحص جميع البنود بدون فلترة
                        all_components = emp.salary_components.all()
                        logger.warning(f"   ⚠️ لا توجد بنود نشطة! إجمالي البنود: {all_components.count()}")
                        for comp in all_components:
                            logger.warning(f"      - {comp.name}: is_active={comp.is_active}, effective_from={comp.effective_from}, effective_to={comp.effective_to}")
                    
                    if components.exists():
                        valid_employee_ids.append(emp.id)
                        # تحديد إذا كان راتب جزئي
                        if components.first().effective_from > month_date:
                            logger.info(f"   ✅ تمت الإضافة للمعالجة (راتب جزئي من {components.first().effective_from})")
                        else:
                            logger.info(f"   ✅ تمت الإضافة للمعالجة (راتب كامل)")
                    else:
                        logger.warning(f"   ❌ لم تتم الإضافة (لا توجد بنود راتب نشطة)")
            
            # تحديث قائمة الموظفين لتشمل فقط الموظفين الصالحين
            employees = employees.filter(id__in=valid_employee_ids)
            
            # معاينة فقط
            if action == 'preview':
                # حساب تقدير التكلفة
                from decimal import Decimal
                
                estimated_cost = Decimal('0')
                employee_previews = []
                
                for emp in employees:
                    # حساب تقديري سريع باستخدام نفس منطق PayrollService
                    contract = emp.contracts.filter(status='active').first()
                    if contract:
                        components = emp.salary_components.filter(
                            is_active=True,
                            effective_from__lte=month_end_date
                        ).filter(
                            Q(effective_to__isnull=True) | Q(effective_to__gte=month_date)
                        )
                        
                        # حساب الراتب الأساسي من العقد أولاً
                        if contract.basic_salary:
                            basic_salary = Decimal(str(contract.basic_salary))
                        else:
                            basic_component = components.filter(is_basic=True).first()
                            basic_salary = basic_component.amount if basic_component else Decimal('0')
                        
                        # حساب أيام العمل الفعلية (راتب جزئي إذا معين في منتصف الشهر)
                        contract_start = contract.start_date
                        if contract_start.year == month_date.year and contract_start.month == month_date.month:
                            # راتب جزئي
                            days_from_start = last_day - contract_start.day + 1
                            worked_days = days_from_start
                        else:
                            # راتب كامل
                            worked_days = last_day
                        
                        # إعداد السياق للحساب (نفس منطق PayrollService)
                        context = {
                            'basic_salary': basic_salary,
                            'worked_days': worked_days,
                            'month': month_date
                        }
                        
                        # حساب المستحقات (مع الصيغ والنسب)
                        earnings_components = components.filter(component_type='earning')
                        earnings_sum = sum(c.calculate_amount(context) for c in earnings_components)
                        total_earnings = basic_salary + earnings_sum
                        
                        # حساب الاستقطاعات (مع الصيغ والنسب)
                        deductions_components = components.filter(component_type='deduction')
                        total_deductions = sum(c.calculate_amount(context) for c in deductions_components)
                        
                        net = total_earnings - total_deductions
                        
                        estimated_cost += net
                        
                        # تحديد نوع الراتب
                        is_partial = contract_start.year == month_date.year and contract_start.month == month_date.month
                        
                        employee_previews.append({
                            'employee': emp,
                            'basic_salary': basic_salary,
                            'total_earnings': total_earnings,
                            'total_deductions': total_deductions,
                            'estimated_net': net,
                            'components_count': components.count(),
                            'worked_days': worked_days,
                            'total_days': last_day,
                            'is_partial': is_partial,
                            'start_date': contract_start if is_partial else None
                        })
                
                context = {
                    'form': form,
                    'month_str': month_str,
                    'employees': employee_previews,
                    'total_employees': len(employee_previews),
                    'estimated_cost': estimated_cost,
                    'is_preview': True,
                    'page_title': 'معاينة معالجة الرواتب',
                    'page_subtitle': f'شهر {month_str}',
                    'page_icon': 'fas fa-eye',
                    'breadcrumb_items': [
                        {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
                        {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
                        {'title': 'مسيرات الرواتب', 'url': reverse('hr:payroll_run_list'), 'icon': 'fas fa-money-check-alt'},
                        {'title': 'معاينة', 'active': True},
                    ],
                }
                return render(request, 'hr/payroll/run_preview.html', context)
            
            # المعالجة الفعلية
            elif action == 'process':
                try:
                    logger.info(f"بدء إنشاء مسيرة رواتب {month_str} بواسطة {request.user.username}")
                    
                    # تمرير قائمة الموظفين المفلترة للـ service
                    results = PayrollService.process_monthly_payroll(
                        month_date,
                        request.user,
                        employees  # ← تمرير الموظفين المفلترين
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
        # التحقق من وجود شهر في الـ query parameter
        initial_month = request.GET.get('month')
        if initial_month:
            form = PayrollProcessForm(initial={'month': initial_month})
        else:
            form = PayrollProcessForm()
    
    context = {
        'form': form,
        'page_title': 'إنشاء مسيرة رواتب',
        'page_subtitle': 'إنشاء مسيرة رواتب جديدة',
        'page_icon': 'fas fa-plus-circle',
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
            {'title': 'إنشاء مسيرة', 'active': True},
        ],
    }
    return render(request, 'hr/payroll/run_process.html', context)


@login_required
def payroll_run_detail(request, month):
    """تفاصيل مسيرة رواتب شهر محدد"""
    from datetime import datetime
    
    # تحويل month (YYYY-MM) إلى تاريخ (أول يوم في الشهر)
    month_date = datetime.strptime(month, '%Y-%m').date()
    
    # أسماء الشهور بالعربي
    arabic_months = {
        1: 'يناير', 2: 'فبراير', 3: 'مارس', 4: 'أبريل',
        5: 'مايو', 6: 'يونيو', 7: 'يوليو', 8: 'أغسطس',
        9: 'سبتمبر', 10: 'أكتوبر', 11: 'نوفمبر', 12: 'ديسمبر'
    }
    
    # تنسيق اسم الشهر بالعربي
    month_name = f"{arabic_months[month_date.month]} {month_date.year}"
    
    payrolls = Payroll.objects.filter(month=month_date).select_related('employee', 'employee__department', 'contract')
    
    stats = payrolls.aggregate(
        total_employees=Count('id'),
        total_gross=Sum('gross_salary'),
        total_deductions=Sum('total_deductions'),
        total_net=Sum('net_salary'),
        paid_count=Count('id', filter=Q(status='paid'))
    )
    
    # حساب عدد الموظفين النشطين
    total_active_employees = Employee.objects.filter(status='active').count()
    current_payrolls_count = payrolls.count()
    remaining_employees = total_active_employees - current_payrolls_count
    
    # إعداد الأزرار
    header_buttons = [
        {
            'url': reverse('hr:payroll_run_list'),
            'icon': 'fa-arrow-right',
            'text': 'رجوع',
            'class': 'btn-secondary',
        },
    ]
    
    # إضافة زر "إضافة قسائم متبقية" إذا كان هناك موظفين بدون قسائم
    if remaining_employees > 0:
        header_buttons.insert(0, {
            'url': reverse('hr:payroll_run_process') + f'?month={month}',
            'icon': 'fa-plus-circle',
            'text': f'إضافة قسائم متبقية ({remaining_employees})',
            'class': 'btn-success',
        })
    
    # إعداد headers لجدول قسائم الرواتب
    payslips_headers = [
        {'key': 'employee.first_name_ar', 'label': 'الموظف', 'sortable': True, 'template': 'components/cells/employee_name.html'},
        {'key': 'employee.department.name_ar', 'label': 'القسم', 'sortable': True},
        {'key': 'basic_salary', 'label': 'الأساسي', 'format': 'number', 'sortable': True},
        {'key': 'total_earnings', 'label': 'المستحقات', 'format': 'number', 'sortable': True},
        {'key': 'total_deductions', 'label': 'الخصومات', 'format': 'number', 'sortable': True},
        {'key': 'net_salary', 'label': 'الصافي', 'format': 'currency', 'sortable': True},
        {'key': 'status', 'label': 'الحالة', 'format': 'status', 'sortable': True},
    ]
    
    # أزرار الإجراءات لجدول قسائم الرواتب
    payslips_action_buttons = [
        {'url': 'hr:payroll_detail', 'icon': 'fa-eye', 'label': 'عرض', 'class': 'action-view'},
    ]
    
    # إعداد headers لجدول المدفوعات
    payments_headers = [
        {'key': 'employee.first_name_ar', 'label': 'الموظف', 'sortable': True, 'template': 'components/cells/employee_name.html'},
        {'key': 'net_salary', 'label': 'المبلغ المدفوع', 'format': 'currency', 'sortable': True},
        {'key': 'payment_method', 'label': 'طريقة الدفع', 'format': 'status', 'sortable': True},
        {'key': 'payment_date', 'label': 'تاريخ الدفع', 'format': 'date', 'sortable': True},
        {'key': 'notes', 'label': 'ملاحظات', 'ellipsis': True},
    ]
    
    # فلترة المدفوعات فقط
    paid_payrolls = payrolls.filter(status='paid')
    
    context = {
        'month': month,
        'month_name': month_name,
        'payrolls': payrolls,
        'paid_payrolls': paid_payrolls,
        'stats': stats,
        'remaining_employees': remaining_employees,
        'page_title': f'مسيرة رواتب {month_name}',
        'page_subtitle': f'تفاصيل رواتب شهر {month_name}',
        'page_icon': 'fas fa-file-invoice-dollar',
        'header_buttons': header_buttons,
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'مسيرات الرواتب', 'url': reverse('hr:payroll_run_list'), 'icon': 'fas fa-money-check-alt'},
            {'title': f'مسيرة {month_name}', 'active': True},
        ],
        # بيانات الجداول الموحدة
        'payslips_headers': payslips_headers,
        'payslips_action_buttons': payslips_action_buttons,
        'payments_headers': payments_headers,
        'currency_symbol': 'ج.م',
    }
    return render(request, 'hr/payroll/run_detail.html', context)


@login_required
def payroll_detail(request, pk):
    """تفاصيل قسيمة الراتب مع PayrollLines"""
    payroll = get_object_or_404(Payroll, pk=pk)
    
    # جلب جميع الأسطر (PayrollLines)
    lines = payroll.lines.select_related('salary_component').order_by('order')
    
    # تصنيف البنود
    earnings = lines.filter(component_type='earning')
    deductions = lines.filter(component_type='deduction')
    
    # حساب الإجماليات من Lines (إذا كانت موجودة)
    if lines.exists():
        earnings_sum = sum(line.amount for line in earnings)
        # إضافة الراتب الأساسي لإجمالي المستحقات
        total_earnings = payroll.basic_salary + earnings_sum
        total_deductions = sum(line.amount for line in deductions)
        has_lines = True
    else:
        # استخدام البيانات القديمة إذا لم توجد Lines
        total_earnings = payroll.total_additions or 0
        total_deductions = payroll.total_deductions or 0
        has_lines = False
    
    # تحديد ما إذا كان الراتب جزئي (بدأ العمل في نفس شهر الراتب)
    is_partial_salary = False
    partial_reason = ""
    
    if payroll.contract and payroll.contract.start_date:
        contract_start = payroll.contract.start_date
        month_date = payroll.month
        
        # إذا بدأ العقد في نفس شهر الراتب
        if contract_start.year == month_date.year and contract_start.month == month_date.month:
            is_partial_salary = True
            partial_reason = f"بدء العمل من {contract_start.strftime('%Y-%m-%d')}"
    
    # إعداد الأزرار
    header_buttons = []
    
    # زر تعديل البنود (يظهر فقط قبل الاعتماد)
    if payroll.status in ['draft', 'calculated']:
        header_buttons.append({
            'url': reverse('hr:payroll_edit_lines', kwargs={'pk': payroll.pk}),
            'icon': 'fa-edit',
            'text': 'تعديل البنود',
            'class': 'btn-warning',
        })
    
    if payroll.status == 'calculated':
        header_buttons.append({
            'url': '#',
            'toggle': 'modal',
            'target': '#approvePayrollModal',
            'icon': 'fa-check',
            'text': 'اعتماد',
            'class': 'btn-success',
        })
    
    # زر الدفع (يظهر فقط للقسائم المعتمدة وغير المدفوعة)
    if payroll.status == 'approved':
        header_buttons.append({
            'url': '#',
            'toggle': 'modal',
            'target': '#paymentModal',
            'icon': 'fa-money-bill-wave',
            'text': 'دفع الراتب',
            'class': 'btn-primary',
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
        'lines': lines,
        'earnings': earnings,
        'deductions': deductions,
        'total_earnings': total_earnings,
        'total_deductions': total_deductions,
        'has_lines': has_lines,
        'is_partial_salary': is_partial_salary,
        'partial_reason': partial_reason,
    }
    
    # إضافة بيانات المودال للقسائم المعتمدة
    if payroll.status == 'approved':
        # استيراد ChartOfAccounts هنا لتجنب الاستيراد الدائري
        from financial.models import ChartOfAccounts
        
        # الحصول على حسابات الصناديق والبنوك
        payment_accounts = ChartOfAccounts.objects.filter(
            Q(is_cash_account=True) | Q(is_bank_account=True),
            is_active=True
        ).order_by('name')
        
        context['payment_accounts'] = payment_accounts
    
    # إضافة بيانات الهيدر الموحد
    context.update({
        # بيانات الهيدر الموحد
        'page_title': f'قسيمة راتب {payroll.employee.get_full_name_ar()}',
        'page_subtitle': f'شهر {payroll.month.strftime("%Y-%m")}',
        'page_icon': 'fas fa-file-invoice-dollar',
        'header_buttons': header_buttons,
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'قسائم الرواتب', 'url': reverse('hr:payroll_list'), 'icon': 'fas fa-money-bill-wave'},
            {'title': 'تفاصيل قسيمة الراتب', 'active': True},
        ],
    })
    return render(request, 'hr/payroll/detail.html', context)


@login_required
@can_process_payroll
def payroll_approve(request, pk):
    """اعتماد قسيمة راتب"""
    payroll = get_object_or_404(Payroll, pk=pk)
    
    # التحقق من الحالة
    if payroll.status != 'calculated':
        messages.error(request, 'لا يمكن اعتماد قسيمة راتب غير محسوبة')
        return redirect('hr:payroll_detail', pk=pk)
    
    if request.method == 'POST':
        try:
            # استخدام PayrollService للاعتماد
            PayrollService.approve_payroll(payroll, request.user)
            
            success_message = f'تم اعتماد قسيمة راتب {payroll.employee.get_full_name_ar()} بنجاح'
            logger.info(f"تم اعتماد قسيمة راتب {payroll.pk} بواسطة {request.user.username}")
            
            # إذا كان طلب AJAX، إرجاع JSON
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': success_message})
            
            messages.success(request, success_message)
            return redirect('hr:payroll_detail', pk=pk)
            
        except ValueError as e:
            # أخطاء متوقعة (مثل عدم وجود فترة محاسبية)
            # معالجة الخطأ سواء كان list أو string
            if isinstance(e.args[0], list):
                error_msg = e.args[0][0] if e.args[0] else str(e)
            else:
                error_msg = str(e)
                
            if 'لا توجد فترة محاسبية مفتوحة' in error_msg:
                error_message = 'لا يمكن اعتماد القسيمة: لا توجد فترة محاسبية مفتوحة لهذا الشهر. يرجى فتح فترة محاسبية أولاً من قائمة الفترات المحاسبية.'
            else:
                error_message = f'لا يمكن اعتماد القسيمة: {error_msg}'
            
            logger.warning(f"فشل اعتماد قسيمة الراتب {payroll.pk}: {error_msg}")
            
            # إذا كان طلب AJAX، إرجاع JSON
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': error_message})
            
            messages.error(request, error_message)
            return redirect('hr:payroll_detail', pk=pk)
            
        except Exception as e:
            # معالجة الخطأ سواء كان list أو string
            if hasattr(e, 'args') and e.args and isinstance(e.args[0], list):
                error_msg = e.args[0][0] if e.args[0] else str(e)
            else:
                error_msg = str(e)
            
            # التحقق من نوع الخطأ
            if 'لا توجد فترة محاسبية مفتوحة' in error_msg:
                error_message = 'لا يمكن اعتماد القسيمة: لا توجد فترة محاسبية مفتوحة لهذا الشهر. يرجى فتح فترة محاسبية أولاً من قائمة الفترات المحاسبية.'
                logger.warning(f"فشل اعتماد قسيمة الراتب {payroll.pk}: فترة محاسبية غير متاحة")
            else:
                logger.exception(f"خطأ غير متوقع في اعتماد قسيمة الراتب {payroll.pk}: {error_msg}")
                from django.conf import settings
                if settings.DEBUG:
                    error_message = f'حدث خطأ أثناء الاعتماد: {error_msg}'
                else:
                    error_message = f'حدث خطأ غير متوقع أثناء الاعتماد. يرجى المحاولة مرة أخرى أو الاتصال بالدعم الفني.'
            
            # إذا كان طلب AJAX، إرجاع JSON
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': error_message})
            
            messages.error(request, error_message)
            return redirect('hr:payroll_detail', pk=pk)
    
    # صفحة التأكيد
    context = {
        'payroll': payroll,
        'page_title': 'اعتماد قسيمة الراتب',
        'page_subtitle': f'{payroll.employee.get_full_name_ar()} - {payroll.month.strftime("%Y-%m")}',
        'page_icon': 'fas fa-check-circle',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'قسائم الرواتب', 'url': reverse('hr:payroll_list'), 'icon': 'fas fa-money-bill-wave'},
            {'title': 'اعتماد', 'active': True},
        ],
    }
    return render(request, 'hr/payroll/approve_modal.html', context)


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
@can_process_payroll
def payroll_run_delete(request, month):
    """حذف مسيرة رواتب شهر محدد"""
    from datetime import datetime
    from django.db import transaction
    
    # تحويل month (YYYY-MM) إلى تاريخ
    try:
        month_date = datetime.strptime(month, '%Y-%m').date()
    except ValueError:
        messages.error(request, 'صيغة الشهر غير صحيحة')
        return redirect('hr:payroll_run_list')
    
    # أسماء الشهور بالعربي
    arabic_months = {
        1: 'يناير', 2: 'فبراير', 3: 'مارس', 4: 'أبريل',
        5: 'مايو', 6: 'يونيو', 7: 'يوليو', 8: 'أغسطس',
        9: 'سبتمبر', 10: 'أكتوبر', 11: 'نوفمبر', 12: 'ديسمبر'
    }
    month_name = f"{arabic_months[month_date.month]} {month_date.year}"
    
    # الحصول على جميع قسائم الرواتب للشهر
    payrolls = Payroll.objects.filter(month=month_date).select_related('employee')
    
    if not payrolls.exists():
        messages.warning(request, f'لا توجد قسائم رواتب لشهر {month_name}')
        return redirect('hr:payroll_run_list')
    
    # التحقق من وجود رواتب مدفوعة
    paid_count = payrolls.filter(status='paid').count()
    if paid_count > 0:
        messages.error(request, f'لا يمكن حذف مسيرة الرواتب لأن {paid_count} راتب مدفوع بالفعل')
        return redirect('hr:payroll_run_detail', month=month)
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # حذف جميع قسائم الرواتب للشهر
                deleted_count = payrolls.count()
                payrolls.delete()
                
                messages.success(request, f'تم حذف مسيرة رواتب {month_name} بنجاح ({deleted_count} قسيمة)')
                logger.info(f"تم حذف مسيرة رواتب {month} بواسطة {request.user.username}")
                
                # إذا كان طلب AJAX، إرجاع JSON
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': True, 'message': f'تم حذف مسيرة رواتب {month_name} بنجاح'})
                
                return redirect('hr:payroll_run_list')
        except Exception as e:
            logger.exception(f"خطأ في حذف مسيرة رواتب {month}: {str(e)}")
            
            # إذا كان طلب AJAX، إرجاع JSON
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': f'حدث خطأ: {str(e)}'})
            
            messages.error(request, f'حدث خطأ أثناء الحذف: {str(e)}')
            return redirect('hr:payroll_run_detail', month=month)
    
    # إحصائيات للعرض
    stats = payrolls.aggregate(
        total_employees=Count('id'),
        total_net=Sum('net_salary'),
        approved_count=Count('id', filter=Q(status='approved')),
        calculated_count=Count('id', filter=Q(status='calculated')),
        draft_count=Count('id', filter=Q(status='draft'))
    )
    
    context = {
        'month': month,
        'month_name': month_name,
        'payrolls': payrolls,
        'stats': stats,
        'page_title': f'حذف مسيرة رواتب {month_name}',
        'page_subtitle': f'تأكيد حذف {stats["total_employees"]} قسيمة راتب',
        'page_icon': 'fas fa-trash-alt',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'مسيرات الرواتب', 'url': reverse('hr:payroll_run_list'), 'icon': 'fas fa-money-check-alt'},
            {'title': f'مسيرة {month_name}', 'url': reverse('hr:payroll_run_detail', kwargs={'month': month})},
            {'title': 'حذف', 'active': True},
        ],
    }
    
    return render(request, 'hr/payroll/run_delete.html', context)


@login_required
def salary_settings(request):
    """إعدادات الرواتب"""
    from ..models import SalaryComponent
    salary_components = SalaryComponent.objects.all()
    return render(request, 'hr/salary/settings.html', {'salary_components': salary_components})


@login_required
@can_process_payroll
def payroll_delete(request, pk):
    """حذف قسيمة راتب"""
    payroll = get_object_or_404(Payroll, pk=pk)
    
    # التحقق من إمكانية الحذف
    if payroll.status == 'paid':
        messages.error(request, 'لا يمكن حذف قسيمة راتب مدفوعة')
        return redirect('hr:payroll_list')
    
    if request.method == 'POST':
        try:
            employee_name = payroll.employee.get_full_name_ar()
            month_name = payroll.month.strftime('%Y-%m')
            
            # حذف القسيمة
            payroll.delete()
            
            success_message = f'تم حذف قسيمة راتب {employee_name} لشهر {month_name} بنجاح'
            logger.info(f"تم حذف قسيمة راتب {pk} بواسطة {request.user.username}")
            
            # إذا كان طلب AJAX، إرجاع JSON
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': success_message})
            
            messages.success(request, success_message)
            return redirect('hr:payroll_list')
            
        except Exception as e:
            logger.exception(f"خطأ في حذف قسيمة راتب {pk}: {str(e)}")
            error_message = f'حدث خطأ أثناء الحذف: {str(e)}'
            
            # إذا كان طلب AJAX، إرجاع JSON
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': error_message})
            
            messages.error(request, error_message)
            return redirect('hr:payroll_detail', pk=pk)
    
    context = {
        'payroll': payroll,
        'page_title': f'حذف قسيمة راتب {payroll.employee.get_full_name_ar()}',
        'page_subtitle': f'شهر {payroll.month.strftime("%Y-%m")}',
        'page_icon': 'fas fa-trash-alt',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'قسائم الرواتب', 'url': reverse('hr:payroll_list'), 'icon': 'fas fa-money-bill-wave'},
            {'title': f'قسيمة {payroll.employee.get_full_name_ar()}', 'url': reverse('hr:payroll_detail', kwargs={'pk': pk})},
            {'title': 'حذف', 'active': True},
        ],
    }
    
    return render(request, 'hr/payroll/delete.html', context)
