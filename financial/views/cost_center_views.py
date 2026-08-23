from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.db.models import Sum
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from django.db import models
from financial.models import CostCenter, CostCenterBudget, CostCenterBalanceSnapshot, CostCenterAuditLog, JournalEntryLine
from financial.services.cost_center_code_service import CostCenterCodeService


@login_required
@require_http_methods(["GET"])
def suggest_cost_center_code(request):
    """
    API endpoint للحصول على كود مقترح لمركز التكلفة بناءً على المركز الأب
    """
    parent_id = request.GET.get('parent_id')
    try:
        parent_id = int(parent_id) if parent_id else None
    except (ValueError, TypeError):
        parent_id = None

    suggested_code = CostCenterCodeService.get_next_code(parent_id=parent_id)
    return JsonResponse({
        'success': True,
        'suggested_code': suggested_code
    })


@login_required
def cost_centers_list_view(request):
    """
    شاشة شجرة ورصيد مراكز التكلفة والموازنة المعتمدة (Cost Centers Tree, Budgets & Balance View)
    """
    queryset = CostCenter.objects.all().order_by('tree_path')

    search_query = request.GET.get('search', '').strip()
    policy_filter = request.GET.get('policy', '').strip()

    if search_query:
        from utils.search import smart_search_filter
        queryset = smart_search_filter(
            queryset,
            search_query,
            text_fields=['name', 'description'],
            code_fields=['code']
        )

    if policy_filter in ['OPTIONAL', 'REQUIRED', 'FORBIDDEN']:
        queryset = queryset.filter(cost_center_policy=policy_filter)

    # جلب الموازنات الفعالة المعتمدة لكل مركز تكلفة
    active_budgets = {}
    for b in CostCenterBudget.objects.filter(status='APPROVED').select_related('fiscal_year'):
        active_budgets[b.cost_center_id] = b

    for cc in queryset:
        cc.active_budget = active_budgets.get(cc.id)
        if cc.active_budget:
            snapshots = CostCenterBalanceSnapshot.objects.filter(cost_center=cc)
            cc.total_debit = snapshots.aggregate(s=Sum('total_debit'))['s'] or Decimal('0.00')
            cc.total_credit = snapshots.aggregate(s=Sum('total_credit'))['s'] or Decimal('0.00')
            cc.actual_spent = cc.total_debit - cc.total_credit
            cc.budget_amount = cc.active_budget.current_budget
            cc.variance = cc.budget_amount - cc.actual_spent
            cc.usage_pct = round(float(cc.actual_spent / cc.budget_amount * 100), 1) if cc.budget_amount > 0 else 0
        else:
            cc.actual_spent = Decimal('0.00')
            cc.budget_amount = Decimal('0.00')
            cc.variance = Decimal('0.00')
            cc.usage_pct = 0

    header_buttons = [
        {
            'toggle': 'modal',
            'target': '#createCostCenterModal',
            'text': 'إضافة مركز تكلفة جديد',
            'icon': 'fa-plus-circle',
            'class': 'btn-primary',
        }
    ]

    suggested_code = CostCenterCodeService.get_next_root_code()

    context = {
        'cost_centers': queryset,
        'search_query': search_query,
        'policy_filter': policy_filter,
        'header_buttons': header_buttons,
        'suggested_code': suggested_code,
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
    إنشاء مركز تكلفة جديد مع التوليد التلقائي للكود
    """
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        parent_id = request.POST.get('parent')
        policy = request.POST.get('cost_center_policy', 'OPTIONAL')

        if not name:
            messages.error(request, "اسم مركز التكلفة حقل مطلوب.")
            return redirect('financial:cost_centers_list')

        parent_obj = CostCenter.objects.filter(id=parent_id).first() if parent_id else None

        cc = CostCenter.objects.create(
            name=name,
            parent=parent_obj,
            cost_center_policy=policy
        )

        CostCenterAuditLog.objects.create(
            cost_center=cc,
            action='CREATED',
            performed_by=request.user,
            user_name_snapshot=request.user.username,
            changes_json=f'{{"code": "{cc.code}", "name": "{name}"}}'
        )

        messages.success(request, f"تم إنشاء مركز التكلفة بنجاح: {cc.code} - {cc.name}")
        return redirect('financial:cost_centers_list')

    return redirect('financial:cost_centers_list')


@login_required
def cost_center_detail_view(request, pk):
    """
    تفاصيل مركز التكلفة ورابط الموازنة والانحرافات
    """
    cost_center = get_object_or_404(CostCenter, pk=pk)
    children = cost_center.children.all().order_by('code')
    audit_logs = cost_center.audit_logs.all().order_by('-timestamp')[:20]

    movements = JournalEntryLine.objects.filter(
        cost_center=cost_center,
        journal_entry__status='posted'
    ).select_related('journal_entry', 'account').order_by('-journal_entry__date')[:50]

    movements_totals = movements.aggregate(
        total_debit=Sum('debit'),
        total_credit=Sum('credit')
    )

    # الموازنة التقديرية المعتمدة الفعالة لمركز التكلفة
    active_budget = CostCenterBudget.objects.filter(
        cost_center=cost_center,
        status='APPROVED'
    ).order_by('-version').first()

    budget_summary = {
        'allocated_amount': Decimal('0.00'),
        'actual_spent': Decimal('0.00'),
        'variance': Decimal('0.00'),
        'usage_pct': 0,
    }

    if active_budget:
        budget_summary['allocated_amount'] = active_budget.current_budget
        snapshots = CostCenterBalanceSnapshot.objects.filter(cost_center=cost_center)
        total_debit = snapshots.aggregate(s=Sum('total_debit'))['s'] or Decimal('0.00')
        total_credit = snapshots.aggregate(s=Sum('total_credit'))['s'] or Decimal('0.00')
        budget_summary['actual_spent'] = total_debit - total_credit
        budget_summary['variance'] = budget_summary['allocated_amount'] - budget_summary['actual_spent']
        if budget_summary['allocated_amount'] > 0:
            budget_summary['usage_pct'] = round(float(budget_summary['actual_spent'] / budget_summary['allocated_amount'] * 100), 1)

    all_cost_centers = CostCenter.objects.exclude(pk=cost_center.pk).order_by('code')

    header_buttons = [
        {
            'toggle': 'modal',
            'target': '#editCostCenterModal',
            'text': 'تعديل',
            'icon': 'fa-edit',
            'class': 'btn-outline-primary',
        },
        {
            'url': reverse('financial:cost_center_delete', kwargs={'pk': cost_center.pk}),
            'text': 'حذف',
            'icon': 'fa-trash-alt',
            'class': 'btn-outline-danger',
        },
        {
            'url': reverse('financial:cost_centers_list'),
            'text': 'العودة للقائمة',
            'icon': 'fa-arrow-right',
            'class': 'btn-outline-secondary',
        },
    ]

    context = {
        'cost_center': cost_center,
        'children': children,
        'all_cost_centers': all_cost_centers,
        'audit_logs': audit_logs,
        'movements': movements,
        'movements_totals': movements_totals,
        'active_budget': active_budget,
        'budget_summary': budget_summary,
        'header_buttons': header_buttons,
        'suggested_child_code': CostCenterCodeService.get_next_child_code(cost_center),
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
def cost_center_delete_view(request, pk):
    """
    حذف أو أرشفة مركز تكلفة مع حماية الشجرة والقيود المحاسبية وكائنات النظام
    """
    cost_center = get_object_or_404(CostCenter, pk=pk)
    has_children = cost_center.children.exists()
    children_count = cost_center.children.count() if has_children else 0

    from financial.models import JournalEntryLine
    has_movements = JournalEntryLine.objects.filter(
        models.Q(cost_center=cost_center) | models.Q(cost_allocations__cost_center=cost_center)
    ).exists()
    movements_count = JournalEntryLine.objects.filter(
        models.Q(cost_center=cost_center) | models.Q(cost_allocations__cost_center=cost_center)
    ).count() if has_movements else 0

    has_budgets = CostCenterBudget.objects.filter(cost_center=cost_center).exists()
    
    can_delete_permanently = (not cost_center.is_system and not has_children and not has_movements and not has_budgets)
    can_archive = (not cost_center.is_system and not has_children and (has_movements or has_budgets))

    if request.method == "POST":
        if cost_center.is_system:
            messages.error(request, f'حظر الحوكمة: لا يمكن حذف مركز تكلفة تابع للنظام: "{cost_center.name}".')
            return redirect('financial:cost_center_detail', pk=pk)

        if has_children:
            messages.error(request, f'لا يمكن حذف أو أرشفة مركز التكلفة "{cost_center.name}" لأنه يحتوي على {children_count} مركز فرعي. يرجى نقل أو حذف المراكز الفرعية أولاً.')
            return redirect('financial:cost_center_detail', pk=pk)

        if can_delete_permanently:
            cc_name = cost_center.name
            cc_code = cost_center.code
            cost_center.delete()
            messages.success(request, f'تم حذف مركز التكلفة "{cc_name}" ({cc_code}) نهائياً.')
            return redirect('financial:cost_centers_list')
        else:
            cost_center.is_active = False
            cost_center.save(update_fields=['is_active'])
            CostCenterAuditLog.objects.create(
                cost_center=cost_center,
                action='DEACTIVATED',
                performed_by=request.user,
                user_name_snapshot=request.user.username,
                changes_json='{"is_active": false}'
            )
            messages.warning(request, f'تمت أرشفة وتعطيل مركز التكلفة "{cost_center.name}" بنجاح لوجود حركات محاسبية مرتبطة.')
            return redirect('financial:cost_centers_list')

    context = {
        "cost_center": cost_center,
        "has_children": has_children,
        "children_count": children_count,
        "has_movements": has_movements,
        "movements_count": movements_count,
        "has_budgets": has_budgets,
        "can_delete_permanently": can_delete_permanently,
        "can_archive": can_archive,
        "page_title": f"حذف / أرشفة مركز تكلفة: {cost_center.name}",
        "page_icon": "fas fa-trash-alt",
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "مراكز التكلفة", "url": reverse("financial:cost_centers_list"), "icon": "fas fa-network-wired"},
            {"title": cost_center.name, "url": reverse("financial:cost_center_detail", kwargs={"pk": cost_center.pk})},
            {"title": "حذف / أرشفة", "active": True},
        ]
    }
    return render(request, "financial/cost_centers/cost_center_delete.html", context)


@login_required
def cost_center_edit_view(request, pk):
    """
    تعديل مركز تكلفة
    """
    cost_center = get_object_or_404(CostCenter, pk=pk)

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        policy = request.POST.get('cost_center_policy', 'OPTIONAL')

        if not name:
            messages.error(request, "اسم مركز التكلفة مطلوب.")
            return redirect('financial:cost_center_detail', pk=pk)

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

        messages.success(request, f"تم تحديث بيانات مركز التكلفة بنجاح: {cost_center.code}")
        return redirect('financial:cost_center_detail', pk=pk)

    return redirect('financial:cost_center_detail', pk=pk)


@login_required
def cost_center_tree_api(request):
    """
    API استرجاع الهيكل الشجري لمراكز التكلفة
    """
    cost_centers = CostCenter.objects.all().order_by('code')
    data = [
        {
            'id': cc.id,
            'code': cc.code,
            'name': cc.name,
            'parent_id': cc.parent_id,
            'policy': cc.cost_center_policy
        }
        for cc in cost_centers
    ]
    return JsonResponse({'status': 'success', 'cost_centers': data})
