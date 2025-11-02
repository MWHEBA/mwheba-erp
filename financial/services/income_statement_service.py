# financial/services/income_statement_service.py
"""خدمة قائمة الدخل - Income Statement Service"""

from django.db.models import Sum, Q
from django.db.models.functions import Coalesce
from django.utils import timezone
from decimal import Decimal
from datetime import date
from typing import Dict, Optional
import logging

from ..models import ChartOfAccounts, JournalEntryLine

logger = logging.getLogger(__name__)


class IncomeStatementService:
    """خدمة قائمة الدخل"""

    @staticmethod
    def generate_income_statement(
        date_from: Optional[date] = None,
        date_to: Optional[date] = None
    ) -> Dict:
        """إنشاء قائمة الدخل"""
        try:
            if date_to is None:
                date_to = timezone.now().date()
            if date_from is None:
                date_from = date(date_to.year, date_to.month, 1)
            
            # الإيرادات
            revenue_accounts = ChartOfAccounts.objects.filter(
                account_type__category='revenue',
                is_leaf=True,
                is_active=True
            ).select_related('account_type').order_by('code')
            
            revenues = []
            total_revenue = Decimal('0')
            
            for account in revenue_accounts:
                query = Q(
                    account=account,
                    journal_entry__status='posted',
                    journal_entry__date__gte=date_from,
                    journal_entry__date__lte=date_to
                )
                
                totals = JournalEntryLine.objects.filter(query).aggregate(
                    total_debit=Coalesce(Sum('debit'), Decimal('0')),
                    total_credit=Coalesce(Sum('credit'), Decimal('0'))
                )
                
                balance = totals['total_credit'] - totals['total_debit']
                
                if balance != 0:
                    revenues.append({
                        'account': account,
                        'amount': balance
                    })
                    total_revenue += balance
            
            # المصروفات
            expense_accounts = ChartOfAccounts.objects.filter(
                account_type__category='expense',
                is_leaf=True,
                is_active=True
            ).select_related('account_type').order_by('code')
            
            expenses = []
            total_expense = Decimal('0')
            
            for account in expense_accounts:
                query = Q(
                    account=account,
                    journal_entry__status='posted',
                    journal_entry__date__gte=date_from,
                    journal_entry__date__lte=date_to
                )
                
                totals = JournalEntryLine.objects.filter(query).aggregate(
                    total_debit=Coalesce(Sum('debit'), Decimal('0')),
                    total_credit=Coalesce(Sum('credit'), Decimal('0'))
                )
                
                balance = totals['total_debit'] - totals['total_credit']
                
                if balance != 0:
                    expenses.append({
                        'account': account,
                        'amount': balance
                    })
                    total_expense += balance
            
            # صافي الربح/الخسارة
            net_income = total_revenue - total_expense
            
            return {
                'date_from': date_from,
                'date_to': date_to,
                'generated_at': timezone.now(),
                'revenues': revenues,
                'expenses': expenses,
                'total_revenue': total_revenue,
                'total_expense': total_expense,
                'net_income': net_income,
                'is_profit': net_income > 0,
            }
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء قائمة الدخل: {e}")
            return {
                'revenues': [],
                'expenses': [],
                'total_revenue': Decimal('0'),
                'total_expense': Decimal('0'),
                'net_income': Decimal('0'),
                'error': str(e)
            }

    @staticmethod
    def export_to_excel(date_from: Optional[date] = None, date_to: Optional[date] = None) -> bytes:
        """تصدير قائمة الدخل إلى Excel"""
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill
            from io import BytesIO
            
            income_statement = IncomeStatementService.generate_income_statement(date_from, date_to)
            
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "قائمة الدخل"
            
            # تنسيق
            header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
            header_font = Font(bold=True, color="FFFFFF", size=12)
            total_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
            total_font = Font(bold=True, color="FFFFFF", size=12)
            
            # العنوان
            ws['A1'] = "قائمة الدخل"
            ws['A1'].font = Font(bold=True, size=16)
            ws.merge_cells('A1:C1')
            
            ws['A2'] = f"من {income_statement['date_from']} إلى {income_statement['date_to']}"
            ws.merge_cells('A2:C2')
            
            row = 4
            
            # الإيرادات
            ws[f'A{row}'] = "الإيرادات"
            ws[f'A{row}'].font = header_font
            ws[f'A{row}'].fill = header_fill
            ws.merge_cells(f'A{row}:C{row}')
            row += 1
            
            for item in income_statement['revenues']:
                ws[f'A{row}'] = item['account'].code
                ws[f'B{row}'] = item['account'].name
                ws[f'C{row}'] = float(item['amount'])
                row += 1
            
            ws[f'B{row}'] = "إجمالي الإيرادات"
            ws[f'C{row}'] = float(income_statement['total_revenue'])
            for col in ['A', 'B', 'C']:
                ws[f'{col}{row}'].fill = total_fill
                ws[f'{col}{row}'].font = total_font
            row += 2
            
            # المصروفات
            ws[f'A{row}'] = "المصروفات"
            ws[f'A{row}'].font = header_font
            ws[f'A{row}'].fill = header_fill
            ws.merge_cells(f'A{row}:C{row}')
            row += 1
            
            for item in income_statement['expenses']:
                ws[f'A{row}'] = item['account'].code
                ws[f'B{row}'] = item['account'].name
                ws[f'C{row}'] = float(item['amount'])
                row += 1
            
            ws[f'B{row}'] = "إجمالي المصروفات"
            ws[f'C{row}'] = float(income_statement['total_expense'])
            for col in ['A', 'B', 'C']:
                ws[f'{col}{row}'].fill = total_fill
                ws[f'{col}{row}'].font = total_font
            row += 2
            
            # صافي الربح/الخسارة
            ws[f'B{row}'] = "صافي الربح/الخسارة"
            ws[f'C{row}'] = float(income_statement['net_income'])
            ws[f'B{row}'].font = Font(bold=True, size=14)
            ws[f'C{row}'].font = Font(bold=True, size=14)
            
            # ضبط عرض الأعمدة
            from openpyxl.utils import get_column_letter
            for idx in range(1, 4):
                ws.column_dimensions[get_column_letter(idx)].width = 30
            
            output = BytesIO()
            wb.save(output)
            output.seek(0)
            
            return output.getvalue()
            
        except Exception as e:
            logger.error(f"خطأ في تصدير Excel: {e}")
            raise
