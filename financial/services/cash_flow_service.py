# financial/services/cash_flow_service.py
"""
خدمة تقرير التدفقات النقدية
تحليل التدفقات النقدية من الأنشطة التشغيلية والاستثمارية والتمويلية
"""

from django.db.models import Sum, Q, F
from decimal import Decimal
from datetime import date, datetime
from typing import Dict, List, Optional, Any
from ..models import (
    JournalEntry,
    JournalEntryLine,
    ChartOfAccounts,
    AccountType,
)


class CashFlowService:
    """خدمة تقرير التدفقات النقدية"""
    
    def __init__(self, date_from: Optional[date] = None, date_to: Optional[date] = None):
        """
        تهيئة الخدمة
        
        Args:
            date_from: تاريخ البداية (اختياري)
            date_to: تاريخ النهاية (اختياري)
        """
        self.date_from = date_from
        self.date_to = date_to
    
    def generate_cash_flow_statement(self) -> Dict[str, Any]:
        """
        إنشاء قائمة التدفقات النقدية
        
        Returns:
            قاموس يحتوي على:
            - operating_activities: التدفقات من الأنشطة التشغيلية
            - investing_activities: التدفقات من الأنشطة الاستثمارية
            - financing_activities: التدفقات من الأنشطة التمويلية
            - net_cash_flow: صافي التدفق النقدي
            - opening_cash: الرصيد النقدي الافتتاحي
            - closing_cash: الرصيد النقدي الختامي
        """
        # جلب الحسابات النقدية
        cash_accounts = self._get_cash_accounts()
        
        # حساب الرصيد الافتتاحي
        opening_cash = self._calculate_opening_cash(cash_accounts)
        
        # التدفقات من الأنشطة التشغيلية
        operating_activities = self._calculate_operating_activities()
        
        # التدفقات من الأنشطة الاستثمارية
        investing_activities = self._calculate_investing_activities()
        
        # التدفقات من الأنشطة التمويلية
        financing_activities = self._calculate_financing_activities()
        
        # حساب صافي التدفق النقدي
        net_operating = operating_activities.get('net_cash_from_operating', Decimal('0'))
        net_investing = investing_activities.get('net_cash_from_investing', Decimal('0'))
        net_financing = financing_activities.get('net_cash_from_financing', Decimal('0'))
        
        net_cash_flow = net_operating + net_investing + net_financing
        
        # الرصيد النقدي الختامي
        closing_cash = opening_cash + net_cash_flow
        
        return {
            'operating_activities': operating_activities,
            'investing_activities': investing_activities,
            'financing_activities': financing_activities,
            'net_cash_flow': net_cash_flow,
            'opening_cash': opening_cash,
            'closing_cash': closing_cash,
            'date_from': self.date_from,
            'date_to': self.date_to,
        }
    
    def _get_cash_accounts(self) -> List[ChartOfAccounts]:
        """جلب الحسابات النقدية (الخزينة والبنوك)"""
        return ChartOfAccounts.objects.filter(
            Q(name__icontains='خزينة') | Q(name__icontains='بنك') | Q(name__icontains='نقدية'),
            is_active=True,
            is_leaf=True
        )
    
    def _calculate_opening_cash(self, cash_accounts: List[ChartOfAccounts]) -> Decimal:
        """حساب الرصيد النقدي الافتتاحي"""
        if not self.date_from or not cash_accounts:
            return Decimal('0')
        
        opening_balance = Decimal('0')
        
        for account in cash_accounts:
            # جلب القيود قبل تاريخ البداية
            lines = JournalEntryLine.objects.filter(
                account=account,
                journal_entry__status='posted',
                journal_entry__date__lt=self.date_from
            ).aggregate(
                total_debit=Sum('debit'),
                total_credit=Sum('credit')
            )
            
            debit = lines['total_debit'] or Decimal('0')
            credit = lines['total_credit'] or Decimal('0')
            
            # الحسابات النقدية عادة مدينة
            opening_balance += (debit - credit)
        
        return opening_balance
    
    def _calculate_operating_activities(self) -> Dict[str, Any]:
        """حساب التدفقات من الأنشطة التشغيلية"""
        # بناء الفلتر
        filters = {'journal_entry__status': 'posted'}
        if self.date_from:
            filters['journal_entry__date__gte'] = self.date_from
        if self.date_to:
            filters['journal_entry__date__lte'] = self.date_to
        
        # الإيرادات النقدية
        revenue_accounts = ChartOfAccounts.objects.filter(
            account_type__category='revenue',
            is_active=True,
            is_leaf=True
        )
        
        cash_from_revenue = Decimal('0')
        for account in revenue_accounts:
            lines = JournalEntryLine.objects.filter(
                account=account,
                **filters
            ).aggregate(
                total_credit=Sum('credit'),
                total_debit=Sum('debit')
            )
            credit = lines['total_credit'] or Decimal('0')
            debit = lines['total_debit'] or Decimal('0')
            cash_from_revenue += (credit - debit)
        
        # المصروفات النقدية
        expense_accounts = ChartOfAccounts.objects.filter(
            account_type__category='expense',
            is_active=True,
            is_leaf=True
        )
        
        cash_for_expenses = Decimal('0')
        for account in expense_accounts:
            lines = JournalEntryLine.objects.filter(
                account=account,
                **filters
            ).aggregate(
                total_debit=Sum('debit'),
                total_credit=Sum('credit')
            )
            debit = lines['total_debit'] or Decimal('0')
            credit = lines['total_credit'] or Decimal('0')
            cash_for_expenses += (debit - credit)
        
        # صافي التدفق من الأنشطة التشغيلية
        net_cash_from_operating = cash_from_revenue - cash_for_expenses
        
        return {
            'cash_from_revenue': cash_from_revenue,
            'cash_for_expenses': cash_for_expenses,
            'net_cash_from_operating': net_cash_from_operating,
        }
    
    def _calculate_investing_activities(self) -> Dict[str, Any]:
        """حساب التدفقات من الأنشطة الاستثمارية"""
        # بناء الفلتر
        filters = {'journal_entry__status': 'posted'}
        if self.date_from:
            filters['journal_entry__date__gte'] = self.date_from
        if self.date_to:
            filters['journal_entry__date__lte'] = self.date_to
        
        # الأصول الثابتة
        fixed_asset_accounts = ChartOfAccounts.objects.filter(
            Q(name__icontains='أصول ثابتة') | Q(name__icontains='معدات') | Q(name__icontains='مباني'),
            is_active=True,
            is_leaf=True
        )
        
        cash_for_investments = Decimal('0')
        cash_from_asset_sales = Decimal('0')
        
        for account in fixed_asset_accounts:
            lines = JournalEntryLine.objects.filter(
                account=account,
                **filters
            ).aggregate(
                total_debit=Sum('debit'),
                total_credit=Sum('credit')
            )
            debit = lines['total_debit'] or Decimal('0')
            credit = lines['total_credit'] or Decimal('0')
            
            # المدين = شراء أصول (تدفق خارج)
            cash_for_investments += debit
            # الدائن = بيع أصول (تدفق داخل)
            cash_from_asset_sales += credit
        
        # صافي التدفق من الأنشطة الاستثمارية
        net_cash_from_investing = cash_from_asset_sales - cash_for_investments
        
        return {
            'cash_for_investments': cash_for_investments,
            'cash_from_asset_sales': cash_from_asset_sales,
            'net_cash_from_investing': net_cash_from_investing,
        }
    
    def _calculate_financing_activities(self) -> Dict[str, Any]:
        """حساب التدفقات من الأنشطة التمويلية"""
        # بناء الفلتر
        filters = {'journal_entry__status': 'posted'}
        if self.date_from:
            filters['journal_entry__date__gte'] = self.date_from
        if self.date_to:
            filters['journal_entry__date__lte'] = self.date_to
        
        # حقوق الملكية والقروض
        equity_accounts = ChartOfAccounts.objects.filter(
            Q(account_type__category='equity') | Q(name__icontains='قرض') | Q(name__icontains='رأس المال'),
            is_active=True,
            is_leaf=True
        )
        
        cash_from_financing = Decimal('0')
        cash_for_financing = Decimal('0')
        
        for account in equity_accounts:
            lines = JournalEntryLine.objects.filter(
                account=account,
                **filters
            ).aggregate(
                total_credit=Sum('credit'),
                total_debit=Sum('debit')
            )
            credit = lines['total_credit'] or Decimal('0')
            debit = lines['total_debit'] or Decimal('0')
            
            # الدائن = زيادة في التمويل (تدفق داخل)
            cash_from_financing += credit
            # المدين = سداد تمويل (تدفق خارج)
            cash_for_financing += debit
        
        # صافي التدفق من الأنشطة التمويلية
        net_cash_from_financing = cash_from_financing - cash_for_financing
        
        return {
            'cash_from_financing': cash_from_financing,
            'cash_for_financing': cash_for_financing,
            'net_cash_from_financing': net_cash_from_financing,
        }
    
    def export_to_excel(self, cash_flow_data: Dict[str, Any]) -> bytes:
        """
        تصدير التقرير إلى Excel
        
        Args:
            cash_flow_data: بيانات التدفقات النقدية
            
        Returns:
            محتوى ملف Excel
        """
        try:
            import openpyxl
            from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
            from io import BytesIO
            
            # إنشاء workbook
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "التدفقات النقدية"
            
            # تنسيق العنوان
            title_font = Font(name='Arial', size=16, bold=True)
            header_font = Font(name='Arial', size=12, bold=True, color='FFFFFF')
            header_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
            
            # العنوان
            ws['A1'] = 'قائمة التدفقات النقدية'
            ws['A1'].font = title_font
            ws.merge_cells('A1:C1')
            
            # الفترة
            ws['A2'] = f"من {self.date_from} إلى {self.date_to}"
            ws.merge_cells('A2:C2')
            
            # الرصيد الافتتاحي
            row = 4
            ws[f'A{row}'] = 'الرصيد النقدي الافتتاحي'
            ws[f'C{row}'] = float(cash_flow_data['opening_cash'])
            
            # الأنشطة التشغيلية
            row += 2
            ws[f'A{row}'] = 'التدفقات من الأنشطة التشغيلية'
            ws[f'A{row}'].font = header_font
            ws[f'A{row}'].fill = header_fill
            
            operating = cash_flow_data['operating_activities']
            row += 1
            ws[f'A{row}'] = 'النقدية من الإيرادات'
            ws[f'C{row}'] = float(operating['cash_from_revenue'])
            
            row += 1
            ws[f'A{row}'] = 'النقدية للمصروفات'
            ws[f'C{row}'] = float(operating['cash_for_expenses'])
            
            row += 1
            ws[f'A{row}'] = 'صافي التدفق من الأنشطة التشغيلية'
            ws[f'A{row}'].font = Font(bold=True)
            ws[f'C{row}'] = float(operating['net_cash_from_operating'])
            ws[f'C{row}'].font = Font(bold=True)
            
            # الأنشطة الاستثمارية
            row += 2
            ws[f'A{row}'] = 'التدفقات من الأنشطة الاستثمارية'
            ws[f'A{row}'].font = header_font
            ws[f'A{row}'].fill = header_fill
            
            investing = cash_flow_data['investing_activities']
            row += 1
            ws[f'A{row}'] = 'النقدية لشراء الأصول'
            ws[f'C{row}'] = float(investing['cash_for_investments'])
            
            row += 1
            ws[f'A{row}'] = 'النقدية من بيع الأصول'
            ws[f'C{row}'] = float(investing['cash_from_asset_sales'])
            
            row += 1
            ws[f'A{row}'] = 'صافي التدفق من الأنشطة الاستثمارية'
            ws[f'A{row}'].font = Font(bold=True)
            ws[f'C{row}'] = float(investing['net_cash_from_investing'])
            ws[f'C{row}'].font = Font(bold=True)
            
            # الأنشطة التمويلية
            row += 2
            ws[f'A{row}'] = 'التدفقات من الأنشطة التمويلية'
            ws[f'A{row}'].font = header_font
            ws[f'A{row}'].fill = header_fill
            
            financing = cash_flow_data['financing_activities']
            row += 1
            ws[f'A{row}'] = 'النقدية من التمويل'
            ws[f'C{row}'] = float(financing['cash_from_financing'])
            
            row += 1
            ws[f'A{row}'] = 'النقدية لسداد التمويل'
            ws[f'C{row}'] = float(financing['cash_for_financing'])
            
            row += 1
            ws[f'A{row}'] = 'صافي التدفق من الأنشطة التمويلية'
            ws[f'A{row}'].font = Font(bold=True)
            ws[f'C{row}'] = float(financing['net_cash_from_financing'])
            ws[f'C{row}'].font = Font(bold=True)
            
            # الإجمالي
            row += 2
            ws[f'A{row}'] = 'صافي التدفق النقدي'
            ws[f'A{row}'].font = Font(bold=True, size=12)
            ws[f'C{row}'] = float(cash_flow_data['net_cash_flow'])
            ws[f'C{row}'].font = Font(bold=True, size=12)
            
            row += 1
            ws[f'A{row}'] = 'الرصيد النقدي الختامي'
            ws[f'A{row}'].font = Font(bold=True, size=12)
            ws[f'C{row}'] = float(cash_flow_data['closing_cash'])
            ws[f'C{row}'].font = Font(bold=True, size=12)
            
            # تنسيق الأعمدة
            ws.column_dimensions['A'].width = 40
            ws.column_dimensions['B'].width = 5
            ws.column_dimensions['C'].width = 20
            
            # حفظ في BytesIO
            output = BytesIO()
            wb.save(output)
            output.seek(0)
            
            return output.getvalue()
            
        except ImportError:
            # في حالة عدم توفر openpyxl
            return b''
