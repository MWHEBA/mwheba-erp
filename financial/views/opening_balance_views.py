import json
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils.translation import gettext as _
from django.core.paginator import Paginator
from django.utils import timezone
from django.views.decorators.http import require_POST

from financial.models.opening_balance import OpeningBalanceBatch, OpeningBalanceLine
from financial.models.fiscal_year import FiscalYear
from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.currency import Currency
from financial.services.opening_balance_service import OpeningBalancePostingService
from financial.exceptions import ImmutableLedgerError


from django.urls import reverse

@login_required
def opening_balance_list(request):
    """عرض قائمة دفعات الأرصدة الافتتاحية المنسقة"""
    batches_qs = OpeningBalanceBatch.objects.select_related('fiscal_year', 'journal_entry', 'reversal_journal_entry', 'created_by', 'posted_by').order_by('-created_at')
    
    # فلترة سريعة
    status_filter = request.GET.get('status')
    if status_filter:
        batches_qs = batches_qs.filter(status=status_filter)

    paginator = Paginator(batches_qs, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # حساب إحصائيات المؤشرات الرقمية KPI
    total_count = batches_qs.count()
    draft_count = OpeningBalanceBatch.objects.filter(status='draft').count()
    posted_count = OpeningBalanceBatch.objects.filter(status='posted').count()
    reversed_count = OpeningBalanceBatch.objects.filter(status='reversed').count()

    return render(request, 'financial/opening_balance_list.html', {
        'page_obj': page_obj,
        'batches': page_obj.object_list,
        'total_count': total_count,
        'draft_count': draft_count,
        'posted_count': posted_count,
        'reversed_count': reversed_count,
        'page_title': _("معالج الأرصدة الافتتاحية"),
        'page_subtitle': _("إدارة وتدقيق وتأكيد دفعات الأرصدة الافتتاحية للمجلس المحاسبي"),
        'page_icon': "fas fa-balance-scale",
        'breadcrumb_items': [
            {'title': _("الرئيسية"), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _("الإدارة المالية"), 'url': reverse('financial:chart_of_accounts_list'), 'icon': 'fa-calculator'},
            {'title': _("الأرصدة الافتتاحية"), 'active': True}
        ],
        'header_buttons': [
            {
                'url': reverse('financial:opening_balance_create'),
                'icon': 'fa-plus',
                'text': _("إضافة دفعة افتتاحية جديدة"),
                'class': 'btn-primary',
            }
        ]
    })


@login_required
def opening_balance_wizard(request, pk=None):
    """معالج وتفاصيل إدخال وتدقيق الأرصدة الافتتاحية"""
    if pk:
        batch = get_object_or_404(OpeningBalanceBatch.objects.select_related('fiscal_year', 'journal_entry', 'reversal_journal_entry'), pk=pk)
    else:
        # إنشاء دفعة جديدة تلقائياً
        active_year = FiscalYear.objects.filter(status='open').first() or FiscalYear.objects.exclude(status='closed').first()
        if not active_year:
            messages.error(request, _("لا توجد سنة مالية مفتوحة مسجلة بالنظام."))
            return redirect("financial:opening_balance_list")
        
        from core.services.sequence_service import SequenceService
        batch_number = SequenceService.get_next_number('OPENING_BALANCE', date=active_year.start_date)
        batch = OpeningBalanceBatch.objects.create(
            fiscal_year=active_year,
            batch_number=batch_number,
            description=_("دفعة أرصدة افتتاحية أولية"),
            status="draft",
            created_by=request.user
        )
        return redirect("financial:opening_balance_wizard_detail", pk=batch.pk)

    lines = batch.lines.select_related('account', 'currency', 'customer', 'supplier', 'treasury_account').all()
    
    total_debit = sum((l.debit for l in lines), Decimal('0.00'))
    total_credit = sum((l.credit for l in lines), Decimal('0.00'))
    balance_diff = total_debit - total_credit
    is_balanced = (balance_diff == Decimal('0.00'))

    accounts = ChartOfAccounts.objects.filter(is_active=True, is_leaf=True).order_by('code')
    currencies = Currency.objects.filter(is_active=True)

    return render(request, 'financial/opening_balance_wizard.html', {
        'batch': batch,
        'lines': lines,
        'total_debit': total_debit,
        'total_credit': total_credit,
        'balance_diff': balance_diff,
        'is_balanced': is_balanced,
        'accounts': accounts,
        'currencies': currencies,
        'page_title': f"دفعة الأرصدة الافتتاحية: {batch.batch_number}",
        'page_subtitle': _("تدقيق وتأكيد التوازن ومطابقة الدفاتر"),
        'page_icon': "fas fa-calculator",
        'breadcrumb_items': [
            {'title': _("الرئيسية"), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _("الإدارة المالية"), 'url': reverse('financial:chart_of_accounts_list'), 'icon': 'fa-calculator'},
            {'title': _("الأرصدة الافتتاحية"), 'url': reverse('financial:opening_balance_list'), 'icon': 'fa-balance-scale'},
            {'title': batch.batch_number, 'active': True}
        ],
    })


@login_required
@require_POST
def opening_balance_post_action(request, pk):
    """إجراء ترحيل الدفعة عبر OpeningBalancePostingService"""
    batch = get_object_or_404(OpeningBalanceBatch, pk=pk)
    try:
        posted_batch = OpeningBalancePostingService.post(batch.pk, request.user)
        messages.success(request, _("تم ترحيل الدفعة الافتتاحية بنجاح وتوليد القيد رقم {}").format(posted_batch.journal_entry.number if posted_batch.journal_entry else ''))
        return JsonResponse({'success': True, 'message': _("تم الترحيل بنجاح")})
    except (ValidationError, ImmutableLedgerError) as e:
        msg = e.message if hasattr(e, 'message') else str(e)
        return JsonResponse({'success': False, 'error': msg}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
def opening_balance_reverse_action(request, pk):
    """إجراء عكس الدفعة المرحّلة عبر OpeningBalancePostingService"""
    batch = get_object_or_404(OpeningBalanceBatch, pk=pk)
    reason = request.POST.get('reason', '').strip()
    if not reason:
        return JsonResponse({'success': False, 'error': _("يجب تقديم سبب لإلغاء وعكس الدفعة.")}, status=400)

    try:
        reversed_batch = OpeningBalancePostingService.reverse(batch.pk, request.user, reason)
        messages.success(request, _("تم إلغاء وعكس الدفعة الافتتاحية بنجاح وتوليد القيد العكسي رقم {}").format(reversed_batch.reversal_journal_entry.number if reversed_batch.reversal_journal_entry else ''))
        return JsonResponse({'success': True, 'message': _("تم العكس بنجاح")})
    except (ValidationError, ImmutableLedgerError) as e:
        msg = e.message if hasattr(e, 'message') else str(e)
        return JsonResponse({'success': False, 'error': msg}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
