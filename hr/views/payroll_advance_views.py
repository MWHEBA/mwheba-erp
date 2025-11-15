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
from decimal import Decimal
import logging
from core.templatetags.pricing_filters import remove_trailing_zeros

# استيراد view تعديل البنود
from .payroll_edit_lines_view import payroll_edit_lines

logger = logging.getLogger(__name__)

__all__ = [
    'payroll_list',
    'payroll_detail',
    'payroll_edit_lines',
    'payroll_approve',
    'payroll_delete',
    'advance_list',
    'advance_request',
    'advance_detail',
    'advance_approve',
    'advance_reject',
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
                'url': reverse('hr:integrated_payroll_dashboard'),
                'icon': 'fa-list',
                'text': 'معالجة الرواتب',
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
        # إذا كان هناك سطر للراتب الأساسي ضمن البنود، لا نعرضه ضمن القائمة لتجنب التكرار
        has_basic_line = earnings.filter(code='BASIC_SALARY').exists()
        earnings_display = earnings.exclude(code='BASIC_SALARY')

        # إجمالي المستحقات: إذا لا يوجد سطر أساسي، أضف الراتب الأساسي من القسيمة
        earnings_sum = sum(line.amount for line in earnings)
        if has_basic_line:
            total_earnings = earnings_sum
        else:
            total_earnings = payroll.basic_salary + earnings_sum

        total_deductions = sum(line.amount for line in deductions)
        has_lines = True
        # استبدال earnings في العرض بالقائمة المعروضة فقط
        earnings = earnings_display
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
    advances = Advance.objects.select_related('employee', 'employee__department').all().order_by('-requested_at')
    
    # إحصائيات محدثة
    total_advances = advances.count()
    pending_advances = advances.filter(status='pending').count()
    in_progress_advances = advances.filter(status='in_progress').count()
    completed_advances = advances.filter(status='completed').count()
    
    context = {
        'advances': advances,
        'total_advances': total_advances,
        'pending_advances': pending_advances,
        'in_progress_advances': in_progress_advances,
        'completed_advances': completed_advances,
        
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
            installments_count = request.POST.get('installments_count', 1)
            deduction_start_month = request.POST.get('deduction_start_month')
            reason = request.POST.get('reason')
            
            # التحقق من البيانات
            if not employee_id or not amount or not reason or not deduction_start_month:
                messages.error(request, 'جميع الحقول مطلوبة')
                return redirect('hr:advance_request')
            
            # تحويل البيانات
            amount = Decimal(amount)
            installments_count = int(installments_count)
            
            # التحقق من القيم
            if amount <= 0 or amount > 50000:
                messages.error(request, 'المبلغ يجب أن يكون بين 1 و 50,000 جنيه')
                return redirect('hr:advance_request')
            
            if installments_count < 1 or installments_count > 24:
                messages.error(request, 'عدد الأقساط يجب أن يكون بين 1 و 24 شهر')
                return redirect('hr:advance_request')
            
            # تحويل تاريخ البدء
            from datetime import datetime
            deduction_start_month = datetime.strptime(deduction_start_month, '%Y-%m').date()
            
            # إنشاء السلفة
            employee = Employee.objects.get(pk=employee_id)
            advance = Advance.objects.create(
                employee=employee,
                amount=amount,
                installments_count=installments_count,
                deduction_start_month=deduction_start_month,
                reason=reason,
                status='pending'
            )
            
            messages.success(
                request, 
                f'تم تقديم طلب السلفة بنجاح - المبلغ: {amount:,.0f} جنيه على {installments_count} قسط'
            )
            return redirect('hr:advance_list')
            
        except Employee.DoesNotExist:
            messages.error(request, 'الموظف غير موجود')
            return redirect('hr:advance_request')
        except ValueError as e:
            messages.error(request, f'خطأ في البيانات المدخلة: {str(e)}')
            return redirect('hr:advance_request')
        except Exception as e:
            logger.exception(f"خطأ في إنشاء السلفة: {str(e)}")
            messages.error(request, f'حدث خطأ: {str(e)}')
            return redirect('hr:advance_request')
    
    # الحصول على قائمة الموظفين النشطين
    employees = Employee.objects.filter(status='active').select_related('department').order_by('first_name_ar')
    
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
    from ..models import AdvanceInstallment
    
    advance = get_object_or_404(
        Advance.objects.select_related('employee', 'employee__department', 'approved_by'), 
        pk=pk
    )
    
    # الحصول على سجل الأقساط
    installments = AdvanceInstallment.objects.filter(
        advance=advance
    ).select_related('payroll').order_by('installment_number')
    
    context = {
        'advance': advance,
        'installments': installments,
        
        # بيانات الهيدر الموحد
        'page_title': 'تفاصيل السلفة',
        'page_subtitle': f'{advance.employee.get_full_name_ar()} - {advance.amount:,.0f} جنيه',
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
    from datetime import date
    
    advance = get_object_or_404(Advance, pk=pk)
    
    if advance.status != 'pending':
        messages.warning(request, 'هذه السلفة تم معالجتها مسبقاً')
        return redirect('hr:advance_detail', pk=pk)
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                advance.status = 'approved'
                advance.approved_by = request.user
                advance.approved_at = date.today()
                advance.save()
                
                messages.success(
                    request, 
                    f'تم اعتماد السلفة بنجاح - سيتم خصم {advance.installment_amount:,.0f} جنيه شهرياً لمدة {advance.installments_count} شهر'
                )
                return redirect('hr:advance_detail', pk=pk)
                
        except Exception as e:
            logger.exception(f"خطأ في اعتماد السلفة {pk}: {str(e)}")
            messages.error(request, f'حدث خطأ أثناء اعتماد السلفة: {str(e)}')
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
    
    # إضافة logging للتشخيص
    logger.info(f"محاولة حذف مسيرة رواتب - الشهر المستلم: '{month}' (نوع: {type(month)})")
    
    # تحويل month (YYYY-MM) إلى تاريخ مع معالجة محسنة للأخطاء
    try:
        # تجربة الصيغة الأساسية أولاً
        month_date = datetime.strptime(month, '%Y-%m').date()
        logger.info(f"✅ تم تحويل الشهر بنجاح: '{month}' -> {month_date}")
    except ValueError:
        try:
            # تجربة صيغة أخرى محتملة
            month_date = datetime.strptime(month, '%Y-%m-%d').date()
            logger.info(f"✅ تم تحويل الشهر بصيغة بديلة: '{month}' -> {month_date}")
        except ValueError:
            # إضافة تفاصيل أكثر للخطأ
            logger.error(f"❌ صيغة شهر غير صحيحة: '{month}' - المتوقع: YYYY-MM")
            messages.error(request, f'صيغة الشهر غير صحيحة: {month}. الصيغة المتوقعة: YYYY-MM (مثل: 2025-11)')
            return redirect('hr:payroll_list')
    
    # أسماء الشهور بالعربي
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
            {'title': 'معالجة الرواتب', 'url': reverse('hr:payroll_list'), 'icon': 'fas fa-money-check-alt'},
            {'title': f'مسيرة {month_name}', 'url': reverse('hr:payroll_run_detail', kwargs={'month': month})},
            {'title': 'حذف', 'active': True},
        ],
    }
    
    return render(request, 'hr/payroll/run_delete.html', context)


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
