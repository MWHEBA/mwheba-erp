"""
خدمة معالجة الرواتب المتكاملة مع الحضور والإجازات

DEPRECATED: This service is deprecated. Use HRPayrollGatewayService instead.
"""
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, timedelta
from django.db import transaction
from django.utils import timezone
from django.db.models import Q
import warnings
from ..models import (
    Payroll, PayrollLine, AttendanceSummary, LeaveSummary,
    Employee, Contract, SalaryComponent, Advance
)
from .advance_service import AdvanceService
import logging

logger = logging.getLogger(__name__)


class IntegratedPayrollService:
    """
    خدمة معالجة الرواتب المتكاملة مع الحضور والإجازات
    
    DEPRECATED: Use HRPayrollGatewayService instead for better governance,
    idempotency, and audit trail.
    """
    
    @staticmethod
    @transaction.atomic
    def calculate_integrated_payroll(employee, month, processed_by):
        """
        حساب راتب موظف بشكل متكامل مع الحضور والإجازات
        
        DEPRECATED: Use HRPayrollGatewayService.calculate_employee_payroll() instead.
        
        Args:
            employee: الموظف
            month: الشهر (datetime.date)
            processed_by: المستخدم المعالج
        
        Returns:
            Payroll: قسيمة الراتب
        """
        warnings.warn(
            "IntegratedPayrollService.calculate_integrated_payroll() is deprecated. "
            "Use HRPayrollGatewayService.calculate_employee_payroll() instead.",
            DeprecationWarning,
            stacklevel=2
        )
        
        
        # 1. التحقق من وجود عقد نشط للشهر المحدد (مع دعم الدورة المرنة)
        from hr.utils.payroll_helpers import get_payroll_period
        _, period_end, _ = get_payroll_period(month)
        contract = employee.contracts.filter(
            status='active',
            start_date__lte=period_end
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=month)
        ).order_by('-start_date').first()
        if not contract:
            raise ValueError(f'لا يوجد عقد نشط للموظف {employee.get_full_name_ar()}')

        # 1b. Attendance approval gate — applies to all employees including exempt ones
        _att_summary_check = AttendanceSummary.objects.filter(
            employee=employee, month=month
        ).first()
        if not _att_summary_check:
            raise ValueError(
                f'لم يتم حساب ملخص الحضور للموظف {employee.get_full_name_ar()} '
                f'لشهر {month.strftime("%Y-%m")} — يجب حساب الملخص واعتماده أولاً'
            )
        if not _att_summary_check.is_approved:
            raise ValueError(
                f'لم يتم اعتماد ملخص الحضور للموظف {employee.get_full_name_ar()} '
                f'لشهر {month.strftime("%Y-%m")} — يجب اعتماد الملخص قبل حساب الراتب'
            )

        # 2. التحقق من عدم وجود راتب لنفس الشهر
        if Payroll.objects.filter(employee=employee, month=month).exists():
            raise ValueError(f'يوجد راتب محسوب مسبقاً لشهر {month.strftime("%Y-%m")}')
        
        # 3. حساب أو جلب ملخص الحضور
        attendance_summary = IntegratedPayrollService._get_or_calculate_attendance_summary(employee, month)
        
        # 4. حساب أو جلب ملخص الإجازات
        leave_summary = IntegratedPayrollService._get_or_calculate_leave_summary(employee, month)
        
        # 5. إنشاء قسيمة الراتب
        dept = getattr(employee, 'department', None)
        fin_subcategory = getattr(dept, 'financial_subcategory', None) if dept else None
        fin_category = fin_subcategory.parent_category if fin_subcategory else None

        payroll = Payroll.objects.create(
            employee=employee,
            month=month,
            contract=contract,
            basic_salary=contract.basic_salary,
            status='calculated',
            processed_by=processed_by,
            processed_at=timezone.now(),
            gross_salary=0,
            net_salary=0,
            financial_subcategory=fin_subcategory,
            financial_category=fin_category,
        )
        
        
        # 6. إضافة بنود الأجر الأساسية من العقد
        IntegratedPayrollService._add_contract_components(payroll, contract)
        
        # 7. إضافة بنود الحضور
        IntegratedPayrollService._add_attendance_components(payroll, attendance_summary)
        
        # 8. إضافة بنود الإجازات
        IntegratedPayrollService._add_leave_components(payroll, leave_summary)
        
        # 9. إضافة خصم السلف
        IntegratedPayrollService._add_advance_deductions(payroll, month)
        
        # 10. تطبيق الجزاءات والمكافآت المعتمدة
        IntegratedPayrollService._add_penalty_reward_components(payroll, employee, month)

        # 11. حساب الإجماليات
        payroll.calculate_totals_from_lines()
        payroll.save()
        
        return payroll
    
    @staticmethod
    def _get_or_calculate_attendance_summary(employee, month):
        """الحصول على ملخص الحضور أو حسابه"""
        from .attendance_summary_service import AttendanceSummaryService
        
        try:
            summary = AttendanceSummary.objects.get(employee=employee, month=month)
            # لو معتمد → لا نعيد الحساب أبداً، نستخدم القيم المعتمدة كما هي
            if summary.is_approved:
                return summary
            # لو محسوب بس مش معتمد → نعيد الحساب لتحديث القيم
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
        """إضافة بنود الراتب من العقد والموظف بمنطق تواريخ متسق"""
        # الأجر الأساسي
        PayrollLine.objects.create(
            payroll=payroll,
            code='BASIC_SALARY',
            name='الأجر الأساسي',
            component_type='earning',
            source='contract',
            quantity=1,
            rate=contract.basic_salary,
            amount=contract.basic_salary,
            order=1
        )
        
        # بنود الراتب الإضافية من الموظف
        # ملاحظة: هنا كنا نستبعد البنود التي effective_from = NULL
        # عن طريق الشرط (effective_from__lte)، وده كان بيخلي بعض البنود
        # النشطة لا تدخل في قسيمة الراتب المتكاملة رغم ظهورها في
        # صفحة بنود الراتب. لذلك نستخدم منطق شبيه بـ
        # SalaryComponentService.get_active_components:
        #   - is_active = True
        #   - (effective_from IS NULL OR effective_from <= month)
        #   - (effective_to IS NULL OR effective_to >= month)
        # Compare against last day of the payroll month so components that start
        # mid-month are still included in that month's payroll.
        import calendar
        from hr.utils.payroll_helpers import get_payroll_period
        _, last_day, _ = get_payroll_period(payroll.month)
        salary_components = contract.employee.salary_components.filter(
            is_active=True
        ).filter(
            Q(effective_from__isnull=True) | Q(effective_from__lte=last_day)
        ).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gte=payroll.month)
        )
        
        order = 10
        for component in salary_components:
            if component.is_basic:
                # الأجر الأساسي تم إضافته كسطر مستقل بالأعلى
                continue
            
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
        
        # خصم الغياب - استخدام snapshot من ملخص الحضور
        if attendance_summary.absence_deduction_amount > 0:
            # محاولة استخدام الـ snapshot المحفوظ في calculation_details
            absence_snapshot = None
            if attendance_summary.calculation_details:
                absence_snapshot = attendance_summary.calculation_details.get('absence_snapshot')
            
            # إزالة الأصفار غير الضرورية وتجنب التنسيق العلمي
            def format_decimal(d):
                try:
                    d = Decimal(str(d))
                    if d == d.to_integral_value():
                        return str(d.to_integral_value())
                    s = str(d.normalize())
                    return s if 'E' not in s else f"{d:f}"
                except:
                    return str(d)
            
            # استخدام الـ snapshot لو موجود
            if absence_snapshot:
                absent_days = absence_snapshot.get('absent_days', attendance_summary.absent_days)
                daily_salary_str = format_decimal(absence_snapshot.get('daily_salary', '0'))
                
                # تجميع الأيام حسب المعامل من الـ snapshot
                multiplier_groups = {}
                for detail in absence_snapshot.get('details', []):
                    multiplier = Decimal(detail['multiplier'])
                    if multiplier not in multiplier_groups:
                        multiplier_groups[multiplier] = 0
                    multiplier_groups[multiplier] += 1
                
                # بناء النص
                calc_parts = []
                for multiplier in sorted(multiplier_groups.keys()):
                    days_count = multiplier_groups[multiplier]
                    multiplier_str = format_decimal(multiplier)
                    calc_parts.append(f'({days_count} يوم × {daily_salary_str} × {multiplier_str})')
                
                calc_text = ' + '.join(calc_parts)
                
                # استخدام البيانات من الـ snapshot
                calculation_details = {
                    'source': 'attendance_summary_snapshot',
                    'attendance_summary_id': attendance_summary.id,
                    'snapshot_used': True,
                    'absent_days': absent_days,
                    'daily_salary': daily_salary_str,
                    'calculation': calc_text,
                    'details': absence_snapshot.get('details', [])
                }
            else:
                # Fallback: استخدام الطريقة القديمة لو الـ snapshot مش موجود
                logger.warning(
                    f"⚠️ لا يوجد snapshot لخصم الغياب في ملخص الحضور {attendance_summary.id} "
                    f"- استخدام البيانات الحالية (قد تكون معدلة)"
                )
                
                from hr.utils.payroll_helpers import get_payroll_period
                _, period_end, _ = get_payroll_period(attendance_summary.month)
                contract = attendance_summary.employee.contracts.filter(
                    status='active',
                    start_date__lte=period_end
                ).filter(
                    Q(end_date__isnull=True) | Q(end_date__gte=attendance_summary.month)
                ).order_by('-start_date').first()
                daily_salary = (contract.basic_salary / Decimal('30')).quantize(Decimal('0.01')) if contract else Decimal('0')
                daily_salary_str = format_decimal(daily_salary)
                
                absent_days = attendance_summary.absent_days
                calc_text = f'{absent_days} يوم × {daily_salary_str}'
                
                calculation_details = {
                    'source': 'attendance_summary_fallback',
                    'attendance_summary_id': attendance_summary.id,
                    'snapshot_used': False,
                    'absent_days': absent_days,
                    'daily_salary': str(daily_salary),
                    'calculation': calc_text
                }
            
            # إنشاء بند الخصم
            name = f'خصم غياب ({absent_days} يوم)'
            
            PayrollLine.objects.create(
                payroll=payroll,
                code='ABSENCE_DEDUCTION',
                name=name,
                component_type='deduction',
                source='attendance',
                quantity=absent_days,
                rate=attendance_summary.absence_deduction_amount / absent_days if absent_days > 0 else 0,
                amount=attendance_summary.absence_deduction_amount,
                description=f'خصم {absent_days} يوم غياب',
                calculation_details=calculation_details,
                order=order
            )
            order += 1
        
        # خصم التأخير - استخدام snapshot من ملخص الحضور
        if attendance_summary.late_deduction_amount > 0:
            # محاولة استخدام الـ snapshot المحفوظ في calculation_details
            late_snapshot = None
            if attendance_summary.calculation_details:
                late_snapshot = attendance_summary.calculation_details.get('late_deduction_snapshot')
            
            # إزالة الأصفار غير الضرورية وتجنب التنسيق العلمي
            def format_decimal(d):
                try:
                    d = Decimal(str(d))
                    if d == d.to_integral_value():
                        return str(d.to_integral_value())
                    s = str(d.normalize())
                    return s if 'E' not in s else f"{d:f}"
                except:
                    return str(d)
            
            # استخدام الـ snapshot لو موجود
            if late_snapshot:
                penalty_name = late_snapshot.get('penalty_name', 'جزاء تأخير')
                penalty_days = late_snapshot.get('penalty_days', '0')
                net_minutes = late_snapshot.get('net_penalizable_minutes', attendance_summary.net_penalizable_minutes)
                
                calc_text = f"جزاء: {penalty_name} ({format_decimal(penalty_days)} يوم)"
                
                calculation_details = {
                    'source': 'attendance_summary_snapshot',
                    'snapshot_used': True,
                    'net_penalizable_minutes': net_minutes,
                    'penalty_name': penalty_name,
                    'penalty_days': penalty_days,
                    'calculation': calc_text
                }
            else:
                # Fallback: استخدام الطريقة القديمة لو الـ snapshot مش موجود
                logger.warning(
                    f"⚠️ لا يوجد snapshot لخصم التأخير في ملخص الحضور {attendance_summary.id} "
                    f"- استخدام البيانات الحالية (قد تكون معدلة)"
                )
                
                from hr.models import AttendancePenalty
                penalty = AttendancePenalty.objects.filter(
                    is_active=True,
                    max_minutes__gte=attendance_summary.net_penalizable_minutes
                ).order_by('max_minutes').first()
                
                if not penalty:
                    penalty = AttendancePenalty.objects.filter(is_active=True, max_minutes=0).first()
                
                calc_text = f"جزاء: {penalty.name} ({format_decimal(penalty.penalty_days)} يوم)" if penalty else ""
                
                calculation_details = {
                    'source': 'attendance_summary_fallback',
                    'snapshot_used': False,
                    'net_penalizable_minutes': attendance_summary.net_penalizable_minutes,
                    'calculation': calc_text
                }
            
            PayrollLine.objects.create(
                payroll=payroll,
                code='LATE_DEDUCTION',
                name=f'خصم تأخير ({attendance_summary.net_penalizable_minutes} دقيقة)',
                component_type='deduction',
                source='attendance',
                quantity=1,
                rate=attendance_summary.late_deduction_amount,
                amount=attendance_summary.late_deduction_amount,
                description=f'خصم {attendance_summary.net_penalizable_minutes} دقيقة تأخير',
                calculation_details=calculation_details,
                order=order
            )
            order += 1

        # الأذونات الإضافية
        if hasattr(attendance_summary, 'extra_permissions_deduction_amount') and attendance_summary.extra_permissions_deduction_amount > 0:
            from hr.services.permission_quota_service import PermissionQuotaService
            from hr.utils.payroll_helpers import get_payroll_period
            
            # الحصول على العقد النشط للشهر (مع دعم الدورة المرنة)
            _, period_end, _ = get_payroll_period(attendance_summary.month)
            _contract = attendance_summary.employee.contracts.filter(
                status='active',
                start_date__lte=period_end
            ).filter(
                Q(end_date__isnull=True) | Q(end_date__gte=attendance_summary.month)
            ).order_by('-start_date').first()
            
            result = PermissionQuotaService.calculate_extra_permission_deduction(
                employee=payroll.employee,
                month=payroll.month,
                basic_salary=_contract.basic_salary if _contract else Decimal('0'),
                worked_days=attendance_summary.total_working_days
            )

            if result['total_deduction'] > 0:
                PayrollLine.objects.create(
                    payroll=payroll,
                    code='EXTRA_PERM_DEDUCTION',
                    name='خصم: أذونات إضافية',
                    component_type='deduction',
                    source='permission',
                    amount=result['total_deduction'],
                    calculation_details={
                        'permissions': [
                            {'id': p['id'], 'date': p['date'].isoformat(), 
                             'hours': str(p['hours']), 'amount': str(p['amount'])}
                            for p in result['permissions']
                        ],
                        'hourly_rate': str(result['hourly_rate']),
                        'worked_days': result['worked_days']
                    },
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
                rate=attendance_summary.overtime_amount / Decimal(str(attendance_summary.total_overtime_hours)) if attendance_summary.total_overtime_hours > 0 else 0,
                amount=attendance_summary.overtime_amount,
                description=f'{attendance_summary.total_overtime_hours} ساعة عمل إضافي',
                order=order
            )
    
    @staticmethod
    def _add_leave_components(payroll, leave_summary):
        """إضافة بنود الإجازات مع ربط كل بند بالإجازة المصدر"""
        from ..models import Leave
        order = 200
        
        # خصم الإجازات غير المدفوعة - بند منفصل لكل إجازة
        if leave_summary.deduction_amount > 0 and leave_summary.details:
            for detail in leave_summary.details:
                if not detail.get('is_paid', True):  # إجازة غير مدفوعة
                    leave_id = detail.get('leave_id')
                    days = detail.get('days_in_month', 0)
                    multiplier = Decimal(detail.get('deduction_multiplier', '1.0'))
                    
                    # حساب المبلغ لهذه الإجازة (مع دعم الدورة المرنة)
                    from hr.utils.payroll_helpers import get_payroll_period
                    _, period_end, _ = get_payroll_period(payroll.month)
                    contract = payroll.employee.contracts.filter(
                        status='active',
                        start_date__lte=period_end
                    ).filter(
                        Q(end_date__isnull=True) | Q(end_date__gte=payroll.month)
                    ).order_by('-start_date').first()
                    if contract and days > 0:
                        daily_salary = (Decimal(str(contract.basic_salary)) / Decimal('30')).quantize(
                            Decimal('0.01'),
                            rounding=ROUND_HALF_UP
                        )
                        amount = (Decimal(str(days)) * daily_salary * multiplier).quantize(
                            Decimal('0.01'),
                            rounding=ROUND_HALF_UP
                        )
                        
                        # جلب الإجازة للربط
                        leave_record = None
                        if leave_id:
                            try:
                                leave_record = Leave.objects.get(id=leave_id)
                            except Leave.DoesNotExist:
                                pass
                        
                        PayrollLine.objects.create(
                            payroll=payroll,
                            code='UNPAID_LEAVE_DEDUCTION',
                            name=f'خصم إجازة: {detail.get("leave_type", "غير مدفوعة")}',
                            component_type='deduction',
                            source='leave',
                            leave_record=leave_record,  # ✅ ربط البند بالإجازة
                            quantity=days,
                            rate=daily_salary * multiplier,
                            amount=amount,
                            description=f'خصم {days} يوم من {detail.get("start_date")} إلى {detail.get("end_date")}',
                            calculation_details={
                                'leave_id': leave_id,
                                'leave_type': detail.get('leave_type'),
                                'start_date': detail.get('start_date'),
                                'end_date': detail.get('end_date'),
                                'days_in_month': days,
                                'deduction_multiplier': str(multiplier),
                                'daily_salary': str(daily_salary),
                                'calculation': f'{days} يوم × {daily_salary} × {multiplier}'
                            },
                            order=order
                        )
                        order += 1
    
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
    def _add_penalty_reward_components(payroll, employee, month):
        """تطبيق الجزاءات والمكافآت المعتمدة على قسيمة الراتب"""
        from hr.services.penalty_reward_service import PenaltyRewardService

        approved_items = PenaltyRewardService.get_approved_for_month(employee, month)
        for pr in approved_items:
            try:
                PenaltyRewardService.apply_to_payroll(pr, payroll)
            except Exception as e:
                logger.warning(f"تعذر تطبيق جزاء/مكافأة {pr.id}: {e}")

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
            employees = Employee.objects.filter(status='active', is_insurance_only=False)
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
        
        
        return results

