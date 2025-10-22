# financial/views/account_views.py
# عروض دليل الحسابات وإدارة الحسابات وأنواع الحسابات

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


# ============== الدوال المساعدة الأساسية ==============


def get_cash_and_bank_accounts():
    """الحصول على الحسابات النقدية والبنكية من النظام الجديد"""
    try:
        return (
            ChartOfAccounts.objects.filter(is_active=True, is_leaf=True)
            .filter(
                Q(is_cash_account=True)
                | Q(is_bank_account=True)
                | Q(account_type__name__icontains="نقدي")
                | Q(account_type__name__icontains="بنك")
                | Q(account_type__name__icontains="صندوق")
            )
            .order_by("code")
        )
    except Exception:
        # النظام القديم لم يعد متوفراً
        return ChartOfAccounts.objects.none()


def get_all_active_accounts():
    """الحصول على جميع الحسابات النشطة من النظام الجديد"""
    try:
        return ChartOfAccounts.objects.filter(is_active=True, is_leaf=True).order_by(
            "code"
        )
    except Exception:
        # النظام القديم لم يعد متوفراً
        return ChartOfAccounts.objects.none()


def get_accounts_by_category(category):
    """الحصول على الحسابات حسب التصنيف من النظام الجديد"""
    try:
        return ChartOfAccounts.objects.filter(
            is_active=True, is_leaf=True, account_type__category=category
        ).order_by("code")
    except Exception:
        # النظام القديم لم يعد متوفراً
        return ChartOfAccounts.objects.none()


def get_bank_accounts():
    """الحصول على الحسابات البنكية فقط"""
    try:
        return ChartOfAccounts.objects.filter(
            is_active=True, is_leaf=True, is_bank_account=True
        ).order_by("code")
    except Exception:
        # النظام القديم لم يعد متوفراً
        return ChartOfAccounts.objects.none()


def get_next_available_code(prefix=""):
    """الحصول على أول كود متاح"""
    if not ChartOfAccounts:
        return "1000"

    if prefix:
        # البحث عن آخر كود بنفس البادئة
        existing_codes = (
            ChartOfAccounts.objects.filter(code__startswith=prefix)
            .values_list("code", flat=True)
            .order_by("code")
        )

        if not existing_codes:
            return f"{prefix}01"

        # العثور على أول رقم متاح
        for i in range(1, 100):
            code = f"{prefix}{i:02d}"
            if code not in existing_codes:
                return code

    # البحث العام عن كود متاح
    existing_codes = set(ChartOfAccounts.objects.values_list("code", flat=True))

    # البحث في النطاقات المختلفة
    ranges = [
        (1000, 1999),  # الأصول
        (2000, 2999),  # الخصوم
        (3000, 3999),  # حقوق الملكية
        (4000, 4999),  # الإيرادات
        (5000, 5999),  # المصروفات
    ]

    for start, end in ranges:
        for code in range(start, end + 1):
            if str(code) not in existing_codes:
                return str(code)

    return "9999"  # كود احتياطي


# ============== قائمة الخزن والحسابات النقدية ==============

@login_required
def cash_and_bank_accounts_list(request):
    """عرض قائمة الحسابات النقدية والبنكية فقط (الخزن)"""
    # فلترة الحسابات النقدية والبنكية فقط
    try:
        # محاولة استخدام الحقول المحسنة
        accounts = (
            ChartOfAccounts.objects.filter(
                is_active=True, is_leaf=True  # الحسابات الفرعية فقط
            )
            .filter(
                Q(is_cash_account=True)
                | Q(is_bank_account=True)
                | Q(account_type__name__icontains="نقدي")
                | Q(account_type__name__icontains="بنك")
                | Q(account_type__name__icontains="صندوق")
            )
            .order_by("code")
        )

        # اختبار الاستعلام
        list(accounts[:1])  # تنفيذ الاستعلام للتأكد من عدم وجود أخطاء

    except Exception as e:
        # في حالة وجود مشكلة في قاعدة البيانات، استخدم فلترة أساسية
        accounts = (
            ChartOfAccounts.objects.filter(is_active=True, is_leaf=True)
            .filter(
                Q(account_type__name__icontains="نقدي")
                | Q(account_type__name__icontains="بنك")
                | Q(account_type__name__icontains="صندوق")
                | Q(account_type__name__icontains="خزن")
            )
            .order_by("code")
        )

    # حساب الإحصائيات
    try:
        cash_accounts_count = accounts.filter(is_cash_account=True).count()
        bank_accounts_count = accounts.filter(is_bank_account=True).count()
    except Exception:
        # في حالة عدم وجود الحقول، استخدم فلترة بديلة
        cash_accounts_count = accounts.filter(
            account_type__name__icontains="نقدي"
        ).count()
        bank_accounts_count = accounts.filter(
            account_type__name__icontains="بنك"
        ).count()

    # حساب إجمالي الأرصدة من القيود المحاسبية
    total_balance = 0
    for account in accounts:
        try:
            # استخدام القيود المحاسبية فقط لجميع الحسابات
            balance = account.get_balance(include_opening=True)
            total_balance += balance

            # إضافة الرصيد المحسوب للحساب كخاصية مؤقتة للعرض
            account.calculated_balance = balance
            
            # حساب آخر حركة مالية للحساب
            from ..models.journal_entry import JournalEntryLine
            
            # تشخيص: عد الحركات للحساب
            movements_count = JournalEntryLine.objects.filter(account=account).count()
            print(f"Account {account.name} ({account.code}) has {movements_count} movements")
            
            last_movement = JournalEntryLine.objects.filter(
                account=account
            ).order_by('-journal_entry__date').first()
            
            if last_movement:
                account.last_movement_date = last_movement.journal_entry.date
                print(f"Last movement date for {account.name}: {last_movement.journal_entry.date}")
            else:
                account.last_movement_date = None
                print(f"No movements found for {account.name}")

        except Exception as e:
            # في حالة الخطأ، استخدم الرصيد الافتتاحي فقط
            fallback_balance = account.opening_balance or 0
            total_balance += fallback_balance
            account.calculated_balance = fallback_balance
            account.last_movement_date = None

    context = {
        "accounts": accounts,
        "accounts_count": len(accounts),
        "cash_accounts_count": cash_accounts_count,
        "bank_accounts_count": bank_accounts_count,
        "total_balance": total_balance,
        "page_title": "قائمة الخزن والحسابات النقدية",
        "page_icon": "fas fa-money-bill-wave",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "الإدارة المالية", "url": "#", "icon": "fas fa-money-bill-wave"},
            {"title": "قائمة الخزن والحسابات النقدية", "active": True},
        ],
    }
    return render(
        request, "financial/banking/cash_and_bank_accounts_list.html", context
    )


# ============== دليل الحسابات ==============

@login_required
def chart_of_accounts_list(request):
    """عرض قائمة دليل الحسابات بشكل محسّن مع شجرة هرمية تفاعلية"""
    from django.db.models import Sum, Count, Q, Prefetch
    from decimal import Decimal

    if ChartOfAccounts is None:
        accounts = []
        root_accounts = []
        stats = {}
        account_types = []
        tree_data = []
    else:
        # الفلترة والبحث
        account_type_filter = request.GET.get("type")
        search_query = request.GET.get("search")
        view_mode = request.GET.get("view", "tree")  # tree أو flat
        show_inactive = request.GET.get("show_inactive", False)

        # استعلام محسن مع prefetch للأداء
        accounts_query = ChartOfAccounts.objects.select_related(
            "account_type", "parent"
        ).prefetch_related(
            Prefetch(
                "children",
                queryset=ChartOfAccounts.objects.select_related("account_type"),
            )
        )

        # تطبيق الفلاتر
        if not show_inactive:
            accounts_query = accounts_query.filter(is_active=True)

        if account_type_filter:
            accounts_query = accounts_query.filter(
                account_type__code=account_type_filter
            )

        if search_query:
            accounts_query = accounts_query.filter(
                Q(name__icontains=search_query)
                | Q(code__icontains=search_query)
                | Q(name_en__icontains=search_query)
                | Q(account_type__name__icontains=search_query)
            )

        # جلب الحسابات حسب نمط العرض
        if view_mode == "flat":
            root_accounts = accounts_query.order_by("code")
        else:
            # عرض الحسابات الرئيسية فقط (الحسابات الأب الـ5)
            root_accounts = accounts_query.filter(parent=None).order_by("code")

        # جلب أنواع الحسابات للفلترة
        account_types = AccountType.objects.filter(is_active=True).order_by("code")

        # إحصائيات شاملة ومحسنة
        all_accounts = ChartOfAccounts.objects.filter(is_active=True, is_leaf=True)

        # حساب الأرصدة بطريقة محسنة
        def calculate_category_balance(category):
            return sum(
                acc.get_balance() or Decimal("0")
                for acc in all_accounts
                if acc.account_type.category == category
            )

        assets_balance = calculate_category_balance("asset")
        liabilities_balance = calculate_category_balance("liability")
        equity_balance = calculate_category_balance("equity")
        revenue_balance = calculate_category_balance("revenue")
        expense_balance = calculate_category_balance("expense")

        # بناء بيانات الشجرة للعرض التفاعلي
        def build_tree_data(account, level=0):
            """بناء بيانات الشجرة بشكل تكراري"""
            balance = account.get_balance() or Decimal("0")
            children_data = []

            # جلب الأطفال النشطة فقط (إلا إذا كان العرض يشمل غير النشطة)
            children_query = account.children.all()
            if not show_inactive:
                children_query = children_query.filter(is_active=True)

            for child in children_query.order_by("code"):
                children_data.append(build_tree_data(child, level + 1))

            return {
                "id": account.id,
                "code": account.code,
                "name": account.name,
                "account_type": account.account_type.name,
                "category": account.account_type.category,
                "nature": account.account_type.nature,
                "balance": float(balance),
                "balance_formatted": f"{balance:,.2f}",
                "is_leaf": account.is_leaf,
                "is_active": account.is_active,
                "is_cash": account.is_cash_account,
                "is_bank": account.is_bank_account,
                "level": level,
                "has_children": len(children_data) > 0,
                "children": children_data,
                "url_detail": f"/financial/accounts/{account.id}/",
                "url_edit": f"/financial/accounts/{account.id}/edit/",
            }

        # بناء بيانات الشجرة
        tree_data = []
        for root_account in root_accounts:
            tree_data.append(build_tree_data(root_account))

        # حساب إجمالي النقدية
        cash_balance = sum(
            acc.get_balance() or Decimal("0")
            for acc in all_accounts
            if (acc.is_cash_account or acc.is_bank_account) and acc.is_leaf
        )

        stats = {
            "total": ChartOfAccounts.objects.count(),
            "active": ChartOfAccounts.objects.filter(is_active=True).count(),
            "inactive": ChartOfAccounts.objects.filter(is_active=False).count(),
            "leaf": ChartOfAccounts.objects.filter(is_leaf=True).count(),
            "parent": ChartOfAccounts.objects.filter(is_leaf=False).count(),
            "cash": ChartOfAccounts.objects.filter(is_cash_account=True).count(),
            "bank": ChartOfAccounts.objects.filter(is_bank_account=True).count(),
            # أرصدة حسب التصنيف
            "assets_balance": assets_balance,
            "liabilities_balance": liabilities_balance,
            "equity_balance": equity_balance,
            "revenue_balance": revenue_balance,
            "expense_balance": expense_balance,
            "net_assets": assets_balance - liabilities_balance,
            "cash_balance": cash_balance,
        }

        # إحصائيات حسب النوع
        type_stats = []
        for acc_type in AccountType.objects.filter(is_active=True).order_by(
            "category", "code"
        ):
            count = all_accounts.filter(account_type=acc_type).count()
            if count > 0:
                type_stats.append(
                    {
                        "type": acc_type,
                        "count": count,
                    }
                )

        stats["by_type"] = type_stats
        accounts = all_accounts.order_by("code")

    # أنواع الحسابات للفلترة
    account_types = AccountType.objects.filter(is_active=True).order_by(
        "category", "code"
    )

    context = {
        "accounts": accounts if "accounts" in locals() else [],
        "root_accounts": root_accounts,
        "account_types": account_types if "account_types" in locals() else [],
        "tree_data": tree_data if "tree_data" in locals() else [],
        "stats": stats if "stats" in locals() else {},
        "selected_type": account_type_filter,
        "search_query": search_query,
        "view_mode": view_mode if "view_mode" in locals() else "tree",
        "show_inactive": show_inactive,
        "page_title": "دليل الحسابات",
        "page_icon": "fas fa-sitemap",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "النظام المحاسبي", "url": "#", "icon": "fas fa-calculator"},
            {"title": "دليل الحسابات", "active": True},
        ],
    }
    return render(request, "financial/accounts/chart_of_accounts_list.html", context)


@login_required
def chart_tree_api(request):
    """API لجلب بيانات الشجرة الهرمية بشكل ديناميكي"""
    from django.http import JsonResponse
    from decimal import Decimal

    try:
        account_id = request.GET.get("account_id")
        expand_all = request.GET.get("expand_all", "false").lower() == "true"

        if account_id:
            # جلب حساب معين مع أطفاله
            account = get_object_or_404(ChartOfAccounts, id=account_id)
            children = account.children.filter(is_active=True).order_by("code")

            tree_data = []
            for child in children:
                balance = child.get_balance() or Decimal("0")
                tree_data.append(
                    {
                        "id": child.id,
                        "code": child.code,
                        "name": child.name,
                        "account_type": child.account_type.name,
                        "balance": float(balance),
                        "balance_formatted": f"{balance:,.2f}",
                        "is_leaf": child.is_leaf,
                        "is_active": child.is_active,
                        "is_cash": child.is_cash_account,
                        "is_bank": child.is_bank_account,
                        "has_children": child.children.filter(is_active=True).exists(),
                        "url_detail": f"/financial/accounts/{child.id}/",
                        "url_edit": f"/financial/accounts/{child.id}/edit/",
                    }
                )
        else:
            # جلب الشجرة الكاملة أو الجذور فقط
            if expand_all:
                # بناء الشجرة الكاملة
                def build_full_tree(account, level=0):
                    balance = account.get_balance() or Decimal("0")
                    children_data = []

                    for child in account.children.filter(is_active=True).order_by(
                        "code"
                    ):
                        children_data.append(build_full_tree(child, level + 1))

                    return {
                        "id": account.id,
                        "code": account.code,
                        "name": account.name,
                        "account_type": account.account_type.name,
                        "balance": float(balance),
                        "balance_formatted": f"{balance:,.2f}",
                        "is_leaf": account.is_leaf,
                        "is_active": account.is_active,
                        "is_cash": account.is_cash_account,
                        "is_bank": account.is_bank_account,
                        "level": level,
                        "has_children": len(children_data) > 0,
                        "children": children_data,
                        "expanded": True,
                        "url_detail": f"/financial/accounts/{account.id}/",
                        "url_edit": f"/financial/accounts/{account.id}/edit/",
                    }

                root_accounts = ChartOfAccounts.objects.filter(
                    parent=None, is_active=True
                ).order_by("code")

                tree_data = [build_full_tree(account) for account in root_accounts]
            else:
                # جلب الجذور فقط
                root_accounts = ChartOfAccounts.objects.filter(
                    parent=None, is_active=True
                ).order_by("code")

                tree_data = []
                for account in root_accounts:
                    balance = account.get_balance() or Decimal("0")
                    tree_data.append(
                        {
                            "id": account.id,
                            "code": account.code,
                            "name": account.name,
                            "account_type": account.account_type.name,
                            "balance": float(balance),
                            "balance_formatted": f"{balance:,.2f}",
                            "is_leaf": account.is_leaf,
                            "is_active": account.is_active,
                            "is_cash": account.is_cash_account,
                            "is_bank": account.is_bank_account,
                            "has_children": account.children.filter(
                                is_active=True
                            ).exists(),
                            "expanded": False,
                            "url_detail": f"/financial/accounts/{account.id}/",
                            "url_edit": f"/financial/accounts/{account.id}/edit/",
                        }
                    )

        return JsonResponse(
            {"success": True, "data": tree_data, "count": len(tree_data)}
        )

    except Exception as e:
        return JsonResponse({"success": False, "error": "خطأ في العملية"}, status=400)


@login_required
def chart_of_accounts_create(request):
    """إنشاء حساب جديد في دليل الحسابات"""
    if request.method == "POST":
        try:
            # التحقق من توفر الكود
            code = request.POST.get("code", "").strip()
            if ChartOfAccounts and ChartOfAccounts.objects.filter(code=code).exists():
                messages.error(
                    request, f"كود الحساب {code} موجود مسبقاً. يرجى استخدام كود آخر."
                )
                # اقتراح كود بديل
                suggested_code = get_next_available_code()
                messages.info(request, f"كود مقترح متاح: {suggested_code}")

                # إعادة تحميل الصفحة مع البيانات
                context = {
                    "account_types": AccountType.objects.all() if AccountType else [],
                    "parent_accounts": ChartOfAccounts.objects.filter(is_active=True)
                    if ChartOfAccounts
                    else [],
                    "suggested_code": suggested_code,
                    "form_data": request.POST,
                    "page_title": "إنشاء حساب جديد",
                    "page_icon": "fas fa-plus",
                    "breadcrumb_items": [
                        {
                            "title": "الرئيسية",
                            "url": reverse("core:dashboard"),
                            "icon": "fas fa-home",
                        },
                        {
                            "title": "دليل الحسابات",
                            "url": reverse("financial:chart_of_accounts_list"),
                            "icon": "fas fa-sitemap",
                        },
                        {"title": "إنشاء حساب جديد", "active": True},
                    ],
                }
                return render(
                    request, "financial/accounts/chart_of_accounts_form.html", context
                )

            # إنشاء حساب جديد
            account = ChartOfAccounts()

            # تحديث البيانات الأساسية
            account.code = code
            account.name = request.POST.get("name", "").strip()
            account.name_en = request.POST.get("name_en", "").strip()

            # تحديث نوع الحساب
            account_type_id = request.POST.get("account_type")
            if account_type_id and AccountType:
                account.account_type = AccountType.objects.get(id=account_type_id)

            # تحديث الحساب الأب
            parent_id = request.POST.get("parent")
            if parent_id:
                account.parent = ChartOfAccounts.objects.get(id=parent_id)

            # تحديث الرصيد الافتتاحي
            opening_balance = request.POST.get("opening_balance", "0")
            try:
                account.opening_balance = (
                    float(opening_balance) if opening_balance else 0.00
                )
            except (ValueError, TypeError):
                account.opening_balance = 0.00

            # تحديث تاريخ الرصيد الافتتاحي
            opening_balance_date = request.POST.get("opening_balance_date")
            if opening_balance_date:
                from datetime import datetime

                account.opening_balance_date = datetime.strptime(
                    opening_balance_date, "%Y-%m-%d"
                ).date()

            # تحديث الخصائص
            account.is_leaf = "is_leaf" in request.POST
            account.is_bank_account = "is_bank_account" in request.POST
            account.is_cash_account = "is_cash_account" in request.POST
            account.is_reconcilable = "is_reconcilable" in request.POST
            account.is_control_account = "is_control_account" in request.POST
            account.is_active = "is_active" in request.POST

            # تحديث المعلومات الإضافية
            account.description = request.POST.get("description", "").strip()
            account.notes = request.POST.get("notes", "").strip()

            # تعيين المستخدم الحالي
            account.created_by = request.user

            # حفظ الحساب الجديد
            account.save()

            messages.success(request, f'تم إنشاء الحساب "{account.name}" بنجاح.')
            return redirect("financial:account_detail", pk=account.pk)

        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء إنشاء الحساب: {str(e)}")

    # تحميل أنواع الحسابات للنموذج
    account_types = []
    if AccountType:
        account_types = AccountType.objects.filter(is_active=True).order_by("code")

    # تحميل الحسابات الأب المحتملة
    parent_accounts = []
    if ChartOfAccounts:
        parent_accounts = ChartOfAccounts.objects.filter(is_active=True).order_by(
            "code"
        )

    # اقتراح كود متاح
    suggested_code = get_next_available_code()

    context = {
        "account_types": account_types,
        "parent_accounts": parent_accounts,
        "suggested_code": suggested_code,
        "page_title": "إضافة حساب جديد",
        "page_icon": "fas fa-plus-circle",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "النظام المحاسبي", "url": "#", "icon": "fas fa-calculator"},
            {
                "title": "دليل الحسابات",
                "url": reverse("financial:account_list"),
                "icon": "fas fa-sitemap",
            },
            {"title": "إضافة حساب جديد", "active": True},
        ],
    }
    return render(request, "financial/accounts/chart_of_accounts_form.html", context)


@login_required
def chart_of_accounts_detail(request, pk):
    """عرض تفاصيل حساب مع الحركات للحسابات النقدية"""
    if ChartOfAccounts is None:
        messages.error(request, "نموذج دليل الحسابات غير متاح.")
        return redirect("financial:chart_of_accounts_list")

    account = get_object_or_404(ChartOfAccounts, pk=pk)

    # متغيرات الحركات
    movements = []
    filter_form = None
    balance_summary = None

    # إنشاء ملخص رصيد أساسي لجميع الحسابات
    balance_summary = {
        "opening_balance": account.opening_balance or 0,
        "total_in": 0,
        "total_out": 0,
        "current_balance": account.opening_balance or 0,
    }

    # محاولة جلب البيانات من القيود المحاسبية أولاً (الأكثر استقراراً)
    try:
        # جلب جميع القيود (مرحلة وغير مرحلة)
        all_lines = JournalEntryLine.objects.filter(account=account)
        total_debit_all = all_lines.aggregate(Sum("debit"))["debit__sum"] or 0
        total_credit_all = all_lines.aggregate(Sum("credit"))["credit__sum"] or 0

        # جلب القيود المرحلة فقط للرصيد المعتمد
        posted_lines = all_lines.filter(journal_entry__status="posted")
        total_debit_posted = posted_lines.aggregate(Sum("debit"))["debit__sum"] or 0
        total_credit_posted = posted_lines.aggregate(Sum("credit"))["credit__sum"] or 0

        # حساب الرصيد حسب طبيعة الحساب
        if account.nature == "debit":  # حسابات مدينة
            # للحسابات المدينة: الرصيد = الافتتاحي + المدين - الدائن
            total_balance = (
                (account.opening_balance or 0) + total_debit_all - total_credit_all
            )
            approved_balance_calc = (
                (account.opening_balance or 0)
                + total_debit_posted
                - total_credit_posted
            )
        else:  # حسابات دائنة
            # للحسابات الدائنة: الرصيد = الافتتاحي + الدائن - المدين
            total_balance = (
                (account.opening_balance or 0) + total_credit_all - total_debit_all
            )
            approved_balance_calc = (
                (account.opening_balance or 0)
                + total_credit_posted
                - total_debit_posted
            )

        # حساب الرصيد المعتمد (القيود المرحلة فقط)
        try:
            approved_balance = account.get_balance(include_opening=True)
        except Exception:
            approved_balance = approved_balance_calc

        # تحديد الوارد والصادر حسب طبيعة الحساب
        if account.nature == "debit":  # حسابات مدينة (أصول، مصروفات)
            # للحسابات المدينة: المدين = وارد، الدائن = صادر
            total_in_all = total_debit_all
            total_out_all = total_credit_all
            total_in_posted = total_debit_posted
            total_out_posted = total_credit_posted
        else:  # حسابات دائنة (خصوم، حقوق ملكية، إيرادات)
            # للحسابات الدائنة: الدائن = وارد، المدين = صادر
            total_in_all = total_credit_all
            total_out_all = total_debit_all
            total_in_posted = total_credit_posted
            total_out_posted = total_debit_posted

        # تحديث ملخص الرصيد مع إظهار الفرق
        balance_summary = {
            "opening_balance": account.opening_balance or 0,
            "total_in": total_in_all,
            "total_out": total_out_all,
            "total_in_posted": total_in_posted,
            "total_out_posted": total_out_posted,
            "current_balance": total_balance,  # الرصيد الإجمالي
            "approved_balance": approved_balance,  # الرصيد المعتمد
            "pending_amount": total_balance - approved_balance,  # المبلغ المعلق
            # قيم تشخيصية
            "total_debit_all": total_debit_all,
            "total_credit_all": total_credit_all,
            "total_debit_posted": total_debit_posted,
            "total_credit_posted": total_credit_posted,
        }

        # جلب آخر 50 قيد محاسبي كحركات (مع حالة الترحيل)
        journal_lines = (
            JournalEntryLine.objects.filter(account=account)
            .select_related("journal_entry")
            .order_by("-journal_entry__date", "-id")[:50]
        )
        movements = journal_lines

    except Exception as e:
        movements = []

    # يمكن عرض معلومات إضافية للحسابات النقدية/البنكية لاحقاً

    # تحميل أنواع الحسابات للنموذج
    account_types = []
    if AccountType:
        account_types = AccountType.objects.filter(is_active=True).order_by("code")

    # تحميل الحسابات الأب المحتملة (تجنب الحساب الحالي وأطفاله)
    parent_accounts = []
    if ChartOfAccounts:
        # الحصول على جميع أطفال الحساب الحالي لتجنبها
        children_ids = [child.id for child in account.get_children_recursive()]
        children_ids.append(account.id)  # تجنب الحساب نفسه

        parent_accounts = (
            ChartOfAccounts.objects.filter(is_active=True)
            .exclude(id__in=children_ids)
            .order_by("code")
        )

    # إضافة المتغيرات المطلوبة للقالب الجديد
    transactions = movements  # نفس البيانات بس اسم مختلف

    # حساب التحليلات
    analytics = {
        "current_balance": balance_summary.get("current_balance", 0),
        "previous_balance": balance_summary.get("opening_balance", 0),
        "balance_change": balance_summary.get("current_balance", 0)
        - balance_summary.get("opening_balance", 0),
        "total_debit": balance_summary.get("total_debit_all", 0),
        "total_credit": balance_summary.get("total_credit_all", 0),
        "transaction_count": len(movements),
        "accounts_included": 1,
        "period_days": 30,
        "avg_daily_transactions": len(movements) / 30 if len(movements) > 0 else 0,
        "trend": "positive"
        if balance_summary.get("current_balance", 0)
        > balance_summary.get("opening_balance", 0)
        else "negative",
        "trend_icon": "fa-arrow-up"
        if balance_summary.get("current_balance", 0)
        > balance_summary.get("opening_balance", 0)
        else "fa-arrow-down",
        "trend_color": "success"
        if balance_summary.get("current_balance", 0)
        > balance_summary.get("opening_balance", 0)
        else "danger",
    }

    # الحسابات الفرعية
    sub_accounts = (
        account.children.filter(is_active=True).order_by("code")
        if not account.is_leaf
        else []
    )

    # إحصائيات إضافية
    income_sum = balance_summary.get("total_credit_all", 0)
    expense_sum = balance_summary.get("total_debit_all", 0)

    context = {
        "account": account,
        "movements": movements,
        "transactions": transactions,  # للقالب الجديد
        "analytics": analytics,  # للقالب الجديد
        "sub_accounts": sub_accounts,  # للقالب الجديد
        "income_sum": income_sum,  # للقالب الجديد
        "expense_sum": expense_sum,  # للقالب الجديد
        "balance_summary": balance_summary,
        "is_cash_account": account.is_cash_account or account.is_bank_account,
        "page_title": f"تفاصيل حساب: {account.name}",
        "page_icon": "fas fa-file-invoice-dollar",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "النظام المحاسبي", "url": "#", "icon": "fas fa-calculator"},
            {
                "title": "دليل الحسابات",
                "url": reverse("financial:chart_of_accounts_list"),
                "icon": "fas fa-sitemap",
            },
            {"title": f"{account.name}", "active": True},
        ],
    }
    return render(request, "financial/accounts/chart_of_accounts_detail.html", context)


@login_required
def chart_of_accounts_delete(request, pk):
    """حذف حساب"""
    account = get_object_or_404(ChartOfAccounts, pk=pk)
    if request.method == "POST":
        account.is_active = False
        account.save()
        messages.success(request, f'تم حذف الحساب "{account.name}" بنجاح.')
        return redirect("financial:chart_of_accounts_list")

    context = {
        "account": account,
        "page_title": f"حذف حساب: {account.name}",
        "page_icon": "fas fa-trash",
    }
    return render(request, "financial/accounts/chart_of_accounts_delete.html", context)


# ============== أنواع الحسابات ==============

@login_required
def account_types_list(request):
    """عرض قائمة أنواع الحسابات بشكل هرمي مع جميع المستويات"""

    def build_tree_structure(parent=None, level=0):
        """بناء الهيكل الهرمي للأنواع"""
        types = AccountType.objects.filter(parent=parent).order_by("code")
        tree_data = []

        for account_type in types:
            # عدد الحسابات المرتبطة بهذا النوع
            accounts_count = 0
            if ChartOfAccounts:
                accounts_count = ChartOfAccounts.objects.filter(
                    account_type=account_type
                ).count()

            # عدد الأنواع الفرعية
            children_count = AccountType.objects.filter(parent=account_type).count()

            type_data = {
                "type": account_type,
                "level": level,
                "accounts_count": accounts_count,
                "children_count": children_count,
                "has_children": children_count > 0,
                "children": [],
            }

            # إضافة الأطفال بشكل تكراري
            if children_count > 0:
                type_data["children"] = build_tree_structure(account_type, level + 1)

            tree_data.append(type_data)

        return tree_data

    # بناء الشجرة كاملة
    tree_structure = build_tree_structure()

    # جلب جميع الأنواع للإحصائيات
    all_types = AccountType.objects.all()
    root_types = AccountType.objects.filter(parent=None)

    # إحصائيات شاملة
    total_types = all_types.count()
    root_count = root_types.count()
    child_count = AccountType.objects.exclude(parent=None).count()

    # إحصائيات النشطة فقط
    active_types = all_types.filter(is_active=True).count()
    inactive_types = total_types - active_types

    # إحصائيات حسب التصنيف
    category_stats = {}
    for category in ["asset", "liability", "equity", "revenue", "expense"]:
        category_stats[category] = all_types.filter(category=category).count()

    # إحصائيات حسب المستوى
    level_stats = {}
    for level in range(1, 6):  # حتى 5 مستويات
        level_stats[level] = all_types.filter(level=level).count()

    context = {
        "tree_structure": tree_structure,
        "all_types": all_types,  # لعرض جدول مسطح إضافي إذا لزم الأمر
        "total_types": total_types,
        "root_count": root_count,
        "child_count": child_count,
        "active_types": active_types,
        "inactive_types": inactive_types,
        "category_stats": category_stats,
        "level_stats": level_stats,
        "page_title": "أنواع الحسابات",
        "page_icon": "fas fa-layer-group",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "الإدارة المالية", "url": "#", "icon": "fas fa-money-bill-wave"},
            {"title": "أنواع الحسابات", "active": True},
        ],
    }
    return render(request, "financial/accounts/account_types_list.html", context)


@login_required
def account_types_detail(request, pk):
    """عرض تفاصيل نوع حساب"""
    account_type = get_object_or_404(AccountType, pk=pk)
    
    # جلب الحسابات المرتبطة بهذا النوع
    related_accounts = []
    if ChartOfAccounts:
        related_accounts = ChartOfAccounts.objects.filter(
            account_type=account_type,
            is_active=True
        ).order_by("code")
    
    # جلب الأنواع الفرعية
    child_types = AccountType.objects.filter(parent=account_type).order_by("code")
    
    # إحصائيات
    accounts_count = len(related_accounts)
    children_count = child_types.count()
    
    context = {
        "account_type": account_type,
        "related_accounts": related_accounts,
        "child_types": child_types,
        "accounts_count": accounts_count,
        "children_count": children_count,
        "page_title": f"تفاصيل نوع الحساب: {account_type.name}",
        "page_icon": "fas fa-info-circle",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "الإدارة المالية", "url": "#", "icon": "fas fa-money-bill-wave"},
            {
                "title": "أنواع الحسابات",
                "url": reverse("financial:account_types_list"),
                "icon": "fas fa-layer-group",
            },
            {"title": account_type.name, "active": True},
        ],
    }
    return render(request, "financial/accounts/account_types_detail.html", context)


@login_required
def account_types_create(request):
    """إنشاء نوع حساب جديد"""
    if request.method == "POST":
        try:
            # إنشاء نوع حساب جديد
            account_type = AccountType()

            # تحديث البيانات الأساسية
            account_type.code = request.POST.get("code", "").strip().upper()
            account_type.name = request.POST.get("name", "").strip()
            account_type.category = request.POST.get("category", "").strip()
            account_type.nature = request.POST.get("nature", "").strip()

            # تحديث النوع الأب
            parent_id = request.POST.get("parent")
            if parent_id:
                account_type.parent = AccountType.objects.get(id=parent_id)
                account_type.level = account_type.parent.level + 1
            else:
                account_type.level = 1

            # تحديث الحالة
            account_type.is_active = "is_active" in request.POST

            # تعيين المستخدم الحالي
            account_type.created_by = request.user

            # حفظ نوع الحساب الجديد
            account_type.save()

            messages.success(
                request, f'تم إنشاء نوع الحساب "{account_type.name}" بنجاح.'
            )
            return redirect("financial:account_types_list")

        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء إنشاء نوع الحساب: {str(e)}")

    # تحميل الأنواع الأب المحتملة
    parent_types = []
    if AccountType:
        parent_types = AccountType.objects.filter(is_active=True).order_by("code")

    context = {
        "parent_types": parent_types,
        "page_title": "إضافة نوع حساب جديد",
        "page_icon": "fas fa-plus-circle",
    }
    return render(request, "financial/accounts/account_types_form.html", context)


@login_required
def account_types_edit(request, pk):
    """تعديل نوع حساب"""
    account_type = get_object_or_404(AccountType, pk=pk)

    if request.method == "POST":
        try:
            # تحديث البيانات الأساسية
            account_type.code = request.POST.get("code", "").strip().upper()
            account_type.name = request.POST.get("name", "").strip()
            account_type.category = request.POST.get("category", "").strip()
            account_type.nature = request.POST.get("nature", "").strip()

            # تحديث النوع الأب
            parent_id = request.POST.get("parent")
            if parent_id:
                parent = AccountType.objects.get(id=parent_id)
                # التأكد من عدم إنشاء حلقة مفرغة
                # التحقق البسيط: الأب لا يمكن أن يكون النوع نفسه أو أحد أطفاله
                if parent != account_type:
                    # التحقق من أن الأب ليس طفل للنوع الحالي
                    is_valid = True
                    temp_parent = parent
                    while temp_parent:
                        if temp_parent == account_type:
                            is_valid = False
                            break
                        temp_parent = temp_parent.parent

                    if is_valid:
                        account_type.parent = parent
                        account_type.level = parent.level + 1
                    else:
                        messages.warning(
                            request, "لا يمكن جعل النوع أباً لنفسه أو لأحد أجداده"
                        )
            else:
                account_type.parent = None
                account_type.level = 1

            # تحديث الحالة
            account_type.is_active = "is_active" in request.POST

            # حفظ التغييرات
            account_type.save()

            messages.success(
                request, f'تم تحديث نوع الحساب "{account_type.name}" بنجاح.'
            )
            return redirect("financial:account_types_list")

        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء تحديث نوع الحساب: {str(e)}")

    # تحميل الأنواع الأب المحتملة (تجنب النوع الحالي وأطفاله)
    parent_types = []
    if AccountType:
        parent_types = (
            AccountType.objects.filter(is_active=True)
            .exclude(id=account_type.id)
            .order_by("code")
        )
        # يمكن إضافة منطق لتجنب الأطفال أيضاً

    context = {
        "account_type": account_type,
        "parent_types": parent_types,
        "page_title": f"تعديل نوع حساب: {account_type.name}",
        "page_icon": "fas fa-edit",
    }
    return render(request, "financial/accounts/account_types_form.html", context)


@login_required
def account_types_delete(request, pk):
    """حذف نوع حساب"""
    account_type = get_object_or_404(AccountType, pk=pk)
    if request.method == "POST":
        account_type.is_active = False
        account_type.save()
        messages.success(request, f'تم حذف نوع الحساب "{account_type.name}" بنجاح.')
        return redirect("financial:account_types_list")

    context = {
        "page_title": f"حذف نوع حساب: {account_type.name}",
        "page_icon": "fas fa-times-circle",
    }
    return render(request, "financial/accounts/account_types_delete.html", context)


@login_required
def account_list(request):
    """
    عرض قائمة الحسابات المالية
    """
    accounts = get_all_active_accounts()

    # إحصائيات من النظام الجديد
    total_assets = (
        accounts.filter(opening_balance__gt=0)
        .aggregate(Sum("opening_balance"))
        .get("opening_balance__sum", 0)
        or 0
    )
    # total_income = 0  # سيتم حسابها من القيود المحاسبية لاحقاً
    # total_expenses = 0  # سيتم حسابها من القيود المحاسبية لاحقاً
    total_income = 0
    total_expenses = 0

    context = {
        "accounts": accounts,
        "total_assets": total_assets,
        "total_income": total_income,
        "total_expenses": total_expenses,
        "page_title": "الحسابات المالية",
        "page_icon": "fas fa-landmark",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "الإدارة المالية", "url": "#", "icon": "fas fa-money-bill-wave"},
            {"title": "الحسابات المالية", "active": True},
        ],
    }

    return render(request, "financial/accounts/account_list.html", context)


def get_account_transactions(account, limit=50, transaction_type="all"):
    """
    جلب حركات الحساب بطريقة ذكية حسب نوع الحساب
    """
    transactions = []

    if account.is_leaf:
        # جلب جميع القيود للحساب النهائي
        all_journal_lines = JournalEntryLine.objects.filter(account=account)

        # جلب جميع القيود بغض النظر عن الحالة
        transactions = list(
            all_journal_lines.select_related("journal_entry").order_by(
                "-journal_entry__date", "-id"
            )[:limit]
        )

        # إضافة حركات الخزن إذا كان حساب نقدي/بنكي (تم إزالة CashMovement)
        if account.is_cash_account or account.is_bank_account:
            try:
                # البحث في القيود المحاسبية المرتبطة بالحساب
                from ..models.journal_entry import JournalEntry

                journal_entries = (
                    JournalEntry.objects.filter(lines__account=account, status="posted")
                    .distinct()
                    .order_by("-date")[: limit // 2]
                )

                # دمج الحركات (سيتم تطويرها لاحقاً)
                # transactions = merge_transactions(journal_lines, cash_movements)
            except ImportError:
                pass

    else:
        # حساب أب: جلب حركات جميع الأحفاد النهائيين
        leaf_accounts = account.get_leaf_descendants(include_self=True)

        if leaf_accounts:
            # جلب جميع القيود للأحفاد
            all_lines = JournalEntryLine.objects.filter(account__in=leaf_accounts)

            # جلب جميع القيود بغض النظر عن الحالة
            transactions = list(
                all_lines.select_related("journal_entry", "account").order_by(
                    "-journal_entry__date", "-id"
                )[:limit]
            )

    return transactions


def get_account_analytics(account, period_days=30):
    """
    تحليلات متقدمة للحساب
    """
    from datetime import datetime, timedelta
    from decimal import Decimal

    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=period_days)

    # جلب ملخص المعاملات
    summary = account.get_transactions_summary(date_from=start_date, date_to=end_date)

    # حساب الرصيد الحالي
    current_balance = account.get_balance()

    # حساب الرصيد في بداية الفترة
    previous_balance = account.get_balance(date_to=start_date)

    analytics = {
        "current_balance": current_balance,
        "previous_balance": previous_balance,
        "balance_change": current_balance - previous_balance,
        "total_debit": summary["total_debit"],
        "total_credit": summary["total_credit"],
        "transaction_count": summary["transaction_count"],
        "accounts_included": summary["accounts_included"],
        "period_days": period_days,
        "avg_daily_transactions": summary["transaction_count"] / period_days
        if period_days > 0
        else 0,
    }

    # تحديد اتجاه التغيير
    if analytics["balance_change"] > 0:
        analytics["trend"] = "positive"
        analytics["trend_icon"] = "fa-arrow-up"
        analytics["trend_color"] = "success"
    elif analytics["balance_change"] < 0:
        analytics["trend"] = "negative"
        analytics["trend_icon"] = "fa-arrow-down"
        analytics["trend_color"] = "danger"
    else:
        analytics["trend"] = "stable"
        analytics["trend_icon"] = "fa-minus"
        analytics["trend_color"] = "secondary"

    return analytics


@login_required
def account_detail(request, pk):
    """
    عرض تفاصيل حساب مالي محدد - محسن ومطور
    """
    account = get_object_or_404(ChartOfAccounts, pk=pk)

    # جلب المعاملات بالطريقة الذكية الجديدة
    transactions = get_account_transactions(account, limit=20)

    # جلب التحليلات المتقدمة
    analytics = get_account_analytics(account, period_days=30)

    # إحصائيات إضافية للعرض
    try:
        # إحصائيات الحساب من القيود المحاسبية
        if account.is_leaf:
            all_lines = JournalEntryLine.objects.filter(
                account=account, journal_entry__status="posted"
            )
        else:
            leaf_accounts = account.get_leaf_descendants(include_self=True)
            all_lines = JournalEntryLine.objects.filter(
                account__in=leaf_accounts, journal_entry__status="posted"
            )

        income_sum = all_lines.aggregate(Sum("credit")).get("credit__sum", 0) or 0
        expense_sum = all_lines.aggregate(Sum("debit")).get("debit__sum", 0) or 0
    except Exception:
        income_sum = 0
        expense_sum = 0

    # تعريف رؤوس الأعمدة للجدول الموحد
    transaction_headers = [
        {
            "key": "transaction_type",
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
            "key": "reference_number",
            "label": "المرجع",
            "sortable": False,
            "format": "reference",
            "class": "text-center",
            "width": "10%",
        },
    ]

    # تعريف أزرار الإجراءات
    transaction_actions = [
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
    ]

    # معلومات إضافية للحسابات الأب
    sub_accounts = []
    if not account.is_leaf:
        sub_accounts = account.children.filter(is_active=True).order_by("code")

    context = {
        "account": account,
        "transactions": transactions,
        "analytics": analytics,
        "income_sum": income_sum,
        "expense_sum": expense_sum,
        "sub_accounts": sub_accounts,
        "title": f"حساب: {account.name}",
        "transaction_headers": transaction_headers,
        "transaction_actions": transaction_actions,
        "page_title": f"تفاصيل الحساب - {account.name}",
        "page_icon": "fas fa-file-invoice-dollar",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "النظام المحاسبي", "url": "#", "icon": "fas fa-calculator"},
            {
                "title": "دليل الحسابات",
                "url": reverse("financial:chart_of_accounts_list"),
                "icon": "fas fa-sitemap",
            },
            {"title": account.name, "active": True},
        ],
    }

    return render(request, "financial/accounts/chart_of_accounts_detail.html", context)


@login_required
def account_create(request):
    """
    إنشاء حساب مالي جديد
    """
    if request.method == "POST":
        form = AccountForm(request.POST)
        if form.is_valid():
            account = form.save(commit=False)
            account.created_by = request.user

            # التعامل مع الرصيد الافتتاحي
            initial_balance = form.cleaned_data.get("initial_balance", 0)
            account.balance = initial_balance

            account.save()

            # إنشاء معاملة افتتاحية إذا كان الرصيد الافتتاحي موجودًا
            if initial_balance > 0:
                transaction = Transaction.objects.create(
                    account=account,
                    transaction_type="income",
                    amount=initial_balance,
                    date=timezone.now().date(),
                    description=f"رصيد افتتاحي - {account.name}",
                    reference=f"INIT-{account.code}",
                    created_by=request.user,
                )

                # إنشاء بنود القيد المحاسبي
                TransactionLine.objects.create(
                    transaction=transaction,
                    account=account,
                    debit=initial_balance,
                    credit=0,
                    description="رصيد افتتاحي",
                )

                # حساب رأس المال أو الأصول
                capital_account = get_accounts_by_category("equity").first()
                if not capital_account:
                    # يجب إنشاء حساب رأس المال في النظام الجديد
                    messages.warning(
                        request, "يجب إنشاء حساب رأس المال في دليل الحسابات أولاً"
                    )
                    return redirect(
                        reverse("financial:account_create") + "?category=equity"
                    )

                TransactionLine.objects.create(
                    transaction=transaction,
                    account=capital_account,
                    debit=0,
                    credit=initial_balance,
                    description="رصيد افتتاحي",
                )

            messages.success(request, f'تم إنشاء الحساب "{account.name}" بنجاح.')
            return redirect("financial:account_detail", pk=account.pk)
    else:
        form = AccountForm()

    context = {
        "form": form,
        "title": "إنشاء حساب جديد",
    }

    return render(request, "financial/accounts/account_form.html", context)


@login_required
def account_edit(request, pk):
    """
    تعديل حساب مالي - استخدام النظام الجديد
    """
    account = get_object_or_404(ChartOfAccounts, pk=pk)

    if request.method == "POST":
        try:
            # تحديث بيانات الحساب
            account.name = request.POST.get("name")
            account.code = request.POST.get("code")
            account.description = request.POST.get("description", "")

            # تحديث نوع الحساب
            account_type_id = request.POST.get("account_type")
            if account_type_id:
                account.account_type = AccountType.objects.get(id=account_type_id)

            # تحديث الحساب الأب
            parent_id = request.POST.get("parent")
            if parent_id:
                account.parent = ChartOfAccounts.objects.get(id=parent_id)
            else:
                account.parent = None

            # تحديث الرصيد الافتتاحي
            opening_balance = request.POST.get("opening_balance")
            if opening_balance:
                account.opening_balance = Decimal(opening_balance)

            opening_balance_date = request.POST.get("opening_balance_date")
            if opening_balance_date:
                account.opening_balance_date = opening_balance_date

            # تحديث الخصائص
            account.is_cash_account = request.POST.get("is_cash_account") == "on"
            account.is_bank_account = request.POST.get("is_bank_account") == "on"
            account.is_active = request.POST.get("is_active", "on") == "on"

            account.save()
            messages.success(request, f'تم تعديل الحساب "{account.name}" بنجاح.')
            return redirect("financial:account_detail", pk=account.pk)
        except Exception as e:
            messages.error(request, f"خطأ في تعديل الحساب: {str(e)}")

    # تحميل البيانات المطلوبة
    account_types = AccountType.objects.filter(is_active=True).order_by("name")
    parent_accounts = (
        ChartOfAccounts.objects.filter(is_active=True)
        .exclude(id=account.id)
        .order_by("code")
    )

    context = {
        "account": account,
        "account_types": account_types,
        "parent_accounts": parent_accounts,
        "title": f"تعديل حساب: {account.name}",
    }

    return render(request, "financial/accounts/chart_of_accounts_form.html", context)


@login_required
def account_transactions(request, pk):
    """
    عرض معاملات حساب محدد
    """
    account = get_object_or_404(ChartOfAccounts, pk=pk)

    # استخدام النظام الجديد
    try:
        journal_lines = (
            JournalEntryLine.objects.filter(account=account)
            .select_related("journal_entry")
            .order_by("-journal_entry__date", "-id")
        )
        transactions = journal_lines
    except Exception:
        transactions = []

    # تعريف رؤوس الأعمدة للجدول الموحد
    transaction_headers = [
        {
            "key": "transaction_type",
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
            "key": "reference_number",
            "label": "المرجع",
            "sortable": False,
            "format": "reference",
            "class": "text-center",
            "width": "10%",
        },
    ]

    # تعريف أزرار الإجراءات
    transaction_actions = [
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

    context = {
        "account": account,
        "transactions": transactions,
        "title": f"معاملات حساب: {account.name}",
        "transaction_headers": transaction_headers,
        "transaction_actions": transaction_actions,
        "page_title": f"معاملات حساب: {account.name}",
        "page_icon": "fas fa-exchange-alt",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "الإدارة المالية", "url": "#", "icon": "fas fa-money-bill-wave"},
            {
                "title": "الحسابات",
                "url": reverse("financial:chart_of_accounts_list"),
                "icon": "fas fa-wallet",
            },
            {
                "title": account.name,
                "url": reverse("financial:account_detail", kwargs={"pk": account.pk}),
                "icon": "fas fa-info-circle",
            },
            {"title": "المعاملات", "active": True},
        ],
    }

    return render(request, "financial/accounts/account_transactions.html", context)


@login_required
def account_delete(request, pk):
    """
    حذف حساب مالي
    """
    account = get_object_or_404(ChartOfAccounts, pk=pk)

    # التحقق من عدم وجود معاملات مرتبطة بالحساب
    has_transactions = False
    try:
        has_transactions = JournalEntryLine.objects.filter(account=account).exists()
    except Exception:
        pass

    if request.method == "POST":
        account_name = account.name

        # تعديل حالة الحساب بدلاً من الحذف الفعلي (حذف ناعم)
        account.is_active = False
        account.save()

        messages.success(request, f'تم حذف الحساب "{account_name}" بنجاح.')
        return redirect("financial:chart_of_accounts_list")

    context = {
        "object": account,
        "object_name": "الحساب",
        "title": f"حذف حساب: {account.name}",
        "cancel_url": reverse("financial:account_detail", kwargs={"pk": account.pk}),
        "warning_message": "سيتم تعطيل الحساب وعدم ظهوره في قوائم الحسابات النشطة."
        + (" كما أن هذا الحساب مرتبط بمعاملات مالية." if has_transactions else ""),
    }

    return render(request, "financial/accounts/account_confirm_delete.html", context)


@login_required
def bank_reconciliation_list(request):
    """
    عرض قائمة التسويات البنكية
    """
    reconciliations = BankReconciliation.objects.all().order_by("-reconciliation_date")
    accounts = get_bank_accounts()

    context = {
        "reconciliations": reconciliations,
        "accounts": accounts,
        "title": "التسويات البنكية",
    }

    return render(request, "financial/banking/bank_reconciliation_list.html", context)


@login_required
def bank_reconciliation_create(request):
    """
    إنشاء تسوية بنكية جديدة
    """
    if request.method == "POST":
        form = BankReconciliationForm(request.POST)
        if form.is_valid():
            reconciliation = form.save(commit=False)
            reconciliation.created_by = request.user

            # حساب القيم التلقائية
            account = form.cleaned_data.get("account")
            reconciliation.system_balance = account.balance
            reconciliation.difference = (
                form.cleaned_data.get("bank_balance") - account.balance
            )

            reconciliation.save()

            # إجراء التسوية على الحساب
            success, message, difference = account.reconcile(
                form.cleaned_data.get("bank_balance"),
                form.cleaned_data.get("reconciliation_date"),
            )

            if success:
                messages.success(request, f"تم إجراء التسوية البنكية بنجاح. {message}")
            else:
                messages.error(request, f"حدث خطأ أثناء إجراء التسوية: {message}")

            return redirect("financial:bank_reconciliation_list")
    else:
        form = BankReconciliationForm()

    context = {
        "form": form,
        "title": "إنشاء تسوية بنكية",
    }

    return render(request, "financial/banking/bank_reconciliation_form.html", context)


@login_required
def enhanced_balances_list(request):
    """
    عرض قائمة الأرصدة المحسنة
    """
    try:
        from financial.services.enhanced_balance_service import EnhancedBalanceService

        service = EnhancedBalanceService()
        balances = service.get_all_balances()
    except ImportError as e:
        balances = []
        messages.warning(request, f"خدمة الأرصدة المحسنة غير متاحة حالياً: {str(e)}")

    # حساب الإحصائيات
    bank_accounts_count = sum(1 for b in balances if b.get("is_bank_account", False))
    cash_accounts_count = sum(1 for b in balances if b.get("is_cash_account", False))
    other_accounts_count = len(balances) - bank_accounts_count - cash_accounts_count

    context = {
        "balances": balances,
        "bank_accounts_count": bank_accounts_count,
        "cash_accounts_count": cash_accounts_count,
        "other_accounts_count": other_accounts_count,
        "page_title": "الأرصدة المحسنة",
        "page_icon": "fas fa-balance-scale",
    }
    return render(request, "financial/accounts/enhanced_balances_list.html", context)


@login_required
def enhanced_balances_refresh(request):
    """
    تحديث الأرصدة المحسنة
    """
    if request.method == "POST":
        try:
            from financial.services.enhanced_balance_service import EnhancedBalanceService

            service = EnhancedBalanceService()
            results = service.bulk_refresh_balances()

            messages.success(request, f'تم تحديث {results["success"]} رصيد بنجاح.')
            if results["failed"] > 0:
                messages.warning(request, f'فشل في تحديث {results["failed"]} رصيد.')

        except ImportError as e:
            messages.error(request, f"خدمة الأرصدة المحسنة غير متاحة حالياً: {str(e)}")
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء تحديث الأرصدة: {str(e)}")

    return redirect("financial:enhanced_balances_list")


@login_required
def enhanced_balances_audit(request):
    """
    مراجعة الأرصدة المحسنة
    """
    try:
        from financial.services.enhanced_balance_service import EnhancedBalanceService

        service = EnhancedBalanceService()
        audit_results = []  # يمكن إضافة منطق المراجعة هنا لاحقاً

        messages.info(request, "ميزة مراجعة الأرصدة تحت التطوير.")

    except ImportError as e:
        messages.error(request, f"خدمة الأرصدة المحسنة غير متاحة حالياً: {str(e)}")
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء مراجعة الأرصدة: {str(e)}")

    return redirect("financial:enhanced_balances_list")


@login_required
def cash_account_movements(request, pk):
    """
    عرض حركات حساب خزن معين من القيود المحاسبية
    """
    account = get_object_or_404(ChartOfAccounts, pk=pk)

    # التحقق من أن الحساب نقدي أو بنكي
    if not (account.is_cash_account or account.is_bank_account):
        messages.error(request, "هذا الحساب ليس حساباً نقدياً أو بنكياً")
        return redirect("financial:cash_and_bank_accounts_list")

    # جلب حركات الحساب من القيود المحاسبية
    movements = (
        JournalEntryLine.objects.filter(account=account)
        .select_related("journal_entry")
        .order_by("-journal_entry__date", "-id")
    )

    # الفلترة
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    search = request.GET.get("search", "").strip()

    if date_from:
        movements = movements.filter(journal_entry__date__gte=date_from)
    if date_to:
        movements = movements.filter(journal_entry__date__lte=date_to)
    if search:
        from django.db import models

        movements = movements.filter(
            models.Q(journal_entry__description__icontains=search)
            | models.Q(journal_entry__reference__icontains=search)
            | models.Q(description__icontains=search)
        )

    # حساب الرصيد التراكمي لكل حركة
    running_balance = 0
    movements_with_balance = []

    for movement in movements:
        # حساب تأثير الحركة على الرصيد
        movement_effect = (movement.debit or 0) - (movement.credit or 0)
        running_balance += movement_effect

        # إضافة الرصيد التراكمي للحركة
        movement.running_balance = running_balance
        movements_with_balance.append(movement)

    # الترقيم
    paginator = Paginator(movements_with_balance, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # حساب الرصيد الإجمالي
    from django.db.models import Sum

    total_debit = movements.aggregate(Sum("debit"))["debit__sum"] or 0
    total_credit = movements.aggregate(Sum("credit"))["credit__sum"] or 0
    current_balance = total_debit - total_credit

    context = {
        "account": account,
        "movements": page_obj,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "current_balance": current_balance,
        "date_from": date_from,
        "date_to": date_to,
        "search": search,
        "page_title": f"حركات {account.name}",
        "page_icon": "fas fa-list-alt",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "الإدارة المالية", "url": "#", "icon": "fas fa-money-bill-wave"},
            {
                "title": "الحسابات النقدية",
                "url": reverse("financial:cash_and_bank_accounts_list"),
                "icon": "fas fa-money-bill-wave",
            },
            {"title": f"حركات {account.name}", "active": True},
        ],
    }

    return render(request, "financial/banking/cash_account_movements.html", context)


@login_required
def partner_dashboard(request):
    """
    لوحة تحكم معاملات الشريك
    """
    from ..utils.partner_integration import PartnerFinancialIntegration
    from ..models.partner_transactions import PartnerTransaction, PartnerBalance
    
    # الحصول على حساب الشريك باستخدام أدوات التكامل
    try:
        partner_account = PartnerFinancialIntegration.find_or_create_partner_account()
    except Exception as e:
        messages.error(request, f"خطأ في الوصول لحساب الشريك: {str(e)}")
        return redirect('financial:chart_of_accounts_list')
    
    # الحصول على أو إنشاء رصيد الشريك
    partner_balance, created = PartnerBalance.objects.get_or_create(
        partner_account=partner_account
    )
    
    if created:
        partner_balance.update_balance()
    
    # إحصائيات سريعة
    recent_transactions = PartnerTransaction.objects.filter(
        partner_account=partner_account
    ).order_by('-created_at')[:10]
    
    # إحصائيات شهرية
    thirty_days_ago = timezone.now().date() - timedelta(days=30)
    
    monthly_stats = {
        'contributions': PartnerTransaction.objects.filter(
            partner_account=partner_account,
            transaction_type='contribution',
            transaction_date__gte=thirty_days_ago,
            status='completed'
        ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0'),
        
        'withdrawals': PartnerTransaction.objects.filter(
            partner_account=partner_account,
            transaction_type='withdrawal',
            transaction_date__gte=thirty_days_ago,
            status='completed'
        ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0'),
    }
    
    # الحسابات النقدية المتاحة باستخدام أدوات التكامل
    cash_accounts = PartnerFinancialIntegration.get_available_cash_accounts()
    
    context = {
        'partner_account': partner_account,
        'partner_balance': partner_balance,
        'recent_transactions': recent_transactions,
        'monthly_stats': monthly_stats,
        'cash_accounts': cash_accounts,
        'page_title': 'معاملات الشريك',
        'page_icon': 'fas fa-handshake',
    }
    
    return render(request, 'financial/partner/dashboard.html', context)


@login_required
@require_http_methods(["POST"])
def create_contribution(request):
    """
    إنشاء مساهمة جديدة للشريك
    """
    from ..utils.partner_integration import PartnerFinancialIntegration
    from ..models.partner_transactions import PartnerTransaction, PartnerBalance
    
    try:
        # الحصول على البيانات
        partner_account_id = request.POST.get('partner_account')
        cash_account_id = request.POST.get('cash_account')
        amount = Decimal(request.POST.get('amount', '0'))
        contribution_type = request.POST.get('contribution_type')
        description = request.POST.get('description', '')
        transaction_date = request.POST.get('transaction_date')
        
        # التحقق من صحة البيانات الأساسية فقط
        if amount <= 0:
            raise ValueError("المبلغ يجب أن يكون أكبر من صفر")
        
        # الحصول على الحسابات
        partner_account = get_object_or_404(ChartOfAccounts, id=partner_account_id)
        cash_account = get_object_or_404(ChartOfAccounts, id=cash_account_id)
        
        # إنشاء المعاملة باستخدام أدوات التكامل المبسطة
        with transaction.atomic():
            partner_transaction = PartnerFinancialIntegration.create_partner_transaction(
                transaction_type='contribution',
                partner_account=partner_account,
                cash_account=cash_account,
                amount=amount,
                description=description,
                created_by=request.user,
                contribution_type=contribution_type,
                transaction_date=transaction_date
            )
            
            # الحصول على الرصيد المحدث
            partner_balance = PartnerBalance.objects.get(partner_account=partner_account)
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': 'تم إضافة المساهمة بنجاح',
                    'transaction_id': partner_transaction.id,
                    'new_balance': str(partner_balance.current_balance)
                })
            else:
                messages.success(request, 'تم إضافة المساهمة بنجاح')
    
    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': str(e)
            })
        else:
            messages.error(request, f"خطأ في إضافة المساهمة: {str(e)}")
    
    return redirect('financial:partner_dashboard')


@login_required
def payment_list(request):
    """
    قائمة الدفعات
    """
    try:
        payments = []

        # جلب دفعات المبيعات
        try:
            from sale.models import SalePayment
            sale_payments = SalePayment.objects.select_related(
                "sale", "sale__customer"
            ).all()
            for payment in sale_payments:
                payments.append(
                    {
                        "id": payment.id,
                        "type": "sale",
                        "type_display": "مبيعات",
                        "amount": payment.amount,
                        "date": payment.payment_date,
                        "method": payment.get_payment_method_display(),
                        "status": payment.financial_status,
                        "invoice_number": payment.sale.number
                        if payment.sale
                        else "غير محدد",
                        "party_name": payment.sale.customer.name
                        if payment.sale and payment.sale.customer
                        else "غير محدد",
                        "url": reverse("sale:sale_detail", args=[payment.sale.id])
                        if payment.sale
                        else "#",
                        "payment_type": "sale",
                        "payment_id": payment.id,
                    }
                )
        except ImportError:
            pass

        # جلب دفعات المشتريات
        try:
            from purchase.models import PurchasePayment
            purchase_payments = PurchasePayment.objects.select_related(
                "purchase", "purchase__supplier"
            ).all()
            for payment in purchase_payments:
                payments.append(
                    {
                        "id": payment.id,
                        "type": "purchase",
                        "type_display": "مشتريات",
                        "amount": payment.amount,
                        "date": payment.payment_date,
                        "method": payment.get_payment_method_display(),
                        "status": payment.financial_status,
                        "invoice_number": payment.purchase.number
                        if payment.purchase
                        else "غير محدد",
                        "party_name": payment.purchase.supplier.name
                        if payment.purchase and payment.purchase.supplier
                        else "غير محدد",
                        "url": reverse("purchase:purchase_detail", args=[payment.purchase.id])
                        if payment.purchase
                        else "#",
                        "payment_type": "purchase",
                        "payment_id": payment.id,
                    }
                )
        except ImportError:
            pass

        # ترتيب الدفعات حسب التاريخ
        payments.sort(key=lambda x: x["date"], reverse=True)

        # حساب الإحصائيات
        total_count = len(payments)
        synced_count = len([p for p in payments if p.get('status') == 'synced'])
        pending_count = len([p for p in payments if p.get('status') == 'pending'])
        total_amount = sum([p.get('amount', 0) for p in payments])
        
        # تعريف رؤوس الأعمدة
        payment_headers = [
            {"key": "type_display", "label": "النوع", "sortable": True, "width": "10%"},
            {"key": "invoice_number", "label": "رقم الفاتورة", "sortable": True, "width": "12%", "template": "components/cells/invoice_link.html"},
            {"key": "party_name", "label": "العميل/المورد", "sortable": True, "width": "20%"},
            {"key": "amount", "label": "المبلغ", "sortable": True, "template": "components/cells/payment_amount.html", "class": "text-end", "width": "12%"},
            {"key": "date", "label": "التاريخ", "sortable": True, "format": "date", "class": "text-center", "width": "12%"},
            {"key": "method", "label": "طريقة الدفع", "sortable": False, "width": "12%"},
            {"key": "status", "label": "الحالة", "sortable": False, "template": "components/cells/payment_status.html", "class": "text-center", "width": "10%"},
        ]
        
        # تعريف أزرار الإجراءات - معطلة مؤقتاً
        payment_actions = []
        
        # الترقيم
        paginator = Paginator(payments, 25)
        page_number = request.GET.get("page")
        page_obj = paginator.get_page(page_number)

        context = {
            "payments": page_obj,
            "page_obj": page_obj,
            "payment_headers": payment_headers,
            "payment_actions": payment_actions,
            "summary": {
                "total_count": total_count,
                "synced_count": synced_count,
                "pending_count": pending_count,
                "total_amount": total_amount,
            },
            "page_title": "قائمة الدفعات",
            "page_icon": "fas fa-credit-card",
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
                {"title": "المدفوعات", "active": True},
            ],
        }

        return render(request, "financial/banking/payment_list.html", context)

    except Exception as e:
        messages.error(request, f"خطأ في تحميل قائمة الدفعات: {str(e)}")
        return render(request, "financial/banking/payment_list.html", {
            "payments": None,
            "payment_headers": [],
            "payment_actions": [],
            "summary": {
                "total_count": 0,
                "synced_count": 0,
                "pending_count": 0,
                "total_amount": 0,
            },
            "page_title": "قائمة الدفعات",
            "page_icon": "fas fa-credit-card",
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
                {"title": "المدفوعات", "active": True},
            ],
        })


@login_required
def payment_detail(request, payment_type, payment_id):
    """
    تفاصيل الدفعة
    """
    try:
        payment = None

        if payment_type == "sale":
            try:
                from sale.models import SalePayment
                try:
                    payment = SalePayment.objects.select_related(
                        "sale", "sale__customer"
                    ).get(pk=payment_id)
                except SalePayment.DoesNotExist:
                    messages.error(request, f"دفعة المبيعات #{payment_id} غير موجودة أو تم حذفها")
                    return redirect("financial:payment_list")
            except ImportError:
                messages.error(request, "نماذج المبيعات غير متاحة")
                return redirect("financial:payment_list")
        elif payment_type == "purchase":
            try:
                from purchase.models import PurchasePayment
                try:
                    payment = PurchasePayment.objects.select_related(
                        "purchase", "purchase__supplier"
                    ).get(pk=payment_id)
                except PurchasePayment.DoesNotExist:
                    messages.error(request, f"دفعة المشتريات #{payment_id} غير موجودة أو تم حذفها")
                    return redirect("financial:payment_list")
            except ImportError:
                messages.error(request, "نماذج المشتريات غير متاحة")
                return redirect("financial:payment_list")
        else:
            messages.error(request, "نوع الدفعة غير صحيح")
            return redirect("financial:payment_list")

        # التحقق من وجود الدفعة
        if not payment:
            messages.error(request, f"الدفعة #{payment_id} غير موجودة")
            return redirect("financial:payment_list")

        context = {
            "payment": payment,
            "payment_type": payment_type,
            "page_title": f"تفاصيل الدفعة #{payment.id}",
            "page_icon": "fas fa-info-circle",
        }

        return render(request, "financial/banking/payment_detail.html", context)

    except Exception as e:
        messages.error(request, f"خطأ في تحميل تفاصيل الدفعة: {str(e)}")
        return redirect("financial:payment_list")


# ============== الدوال المساعدة المتقدمة ==============


def get_account_transactions(account, limit=50, transaction_type="all"):
    """
    جلب حركات الحساب بطريقة ذكية حسب نوع الحساب
    """
    transactions = []

    if account.is_leaf:
        # جلب جميع القيود للحساب النهائي
        all_journal_lines = JournalEntryLine.objects.filter(account=account)

        # جلب جميع القيود بغض النظر عن الحالة
        transactions = list(
            all_journal_lines.select_related("journal_entry").order_by(
                "-journal_entry__date", "-id"
            )[:limit]
        )

        # إضافة حركات الخزن إذا كان حساب نقدي/بنكي (تم إزالة CashMovement)
        if account.is_cash_account or account.is_bank_account:
            try:
                # البحث في القيود المحاسبية المرتبطة بالحساب
                from ..models.journal_entry import JournalEntry

                journal_entries = (
                    JournalEntry.objects.filter(lines__account=account, status="posted")
                    .distinct()
                    .order_by("-date")[: limit // 2]
                )

                # دمج الحركات (سيتم تطويرها لاحقاً)
                # transactions = merge_transactions(journal_lines, cash_movements)
            except ImportError:
                pass

    else:
        # حساب أب: جلب حركات جميع الأحفاد النهائيين
        leaf_accounts = account.get_leaf_descendants(include_self=True)

        if leaf_accounts:
            # جلب جميع القيود للأحفاد
            all_lines = JournalEntryLine.objects.filter(account__in=leaf_accounts)

            # جلب جميع القيود بغض النظر عن الحالة
            transactions = list(
                all_lines.select_related("journal_entry", "account").order_by(
                    "-journal_entry__date", "-id"
                )[:limit]
            )

    return transactions


def get_account_analytics(account, period_days=30):
    """
    تحليلات متقدمة للحساب
    """
    from datetime import datetime, timedelta
    from decimal import Decimal

    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=period_days)

    # جلب ملخص المعاملات
    try:
        summary = account.get_transactions_summary(date_from=start_date, date_to=end_date)
    except AttributeError:
        # إذا لم تكن الدالة موجودة، استخدم حساب بديل
        summary = {
            "total_debit": 0,
            "total_credit": 0,
            "transaction_count": 0,
            "accounts_included": 1,
        }

    # حساب الرصيد الحالي
    current_balance = account.get_balance() if hasattr(account, 'get_balance') else 0

    # حساب الرصيد في بداية الفترة
    try:
        previous_balance = account.get_balance(date_to=start_date) if hasattr(account, 'get_balance') else 0
    except:
        previous_balance = 0

    analytics = {
        "current_balance": current_balance,
        "previous_balance": previous_balance,
        "balance_change": current_balance - previous_balance,
        "total_debit": summary["total_debit"],
        "total_credit": summary["total_credit"],
        "transaction_count": summary["transaction_count"],
        "accounts_included": summary["accounts_included"],
        "period_days": period_days,
        "avg_daily_transactions": summary["transaction_count"] / period_days
        if period_days > 0
        else 0,
    }

    # تحديد اتجاه التغيير
    if analytics["balance_change"] > 0:
        analytics["trend"] = "positive"
        analytics["trend_icon"] = "fa-arrow-up"
        analytics["trend_color"] = "success"
    elif analytics["balance_change"] < 0:
        analytics["trend"] = "negative"
        analytics["trend_icon"] = "fa-arrow-down"
        analytics["trend_color"] = "danger"
    else:
        analytics["trend"] = "stable"
        analytics["trend_icon"] = "fa-minus"
        analytics["trend_color"] = "secondary"

    return analytics


# ============== دوال الشراكة المفقودة ==============


@login_required
@require_http_methods(["POST"])
def create_withdrawal(request):
    """
    إنشاء سحب جديد للشريك
    """
    try:
        # الحصول على البيانات
        partner_account_id = request.POST.get('partner_account')
        cash_account_id = request.POST.get('cash_account')
        amount = Decimal(request.POST.get('amount', '0'))
        withdrawal_type = request.POST.get('withdrawal_type')
        description = request.POST.get('description', '')
        transaction_date = request.POST.get('transaction_date')
        
        # التحقق من صحة البيانات الأساسية فقط
        if amount <= 0:
            raise ValueError("المبلغ يجب أن يكون أكبر من صفر")
        
        # الحصول على الحسابات
        partner_account = get_object_or_404(ChartOfAccounts, id=partner_account_id)
        cash_account = get_object_or_404(ChartOfAccounts, id=cash_account_id)
        
        # إنشاء قيد محاسبي للسحب
        with transaction.atomic():
            journal_entry = JournalEntry.objects.create(
                number=f"WD-{timezone.now().strftime('%Y%m%d')}-{JournalEntry.objects.count() + 1}",
                date=transaction_date or timezone.now().date(),
                description=f"سحب شريك: {description}",
                entry_type="manual",
                status="posted",
                created_by=request.user
            )
            
            # خصم من حساب الشريك
            JournalEntryLine.objects.create(
                journal_entry=journal_entry,
                account=partner_account,
                debit=amount,
                credit=0,
                description=f"سحب شريك: {description}"
            )
            
            # دائن في الحساب النقدي
            JournalEntryLine.objects.create(
                journal_entry=journal_entry,
                account=cash_account,
                debit=0,
                credit=amount,
                description=f"سحب شريك: {description}"
            )
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': 'تم إضافة السحب بنجاح',
                    'journal_entry_id': journal_entry.id,
                })
            else:
                messages.success(request, 'تم إضافة السحب بنجاح')
    
    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': str(e)
            })
        else:
            messages.error(request, f"خطأ في إضافة السحب: {str(e)}")
    
    return redirect('financial:partner_dashboard')


@login_required
def partner_transactions_list(request):
    """
    قائمة معاملات الشريك
    """
    # الحصول على حساب الشريك
    try:
        partner_account = ChartOfAccounts.objects.get(
            name__icontains="جاري الشريك",
            is_active=True
        )
    except ChartOfAccounts.DoesNotExist:
        messages.error(request, "لم يتم العثور على حساب الشريك")
        return redirect('financial:chart_of_accounts_list')
    
    # جلب القيود المحاسبية المرتبطة بحساب الشريك
    partner_entries = JournalEntry.objects.filter(
        lines__account=partner_account
    ).distinct().order_by('-date', '-id')
    
    # الفلترة
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    transaction_type = request.GET.get('transaction_type')
    
    if date_from:
        date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
        partner_entries = partner_entries.filter(date__gte=date_from)
    
    if date_to:
        date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
        partner_entries = partner_entries.filter(date__lte=date_to)
    
    if transaction_type:
        if transaction_type == 'contribution':
            partner_entries = partner_entries.filter(description__icontains='مساهمة')
        elif transaction_type == 'withdrawal':
            partner_entries = partner_entries.filter(description__icontains='سحب')
    
    # تحويل القيود المحاسبية إلى تنسيق يتوافق مع القالب
    enhanced_transactions = []
    total_contributions = Decimal('0')
    total_withdrawals = Decimal('0')
    
    for entry in partner_entries:
        # الحصول على بنود الشريك في هذا القيد
        partner_lines = entry.lines.filter(account=partner_account)
        
        for line in partner_lines:
            # تحديد نوع المعاملة بناءً على الدائن/المدين
            if line.credit > 0:
                transaction_type = 'contribution'
                amount = line.credit
                total_contributions += amount
            else:
                transaction_type = 'withdrawal'
                amount = line.debit
                total_withdrawals += amount
            
            # الحصول على الحساب المقابل (الخزينة)
            other_lines = entry.lines.exclude(account=partner_account)
            cash_account_name = ', '.join([ol.account.name for ol in other_lines])
            
            enhanced_transaction = {
                'id': entry.id,
                'transaction_type': transaction_type,
                'amount': amount,
                'description': entry.description,
                'transaction_date': entry.date,
                'status': 'completed',  # جميع القيود المحاسبية مكتملة
                'cash_account_name': cash_account_name,
                'created_by': entry.created_by,
                'created_at': entry.created_at,
                'journal_entry': entry,
                'get_status_display': 'مكتمل',
                'get_sub_type_display': '',
            }
            enhanced_transactions.append(enhanced_transaction)
    
    # الترقيم الصفحي
    paginator = Paginator(enhanced_transactions, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # حساب صافي الرصيد
    net_balance = total_contributions - total_withdrawals
    
    context = {
        'partner_account': partner_account,
        'transactions': page_obj,
        'total_contributions': total_contributions,
        'total_withdrawals': total_withdrawals,
        'net_balance': net_balance,
        'page_title': 'معاملات الشريك',
        'page_icon': 'fas fa-handshake',
        'breadcrumb_items': [
            {
                'title': 'الرئيسية',
                'url': reverse('core:dashboard'),
                'icon': 'fas fa-home'
            },
            {
                'title': 'الإدارة المالية',
                'url': '#',
                'icon': 'fas fa-money-bill-wave'
            },
            {'title': 'معاملات الشريك', 'active': True}
        ]
    }
    
    return render(request, 'financial/partner/transactions_list.html', context)


@login_required
def partner_transaction_detail(request, pk):
    """
    تفاصيل معاملة شريك
    """
    journal_entry = get_object_or_404(JournalEntry, pk=pk)
    
    # التحقق من أن القيد مرتبط بحساب الشريك
    partner_lines = journal_entry.lines.filter(
        account__name__icontains="جاري الشريك"
    )
    
    if not partner_lines.exists():
        messages.error(request, "هذا القيد غير مرتبط بحساب الشريك")
        return redirect('financial:partner_transactions_list')
    
    context = {
        'journal_entry': journal_entry,
        'partner_lines': partner_lines,
        'page_title': f'تفاصيل معاملة الشريك #{journal_entry.number}',
        'page_icon': 'fas fa-info-circle',
        'breadcrumb_items': [
            {
                'title': 'الرئيسية',
                'url': reverse('core:dashboard'),
                'icon': 'fas fa-home'
            },
            {
                'title': 'الإدارة المالية',
                'url': '#',
                'icon': 'fas fa-money-bill-wave'
            },
            {
                'title': 'معاملات الشريك',
                'url': reverse('financial:partner_transactions_list'),
                'icon': 'fas fa-handshake'
            },
            {'title': f'معاملة #{journal_entry.number}', 'active': True}
        ]
    }
    
    return render(request, 'financial/partner/transaction_detail.html', context)


def get_partner_balance(request):
    """
    API لجلب رصيد الشريك
    """
    try:
        partner_account = ChartOfAccounts.objects.get(
            name__icontains="جاري الشريك",
            is_active=True
        )
        
        # حساب الرصيد من القيود المحاسبية
        partner_lines = JournalEntryLine.objects.filter(
            account=partner_account,
            journal_entry__status='posted'
        )
        
        total_debit = partner_lines.aggregate(Sum('debit'))['debit__sum'] or 0
        total_credit = partner_lines.aggregate(Sum('credit'))['credit__sum'] or 0
        
        # رصيد الشريك = المدين - الدائن (حيث المدين هو المساهمات والدائن هو السحوبات)
        balance = total_debit - total_credit
        
        return JsonResponse({
            'success': True,
            'balance': float(balance),
            'total_contributions': float(total_debit),
            'total_withdrawals': float(total_credit),
            'account_name': partner_account.name
        })
        
    except ChartOfAccounts.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'لم يتم العثور على حساب الشريك'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


# ============== دوال الدفعات المفقودة ==============


@login_required
def payment_edit(request, payment_type, payment_id):
    """
    تعديل دفعة
    """
    try:
        payment = None
        
        if payment_type == "sale":
            try:
                from sale.models import SalePayment
                payment = get_object_or_404(SalePayment, pk=payment_id)
            except ImportError:
                messages.error(request, "نماذج المبيعات غير متاحة")
                return redirect("financial:payment_list")
        elif payment_type == "purchase":
            try:
                from purchase.models import PurchasePayment
                payment = get_object_or_404(PurchasePayment, pk=payment_id)
            except ImportError:
                messages.error(request, "نماذج المشتريات غير متاحة")
                return redirect("financial:payment_list")
        else:
            messages.error(request, "نوع الدفعة غير صحيح")
            return redirect("financial:payment_list")
        
        if request.method == "POST":
            # تحديث بيانات الدفعة
            payment.amount = Decimal(request.POST.get('amount', payment.amount))
            payment.payment_date = request.POST.get('payment_date', payment.payment_date)
            payment.payment_method = request.POST.get('payment_method', payment.payment_method)
            payment.notes = request.POST.get('notes', payment.notes or '')
            payment.save()
            
            messages.success(request, "تم تحديث الدفعة بنجاح")
            return redirect("financial:payment_detail", payment_type=payment_type, payment_id=payment_id)
        
        context = {
            "payment": payment,
            "payment_type": payment_type,
            "page_title": f"تعديل الدفعة #{payment.id}",
            "page_icon": "fas fa-edit",
        }
        
        return render(request, "financial/banking/payment_edit.html", context)
        
    except Exception as e:
        messages.error(request, f"خطأ في تعديل الدفعة: {str(e)}")
        return redirect("financial:payment_list")


@login_required
def payment_unpost(request, payment_type, payment_id):
    """
    إلغاء ترحيل دفعة
    """
    try:
        payment = None
        
        if payment_type == "sale":
            try:
                from sale.models import SalePayment
                payment = get_object_or_404(SalePayment, pk=payment_id)
            except ImportError:
                messages.error(request, "نماذج المبيعات غير متاحة")
                return redirect("financial:payment_list")
        elif payment_type == "purchase":
            try:
                from purchase.models import PurchasePayment
                payment = get_object_or_404(PurchasePayment, pk=payment_id)
            except ImportError:
                messages.error(request, "نماذج المشتريات غير متاحة")
                return redirect("financial:payment_list")
        else:
            messages.error(request, "نوع الدفعة غير صحيح")
            return redirect("financial:payment_list")
        
        if request.method == "POST":
            # إلغاء ترحيل الدفعة
            if hasattr(payment, 'financial_status'):
                payment.financial_status = 'pending'
                payment.save()
                messages.success(request, "تم إلغاء ترحيل الدفعة بنجاح")
            else:
                messages.warning(request, "لا يمكن إلغاء ترحيل هذه الدفعة")
            
            return redirect("financial:payment_detail", payment_type=payment_type, payment_id=payment_id)
        
        context = {
            "payment": payment,
            "payment_type": payment_type,
            "page_title": f"إلغاء ترحيل الدفعة #{payment.id}",
            "page_icon": "fas fa-undo",
        }
        
        return render(request, "financial/banking/payment_unpost.html", context)
        
    except Exception as e:
        messages.error(request, f"خطأ في إلغاء ترحيل الدفعة: {str(e)}")
        return redirect("financial:payment_list")


@login_required
def payment_delete(request, payment_type, payment_id):
    """
    حذف دفعة
    """
    try:
        payment = None
        
        if payment_type == "sale":
            try:
                from sale.models import SalePayment
                payment = get_object_or_404(SalePayment, pk=payment_id)
            except ImportError:
                messages.error(request, "نماذج المبيعات غير متاحة")
                return redirect("financial:payment_list")
        elif payment_type == "purchase":
            try:
                from purchase.models import PurchasePayment
                payment = get_object_or_404(PurchasePayment, pk=payment_id)
            except ImportError:
                messages.error(request, "نماذج المشتريات غير متاحة")
                return redirect("financial:payment_list")
        else:
            messages.error(request, "نوع الدفعة غير صحيح")
            return redirect("financial:payment_list")
        
        if request.method == "POST":
            payment_info = f"#{payment.id} - {payment.amount}"
            payment.delete()
            messages.success(request, f"تم حذف الدفعة {payment_info} بنجاح")
            return redirect("financial:payment_list")
        
        context = {
            "payment": payment,
            "payment_type": payment_type,
            "page_title": f"حذف الدفعة #{payment.id}",
            "page_icon": "fas fa-trash",
        }
        
        return render(request, "financial/banking/payment_delete.html", context)
        
    except Exception as e:
        messages.error(request, f"خطأ في حذف الدفعة: {str(e)}")
        return redirect("financial:payment_list")


@login_required
def payment_history(request, payment_type, payment_id):
    """
    تاريخ الدفعة
    """
    try:
        payment = None
        
        if payment_type == "sale":
            try:
                from sale.models import SalePayment
                payment = get_object_or_404(SalePayment, pk=payment_id)
            except ImportError:
                messages.error(request, "نماذج المبيعات غير متاحة")
                return redirect("financial:payment_list")
        elif payment_type == "purchase":
            try:
                from purchase.models import PurchasePayment
                payment = get_object_or_404(PurchasePayment, pk=payment_id)
            except ImportError:
                messages.error(request, "نماذج المشتريات غير متاحة")
                return redirect("financial:payment_list")
        else:
            messages.error(request, "نوع الدفعة غير صحيح")
            return redirect("financial:payment_list")
        
        # جلب تاريخ التغييرات (إذا كان متاحاً)
        history = []
        if hasattr(payment, 'history'):
            history = payment.history.all()
        
        context = {
            "payment": payment,
            "payment_type": payment_type,
            "history": history,
            "page_title": f"تاريخ الدفعة #{payment.id}",
            "page_icon": "fas fa-history",
        }
        
        return render(request, "financial/banking/payment_history.html", context)
        
    except Exception as e:
        messages.error(request, f"خطأ في عرض تاريخ الدفعة: {str(e)}")
        return redirect("financial:payment_list")


# ============== اكتمل ملف account_views.py بالكامل ==============
# تم نقل جميع دوال الحسابات والتسويات البنكية بنجاح
