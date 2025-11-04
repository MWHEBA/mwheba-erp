"""
خدمة معالجة الرواتب
"""
from django.db import transaction
from datetime import date
from decimal import Decimal
from ..models import Payroll, Employee, Advance
from .attendance_service import AttendanceService


class PayrollService:
    """خدمة معالجة الرواتب"""
    
    @staticmethod
    @transaction.atomic
    def calculate_payroll(employee, month, processed_by):
        """
        حساب راتب موظف لشهر معين
        
        Args:
            employee: الموظف
            month: الشهر (datetime.date)
            processed_by: المستخدم الذي عالج الراتب
        
        Returns:
            Payroll: كشف الراتب
        """
        # الحصول على الراتب النشط
        salary = employee.salaries.filter(is_active=True).first()
        if not salary:
            raise ValueError('لا يوجد راتب نشط للموظف')
        
        # حساب الحضور
        attendance_stats = AttendanceService.calculate_monthly_attendance(employee, month)
        
        # حساب العمل الإضافي
        overtime_rate = salary.basic_salary / 180  # سعر الساعة
        overtime_amount = Decimal(str(attendance_stats['total_overtime_hours'])) * overtime_rate
        
        # حساب خصم الغياب
        absence_days = attendance_stats.get('absent_days', 0)
        absence_deduction = (salary.basic_salary / 30) * absence_days
        
        # حساب خصم السلف
        advance_deduction = PayrollService._calculate_advance_deduction(employee, month)
        
        # إنشاء كشف الراتب
        payroll = Payroll.objects.create(
            employee=employee,
            month=month,
            salary=salary,
            basic_salary=salary.basic_salary,
            allowances=salary.housing_allowance + salary.transport_allowance + salary.food_allowance,
            overtime_hours=Decimal(str(attendance_stats['total_overtime_hours'])),
            overtime_rate=overtime_rate,
            overtime_amount=overtime_amount,
            absence_days=absence_days,
            absence_deduction=absence_deduction,
            social_insurance=salary.basic_salary * (salary.social_insurance_rate / 100),
            tax=salary.gross_salary * (salary.tax_rate / 100),
            advance_deduction=advance_deduction,
            processed_by=processed_by,
            status='calculated'
        )
        
        # حساب الإجماليات
        payroll.calculate_totals()
        
        return payroll
    
    @staticmethod
    def _calculate_advance_deduction(employee, month):
        """حساب خصم السلف للشهر"""
        # الحصول على السلف المعتمدة وغير المخصومة
        advances = Advance.objects.filter(
            employee=employee,
            status='paid',
            deducted=False
        )
        
        total_deduction = sum(advance.amount for advance in advances)
        
        # تحديد السلف كمخصومة
        for advance in advances:
            advance.mark_as_deducted(month)
        
        return Decimal(str(total_deduction))
    
    @staticmethod
    @transaction.atomic
    def process_monthly_payroll(month, processed_by):
        """
        معالجة رواتب جميع الموظفين لشهر معين
        
        Args:
            month: الشهر (datetime.date)
            processed_by: المستخدم الذي عالج الرواتب
        
        Returns:
            list: نتائج المعالجة
        """
        employees = Employee.objects.filter(status='active')
        results = []
        
        for employee in employees:
            try:
                payroll = PayrollService.calculate_payroll(employee, month, processed_by)
                results.append({
                    'employee': employee,
                    'payroll': payroll,
                    'success': True
                })
            except Exception as e:
                results.append({
                    'employee': employee,
                    'error': str(e),
                    'success': False
                })
        
        return results
    
    @staticmethod
    @transaction.atomic
    def approve_payroll(payroll, approved_by):
        """
        اعتماد كشف راتب
        
        Args:
            payroll: كشف الراتب
            approved_by: المعتمد
        
        Returns:
            Payroll: كشف الراتب المعتمد
        """
        payroll.status = 'approved'
        payroll.approved_by = approved_by
        payroll.approved_at = date.today()
        
        # إنشاء قيد محاسبي
        journal_entry = PayrollService._create_journal_entry(payroll)
        payroll.journal_entry = journal_entry
        
        payroll.save()
        
        return payroll
    
    @staticmethod
    def _create_journal_entry(payroll):
        """
        إنشاء قيد محاسبي للراتب
        
        Args:
            payroll: كشف الراتب
        
        Returns:
            JournalEntry: القيد المحاسبي
        """
        from financial.models import JournalEntry, JournalEntryLine, ChartOfAccounts
        
        # إنشاء القيد
        entry = JournalEntry.objects.create(
            date=payroll.month,
            description=f'راتب {payroll.employee.get_full_name_ar()} - {payroll.month.strftime("%Y-%m")}',
            created_by=payroll.processed_by
        )
        
        # من حـ/ مصروف الرواتب
        salary_expense_account = ChartOfAccounts.objects.filter(code='5101').first()
        if salary_expense_account:
            JournalEntryLine.objects.create(
                journal_entry=entry,
                account=salary_expense_account,
                debit=payroll.gross_salary,
                credit=0
            )
        
        # إلى حـ/ البنك (الصافي)
        bank_account = ChartOfAccounts.objects.filter(code='1102').first()
        if bank_account:
            JournalEntryLine.objects.create(
                journal_entry=entry,
                account=bank_account,
                debit=0,
                credit=payroll.net_salary
            )
        
        # إلى حـ/ التأمينات
        insurance_account = ChartOfAccounts.objects.filter(code='2103').first()
        if insurance_account:
            JournalEntryLine.objects.create(
                journal_entry=entry,
                account=insurance_account,
                debit=0,
                credit=payroll.social_insurance
            )
        
        # إلى حـ/ الضرائب
        tax_account = ChartOfAccounts.objects.filter(code='2104').first()
        if tax_account:
            JournalEntryLine.objects.create(
                journal_entry=entry,
                account=tax_account,
                debit=0,
                credit=payroll.tax
            )
        
        return entry
