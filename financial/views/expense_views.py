# financial/views/expense_views.py
# عروض إدارة المصروفات

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.utils.translation import gettext as _
from datetime import datetime
from decimal import Decimal

from ..models import JournalEntry, ChartOfAccounts, JournalEntryLine
from ..services.account_helper import AccountHelperService
from .shared_helpers import (
    validate_transaction_data,
    create_journal_entry_for_expense,
    prepare_list_context
)


@login_required
def expense_list(request):
    """عرض قائمة المصروفات من القيود المحاسبية"""
    
    # فلترة القيود التي تحتوي على مصروفات (من الأحدث للأقدم)
    expense_entries = (
        JournalEntry.objects.filter(
            lines__account__account_type__category="expense", 
            lines__debit__gt=0
        )
        .order_by("-date", "-id")
        .distinct()
    )

    accounts = AccountHelperService.get_all_active_accounts()

    # فلترة
    account_id = request.GET.get("account")
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")

    if account_id:
        account = get_object_or_404(ChartOfAccounts, id=account_id)
        expense_entries = expense_entries.filter(lines__account=account).distinct()

    if date_from:
        date_from = datetime.strptime(date_from, "%Y-%m-%d").date()
        expense_entries = expense_entries.filter(date__gte=date_from)

    if date_to:
        date_to = datetime.strptime(date_to, "%Y-%m-%d").date()
        expense_entries = expense_entries.filter(date__lte=date_to)

    # إحصائيات
    total_expenses = 0
    for entry in expense_entries:
        expense_lines = entry.lines.filter(
            account__account_type__category="expense", 
            debit__gt=0
        )
        total_expenses += sum(line.debit for line in expense_lines)

    # تعريف رؤوس الأعمدة للجدول
    headers = [
        {"key": "number", "label": "رقم القيد", "sortable": True, "width": "10%"},
        {
            "key": "date",
            "label": "التاريخ",
            "sortable": True,
            "format": "date",
            "class": "text-center",
            "width": "14%",
        },
        {
            "key": "description",
            "label": "البيان",
            "sortable": False,
            "ellipsis": True,
            "width": "auto",
        },
        {
            "key": "expense_amount",
            "label": "قيمة المصروف",
            "sortable": False,
            "template": "components/cells/expense_amount.html",
            "class": "text-center",
            "width": "15%",
        },
        {
            "key": "expense_accounts",
            "label": "حسابات المصروف",
            "sortable": False,
            "width": "20%",
        },
        {
            "key": "status",
            "label": "الحالة",
            "sortable": False,
            "template": "components/cells/expense_status.html",
            "class": "text-center",
            "width": "10%",
        },
    ]

    # تعريف أزرار الإجراءات
    action_buttons = [
        {
            "url": "financial:transaction_detail",
            "icon": "fa-eye",
            "label": "عرض",
            "class": "action-view",
        },
        {
            "onclick": "openPostModal({id})",
            "icon": "fa-check-circle",
            "label": "ترحيل",
            "class": "action-post btn-success",
            "condition": "status == 'draft'",
        }
    ]

    # إعداد بيانات محسنة لكل قيد
    enhanced_entries = prepare_list_context(expense_entries, 'expense')

    # إعداد الترقيم الصفحي
    paginator = Paginator(enhanced_entries, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "expenses": page_obj,
        "journal_entries": page_obj,
        "expense_headers": headers,
        "expense_actions": action_buttons,
        "primary_key": "id",
        "accounts": accounts,
        "total_expenses": total_expenses,
        "page_title": "المصروفات",
        "page_subtitle": "إدارة وتتبع المصروفات في النظام",
        "page_icon": "fas fa-money-bill-wave",
        "header_buttons": [
            {
                "url": "#",
                "icon": "fa-plus",
                "text": "إضافة مصروف",
                "class": "btn-primary",
                "id": "addExpenseBtn",
            },
        ],
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "الإدارة المالية", "url": "#", "icon": "fas fa-money-bill-wave"},
            {"title": "المصروفات", "active": True},
        ],
    }

    return render(request, "financial/expenses/expense_list.html", context)


@login_required
def expense_create(request):
    """إنشاء مصروف جديد - يدعم AJAX"""
    
    if request.method != 'POST':
        return redirect('financial:expense_list')
    
    try:
        # التحقق من البيانات
        is_valid, errors, cleaned_data = validate_transaction_data(
            request.POST, 
            transaction_type='expense'
        )
        
        if not is_valid:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'errors': errors,
                    'message': _('يرجى تصحيح الأخطاء')
                })
            for field, field_errors in errors.items():
                for error in field_errors:
                    messages.error(request, error)
            return redirect('financial:expense_list')
        
        # إنشاء القيد المحاسبي
        journal_entry = create_journal_entry_for_expense(cleaned_data, request.user)
        
        success_msg = _('تم إنشاء المصروف بنجاح')
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': success_msg,
                'redirect_url': reverse('financial:expense_list')
            })
        
        messages.success(request, success_msg)
        return redirect('financial:expense_list')
        
    except Exception as e:
        error_msg = _('حدث خطأ أثناء إنشاء المصروف: {}').format(str(e))
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'message': error_msg
            })
        messages.error(request, error_msg)
        return redirect('financial:expense_list')


@login_required
def expense_detail(request, pk):
    """عرض تفاصيل مصروف معين"""
    
    try:
        journal_entry = get_object_or_404(JournalEntry, pk=pk)

        # استخراج معلومات المصروف من بنود القيد
        expense_lines = journal_entry.lines.filter(debit__gt=0)
        payment_lines = journal_entry.lines.filter(credit__gt=0)

        expense_amount = sum(line.debit for line in expense_lines)

        context = {
            "journal_entry": journal_entry,
            "expense_lines": expense_lines,
            "payment_lines": payment_lines,
            "expense_amount": expense_amount,
            "page_title": f"تفاصيل المصروف - {journal_entry.number}",
            "page_subtitle": "عرض تفاصيل المصروف والقيد المحاسبي المرتبط",
            "page_icon": "fas fa-receipt",
            "breadcrumb_items": [
                {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
                {"title": "المصروفات", "url": reverse("financial:expense_list"), "icon": "fas fa-money-bill-wave"},
                {"title": f"المصروف {journal_entry.number}", "active": True},
            ],
            "header_buttons": [
                {
                    "url": reverse("financial:expense_list"),
                    "icon": "fa-arrow-left",
                    "text": "العودة للقائمة",
                    "class": "btn-secondary",
                }
            ],
        }

        return render(request, "financial/expense_detail.html", context)

    except Exception as e:
        messages.error(request, f"خطأ في تحميل تفاصيل المصروف: {str(e)}")
        return redirect("financial:expense_list")


@login_required
def expense_edit(request, pk):
    """تعديل مصروف"""
    journal_entry = get_object_or_404(JournalEntry, pk=pk)
    
    # التحقق من أن القيد غير مرحل
    if journal_entry.status == 'posted':
        messages.error(request, "لا يمكن تعديل قيد مرحل. يجب إلغاء الترحيل أولاً.")
        return redirect("financial:expense_detail", pk=pk)
    
    if request.method == "POST":
        try:
            # التحقق من البيانات
            is_valid, errors, cleaned_data = validate_transaction_data(
                request.POST, 
                transaction_type='expense'
            )
            
            if not is_valid:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'errors': errors,
                        'message': _('يرجى تصحيح الأخطاء')
                    })
                for field, field_errors in errors.items():
                    for error in field_errors:
                        messages.error(request, error)
                return redirect("financial:expense_detail", pk=pk)
            
            # تحديث القيد المحاسبي
            journal_entry.date = cleaned_data['date']
            journal_entry.description = cleaned_data['description']
            journal_entry.notes = cleaned_data.get('notes', '')
            
            # حذف البنود القديمة
            journal_entry.lines.all().delete()
            
            # إنشاء البنود الجديدة
            expense_account = get_object_or_404(ChartOfAccounts, id=cleaned_data['account_id'])
            payment_account = get_object_or_404(ChartOfAccounts, id=cleaned_data['payment_account_id'])
            
            # سطر المدين (حساب المصروف)
            JournalEntryLine.objects.create(
                journal_entry=journal_entry,
                account=expense_account,
                debit=cleaned_data['amount'],
                credit=Decimal('0'),
                description=cleaned_data['description']
            )
            
            # سطر الدائن (الخزينة)
            JournalEntryLine.objects.create(
                journal_entry=journal_entry,
                account=payment_account,
                debit=Decimal('0'),
                credit=cleaned_data['amount'],
                description=cleaned_data['description']
            )
            
            journal_entry.save()
            
            success_msg = _('تم تحديث المصروف بنجاح')
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': success_msg,
                    'redirect_url': reverse('financial:expense_detail', args=[pk])
                })
            
            messages.success(request, success_msg)
            return redirect('financial:expense_detail', pk=pk)
            
        except Exception as e:
            error_msg = _('حدث خطأ أثناء تحديث المصروف: {}').format(str(e))
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': error_msg
                })
            messages.error(request, error_msg)
            return redirect('financial:expense_detail', pk=pk)
    
    # GET request - عرض نموذج التعديل
    # استخراج البيانات من القيد
    expense_lines = journal_entry.lines.filter(
        account__account_type__category="expense", 
        debit__gt=0
    )
    payment_lines = journal_entry.lines.filter(
        account__account_type__category__in=["asset", "liability"], 
        credit__gt=0
    )
    
    expense_account = expense_lines.first().account if expense_lines.exists() else None
    payment_account = payment_lines.first().account if payment_lines.exists() else None
    expense_amount = expense_lines.first().debit if expense_lines.exists() else 0
    
    accounts = AccountHelperService.get_all_active_accounts()
    
    context = {
        "journal_entry": journal_entry,
        "expense_account": expense_account,
        "payment_account": payment_account,
        "expense_amount": expense_amount,
        "accounts": accounts,
    }
    
    # للطلبات AJAX، إرجاع المودال فقط
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request, "financial/components/quick_expense_modal.html", context)
    
    # للطلبات العادية، إرجاع صفحة كاملة
    context.update({
        "page_title": f"تعديل مصروف - {journal_entry.number}",
        "page_subtitle": "تعديل بيانات المصروف",
        "page_icon": "fas fa-edit",
    })
    return render(request, "financial/expenses/expense_edit.html", context)
