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
        # جلب جميع القيود مرتبة من الأحدث لحظياً
        journal_entries_list = JournalEntry.objects.select_related('financial_category').all().order_by("-created_at", "-date", "-id")

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
            from utils.search import smart_search_filter
            journal_entries_list = smart_search_filter(
                journal_entries_list,
                search,
                text_fields=["description", "reference"],
                code_fields=["reference", "journal_entry_number"]
            )

        if date_from:
            journal_entries_list = journal_entries_list.filter(date__gte=date_from)

        if date_to:
            journal_entries_list = journal_entries_list.filter(date__lte=date_to)

        if category_filter:
            journal_entries_list = journal_entries_list.filter(financial_category_id=category_filter)

        # فلتر نوع القيد (عكسي / معكوس / إغلاق سنوي / افتتاحي / عادي)
        reversal_filter = request.GET.get("reversal_type", "")
        if reversal_filter == "reversal":
            journal_entries_list = journal_entries_list.filter(is_reversal=True)
        elif reversal_filter == "reversed":
            journal_entries_list = journal_entries_list.filter(reversal_entries__isnull=False).distinct()
        elif reversal_filter == "closing":
            journal_entries_list = journal_entries_list.filter(entry_type='closing')
        elif reversal_filter == "opening":
            journal_entries_list = journal_entries_list.filter(entry_type='opening')
        elif reversal_filter == "normal":
            journal_entries_list = journal_entries_list.filter(
                is_reversal=False,
                reversal_entries__isnull=True
            ).exclude(entry_type__in=['closing', 'opening']).distinct()

        # إعداد نموذج الفلترة
        filter_form = {
            "status": status,
            "search": search,
            "date_from": date_from,
            "date_to": date_to,
            "category": category_filter,
            "reversal_type": reversal_filter,
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

        # التصدير المزدوج: تصدير كافة القيود المحاسبية المفلترة من الباك إند
        if request.GET.get('export') == 'excel':
            from utils.export import export_queryset_to_excel
            return export_queryset_to_excel(
                journal_entries_list,
                filename="journal_entries_export.xlsx",
                fields=["number", "date", "description", "status", "created_by.username"],
                headers=["رقم القيد", "التاريخ", "الوصف", "الحالة", "المستخدم"]
            )

        # Whitelist الفرز الأمني
        allowed_sort_fields = {
            'entry_number': 'number',
            'date': 'date',
            'financial_category': 'financial_category__name',
            'status': 'status',
            'created_by': 'created_by__username',
        }

        # الترقيم والفرز الـ SSR عبر المحرك المركزي
        from core.utils import paginate_queryset, render_paginated_response
        pagination_data = paginate_queryset(
            journal_entries_list,
            request,
            default_per_page=50,
            allowed_sort_fields=allowed_sort_fields
        )

        page_obj = pagination_data['page_obj']
        
        # تحميل القيود للصفحة الحالية فقط مع خطوطها والحسابات والمستخدمين
        journal_entries_raw = page_obj.object_list.prefetch_related(
            'lines__account',
            'reversal_entries',  # تحميل القيود العكسية مسبقاً
        ).select_related('created_by', 'accounting_period')
        
        # حصر المرفقات المربوطة بـ JournalEntry للصفحة الحالية بفرز سريع
        from django.contrib.contenttypes.models import ContentType
        from core.models import Attachment
        try:
            je_ct = ContentType.objects.get_for_model(JournalEntry)
            raw_ids = [e.id for e in journal_entries_raw]
            attached_entry_ids = set(
                Attachment.objects.filter(
                    content_type=je_ct,
                    object_id__in=raw_ids,
                    deleted_at__isnull=True
                ).values_list('object_id', flat=True)
            )
        except Exception:
            attached_entry_ids = set()

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
                    
                    # التحقق من وجود حسابات العملاء/موردين
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
                    # فواتير المبيعات البديلة: العملاء (مدين) + أي حساب آخر (دائن)
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
            
            # تحديد أيقونة ولون النوع
            entry_type_display = entry.get_entry_type_display() if hasattr(entry, 'get_entry_type_display') else "غير محدد"
            entry_type_raw = entry.entry_type if hasattr(entry, 'entry_type') else 'manual'
            
            # تعيين الأيقونة واللون حسب النوع
            type_icon_map = {
                'manual': ('fa-edit', 'secondary'),
                'automatic': ('fa-robot', 'primary'),
                'sales_invoice': ('fa-file-invoice', 'primary'),
                'sale': ('fa-file-invoice', 'primary'),
                'customer_payment': ('fa-hand-holding-usd', 'success'),
                'sales_return': ('fa-undo', 'warning'),
                'purchase_invoice': ('fa-file-invoice-dollar', 'info'),
                'purchase': ('fa-file-invoice-dollar', 'info'),
                'vendor_payment': ('fa-money-check-alt', 'danger'),
                'purchase_return': ('fa-undo-alt', 'warning'),
                'receipt_voucher': ('fa-receipt', 'success'),
                'payment_voucher': ('fa-money-bill-wave', 'danger'),
                'adjustment': ('fa-balance-scale', 'warning'),
                'closing': ('fa-door-closed', 'dark'),
                'opening': ('fa-door-open', 'success'),
                'inventory': ('fa-boxes', 'info'),
                'fee': ('fa-file-invoice-dollar', 'primary'),
                'product_delivery': ('fa-truck', 'info'),
                'delivery_fee': ('fa-shipping-fast', 'info'),
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
                'is_reversal': getattr(entry, 'is_reversal', False),
                'has_reversal': entry.reversal_entries.exists() if hasattr(entry, 'reversal_entries') else False,
                'is_locked': getattr(entry, 'is_locked', False),
                'has_attachments': entry.id in attached_entry_ids,
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
        {"key": "entry_number", "label": "القيد", "sortable": True, "width": "150px", "format": "html"},
        {"key": "entry_type", "label": "النوع", "sortable": False, "width": "130px", "format": "html"},
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
        display_text = entry._original.get_entry_type_display() if hasattr(entry._original, 'get_entry_type_display') else entry.entry_type
        entry_type_badge = f'<span class="badge bg-{entry.entry_type_color}"><i class="fas {entry.entry_type_icon} me-1"></i>{display_text}</span>'

        # أيقونة المرفقات إن وجد مرفق للقيد
        attachment_badge = ' <i class="fas fa-paperclip text-primary ms-1" title="يوجد مرفقات" style="font-size: 0.85rem;"></i>' if getattr(entry, 'has_attachments', False) else ''

        # نسق التاريخ الصغير المصاحب لرقم القيد
        formatted_date = entry.date.strftime("%Y-%m-%d") if hasattr(entry.date, 'strftime') else str(entry.date)
        date_badge = f'<small class="text-muted d-block my-1" style="font-size: 0.8rem;"><i class="far fa-calendar-alt me-1"></i>{formatted_date}</small>'

        # تمييز رقم القيد بناءً على حالته وحظر الفترة الإقفالية
        if entry.is_reversal:
            # قيد عكسي - أيقونة تبادل
            reference_html = (
                f'<span class="fw-bold text-dark">{entry.reference}</span>{attachment_badge}'
                f'{date_badge}'
                f'<span class="badge bg-dark mt-1" title="قيد عكسي">'
                f'<i class="fas fa-exchange-alt me-1"></i>عكسي</span>'
            )
        elif entry.has_reversal:
            # قيد تم عكسه - خط في المنتصف + badge
            reference_html = (
                f'<span class="fw-bold text-muted" style="text-decoration:line-through">{entry.reference}</span>{attachment_badge}'
                f'{date_badge}'
                f'<span class="badge bg-secondary mt-1" title="تم عكس هذا القيد">'
                f'<i class="fas fa-ban me-1"></i>معكوس</span>'
            )
        elif entry._original.entry_type == 'closing':
            reference_html = (
                f'<span class="fw-bold text-dark">{entry.reference}</span>{attachment_badge}'
                f'{date_badge}'
                f'<span class="badge bg-danger mt-1" title="قيد إغلاق سنوي محمي">'
                f'<i class="fas fa-lock me-1"></i>إغلاق سنوي</span>'
            )
        elif entry._original.entry_type == 'opening':
            reference_html = (
                f'<span class="fw-bold text-dark">{entry.reference}</span>{attachment_badge}'
                f'{date_badge}'
                f'<span class="badge bg-success mt-1" title="قيد افتتاحي">'
                f'<i class="fas fa-door-open me-1"></i>افتتاحي</span>'
            )
        elif entry._original.is_period_locked or entry.is_locked:
            # قيد محظر/مقفل بسبب الفترة/السنة المغلقة
            reference_html = (
                f'<span class="fw-bold">{entry.reference}</span>{attachment_badge}'
                f'{date_badge}'
                f'<span class="badge bg-secondary text-dark mt-1" title="القيد يقع في فترة/سنة مغلقة">'
                f'<i class="fas fa-lock me-1"></i>فترة مغلقة</span>'
            )
        else:
            reference_html = (
                f'<span class="fw-bold">{entry.reference}</span>{attachment_badge}'
                f'{date_badge}'
            )

        row_data = {
            'id': entry.id,
            'entry_number': reference_html,
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
        **pagination_data,
        "journal_entries": journal_entries,
        "table_headers": table_headers,
        "table_data": table_data,
        "headers": table_headers,
        "primary_key": "id",
        "filter_form": filter_form or {},
        "status_choices": status_choices,
        "categories": categories,
        "show_export": True,
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
                "url": reverse("financial:chart_of_accounts_list"),
                "icon": "fas fa-calculator",
            },
            {"title": "القيود اليومية", "active": True},
        ],
    }
    return render_paginated_response(
        request,
        "financial/transactions/journal_entries_list.html",
        context,
        table_template_name="components/data_table.html"
    )


@login_required
def journal_entries_create(request):
    """إنشاء قيد جديد"""
    if request.method == "POST":
        try:
            with transaction.atomic():
                import re
                from datetime import datetime
                from core.services.attachment_binding_service import AttachmentBindingService

                date_str = request.POST.get('date')
                entry_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else timezone.now().date()
                reference = request.POST.get('reference', '').strip()
                if not reference:
                    reference = f"MANUAL-{timezone.now().strftime('%Y%m%d%H%M%S')}"

                description = request.POST.get('description', '').strip()
                notes = request.POST.get('notes', '').strip()
                period_id = request.POST.get('accounting_period')

                period = None
                if period_id:
                    period = AccountingPeriod.objects.filter(pk=period_id, status='open').first()
                if not period:
                    period = AccountingPeriod.get_period_for_date(entry_date)

                journal_entry = JournalEntry.objects.create(
                    date=entry_date,
                    reference=reference,
                    description=description,
                    notes=notes,
                    accounting_period=period,
                    status='draft',
                    entry_type='manual',
                    created_by=request.user
                )

                # استخراج ومعالجة بنود القيد
                line_data = {}
                for key, val in request.POST.items():
                    m = re.match(r'lines\[(\d+)\]\[(\w+)\]', key)
                    if m:
                        idx, field = int(m.group(1)), m.group(2)
                        if idx not in line_data:
                            line_data[idx] = {}
                        line_data[idx][field] = val

                total_debit = Decimal('0.00')
                total_credit = Decimal('0.00')

                for idx in sorted(line_data.keys()):
                    item = line_data[idx]
                    acc_id = item.get('account')
                    if not acc_id:
                        continue
                    account = get_object_or_404(ChartOfAccounts, id=acc_id)
                    debit = Decimal(str(item.get('debit') or 0))
                    credit = Decimal(str(item.get('credit') or 0))
                    desc = item.get('description') or journal_entry.description

                    if debit > 0 or credit > 0:
                        JournalEntryLine.objects.create(
                            journal_entry=journal_entry,
                            account=account,
                            debit=debit.quantize(Decimal('0.01')),
                            credit=credit.quantize(Decimal('0.01')),
                            transaction_debit=debit.quantize(Decimal('0.01')),
                            transaction_credit=credit.quantize(Decimal('0.01')),
                            description=desc
                        )
                        total_debit += debit
                        total_credit += credit

                # حفظ المرفقات المتعددة
                uploaded_files = request.FILES.getlist('attachments') or request.FILES.getlist('attachment_file') or [f for f in request.FILES.values()]
                if uploaded_files:
                    AttachmentBindingService.save_attachments_for_object(
                        uploaded_files,
                        journal_entry,
                        request.user,
                        category_code='JOURNAL_ENTRY',
                        category_name='مرفقات القيود اليومية'
                    )

                if request.POST.get('status') == 'posted':
                    from financial.services.ledger_core_service import LedgerCoreService
                    LedgerCoreService.post_entry(journal_entry.pk, user=request.user)
                    messages.success(request, f"تم إنشاء وترحيل القيد {journal_entry.reference} بنجاح.")
                else:
                    if abs(total_debit - total_credit) > Decimal('0.01'):
                        messages.warning(request, f"تم حفظ المسودة بنجاح (تنبيه: القيد غير متوازن: مدين {total_debit} / دائن {total_credit})")
                    else:
                        messages.success(request, f"تم إنشاء مسودة القيد {journal_entry.reference} بنجاح.")

                return redirect("financial:journal_entries_detail", pk=journal_entry.pk)

        except Exception as e:
            logger.error(f"Error creating journal entry: {str(e)}", exc_info=True)
            messages.error(request, f"حدث خطأ أثناء إنشاء القيد: {str(e)}")

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
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "الإدارة المالية",
                "url": reverse("financial:chart_of_accounts_list"),
                "icon": "fas fa-calculator",
            },
            {
                "title": "القيود اليومية",
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

        if hasattr(journal_entry, 'purchase_payment'):
            source_payment = journal_entry.purchase_payment
            source_payment_url = reverse("purchase:payment_detail", kwargs={"pk": source_payment.pk})
            source_party = source_payment.supplier.name if source_payment.supplier else None
    except Exception:
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

    # استخراج المرفقات المنسوبة للقيد المحاسبي
    from django.contrib.contenttypes.models import ContentType
    from core.models import Attachment
    
    ct = ContentType.objects.get_for_model(journal_entry)
    attachments = Attachment.objects.filter(
        content_type=ct,
        object_id=journal_entry.pk,
        deleted_at__isnull=True
    ).select_related('category', 'file_blob')

    header_buttons = []
    if journal_entry.status == 'draft':
        if not journal_entry.is_period_locked:
            header_buttons.append({
                "url": reverse("financial:journal_entries_edit", kwargs={"pk": journal_entry.pk}),
                "icon": "fa-edit",
                "text": "تعديل القيد",
                "class": "btn-warning",
            })
            if total_debits == total_credits and journal_entry.lines.exists():
                header_buttons.append({
                    "onclick": f"postJournalEntry({journal_entry.pk})",
                    "id": "post_entry_btn",
                    "icon": "fa-check",
                    "text": "ترحيل القيد",
                    "class": "btn-success",
                })
            header_buttons.append({
                "onclick": f"deleteJournalEntry({journal_entry.pk}, 'draft')",
                "id": "delete_entry_btn",
                "icon": "fa-trash-alt",
                "text": "حذف القيد",
                "class": "btn-outline-danger",
            })
    elif journal_entry.status == 'posted':
        if not journal_entry.is_period_locked and not journal_entry.is_reversal and not journal_entry.reversed_entry:
            header_buttons.append({
                "onclick": f"editJournalEntry({journal_entry.pk})",
                "id": "edit_entry_btn",
                "icon": "fa-edit",
                "text": "تعديل القيد",
                "class": "btn-warning",
            })
            header_buttons.append({
                "onclick": f"deleteJournalEntry({journal_entry.pk}, 'posted')",
                "id": "delete_entry_btn",
                "icon": "fa-trash-alt",
                "text": "حذف القيد",
                "class": "btn-outline-danger",
            })
            header_buttons.append({
                "onclick": f"reverseJournalEntry({journal_entry.pk})",
                "id": "reverse_entry_btn",
                "icon": "fa-exchange-alt",
                "text": "إنشاء قيد عكسي",
                "class": "btn-outline-secondary",
            })

    header_badges = []
    if journal_entry.is_period_locked:
        header_badges.append({
            "text": "قيد محمي ومحظر في فترة/سنة مغلقة أو قيد إغلاق نظامي",
            "class": "bg-danger text-white",
            "icon": "fa-lock"
        })
    elif journal_entry.status == 'posted':
        header_badges.append({
            "text": "القيد مرحل محمي في السجلات",
            "class": "bg-success",
            "icon": "fa-shield-alt"
        })
    elif journal_entry.status == 'draft':
        header_badges.append({
            "text": "مسودة قيد غير مرحل",
            "class": "bg-warning text-dark",
            "icon": "fa-pencil-alt"
        })

    context = {
        "journal_entry": journal_entry,
        "attachments": attachments,
        "total_debits": total_debits,
        "total_credits": total_credits,
        "difference": difference,
        "source_invoice": source_invoice,
        "source_party": source_party,
        "invoice_type": invoice_type,
        "source_payment": source_payment,
        "source_payment_url": source_payment_url,
        "header_buttons": header_buttons,
        "header_badges": header_badges,
        "page_title": f"تفاصيل قيد رقم: {journal_entry.number}",
        "page_subtitle": f"تاريخ القيد: {journal_entry.date}",
        "page_icon": "fas fa-file-invoice",
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "الإدارة المالية", "url": reverse("financial:chart_of_accounts_list"), "icon": "fas fa-calculator"},
            {"title": "القيود اليومية", "url": reverse("financial:journal_entries_list"), "icon": "fas fa-book"},
            {"title": f"قيد {journal_entry.number or journal_entry.reference}", "active": True},
        ],
    }
    return render(request, "financial/transactions/journal_entries_detail.html", context)


@login_required
def journal_entries_edit(request, pk):
    """تعديل قيد مسودة - يدعم إلغاء الترحيل التلقائي عند فتح قيد مرحل"""
    journal_entry = get_object_or_404(JournalEntry, pk=pk)

    if journal_entry.is_period_locked:
        messages.error(request, "لا يمكن تعديل قيد محمي في فترة/سنة مغلقة أو قيد نظامي.")
        return redirect("financial:journal_entries_detail", pk=pk)

    if journal_entry.is_reversal or journal_entry.reversed_entry:
        messages.error(request, "لا يمكن تعديل قيد تم عكسه أو قيد عكسي.")
        return redirect("financial:journal_entries_detail", pk=pk)

    # إذا كان القيد مرحلاً، نقوم بإلغاء ترحيله أولاً لإتاحته للتعديل
    if journal_entry.status == 'posted':
        try:
            from financial.services.ledger_core_service import LedgerCoreService
            journal_entry = LedgerCoreService.unpost_entry(
                entry_id=journal_entry.pk,
                user=request.user,
                reason="إلغاء الترحيل لفتح القيد للتعديل"
            )
            messages.info(request, f"تم إلغاء ترحيل القيد {journal_entry.reference} بنجاح وإعادته للمسودة لتعديله.")
        except Exception as e:
            logger.error(f"Error unposting journal entry before edit: {str(e)}", exc_info=True)
            messages.error(request, f"تعذر إلغاء ترحيل القيد للتعديل: {str(e)}")
            return redirect("financial:journal_entries_detail", pk=pk)

    if request.method == "POST":
        try:
            with transaction.atomic():
                import re
                from datetime import datetime

                date_str = request.POST.get('date')
                if date_str:
                    journal_entry.date = datetime.strptime(date_str, '%Y-%m-%d').date()

                reference = request.POST.get('reference', '').strip()
                if reference:
                    journal_entry.reference = reference

                journal_entry.description = request.POST.get('description', '').strip()
                journal_entry.notes = request.POST.get('notes', '').strip()

                period_id = request.POST.get('accounting_period')
                if period_id:
                    journal_entry.accounting_period_id = period_id
                else:
                    journal_entry.accounting_period = AccountingPeriod.get_period_for_date(journal_entry.date)

                journal_entry.save()

                # استخراج ومعالجة بنود القيد
                line_data = {}
                for key, val in request.POST.items():
                    m = re.match(r'lines\[(\d+)\]\[(\w+)\]', key)
                    if m:
                        idx, field = int(m.group(1)), m.group(2)
                        if idx not in line_data:
                            line_data[idx] = {}
                        line_data[idx][field] = val

                if line_data:
                    # حذف البنود القديمة للمسودة
                    journal_entry.lines.all().delete()

                    total_debit = Decimal('0.00')
                    total_credit = Decimal('0.00')

                    for idx in sorted(line_data.keys()):
                        item = line_data[idx]
                        acc_id = item.get('account')
                        if not acc_id:
                            continue
                        account = get_object_or_404(ChartOfAccounts, id=acc_id)
                        debit = Decimal(str(item.get('debit') or 0))
                        credit = Decimal(str(item.get('credit') or 0))
                        desc = item.get('description') or journal_entry.description

                        if debit > 0 or credit > 0:
                            JournalEntryLine.objects.create(
                                journal_entry=journal_entry,
                                account=account,
                                debit=debit.quantize(Decimal('0.01')),
                                credit=credit.quantize(Decimal('0.01')),
                                transaction_debit=debit.quantize(Decimal('0.01')),
                                transaction_credit=credit.quantize(Decimal('0.01')),
                                description=desc
                            )
                            total_debit += debit
                            total_credit += credit

                # حفظ المرفقات المتعددة الجديدة إن وجدت
                uploaded_files = request.FILES.getlist('attachments') or request.FILES.getlist('attachment_file') or [f for f in request.FILES.values()]
                if uploaded_files:
                    from core.services.attachment_binding_service import AttachmentBindingService
                    AttachmentBindingService.save_attachments_for_object(
                        uploaded_files,
                        journal_entry,
                        request.user,
                        category_code='JOURNAL_ENTRY',
                        category_name='مرفقات القيود اليومية'
                    )

                if abs(total_debit - total_credit) > Decimal('0.01'):
                    messages.warning(request, f"تم حفظ المسودة (تنبيه: القيد غير متوازن: مدين {total_debit} / دائن {total_credit})")
                else:
                    messages.success(request, f"تم حفظ تعديلات القيد {journal_entry.reference} بنجاح.")

                # إذا طلب المستخدم الترحيل المباشر
                if request.POST.get('status') == 'posted':
                    from financial.services.ledger_core_service import LedgerCoreService
                    LedgerCoreService.post_entry(journal_entry.pk, user=request.user)
                    messages.success(request, f"تم حفظ وترحيل القيد {journal_entry.reference} بنجاح.")

                return redirect("financial:journal_entries_detail", pk=journal_entry.pk)

        except Exception as e:
            logger.error(f"Error updating journal entry: {str(e)}", exc_info=True)
            messages.error(request, f"حدث خطأ أثناء تعديل القيد: {str(e)}")

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

    # استخراج المرفقات الحالية للقيد
    from django.contrib.contenttypes.models import ContentType
    from core.models import Attachment
    ct = ContentType.objects.get_for_model(journal_entry)
    existing_attachments = Attachment.objects.filter(
        content_type=ct,
        object_id=journal_entry.pk,
        deleted_at__isnull=True
    ).select_related('file_blob', 'category')

    context = {
        "journal_entry": journal_entry,
        "accounts": accounts,
        "accounting_periods": accounting_periods,
        "existing_attachments": existing_attachments,
        "page_title": f"تعديل قيد: {journal_entry.reference}",
        "page_icon": "fas fa-edit",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "الإدارة المالية",
                "url": reverse("financial:chart_of_accounts_list"),
                "icon": "fas fa-calculator",
            },
            {
                "title": "القيود اليومية",
                "url": reverse("financial:journal_entries_list"),
                "icon": "fas fa-book",
            },
            {"title": f"تعديل قيد: {journal_entry.reference}", "active": True},
        ],
    }
    return render(request, "financial/transactions/journal_entries_form.html", context)


@login_required
def journal_entries_delete(request, pk):
    """حذف قيد - يدعم إلغاء الترحيل التلقائي قبل الحذف ويدعم AJAX"""
    journal_entry = get_object_or_404(JournalEntry, pk=pk)

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json'

    if journal_entry.is_period_locked:
        msg = "لا يمكن حذف قيد محمي في فترة/سنة مغلقة أو قيد نظامي."
        if is_ajax:
            return JsonResponse({"success": False, "message": msg}, status=400)
        messages.error(request, msg)
        return redirect("financial:journal_entries_detail", pk=pk)

    if journal_entry.is_reversal or journal_entry.reversed_entry:
        msg = "لا يمكن حذف قيد تم عكسه أو قيد عكسي."
        if is_ajax:
            return JsonResponse({"success": False, "message": msg}, status=400)
        messages.error(request, msg)
        return redirect("financial:journal_entries_detail", pk=pk)

    if request.method == "POST":
        try:
            with transaction.atomic():
                # إذا كان القيد مرحلاً، نقوم بإلغاء ترحيله أولاً لتحديث الأرصدة والموازنة ومسح مراجع الترحيل
                if journal_entry.status == 'posted':
                    from financial.services.ledger_core_service import LedgerCoreService
                    journal_entry = LedgerCoreService.unpost_entry(
                        entry_id=journal_entry.pk,
                        user=request.user,
                        reason="إلغاء الترحيل تمهيداً لحذف القيد"
                    )

                ref = journal_entry.reference or str(journal_entry.number)
                journal_entry.delete()

                success_msg = f'تم حذف القيد "{ref}" بنجاح.'
                if is_ajax:
                    return JsonResponse({
                        "success": True,
                        "message": success_msg,
                        "redirect_url": reverse("financial:journal_entries_list")
                    })
                messages.success(request, success_msg)
                return redirect("financial:journal_entries_list")
        except Exception as e:
            logger.error(f"Error deleting journal entry: {str(e)}", exc_info=True)
            err_msg = f"حدث خطأ أثناء حذف القيد: {str(e)}"
            if is_ajax:
                return JsonResponse({"success": False, "message": err_msg}, status=500)
            messages.error(request, err_msg)
            return redirect("financial:journal_entries_detail", pk=pk)

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
            from financial.services.ledger_core_service import LedgerCoreService
            from financial.exceptions import FinancialCoreError, ImmutableLedgerError
            from django.core.exceptions import ValidationError

            entry = LedgerCoreService.post_entry(
                entry_id=journal_entry.pk,
                user=request.user,
                posting_source=journal_entry.posting_source or "MANUAL_JOURNAL",
                posting_reference=journal_entry.reference
            )

            return JsonResponse(
                {
                    "success": True,
                    "message": f'تم ترحيل القيد "{entry.number or entry.reference}" بنجاح.',
                }
            )

        except (FinancialCoreError, ImmutableLedgerError, ValidationError) as e:
            msg = e.messages[0] if hasattr(e, 'messages') and e.messages else str(e)
            return JsonResponse({"success": False, "message": msg})
        except Exception as e:
            logger.error(f"Error in post: {str(e)}", exc_info=True)
            return JsonResponse({"success": False, "message": f"حدث خطأ أثناء الترحيل: {str(e)}"})

    return JsonResponse({"success": False, "message": "يجب استخدام POST للترحيل"}, status=405)


@login_required
def journal_entries_unpost(request, pk):
    """إلغاء ترحيل قيد - AJAX only"""
    journal_entry = get_object_or_404(JournalEntry, pk=pk)

    if request.method == "POST":
        try:
            from financial.services.ledger_core_service import LedgerCoreService
            from financial.exceptions import FinancialCoreError, ImmutableLedgerError
            from django.core.exceptions import ValidationError

            reason = ""
            try:
                import json
                if request.body:
                    body = json.loads(request.body)
                    reason = body.get('reason', '')
            except Exception:
                reason = request.POST.get('reason', '')

            entry = LedgerCoreService.unpost_entry(
                entry_id=journal_entry.pk,
                user=request.user,
                reason=reason
            )

            return JsonResponse(
                {
                    "success": True,
                    "message": f'تم إلغاء ترحيل القيد "{entry.number or entry.reference}" بنجاح وإعادته لحالة المسودة.',
                }
            )

        except (FinancialCoreError, ImmutableLedgerError, ValidationError) as e:
            msg = e.messages[0] if hasattr(e, 'messages') and e.messages else str(e)
            return JsonResponse({"success": False, "message": msg})
        except Exception as e:
            logger.error(f"Error in unpost: {str(e)}", exc_info=True)
            return JsonResponse({"success": False, "message": f"حدث خطأ أثناء إلغاء الترحيل: {str(e)}"})

    return JsonResponse({"success": False, "message": "يجب استخدام POST لإلغاء الترحيل"}, status=405)


@login_required
def journal_entries_reverse(request, pk):
    """إنشاء قيد عكسي للقيود المقفلة أو المرحّلة - AJAX only"""
    journal_entry = get_object_or_404(JournalEntry, pk=pk)

    if request.method == "POST":
        try:
            # التحقق من أن القيد مرحل
            if journal_entry.status != 'posted':
                return JsonResponse({"success": False, "message": "يمكن عكس القيود المرحّلة فقط"})

            # التحقق من أنه لم يُعكس مسبقاً
            if journal_entry.reversed_entry:
                return JsonResponse({
                    "success": False,
                    "message": f"تم عكس هذا القيد مسبقاً - القيد العكسي: {journal_entry.reversed_entry.number}"
                })

            # التحقق من أنه ليس قيداً عكسياً أو قيد إغلاق/افتتاحي نظامي
            if journal_entry.is_reversal:
                return JsonResponse({"success": False, "message": "لا يمكن عكس قيد عكسي"})

            if journal_entry.entry_type in ['closing', 'opening']:
                return JsonResponse({"success": False, "message": "لا يمكن عكس قيود الإغلاق أو القيود الافتتاحية النظامية."})

            # استخراج سبب العكس من الطلب
            try:
                body = json.loads(request.body)
                reason = body.get('reason', '').strip()
            except (json.JSONDecodeError, AttributeError):
                reason = request.POST.get('reason', '').strip()

            if not reason:
                return JsonResponse({"success": False, "message": "يجب إدخال سبب العكس"})

            # استدعاء الدالة الموجودة
            success, reversal_entry, message = reverse_entry_optimized(
                entry_id=journal_entry.pk,
                reversal_date=timezone.now().date(),
                user=request.user,
            )

            if not success:
                return JsonResponse({"success": False, "message": message})

            # ربط القيد العكسي بالأصلي وتسجيل السبب
            reversal_entry.original_entry = journal_entry
            reversal_entry.is_reversal = True
            reversal_entry.reversal_reason = reason
            reversal_entry._bypass_period_lock = True
            reversal_entry.save(update_fields=['original_entry', 'is_reversal', 'reversal_reason'])

            # ترحيل القيد العكسي تلقائياً
            reversal_entry._bypass_period_lock = True
            reversal_entry.status = 'posted'
            reversal_entry.posted_at = timezone.now()
            reversal_entry.posted_by = request.user
            reversal_entry.save(update_fields=['status', 'posted_at', 'posted_by'])

            return JsonResponse({
                "success": True,
                "message": f'تم إنشاء القيد العكسي "{reversal_entry.number}" بنجاح.',
                "reversal_pk": reversal_entry.pk,
                "reversal_number": reversal_entry.number,
            })

        except Exception as e:
            logger.error(f"Error in reverse entry: {str(e)}", exc_info=True)
            return JsonResponse({"success": False, "message": f"حدث خطأ غير متوقع: {str(e)}"})

    return JsonResponse({"success": False, "message": "يجب استخدام POST"}, status=405)


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
            "label": "التاريخ",
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
    
    # إعداد الترقيم الصفحي SSR
    from core.utils import paginate_queryset
    pagination_context = paginate_queryset(journal_entries, request, default_per_page=25)
    page_obj = pagination_context["page_obj"]

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
        "page_obj": page_obj,
        **pagination_context,
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
            from utils.search import smart_search_filter
            search_term = filters['search']
            queryset = smart_search_filter(
                queryset,
                search_term,
                text_fields=["description", "reference"],
                code_fields=["number", "reference"]
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
            reversal_entry.is_reversal = True
            reversal_entry.original_entry = original_entry
            
            # استخدام الفترة المحاسبية الحالية (ليس فترة القيد الأصلي المحتمل إغلاقها)
            current_period = AccountingPeriod.get_period_for_date(reversal_entry.date)
            if not current_period:
                return False, None, "لا توجد فترة محاسبية مفتوحة للتاريخ الحالي"
            reversal_entry.accounting_period = current_period
            
            if user:
                reversal_entry.created_by = user
            
            reversal_entry._gateway_approved = True
            reversal_entry.save()
            
            # إنشاء رقم القيد
            reversal_entry.number = f"REV-{reversal_entry.id:06d}"
            reversal_entry.save(update_fields=['number'])
            
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
            
            return True, reversal_entry, "تم إنشاء القيد العكسي بنجاح"
    
    except JournalEntry.DoesNotExist:
        return False, None, "القيد الأصلي غير موجود أو غير مرحل"
    except Exception as e:
        return False, None, str(e)



# ============== القيود اليدوية (Manual Journal Entries) ==============

@login_required
def manual_journal_entry_create(request):
    """
    إنشاء قيد يدوي مركّب ومحسّن - دعم الأسطر المتعددة ومراكز التكلفة والمرفقات
    """
    if not request.user.is_superuser:
        messages.error(request, "عذراً، هذه الصفحة متاحة فقط للمسؤول الرئيسي")
        return redirect('financial:journal_entries_list')

    from financial.models import CostCenter
    from core.services.attachment_binding_service import AttachmentBindingService

    if request.method == 'POST':
        try:
            from governance.services import AccountingGateway, JournalEntryLineData
            from governance.exceptions import IdempotencyError, AuthorityViolationError
            from financial.services.exchange_rate_service import ExchangeRateService
            entry_currency_code = request.POST.get('entry_currency', 'EGP').strip()
            exchange_rate_val = Decimal(request.POST.get('exchange_rate', '1.000000'))
            func_currency = ExchangeRateService.get_functional_currency()
            func_code = func_currency.code if func_currency else 'EGP'

            entry_date = request.POST.get('entry_date')
            description = request.POST.get('description', '').strip()

            # التمييز بين القيد المركب الشبكي (Multi-Line Grid) والقيد الثنائي البسيط (Legacy Form)
            accounts_list = request.POST.getlist('accounts[]')
            
            lines = []
            if accounts_list and len(accounts_list) > 0:
                # 1. معالجة القيد المركب المتعدد الأسطر
                debits_list = request.POST.getlist('debits[]')
                credits_list = request.POST.getlist('credits[]')
                line_descriptions = request.POST.getlist('line_descriptions[]')
                cost_centers_list = request.POST.getlist('cost_centers[]')
                allocations_json_list = request.POST.getlist('line_allocations_json[]')

                total_debit = Decimal('0.00')
                total_credit = Decimal('0.00')

                for idx, account_id in enumerate(accounts_list):
                    if not account_id:
                        continue

                    account = get_object_or_404(ChartOfAccounts, id=account_id, is_active=True)
                    
                    # فحص حظر تضارب العملات على الحسابات المقيدة (Account Currency Matching Guard)
                    if hasattr(account, 'currency') and account.currency and account.currency.code != func_code:
                        if entry_currency_code != func_code and entry_currency_code != account.currency.code:
                            messages.error(request, f"تضارب العملة: الحساب ({account.name}) مقيد بعملة ({account.currency.code}). لا يمكن إدراج قيد عليه بعملة أجنبية مختلفة ({entry_currency_code}).")
                            return redirect('financial:manual_journal_entry_create')

                    raw_debit = Decimal(debits_list[idx]) if idx < len(debits_list) and debits_list[idx] else Decimal('0.00')
                    raw_credit = Decimal(credits_list[idx]) if idx < len(credits_list) and credits_list[idx] else Decimal('0.00')
                    line_desc = line_descriptions[idx].strip() if idx < len(line_descriptions) and line_descriptions[idx] else description

                    if entry_currency_code != func_code:
                        foreign_debit_val = raw_debit
                        foreign_credit_val = raw_credit
                        debit_val = (foreign_debit_val * exchange_rate_val).quantize(Decimal('0.01'))
                        credit_val = (foreign_credit_val * exchange_rate_val).quantize(Decimal('0.01'))
                    else:
                        debit_val = raw_debit
                        credit_val = raw_credit
                        foreign_debit_val = Decimal('0.00')
                        foreign_credit_val = Decimal('0.00')
                        exchange_rate_val = Decimal('1.000000')

                    cc_code = None
                    if idx < len(cost_centers_list) and cost_centers_list[idx] and cost_centers_list[idx] != 'MULTI':
                        if str(cost_centers_list[idx]).isdigit():
                            cc_obj = CostCenter.objects.filter(id=cost_centers_list[idx]).first()
                            if cc_obj:
                                cc_code = cc_obj.code

                    # معالجة التوزيع المتعدد للسطر الواحدة (Multi-Cost-Center Sub-Allocations)
                    allocations_data = None
                    if idx < len(allocations_json_list) and allocations_json_list[idx]:
                        try:
                            import json
                            raw_alloc = json.loads(allocations_json_list[idx])
                            if isinstance(raw_alloc, list) and len(raw_alloc) > 0:
                                # 1. قاعدة P&L Accounts Only Rule (المصروفات والإيرادات فقط)
                                account_category = account.account_type.category if (account.account_type and hasattr(account.account_type, 'category')) else ''
                                if account_category not in ['expense', 'revenue']:
                                    messages.error(request, f"عذراً، التوزيع المتعدد متاح فقط لحسابات المصروفات والإيرادات. الحساب ({account.name}) ينتمي للميزانية العمومية.")
                                    return redirect('financial:manual_journal_entry_create')

                                line_amount_func = debit_val if debit_val > Decimal('0.00') else credit_val
                                line_amount_foreign = raw_debit if raw_debit > Decimal('0.00') else raw_credit

                                if line_amount_func <= Decimal('0.00'):
                                    messages.error(request, f"خطأ الحوكمة: السطر رقم ({idx+1}) يجب أن يحتوي على مبلغ مدين أو دائن أكبر من صفر للتوزيع.")
                                    return redirect('financial:manual_journal_entry_create')

                                # 2. فحص نشاط مراكز التكلفة وحظر المراكز الأب وتكرار المركز
                                requested_cc_ids = [item.get('cost_center_id') for item in raw_alloc if item.get('cost_center_id')]
                                if len(requested_cc_ids) != len(set(requested_cc_ids)):
                                    messages.error(request, f"حظر التكرار: السطر رقم ({idx+1}) يحتوي على مركز تكلفة مكرر أكثر من مرة.")
                                    return redirect('financial:manual_journal_entry_create')

                                active_ccs = CostCenter.objects.filter(id__in=requested_cc_ids, is_active=True).prefetch_related('children')
                                active_cc_map = {cc.id: cc for cc in active_ccs}

                                for c_id in requested_cc_ids:
                                    if c_id not in active_cc_map:
                                        messages.error(request, f"حظر الحوكمة: مركز التكلفة رقم ({c_id}) غير موجود أو تم إيقاف نشاطه.")
                                        return redirect('financial:manual_journal_entry_create')
                                    cc_obj = active_cc_map[c_id]
                                    if cc_obj.children.exists():
                                        messages.error(request, f"حظر التوجيه: لا يمكن اختيار مركز تكلفة تجميعي/أب ({cc_obj.name}) للتعاملات المالية المباشرة.")
                                        return redirect('financial:manual_journal_entry_create')

                                allocations_data = []
                                total_pct = Decimal('0.00')
                                calc_alloc_func_sum = Decimal('0.00')
                                calc_alloc_foreign_sum = Decimal('0.00')

                                for item in raw_alloc:
                                    c_id = item.get('cost_center_id')
                                    pct = Decimal(str(item.get('percentage', 0)))
                                    raw_amt = Decimal(str(item.get('amount', 0)))

                                    if pct < Decimal('0.00') or raw_amt < Decimal('0.00'):
                                        messages.error(request, f"حظر القيم السالبة: السطر رقم ({idx+1}) يحتوي على نسبة مئوية أو مبلغ سالب.")
                                        return redirect('financial:manual_journal_entry_create')

                                    # المرونة المزدوجة (% أو مبلغ)
                                    if pct > Decimal('0.00') and raw_amt == Decimal('0.00'):
                                        amt_func = (line_amount_func * (pct / Decimal('100'))).quantize(Decimal('0.01'))
                                    elif raw_amt > Decimal('0.00') and pct == Decimal('0.00'):
                                        pct = ((raw_amt / line_amount_func) * Decimal('100')).quantize(Decimal('0.01'))
                                        amt_func = raw_amt.quantize(Decimal('0.01'))
                                    else:
                                        amt_func = (line_amount_func * (pct / Decimal('100'))).quantize(Decimal('0.01'))

                                    total_pct += pct

                                    if entry_currency_code != func_code:
                                        amt_foreign = (line_amount_foreign * (pct / Decimal('100'))).quantize(Decimal('0.01'))
                                    else:
                                        amt_foreign = Decimal('0.00')

                                    calc_alloc_func_sum += amt_func
                                    calc_alloc_foreign_sum += amt_foreign

                                    allocations_data.append({
                                        'cost_center_id': c_id,
                                        'percentage': pct,
                                        'amount': amt_func,
                                        'foreign_amount': amt_foreign
                                    })

                                if abs(total_pct - Decimal('100.00')) > Decimal('0.05') and abs(calc_alloc_func_sum - line_amount_func) > Decimal('0.05'):
                                    messages.error(request, f"إجمالي نسبة التوزيع المحاسبي للسطر رقم ({idx+1}) يجب أن يساوي 100% بالتمام (النسبة الحالية: {total_pct}%).")
                                    return redirect('financial:manual_journal_entry_create')

                                # تسوية فروق التقريب (Penny Difference Adjustment)
                                penny_diff_func = line_amount_func - calc_alloc_func_sum
                                if penny_diff_func != Decimal('0.00') and len(allocations_data) > 0:
                                    allocations_data[-1]['amount'] += penny_diff_func

                                if entry_currency_code != func_code:
                                    penny_diff_foreign = line_amount_foreign - calc_alloc_foreign_sum
                                    if penny_diff_foreign != Decimal('0.00') and len(allocations_data) > 0:
                                        allocations_data[-1]['foreign_amount'] += penny_diff_foreign

                                # Exclusivity Rule: إلغاء cc_code المباشر في حالة وجود توزيع فرعي متعدد
                                cc_code = None
                        except Exception as parse_err:
                            import logging
                            logging.getLogger(__name__).error(f"Error parsing allocations JSON for line {idx}: {parse_err}")

                    total_debit += debit_val
                    total_credit += credit_val

                    lines.append(
                        JournalEntryLineData(
                            account_code=account.code,
                            debit=debit_val,
                            credit=credit_val,
                            description=line_desc,
                            cost_center=cc_code,
                            cost_allocations=allocations_data
                        )
                    )

                if abs(total_debit - total_credit) > Decimal('0.001'):
                    messages.error(request, f"القيد غير متوازن: إجمالي المدين ({total_debit}) لا يساوي إجمالي الدائن ({total_credit})")
                    return redirect('financial:manual_journal_entry_create')

            else:
                # 2. معالجة النموذج الثنائي المباشر (Legacy Fallback)
                amount = Decimal(request.POST.get('amount', 0))
                debit_account_id = request.POST.get('debit_account')
                credit_account_id = request.POST.get('credit_account')

                if not all([amount, debit_account_id, credit_account_id, description, entry_date]):
                    messages.error(request, "جميع الحقول مطلوبة")
                    return redirect('financial:manual_journal_entry_create')

                debit_account = get_object_or_404(ChartOfAccounts, id=debit_account_id, is_active=True)
                credit_account = get_object_or_404(ChartOfAccounts, id=credit_account_id, is_active=True)

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

            entry_date_obj = datetime.strptime(entry_date, '%Y-%m-%d').date()
            timestamp_seconds = int(timezone.now().timestamp())
            unique_id = (timestamp_seconds % 1000000000) + request.user.id
            idempotency_key = f"manual_entry_{request.user.id}_{timestamp_seconds}"

            gateway = AccountingGateway()
            journal_entry = gateway.create_journal_entry(
                source_module='financial',
                source_model='ManualJournalEntry',
                source_id=unique_id,
                lines=lines,
                idempotency_key=idempotency_key,
                user=request.user,
                entry_type='manual',
                description=description,
                reference=f"MANUAL-{timezone.now().strftime('%Y%m%d%H%M%S')}",
                date=entry_date_obj
            )

            # حفظ المرفقات المرفوعة المتعددة
            uploaded_files = request.FILES.getlist('attachments') or request.FILES.getlist('attachment_file') or [f for f in request.FILES.values()]
            if uploaded_files:
                AttachmentBindingService.save_attachments_for_object(
                    uploaded_files,
                    journal_entry,
                    request.user,
                    category_code='JOURNAL_ENTRY',
                    category_name='مرفقات القيود اليومية'
                )

            # ربط المسودات المرفوعة إن وجدت
            draft_tokens = [t.strip() for t in request.POST.getlist('draft_tokens[]') if t and t.strip()]
            if draft_tokens:
                AttachmentBindingService.bind_draft_attachments(draft_tokens, journal_entry, request.user)

            messages.success(request, f"تم إنشاء القيد اليدوي بنجاح - رقم القيد: {journal_entry.number}")
            return redirect('financial:journal_entries_detail', pk=journal_entry.id)

        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creating manual journal entry: {str(e)}", exc_info=True)
            messages.error(request, f"حدث خطأ أثناء إنشاء القيد: {str(e)}")
            return redirect('financial:manual_journal_entry_create')

    # GET request - إعداد البيانات (الحسابات الفرعية القابلة للترحيل فقط is_leaf=True)
    import json
    from financial.models.currency import Currency
    from financial.services.exchange_rate_service import ExchangeRateService

    accounts = ChartOfAccounts.objects.filter(is_active=True, is_leaf=True).select_related('account_type', 'currency').order_by('code')
    cost_centers = CostCenter.objects.filter(is_active=True, children__isnull=True).order_by('code')
    currencies = Currency.objects.filter(is_active=True).order_by('code')
    func_currency = ExchangeRateService.get_functional_currency()
    func_code = func_currency.code if func_currency else 'EGP'

    rates_map = {}
    for c in currencies:
        try:
            r = ExchangeRateService.get_rate(c.code)
            rates_map[c.code] = str(r)
        except Exception:
            rates_map[c.code] = "1.000000"

    accounts_by_type = {}
    for account in accounts:
        type_name = account.account_type.name if account.account_type else "غير مصنف"
        if type_name not in accounts_by_type:
            accounts_by_type[type_name] = []
        accounts_by_type[type_name].append(account)

    context = {
        'accounts': accounts,
        'accounts_by_type': accounts_by_type,
        'cost_centers': cost_centers,
        'currencies': currencies,
        'func_currency': func_currency,
        'func_code': func_code,
        'rates_map_json': json.dumps(rates_map),
        'today': timezone.now().date(),
        'page_title': 'إضافة قيد يدوي مركّب',
        'page_subtitle': 'إدخال قيود محاسبية مركبة ومرفقات ومراكز تكلفة',
        'page_icon': 'fas fa-edit',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الإدارة المالية', 'url': reverse('financial:chart_of_accounts_list'), 'icon': 'fas fa-calculator'},
            {'title': 'القيود اليومية', 'url': reverse('financial:journal_entries_list'), 'icon': 'fas fa-book'},
            {'title': 'إضافة قيد يدوي', 'active': True}
        ]
    }

    return render(request, 'financial/transactions/manual_journal_entry_create.html', context)
