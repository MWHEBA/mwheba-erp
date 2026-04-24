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

def _get_user_display_name(user):
    """الحصول على اسم المستخدم للعرض"""
    if not user:
        return "غير محدد"
    
    # محاولة الحصول على الاسم الكامل
    full_name = user.get_full_name() if hasattr(user, 'get_full_name') else None
    if full_name and full_name.strip():
        return full_name.strip()
    
    # إذا لم يكن هناك اسم كامل، استخدم اسم المستخدم
    if hasattr(user, 'username') and user.username:
        return user.username
    
    # إذا لم يكن هناك اسم مستخدم، استخدم البريد الإلكتروني
    if hasattr(user, 'email') and user.email:
        return user.email
    
    return "مستخدم غير معروف"


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
        journal_entries_list = JournalEntry.objects.select_related('financial_category').all().order_by("-date", "-id")

        # معلمات الفلترة
        status = request.GET.get("status", "")
        search = request.GET.get("search", "")
        date_from = request.GET.get("date_from", "")
        date_to = request.GET.get("date_to", "")
        category_filter = request.GET.get("category", "")

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

        if category_filter:
            journal_entries_list = journal_entries_list.filter(financial_category_id=category_filter)

        # إعداد نموذج الفلترة
        filter_form = {
            "status": status,
            "search": search,
            "date_from": date_from,
            "date_to": date_to,
            "category": category_filter,
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

        # Django pagination على مستوى database
        from django.core.paginator import Paginator
        paginator = Paginator(journal_entries_list, 50)  # 50 قيد في الصفحة
        page_number = request.GET.get("page", 1)
        page_obj = paginator.get_page(page_number)
        
        # تحميل القيود للصفحة الحالية فقط مع خطوطها والحسابات والمستخدمين
        journal_entries_raw = page_obj.object_list.prefetch_related(
            'lines__account'
        ).select_related('created_by', 'accounting_period')
        
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
                
                # استخدام النوع المحفوظ في القيد أولاً
                if hasattr(entry, 'entry_type') and entry.entry_type and entry.entry_type != 'manual':
                    # استخدام النوع المحفوظ مباشرة
                    entry_type = entry.get_entry_type_display() if hasattr(entry, 'get_entry_type_display') else entry.entry_type
                # تحديد نوع القيد بناءً على تحليل الخطوط (للقيود اليدوية فقط)
                elif len(lines) == 2:
                    line1, line2 = lines[0], lines[1]
                    
                    # تحليل ذكي لنوع القيد بناءً على أسماء الحسابات الفعلية
                    account_names = [line1.account.name, line2.account.name]
                    
                    # التحقق من وجود حسابات نقدية (صندوق)
                    cash_accounts = ['الصندوق', 'صندوق', 'نقدية', 'كاش']
                    has_cash = any(cash_word in acc_name for acc_name in account_names for cash_word in cash_accounts)
                    
                    # التحقق من وجود حسابات بنكية
                    bank_accounts = ['بنك', 'البنك', 'مصرف']
                    has_bank = any(bank_word in acc_name for acc_name in account_names for bank_word in bank_accounts)
                    
                    # التحقق من وجود حسابات أولياء الأمور/موردين
                    parent_accounts = ['العملاء', 'عميل', 'مدينون', 'أولياء الأمور', 'ولي أمر']
                    supplier_accounts = ['الموردون', 'مورد', 'دائنون']
                    has_parent = any(parent_word in acc_name for acc_name in account_names for parent_word in parent_accounts)
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
                    # فواتير المبيعات: أولياء الأمور (مدين) + إيرادات (دائن)
                    elif has_parent and has_revenue:
                        entry_type = "فاتورة مبيعات"
                    # فواتير المشتريات: مصروفات/مخزون (مدين) + موردون (دائن)
                    elif has_supplier and has_expense:
                        entry_type = "فاتورة مشتريات"
                    # فواتير المشتريات البديلة: موردون (دائن) + أي حساب آخر (مدين)
                    elif has_supplier and not (has_cash or has_bank or has_parent):
                        entry_type = "فاتورة مشتريات"
                    # فواتير المبيعات البديلة: أولياء الأمور (مدين) + أي حساب آخر (دائن)
                    elif has_parent and not (has_cash or has_bank or has_supplier):
                        entry_type = "فاتورة مبيعات"
                    elif has_parent and (has_cash or has_bank):
                        entry_type = "تحصيل من ولي أمر"
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
            
            # تحديد أيقونة ولون النوع
            entry_type_display = entry.get_entry_type_display() if hasattr(entry, 'get_entry_type_display') else "غير محدد"
            entry_type_raw = entry.entry_type if hasattr(entry, 'entry_type') else 'manual'
            
            # تعيين الأيقونة واللون حسب النوع
            type_icon_map = {
                'manual': ('fa-edit', 'secondary'),
                'automatic': ('fa-robot', 'primary'),
                'adjustment': ('fa-balance-scale', 'warning'),
                'closing': ('fa-door-closed', 'dark'),
                'opening': ('fa-door-open', 'success'),
                'inventory': ('fa-boxes', 'info'),
                'fee': ('fa-file-invoice-dollar', 'primary'),  # للتوافق مع القيود القديمة
                'application_fee': ('fa-file-invoice', 'primary'),
                'tuition_fee': ('fa-graduation-cap', 'primary'),
                'bus_fee': ('fa-bus', 'primary'),
                'materials_fee': ('fa-book', 'primary'),
                'services_fee': ('fa-concierge-bell', 'primary'),
                'activity_fee': ('fa-running', 'primary'),
                'admin_fee': ('fa-user-tie', 'primary'),
                'product_delivery': ('fa-truck', 'info'),
                'delivery_fee': ('fa-shipping-fast', 'info'),
                'complementary_fee': ('fa-plus-circle', 'primary'),
                'parent_payment': ('fa-hand-holding-usd', 'success'),
                'supplier_payment': ('fa-money-check-alt', 'danger'),
                'salary_payment': ('fa-money-bill-wave', 'warning'),
                'partner_contribution': ('fa-handshake', 'success'),
                'partner_withdrawal': ('fa-hand-holding-usd', 'danger'),
                'cash_receipt': ('fa-cash-register', 'success'),
                'cash_payment': ('fa-money-bill-wave', 'danger'),
                'bank_receipt': ('fa-university', 'success'),
                'bank_payment': ('fa-credit-card', 'danger'),
                'transfer': ('fa-exchange-alt', 'info'),
                'refund': ('fa-undo', 'warning'),
                'settlement': ('fa-handshake', 'info'),
                'discount': ('fa-percentage', 'success'),
                'penalty': ('fa-exclamation-triangle', 'danger'),
                'reversal': ('fa-undo-alt', 'dark'),
            }
            
            icon, color = type_icon_map.get(entry_type_raw, ('fa-file-alt', 'secondary'))
            
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
                'reference': entry.number or f"JE-{entry.id}",  # استخدام رقم القيد الفعلي
                'date': entry.date,
                'entry_type': entry_type_display,
                'entry_type_raw': entry_type_raw,
                'entry_type_icon': icon,
                'entry_type_color': color,
                'original_entry_type': entry_type,  # النوع المحسوب للمرجعية
                'description': entry.description or "بدون وصف",
                'amount': amount,
                'status': entry.status or 'posted',
                'created_by': _get_user_display_name(entry.created_by),
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
    table_headers = [
        {"key": "reference", "label": "رقم القيد", "sortable": True, "width": "120px"},
        {"key": "date", "label": "التاريخ", "sortable": True, "format": "date", "width": "120px"},
        {"key": "entry_type", "label": "النوع", "sortable": False, "width": "150px", "format": "html"},
        {"key": "financial_category", "label": "التصنيف المالي", "sortable": True, "width": "150px", "format": "html"},
        {"key": "description", "label": "الوصف", "sortable": False},
        {"key": "amount", "label": "المبلغ", "sortable": True, "format": "currency", "width": "120px"},
        {"key": "status", "label": "الحالة", "sortable": True, "format": "status", "width": "100px"},
        {"key": "created_by", "label": "المستخدم", "sortable": True, "width": "120px"},
    ]

    # تحضير البيانات للجدول الموحد
    table_data = []
    for entry in journal_entries:
        actions = [
            {
                'url': reverse('financial:journal_entries_detail', args=[entry.id]),
                'icon': 'fas fa-eye',
                'label': 'عرض التفاصيل',
                'class': 'btn-outline-info btn-sm',
                'title': 'عرض التفاصيل'
            }
        ]
        
        # تحضير عرض التصنيف المالي (الفرعي أولاً، ثم الرئيسي)
        category_display = '-'
        if hasattr(entry, '_original') and hasattr(entry._original, 'financial_category'):
            # أولوية للتصنيف الفرعي
            if hasattr(entry._original, 'financial_subcategory') and entry._original.financial_subcategory:
                subcat = entry._original.financial_subcategory
                category_display = f'<span class="badge bg-primary">{subcat.name}</span>'
            elif entry._original.financial_category:
                # تصنيف أساسي فقط
                cat = entry._original.financial_category
                category_display = f'<span class="badge bg-primary">{cat.name}</span>'
        
        # تحضير badge النوع مع الأيقونة - استخدام entry_type_display للحصول على الترجمة الصحيحة
        # entry.entry_type يحتوي على entry_type_display من enhanced_data
        # لكن للتأكد، نستخدم القيمة مباشرة من الكائن الأصلي
        display_text = entry._original.get_entry_type_display() if hasattr(entry._original, 'get_entry_type_display') else entry.entry_type
        entry_type_badge = f'<span class="badge bg-{entry.entry_type_color}"><i class="fas {entry.entry_type_icon} me-1"></i>{display_text}</span>'
        
        row_data = {
            'id': entry.id,
            'reference': entry.reference,
            'date': entry.date,
            'entry_type': entry_type_badge,
            'financial_category': category_display,
            'description': entry.description,
            'amount': entry.amount,
            'status': entry.status,
            'created_by': entry.created_by,
            'actions': actions
        }
        table_data.append(row_data)

    # إعداد action buttons
    header_buttons = [
        {
            "url": reverse("financial:cash_and_bank_accounts_list"),
            "icon": "fa-wallet",
            "text": "الخزائن والبنوك",
            "class": "btn-outline-primary",
        },
        {
            "url": reverse("financial:chart_of_accounts_list"),
            "icon": "fa-sitemap",
            "text": "دليل الحسابات",
            "class": "btn-outline-secondary",
        },
    ]
    
    # إضافة زر القيود اليدوية للسوبر أدمن فقط
    if request.user.is_superuser:
        header_buttons.insert(0, {
            "url": reverse("financial:manual_journal_entry_create"),
            "icon": "fa-edit",
            "text": "قيد يدوي",
            "class": "btn-warning",
        })

    # جلب التصنيفات المالية للفلتر
    from financial.models import FinancialCategory
    categories = FinancialCategory.objects.filter(is_active=True).order_by('name')

    context = {
        "journal_entries": journal_entries,
        "table_headers": table_headers,
        "table_data": table_data,
        "headers": table_headers,  # للتوافق مع القالب القديم
        "primary_key": "id",
        "filter_form": filter_form or {},
        "status_choices": status_choices,
        "categories": categories,
        # Django pagination
        "page_obj": page_obj if 'page_obj' in locals() else None,
        "paginator": paginator if 'paginator' in locals() else None,
        # إحصائيات متقدمة
        "total_transactions": total_transactions if 'total_transactions' in locals() else 0,
        "total_debit": total_debit if 'total_debit' in locals() else 0,
        "total_credit": total_credit if 'total_credit' in locals() else 0,
        "page_title": "القيود المحاسبية",
        "page_subtitle": "إدارة القيود المحاسبية والقيود اليومية",
        "page_icon": "fas fa-book",
        "header_buttons": header_buttons,
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
        "page_subtitle": "إدارة القيود المحاسبية",
        "page_icon": "fas fa-plus-square",
        "header_buttons": [
            {
                "url": reverse("financial:journal_entries_list"),
                "icon": "fa-arrow-left",
                "text": "العودة للقائمة",
                "class": "btn-secondary",
            },
        ],
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

    # Sale module removed - skip sale payment lookup

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

    # Sale module removed - skip sale invoice lookup

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
        "page_subtitle": "تفاصيل القيد المحاسبي والبنود المرتبطة",
        "page_icon": "fas fa-file-invoice",
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "القيود المحاسبية", "url": reverse("financial:journal_entries_list"), "icon": "fas fa-book"},
            {"title": f"قيد {journal_entry.number}", "active": True},
        ],
        "header_buttons": [
            {
                "url": reverse("financial:journal_entries_list"),
                "icon": "fa-arrow-left",
                "text": "العودة للقيود",
                "class": "btn-secondary",
            }
        ] + ([
            {
                "url": reverse("financial:journal_entries_edit", kwargs={"pk": journal_entry.pk}),
                "icon": "fa-edit",
                "text": "تعديل القيد",
                "class": "btn-warning",
            },
            {
                "url": reverse("financial:journal_entries_post", kwargs={"pk": journal_entry.pk}),
                "icon": "fa-check",
                "text": "ترحيل القيد",
                "class": "btn-success",
            }
        ] if journal_entry.status == 'draft' else []),
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
    """ترحيل قيد - AJAX only"""
    journal_entry = get_object_or_404(JournalEntry, pk=pk)

    if request.method == "POST":
        try:
            # استخدام الـ method المخصص للترحيل
            journal_entry.post(user=request.user)

            # إرجاع JSON response
            return JsonResponse(
                {
                    "success": True,
                    "message": f'تم ترحيل القيد "{journal_entry.number or journal_entry.reference}" بنجاح.',
                }
            )

        except Exception as e:
            logger.error(f"Error in views.py: {str(e)}", exc_info=True)
            return JsonResponse({"success": False, "message": "حدث خطأ غير متوقع"})
    
    # GET request - إرجاع خطأ (يجب استخدام المودال)
    return JsonResponse({"success": False, "message": "يجب استخدام المودال للترحيل"}, status=405)


@login_required
def journal_entries_unpost(request, pk):
    """إلغاء ترحيل قيد - AJAX only"""
    journal_entry = get_object_or_404(JournalEntry, pk=pk)

    if request.method == "POST":
        try:
            # التحقق من أن القيد مرحل
            if journal_entry.status != 'posted':
                return JsonResponse({"success": False, "message": "القيد غير مرحل"})
            
            # إلغاء الترحيل
            journal_entry.status = 'draft'
            journal_entry.posted_at = None
            journal_entry.posted_by = None
            journal_entry.save()

            # إرجاع JSON response
            return JsonResponse(
                {
                    "success": True,
                    "message": f'تم إلغاء ترحيل القيد "{journal_entry.number or journal_entry.reference}" بنجاح.',
                }
            )

        except Exception as e:
            logger.error(f"Error in unpost: {str(e)}", exc_info=True)
            return JsonResponse({"success": False, "message": "حدث خطأ غير متوقع"})
    
    # GET request - إرجاع خطأ
    return JsonResponse({"success": False, "message": "يجب استخدام المودال لإلغاء الترحيل"}, status=405)


@login_required
def transaction_list(request):
    """
    عرض قائمة المعاملات النقدية والبنكية فقط
    (القيود التي تحتوي على حركة في الصندوق أو البنك)
    """
    # استخدام JournalEntry بدلاً من Transaction مع prefetch للأداء
    from django.db.models import Prefetch, Q
    
    # جلب القيود التي تحتوي على حسابات نقدية أو بنكية فقط
    journal_entries = (
        JournalEntry.objects.filter(
            Q(lines__account__is_cash_account=True) | 
            Q(lines__account__is_bank_account=True)
        )
        .distinct()
        .prefetch_related('lines', 'lines__account', 'lines__account__account_type')
        .order_by("-date", "-id")
    )
    
    # جلب الحسابات النقدية والبنكية فقط للفلترة
    accounts = ChartOfAccounts.objects.filter(
        Q(is_cash_account=True) | Q(is_bank_account=True),
        is_active=True
    ).order_by('code')

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

    # إحصائيات - حساب إجمالي الوارد والصادر من الحسابات النقدية فقط
    total_entries = journal_entries.count()
    
    # حساب الوارد: المدين في الحسابات النقدية والبنكية
    total_debit = (
        JournalEntryLine.objects.filter(
            journal_entry__in=journal_entries
        ).filter(
            Q(account__is_cash_account=True) | Q(account__is_bank_account=True)
        ).aggregate(Sum("debit"))["debit__sum"] or 0
    )
    
    # حساب الصادر: الدائن في الحسابات النقدية والبنكية
    total_credit = (
        JournalEntryLine.objects.filter(
            journal_entry__in=journal_entries
        ).filter(
            Q(account__is_cash_account=True) | Q(account__is_bank_account=True)
        ).aggregate(Sum("credit"))["credit__sum"] or 0
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

    # أزرار الإجراءات
    page_actions = [
        {
            "label": "إضافة إيراد",
            "url": "#",
            "icon": "fas fa-plus-circle",
            "class": "btn-success",
            "modal": "#quickIncomeModal"
        },
        {
            "label": "إضافة مصروف",
            "url": "#",
            "icon": "fas fa-minus-circle",
            "class": "btn-danger",
            "modal": "#quickExpenseModal"
        },
    ]
    
    context = {
        "transactions": page_obj,  # استخدام transactions للتوافق مع template
        "journal_entries": page_obj,
        "headers": headers,
        "action_buttons": action_buttons,
        "accounts": accounts,
        "total_transactions": total_entries,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "page_title": "الحركات النقدية والبنكية",
        "page_subtitle": "عرض جميع المعاملات التي تؤثر على الصندوق والبنك",
        "page_icon": "fas fa-money-bill-wave",
        "page_actions": page_actions,
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "الإدارة المالية", "url": "#", "icon": "fas fa-money-bill-wave"},
            {"title": "الحركات النقدية والبنكية", "active": True},
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
            self.status = journal_entry.status  # إضافة الحالة
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
            has_revenue = False
            has_expense = False
            
            for line in lines:
                if line.account and line.account.account_type:
                    category = line.account.account_type.category
                    if category == "revenue":
                        has_revenue = True
                    elif category == "expense":
                        has_expense = True
            
            # تحديد النوع بناءً على الحسابات الموجودة
            if has_revenue:
                return "income"
            elif has_expense:
                return "expense"
            
            return "manual"

        def _get_main_account(self, entry):
            """الحصول على الحساب الرئيسي (أول حساب في القيد)"""
            first_line = entry.lines.first()
            return first_line.account if first_line else None

    transaction_proxy = TransactionProxy(journal_entry)
    
    # تحديد نوع المعاملة للـ breadcrumb
    transaction_type = transaction_proxy.transaction_type
    if transaction_type == "income":
        parent_title = "الإيرادات"
        parent_url = reverse("financial:income_list")
    elif transaction_type == "expense":
        parent_title = "المصروفات"
        parent_url = reverse("financial:expense_list")
    else:
        parent_title = "الحركات النقدية والبنكية"
        parent_url = reverse("financial:transaction_list")

    context = {
        "transaction": transaction_proxy,  # للتوافق مع template
        "journal_entry": journal_entry,
        "journal_lines": journal_entry.lines.all(),
        "title": f"قيد محاسبي: {journal_entry.number}",
        "page_title": f"تفاصيل القيد - {journal_entry.number}",
        "page_icon": "fas fa-file-invoice",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "الإدارة المالية", "url": "#", "icon": "fas fa-money-bill-wave"},
            {"title": parent_title, "url": parent_url},
            {"title": f"قيد {journal_entry.number}", "active": True},
        ],
    }

    return render(request, "financial/transactions/transaction_detail.html", context)


# تم حذف transaction_create, transaction_edit, transaction_delete
# كانت "تحت التطوير" وغير مستخدمة - استخدم journal_entries بدلاً منها


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


# ============== الخدمات المحسنة للقيود المحاسبية ==============

def create_entry_optimized(entry_data, lines_data, user=None):
    """
    إنشاء قيد محسن مع البنود والتحقق من التوازن
    
    Args:
        entry_data (dict): بيانات القيد الأساسية
        lines_data (list): قائمة بنود القيد
        user (User): المستخدم الحالي
    
    Returns:
        tuple: (success: bool, entry: JournalEntry, message: str)
    """
    from django.db import transaction as db_transaction
    from decimal import Decimal
    
    try:
        with db_transaction.atomic():
            # إنشاء القيد الأساسي
            entry = JournalEntry()
            
            # تعيين البيانات الأساسية
            entry.date = entry_data.get('date', timezone.now().date())
            entry.description = entry_data.get('description', '')
            entry.entry_type = entry_data.get('entry_type', 'manual')
            entry.reference = entry_data.get('reference', '')
            entry.status = entry_data.get('status', 'draft')
            
            # تعيين الفترة المحاسبية
            if 'accounting_period' in entry_data:
                entry.accounting_period = entry_data['accounting_period']
            else:
                # البحث عن الفترة المحاسبية المناسبة
                try:
                    period = AccountingPeriod.objects.filter(
                        start_date__lte=entry.date,
                        end_date__gte=entry.date,
                        status='open'
                    ).first()
                    if period:
                        entry.accounting_period = period
                except Exception:
                    pass
            
            # تعيين المستخدم
            if user:
                entry.created_by = user
            
            # حفظ القيد أولاً للحصول على ID
            entry.save()
            
            # إنشاء رقم القيد إذا لم يكن موجوداً
            if not entry.number:
                entry.number = f"JE-{entry.id:06d}"
                entry.save()
            
            # إنشاء بنود القيد
            total_debit = Decimal('0')
            total_credit = Decimal('0')
            
            for line_data in lines_data:
                line = JournalEntryLine()
                line.journal_entry = entry
                
                # تعيين الحساب
                account_id = line_data.get('account_id')
                if account_id:
                    try:
                        line.account = ChartOfAccounts.objects.get(id=account_id)
                    except ChartOfAccounts.DoesNotExist:
                        raise ValueError(f"الحساب غير موجود: {account_id}")
                else:
                    raise ValueError("معرف الحساب مطلوب")
                
                # تعيين المبالغ
                debit = Decimal(str(line_data.get('debit', '0') or '0'))
                credit = Decimal(str(line_data.get('credit', '0') or '0'))
                
                # التحقق من صحة المبالغ
                if debit < 0 or credit < 0:
                    raise ValueError("المبالغ يجب أن تكون موجبة")
                
                if debit > 0 and credit > 0:
                    raise ValueError("لا يمكن أن يكون البند مدين ودائن في نفس الوقت")
                
                if debit == 0 and credit == 0:
                    raise ValueError("يجب أن يحتوي البند على مبلغ مدين أو دائن")
                
                line.debit = debit
                line.credit = credit
                line.description = line_data.get('description', '')
                
                # حفظ البند
                line.save()
                
                # تجميع المبالغ للتحقق من التوازن
                total_debit += debit
                total_credit += credit
            
            # التحقق من توازن القيد
            if total_debit != total_credit:
                raise ValueError(f"القيد غير متوازن: المدين {total_debit} ≠ الدائن {total_credit}")
            
            # تحديث إجمالي القيد
            entry.total_amount = total_debit
            entry.save()
            
            return True, entry, "تم إنشاء القيد بنجاح"
    
    except Exception as e:
        return False, None, str(e)


def post_entries_batch(entry_ids, user=None):
    """
    ترحيل مجمع للقيود مع التحقق من التوازن
    
    Args:
        entry_ids (list): قائمة معرفات القيود
        user (User): المستخدم الحالي
    
    Returns:
        dict: نتائج الترحيل
    """
    from django.db import transaction as db_transaction
    
    results = {
        'success_count': 0,
        'failed_count': 0,
        'errors': [],
        'posted_entries': []
    }
    
    if not entry_ids:
        results['errors'].append("لا توجد قيود للترحيل")
        return results
    
    # جلب القيود مع البنود
    entries = JournalEntry.objects.filter(
        id__in=entry_ids,
        status='draft'
    ).prefetch_related('lines', 'lines__account')
    
    for entry in entries:
        try:
            with db_transaction.atomic():
                # التحقق من صحة القيد
                validation_result = validate_entry_for_posting(entry)
                if not validation_result['valid']:
                    results['failed_count'] += 1
                    results['errors'].append(f"القيد {entry.number}: {validation_result['message']}")
                    continue
                
                # ترحيل القيد
                entry.status = 'posted'
                entry.posted_at = timezone.now()
                if user:
                    entry.posted_by = user
                
                entry.save()
                
                # تحديث أرصدة الحسابات (إذا كان هناك نظام تخزين مؤقت للأرصدة)
                update_account_balances_for_entry(entry)
                
                results['success_count'] += 1
                results['posted_entries'].append(entry.id)
        
        except Exception as e:
            results['failed_count'] += 1
            results['errors'].append(f"القيد {entry.number}: {str(e)}")
    
    return results


def validate_entry_for_posting(entry):
    """
    التحقق من صحة القيد قبل الترحيل
    
    Args:
        entry (JournalEntry): القيد المراد التحقق منه
    
    Returns:
        dict: نتيجة التحقق
    """
    from decimal import Decimal
    
    # التحقق من وجود بنود
    lines = list(entry.lines.all())
    if not lines:
        return {'valid': False, 'message': 'القيد لا يحتوي على بنود'}
    
    if len(lines) < 2:
        return {'valid': False, 'message': 'القيد يجب أن يحتوي على بندين على الأقل'}
    
    # التحقق من التوازن
    total_debit = sum(line.debit or Decimal('0') for line in lines)
    total_credit = sum(line.credit or Decimal('0') for line in lines)
    
    if total_debit != total_credit:
        return {
            'valid': False, 
            'message': f'القيد غير متوازن: المدين {total_debit} ≠ الدائن {total_credit}'
        }
    
    # التحقق من صحة الحسابات
    for line in lines:
        if not line.account:
            return {'valid': False, 'message': 'يوجد بند بدون حساب'}
        
        if not line.account.is_active:
            return {'valid': False, 'message': f'الحساب {line.account.name} غير نشط'}
        
        if not line.account.is_leaf:
            return {'valid': False, 'message': f'الحساب {line.account.name} ليس حساباً نهائياً'}
    
    # التحقق من الفترة المحاسبية
    if entry.accounting_period and entry.accounting_period.status != 'open':
        return {'valid': False, 'message': 'الفترة المحاسبية مغلقة'}
    
    # التحقق من التاريخ
    if entry.date > timezone.now().date():
        return {'valid': False, 'message': 'تاريخ القيد في المستقبل'}
    
    return {'valid': True, 'message': 'القيد صحيح ومتوازن'}


def update_account_balances_for_entry(entry):
    """
    تحديث أرصدة الحسابات بعد ترحيل القيد
    
    Args:
        entry (JournalEntry): القيد المرحل
    """
    from django.core.cache import cache
    
    # الحصول على الحسابات المتأثرة
    affected_accounts = set()
    for line in entry.lines.all():
        affected_accounts.add(line.account.id)
        
        # إضافة الحسابات الأب أيضاً
        parent = line.account.parent
        while parent:
            affected_accounts.add(parent.id)
            parent = parent.parent
    
    # حذف التخزين المؤقت للحسابات المتأثرة
    for account_id in affected_accounts:
        cache_keys = [
            f"account_balance_{account_id}",
            f"account_transactions_{account_id}",
        ]
        cache.delete_many(cache_keys)
    
    # حذف التخزين المؤقت العام
    cache.delete_many([
        'accounts_summary_all',
        'balances_batch_*'
    ])


def get_entries_with_filters_optimized(filters=None, page_size=25):
    """
    جلب القيود مع الفلاتر والأداء المحسن
    
    Args:
        filters (dict): فلاتر البحث
        page_size (int): حجم الصفحة
    
    Returns:
        QuerySet: القيود المفلترة
    """
    from django.db.models import Prefetch, Q
    
    # الاستعلام الأساسي المحسن
    queryset = JournalEntry.objects.select_related(
        'created_by',
        'posted_by',
        'accounting_period'
    ).prefetch_related(
        Prefetch(
            'lines',
            queryset=JournalEntryLine.objects.select_related('account', 'account__account_type')
        )
    )
    
    # تطبيق الفلاتر
    if filters:
        # فلتر الحالة
        if 'status' in filters and filters['status']:
            queryset = queryset.filter(status=filters['status'])
        
        # فلتر التاريخ
        if 'date_from' in filters and filters['date_from']:
            queryset = queryset.filter(date__gte=filters['date_from'])
        if 'date_to' in filters and filters['date_to']:
            queryset = queryset.filter(date__lte=filters['date_to'])
        
        # فلتر نوع القيد
        if 'entry_type' in filters and filters['entry_type']:
            queryset = queryset.filter(entry_type=filters['entry_type'])
        
        # البحث النصي
        if 'search' in filters and filters['search']:
            search_term = filters['search']
            queryset = queryset.filter(
                Q(number__icontains=search_term) |
                Q(reference__icontains=search_term) |
                Q(description__icontains=search_term)
            )
        
        # فلتر الحساب
        if 'account_id' in filters and filters['account_id']:
            queryset = queryset.filter(lines__account_id=filters['account_id']).distinct()
        
        # فلتر المستخدم
        if 'created_by' in filters and filters['created_by']:
            queryset = queryset.filter(created_by=filters['created_by'])
        
        # فلتر الفترة المحاسبية
        if 'accounting_period' in filters and filters['accounting_period']:
            queryset = queryset.filter(accounting_period=filters['accounting_period'])
        
        # فلتر المبلغ
        if 'amount_from' in filters and filters['amount_from']:
            queryset = queryset.filter(total_amount__gte=filters['amount_from'])
        if 'amount_to' in filters and filters['amount_to']:
            queryset = queryset.filter(total_amount__lte=filters['amount_to'])
    
    # ترتيب محسن
    queryset = queryset.order_by('-date', '-id')
    
    return queryset


def get_entry_analytics(entry_ids=None, date_range=None):
    """
    تحليلات متقدمة للقيود المحاسبية
    
    Args:
        entry_ids (list): قائمة معرفات القيود (None للجميع)
        date_range (dict): نطاق التاريخ
    
    Returns:
        dict: تحليلات شاملة
    """
    from django.db.models import Count, Sum, Avg, Q
    from decimal import Decimal
    
    # الاستعلام الأساسي
    queryset = JournalEntry.objects.all()
    
    # تطبيق الفلاتر
    if entry_ids:
        queryset = queryset.filter(id__in=entry_ids)
    
    if date_range:
        if 'from' in date_range and date_range['from']:
            queryset = queryset.filter(date__gte=date_range['from'])
        if 'to' in date_range and date_range['to']:
            queryset = queryset.filter(date__lte=date_range['to'])
    
    # إحصائيات أساسية
    total_entries = queryset.count()
    
    # إحصائيات حسب الحالة
    status_stats = queryset.values('status').annotate(
        count=Count('id'),
        total_amount=Sum('total_amount')
    )
    
    # إحصائيات حسب النوع
    type_stats = queryset.values('entry_type').annotate(
        count=Count('id'),
        total_amount=Sum('total_amount')
    )
    
    # إحصائيات المبالغ
    amount_stats = queryset.aggregate(
        total_amount=Sum('total_amount'),
        avg_amount=Avg('total_amount'),
        max_amount=models.Max('total_amount'),
        min_amount=models.Min('total_amount')
    )
    
    # إحصائيات حسب المستخدم
    user_stats = queryset.values('created_by__username').annotate(
        count=Count('id'),
        total_amount=Sum('total_amount')
    ).order_by('-count')[:10]
    
    # إحصائيات شهرية (آخر 12 شهر)
    from django.db.models.functions import TruncMonth
    monthly_stats = queryset.annotate(
        month=TruncMonth('date')
    ).values('month').annotate(
        count=Count('id'),
        total_amount=Sum('total_amount')
    ).order_by('month')
    
    return {
        'total_entries': total_entries,
        'status_stats': {item['status']: item for item in status_stats},
        'type_stats': {item['entry_type']: item for item in type_stats},
        'amount_stats': amount_stats,
        'user_stats': list(user_stats),
        'monthly_stats': list(monthly_stats),
        'posted_entries': queryset.filter(status='posted').count(),
        'draft_entries': queryset.filter(status='draft').count(),
        'cancelled_entries': queryset.filter(status='cancelled').count(),
    }


def duplicate_entry_optimized(entry_id, new_date=None, user=None):
    """
    نسخ قيد محاسبي مع تحسينات
    
    Args:
        entry_id (int): معرف القيد المراد نسخه
        new_date (date): التاريخ الجديد
        user (User): المستخدم الحالي
    
    Returns:
        tuple: (success: bool, new_entry: JournalEntry, message: str)
    """
    from django.db import transaction as db_transaction
    
    try:
        # جلب القيد الأصلي مع البنود
        original_entry = JournalEntry.objects.prefetch_related('lines').get(id=entry_id)
        
        with db_transaction.atomic():
            # إنشاء القيد الجديد
            new_entry = JournalEntry()
            new_entry.date = new_date or timezone.now().date()
            new_entry.description = f"نسخة من: {original_entry.description}"
            new_entry.entry_type = original_entry.entry_type
            new_entry.reference = f"نسخة من {original_entry.reference}" if original_entry.reference else ""
            new_entry.status = 'draft'  # دائماً مسودة
            new_entry.accounting_period = original_entry.accounting_period
            
            if user:
                new_entry.created_by = user
            
            new_entry.save()
            
            # إنشاء رقم القيد
            new_entry.number = f"JE-{new_entry.id:06d}"
            new_entry.save()
            
            # نسخ البنود
            for original_line in original_entry.lines.all():
                new_line = JournalEntryLine()
                new_line.journal_entry = new_entry
                new_line.account = original_line.account
                new_line.debit = original_line.debit
                new_line.credit = original_line.credit
                new_line.description = original_line.description
                new_line.save()
            
            # تحديث إجمالي القيد
            new_entry.total_amount = original_entry.total_amount
            new_entry.save()
            
            return True, new_entry, "تم نسخ القيد بنجاح"
    
    except JournalEntry.DoesNotExist:
        return False, None, "القيد الأصلي غير موجود"
    except Exception as e:
        return False, None, str(e)


def reverse_entry_optimized(entry_id, reversal_date=None, user=None):
    """
    عكس قيد محاسبي (إنشاء قيد عكسي)
    
    Args:
        entry_id (int): معرف القيد المراد عكسه
        reversal_date (date): تاريخ القيد العكسي
        user (User): المستخدم الحالي
    
    Returns:
        tuple: (success: bool, reversal_entry: JournalEntry, message: str)
    """
    from django.db import transaction as db_transaction
    
    try:
        # جلب القيد الأصلي مع البنود
        original_entry = JournalEntry.objects.prefetch_related('lines').get(
            id=entry_id, 
            status='posted'  # يمكن عكس القيود المرحلة فقط
        )
        
        with db_transaction.atomic():
            # إنشاء القيد العكسي
            reversal_entry = JournalEntry()
            reversal_entry.date = reversal_date or timezone.now().date()
            reversal_entry.description = f"عكس قيد: {original_entry.description}"
            reversal_entry.entry_type = 'reversal'
            reversal_entry.reference = f"عكس {original_entry.number}"
            reversal_entry.status = 'draft'
            reversal_entry.accounting_period = original_entry.accounting_period
            
            if user:
                reversal_entry.created_by = user
            
            reversal_entry.save()
            
            # إنشاء رقم القيد
            reversal_entry.number = f"REV-{reversal_entry.id:06d}"
            reversal_entry.save()
            
            # إنشاء البنود العكسية
            for original_line in original_entry.lines.all():
                reversal_line = JournalEntryLine()
                reversal_line.journal_entry = reversal_entry
                reversal_line.account = original_line.account
                # عكس المدين والدائن
                reversal_line.debit = original_line.credit
                reversal_line.credit = original_line.debit
                reversal_line.description = f"عكس: {original_line.description}"
                reversal_line.save()
            
            # تحديث إجمالي القيد
            reversal_entry.total_amount = original_entry.total_amount
            reversal_entry.save()
            
            return True, reversal_entry, "تم إنشاء القيد العكسي بنجاح"
    
    except JournalEntry.DoesNotExist:
        return False, None, "القيد الأصلي غير موجود أو غير مرحل"
    except Exception as e:
        return False, None, str(e)



# ============== القيود اليدوية (Manual Journal Entries) ==============

@login_required
def manual_journal_entry_create(request):
    """
    إنشاء قيد يدوي - متاح فقط للسوبر أدمن
    """
    # التحقق من صلاحيات السوبر أدمن
    if not request.user.is_superuser:
        messages.error(request, "عذراً، هذه الصفحة متاحة فقط للمسؤول الرئيسي")
        return redirect('financial:journal_entries_list')
    
    if request.method == 'POST':
        try:
            # استيراد AccountingGateway والخدمات المطلوبة
            from governance.services import AccountingGateway, JournalEntryLineData
            from governance.exceptions import IdempotencyError, AuthorityViolationError
            
            # جلب البيانات من الفورم
            amount = Decimal(request.POST.get('amount', 0))
            debit_account_id = request.POST.get('debit_account')
            credit_account_id = request.POST.get('credit_account')
            description = request.POST.get('description', '').strip()
            entry_date = request.POST.get('entry_date')
            
            # التحقق من البيانات
            if not all([amount, debit_account_id, credit_account_id, description, entry_date]):
                messages.error(request, "جميع الحقول مطلوبة")
                return redirect('financial:manual_journal_entry_create')
            
            if amount <= 0:
                messages.error(request, "المبلغ يجب أن يكون أكبر من صفر")
                return redirect('financial:manual_journal_entry_create')
            
            if debit_account_id == credit_account_id:
                messages.error(request, "لا يمكن أن يكون الحساب المدين والدائن نفس الحساب")
                return redirect('financial:manual_journal_entry_create')
            
            # جلب الحسابات
            debit_account = get_object_or_404(ChartOfAccounts, id=debit_account_id, is_active=True)
            credit_account = get_object_or_404(ChartOfAccounts, id=credit_account_id, is_active=True)
            
            # تحويل التاريخ
            entry_date_obj = datetime.strptime(entry_date, '%Y-%m-%d').date()
            
            # إنشاء idempotency key فريد
            # استخدام timestamp بالثواني + user_id لضمان الفرادة
            timestamp_seconds = int(timezone.now().timestamp())
            unique_id = (timestamp_seconds % 1000000000) + request.user.id  # رقم صغير نسبياً
            idempotency_key = f"manual_entry_{request.user.id}_{timestamp_seconds}"
            
            # إعداد بيانات خطوط القيد
            lines = [
                JournalEntryLineData(
                    account_code=debit_account.code,
                    debit=amount,
                    credit=Decimal('0.00'),
                    description=f"مدين - {description}"
                ),
                JournalEntryLineData(
                    account_code=credit_account.code,
                    debit=Decimal('0.00'),
                    credit=amount,
                    description=f"دائن - {description}"
                )
            ]
            
            # إنشاء القيد عبر AccountingGateway
            gateway = AccountingGateway()
            
            journal_entry = gateway.create_journal_entry(
                source_module='financial',
                source_model='ManualJournalEntry',
                source_id=unique_id,  # استخدام ID صغير نسبياً للقيود اليدوية
                lines=lines,
                idempotency_key=idempotency_key,
                user=request.user,
                entry_type='manual',
                description=description,
                reference=f"MANUAL-{timezone.now().strftime('%Y%m%d%H%M%S')}",
                date=entry_date_obj
            )
            
            messages.success(request, f"تم إنشاء القيد اليدوي بنجاح - رقم القيد: {journal_entry.number}")
            return redirect('financial:journal_entries_detail', pk=journal_entry.id)
            
        except IdempotencyError as e:
            messages.error(request, "هذا القيد موجود بالفعل (تكرار)")
            return redirect('financial:manual_journal_entry_create')
        except AuthorityViolationError as e:
            messages.error(request, f"خطأ في الصلاحيات: {str(e)}")
            return redirect('financial:manual_journal_entry_create')
        except ValueError as e:
            messages.error(request, f"خطأ في البيانات المدخلة: {str(e)}")
            return redirect('financial:manual_journal_entry_create')
        except Exception as e:
            # Log the full error for debugging
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creating manual journal entry: {str(e)}", exc_info=True)
            messages.error(request, f"حدث خطأ أثناء إنشاء القيد: {str(e)}")
            return redirect('financial:manual_journal_entry_create')
    
    # GET request - عرض الفورم
    # جلب جميع الحسابات النشطة
    accounts = ChartOfAccounts.objects.filter(
        is_active=True
    ).select_related('account_type').order_by('code')
    
    # تجميع الحسابات حسب النوع
    accounts_by_type = {}
    for account in accounts:
        type_name = account.account_type.name if account.account_type else "غير مصنف"
        if type_name not in accounts_by_type:
            accounts_by_type[type_name] = []
        accounts_by_type[type_name].append(account)
    
    context = {
        'accounts': accounts,
        'accounts_by_type': accounts_by_type,
        'today': timezone.now().date(),
        'page_title': 'إضافة قيد يدوي',
        'page_subtitle': 'إنشاء قيد محاسبي يدوي (متاح للمسؤول الرئيسي فقط)',
        'page_icon': 'fas fa-edit',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'القيود المحاسبية', 'url': reverse('financial:journal_entries_list'), 'icon': 'fas fa-book'},
            {'title': 'إضافة قيد يدوي', 'active': True}
        ]
    }
    
    return render(request, 'financial/transactions/manual_journal_entry_create.html', context)
