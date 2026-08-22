import json
from decimal import Decimal
from django.db import models
from django.db.models import Q
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
from django.core.exceptions import ValidationError
from django.urls import reverse

@login_required
def opening_balance_list(request):
    """عرض قائمة دفعات الأرصدة الافتتاحية المنسقة"""
    batches_qs = OpeningBalanceBatch.objects.select_related('fiscal_year', 'journal_entry', 'reversal_journal_entry', 'created_by', 'posted_by').order_by('-created_at')
    
    # فلترة سريعة
    status_filter = request.GET.get('status')
    if status_filter:
        batches_qs = batches_qs.filter(status=status_filter)

    from core.utils import paginate_queryset
    pagination_context = paginate_queryset(batches_qs, request)
    page_obj = pagination_context["page_obj"]

    # حساب إحصائيات المؤشرات الرقمية KPI
    total_count = batches_qs.count()
    draft_count = OpeningBalanceBatch.objects.filter(status='draft').count()
    posted_count = OpeningBalanceBatch.objects.filter(status='posted').count()
    reversed_count = OpeningBalanceBatch.objects.filter(status='reversed').count()

    return render(request, 'financial/opening_balance_list.html', {
        'page_obj': page_obj,
        'batches': page_obj.object_list,
        **pagination_context,
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
        from core.enums.document_types import DocumentType
        batch_number = SequenceService.get_next_number(DocumentType.OPENING_BALANCE, date=active_year.start_date)
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
    # Empty batch cannot be balanced. Tolerates penny difference <= 0.05 EGP (Rule 3)
    is_balanced = (lines.exists() and abs(balance_diff) <= Decimal('0.05'))

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

    from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
    from client.models import Customer
    from supplier.models import Supplier

    control_codes = set()
    for role_name in [
        AccountRoleNames.CUSTOMER_RECEIVABLE_CONTROL,
        AccountRoleNames.SUPPLIER_PAYABLE_CONTROL,
        AccountRoleNames.CUSTOMER_ADVANCE_LIABILITY,
        AccountRoleNames.SUPPLIER_ADVANCE_ASSET,
        AccountRoleNames.DEFAULT_CASH_DRAWER,
        AccountRoleNames.DEFAULT_BANK_ACCOUNT,
        AccountRoleNames.INVENTORY_GENERAL,
    ]:
        try:
            code = AccountRoleRegistry.resolve_role_code(role_name)
            if code:
                control_codes.add(code)
        except Exception:
            pass

    customer_acc_ids = set(Customer.objects.filter(financial_account__isnull=False).values_list('financial_account_id', flat=True))
    supplier_acc_ids = set(Supplier.objects.filter(financial_account__isnull=False).values_list('financial_account_id', flat=True))

    control_account_ids = [
        str(acc.id) for acc in accounts 
        if acc.code in control_codes 
        or acc.id in customer_acc_ids
        or acc.id in supplier_acc_ids
        or getattr(acc, 'is_control_account', False)
        or getattr(acc, 'is_cash_account', False)
        or getattr(acc, 'is_bank_account', False)
    ]

    treasury_accounts = ChartOfAccounts.objects.filter(
        models.Q(is_cash_account=True) | models.Q(is_bank_account=True),
        is_active=True,
        is_leaf=True
    ).order_by('code')

    header_buttons = []
    if batch.status == 'draft':
        header_buttons.append({
            'toggle': 'modal',
            'target': '#importExcelModal',
            'icon': 'fa-file-excel',
            'text': _("استيراد من Excel"),
            'class': 'btn-outline-success',
        })
        header_buttons.append({
            'url': reverse('financial:opening_balance_download_template'),
            'icon': 'fa-download',
            'text': _("تحميل نموذج Excel"),
            'class': 'btn-outline-secondary',
        })
    elif batch.status == 'posted':
        header_buttons.append({
            'toggle': 'modal',
            'target': '#reverseBatchModal',
            'icon': 'fa-undo',
            'text': _("إلغاء وعكس الدفعة"),
            'class': 'btn-outline-danger',
        })
        if batch.journal_entry:
            header_buttons.append({
                'url': reverse('financial:journal_entries_detail', args=[batch.journal_entry.pk]),
                'icon': 'fa-file-invoice',
                'text': _("عرض قيد اليومية"),
                'class': 'btn-outline-primary',
            })

    header_badges = []
    if batch.status == 'posted':
        header_badges.append({'text': _("مرحلة نهائياً"), 'class': 'bg-success text-white', 'icon': 'fa-check-circle'})
        if batch.journal_entry:
            header_badges.append({
                'url': reverse('financial:journal_entries_detail', args=[batch.journal_entry.pk]),
                'text': f"{_('قيد اليومية')}: #{batch.journal_entry.number}",
                'class': 'bg-primary text-white',
                'icon': 'fa-receipt'
            })
    elif batch.status == 'reversed':
        header_badges.append({'text': _("معكوسة"), 'class': 'bg-danger text-white', 'icon': 'fa-undo'})
        if batch.reversal_journal_entry:
            header_badges.append({
                'url': reverse('financial:journal_entries_detail', args=[batch.reversal_journal_entry.pk]),
                'text': f"{_('القيد العكسي')}: #{batch.reversal_journal_entry.number}",
                'class': 'bg-danger text-white',
                'icon': 'fa-receipt'
            })
    else:
        header_badges.append({'text': _("مسودة / تحت التدقيق"), 'class': 'bg-warning text-dark', 'icon': 'fa-edit'})

    import json
    from financial.services.exchange_rate_service import ExchangeRateService

    functional_currency = Currency.objects.filter(is_functional=True).first() or Currency.objects.filter(is_active=True).first()
    func_code = functional_currency.code if functional_currency else ""

    currency_rates = {}
    for c in currencies:
        try:
            r = float(ExchangeRateService.get_rate(c.code, func_code, date=batch.opening_date))
        except Exception:
            r = 1.0
        currency_rates[str(c.id)] = {
            'code': c.code,
            'name': c.name,
            'symbol': c.symbol or c.code,
            'is_functional': c.is_functional,
            'rate': r
        }

    account_currencies = {
        str(acc.id): str(acc.currency_id) if acc.currency_id else ""
        for acc in accounts
    }

    equity_account_ids = [
        str(acc.id) for acc in accounts
        if (acc.account_type and str(acc.account_type.category).lower() == 'equity') or str(acc.code).startswith('3')
    ]

    return render(request, 'financial/opening_balance_wizard.html', {
        'batch': batch,
        'lines': lines,
        'total_debit': total_debit,
        'total_credit': total_credit,
        'balance_diff': balance_diff,
        'is_balanced': is_balanced,
        'accounts': accounts,
        'treasury_accounts': treasury_accounts,
        'currencies': currencies,
        'functional_currency': functional_currency,
        'customers': customers,
        'suppliers': suppliers,
        'currency_rates_json': json.dumps(currency_rates),
        'account_currencies_json': json.dumps(account_currencies),
        'control_account_ids_json': json.dumps(control_account_ids),
        'equity_account_ids_json': json.dumps(equity_account_ids),
        'page_title': f"دفعة الأرصدة الافتتاحية: {batch.batch_number}",
        'page_subtitle': _("تدقيق وتأكيد التوازن ومطابقة الدفاتر"),
        'page_icon': "fas fa-calculator",
        'breadcrumb_items': [
            {'title': _("الرئيسية"), 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': _("الإدارة المالية"), 'url': reverse('financial:chart_of_accounts_list'), 'icon': 'fa-calculator'},
            {'title': _("الأرصدة الافتتاحية"), 'url': reverse('financial:opening_balance_list'), 'icon': 'fa-balance-scale'},
            {'title': batch.batch_number, 'active': True}
        ],
        'header_buttons': header_buttons,
        'header_badges': header_badges,
    })


@login_required
def _get_opening_balance_rendered_response(request, batch, message=""):
    """دالة مساعدة لحساب المجاميع وتوليد HTML البارتشال للجداول والكروت تفاعلياً"""
    from django.template.loader import render_to_string
    lines = batch.lines.select_related('account', 'customer', 'supplier', 'treasury_account', 'currency').all()
    total_debit = sum((l.debit for l in lines), Decimal('0.00'))
    total_credit = sum((l.credit for l in lines), Decimal('0.00'))
    balance_diff = abs(total_debit - total_credit)
    is_balanced = (balance_diff <= Decimal('0.05') and len(lines) > 0 and (total_debit > 0 or total_credit > 0))

    context = {
        'batch': batch,
        'lines': lines,
        'total_debit': total_debit,
        'total_credit': total_credit,
        'balance_diff': balance_diff,
        'is_balanced': is_balanced,
    }

    summary_html = render_to_string('financial/partials/opening_balance_summary_cards_partial.html', context, request=request)
    table_html = render_to_string('financial/partials/opening_balance_lines_table_partial.html', context, request=request)

    return {
        'success': True,
        'message': message,
        'summary_html': summary_html,
        'table_html': table_html,
        'is_balanced': is_balanced,
        'lines_count': len(lines),
        'total_debit': str(total_debit),
        'total_credit': str(total_credit),
        'balance_diff': str(balance_diff),
    }


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
        exchange_rate = Decimal(request.POST.get('exchange_rate', '1.000000'))
        customer_id = request.POST.get('customer_id') or None
        supplier_id = request.POST.get('supplier_id') or None
        treasury_account_id = request.POST.get('treasury_account_id') or None

        if line_type == 'EQUITY':
            currency_id = None
            debit_foreign = Decimal('0.00')
            credit_foreign = Decimal('0.00')
            exchange_rate = Decimal('1.000000')
        elif currency_id:
            from financial.models.currency import Currency
            curr = Currency.objects.filter(pk=currency_id).first()
            if curr and not curr.is_functional:
                debit_foreign = debit
                credit_foreign = credit
                debit = (debit_foreign * exchange_rate).quantize(Decimal('0.01'))
                credit = (credit_foreign * exchange_rate).quantize(Decimal('0.01'))
            else:
                currency_id = None
                debit_foreign = Decimal('0.00')
                credit_foreign = Decimal('0.00')
                exchange_rate = Decimal('1.000000')
        else:
            debit_foreign = Decimal('0.00')
            credit_foreign = Decimal('0.00')
            exchange_rate = Decimal('1.000000')

        # Auto-resolve account_id based on line_type
        if line_type == 'AR' and customer_id:
            from client.models import Customer
            from client.services.customer_service import CustomerService
            customer = Customer.objects.filter(pk=customer_id).first()
            if customer:
                if not customer.financial_account_id:
                    acc = CustomerService.create_financial_account_for_customer(customer, user=request.user)
                    account_id = acc.id
                else:
                    account_id = customer.financial_account_id
        elif line_type == 'AP' and supplier_id:
            from supplier.models import Supplier
            from supplier.services.supplier_service import SupplierService
            supplier = Supplier.objects.filter(pk=supplier_id).first()
            if supplier:
                if not supplier.financial_account_id:
                    acc = SupplierService.create_financial_account_for_supplier(supplier, user=request.user)
                    account_id = acc.id
                else:
                    account_id = supplier.financial_account_id
        elif line_type == 'TREASURY' and treasury_account_id:
            account_id = treasury_account_id
        elif line_type == 'INVENTORY' and not account_id:
            from financial.services.role_registry import AccountRoleRegistry
            account_id = AccountRoleRegistry.get_account("INVENTORY_GENERAL").id

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
            customer_id=customer_id if line_type == 'AR' else None,
            supplier_id=supplier_id if line_type == 'AP' else None,
            treasury_account_id=treasury_account_id if line_type == 'TREASURY' else None
        )
        line.full_clean()
        line.save()

        resp = _get_opening_balance_rendered_response(request, batch, message=_("تمت إضافة السطر بنجاح"))
        return JsonResponse(resp)
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
    resp = _get_opening_balance_rendered_response(request, batch, message=_("تم حذف سطر الرصيد الافتتاحي بنجاح."))
    return JsonResponse(resp)


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
        valid_rows, invalid_rows = ExcelImportService.validate_rows(raw_rows, batch=batch)

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


@login_required
def opening_balance_get_balancing_options(request, pk):
    """جلب خيارات وتحليلات الموازنة الذكية عبر AJAX"""
    batch = get_object_or_404(OpeningBalanceBatch, pk=pk)
    try:
        from financial.services.opening_balance_balancing_service import SmartBalancingService
        analysis = SmartBalancingService.get_balancing_analysis(batch)
        return JsonResponse({'success': True, 'data': analysis})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
def opening_balance_apply_balancing_action(request, pk):
    """تطبيق الموازنة الذكية (كاملة أو Split أو دمج) عبر AJAX"""
    batch = get_object_or_404(OpeningBalanceBatch, pk=pk)
    if batch.status in ['posted', 'reversed']:
        return JsonResponse({'success': False, 'error': _("لا يمكن موازنة دفعة مرحلة أو معكوسة.")}, status=400)

    try:
        import json
        payload = json.loads(request.body.decode('utf-8')) if request.body else {}
        mode = payload.get('mode', 'SINGLE')
        data = payload.get('data', {})

        from financial.services.opening_balance_balancing_service import SmartBalancingService
        result = SmartBalancingService.apply_balancing(batch, mode, data, request.user)
        resp = _get_opening_balance_rendered_response(request, batch, message=result.get('message', _("تمت موازنة الدفعة بنجاح.")))
        resp.update(result)
        return JsonResponse(resp)
    except (ValidationError, ImmutableLedgerError) as e:
        msg = e.message if hasattr(e, 'message') else str(e)
        return JsonResponse({'success': False, 'error': msg}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


