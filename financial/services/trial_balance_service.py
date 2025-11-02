# financial/services/trial_balance_service.py
"""
خدمة ميزان المراجعة - Trial Balance Service
توفر جميع العمليات المتعلقة بميزان المراجعة بشكل احترافي وديناميكي
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


class TrialBalanceService:
    """
    خدمة ميزان المراجعة - توفر جميع العمليات المتعلقة بميزان المراجعة
    """

    @staticmethod
    def generate_trial_balance(
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        group_by_type: bool = True,
        only_active: bool = True
    ) -> Dict:
        """
        إنشاء ميزان المراجعة الكامل
        
        Args:
            date_from: من تاريخ (اختياري)
            date_to: إلى تاريخ (اختياري)
            group_by_type: تجميع حسب نوع الحساب؟
            only_active: فقط الحسابات النشطة؟
            
        Returns:
            ميزان المراجعة الكامل
        """
        try:
            # جلب جميع الحسابات
            accounts_query = ChartOfAccounts.objects.filter(
                is_leaf=True  # فقط الحسابات الفرعية
            ).select_related('account_type')
            
            if only_active:
                accounts_query = accounts_query.filter(is_active=True)
            
            accounts_query = accounts_query.order_by(
                'account_type__category',
                'code'
            )
            
            # حساب أرصدة الحسابات
            accounts_data = []
            total_debit = Decimal('0')
            total_credit = Decimal('0')
            
            for account in accounts_query:
                # حساب الرصيد الافتتاحي
                opening_balance = Decimal('0')
                if date_from:
                    opening_balance = LedgerService.get_opening_balance(account, date_from)
                
                # حساب الحركة خلال الفترة
                query = Q(account=account, journal_entry__status='posted')
                
                if date_from:
                    query &= Q(journal_entry__date__gte=date_from)
                if date_to:
                    query &= Q(journal_entry__date__lte=date_to)
                
                totals = JournalEntryLine.objects.filter(query).aggregate(
                    period_debit=Coalesce(Sum('debit'), Decimal('0')),
                    period_credit=Coalesce(Sum('credit'), Decimal('0'))
                )
                
                period_debit = totals['period_debit']
                period_credit = totals['period_credit']
                
                # حساب الرصيد الختامي حسب طبيعة الحساب
                if account.account_type.nature == 'debit':
                    # حسابات مدينة (أصول، مصروفات)
                    closing_balance = opening_balance + period_debit - period_credit
                    debit_balance = closing_balance if closing_balance > 0 else Decimal('0')
                    credit_balance = abs(closing_balance) if closing_balance < 0 else Decimal('0')
                else:
                    # حسابات دائنة (خصوم، إيرادات، حقوق ملكية)
                    closing_balance = opening_balance + period_credit - period_debit
                    credit_balance = closing_balance if closing_balance > 0 else Decimal('0')
                    debit_balance = abs(closing_balance) if closing_balance < 0 else Decimal('0')
                
                # إضافة الحساب إذا كان له رصيد أو حركة
                if (opening_balance != 0 or period_debit > 0 or period_credit > 0 or 
                    debit_balance > 0 or credit_balance > 0):
                    
                    accounts_data.append({
                        'account': account,
                        'opening_balance': opening_balance,
                        'period_debit': period_debit,
                        'period_credit': period_credit,
                        'closing_balance': closing_balance,
                        'debit_balance': debit_balance,
                        'credit_balance': credit_balance,
                        'account_type': account.account_type.category,
                        'account_type_name': account.account_type.name,
                    })
                    
                    total_debit += debit_balance
                    total_credit += credit_balance
            
            # تجميع حسب نوع الحساب إذا طُلب
            grouped_data = {}
            if group_by_type:
                grouped_data = TrialBalanceService._group_by_account_type(accounts_data)
            
            # التحقق من التوازن
            is_balanced = abs(total_debit - total_credit) < Decimal('0.01')
            difference = total_debit - total_credit
            
            return {
                'accounts': accounts_data,
                'grouped': grouped_data,
                'total_debit': total_debit,
                'total_credit': total_credit,
                'is_balanced': is_balanced,
                'difference': difference,
                'date_from': date_from,
                'date_to': date_to,
                'generated_at': timezone.now(),
                'accounts_count': len(accounts_data),
            }
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء ميزان المراجعة: {e}")
            return {
                'accounts': [],
                'grouped': {},
                'total_debit': Decimal('0'),
                'total_credit': Decimal('0'),
                'is_balanced': False,
                'difference': Decimal('0'),
                'error': str(e)
            }

    @staticmethod
    def _group_by_account_type(accounts_data: List[Dict]) -> Dict:
        """
        تجميع الحسابات حسب النوع
        
        Args:
            accounts_data: قائمة بيانات الحسابات
            
        Returns:
            بيانات مجمعة حسب النوع
        """
        grouped = {}
        
        # تعريف ترتيب الأنواع
        type_order = {
            'asset': 1,
            'liability': 2,
            'equity': 3,
            'revenue': 4,
            'expense': 5,
        }
        
        # تعريف أسماء الأنواع بالعربية
        type_names = {
            'asset': 'الأصول',
            'liability': 'الخصوم',
            'equity': 'حقوق الملكية',
            'revenue': 'الإيرادات',
            'expense': 'المصروفات',
        }
        
        for account_data in accounts_data:
            account_type = account_data['account_type']
            
            if account_type not in grouped:
                grouped[account_type] = {
                    'name': type_names.get(account_type, account_type),
                    'order': type_order.get(account_type, 99),
                    'accounts': [],
                    'total_debit': Decimal('0'),
                    'total_credit': Decimal('0'),
                }
            
            grouped[account_type]['accounts'].append(account_data)
            grouped[account_type]['total_debit'] += account_data['debit_balance']
            grouped[account_type]['total_credit'] += account_data['credit_balance']
        
        # ترتيب حسب الترتيب المحدد
        sorted_grouped = dict(sorted(
            grouped.items(),
            key=lambda x: x[1]['order']
        ))
        
        return sorted_grouped

    @staticmethod
    def get_comparative_trial_balance(
        current_date_from: Optional[date] = None,
        current_date_to: Optional[date] = None,
        previous_date_from: Optional[date] = None,
        previous_date_to: Optional[date] = None
    ) -> Dict:
        """
        إنشاء ميزان مراجعة مقارن بين فترتين
        
        Args:
            current_date_from: من تاريخ (الفترة الحالية)
            current_date_to: إلى تاريخ (الفترة الحالية)
            previous_date_from: من تاريخ (الفترة السابقة)
            previous_date_to: إلى تاريخ (الفترة السابقة)
            
        Returns:
            ميزان مراجعة مقارن
        """
        try:
            # إنشاء ميزان المراجعة للفترة الحالية
            current = TrialBalanceService.generate_trial_balance(
                current_date_from,
                current_date_to,
                group_by_type=False
            )
            
            # إنشاء ميزان المراجعة للفترة السابقة
            previous = TrialBalanceService.generate_trial_balance(
                previous_date_from,
                previous_date_to,
                group_by_type=False
            )
            
            # دمج البيانات
            comparison = []
            current_accounts = {acc['account'].id: acc for acc in current['accounts']}
            previous_accounts = {acc['account'].id: acc for acc in previous['accounts']}
            
            # جميع الحسابات (من الفترتين)
            all_account_ids = set(current_accounts.keys()) | set(previous_accounts.keys())
            
            for account_id in all_account_ids:
                current_data = current_accounts.get(account_id, {})
                previous_data = previous_accounts.get(account_id, {})
                
                if current_data:
                    account = current_data['account']
                    current_debit = current_data['debit_balance']
                    current_credit = current_data['credit_balance']
                else:
                    account = previous_data['account']
                    current_debit = Decimal('0')
                    current_credit = Decimal('0')
                
                previous_debit = previous_data.get('debit_balance', Decimal('0'))
                previous_credit = previous_data.get('credit_balance', Decimal('0'))
                
                # حساب التغيير
                debit_change = current_debit - previous_debit
                credit_change = current_credit - previous_credit
                
                # حساب نسبة التغيير
                debit_change_pct = (
                    (debit_change / previous_debit * 100) 
                    if previous_debit > 0 
                    else Decimal('0')
                )
                credit_change_pct = (
                    (credit_change / previous_credit * 100) 
                    if previous_credit > 0 
                    else Decimal('0')
                )
                
                comparison.append({
                    'account': account,
                    'current_debit': current_debit,
                    'current_credit': current_credit,
                    'previous_debit': previous_debit,
                    'previous_credit': previous_credit,
                    'debit_change': debit_change,
                    'credit_change': credit_change,
                    'debit_change_pct': debit_change_pct,
                    'credit_change_pct': credit_change_pct,
                })
            
            return {
                'comparison': comparison,
                'current_total_debit': current['total_debit'],
                'current_total_credit': current['total_credit'],
                'previous_total_debit': previous['total_debit'],
                'previous_total_credit': previous['total_credit'],
                'current_period': {
                    'from': current_date_from,
                    'to': current_date_to
                },
                'previous_period': {
                    'from': previous_date_from,
                    'to': previous_date_to
                },
            }
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء ميزان المراجعة المقارن: {e}")
            return {
                'comparison': [],
                'error': str(e)
            }

    @staticmethod
    def export_to_excel(
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        group_by_type: bool = True
    ) -> bytes:
        """
        تصدير ميزان المراجعة إلى Excel
        
        Args:
            date_from: من تاريخ
            date_to: إلى تاريخ
            group_by_type: تجميع حسب النوع؟
            
        Returns:
            ملف Excel كـ bytes
        """
        try:
            import openpyxl
            from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
            from io import BytesIO
            
            # إنشاء ميزان المراجعة
            trial_balance = TrialBalanceService.generate_trial_balance(
                date_from,
                date_to,
                group_by_type
            )
            
            # إنشاء workbook
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "ميزان المراجعة"
            
            # تنسيق
            header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
            header_font = Font(bold=True, color="FFFFFF", size=12)
            subtotal_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
            total_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
            total_font = Font(bold=True, color="FFFFFF", size=12)
            
            # العنوان
            ws['A1'] = "ميزان المراجعة"
            ws['A1'].font = Font(bold=True, size=16)
            ws.merge_cells('A1:F1')
            
            # معلومات الفترة
            row = 2
            if date_from or date_to:
                period_text = f"الفترة: {date_from or 'البداية'} - {date_to or 'النهاية'}"
                ws[f'A{row}'] = period_text
                ws.merge_cells(f'A{row}:F{row}')
                row += 1
            
            # تاريخ الإنشاء
            ws[f'A{row}'] = f"تاريخ الإنشاء: {trial_balance['generated_at'].strftime('%Y-%m-%d %H:%M')}"
            ws.merge_cells(f'A{row}:F{row}')
            row += 2
            
            # العناوين
            headers = ['الكود', 'الحساب', 'النوع', 'مدين', 'دائن', 'الرصيد']
            for col, header in enumerate(headers, 1):
                cell = ws.cell(row=row, column=col, value=header)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal='center')
            
            row += 1
            
            # البيانات
            if group_by_type and trial_balance['grouped']:
                # عرض مجمع حسب النوع
                for type_key, type_data in trial_balance['grouped'].items():
                    # عنوان النوع
                    ws.cell(row=row, column=1, value=type_data['name']).font = Font(bold=True)
                    ws.merge_cells(f'A{row}:C{row}')
                    row += 1
                    
                    # حسابات النوع
                    for account_data in type_data['accounts']:
                        ws.cell(row=row, column=1, value=account_data['account'].code)
                        ws.cell(row=row, column=2, value=account_data['account'].name)
                        ws.cell(row=row, column=3, value=account_data['account_type_name'])
                        ws.cell(row=row, column=4, value=float(account_data['debit_balance']))
                        ws.cell(row=row, column=5, value=float(account_data['credit_balance']))
                        
                        # الرصيد
                        if account_data['debit_balance'] > 0:
                            ws.cell(row=row, column=6, value=f"{float(account_data['debit_balance'])} مدين")
                        elif account_data['credit_balance'] > 0:
                            ws.cell(row=row, column=6, value=f"{float(account_data['credit_balance'])} دائن")
                        else:
                            ws.cell(row=row, column=6, value="-")
                        
                        row += 1
                    
                    # إجمالي النوع
                    ws.cell(row=row, column=1, value=f"إجمالي {type_data['name']}").font = Font(bold=True)
                    ws.merge_cells(f'A{row}:C{row}')
                    ws.cell(row=row, column=4, value=float(type_data['total_debit'])).font = Font(bold=True)
                    ws.cell(row=row, column=5, value=float(type_data['total_credit'])).font = Font(bold=True)
                    for col in range(1, 7):
                        ws.cell(row=row, column=col).fill = subtotal_fill
                    row += 1
                    row += 1  # سطر فارغ
            else:
                # عرض عادي بدون تجميع
                for account_data in trial_balance['accounts']:
                    ws.cell(row=row, column=1, value=account_data['account'].code)
                    ws.cell(row=row, column=2, value=account_data['account'].name)
                    ws.cell(row=row, column=3, value=account_data['account_type_name'])
                    ws.cell(row=row, column=4, value=float(account_data['debit_balance']))
                    ws.cell(row=row, column=5, value=float(account_data['credit_balance']))
                    
                    # الرصيد
                    if account_data['debit_balance'] > 0:
                        ws.cell(row=row, column=6, value=f"{float(account_data['debit_balance'])} مدين")
                    elif account_data['credit_balance'] > 0:
                        ws.cell(row=row, column=6, value=f"{float(account_data['credit_balance'])} دائن")
                    else:
                        ws.cell(row=row, column=6, value="-")
                    
                    row += 1
            
            # الإجمالي النهائي
            ws.cell(row=row, column=1, value="الإجمالي").font = total_font
            ws.merge_cells(f'A{row}:C{row}')
            ws.cell(row=row, column=4, value=float(trial_balance['total_debit'])).font = total_font
            ws.cell(row=row, column=5, value=float(trial_balance['total_credit'])).font = total_font
            
            # حالة التوازن
            if trial_balance['is_balanced']:
                ws.cell(row=row, column=6, value="متوازن ✓").font = total_font
            else:
                ws.cell(row=row, column=6, value=f"غير متوازن (فرق: {float(trial_balance['difference'])})").font = total_font
            
            for col in range(1, 7):
                ws.cell(row=row, column=col).fill = total_fill
            
            # ضبط عرض الأعمدة
            from openpyxl.utils import get_column_letter
            for idx in range(1, 7):
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
