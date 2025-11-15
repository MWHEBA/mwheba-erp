"""
خدمة معالجة الرواتب المتكاملة مع الحضور والإجازات
"""
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, timedelta
from django.db import transaction
from django.utils import timezone
from django.db.models import Q
from ..models import (
    Payroll, PayrollLine, AttendanceSummary, LeaveSummary,
    Employee, Contract, SalaryComponent, Advance
)
from .advance_service import AdvanceService
import logging

logger = logging.getLogger(__name__)


class IntegratedPayrollService:
    """خدمة معالجة الرواتب المتكاملة مع الحضور والإجازات"""
    
    @staticmethod
    @transaction.atomic
    def calculate_integrated_payroll(employee, month, processed_by):
        """
        حساب راتب موظف بشكل متكامل مع الحضور والإجازات
        
        Args:
            employee: الموظف
            month: الشهر (datetime.date)
            processed_by: المستخدم المعالج
        
        Returns:
            Payroll: قسيمة الراتب
        """
        logger.info(f"بدء حساب راتب متكامل لـ {employee.get_full_name_ar()} - {month.strftime('%Y-%m')}")
        
        # 1. التحقق من وجود عقد نشط
        contract = employee.contracts.filter(status='active').first()
        if not contract:
            raise ValueError(f'لا يوجد عقد نشط للموظف {employee.get_full_name_ar()}')
        
        # 2. التحقق من عدم وجود راتب لنفس الشهر
        if Payroll.objects.filter(employee=employee, month=month).exists():
            raise ValueError(f'يوجد راتب محسوب مسبقاً لشهر {month.strftime("%Y-%m")}')
        
        # 3. حساب أو جلب ملخص الحضور
        attendance_summary = IntegratedPayrollService._get_or_calculate_attendance_summary(employee, month)
        
        # 4. حساب أو جلب ملخص الإجازات
        leave_summary = IntegratedPayrollService._get_or_calculate_leave_summary(employee, month)
        
        # 5. إنشاء قسيمة الراتب
        payroll = Payroll.objects.create(
            employee=employee,
            month=month,
            contract=contract,
            basic_salary=contract.basic_salary,
            status='calculated',
            processed_by=processed_by,
            processed_at=timezone.now(),
            gross_salary=0,
            net_salary=0
        )
        
        logger.info(f"تم إنشاء قسيمة راتب #{payroll.id}")
        
        # 6. إضافة بنود الراتب الأساسية من العقد
        IntegratedPayrollService._add_contract_components(payroll, contract)
        
        # 7. إضافة بنود الحضور
        IntegratedPayrollService._add_attendance_components(payroll, attendance_summary)
        
        # 8. إضافة بنود الإجازات
        IntegratedPayrollService._add_leave_components(payroll, leave_summary)
        
        # 9. إضافة خصم السلف
        IntegratedPayrollService._add_advance_deductions(payroll, month)
        
        # 10. حساب الإجماليات
        payroll.calculate_totals_from_lines()
        payroll.save()
        
        logger.info(f"تم حساب الراتب: إجمالي {payroll.gross_salary}، صافي {payroll.net_salary}")
        
        return payroll
    
    @staticmethod
    def _get_or_calculate_attendance_summary(employee, month):
        """الحصول على ملخص الحضور أو حسابه"""
        from .attendance_summary_service import AttendanceSummaryService
        
        try:
            summary = AttendanceSummary.objects.get(employee=employee, month=month)
            if not summary.is_calculated:
                summary.calculate()
        except AttendanceSummary.DoesNotExist:
            summary = AttendanceSummaryService.calculate_monthly_summary(employee, month)
        
        return summary
    
    @staticmethod
    def _get_or_calculate_leave_summary(employee, month):
        """الحصول على ملخص الإجازات أو حسابه"""
        try:
            summary = LeaveSummary.objects.get(employee=employee, month=month)
            if not summary.is_calculated:
                summary.calculate()
        except LeaveSummary.DoesNotExist:
            summary = LeaveSummary.objects.create(employee=employee, month=month)
            summary.calculate()
        
        return summary
    
    @staticmethod
    def _add_contract_components(payroll, contract):
        """إضافة بنود الراتب من العقد"""
        # الراتب الأساسي
        PayrollLine.objects.create(
            payroll=payroll,
            code='BASIC_SALARY',
            name='الراتب الأساسي',
            component_type='earning',
            source='contract',
            quantity=1,
            rate=contract.basic_salary,
            amount=contract.basic_salary,
            order=1
        )
        
        # بنود الراتب الإضافية من الموظف
        salary_components = contract.employee.salary_components.filter(
            is_active=True,
            effective_from__lte=payroll.month
        ).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gte=payroll.month)
        )
        
        order = 10
        for component in salary_components:
            if component.is_basic:
                continue  # تخطي الراتب الأساسي لأنه مضاف بالفعل
            
            PayrollLine.objects.create(
                payroll=payroll,
                code=component.code,
                name=component.name,
                component_type=component.component_type,
                source='contract',
                quantity=1,
                rate=component.amount,
                amount=component.amount,
                salary_component=component,
                order=order
            )
            order += 1
    
    @staticmethod
    def _add_attendance_components(payroll, attendance_summary):
        """إضافة بنود الحضور"""
        order = 100
        
        # خصم الغياب
        if attendance_summary.absence_deduction_amount > 0:
            PayrollLine.objects.create(
                payroll=payroll,
                code='ABSENCE_DEDUCTION',
                name=f'خصم غياب ({attendance_summary.absent_days} يوم)',
                component_type='deduction',
                source='attendance',
                quantity=attendance_summary.absent_days,
                rate=attendance_summary.absence_deduction_amount / attendance_summary.absent_days if attendance_summary.absent_days > 0 else 0,
                amount=attendance_summary.absence_deduction_amount,
                description=f'خصم {attendance_summary.absent_days} يوم غياب',
                order=order
            )
            order += 1
        
        # خصم التأخير
        if attendance_summary.late_deduction_amount > 0:
            PayrollLine.objects.create(
                payroll=payroll,
                code='LATE_DEDUCTION',
                name=f'خصم تأخير ({attendance_summary.total_late_minutes} دقيقة)',
                component_type='deduction',
                source='attendance',
                quantity=attendance_summary.total_late_minutes,
                rate=attendance_summary.late_deduction_amount / attendance_summary.total_late_minutes if attendance_summary.total_late_minutes > 0 else 0,
                amount=attendance_summary.late_deduction_amount,
                description=f'خصم {attendance_summary.total_late_minutes} دقيقة تأخير',
                order=order
            )
            order += 1
        
        # العمل الإضافي
        if attendance_summary.overtime_amount > 0:
            PayrollLine.objects.create(
                payroll=payroll,
                code='OVERTIME',
                name=f'عمل إضافي ({attendance_summary.total_overtime_hours} ساعة)',
                component_type='earning',
                source='overtime',
                quantity=attendance_summary.total_overtime_hours,
                rate=attendance_summary.overtime_amount / attendance_summary.total_overtime_hours if attendance_summary.total_overtime_hours > 0 else 0,
                amount=attendance_summary.overtime_amount,
                description=f'{attendance_summary.total_overtime_hours} ساعة عمل إضافي',
                order=order
            )
    
    @staticmethod
    def _add_leave_components(payroll, leave_summary):
        """إضافة بنود الإجازات"""
        order = 200
        
        # خصم الإجازات غير المدفوعة
        if leave_summary.deduction_amount > 0:
            PayrollLine.objects.create(
                payroll=payroll,
                code='UNPAID_LEAVE_DEDUCTION',
                name=f'خصم إجازات بدون راتب ({leave_summary.total_unpaid_days} يوم)',
                component_type='deduction',
                source='leave',
                quantity=leave_summary.total_unpaid_days,
                rate=leave_summary.deduction_amount / leave_summary.total_unpaid_days if leave_summary.total_unpaid_days > 0 else 0,
                amount=leave_summary.deduction_amount,
                description=f'خصم {leave_summary.total_unpaid_days} يوم إجازة بدون راتب',
                calculation_details=leave_summary.details,
                order=order
            )
    
    @staticmethod
    def _add_advance_deductions(payroll, month):
        """إضافة خصم السلف - استخدام AdvanceService"""
        # استخدام AdvanceService لحساب الخصومات
        total_deduction, advances_list = AdvanceService.calculate_advance_deduction(
            employee=payroll.employee,
            payroll_month=month
        )
        
        order = 300
        for advance_data in advances_list:
            advance = advance_data['advance']
            installment_amount = advance_data['amount']
            
            # تسجيل القسط
            installment = AdvanceService.record_advance_deduction(
                payroll=payroll,
                advance=advance,
                amount=installment_amount
            )
            
            # إضافة بند الخصم
            PayrollLine.objects.create(
                payroll=payroll,
                code=f'ADVANCE_{advance.id}',
                name=f'قسط سلفة ({advance.paid_installments}/{advance.installments_count})',
                component_type='deduction',
                source='advance',
                quantity=1,
                rate=installment_amount,
                amount=installment_amount,
                advance_installment=installment,
                description=f'قسط {advance.paid_installments} من {advance.installments_count}',
                order=order
            )
            order += 1
    
    @staticmethod
    @transaction.atomic
    def process_monthly_payroll_integrated(month, processed_by, employees=None):
        """
        معالجة رواتب الموظفين لشهر معين بشكل متكامل
        
        Args:
            month: الشهر
            processed_by: المستخدم المعالج
            employees: قائمة الموظفين (اختياري)
        
        Returns:
            dict: نتائج المعالجة
        """
        if employees is None:
            employees = Employee.objects.filter(status='active')
            # استبعاد الموظفين اللي عندهم راتب في نفس الشهر
            processed_ids = Payroll.objects.filter(month=month).values_list('employee_id', flat=True)
            employees = employees.exclude(id__in=processed_ids)
        
        results = {
            'success': [],
            'failed': [],
            'total': employees.count()
        }
        
        for employee in employees:
            try:
                payroll = IntegratedPayrollService.calculate_integrated_payroll(
                    employee, month, processed_by
                )
                results['success'].append({
                    'employee': employee,
                    'payroll': payroll
                })
            except Exception as e:
                logger.error(f"فشل حساب راتب {employee.get_full_name_ar()}: {str(e)}")
                results['failed'].append({
                    'employee': employee,
                    'error': str(e)
                })
        
        logger.info(f"تم معالجة {len(results['success'])} راتب، فشل {len(results['failed'])}")
        
        return results

