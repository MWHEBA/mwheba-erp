# financial/services/customer_supplier_balances_service.py
"""
خدمة تقارير أرصدة العملاء والموردين
تحليل الفواتير المستحقة حسب فترات الاستحقاق
"""

from django.db.models import Sum, Q, F, Case, When, Value, DecimalField
from django.db.models.functions import Coalesce
from decimal import Decimal
from datetime import date, timedelta
from typing import Dict, List, Optional, Any


class CustomerSupplierBalancesService:
    """خدمة تقارير أرصدة العملاء والموردين"""
    
    def __init__(self, as_of_date: Optional[date] = None):
        """
        تهيئة الخدمة
        
        Args:
            as_of_date: تاريخ التقرير (افتراضي: اليوم)
        """
        from django.utils import timezone
        self.as_of_date = as_of_date or timezone.now().date()
    
    def generate_customer_balances_report(self) -> Dict[str, Any]:
        """
        إنشاء تقرير أرصدة العملاء
        
        Returns:
            قاموس يحتوي على:
            - accounts: قائمة الحسابات مع الأرصدة
            - due_periods: التوزيع حسب فترات الاستحقاق
            - summary: ملخص الإجماليات
        """
        # استخدام نماذج المبيعات مباشرة (الطريقة الصحيحة)
        try:
            from client.models import Customer
            from sale.models import Sale, SalePayment
        except ImportError:
            return {
                'error': 'نماذج المبيعات غير متوفرة',
                'accounts': [],
                'due_periods': {},
                'summary': {}
            }
        
        # جلب جميع العملاء النشطين
        customers = Customer.objects.filter(is_active=True)
        
        accounts_data = []
        total_current = Decimal('0')
        total_30 = Decimal('0')
        total_60 = Decimal('0')
        total_90 = Decimal('0')
        total_over_90 = Decimal('0')
        
        for customer in customers:
            # حساب رصيد العميل
            account_data = self._calculate_customer_balance(customer)
            
            if account_data['total_balance'] > 0:
                accounts_data.append(account_data)
                
                # إضافة للإجماليات
                total_current += account_data['current']
                total_30 += account_data['days_1_30']
                total_60 += account_data['days_31_60']
                total_90 += account_data['days_61_90']
                total_over_90 += account_data['over_90']
        
        # ترتيب حسب الرصيد (الأكبر أولاً)
        accounts_data.sort(key=lambda x: x['total_balance'], reverse=True)
        
        # حساب النسب المئوية
        total_balance = total_current + total_30 + total_60 + total_90 + total_over_90
        
        due_periods = {
            'current': {
                'amount': total_current,
                'percentage': (total_current / total_balance * 100) if total_balance > 0 else 0,
                'label': 'حالي (0-30 يوم)',
                'days': '0-30'
            },
            'days_1_30': {
                'amount': total_30,
                'percentage': (total_30 / total_balance * 100) if total_balance > 0 else 0,
                'label': '31-60 يوم',
                'days': '31-60'
            },
            'days_31_60': {
                'amount': total_60,
                'percentage': (total_60 / total_balance * 100) if total_balance > 0 else 0,
                'label': '61-90 يوم',
                'days': '61-90'
            },
            'days_61_90': {
                'amount': total_90,
                'percentage': (total_90 / total_balance * 100) if total_balance > 0 else 0,
                'label': '91-120 يوم',
                'days': '91-120'
            },
            'over_90': {
                'amount': total_over_90,
                'percentage': (total_over_90 / total_balance * 100) if total_balance > 0 else 0,
                'label': 'أكثر من 120 يوم',
                'days': '120+'
            },
        }
        
        summary = {
            'total_balance': total_balance,
            'total_accounts': len(accounts_data),
            'as_of_date': self.as_of_date,
        }
        
        return {
            'accounts': accounts_data,
            'due_periods': due_periods,
            'summary': summary,
            'as_of_date': self.as_of_date,
        }
    
    def generate_supplier_balances_report(self) -> Dict[str, Any]:
        """
        إنشاء تقرير أرصدة الموردين
        
        Returns:
            قاموس يحتوي على:
            - accounts: قائمة الحسابات مع الأرصدة
            - due_periods: التوزيع حسب فترات الاستحقاق
            - summary: ملخص الإجماليات
        """
        # استخدام نماذج المشتريات مباشرة (الطريقة الصحيحة)
        try:
            from supplier.models import Supplier
            from purchase.models import Purchase, PurchasePayment
        except ImportError:
            return {
                'error': 'نماذج المشتريات غير متوفرة',
                'accounts': [],
                'due_periods': {},
                'summary': {}
            }
        
        # جلب جميع الموردين النشطين
        suppliers = Supplier.objects.filter(is_active=True)
        
        accounts_data = []
        total_current = Decimal('0')
        total_30 = Decimal('0')
        total_60 = Decimal('0')
        total_90 = Decimal('0')
        total_over_90 = Decimal('0')
        
        for supplier in suppliers:
            # حساب رصيد المورد
            account_data = self._calculate_supplier_balance(supplier)
            
            if account_data['total_balance'] > 0:
                accounts_data.append(account_data)
                
                # إضافة للإجماليات
                total_current += account_data['current']
                total_30 += account_data['days_1_30']
                total_60 += account_data['days_31_60']
                total_90 += account_data['days_61_90']
                total_over_90 += account_data['over_90']
        
        # ترتيب حسب الرصيد (الأكبر أولاً)
        accounts_data.sort(key=lambda x: x['total_balance'], reverse=True)
        
        # حساب النسب المئوية
        total_balance = total_current + total_30 + total_60 + total_90 + total_over_90
        
        due_periods = {
            'current': {
                'amount': total_current,
                'percentage': (total_current / total_balance * 100) if total_balance > 0 else 0,
                'label': 'حالي (0-30 يوم)',
                'days': '0-30'
            },
            'days_1_30': {
                'amount': total_30,
                'percentage': (total_30 / total_balance * 100) if total_balance > 0 else 0,
                'label': '31-60 يوم',
                'days': '31-60'
            },
            'days_31_60': {
                'amount': total_60,
                'percentage': (total_60 / total_balance * 100) if total_balance > 0 else 0,
                'label': '61-90 يوم',
                'days': '61-90'
            },
            'days_61_90': {
                'amount': total_90,
                'percentage': (total_90 / total_balance * 100) if total_balance > 0 else 0,
                'label': '91-120 يوم',
                'days': '91-120'
            },
            'over_90': {
                'amount': total_over_90,
                'percentage': (total_over_90 / total_balance * 100) if total_balance > 0 else 0,
                'label': 'أكثر من 120 يوم',
                'days': '120+'
            },
        }
        
        summary = {
            'total_balance': total_balance,
            'total_accounts': len(accounts_data),
            'as_of_date': self.as_of_date,
        }
        
        return {
            'accounts': accounts_data,
            'due_periods': due_periods,
            'summary': summary,
            'as_of_date': self.as_of_date,
        }
    
    def _calculate_customer_balance(self, customer) -> Dict[str, Any]:
        """حساب رصيد عميل معين حسب فترات الاستحقاق"""
        try:
            from sale.models import Sale
        except ImportError:
            return self._empty_balance_data(customer.name, customer.id)
        
        # جلب الفواتير المؤكدة فقط حتى تاريخ التقرير
        sales = Sale.objects.filter(
            customer=customer,
            status='confirmed',  # فقط الفواتير المؤكدة
            date__lte=self.as_of_date
        )
        
        current = Decimal('0')
        days_1_30 = Decimal('0')
        days_31_60 = Decimal('0')
        days_61_90 = Decimal('0')
        over_90 = Decimal('0')
        
        for sale in sales:
            # حساب الرصيد المتبقي (الإجمالي - المدفوع)
            remaining_balance = sale.amount_due
            
            # تخطي الفواتير المدفوعة بالكامل
            if remaining_balance <= 0:
                continue
            
            # حساب عدد الأيام منذ تاريخ الفاتورة
            days_old = (self.as_of_date - sale.date).days
            
            # تصنيف حسب العمر
            if days_old <= 30:
                current += remaining_balance
            elif days_old <= 60:
                days_1_30 += remaining_balance
            elif days_old <= 90:
                days_31_60 += remaining_balance
            elif days_old <= 120:
                days_61_90 += remaining_balance
            else:
                over_90 += remaining_balance
        
        total_balance = current + days_1_30 + days_31_60 + days_61_90 + over_90
        
        return {
            'account_id': customer.id,
            'account_name': customer.name,
            'account_code': customer.code or '',
            'current': current,
            'days_1_30': days_1_30,
            'days_31_60': days_31_60,
            'days_61_90': days_61_90,
            'over_90': over_90,
            'total_balance': total_balance,
        }
    
    def _calculate_supplier_balance(self, supplier) -> Dict[str, Any]:
        """حساب رصيد مورد معين حسب فترات الاستحقاق"""
        try:
            from purchase.models import Purchase
        except ImportError:
            return self._empty_balance_data(supplier.name, supplier.id)
        
        # جلب الفواتير المؤكدة فقط حتى تاريخ التقرير
        purchases = Purchase.objects.filter(
            supplier=supplier,
            status='confirmed',  # فقط الفواتير المؤكدة
            date__lte=self.as_of_date
        )
        
        current = Decimal('0')
        days_1_30 = Decimal('0')
        days_31_60 = Decimal('0')
        days_61_90 = Decimal('0')
        over_90 = Decimal('0')
        
        for purchase in purchases:
            # حساب الرصيد المتبقي (الإجمالي - المدفوع)
            remaining_balance = purchase.amount_due
            
            # تخطي الفواتير المدفوعة بالكامل
            if remaining_balance <= 0:
                continue
            
            # حساب عدد الأيام منذ تاريخ الفاتورة
            days_old = (self.as_of_date - purchase.date).days
            
            # تصنيف حسب العمر
            if days_old <= 30:
                current += remaining_balance
            elif days_old <= 60:
                days_1_30 += remaining_balance
            elif days_old <= 90:
                days_31_60 += remaining_balance
            elif days_old <= 120:
                days_61_90 += remaining_balance
            else:
                over_90 += remaining_balance
        
        total_balance = current + days_1_30 + days_31_60 + days_61_90 + over_90
        
        return {
            'account_id': supplier.id,
            'account_name': supplier.name,
            'account_code': supplier.code or '',
            'current': current,
            'days_1_30': days_1_30,
            'days_31_60': days_31_60,
            'days_61_90': days_61_90,
            'over_90': over_90,
            'total_balance': total_balance,
        }
    
    def _empty_balance_data(self, name: str, account_id: int) -> Dict[str, Any]:
        """بيانات فارغة لحساب بدون رصيد"""
        return {
            'account_id': account_id,
            'account_name': name,
            'account_code': '',
            'current': Decimal('0'),
            'days_1_30': Decimal('0'),
            'days_31_60': Decimal('0'),
            'days_61_90': Decimal('0'),
            'over_90': Decimal('0'),
            'total_balance': Decimal('0'),
        }
    
    def export_to_excel(self, report_data: Dict[str, Any], report_type: str = 'ar') -> bytes:
        """
        تصدير التقرير إلى Excel
        
        Args:
            report_data: بيانات التقرير
            report_type: نوع التقرير ('ar' أو 'ap')
            
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
            
            title = 'تقرير أرصدة العملاء' if report_type == 'ar' else 'تقرير أرصدة الموردين'
            ws.title = title
            
            # تنسيق العنوان
            title_font = Font(name='Arial', size=16, bold=True)
            header_font = Font(name='Arial', size=12, bold=True, color='FFFFFF')
            header_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
            
            # العنوان
            ws['A1'] = title
            ws['A1'].font = title_font
            ws.merge_cells('A1:H1')
            
            # التاريخ
            ws['A2'] = f"كما في: {self.as_of_date}"
            ws.merge_cells('A2:H2')
            
            # العناوين
            row = 4
            headers = ['الكود', 'الاسم', 'حالي (0-30)', '31-60 يوم', '61-90 يوم', '91-120 يوم', '+120 يوم', 'الإجمالي']
            for col, header in enumerate(headers, 1):
                cell = ws.cell(row=row, column=col)
                cell.value = header
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = Alignment(horizontal='center')
            
            # البيانات
            for account in report_data['accounts']:
                row += 1
                ws.cell(row=row, column=1, value=account['account_code'])
                ws.cell(row=row, column=2, value=account['account_name'])
                ws.cell(row=row, column=3, value=float(account['current']))
                ws.cell(row=row, column=4, value=float(account['days_1_30']))
                ws.cell(row=row, column=5, value=float(account['days_31_60']))
                ws.cell(row=row, column=6, value=float(account['days_61_90']))
                ws.cell(row=row, column=7, value=float(account['over_90']))
                ws.cell(row=row, column=8, value=float(account['total_balance']))
            
            # الإجماليات
            row += 2
            ws.cell(row=row, column=2, value='الإجمالي').font = Font(bold=True)
            due_periods = report_data['due_periods']
            ws.cell(row=row, column=3, value=float(due_periods['current']['amount'])).font = Font(bold=True)
            ws.cell(row=row, column=4, value=float(due_periods['days_1_30']['amount'])).font = Font(bold=True)
            ws.cell(row=row, column=5, value=float(due_periods['days_31_60']['amount'])).font = Font(bold=True)
            ws.cell(row=row, column=6, value=float(due_periods['days_61_90']['amount'])).font = Font(bold=True)
            ws.cell(row=row, column=7, value=float(due_periods['over_90']['amount'])).font = Font(bold=True)
            ws.cell(row=row, column=8, value=float(report_data['summary']['total_balance'])).font = Font(bold=True)
            
            # تنسيق الأعمدة
            ws.column_dimensions['A'].width = 12
            ws.column_dimensions['B'].width = 30
            for col in ['C', 'D', 'E', 'F', 'G', 'H']:
                ws.column_dimensions[col].width = 15
            
            # حفظ في BytesIO
            output = BytesIO()
            wb.save(output)
            output.seek(0)
            
            return output.getvalue()
            
        except ImportError:
            return b''
    
    def _generate_customer_from_journal_entries(self) -> Dict[str, Any]:
        """
        إنشاء تقرير أرصدة العملاء من القيود المحاسبية مباشرة
        """
        from financial.models.chart_of_accounts import ChartOfAccounts
        from financial.models.journal_entry import JournalEntryLine
        
        # جلب حسابات العملاء فقط (كود 11030)
        try:
            base_account = ChartOfAccounts.objects.get(code='11030', is_active=True)
            # جلب الحساب الرئيسي وجميع الحسابات الفرعية
            asset_accounts = ChartOfAccounts.objects.filter(
                code__startswith='11030',
                is_active=True
            )
        except ChartOfAccounts.DoesNotExist:
            # إذا لم يوجد حساب العملاء، نرجع بيانات فارغة
            return {
                'accounts': [],
                'due_periods': {},
                'summary': {'total_balance': Decimal('0'), 'accounts_count': 0},
                'as_of_date': self.as_of_date,
            }
        
        accounts_data = []
        total_current = Decimal('0')
        total_30 = Decimal('0')
        total_60 = Decimal('0')
        total_90 = Decimal('0')
        total_over_90 = Decimal('0')
        
        for account in asset_accounts:
            # حساب الرصيد المدين لكل فترة استحقاق
            account_balance = self._calculate_account_balance_from_entries(account, 'debit')
            
            if account_balance['total_balance'] > 0:
                accounts_data.append(account_balance)
                total_current += account_balance['current']
                total_30 += account_balance['days_1_30']
                total_60 += account_balance['days_31_60']
                total_90 += account_balance['days_61_90']
                total_over_90 += account_balance['over_90']
        
        # ترتيب حسب الرصيد
        accounts_data.sort(key=lambda x: x['total_balance'], reverse=True)
        
        # حساب الإجماليات
        total_balance = total_current + total_30 + total_60 + total_90 + total_over_90
        
        due_periods = {
            'current': {
                'amount': total_current,
                'percentage': (total_current / total_balance * 100) if total_balance > 0 else 0,
                'label': 'حالي (0-30 يوم)',
                'days': '0-30'
            },
            'days_1_30': {
                'amount': total_30,
                'percentage': (total_30 / total_balance * 100) if total_balance > 0 else 0,
                'label': '31-60 يوم',
                'days': '31-60'
            },
            'days_31_60': {
                'amount': total_60,
                'percentage': (total_60 / total_balance * 100) if total_balance > 0 else 0,
                'label': '61-90 يوم',
                'days': '61-90'
            },
            'days_61_90': {
                'amount': total_90,
                'percentage': (total_90 / total_balance * 100) if total_balance > 0 else 0,
                'label': '91-120 يوم',
                'days': '91-120'
            },
            'over_90': {
                'amount': total_over_90,
                'percentage': (total_over_90 / total_balance * 100) if total_balance > 0 else 0,
                'label': 'أكثر من 120 يوم',
                'days': '>120'
            }
        }
        
        summary = {
            'total_balance': total_balance,
            'accounts_count': len(accounts_data),
        }
        
        return {
            'accounts': accounts_data,
            'due_periods': due_periods,
            'summary': summary,
            'as_of_date': self.as_of_date,
        }
    
    def _calculate_account_balance_from_entries(self, account, balance_type='debit') -> Dict[str, Any]:
        """
        حساب رصيد حساب معين حسب فترات الاستحقاق من القيود المحاسبية
        يحسب صافي الرصيد (المدين - الدائن) لكل فترة
        """
        from financial.models.journal_entry import JournalEntryLine
        
        # جلب جميع القيود المرحلة للحساب حتى تاريخ التقرير
        lines = JournalEntryLine.objects.filter(
            account=account,
            journal_entry__status='posted',
            journal_entry__date__lte=self.as_of_date
        ).select_related('journal_entry')
        
        current = Decimal('0')
        days_1_30 = Decimal('0')
        days_31_60 = Decimal('0')
        days_61_90 = Decimal('0')
        over_90 = Decimal('0')
        
        for line in lines:
            # حساب عمر القيد
            age_days = (self.as_of_date - line.journal_entry.date).days
            
            # حساب صافي المبلغ (المدين - الدائن)
            # للعملاء: المدين موجب (لهم علينا)، الدائن سالب (دفعوا)
            # للموردين: الدائن موجب (علينا لهم)، المدين سالب (دفعنا)
            if balance_type == 'debit':
                net_amount = line.debit - line.credit
            else:
                net_amount = line.credit - line.debit
            
            # تصنيف حسب العمر (فقط الأرصدة الموجبة)
            if net_amount > 0:
                if age_days <= 30:
                    current += net_amount
                elif age_days <= 60:
                    days_1_30 += net_amount
                elif age_days <= 90:
                    days_31_60 += net_amount
                elif age_days <= 120:
                    days_61_90 += net_amount
                else:
                    over_90 += net_amount
        
        total_balance = current + days_1_30 + days_31_60 + days_61_90 + over_90
        
        return {
            'account_code': account.code,
            'account_name': account.name,
            'current': current,
            'days_1_30': days_1_30,
            'days_31_60': days_31_60,
            'days_61_90': days_61_90,
            'over_90': over_90,
            'total_balance': total_balance,
        }
    
    def _generate_supplier_from_journal_entries(self) -> Dict[str, Any]:
        """
        إنشاء تقرير أرصدة الموردين من القيود المحاسبية مباشرة
        """
        from financial.models.chart_of_accounts import ChartOfAccounts
        
        # جلب حسابات الموردين فقط (كود 21010)
        try:
            base_account = ChartOfAccounts.objects.get(code='21010', is_active=True)
            # جلب الحساب الرئيسي وجميع الحسابات الفرعية
            liability_accounts = ChartOfAccounts.objects.filter(
                code__startswith='21010',
                is_active=True
            )
        except ChartOfAccounts.DoesNotExist:
            # إذا لم يوجد حساب الموردين، نرجع بيانات فارغة
            return {
                'accounts': [],
                'due_periods': {},
                'summary': {'total_balance': Decimal('0'), 'accounts_count': 0},
                'as_of_date': self.as_of_date,
            }
        
        accounts_data = []
        total_current = Decimal('0')
        total_30 = Decimal('0')
        total_60 = Decimal('0')
        total_90 = Decimal('0')
        total_over_90 = Decimal('0')
        
        for account in liability_accounts:
            # حساب الرصيد الدائن لكل فترة استحقاق
            account_balance = self._calculate_account_balance_from_entries(account, 'credit')
            
            if account_balance['total_balance'] > 0:
                accounts_data.append(account_balance)
                total_current += account_balance['current']
                total_30 += account_balance['days_1_30']
                total_60 += account_balance['days_31_60']
                total_90 += account_balance['days_61_90']
                total_over_90 += account_balance['over_90']
        
        # ترتيب حسب الرصيد
        accounts_data.sort(key=lambda x: x['total_balance'], reverse=True)
        
        # حساب الإجماليات
        total_balance = total_current + total_30 + total_60 + total_90 + total_over_90
        
        due_periods = {
            'current': {
                'amount': total_current,
                'percentage': (total_current / total_balance * 100) if total_balance > 0 else 0,
                'label': 'حالي (0-30 يوم)',
                'days': '0-30'
            },
            'days_1_30': {
                'amount': total_30,
                'percentage': (total_30 / total_balance * 100) if total_balance > 0 else 0,
                'label': '31-60 يوم',
                'days': '31-60'
            },
            'days_31_60': {
                'amount': total_60,
                'percentage': (total_60 / total_balance * 100) if total_balance > 0 else 0,
                'label': '61-90 يوم',
                'days': '61-90'
            },
            'days_61_90': {
                'amount': total_90,
                'percentage': (total_90 / total_balance * 100) if total_balance > 0 else 0,
                'label': '91-120 يوم',
                'days': '91-120'
            },
            'over_90': {
                'amount': total_over_90,
                'percentage': (total_over_90 / total_balance * 100) if total_balance > 0 else 0,
                'label': 'أكثر من 120 يوم',
                'days': '>120'
            }
        }
        
        summary = {
            'total_balance': total_balance,
            'accounts_count': len(accounts_data),
        }
        
        return {
            'accounts': accounts_data,
            'due_periods': due_periods,
            'summary': summary,
            'as_of_date': self.as_of_date,
        }
