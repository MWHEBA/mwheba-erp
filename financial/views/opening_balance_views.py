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
        # الحصول على السنة المالية النشطة أو إنشاؤها وتفعيلها تلقائياً
        from financial.services.period_control_service import PeriodControlService
        active_year = PeriodControlService.get_or_create_active_fiscal_year()
        
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
    # Empty batch cannot be balanced
    is_balanced = (lines.exists() and balance_diff == Decimal('0.00'))

    accounts = ChartOfAccounts.objects.filter(is_active=True, is_leaf=True).order_by('code')
    currencies = Currency.objects.filter(is_active=True)

    try:
        from client.models import Customer
        customers = Customer.objects.filter(is_active=True)
    except Exception:
        customers = []

    try:
        from supplier.models import Supplier
        suppliers = Supplier.objects.filter(is_active=True)
    except Exception:
        suppliers = []

    return render(request, 'financial/opening_balance_wizard.html', {
        'batch': batch,
        'lines': lines,
        'total_debit': total_debit,
        'total_credit': total_credit,
        'balance_diff': balance_diff,
        'is_balanced': is_balanced,
        'accounts': accounts,
        'currencies': currencies,
        'customers': customers,
        'suppliers': suppliers,
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
def opening_balance_add_line_action(request, pk):
    """إضافة سطر رصيد افتتاحي تفاعلياً للدفعة المسودة"""
    batch = get_object_or_404(OpeningBalanceBatch, pk=pk)
    if batch.status in ['posted', 'reversed']:
        return JsonResponse({'success': False, 'error': _("لا يمكن تعديل أسطر دفعة مرحلة أو معكوسة.")}, status=400)

    try:
        line_type = request.POST.get('line_type', 'GL')
        account_id = request.POST.get('account_id')
        debit = Decimal(request.POST.get('debit', '0.00'))
        credit = Decimal(request.POST.get('credit', '0.00'))

        currency_id = request.POST.get('currency_id') or None
        debit_foreign = Decimal(request.POST.get('debit_foreign', '0.00'))
        credit_foreign = Decimal(request.POST.get('credit_foreign', '0.00'))
        exchange_rate = Decimal(request.POST.get('exchange_rate', '1.000000'))

        customer_id = request.POST.get('customer_id') or None
        supplier_id = request.POST.get('supplier_id') or None
        treasury_account_id = request.POST.get('treasury_account_id') or None

        line = OpeningBalanceLine(
            batch=batch,
            line_type=line_type,
            account_id=account_id,
            debit=debit,
            credit=credit,
            currency_id=currency_id,
            debit_foreign=debit_foreign,
            credit_foreign=credit_foreign,
            exchange_rate=exchange_rate,
            customer_id=customer_id,
            supplier_id=supplier_id,
            treasury_account_id=treasury_account_id
        )
        line.full_clean()
        line.save()

        messages.success(request, _("تمت إضافة سطر الرصيد الافتتاحي بنجاح."))
        return JsonResponse({'success': True, 'message': _("تمت إضافة السطر بنجاح")})
    except ValidationError as e:
        msg = e.message_dict if hasattr(e, 'message_dict') else (e.message if hasattr(e, 'message') else str(e))
        return JsonResponse({'success': False, 'error': str(msg)}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
def opening_balance_delete_line_action(request, pk, line_pk):
    """حذف سطر رصيد افتتاحي من الدفعة المسودة"""
    batch = get_object_or_404(OpeningBalanceBatch, pk=pk)
    if batch.status in ['posted', 'reversed']:
        return JsonResponse({'success': False, 'error': _("لا يمكن حذف أسطر دفعة مرحلة أو معكوسة.")}, status=400)

    line = get_object_or_404(OpeningBalanceLine, pk=line_pk, batch=batch)
    line.delete()
    messages.success(request, _("تم حذف سطر الرصيد الافتتاحي."))
    return JsonResponse({'success': True, 'message': _("تم الحذف بنجاح")})


@login_required
@require_POST
def opening_balance_import_excel_action(request, pk):
    """رفع واستيراد شيت الأرصدة الافتتاحية من Excel/CSV"""
    batch = get_object_or_404(OpeningBalanceBatch, pk=pk)
    if batch.status in ['posted', 'reversed']:
        return JsonResponse({'success': False, 'error': _("لا يمكن الاستيراد على دفعة مرحلة أو معكوسة.")}, status=400)

    file_obj = request.FILES.get('excel_file')
    if not file_obj:
        return JsonResponse({'success': False, 'error': _("يرجى اختيار ملف Excel أو CSV للرفع.")}, status=400)

    try:
        from financial.services.excel_import_service import ExcelImportService
        raw_rows = ExcelImportService.parse(file_obj)
        valid_rows, invalid_rows = ExcelImportService.validate_rows(raw_rows)

        if not valid_rows:
            return JsonResponse({'success': False, 'error': _("لم يتم العثور على صفوف صحيحة للاستيراد. يرجى مراجعة أكواد الحسابات والمبالغ.")}, status=400)

        import_record = ExcelImportService.commit(batch, valid_rows, request.user, filename=file_obj.name)
        messages.success(request, _("تم استيراد {} سطر صحيح بنجاح من الشيت.").format(import_record.valid_rows))
        return JsonResponse({'success': True, 'valid_count': import_record.valid_rows, 'invalid_count': len(invalid_rows)})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def opening_balance_download_template(request):
    """تحميل قالب Excel المعياري للأرصدة الافتتاحية"""
    import csv
    from django.http import HttpResponse
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="opening_balances_template_v1.0.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['kood_alhesab', 'account_code', 'line_type', 'debit', 'credit', 'currency_code', 'exchange_rate', 'customer_id', 'supplier_id', 'description'])
    writer.writerow(['10100', '10100', 'GL', '50000.00', '0.00', 'EGP', '1.0', '', '', 'رصيد افتتاحي الخزينة الرئيسية'])
    writer.writerow(['11010', '11010', 'AR', '12000.00', '0.00', 'USD', '50.0', '1', '', 'رصيد افتتاحي للعميل'])
    return response


@login_required
@require_POST
def opening_balance_retry_inventory_sync_action(request, pk):
    """إعادة محاولة مزامنة المخزون للدفعة المرحلة"""
    batch = get_object_or_404(OpeningBalanceBatch, pk=pk)
    try:
        updated_batch = OpeningBalancePostingService.retry_inventory_sync(batch.pk, request.user)
        if updated_batch.inventory_sync_status == 'COMPLETED':
            messages.success(request, _("تمت مزامنة كميات وتكلفة المخزون بنجاح."))
            return JsonResponse({'success': True, 'status': 'COMPLETED'})
        else:
            return JsonResponse({'success': False, 'error': updated_batch.last_error or _("فشلت إعادة محاولة المزامنة.")}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


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

