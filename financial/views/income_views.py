# financial/views/income_views.py
# عروض إدارة الإيرادات

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
    create_journal_entry_for_income,
    prepare_list_context
)

@login_required
def income_list(request):
    """
    عرض قائمة الإيرادات من القيود المحاسبية
    يعرض فقط الإيرادات المباشرة (FinancialTransaction من نوع income)
    """
    # فلترة القيود التي source_model = FinancialTransaction ونوعها income
    income_entries = (
        JournalEntry.objects.filter(
            source_module='financial',
            source_model='FinancialTransaction'
        )
        .select_related('financial_category', 'financial_subcategory')
        .order_by("-date", "-id")
    )
    
    # فلترة الإيرادات فقط (استبعاد المصروفات)
    from ..models import FinancialTransaction
    income_transaction_ids = FinancialTransaction.objects.filter(
        transaction_type='income'
    ).values_list('id', flat=True)
    
    income_entries = income_entries.filter(source_id__in=income_transaction_ids)

    accounts = AccountHelperService.get_all_active_accounts()

    # فلترة
    account_id = request.GET.get("account")
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    
    # تعيين التواريخ الافتراضية إذا لم يتم تحديدها
    from datetime import date
    if not date_from:
        # أول يوم في الشهر الحالي
        today = date.today()
        date_from = date(today.year, today.month, 1).strftime("%Y-%m-%d")
    
    if not date_to:
        # تاريخ اليوم
        date_to = date.today().strftime("%Y-%m-%d")

    if account_id:
        account = get_object_or_404(ChartOfAccounts, id=account_id)
        income_entries = income_entries.filter(lines__account=account).distinct()

    if date_from:
        date_from_obj = datetime.strptime(date_from, "%Y-%m-%d").date()
        income_entries = income_entries.filter(date__gte=date_from_obj)

    if date_to:
        date_to_obj = datetime.strptime(date_to, "%Y-%m-%d").date()
        income_entries = income_entries.filter(date__lte=date_to_obj)

    # تعريف رؤوس الأعمدة للجدول
    headers = [
        {"key": "number", "label": "رقم القيد", "sortable": True, "width": "10%"},
        {
            "key": "date",
            "label": "التاريخ",
            "sortable": True,
            "format": "date",
            "class": "text-center",
            "width": "120px",
        },
        {
            "key": "description",
            "label": "البيان",
            "sortable": False,
            "ellipsis": True,
            "width": "auto",
        },
        {
            "key": "income_amount",
            "label": "قيمة الإيراد",
            "sortable": False,
            "template": "components/cells/income_amount.html",
            "class": "text-center",
            "width": "15%",
        },
        {
            "key": "income_accounts",
            "label": "التصنيف المالي",
            "sortable": False,
            "width": "20%",
        },
        {
            "key": "status",
            "label": "الحالة",
            "sortable": False,
            "template": "components/cells/income_status.html",
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
    enhanced_entries = prepare_list_context(income_entries, 'income')

    # إعداد الترقيم الصفحي
    paginator = Paginator(enhanced_entries, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "incomes": page_obj,  # للتوافق مع template
        "journal_entries": page_obj,
        "income_headers": headers,
        "income_actions": action_buttons,
        "primary_key": "id",
        "accounts": accounts,
        "categories": [],  # سيتم إضافتها لاحقاً
        "date_from": date_from,  # للعرض في الفورم
        "date_to": date_to,  # للعرض في الفورم
        "page_title": "الإيرادات",
        "page_subtitle": f"من {date_from} إلى {date_to}",
        "page_icon": "fas fa-cash-register",
        "header_buttons": [
            {
                "onclick": "openQuickIncomeModal()",
                "icon": "fa-plus",
                "text": "إضافة إيراد",
                "class": "btn-success",
            }
        ],
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "الإدارة المالية", "url": "#", "icon": "fas fa-money-bill-wave"},
            {"title": "الإيرادات", "active": True},
        ],
    }

    return render(request, "financial/income/income_list.html", context)


@login_required
def income_detail(request, pk):
    """
    ❌ تم إلغاء هذه الصفحة - الموديل Income غير موجود
    النظام الجديد يستخدم JournalEntry للقيود المحاسبية
    """
    messages.info(request, "هذه الميزة تحت التطوير. يرجى استخدام صفحة القيود المحاسبية.")
    return redirect("financial:income_list")


@login_required
def income_create(request):
    """إنشاء إيراد جديد - يدعم AJAX"""
    
    if request.method != 'POST':
        return redirect('financial:income_list')
    
    try:
        # التحقق من البيانات
        is_valid, errors, cleaned_data = validate_transaction_data(
            request.POST, 
            transaction_type='income'
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
            return redirect('financial:income_list')
        
        # إنشاء القيد المحاسبي
        journal_entry = create_journal_entry_for_income(cleaned_data, request.user)
        
        success_msg = _('تم إنشاء الإيراد بنجاح')
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': success_msg,
                'redirect_url': reverse('financial:income_list')
            })
        
        messages.success(request, success_msg)
        return redirect('financial:income_list')
        
    except Exception as e:
        error_msg = _('حدث خطأ أثناء إنشاء الإيراد: {}').format(str(e))
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'message': error_msg
            })
        messages.error(request, error_msg)
        return redirect('financial:income_list')


@login_required
def income_edit(request, pk):
    """تعديل إيراد"""
    journal_entry = get_object_or_404(JournalEntry, pk=pk)
    
    # التحقق من أن القيد غير مرحل
    if journal_entry.status == 'posted':
        messages.error(request, "لا يمكن تعديل قيد مرحل. يجب إلغاء الترحيل أولاً.")
        return redirect("financial:income_list")
    
    if request.method == "POST":
        try:
            # التحقق من البيانات
            is_valid, errors, cleaned_data = validate_transaction_data(
                request.POST, 
                transaction_type='income'
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
                return redirect("financial:income_list")
            
            # تحديث القيد المحاسبي
            journal_entry.date = cleaned_data['date']
            journal_entry.description = cleaned_data['description']
            journal_entry.notes = cleaned_data.get('notes', '')
            
            # حذف البنود القديمة
            journal_entry.lines.all().delete()
            
            # إنشاء البنود الجديدة
            income_account = get_object_or_404(ChartOfAccounts, id=cleaned_data['account_id'])
            receipt_account = get_object_or_404(ChartOfAccounts, id=cleaned_data['payment_account_id'])
            
            # استخدام AccountingGateway pattern لإعادة إنشاء البنود
            from governance.services import JournalEntryLineData
            
            lines = [
                JournalEntryLineData(
                    account_code=receipt_account.code,
                    debit=cleaned_data['amount'],
                    credit=Decimal('0'),
                    description=cleaned_data['description']
                ),
                JournalEntryLineData(
                    account_code=income_account.code,
                    debit=Decimal('0'),
                    credit=cleaned_data['amount'],
                    description=cleaned_data['description']
                )
            ]
            
            # إعادة إنشاء البنود
            for line_data in lines:
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=ChartOfAccounts.objects.get(code=line_data.account_code),
                    debit=line_data.debit,
                    credit=line_data.credit,
                    description=line_data.description
                )
            
            journal_entry.save()
            
            success_msg = _('تم تحديث الإيراد بنجاح')
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': success_msg,
                    'redirect_url': reverse('financial:income_list')
                })
            
            messages.success(request, success_msg)
            return redirect('financial:income_list')
            
        except Exception as e:
            error_msg = _('حدث خطأ أثناء تحديث الإيراد: {}').format(str(e))
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': error_msg
                })
            messages.error(request, error_msg)
            return redirect('financial:income_list')
    
    # GET request - عرض نموذج التعديل
    # استخراج البيانات من القيد
    income_lines = journal_entry.lines.filter(
        account__account_type__category="revenue", 
        credit__gt=0
    )
    receipt_lines = journal_entry.lines.filter(
        account__account_type__category__in=["asset", "liability"], 
        debit__gt=0
    )
    
    income_account = income_lines.first().account if income_lines.exists() else None
    receipt_account = receipt_lines.first().account if receipt_lines.exists() else None
    income_amount = income_lines.first().credit if income_lines.exists() else 0
    
    accounts = AccountHelperService.get_all_active_accounts()
    
    context = {
        "journal_entry": journal_entry,
        "income_account": income_account,
        "receipt_account": receipt_account,
        "income_amount": income_amount,
        "accounts": accounts,
    }
    
    # للطلبات AJAX، إرجاع المودال الموحد
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request, "financial/components/quick_income_modal.html", context)
    
    # للطلبات العادية، إرجاع صفحة كاملة
    context.update({
        "page_title": f"تعديل إيراد - {journal_entry.number}",
        "page_subtitle": "تعديل بيانات الإيراد",
        "page_icon": "fas fa-edit",
    })
    return render(request, "financial/income/income_edit.html", context)
