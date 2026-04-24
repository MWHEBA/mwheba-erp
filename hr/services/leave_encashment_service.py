"""
خدمة تحويل رصيد الإجازات المتبقي لمقابل مالي
"""
from decimal import Decimal
from datetime import date
from django.db import transaction
from ..models import LeaveBalance, LeaveType


class LeaveEncashmentService:
    """
    تحويل رصيد الإجازات المتبقي لمقابل مالي يُضاف للمرتب.

    الشروط:
    - leave_encashment_enabled = True في SystemSetting
    - LeaveType.allow_encashment = True للنوع المراد تحويله
    - الموظف عنده عقد ساري

    معادلة الراتب اليومي (نفس المعادلة في payroll_service.py):
        daily_rate = basic_salary / 30
    """

    @staticmethod
    def calculate_encashment_preview(employee, year):
        """
        حساب قيمة التحويل المتوقعة بدون تنفيذ.
        مفيد لعرض المعاينة قبل التأكيد.

        Args:
            employee: نموذج الموظف
            year: السنة

        Returns:
            dict: {
                'can_encash': bool,
                'reason': str,
                'total_amount': Decimal,
                'daily_rate': Decimal,
                'details': list of dicts,
            }
        """
        from core.models import SystemSetting

        if not SystemSetting.get_setting('leave_encashment_enabled', False):
            return {
                'can_encash': False,
                'reason': 'تحويل الإجازات لمقابل مالي غير مفعل في إعدادات النظام',
                'total_amount': Decimal('0'),
                'daily_rate': Decimal('0'),
                'details': [],
            }

        contract = employee.get_active_contract()
        if not contract:
            return {
                'can_encash': False,
                'reason': 'لا يوجد عقد ساري للموظف',
                'total_amount': Decimal('0'),
                'daily_rate': Decimal('0'),
                'details': [],
            }

        daily_rate = (contract.basic_salary / Decimal('30')).quantize(Decimal('0.01'))

        encashable_balances = LeaveBalance.objects.filter(
            employee=employee,
            leave_type__allow_encashment=True,
            year=year,
            remaining_days__gt=0
        ).select_related('leave_type')

        total_amount = Decimal('0')
        details = []

        for balance in encashable_balances:
            amount = Decimal(balance.remaining_days) * daily_rate
            total_amount += amount
            details.append({
                'leave_type':     balance.leave_type.name_ar,
                'remaining_days': balance.remaining_days,
                'daily_rate':     daily_rate,
                'amount':         amount,
            })

        return {
            'can_encash':   True,
            'reason':       '',
            'total_amount': total_amount,
            'daily_rate':   daily_rate,
            'details':      details,
        }

    @staticmethod
    @transaction.atomic
    def process_encashment(employee, year, processed_by, encashment_month=None):
        """
        تنفيذ تحويل رصيد الإجازات لمقابل مالي.

        الخطوات:
        1. التحقق من الشروط
        2. حساب المبلغ لكل نوع إجازة يسمح بالتحويل
        3. تصفير remaining_days وتحديث used_days
        4. تسجيل العملية في LeaveEncashmentLog
        5. إرجاع البيانات

        Args:
            employee: نموذج الموظف
            year: السنة
            processed_by: المستخدم الذي نفّذ العملية
            encashment_month: أول يوم من شهر الإضافة (اختياري — يُحدَّث لاحقاً في inject_into_payroll)

        Returns:
            dict: {
                'total_amount': Decimal,
                'daily_rate': Decimal,
                'details': list,
                'log': LeaveEncashmentLog instance,
            }

        Raises:
            ValueError: إذا لم تتحقق الشروط
        """
        from core.models import SystemSetting
        from ..models import LeaveEncashmentLog

        if not SystemSetting.get_setting('leave_encashment_enabled', False):
            raise ValueError('تحويل الإجازات لمقابل مالي غير مفعل في إعدادات النظام')

        contract = employee.get_active_contract()
        if not contract:
            raise ValueError('لا يوجد عقد ساري للموظف')

        daily_rate = (contract.basic_salary / Decimal('30')).quantize(Decimal('0.01'))

        encashable_balances = LeaveBalance.objects.select_for_update().filter(
            employee=employee,
            leave_type__allow_encashment=True,
            year=year,
            remaining_days__gt=0
        ).select_related('leave_type')

        if not encashable_balances.exists():
            raise ValueError(f'لا توجد أيام إجازة قابلة للتحويل للموظف {employee.name} في سنة {year}')

        total_amount = Decimal('0')
        details = []

        for balance in encashable_balances:
            days   = balance.remaining_days
            amount = Decimal(days) * daily_rate
            total_amount += amount

            details.append({
                'leave_type':    balance.leave_type.name_ar,
                'leave_type_id': balance.leave_type.id,
                'days':          days,
                'daily_rate':    str(daily_rate),
                'amount':        str(amount),
            })

            # تصفير الرصيد
            balance.used_days      += days
            balance.remaining_days  = 0
            balance.save()

        # تسجيل في Audit Trail
        log = LeaveEncashmentLog.objects.create(
            employee=employee,
            year=year,
            encashment_month=encashment_month or date.today().replace(day=1),
            total_days=sum(d['days'] for d in details),
            daily_rate=daily_rate,
            total_amount=total_amount,
            processed_by=processed_by,
            details=details,
        )

        return {
            'total_amount': total_amount,
            'daily_rate':   daily_rate,
            'details':      details,
            'log':          log,
        }

    @staticmethod
    @transaction.atomic
    def inject_into_payroll(employee, year, encashment_month, processed_by):
        """
        الدالة الرئيسية: تنفذ الـ encashment وتضيفه كـ PayrollLine على الراتب المستهدف.

        الـ workflow الصح:
        1. احسب الراتب (status=calculated)
        2. نفّذ inject_into_payroll
        3. اعتمد الراتب
        4. ادفع

        Args:
            employee: نموذج الموظف
            year: سنة الإجازات (LeaveBalance.year)
            encashment_month: أول يوم من الشهر المستهدف (مثال: date(2026, 8, 1))
            processed_by: المستخدم المنفِّذ

        Returns:
            dict: نتيجة process_encashment + 'payroll'

        Raises:
            ValueError: لو الراتب مش موجود أو في حالة approved/paid
        """
        from ..models import Payroll, PayrollLine

        # 1. التحقق من الراتب المستهدف قبل تصفير الأرصدة
        payroll = Payroll.objects.filter(
            employee=employee,
            month=encashment_month
        ).first()

        if not payroll:
            raise ValueError(
                f'لا يوجد راتب للموظف {employee.name} في شهر '
                f'{encashment_month.strftime("%Y-%m")} — يجب حساب الراتب أولاً'
            )

        if payroll.status in ('approved', 'paid'):
            raise ValueError(
                f'راتب {encashment_month.strftime("%Y-%m")} في حالة '
                f'"{payroll.get_status_display()}" — '
                f'يجب إعادته لحالة "محسوب" قبل إضافة مقابل الإجازات'
            )

        # 2. تنفيذ الـ encashment وتصفير الأرصدة
        result = LeaveEncashmentService.process_encashment(
            employee, year, processed_by, encashment_month=encashment_month
        )

        if result['total_amount'] == 0:
            return {**result, 'payroll': payroll}

        # 3. إضافة PayrollLine
        PayrollLine.objects.create(
            payroll=payroll,
            code='LEAVE_ENCASH',
            name=f'مقابل إجازات غير مستخدمة — {year}',
            component_type='earning',
            source='leave',
            amount=result['total_amount'],
            calculation_details={
                'year':        year,
                'total_days':  sum(d['days'] for d in result['details']),
                'daily_rate':  str(result['daily_rate']),
                'details':     result['details'],
            },
            order=150,
        )

        # 4. إعادة حساب الإجماليات
        payroll.calculate_totals_from_lines()
        payroll.save()

        # 5. ربط الـ log بالـ payroll
        result['log'].payroll = payroll
        result['log'].encashment_month = encashment_month
        result['log'].save(update_fields=['payroll', 'encashment_month'])

        return {**result, 'payroll': payroll}
