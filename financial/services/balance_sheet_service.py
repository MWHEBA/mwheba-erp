# financial/services/balance_sheet_service.py
"""
خدمة الميزانية العمومية - Balance Sheet Service
توفر جميع العمليات المتعلقة بالميزانية العمومية بشكل احترافي وديناميكي
"""

from django.db.models import Sum, Q
from django.db.models.functions import Coalesce
from django.utils import timezone
from decimal import Decimal
from datetime import date
from typing import Dict, List, Optional
import logging

from ..models import (
    ChartOfAccounts,
    JournalEntryLine,
    AccountType,
)
from .ledger_service import LedgerService

logger = logging.getLogger(__name__)


class BalanceSheetService:
    """
    خدمة الميزانية العمومية - توفر جميع العمليات المتعلقة بالميزانية العمومية
    """

    @staticmethod
    def get_account_balance_at_date(
        account: ChartOfAccounts,
        as_of_date: date
    ) -> Decimal:
        """
        حساب رصيد الحساب في تاريخ معين
        
        Args:
            account: الحساب
            as_of_date: التاريخ
            
        Returns:
            الرصيد
        """
        try:
            # جلب جميع القيود المرحلة حتى التاريخ المحدد
            query = Q(
                account=account,
                journal_entry__status='posted',
                journal_entry__date__lte=as_of_date
            )
            
            totals = JournalEntryLine.objects.filter(query).aggregate(
                total_debit=Coalesce(Sum('debit'), Decimal('0')),
                total_credit=Coalesce(Sum('credit'), Decimal('0'))
            )
            
            total_debit = totals['total_debit']
            total_credit = totals['total_credit']
            
            # حساب الرصيد حسب طبيعة الحساب
            if account.account_type.nature == 'debit':
                balance = total_debit - total_credit
            else:
                balance = total_credit - total_debit
            
            return balance
            
        except Exception as e:
            logger.error(f"خطأ في حساب رصيد الحساب {account.code}: {e}")
            return Decimal('0')

    @staticmethod
    def get_assets(
        as_of_date: date,
        group_by_subtype: bool = True
    ) -> Dict:
        """
        حساب الأصول
        
        Args:
            as_of_date: التاريخ
            group_by_subtype: تجميع حسب النوع الفرعي؟
            
        Returns:
            بيانات الأصول
        """
        try:
            # جلب حسابات الأصول
            asset_accounts = ChartOfAccounts.objects.filter(
                account_type__category='asset',
                is_leaf=True,
                is_active=True
            ).select_related('account_type').order_by('code')
            
            assets_data = []
            total = Decimal('0')
            
            # تجميع حسب النوع الفرعي
            grouped = {}
            
            for account in asset_accounts:
                balance = BalanceSheetService.get_account_balance_at_date(
                    account,
                    as_of_date
                )
                
                # فقط الحسابات التي لها رصيد
                if balance != 0:
                    account_data = {
                        'account': account,
                        'balance': balance,
                        'type': account.account_type.name,
                    }
                    
                    assets_data.append(account_data)
                    total += balance
                    
                    # تجميع
                    if group_by_subtype:
                        type_name = account.account_type.name
                        if type_name not in grouped:
                            grouped[type_name] = {
                                'name': type_name,
                                'accounts': [],
                                'total': Decimal('0')
                            }
                        grouped[type_name]['accounts'].append(account_data)
                        grouped[type_name]['total'] += balance
            
            return {
                'accounts': assets_data,
                'grouped': grouped,
                'total': total,
            }
            
        except Exception as e:
            logger.error(f"خطأ في حساب الأصول: {e}")
            return {
                'accounts': [],
                'grouped': {},
                'total': Decimal('0'),
                'error': str(e)
            }

    @staticmethod
    def get_liabilities(
        as_of_date: date,
        group_by_subtype: bool = True
    ) -> Dict:
        """
        حساب الخصوم
        
        Args:
            as_of_date: التاريخ
            group_by_subtype: تجميع حسب النوع الفرعي؟
            
        Returns:
            بيانات الخصوم
        """
        try:
            # جلب حسابات الخصوم
            liability_accounts = ChartOfAccounts.objects.filter(
                account_type__category='liability',
                is_leaf=True,
                is_active=True
            ).select_related('account_type').order_by('code')
            
            liabilities_data = []
            total = Decimal('0')
            
            # تجميع حسب النوع الفرعي
            grouped = {}
            
            for account in liability_accounts:
                balance = BalanceSheetService.get_account_balance_at_date(
                    account,
                    as_of_date
                )
                
                # فقط الحسابات التي لها رصيد
                if balance != 0:
                    account_data = {
                        'account': account,
                        'balance': balance,
                        'type': account.account_type.name,
                    }
                    
                    liabilities_data.append(account_data)
                    total += balance
                    
                    # تجميع
                    if group_by_subtype:
                        type_name = account.account_type.name
                        if type_name not in grouped:
                            grouped[type_name] = {
                                'name': type_name,
                                'accounts': [],
                                'total': Decimal('0')
                            }
                        grouped[type_name]['accounts'].append(account_data)
                        grouped[type_name]['total'] += balance
            
            return {
                'accounts': liabilities_data,
                'grouped': grouped,
                'total': total,
            }
            
        except Exception as e:
            logger.error(f"خطأ في حساب الخصوم: {e}")
            return {
                'accounts': [],
                'grouped': {},
                'total': Decimal('0'),
                'error': str(e)
            }

    @staticmethod
    def get_equity(
        as_of_date: date,
        include_net_income: bool = True
    ) -> Dict:
        """
        حساب حقوق الملكية
        
        Args:
            as_of_date: التاريخ
            include_net_income: هل نشمل صافي الربح/الخسارة؟
            
        Returns:
            بيانات حقوق الملكية
        """
        try:
            # جلب حسابات حقوق الملكية
            equity_accounts = ChartOfAccounts.objects.filter(
                account_type__category='equity',
                is_leaf=True,
                is_active=True
            ).select_related('account_type').order_by('code')
            
            equity_data = []
            total = Decimal('0')
            
            for account in equity_accounts:
                balance = BalanceSheetService.get_account_balance_at_date(
                    account,
                    as_of_date
                )
                
                # فقط الحسابات التي لها رصيد
                if balance != 0:
                    account_data = {
                        'account': account,
                        'balance': balance,
                        'type': account.account_type.name,
                    }
                    
                    equity_data.append(account_data)
                    total += balance
            
            # حساب صافي الربح/الخسارة
            net_income = Decimal('0')
            if include_net_income:
                net_income = BalanceSheetService.calculate_net_income(as_of_date)
                
                if net_income != 0:
                    # إضافة صافي الربح/الخسارة كبند منفصل
                    equity_data.append({
                        'account': type('obj', (object,), {
                            'name': 'صافي الربح/الخسارة',
                            'code': 'NET_INCOME'
                        })(),
                        'balance': net_income,
                        'type': 'صافي الربح/الخسارة',
                        'is_net_income': True
                    })
                    total += net_income
            
            return {
                'accounts': equity_data,
                'total': total,
                'net_income': net_income,
            }
            
        except Exception as e:
            logger.error(f"خطأ في حساب حقوق الملكية: {e}")
            return {
                'accounts': [],
                'total': Decimal('0'),
                'net_income': Decimal('0'),
                'error': str(e)
            }

    @staticmethod
    def calculate_net_income(as_of_date: date) -> Decimal:
        """
        حساب صافي الربح/الخسارة حتى تاريخ معين
        
        Args:
            as_of_date: التاريخ
            
        Returns:
            صافي الربح/الخسارة
        """
        try:
            # حساب إجمالي الإيرادات
            revenue_accounts = ChartOfAccounts.objects.filter(
                account_type__category='revenue',
                is_leaf=True,
                is_active=True
            )
            
            total_revenue = Decimal('0')
            for account in revenue_accounts:
                balance = BalanceSheetService.get_account_balance_at_date(
                    account,
                    as_of_date
                )
                total_revenue += balance
            
            # حساب إجمالي المصروفات
            expense_accounts = ChartOfAccounts.objects.filter(
                account_type__category='expense',
                is_leaf=True,
                is_active=True
            )
            
            total_expense = Decimal('0')
            for account in expense_accounts:
                balance = BalanceSheetService.get_account_balance_at_date(
                    account,
                    as_of_date
                )
                total_expense += balance
            
            # صافي الربح = الإيرادات - المصروفات
            net_income = total_revenue - total_expense
            
            return net_income
            
        except Exception as e:
            logger.error(f"خطأ في حساب صافي الربح: {e}")
            return Decimal('0')

    @staticmethod
    def generate_balance_sheet(
        as_of_date: Optional[date] = None,
        group_by_subtype: bool = True,
        include_net_income: bool = True
    ) -> Dict:
        """
        إنشاء الميزانية العمومية الكاملة
        
        Args:
            as_of_date: التاريخ (افتراضي: اليوم)
            group_by_subtype: تجميع حسب النوع الفرعي؟
            include_net_income: هل نشمل صافي الربح؟
            
        Returns:
            الميزانية العمومية الكاملة
        """
        try:
            if as_of_date is None:
                as_of_date = timezone.now().date()
            
            # حساب الأصول
            assets = BalanceSheetService.get_assets(as_of_date, group_by_subtype)
            
            # حساب الخصوم
            liabilities = BalanceSheetService.get_liabilities(as_of_date, group_by_subtype)
            
            # حساب حقوق الملكية
            equity = BalanceSheetService.get_equity(as_of_date, include_net_income)
            
            # الإجماليات
            total_assets = assets['total']
            total_liabilities = liabilities['total']
            total_equity = equity['total']
            total_liabilities_equity = total_liabilities + total_equity
            
            # التحقق من التوازن
            difference = total_assets - total_liabilities_equity
            is_balanced = abs(difference) < Decimal('0.01')
            
            return {
                'as_of_date': as_of_date,
                'generated_at': timezone.now(),
                'assets': assets,
                'liabilities': liabilities,
                'equity': equity,
                'total_assets': total_assets,
                'total_liabilities': total_liabilities,
                'total_equity': total_equity,
                'total_liabilities_equity': total_liabilities_equity,
                'difference': difference,
                'is_balanced': is_balanced,
            }
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء الميزانية العمومية: {e}")
            return {
                'as_of_date': as_of_date,
                'generated_at': timezone.now(),
                'assets': {'accounts': [], 'grouped': {}, 'total': Decimal('0')},
                'liabilities': {'accounts': [], 'grouped': {}, 'total': Decimal('0')},
                'equity': {'accounts': [], 'total': Decimal('0'), 'net_income': Decimal('0')},
                'total_assets': Decimal('0'),
                'total_liabilities': Decimal('0'),
                'total_equity': Decimal('0'),
                'total_liabilities_equity': Decimal('0'),
                'difference': Decimal('0'),
                'is_balanced': False,
                'error': str(e)
            }

    @staticmethod
    def calculate_financial_ratios(balance_sheet_data: Dict) -> Dict:
        """
        حساب النسب المالية من الميزانية العمومية
        
        Args:
            balance_sheet_data: بيانات الميزانية العمومية
            
        Returns:
            النسب المالية
        """
        try:
            total_assets = balance_sheet_data['total_assets']
            total_liabilities = balance_sheet_data['total_liabilities']
            total_equity = balance_sheet_data['total_equity']
            
            ratios = {}
            
            # نسبة المديونية (Debt Ratio)
            if total_assets > 0:
                ratios['debt_ratio'] = (total_liabilities / total_assets) * 100
            else:
                ratios['debt_ratio'] = Decimal('0')
            
            # نسبة حقوق الملكية (Equity Ratio)
            if total_assets > 0:
                ratios['equity_ratio'] = (total_equity / total_assets) * 100
            else:
                ratios['equity_ratio'] = Decimal('0')
            
            # نسبة الدين إلى حقوق الملكية (Debt to Equity Ratio)
            if total_equity > 0:
                ratios['debt_to_equity'] = (total_liabilities / total_equity) * 100
            else:
                ratios['debt_to_equity'] = Decimal('0')
            
            # العائد على الأصول (ROA) - يحتاج صافي الربح
            net_income = balance_sheet_data['equity'].get('net_income', Decimal('0'))
            if total_assets > 0:
                ratios['roa'] = (net_income / total_assets) * 100
            else:
                ratios['roa'] = Decimal('0')
            
            # العائد على حقوق الملكية (ROE)
            if total_equity > 0:
                ratios['roe'] = (net_income / total_equity) * 100
            else:
                ratios['roe'] = Decimal('0')
            
            return ratios
            
        except Exception as e:
            logger.error(f"خطأ في حساب النسب المالية: {e}")
            return {}

    @staticmethod
    def export_to_excel(
        as_of_date: Optional[date] = None,
        group_by_subtype: bool = True
    ) -> bytes:
        """
        تصدير الميزانية العمومية إلى Excel
        
        Args:
            as_of_date: التاريخ
            group_by_subtype: تجميع حسب النوع؟
            
        Returns:
            ملف Excel كـ bytes
        """
        try:
            import openpyxl
            from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
            from io import BytesIO
            
            # إنشاء الميزانية العمومية
            balance_sheet = BalanceSheetService.generate_balance_sheet(
                as_of_date,
                group_by_subtype
            )
            
            # إنشاء workbook
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "الميزانية العمومية"
            
            # تنسيق
            header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
            header_font = Font(bold=True, color="FFFFFF", size=12)
            title_font = Font(bold=True, size=16)
            subtotal_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
            total_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
            total_font = Font(bold=True, color="FFFFFF", size=12)
            
            # العنوان
            ws['A1'] = "الميزانية العمومية"
            ws['A1'].font = title_font
            ws.merge_cells('A1:C1')
            
            # التاريخ
            ws['A2'] = f"كما في: {balance_sheet['as_of_date'].strftime('%Y-%m-%d')}"
            ws.merge_cells('A2:C2')
            
            row = 4
            
            # الأصول
            ws[f'A{row}'] = "الأصول"
            ws[f'A{row}'].font = header_font
            ws[f'A{row}'].fill = header_fill
            ws.merge_cells(f'A{row}:C{row}')
            row += 1
            
            if group_by_subtype and balance_sheet['assets']['grouped']:
                for type_name, type_data in balance_sheet['assets']['grouped'].items():
                    # عنوان المجموعة
                    ws[f'A{row}'] = type_name
                    ws[f'A{row}'].font = Font(bold=True)
                    row += 1
                    
                    # الحسابات
                    for account_data in type_data['accounts']:
                        ws[f'A{row}'] = account_data['account'].code
                        ws[f'B{row}'] = account_data['account'].name
                        ws[f'C{row}'] = float(account_data['balance'])
                        row += 1
                    
                    # إجمالي المجموعة
                    ws[f'B{row}'] = f"إجمالي {type_name}"
                    ws[f'C{row}'] = float(type_data['total'])
                    ws[f'B{row}'].font = Font(bold=True)
                    ws[f'C{row}'].font = Font(bold=True)
                    for col in ['A', 'B', 'C']:
                        ws[f'{col}{row}'].fill = subtotal_fill
                    row += 1
            else:
                for account_data in balance_sheet['assets']['accounts']:
                    ws[f'A{row}'] = account_data['account'].code
                    ws[f'B{row}'] = account_data['account'].name
                    ws[f'C{row}'] = float(account_data['balance'])
                    row += 1
            
            # إجمالي الأصول
            ws[f'B{row}'] = "إجمالي الأصول"
            ws[f'C{row}'] = float(balance_sheet['total_assets'])
            for col in ['A', 'B', 'C']:
                ws[f'{col}{row}'].fill = total_fill
                ws[f'{col}{row}'].font = total_font
            row += 2
            
            # الخصوم
            ws[f'A{row}'] = "الخصوم"
            ws[f'A{row}'].font = header_font
            ws[f'A{row}'].fill = header_fill
            ws.merge_cells(f'A{row}:C{row}')
            row += 1
            
            for account_data in balance_sheet['liabilities']['accounts']:
                ws[f'A{row}'] = account_data['account'].code
                ws[f'B{row}'] = account_data['account'].name
                ws[f'C{row}'] = float(account_data['balance'])
                row += 1
            
            # إجمالي الخصوم
            ws[f'B{row}'] = "إجمالي الخصوم"
            ws[f'C{row}'] = float(balance_sheet['total_liabilities'])
            for col in ['A', 'B', 'C']:
                ws[f'{col}{row}'].fill = total_fill
                ws[f'{col}{row}'].font = total_font
            row += 2
            
            # حقوق الملكية
            ws[f'A{row}'] = "حقوق الملكية"
            ws[f'A{row}'].font = header_font
            ws[f'A{row}'].fill = header_fill
            ws.merge_cells(f'A{row}:C{row}')
            row += 1
            
            for account_data in balance_sheet['equity']['accounts']:
                ws[f'A{row}'] = account_data['account'].code if hasattr(account_data['account'], 'code') else '-'
                ws[f'B{row}'] = account_data['account'].name
                ws[f'C{row}'] = float(account_data['balance'])
                row += 1
            
            # إجمالي حقوق الملكية
            ws[f'B{row}'] = "إجمالي حقوق الملكية"
            ws[f'C{row}'] = float(balance_sheet['total_equity'])
            for col in ['A', 'B', 'C']:
                ws[f'{col}{row}'].fill = total_fill
                ws[f'{col}{row}'].font = total_font
            row += 2
            
            # حالة التوازن
            ws[f'B{row}'] = "حالة التوازن"
            if balance_sheet['is_balanced']:
                ws[f'C{row}'] = "متوازنة ✓"
            else:
                ws[f'C{row}'] = f"غير متوازنة (فرق: {float(balance_sheet['difference'])})"
            ws[f'B{row}'].font = Font(bold=True)
            ws[f'C{row}'].font = Font(bold=True)
            
            # ضبط عرض الأعمدة
            from openpyxl.utils import get_column_letter
            for idx in range(1, 4):
                max_length = 0
                column_letter = get_column_letter(idx)
                for cell in ws[column_letter]:
                    try:
                        if cell.value and len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                ws.column_dimensions[column_letter].width = adjusted_width
            
            # حفظ في BytesIO
            output = BytesIO()
            wb.save(output)
            output.seek(0)
            
            return output.getvalue()
            
        except Exception as e:
            logger.error(f"خطأ في تصدير Excel: {e}")
            raise
