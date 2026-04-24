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
import logging

logger = logging.getLogger(__name__)


def generate_balance_sheet_optimized(balance_date, group_by_subtype=True):
    """
    إنشاء الميزانية العمومية بطريقة محسنة مع استخدام الطرق المحسنة
    """
    from decimal import Decimal
    
    # جلب جميع الحسابات النهائية النشطة مع تحسين الاستعلام
    accounts = ChartOfAccounts.objects.select_related('account_type').filter(
        is_leaf=True,
        is_active=True
    ).order_by('account_type__category', 'code')
    
    # تصنيف الحسابات
    assets = []
    liabilities = []
    equity = []
    
    # معالجة الحسابات بشكل محسن
    for account in accounts:
        balance = account.get_balance_optimized(date_to=balance_date, use_cache=True)
        
        if balance != 0:  # تجاهل الحسابات بدون رصيد
            account_data = {
                'id': account.id,
                'code': account.code,
                'name': account.name,
                'balance': balance,
                'account_type': account.account_type.name,
                'category': account.category
            }
            
            if account.category == 'asset':
                assets.append(account_data)
            elif account.category == 'liability':
                liabilities.append(account_data)
            elif account.category == 'equity':
                equity.append(account_data)
    
    # حساب المجاميع
    total_assets = sum(acc['balance'] for acc in assets)
    total_liabilities = sum(acc['balance'] for acc in liabilities)
    total_equity = sum(acc['balance'] for acc in equity)
    
    # حساب صافي الدخل من حسابات الإيرادات والمصروفات
    revenue_accounts = ChartOfAccounts.objects.select_related('account_type').filter(
        is_leaf=True,
        is_active=True,
        account_type__category='revenue'
    )
    
    expense_accounts = ChartOfAccounts.objects.select_related('account_type').filter(
        is_leaf=True,
        is_active=True,
        account_type__category='expense'
    )
    
    total_revenue = sum(
        acc.get_balance_optimized(date_to=balance_date, use_cache=True) 
        for acc in revenue_accounts
    )
    total_expenses = sum(
        acc.get_balance_optimized(date_to=balance_date, use_cache=True) 
        for acc in expense_accounts
    )
    
    net_income = total_revenue - total_expenses
    total_equity += net_income
    
    # التحقق من توازن الميزانية
    total_liabilities_equity = total_liabilities + total_equity
    is_balanced = abs(total_assets - total_liabilities_equity) < Decimal('0.01')
    
    return {
        'assets': {
            'accounts': assets,
            'total': total_assets,
            'grouped': group_accounts_by_type(assets) if group_by_subtype else {}
        },
        'liabilities': {
            'accounts': liabilities,
            'total': total_liabilities,
            'grouped': group_accounts_by_type(liabilities) if group_by_subtype else {}
        },
        'equity': {
            'accounts': equity,
            'total': total_equity,
            'net_income': net_income
        },
        'total_assets': total_assets,
        'total_liabilities': total_liabilities,
        'total_equity': total_equity,
        'total_liabilities_equity': total_liabilities_equity,
        'is_balanced': is_balanced,
        'balance_date': balance_date
    }


def group_accounts_by_type(accounts):
    """
    تجميع الحسابات حسب النوع
    """
    grouped = {}
    for account in accounts:
        account_type = account['account_type']
        if account_type not in grouped:
            grouped[account_type] = {
                'accounts': [],
                'total': Decimal('0')
            }
        grouped[account_type]['accounts'].append(account)
        grouped[account_type]['total'] += account['balance']
    
    return grouped


def calculate_financial_ratios_optimized(balance_sheet_data):
    """
    حساب النسب المالية المحسنة
    """
    ratios = {}
    
    try:
        total_assets = balance_sheet_data['total_assets']
        total_liabilities = balance_sheet_data['total_liabilities']
        total_equity = balance_sheet_data['total_equity']
        
        if total_assets > 0:
            # نسبة الدين إلى الأصول
            ratios['debt_to_assets'] = (total_liabilities / total_assets) * 100
            
            # نسبة حقوق الملكية إلى الأصول
            ratios['equity_to_assets'] = (total_equity / total_assets) * 100
        
        if total_equity > 0:
            # نسبة الدين إلى حقوق الملكية
            ratios['debt_to_equity'] = (total_liabilities / total_equity) * 100
        
        # نسبة السيولة (إذا كانت متاحة)
        current_assets = Decimal('0')
        current_liabilities = Decimal('0')
        
        # البحث عن الأصول والخصوم المتداولة
        for asset in balance_sheet_data['assets']['accounts']:
            if 'متداول' in asset['account_type'] or 'نقد' in asset['account_type']:
                current_assets += asset['balance']
        
        for liability in balance_sheet_data['liabilities']['accounts']:
            if 'متداول' in liability['account_type'] or 'قصير' in liability['account_type']:
                current_liabilities += liability['balance']
        
        if current_liabilities > 0:
            ratios['current_ratio'] = current_assets / current_liabilities
        
    except (KeyError, ZeroDivisionError, TypeError):
        pass
    
    return ratios


def generate_balance_sheet_excel_optimized(balance_date, group_by_subtype=True):
    """
    تصدير الميزانية العمومية إلى Excel بطريقة محسنة
    """
    try:
        import openpyxl
        from openpyxl.styles import Font, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
        
        # إنشاء الميزانية
        balance_sheet_data = generate_balance_sheet_optimized(balance_date, group_by_subtype)
        
        # إنشاء ملف Excel
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "الميزانية العمومية"
        
        # تنسيق الخطوط والحدود
        header_font = Font(bold=True, size=14)
        subheader_font = Font(bold=True, size=12)
        normal_font = Font(size=11)
        border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        
        # العنوان الرئيسي
        ws.merge_cells('A1:D1')
        ws['A1'] = f"الميزانية العمومية كما في {balance_date.strftime('%Y-%m-%d')}"
        ws['A1'].font = header_font
        ws['A1'].alignment = Alignment(horizontal='center')
        
        row = 3
        
        # الأصول
        ws[f'A{row}'] = "الأصول"
        ws[f'A{row}'].font = subheader_font
        row += 1
        
        for asset in balance_sheet_data['assets']['accounts']:
            ws[f'A{row}'] = asset['code']
            ws[f'B{row}'] = asset['name']
            ws[f'C{row}'] = float(asset['balance'])
            row += 1
        
        ws[f'B{row}'] = "إجمالي الأصول"
        ws[f'C{row}'] = float(balance_sheet_data['total_assets'])
        ws[f'B{row}'].font = subheader_font
        ws[f'C{row}'].font = subheader_font
        row += 2
        
        # الخصوم
        ws[f'A{row}'] = "الخصوم"
        ws[f'A{row}'].font = subheader_font
        row += 1
        
        for liability in balance_sheet_data['liabilities']['accounts']:
            ws[f'A{row}'] = liability['code']
            ws[f'B{row}'] = liability['name']
            ws[f'C{row}'] = float(liability['balance'])
            row += 1
        
        ws[f'B{row}'] = "إجمالي الخصوم"
        ws[f'C{row}'] = float(balance_sheet_data['total_liabilities'])
        ws[f'B{row}'].font = subheader_font
        ws[f'C{row}'].font = subheader_font
        row += 2
        
        # حقوق الملكية
        ws[f'A{row}'] = "حقوق الملكية"
        ws[f'A{row}'].font = subheader_font
        row += 1
        
        for equity in balance_sheet_data['equity']['accounts']:
            ws[f'A{row}'] = equity['code']
            ws[f'B{row}'] = equity['name']
            ws[f'C{row}'] = float(equity['balance'])
            row += 1
        
        # صافي الدخل
        ws[f'B{row}'] = "صافي الدخل"
        ws[f'C{row}'] = float(balance_sheet_data['equity']['net_income'])
        row += 1
        
        ws[f'B{row}'] = "إجمالي حقوق الملكية"
        ws[f'C{row}'] = float(balance_sheet_data['total_equity'])
        ws[f'B{row}'].font = subheader_font
        ws[f'C{row}'].font = subheader_font
        row += 2
        
        # المجموع النهائي
        ws[f'B{row}'] = "إجمالي الخصوم وحقوق الملكية"
        ws[f'C{row}'] = float(balance_sheet_data['total_liabilities_equity'])
        ws[f'B{row}'].font = header_font
        ws[f'C{row}'].font = header_font
        
        # تطبيق التنسيق على جميع الخلايا
        for row_cells in ws.iter_rows():
            for cell in row_cells:
                if cell.value is not None:
                    cell.border = border
                    if cell.font == Font():
                        cell.font = normal_font
        
        # ضبط عرض الأعمدة
        ws.column_dimensions['A'].width = 15
        ws.column_dimensions['B'].width = 40
        ws.column_dimensions['C'].width = 20
        
        # حفظ الملف في الذاكرة
        from io import BytesIO
        output = BytesIO()
        wb.save(output)
        output.seek(0)
        
        return output.getvalue()
        
    except ImportError:
        return None


def handle_progressive_ledger_load(request, account_id, date_from, date_to, page_size):
    """
    معالجة التحميل التدريجي لبيانات دفتر الأستاذ
    """
    try:
        page = int(request.GET.get('page', 1))
        account = get_object_or_404(ChartOfAccounts, id=account_id)
        
        # جلب المعاملات بشكل محسن
        transactions, _ = get_account_transactions_optimized(account, date_from, date_to)
        
        # تطبيق Pagination
        paginator = Paginator(transactions, page_size)
        page_obj = paginator.get_page(page)
        
        # تحويل البيانات إلى JSON
        transactions_data = []
        for transaction in page_obj:
            transactions_data.append({
                'date': transaction.get('date', '').strftime('%Y-%m-%d') if transaction.get('date') else '',
                'reference': transaction.get('reference', ''),
                'description': transaction.get('description', ''),
                'debit': float(transaction.get('debit', 0)),
                'credit': float(transaction.get('credit', 0)),
                'balance': float(transaction.get('balance', 0)),
            })
        
        return JsonResponse({
            'success': True,
            'transactions': transactions_data,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
            'page_number': page_obj.number,
            'total_pages': paginator.num_pages,
            'total_count': paginator.count,
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def get_account_transactions_optimized(account, date_from=None, date_to=None):
    """
    جلب معاملات الحساب بطريقة محسنة مع استخدام الطرق المحسنة
    """
    from .journal_entry import JournalEntryLine
    from django.db.models import Q, F
    from decimal import Decimal
    
    # بناء الاستعلام المحسن
    query = Q(account=account, journal_entry__status="posted")
    
    if date_from:
        query &= Q(journal_entry__date__gte=date_from)
    if date_to:
        query &= Q(journal_entry__date__lte=date_to)
    
    # جلب البنود مع تحسين الاستعلام
    lines = JournalEntryLine.objects.select_related(
        'journal_entry', 'account'
    ).filter(query).order_by(
        'journal_entry__date', 'journal_entry__id', 'id'
    )
    
    # تحضير قائمة المعاملات مع حساب الرصيد التراكمي
    transactions = []
    running_balance = account.opening_balance or Decimal('0')
    
    # إضافة الرصيد الافتتاحي كأول معاملة إذا كان موجوداً
    if account.opening_balance and account.opening_balance != 0:
        opening_date = account.opening_balance_date or date(2020, 1, 1)
        if (not date_from or opening_date >= date_from) and (not date_to or opening_date <= date_to):
            transactions.append({
                'date': opening_date,
                'reference': 'رصيد افتتاحي',
                'description': 'الرصيد الافتتاحي للحساب',
                'debit': account.opening_balance if account.nature == 'debit' and account.opening_balance > 0 else Decimal('0'),
                'credit': account.opening_balance if account.nature == 'credit' and account.opening_balance > 0 else Decimal('0'),
                'balance': running_balance,
                'is_opening': True
            })
    
    # معالجة البنود
    for line in lines:
        # حساب الرصيد التراكمي حسب طبيعة الحساب
        if account.nature == 'debit':
            running_balance += line.debit - line.credit
        else:
            running_balance += line.credit - line.debit
        
        transactions.append({
            'date': line.journal_entry.date,
            'reference': line.journal_entry.reference or f"قيد رقم {line.journal_entry.id}",
            'description': line.description or line.journal_entry.description,
            'debit': line.debit,
            'credit': line.credit,
            'balance': running_balance,
            'journal_entry_id': line.journal_entry.id,
            'line_id': line.id,
            'is_opening': False
        })
    
    # حساب الملخص
    total_debit = sum(t['debit'] for t in transactions)
    total_credit = sum(t['credit'] for t in transactions)
    
    summary = {
        'opening_balance': account.opening_balance or Decimal('0'),
        'total_debit': total_debit,
        'total_credit': total_credit,
        'closing_balance': running_balance,
        'net_movement': total_debit - total_credit,
        'transaction_count': len(transactions)
    }
    
    return transactions, summary


def get_all_accounts_summary_optimized(date_from=None, date_to=None):
    """
    جلب ملخص جميع الحسابات بطريقة محسنة
    """
    from django.db.models import Sum, Count, Q
    from decimal import Decimal
    
    # جلب الحسابات النهائية النشطة
    accounts = ChartOfAccounts.objects.filter(
        is_leaf=True,
        is_active=True
    ).select_related('account_type').order_by('code')
    
    summaries = []
    
    for account in accounts:
        # استخدام الطريقة المحسنة لحساب الرصيد
        current_balance = account.get_balance_optimized(
            date_from=date_from,
            date_to=date_to,
            use_cache=True
        )
        
        # جلب إحصائيات المعاملات
        from .journal_entry import JournalEntryLine
        
        query = Q(account=account, journal_entry__status="posted")
        if date_from:
            query &= Q(journal_entry__date__gte=date_from)
        if date_to:
            query &= Q(journal_entry__date__lte=date_to)
        
        stats = JournalEntryLine.objects.filter(query).aggregate(
            total_debit=Sum('debit'),
            total_credit=Sum('credit'),
            transaction_count=Count('id')
        )
        
        # إضافة الملخص فقط للحسابات التي لها حركة أو رصيد
        if (current_balance != 0 or 
            stats['transaction_count'] > 0 or 
            (account.opening_balance and account.opening_balance != 0)):
            
            summaries.append({
                'account': account,
                'current_balance': current_balance,
                'total_debit': stats['total_debit'] or Decimal('0'),
                'total_credit': stats['total_credit'] or Decimal('0'),
                'transaction_count': stats['transaction_count'] or 0,
                'net_movement': (stats['total_debit'] or Decimal('0')) - (stats['total_credit'] or Decimal('0')),
                'account_type': account.account_type.name,
                'category': account.category
            })
    
    return summaries


def generate_ledger_excel_optimized(account, date_from=None, date_to=None):
    """
    تصدير دفتر الأستاذ إلى Excel بطريقة محسنة
    """
    try:
        import openpyxl
        from openpyxl.styles import Font, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
        
        # إنشاء ملف Excel
        wb = openpyxl.Workbook()
        ws = wb.active
        
        if account:
            ws.title = f"دفتر الأستاذ - {account.code}"
            
            # جلب المعاملات
            transactions, summary = get_account_transactions_optimized(account, date_from, date_to)
            
            # تنسيق الخطوط والحدود
            header_font = Font(bold=True, size=14)
            subheader_font = Font(bold=True, size=12)
            normal_font = Font(size=11)
            border = Border(
                left=Side(style='thin'),
                right=Side(style='thin'),
                top=Side(style='thin'),
                bottom=Side(style='thin')
            )
            
            # العنوان الرئيسي
            ws.merge_cells('A1:F1')
            ws['A1'] = f"دفتر الأستاذ - {account.name} ({account.code})"
            ws['A1'].font = header_font
            ws['A1'].alignment = Alignment(horizontal='center')
            
            # معلومات الفترة
            row = 2
            if date_from or date_to:
                period_text = f"الفترة: من {date_from or 'البداية'} إلى {date_to or 'النهاية'}"
                ws.merge_cells(f'A{row}:F{row}')
                ws[f'A{row}'] = period_text
                ws[f'A{row}'].font = subheader_font
                ws[f'A{row}'].alignment = Alignment(horizontal='center')
                row += 1
            
            row += 1
            
            # رؤوس الأعمدة
            headers = ['التاريخ', 'المرجع', 'الوصف', 'مدين', 'دائن', 'الرصيد']
            for col, header in enumerate(headers, 1):
                cell = ws.cell(row=row, column=col, value=header)
                cell.font = subheader_font
                cell.border = border
                cell.alignment = Alignment(horizontal='center')
            
            row += 1
            
            # البيانات
            for transaction in transactions:
                ws.cell(row=row, column=1, value=transaction['date'].strftime('%Y-%m-%d') if transaction['date'] else '')
                ws.cell(row=row, column=2, value=transaction['reference'])
                ws.cell(row=row, column=3, value=transaction['description'])
                ws.cell(row=row, column=4, value=float(transaction['debit']))
                ws.cell(row=row, column=5, value=float(transaction['credit']))
                ws.cell(row=row, column=6, value=float(transaction['balance']))
                
                # تطبيق التنسيق
                for col in range(1, 7):
                    ws.cell(row=row, column=col).border = border
                    ws.cell(row=row, column=col).font = normal_font
                
                row += 1
            
            # الملخص
            row += 1
            ws.cell(row=row, column=3, value="إجمالي المدين:").font = subheader_font
            ws.cell(row=row, column=4, value=float(summary['total_debit'])).font = subheader_font
            row += 1
            ws.cell(row=row, column=3, value="إجمالي الدائن:").font = subheader_font
            ws.cell(row=row, column=5, value=float(summary['total_credit'])).font = subheader_font
            row += 1
            ws.cell(row=row, column=3, value="الرصيد الختامي:").font = subheader_font
            ws.cell(row=row, column=6, value=float(summary['closing_balance'])).font = subheader_font
            
        else:
            # تصدير ملخص جميع الحسابات
            ws.title = "ملخص دفتر الأستاذ العام"
            
            summaries = get_all_accounts_summary_optimized(date_from, date_to)
            
            # العنوان
            ws.merge_cells('A1:G1')
            ws['A1'] = "ملخص دفتر الأستاذ العام"
            ws['A1'].font = Font(bold=True, size=14)
            ws['A1'].alignment = Alignment(horizontal='center')
            
            # رؤوس الأعمدة
            headers = ['كود الحساب', 'اسم الحساب', 'نوع الحساب', 'إجمالي مدين', 'إجمالي دائن', 'الرصيد الحالي', 'عدد المعاملات']
            for col, header in enumerate(headers, 1):
                cell = ws.cell(row=3, column=col, value=header)
                cell.font = Font(bold=True)
                cell.alignment = Alignment(horizontal='center')
            
            # البيانات
            for row_idx, summary in enumerate(summaries, 4):
                ws.cell(row=row_idx, column=1, value=summary['account'].code)
                ws.cell(row=row_idx, column=2, value=summary['account'].name)
                ws.cell(row=row_idx, column=3, value=summary['account_type'])
                ws.cell(row=row_idx, column=4, value=float(summary['total_debit']))
                ws.cell(row=row_idx, column=5, value=float(summary['total_credit']))
                ws.cell(row=row_idx, column=6, value=float(summary['current_balance']))
                ws.cell(row=row_idx, column=7, value=summary['transaction_count'])
        
        # ضبط عرض الأعمدة
        for col in range(1, 8):
            ws.column_dimensions[get_column_letter(col)].width = 15
        
        # حفظ الملف في الذاكرة
        from io import BytesIO
        output = BytesIO()
        wb.save(output)
        output.seek(0)
        
        return output.getvalue()
        
    except ImportError:
        return None


# إضافة دالة محسنة لتصدير التقارير
def optimize_report_export(report_data, report_type="balance_sheet"):
    """
    تحسين تصدير التقارير مع ضغط البيانات الكبيرة
    """
    try:
        import gzip
        import json
        
        # تحويل البيانات إلى JSON
        json_data = json.dumps(report_data, default=str, ensure_ascii=False)
        
        # ضغط البيانات إذا كانت كبيرة (أكثر من 1MB)
        if len(json_data.encode('utf-8')) > 1024 * 1024:
            compressed_data = gzip.compress(json_data.encode('utf-8'))
            return compressed_data, True  # مضغوط
        else:
            return json_data.encode('utf-8'), False  # غير مضغوط
            
    except Exception:
        return None, False

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
def api_financial_categories(request):
    """API لجلب التصنيفات المالية النشطة للمصروفات والإيرادات مع الفرعية"""
    try:
        from ..models import FinancialCategory, FinancialSubcategory
        
        category_type = request.GET.get('type', 'expense')
        
        # جلب التصنيفات المالية النشطة
        categories_qs = FinancialCategory.objects.filter(is_active=True)
        
        if category_type == 'income':
            # للإيرادات: التصنيفات التي لها حساب إيراد افتراضي
            categories_qs = categories_qs.filter(default_revenue_account__isnull=False)
        else:
            # للمصروفات: التصنيفات التي لها حساب مصروف افتراضي
            categories_qs = categories_qs.filter(default_expense_account__isnull=False)
        
        categories_qs = categories_qs.order_by('display_order', 'name')
        
        # بناء القائمة مع التصنيفات الفرعية
        categories_list = []
        for category in categories_qs:
            cat_data = {
                'id': category.id,
                'name': category.name,
                'code': category.code,
                'subcategories': []
            }
            
            # جلب التصنيفات الفرعية النشطة
            subcategories = category.subcategories.filter(is_active=True).order_by('display_order', 'name')
            for subcat in subcategories:
                cat_data['subcategories'].append({
                    'id': subcat.id,
                    'name': subcat.name,
                    'code': subcat.code
                })
            
            categories_list.append(cat_data)
        
        return JsonResponse({'categories': categories_list}, safe=False)
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
    تقرير دفتر الأستاذ العام - محسّن واحترافي مع التحميل التدريجي
    يستخدم الطرق المحسنة والتخزين المؤقت لمعالجة البيانات الكبيرة
    """
    from django.http import HttpResponse, JsonResponse
    from django.core.paginator import Paginator
    from django.core.cache import cache
    from django.db.models import Prefetch
    import hashlib
    import json
    
    # معالجة الفلاتر
    account_id = request.GET.get("account")
    date_from_str = request.GET.get("date_from")
    date_to_str = request.GET.get("date_to")
    export_format = request.GET.get("export")  # excel أو pdf
    page_size = int(request.GET.get("page_size", "50"))  # حجم الصفحة القابل للتخصيص
    use_cache = request.GET.get("use_cache", "1") == "1"
    progressive_load = request.GET.get("progressive", "0") == "1"
    
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
    
    # جلب جميع الحسابات للفلتر مع تحسين الاستعلام
    accounts = ChartOfAccounts.objects.filter(
        is_leaf=True,
        is_active=True
    ).select_related('account_type').only(
        'id', 'code', 'name', 'account_type__name'
    ).order_by('code')
    
    # معالجة التصدير
    if export_format == 'excel':
        try:
            account = None
            if account_id:
                account = get_object_or_404(ChartOfAccounts, id=account_id)
            
            # محاولة استخدام خدمة دفتر الأستاذ إذا كانت متاحة
            try:
                from ..services.ledger_service import LedgerService
                excel_data = LedgerService.export_to_excel(account, date_from, date_to)
            except ImportError:
                # استخدام التنفيذ المحسن المباشر
                excel_data = generate_ledger_excel_optimized(account, date_from, date_to)
            
            response = HttpResponse(
                excel_data,
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            filename = f"ledger_report_{timezone.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            return response
        except Exception as e:
            messages.error(request, f"خطأ في تصدير Excel: {e}")
    
    # معالجة طلبات AJAX للتحميل التدريجي
    if progressive_load and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return handle_progressive_ledger_load(request, account_id, date_from, date_to, page_size)
    
    # عرض تفاصيل حساب معين
    if account_id:
        try:
            account = get_object_or_404(ChartOfAccounts, id=account_id)
            
            # إنشاء مفتاح التخزين المؤقت
            cache_key_data = f"ledger_{account_id}_{date_from}_{date_to}_{page_size}"
            cache_key = f"ledger_{hashlib.md5(cache_key_data.encode()).hexdigest()}"
            
            # محاولة الحصول على البيانات من التخزين المؤقت
            cached_data = None
            if use_cache:
                cached_data = cache.get(cache_key)
            
            if cached_data:
                transactions, summary = cached_data
                messages.info(request, "تم تحميل البيانات من التخزين المؤقت لتحسين الأداء")
            else:
                # جلب المعاملات والملخص بطريقة محسنة
                try:
                    from ..services.ledger_service import LedgerService
                    transactions = LedgerService.get_account_transactions(
                        account, date_from, date_to
                    )
                    summary = LedgerService.get_account_summary(
                        account, date_from, date_to
                    )
                except ImportError:
                    # استخدام التنفيذ المحسن المباشر
                    transactions, summary = get_account_transactions_optimized(
                        account, date_from, date_to
                    )
                
                # حفظ في التخزين المؤقت لمدة 15 دقيقة
                if use_cache:
                    cache.set(cache_key, (transactions, summary), 900)
            
            # Pagination محسن للمعاملات
            paginator = Paginator(transactions, page_size)
            page_number = request.GET.get('page', 1)
            page_obj = paginator.get_page(page_number)
            
            # بناء أزرار الهيدر
            header_buttons = [
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
            ]
            
            # إضافة زر تحديث إذا كانت البيانات مخزنة مؤقتاً
            if cached_data:
                header_buttons.append({
                    "url": f"?account={account_id}&date_from={date_from or ''}&date_to={date_to or ''}&use_cache=0",
                    "icon": "fa-sync",
                    "text": "تحديث البيانات",
                    "class": "btn-outline-warning",
                })
            
            context = {
                "page_title": f"دفتر الأستاذ - {account.name}",
                "page_subtitle": f"تقرير تفصيلي لحركة الحساب: {account.code}",
                "page_icon": "fas fa-book-open",
                "header_buttons": header_buttons,
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
                "page_size": page_size,
                "is_cached": cached_data is not None,
                "progressive_load_enabled": len(transactions) > 100,  # تفعيل التحميل التدريجي للبيانات الكبيرة
            }
            
        except ChartOfAccounts.DoesNotExist:
            messages.error(request, "الحساب المطلوب غير موجود")
            return redirect('financial:ledger_report')
        except Exception as e:
            messages.error(request, f"خطأ في تحميل تفاصيل الحساب: {e}")
            return redirect('financial:ledger_report')
    
    else:
        # عرض ملخص جميع الحسابات مع تحسين الأداء
        try:
            # إنشاء مفتاح التخزين المؤقت للملخص العام
            cache_key_data = f"ledger_summary_{date_from}_{date_to}"
            cache_key = f"ledger_summary_{hashlib.md5(cache_key_data.encode()).hexdigest()}"
            
            # محاولة الحصول على البيانات من التخزين المؤقت
            cached_summaries = None
            if use_cache:
                cached_summaries = cache.get(cache_key)
            
            if cached_summaries:
                account_summaries = cached_summaries
                messages.info(request, "تم تحميل ملخص الحسابات من التخزين المؤقت")
            else:
                # جلب ملخص الحسابات بطريقة محسنة
                try:
                    from ..services.ledger_service import LedgerService
                    account_summaries = LedgerService.get_all_accounts_summary(
                        date_from, date_to, only_active=True
                    )
                except ImportError:
                    # استخدام التنفيذ المحسن المباشر
                    account_summaries = get_all_accounts_summary_optimized(
                        date_from, date_to
                    )
                
                # حفظ في التخزين المؤقت لمدة 20 دقيقة
                if use_cache:
                    cache.set(cache_key, account_summaries, 1200)
            
            # Pagination للحسابات
            paginator = Paginator(account_summaries, page_size)
            page_number = request.GET.get('page', 1)
            page_obj = paginator.get_page(page_number)
            
            # بناء أزرار الهيدر
            header_buttons = [
                {
                    "onclick": "window.print()",
                    "icon": "fa-print",
                    "text": "طباعة",
                    "class": "btn-outline-secondary",
                },
            ]
            
            # إضافة زر تحديث إذا كانت البيانات مخزنة مؤقتاً
            if cached_summaries:
                header_buttons.append({
                    "url": f"?date_from={date_from or ''}&date_to={date_to or ''}&use_cache=0",
                    "icon": "fa-sync",
                    "text": "تحديث البيانات",
                    "class": "btn-outline-warning",
                })
            
            context = {
                "page_title": "دفتر الأستاذ العام",
                "page_subtitle": "ملخص شامل لجميع حركات الحسابات",
                "page_icon": "fas fa-book",
                "header_buttons": header_buttons,
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
                "page_size": page_size,
                "is_cached": cached_summaries is not None,
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
    تقرير الميزانية العمومية - محسّن واحترافي مع التخزين المؤقت
    يستخدم الطرق المحسنة لحساب الأرصدة والتخزين المؤقت للتقارير الكبيرة
    """
    from django.http import HttpResponse
    from django.core.cache import cache
    from django.db.models import Q
    from decimal import Decimal
    import hashlib
    import json
    
    # معالجة الفلاتر
    date_str = request.GET.get("date")
    group_by_subtype = request.GET.get("group_by_subtype", "1") == "1"
    export_format = request.GET.get("export")
    use_cache = request.GET.get("use_cache", "1") == "1"
    
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
    
    # إنشاء مفتاح التخزين المؤقت للتقرير
    cache_key_data = f"balance_sheet_{balance_date}_{group_by_subtype}_{export_format or 'html'}"
    cache_key = f"report_{hashlib.md5(cache_key_data.encode()).hexdigest()}"
    
    # محاولة الحصول على التقرير من التخزين المؤقت
    cached_data = None
    if use_cache and not export_format:
        cached_data = cache.get(cache_key)
        if cached_data:
            try:
                balance_sheet_data = json.loads(cached_data)
                # تحويل القيم النصية إلى Decimal
                for category in ['assets', 'liabilities', 'equity']:
                    if category in balance_sheet_data:
                        for account in balance_sheet_data[category].get('accounts', []):
                            if 'balance' in account:
                                account['balance'] = Decimal(str(account['balance']))
                        if 'total' in balance_sheet_data[category]:
                            balance_sheet_data[category]['total'] = Decimal(str(balance_sheet_data[category]['total']))
                
                # إضافة رسالة للمستخدم
                messages.info(request, "تم تحميل التقرير من التخزين المؤقت لتحسين الأداء")
            except (json.JSONDecodeError, KeyError):
                cached_data = None
    
    # معالجة التصدير
    if export_format == 'excel':
        try:
            # محاولة استخدام خدمة الميزانية إذا كانت متاحة
            try:
                from ..services.balance_sheet_service import BalanceSheetService
                excel_data = BalanceSheetService.export_to_excel(
                    balance_date,
                    group_by_subtype
                )
            except ImportError:
                # استخدام التنفيذ المحسن المباشر
                excel_data = generate_balance_sheet_excel_optimized(balance_date, group_by_subtype)
            
            response = HttpResponse(
                excel_data,
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            filename = f"balance_sheet_{balance_date.strftime('%Y%m%d')}.xlsx"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            return response
        except Exception as e:
            messages.error(request, f"خطأ في تصدير Excel: {e}")
    
    # إنشاء الميزانية العمومية إذا لم تكن في التخزين المؤقت
    if not cached_data:
        try:
            # محاولة استخدام خدمة الميزانية إذا كانت متاحة
            try:
                from ..services.balance_sheet_service import BalanceSheetService
                balance_sheet_data = BalanceSheetService.generate_balance_sheet(
                    balance_date,
                    group_by_subtype
                )
                financial_ratios = BalanceSheetService.calculate_financial_ratios(balance_sheet_data)
            except ImportError:
                # استخدام التنفيذ المحسن المباشر
                balance_sheet_data = generate_balance_sheet_optimized(balance_date, group_by_subtype)
                financial_ratios = calculate_financial_ratios_optimized(balance_sheet_data)
            
            # حفظ التقرير في التخزين المؤقت لمدة 30 دقيقة
            if use_cache:
                try:
                    # تحويل Decimal إلى string للتخزين
                    cache_data = json.loads(json.dumps(balance_sheet_data, default=str))
                    cache.set(cache_key, json.dumps(cache_data), 1800)  # 30 minutes
                except Exception as cache_error:
                    # تجاهل أخطاء التخزين المؤقت
                    pass
            
        except Exception as e:
            messages.error(request, f"خطأ في إنشاء الميزانية العمومية: {e}")
            balance_sheet_data = {
                'assets': {'accounts': [], 'grouped': {}, 'total': Decimal('0')},
                'liabilities': {'accounts': [], 'grouped': {}, 'total': Decimal('0')},
                'equity': {'accounts': [], 'total': Decimal('0'), 'net_income': Decimal('0')},
                'total_assets': Decimal('0'),
                'total_liabilities': Decimal('0'),
                'total_equity': Decimal('0'),
                'total_liabilities_equity': Decimal('0'),
                'is_balanced': False,
                'error': str(e)
            }
            financial_ratios = {}
    else:
        # حساب النسب المالية للبيانات المخزنة مؤقتاً
        try:
            financial_ratios = calculate_financial_ratios_optimized(balance_sheet_data)
        except:
            financial_ratios = {}
    
    # بناء أزرار الهيدر مع خيارات التخزين المؤقت
    header_buttons = [
        {
            "onclick": "window.print()",
            "icon": "fa-print",
            "text": "طباعة",
            "class": "btn-outline-success",
        }
    ]
    
    # إضافة زر تصدير Excel
    export_params = []
    if date_str:
        export_params.append(f"date={date_str}")
    if group_by_subtype:
        export_params.append("group_by_subtype=1")
    export_params.append("export=excel")
    export_url = "?" + "&".join(export_params)
    
    header_buttons.append({
        "url": export_url,
        "icon": "fa-file-excel",
        "text": "تصدير Excel",
        "class": "btn-success",
    })
    
    # إضافة زر تحديث التخزين المؤقت
    if cached_data:
        refresh_params = []
        if date_str:
            refresh_params.append(f"date={date_str}")
        if group_by_subtype:
            refresh_params.append("group_by_subtype=1")
        refresh_params.append("use_cache=0")
        refresh_url = "?" + "&".join(refresh_params)
        
        header_buttons.append({
            "url": refresh_url,
            "icon": "fa-sync",
            "text": "تحديث البيانات",
            "class": "btn-outline-warning",
        })
    
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
        "header_buttons": header_buttons,
        "balance_sheet_data": balance_sheet_data,
        "financial_ratios": financial_ratios,
        "balance_date": balance_date,
        "group_by_subtype": group_by_subtype,
        "is_cached": cached_data is not None,
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
    تقرير أرصدة أولياء الأمور والموردين
    account_type: 'customers' أو 'suppliers'
    """
    from ..services.parent_supplier_balances_service import ParentSupplierBalancesService
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
                filename = f'parent_balances_{as_of_date}.xlsx'
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
            page_title = "تقرير أرصدة أولياء الأمور"
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
        "new_parents": analytics["advanced_metrics"]["new_parents"],
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

@login_required

@login_required
def data_integrity_check(request):
    """
    التحقق من سلامة البيانات - فحص شامل
    """
    from financial.models import JournalEntry, ChartOfAccounts
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
                from sale.models import Sale

                for customer in Customer.objects.all():
                    if not customer.financial_account:
                        continue

                    total_sales = Sale.objects.filter(
                        customer=customer, status='confirmed'
                    ).aggregate(total=Sum('total'))['total'] or Decimal('0')

                    total_paid = Sale.objects.filter(
                        customer=customer, status='confirmed'
                    ).aggregate(total=Sum('amount_paid'))['total'] or Decimal('0')

                    calculated_balance = total_sales - total_paid
                    account_balance = customer.financial_account.get_balance()

                    if abs(calculated_balance - account_balance) > Decimal('0.01'):
                        customer_issues.append({
                            'customer': customer,
                            'system_balance': account_balance,
                            'calculated_balance': calculated_balance,
                            'difference': abs(account_balance - calculated_balance),
                        })
            except Exception as e:
                logger.error(f"خطأ في فحص أرصدة العملاء: {str(e)}")

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
            
            # ==================== 8. فحص الفواتير المعلقة ====================
            check_name = "الفواتير غير المكتملة"
            results['summary']['total_checks'] += 1

            try:
                from sale.models import Sale
                from django.utils import timezone
                thirty_days_ago = timezone.now() - timedelta(days=30)

                overdue_sales = Sale.objects.filter(
                    status='pending',
                    created_at__lt=thirty_days_ago
                ).count()

                if overdue_sales > 0:
                    results['warnings'].append({
                        'check': check_name,
                        'count': overdue_sales,
                        'message': f"يوجد {overdue_sales} فاتورة معلقة لأكثر من 30 يوم",
                        'severity': 'medium'
                    })
                    results['summary']['warnings'] += 1
                else:
                    results['checks'].append({'name': check_name, 'status': 'passed'})
                    results['summary']['passed'] += 1
            except Exception as e:
                logger.error(f"خطأ في فحص الفواتير: {str(e)}")
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
        "title": "التحقق من سلامة البيانات",
        "subtitle": "فحص شامل للتأكد من توافق وسلامة البيانات",
        "icon": "fas fa-shield-alt",
        "header_buttons": [
            {
                "onclick": "submitIntegrityCheck()",
                "icon": "fa-sync",
                "text": "بدء الفحص",
                "class": "btn-primary",
            },
        ],
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse('core:dashboard'), "icon": "fas fa-home"},
            {"title": "الإدارة المالية", "url": reverse('financial:cash_and_bank_accounts_list'), "icon": "fas fa-money-bill-wave"},
            {"title": "الصيانة", "icon": "fas fa-tools"},
            {"title": "فحص سلامة البيانات", "active": True},
        ],
        "results": results,
        "active_menu": "financial",
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
