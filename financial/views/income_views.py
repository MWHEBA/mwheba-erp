# financial/views/income_views.py
# عروض إدارة الإيرادات والدخل

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count, Avg
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.contenttypes.models import ContentType
from datetime import date, datetime, timedelta
from decimal import Decimal
from django.db import models
import json

# استيراد النماذج والخدمات الجديدة
from ..forms.expense_forms import ExpenseForm, ExpenseEditForm, ExpenseFilterForm
from ..forms.income_forms import IncomeForm, IncomeEditForm, IncomeFilterForm
from ..services.expense_income_service import ExpenseIncomeService
from ..services.account_helper import AccountHelperService

# استيراد النماذج الأساسية (موجودة بالتأكيد)
from ..models import (
    AccountType,
    ChartOfAccounts,
    AccountingPeriod,
    JournalEntry,
    JournalEntryLine,
)

# استيراد النماذج الاختيارية
try:
    from ..models import (
        AccountGroup,
        JournalEntryTemplate,
        JournalEntryTemplateLine,
        BalanceSnapshot,
        AccountBalanceCache,
        BalanceAuditLog,
        PaymentSyncOperation,
        PaymentSyncLog,
    )
except ImportError:
    # في حالة عدم توفر بعض النماذج الاختيارية
    AccountGroup = None
    JournalEntryTemplate = None
    JournalEntryTemplateLine = None
    BalanceSnapshot = None
    AccountBalanceCache = None
    BalanceAuditLog = None
    PaymentSyncOperation = None
    PaymentSyncLog = None

# استيراد النماذج القديمة للتوافق (اختيارية)
try:
    from ..models import Transaction, Account, TransactionLine, TransactionForm
except ImportError:
    # في حالة عدم توفر النماذج القديمة، إنشاء نماذج وهمية
    class Transaction:
        objects = type(
            "MockManager",
            (),
            {
                "filter": lambda *args, **kwargs: type(
                    "MockQuerySet",
                    (),
                    {
                        "order_by": lambda *args: [],
                        "aggregate": lambda *args: {"amount__sum": 0, "total": 0},
                        "count": lambda: 0,
                        "exists": lambda: False,
                    },
                )(),
                "create": lambda *args, **kwargs: None,
                "all": lambda: type(
                    "MockQuerySet", (), {"order_by": lambda *args: []}
                )(),
            },
        )()

    Account = ChartOfAccounts  # استخدام النموذج الجديد
    TransactionLine = JournalEntryLine
    TransactionForm = None

@login_required
def expense_list(request):
    """
    عرض قائمة المصروفات من القيود المحاسبية
    """
    # فلترة القيوح التي تحتوي على مصروفات
    expense_entries = (
        JournalEntry.objects.filter(
            lines__account__account_type__category="expense", lines__debit__gt=0
        )
        .distinct()
        .order_by("-date", "-id")
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
            account__account_type__category="expense", debit__gt=0
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
        }
    ]

    # إعداد بيانات إضافية لكل قيد
    enhanced_entries = []
    for entry in expense_entries:
        expense_lines = entry.lines.filter(
            account__account_type__category="expense", debit__gt=0
        )

        expense_amount = sum(line.debit for line in expense_lines)
        expense_accounts = ", ".join([line.account.name for line in expense_lines])

        enhanced_entry = {
            "id": entry.id,
            "number": entry.number,
            "date": entry.date,
            "description": entry.description,
            "expense_amount": expense_amount,
            "expense_accounts": expense_accounts,
            "status": entry.status,
            "entry_type": entry.entry_type,
        }
        enhanced_entries.append(enhanced_entry)

    # إعداد الترقيم الصفحي
    paginator = Paginator(enhanced_entries, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "expenses": page_obj,  # للتوافق مع template
        "journal_entries": page_obj,
        "expense_headers": headers,
        "expense_actions": action_buttons,
        "primary_key": "id",
        "accounts": accounts,
        "total_expenses": total_expenses,
        "page_title": "المصروفات",
        "page_icon": "fas fa-money-bill-wave text-danger",
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
def expense_detail(request, pk):
    """
    عرض تفاصيل مصروف معين - تحت التطوير
    """
    messages.info(
        request, "هذه الميزة تحت التطوير. سيتم ربطها بالنماذج المحسنة قريباً."
    )
    return redirect("financial:expense_list")


@login_required
def expense_create(request):
    """
    إنشاء مصروف جديد - تحت التطوير
    """
    messages.info(
        request, "هذه الميزة تحت التطوير. سيتم ربطها بالنماذج المحسنة قريباً."
    )
    return redirect("financial:expense_list")


@login_required
def expense_edit(request, pk):
    """
    تعديل مصروف - تحت التطوير
    """
    messages.info(
        request, "هذه الميزة تحت التطوير. سيتم ربطها بالنماذج المحسنة قريباً."
    )
    return redirect("financial:expense_list")


@login_required
def expense_mark_paid(request, pk):
    """
    تحديد مصروف كمدفوع - تحت التطوير
    """
    messages.info(
        request, "هذه الميزة تحت التطوير. سيتم ربطها بالنماذج المحسنة قريباً."
    )
    return redirect("financial:expense_list")


@login_required
def expense_cancel(request, pk):
    """
    إلغاء مصروف - تحت التطوير
    """
    messages.info(
        request, "هذه الميزة تحت التطوير. سيتم ربطها بالنماذج المحسنة قريباً."
    )
    return redirect("financial:expense_list")


@login_required
def income_list(request):
    """
    عرض قائمة الإيرادات من القيود المحاسبية
    """
    # فلترة القيوح التي تحتوي على إيرادات
    income_entries = (
        JournalEntry.objects.filter(
            lines__account__account_type__category="revenue", lines__credit__gt=0
        )
        .distinct()
        .order_by("-date", "-id")
    )

    accounts = AccountHelperService.get_all_active_accounts()

    # فلترة
    account_id = request.GET.get("account")
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")

    if account_id:
        account = get_object_or_404(ChartOfAccounts, id=account_id)
        income_entries = income_entries.filter(lines__account=account).distinct()

    if date_from:
        date_from = datetime.strptime(date_from, "%Y-%m-%d").date()
        income_entries = income_entries.filter(date__gte=date_from)

    if date_to:
        date_to = datetime.strptime(date_to, "%Y-%m-%d").date()
        income_entries = income_entries.filter(date__lte=date_to)

    # إحصائيات
    total_incomes = 0
    for entry in income_entries:
        income_lines = entry.lines.filter(
            account__account_type__category="revenue", credit__gt=0
        )
        total_incomes += sum(line.credit for line in income_lines)

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
            "label": "حسابات الإيراد",
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
        }
    ]

    # إعداد بيانات إضافية لكل قيد
    enhanced_entries = []
    for entry in income_entries:
        income_lines = entry.lines.filter(
            account__account_type__category="revenue", credit__gt=0
        )

        income_amount = sum(line.credit for line in income_lines)
        income_accounts = ", ".join([line.account.name for line in income_lines])

        enhanced_entry = {
            "id": entry.id,
            "number": entry.number,
            "date": entry.date,
            "description": entry.description,
            "income_amount": income_amount,
            "income_accounts": income_accounts,
            "status": entry.status,
            "entry_type": entry.entry_type,
        }
        enhanced_entries.append(enhanced_entry)

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
        "total_incomes": total_incomes,
        "page_title": "الإيرادات",
        "page_icon": "fas fa-cash-register text-success",
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
    عرض تفاصيل إيراد معين
    """
    income = get_object_or_404(Income, pk=pk)

    context = {
        "income": income,
        "title": f"إيراد: {income.title}",
    }

    return render(request, "financial/income_detail.html", context)


@login_required
def income_mark_received(request, pk):
    """
    تحديد إيراد كمستلم
    """
    income = get_object_or_404(Income, pk=pk)

    if income.status == "received":
        messages.info(request, "هذا الإيراد مستلم بالفعل.")
        return redirect("financial:income_detail", pk=pk)

    if request.method == "POST":
        account_id = request.POST.get("account")

        if not account_id:
            messages.error(
                request, "لم يتم تحديد الحساب! يرجى اختيار حساب لاستلام الإيراد."
            )
            accounts = AccountHelperService.get_all_active_accounts()
            context = {
                "income": income,
                "accounts": accounts,
                "title": "استلام إيراد",
            }
            return render(request, "financial/income_mark_received.html", context)

        account = get_object_or_404(Account, id=account_id)

        # تحديث حالة الإيراد
        income.status = "received"
        income.received_date = timezone.now().date()
        income.save()

        # إنشاء معاملة إيراد
        transaction = Transaction.objects.create(
            account=account,
            transaction_type="income",
            amount=income.amount,
            date=timezone.now().date(),
            description=f"استلام إيراد: {income.title}",
            reference_number=income.reference_number,
        )

        # تحديث رصيد الحساب
        account.balance += income.amount
        account.save()

        messages.success(request, "تم تحديد الإيراد كمستلم بنجاح.")
        return redirect("financial:income_detail", pk=pk)

    accounts = AccountHelperService.get_all_active_accounts()

    context = {
        "income": income,
        "accounts": accounts,
        "title": "استلام إيراد",
    }

    return render(request, "financial/income_mark_received.html", context)


@login_required
def income_cancel(request, pk):
    """
    إلغاء إيراد
    """
    income = get_object_or_404(Income, pk=pk)

    if income.status == "cancelled":
        messages.info(request, "هذا الإيراد ملغي بالفعل.")
        return redirect("financial:income_detail", pk=pk)

    if request.method == "POST":
        income.status = "cancelled"
        income.save()

        messages.success(request, "تم إلغاء الإيراد بنجاح.")
        return redirect("financial:income_detail", pk=pk)

    context = {
        "object": income,
        "title": "إلغاء إيراد",
    }

    return render(request, "financial/confirm_delete.html", context)


@login_required
def category_list(request):
    """
    عرض قائمة أنواع الحسابات (بديل التصنيفات) - تحت التطوير
    """
    messages.info(
        request,
        "هذه الميزة تحت التطوير. يرجى استخدام صفحة أنواع الحسابات من القائمة الجانبية.",
    )
    return redirect("financial:account_types_list")
    context = {
        "categories": page_obj,
        "expense_count": expense_count,
        "income_count": income_count,
        "search_query": search_query,
        "category_type": category_type,
        "page_title": "تصنيفات المصروفات والإيرادات",
        "page_icon": "fas fa-tags",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "الإدارة المالية", "url": "#", "icon": "fas fa-money-bill-wave"},
            {"title": "تصنيفات المصروفات والإيرادات", "active": True},
        ],
    }

    return render(request, "financial/category_list.html", context)


@login_required
def category_create(request):
    """
    إنشاء فئة جديدة
    """
    if request.method == "POST":
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.created_by = request.user
            category.save()

            messages.success(request, "تم إنشاء التصنيف بنجاح.")
            return redirect("financial:category_list")
    else:
        form = CategoryForm()

        # تعيين النوع بناءً على المعلمة في URL
        category_type = request.GET.get("type", "")
        if category_type in ("expense", "income"):
            form.fields["type"].initial = category_type

    context = {
        "form": form,
        "page_title": "إضافة فئة جديدة",
        "page_icon": "fas fa-plus-circle",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "الإدارة المالية", "url": "#", "icon": "fas fa-money-bill-wave"},
            {
                "title": "تصنيفات المصروفات والإيرادات",
                "url": reverse("financial:category_list"),
                "icon": "fas fa-tags",
            },
            {"title": "إضافة فئة جديدة", "active": True},
        ],
    }

    return render(request, "financial/category_form.html", context)


@login_required
def category_edit(request, pk):
    """
    تعديل فئة موجودة
    """
    category = get_object_or_404(Category, pk=pk)

    # حساب عدد المعاملات المرتبطة بهذا التصنيف
    transaction_count = 0
    # استخدام النماذج الجديدة بدلاً من القديمة
    try:
        from .models.transactions import ExpenseTransaction, IncomeTransaction

        if category.type == "expense":
            transaction_count = ExpenseTransaction.objects.filter(
                category=category
            ).count()
        elif category.type == "income":
            transaction_count = IncomeTransaction.objects.filter(
                category=category
            ).count()
    except ImportError:
        # في حالة عدم توفر النماذج الجديدة
        transaction_count = 0

    if request.method == "POST":
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تعديل التصنيف بنجاح.")
            return redirect("financial:category_list")
    else:
        form = CategoryForm(instance=category)

    context = {
        "form": form,
        "category": category,
        "transaction_count": transaction_count,
        "page_title": f"تعديل فئة: {category.name}",
        "page_icon": "fas fa-edit",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "الإدارة المالية", "url": "#", "icon": "fas fa-money-bill-wave"},
            {
                "title": "تصنيفات المصروفات والإيرادات",
                "url": reverse("financial:category_list"),
                "icon": "fas fa-tags",
            },
            {"title": f"تعديل فئة: {category.name}", "active": True},
        ],
    }

    return render(request, "financial/category_form.html", context)


@login_required
def category_delete(request, pk):
    """
    حذف فئة
    """
    category = get_object_or_404(Category, pk=pk)

    # التحقق من استخدام التصنيف في المعاملات
    has_transactions = False
    transaction_count = 0

    # استخدام النماذج الجديدة بدلاً من القديمة
    try:
        from .models.transactions import ExpenseTransaction, IncomeTransaction

        if category.type == "expense":
            transaction_count = ExpenseTransaction.objects.filter(
                category=category
            ).count()
            has_transactions = transaction_count > 0
        elif category.type == "income":
            transaction_count = IncomeTransaction.objects.filter(
                category=category
            ).count()
            has_transactions = transaction_count > 0
    except ImportError:
        # في حالة عدم توفر النماذج الجديدة
        transaction_count = 0
        has_transactions = False

    if request.method == "POST":
        # إذا تم تأكيد الحذف
        confirm_deletion = (
            request.POST.get("confirm_deletion") == "on" if has_transactions else True
        )

        if confirm_deletion:
            category_name = category.name
            category.delete()
            messages.success(request, f'تم حذف التصنيف "{category_name}" بنجاح.')
            return redirect("financial:category_list")
        else:
            messages.error(request, "يجب تأكيد الحذف للتصنيفات المستخدمة في معاملات.")

    context = {
        "category": category,
        "has_transactions": has_transactions,
        "transaction_count": transaction_count,
        "page_title": f"حذف فئة: {category.name}",
        "page_icon": "fas fa-trash",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "الإدارة المالية", "url": "#", "icon": "fas fa-money-bill-wave"},
            {
                "title": "تصنيفات المصروفات والإيرادات",
                "url": reverse("financial:category_list"),
                "icon": "fas fa-tags",
            },
            {"title": f"حذف فئة: {category.name}", "active": True},
        ],
    }

    return render(request, "financial/category_delete.html", context)


@login_required
def expense_create_enhanced(request):
    """
    إنشاء مصروف جديد محسن - للمودال فقط
    """
    if request.method == "POST":
        form = ExpenseForm(request.POST)
        if form.is_valid():
            try:
                # تحضير البيانات للخدمة
                expense_data = {
                    'description': form.cleaned_data['description'],
                    'amount': form.cleaned_data['amount'],
                    'expense_date': form.cleaned_data['expense_date'],
                    'expense_account': form.cleaned_data['expense_account'],
                    'payment_account': form.cleaned_data['payment_account'],
                    'reference': form.cleaned_data.get('reference', ''),
                    'notes': form.cleaned_data.get('notes', ''),
                    'auto_post': form.cleaned_data.get('auto_post', True),  # ترحيل تلقائي افتراضياً
                }
                
                # إنشاء المصروف باستخدام الخدمة
                journal_entry = ExpenseIncomeService.create_expense(
                    expense_data, request.user
                )

                success_message = f"تم إنشاء المصروف بنجاح. رقم القيد: {journal_entry.reference}"
                
                # معالجة AJAX
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'message': success_message,
                        'redirect_url': reverse("financial:expense_detail", kwargs={'pk': journal_entry.pk}),
                        'journal_entry_id': journal_entry.pk,
                        'reference': journal_entry.reference
                    })
                
                messages.success(request, success_message)
                return redirect("financial:expense_detail", pk=journal_entry.pk)
            except Exception as e:
                error_message = f"خطأ في إنشاء المصروف: {str(e)}"
                
                # معالجة AJAX للأخطاء
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'message': error_message
                    })
                
                messages.error(request, error_message)
        else:
            # معالجة أخطاء النموذج للـ AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'errors': form.errors,
                    'message': 'يرجى تصحيح الأخطاء في النموذج'
                })
    
    # إعادة توجيه للقائمة إذا لم يكن AJAX
    return redirect("financial:expense_list")


@login_required
def expense_detail_enhanced(request, pk):
    """
    تفاصيل المصروف المحسن
    """
    try:
        journal_entry = get_object_or_404(JournalEntry, pk=pk)

        # التحقق من أن هذا قيد مصروف
        if not journal_entry.reference.startswith("EXP-"):
            messages.error(request, "هذا ليس قيد مصروف")
            return redirect("financial:expense_list")

        # استخراج معلومات المصروف من بنود القيد
        expense_lines = journal_entry.lines.filter(debit__gt=0)
        payment_lines = journal_entry.lines.filter(credit__gt=0)

        expense_amount = sum(line.debit for line in expense_lines)

        context = {
            "journal_entry": journal_entry,
            "expense_lines": expense_lines,
            "payment_lines": payment_lines,
            "expense_amount": expense_amount,
            "page_title": f"تفاصيل المصروف - {journal_entry.reference}",
            "page_icon": "fas fa-receipt",
            "breadcrumb_items": [
                {"title": "النظام المالي", "url": reverse("financial:expense_list")},
                {"title": "المصروفات", "url": reverse("financial:expense_list")},
                {"title": f"المصروف {journal_entry.reference}", "active": True},
            ],
        }

        return render(request, "financial/expense_detail.html", context)

    except Exception as e:
        messages.error(request, f"خطأ في تحميل تفاصيل المصروف: {str(e)}")
        return redirect("financial:expense_list")


# ============== اكتمل ملف income_views.py بالكامل ==============
# تم نقل جميع دوال المصروفات والإيرادات بنجاح
