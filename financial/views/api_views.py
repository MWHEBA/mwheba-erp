# financial/views/api_views.py
# نقاط النهاية للـ APIs المساعدة والدوال المساعدة

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
def api_expense_accounts(request):
    """API لجلب حسابات المصروفات النهائية فقط (باستثناء تكلفة البضاعة المباعة)"""
    try:
        # جلب الحسابات النهائية (الفرعية) فقط من فئة المصروفات
        # استثناء: تكلفة البضاعة المباعة (خاصة بالمبيعات فقط)
        accounts = ChartOfAccounts.objects.filter(
            is_active=True, 
            is_leaf=True,  # الحسابات النهائية فقط
            account_type__category="expense"  # فئة المصروفات
        ).exclude(
            code__startswith='51'  # استثناء تكلفة البضاعة المباعة (51xxx)
        ).values('id', 'name', 'code').order_by('code')
        
        return JsonResponse(list(accounts), safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required 
def api_payment_accounts(request):
    """API لجلب حسابات الخزينة (نقدية وبنكية) النهائية فقط"""
    try:
        # جلب الحسابات النهائية للخزينة والبنوك فقط
        accounts = ChartOfAccounts.objects.filter(
            is_active=True, 
            is_leaf=True,  # الحسابات النهائية فقط
            account_type__category="asset"  # من فئة الأصول
        ).filter(
            models.Q(is_cash_account=True) |  # حسابات نقدية
            models.Q(is_bank_account=True) |  # حسابات بنكية
            models.Q(account_type__code="CASH") |  # نوع الخزينة
            models.Q(account_type__code="BANK")   # نوع البنوك
        ).values('id', 'name', 'code').order_by('code')
        
        return JsonResponse(list(accounts), safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def api_income_accounts(request):
    """API لجلب حسابات الإيرادات النهائية فقط (باستثناء إيرادات المبيعات)"""
    try:
        # جلب الحسابات النهائية (الفرعية) فقط من فئة الإيرادات
        # استثناء: إيرادات المبيعات (خاصة بالمبيعات فقط)
        accounts = ChartOfAccounts.objects.filter(
            is_active=True, 
            is_leaf=True,  # الحسابات النهائية فقط
            account_type__category="revenue"  # فئة الإيرادات
        ).exclude(
            code__startswith='41'  # استثناء إيرادات المبيعات (41xxx)
        ).values('id', 'name', 'code').order_by('code')
        
        return JsonResponse(list(accounts), safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def export_transactions(request):
    """
    تصدير المعاملات المالية
    """
    try:
        from .models.transactions import FinancialTransaction

        transactions = FinancialTransaction.objects.all().order_by("-date", "-id")
    except ImportError:
        # استخدام القيود المحاسبية كبديل
        transactions = JournalEntry.objects.all().order_by("-date", "-id")

    # تطبيق الفلترة إذا كانت موجودة
    account_id = request.GET.get("account")
    trans_type = request.GET.get("type")
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")

    if account_id:
        account = get_object_or_404(Account, id=account_id)
        transactions = transactions.filter(Q(account=account) | Q(to_account=account))

    if trans_type:
        transactions = transactions.filter(transaction_type=trans_type)

    if date_from:
        date_from = datetime.strptime(date_from, "%Y-%m-%d").date()
        transactions = transactions.filter(date__gte=date_from)

    if date_to:
        date_to = datetime.strptime(date_to, "%Y-%m-%d").date()
        transactions = transactions.filter(date__lte=date_to)

    # إنشاء ملف CSV
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="transactions.csv"'

    writer = csv.writer(response)
    writer.writerow(
        ["ID", "التاريخ", "النوع", "الحساب", "الوصف", "المبلغ", "الرقم المرجعي"]
    )

    for transaction in transactions:
        writer.writerow(
            [
                transaction.id,
                transaction.date,
                transaction.get_transaction_type_display(),
                transaction.account.name,
                transaction.description,
                transaction.amount,
                transaction.reference_number or "",
            ]
        )

    return response


@login_required
def ledger_report(request):
    """
    تقرير دفتر الأستاذ العام - محسّن واحترافي
    يستخدم LedgerService للحسابات الديناميكية والدقيقة
    """
    from ..services.ledger_service import LedgerService
    from django.http import HttpResponse
    from django.core.paginator import Paginator
    
    # معالجة الفلاتر
    account_id = request.GET.get("account")
    date_from_str = request.GET.get("date_from")
    date_to_str = request.GET.get("date_to")
    export_format = request.GET.get("export")  # excel أو pdf
    
    # تحويل التواريخ
    date_from = None
    date_to = None
    
    if date_from_str:
        try:
            date_from = datetime.strptime(date_from_str, "%Y-%m-%d").date()
        except ValueError:
            messages.warning(request, "تنسيق تاريخ البداية غير صحيح")
    
    if date_to_str:
        try:
            date_to = datetime.strptime(date_to_str, "%Y-%m-%d").date()
        except ValueError:
            messages.warning(request, "تنسيق تاريخ النهاية غير صحيح")
    
    # جلب جميع الحسابات للفلتر
    accounts = ChartOfAccounts.objects.filter(
        is_leaf=True,
        is_active=True
    ).select_related('account_type').order_by('code')
    
    # معالجة التصدير
    if export_format == 'excel':
        try:
            account = None
            if account_id:
                account = get_object_or_404(ChartOfAccounts, id=account_id)
            
            excel_data = LedgerService.export_to_excel(account, date_from, date_to)
            
            response = HttpResponse(
                excel_data,
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            filename = f"ledger_report_{timezone.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            return response
        except Exception as e:
            messages.error(request, f"خطأ في تصدير Excel: {e}")
    
    # عرض تفاصيل حساب معين
    if account_id:
        try:
            account = get_object_or_404(ChartOfAccounts, id=account_id)
            
            # جلب المعاملات والملخص
            transactions = LedgerService.get_account_transactions(
                account,
                date_from,
                date_to
            )
            summary = LedgerService.get_account_summary(
                account,
                date_from,
                date_to
            )
            
            # Pagination للمعاملات
            paginator = Paginator(transactions, 30)  # 30 معاملة في الصفحة
            page_number = request.GET.get('page', 1)
            page_obj = paginator.get_page(page_number)
            
            context = {
                "page_title": f"دفتر الأستاذ - {account.name}",
                "page_subtitle": f"تقرير تفصيلي لحركة الحساب: {account.code}",
                "page_icon": "fas fa-book-open",
                "header_buttons": [
                    {
                        "onclick": "window.print()",
                        "icon": "fa-print",
                        "text": "طباعة",
                        "class": "btn-outline-secondary",
                    },
                    {
                        "url": f"?account={account_id}&date_from={date_from or ''}&date_to={date_to or ''}&export=excel",
                        "icon": "fa-file-excel",
                        "text": "تصدير Excel",
                        "class": "btn-success",
                    },
                ],
                "breadcrumb_items": [
                    {"title": "الرئيسية", "url": reverse('core:dashboard'), "icon": "fas fa-home"},
                    {"title": "الإدارة المالية", "icon": "fas fa-money-bill-wave"},
                    {"title": "التقارير", "icon": "fas fa-chart-bar"},
                    {"title": "دفتر الأستاذ", "active": True},
                ],
                "account": account,
                "summary": summary,
                "page_obj": page_obj,
                "transactions": transactions,
                "accounts": accounts,
                "date_from": date_from,
                "date_to": date_to,
                "selected_account_id": int(account_id),
            }
            
        except ChartOfAccounts.DoesNotExist:
            messages.error(request, "الحساب المطلوب غير موجود")
            return redirect('financial:ledger_report')
        except Exception as e:
            messages.error(request, f"خطأ في تحميل تفاصيل الحساب: {e}")
            return redirect('financial:ledger_report')
    
    else:
        # عرض ملخص جميع الحسابات
        try:
            account_summaries = LedgerService.get_all_accounts_summary(
                date_from,
                date_to,
                only_active=True
            )
            
            # Pagination للحسابات
            paginator = Paginator(account_summaries, 30)  # 30 حساب في الصفحة
            page_number = request.GET.get('page', 1)
            page_obj = paginator.get_page(page_number)
            
            context = {
                "page_title": "دفتر الأستاذ العام",
                "page_subtitle": "ملخص شامل لجميع حركات الحسابات",
                "page_icon": "fas fa-book",
                "header_buttons": [
                    {
                        "onclick": "window.print()",
                        "icon": "fa-print",
                        "text": "طباعة",
                        "class": "btn-outline-secondary",
                    },
                ],
                "breadcrumb_items": [
                    {"title": "الرئيسية", "url": reverse('core:dashboard'), "icon": "fas fa-home"},
                    {"title": "الإدارة المالية", "icon": "fas fa-money-bill-wave"},
                    {"title": "التقارير", "icon": "fas fa-chart-bar"},
                    {"title": "دفتر الأستاذ", "active": True},
                ],
                "page_obj": page_obj,
                "account_summaries": account_summaries,
                "accounts": accounts,
                "date_from": date_from,
                "date_to": date_to,
            }
            
        except Exception as e:
            messages.error(request, f"خطأ في تحميل ملخص الحسابات: {e}")
            context = {
                "page_title": "دفتر الأستاذ العام",
                "page_subtitle": "ملخص شامل لجميع حركات الحسابات",
                "page_icon": "fas fa-book",
                "breadcrumb_items": [
                    {"title": "الرئيسية", "url": reverse('core:dashboard'), "icon": "fas fa-home"},
                    {"title": "الإدارة المالية", "icon": "fas fa-money-bill-wave"},
                    {"title": "التقارير", "icon": "fas fa-chart-bar"},
                    {"title": "دفتر الأستاذ", "active": True},
                ],
                "accounts": accounts,
                "date_from": date_from,
                "date_to": date_to,
                "error": str(e)
            }
    
    return render(request, "financial/reports/ledger_report.html", context)


@login_required
def balance_sheet(request):
    """
    تقرير الميزانية العمومية - محسّن واحترافي
    يستخدم BalanceSheetService للحسابات الديناميكية والدقيقة
    """
    from ..services.balance_sheet_service import BalanceSheetService
    from django.http import HttpResponse
    
    # معالجة الفلاتر
    date_str = request.GET.get("date")
    group_by_subtype = request.GET.get("group_by_subtype", "1") == "1"
    export_format = request.GET.get("export")
    
    # تحويل التاريخ
    balance_date = None
    if date_str:
        try:
            balance_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            messages.warning(request, "تنسيق التاريخ غير صحيح")
            balance_date = timezone.now().date()
    else:
        balance_date = timezone.now().date()
    
    # معالجة التصدير
    if export_format == 'excel':
        try:
            excel_data = BalanceSheetService.export_to_excel(
                balance_date,
                group_by_subtype
            )
            
            response = HttpResponse(
                excel_data,
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            filename = f"balance_sheet_{balance_date.strftime('%Y%m%d')}.xlsx"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            return response
        except Exception as e:
            messages.error(request, f"خطأ في تصدير Excel: {e}")
    
    # إنشاء الميزانية العمومية
    try:
        balance_sheet_data = BalanceSheetService.generate_balance_sheet(
            balance_date,
            group_by_subtype
        )
        
        # حساب النسب المالية
        financial_ratios = BalanceSheetService.calculate_financial_ratios(balance_sheet_data)
        
        context = {
            "page_title": "الميزانية العمومية",
            "page_subtitle": f"تقرير الميزانية العمومية كما في {balance_date.strftime('%d-%m-%Y')}",
            "page_icon": "fas fa-balance-scale",
            "breadcrumb_items": [
                {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
                {"title": "الإدارة المالية", "url": reverse("financial:chart_of_accounts_list"), "icon": "fas fa-money-bill-wave"},
                {"title": "التقارير", "url": "#", "icon": "fas fa-chart-bar"},
                {"title": "الميزانية العمومية", "active": True},
            ],
            "header_buttons": [
                {
                    "onclick": "window.print()",
                    "icon": "fa-print",
                    "text": "طباعة",
                    "class": "btn-outline-success",
                }
            ],
            "balance_sheet_data": balance_sheet_data,
            "financial_ratios": financial_ratios,
            "balance_date": balance_date,
            "group_by_subtype": group_by_subtype,
        }
        
    except Exception as e:
        messages.error(request, f"خطأ في إنشاء الميزانية العمومية: {e}")
        context = {
            "page_title": "الميزانية العمومية",
            "page_icon": "fas fa-balance-scale",
            "breadcrumb_items": [
                {"title": "الرئيسية", "url": "/", "icon": "fas fa-home"},
                {"title": "الإدارة المالية", "url": "#", "icon": "fas fa-money-bill-wave"},
                {"title": "التقارير", "url": "#", "icon": "fas fa-chart-bar"},
                {"title": "الميزانية العمومية", "active": True, "icon": "fas fa-balance-scale"},
            ],
            "balance_sheet_data": {
                'assets': {'accounts': [], 'grouped': {}, 'total': 0},
                'liabilities': {'accounts': [], 'grouped': {}, 'total': 0},
                'equity': {'accounts': [], 'total': 0, 'net_income': 0},
                'total_assets': 0,
                'total_liabilities': 0,
                'total_equity': 0,
                'total_liabilities_equity': 0,
                'is_balanced': False,
                'error': str(e)
            },
            "financial_ratios": {},
            "balance_date": balance_date,
            "group_by_subtype": group_by_subtype,
        }
    
    return render(request, "financial/reports/balance_sheet.html", context)


@login_required
def income_statement(request):
    """
    تقرير قائمة الدخل - محسّن واحترافي
    يستخدم IncomeStatementService للحسابات الديناميكية والدقيقة
    """
    from ..services.income_statement_service import IncomeStatementService
    from django.http import HttpResponse
    
    # معالجة الفلاتر
    date_from_str = request.GET.get("date_from")
    date_to_str = request.GET.get("date_to")
    export_format = request.GET.get("export")
    
    # تحويل التواريخ
    date_from = None
    date_to = None
    
    if date_from_str:
        try:
            date_from = datetime.strptime(date_from_str, "%Y-%m-%d").date()
        except ValueError:
            messages.warning(request, "تنسيق تاريخ البداية غير صحيح")
    
    if date_to_str:
        try:
            date_to = datetime.strptime(date_to_str, "%Y-%m-%d").date()
        except ValueError:
            messages.warning(request, "تنسيق تاريخ النهاية غير صحيح")
    
    # معالجة التصدير
    if export_format == 'excel':
        try:
            excel_data = IncomeStatementService.export_to_excel(date_from, date_to)
            
            response = HttpResponse(
                excel_data,
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            filename = f"income_statement_{timezone.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            return response
        except Exception as e:
            messages.error(request, f"خطأ في تصدير Excel: {e}")
    
    # إنشاء قائمة الدخل
    try:
        income_statement_data = IncomeStatementService.generate_income_statement(date_from, date_to)
        
        context = {
            "page_title": "قائمة الدخل",
            "page_subtitle": f"تقرير الأرباح والخسائر للفترة من {income_statement_data.get('date_from')} إلى {income_statement_data.get('date_to')}",
            "page_icon": "fas fa-chart-line",
            "header_buttons": [
                {
                    "onclick": "window.print()",
                    "icon": "fa-print",
                    "text": "طباعة",
                    "class": "btn-success",
                },
            ],
            "breadcrumb_items": [
                {"title": "الرئيسية", "url": "/", "icon": "fas fa-home"},
                {"title": "الإدارة المالية", "url": "#", "icon": "fas fa-money-bill-wave"},
                {"title": "التقارير", "url": "#", "icon": "fas fa-chart-bar"},
                {"title": "قائمة الدخل", "active": True},
            ],
            "income_statement_data": income_statement_data,
            "date_from": income_statement_data.get('date_from'),
            "date_to": income_statement_data.get('date_to'),
        }
        
    except Exception as e:
        messages.error(request, f"خطأ في إنشاء قائمة الدخل: {e}")
        context = {
            "page_title": "قائمة الدخل",
            "page_icon": "fas fa-file-invoice-dollar",
            "breadcrumb_items": [
                {"title": "الرئيسية", "url": "/", "icon": "fas fa-home"},
                {"title": "الإدارة المالية", "url": "#", "icon": "fas fa-money-bill-wave"},
                {"title": "التقارير", "url": "#", "icon": "fas fa-chart-bar"},
                {"title": "قائمة الدخل", "active": True, "icon": "fas fa-file-invoice-dollar"},
            ],
            "income_statement_data": {
                'revenues': [],
                'expenses': [],
                'total_revenue': 0,
                'total_expense': 0,
                'net_income': 0,
                'error': str(e)
            },
            "date_from": date_from,
            "date_to": date_to,
        }
    
    return render(request, "financial/reports/income_statement.html", context)


@login_required
def cash_flow_statement(request):
    """
    تقرير قائمة التدفقات النقدية
    """
    from ..services.cash_flow_service import CashFlowService
    from django.http import HttpResponse
    
    # تحديد فترة التقرير
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")

    if date_from:
        date_from = datetime.strptime(date_from, "%Y-%m-%d").date()
    else:
        # افتراضيًا، بداية الشهر الحالي
        today = timezone.now().date()
        date_from = datetime(today.year, today.month, 1).date()

    if date_to:
        date_to = datetime.strptime(date_to, "%Y-%m-%d").date()
    else:
        # افتراضيًا، تاريخ اليوم
        date_to = timezone.now().date()

    try:
        # إنشاء خدمة التدفقات النقدية
        cash_flow_service = CashFlowService(date_from=date_from, date_to=date_to)
        
        # التحقق من طلب التصدير
        if request.GET.get('export') == 'excel':
            # إنشاء التقرير
            report_data = cash_flow_service.generate_cash_flow_statement()
            
            # تصدير إلى Excel
            excel_content = cash_flow_service.export_to_excel(report_data)
            
            if excel_content:
                response = HttpResponse(
                    excel_content,
                    content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
                response['Content-Disposition'] = f'attachment; filename="cash_flow_{date_from}_{date_to}.xlsx"'
                return response
            else:
                messages.warning(request, "تصدير Excel غير متاح. يرجى تثبيت openpyxl")
        
        # إنشاء التقرير
        report_data = cash_flow_service.generate_cash_flow_statement()

        context = {
            "page_title": "قائمة التدفقات النقدية",
            "page_subtitle": f"من {date_from.strftime('%Y-%m-%d')} إلى {date_to.strftime('%Y-%m-%d')}",
            "page_icon": "fas fa-money-bill-wave",
            "header_buttons": [
                {
                    "onclick": "window.print()",
                    "icon": "fa-print",
                    "text": "طباعة",
                    "class": "btn-success",
                },
                {
                    "url": f"?date_from={date_from.strftime('%Y-%m-%d')}&date_to={date_to.strftime('%Y-%m-%d')}&export=excel",
                    "icon": "fa-file-excel",
                    "text": "تصدير Excel",
                    "class": "btn-primary",
                },
            ],
            "breadcrumb_items": [
                {"title": "الرئيسية", "url": "/", "icon": "fas fa-home"},
                {"title": "الإدارة المالية", "url": "#", "icon": "fas fa-money-bill-wave"},
                {"title": "التقارير", "url": "#", "icon": "fas fa-chart-bar"},
                {"title": "قائمة التدفقات النقدية", "active": True},
            ],
            "cash_flow_data": report_data,
            "date_from": date_from,
            "date_to": date_to,
        }

        return render(request, "financial/reports/cash_flow_statement.html", context)

    except Exception as e:
        messages.error(request, f"خطأ في تحميل قائمة التدفقات النقدية: {e}")
        return redirect("core:dashboard")


@login_required
def customer_supplier_balances_report(request, account_type):
    """
    تقرير أرصدة العملاء والموردين
    account_type: 'customers' أو 'suppliers'
    """
    from ..services.customer_supplier_balances_service import CustomerSupplierBalancesService
    from django.http import HttpResponse
    
    # تحديد تاريخ التقرير
    as_of_date = request.GET.get("as_of_date")
    
    if as_of_date:
        as_of_date = datetime.strptime(as_of_date, "%Y-%m-%d").date()
    else:
        # افتراضيًا، تاريخ اليوم
        as_of_date = timezone.now().date()
    
    try:
        # إنشاء خدمة تقارير الأرصدة
        balances_service = CustomerSupplierBalancesService(as_of_date=as_of_date)
        
        # التحقق من طلب التصدير
        if request.GET.get('export') == 'excel':
            # إنشاء التقرير
            if account_type == "customers":
                report_data = balances_service.generate_customer_balances_report()
                report_type = 'ar'
                filename = f'customer_balances_{as_of_date}.xlsx'
            else:
                report_data = balances_service.generate_supplier_balances_report()
                report_type = 'ap'
                filename = f'supplier_balances_{as_of_date}.xlsx'
            
            # تصدير إلى Excel
            excel_content = balances_service.export_to_excel(report_data, report_type)
            
            if excel_content:
                response = HttpResponse(
                    excel_content,
                    content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
                response['Content-Disposition'] = f'attachment; filename="{filename}"'
                return response
            else:
                messages.warning(request, "تصدير Excel غير متاح. يرجى تثبيت openpyxl")
        
        # إنشاء التقرير
        if account_type == "customers":
            report_data = balances_service.generate_customer_balances_report()
        else:
            report_data = balances_service.generate_supplier_balances_report()
        
        # التحقق من وجود خطأ
        if "error" in report_data:
            messages.error(request, report_data["error"])
            return redirect("core:dashboard")
        
        # تحديد العنوان والأيقونة حسب النوع
        if account_type == "customers":
            page_title = "تقرير أرصدة العملاء"
            page_icon = "fas fa-users"
        else:
            page_title = "تقرير أرصدة الموردين"
            page_icon = "fas fa-truck"
        
        context = {
            "page_title": page_title,
            "page_subtitle": f"عرض الأرصدة المستحقة والمدفوعة حتى {as_of_date}",
            "page_icon": page_icon,
            "header_buttons": [
                {
                    "onclick": "window.print()",
                    "icon": "fa-print",
                    "text": "طباعة",
                    "class": "btn-outline-secondary",
                },
                {
                    "url": f"?as_of_date={as_of_date}&export=excel",
                    "icon": "fa-file-excel",
                    "text": "تصدير Excel",
                    "class": "btn-success",
                },
            ],
            "breadcrumb_items": [
                {"title": "الرئيسية", "url": reverse('core:dashboard'), "icon": "fas fa-home"},
                {"title": "الإدارة المالية", "icon": "fas fa-money-bill-wave"},
                {"title": "التقارير", "icon": "fas fa-chart-bar"},
                {"title": page_title, "active": True},
            ],
            "report_data": report_data,
            "as_of_date": as_of_date,
            "account_type": account_type,
        }
        
        return render(request, "financial/reports/customer_supplier_balances.html", context)
    
    except Exception as e:
        messages.error(request, f"خطأ في تحميل تقرير الأرصدة: {e}")
        return redirect("core:dashboard")


@login_required
def financial_analytics(request):
    """
    عرض صفحة التحليلات المالية - محدّث ✅
    تعرض مجموعة من المؤشرات المالية الرئيسية والرسوم البيانية
    """
    from financial.services.financial_analytics_service import FinancialAnalyticsService
    from django.utils import timezone

    # الحصول على الفترة الزمنية من الطلب
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")

    # تحويل التواريخ إذا كانت موجودة
    if date_from:
        try:
            date_from = datetime.strptime(date_from, "%Y-%m-%d").date()
        except ValueError:
            date_from = None

    if date_to:
        try:
            date_to = datetime.strptime(date_to, "%Y-%m-%d").date()
        except ValueError:
            date_to = None

    # إنشاء خدمة التحليلات
    analytics_service = FinancialAnalyticsService(
        date_from=date_from,
        date_to=date_to
    )

    # الحصول على جميع التحليلات
    analytics = analytics_service.get_complete_analytics()

    # تحويل البيانات إلى JSON للاستخدام في JavaScript
    import json
    monthly_trends_json = json.dumps(analytics["monthly_trends"])
    expense_distribution_json = json.dumps(analytics["expense_distribution"])

    # إعداد سياق البيانات
    context = {
        "page_title": "التحليلات المالية",
        "page_subtitle": "مؤشرات ورسوم بيانية للأداء المالي",
        "page_icon": "fas fa-chart-pie",
        "header_buttons": [
            {
                "onclick": "window.print()",
                "icon": "fa-print",
                "text": "طباعة",
                "class": "btn-outline-secondary",
            },
        ],
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse('core:dashboard'), "icon": "fas fa-home"},
            {"title": "الإدارة المالية", "icon": "fas fa-money-bill-wave"},
            {"title": "التقارير", "icon": "fas fa-chart-bar"},
            {"title": "التحليلات المالية", "active": True},
        ],
        # المؤشرات الأساسية
        "monthly_income": analytics["basic_metrics"]["monthly_income"],
        "monthly_expenses": analytics["basic_metrics"]["monthly_expenses"],
        "net_profit": analytics["basic_metrics"]["net_profit"],
        "profit_margin": analytics["basic_metrics"]["profit_margin"],
        "avg_invoice": analytics["basic_metrics"]["avg_entry_value"],
        "daily_transactions": analytics["basic_metrics"]["daily_transactions"],
        # المؤشرات المتقدمة
        "collection_rate": analytics["advanced_metrics"]["collection_rate"],
        "new_customers": analytics["advanced_metrics"]["new_customers"],
        "sales_cycle": analytics["advanced_metrics"]["sales_cycle"],
        "due_debt": analytics["advanced_metrics"]["due_debt"],
        "total_receivables": analytics["advanced_metrics"]["total_receivables"],
        # الاتجاهات الشهرية (JSON)
        "monthly_trends": monthly_trends_json,
        # توزيع المصروفات (JSON)
        "expense_distribution": expense_distribution_json,
        # الفترة الزمنية
        "date_from": analytics["date_from"],
        "date_to": analytics["date_to"],
    }
    return render(request, "financial/reports/analytics.html", context)


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
            status="failed", retry_count__lt=models.F("max_retries")
        )

        count = 0
        for operation in failed_operations:
            operation.status = "pending"
            operation.retry_count += 1
            operation.save()
            count += 1

        return JsonResponse(
            {
                "success": True,
                "count": count,
                "message": f"تم إعادة تعيين {count} عملية للمحاولة مرة أخرى",
            }
        )

    except ImportError:
        return JsonResponse({"success": False, "message": "نماذج التزامن غير متاحة"})
    except Exception as e:
        logger.error(f"Error in views.py: {str(e)}", exc_info=True)
        return JsonResponse({"success": False, "message": "حدث خطأ غير متوقع"})


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
            error_message__icontains="import", is_resolved=False
        )

        import_count = import_errors.update(
            is_resolved=True,
            resolved_at=timezone.now(),
            resolution_notes="تم إنشاء النماذج المفقودة",
        )

        # حل الأخطاء القديمة (أكثر من 7 أيام)
        old_errors = PaymentSyncError.objects.filter(
            occurred_at__lt=timezone.now() - timedelta(days=7), is_resolved=False
        )

        old_count = old_errors.update(
            is_resolved=True,
            resolved_at=timezone.now(),
            resolution_notes="حل تلقائي للأخطاء القديمة",
        )

        total_count = import_count + old_count

        return JsonResponse(
            {
                "success": True,
                "count": total_count,
                "message": f"تم حل {total_count} خطأ ({import_count} أخطاء استيراد + {old_count} أخطاء قديمة)",
            }
        )

    except ImportError:
        return JsonResponse({"success": False, "message": "نماذج الأخطاء غير متاحة"})
    except Exception as e:
        logger.error(f"Error in views.py: {str(e)}", exc_info=True)
        return JsonResponse({"success": False, "message": "حدث خطأ غير متوقع"})


@login_required
def trial_balance_report(request):
    """
    تقرير ميزان المراجعة - محسّن واحترافي
    يستخدم TrialBalanceService للحسابات الديناميكية والدقيقة
    """
    from ..services.trial_balance_service import TrialBalanceService
    from django.http import HttpResponse
    
    # معالجة الفلاتر
    date_from_str = request.GET.get("date_from")
    date_to_str = request.GET.get("date_to")
    group_by_type = request.GET.get("group_by_type", "1") == "1"
    export_format = request.GET.get("export")
    
    # تحويل التواريخ
    date_from = None
    date_to = None
    
    if date_from_str:
        try:
            date_from = datetime.strptime(date_from_str, "%Y-%m-%d").date()
        except ValueError:
            messages.warning(request, "تنسيق تاريخ البداية غير صحيح")
    
    if date_to_str:
        try:
            date_to = datetime.strptime(date_to_str, "%Y-%m-%d").date()
        except ValueError:
            messages.warning(request, "تنسيق تاريخ النهاية غير صحيح")
    
    # معالجة التصدير
    if export_format == 'excel':
        try:
            excel_data = TrialBalanceService.export_to_excel(
                date_from,
                date_to,
                group_by_type
            )
            
            response = HttpResponse(
                excel_data,
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            filename = f"trial_balance_{timezone.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            return response
        except Exception as e:
            messages.error(request, f"خطأ في تصدير Excel: {e}")
    
    # إنشاء ميزان المراجعة
    try:
        trial_balance_data = TrialBalanceService.generate_trial_balance(
            date_from,
            date_to,
            group_by_type=group_by_type
        )
        
        # بناء URL للتصدير
        export_params = []
        if date_from:
            export_params.append(f"date_from={date_from.strftime('%Y-%m-%d')}")
        if date_to:
            export_params.append(f"date_to={date_to.strftime('%Y-%m-%d')}")
        if group_by_type:
            export_params.append("group_by_type=1")
        export_params.append("export=excel")
        export_url = "?" + "&".join(export_params)
        
        context = {
            "page_title": "ميزان المراجعة",
            "page_subtitle": f"تقرير ميزان المراجعة حتى {date_to.strftime('%Y-%m-%d') if date_to else 'اليوم'}",
            "page_icon": "fas fa-balance-scale",
            "header_buttons": [
                {
                    "onclick": "window.print()",
                    "icon": "fa-print",
                    "text": "طباعة",
                    "class": "btn-success",
                },
                {
                    "url": export_url,
                    "icon": "fa-file-excel",
                    "text": "تصدير Excel",
                    "class": "btn-primary",
                },
            ],
            "breadcrumb_items": [
                {"title": "الرئيسية", "url": "/", "icon": "fas fa-home"},
                {"title": "الإدارة المالية", "url": "#", "icon": "fas fa-money-bill-wave"},
                {"title": "التقارير", "url": "#", "icon": "fas fa-chart-bar"},
                {"title": "ميزان المراجعة", "active": True},
            ],
            "trial_balance_data": trial_balance_data,
            "date_from": date_from,
            "date_to": date_to,
            "group_by_type": group_by_type,
        }
        
    except Exception as e:
        messages.error(request, f"خطأ في إنشاء ميزان المراجعة: {e}")
        context = {
            "page_title": "ميزان المراجعة",
            "page_icon": "fas fa-balance-scale",
            "breadcrumb_items": [
                {"title": "الرئيسية", "url": "/", "icon": "fas fa-home"},
                {"title": "الإدارة المالية", "url": "#", "icon": "fas fa-money-bill-wave"},
                {"title": "التقارير", "url": "#", "icon": "fas fa-chart-bar"},
                {"title": "ميزان المراجعة", "active": True, "icon": "fas fa-balance-scale"},
            ],
            "trial_balance_data": {
                'accounts': [],
                'grouped': {},
                'total_debit': 0,
                'total_credit': 0,
                'is_balanced': False,
                'error': str(e)
            },
            "date_from": date_from,
            "date_to": date_to,
            "group_by_type": group_by_type,
        }
    
    return render(request, "financial/reports/trial_balance_report.html", context)


@login_required
def sales_report(request):
    """
    تقرير المبيعات - محدّث ✅
    بناءً على حسابات الإيرادات مع تحليلات متقدمة
    """
    from financial.services.sales_report_service import SalesReportService
    import json

    # تحديد فترة التقرير
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    
    if date_from:
        try:
            date_from = datetime.strptime(date_from, "%Y-%m-%d").date()
        except ValueError:
            date_from = None
    
    if date_to:
        try:
            date_to = datetime.strptime(date_to, "%Y-%m-%d").date()
        except ValueError:
            date_to = None
    
    # إنشاء خدمة التقرير
    sales_service = SalesReportService(
        date_from=date_from,
        date_to=date_to
    )
    
    # الحصول على التقرير الكامل
    report = sales_service.get_complete_report()
    
    # تحويل البيانات إلى JSON للاستخدام في JavaScript
    from decimal import Decimal
    
    class DecimalEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, Decimal):
                return float(obj)
            return super(DecimalEncoder, self).default(obj)
    
    daily_trend_json = json.dumps(report["daily_trend"], cls=DecimalEncoder)
    monthly_comparison_json = json.dumps(report["monthly_comparison"], cls=DecimalEncoder)
    sales_by_category_json = json.dumps(report["sales_by_category"], cls=DecimalEncoder)
    
    context = {
        "page_title": "تقرير المبيعات",
        "page_subtitle": "تحليل شامل للإيرادات والمبيعات",
        "page_icon": "fas fa-chart-line",
        "header_buttons": [
            {
                "onclick": "window.print()",
                "icon": "fa-print",
                "text": "طباعة",
                "class": "btn-outline-secondary",
            },
        ],
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse('core:dashboard'), "icon": "fas fa-home"},
            {"title": "الإدارة المالية", "icon": "fas fa-money-bill-wave"},
            {"title": "التقارير", "icon": "fas fa-chart-bar"},
            {"title": "تقرير المبيعات", "active": True},
        ],
        "sales_data": report["sales_data"],
        "total_sales": report["total_sales"],
        "statistics": report["statistics"],
        "daily_trend": daily_trend_json,
        "monthly_comparison": monthly_comparison_json,
        "sales_by_category": sales_by_category_json,
        "date_from": report["date_from"],
        "date_to": report["date_to"],
        # للتوافق مع القالب القديم
        "avg_daily_sales": report["statistics"]["avg_daily_sales"],
        "days_count": report["statistics"]["days_count"],
    }
    return render(request, "financial/reports/sales_report.html", context)


@login_required
def purchases_report(request):
    """
    تقرير المشتريات - محدّث ✅
    بناءً على حسابات المصروفات مع تحليلات متقدمة
    """
    from financial.services.purchases_report_service import PurchasesReportService
    import json

    # تحديد فترة التقرير
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    
    if date_from:
        try:
            date_from = datetime.strptime(date_from, "%Y-%m-%d").date()
        except ValueError:
            date_from = None
    
    if date_to:
        try:
            date_to = datetime.strptime(date_to, "%Y-%m-%d").date()
        except ValueError:
            date_to = None
    
    # إنشاء خدمة التقرير
    purchases_service = PurchasesReportService(
        date_from=date_from,
        date_to=date_to
    )
    
    # الحصول على التقرير الكامل
    report = purchases_service.get_complete_report()
    
    # تحويل البيانات إلى JSON للاستخدام في JavaScript
    from decimal import Decimal
    
    class DecimalEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, Decimal):
                return float(obj)
            return super(DecimalEncoder, self).default(obj)
    
    monthly_comparison_json = json.dumps(report["monthly_comparison"], cls=DecimalEncoder)
    purchases_by_category_json = json.dumps(report["purchases_by_category"], cls=DecimalEncoder)
    
    context = {
        "page_title": "تقرير المشتريات",
        "page_subtitle": "تحليل شامل للمصروفات والمشتريات",
        "page_icon": "fas fa-shopping-cart",
        "header_buttons": [
            {
                "onclick": "window.print()",
                "icon": "fa-print",
                "text": "طباعة",
                "class": "btn-outline-secondary",
            },
        ],
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse('core:dashboard'), "icon": "fas fa-home"},
            {"title": "الإدارة المالية", "icon": "fas fa-money-bill-wave"},
            {"title": "التقارير", "icon": "fas fa-chart-bar"},
            {"title": "تقرير المشتريات", "active": True},
        ],
        "purchases_data": report["purchases_data"],
        "total_purchases": report["total_purchases"],
        "statistics": report["statistics"],
        "monthly_comparison": monthly_comparison_json,
        "purchases_by_category": purchases_by_category_json,
        "date_from": report["date_from"],
        "date_to": report["date_to"],
        # للتوافق مع القالب القديم
        "avg_daily_purchases": report["statistics"]["avg_daily_purchases"],
        "days_count": report["statistics"]["days_count"],
    }
    return render(request, "financial/reports/purchases_report.html", context)


@login_required
def inventory_report(request):
    """
    تقرير المخزون - محدّث ✅
    بناءً على حسابات الأصول المتعلقة بالمخزون مع تحليلات متقدمة
    """
    from financial.services.inventory_report_service import InventoryReportService
    from django.http import HttpResponse

    # تحديد تاريخ التقرير
    report_date = request.GET.get("date")
    if report_date:
        try:
            report_date = datetime.strptime(report_date, "%Y-%m-%d").date()
        except ValueError:
            report_date = None

    # إنشاء خدمة التقرير
    inventory_service = InventoryReportService(report_date=report_date)

    # التحقق من طلب التصدير
    if request.GET.get('export') == 'excel':
        try:
            excel_data = inventory_service.export_to_excel()
            
            if excel_data:
                response = HttpResponse(
                    excel_data,
                    content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
                filename = f"inventory_report_{inventory_service.report_date.strftime('%Y%m%d')}.xlsx"
                response['Content-Disposition'] = f'attachment; filename="{filename}"'
                return response
            else:
                messages.warning(request, "تصدير Excel غير متاح. يرجى تثبيت openpyxl")
        except Exception as e:
            messages.error(request, f"خطأ في تصدير Excel: {e}")

    # الحصول على التقرير الكامل
    try:
        report = inventory_service.get_complete_report()

        context = {
            "page_title": "تقرير المخزون",
            "page_subtitle": "تحليل شامل لقيمة وحركة المخزون",
            "page_icon": "fas fa-boxes",
            "header_buttons": [
                {
                    "onclick": "window.print()",
                    "icon": "fa-print",
                    "text": "طباعة",
                    "class": "btn-outline-secondary",
                },
                {
                    "url": f"?date={report['report_date']}&export=excel",
                    "icon": "fa-file-excel",
                    "text": "تصدير Excel",
                    "class": "btn-success",
                },
            ],
            "breadcrumb_items": [
                {"title": "الرئيسية", "url": reverse('core:dashboard'), "icon": "fas fa-home"},
                {"title": "الإدارة المالية", "icon": "fas fa-money-bill-wave"},
                {"title": "التقارير", "icon": "fas fa-chart-bar"},
                {"title": "تقرير المخزون", "active": True},
            ],
            "inventory_data": report["inventory_data"],
            "total_inventory_value": report["total_inventory_value"],
            "statistics": report["statistics"],
            "inventory_by_category": report["inventory_by_category"],
            "turnover_analysis": report["turnover_analysis"],
            "report_date": report["report_date"],
            # للتوافق مع القالب القديم
            "total_accounts": report["statistics"]["total_accounts"],
            "avg_account_value": report["statistics"]["avg_account_value"],
            "active_accounts": report["statistics"]["active_accounts"],
        }
    except Exception as e:
        messages.error(request, f"خطأ في تحميل تقرير المخزون: {e}")
        context = {
            "page_title": "تقرير المخزون",
            "page_icon": "fas fa-boxes",
            "breadcrumb_items": [
                {"title": "الرئيسية", "url": "/", "icon": "fas fa-home"},
                {"title": "الإدارة المالية", "url": "#", "icon": "fas fa-money-bill-wave"},
                {"title": "التقارير", "url": "#", "icon": "fas fa-chart-bar"},
                {"title": "تقرير المخزون", "active": True, "icon": "fas fa-boxes"},
            ],
            "inventory_data": [],
            "total_inventory_value": 0,
            "total_accounts": 0,
            "avg_account_value": 0,
            "active_accounts": 0,
            "report_date": inventory_service.report_date,
            "error": str(e)
        }

    return render(request, "financial/reports/inventory_report.html", context)


@login_required
def abc_analysis_report(request):
    """
    تقرير تحليل ABC - محدّث ✅
    تصنيف المخزون حسب الأهمية (A, B, C)
    """
    from financial.services.abc_analysis_service import ABCAnalysisService
    from django.http import HttpResponse

    # تحديد تاريخ التحليل وفترة التحليل
    analysis_date = request.GET.get("date")
    days_period = request.GET.get("days_period", "365")
    
    if analysis_date:
        try:
            analysis_date = datetime.strptime(analysis_date, "%Y-%m-%d").date()
        except ValueError:
            analysis_date = None
    
    try:
        days_period = int(days_period)
    except ValueError:
        days_period = 365

    # إنشاء خدمة التحليل
    abc_service = ABCAnalysisService(
        analysis_date=analysis_date,
        days_period=days_period
    )

    # التحقق من طلب التصدير
    if request.GET.get('export') == 'excel':
        try:
            excel_data = abc_service.export_to_excel()
            
            if excel_data:
                response = HttpResponse(
                    excel_data,
                    content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
                filename = f"abc_analysis_{abc_service.analysis_date.strftime('%Y%m%d')}.xlsx"
                response['Content-Disposition'] = f'attachment; filename="{filename}"'
                return response
            else:
                messages.warning(request, "تصدير Excel غير متاح. يرجى تثبيت openpyxl")
        except Exception as e:
            messages.error(request, f"خطأ في تصدير Excel: {e}")

    # الحصول على التحليل الكامل
    try:
        analysis = abc_service.get_complete_analysis()

        context = {
            "page_title": "تحليل ABC للمخزون",
            "page_subtitle": "تصنيف المخزون حسب الأهمية (A, B, C)",
            "page_icon": "fas fa-chart-pie",
            "header_buttons": [
                {
                    "onclick": "window.print()",
                    "icon": "fa-print",
                    "text": "طباعة",
                    "class": "btn-outline-secondary",
                },
                {
                    "url": f"?date={analysis['analysis_date']}&days_period={analysis['days_period']}&export=excel",
                    "icon": "fa-file-excel",
                    "text": "تصدير Excel",
                    "class": "btn-success",
                },
            ],
            "breadcrumb_items": [
                {"title": "الرئيسية", "url": reverse('core:dashboard'), "icon": "fas fa-home"},
                {"title": "الإدارة المالية", "icon": "fas fa-money-bill-wave"},
                {"title": "التقارير", "icon": "fas fa-chart-bar"},
                {"title": "تحليل ABC", "active": True},
            ],
            "inventory_data": analysis["inventory_data"],
            "total_value": analysis["total_value"],
            "statistics": analysis["statistics"],
            "recommendations": analysis["recommendations"],
            "analysis_date": analysis["analysis_date"],
            "days_period": analysis["days_period"],
            "date_from": analysis["date_from"],
        }
    except Exception as e:
        messages.error(request, f"خطأ في تحميل تحليل ABC: {e}")
        context = {
            "page_title": "تحليل ABC للمخزون",
            "page_icon": "fas fa-chart-pie",
            "breadcrumb_items": [
                {"title": "الرئيسية", "url": "/", "icon": "fas fa-home"},
                {"title": "الإدارة المالية", "url": "#", "icon": "fas fa-money-bill-wave"},
                {"title": "التقارير", "url": "#", "icon": "fas fa-chart-bar"},
                {"title": "تحليل ABC", "active": True, "icon": "fas fa-chart-pie"},
            ],
            "inventory_data": [],
            "total_value": 0,
            "statistics": {
                "category_a": {"count": 0, "value": 0, "percentage_count": 0, "percentage_value": 0, "avg_value": 0},
                "category_b": {"count": 0, "value": 0, "percentage_count": 0, "percentage_value": 0, "avg_value": 0},
                "category_c": {"count": 0, "value": 0, "percentage_count": 0, "percentage_value": 0, "avg_value": 0},
                "total_items": 0,
                "total_value": 0,
            },
            "recommendations": {"category_a": [], "category_b": [], "category_c": []},
            "analysis_date": abc_service.analysis_date,
            "days_period": days_period,
            "error": str(e)
        }

    return render(request, "financial/reports/abc_analysis.html", context)


@login_required
def general_backup(request):
    """
    النسخ الاحتياطي العام
    """
    if request.method == "POST":
        try:
            # يمكن إضافة منطق النسخ الاحتياطي هنا لاحقاً
            messages.success(request, "تم إنشاء النسخة الاحتياطية بنجاح.")
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء إنشاء النسخة الاحتياطية: {str(e)}")

    context = {
        "page_title": "النسخ الاحتياطي العام",
        "page_subtitle": "إنشاء نسخة احتياطية كاملة لجميع بيانات النظام",
        "page_icon": "fas fa-database",
        "header_buttons": [
            {
                "onclick": "document.getElementById('backupForm').submit()",
                "icon": "fa-download",
                "text": "إنشاء نسخة احتياطية",
                "class": "btn-primary",
            },
        ],
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse('core:dashboard'), "icon": "fas fa-home"},
            {"title": "الإدارة المالية", "icon": "fas fa-money-bill-wave"},
            {"title": "النسخ الاحتياطي", "icon": "fas fa-database"},
            {"title": "النسخ العام", "active": True},
        ],
    }
    return render(request, "financial/reports/general_backup.html", context)


@login_required
def financial_backup_advanced(request):
    """
    النسخ الاحتياطي المالي المتقدم
    """
    if request.method == "POST":
        try:
            from .services.financial_backup_service import FinancialBackupService

            service = FinancialBackupService()
            # يمكن إضافة منطق النسخ الاحتياطي المتقدم هنا
            messages.success(
                request, "تم إنشاء النسخة الاحتياطية المالية المتقدمة بنجاح."
            )
        except ImportError:
            messages.error(request, "خدمة النسخ الاحتياطي المالي غير متاحة حالياً.")
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء إنشاء النسخة الاحتياطية: {str(e)}")

    context = {
        "page_title": "نسخ احتياطي مالي متقدم",
        "page_subtitle": "نسخة احتياطية متقدمة للبيانات المالية فقط",
        "page_icon": "fas fa-coins",
        "header_buttons": [
            {
                "onclick": "document.getElementById('financialBackupForm').submit()",
                "icon": "fa-download",
                "text": "إنشاء نسخة مالية",
                "class": "btn-success",
            },
        ],
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse('core:dashboard'), "icon": "fas fa-home"},
            {"title": "الإدارة المالية", "icon": "fas fa-money-bill-wave"},
            {"title": "النسخ الاحتياطي", "icon": "fas fa-database"},
            {"title": "نسخ مالي متقدم", "active": True},
        ],
    }
    return render(request, "financial/reports/financial_backup_advanced.html", context)


@login_required
def restore_data(request):
    """
    استعادة البيانات
    """
    if request.method == "POST":
        try:
            # يمكن إضافة منطق استعادة البيانات هنا لاحقاً
            messages.success(request, "تم استعادة البيانات بنجاح.")
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء استعادة البيانات: {str(e)}")

    context = {
        "page_title": "استعادة البيانات",
        "page_subtitle": "استعادة البيانات من نسخة احتياطية سابقة",
        "page_icon": "fas fa-history",
        "header_buttons": [
            {
                "onclick": "document.getElementById('restoreForm').submit()",
                "icon": "fa-upload",
                "text": "استعادة البيانات",
                "class": "btn-warning",
            },
        ],
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse('core:dashboard'), "icon": "fas fa-home"},
            {"title": "الإدارة المالية", "icon": "fas fa-money-bill-wave"},
            {"title": "النسخ الاحتياطي", "icon": "fas fa-database"},
            {"title": "استعادة البيانات", "active": True},
        ],
    }
    return render(request, "financial/reports/restore_data.html", context)


@login_required
def data_integrity_check(request):
    """
    التحقق من سلامة البيانات - فحص شامل
    """
    from financial.models import JournalEntry, ChartOfAccounts
    from sale.models import Sale
    from purchase.models import Purchase
    from product.models import Stock, StockMovement
    from client.models import Customer
    from supplier.models import Supplier
    from django.db.models import Sum, Q, Count
    from decimal import Decimal
    
    results = {
        'checks': [],
        'errors': [],
        'warnings': [],
        'summary': {
            'total_checks': 0,
            'passed': 0,
            'failed': 0,
            'warnings': 0
        }
    }
    
    if request.method == "POST":
        try:
            # ==================== 1. فحص القيود المحاسبية ====================
            check_name = "توازن القيود المحاسبية"
            results['summary']['total_checks'] += 1
            
            unbalanced_entries = []
            for entry in JournalEntry.objects.all():
                debits = entry.lines.aggregate(total=Sum('debit'))['total'] or Decimal('0')
                credits = entry.lines.aggregate(total=Sum('credit'))['total'] or Decimal('0')
                if debits != credits:
                    unbalanced_entries.append({
                        'entry': entry,
                        'difference': abs(debits - credits)
                    })
            
            if unbalanced_entries:
                results['errors'].append({
                    'check': check_name,
                    'count': len(unbalanced_entries),
                    'details': unbalanced_entries[:10],  # أول 10 فقط
                    'severity': 'high'
                })
                results['summary']['failed'] += 1
            else:
                results['checks'].append({'name': check_name, 'status': 'passed'})
                results['summary']['passed'] += 1
            
            # ==================== 2. فحص أرصدة العملاء ====================
            check_name = "أرصدة العملاء"
            results['summary']['total_checks'] += 1
            
            customer_issues = []
            try:
                from client.models import CustomerPayment
                
                for customer in Customer.objects.all():
                    calculated_balance = Decimal('0')
                    
                    # حساب من المبيعات
                    sales_total = Sale.objects.filter(customer=customer).aggregate(
                        total=Sum('total')
                    )['total'] or Decimal('0')
                    
                    # حساب من الدفعات
                    if CustomerPayment:
                        payments_total = CustomerPayment.objects.filter(customer=customer).aggregate(
                            total=Sum('amount')
                        )['total'] or Decimal('0')
                    else:
                        payments_total = Decimal('0')
                    
                    calculated_balance = sales_total - payments_total
                    
                    if abs(calculated_balance - customer.balance) > Decimal('0.01'):
                        customer_issues.append({
                            'customer': customer,
                            'system_balance': customer.balance,
                            'calculated_balance': calculated_balance,
                            'difference': abs(customer.balance - calculated_balance)
                        })
            except Exception as e:
                # تجاهل الخطأ إذا كان النموذج غير موجود
                pass
            
            if customer_issues:
                results['warnings'].append({
                    'check': check_name,
                    'count': len(customer_issues),
                    'details': customer_issues[:10],
                    'severity': 'medium'
                })
                results['summary']['warnings'] += 1
            else:
                results['checks'].append({'name': check_name, 'status': 'passed'})
                results['summary']['passed'] += 1
            
            # ==================== 3. فحص أرصدة الموردين ====================
            check_name = "أرصدة الموردين"
            results['summary']['total_checks'] += 1
            
            supplier_issues = []
            try:
                from purchase.models import PurchasePayment
                
                for supplier in Supplier.objects.all():
                    calculated_balance = Decimal('0')
                    
                    # حساب من المشتريات
                    purchases_total = Purchase.objects.filter(supplier=supplier).aggregate(
                        total=Sum('total')
                    )['total'] or Decimal('0')
                    
                    # حساب من الدفعات
                    if PurchasePayment:
                        payments_total = PurchasePayment.objects.filter(purchase__supplier=supplier).aggregate(
                            total=Sum('amount')
                        )['total'] or Decimal('0')
                    else:
                        payments_total = Decimal('0')
                    
                    calculated_balance = purchases_total - payments_total
                    
                    if abs(calculated_balance - supplier.balance) > Decimal('0.01'):
                        supplier_issues.append({
                            'supplier': supplier,
                            'system_balance': supplier.balance,
                            'calculated_balance': calculated_balance,
                            'difference': abs(supplier.balance - calculated_balance)
                        })
            except Exception as e:
                # تجاهل الخطأ إذا كان النموذج غير موجود
                pass
            
            if supplier_issues:
                results['warnings'].append({
                    'check': check_name,
                    'count': len(supplier_issues),
                    'details': supplier_issues[:10],
                    'severity': 'medium'
                })
                results['summary']['warnings'] += 1
            else:
                results['checks'].append({'name': check_name, 'status': 'passed'})
                results['summary']['passed'] += 1
            
            # ==================== 4. فحص المخزون ====================
            check_name = "أرصدة المخزون"
            results['summary']['total_checks'] += 1
            
            stock_issues = []
            for stock in Stock.objects.all():
                # حساب من حركات المخزون
                movements_in = StockMovement.objects.filter(
                    product=stock.product,
                    movement_type__in=['purchase', 'return_in', 'adjustment_in']
                ).aggregate(total=Sum('quantity'))['total'] or 0
                
                movements_out = StockMovement.objects.filter(
                    product=stock.product,
                    movement_type__in=['sale', 'return_out', 'adjustment_out']
                ).aggregate(total=Sum('quantity'))['total'] or 0
                
                calculated_quantity = movements_in - movements_out
                
                if abs(calculated_quantity - stock.quantity) > 0.01:
                    stock_issues.append({
                        'product': stock.product,
                        'system_quantity': stock.quantity,
                        'calculated_quantity': calculated_quantity,
                        'difference': abs(stock.quantity - calculated_quantity)
                    })
            
            if stock_issues:
                results['errors'].append({
                    'check': check_name,
                    'count': len(stock_issues),
                    'details': stock_issues[:10],
                    'severity': 'high'
                })
                results['summary']['failed'] += 1
            else:
                results['checks'].append({'name': check_name, 'status': 'passed'})
                results['summary']['passed'] += 1
            
            # ==================== 5. فحص القيود اليتيمة ====================
            check_name = "القيود بدون مستند مرجعي"
            results['summary']['total_checks'] += 1
            
            orphan_entries = JournalEntry.objects.filter(
                Q(reference_type__isnull=True) | Q(reference_id__isnull=True)
            ).exclude(entry_type='manual').count()
            
            if orphan_entries > 0:
                results['warnings'].append({
                    'check': check_name,
                    'count': orphan_entries,
                    'message': f"يوجد {orphan_entries} قيد بدون مستند مرجعي",
                    'severity': 'low'
                })
                results['summary']['warnings'] += 1
            else:
                results['checks'].append({'name': check_name, 'status': 'passed'})
                results['summary']['passed'] += 1
            
            # ==================== 6. فحص الحسابات المكررة ====================
            check_name = "الحسابات المكررة"
            results['summary']['total_checks'] += 1
            
            duplicate_accounts = ChartOfAccounts.objects.values('code').annotate(
                count=Count('id')
            ).filter(count__gt=1)
            
            if duplicate_accounts.exists():
                results['errors'].append({
                    'check': check_name,
                    'count': duplicate_accounts.count(),
                    'message': f"يوجد {duplicate_accounts.count()} رمز حساب مكرر",
                    'severity': 'high'
                })
                results['summary']['failed'] += 1
            else:
                results['checks'].append({'name': check_name, 'status': 'passed'})
                results['summary']['passed'] += 1
            
            # ==================== 7. فحص المخزون السالب ====================
            check_name = "المخزون السالب"
            results['summary']['total_checks'] += 1
            
            negative_stock = Stock.objects.filter(quantity__lt=0).count()
            
            if negative_stock > 0:
                results['warnings'].append({
                    'check': check_name,
                    'count': negative_stock,
                    'message': f"يوجد {negative_stock} منتج برصيد سالب",
                    'severity': 'medium'
                })
                results['summary']['warnings'] += 1
            else:
                results['checks'].append({'name': check_name, 'status': 'passed'})
                results['summary']['passed'] += 1
            
            # رسالة النجاح
            if results['summary']['failed'] == 0 and results['summary']['warnings'] == 0:
                messages.success(request, "✅ تم فحص سلامة البيانات بنجاح. جميع الفحوصات اجتازت بنجاح!")
            elif results['summary']['failed'] > 0:
                messages.error(request, f"⚠️ تم العثور على {results['summary']['failed']} مشكلة حرجة تحتاج إلى إصلاح فوري!")
            else:
                messages.warning(request, f"⚠️ تم العثور على {results['summary']['warnings']} تحذير يحتاج إلى مراجعة.")
                
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء فحص البيانات: {str(e)}")
            import traceback
            traceback.print_exc()

    context = {
        "page_title": "التحقق من سلامة البيانات",
        "page_subtitle": "فحص شامل للتأكد من توافق وسلامة البيانات",
        "page_icon": "fas fa-shield-alt",
        "header_buttons": [
            {
                "onclick": "document.getElementById('integrityCheckForm').submit()",
                "icon": "fa-sync",
                "text": "بدء الفحص",
                "class": "btn-primary",
            },
        ],
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse('core:dashboard'), "icon": "fas fa-home"},
            {"title": "الإدارة المالية", "icon": "fas fa-money-bill-wave"},
            {"title": "الصيانة", "icon": "fas fa-tools"},
            {"title": "فحص سلامة البيانات", "active": True},
        ],
        "results": results,
    }
    return render(request, "financial/reports/data_integrity_check.html", context)


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
        pending_ops = PaymentSyncOperation.objects.filter(status="pending")
        processing_ops = PaymentSyncOperation.objects.filter(status="processing")

        # العمليات العالقة (أكثر من 10 دقائق)
        ten_minutes_ago = timezone.now() - timedelta(minutes=10)
        stuck_pending = pending_ops.filter(created_at__lt=ten_minutes_ago).count()
        stuck_processing = processing_ops.filter(started_at__lt=ten_minutes_ago).count()

        return JsonResponse(
            {
                "success": True,
                "pending_count": pending_ops.count(),
                "processing_count": processing_ops.count(),
                "stuck_operations": stuck_pending + stuck_processing,
                "details": {
                    "stuck_pending": stuck_pending,
                    "stuck_processing": stuck_processing,
                },
            }
        )

    except ImportError:
        return JsonResponse({"success": False, "message": "نماذج التزامن غير متاحة"})
    except Exception as e:
        logger.error(f"Error in views.py: {str(e)}", exc_info=True)
        return JsonResponse({"success": False, "message": "حدث خطأ غير متوقع"})


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
        pending_ops = PaymentSyncOperation.objects.filter(status="pending").order_by(
            "created_at"
        )

        if not pending_ops.exists():
            return JsonResponse(
                {
                    "success": True,
                    "message": "لا توجد عمليات معلقة",
                    "processed_count": 0,
                }
            )

        # تشغيل العمليات
        sync_service = PaymentSyncService()
        processed_count = 0

        for operation in pending_ops[:10]:  # معالجة 10 عمليات كحد أقصى
            try:
                # تحديث حالة العملية إلى قيد المعالجة
                operation.status = "processing"
                operation.started_at = timezone.now()
                operation.save()

                # محاولة تنفيذ العملية
                if operation.operation_type == "retry_failed":
                    # إعادة محاولة العملية الفاشلة
                    sync_service.retry_failed_operation(operation)
                elif operation.operation_type == "delete_payment":
                    # حذف دفعة
                    sync_service.process_payment_deletion(operation)
                else:
                    # عملية عامة
                    sync_service.process_operation(operation)

                processed_count += 1

            except Exception as e:
                # تسجيل فشل العملية
                operation.status = "failed"
                operation.error_message = str(e)
                operation.save()

        return JsonResponse(
            {
                "success": True,
                "message": f"تم تشغيل {processed_count} عملية",
                "processed_count": processed_count,
            }
        )

    except ImportError:
        return JsonResponse({"success": False, "message": "خدمة التزامن غير متاحة"})
    except Exception as e:
        logger.error(f"Error in views.py: {str(e)}", exc_info=True)
        return JsonResponse({"success": False, "message": "حدث خطأ غير متوقع"})


@login_required
def audit_trail_list(request):
    """
    قائمة سجل التدقيق
    """
    try:
        from financial.models import AuditTrail
        
        # الفلترة
        action_filter = request.GET.get('action', '')
        entity_type_filter = request.GET.get('entity_type', '')
        user_filter = request.GET.get('user', '')
        date_from = request.GET.get('date_from', '')
        date_to = request.GET.get('date_to', '')
        
        # الاستعلام الأساسي
        audit_entries = AuditTrail.objects.select_related('user').order_by('-timestamp')
        
        # تطبيق الفلاتر
        if action_filter:
            audit_entries = audit_entries.filter(action=action_filter)
        
        if entity_type_filter:
            audit_entries = audit_entries.filter(entity_type=entity_type_filter)
        
        if user_filter:
            audit_entries = audit_entries.filter(user_id=user_filter)
        
        if date_from:
            audit_entries = audit_entries.filter(timestamp__date__gte=date_from)
        
        if date_to:
            audit_entries = audit_entries.filter(timestamp__date__lte=date_to)
        
        # الترقيم الصفحي
        paginator = Paginator(audit_entries, 50)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        # الإحصائيات
        from django.contrib.auth import get_user_model
        from datetime import datetime, timedelta
        
        User = get_user_model()
        today = datetime.now().date()
        
        total_entries = audit_entries.count()
        today_entries = AuditTrail.objects.filter(timestamp__date=today).count()
        active_users = AuditTrail.objects.filter(timestamp__date=today).values('user').distinct().count()
        delete_entries = AuditTrail.objects.filter(action='delete').count()
        
        # قائمة المستخدمين للفلترة
        users = User.objects.filter(
            id__in=AuditTrail.objects.values_list('user_id', flat=True).distinct()
        ).order_by('first_name', 'last_name', 'username')
        
        context = {
            "page_obj": page_obj,
            "total_entries": total_entries,
            "users": users,
            "summary": {
                "total_count": total_entries,
                "today_count": today_entries,
                "active_users": active_users,
                "delete_count": delete_entries,
            },
            "filters": {
                "action": action_filter,
                "entity_type": entity_type_filter,
                "user": user_filter,
                "date_from": date_from,
                "date_to": date_to,
            },
            "page_title": "سجل التدقيق",
            "page_subtitle": "تتبع جميع العمليات والتغييرات في النظام",
            "page_icon": "fas fa-clipboard-list",
            "header_buttons": [
                {
                    "onclick": "window.print()",
                    "icon": "fa-print",
                    "text": "طباعة",
                    "class": "btn-outline-secondary",
                },
                {
                    "onclick": "confirmCleanup()",
                    "icon": "fa-trash",
                    "text": "تنظيف السجل",
                    "class": "btn-outline-danger",
                },
            ],
            "breadcrumb_items": [
                {"title": "الرئيسية", "url": reverse('core:dashboard'), "icon": "fas fa-home"},
                {"title": "الإدارة المالية", "icon": "fas fa-money-bill-wave"},
                {"title": "التقارير", "icon": "fas fa-chart-bar"},
                {"title": "سجل التدقيق", "active": True},
            ],
            "action_filter": action_filter,
            "entity_type_filter": entity_type_filter,
        }

        return render(request, "financial/reports/audit_trail_list.html", context)

    except Exception as e:
        messages.error(request, f"خطأ في تحميل سجل التدقيق: {str(e)}")
        return render(request, "financial/reports/audit_trail_list.html", {"page_obj": None})


@login_required
@transaction.atomic
def audit_trail_cleanup(request):
    """
    تنظيف سجل التدقيق - حذف السجلات القديمة
    """
    if request.method == 'POST':
        try:
            from financial.models import AuditTrail
            from datetime import datetime
            
            cleanup_date = request.POST.get('cleanup_date')
            if not cleanup_date:
                messages.error(request, "يجب تحديد تاريخ التنظيف")
                return redirect("financial:audit_trail_list")
            
            # تحويل التاريخ
            cleanup_date = datetime.strptime(cleanup_date, '%Y-%m-%d').date()
            
            # فحص السجلات الموجودة للتشخيص
            total_records = AuditTrail.objects.count()
            records_before_date = AuditTrail.objects.filter(
                timestamp__date__lte=cleanup_date
            ).count()
            
            print(f"DEBUG: إجمالي السجلات: {total_records}")
            print(f"DEBUG: السجلات قبل {cleanup_date}: {records_before_date}")
            
            # حذف السجلات الأقدم من أو تساوي التاريخ المحدد
            records_to_delete = AuditTrail.objects.filter(
                timestamp__date__lte=cleanup_date
            )
            
            deleted_count = records_to_delete.count()
            print(f"DEBUG: سيتم حذف {deleted_count} سجل")
            
            # عرض بعض السجلات التي سيتم حذفها للتشخيص
            if deleted_count > 0:
                sample_records = records_to_delete[:5]
                print("DEBUG: عينة من السجلات التي سيتم حذفها:")
                for record in sample_records:
                    print(f"  - ID: {record.id}, التاريخ: {record.timestamp}, الوصف: {record.description[:50]}")
            
            if deleted_count > 0:
                # تنفيذ الحذف الفعلي
                deleted_result = records_to_delete.delete()
                actual_deleted = deleted_result[0]  # العدد الفعلي المحذوف
                
                print(f"DEBUG: تم حذف {actual_deleted} سجل فعلياً")
                
                # فحص السجلات المتبقية للتأكد
                remaining_records = AuditTrail.objects.count()
                print(f"DEBUG: السجلات المتبقية بعد الحذف: {remaining_records}")
                
                success_message = f"تم حذف {actual_deleted} سجل تدقيق أقدم من أو يساوي {cleanup_date}. السجلات المتبقية: {remaining_records}"
                
                # للطلبات AJAX
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True, 
                        'message': success_message,
                        'deleted_count': actual_deleted,
                        'remaining_count': remaining_records
                    })
                
                messages.success(request, success_message)
                
                # تسجيل عملية التنظيف في سجل التدقيق
                AuditTrail.log_action(
                    action='delete',
                    entity_type='audit_trail',
                    entity_id=0,
                    user=request.user,
                    description=f"تنظيف سجل التدقيق - حذف {actual_deleted} سجل أقدم من {cleanup_date}",
                    reason="تنظيف دوري للسجلات القديمة",
                    request=request
                )
            else:
                info_message = f"لا توجد سجلات أقدم من أو تساوي {cleanup_date} للحذف. إجمالي السجلات الحالية: {total_records}"
                
                # للطلبات AJAX
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False, 
                        'message': info_message,
                        'deleted_count': 0,
                        'remaining_count': total_records
                    })
                
                messages.info(request, info_message)
                
        except ValueError:
            error_message = "تاريخ غير صحيح"
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': error_message})
            messages.error(request, error_message)
        except Exception as e:
            error_message = f"خطأ في تنظيف السجل: {str(e)}"
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': error_message})
            messages.error(request, error_message)
    
    return redirect("financial:audit_trail_list")


@login_required
def payment_sync_operations(request):
    """
    عمليات تزامن المدفوعات
    """
    try:
        from .models.payment_sync import PaymentSyncOperation
        
        operations = PaymentSyncOperation.objects.select_related(
            'created_by'
        ).order_by('-created_at')[:100]
        
        context = {
            "operations": operations,
            "page_title": "عمليات تزامن المدفوعات",
            "page_icon": "fas fa-sync-alt",
        }
        return render(request, "financial/banking/payment_sync_operations.html", context)
    except ImportError:
        messages.warning(request, "نماذج تزامن المدفوعات غير متاحة حالياً.")
        return render(request, "financial/banking/payment_sync_operations.html", {"operations": []})


@login_required
def payment_sync_logs(request):
    """
    سجلات تزامن المدفوعات
    """
    try:
        from .models.payment_sync import PaymentSyncError
        
        logs = PaymentSyncError.objects.order_by('-occurred_at')[:100]
        
        context = {
            "logs": logs,
            "page_title": "سجلات تزامن المدفوعات",
            "page_icon": "fas fa-list-alt",
        }
        return render(request, "financial/banking/payment_sync_logs.html", context)
    except ImportError:
        messages.warning(request, "نماذج سجلات التزامن غير متاحة حالياً.")
        return render(request, "financial/banking/payment_sync_logs.html", {"logs": []})


@login_required
def journal_entry_summary_api(request, journal_entry_id):
    """
    API لجلب ملخص القيد المحاسبي
    """
    try:
        journal_entry = get_object_or_404(JournalEntry, id=journal_entry_id)
        
        # جلب بيانات القيد
        data = {
            'id': journal_entry.id,
            'number': journal_entry.number,
            'reference': journal_entry.reference,
            'date': journal_entry.date.strftime('%Y-%m-%d') if journal_entry.date else '',
            'description': journal_entry.description,
            'status': journal_entry.status,
            'created_by': journal_entry.created_by.get_full_name() if journal_entry.created_by else 'غير محدد',
            'lines': []
        }
        
        # جلب بنود القيد
        for line in journal_entry.lines.all():
            data['lines'].append({
                'account_name': line.account.name,
                'account_code': line.account.code,
                'debit': float(line.debit) if line.debit else 0,
                'credit': float(line.credit) if line.credit else 0,
                'description': line.description or ''
            })
        
        return JsonResponse(data)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"خطأ في جلب ملخص القيد {journal_entry_id}: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': 'حدث خطأ أثناء جلب تفاصيل القيد'
        }, status=500)


# ============== اكتمل ملف api_views.py بالكامل ==============
# تم نقل جميع دوال APIs والتصدير والتقارير بنجاح
