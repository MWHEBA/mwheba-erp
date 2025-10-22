# financial/views/transaction_views.py
# عروض القيود المحاسبية والمعاملات المالية

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

# ============== القيود المحاسبية المتقدمة ==============

@login_required
def journal_entries_list(request):
    """عرض قائمة القيود اليومية مع إمكانية الفلترة"""
    if JournalEntry is None:
        journal_entries = []
        paginator = None
        page_obj = None
        filter_form = None
    else:
        # جلب جميع القيود مرتبة من الأحدث
        journal_entries_list = JournalEntry.objects.all().order_by("-date", "-id")

        # معلمات الفلترة
        status = request.GET.get("status", "")
        search = request.GET.get("search", "")
        date_from = request.GET.get("date_from", "")
        date_to = request.GET.get("date_to", "")

        # تطبيق الفلاتر
        if status:
            journal_entries_list = journal_entries_list.filter(status=status)

        if search:
            journal_entries_list = journal_entries_list.filter(
                Q(reference__icontains=search) | Q(description__icontains=search)
            )

        if date_from:
            journal_entries_list = journal_entries_list.filter(date__gte=date_from)

        if date_to:
            journal_entries_list = journal_entries_list.filter(date__lte=date_to)

        # إعداد نموذج الفلترة
        filter_form = {
            "status": status,
            "search": search,
            "date_from": date_from,
            "date_to": date_to,
        }

        # حساب الإحصائيات المتقدمة
        from django.db.models import Sum, Count
        
        # إحصائيات عامة
        total_transactions = journal_entries_list.count()
        
        # حساب إجمالي المدين والدائن
        if JournalEntryLine:
            stats = JournalEntryLine.objects.filter(
                journal_entry__in=journal_entries_list
            ).aggregate(
                total_debit=Sum('debit'),
                total_credit=Sum('credit')
            )
            total_debit = stats['total_debit'] or 0
            total_credit = stats['total_credit'] or 0
        else:
            total_debit = 0
            total_credit = 0

        # الترقيم الصفحي مع تحميل الخطوط
        paginator = Paginator(journal_entries_list, 25)  # 25 قيد في الصفحة
        page_number = request.GET.get("page")
        page_obj = paginator.get_page(page_number)
        
        # تحميل القيود مع خطوطها والحسابات
        journal_entries_raw = page_obj.object_list.prefetch_related(
            'lines__account'
        ).select_related('created_by')
        
        # تحضير البيانات للجدول مع المعلومات الإضافية
        journal_entries = []
        for entry in journal_entries_raw:
            # حساب المبلغ الأساسي ونوع القيد من خطوط القيد
            amount = 0
            entry_type = "غير محدد"
            
            # الحصول على خطوط القيد
            lines = []
            if hasattr(entry, 'lines'):
                lines = list(entry.lines.all())
            elif hasattr(entry, 'journalentryline_set'):
                lines = list(entry.journalentryline_set.all())
            
            if lines:
                first_line = lines[0]
                amount = first_line.debit if first_line.debit > 0 else first_line.credit
                
                # تحديد نوع القيد بناءً على تحليل الخطوط
                if len(lines) == 2:
                    line1, line2 = lines[0], lines[1]
                    
                    # تحليل ذكي لنوع القيد بناءً على أسماء الحسابات الفعلية
                    account_names = [line1.account.name, line2.account.name]
                    
                    # التحقق من وجود حسابات نقدية (صندوق)
                    cash_accounts = ['الصندوق', 'صندوق', 'نقدية', 'كاش']
                    has_cash = any(cash_word in acc_name for acc_name in account_names for cash_word in cash_accounts)
                    
                    # التحقق من وجود حسابات بنكية
                    bank_accounts = ['بنك', 'البنك', 'مصرف']
                    has_bank = any(bank_word in acc_name for acc_name in account_names for bank_word in bank_accounts)
                    
                    # التحقق من وجود حسابات عملاء/موردين
                    customer_accounts = ['العملاء', 'عميل', 'مدينون']
                    supplier_accounts = ['الموردون', 'مورد', 'دائنون']
                    has_customer = any(cust_word in acc_name for acc_name in account_names for cust_word in customer_accounts)
                    has_supplier = any(supp_word in acc_name for acc_name in account_names for supp_word in supplier_accounts)
                    
                    # التحقق من حسابات الإيرادات والمصروفات والمخزون
                    revenue_accounts = ['إيرادات', 'مبيعات', 'دخل']
                    expense_accounts = ['مصروفات', 'مصاريف', 'تكلفة', 'مخزون']
                    has_revenue = any(rev_word in acc_name for acc_name in account_names for rev_word in revenue_accounts)
                    has_expense = any(exp_word in acc_name for acc_name in account_names for exp_word in expense_accounts)
                    
                    # تحديد نوع القيد بناءً على المنطق المحاسبي
                    if has_cash and (line1.debit > 0 and 'الصندوق' in line1.account.name) or (line2.debit > 0 and 'الصندوق' in line2.account.name):
                        entry_type = "إيراد نقدي"
                    elif has_cash and (line1.credit > 0 and 'الصندوق' in line1.account.name) or (line2.credit > 0 and 'الصندوق' in line2.account.name):
                        entry_type = "مصروف نقدي"
                    elif has_bank and (line1.debit > 0 and 'بنك' in line1.account.name) or (line2.debit > 0 and 'بنك' in line2.account.name):
                        entry_type = "إيراد بنكي"
                    elif has_bank and (line1.credit > 0 and 'بنك' in line1.account.name) or (line2.credit > 0 and 'بنك' in line2.account.name):
                        entry_type = "مصروف بنكي"
                    # فواتير المبيعات: العملاء (مدين) + إيرادات (دائن)
                    elif has_customer and has_revenue:
                        entry_type = "فاتورة مبيعات"
                    # فواتير المشتريات: مصروفات/مخزون (مدين) + موردون (دائن)
                    elif has_supplier and has_expense:
                        entry_type = "فاتورة مشتريات"
                    # فواتير المشتريات البديلة: موردون (دائن) + أي حساب آخر (مدين)
                    elif has_supplier and not (has_cash or has_bank or has_customer):
                        entry_type = "فاتورة مشتريات"
                    # فواتير المبيعات البديلة: عملاء (مدين) + أي حساب آخر (دائن)
                    elif has_customer and not (has_cash or has_bank or has_supplier):
                        entry_type = "فاتورة مبيعات"
                    elif has_customer and (has_cash or has_bank):
                        entry_type = "تحصيل من عميل"
                    elif has_supplier and (has_cash or has_bank):
                        entry_type = "دفع لمورد"
                    else:
                        entry_type = "تحويل"
                elif len(lines) > 2:
                    entry_type = "قيد مركب"
                else:
                    entry_type = "تحويل"
            else:
                # استخدام النوع الأصلي من النموذج كـ fallback
                if hasattr(entry, 'get_entry_type_display'):
                    entry_type = entry.get_entry_type_display()
                elif hasattr(entry, 'entry_type'):
                    entry_type = entry.entry_type
            
            # إنشاء كائن محسن للعرض مع الاحتفاظ بالكائن الأصلي
            class EnhancedEntry:
                def __init__(self, original_entry, enhanced_data):
                    # نسخ البيانات المحسنة
                    for key, value in enhanced_data.items():
                        setattr(self, key, value)
                    # الاحتفاظ بالكائن الأصلي للوصول للعلاقات
                    self._original = original_entry
                    
                @property
                def journalentryline_set(self):
                    return self._original.journalentryline_set if hasattr(self._original, 'journalentryline_set') else None
                
                # إضافة get_attr للتوافق مع data_table
                def get_attr(self, key):
                    if hasattr(self, key):
                        return getattr(self, key)
                    return None
            
            enhanced_data = {
                'id': entry.id,
                'reference': entry.reference or entry.number or str(entry.id),
                'date': entry.date,
                'entry_type': entry_type,  # النوع المحسوب بناءً على التحليل
                'original_entry_type': entry.get_entry_type_display() if hasattr(entry, 'get_entry_type_display') else entry_type,  # النوع الأصلي من النموذج
                'description': entry.description or "بدون وصف",
                'amount': amount,
                'status': entry.status or 'posted',
                'created_by': entry.created_by.get_full_name() if hasattr(entry, 'created_by') and entry.created_by else "غير محدد",
            }
            
            enhanced_entry = EnhancedEntry(entry, enhanced_data)
            journal_entries.append(enhanced_entry)

    # قائمة حالات القيود
    status_choices = [
        ("", "الكل"),
        ("draft", "مسودة"),
        ("posted", "مرحل"),
        ("cancelled", "ملغى"),
    ]

    # إعداد headers للجدول الموحد
    headers = [
        {"key": "reference", "label": "رقم القيد", "sortable": True, "width": "120px"},
        {"key": "date", "label": "التاريخ", "sortable": True, "format": "date", "width": "120px"},
        {"key": "entry_type", "label": "النوع", "sortable": False, "width": "130px"},
        {"key": "description", "label": "الوصف", "sortable": False},
        {"key": "amount", "label": "المبلغ", "sortable": True, "format": "currency", "width": "120px"},
        {"key": "status", "label": "الحالة", "sortable": True, "format": "status", "width": "100px"},
        {"key": "created_by", "label": "المستخدم", "sortable": True, "width": "120px"},
    ]

    # إعداد action buttons - تم إزالة الإجراءات
    action_buttons = []

    context = {
        "journal_entries": journal_entries,
        "headers": headers,
        "action_buttons": action_buttons,
        "primary_key": "id",
        "page_obj": page_obj,
        "paginator": paginator,
        "filter_form": filter_form or {},
        "status_choices": status_choices,
        # إحصائيات متقدمة
        "total_transactions": total_transactions if 'total_transactions' in locals() else 0,
        "total_debit": total_debit if 'total_debit' in locals() else 0,
        "total_credit": total_credit if 'total_credit' in locals() else 0,
        "page_title": "القيود اليومية",
        "page_icon": "fas fa-book",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "الإدارة المالية",
                "url": "#",
                "icon": "fas fa-money-bill-wave",
            },
            {"title": "القيود المحاسبية", "active": True},
        ],
    }
    return render(request, "financial/transactions/journal_entries_list.html", context)


@login_required
def journal_entries_create(request):
    """إنشاء قيد جديد"""

    # تحميل الحسابات من النظام الجديد
    accounts = []
    if ChartOfAccounts:
        accounts = ChartOfAccounts.objects.filter(
            is_active=True, is_leaf=True  # الحسابات الفرعية فقط
        ).order_by("code")

    # تحميل الفترات المحاسبية
    accounting_periods = []
    if AccountingPeriod:
        accounting_periods = AccountingPeriod.objects.filter(status="open").order_by(
            "-start_date"
        )

    context = {
        "accounts": accounts,
        "accounting_periods": accounting_periods,
        "page_title": "إنشاء قيد جديد",
        "page_icon": "fas fa-plus-square",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "القيود المحاسبية",
                "url": reverse("financial:journal_entries_list"),
                "icon": "fas fa-book",
            },
            {"title": "إنشاء قيد جديد", "active": True},
        ],
    }
    return render(request, "financial/transactions/journal_entries_form.html", context)


@login_required
def journal_entries_detail(request, pk):
    """عرض تفاصيل قيد"""
    if JournalEntry is None:
        messages.error(request, "نموذج القيود غير متاح.")
        return redirect("financial:journal_entries_list")

    journal_entry = get_object_or_404(JournalEntry, pk=pk)

    # حساب الإجماليات
    total_debits = sum(line.debit or 0 for line in journal_entry.lines.all())
    total_credits = sum(line.credit or 0 for line in journal_entry.lines.all())
    difference = abs(total_debits - total_credits)

    # استخراج معلومات المصدر باستخدام العلاقات العكسية (أسرع وأبسط!)
    source_invoice = None
    source_party = None  # العميل أو المورد
    invoice_type = None  # نوع الفاتورة
    source_payment = None  # الدفعة المرتبطة
    source_payment_url = None  # رابط الدفعة

    # أولاً: البحث في الدفعات باستخدام العلاقات العكسية (أسرع!)
    try:
        from purchase.models import PurchasePayment
        from django.urls import reverse

        # البحث في دفعات المشتريات - استخدام العلاقة العكسية
        purchase_payment = journal_entry.purchasepayment_set.select_related(
            "purchase", "purchase__supplier"
        ).first()
        if purchase_payment:
            source_payment = purchase_payment
            source_payment_url = reverse(
                "purchase:payment_detail", args=[purchase_payment.pk]
            )
            source_invoice = purchase_payment.purchase
            source_party = purchase_payment.purchase.supplier
            invoice_type = "purchase"
    except (ImportError, AttributeError):
        pass

    if not source_payment:
        try:
            from sale.models import SalePayment

            # البحث في دفعات المبيعات - استخدام العلاقة العكسية
            sale_payment = journal_entry.salepayment_set.select_related(
                "sale", "sale__customer"
            ).first()
            if sale_payment:
                source_payment = sale_payment
                source_payment_url = reverse(
                    "sale:payment_detail", args=[sale_payment.pk]
                )
                source_invoice = sale_payment.sale
                source_party = sale_payment.sale.customer
                invoice_type = "sale"
        except (ImportError, AttributeError):
            pass

    # ثانياً: إذا لم نجد دفعة، نبحث في الفواتير باستخدام العلاقات العكسية
    if not source_invoice:
        try:
            from purchase.models import Purchase

            # البحث في فواتير المشتريات - استخدام العلاقة العكسية
            purchase = journal_entry.purchases.select_related("supplier").first()
            if purchase:
                source_invoice = purchase
                source_party = purchase.supplier
                invoice_type = "purchase"
        except (ImportError, AttributeError):
            pass

    if not source_invoice:
        try:
            from sale.models import Sale

            # البحث في فواتير المبيعات - استخدام العلاقة العكسية
            sale = journal_entry.sales.select_related("customer").first()
            if sale:
                source_invoice = sale
                source_party = sale.customer
                invoice_type = "sale"
        except (ImportError, AttributeError):
            pass

    context = {
        "journal_entry": journal_entry,
        "total_debits": total_debits,
        "total_credits": total_credits,
        "difference": difference,
        "source_invoice": source_invoice,
        "source_party": source_party,
        "invoice_type": invoice_type,
        "source_payment": source_payment,
        "source_payment_url": source_payment_url,
        "page_title": f"قيد رقم: {journal_entry.number}",
        "page_icon": "fas fa-info-circle",
    }
    return render(request, "financial/transactions/journal_entries_detail.html", context)


@login_required
def journal_entries_edit(request, pk):
    """تعديل قيد"""
    journal_entry = get_object_or_404(JournalEntry, pk=pk)

    # تحميل الحسابات من النظام الجديد
    accounts = []
    if ChartOfAccounts:
        accounts = ChartOfAccounts.objects.filter(
            is_active=True, is_leaf=True  # الحسابات الفرعية فقط
        ).order_by("code")

    # تحميل الفترات المحاسبية
    accounting_periods = []
    if AccountingPeriod:
        accounting_periods = AccountingPeriod.objects.filter(status="open").order_by(
            "-start_date"
        )

    context = {
        "journal_entry": journal_entry,
        "accounts": accounts,
        "accounting_periods": accounting_periods,
        "page_title": f"تعديل قيد: {journal_entry.reference}",
        "page_icon": "fas fa-edit",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "القيود المحاسبية",
                "url": reverse("financial:journal_entries_list"),
                "icon": "fas fa-book",
            },
            {"title": f"تعديل قيد: {journal_entry.reference}", "active": True},
        ],
    }
    return render(request, "financial/transactions/journal_entries_form.html", context)


@login_required
def journal_entries_delete(request, pk):
    """حذف قيد"""
    journal_entry = get_object_or_404(JournalEntry, pk=pk)
    if request.method == "POST":
        journal_entry.delete()
        messages.success(request, f'تم حذف القيد "{journal_entry.reference}" بنجاح.')
        return redirect("financial:journal_entries_list")

    context = {
        "journal_entry": journal_entry,
        "page_title": f"حذف قيد: {journal_entry.reference}",
        "page_icon": "fas fa-trash",
    }
    return render(request, "financial/transactions/journal_entry_delete_confirm.html", context)


@login_required
def journal_entries_post(request, pk):
    """ترحيل قيد"""
    journal_entry = get_object_or_404(JournalEntry, pk=pk)

    if request.method == "POST":
        try:
            # استخدام الـ method المخصص للترحيل
            journal_entry.post(user=request.user)

            # إرجاع JSON response دائماً للطلبات POST
            return JsonResponse(
                {
                    "success": True,
                    "message": f'تم ترحيل القيد "{journal_entry.number or journal_entry.reference}" بنجاح.',
                }
            )

        except Exception as e:
            logger.error(f"Error in views.py: {str(e)}", exc_info=True)
            return JsonResponse({"success": False, "message": "حدث خطأ غير متوقع"})

    context = {
        "journal_entry": journal_entry,
        "page_title": f"ترحيل قيد: {journal_entry.reference}",
        "page_icon": "fas fa-check-circle",
    }
    return render(request, "financial/transactions/journal_entries_post.html", context)


@login_required
def transaction_list(request):
    """
    عرض قائمة القيود المحاسبية (المعاملات المالية) باستخدام النظام الجديد
    """
    # استخدام JournalEntry بدلاً من Transaction
    journal_entries = JournalEntry.objects.all().order_by("-date", "-id")
    accounts = AccountHelperService.get_all_active_accounts()

    # فلترة
    account_id = request.GET.get("account")
    entry_type = request.GET.get("type")
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")

    if account_id:
        account = get_object_or_404(ChartOfAccounts, id=account_id)
        # البحث في بنود القيد للحساب المحدد
        journal_entries = journal_entries.filter(
            journalentryline__account=account
        ).distinct()

    if entry_type:
        # تصنيف القيود حسب النوع (دخل/مصروف) بناءً على نوع الحسابات المستخدمة
        if entry_type == "income":
            journal_entries = journal_entries.filter(
                journalentryline__account__account_type__nature="credit",
                journalentryline__credit__gt=0,
            ).distinct()
        elif entry_type == "expense":
            journal_entries = journal_entries.filter(
                journalentryline__account__account_type__nature="debit",
                journalentryline__debit__gt=0,
            ).distinct()

    if date_from:
        date_from = datetime.strptime(date_from, "%Y-%m-%d").date()
        journal_entries = journal_entries.filter(date__gte=date_from)

    if date_to:
        date_to = datetime.strptime(date_to, "%Y-%m-%d").date()
        journal_entries = journal_entries.filter(date__lte=date_to)

    # إحصائيات - حساب إجمالي المدين والدائن
    total_entries = journal_entries.count()
    total_debit = (
        JournalEntryLine.objects.filter(journal_entry__in=journal_entries).aggregate(
            Sum("debit")
        )["debit__sum"]
        or 0
    )
    total_credit = (
        JournalEntryLine.objects.filter(journal_entry__in=journal_entries).aggregate(
            Sum("credit")
        )["credit__sum"]
        or 0
    )

    # تعريف رؤوس الأعمدة للجدول الموحد
    headers = [
        {
            "key": "entry_type",
            "label": "النوع",
            "sortable": False,
            "format": "icon_text",
            "icon_callback": "get_type_class",
            "icon_class_callback": "get_type_icon",
            "width": "8%",
        },
        {
            "key": "created_at",
            "label": "التاريخ والوقت",
            "sortable": True,
            "format": "datetime_12h",
            "class": "text-center",
            "width": "12%",
        },
        {"key": "account", "label": "الحساب", "sortable": False, "width": "12%"},
        {
            "key": "description",
            "label": "الوصف",
            "sortable": False,
            "ellipsis": True,
            "width": "auto",
        },
        {
            "key": "deposit",
            "label": "الإيراد",
            "sortable": False,
            "format": "currency",
            "class": "text-center",
            "variant": "positive",
            "width": "10%",
            "decimals": 2,
        },
        {
            "key": "withdraw",
            "label": "المصروف",
            "sortable": False,
            "format": "currency",
            "class": "text-center",
            "variant": "negative",
            "width": "10%",
            "decimals": 2,
        },
        {
            "key": "balance_after",
            "label": "الرصيد بعد",
            "sortable": False,
            "format": "currency",
            "class": "text-center fw-bold",
            "variant": "neutral",
            "width": "12%",
            "decimals": 2,
        },
        {
            "key": "number",
            "label": "رقم القيد",
            "sortable": False,
            "format": "reference",
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
            "url": "financial:transaction_edit",
            "icon": "fa-edit",
            "label": "تعديل",
            "class": "action-edit",
        },
        {
            "url": "financial:transaction_delete",
            "icon": "fa-trash-alt",
            "label": "حذف",
            "class": "action-delete",
        },
    ]

    # معالجة الترتيب
    current_order_by = request.GET.get("order_by", "")
    current_order_dir = request.GET.get("order_dir", "")

    # إعداد الترقيم الصفحي
    paginator = Paginator(journal_entries, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "transactions": page_obj,  # استخدام transactions للتوافق مع template
        "journal_entries": page_obj,
        "headers": headers,
        "action_buttons": action_buttons,
        "accounts": accounts,
        "total_transactions": total_entries,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "page_title": "القيود المحاسبية",
        "page_icon": "fas fa-book",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "الإدارة المالية", "url": "#", "icon": "fas fa-money-bill-wave"},
            {"title": "القيود المحاسبية", "active": True},
        ],
        "current_order_by": current_order_by,
        "current_order_dir": current_order_dir,
    }

    return render(request, "financial/transactions/transaction_list.html", context)


@login_required
def transaction_detail(request, pk):
    """
    عرض تفاصيل قيد محاسبي معين
    """
    """
    عرض تفاصيل قيد محاسبي معين
    """
    journal_entry = get_object_or_404(JournalEntry, pk=pk)

    # إنشاء كائن وهمي للتوافق مع template
    class TransactionProxy:
        def __init__(self, journal_entry):
            self.id = journal_entry.id
            self.number = journal_entry.number
            self.date = journal_entry.date
            self.description = journal_entry.description
            self.reference_number = journal_entry.reference or journal_entry.number
            self.created_at = journal_entry.created_at
            self.created_by = journal_entry.created_by
            self.amount = self._calculate_amount(journal_entry)
            self.transaction_type = self._determine_type(journal_entry)
            self.account = self._get_main_account(journal_entry)
            self.to_account = None  # للتحويلات

        def _calculate_amount(self, entry):
            """حساب المبلغ الإجمالي للقيد"""
            total_debit = sum(line.debit for line in entry.lines.all())
            return total_debit

        def _determine_type(self, entry):
            """تحديد نوع المعاملة بناءً على الحسابات"""
            lines = entry.lines.all()
            if not lines:
                return "manual"

            # فحص أنواع الحسابات لتحديد النوع
            account_types = [
                line.account.account_type.nature
                for line in lines
                if line.account.account_type
            ]

            if "credit" in account_types and any(line.credit > 0 for line in lines):
                return "income"
            elif "debit" in account_types and any(line.debit > 0 for line in lines):
                return "expense"
            else:
                return "manual"

        def _get_main_account(self, entry):
            """الحصول على الحساب الرئيسي (أول حساب في القيد)"""
            first_line = entry.lines.first()
            return first_line.account if first_line else None

    transaction_proxy = TransactionProxy(journal_entry)

    context = {
        "transaction": transaction_proxy,  # للتوافق مع template
        "journal_entry": journal_entry,
        "journal_lines": journal_entry.lines.all(),
        "title": f"قيد محاسبي: {journal_entry.number}",
    }

    return render(request, "financial/transactions/transaction_detail.html", context)


@login_required
def transaction_create(request):
    """
    إنشاء قيد محاسبي جديد - تحت التطوير
    """
    messages.info(
        request,
        "هذه الميزة تحت التطوير. يرجى استخدام صفحة القيود المحاسبية من القائمة الجانبية.",
    )
    return redirect("financial:journal_entries_list")

    if request.method == "POST":
        form = TransactionForm(request.POST)
        if form.is_valid():
            from django.db import transaction as db_transaction

            with db_transaction.atomic():
                # إنشاء المعاملة
                trans = form.save(commit=False)
                trans.created_by = request.user
                trans.save()

                # استخراج البيانات الأخرى من النموذج
                account = form.cleaned_data["account"]
                transaction_type = form.cleaned_data["transaction_type"]
                amount = form.cleaned_data["amount"]
                description = form.cleaned_data.get("description", "")

                # حساب مقابل افتراضي حسب نوع المعاملة
                contra_account = None
                if transaction_type == "income":
                    # بحث عن حساب إيرادات افتراضي
                    contra_account = get_accounts_by_category("revenue").first()
                    if not contra_account:
                        # إنشاء حساب افتراضي في النظام القديم (مؤقت)
                        contra_account = Account.objects.create(
                            name="الإيرادات",
                            code="INC001",
                            account_type="income",
                            created_by=request.user,
                        )
                elif transaction_type == "expense":
                    # بحث عن حساب مصروفات افتراضي
                    contra_account = get_accounts_by_category("expense").first()
                    if not contra_account:
                        # إنشاء حساب افتراضي في النظام القديم (مؤقت)
                        contra_account = Account.objects.create(
                            name="المصروفات",
                            code="EXP001",
                            account_type="expense",
                            created_by=request.user,
                        )

                # التأكد من وجود حساب قبل الاستمرار
                if not account:
                    messages.error(request, "يجب تحديد الحساب الرئيسي للمعاملة")
                    return redirect("financial:transaction_create")

                # إنشاء بنود القيد المحاسبي
                if transaction_type == "income":
                    # التأكد من وجود الحسابات المطلوبة
                    if not contra_account:
                        messages.error(request, "لم يتم العثور على حساب الإيرادات")
                        return redirect("financial:transaction_create")

                    # مدين: الحساب المختار (زيادة في الأصول)
                    TransactionLine.objects.create(
                        transaction=trans,
                        account=account,
                        debit=amount,
                        credit=0,
                        description=description,
                    )
                    # دائن: حساب الإيرادات
                    TransactionLine.objects.create(
                        transaction=trans,
                        account=contra_account,
                        debit=0,
                        credit=amount,
                        description=description,
                    )

                    # تحديث رصيد الحساب
                    account.update_balance(amount, "add")

                elif transaction_type == "expense":
                    # التأكد من وجود الحسابات المطلوبة
                    if not contra_account:
                        messages.error(request, "لم يتم العثور على حساب المصروفات")
                        return redirect("financial:transaction_create")

                    # مدين: حساب المصروفات
                    TransactionLine.objects.create(
                        transaction=trans,
                        account=contra_account,
                        debit=amount,
                        credit=0,
                        description=description,
                    )
                    # دائن: الحساب المختار (نقص في الأصول)
                    TransactionLine.objects.create(
                        transaction=trans,
                        account=account,
                        debit=0,
                        credit=amount,
                        description=description,
                    )

                    # تحديث رصيد الحساب
                    account.update_balance(amount, "subtract")

                elif transaction_type == "transfer":
                    to_account = form.cleaned_data.get("to_account")
                    if to_account:
                        # مدين: حساب الوجهة (زيادة)
                        TransactionLine.objects.create(
                            transaction=trans,
                            account=to_account,
                            debit=amount,
                            credit=0,
                            description=description,
                        )
                        # دائن: حساب المصدر (نقص)
                        TransactionLine.objects.create(
                            transaction=trans,
                            account=account,
                            debit=0,
                            credit=amount,
                            description=description,
                        )

                        # تحديث رصيد الحسابين
                        account.update_balance(amount, "subtract")
                        to_account.update_balance(amount, "add")
                    else:
                        # في حالة عدم وجود حساب وجهة (يجب ألا يحدث بسبب التحقق في النموذج)
                        messages.error(request, "يجب تحديد حساب الوجهة للتحويل")
                        return redirect("financial:transaction_create")

            messages.success(request, "تم إنشاء المعاملة المالية بنجاح.")
            return redirect("financial:transaction_detail", pk=trans.pk)
    else:
        form = TransactionForm()

    context = {
        "form": form,
        "title": "إنشاء معاملة مالية",
    }
    return render(request, "financial/transactions/transaction_form.html", context)


@login_required
def transaction_edit(request, pk):
    """
    تعديل قيد محاسبي - تحت التطوير
    """
    messages.info(
        request,
        "هذه الميزة تحت التطوير. يرجى استخدام صفحة القيود المحاسبية من القائمة الجانبية.",
    )
    return redirect("financial:journal_entries_list")


@login_required
def transaction_delete(request, pk):
    """
    حذف قيد محاسبي - تحت التطوير
    """
    messages.info(
        request,
        "هذه الميزة تحت التطوير. يرجى استخدام صفحة القيود المحاسبية من القائمة الجانبية.",
    )
    return redirect("financial:journal_entries_list")

    journal_entry = get_object_or_404(JournalEntry, pk=pk)

    if request.method == "POST":
        # إلغاء تأثير المعاملة على الحساب
        if transaction.transaction_type == "income" and transaction.account:
            # التأكد من وجود الحساب قبل تعديل رصيده
            if hasattr(transaction.account, "balance"):
                transaction.account.balance -= transaction.amount
                transaction.account.save()
            else:
                messages.warning(
                    request,
                    "لم يتم العثور على الحساب المرتبط بالمعاملة أو تم حذفه مسبقاً.",
                )

        elif transaction.transaction_type == "expense" and transaction.account:
            # التأكد من وجود الحساب قبل تعديل رصيده
            if hasattr(transaction.account, "balance"):
                transaction.account.balance += transaction.amount
                transaction.account.save()
            else:
                messages.warning(
                    request,
                    "لم يتم العثور على الحساب المرتبط بالمعاملة أو تم حذفه مسبقاً.",
                )

        elif transaction.transaction_type == "transfer":
            # التحقق من وجود الحساب المصدر
            if transaction.account and hasattr(transaction.account, "balance"):
                transaction.account.balance += transaction.amount
                transaction.account.save()
            else:
                messages.warning(
                    request, "لم يتم العثور على الحساب المصدر أو تم حذفه مسبقاً."
                )

            # التحقق من وجود الحساب المستلم
            if transaction.to_account and hasattr(transaction.to_account, "balance"):
                transaction.to_account.balance -= transaction.amount
                transaction.to_account.save()
            else:
                messages.warning(
                    request, "لم يتم العثور على الحساب المستلم أو تم حذفه مسبقاً."
                )

        # حذف المعاملة بغض النظر عن حالة الحسابات
        transaction.delete()
        messages.success(request, "تم حذف المعاملة بنجاح.")
        return redirect("financial:transaction_list")

    context = {
        "object": transaction,
        "title": "حذف معاملة",
    }

    return render(request, "financial/confirm_delete.html", context)


@login_required
def journal_entry_delete(request, pk):
    """
    حذف قيد محاسبي مع التحقق من الصلاحيات
    """
    from .permissions import check_user_can_delete_entry
    from django.core.exceptions import ValidationError

    entry = get_object_or_404(JournalEntry, pk=pk)

    # التحقق من الصلاحيات
    if not check_user_can_delete_entry(request.user, entry):
        messages.error(request, "ليس لديك صلاحية حذف هذا القيد")
        return redirect("financial:journal_entries_list")

    if request.method == "POST":
        try:
            entry_number = entry.number
            entry.delete()
            messages.success(request, f"تم حذف القيد {entry_number} بنجاح")
            return redirect("financial:journal_entries_list")
        except ValidationError as e:
            messages.error(request, str(e))
            return redirect("financial:journal_entries_detail", pk=pk)
        except Exception as e:
            messages.error(request, f"خطأ في الحذف: {str(e)}")
            return redirect("financial:journal_entries_detail", pk=pk)

    context = {
        "entry": entry,
        "can_delete": entry.can_be_deleted(),
    }
    return render(request, "financial/journal_entry_delete_confirm.html", context)


# ============== اكتمل ملف transaction_views.py بالكامل ==============
# تم نقل جميع دوال القيود المحاسبية والمعاملات بنجاح
