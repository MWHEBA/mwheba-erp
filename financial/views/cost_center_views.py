from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.http import JsonResponse

from financial.models import CostCenter, CostCenterBudget, CostCenterAuditLog


@login_required
def cost_centers_list_view(request):
    """
    شاشة شجرة ورصيد مراكز التكلفة (Cost Centers Tree & List View)
    """
    queryset = CostCenter.objects.all().order_by('tree_path')

    search_query = request.GET.get('search', '').strip()
    policy_filter = request.GET.get('policy', '').strip()

    if search_query:
        queryset = queryset.filter(code__icontains=search_query) | queryset.filter(name__icontains=search_query)

    if policy_filter in ['OPTIONAL', 'REQUIRED', 'FORBIDDEN']:
        queryset = queryset.filter(cost_center_policy=policy_filter)

    header_buttons = [
        {
            'toggle': 'modal',
            'target': '#createCostCenterModal',
            'text': 'إضافة مركز تكلفة جديد',
            'icon': 'fa-plus-circle',
            'class': 'btn-primary',
        }
    ]

    context = {
        'cost_centers': queryset,
        'search_query': search_query,
        'policy_filter': policy_filter,
        'header_buttons': header_buttons,
        'page_title': 'إدارة مراكز التكلفة',
        'page_subtitle': 'الهيكلية الشجرية والميزانيات المعتمدة لمراكز التكلفة',
        'page_icon': 'fas fa-network-wired',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الإدارة المالية', 'url': reverse('financial:chart_of_accounts_list'), 'icon': 'fas fa-calculator'},
            {'title': 'مراكز التكلفة', 'active': True}
        ]
    }
    return render(request, 'financial/cost_centers/cost_centers_list.html', context)


@login_required
def cost_center_create_view(request):
    """
    إنشاء مركز تكلفة جديد
    """
    if request.method == 'POST':
        code = request.POST.get('code', '').strip()
        name = request.POST.get('name', '').strip()
        parent_id = request.POST.get('parent')
        policy = request.POST.get('cost_center_policy', 'OPTIONAL')
        description = request.POST.get('description', '').strip()

        if not code or not name:
            messages.error(request, "كود واسم مركز التكلفة حقول مطلوبة.")
            return redirect('financial:cost_center_create')

        parent_obj = CostCenter.objects.filter(id=parent_id).first() if parent_id else None

        cc = CostCenter.objects.create(
            code=code,
            name=name,
            parent=parent_obj,
            cost_center_policy=policy
        )

        CostCenterAuditLog.objects.create(
            cost_center=cc,
            action='CREATED',
            performed_by=request.user,
            user_name_snapshot=request.user.username,
            changes_json=f'{{"code": "{code}", "name": "{name}"}}'
        )

        messages.success(request, f"تم إنشاء مركز التكلفة بنجاح: {cc.code} - {cc.name}")
        return redirect('financial:cost_centers_list')

    return redirect('financial:cost_centers_list')


@login_required
def cost_center_detail_view(request, pk):
    """
    تفاصيل مركز التكلفة
    """
    cost_center = get_object_or_404(CostCenter, pk=pk)
    children = cost_center.children.all().order_by('code')
    audit_logs = cost_center.audit_logs.all().order_by('-timestamp')[:20]

    from financial.models import JournalEntryLine
    from django.db.models import Sum

    movements = JournalEntryLine.objects.filter(
        cost_center=cost_center,
        journal_entry__status='posted'
    ).select_related('journal_entry', 'account').order_by('-journal_entry__date')[:50]

    movements_totals = movements.aggregate(
        total_debit=Sum('debit'),
        total_credit=Sum('credit')
    )

    all_cost_centers = CostCenter.objects.exclude(pk=cost_center.pk).order_by('code')

    header_buttons = [
        {
            'toggle': 'modal',
            'target': '#editCostCenterModal',
            'text': 'تعديل مركز التكلفة',
            'icon': 'fa-edit',
            'class': 'btn-primary',
        }
    ]

    context = {
        'cost_center': cost_center,
        'children': children,
        'all_cost_centers': all_cost_centers,
        'audit_logs': audit_logs,
        'movements': movements,
        'movements_totals': movements_totals,
        'header_buttons': header_buttons,
        'page_title': f'تفاصيل مركز التكلفة: {cost_center.name}',
        'page_subtitle': f'كود مركز التكلفة: {cost_center.code}',
        'page_icon': 'fas fa-network-wired',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'مراكز التكلفة', 'url': reverse('financial:cost_centers_list'), 'icon': 'fas fa-network-wired'},
            {'title': cost_center.name, 'active': True}
        ]
    }
    return render(request, 'financial/cost_centers/cost_center_detail.html', context)


@login_required
def cost_center_edit_view(request, pk):
    """
    تعديل مركز تكلفة
    """
    cost_center = get_object_or_404(CostCenter, pk=pk)

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        policy = request.POST.get('cost_center_policy', 'OPTIONAL')
        description = request.POST.get('description', '').strip()

        if not name:
            messages.error(request, "اسم مركز التكلفة مطلوب.")
            return redirect('financial:cost_center_edit', pk=pk)

        cost_center.name = name
        cost_center.cost_center_policy = policy
        cost_center.save()

        CostCenterAuditLog.objects.create(
            cost_center=cost_center,
            action='UPDATED',
            performed_by=request.user,
            user_name_snapshot=request.user.username,
            changes_json=f'{{"name": "{name}", "policy": "{policy}"}}'
        )

        messages.success(request, f"تم تعديل مركز التكلفة بنجاح: {cost_center.code}")
        return redirect('financial:cost_center_detail', pk=pk)

    return redirect('financial:cost_center_detail', pk=pk)


@login_required
def cost_center_tree_api(request):
    """
    API لاسترجاع الهيكل الشجري الكامل لمراكز التكلفة
    """
    cost_centers = CostCenter.objects.all().order_by('code')
    data = [
        {
            'id': cc.id,
            'code': cc.code,
            'name': cc.name,
            'parent_id': cc.parent_id,
            'tree_path': cc.tree_path,
            'policy': cc.cost_center_policy,
            'is_system': cc.is_system,
        }
        for cc in cost_centers
    ]
    return JsonResponse({'status': 'success', 'data': data})
