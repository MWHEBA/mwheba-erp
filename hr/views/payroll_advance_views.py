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

logger = logging.getLogger(__name__)

__all__ = [
    'payroll_list',
    'payroll_detail',
    'payroll_approve',
    'payroll_unapprove',
    'payroll_delete',
    'payroll_export',
    'advance_list',
    'advance_request',
    'advance_detail',
    'advance_approve',
    'advance_reject',
    'advance_pay',
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
        'contract',
        'financial_subcategory',
        'financial_category',
    ).prefetch_related('lines').filter(
        month__gte=date(selected_year, 1, 1),
        month__lte=date(selected_year, 12, 31)
    )
    
    # الحصول على جميع السنوات المتاحة (فريدة ومرتبة)
    available_years = Payroll.objects.dates('month', 'year').order_by('-month')
    # تحويل إلى قائمة سنوات فريدة
    unique_years = []
    seen_years = set()
    for date_obj in available_years:
        if date_obj.year not in seen_years:
            unique_years.append(date_obj.year)
            seen_years.add(date_obj.year)
    
    # الفلترة حسب الشهر — افتراضياً الشهر الحالي
    default_month = str(date.today().month).zfill(2)
    month_filter = request.GET.get('month', default_month)
    selected_month = month_filter
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
            Q(employee__name__icontains=search) |
            Q(employee__employee_number__icontains=search)
        )
    
    # تعريف رؤوس الجدول
    table_headers = [
        {'key': 'employee_name', 'label': 'الموظف', 'sortable': True, 'class': 'text-center fw-bold'},
        {'key': 'employee_number', 'label': 'رقم الموظف', 'sortable': True, 'class': 'text-center'},
        {'key': 'financial_category_display', 'label': 'التصنيف المالي', 'format': 'html', 'class': 'text-center'},
        {'key': 'month_display', 'label': 'الشهر', 'sortable': True, 'class': 'text-center'},
        {'key': 'basic_salary', 'label': 'الأساسي', 'format': 'number', 'class': 'text-end'},
        {'key': 'total_earnings_display', 'label': 'الحوافز والمكافآت', 'format': 'number', 'class': 'text-end'},
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
        # الحوافز والمكافآت = earnings بدون الأجر الأساسي والأجر التأميني (من الـ prefetched lines)
        from decimal import Decimal as _Decimal
        bonuses = sum(
            (line.amount for line in payroll.lines.all()
             if line.component_type == 'earning' and line.code not in ('BASIC_SALARY', 'INSURABLE_SALARY')),
            _Decimal('0')
        )
        payroll.total_earnings_display = remove_trailing_zeros(bonuses)
        payroll.total_deductions = remove_trailing_zeros(payroll.total_deductions)
        # استخدام صافي الراتب الصحيح (يستبعد INSURABLE_SALARY)
        payroll.net_salary = remove_trailing_zeros(payroll.correct_net_salary)
        
        # عرض التصنيف المالي (الفرعي أولاً، ثم الرئيسي كـ fallback)
        SUBCATEGORY_BADGE_COLORS = {
            'dept_admin': 'soft-badge-warning',
            'dept_operations': 'soft-badge-info',
            'dept_auto': 'soft-badge-purple',
        }
        if payroll.financial_subcategory:
            badge_class = SUBCATEGORY_BADGE_COLORS.get(payroll.financial_subcategory.code, 'soft-badge-secondary')
            payroll.financial_category_display = f'<span class="soft-badge {badge_class}">{payroll.financial_subcategory.name}</span>'
        elif payroll.financial_category:
            payroll.financial_category_display = f'<span class="soft-badge soft-badge-secondary">{payroll.financial_category.name}</span>'
        else:
            payroll.financial_category_display = '<span class="text-muted">غير محدد</span>'
        
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
        'selected_month': selected_month,
        
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
            {
                'url': f"{reverse('hr:payroll_export')}?{request.GET.urlencode()}",
                'icon': 'fa-file-excel',
                'text': 'تصدير Excel',
                'class': 'btn-success',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'قسائم الرواتب', 'active': True},
        ],
    }
    return render(request, 'hr/payroll/list.html', context)



@login_required
@can_view_salaries
def payroll_detail(request, pk):
    """تفاصيل قسيمة الراتب مع PayrollLines"""
    payroll = get_object_or_404(
        Payroll.objects.select_related(
            'financial_category', 'financial_subcategory', 'employee__department__financial_subcategory__parent_category'
        ),
        pk=pk,
    )

    # Backfill financial_subcategory and financial_category for old payrolls
    if not payroll.financial_subcategory:
        try:
            dept = getattr(payroll.employee, 'department', None)
            fin_sub = getattr(dept, 'financial_subcategory', None) if dept else None
            if fin_sub:
                payroll.financial_subcategory = fin_sub
                payroll.financial_category = fin_sub.parent_category
            elif not payroll.financial_category:
                from financial.models import FinancialCategory
                payroll.financial_category = FinancialCategory.objects.filter(
                    code='salaries', is_active=True
                ).first()
            update_fields = ['financial_subcategory', 'financial_category']
            payroll.save(update_fields=update_fields)
        except Exception:
            pass
    
    # جلب جميع الأسطر (PayrollLines) كـ list لتجنب إعادة query عند التصنيف
    from hr.views.payroll_line_ajax_views import READONLY_CODES, READONLY_PREFIXES, VALUE_ONLY_CODES
    lines_qs = payroll.lines.select_related('salary_component').order_by('order')
    lines = list(lines_qs)

    # تصنيف البنود وإضافة line_category لكل بند على نفس الـ objects
    for line in lines:
        if line.code in READONLY_CODES or line.code.startswith(READONLY_PREFIXES):
            line.line_category = 'a'
        elif line.code in VALUE_ONLY_CODES:
            line.line_category = 'b'
        else:
            line.line_category = 'c'

    # تصنيف البنود وترتيبها: المقفولة (a) أولاً، ثم (b)، ثم (c)
    earnings = sorted(
        [l for l in lines if l.component_type == 'earning'],
        key=lambda x: (x.line_category, x.order)
    )
    deductions = sorted(
        [l for l in lines if l.component_type == 'deduction'],
        key=lambda x: (x.line_category, x.order)
    )
    
    # حساب الإجماليات من Lines (إذا كانت موجودة)
    if lines:
        # إذا كان هناك سطر للأجر الأساسي ضمن البنود، لا نعرضه ضمن القائمة لتجنب التكرار
        has_basic_line = any(line.code == 'BASIC_SALARY' for line in earnings)
        earnings_display = [line for line in earnings if line.code not in ['BASIC_SALARY', 'INSURABLE_SALARY']]

        # الأجر التأميني — مرجعية فقط، يُعرض منفصلاً
        insurable_salary_line = next((line for line in earnings if line.code == 'INSURABLE_SALARY'), None)

        # إجمالي المستحقات: يستبعد INSURABLE_SALARY لأنه مرجعية فقط
        earnings_sum = sum(line.amount for line in earnings if line.code != 'INSURABLE_SALARY')
        if has_basic_line:
            total_earnings = earnings_sum
        else:
            total_earnings = payroll.basic_salary + earnings_sum

        total_deductions = sum(line.amount for line in deductions)
        has_lines = True
        # استبدال earnings في العرض بالقائمة المعروضة فقط
        earnings = earnings_display
        # حساب صافي الراتب الصحيح (بدون INSURABLE_SALARY) — يتقرّب لأقرب جنيه صحيح
        from decimal import Decimal, ROUND_HALF_UP
        net_raw = total_earnings - total_deductions
        correct_net_salary = net_raw.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        correct_gross_salary = total_earnings
    else:
        # استخدام البيانات القديمة إذا لم توجد Lines
        total_earnings = payroll.total_additions or 0
        total_deductions = payroll.total_deductions or 0
        has_lines = False
        insurable_salary_line = None
        correct_net_salary = payroll.correct_net_salary
        correct_gross_salary = payroll.correct_gross_salary
    
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
    
    # زر إعادة الحساب (يظهر فقط قبل الاعتماد)
    if payroll.status in ['draft', 'calculated']:
        header_buttons.append({
            'onclick': f'confirmRecalculate({payroll.pk})',
            'icon': 'fa-sync-alt',
            'text': 'إعادة الحساب',
            'class': 'btn-info',
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
    
    # زر إلغاء الاعتماد (للسوبر ادمن فقط - القسائم المعتمدة وغير المدفوعة)
    if payroll.status == 'approved' and request.user.is_superuser:
        header_buttons.append({
            'onclick': f'confirmUnapprove({payroll.pk})',
            'icon': 'fa-undo',
            'text': 'إلغاء الاعتماد',
            'class': 'btn-outline-danger',
        })
    
    header_buttons.extend([
        {
            'url': reverse('hr:payroll_list'),
            'icon': 'fa-arrow-right',
            'text': 'رجوع',
            'class': 'btn-secondary',
        },
    ])
    
    # ✅ جلب سجل التدقيق
    from hr.models import PayrollAuditLog
    audit_logs = PayrollAuditLog.objects.filter(
        payroll=payroll
    ).select_related('performed_by').order_by('-timestamp')

    # جلب صافي مرتب الشهر السابق لنفس الموظف
    from dateutil.relativedelta import relativedelta
    prev_month = payroll.month - relativedelta(months=1)
    prev_payroll = (
        Payroll.objects.filter(
            employee=payroll.employee,
            month=prev_month,
            status__in=['approved', 'paid'],
        )
        .only('net_salary', 'month')
        .first()
    )
    prev_net_salary = prev_payroll.correct_net_salary if prev_payroll else None

    # حساب قيمة اليوم والساعة
    from decimal import Decimal, ROUND_HALF_UP
    _basic = payroll.basic_salary or Decimal('0')
    daily_value = (_basic / Decimal('30')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    hourly_value = (daily_value / Decimal('8')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    context = {
        'payroll': payroll,
        'lines': lines,
        'earnings': earnings,
        'deductions': deductions,
        'insurable_salary_line': insurable_salary_line if has_lines else None,
        'total_earnings': total_earnings,
        'total_deductions': total_deductions,
        'correct_net_salary': correct_net_salary,
        'correct_gross_salary': correct_gross_salary,
        'has_lines': has_lines,
        'is_partial_salary': is_partial_salary,
        'partial_reason': partial_reason,
        'audit_logs': audit_logs,
        'prev_net_salary': prev_net_salary,
        'daily_value': daily_value,
        'hourly_value': hourly_value,
    }

    # إضافة بيانات الهيدر الموحد
    context.update({
        # بيانات الهيدر الموحد
        'page_title': f'قسيمة راتب {payroll.employee.get_full_name_ar()}',
        'page_subtitle': f'شهر {payroll.month.strftime("%Y-%m")}',
        'page_icon': 'fas fa-file-invoice-dollar',
        'header_buttons': header_buttons,
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
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

    # التحقق من عدم وجود جزاءات/مكافآت معلقة
    from hr.services.penalty_reward_service import PenaltyRewardService
    has_pending, pending_count = PenaltyRewardService.check_pending_for_month(
        payroll.employee, payroll.month
    )
    if has_pending:
        msg = f'لا يمكن اعتماد الراتب: يوجد {pending_count} جزاء/مكافأة معلق لهذا الموظف في نفس الشهر. يرجى اعتمادها أو رفضها أولاً.'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': msg})
        messages.error(request, msg)
        return redirect('hr:payroll_detail', pk=pk)
    
    if request.method == 'POST':
        try:
            # استخدام PayrollService للاعتماد
            PayrollService.approve_payroll(payroll, request.user)
            
            success_message = f'تم اعتماد قسيمة راتب {payroll.employee.get_full_name_ar()} بنجاح'
            
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
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'قسائم الرواتب', 'url': reverse('hr:payroll_list'), 'icon': 'fas fa-money-bill-wave'},
            {'title': 'اعتماد', 'active': True},
        ],
    }
    return render(request, 'hr/payroll/approve_modal.html', context)


@login_required
def payroll_unapprove(request, pk):
    """إلغاء اعتماد قسيمة راتب - للسوبر ادمن فقط"""
    if not request.user.is_superuser:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'غير مصرح لك بهذا الإجراء'})
        messages.error(request, 'غير مصرح لك بهذا الإجراء')
        return redirect('hr:payroll_detail', pk=pk)

    payroll = get_object_or_404(Payroll, pk=pk)

    if request.method == 'POST':
        try:
            PayrollService.unapprove_payroll(payroll, request.user)
            success_message = f'تم إلغاء اعتماد قسيمة راتب {payroll.employee.get_full_name_ar()} بنجاح'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': success_message})
            messages.success(request, success_message)
        except ValueError as e:
            error_message = str(e)
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': error_message})
            messages.error(request, error_message)

    return redirect('hr:payroll_detail', pk=pk)


# ==================== السلف ====================

@login_required
def advance_list(request):
    """قائمة السلف"""
    advances = Advance.objects.select_related('employee', 'employee__department').all()

    # --- فلاتر ---
    search = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '').strip()

    from datetime import date
    default_month = date.today().strftime('%Y-%m')
    month_filter = request.GET.get('month', default_month).strip()

    if search:
        advances = advances.filter(
            Q(employee__name__icontains=search) |
            Q(employee__name_en__icontains=search) |
            Q(employee__employee_number__icontains=search)
        )
    if status_filter:
        advances = advances.filter(status=status_filter)
    if month_filter:
        try:
            from datetime import datetime
            month_date = datetime.strptime(month_filter, '%Y-%m').date()
            advances = advances.filter(
                deduction_start_month__year=month_date.year,
                deduction_start_month__month=month_date.month
            )
        except ValueError:
            pass

    advances = advances.order_by('-requested_at')

    context = {
        'advances': advances,
        'total_advances': advances.count(),
        'pending_advances': advances.filter(status='pending').count(),
        'in_progress_advances': advances.filter(status='in_progress').count(),
        'completed_advances': advances.filter(status='completed').count(),

        # قيم الفلاتر الحالية
        'current_search': search,
        'current_status': status_filter,
        'current_month': month_filter,

        'page_title': 'السلف',
        'page_subtitle': f'سلف الموظفين عن شهر {month_filter}' if month_filter else 'إدارة سلف الموظفين والخصومات',
        'page_icon': 'fas fa-hand-holding-usd',
        'header_buttons': [
            {'url': reverse('hr:advance_request'), 'icon': 'fa-plus', 'text': 'طلب سلفة', 'class': 'btn-primary'},
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
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
            financial_category_id = request.POST.get('financial_category')
            
            # التحقق من البيانات
            if not employee_id or not amount or not reason or not deduction_start_month:
                messages.error(request, 'جميع الحقول مطلوبة')
                return redirect('hr:advance_request')
            
            # تحويل البيانات
            amount = Decimal(amount)
            installments_count = int(installments_count)
            
            # التحقق من القيم
            if amount <= 0 or amount > 10000:
                messages.error(request, 'المبلغ يجب أن يكون بين 1 و 10,000 جنيه')
                return redirect('hr:advance_request')
            
            if installments_count < 1 or installments_count > 5:
                messages.error(request, 'عدد الأقساط يجب أن يكون بين 1 و 5 أشهر')
                return redirect('hr:advance_request')
            
            # تحويل تاريخ البدء
            from datetime import datetime
            deduction_start_month = datetime.strptime(deduction_start_month, '%Y-%m').date()
            
            # الحصول على التصنيف المالي
            financial_category = None
            if financial_category_id:
                from financial.models import FinancialCategory
                try:
                    financial_category = FinancialCategory.objects.get(pk=financial_category_id)
                except FinancialCategory.DoesNotExist:
                    pass
            
            # إذا لم يتم تحديد تصنيف، استخدم "رواتب" كافتراضي
            if not financial_category:
                from financial.models import FinancialCategory
                try:
                    financial_category = FinancialCategory.objects.get(code='salaries', is_active=True)
                except FinancialCategory.DoesNotExist:
                    pass
            
            # إنشاء السلفة
            employee = Employee.objects.get(pk=employee_id)
            advance = Advance.objects.create(
                employee=employee,
                amount=amount,
                installments_count=installments_count,
                deduction_start_month=deduction_start_month,
                reason=reason,
                financial_category=financial_category,
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
    employees = Employee.objects.filter(status='active', is_insurance_only=False).select_related('department').order_by('name')
    
    # الحصول على التصنيف الافتراضي "رواتب"
    from financial.models import FinancialCategory
    default_category = None
    try:
        default_category = FinancialCategory.objects.get(code='salaries', is_active=True)
    except FinancialCategory.DoesNotExist:
        pass
    
    context = {
        'employees': employees,
        'default_category': default_category,
        
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
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
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
    
    # بناء أزرار الهيدر حسب حالة السلفة
    header_buttons = [
        {'url': reverse('hr:advance_list'), 'icon': 'fa-arrow-right', 'text': 'رجوع', 'class': 'btn-secondary'},
    ]
    if advance.status == 'pending':
        header_buttons = [
            {'onclick': f'advanceAction({advance.pk}, "approve")', 'icon': 'fa-check', 'text': 'اعتماد', 'class': 'btn-success'},
            {'onclick': f'advanceAction({advance.pk}, "reject")', 'icon': 'fa-times', 'text': 'رفض', 'class': 'btn-danger'},
            {'url': reverse('hr:advance_list'), 'icon': 'fa-arrow-right', 'text': 'رجوع', 'class': 'btn-secondary'},
        ]
    elif advance.status == 'approved':
        header_buttons = [
            {'onclick': f'advancePay({advance.pk})', 'icon': 'fa-money-bill-wave', 'text': 'صرف السلفة', 'class': 'btn-info'},
            {'url': reverse('hr:advance_list'), 'icon': 'fa-arrow-right', 'text': 'رجوع', 'class': 'btn-secondary'},
        ]

    context = {
        'advance': advance,
        'installments': installments,
        'page_title': 'تفاصيل السلفة',
        'page_subtitle': f'{advance.employee.get_full_name_ar()} - {advance.amount:,.0f} جنيه',
        'page_icon': 'fas fa-hand-holding-usd',
        'header_buttons': header_buttons,
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'السلف', 'url': reverse('hr:advance_list'), 'icon': 'fas fa-hand-holding-usd'},
            {'title': 'تفاصيل السلفة', 'active': True},
        ],
    }
    return render(request, 'hr/advance/detail.html', context)


@login_required
def advance_approve(request, pk):
    """اعتماد السلفة"""
    from django.http import JsonResponse
    from django.utils import timezone
    
    advance = get_object_or_404(Advance, pk=pk)
    
    if advance.status != 'pending':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'هذه السلفة تم معالجتها مسبقاً'})
        messages.warning(request, 'هذه السلفة تم معالجتها مسبقاً')
        return redirect('hr:advance_detail', pk=pk)
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                advance.status = 'approved'
                advance.approved_by = request.user
                advance.approved_at = timezone.now()
                advance.save()
                
                msg = f'تم اعتماد السلفة بنجاح - سيتم خصم {advance.installment_amount:,.0f} جنيه شهرياً لمدة {advance.installments_count} شهر'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': True, 'message': msg})
                messages.success(request, msg)
                return redirect('hr:advance_detail', pk=pk)
                
        except Exception as e:
            logger.exception(f"خطأ في اعتماد السلفة {pk}: {str(e)}")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': f'حدث خطأ: {str(e)}'})
            messages.error(request, f'حدث خطأ أثناء اعتماد السلفة: {str(e)}')
            return redirect('hr:advance_detail', pk=pk)
    
    return redirect('hr:advance_detail', pk=pk)


@login_required
def advance_pay(request, pk):
    """صرف السلفة - تحويل الحالة من approved إلى paid مع إنشاء القيد المحاسبي"""
    from django.http import JsonResponse
    from django.utils import timezone
    from ..services.advance_service import AdvanceService
    from financial.models import ChartOfAccounts

    advance = get_object_or_404(Advance, pk=pk)

    if advance.status != 'approved':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'يمكن صرف السلف المعتمدة فقط'})
        messages.warning(request, 'يمكن صرف السلف المعتمدة فقط')
        return redirect('hr:advance_detail', pk=pk)

    if request.method == 'POST':
        try:
            payment_date_str = request.POST.get('payment_date')
            payment_account_code = request.POST.get('payment_account')

            if not payment_account_code:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': 'يجب اختيار حساب الصرف (الخزينة/البنك)'})
                messages.error(request, 'يجب اختيار حساب الصرف')
                return redirect('hr:advance_detail', pk=pk)

            payment_account = ChartOfAccounts.objects.filter(
                code=payment_account_code, is_active=True
            ).first()
            if not payment_account:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': 'حساب الصرف غير موجود'})
                messages.error(request, 'حساب الصرف غير موجود')
                return redirect('hr:advance_detail', pk=pk)

            with transaction.atomic():
                advance.status = 'paid'
                advance.payment_date = (
                    datetime.strptime(payment_date_str, '%Y-%m-%d').date()
                    if payment_date_str else timezone.now().date()
                )
                advance.save(update_fields=['status', 'payment_date'])

                # إنشاء القيد المحاسبي
                AdvanceService.create_disbursement_journal_entry(
                    advance=advance,
                    payment_account=payment_account,
                    created_by=request.user,
                )

            msg = f'تم صرف السلفة بنجاح - سيبدأ الخصم من شهر {advance.deduction_start_month.strftime("%Y-%m")}'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': msg})
            messages.success(request, msg)
            return redirect('hr:advance_detail', pk=pk)

        except Exception as e:
            logger.exception(f"خطأ في صرف السلفة {pk}: {str(e)}")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': f'حدث خطأ: {str(e)}'})
            messages.error(request, f'حدث خطأ أثناء صرف السلفة: {str(e)}')
            return redirect('hr:advance_detail', pk=pk)

    return redirect('hr:advance_detail', pk=pk)


@login_required
def advance_reject(request, pk):
    """رفض السلفة"""
    from django.http import JsonResponse
    
    advance = get_object_or_404(Advance, pk=pk)
    if request.method == 'POST':
        advance.status = 'rejected'
        advance.save()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'تم رفض السلفة'})
        messages.success(request, 'تم رفض السلفة')
        return redirect('hr:advance_detail', pk=pk)
    return redirect('hr:advance_detail', pk=pk)


@login_required
@can_process_payroll
def payroll_run_delete(request, month):
    """حذف مسيرة رواتب شهر محدد"""
    from datetime import datetime
    from django.db import transaction
    
    # إضافة logging للتشخيص
    
    # تحويل month (YYYY-MM) إلى تاريخ مع معالجة محسنة للأخطاء
    try:
        # تجربة الصيغة الأساسية أولاً
        month_date = datetime.strptime(month, '%Y-%m').date()
    except ValueError:
        try:
            # تجربة صيغة أخرى محتملة
            month_date = datetime.strptime(month, '%Y-%m-%d').date()
        except ValueError:
            # إضافة تفاصيل أكثر للخطأ
            logger.error(f"❌ صيغة شهر غير صحيحة: '{month}' - المتوقع: YYYY-MM")
            messages.error(request, f'صيغة الشهر غير صحيحة: {month}. الصيغة المتوقعة: YYYY-MM (مثل: 2025-11)')
            return redirect('hr:payroll_list')
    
    # أسماء الشهور بالعربي
            return redirect('hr:payroll_run_detail', month=month)
    
    # إحصائيات للعرض — total_net بيتحسب من property لاستبعاد INSURABLE_SALARY
    stats = payrolls.aggregate(
        total_employees=Count('id'),
        approved_count=Count('id', filter=Q(status='approved')),
        calculated_count=Count('id', filter=Q(status='calculated')),
        draft_count=Count('id', filter=Q(status='draft'))
    )
    stats['total_net'] = sum(p.correct_net_salary for p in payrolls)
    
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
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
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
    
    # حساب صافي الراتب الصحيح — استخدام property من الـ model
    context = {
        'payroll': payroll,
        'correct_net_salary': payroll.correct_net_salary,
        'correct_gross_salary': payroll.correct_gross_salary,
        'page_title': f'حذف قسيمة راتب {payroll.employee.get_full_name_ar()}',
        'page_subtitle': f'شهر {payroll.month.strftime("%Y-%m")}',
        'page_icon': 'fas fa-trash-alt',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'قسائم الرواتب', 'url': reverse('hr:payroll_list'), 'icon': 'fas fa-money-bill-wave'},
            {'title': f'قسيمة {payroll.employee.get_full_name_ar()}', 'url': reverse('hr:payroll_detail', kwargs={'pk': pk})},
            {'title': 'حذف', 'active': True},
        ],
    }
    
    return render(request, 'hr/payroll/delete.html', context)


@login_required
@can_view_salaries
def payroll_export(request):
    """Export payroll data to XLSX grouped by department"""
    from datetime import date as _date
    from decimal import Decimal as _Decimal

    # --- Apply same filters as payroll_list ---
    selected_year = request.GET.get('year', _date.today().year)
    try:
        selected_year = int(selected_year)
    except ValueError:
        selected_year = _date.today().year

    payrolls = Payroll.objects.select_related(
        'employee',
        'employee__department',
        'employee__job_title',
    ).prefetch_related('lines').filter(
        month__gte=_date(selected_year, 1, 1),
        month__lte=_date(selected_year, 12, 31)
    )

    month_filter = request.GET.get('month', '')
    if month_filter:
        try:
            payrolls = payrolls.filter(month__month=int(month_filter))
        except ValueError:
            pass

    status_filter = request.GET.get('status', '')
    if status_filter:
        payrolls = payrolls.filter(status=status_filter)

    search = request.GET.get('search', '')
    if search:
        payrolls = payrolls.filter(
            Q(employee__name__icontains=search) |
            Q(employee__employee_number__icontains=search)
        )

    payrolls = payrolls.order_by('employee__department__name_ar', 'employee__name', 'month')

    # --- Build workbook ---
    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # remove default sheet

    header_fill = PatternFill(start_color='1F4E79', end_color='1F4E79', fill_type='solid')
    dept_fill   = PatternFill(start_color='2E75B6', end_color='2E75B6', fill_type='solid')
    total_fill  = PatternFill(start_color='D6E4F0', end_color='D6E4F0', fill_type='solid')
    header_font = Font(bold=True, color='FFFFFF', size=11)
    dept_font   = Font(bold=True, color='FFFFFF', size=11)
    total_font  = Font(bold=True, size=11)
    center      = Alignment(horizontal='center', vertical='center')
    right_align = Alignment(horizontal='right', vertical='center')

    COLUMNS = [
        ('رقم الموظف',      14),
        ('اسم الموظف',      24),
        ('المسمى الوظيفي',  20),
        ('الشهر',           12),
        ('الأجر الأساسي',   16),
        ('الحوافز والمكافآت', 18),
        ('إجمالي الراتب',   16),
        ('الخصومات',        14),
        ('صافي الراتب',     16),
        ('الحالة',          12),
    ]

    STATUS_MAP = {
        'draft':      'مسودة',
        'calculated': 'محسوب',
        'approved':   'معتمد',
        'paid':       'مدفوع',
    }

    def _write_headers(ws):
        for col_idx, (label, width) in enumerate(COLUMNS, 1):
            cell = ws.cell(row=1, column=col_idx, value=label)
            cell.fill   = header_fill
            cell.font   = header_font
            cell.alignment = center
            ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = width
        ws.row_dimensions[1].height = 22

    def _write_row(ws, row_num, payroll, dept_name=None):
        bonuses = sum(
            (line.amount for line in payroll.lines.all()
             if line.component_type == 'earning' and line.code not in ('BASIC_SALARY', 'INSURABLE_SALARY')),
            _Decimal('0')
        )
        values = [
            payroll.employee.employee_number or '',
            payroll.employee.name or '',
            payroll.employee.job_title.title_ar if payroll.employee.job_title else '',
            payroll.month.strftime('%Y-%m'),
            float(payroll.basic_salary or 0),
            float(bonuses),
            float(payroll.correct_gross_salary),
            float(payroll.total_deductions or 0),
            float(payroll.correct_net_salary),
            STATUS_MAP.get(payroll.status, payroll.status),
        ]
        for col_idx, val in enumerate(values, 1):
            cell = ws.cell(row=row_num, column=col_idx, value=val)
            cell.alignment = center if not isinstance(val, float) else right_align

    # --- Group payrolls by department ---
    from collections import defaultdict
    dept_groups = defaultdict(list)
    for p in payrolls:
        dept_name = p.employee.department.name_ar if p.employee.department else 'بدون قسم'
        dept_groups[dept_name].append(p)

    summary_data = []  # (dept_name, count, total_basic, total_bonuses, total_gross, total_deductions, total_net)

    for dept_name, dept_payrolls in dept_groups.items():
        # Sanitize sheet name (Excel limit: 31 chars, no special chars)
        sheet_name = dept_name[:28].replace('/', '-').replace('\\', '-').replace('*', '').replace('?', '').replace('[', '').replace(']', '').replace(':', '')
        ws = wb.create_sheet(title=sheet_name)
        _write_headers(ws)

        # Department title row
        ws.insert_rows(1)
        title_cell = ws.cell(row=1, column=1, value=f'قسم: {dept_name}')
        title_cell.fill = dept_fill
        title_cell.font = dept_font
        title_cell.alignment = center
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(COLUMNS))
        ws.row_dimensions[1].height = 24

        row_num = 3  # data starts at row 3 (row 1=dept title, row 2=headers)
        dept_totals = {k: _Decimal('0') for k in ('basic', 'bonuses', 'gross', 'deductions', 'net')}

        for p in dept_payrolls:
            bonuses = sum(
                (line.amount for line in p.lines.all()
                 if line.component_type == 'earning' and line.code not in ('BASIC_SALARY', 'INSURABLE_SALARY')),
                _Decimal('0')
            )
            values = [
                p.employee.employee_number or '',
                p.employee.name or '',
                p.employee.job_title.title_ar if p.employee.job_title else '',
                p.month.strftime('%Y-%m'),
                float(p.basic_salary or 0),
                float(bonuses),
                float(p.correct_gross_salary),
                float(p.total_deductions or 0),
                float(p.correct_net_salary),
                STATUS_MAP.get(p.status, p.status),
            ]
            for col_idx, val in enumerate(values, 1):
                cell = ws.cell(row=row_num, column=col_idx, value=val)
                cell.alignment = right_align if isinstance(val, float) else center
            row_num += 1

            dept_totals['basic']      += p.basic_salary or _Decimal('0')
            dept_totals['bonuses']    += bonuses
            dept_totals['gross']      += p.correct_gross_salary
            dept_totals['deductions'] += p.total_deductions or _Decimal('0')
            dept_totals['net']        += p.correct_net_salary

        # Totals row for this department
        totals_row = ['', f'الإجمالي ({len(dept_payrolls)} قسيمة)', '', '',
                      float(dept_totals['basic']), float(dept_totals['bonuses']),
                      float(dept_totals['gross']), float(dept_totals['deductions']),
                      float(dept_totals['net']), '']
        for col_idx, val in enumerate(totals_row, 1):
            cell = ws.cell(row=row_num, column=col_idx, value=val)
            cell.fill = total_fill
            cell.font = total_font
            cell.alignment = right_align if isinstance(val, float) else center

        summary_data.append((
            dept_name, len(dept_payrolls),
            dept_totals['basic'], dept_totals['bonuses'],
            dept_totals['gross'], dept_totals['deductions'],
            dept_totals['net'],
        ))

    # --- Summary sheet ---
    ws_summary = wb.create_sheet(title='ملخص الأقسام', index=0)
    summary_headers = [
        ('القسم', 28), ('عدد القسائم', 14), ('إجمالي الأساسي', 18),
        ('إجمالي الحوافز', 18), ('إجمالي الراتب', 18),
        ('إجمالي الخصومات', 18), ('إجمالي الصافي', 18),
    ]
    for col_idx, (label, width) in enumerate(summary_headers, 1):
        cell = ws_summary.cell(row=1, column=col_idx, value=label)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center
        ws_summary.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = width

    grand = [_Decimal('0')] * 5
    for row_idx, (dept_name, count, basic, bonuses, gross, deductions, net) in enumerate(summary_data, 2):
        row_vals = [dept_name, count, float(basic), float(bonuses), float(gross), float(deductions), float(net)]
        for col_idx, val in enumerate(row_vals, 1):
            cell = ws_summary.cell(row=row_idx, column=col_idx, value=val)
            cell.alignment = right_align if isinstance(val, float) else center
        grand[0] += basic; grand[1] += bonuses; grand[2] += gross; grand[3] += deductions; grand[4] += net

    # Grand total row
    grand_row_idx = len(summary_data) + 2
    grand_vals = ['الإجمالي الكلي', sum(d[1] for d in summary_data),
                  float(grand[0]), float(grand[1]), float(grand[2]), float(grand[3]), float(grand[4])]
    for col_idx, val in enumerate(grand_vals, 1):
        cell = ws_summary.cell(row=grand_row_idx, column=col_idx, value=val)
        cell.fill = total_fill
        cell.font = total_font
        cell.alignment = right_align if isinstance(val, float) else center

    # --- Return response ---
    from django.utils import timezone as _tz
    filename = f'payroll_{selected_year}'
    if month_filter:
        filename += f'_{month_filter.zfill(2)}'
    filename += f'_{_tz.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response
