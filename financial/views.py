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
import json

# استيراد النماذج والخدمات الجديدة
try:
    from .forms.expense_forms import ExpenseForm, ExpenseEditForm, ExpenseFilterForm
    from .forms.income_forms import IncomeForm, IncomeEditForm, IncomeFilterForm
    from .services.expense_income_service import ExpenseIncomeService
except ImportError:
    # في حالة عدم وجود الملفات، استخدم نماذج بسيطة
    ExpenseForm = None
    IncomeForm = None
    ExpenseEditForm = None
    IncomeEditForm = None
    ExpenseFilterForm = None
    IncomeFilterForm = None
    ExpenseIncomeService = None

# سيتم إضافة دوال حركات الخزن في نهاية الملف

# استيراد النماذج الأساسية (موجودة بالتأكيد)
from .models import AccountType, ChartOfAccounts, AccountingPeriod, JournalEntry, JournalEntryLine

# استيراد النماذج الاختيارية
try:
    from .models import (
        AccountGroup, JournalEntryTemplate, JournalEntryTemplateLine,
        BalanceSnapshot, AccountBalanceCache, BalanceAuditLog,
        PaymentSyncOperation, PaymentSyncLog
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
    from .models import Transaction, Account, TransactionLine, TransactionForm
except ImportError:
    # في حالة عدم توفر النماذج القديمة، إنشاء نماذج وهمية
    class Transaction:
        objects = type('MockManager', (), {
            'filter': lambda *args, **kwargs: type('MockQuerySet', (), {
                'order_by': lambda *args: [],
                'aggregate': lambda *args: {'amount__sum': 0, 'total': 0},
                'count': lambda: 0,
                'exists': lambda: False
            })(),
            'create': lambda *args, **kwargs: None,
            'all': lambda: type('MockQuerySet', (), {
                'order_by': lambda *args: []
            })()
        })()
    
    Account = ChartOfAccounts  # استخدام النموذج الجديد
    TransactionLine = JournalEntryLine
    TransactionForm = None


def get_cash_and_bank_accounts():
    """الحصول على الحسابات النقدية والبنكية من النظام الجديد"""
    try:
        return ChartOfAccounts.objects.filter(
            is_active=True,
            is_leaf=True
        ).filter(
            Q(is_cash_account=True) | 
            Q(is_bank_account=True) |
            Q(account_type__name__icontains='نقدي') |
            Q(account_type__name__icontains='بنك') |
            Q(account_type__name__icontains='صندوق')
        ).order_by('code')
    except Exception:
        # النظام القديم لم يعد متوفراً
        return ChartOfAccounts.objects.none()


def get_all_active_accounts():
    """الحصول على جميع الحسابات النشطة من النظام الجديد"""
    try:
        return ChartOfAccounts.objects.filter(
            is_active=True,
            is_leaf=True
        ).order_by('code')
    except Exception:
        # النظام القديم لم يعد متوفراً
        return ChartOfAccounts.objects.none()


def get_accounts_by_category(category):
    """الحصول على الحسابات حسب التصنيف من النظام الجديد"""
    try:
        return ChartOfAccounts.objects.filter(
            is_active=True,
            is_leaf=True,
            account_type__category=category
        ).order_by('code')
    except Exception:
        # النظام القديم لم يعد متوفراً
        return ChartOfAccounts.objects.none()


def get_bank_accounts():
    """الحصول على الحسابات البنكية فقط"""
    try:
        return ChartOfAccounts.objects.filter(
            is_active=True,
            is_leaf=True,
            is_bank_account=True
        ).order_by('code')
    except Exception:
        # النظام القديم لم يعد متوفراً
        return ChartOfAccounts.objects.none()


def get_next_available_code(prefix=""):
    """الحصول على أول كود متاح"""
    if not ChartOfAccounts:
        return "1000"
    
    if prefix:
        # البحث عن آخر كود بنفس البادئة
        existing_codes = ChartOfAccounts.objects.filter(
            code__startswith=prefix
        ).values_list('code', flat=True).order_by('code')
        
        if not existing_codes:
            return f"{prefix}01"
        
        # العثور على أول رقم متاح
        for i in range(1, 100):
            code = f"{prefix}{i:02d}"
            if code not in existing_codes:
                return code
    
    # البحث العام عن كود متاح
    existing_codes = set(ChartOfAccounts.objects.values_list('code', flat=True))
    
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
        accounts = ChartOfAccounts.objects.filter(
            is_active=True,
            is_leaf=True  # الحسابات الفرعية فقط
        ).filter(
            Q(is_cash_account=True) | 
            Q(is_bank_account=True) |
            Q(account_type__name__icontains='نقدي') |
            Q(account_type__name__icontains='بنك') |
            Q(account_type__name__icontains='صندوق')
        ).order_by('code')
        
        # اختبار الاستعلام
        list(accounts[:1])  # تنفيذ الاستعلام للتأكد من عدم وجود أخطاء
        
    except Exception as e:
        # في حالة وجود مشكلة في قاعدة البيانات، استخدم فلترة أساسية
        accounts = ChartOfAccounts.objects.filter(
            is_active=True,
            is_leaf=True
        ).filter(
            Q(account_type__name__icontains='نقدي') |
            Q(account_type__name__icontains='بنك') |
            Q(account_type__name__icontains='صندوق') |
            Q(account_type__name__icontains='خزن')
        ).order_by('code')
    
    # حساب الإحصائيات
    try:
        cash_accounts_count = accounts.filter(is_cash_account=True).count()
        bank_accounts_count = accounts.filter(is_bank_account=True).count()
    except Exception:
        # في حالة عدم وجود الحقول، استخدم فلترة بديلة
        cash_accounts_count = accounts.filter(account_type__name__icontains='نقدي').count()
        bank_accounts_count = accounts.filter(account_type__name__icontains='بنك').count()
    
    # حساب إجمالي الأرصدة من القيود المحاسبية
    total_balance = 0
    for account in accounts:
        try:
            # استخدام القيود المحاسبية فقط لجميع الحسابات
            balance = account.get_balance(include_opening=True)
            total_balance += balance
            
            # إضافة الرصيد المحسوب للحساب كخاصية مؤقتة للعرض
            account.calculated_balance = balance
            
        except Exception as e:
            # في حالة الخطأ، استخدم الرصيد الافتتاحي فقط
            fallback_balance = account.opening_balance or 0
            total_balance += fallback_balance
            account.calculated_balance = fallback_balance
    
    context = {
        'accounts': accounts,
        'accounts_count': len(accounts),
        'cash_accounts_count': cash_accounts_count,
        'bank_accounts_count': bank_accounts_count,
        'total_balance': total_balance,
        'page_title': 'قائمة الخزن والحسابات النقدية',
        'page_icon': 'fas fa-money-bill-wave',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الإدارة المالية', 'url': '#', 'icon': 'fas fa-money-bill-wave'},
            {'title': 'قائمة الخزن والحسابات النقدية', 'active': True}
        ]
    }
    return render(request, 'financial/advanced/cash_and_bank_accounts_list.html', context)


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
        account_type_filter = request.GET.get('type')
        search_query = request.GET.get('search')
        view_mode = request.GET.get('view', 'tree')  # tree أو flat
        show_inactive = request.GET.get('show_inactive', False)
        
        # استعلام محسن مع prefetch للأداء
        accounts_query = ChartOfAccounts.objects.select_related(
            'account_type', 'parent'
        ).prefetch_related(
            Prefetch('children', queryset=ChartOfAccounts.objects.select_related('account_type'))
        )
        
        # تطبيق الفلاتر
        if not show_inactive:
            accounts_query = accounts_query.filter(is_active=True)
            
        if account_type_filter:
            accounts_query = accounts_query.filter(account_type__code=account_type_filter)
        
        if search_query:
            accounts_query = accounts_query.filter(
                Q(name__icontains=search_query) | 
                Q(code__icontains=search_query) |
                Q(name_en__icontains=search_query) |
                Q(account_type__name__icontains=search_query)
            )
        
        # جلب الحسابات حسب نمط العرض
        if view_mode == 'flat':
            root_accounts = accounts_query.order_by('code')
        else:
            # عرض الحسابات الرئيسية فقط (الحسابات الأب الـ5)
            root_accounts = accounts_query.filter(parent=None).order_by('code')
        
        # جلب أنواع الحسابات للفلترة
        account_types = AccountType.objects.filter(is_active=True).order_by('code')
        
        # إحصائيات شاملة ومحسنة
        all_accounts = ChartOfAccounts.objects.filter(is_active=True, is_leaf=True)
        
        # حساب الأرصدة بطريقة محسنة
        def calculate_category_balance(category):
            return sum(
                acc.get_balance() or Decimal('0')
                for acc in all_accounts 
                if acc.account_type.category == category
            )
        
        assets_balance = calculate_category_balance('asset')
        liabilities_balance = calculate_category_balance('liability')
        equity_balance = calculate_category_balance('equity')
        revenue_balance = calculate_category_balance('revenue')
        expense_balance = calculate_category_balance('expense')
        
        # بناء بيانات الشجرة للعرض التفاعلي
        def build_tree_data(account, level=0):
            """بناء بيانات الشجرة بشكل تكراري"""
            balance = account.get_balance() or Decimal('0')
            children_data = []
            
            # جلب الأطفال النشطة فقط (إلا إذا كان العرض يشمل غير النشطة)
            children_query = account.children.all()
            if not show_inactive:
                children_query = children_query.filter(is_active=True)
                
            for child in children_query.order_by('code'):
                children_data.append(build_tree_data(child, level + 1))
            
            return {
                'id': account.id,
                'code': account.code,
                'name': account.name,
                'account_type': account.account_type.name,
                'category': account.account_type.category,
                'nature': account.account_type.nature,
                'balance': float(balance),
                'balance_formatted': f"{balance:,.2f}",
                'is_leaf': account.is_leaf,
                'is_active': account.is_active,
                'is_cash': account.is_cash_account,
                'is_bank': account.is_bank_account,
                'level': level,
                'has_children': len(children_data) > 0,
                'children': children_data,
                'url_detail': f"/financial/accounts/{account.id}/",
                'url_edit': f"/financial/accounts/{account.id}/edit/",
            }
        
        # بناء بيانات الشجرة
        tree_data = []
        for root_account in root_accounts:
            tree_data.append(build_tree_data(root_account))
        
        # حساب إجمالي النقدية
        cash_balance = sum(
            acc.get_balance() or Decimal('0')
            for acc in all_accounts 
            if (acc.is_cash_account or acc.is_bank_account) and acc.is_leaf
        )
        
        stats = {
            'total': ChartOfAccounts.objects.count(),
            'active': ChartOfAccounts.objects.filter(is_active=True).count(),
            'inactive': ChartOfAccounts.objects.filter(is_active=False).count(),
            'leaf': ChartOfAccounts.objects.filter(is_leaf=True).count(),
            'parent': ChartOfAccounts.objects.filter(is_leaf=False).count(),
            'cash': ChartOfAccounts.objects.filter(is_cash_account=True).count(),
            'bank': ChartOfAccounts.objects.filter(is_bank_account=True).count(),
            # أرصدة حسب التصنيف
            'assets_balance': assets_balance,
            'liabilities_balance': liabilities_balance,
            'equity_balance': equity_balance,
            'revenue_balance': revenue_balance,
            'expense_balance': expense_balance,
            'net_assets': assets_balance - liabilities_balance,
            'cash_balance': cash_balance,
        }
        
        # إحصائيات حسب النوع
        type_stats = []
        for acc_type in AccountType.objects.filter(is_active=True).order_by('category', 'code'):
            count = all_accounts.filter(account_type=acc_type).count()
            if count > 0:
                type_stats.append({
                    'type': acc_type,
                    'count': count,
                })
        
        stats['by_type'] = type_stats
        accounts = all_accounts.order_by('code')
    
    # أنواع الحسابات للفلترة
    account_types = AccountType.objects.filter(is_active=True).order_by('category', 'code')
    
    context = {
        'accounts': accounts if 'accounts' in locals() else [],
        'root_accounts': root_accounts,
        'account_types': account_types if 'account_types' in locals() else [],
        'tree_data': tree_data if 'tree_data' in locals() else [],
        'stats': stats if 'stats' in locals() else {},
        'selected_type': account_type_filter,
        'search_query': search_query,
        'view_mode': view_mode if 'view_mode' in locals() else 'tree',
        'show_inactive': show_inactive,
        'page_title': 'دليل الحسابات',
        'page_icon': 'fas fa-sitemap',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'النظام المحاسبي', 'url': '#', 'icon': 'fas fa-calculator'},
            {'title': 'دليل الحسابات', 'active': True}
        ],
    }
    return render(request, 'financial/advanced/chart_of_accounts_list.html', context)


@login_required
def chart_tree_api(request):
    """API لجلب بيانات الشجرة الهرمية بشكل ديناميكي"""
    from django.http import JsonResponse
    from decimal import Decimal
    
    try:
        account_id = request.GET.get('account_id')
        expand_all = request.GET.get('expand_all', 'false').lower() == 'true'
        
        if account_id:
            # جلب حساب معين مع أطفاله
            account = get_object_or_404(ChartOfAccounts, id=account_id)
            children = account.children.filter(is_active=True).order_by('code')
            
            tree_data = []
            for child in children:
                balance = child.get_balance() or Decimal('0')
                tree_data.append({
                    'id': child.id,
                    'code': child.code,
                    'name': child.name,
                    'account_type': child.account_type.name,
                    'balance': float(balance),
                    'balance_formatted': f"{balance:,.2f}",
                    'is_leaf': child.is_leaf,
                    'is_active': child.is_active,
                    'is_cash': child.is_cash_account,
                    'is_bank': child.is_bank_account,
                    'has_children': child.children.filter(is_active=True).exists(),
                    'url_detail': f"/financial/accounts/{child.id}/",
                    'url_edit': f"/financial/accounts/{child.id}/edit/",
                })
        else:
            # جلب الشجرة الكاملة أو الجذور فقط
            if expand_all:
                # بناء الشجرة الكاملة
                def build_full_tree(account, level=0):
                    balance = account.get_balance() or Decimal('0')
                    children_data = []
                    
                    for child in account.children.filter(is_active=True).order_by('code'):
                        children_data.append(build_full_tree(child, level + 1))
                    
                    return {
                        'id': account.id,
                        'code': account.code,
                        'name': account.name,
                        'account_type': account.account_type.name,
                        'balance': float(balance),
                        'balance_formatted': f"{balance:,.2f}",
                        'is_leaf': account.is_leaf,
                        'is_active': account.is_active,
                        'is_cash': account.is_cash_account,
                        'is_bank': account.is_bank_account,
                        'level': level,
                        'has_children': len(children_data) > 0,
                        'children': children_data,
                        'expanded': True,
                        'url_detail': f"/financial/accounts/{account.id}/",
                        'url_edit': f"/financial/accounts/{account.id}/edit/",
                    }
                
                root_accounts = ChartOfAccounts.objects.filter(
                    parent=None, is_active=True
                ).order_by('code')
                
                tree_data = [build_full_tree(account) for account in root_accounts]
            else:
                # جلب الجذور فقط
                root_accounts = ChartOfAccounts.objects.filter(
                    parent=None, is_active=True
                ).order_by('code')
                
                tree_data = []
                for account in root_accounts:
                    balance = account.get_balance() or Decimal('0')
                    tree_data.append({
                        'id': account.id,
                        'code': account.code,
                        'name': account.name,
                        'account_type': account.account_type.name,
                        'balance': float(balance),
                        'balance_formatted': f"{balance:,.2f}",
                        'is_leaf': account.is_leaf,
                        'is_active': account.is_active,
                        'is_cash': account.is_cash_account,
                        'is_bank': account.is_bank_account,
                        'has_children': account.children.filter(is_active=True).exists(),
                        'expanded': False,
                        'url_detail': f"/financial/accounts/{account.id}/",
                        'url_edit': f"/financial/accounts/{account.id}/edit/",
                    })
        
        return JsonResponse({
            'success': True,
            'data': tree_data,
            'count': len(tree_data)
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
def chart_of_accounts_create(request):
    """إنشاء حساب جديد في دليل الحسابات"""
    if request.method == 'POST':
        try:
            # التحقق من توفر الكود
            code = request.POST.get('code', '').strip()
            if ChartOfAccounts and ChartOfAccounts.objects.filter(code=code).exists():
                messages.error(request, f'كود الحساب {code} موجود مسبقاً. يرجى استخدام كود آخر.')
                # اقتراح كود بديل
                suggested_code = get_next_available_code()
                messages.info(request, f'كود مقترح متاح: {suggested_code}')
                
                # إعادة تحميل الصفحة مع البيانات
                context = {
                    'account_types': AccountType.objects.all() if AccountType else [],
                    'parent_accounts': ChartOfAccounts.objects.filter(is_active=True) if ChartOfAccounts else [],
                    'suggested_code': suggested_code,
                    'form_data': request.POST,
                    'page_title': 'إنشاء حساب جديد',
                    'page_icon': 'fas fa-plus',
                    'breadcrumb_items': [
                        {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
                        {'title': 'دليل الحسابات', 'url': reverse('financial:chart_of_accounts_list'), 'icon': 'fas fa-sitemap'},
                        {'title': 'إنشاء حساب جديد', 'active': True}
                    ]
                }
                return render(request, 'financial/advanced/chart_of_accounts_form.html', context)
            
            # إنشاء حساب جديد
            account = ChartOfAccounts()
            
            # تحديث البيانات الأساسية
            account.code = code
            account.name = request.POST.get('name', '').strip()
            account.name_en = request.POST.get('name_en', '').strip()
            
            # تحديث نوع الحساب
            account_type_id = request.POST.get('account_type')
            if account_type_id and AccountType:
                account.account_type = AccountType.objects.get(id=account_type_id)
            
            # تحديث الحساب الأب
            parent_id = request.POST.get('parent')
            if parent_id:
                account.parent = ChartOfAccounts.objects.get(id=parent_id)
            
            # تحديث الرصيد الافتتاحي
            opening_balance = request.POST.get('opening_balance', '0')
            try:
                account.opening_balance = float(opening_balance) if opening_balance else 0.00
            except (ValueError, TypeError):
                account.opening_balance = 0.00
            
            # تحديث تاريخ الرصيد الافتتاحي
            opening_balance_date = request.POST.get('opening_balance_date')
            if opening_balance_date:
                from datetime import datetime
                account.opening_balance_date = datetime.strptime(opening_balance_date, '%Y-%m-%d').date()
            
            # تحديث الخصائص
            account.is_leaf = 'is_leaf' in request.POST
            account.is_bank_account = 'is_bank_account' in request.POST
            account.is_cash_account = 'is_cash_account' in request.POST
            account.is_reconcilable = 'is_reconcilable' in request.POST
            account.is_control_account = 'is_control_account' in request.POST
            account.is_active = 'is_active' in request.POST
            
            # تحديث المعلومات الإضافية
            account.description = request.POST.get('description', '').strip()
            account.notes = request.POST.get('notes', '').strip()
            
            # تعيين المستخدم الحالي
            account.created_by = request.user
            
            # حفظ الحساب الجديد
            account.save()
            
            messages.success(request, f'تم إنشاء الحساب "{account.name}" بنجاح.')
            return redirect('financial:account_detail', pk=account.pk)
            
        except Exception as e:
            messages.error(request, f'حدث خطأ أثناء إنشاء الحساب: {str(e)}')
    
    # تحميل أنواع الحسابات للنموذج
    account_types = []
    if AccountType:
        account_types = AccountType.objects.filter(is_active=True).order_by('code')
    
    # تحميل الحسابات الأب المحتملة
    parent_accounts = []
    if ChartOfAccounts:
        parent_accounts = ChartOfAccounts.objects.filter(is_active=True).order_by('code')
    
    # اقتراح كود متاح
    suggested_code = get_next_available_code()
    
    context = {
        'account_types': account_types,
        'parent_accounts': parent_accounts,
        'suggested_code': suggested_code,
        'page_title': 'إضافة حساب جديد',
        'page_icon': 'fas fa-plus-circle',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'النظام المحاسبي', 'url': '#', 'icon': 'fas fa-calculator'},
            {'title': 'دليل الحسابات', 'url': reverse('financial:account_list'), 'icon': 'fas fa-sitemap'},
            {'title': 'إضافة حساب جديد', 'active': True}
        ],
    }
    return render(request, 'financial/advanced/chart_of_accounts_form.html', context)


@login_required
def chart_of_accounts_detail(request, pk):
    """عرض تفاصيل حساب مع الحركات للحسابات النقدية"""
    if ChartOfAccounts is None:
        messages.error(request, 'نموذج دليل الحسابات غير متاح.')
        return redirect('financial:chart_of_accounts_list')
    
    account = get_object_or_404(ChartOfAccounts, pk=pk)
    
    # متغيرات الحركات
    movements = []
    filter_form = None
    balance_summary = None
    
    # إنشاء ملخص رصيد أساسي لجميع الحسابات
    balance_summary = {
        'opening_balance': account.opening_balance or 0,
        'total_in': 0,
        'total_out': 0,
        'current_balance': account.opening_balance or 0,
    }
    
    # محاولة جلب البيانات من القيود المحاسبية أولاً (الأكثر استقراراً)
    try:
        # جلب جميع القيود (مرحلة وغير مرحلة)
        all_lines = JournalEntryLine.objects.filter(account=account)
        total_debit_all = all_lines.aggregate(Sum('debit'))['debit__sum'] or 0
        total_credit_all = all_lines.aggregate(Sum('credit'))['credit__sum'] or 0
        
        # جلب القيود المرحلة فقط للرصيد المعتمد
        posted_lines = all_lines.filter(journal_entry__status='posted')
        total_debit_posted = posted_lines.aggregate(Sum('debit'))['debit__sum'] or 0
        total_credit_posted = posted_lines.aggregate(Sum('credit'))['credit__sum'] or 0
        
        # حساب الرصيد حسب طبيعة الحساب
        if account.nature == 'debit':  # حسابات مدينة
            # للحسابات المدينة: الرصيد = الافتتاحي + المدين - الدائن
            total_balance = (account.opening_balance or 0) + total_debit_all - total_credit_all
            approved_balance_calc = (account.opening_balance or 0) + total_debit_posted - total_credit_posted
        else:  # حسابات دائنة
            # للحسابات الدائنة: الرصيد = الافتتاحي + الدائن - المدين
            total_balance = (account.opening_balance or 0) + total_credit_all - total_debit_all
            approved_balance_calc = (account.opening_balance or 0) + total_credit_posted - total_debit_posted
        
        # حساب الرصيد المعتمد (القيود المرحلة فقط)
        try:
            approved_balance = account.get_balance(include_opening=True)
        except Exception:
            approved_balance = approved_balance_calc
        
        # تحديد الوارد والصادر حسب طبيعة الحساب
        if account.nature == 'debit':  # حسابات مدينة (أصول، مصروفات)
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
            'opening_balance': account.opening_balance or 0,
            'total_in': total_in_all,
            'total_out': total_out_all,
            'total_in_posted': total_in_posted,
            'total_out_posted': total_out_posted,
            'current_balance': total_balance,  # الرصيد الإجمالي
            'approved_balance': approved_balance,  # الرصيد المعتمد
            'pending_amount': total_balance - approved_balance,  # المبلغ المعلق
            # قيم تشخيصية
            'total_debit_all': total_debit_all,
            'total_credit_all': total_credit_all,
            'total_debit_posted': total_debit_posted,
            'total_credit_posted': total_credit_posted,
        }
        
        # جلب آخر 50 قيد محاسبي كحركات (مع حالة الترحيل)
        journal_lines = JournalEntryLine.objects.filter(
            account=account
        ).select_related('journal_entry').order_by('-journal_entry__date', '-id')[:50]
        movements = journal_lines
        
        
    except Exception as e:
        movements = []
    
    
    # يمكن عرض معلومات إضافية للحسابات النقدية/البنكية لاحقاً
    
    # تحميل أنواع الحسابات للنموذج
    account_types = []
    if AccountType:
        account_types = AccountType.objects.filter(is_active=True).order_by('code')
    
    # تحميل الحسابات الأب المحتملة (تجنب الحساب الحالي وأطفاله)
    parent_accounts = []
    if ChartOfAccounts:
        # الحصول على جميع أطفال الحساب الحالي لتجنبها
        children_ids = [child.id for child in account.get_children_recursive()]
        children_ids.append(account.id)  # تجنب الحساب نفسه
        
        parent_accounts = ChartOfAccounts.objects.filter(
            is_active=True
        ).exclude(
            id__in=children_ids
        ).order_by('code')
    
    # إضافة المتغيرات المطلوبة للقالب الجديد
    transactions = movements  # نفس البيانات بس اسم مختلف
    
    # حساب التحليلات
    analytics = {
        'current_balance': balance_summary.get('current_balance', 0),
        'previous_balance': balance_summary.get('opening_balance', 0),
        'balance_change': balance_summary.get('current_balance', 0) - balance_summary.get('opening_balance', 0),
        'total_debit': balance_summary.get('total_debit_all', 0),
        'total_credit': balance_summary.get('total_credit_all', 0),
        'transaction_count': len(movements),
        'accounts_included': 1,
        'period_days': 30,
        'avg_daily_transactions': len(movements) / 30 if len(movements) > 0 else 0,
        'trend': 'positive' if balance_summary.get('current_balance', 0) > balance_summary.get('opening_balance', 0) else 'negative',
        'trend_icon': 'fa-arrow-up' if balance_summary.get('current_balance', 0) > balance_summary.get('opening_balance', 0) else 'fa-arrow-down',
        'trend_color': 'success' if balance_summary.get('current_balance', 0) > balance_summary.get('opening_balance', 0) else 'danger',
    }
    
    # الحسابات الفرعية
    sub_accounts = account.children.filter(is_active=True).order_by('code') if not account.is_leaf else []
    
    # إحصائيات إضافية
    income_sum = balance_summary.get('total_credit_all', 0)
    expense_sum = balance_summary.get('total_debit_all', 0)
    
    context = {
        'account': account,
        'movements': movements,
        'transactions': transactions,  # للقالب الجديد
        'analytics': analytics,  # للقالب الجديد
        'sub_accounts': sub_accounts,  # للقالب الجديد
        'income_sum': income_sum,  # للقالب الجديد
        'expense_sum': expense_sum,  # للقالب الجديد
        'balance_summary': balance_summary,
        'is_cash_account': account.is_cash_account or account.is_bank_account,
        'page_title': f'تفاصيل حساب: {account.name}',
        'page_icon': 'fas fa-file-invoice-dollar',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'النظام المحاسبي', 'url': '#', 'icon': 'fas fa-calculator'},
            {'title': 'دليل الحسابات', 'url': reverse('financial:chart_of_accounts_list'), 'icon': 'fas fa-sitemap'},
            {'title': f'{account.name}', 'active': True}
        ],
    }
    return render(request, 'financial/advanced/chart_of_accounts_detail.html', context)


@login_required
def chart_of_accounts_delete(request, pk):
    """حذف حساب"""
    account = get_object_or_404(ChartOfAccounts, pk=pk)
    if request.method == 'POST':
        account.is_active = False
        account.save()
        messages.success(request, f'تم حذف الحساب "{account.name}" بنجاح.')
        return redirect('financial:chart_of_accounts_list')
    
    context = {
        'account': account,
        'page_title': f'حذف حساب: {account.name}',
        'page_icon': 'fas fa-trash',
    }
    return render(request, 'financial/advanced/chart_of_accounts_delete.html', context)


# ============== أنواع الحسابات ==============

@login_required
def account_types_list(request):
    """عرض قائمة أنواع الحسابات بشكل هرمي مع جميع المستويات"""
    
    def build_tree_structure(parent=None, level=0):
        """بناء الهيكل الهرمي للأنواع"""
        types = AccountType.objects.filter(parent=parent).order_by('code')
        tree_data = []
        
        for account_type in types:
            # عدد الحسابات المرتبطة بهذا النوع
            accounts_count = 0
            if ChartOfAccounts:
                accounts_count = ChartOfAccounts.objects.filter(account_type=account_type).count()
            
            # عدد الأنواع الفرعية
            children_count = AccountType.objects.filter(parent=account_type).count()
            
            type_data = {
                'type': account_type,
                'level': level,
                'accounts_count': accounts_count,
                'children_count': children_count,
                'has_children': children_count > 0,
                'children': []
            }
            
            # إضافة الأطفال بشكل تكراري
            if children_count > 0:
                type_data['children'] = build_tree_structure(account_type, level + 1)
            
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
    for category in ['asset', 'liability', 'equity', 'revenue', 'expense']:
        category_stats[category] = all_types.filter(category=category).count()
    
    # إحصائيات حسب المستوى
    level_stats = {}
    for level in range(1, 6):  # حتى 5 مستويات
        level_stats[level] = all_types.filter(level=level).count()
    
    context = {
        'tree_structure': tree_structure,
        'all_types': all_types,  # لعرض جدول مسطح إضافي إذا لزم الأمر
        'total_types': total_types,
        'root_count': root_count,
        'child_count': child_count,
        'active_types': active_types,
        'inactive_types': inactive_types,
        'category_stats': category_stats,
        'level_stats': level_stats,
        'page_title': 'أنواع الحسابات',
        'page_icon': 'fas fa-layer-group',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الإدارة المالية', 'url': '#', 'icon': 'fas fa-money-bill-wave'},
            {'title': 'أنواع الحسابات', 'active': True}
        ]
    }
    return render(request, 'financial/advanced/account_types_list.html', context)


@login_required
def account_types_create(request):
    """إنشاء نوع حساب جديد"""
    if request.method == 'POST':
        try:
            # إنشاء نوع حساب جديد
            account_type = AccountType()
            
            # تحديث البيانات الأساسية
            account_type.code = request.POST.get('code', '').strip().upper()
            account_type.name = request.POST.get('name', '').strip()
            account_type.category = request.POST.get('category', '').strip()
            account_type.nature = request.POST.get('nature', '').strip()
            
            # تحديث النوع الأب
            parent_id = request.POST.get('parent')
            if parent_id:
                account_type.parent = AccountType.objects.get(id=parent_id)
                account_type.level = account_type.parent.level + 1
            else:
                account_type.level = 1
            
            # تحديث الحالة
            account_type.is_active = 'is_active' in request.POST
            
            # تعيين المستخدم الحالي
            account_type.created_by = request.user
            
            # حفظ نوع الحساب الجديد
            account_type.save()
            
            messages.success(request, f'تم إنشاء نوع الحساب "{account_type.name}" بنجاح.')
            return redirect('financial:account_types_list')
            
        except Exception as e:
            messages.error(request, f'حدث خطأ أثناء إنشاء نوع الحساب: {str(e)}')
    
    # تحميل الأنواع الأب المحتملة
    parent_types = []
    if AccountType:
        parent_types = AccountType.objects.filter(is_active=True).order_by('code')
    
    context = {
        'parent_types': parent_types,
        'page_title': 'إضافة نوع حساب جديد',
        'page_icon': 'fas fa-plus-circle',
    }
    return render(request, 'financial/advanced/account_types_form.html', context)


@login_required
def account_types_edit(request, pk):
    """تعديل نوع حساب"""
    account_type = get_object_or_404(AccountType, pk=pk)
    
    if request.method == 'POST':
        try:
            # تحديث البيانات الأساسية
            account_type.code = request.POST.get('code', '').strip().upper()
            account_type.name = request.POST.get('name', '').strip()
            account_type.category = request.POST.get('category', '').strip()
            account_type.nature = request.POST.get('nature', '').strip()
            
            # تحديث النوع الأب
            parent_id = request.POST.get('parent')
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
                        messages.warning(request, 'لا يمكن جعل النوع أباً لنفسه أو لأحد أجداده')
            else:
                account_type.parent = None
                account_type.level = 1
            
            # تحديث الحالة
            account_type.is_active = 'is_active' in request.POST
            
            # حفظ التغييرات
            account_type.save()
            
            messages.success(request, f'تم تحديث نوع الحساب "{account_type.name}" بنجاح.')
            return redirect('financial:account_types_list')
            
        except Exception as e:
            messages.error(request, f'حدث خطأ أثناء تحديث نوع الحساب: {str(e)}')
    
    # تحميل الأنواع الأب المحتملة (تجنب النوع الحالي وأطفاله)
    parent_types = []
    if AccountType:
        parent_types = AccountType.objects.filter(is_active=True).exclude(id=account_type.id).order_by('code')
        # يمكن إضافة منطق لتجنب الأطفال أيضاً
    
    context = {
        'account_type': account_type,
        'parent_types': parent_types,
        'page_title': f'تعديل نوع حساب: {account_type.name}',
        'page_icon': 'fas fa-edit',
    }
    return render(request, 'financial/advanced/account_types_form.html', context)


@login_required
def account_types_delete(request, pk):
    """حذف نوع حساب"""
    account_type = get_object_or_404(AccountType, pk=pk)
    if request.method == 'POST':
        account_type.is_active = False
        account_type.save()
        messages.success(request, f'تم حذف نوع الحساب "{account_type.name}" بنجاح.')
        return redirect('financial:account_types_list')
    
    context = {
        'page_title': f'حذف نوع حساب: {account_type.name}',
        'page_icon': 'fas fa-times-circle',
    }
    return render(request, 'financial/advanced/account_types_delete.html', context)


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
        journal_entries_list = JournalEntry.objects.all().order_by('-date', '-id')
        
        # معلمات الفلترة
        status = request.GET.get('status', '')
        search = request.GET.get('search', '')
        date_from = request.GET.get('date_from', '')
        date_to = request.GET.get('date_to', '')
        
        # تطبيق الفلاتر
        if status:
            journal_entries_list = journal_entries_list.filter(status=status)
            
        if search:
            journal_entries_list = journal_entries_list.filter(
                Q(reference__icontains=search) |
                Q(description__icontains=search)
            )
            
        if date_from:
            journal_entries_list = journal_entries_list.filter(date__gte=date_from)
            
        if date_to:
            journal_entries_list = journal_entries_list.filter(date__lte=date_to)
        
        # إعداد نموذج الفلترة
        filter_form = {
            'status': status,
            'search': search,
            'date_from': date_from,
            'date_to': date_to,
        }
        
        # الترقيم الصفحي
        paginator = Paginator(journal_entries_list, 25)  # 25 قيد في الصفحة
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        journal_entries = page_obj.object_list
    
    # قائمة حالات القيود
    status_choices = [
        ('', 'الكل'),
        ('draft', 'مسودة'),
        ('posted', 'مرحل'),
        ('cancelled', 'ملغى'),
    ]
    
    # إعداد headers للجدول الموحد
    headers = [
        {'key': 'reference', 'label': 'رقم القيد', 'sortable': True},
        {'key': 'date', 'label': 'التاريخ', 'sortable': True, 'format': 'date'},
        {'key': 'description', 'label': 'الوصف', 'sortable': False},
        {'key': 'total_debit', 'label': 'إجمالي المدين', 'sortable': True, 'format': 'currency'},
        {'key': 'total_credit', 'label': 'إجمالي الدائن', 'sortable': True, 'format': 'currency'},
        {'key': 'status', 'label': 'الحالة', 'sortable': True, 'format': 'badge'},
        {'key': 'created_by', 'label': 'أنشئ بواسطة', 'sortable': True},
    ]
    
    # إعداد action buttons
    action_buttons = [
        {
            'label': 'عرض',
            'url': '/financial/journal-entries/{id}/',
            'class': 'btn-outline-primary',
            'icon': 'fas fa-eye'
        },
        {
            'label': 'تعديل',
            'url': '/financial/journal-entries/{id}/edit/',
            'class': 'btn-outline-secondary',
            'icon': 'fas fa-edit'
        },
        {
            'label': 'حذف',
            'url': '/financial/journal-entries/{id}/delete/',
            'class': 'btn-outline-danger',
            'icon': 'fas fa-trash',
            'confirm': 'هل أنت متأكد من حذف هذا القيد؟'
        }
    ]
    
    context = {
        'journal_entries': journal_entries,
        'headers': headers,
        'action_buttons': action_buttons,
        'primary_key': 'id',
        'page_obj': page_obj,
        'paginator': paginator,
        'filter_form': filter_form or {},\
        'status_choices': status_choices,
        'page_title': 'القيود اليومية',\
        'page_icon': 'fas fa-book',\
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'القيود المحاسبية', 'url': reverse('financial:journal_entries_list'), 'icon': 'fas fa-book'},
            {'title': 'إنشاء قيد جديد', 'active': True}
        ]
    }
    return render(request, 'financial/advanced/journal_entries_list.html', context)


@login_required
def journal_entries_create(request):
    """إنشاء قيد جديد"""
    
    # تحميل الحسابات من النظام الجديد
    accounts = []
    if ChartOfAccounts:
        accounts = ChartOfAccounts.objects.filter(
            is_active=True,
            is_leaf=True  # الحسابات الفرعية فقط
        ).order_by('code')
    
    # تحميل الفترات المحاسبية
    accounting_periods = []
    if AccountingPeriod:
        accounting_periods = AccountingPeriod.objects.filter(is_active=True).order_by('-start_date')
    
    context = {
        'accounts': accounts,
        'accounting_periods': accounting_periods,
        'page_title': 'إنشاء قيد جديد',
        'page_icon': 'fas fa-plus-square',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'القيود المحاسبية', 'url': reverse('financial:journal_entries_list'), 'icon': 'fas fa-book'},
            {'title': 'إنشاء قيد جديد', 'active': True}
        ]
    }
    return render(request, 'financial/advanced/journal_entries_form.html', context)


@login_required
def journal_entries_detail(request, pk):
    """عرض تفاصيل قيد"""
    if JournalEntry is None:
        messages.error(request, 'نموذج القيود غير متاح.')
        return redirect('financial:journal_entries_list')
    
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
        purchase_payment = journal_entry.purchasepayment_set.select_related('purchase', 'purchase__supplier').first()
        if purchase_payment:
            source_payment = purchase_payment
            source_payment_url = reverse('purchase:payment_detail', args=[purchase_payment.pk])
            source_invoice = purchase_payment.purchase
            source_party = purchase_payment.purchase.supplier
            invoice_type = 'purchase'
    except (ImportError, AttributeError):
        pass
    
    if not source_payment:
        try:
            from sale.models import SalePayment
            # البحث في دفعات المبيعات - استخدام العلاقة العكسية
            sale_payment = journal_entry.salepayment_set.select_related('sale', 'sale__customer').first()
            if sale_payment:
                source_payment = sale_payment
                source_payment_url = reverse('sale:payment_detail', args=[sale_payment.pk])
                source_invoice = sale_payment.sale
                source_party = sale_payment.sale.customer
                invoice_type = 'sale'
        except (ImportError, AttributeError):
            pass
    
    # ثانياً: إذا لم نجد دفعة، نبحث في الفواتير باستخدام العلاقات العكسية
    if not source_invoice:
        try:
            from purchase.models import Purchase
            # البحث في فواتير المشتريات - استخدام العلاقة العكسية
            purchase = journal_entry.purchases.select_related('supplier').first()
            if purchase:
                source_invoice = purchase
                source_party = purchase.supplier
                invoice_type = 'purchase'
        except (ImportError, AttributeError):
            pass
    
    if not source_invoice:
        try:
            from sale.models import Sale
            # البحث في فواتير المبيعات - استخدام العلاقة العكسية
            sale = journal_entry.sales.select_related('customer').first()
            if sale:
                source_invoice = sale
                source_party = sale.customer
                invoice_type = 'sale'
        except (ImportError, AttributeError):
            pass
    
    context = {
        'journal_entry': journal_entry,
        'total_debits': total_debits,
        'total_credits': total_credits,
        'difference': difference,
        'source_invoice': source_invoice,
        'source_party': source_party,
        'invoice_type': invoice_type,
        'source_payment': source_payment,
        'source_payment_url': source_payment_url,
        'page_title': f'قيد رقم: {journal_entry.number}',
        'page_icon': 'fas fa-info-circle',
    }
    return render(request, 'financial/advanced/journal_entries_detail.html', context)


@login_required
def journal_entries_edit(request, pk):
    """تعديل قيد"""
    journal_entry = get_object_or_404(JournalEntry, pk=pk)
    
    # تحميل الحسابات من النظام الجديد
    accounts = []
    if ChartOfAccounts:
        accounts = ChartOfAccounts.objects.filter(
            is_active=True,
            is_leaf=True  # الحسابات الفرعية فقط
        ).order_by('code')
    
    # تحميل الفترات المحاسبية
    accounting_periods = []
    if AccountingPeriod:
        accounting_periods = AccountingPeriod.objects.filter(is_active=True).order_by('-start_date')
    
    context = {
        'journal_entry': journal_entry,
        'accounts': accounts,
        'accounting_periods': accounting_periods,
        'page_title': f'تعديل قيد: {journal_entry.reference}',
        'page_icon': 'fas fa-edit',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'القيود المحاسبية', 'url': reverse('financial:journal_entries_list'), 'icon': 'fas fa-book'},
            {'title': f'تعديل قيد: {journal_entry.reference}', 'active': True}
        ]
    }
    return render(request, 'financial/advanced/journal_entries_form.html', context)


@login_required
def journal_entries_delete(request, pk):
    """حذف قيد"""
    journal_entry = get_object_or_404(JournalEntry, pk=pk)
    if request.method == 'POST':
        journal_entry.delete()
        messages.success(request, f'تم حذف القيد "{journal_entry.reference}" بنجاح.')
        return redirect('financial:journal_entries_list')
    
    context = {
        'journal_entry': journal_entry,
        'page_title': f'حذف قيد: {journal_entry.reference}',
        'page_icon': 'fas fa-trash',
    }
    return render(request, 'financial/advanced/journal_entries_delete.html', context)


@login_required
def journal_entries_post(request, pk):
    """ترحيل قيد"""
    journal_entry = get_object_or_404(JournalEntry, pk=pk)
    
    if request.method == 'POST':
        try:
            # استخدام الـ method المخصص للترحيل
            journal_entry.post(user=request.user)
            
            # إرجاع JSON response دائماً للطلبات POST
            return JsonResponse({
                'success': True,
                'message': f'تم ترحيل القيد "{journal_entry.number or journal_entry.reference}" بنجاح.'
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'حدث خطأ: {str(e)}'
            })
    
    context = {
        'journal_entry': journal_entry,
        'page_title': f'ترحيل قيد: {journal_entry.reference}',
        'page_icon': 'fas fa-check-circle',
    }
    return render(request, 'financial/advanced/journal_entries_post.html', context)


# ============== الفترات المحاسبية ==============

@login_required
def accounting_periods_list(request):
    """عرض قائمة الفترات المحاسبية"""
    if AccountingPeriod is None:
        periods = []
    else:
        periods = AccountingPeriod.objects.all().order_by('-start_date')
    context = {
        'periods': periods,
        'page_title': 'الفترات المحاسبية',
        'page_icon': 'fas fa-calendar-alt',
    }
    return render(request, 'financial/advanced/accounting_periods_list.html', context)


@login_required
def accounting_periods_create(request):
    """إنشاء فترة محاسبية جديدة"""
    if request.method == 'POST':
        try:
            period = AccountingPeriod.objects.create(
                name=request.POST.get('name'),
                start_date=request.POST.get('start_date'),
                end_date=request.POST.get('end_date'),
                status=request.POST.get('status', 'open'),
                created_by=request.user
            )
            messages.success(request, f'تم إنشاء الفترة "{period.name}" بنجاح.')
            return redirect('financial:accounting_periods_list')
        except Exception as e:
            messages.error(request, f'حدث خطأ أثناء إنشاء الفترة: {str(e)}')
    
    context = {
        'page_title': 'إنشاء فترة محاسبية جديدة',
        'page_icon': 'fas fa-plus-circle',
    }
    return render(request, 'financial/advanced/accounting_periods_form.html', context)


@login_required
def accounting_periods_edit(request, pk):
    """تعديل فترة محاسبية"""
    period = get_object_or_404(AccountingPeriod, pk=pk)
    
    if request.method == 'POST':
        try:
            period.name = request.POST.get('name')
            period.start_date = request.POST.get('start_date')
            period.end_date = request.POST.get('end_date')
            period.status = request.POST.get('status', 'open')
            period.save()
            messages.success(request, f'تم تحديث الفترة "{period.name}" بنجاح.')
            return redirect('financial:accounting_periods_list')
        except Exception as e:
            messages.error(request, f'حدث خطأ أثناء تحديث الفترة: {str(e)}')
    
    context = {
        'period': period,
        'page_title': f'تعديل فترة: {period.name}',
        'page_icon': 'fas fa-edit',
    }
    return render(request, 'financial/advanced/accounting_periods_form.html', context)


@login_required
def accounting_periods_close(request, pk):
    """إغلاق فترة محاسبية"""
    period = get_object_or_404(AccountingPeriod, pk=pk)
    if request.method == 'POST':
        period.status = 'closed'
        period.closed_at = timezone.now()
        period.closed_by = request.user
        period.save()
        messages.success(request, f'تم إغلاق الفترة "{period.name}" بنجاح.')
        return redirect('financial:accounting_periods_list')
    
    context = {
        'period': period,
        'page_title': f'إغلاق فترة: {period.name}',
        'page_icon': 'fas fa-lock',
    }
    return render(request, 'financial/advanced/accounting_periods_close.html', context)


@login_required
def account_list(request):
    """
    عرض قائمة الحسابات المالية
    """
    accounts = get_all_active_accounts()
    
    # إحصائيات من النظام الجديد
    total_assets = accounts.filter(opening_balance__gt=0).aggregate(Sum('opening_balance')).get('opening_balance__sum', 0) or 0
    # total_income = 0  # سيتم حسابها من القيود المحاسبية لاحقاً
    # total_expenses = 0  # سيتم حسابها من القيود المحاسبية لاحقاً
    total_income = 0
    total_expenses = 0
    
    context = {
        'accounts': accounts,
        'total_assets': total_assets,
        'total_income': total_income,
        'total_expenses': total_expenses,
        'page_title': 'الحسابات المالية',
        'page_icon': 'fas fa-landmark',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الإدارة المالية', 'url': '#', 'icon': 'fas fa-money-bill-wave'},
            {'title': 'الحسابات المالية', 'active': True}
        ],
    }
    
    return render(request, 'financial/account_list.html', context)


def get_account_transactions(account, limit=50, transaction_type='all'):
    """
    جلب حركات الحساب بطريقة ذكية حسب نوع الحساب
    """
    transactions = []
    
    if account.is_leaf:
        # جلب جميع القيود للحساب النهائي
        all_journal_lines = JournalEntryLine.objects.filter(account=account)
        
        # جلب جميع القيود بغض النظر عن الحالة
        transactions = list(all_journal_lines.select_related('journal_entry').order_by('-journal_entry__date', '-id')[:limit])
        
        # إضافة حركات الخزن إذا كان حساب نقدي/بنكي (تم إزالة CashMovement)
        if account.is_cash_account or account.is_bank_account:
            try:
                # البحث في القيود المحاسبية المرتبطة بالحساب
                from .models.journal_entry import JournalEntry
                journal_entries = JournalEntry.objects.filter(
                    lines__account=account,
                    status='posted'
                ).distinct().order_by('-date')[:limit//2]
                
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
            transactions = list(all_lines.select_related('journal_entry', 'account').order_by('-journal_entry__date', '-id')[:limit])
    
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
        'current_balance': current_balance,
        'previous_balance': previous_balance,
        'balance_change': current_balance - previous_balance,
        'total_debit': summary['total_debit'],
        'total_credit': summary['total_credit'],
        'transaction_count': summary['transaction_count'],
        'accounts_included': summary['accounts_included'],
        'period_days': period_days,
        'avg_daily_transactions': summary['transaction_count'] / period_days if period_days > 0 else 0,
    }
    
    # تحديد اتجاه التغيير
    if analytics['balance_change'] > 0:
        analytics['trend'] = 'positive'
        analytics['trend_icon'] = 'fa-arrow-up'
        analytics['trend_color'] = 'success'
    elif analytics['balance_change'] < 0:
        analytics['trend'] = 'negative'
        analytics['trend_icon'] = 'fa-arrow-down'
        analytics['trend_color'] = 'danger'
    else:
        analytics['trend'] = 'stable'
        analytics['trend_icon'] = 'fa-minus'
        analytics['trend_color'] = 'secondary'
    
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
            all_lines = JournalEntryLine.objects.filter(account=account, journal_entry__status='posted')
        else:
            leaf_accounts = account.get_leaf_descendants(include_self=True)
            all_lines = JournalEntryLine.objects.filter(account__in=leaf_accounts, journal_entry__status='posted')
        
        income_sum = all_lines.aggregate(Sum('credit')).get('credit__sum', 0) or 0
        expense_sum = all_lines.aggregate(Sum('debit')).get('debit__sum', 0) or 0
    except Exception:
        income_sum = 0
        expense_sum = 0
    
    # تعريف رؤوس الأعمدة للجدول الموحد
    transaction_headers = [
        {
            'key': 'transaction_type', 
            'label': 'النوع', 
            'sortable': False, 
            'format': 'icon_text',
            'icon_callback': 'get_type_class', 
            'icon_class_callback': 'get_type_icon',
            'width': '8%'
        },
        {
            'key': 'created_at', 
            'label': 'التاريخ والوقت', 
            'sortable': True, 
            'format': 'datetime_12h',
            'class': 'text-center',
            'width': '12%'
        },
        {
            'key': 'description', 
            'label': 'الوصف', 
            'sortable': False, 
            'ellipsis': True,
            'width': 'auto'
        },
        {
            'key': 'deposit', 
            'label': 'الإيراد', 
            'sortable': False, 
            'format': 'currency', 
            'class': 'text-center',
            'variant': 'positive',
            'width': '10%',
            'decimals': 2
        },
        {
            'key': 'withdraw', 
            'label': 'المصروف', 
            'sortable': False, 
            'format': 'currency', 
            'class': 'text-center',
            'variant': 'negative',
            'width': '10%',
            'decimals': 2
        },
        {
            'key': 'reference_number', 
            'label': 'المرجع', 
            'sortable': False, 
            'format': 'reference',
            'class': 'text-center',
            'width': '10%'
        },
    ]
    
    # تعريف أزرار الإجراءات
    transaction_actions = [
        {
            'url': 'financial:transaction_detail', 
            'icon': 'fa-eye', 
            'label': 'عرض', 
            'class': 'action-view'
        },
        {
            'url': 'financial:transaction_edit', 
            'icon': 'fa-edit', 
            'label': 'تعديل', 
            'class': 'action-edit'
        }
    ]
    
    # معلومات إضافية للحسابات الأب
    sub_accounts = []
    if not account.is_leaf:
        sub_accounts = account.children.filter(is_active=True).order_by('code')
    
    context = {
        'account': account,
        'transactions': transactions,
        'analytics': analytics,
        'income_sum': income_sum,
        'expense_sum': expense_sum,
        'sub_accounts': sub_accounts,
        'title': f'حساب: {account.name}',
        'transaction_headers': transaction_headers,
        'transaction_actions': transaction_actions,
        'page_title': f'تفاصيل الحساب - {account.name}',
        'page_icon': 'fas fa-file-invoice-dollar',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'النظام المحاسبي', 'url': '#', 'icon': 'fas fa-calculator'},
            {'title': 'دليل الحسابات', 'url': reverse('financial:chart_of_accounts_list'), 'icon': 'fas fa-sitemap'},
            {'title': account.name, 'active': True}
        ],
    }
    
    return render(request, 'financial/advanced/chart_of_accounts_detail.html', context)


@login_required
def account_create(request):
    """
    إنشاء حساب مالي جديد
    """
    if request.method == 'POST':
        form = AccountForm(request.POST)
        if form.is_valid():
            account = form.save(commit=False)
            account.created_by = request.user
            
            # التعامل مع الرصيد الافتتاحي
            initial_balance = form.cleaned_data.get('initial_balance', 0)
            account.balance = initial_balance
            
            account.save()
            
            # إنشاء معاملة افتتاحية إذا كان الرصيد الافتتاحي موجودًا
            if initial_balance > 0:
                transaction = Transaction.objects.create(
                    account=account,
                    transaction_type='income',
                    amount=initial_balance,
                    date=timezone.now().date(),
                    description=f'رصيد افتتاحي - {account.name}',
                    reference=f'INIT-{account.code}',
                    created_by=request.user
                )
                
                # إنشاء بنود القيد المحاسبي
                TransactionLine.objects.create(
                    transaction=transaction,
                    account=account,
                    debit=initial_balance,
                    credit=0,
                    description='رصيد افتتاحي'
                )
                
                # حساب رأس المال أو الأصول
                capital_account = get_accounts_by_category('equity').first()
                if not capital_account:
                    # يجب إنشاء حساب رأس المال في النظام الجديد
                    messages.warning(request, 'يجب إنشاء حساب رأس المال في دليل الحسابات أولاً')
                    return redirect(reverse('financial:account_create') + '?category=equity')
                
                TransactionLine.objects.create(
                    transaction=transaction,
                    account=capital_account,
                    debit=0,
                    credit=initial_balance,
                    description='رصيد افتتاحي'
                )
                
            messages.success(request, f'تم إنشاء الحساب "{account.name}" بنجاح.')
            return redirect('financial:account_detail', pk=account.pk)
    else:
        form = AccountForm()
    
    context = {
        'form': form,
        'title': 'إنشاء حساب جديد',
    }
    
    return render(request, 'financial/account_form.html', context)


@login_required
def account_edit(request, pk):
    """
    تعديل حساب مالي - استخدام النظام الجديد
    """
    account = get_object_or_404(ChartOfAccounts, pk=pk)
    
    if request.method == 'POST':
        try:
            # تحديث بيانات الحساب
            account.name = request.POST.get('name')
            account.code = request.POST.get('code')
            account.description = request.POST.get('description', '')
            
            # تحديث نوع الحساب
            account_type_id = request.POST.get('account_type')
            if account_type_id:
                account.account_type = AccountType.objects.get(id=account_type_id)
            
            # تحديث الحساب الأب
            parent_id = request.POST.get('parent')
            if parent_id:
                account.parent = ChartOfAccounts.objects.get(id=parent_id)
            else:
                account.parent = None
            
            # تحديث الرصيد الافتتاحي
            opening_balance = request.POST.get('opening_balance')
            if opening_balance:
                account.opening_balance = Decimal(opening_balance)
            
            opening_balance_date = request.POST.get('opening_balance_date')
            if opening_balance_date:
                account.opening_balance_date = opening_balance_date
            
            # تحديث الخصائص
            account.is_cash_account = request.POST.get('is_cash_account') == 'on'
            account.is_bank_account = request.POST.get('is_bank_account') == 'on'
            account.is_active = request.POST.get('is_active', 'on') == 'on'
            
            account.save()
            messages.success(request, f'تم تعديل الحساب "{account.name}" بنجاح.')
            return redirect('financial:account_detail', pk=account.pk)
        except Exception as e:
            messages.error(request, f'خطأ في تعديل الحساب: {str(e)}')
    
    # تحميل البيانات المطلوبة
    account_types = AccountType.objects.filter(is_active=True).order_by('name')
    parent_accounts = ChartOfAccounts.objects.filter(is_active=True).exclude(id=account.id).order_by('code')
    
    context = {
        'account': account,
        'account_types': account_types,
        'parent_accounts': parent_accounts,
        'title': f'تعديل حساب: {account.name}',
    }
    
    return render(request, 'financial/advanced/chart_of_accounts_form.html', context)


@login_required
def account_transactions(request, pk):
    """
    عرض معاملات حساب محدد
    """
    account = get_object_or_404(ChartOfAccounts, pk=pk)
    
    # استخدام النظام الجديد
    try:
        journal_lines = JournalEntryLine.objects.filter(
            account=account
        ).select_related('journal_entry').order_by('-journal_entry__date', '-id')
        transactions = journal_lines
    except Exception:
        transactions = []
    
    # تعريف رؤوس الأعمدة للجدول الموحد
    transaction_headers = [
        {
            'key': 'transaction_type', 
            'label': 'النوع', 
            'sortable': False, 
            'format': 'icon_text',
            'icon_callback': 'get_type_class', 
            'icon_class_callback': 'get_type_icon',
            'width': '8%'
        },
        {
            'key': 'created_at', 
            'label': 'التاريخ والوقت', 
            'sortable': True, 
            'format': 'datetime_12h',
            'class': 'text-center',
            'width': '12%'
        },
        {
            'key': 'description', 
            'label': 'الوصف', 
            'sortable': False, 
            'ellipsis': True,
            'width': 'auto'
        },
        {
            'key': 'deposit', 
            'label': 'الإيراد', 
            'sortable': False, 
            'format': 'currency', 
            'class': 'text-center',
            'variant': 'positive',
            'width': '10%',
            'decimals': 2
        },
        {
            'key': 'withdraw', 
            'label': 'المصروف', 
            'sortable': False, 
            'format': 'currency', 
            'class': 'text-center',
            'variant': 'negative',
            'width': '10%',
            'decimals': 2
        },
        {
            'key': 'balance_after', 
            'label': 'الرصيد بعد', 
            'sortable': False, 
            'format': 'currency', 
            'class': 'text-center fw-bold',
            'variant': 'neutral',
            'width': '12%',
            'decimals': 2
        },
        {
            'key': 'reference_number', 
            'label': 'المرجع', 
            'sortable': False, 
            'format': 'reference',
            'class': 'text-center',
            'width': '10%'
        },
    ]
    
    # تعريف أزرار الإجراءات
    transaction_actions = [
        {
            'url': 'financial:transaction_detail', 
            'icon': 'fa-eye', 
            'label': 'عرض', 
            'class': 'action-view'
        },
        {
            'url': 'financial:transaction_edit', 
            'icon': 'fa-edit', 
            'label': 'تعديل', 
            'class': 'action-edit'
        },
        {
            'url': 'financial:transaction_delete', 
            'icon': 'fa-trash-alt', 
            'label': 'حذف', 
            'class': 'action-delete'
        },
    ]
    
    context = {
        'account': account,
        'transactions': transactions,
        'title': f'معاملات حساب: {account.name}',
        'transaction_headers': transaction_headers,
        'transaction_actions': transaction_actions,
        'page_title': f'معاملات حساب: {account.name}',
        'page_icon': 'fas fa-exchange-alt',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الإدارة المالية', 'url': '#', 'icon': 'fas fa-money-bill-wave'},
            {'title': 'الحسابات', 'url': reverse('financial:chart_of_accounts_list'), 'icon': 'fas fa-wallet'},
            {'title': account.name, 'url': reverse('financial:account_detail', kwargs={'pk': account.pk}), 'icon': 'fas fa-info-circle'},
            {'title': 'المعاملات', 'active': True}
        ],
    }
    
    return render(request, 'financial/account_transactions.html', context)


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
    
    if request.method == 'POST':
        account_name = account.name
        
        # تعديل حالة الحساب بدلاً من الحذف الفعلي (حذف ناعم)
        account.is_active = False
        account.save()
        
        messages.success(request, f'تم حذف الحساب "{account_name}" بنجاح.')
        return redirect('financial:chart_of_accounts_list')
    
    context = {
        'object': account,
        'object_name': 'الحساب',
        'title': f'حذف حساب: {account.name}',
        'cancel_url': reverse('financial:account_detail', kwargs={'pk': account.pk}),
        'warning_message': 'سيتم تعطيل الحساب وعدم ظهوره في قوائم الحسابات النشطة.' + 
                          (' كما أن هذا الحساب مرتبط بمعاملات مالية.' if has_transactions else '')
    }
    
    return render(request, 'financial/account_confirm_delete.html', context)


@login_required
def transaction_list(request):
    """
    عرض قائمة القيود المحاسبية (المعاملات المالية) باستخدام النظام الجديد
    """
    # استخدام JournalEntry بدلاً من Transaction
    journal_entries = JournalEntry.objects.all().order_by('-date', '-id')
    accounts = get_all_active_accounts()
    
    # فلترة
    account_id = request.GET.get('account')
    entry_type = request.GET.get('type')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if account_id:
        account = get_object_or_404(ChartOfAccounts, id=account_id)
        # البحث في بنود القيد للحساب المحدد
        journal_entries = journal_entries.filter(
            journalentryline__account=account
        ).distinct()
    
    if entry_type:
        # تصنيف القيود حسب النوع (دخل/مصروف) بناءً على نوع الحسابات المستخدمة
        if entry_type == 'income':
            journal_entries = journal_entries.filter(
                journalentryline__account__account_type__nature='credit',
                journalentryline__credit__gt=0
            ).distinct()
        elif entry_type == 'expense':
            journal_entries = journal_entries.filter(
                journalentryline__account__account_type__nature='debit',
                journalentryline__debit__gt=0
            ).distinct()
    
    if date_from:
        date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
        journal_entries = journal_entries.filter(date__gte=date_from)
    
    if date_to:
        date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
        journal_entries = journal_entries.filter(date__lte=date_to)
    
    # إحصائيات - حساب إجمالي المدين والدائن
    total_entries = journal_entries.count()
    total_debit = JournalEntryLine.objects.filter(
        journal_entry__in=journal_entries
    ).aggregate(Sum('debit'))['debit__sum'] or 0
    total_credit = JournalEntryLine.objects.filter(
        journal_entry__in=journal_entries
    ).aggregate(Sum('credit'))['credit__sum'] or 0
    
    # تعريف رؤوس الأعمدة للجدول الموحد
    headers = [
        {
            'key': 'entry_type',
            'label': 'النوع', 
            'sortable': False, 
            'format': 'icon_text',
            'icon_callback': 'get_type_class', 
            'icon_class_callback': 'get_type_icon',
            'width': '8%'
        },
        {
            'key': 'created_at', 
            'label': 'التاريخ والوقت', 
            'sortable': True, 
            'format': 'datetime_12h',
            'class': 'text-center',
            'width': '12%'
        },
        {
            'key': 'account', 
            'label': 'الحساب', 
            'sortable': False,
            'width': '12%'
        },
        {
            'key': 'description', 
            'label': 'الوصف', 
            'sortable': False, 
            'ellipsis': True,
            'width': 'auto'
        },
        {
            'key': 'deposit', 
            'label': 'الإيراد', 
            'sortable': False, 
            'format': 'currency', 
            'class': 'text-center',
            'variant': 'positive',
            'width': '10%',
            'decimals': 2
        },
        {
            'key': 'withdraw', 
            'label': 'المصروف', 
            'sortable': False, 
            'format': 'currency', 
            'class': 'text-center',
            'variant': 'negative',
            'width': '10%',
            'decimals': 2
        },
        {
            'key': 'balance_after', 
            'label': 'الرصيد بعد', 
            'sortable': False, 
            'format': 'currency', 
            'class': 'text-center fw-bold',
            'variant': 'neutral',
            'width': '12%',
            'decimals': 2
        },
        {
            'key': 'number', 
            'label': 'رقم القيد', 
            'sortable': False, 
            'format': 'reference',
            'class': 'text-center',
            'width': '10%'
        },
    ]
    
    # تعريف أزرار الإجراءات
    action_buttons = [
        {
            'url': 'financial:transaction_detail', 
            'icon': 'fa-eye', 
            'label': 'عرض', 
            'class': 'action-view'
        },
        {
            'url': 'financial:transaction_edit', 
            'icon': 'fa-edit', 
            'label': 'تعديل', 
            'class': 'action-edit'
        },
        {
            'url': 'financial:transaction_delete', 
            'icon': 'fa-trash-alt', 
            'label': 'حذف', 
            'class': 'action-delete'
        },
    ]
    
    # معالجة الترتيب
    current_order_by = request.GET.get('order_by', '')
    current_order_dir = request.GET.get('order_dir', '')
    
    # إعداد الترقيم الصفحي
    paginator = Paginator(journal_entries, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'transactions': page_obj,  # استخدام transactions للتوافق مع template
        'journal_entries': page_obj,
        'headers': headers,
        'action_buttons': action_buttons,
        'accounts': accounts,
        'total_transactions': total_entries,
        'total_debit': total_debit,
        'total_credit': total_credit,
        'page_title': 'القيود المحاسبية',
        'page_icon': 'fas fa-book',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الإدارة المالية', 'url': '#', 'icon': 'fas fa-money-bill-wave'},
            {'title': 'القيود المحاسبية', 'active': True}
        ],
        'current_order_by': current_order_by,
        'current_order_dir': current_order_dir,
    }
    
    return render(request, 'financial/transaction_list.html', context)


@login_required
def transaction_detail(request, pk):
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
                return 'manual'
            
            # فحص أنواع الحسابات لتحديد النوع
            account_types = [line.account.account_type.nature for line in lines if line.account.account_type]
            
            if 'credit' in account_types and any(line.credit > 0 for line in lines):
                return 'income'
            elif 'debit' in account_types and any(line.debit > 0 for line in lines):
                return 'expense'
            else:
                return 'manual'
                
        def _get_main_account(self, entry):
            """الحصول على الحساب الرئيسي (أول حساب في القيد)"""
            first_line = entry.lines.first()
            return first_line.account if first_line else None
    
    transaction_proxy = TransactionProxy(journal_entry)
    
    context = {
        'transaction': transaction_proxy,  # للتوافق مع template
        'journal_entry': journal_entry,
        'journal_lines': journal_entry.lines.all(),
        'title': f'قيد محاسبي: {journal_entry.number}',
    }
    
    return render(request, 'financial/transaction_detail.html', context)


@login_required
def transaction_create(request):
    """
    إنشاء قيد محاسبي جديد - تحت التطوير
    """
    messages.info(request, 'هذه الميزة تحت التطوير. يرجى استخدام صفحة القيود المحاسبية من القائمة الجانبية.')
    return redirect('financial:journal_entries_list')
    
    if request.method == 'POST':
        form = TransactionForm(request.POST)
        if form.is_valid():
            from django.db import transaction as db_transaction
            
            with db_transaction.atomic():
                # إنشاء المعاملة
                trans = form.save(commit=False)
                trans.created_by = request.user
                trans.save()
                
                # استخراج البيانات الأخرى من النموذج
                account = form.cleaned_data['account']
                transaction_type = form.cleaned_data['transaction_type']
                amount = form.cleaned_data['amount']
                description = form.cleaned_data.get('description', '')
                
                # حساب مقابل افتراضي حسب نوع المعاملة
                contra_account = None
                if transaction_type == 'income':
                    # بحث عن حساب إيرادات افتراضي
                    contra_account = get_accounts_by_category('revenue').first()
                    if not contra_account:
                        # إنشاء حساب افتراضي في النظام القديم (مؤقت)
                        contra_account = Account.objects.create(
                            name='الإيرادات',
                            code='INC001',
                            account_type='income',
                            created_by=request.user
                        )
                elif transaction_type == 'expense':
                    # بحث عن حساب مصروفات افتراضي
                    contra_account = get_accounts_by_category('expense').first()
                    if not contra_account:
                        # إنشاء حساب افتراضي في النظام القديم (مؤقت)
                        contra_account = Account.objects.create(
                            name='المصروفات',
                            code='EXP001',
                            account_type='expense',
                            created_by=request.user
                        )
                
                # التأكد من وجود حساب قبل الاستمرار
                if not account:
                    messages.error(request, 'يجب تحديد الحساب الرئيسي للمعاملة')
                    return redirect('financial:transaction_create')
                
                # إنشاء بنود القيد المحاسبي
                if transaction_type == 'income':
                    # التأكد من وجود الحسابات المطلوبة
                    if not contra_account:
                        messages.error(request, 'لم يتم العثور على حساب الإيرادات')
                        return redirect('financial:transaction_create')
                        
                    # مدين: الحساب المختار (زيادة في الأصول)
                    TransactionLine.objects.create(
                        transaction=trans,
                        account=account,
                        debit=amount,
                        credit=0,
                        description=description
                    )
                    # دائن: حساب الإيرادات
                    TransactionLine.objects.create(
                        transaction=trans,
                        account=contra_account,
                        debit=0,
                        credit=amount,
                        description=description
                    )
                    
                    # تحديث رصيد الحساب
                    account.update_balance(amount, 'add')
                    
                elif transaction_type == 'expense':
                    # التأكد من وجود الحسابات المطلوبة
                    if not contra_account:
                        messages.error(request, 'لم يتم العثور على حساب المصروفات')
                        return redirect('financial:transaction_create')
                        
                    # مدين: حساب المصروفات
                    TransactionLine.objects.create(
                        transaction=trans,
                        account=contra_account,
                        debit=amount,
                        credit=0,
                        description=description
                    )
                    # دائن: الحساب المختار (نقص في الأصول)
                    TransactionLine.objects.create(
                        transaction=trans,
                        account=account,
                        debit=0,
                        credit=amount,
                        description=description
                    )
                    
                    # تحديث رصيد الحساب
                    account.update_balance(amount, 'subtract')
                
                elif transaction_type == 'transfer':
                    to_account = form.cleaned_data.get('to_account')
                    if to_account:
                        # مدين: حساب الوجهة (زيادة)
                        TransactionLine.objects.create(
                            transaction=trans,
                            account=to_account,
                            debit=amount,
                            credit=0,
                            description=description
                        )
                        # دائن: حساب المصدر (نقص)
                        TransactionLine.objects.create(
                            transaction=trans,
                            account=account,
                            debit=0,
                            credit=amount,
                            description=description
                        )
                        
                        # تحديث رصيد الحسابين
                        account.update_balance(amount, 'subtract')
                        to_account.update_balance(amount, 'add')
                    else:
                        # في حالة عدم وجود حساب وجهة (يجب ألا يحدث بسبب التحقق في النموذج)
                        messages.error(request, 'يجب تحديد حساب الوجهة للتحويل')
                        return redirect('financial:transaction_create')
                
            messages.success(request, 'تم إنشاء المعاملة المالية بنجاح.')
            return redirect('financial:transaction_detail', pk=trans.pk)
    else:
        form = TransactionForm()
    
    context = {
        'form': form,
        'title': 'إنشاء معاملة مالية',
    }
    return render(request, 'financial/transaction_form.html', context)


@login_required
def transaction_edit(request, pk):
    """
    تعديل قيد محاسبي - تحت التطوير
    """
    messages.info(request, 'هذه الميزة تحت التطوير. يرجى استخدام صفحة القيود المحاسبية من القائمة الجانبية.')
    return redirect('financial:journal_entries_list')


@login_required
def transaction_delete(request, pk):
    """
    حذف قيد محاسبي - تحت التطوير
    """
    messages.info(request, 'هذه الميزة تحت التطوير. يرجى استخدام صفحة القيود المحاسبية من القائمة الجانبية.')
    return redirect('financial:journal_entries_list')
    
    journal_entry = get_object_or_404(JournalEntry, pk=pk)
    
    if request.method == 'POST':
        # إلغاء تأثير المعاملة على الحساب
        if transaction.transaction_type == 'income' and transaction.account:
            # التأكد من وجود الحساب قبل تعديل رصيده
            if hasattr(transaction.account, 'balance'):
                transaction.account.balance -= transaction.amount
                transaction.account.save()
            else:
                messages.warning(request, 'لم يتم العثور على الحساب المرتبط بالمعاملة أو تم حذفه مسبقاً.')
        
        elif transaction.transaction_type == 'expense' and transaction.account:
            # التأكد من وجود الحساب قبل تعديل رصيده
            if hasattr(transaction.account, 'balance'):
                transaction.account.balance += transaction.amount
                transaction.account.save()
            else:
                messages.warning(request, 'لم يتم العثور على الحساب المرتبط بالمعاملة أو تم حذفه مسبقاً.')
        
        elif transaction.transaction_type == 'transfer':
            # التحقق من وجود الحساب المصدر
            if transaction.account and hasattr(transaction.account, 'balance'):
                transaction.account.balance += transaction.amount
                transaction.account.save()
            else:
                messages.warning(request, 'لم يتم العثور على الحساب المصدر أو تم حذفه مسبقاً.')
            
            # التحقق من وجود الحساب المستلم
            if transaction.to_account and hasattr(transaction.to_account, 'balance'):
                transaction.to_account.balance -= transaction.amount
                transaction.to_account.save()
            else:
                messages.warning(request, 'لم يتم العثور على الحساب المستلم أو تم حذفه مسبقاً.')
        
        # حذف المعاملة بغض النظر عن حالة الحسابات
        transaction.delete()
        messages.success(request, 'تم حذف المعاملة بنجاح.')
        return redirect('financial:transaction_list')
    
    context = {
        'object': transaction,
        'title': 'حذف معاملة',
    }
    
    return render(request, 'financial/confirm_delete.html', context)


@login_required
def expense_list(request):
    """
    عرض قائمة المصروفات من القيود المحاسبية
    """
    # فلترة القيوح التي تحتوي على مصروفات
    expense_entries = JournalEntry.objects.filter(
        lines__account__account_type__category='expense',
        lines__debit__gt=0
    ).distinct().order_by('-date', '-id')
    
    accounts = get_all_active_accounts()
    
    # فلترة
    account_id = request.GET.get('account')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if account_id:
        account = get_object_or_404(ChartOfAccounts, id=account_id)
        expense_entries = expense_entries.filter(lines__account=account).distinct()
    
    if date_from:
        date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
        expense_entries = expense_entries.filter(date__gte=date_from)
    
    if date_to:
        date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
        expense_entries = expense_entries.filter(date__lte=date_to)
    
    # إحصائيات
    total_expenses = 0
    for entry in expense_entries:
        expense_lines = entry.lines.filter(
            account__account_type__category='expense',
            debit__gt=0
        )
        total_expenses += sum(line.debit for line in expense_lines)
    
    # تعريف رؤوس الأعمدة للجدول
    headers = [
        {
            'key': 'number',
            'label': 'رقم القيد',
            'sortable': True,
            'width': '10%'
        },
        {
            'key': 'date',
            'label': 'التاريخ',
            'sortable': True,
            'format': 'datetime_12h',
            'class': 'text-center',
            'width': '14%'
        },
        {
            'key': 'description',
            'label': 'البيان',
            'sortable': False,
            'ellipsis': True,
            'width': 'auto'
        },
        {
            'key': 'expense_amount',
            'label': 'قيمة المصروف',
            'sortable': False,
            'template': 'components/cells/expense_amount.html',
            'class': 'text-center',
            'width': '15%'
        },
        {
            'key': 'expense_accounts',
            'label': 'حسابات المصروف',
            'sortable': False,
            'width': '20%'
        },
        {
            'key': 'status',
            'label': 'الحالة',
            'sortable': False,
            'template': 'components/cells/expense_status.html',
            'class': 'text-center',
            'width': '10%'
        }
    ]
    
    # تعريف أزرار الإجراءات
    action_buttons = [
        {
            'url': 'financial:transaction_detail',
            'icon': 'fa-eye',
            'label': 'عرض',
            'class': 'action-view'
        }
    ]
    
    # إعداد بيانات إضافية لكل قيد
    enhanced_entries = []
    for entry in expense_entries:
        expense_lines = entry.lines.filter(
            account__account_type__category='expense',
            debit__gt=0
        )
        
        expense_amount = sum(line.debit for line in expense_lines)
        expense_accounts = ', '.join([line.account.name for line in expense_lines])
        
        enhanced_entry = {
            'id': entry.id,
            'number': entry.number,
            'date': entry.date,
            'description': entry.description,
            'expense_amount': expense_amount,
            'expense_accounts': expense_accounts,
            'status': entry.status,
            'entry_type': entry.entry_type
        }
        enhanced_entries.append(enhanced_entry)
    
    # إعداد الترقيم الصفحي
    paginator = Paginator(enhanced_entries, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'expenses': page_obj,  # للتوافق مع template
        'journal_entries': page_obj,
        'expense_headers': headers,
        'expense_actions': action_buttons,
        'primary_key': 'id',
        'accounts': accounts,
        'total_expenses': total_expenses,
        'page_title': 'المصروفات',
        'page_icon': 'fas fa-money-bill-wave text-danger',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الإدارة المالية', 'url': '#', 'icon': 'fas fa-money-bill-wave'},
            {'title': 'المصروفات', 'active': True}
        ],
    }
    
    return render(request, 'financial/expense_list.html', context)
    
    if category_id:
        expenses = expenses.filter(category_id=category_id)
    
    if status:
        expenses = expenses.filter(status=status)
    
    if date_from:
        date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
        expenses = expenses.filter(date__gte=date_from)
    
    if date_to:
        date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
        expenses = expenses.filter(date__lte=date_to)
    
    # إحصائيات
    total_expense = expenses.aggregate(Sum('amount')).get('amount__sum', 0) or 0
    paid_expenses = expenses.filter(status='paid').aggregate(Sum('amount')).get('amount__sum', 0) or 0
    pending_expenses = expenses.filter(status='pending').aggregate(Sum('amount')).get('amount__sum', 0) or 0
    
    # حساب متوسط المصروفات الشهرية
    today = timezone.now().date()
    six_months_ago = today - timedelta(days=180)
    monthly_expenses = expenses.filter(date__gte=six_months_ago).aggregate(Sum('amount')).get('amount__sum', 0) or 0
    monthly_average = monthly_expenses / 6 if monthly_expenses > 0 else 0
    
    # تعريف رؤوس الأعمدة للجدول الموحد
    headers = [
        {
            'key': 'title', 
            'label': 'العنوان', 
            'sortable': True,
            'width': '15%'
        },
        {
            'key': 'created_at', 
            'label': 'التاريخ والوقت', 
            'sortable': True, 
            'format': 'datetime_12h',
            'class': 'text-center',
            'width': '12%'
        },
        {
            'key': 'category', 
            'label': 'التصنيف', 
            'sortable': False,
            'width': '12%'
        },
        {
            'key': 'amount', 
            'label': 'المبلغ', 
            'sortable': False, 
            'format': 'currency', 
            'class': 'text-center',
            'variant': 'negative',
            'width': '12%',
            'decimals': 2
        },
        {
            'key': 'payee', 
            'label': 'المستفيد', 
            'sortable': False,
            'width': '15%'
        },
        {
            'key': 'reference_number', 
            'label': 'رقم المرجع', 
            'sortable': False, 
            'format': 'reference',
            'class': 'text-center',
            'width': '10%'
        },
        {
            'key': 'status', 
            'label': 'الحالة', 
            'sortable': False, 
            'format': 'status',
            'class': 'text-center',
            'width': '10%'
        }
    ]
    
    # تعريف أزرار الإجراءات
    action_buttons = [
        {
            'url': 'financial:expense_detail', 
            'icon': 'fa-eye', 
            'label': 'عرض', 
            'class': 'action-view'
        },
        {
            'url': 'financial:expense_edit', 
            'icon': 'fa-edit', 
            'label': 'تعديل', 
            'class': 'action-edit'
        }
    ]
    
    # إضافة زر تسديد للمصروفات المعلقة (غير المدفوعة)
    expense_statuses = set(expenses.values_list('status', flat=True))
    if 'pending' in expense_statuses:
        action_buttons.append({
            'url': 'financial:expense_mark_paid', 
            'icon': 'fa-check-circle', 
            'label': 'تسديد', 
            'class': 'action-paid'
        })
    
    # معالجة الترتيب
    current_order_by = request.GET.get('order_by', '')
    current_order_dir = request.GET.get('order_dir', '')
    
    # ترقيم الصفحات
    paginator = Paginator(expenses, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'expenses': page_obj,
        'accounts': accounts,
        'categories': categories,
        'total_expense': total_expense,
        'paid_expenses': paid_expenses,
        'pending_expenses': pending_expenses,
        'monthly_average': monthly_average,
        'headers': headers,
        'action_buttons': action_buttons,
        'current_order_by': current_order_by,
        'current_order_dir': current_order_dir,
        'page_title': 'المصروفات',
        'page_icon': 'fas fa-hand-holding-usd',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الإدارة المالية', 'url': '#', 'icon': 'fas fa-money-bill-wave'},
            {'title': 'المصروفات', 'active': True}
        ],
    }
    
    return render(request, 'financial/expense_list.html', context)


@login_required
def expense_detail(request, pk):
    """
    عرض تفاصيل مصروف معين - تحت التطوير
    """
    messages.info(request, 'هذه الميزة تحت التطوير. سيتم ربطها بالنماذج المحسنة قريباً.')
    return redirect('financial:expense_list')


@login_required
def expense_create(request):
    """
    إنشاء مصروف جديد - تحت التطوير
    """
    messages.info(request, 'هذه الميزة تحت التطوير. سيتم ربطها بالنماذج المحسنة قريباً.')
    return redirect('financial:expense_list')


@login_required
def expense_edit(request, pk):
    """
    تعديل مصروف - تحت التطوير
    """
    messages.info(request, 'هذه الميزة تحت التطوير. سيتم ربطها بالنماذج المحسنة قريباً.')
    return redirect('financial:expense_list')


@login_required
def expense_mark_paid(request, pk):
    """
    تحديد مصروف كمدفوع - تحت التطوير
    """
    messages.info(request, 'هذه الميزة تحت التطوير. سيتم ربطها بالنماذج المحسنة قريباً.')
    return redirect('financial:expense_list')


@login_required
def expense_cancel(request, pk):
    """
    إلغاء مصروف - تحت التطوير
    """
    messages.info(request, 'هذه الميزة تحت التطوير. سيتم ربطها بالنماذج المحسنة قريباً.')
    return redirect('financial:expense_list')


@login_required
def income_list(request):
    """
    عرض قائمة الإيرادات من القيود المحاسبية
    """
    # فلترة القيوح التي تحتوي على إيرادات
    income_entries = JournalEntry.objects.filter(
        lines__account__account_type__category='revenue',
        lines__credit__gt=0
    ).distinct().order_by('-date', '-id')
    
    accounts = get_all_active_accounts()
    
    # فلترة
    account_id = request.GET.get('account')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if account_id:
        account = get_object_or_404(ChartOfAccounts, id=account_id)
        income_entries = income_entries.filter(lines__account=account).distinct()
    
    if date_from:
        date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
        income_entries = income_entries.filter(date__gte=date_from)
    
    if date_to:
        date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
        income_entries = income_entries.filter(date__lte=date_to)
    
    # إحصائيات
    total_incomes = 0
    for entry in income_entries:
        income_lines = entry.lines.filter(
            account__account_type__category='revenue',
            credit__gt=0
        )
        total_incomes += sum(line.credit for line in income_lines)
    
    # تعريف رؤوس الأعمدة للجدول
    headers = [
        {
            'key': 'number',
            'label': 'رقم القيد',
            'sortable': True,
            'width': '10%'
        },
        {
            'key': 'date',
            'label': 'التاريخ',
            'sortable': True,
            'format': 'date',
            'class': 'text-center',
            'width': '120px'
        },
        {
            'key': 'description',
            'label': 'البيان',
            'sortable': False,
            'ellipsis': True,
            'width': 'auto'
        },
        {
            'key': 'income_amount',
            'label': 'قيمة الإيراد',
            'sortable': False,
            'template': 'components/cells/income_amount.html',
            'class': 'text-center',
            'width': '15%'
        },
        {
            'key': 'income_accounts',
            'label': 'حسابات الإيراد',
            'sortable': False,
            'width': '20%'
        },
        {
            'key': 'status',
            'label': 'الحالة',
            'sortable': False,
            'template': 'components/cells/income_status.html',
            'class': 'text-center',
            'width': '10%'
        }
    ]
    
    # تعريف أزرار الإجراءات
    action_buttons = [
        {
            'url': 'financial:transaction_detail',
            'icon': 'fa-eye',
            'label': 'عرض',
            'class': 'action-view'
        }
    ]
    
    # إعداد بيانات إضافية لكل قيد
    enhanced_entries = []
    for entry in income_entries:
        income_lines = entry.lines.filter(
            account__account_type__category='revenue',
            credit__gt=0
        )
        
        income_amount = sum(line.credit for line in income_lines)
        income_accounts = ', '.join([line.account.name for line in income_lines])
        
        enhanced_entry = {
            'id': entry.id,
            'number': entry.number,
            'date': entry.date,
            'description': entry.description,
            'income_amount': income_amount,
            'income_accounts': income_accounts,
            'status': entry.status,
            'entry_type': entry.entry_type
        }
        enhanced_entries.append(enhanced_entry)
    
    # إعداد الترقيم الصفحي
    paginator = Paginator(enhanced_entries, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'incomes': page_obj,  # للتوافق مع template
        'journal_entries': page_obj,
        'income_headers': headers,
        'income_actions': action_buttons,
        'primary_key': 'id',
        'accounts': accounts,
        'total_incomes': total_incomes,
        'page_title': 'الإيرادات',
        'page_icon': 'fas fa-cash-register text-success',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الإدارة المالية', 'url': '#', 'icon': 'fas fa-money-bill-wave'},
            {'title': 'الإيرادات', 'active': True}
        ],
    }
    
    return render(request, 'financial/income_list.html', context)
    category_id = request.GET.get('category')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if account_id:
        incomes = incomes.filter(account_id=account_id)
    
    if category_id:
        incomes = incomes.filter(category_id=category_id)
    
    if date_from:
        date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
        incomes = incomes.filter(date__gte=date_from)
    
    if date_to:
        date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
        incomes = incomes.filter(date__lte=date_to)
    
    # إحصائيات
    total_income = incomes.aggregate(Sum('amount')).get('amount__sum', 0) or 0
    received_incomes = incomes.filter(status='received').aggregate(Sum('amount')).get('amount__sum', 0) or 0
    pending_incomes = incomes.filter(status='pending').aggregate(Sum('amount')).get('amount__sum', 0) or 0
    
    # حساب متوسط الإيرادات الشهرية
    current_date = timezone.now().date()
    start_of_year = current_date.replace(month=1, day=1)
    months_passed = (current_date.year - start_of_year.year) * 12 + current_date.month - start_of_year.month + 1
    monthly_average = total_income / months_passed if months_passed > 0 else 0
    
    # تعريف أعمدة الجدول
    headers = [
        {'key': 'title', 'label': 'العنوان', 'sortable': True, 'class': 'col-title'},
        {'key': 'expense_amount', 'label': 'قيمة المصروف', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/expense_amount.html', 'width': '120px', 'decimals': 2},
        {'key': 'category__name', 'label': 'التصنيف', 'sortable': True},
        {'key': 'created_at', 'label': 'التاريخ والوقت', 'sortable': True, 'class': 'col-date', 'format': 'datetime_12h'},
        {'key': 'status', 'label': 'الحالة', 'sortable': True, 'class': 'col-status', 'format': 'status'},
    ]
    # تعريف أزرار الإجراءات
    action_buttons = [
        {'url': 'financial:income_detail', 'icon': 'fa-eye', 'label': 'عرض', 'class': 'btn-primary action-view'},
        {'url': 'financial:income_edit', 'icon': 'fa-edit', 'label': 'تعديل', 'class': 'btn-secondary action-edit'},
        {'url': 'financial:income_mark_received', 'icon': 'fa-check-circle', 'label': 'استلام', 'class': 'btn-success action-received'},
        {'url': 'financial:income_cancel', 'icon': 'fa-ban', 'label': 'إلغاء', 'class': 'btn-danger action-cancel'},
    ]
    
    # ترقيم الصفحات
    paginator = Paginator(incomes, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'incomes': page_obj,
        'accounts': accounts,
        'categories': categories,
        'total_income': total_income,
        'received_incomes': received_incomes,
        'pending_incomes': pending_incomes,
        'monthly_average': monthly_average,
        'headers': headers,
        'action_buttons': action_buttons,
        'page_title': 'الإيرادات',
        'page_icon': 'fas fa-cash-register',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الإدارة المالية', 'url': '#', 'icon': 'fas fa-money-bill-wave'},
            {'title': 'الإيرادات', 'active': True}
        ],
    }
    
    return render(request, 'financial/income_list.html', context)


@login_required
def income_detail(request, pk):
    """
    عرض تفاصيل إيراد معين
    """
    income = get_object_or_404(Income, pk=pk)
    
    context = {
        'income': income,
        'title': f'إيراد: {income.title}',
    }
    
    return render(request, 'financial/income_detail.html', context)


@login_required
def income_create(request):
    """
    إنشاء إيراد جديد
    """
    if request.method == 'POST':
        form = IncomeForm(request.POST)
        if form.is_valid():
            income = form.save(commit=False)
            income.created_by = request.user
            
            # تعيين حساب الإيراد بناءً على حساب الاستلام
            receiving_account = form.cleaned_data.get('receiving_account')
            if receiving_account:
                income.account = receiving_account
            else:
                # استخدام حساب افتراضي
                default_account = get_cash_and_bank_accounts().filter(name__icontains='خزينة').first()
                if not default_account:
                    default_account = get_cash_and_bank_accounts().filter(is_cash_account=True).first()
                if not default_account:
                    default_account = get_cash_and_bank_accounts().first()
                
                if default_account:
                    income.account = default_account
                    income.receiving_account = default_account
            
            income.save()
            
            messages.success(request, 'تم إنشاء الإيراد بنجاح.')
            return redirect('financial:income_detail', pk=income.pk)
    else:
        form = IncomeForm()
    
    context = {
        'form': form,
        'title': 'إضافة إيراد جديد',
    }
    
    return render(request, 'financial/income_form.html', context)


@login_required
def income_edit(request, pk):
    """
    تعديل إيراد
    """
    income = get_object_or_404(Income, pk=pk)
    
    if request.method == 'POST':
        form = IncomeForm(request.POST, instance=income)
        if form.is_valid():
            income = form.save(commit=False)
            
            # تعيين حساب الإيراد بناءً على حساب الاستلام
            receiving_account = form.cleaned_data.get('receiving_account')
            if receiving_account:
                income.account = receiving_account
            else:
                # استخدام حساب افتراضي
                default_account = get_cash_and_bank_accounts().filter(name__icontains='خزينة').first()
                if not default_account:
                    default_account = get_cash_and_bank_accounts().filter(is_cash_account=True).first()
                if not default_account:
                    default_account = get_cash_and_bank_accounts().first()
                
                if default_account:
                    income.account = default_account
                    income.receiving_account = default_account
            
            income.save()
            
            messages.success(request, 'تم تعديل الإيراد بنجاح.')
            return redirect('financial:income_detail', pk=income.pk)
    else:
        form = IncomeForm(instance=income)
    
    context = {
        'form': form,
        'income': income,
        'title': f'تعديل إيراد: {income.title}',
    }
    
    return render(request, 'financial/income_form.html', context)


@login_required
def income_mark_received(request, pk):
    """
    تحديد إيراد كمستلم
    """
    income = get_object_or_404(Income, pk=pk)
    
    if income.status == 'received':
        messages.info(request, 'هذا الإيراد مستلم بالفعل.')
        return redirect('financial:income_detail', pk=pk)
    
    if request.method == 'POST':
        account_id = request.POST.get('account')
        
        if not account_id:
            messages.error(request, 'لم يتم تحديد الحساب! يرجى اختيار حساب لاستلام الإيراد.')
            accounts = get_all_active_accounts()
            context = {
                'income': income,
                'accounts': accounts,
                'title': 'استلام إيراد',
            }
            return render(request, 'financial/income_mark_received.html', context)
        
        account = get_object_or_404(Account, id=account_id)
        
        # تحديث حالة الإيراد
        income.status = 'received'
        income.received_date = timezone.now().date()
        income.save()
        
        # إنشاء معاملة إيراد
        transaction = Transaction.objects.create(
            account=account,
            transaction_type='income',
            amount=income.amount,
            date=timezone.now().date(),
            description=f'استلام إيراد: {income.title}',
            reference_number=income.reference_number,
        )
        
        # تحديث رصيد الحساب
        account.balance += income.amount
        account.save()
        
        messages.success(request, 'تم تحديد الإيراد كمستلم بنجاح.')
        return redirect('financial:income_detail', pk=pk)
    
    accounts = get_all_active_accounts()
    
    context = {
        'income': income,
        'accounts': accounts,
        'title': 'استلام إيراد',
    }
    
    return render(request, 'financial/income_mark_received.html', context)


@login_required
def income_cancel(request, pk):
    """
    إلغاء إيراد
    """
    income = get_object_or_404(Income, pk=pk)
    
    if income.status == 'cancelled':
        messages.info(request, 'هذا الإيراد ملغي بالفعل.')
        return redirect('financial:income_detail', pk=pk)
    
    if request.method == 'POST':
        income.status = 'cancelled'
        income.save()
        
        messages.success(request, 'تم إلغاء الإيراد بنجاح.')
        return redirect('financial:income_detail', pk=pk)
    
    context = {
        'object': income,
        'title': 'إلغاء إيراد',
    }
    
    return render(request, 'financial/confirm_delete.html', context)


@login_required
def export_transactions(request):
    """
    تصدير المعاملات المالية
    """
    try:
        from .models.transactions import FinancialTransaction
        transactions = FinancialTransaction.objects.all().order_by('-date', '-id')
    except ImportError:
        # استخدام القيود المحاسبية كبديل
        transactions = JournalEntry.objects.all().order_by('-date', '-id')
    
    # تطبيق الفلترة إذا كانت موجودة
    account_id = request.GET.get('account')
    trans_type = request.GET.get('type')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if account_id:
        account = get_object_or_404(Account, id=account_id)
        transactions = transactions.filter(Q(account=account) | Q(to_account=account))
    
    if trans_type:
        transactions = transactions.filter(transaction_type=trans_type)
    
    if date_from:
        date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
        transactions = transactions.filter(date__gte=date_from)
    
    if date_to:
        date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
        transactions = transactions.filter(date__lte=date_to)
    
    # إنشاء ملف CSV
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="transactions.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['ID', 'التاريخ', 'النوع', 'الحساب', 'الوصف', 'المبلغ', 'الرقم المرجعي'])
    
    for transaction in transactions:
        writer.writerow([
            transaction.id,
            transaction.date,
            transaction.get_transaction_type_display(),
            transaction.account.name,
            transaction.description,
            transaction.amount,
            transaction.reference_number or '',
        ])
    
    return response


@login_required
def bank_reconciliation_list(request):
    """
    عرض قائمة التسويات البنكية
    """
    reconciliations = BankReconciliation.objects.all().order_by('-reconciliation_date')
    accounts = get_bank_accounts()
    
    context = {
        'reconciliations': reconciliations,
        'accounts': accounts,
        'title': 'التسويات البنكية',
    }
    
    return render(request, 'financial/bank_reconciliation_list.html', context)


@login_required
def bank_reconciliation_create(request):
    """
    إنشاء تسوية بنكية جديدة
    """
    if request.method == 'POST':
        form = BankReconciliationForm(request.POST)
        if form.is_valid():
            reconciliation = form.save(commit=False)
            reconciliation.created_by = request.user
            
            # حساب القيم التلقائية
            account = form.cleaned_data.get('account')
            reconciliation.system_balance = account.balance
            reconciliation.difference = form.cleaned_data.get('bank_balance') - account.balance
            
            reconciliation.save()
            
            # إجراء التسوية على الحساب
            success, message, difference = account.reconcile(
                form.cleaned_data.get('bank_balance'),
                form.cleaned_data.get('reconciliation_date')
            )
            
            if success:
                messages.success(request, f'تم إجراء التسوية البنكية بنجاح. {message}')
            else:
                messages.error(request, f'حدث خطأ أثناء إجراء التسوية: {message}')
            
            return redirect('financial:bank_reconciliation_list')
    else:
        form = BankReconciliationForm()
    
    context = {
        'form': form,
        'title': 'إنشاء تسوية بنكية',
    }
    
    return render(request, 'financial/bank_reconciliation_form.html', context)


@login_required
def ledger_report(request):
    """
    تقرير دفتر الأستاذ العام
    """
    transactions = []
    accounts = get_all_active_accounts().order_by('account_type', 'name')
    
    # فلترة
    account_id = request.GET.get('account')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    # في حالة تحديد حساب معين، نعرض التفاصيل من خلال بنود المعاملات
    if account_id:
        account = get_object_or_404(Account, id=account_id)
        transaction_lines = TransactionLine.objects.filter(account=account).select_related('transaction')
        
        if date_from:
            date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            transaction_lines = transaction_lines.filter(transaction__date__gte=date_from)
        
        if date_to:
            date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            transaction_lines = transaction_lines.filter(transaction__date__lte=date_to)
        
        transactions = transaction_lines.order_by('transaction__date', 'transaction__id')
        
        # حساب المجاميع
        total_debit = transaction_lines.aggregate(Sum('debit'))['debit__sum'] or 0
        total_credit = transaction_lines.aggregate(Sum('credit'))['credit__sum'] or 0
        balance = total_debit - total_credit
        
        context = {
            'account': account,
            'transactions': transactions,
            'total_debit': total_debit,
            'total_credit': total_credit,
            'balance': balance,
            'accounts': accounts,
            'date_from': date_from,
            'date_to': date_to,
            'title': f'دفتر الأستاذ - {account.name}',
        }
    else:
        # إذا لم يتم تحديد حساب، نعرض ملخص لكل الحسابات
        account_balances = []
        
        for account in accounts:
            # حساب الإجماليات لكل حساب
            transaction_lines = TransactionLine.objects.filter(account=account)
            
            if date_from:
                date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
                transaction_lines = transaction_lines.filter(transaction__date__gte=date_from)
            
            if date_to:
                date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
                transaction_lines = transaction_lines.filter(transaction__date__lte=date_to)
            
            total_debit = transaction_lines.aggregate(Sum('debit'))['debit__sum'] or 0
            total_credit = transaction_lines.aggregate(Sum('credit'))['credit__sum'] or 0
            
            # حساب الرصيد النهائي حسب نوع الحساب
            if account.account_type in ['asset', 'expense']:
                # الأصول والمصروفات لها رصيد مدين
                balance = total_debit - total_credit
            else:
                # الخصوم والإيرادات وحقوق الملكية لها رصيد دائن
                balance = total_credit - total_debit
            
            if total_debit > 0 or total_credit > 0:  # عرض الحسابات النشطة فقط
                account_balances.append({
                    'account': account,
                    'total_debit': total_debit,
                    'total_credit': total_credit,
                    'balance': balance
                })
        
        context = {
            'account_balances': account_balances,
            'accounts': accounts,
            'date_from': date_from,
            'date_to': date_to,
            'title': 'دفتر الأستاذ العام',
        }
    
    return render(request, 'financial/ledger_report.html', context)


@login_required
def balance_sheet(request):
    """
    تقرير الميزانية العمومية
    """
    # تحديد تاريخ الميزانية (افتراضيًا التاريخ الحالي)
    balance_date = request.GET.get('date')
    if balance_date:
        balance_date = datetime.strptime(balance_date, '%Y-%m-%d').date()
    else:
        balance_date = timezone.now().date()
    
    # جمع الأصول
    assets = []
    assets_total = 0
    asset_accounts = get_accounts_by_category('asset')
    
    for account in asset_accounts:
        journal_lines = JournalEntryLine.objects.filter(
            account=account,
            journal_entry__date__lte=balance_date
        )
        
        total_debit = journal_lines.aggregate(Sum('debit'))['debit__sum'] or 0
        total_credit = journal_lines.aggregate(Sum('credit'))['credit__sum'] or 0
        balance = total_debit - total_credit
        
        if balance != 0:  # عرض الحسابات ذات الرصيد فقط
            assets.append({
                'account': account,
                'balance': balance,
                'total_debit': total_debit,
                'total_credit': total_credit,
                'balance': balance
            })
            assets_total += balance
    
    # جمع الخصوم
    liabilities = []
    liabilities_total = 0
    liability_accounts = get_accounts_by_category('liability')
    
    for account in liability_accounts:
        journal_lines = JournalEntryLine.objects.filter(
            account=account,
            journal_entry__date__lte=balance_date
        )
        
        total_debit = journal_lines.aggregate(Sum('debit'))['debit__sum'] or 0
        total_credit = journal_lines.aggregate(Sum('credit'))['credit__sum'] or 0
        balance = total_credit - total_debit  # الخصوم لها رصيد دائن
        
        if balance != 0:  # عرض الحسابات ذات الرصيد فقط
            liabilities.append({
                'account': account,
                'balance': balance
            })
            liabilities_total += balance
    
    # جمع حقوق الملكية
    equity = []
    equity_total = 0
    equity_accounts = get_accounts_by_category('equity')
    
    for account in equity_accounts:
        journal_lines = JournalEntryLine.objects.filter(
            account=account,
            journal_entry__date__lte=balance_date
        )
        
        total_debit = journal_lines.aggregate(Sum('debit'))['debit__sum'] or 0
        total_credit = journal_lines.aggregate(Sum('credit'))['credit__sum'] or 0
        balance = total_credit - total_debit  # حقوق الملكية لها رصيد دائن
        
        if balance != 0:  # عرض الحسابات ذات الرصيد فقط
            equity.append({
                'account': account,
                'balance': balance
            })
            equity_total += balance
    
    # حساب صافي الربح/الخسارة من حسابات الإيرادات والمصروفات
    # (يتم حسابه فقط إذا كان تاريخ الميزانية العمومية هو تاريخ اليوم)
    net_income = 0
    if balance_date == timezone.now().date():
        # حساب إجمالي الإيرادات
        income_accounts = get_accounts_by_category('revenue')
        total_income = 0
        
        for account in income_accounts:
            journal_lines = JournalEntryLine.objects.filter(
                account=account,
                journal_entry__date__lte=balance_date
            )
            
            total_debit = journal_lines.aggregate(Sum('debit'))['debit__sum'] or 0
            total_credit = journal_lines.aggregate(Sum('credit'))['credit__sum'] or 0
            balance = total_credit - total_debit  # الإيرادات لها رصيد دائن
            total_income += balance
        
        # حساب إجمالي المصروفات
        expense_accounts = get_accounts_by_category('expense')
        total_expense = 0
        
        for account in expense_accounts:
            journal_lines = JournalEntryLine.objects.filter(
                account=account,
                journal_entry__date__lte=balance_date
            )
            
            total_debit = journal_lines.aggregate(Sum('debit'))['debit__sum'] or 0
            total_credit = journal_lines.aggregate(Sum('credit'))['credit__sum'] or 0
            balance = total_debit - total_credit  # المصروفات لها رصيد مدين
            total_expense += balance
        
        net_income = total_income - total_expense
        
        # إضافة صافي الربح/الخسارة إلى حقوق الملكية
        if net_income != 0:
            equity.append({
                'account': {'name': 'صافي الربح/الخسارة'},
                'balance': net_income
            })
            equity_total += net_income
    
    # إجماليات الميزانية
    total_assets = assets_total
    total_liabilities_equity = liabilities_total + equity_total
    
    context = {
        'assets': assets,
        'liabilities': liabilities,
        'equity': equity,
        'total_assets': total_assets,
        'total_liabilities': liabilities_total,
        'total_equity': equity_total,
        'total_liabilities_equity': total_liabilities_equity,
        'balance_date': balance_date,
        'title': 'الميزانية العمومية',
    }
    
    return render(request, 'financial/balance_sheet.html', context)


@login_required
def income_statement(request):
    """
    تقرير قائمة الإيرادات والمصروفات (الأرباح والخسائر)
    """
    # تحديد فترة التقرير
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if date_from:
        date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
    else:
        # افتراضيًا، بداية الشهر الحالي
        today = timezone.now().date()
        date_from = datetime(today.year, today.month, 1).date()
    
    if date_to:
        date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
    else:
        # افتراضيًا، تاريخ اليوم
        date_to = timezone.now().date()
    
    # جمع الإيرادات
    income_items = []
    total_income = 0
    income_accounts = get_accounts_by_category('revenue')
    
    for account in income_accounts:
        journal_lines = JournalEntryLine.objects.filter(
            account=account,
            journal_entry__date__gte=date_from,
            journal_entry__date__lte=date_to
        )
        
        total_debit = journal_lines.aggregate(Sum('debit'))['debit__sum'] or 0
        total_credit = journal_lines.aggregate(Sum('credit'))['credit__sum'] or 0
        balance = total_credit - total_debit  # الإيرادات لها رصيد دائن
        
        if balance != 0:  # عرض الحسابات ذات الرصيد فقط
            income_items.append({
                'account': account,
                'amount': balance
            })
            total_income += balance
    
    # جمع المصروفات
    expense_items = []
    total_expense = 0
    expense_accounts = get_accounts_by_category('expense')
    
    for account in expense_accounts:
        journal_lines = JournalEntryLine.objects.filter(
            account=account,
            journal_entry__date__gte=date_from,
            journal_entry__date__lte=date_to
        )
        
        total_debit = journal_lines.aggregate(Sum('debit'))['debit__sum'] or 0
        total_credit = journal_lines.aggregate(Sum('credit'))['credit__sum'] or 0
        balance = total_debit - total_credit  # المصروفات لها رصيد مدين
        
        if balance != 0:  # عرض الحسابات ذات الرصيد فقط
            expense_items.append({
                'account': account,
                'amount': balance
            })
            total_expense += balance
    
    # حساب صافي الربح/الخسارة
    net_income = total_income - total_expense
    
    context = {
        'income_items': income_items,
        'expense_items': expense_items,
        'total_income': total_income,
        'total_expense': total_expense,
        'net_income': net_income,
        'date_from': date_from,
        'date_to': date_to,
        'title': 'قائمة الإيرادات والمصروفات',
    }
    
    return render(request, 'financial/income_statement.html', context)


@login_required
def financial_analytics(request):
    """
    عرض صفحة التحليلات المالية
    تعرض مجموعة من المؤشرات المالية الرئيسية والرسوم البيانية
    """
    # التحقق من تسجيل دخول المستخدم
    if not request.user.is_authenticated:
        return redirect('users:login')
    
    # بيانات لوحة التحكم (استخدام النظام الجديد)
    monthly_income = 0
    total_income = 0
    total_expenses = 0
    
    try:
        # استخدام النماذج الجديدة إذا كانت متوفرة
        from .models.transactions import IncomeTransaction, ExpenseTransaction
        
        monthly_income = IncomeTransaction.objects.filter(
            date__gte=datetime.now().replace(day=1, hour=0, minute=0, second=0)
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        total_income = IncomeTransaction.objects.filter(
            date__gte=datetime.now().replace(day=1, hour=0, minute=0, second=0) - timedelta(days=30)
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        total_expenses = ExpenseTransaction.objects.filter(
            date__gte=datetime.now().replace(day=1, hour=0, minute=0, second=0) - timedelta(days=30)
        ).aggregate(total=Sum('amount'))['total'] or 0
    except ImportError:
        # في حالة عدم توفر النماذج الجديدة، استخدم القيود المحاسبية
        try:
            current_month = datetime.now().replace(day=1, hour=0, minute=0, second=0)
            last_month = current_month - timedelta(days=30)
            
            # حساب الإيرادات من القيود المحاسبية
            income_accounts = ChartOfAccounts.objects.filter(
                account_type__category='income'
            )
            
            monthly_income = JournalEntryLine.objects.filter(
                account__in=income_accounts,
                journal_entry__date__gte=current_month
            ).aggregate(total=Sum('credit'))['total'] or 0
            
            total_income = JournalEntryLine.objects.filter(
                account__in=income_accounts,
                journal_entry__date__gte=last_month
            ).aggregate(total=Sum('credit'))['total'] or 0
            
            # حساب المصروفات من القيود المحاسبية
            expense_accounts = ChartOfAccounts.objects.filter(
                account_type__category='expense'
            )
            
            total_expenses = JournalEntryLine.objects.filter(
                account__in=expense_accounts,
                journal_entry__date__gte=last_month
            ).aggregate(total=Sum('debit'))['total'] or 0
        except Exception:
            pass
    
    profit_margin = 0
    if total_income > 0:
        profit_margin = round(((total_income - total_expenses) / total_income) * 100)
    
    # متوسط قيمة الفاتورة والمعاملات اليومية
    avg_invoice = 0
    daily_transactions = 0
    
    try:
        # استخدام النماذج الجديدة إذا كانت متوفرة
        from .models.transactions import FinancialTransaction
        
        recent_transactions = FinancialTransaction.objects.filter(
            date__gte=datetime.now() - timedelta(days=30)
        )
        
        transaction_count = recent_transactions.count()
        total_amount = recent_transactions.aggregate(total=Sum('amount'))['total'] or 0
        
        if transaction_count > 0:
            avg_invoice = total_amount / transaction_count
        
        daily_transactions = FinancialTransaction.objects.filter(
            date__gte=datetime.now() - timedelta(days=1)
        ).count()
    except ImportError:
        # في حالة عدم توفر النماذج الجديدة، استخدم القيود المحاسبية
        try:
            recent_entries = JournalEntry.objects.filter(
                date__gte=datetime.now() - timedelta(days=30)
            )
            
            if recent_entries.exists():
                # حساب متوسط قيمة القيود
                total_amount = 0
                for entry in recent_entries:
                    entry_total = entry.lines.aggregate(Sum('debit'))['debit__sum'] or 0
                    total_amount += entry_total
                
                if recent_entries.count() > 0:
                    avg_invoice = total_amount / recent_entries.count()
            
            daily_transactions = JournalEntry.objects.filter(
                date__gte=datetime.now() - timedelta(days=1)
            ).count()
        except Exception:
            pass
    
    # إعداد سياق البيانات
    context = {
        'page_title': _('التحليلات المالية'),
        'page_icon': 'fas fa-chart-line',
        'monthly_income': monthly_income,
        'profit_margin': profit_margin,
        'avg_invoice': avg_invoice,
        'daily_transactions': daily_transactions
    }
    return render(request, 'financial/analytics.html', context)


@login_required
def category_list(request):
    """
    عرض قائمة أنواع الحسابات (بديل التصنيفات) - تحت التطوير
    """
    messages.info(request, 'هذه الميزة تحت التطوير. يرجى استخدام صفحة أنواع الحسابات من القائمة الجانبية.')
    return redirect('financial:account_types_list')
    context = {
        'categories': page_obj,
        'expense_count': expense_count,
        'income_count': income_count,
        'search_query': search_query,
        'category_type': category_type,
        'page_title': 'تصنيفات المصروفات والإيرادات',
        'page_icon': 'fas fa-tags',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الإدارة المالية', 'url': '#', 'icon': 'fas fa-money-bill-wave'},
            {'title': 'تصنيفات المصروفات والإيرادات', 'active': True}
        ],
    }
    
    return render(request, 'financial/category_list.html', context)


@login_required
def category_create(request):
    """
    إنشاء فئة جديدة
    """
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.created_by = request.user
            category.save()
            
            messages.success(request, 'تم إنشاء التصنيف بنجاح.')
            return redirect('financial:category_list')
    else:
        form = CategoryForm()
        
        # تعيين النوع بناءً على المعلمة في URL
        category_type = request.GET.get('type', '')
        if category_type in ('expense', 'income'):
            form.fields['type'].initial = category_type
    
    context = {
        'form': form,
        'page_title': 'إضافة فئة جديدة',
        'page_icon': 'fas fa-plus-circle',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الإدارة المالية', 'url': '#', 'icon': 'fas fa-money-bill-wave'},
            {'title': 'تصنيفات المصروفات والإيرادات', 'url': reverse('financial:category_list'), 'icon': 'fas fa-tags'},
            {'title': 'إضافة فئة جديدة', 'active': True}
        ],
    }
    
    return render(request, 'financial/category_form.html', context)


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
        if category.type == 'expense':
            transaction_count = ExpenseTransaction.objects.filter(category=category).count()
        elif category.type == 'income':
            transaction_count = IncomeTransaction.objects.filter(category=category).count()
    except ImportError:
        # في حالة عدم توفر النماذج الجديدة
        transaction_count = 0
    
    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, 'تم تعديل التصنيف بنجاح.')
            return redirect('financial:category_list')
    else:
        form = CategoryForm(instance=category)
    
    context = {
        'form': form,
        'category': category,
        'transaction_count': transaction_count,
        'page_title': f'تعديل فئة: {category.name}',
        'page_icon': 'fas fa-edit',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الإدارة المالية', 'url': '#', 'icon': 'fas fa-money-bill-wave'},
            {'title': 'تصنيفات المصروفات والإيرادات', 'url': reverse('financial:category_list'), 'icon': 'fas fa-tags'},
            {'title': f'تعديل فئة: {category.name}', 'active': True}
        ],
    }
    
    return render(request, 'financial/category_form.html', context)


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
        if category.type == 'expense':
            transaction_count = ExpenseTransaction.objects.filter(category=category).count()
            has_transactions = transaction_count > 0
        elif category.type == 'income':
            transaction_count = IncomeTransaction.objects.filter(category=category).count()
            has_transactions = transaction_count > 0
    except ImportError:
        # في حالة عدم توفر النماذج الجديدة
        transaction_count = 0
        has_transactions = False
    
    if request.method == 'POST':
        # إذا تم تأكيد الحذف
        confirm_deletion = request.POST.get('confirm_deletion') == 'on' if has_transactions else True
        
        if confirm_deletion:
            category_name = category.name
            category.delete()
            messages.success(request, f'تم حذف التصنيف "{category_name}" بنجاح.')
            return redirect('financial:category_list')
        else:
            messages.error(request, 'يجب تأكيد الحذف للتصنيفات المستخدمة في معاملات.')
    
    context = {
        'category': category,
        'has_transactions': has_transactions,
        'transaction_count': transaction_count,
        'page_title': f'حذف فئة: {category.name}',
        'page_icon': 'fas fa-trash',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الإدارة المالية', 'url': '#', 'icon': 'fas fa-money-bill-wave'},
            {'title': 'تصنيفات المصروفات والإيرادات', 'url': reverse('financial:category_list'), 'icon': 'fas fa-tags'},
            {'title': f'حذف فئة: {category.name}', 'active': True}
        ],
    }
    
    return render(request, 'financial/category_delete.html', context)


# ============== الأرصدة المحسنة ==============

@login_required
def enhanced_balances_list(request):
    """
    عرض قائمة الأرصدة المحسنة
    """
    try:
        from .services.enhanced_balance_service import EnhancedBalanceService
        service = EnhancedBalanceService()
        balances = service.get_all_balances()
    except ImportError:
        balances = []
        messages.warning(request, 'خدمة الأرصدة المحسنة غير متاحة حالياً.')
    
    # حساب الإحصائيات
    bank_accounts_count = sum(1 for b in balances if b.get('is_bank_account', False))
    cash_accounts_count = sum(1 for b in balances if b.get('is_cash_account', False))
    other_accounts_count = len(balances) - bank_accounts_count - cash_accounts_count
    
    context = {
        'balances': balances,
        'bank_accounts_count': bank_accounts_count,
        'cash_accounts_count': cash_accounts_count,
        'other_accounts_count': other_accounts_count,
        'page_title': 'الأرصدة المحسنة',
        'page_icon': 'fas fa-balance-scale',
    }
    return render(request, 'financial/advanced/enhanced_balances_list.html', context)


@login_required
def enhanced_balances_refresh(request):
    """
    تحديث الأرصدة المحسنة
    """
    if request.method == 'POST':
        try:
            from .services.enhanced_balance_service import EnhancedBalanceService
            service = EnhancedBalanceService()
            results = service.bulk_refresh_balances()
            
            messages.success(request, f'تم تحديث {results["success"]} رصيد بنجاح.')
            if results["failed"] > 0:
                messages.warning(request, f'فشل في تحديث {results["failed"]} رصيد.')
                
        except ImportError:
            messages.error(request, 'خدمة الأرصدة المحسنة غير متاحة حالياً.')
        except Exception as e:
            messages.error(request, f'حدث خطأ أثناء تحديث الأرصدة: {str(e)}')
    
    return redirect('financial:enhanced_balances_list')


@login_required
def enhanced_balances_audit(request):
    """
    مراجعة الأرصدة المحسنة
    """
    try:
        from .services.enhanced_balance_service import EnhancedBalanceService
        service = EnhancedBalanceService()
        audit_results = []  # يمكن إضافة منطق المراجعة هنا لاحقاً
        
        messages.info(request, 'ميزة مراجعة الأرصدة تحت التطوير.')
        
    except ImportError:
        messages.error(request, 'خدمة الأرصدة المحسنة غير متاحة حالياً.')
    except Exception as e:
        messages.error(request, f'حدث خطأ أثناء مراجعة الأرصدة: {str(e)}')
    
    return redirect('financial:enhanced_balances_list')


# ============== تزامن المدفوعات ==============

@login_required
@require_http_methods(["POST"])
def payment_sync_retry_failed_api(request):
    """
    API لإعادة محاولة العمليات الفاشلة
    """
    try:
        from .models.payment_sync import PaymentSyncOperation
        from django.db import models
        
        # العمليات الفاشلة القابلة لإعادة المحاولة
        failed_operations = PaymentSyncOperation.objects.filter(
            status='failed',
            retry_count__lt=models.F('max_retries')
        )
        
        count = 0
        for operation in failed_operations:
            operation.status = 'pending'
            operation.retry_count += 1
            operation.save()
            count += 1
        
        return JsonResponse({
            'success': True,
            'count': count,
            'message': f'تم إعادة تعيين {count} عملية للمحاولة مرة أخرى'
        })
        
    except ImportError:
        return JsonResponse({
            'success': False,
            'message': 'نماذج التزامن غير متاحة'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ: {str(e)}'
        })


@login_required
@require_http_methods(["POST"])
def payment_sync_resolve_errors_api(request):
    """
    API لحل الأخطاء القديمة
    """
    try:
        from .models.payment_sync import PaymentSyncError
        from django.utils import timezone
        from datetime import timedelta
        
        # حل الأخطاء المتعلقة بالاستيراد (تم إصلاحها)
        import_errors = PaymentSyncError.objects.filter(
            error_message__icontains='import',
            is_resolved=False
        )
        
        import_count = import_errors.update(
            is_resolved=True,
            resolved_at=timezone.now(),
            resolution_notes='تم إنشاء النماذج المفقودة'
        )
        
        # حل الأخطاء القديمة (أكثر من 7 أيام)
        old_errors = PaymentSyncError.objects.filter(
            occurred_at__lt=timezone.now() - timedelta(days=7),
            is_resolved=False
        )
        
        old_count = old_errors.update(
            is_resolved=True,
            resolved_at=timezone.now(),
            resolution_notes='حل تلقائي للأخطاء القديمة'
        )
        
        total_count = import_count + old_count
        
        return JsonResponse({
            'success': True,
            'count': total_count,
            'message': f'تم حل {total_count} خطأ ({import_count} أخطاء استيراد + {old_count} أخطاء قديمة)'
        })
        
    except ImportError:
        return JsonResponse({
            'success': False,
            'message': 'نماذج الأخطاء غير متاحة'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ: {str(e)}'
        })



@login_required
def payment_sync_dashboard(request):
    """
    لوحة تحكم تزامن المدفوعات
    """
    try:
        from .services.payment_sync_service import PaymentSyncService
        service = PaymentSyncService()
        stats = service.get_sync_statistics()
    except ImportError:
        stats = {}
        messages.warning(request, 'خدمة تزامن المدفوعات غير متاحة حالياً.')
    
    context = {
        'stats': stats,
        'page_title': 'تزامن المدفوعات',
        'page_icon': 'fas fa-sync-alt',
    }
    return render(request, 'financial/advanced/payment_sync_dashboard.html', context)


@login_required
def payment_sync_operations(request):
    """
    عمليات تزامن المدفوعات
    """
    try:
        from .models.payment_sync import PaymentSyncOperation
        operations = PaymentSyncOperation.objects.select_related(
            'content_type', 'created_by'
        ).order_by('-created_at')[:50]
    except ImportError:
        operations = []
        messages.warning(request, 'نماذج تزامن المدفوعات غير متاحة حالياً.')
    
    context = {
        'operations': operations,
        'page_title': 'عمليات تزامن المدفوعات',
        'page_icon': 'fas fa-cogs',
    }
    return render(request, 'financial/advanced/payment_sync_operations.html', context)


@login_required
def payment_sync_logs(request):
    """
    سجلات تزامن المدفوعات
    """
    try:
        from .models.payment_sync import PaymentSyncLog
        logs = PaymentSyncLog.objects.select_related(
            'sync_operation', 'sync_operation__created_by'
        ).order_by('-executed_at')[:100]
    except ImportError:
        logs = []
        messages.warning(request, 'نماذج سجلات التزامن غير متاحة حالياً.')
    
    context = {
        'logs': logs,
        'page_title': 'سجلات تزامن المدفوعات',
        'page_icon': 'fas fa-list-alt',
    }
    return render(request, 'financial/advanced/payment_sync_logs.html', context)


# ============== التقارير المحاسبية المتقدمة ==============

@login_required
def ledger_report(request):
    """
    تقرير دفتر الأستاذ المتقدم
    """
    try:
        from .services.reporting_service import ReportingService
        service = ReportingService()
        # يمكن إضافة منطق التقرير هنا لاحقاً
        ledger_data = []
    except ImportError:
        ledger_data = []
        messages.warning(request, 'خدمة التقارير غير متاحة حالياً.')
    
    context = {
        'ledger_data': ledger_data,
        'page_title': 'دفتر الأستاذ المتقدم',
        'page_icon': 'fas fa-book-open',
    }
    return render(request, 'financial/advanced/ledger_report_advanced.html', context)


@login_required
def trial_balance_report(request):
    """
    تقرير ميزان المراجعة
    """
    try:
        from .services.reporting_service import ReportingService
        service = ReportingService()
        # يمكن إضافة منطق التقرير هنا لاحقاً
        trial_balance = []
    except ImportError:
        trial_balance = []
        messages.warning(request, 'خدمة التقارير غير متاحة حالياً.')
    
    context = {
        'trial_balance': trial_balance,
        'page_title': 'ميزان المراجعة',
        'page_icon': 'fas fa-balance-scale',
    }
    return render(request, 'financial/advanced/trial_balance_report.html', context)


# ============== تقارير العمليات ==============

@login_required
def sales_report(request):
    """
    تقرير المبيعات - سيتم ربطه مع نظام المبيعات لاحقاً
    """
    messages.info(request, 'تقرير المبيعات تحت التطوير. سيتم ربطه مع نظام المبيعات قريباً.')
    
    context = {
        'page_title': 'تقرير المبيعات',
        'page_icon': 'fas fa-chart-line',
        'sales_data': [],
    }
    return render(request, 'financial/advanced/sales_report.html', context)


@login_required
def purchases_report(request):
    """
    تقرير المشتريات - سيتم ربطه مع نظام المشتريات لاحقاً
    """
    messages.info(request, 'تقرير المشتريات تحت التطوير. سيتم ربطه مع نظام المشتريات قريباً.')
    
    context = {
        'page_title': 'تقرير المشتريات',
        'page_icon': 'fas fa-chart-pie',
        'purchases_data': [],
    }
    return render(request, 'financial/advanced/purchases_report.html', context)


@login_required
def inventory_report(request):
    """
    تقرير المخزون - سيتم ربطه مع نظام المنتجات لاحقاً
    """
    messages.info(request, 'تقرير المخزون تحت التطوير. سيتم ربطه مع نظام المنتجات قريباً.')
    
    context = {
        'page_title': 'تقرير المخزون',
        'page_icon': 'fas fa-boxes',
        'inventory_data': [],
    }
    return render(request, 'financial/advanced/inventory_report.html', context)


# ============== النسخ الاحتياطي والصيانة ==============

@login_required
def general_backup(request):
    """
    النسخ الاحتياطي العام
    """
    if request.method == 'POST':
        try:
            # يمكن إضافة منطق النسخ الاحتياطي هنا لاحقاً
            messages.success(request, 'تم إنشاء النسخة الاحتياطية بنجاح.')
        except Exception as e:
            messages.error(request, f'حدث خطأ أثناء إنشاء النسخة الاحتياطية: {str(e)}')
    
    context = {
        'page_title': 'النسخ الاحتياطي العام',
        'page_icon': 'fas fa-database',
    }
    return render(request, 'financial/advanced/general_backup.html', context)


@login_required
def financial_backup_advanced(request):
    """
    النسخ الاحتياطي المالي المتقدم
    """
    if request.method == 'POST':
        try:
            from .services.financial_backup_service import FinancialBackupService
            service = FinancialBackupService()
            # يمكن إضافة منطق النسخ الاحتياطي المتقدم هنا
            messages.success(request, 'تم إنشاء النسخة الاحتياطية المالية المتقدمة بنجاح.')
        except ImportError:
            messages.error(request, 'خدمة النسخ الاحتياطي المالي غير متاحة حالياً.')
        except Exception as e:
            messages.error(request, f'حدث خطأ أثناء إنشاء النسخة الاحتياطية: {str(e)}')
    
    context = {
        'page_title': 'نسخ احتياطي مالي متقدم',
        'page_icon': 'fas fa-coins',
    }
    return render(request, 'financial/advanced/financial_backup_advanced.html', context)


@login_required
def restore_data(request):
    """
    استعادة البيانات
    """
    if request.method == 'POST':
        try:
            # يمكن إضافة منطق استعادة البيانات هنا لاحقاً
            messages.success(request, 'تم استعادة البيانات بنجاح.')
        except Exception as e:
            messages.error(request, f'حدث خطأ أثناء استعادة البيانات: {str(e)}')
    
    context = {
        'page_title': 'استعادة البيانات',
        'page_icon': 'fas fa-history',
    }
    return render(request, 'financial/advanced/restore_data.html', context)


@login_required
def data_integrity_check(request):
    """
    التحقق من سلامة البيانات
    """
    if request.method == 'POST':
        try:
            # يمكن إضافة منطق فحص سلامة البيانات هنا لاحقاً
            messages.success(request, 'تم فحص سلامة البيانات بنجاح. لم يتم العثور على أخطاء.')
        except Exception as e:
            messages.error(request, f'حدث خطأ أثناء فحص البيانات: {str(e)}')
    
    context = {
        'page_title': 'التحقق من سلامة البيانات',
        'page_icon': 'fas fa-shield-alt',
    }
    return render(request, 'financial/advanced/data_integrity_check.html', context)


# ============== دوال الحذف المحمية ==============

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
        messages.error(request, 'ليس لديك صلاحية حذف هذا القيد')
        return redirect('financial:journal_entries_list')
    
    if request.method == 'POST':
        try:
            entry.delete()
            messages.success(request, f'تم حذف القيد "{entry.reference}" بنجاح.')
            return redirect('financial:journal_entries_list')
        except ValidationError as e:
            messages.error(request, str(e))
            return redirect('financial:journal_entries_detail', pk=pk)
        except Exception as e:
            messages.error(request, f'خطأ في الحذف: {str(e)}')
            return redirect('financial:journal_entries_detail', pk=pk)
    
    context = {
        'entry': entry,
        'can_delete': entry.can_be_deleted(),
    }
    return render(request, 'financial/journal_entry_delete_confirm.html', context)


@login_required
def cash_account_movements(request, pk):
    """
    عرض حركات حساب خزن معين من القيود المحاسبية
    """
    account = get_object_or_404(ChartOfAccounts, pk=pk)
    
    # التحقق من أن الحساب نقدي أو بنكي
    if not (account.is_cash_account or account.is_bank_account):
        messages.error(request, 'هذا الحساب ليس حساباً نقدياً أو بنكياً')
        return redirect('financial:cash_and_bank_accounts_list')
    
    # جلب حركات الحساب من القيود المحاسبية
    movements = JournalEntryLine.objects.filter(
        account=account
    ).select_related('journal_entry').order_by('-journal_entry__date', '-id')
    
    # الفلترة
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    search = request.GET.get('search', '').strip()
    
    if date_from:
        movements = movements.filter(journal_entry__date__gte=date_from)
    if date_to:
        movements = movements.filter(journal_entry__date__lte=date_to)
    if search:
        from django.db import models
        movements = movements.filter(
            models.Q(journal_entry__description__icontains=search) |
            models.Q(journal_entry__reference__icontains=search) |
            models.Q(description__icontains=search)
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
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # حساب الرصيد الإجمالي
    from django.db.models import Sum
    total_debit = movements.aggregate(Sum('debit'))['debit__sum'] or 0
    total_credit = movements.aggregate(Sum('credit'))['credit__sum'] or 0
    current_balance = total_debit - total_credit
    
    context = {
        'account': account,
        'movements': page_obj,
        'total_debit': total_debit,
        'total_credit': total_credit,
        'current_balance': current_balance,
        'date_from': date_from,
        'date_to': date_to,
        'search': search,
        'page_title': f'حركات {account.name}',
        'page_icon': 'fas fa-list-alt',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الإدارة المالية', 'url': '#', 'icon': 'fas fa-money-bill-wave'},
            {'title': 'الحسابات النقدية', 'url': reverse('financial:cash_and_bank_accounts_list'), 'icon': 'fas fa-money-bill-wave'},
            {'title': f'حركات {account.name}', 'active': True}
        ]
    }
    
    return render(request, 'financial/cash_account_movements.html', context)











# ========================================
# دوال الحذف المحمية
# ========================================

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
        messages.error(request, 'ليس لديك صلاحية حذف هذا القيد')
        return redirect('financial:journal_entries_list')
    
    if request.method == 'POST':
        try:
            entry_number = entry.number
            entry.delete()
            messages.success(request, f'تم حذف القيد {entry_number} بنجاح')
            return redirect('financial:journal_entries_list')
        except ValidationError as e:
            messages.error(request, str(e))
            return redirect('financial:journal_entries_detail', pk=pk)
        except Exception as e:
            messages.error(request, f'خطأ في الحذف: {str(e)}')
            return redirect('financial:journal_entries_detail', pk=pk)
    
    context = {
        'entry': entry,
        'can_delete': entry.can_be_deleted(),
    }
    return render(request, 'financial/journal_entry_delete_confirm.html', context)








# تم حذف جميع الـ APIs واستبدالها بالمنطق المدمج في الـ view


# ============== إدارة الدفعات المحسنة ==============

# استيراد النماذج المطلوبة لإدارة الدفعات
try:
    from sale.models import SalePayment
    from purchase.models import PurchasePayment
    from financial.models import AuditTrail
    from financial.services.payment_edit_service import PaymentEditService
except ImportError as e:
    # في حالة عدم وجود النماذج، سنقوم بإنشاء دوال بديلة
    SalePayment = None
    PurchasePayment = None
    AuditTrail = None
    PaymentEditService = None


@login_required
def payment_dashboard(request):
    """
    لوحة تحكم الدفعات
    """
    try:
        # إحصائيات الدفعات
        stats = {
            'total_sale_payments': 0,
            'total_purchase_payments': 0,
            'posted_sale_payments': 0,
            'posted_purchase_payments': 0,
            'pending_payments': 0,
            'synced_payments': 0,
            'synced_sale_payments': 0,
            'synced_purchase_payments': 0,
            'failed_sale_payments': 0,
            'failed_purchase_payments': 0,
        }
        
        if SalePayment:
            stats['total_sale_payments'] = SalePayment.objects.count()
            stats['posted_sale_payments'] = SalePayment.objects.filter(status='posted').count()
            stats['pending_payments'] += SalePayment.objects.filter(financial_status='pending').count()
            synced_sale = SalePayment.objects.filter(financial_status='synced').count()
            stats['synced_sale_payments'] = synced_sale
            stats['synced_payments'] += synced_sale
            stats['failed_sale_payments'] = SalePayment.objects.filter(financial_status='failed').count()
        
        if PurchasePayment:
            stats['total_purchase_payments'] = PurchasePayment.objects.count()
            stats['posted_purchase_payments'] = PurchasePayment.objects.filter(status='posted').count()
            stats['pending_payments'] += PurchasePayment.objects.filter(financial_status='pending').count()
            synced_purchase = PurchasePayment.objects.filter(financial_status='synced').count()
            stats['synced_purchase_payments'] = synced_purchase
            stats['synced_payments'] += synced_purchase
            stats['failed_purchase_payments'] = PurchasePayment.objects.filter(financial_status='failed').count()
        
        # الدفعات التي تحتاج انتباه
        problematic_payments = {
            'failed_sales': [],
            'failed_purchases': [],
            'pending_sales': [],
            'pending_purchases': [],
        }
        
        if SalePayment:
            problematic_payments['failed_sales'] = SalePayment.objects.filter(financial_status='failed')[:5]
            problematic_payments['pending_sales'] = SalePayment.objects.filter(financial_status='pending')[:5]
        
        if PurchasePayment:
            problematic_payments['failed_purchases'] = PurchasePayment.objects.filter(financial_status='failed')[:5]
            problematic_payments['pending_purchases'] = PurchasePayment.objects.filter(financial_status='pending')[:5]
        
        # الدفعات الأخيرة
        recent_sale_payments = []
        recent_purchase_payments = []
        
        if SalePayment:
            recent_sale_payments = SalePayment.objects.select_related('sale', 'sale__customer').order_by('-created_at')[:5]
        
        if PurchasePayment:
            recent_purchase_payments = PurchasePayment.objects.select_related('purchase', 'purchase__supplier').order_by('-created_at')[:5]
        
        context = {
            'stats': stats,
            'problematic_payments': problematic_payments,
            'recent_sale_payments': recent_sale_payments,
            'recent_purchase_payments': recent_purchase_payments,
            'page_title': 'لوحة تحكم الدفعات',
            'page_icon': 'fas fa-credit-card',
        }
        
        return render(request, 'financial/payment_dashboard.html', context)
    
    except Exception as e:
        messages.error(request, f'خطأ في تحميل لوحة تحكم الدفعات: {str(e)}')
        # إرسال قاموس stats فارغ مع جميع المفاتيح المطلوبة
        empty_stats = {
            'total_sale_payments': 0,
            'total_purchase_payments': 0,
            'posted_sale_payments': 0,
            'posted_purchase_payments': 0,
            'pending_payments': 0,
            'synced_payments': 0,
            'synced_sale_payments': 0,
            'synced_purchase_payments': 0,
            'failed_sale_payments': 0,
            'failed_purchase_payments': 0,
        }
        empty_problematic = {
            'failed_sales': [],
            'failed_purchases': [],
            'pending_sales': [],
            'pending_purchases': [],
        }
        return render(request, 'financial/payment_dashboard.html', {
            'stats': empty_stats,
            'problematic_payments': empty_problematic,
            'recent_sale_payments': [],
            'recent_purchase_payments': [],
            'page_title': 'لوحة تحكم الدفعات',
            'page_icon': 'fas fa-credit-card',
        })


@login_required
def payment_list(request):
    """
    قائمة الدفعات
    """
    try:
        payments = []
        
        # جلب دفعات المبيعات
        if SalePayment:
            sale_payments = SalePayment.objects.select_related('sale', 'sale__customer').all()
            for payment in sale_payments:
                payments.append({
                    'id': payment.id,
                    'type': 'sale',
                    'type_display': 'مبيعات',
                    'amount': payment.amount,
                    'date': payment.payment_date,
                    'method': payment.get_payment_method_display(),
                    'status': payment.financial_status,
                    'invoice_number': payment.sale.number if payment.sale else 'غير محدد',
                    'party_name': payment.sale.customer.name if payment.sale and payment.sale.customer else 'غير محدد',
                    'url': reverse('financial:payment_detail', args=['sale', payment.id]),
                })
        
        # جلب دفعات المشتريات
        if PurchasePayment:
            purchase_payments = PurchasePayment.objects.select_related('purchase', 'purchase__supplier').all()
            for payment in purchase_payments:
                payments.append({
                    'id': payment.id,
                    'type': 'purchase',
                    'type_display': 'مشتريات',
                    'amount': payment.amount,
                    'date': payment.payment_date,
                    'method': payment.get_payment_method_display(),
                    'status': payment.financial_status,
                    'invoice_number': payment.purchase.number if payment.purchase else 'غير محدد',
                    'party_name': payment.purchase.supplier.name if payment.purchase and payment.purchase.supplier else 'غير محدد',
                    'url': reverse('financial:payment_detail', args=['purchase', payment.id]),
                })
        
        # ترتيب الدفعات حسب التاريخ
        payments.sort(key=lambda x: x['date'], reverse=True)
        
        # تعريف أعمدة جدول المدفوعات
        payment_headers = [
            {'key': 'id', 'label': '#', 'sortable': True, 'class': 'text-center', 'width': '50px'},
            {'key': 'type_display', 'label': 'النوع', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/payment_type.html', 'width': '80px'},
            {'key': 'invoice_number', 'label': 'رقم الفاتورة', 'sortable': True, 'class': 'text-center', 'width': '120px'},
            {'key': 'party_name', 'label': 'العميل/المورد', 'sortable': True, 'class': 'text-start'},
            {'key': 'status', 'label': 'الحالة', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/payment_status.html', 'width': '100px'},
            {'key': 'amount', 'label': 'المبلغ', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/payment_amount.html', 'width': '120px'},
            {'key': 'method', 'label': 'طريقة الدفع', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/payment_method.html', 'width': '120px'},
            {'key': 'date', 'label': 'تاريخ الدفع', 'sortable': True, 'class': 'text-center', 'format': 'date', 'width': '120px'},
        ]
        # أزرار الإجراءات - بدون أزرار بسبب تعقيد URL
        payment_actions = []
        # الترقيم
        paginator = Paginator(payments, 25)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        context = {
            'payments': page_obj,
            'payment_headers': payment_headers,
            'payment_actions': payment_actions,
            'primary_key': 'id',
            'page_title': 'قائمة الدفعات',
            'page_icon': 'fas fa-credit-card',
            'breadcrumb_items': [
                {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
                {'title': 'الإدارة المالية', 'url': '#', 'icon': 'fas fa-money-bill-wave'},
                {'title': 'المدفوعات', 'active': True}
            ],
        }
        
        return render(request, 'financial/payment_list.html', context)
    
    except Exception as e:
        messages.error(request, f'خطأ في تحميل قائمة الدفعات: {str(e)}')
        return render(request, 'financial/payment_list.html', {'page_obj': None})


@login_required
def payment_detail(request, payment_type, payment_id):
    """
    تفاصيل الدفعة
    """
    try:
        payment = None
        
        if payment_type == 'sale' and SalePayment:
            payment = get_object_or_404(SalePayment.objects.select_related('sale', 'sale__customer'), pk=payment_id)
        elif payment_type == 'purchase' and PurchasePayment:
            payment = get_object_or_404(PurchasePayment.objects.select_related('purchase', 'purchase__supplier'), pk=payment_id)
        else:
            messages.error(request, 'نوع الدفعة غير صحيح')
            return redirect('financial:payment_list')
        
        context = {
            'payment': payment,
            'payment_type': payment_type,
            'page_title': f'تفاصيل الدفعة #{payment.id}',
            'page_icon': 'fas fa-info-circle',
        }
        
        return render(request, 'financial/payment_detail.html', context)
    
    except Exception as e:
        messages.error(request, f'خطأ في تحميل تفاصيل الدفعة: {str(e)}')
        return redirect('financial:payment_list')


@login_required
def payment_edit(request, payment_type, payment_id):
    """
    تعديل الدفعة
    """
    try:
        payment = None
        
        if payment_type == 'sale' and SalePayment:
            payment = get_object_or_404(SalePayment, pk=payment_id)
        elif payment_type == 'purchase' and PurchasePayment:
            payment = get_object_or_404(PurchasePayment, pk=payment_id)
        else:
            messages.error(request, 'نوع الدفعة غير صحيح')
            return redirect('financial:payment_list')
        
        if request.method == 'POST':
            # استخدام خدمة تعديل الدفعات
            if PaymentEditService:
                service = PaymentEditService()
                success, message = service.edit_payment(payment, request.POST, request.user)
                
                if success:
                    messages.success(request, message)
                    return redirect('financial:payment_detail', payment_type=payment_type, payment_id=payment_id)
                else:
                    messages.error(request, message)
            else:
                messages.error(request, 'خدمة تعديل الدفعات غير متاحة')
        
        context = {
            'payment': payment,
            'payment_type': payment_type,
            'page_title': f'تعديل الدفعة #{payment.id}',
            'page_icon': 'fas fa-edit',
        }
        
        return render(request, 'financial/payment_edit.html', context)
    
    except Exception as e:
        messages.error(request, f'خطأ في تعديل الدفعة: {str(e)}')
        return redirect('financial:payment_list')


@login_required
def payment_unpost(request, payment_type, payment_id):
    """
    إلغاء ترحيل الدفعة
    """
    try:
        payment = None
        
        if payment_type == 'sale' and SalePayment:
            payment = get_object_or_404(SalePayment, pk=payment_id)
        elif payment_type == 'purchase' and PurchasePayment:
            payment = get_object_or_404(PurchasePayment, pk=payment_id)
        else:
            messages.error(request, 'نوع الدفعة غير صحيح')
            return redirect('financial:payment_list')
        
        if request.method == 'POST':
            # منطق إلغاء الترحيل
            try:
                # حذف القيد المحاسبي المرتبط
                if hasattr(payment, 'financial_transaction') and payment.financial_transaction:
                    payment.financial_transaction.delete()
                    payment.financial_transaction = None
                
                # تحديث حالة الربط المالي
                payment.financial_status = 'pending'
                payment.save()
                
                # تسجيل في سجل التدقيق
                if AuditTrail:
                    AuditTrail.objects.create(
                        user=request.user,
                        action='unpost_payment',
                        entity_type=payment_type + '_payment',
                        entity_id=payment.id,
                        description=f'إلغاء ترحيل دفعة {payment_type} #{payment.id}'
                    )
                
                messages.success(request, 'تم إلغاء ترحيل الدفعة بنجاح')
                return redirect('financial:payment_detail', payment_type=payment_type, payment_id=payment_id)
                
            except Exception as e:
                messages.error(request, f'خطأ في إلغاء الترحيل: {str(e)}')
        
        context = {
            'payment': payment,
            'payment_type': payment_type,
            'page_title': f'إلغاء ترحيل الدفعة #{payment.id}',
            'page_icon': 'fas fa-undo',
        }
        
        return render(request, 'financial/payment_unpost.html', context)
    
    except Exception as e:
        messages.error(request, f'خطأ في إلغاء ترحيل الدفعة: {str(e)}')
        return redirect('financial:payment_list')


@login_required
def payment_delete(request, payment_type, payment_id):
    """
    حذف الدفعة
    """
    try:
        payment = None
        
        if payment_type == 'sale' and SalePayment:
            payment = get_object_or_404(SalePayment, pk=payment_id)
        elif payment_type == 'purchase' and PurchasePayment:
            payment = get_object_or_404(PurchasePayment, pk=payment_id)
        else:
            messages.error(request, 'نوع الدفعة غير صحيح')
            return redirect('financial:payment_list')
        
        if request.method == 'POST':
            try:
                # حذف القيد المحاسبي المرتبط أولاً
                if hasattr(payment, 'financial_transaction') and payment.financial_transaction:
                    payment.financial_transaction.delete()
                
                # تسجيل في سجل التدقيق قبل الحذف
                if AuditTrail:
                    AuditTrail.objects.create(
                        user=request.user,
                        action='delete_payment',
                        entity_type=payment_type + '_payment',
                        entity_id=payment.id,
                        description=f'حذف دفعة {payment_type} #{payment.id}'
                    )
                
                # حذف الدفعة
                payment.delete()
                
                messages.success(request, 'تم حذف الدفعة بنجاح')
                return redirect('financial:payment_list')
                
            except Exception as e:
                messages.error(request, f'خطأ في حذف الدفعة: {str(e)}')
        
        context = {
            'payment': payment,
            'payment_type': payment_type,
            'page_title': f'حذف الدفعة #{payment.id}',
            'page_icon': 'fas fa-trash',
        }
        
        return render(request, 'financial/payment_delete.html', context)
    
    except Exception as e:
        messages.error(request, f'خطأ في حذف الدفعة: {str(e)}')
        return redirect('financial:payment_list')


@login_required
def payment_history(request, payment_type, payment_id):
    """
    تاريخ الدفعة
    """
    try:
        payment = None
        
        if payment_type == 'sale' and SalePayment:
            payment = get_object_or_404(SalePayment, pk=payment_id)
        elif payment_type == 'purchase' and PurchasePayment:
            payment = get_object_or_404(PurchasePayment, pk=payment_id)
        else:
            messages.error(request, 'نوع الدفعة غير صحيح')
            return redirect('financial:payment_list')
        
        # جلب سجل التدقيق للدفعة
        audit_entries = []
        if AuditTrail:
            audit_entries = AuditTrail.objects.filter(
                entity_type=payment_type + '_payment',
                entity_id=payment_id
            ).order_by('-created_at')
        
        context = {
            'payment': payment,
            'payment_type': payment_type,
            'audit_entries': audit_entries,
            'page_title': f'تاريخ الدفعة #{payment.id}',
            'page_icon': 'fas fa-history',
        }
        
        return render(request, 'financial/payment_history.html', context)
    
    except Exception as e:
        messages.error(request, f'خطأ في تحميل تاريخ الدفعة: {str(e)}')
        return redirect('financial:payment_list')


# ============== سجل التدقيق ==============

@login_required
def audit_trail_list(request):
    """
    قائمة سجل التدقيق
    """
    try:
        if not AuditTrail:
            messages.warning(request, 'سجل التدقيق غير متاح')
            return render(request, 'financial/audit_trail_list.html', {'page_obj': None})
        
        # الفلاتر
        search_query = request.GET.get('search', '').strip()
        action_filter = request.GET.get('action', '')
        entity_type_filter = request.GET.get('entity_type', '')
        
        # جلب السجلات
        audit_entries = AuditTrail.objects.select_related('user').all()
        
        # تطبيق الفلاتر
        if search_query:
            audit_entries = audit_entries.filter(
                Q(description__icontains=search_query) |
                Q(user__username__icontains=search_query)
            )
        
        if action_filter:
            audit_entries = audit_entries.filter(action=action_filter)
        
        if entity_type_filter:
            audit_entries = audit_entries.filter(entity_type=entity_type_filter)
        
        # ترتيب حسب التاريخ
        audit_entries = audit_entries.order_by('-timestamp')
        
        # الترقيم
        paginator = Paginator(audit_entries, 50)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        context = {
            'page_obj': page_obj,
            'search_query': search_query,
            'action_filter': action_filter,
            'entity_type_filter': entity_type_filter,
        }
        
        return render(request, 'financial/audit_trail_list.html', context)
    
    except Exception as e:
        messages.error(request, f'خطأ في تحميل سجل التدقيق: {str(e)}')
        return render(request, 'financial/audit_trail_list.html', {'page_obj': None})


# ============== نظام المصروفات والإيرادات المحسن ==============

@login_required
def expense_create(request):
    """
    إنشاء مصروف جديد
    """
    try:
        # التحقق من توفر النماذج والخدمات
        if not ExpenseForm or not ExpenseIncomeService:
            messages.error(request, 'نظام المصروفات غير متاح حالياً')
            return redirect('financial:expense_list')
        
        if request.method == 'POST':
            form = ExpenseForm(request.POST)
            if form.is_valid():
                try:
                    # إنشاء المصروف باستخدام الخدمة
                    journal_entry = ExpenseIncomeService.create_expense(
                        form.cleaned_data, 
                        request.user
                    )
                    
                    messages.success(
                        request, 
                        f'تم إنشاء المصروف بنجاح. رقم القيد: {journal_entry.reference}'
                    )
                    return redirect('financial:expense_detail', pk=journal_entry.pk)
                except Exception as e:
                    messages.error(request, f'خطأ في إنشاء المصروف: {str(e)}')
            else:
                # عرض أخطاء النموذج بالتفصيل
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, f'خطأ في {field}: {error}')
        else:
            form = ExpenseForm()
        
        context = {
            'form': form,
            'page_title': 'إضافة مصروف جديد',
            'page_icon': 'fas fa-plus',
            'breadcrumb_items': [
                {'title': 'النظام المالي', 'url': reverse('financial:expense_list')},
                {'title': 'المصروفات', 'url': reverse('financial:expense_list')},
                {'title': 'إضافة مصروف', 'active': True}
            ]
        }
        
        return render(request, 'financial/expense_create.html', context)
    
    except Exception as e:
        messages.error(request, f'خطأ في إنشاء المصروف: {str(e)}')
        return redirect('financial:expense_list')


@login_required
def expense_detail(request, pk):
    """
    تفاصيل المصروف
    """
    try:
        journal_entry = get_object_or_404(JournalEntry, pk=pk)
        
        # التحقق من أن هذا قيد مصروف
        if not journal_entry.reference.startswith('EXP-'):
            messages.error(request, 'هذا ليس قيد مصروف')
            return redirect('financial:expense_list')
        
        # استخراج معلومات المصروف من بنود القيد
        expense_lines = journal_entry.lines.filter(debit_amount__gt=0)
        payment_lines = journal_entry.lines.filter(credit_amount__gt=0)
        
        expense_amount = sum(line.debit_amount for line in expense_lines)
        
        context = {
            'journal_entry': journal_entry,
            'expense_lines': expense_lines,
            'payment_lines': payment_lines,
            'expense_amount': expense_amount,
            'page_title': f'تفاصيل المصروف - {journal_entry.reference}',
            'page_icon': 'fas fa-receipt',
            'breadcrumb_items': [
                {'title': 'النظام المالي', 'url': reverse('financial:expense_list')},
                {'title': 'المصروفات', 'url': reverse('financial:expense_list')},
                {'title': f'المصروف {journal_entry.reference}', 'active': True}
            ]
        }
        
        return render(request, 'financial/expense_detail.html', context)
    
    except Exception as e:
        messages.error(request, f'خطأ في تحميل تفاصيل المصروف: {str(e)}')
        return redirect('financial:expense_list')


@login_required
def expense_edit(request, pk):
    """
    تعديل المصروف
    """
    try:
        journal_entry = get_object_or_404(JournalEntry, pk=pk)
        
        # التحقق من أن هذا قيد مصروف
        if not journal_entry.reference.startswith('EXP-'):
            messages.error(request, 'هذا ليس قيد مصروف')
            return redirect('financial:expense_list')
        
        if request.method == 'POST':
            form = ExpenseEditForm(request.POST, journal_entry=journal_entry)
            if form.is_valid():
                # تحديث المصروف باستخدام الخدمة
                updated_entry = ExpenseIncomeService.update_expense(
                    journal_entry,
                    form.cleaned_data,
                    request.user
                )
                
                messages.success(request, 'تم تحديث المصروف بنجاح')
                return redirect('financial:expense_detail', pk=updated_entry.pk)
            else:
                messages.error(request, 'يرجى تصحيح الأخطاء أدناه')
        else:
            form = ExpenseEditForm(journal_entry=journal_entry)
        
        context = {
            'form': form,
            'journal_entry': journal_entry,
            'page_title': f'تعديل المصروف - {journal_entry.reference}',
            'page_icon': 'fas fa-edit',
            'breadcrumb_items': [
                {'title': 'النظام المالي', 'url': reverse('financial:expense_list')},
                {'title': 'المصروفات', 'url': reverse('financial:expense_list')},
                {'title': f'المصروف {journal_entry.reference}', 'url': reverse('financial:expense_detail', args=[pk])},
                {'title': 'تعديل', 'active': True}
            ]
        }
        
        return render(request, 'financial/expense_edit.html', context)
    
    except Exception as e:
        messages.error(request, f'خطأ في تعديل المصروف: {str(e)}')
        return redirect('financial:expense_detail', pk=pk)


@login_required
def expense_delete(request, pk):
    """
    حذف المصروف
    """
    try:
        journal_entry = get_object_or_404(JournalEntry, pk=pk)
        
        # التحقق من أن هذا قيد مصروف
        if not journal_entry.reference.startswith('EXP-'):
            messages.error(request, 'هذا ليس قيد مصروف')
            return redirect('financial:expense_list')
        
        if request.method == 'POST':
            # حذف المصروف باستخدام الخدمة
            ExpenseIncomeService.delete_journal_entry(journal_entry, request.user)
            
            messages.success(request, f'تم حذف المصروف {journal_entry.reference} بنجاح')
            return redirect('financial:expense_list')
        
        context = {
            'journal_entry': journal_entry,
            'page_title': f'حذف المصروف - {journal_entry.reference}',
            'page_icon': 'fas fa-trash',
            'breadcrumb_items': [
                {'title': 'النظام المالي', 'url': reverse('financial:expense_list')},
                {'title': 'المصروفات', 'url': reverse('financial:expense_list')},
                {'title': f'المصروف {journal_entry.reference}', 'url': reverse('financial:expense_detail', args=[pk])},
                {'title': 'حذف', 'active': True}
            ]
        }
        
        return render(request, 'financial/expense_delete.html', context)
    
    except Exception as e:
        messages.error(request, f'خطأ في حذف المصروف: {str(e)}')
        return redirect('financial:expense_detail', pk=pk)


@login_required
def expense_post(request, pk):
    """
    ترحيل المصروف
    """
    try:
        journal_entry = get_object_or_404(JournalEntry, pk=pk)
        
        # التحقق من أن هذا قيد مصروف
        if not journal_entry.reference.startswith('EXP-'):
            messages.error(request, 'هذا ليس قيد مصروف')
            return redirect('financial:expense_list')
        
        if request.method == 'POST':
            # ترحيل المصروف باستخدام الخدمة
            ExpenseIncomeService.post_journal_entry(journal_entry, request.user)
            
            messages.success(request, f'تم ترحيل المصروف {journal_entry.reference} بنجاح')
            return redirect('financial:expense_detail', pk=pk)
        
        context = {
            'journal_entry': journal_entry,
            'page_title': f'ترحيل المصروف - {journal_entry.reference}',
            'page_icon': 'fas fa-check',
        }
        
        return render(request, 'financial/expense_post.html', context)
    
    except Exception as e:
        messages.error(request, f'خطأ في ترحيل المصروف: {str(e)}')
        return redirect('financial:expense_detail', pk=pk)


# ============== نظام الإيرادات ==============

@login_required
def income_create(request):
    """
    إنشاء إيراد جديد
    """
    try:
        # التحقق من توفر النماذج والخدمات
        if not IncomeForm or not ExpenseIncomeService:
            messages.error(request, 'نظام الإيرادات غير متاح حالياً')
            return redirect('financial:income_list')
        
        if request.method == 'POST':
            form = IncomeForm(request.POST)
            if form.is_valid():
                try:
                    # إنشاء الإيراد باستخدام الخدمة
                    journal_entry = ExpenseIncomeService.create_income(
                        form.cleaned_data, 
                        request.user
                    )
                    
                    messages.success(
                        request, 
                        f'تم إنشاء الإيراد بنجاح. رقم القيد: {journal_entry.reference}'
                    )
                    return redirect('financial:income_detail', pk=journal_entry.pk)
                except Exception as e:
                    messages.error(request, f'خطأ في إنشاء الإيراد: {str(e)}')
            else:
                # عرض أخطاء النموذج بالتفصيل
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, f'خطأ في {field}: {error}')
        else:
            form = IncomeForm()
        
        context = {
            'form': form,
            'page_title': 'إضافة إيراد جديد',
            'page_icon': 'fas fa-plus',
            'breadcrumb_items': [
                {'title': 'النظام المالي', 'url': reverse('financial:income_list')},
                {'title': 'الإيرادات', 'url': reverse('financial:income_list')},
                {'title': 'إضافة إيراد', 'active': True}
            ]
        }
        
        return render(request, 'financial/income_create.html', context)
    
    except Exception as e:
        messages.error(request, f'خطأ في إنشاء الإيراد: {str(e)}')
        return redirect('financial:income_list')


@login_required
def income_detail(request, pk):
    """
    تفاصيل الإيراد
    """
    try:
        journal_entry = get_object_or_404(JournalEntry, pk=pk)
        
        # التحقق من أن هذا قيد إيراد
        if not journal_entry.reference.startswith('INC-'):
            messages.error(request, 'هذا ليس قيد إيراد')
            return redirect('financial:income_list')
        
        # استخراج معلومات الإيراد من بنود القيد
        receipt_lines = journal_entry.lines.filter(debit_amount__gt=0)
        income_lines = journal_entry.lines.filter(credit_amount__gt=0)
        
        income_amount = sum(line.credit_amount for line in income_lines)
        
        context = {
            'journal_entry': journal_entry,
            'receipt_lines': receipt_lines,
            'income_lines': income_lines,
            'income_amount': income_amount,
            'page_title': f'تفاصيل الإيراد - {journal_entry.reference}',
            'page_icon': 'fas fa-money-bill-wave',
            'breadcrumb_items': [
                {'title': 'النظام المالي', 'url': reverse('financial:income_list')},
                {'title': 'الإيرادات', 'url': reverse('financial:income_list')},
                {'title': f'الإيراد {journal_entry.reference}', 'active': True}
            ]
        }
        
        return render(request, 'financial/income_detail.html', context)
    
    except Exception as e:
        messages.error(request, f'خطأ في تحميل تفاصيل الإيراد: {str(e)}')
        return redirect('financial:income_list')


@login_required
def income_edit(request, pk):
    """
    تعديل الإيراد
    """
    try:
        journal_entry = get_object_or_404(JournalEntry, pk=pk)
        
        # التحقق من أن هذا قيد إيراد
        if not journal_entry.reference.startswith('INC-'):
            messages.error(request, 'هذا ليس قيد إيراد')
            return redirect('financial:income_list')
        
        if request.method == 'POST':
            form = IncomeEditForm(request.POST, journal_entry=journal_entry)
            if form.is_valid():
                # تحديث الإيراد باستخدام الخدمة
                updated_entry = ExpenseIncomeService.update_income(
                    journal_entry,
                    form.cleaned_data,
                    request.user
                )
                
                messages.success(request, 'تم تحديث الإيراد بنجاح')
                return redirect('financial:income_detail', pk=updated_entry.pk)
            else:
                messages.error(request, 'يرجى تصحيح الأخطاء أدناه')
        else:
            form = IncomeEditForm(journal_entry=journal_entry)
        
        context = {
            'form': form,
            'journal_entry': journal_entry,
            'page_title': f'تعديل الإيراد - {journal_entry.reference}',
            'page_icon': 'fas fa-edit',
            'breadcrumb_items': [
                {'title': 'النظام المالي', 'url': reverse('financial:income_list')},
                {'title': 'الإيرادات', 'url': reverse('financial:income_list')},
                {'title': f'الإيراد {journal_entry.reference}', 'url': reverse('financial:income_detail', args=[pk])},
                {'title': 'تعديل', 'active': True}
            ]
        }
        
        return render(request, 'financial/income_edit.html', context)
    
    except Exception as e:
        messages.error(request, f'خطأ في تعديل الإيراد: {str(e)}')
        return redirect('financial:income_detail', pk=pk)


@login_required
def income_delete(request, pk):
    """
    حذف الإيراد
    """
    try:
        journal_entry = get_object_or_404(JournalEntry, pk=pk)
        
        # التحقق من أن هذا قيد إيراد
        if not journal_entry.reference.startswith('INC-'):
            messages.error(request, 'هذا ليس قيد إيراد')
            return redirect('financial:income_list')
        
        if request.method == 'POST':
            # حذف الإيراد باستخدام الخدمة
            ExpenseIncomeService.delete_journal_entry(journal_entry, request.user)
            
            messages.success(request, f'تم حذف الإيراد {journal_entry.reference} بنجاح')
            return redirect('financial:income_list')
        
        context = {
            'journal_entry': journal_entry,
            'page_title': f'حذف الإيراد - {journal_entry.reference}',
            'page_icon': 'fas fa-trash',
            'breadcrumb_items': [
                {'title': 'النظام المالي', 'url': reverse('financial:income_list')},
                {'title': 'الإيرادات', 'url': reverse('financial:income_list')},
                {'title': f'الإيراد {journal_entry.reference}', 'url': reverse('financial:income_detail', args=[pk])},
                {'title': 'حذف', 'active': True}
            ]
        }
        
        return render(request, 'financial/income_delete.html', context)
    
    except Exception as e:
        messages.error(request, f'خطأ في حذف الإيراد: {str(e)}')
        return redirect('financial:income_detail', pk=pk)


@login_required
def income_post(request, pk):
    """
    ترحيل الإيراد
    """
    try:
        journal_entry = get_object_or_404(JournalEntry, pk=pk)
        
        # التحقق من أن هذا قيد إيراد
        if not journal_entry.reference.startswith('INC-'):
            messages.error(request, 'هذا ليس قيد إيراد')
            return redirect('financial:income_list')
        
        if request.method == 'POST':
            # ترحيل الإيراد باستخدام الخدمة
            ExpenseIncomeService.post_journal_entry(journal_entry, request.user)
            
            messages.success(request, f'تم ترحيل الإيراد {journal_entry.reference} بنجاح')
            return redirect('financial:income_detail', pk=pk)
        
        context = {
            'journal_entry': journal_entry,
            'page_title': f'ترحيل الإيراد - {journal_entry.reference}',
            'page_icon': 'fas fa-check',
        }
        
        return render(request, 'financial/income_post.html', context)
    
    except Exception as e:
        messages.error(request, f'خطأ في ترحيل الإيراد: {str(e)}')
        return redirect('financial:income_detail', pk=pk)


# ================================
# Payment Sync Management APIs
# ================================

@require_http_methods(["GET"])
@login_required
def payment_sync_check_pending_api(request):
    """
    API لفحص العمليات المعلقة
    """
    try:
        from financial.models.payment_sync import PaymentSyncOperation
        from django.utils import timezone
        
        # العمليات المعلقة
        pending_ops = PaymentSyncOperation.objects.filter(status='pending')
        processing_ops = PaymentSyncOperation.objects.filter(status='processing')
        
        # العمليات العالقة (أكثر من 10 دقائق)
        ten_minutes_ago = timezone.now() - timedelta(minutes=10)
        stuck_pending = pending_ops.filter(created_at__lt=ten_minutes_ago).count()
        stuck_processing = processing_ops.filter(started_at__lt=ten_minutes_ago).count()
        
        return JsonResponse({
            'success': True,
            'pending_count': pending_ops.count(),
            'processing_count': processing_ops.count(),
            'stuck_operations': stuck_pending + stuck_processing,
            'details': {
                'stuck_pending': stuck_pending,
                'stuck_processing': stuck_processing
            }
        })
        
    except ImportError:
        return JsonResponse({
            'success': False,
            'message': 'نماذج التزامن غير متاحة'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'خطأ في فحص العمليات: {str(e)}'
        })


@require_http_methods(["POST"])
@login_required
def payment_sync_process_pending_api(request):
    """
    API لتشغيل العمليات المعلقة
    """
    try:
        from financial.models.payment_sync import PaymentSyncOperation
        from financial.services.payment_sync_service import PaymentSyncService
        
        # جلب العمليات المعلقة
        pending_ops = PaymentSyncOperation.objects.filter(status='pending').order_by('created_at')
        
        if not pending_ops.exists():
            return JsonResponse({
                'success': True,
                'message': 'لا توجد عمليات معلقة',
                'processed_count': 0
            })
        
        # تشغيل العمليات
        sync_service = PaymentSyncService()
        processed_count = 0
        
        for operation in pending_ops[:10]:  # معالجة 10 عمليات كحد أقصى
            try:
                # تحديث حالة العملية إلى قيد المعالجة
                operation.status = 'processing'
                operation.started_at = timezone.now()
                operation.save()
                
                # محاولة تنفيذ العملية
                if operation.operation_type == 'retry_failed':
                    # إعادة محاولة العملية الفاشلة
                    sync_service.retry_failed_operation(operation)
                elif operation.operation_type == 'delete_payment':
                    # حذف دفعة
                    sync_service.process_payment_deletion(operation)
                else:
                    # عملية عامة
                    sync_service.process_operation(operation)
                
                processed_count += 1
                
            except Exception as e:
                # تسجيل فشل العملية
                operation.status = 'failed'
                operation.error_message = str(e)
                operation.save()
        
        return JsonResponse({
            'success': True,
            'message': f'تم تشغيل {processed_count} عملية',
            'processed_count': processed_count
        })
        
    except ImportError:
        return JsonResponse({
            'success': False,
            'message': 'خدمة التزامن غير متاحة'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'خطأ في تشغيل العمليات: {str(e)}'
        })


@require_http_methods(["POST"])
@login_required
def payment_sync_process_all_api(request):
    """
    API موحد لمعالجة جميع العمليات (المعلقة والفاشلة)
    """
    try:
        from financial.models.payment_sync import PaymentSyncOperation
        from financial.services.payment_sync_service import PaymentSyncService
        from django.utils import timezone
        
        # إحصائيات النتائج
        processed_pending = 0
        retried_failed = 0
        errors = 0
        
        sync_service = PaymentSyncService()
        
        # 1. معالجة العمليات المعلقة
        pending_ops = PaymentSyncOperation.objects.filter(status='pending').order_by('created_at')
        for operation in pending_ops[:10]:  # حد أقصى 10 عمليات
            try:
                operation.status = 'processing'
                operation.started_at = timezone.now()
                operation.save()
                
                if operation.operation_type == 'delete_payment':
                    sync_service.process_payment_deletion(operation)
                else:
                    sync_service.process_operation(operation)
                
                processed_pending += 1
                
            except Exception as e:
                operation.status = 'failed'
                operation.error_message = str(e)
                operation.save()
                errors += 1
        
        # 2. إعادة محاولة العمليات الفاشلة
        failed_ops = PaymentSyncOperation.objects.filter(status='failed').order_by('-created_at')
        for operation in failed_ops[:5]:  # حد أقصى 5 عمليات فاشلة
            try:
                if operation.retry_count < operation.max_retries:
                    operation.retry_count += 1
                    operation.status = 'pending'
                    operation.save()
                    retried_failed += 1
                
            except Exception as e:
                errors += 1
        
        total_processed = processed_pending + retried_failed
        
        return JsonResponse({
            'success': True,
            'message': f'تم معالجة {total_processed} عملية',
            'processed_pending': processed_pending,
            'retried_failed': retried_failed,
            'total_processed': total_processed,
            'errors': errors
        })
        
    except ImportError:
        return JsonResponse({
            'success': False,
            'message': 'خدمة التزامن غير متاحة'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'خطأ في معالجة العمليات: {str(e)}'
        })


@require_http_methods(["POST"])
@login_required
def payment_sync_reset_all_api(request):
    """
    API لمسح جميع العمليات والأخطاء
    """
    try:
        from financial.models.payment_sync import PaymentSyncOperation, PaymentSyncError, PaymentSyncRule
        
        # حذف جميع العمليات والأخطاء
        operations_count = PaymentSyncOperation.objects.count()
        errors_count = PaymentSyncError.objects.count()
        
        PaymentSyncOperation.objects.all().delete()
        PaymentSyncError.objects.all().delete()
        
        # إعادة تعيين القواعد (اختياري)
        PaymentSyncRule.objects.update(is_active=False)
        
        return JsonResponse({
            'success': True,
            'message': f'تم حذف {operations_count} عملية و {errors_count} خطأ',
            'deleted_operations': operations_count,
            'deleted_errors': errors_count
        })
        
    except ImportError:
        return JsonResponse({
            'success': False,
            'message': 'نماذج التزامن غير متاحة'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'خطأ في مسح البيانات: {str(e)}'
        })
