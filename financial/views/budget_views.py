from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.utils import timezone

from financial.models import (
    CostCenter,
    CostCenterBudget,
    ChartOfAccounts,
    FiscalYear,
    AccountingPeriod,
    JournalEntryLine
)
from financial.models.cost_center_budget import (
    CostCenterBudgetLine,
    BudgetOverrideRequest,
    CostCenterActualSnapshot
)
from financial.services.budget_approval_service import BudgetApprovalService
from financial.services.budget_actual_service import BudgetActualService



@login_required
def budget_list(request):
    """
    سجل وقائمة الموازنات التقديرية (Budget List View)
    """
    queryset = CostCenterBudget.objects.all().select_related('cost_center', 'fiscal_year').order_by('-fiscal_year', 'cost_center', '-version')

    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '').strip()

    if search_query:
        queryset = queryset.filter(cost_center__name__icontains=search_query) | queryset.filter(cost_center__code__icontains=search_query)

    if status_filter in ['DRAFT', 'SUBMITTED', 'APPROVED', 'REVISED']:
        queryset = queryset.filter(status=status_filter)

    header_buttons = [
        {
            'url': reverse('financial:budget_create'),
            'text': 'إضافة موازنة تقديرية جديدة',
            'icon': 'fa-plus-circle',
            'class': 'btn-primary',
        }
    ]

    context = {
        'budgets': queryset,
        'search_query': search_query,
        'status_filter': status_filter,
        'header_buttons': header_buttons,
        'page_title': 'الموازنات التقديرية',
        'page_subtitle': 'سجل الموازنات المعرفية لجميع مراكز التكلفة',
        'page_icon': 'fas fa-calculator',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'مراكز التكلفة', 'url': reverse('financial:cost_centers_list'), 'icon': 'fas fa-network-wired'},
            {'title': 'الموازنات التقديرية', 'active': True}
        ]
    }
    return render(request, 'financial/budget/budget_list.html', context)


@login_required
def budget_create(request):
    """
    إعداد موازنة تقديرية لمركز تكلفة (Create Budget)
    """
    if request.method == 'POST':
        cost_center_id = request.POST.get('cost_center')
        fiscal_year_id = request.POST.get('fiscal_year')
        target_budget_amount = Decimal(request.POST.get('budget_amount') or '0.00')

        cost_center = get_object_or_404(CostCenter, pk=cost_center_id)
        fiscal_year = get_object_or_404(FiscalYear, pk=fiscal_year_id)

        # حساب رقم الإصدار تلقائياً
        last_version = CostCenterBudget.objects.filter(
            cost_center=cost_center,
            fiscal_year=fiscal_year
        ).count()
        new_version = last_version + 1

        budget = CostCenterBudget.objects.create(
            cost_center=cost_center,
            fiscal_year=fiscal_year,
            version=new_version,
            budget_amount=target_budget_amount,
            status='DRAFT'
        )

        account_ids = request.POST.getlist('account_id[]')
        amounts = request.POST.getlist('allocated_amount[]')
        policies = request.POST.getlist('control_policy[]')

        total_lines_sum = Decimal('0.00')
        for i in range(len(account_ids)):
            if account_ids[i] and amounts[i]:
                acc = ChartOfAccounts.objects.get(pk=account_ids[i])
                amt = Decimal(str(amounts[i]))
                pol = policies[i] if i < len(policies) else 'BLOCK'
                CostCenterBudgetLine.objects.create(
                    budget=budget,
                    account=acc,
                    allocated_amount=amt,
                    control_policy=pol
                )
                total_lines_sum += amt

        # إذا لم يتم تعيين السقف يدوياً يثبت بمجموع البنود
        if target_budget_amount <= 0:
            budget.budget_amount = total_lines_sum
            budget.save(update_fields=['budget_amount'])

        messages.success(request, f"تم حفظ مسودة الموازنة بنجاح لـ ({cost_center.name}) إصدار v{new_version}")
        return redirect('financial:budget_detail', pk=budget.pk)

    cost_centers = CostCenter.objects.filter(is_active=True).order_by('code')
    fiscal_years = FiscalYear.objects.all().order_by('-start_date')
    if not fiscal_years.exists():
        from datetime import date
        current_year = timezone.now().year
        fy, _ = FiscalYear.objects.get_or_create(
            year_code=str(current_year),
            defaults={
                'name': f'السنة المالية {current_year}',
                'start_date': date(current_year, 1, 1),
                'end_date': date(current_year, 12, 31),
                'status': 'open'
            }
        )
        fiscal_years = FiscalYear.objects.all().order_by('-start_date')

    accounts = ChartOfAccounts.objects.filter(is_active=True, is_leaf=True).order_by('code')

    control_policies = CostCenterBudgetLine.CONTROL_POLICIES

    selected_cost_center_id = request.GET.get('cost_center')

    context = {
        'cost_centers': cost_centers,
        'fiscal_years': fiscal_years,
        'accounts': accounts,
        'control_policies': control_policies,
        'selected_cost_center_id': selected_cost_center_id,
        'page_title': 'إعداد موازنة تقديرية جديدة',
        'page_subtitle': 'تخصيص سقف المصروفات والسياسات الرقابية لمركز التكلفة',
        'page_icon': 'fas fa-plus-circle',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموازنات', 'url': reverse('financial:budget_list'), 'icon': 'fas fa-calculator'},
            {'title': 'إعداد موازنة جديدة', 'active': True}
        ]
    }
    return render(request, 'financial/budget/budget_form.html', context)


@login_required
def budget_detail(request, pk):
    """
    عرض تفاصيل ومكونات الموازنة التقديرية (Budget Detail View)
    """
    budget = get_object_or_404(CostCenterBudget.objects.select_related('cost_center', 'fiscal_year'), pk=pk)
    lines = budget.lines.select_related('account').all()

    current_period = AccountingPeriod.get_period_for_date(timezone.now().date())

    lines_summary = []
    total_used = Decimal('0.00')

    for l in lines:
        actual_info = BudgetActualService.get_actual_and_committed(
            budget.cost_center, l.account, current_period
        ) if current_period else {'actual': Decimal('0.00'), 'committed': Decimal('0.00')}

        act = actual_info['actual']
        comm = actual_info['committed']
        used = act + comm
        var = l.allocated_amount - used
        pct = round(float(used / l.allocated_amount * 100), 1) if l.allocated_amount > 0 else 0

        lines_summary.append({
            'line': l,
            'actual': act,
            'committed': comm,
            'used': used,
            'variance': var,
            'percentage': pct
        })
        total_used += used

    total_remaining = budget.budget_amount - total_used

    context = {
        'budget': budget,
        'lines_summary': lines_summary,
        'total_used': total_used,
        'total_remaining': total_remaining,
        'page_title': f'موازنة: {budget.cost_center.name}',
        'page_subtitle': f'السنة المالية: {budget.fiscal_year.name} - الإصدار v{budget.version}',
        'page_icon': 'fas fa-file-invoice-dollar',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموازنات', 'url': reverse('financial:budget_list'), 'icon': 'fas fa-calculator'},
            {'title': budget.cost_center.name, 'active': True}
        ]
    }
    return render(request, 'financial/budget/budget_detail.html', context)


@login_required
def budget_submit(request, pk):
    """
    تقديم الموازنة للاعتماد
    """
    budget = get_object_or_404(CostCenterBudget, pk=pk)
    if request.method == 'POST':
        BudgetApprovalService.submit_budget(budget.pk, user=request.user)
        messages.success(request, "تم تقديم الموازنة بنجاح للموافقة والاعتماد.")
    return redirect('financial:budget_detail', pk=pk)


@login_required
def budget_approve(request, pk):
    """
    اعتماد الموازنة وتفعيل الرقابة فوراً
    """
    budget = get_object_or_404(CostCenterBudget, pk=pk)
    if request.method == 'POST':
        comment = request.POST.get('approval_comment', '')
        BudgetApprovalService.approve_budget(budget.pk, user=request.user, comment=comment)
        messages.success(request, "تم اعتماد الموازنة التقديرية وتفعيل سياسات الرقابة الوقائية فوراً.")
    return redirect('financial:budget_detail', pk=pk)


@login_required
def budget_revise(request, pk):
    """
    إنشاء إصدار معدل من موازنة معتمدة (Budget Revision V+1)
    """
    budget = get_object_or_404(CostCenterBudget, pk=pk)
    if request.method == 'POST':
        new_budget = BudgetApprovalService.revise_budget(budget.pk, user=request.user)
        messages.success(request, f"تم إنشاء الإصدار المعدل v{new_budget.version} بنجاح.")
        return redirect('financial:budget_detail', pk=new_budget.pk)
    return redirect('financial:budget_detail', pk=pk)


@login_required
def budget_override_list(request):
    """
    لوحة طلبات الموافقة الاستثنائية لتجاوز الموازنة (Budget Override Requests)
    """
    requests_qs = BudgetOverrideRequest.objects.all().select_related('cost_center', 'account', 'requested_by').order_by('-created_at')

    context = {
        'override_requests': requests_qs,
        'page_title': 'طلبات استثناء الموازنة',
        'page_subtitle': 'لوحة تحكم الموافقات الاستثنائية لتجاوز سقف المصروفات',
        'page_icon': 'fas fa-user-shield',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموازنات', 'url': reverse('financial:budget_list'), 'icon': 'fas fa-calculator'},
            {'title': 'طلبات التجاوز الاستثنائية', 'active': True}
        ]
    }
    return render(request, 'financial/budget/budget_override_list.html', context)


@login_required
def budget_override_action(request, pk):
    """
    قبول أو رفض طلب تجاوز الموازنة
    """
    req_obj = get_object_or_404(BudgetOverrideRequest, pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'approve':
            req_obj.status = 'APPROVED'
            req_obj.approved_by = request.user
            req_obj.approved_at = timezone.now()
            req_obj.save()
            messages.success(request, f"تمت الموافقة الاستثنائية على طلب التجاوز رقم #{req_obj.id}")
        elif action == 'reject':
            req_obj.status = 'REJECTED'
            req_obj.approved_by = request.user
            req_obj.approved_at = timezone.now()
            req_obj.save()
            messages.info(request, f"تم رفض طلب التجاوز رقم #{req_obj.id}")
    return redirect('financial:budget_override_list')



@login_required
def budget_performance_report(request):
    """
    تقرير تباين أداء الموازنة اللحظي (Real-Time Budget Variance Performance Report)
    """
    selected_cost_center_id = request.GET.get('cost_center')
    cost_centers = CostCenter.objects.filter(is_active=True).order_by('code')

    approved_budgets = CostCenterBudget.objects.filter(status='APPROVED').select_related('cost_center', 'fiscal_year')
    if selected_cost_center_id:
        approved_budgets = approved_budgets.filter(cost_center_id=selected_cost_center_id)

    current_period = AccountingPeriod.get_period_for_date(timezone.now().date())

    report_items = []
    for b in approved_budgets:
        lines = b.lines.select_related('account').all()
        for l in lines:
            actual_info = BudgetActualService.get_actual_and_committed(
                b.cost_center, l.account, current_period
            ) if current_period else {'actual': Decimal('0.00'), 'committed': Decimal('0.00')}

            act = actual_info['actual']
            comm = actual_info['committed']
            used = act + comm
            var = l.allocated_amount - used
            pct = round(float(used / l.allocated_amount * 100), 1) if l.allocated_amount > 0 else 0

            report_items.append({
                'cost_center': b.cost_center,
                'account': l.account,
                'policy': l.control_policy,
                'allocated': l.allocated_amount,
                'actual': act,
                'committed': comm,
                'used': used,
                'variance': var,
                'percentage': pct
            })

    context = {
        'cost_centers': cost_centers,
        'selected_cost_center_id': selected_cost_center_id,
        'report_items': report_items,
        'page_title': 'تقرير تباين الموازنة اللحظي',
        'page_subtitle': 'متابعة حية للمنفق والالتزامات وسقف الرقابة المعيارية لكل مركز تكلفة',
        'page_icon': 'fas fa-chart-line',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموازنات', 'url': reverse('financial:budget_list'), 'icon': 'fas fa-calculator'},
            {'title': 'تقرير التباين اللحظي', 'active': True}
        ]
    }
    return render(request, 'financial/budget/budget_performance_report.html', context)
