"""
خدمة الاستحقاق التدريجي للإجازات
"""
from django.db import transaction
from datetime import date
from dateutil.relativedelta import relativedelta
from ..models import Employee, LeaveBalance, LeaveType


class LeaveAccrualService:
    """خدمة حساب وتحديث الاستحقاق التدريجي للإجازات"""

    # =========================================================
    # الـ Single Source of Truth لحساب total_days
    # =========================================================

    @staticmethod
    def get_entitlement_for_employee(employee, leave_type):
        """
        يرجع عدد أيام الإجازة المستحقة لموظف محدد ونوع إجازة محدد.
        هذه هي الـ single source of truth — كل الأماكن تستدعيها.

        الأولوية:
        1. الإجازات الاستثنائية والغير مدفوعة → max_days_per_year ثابت
        2. كبار الموظفين (50 سنة أو 10 سنوات خدمة فعلية)
        3. أتم 12 شهر → رصيد كامل
        4. أتم leave_partial_after_months → رصيد جزئي
        5. أقل من الحد → صفر

        Args:
            employee: نموذج الموظف
            leave_type: نموذج نوع الإجازة

        Returns:
            int: عدد الأيام المستحقة
        """
        from core.models import SystemSetting

        # الإجازات الاستثنائية والمرضية والغير مدفوعة: لا رصيد لها — تُمنح بدون حد مسبق
        if not leave_type.requires_balance:
            return 0

        months_worked = LeaveAccrualService.calculate_months_worked(employee.hire_date)
        partial_after = int(SystemSetting.get_setting('leave_partial_after_months', 6))

        # كبار الموظفين — الأولوية الأعلى بعد الاستثنائية
        if LeaveAccrualService.is_senior_employee(employee):
            if leave_type.category == 'annual':
                return int(SystemSetting.get_setting('leave_senior_annual_days', 30))
            if leave_type.category == 'emergency':
                return int(SystemSetting.get_setting('leave_senior_emergency_days', 10))

        # إتمام السنة الكاملة (12 شهر)
        if months_worked >= 12:
            if leave_type.category == 'annual':
                return int(SystemSetting.get_setting('leave_annual_full_days', 21))
            if leave_type.category == 'emergency':
                return int(SystemSetting.get_setting('leave_emergency_full_days', 7))

        # المرحلة الجزئية
        if months_worked >= partial_after:
            if leave_type.category == 'annual':
                return int(SystemSetting.get_setting('leave_annual_partial_days', 7))
            if leave_type.category == 'emergency':
                return int(SystemSetting.get_setting('leave_emergency_partial_days', 3))

        # لم يستحق بعد
        return 0

    @staticmethod
    def is_senior_employee(employee):
        """
        الموظف كبير إذا:
        - أتم leave_senior_age_threshold سنة (افتراضي 50)، أو
        - أتم leave_senior_service_years سنة خدمة فعلية (افتراضي 10)

        يعتمد على employee.age و employee.years_of_service (بعد إصلاح المرحلة 0).

        Args:
            employee: نموذج الموظف

        Returns:
            bool
        """
        from core.models import SystemSetting

        age_threshold     = int(SystemSetting.get_setting('leave_senior_age_threshold', 50))
        service_threshold = int(SystemSetting.get_setting('leave_senior_service_years', 10))

        return employee.age >= age_threshold or employee.years_of_service >= service_threshold

    # =========================================================
    # دورة الإجازات — ربط بالسنة المالية
    # =========================================================

    @staticmethod
    def get_leave_cycle_dates():
        """
        يرجع (start_date, end_date) لدورة الإجازات الحالية.

        المرجع يُحدَّد من إعداد leave_year_reference:
        - 'financial_year': يستخدم السنة الميلادية الحالية

        Returns:
            tuple: (start_date, end_date)
        """
        from core.models import SystemSetting

        reference = SystemSetting.get_setting('leave_year_reference', 'financial_year')

        if reference == 'financial_year':
            pass

        # fallback: السنة الميلادية الحالية
        today = date.today()
        return date(today.year, 1, 1), date(today.year, 12, 31)

    @staticmethod
    def get_encashment_month():
        """
        يرجع أول يوم من شهر الـ encashment.

        المنطق: الشهر الأخير قبل بداية الدورة الجديدة.
        - financial_year → encashment_month = ديسمبر (12)

        Returns:
            date: أول يوم من شهر الـ encashment (مثال: date(2026, 12, 1))
        """
        from core.models import SystemSetting

        reference = SystemSetting.get_setting('leave_year_reference', 'financial_year')

        if reference == 'financial_year':
            pass

        # financial_year أو fallback: ديسمبر من السنة الحالية
        return date(date.today().year, 12, 1)

    @staticmethod
    def get_new_cycle_year():
        """
        يرجع السنة التي تبدأ فيها الدورة الجديدة.
        يُستخدم لإنشاء LeaveBalance للسنة الجديدة.

        - financial_year: دايماً السنة التالية

        Returns:
            int: رقم السنة
        """
        from core.models import SystemSetting

        reference = SystemSetting.get_setting('leave_year_reference', 'financial_year')

        if reference == 'financial_year':
            pass

        return date.today().year + 1

    # =========================================================
    # الدوال الموجودة — محدَّثة لاستخدام get_entitlement_for_employee
    # =========================================================

    @staticmethod
    def get_accrual_percentage(months_worked):
        """
        حساب نسبة الاستحقاق بناءً على أشهر العمل.
        محتفظ بها للتوافق مع الكود القديم.

        Args:
            months_worked: عدد الأشهر منذ التعيين

        Returns:
            float: نسبة الاستحقاق (0.0 إلى 1.0)
        """
        from core.models import SystemSetting

        probation_months  = SystemSetting.get_setting('leave_accrual_probation_months', 3)
        partial_percentage = SystemSetting.get_setting('leave_accrual_partial_percentage', 25)
        full_months       = SystemSetting.get_setting('leave_accrual_full_months', 6)

        if months_worked < probation_months:
            return 0.0
        elif months_worked < full_months:
            return partial_percentage / 100.0
        else:
            return 1.0

    @staticmethod
    def calculate_months_worked(hire_date, reference_date=None):
        """
        حساب عدد الأشهر الكاملة منذ التعيين.

        Args:
            hire_date: تاريخ التعيين
            reference_date: تاريخ المرجع (افتراضي: اليوم)

        Returns:
            int: عدد الأشهر
        """
        if reference_date is None:
            reference_date = date.today()

        delta = relativedelta(reference_date, hire_date)
        return delta.months + (delta.years * 12)

    @staticmethod
    def get_accrual_phase(employee, leave_type):
        """
        يرجع مرحلة الاستحقاق الحالية للموظف.
        يُستخدم لاكتشاف الترقي لمرحلة أعلى وتحديث الرصيد تلقائياً.

        Returns:
            str: 'none' | 'partial' | 'full' | 'senior'
        """
        from core.models import SystemSetting

        if not leave_type.requires_balance:
            return 'none'

        if LeaveAccrualService.is_senior_employee(employee):
            return 'senior'

        months_worked = LeaveAccrualService.calculate_months_worked(employee.hire_date)
        partial_after = int(SystemSetting.get_setting('leave_partial_after_months', 6))

        if months_worked >= 12:
            return 'full'
        if months_worked >= partial_after:
            return 'partial'
        return 'none'

    @staticmethod
    @transaction.atomic
    def update_employee_accrual(employee, year=None):
        """
        تحديث استحقاق إجازات موظف محدد.
        يستخدم get_entitlement_for_employee كـ single source of truth.
        يكتشف تغيير المرحلة (phase) ويرفع الرصيد تلقائياً حتى للأرصدة المعدلة يدوياً.

        Args:
            employee: الموظف
            year: السنة (افتراضي: السنة الحالية)

        Returns:
            dict: ملخص التحديثات
        """
        if year is None:
            year = date.today().year

        balances = LeaveBalance.objects.filter(
            employee=employee,
            year=year,
            leave_type__category__in=['annual', 'emergency']
        ).select_related('leave_type')

        updated_count = 0
        summary = []

        for balance in balances:
            new_phase = LeaveAccrualService.get_accrual_phase(employee, balance.leave_type)
            phase_changed = new_phase != balance.accrual_phase

            # لو الرصيد معدل يدوياً ولم تتغير المرحلة — لا تلمسه
            if balance.is_manually_adjusted and not phase_changed:
                continue

            old_total   = balance.total_days
            old_accrued = balance.accrued_days
            old_phase   = balance.accrual_phase

            new_total = LeaveAccrualService.get_entitlement_for_employee(
                employee, balance.leave_type
            )

            balance.total_days     = new_total
            balance.accrued_days   = new_total
            balance.remaining_days = max(0, new_total - balance.used_days)
            balance.accrual_phase  = new_phase
            balance.last_accrual_date = date.today()

            # لو كان معدل يدوياً وتغيرت المرحلة — نرفع الرصيد ونسجل السبب
            if balance.is_manually_adjusted and phase_changed:
                balance.adjustment_reason = (
                    f'[تحديث تلقائي] ترقي من مرحلة "{old_phase}" إلى "{new_phase}" — '
                    f'تم رفع الرصيد من {old_total} إلى {new_total} يوم'
                )
                balance.is_manually_adjusted = False  # أصبح محدثاً تلقائياً

            balance.save()

            if new_total != old_total or balance.accrued_days != old_accrued or phase_changed:
                updated_count += 1
                summary.append({
                    'leave_type':  balance.leave_type.name_ar,
                    'old_total':   old_total,
                    'new_total':   new_total,
                    'old_accrued': old_accrued,
                    'new_accrued': balance.accrued_days,
                    'remaining':   balance.remaining_days,
                    'old_phase':   old_phase,
                    'new_phase':   new_phase,
                    'phase_changed': phase_changed,
                })

        return {
            'employee':      employee.get_full_name_ar(),
            'updated_count': updated_count,
            'summary':       summary,
        }

    @staticmethod
    @transaction.atomic
    def update_all_accruals(year=None):
        """
        تحديث استحقاق جميع الموظفين النشطين.

        Args:
            year: السنة (افتراضي: السنة الحالية)

        Returns:
            dict: ملخص شامل للتحديثات
        """
        if year is None:
            year = date.today().year

        employees = Employee.objects.filter(status='active')
        total_updated    = 0
        employees_updated = []

        for employee in employees:
            result = LeaveAccrualService.update_employee_accrual(employee, year)
            if result['updated_count'] > 0:
                total_updated += result['updated_count']
                employees_updated.append(result)

        return {
            'year':                    year,
            'total_employees':         employees.count(),
            'employees_with_updates':  len(employees_updated),
            'total_balances_updated':  total_updated,
            'details':                 employees_updated,
        }

    @staticmethod
    def get_employee_accrual_status(employee, year=None):
        """
        الحصول على حالة استحقاق موظف مع وصف المرحلة الحالية.

        Args:
            employee: الموظف
            year: السنة (افتراضي: السنة الحالية)

        Returns:
            dict: معلومات الاستحقاق
        """
        if year is None:
            year = date.today().year

        from core.models import SystemSetting

        months_worked  = LeaveAccrualService.calculate_months_worked(employee.hire_date)
        partial_after  = int(SystemSetting.get_setting('leave_partial_after_months', 6))
        is_senior      = LeaveAccrualService.is_senior_employee(employee)

        balances = LeaveBalance.objects.filter(
            employee=employee,
            year=year,
            leave_type__category__in=['annual', 'emergency']
        ).select_related('leave_type')

        balances_info = []
        for balance in balances:
            entitlement = LeaveAccrualService.get_entitlement_for_employee(
                employee, balance.leave_type
            )
            balances_info.append({
                'leave_type':    balance.leave_type.name_ar,
                'category':      balance.leave_type.category,
                'total_days':    balance.total_days,
                'accrued_days':  balance.accrued_days,
                'used_days':     balance.used_days,
                'remaining_days': balance.remaining_days,
                'entitlement':   entitlement,
            })

        # تحديد المرحلة
        if is_senior:
            stage          = 'كبير موظفين — يستحق الرصيد الأعلى'
            next_milestone = 'لا يوجد — يستحق الحد الأقصى'
        elif months_worked >= 12:
            stage          = 'يستحق الرصيد الكامل'
            next_milestone = 'لا يوجد — يستحق الحد الأقصى'
        elif months_worked >= partial_after:
            stage          = 'يستحق الرصيد الجزئي'
            next_milestone = f'سيستحق الرصيد الكامل بعد {12 - months_worked} شهر'
        else:
            stage          = 'لم يستحق بعد'
            next_milestone = f'سيستحق الرصيد الجزئي بعد {partial_after - months_worked} شهر'

        return {
            'employee':      employee.get_full_name_ar(),
            'hire_date':     employee.hire_date,
            'months_worked': months_worked,
            'is_senior':     is_senior,
            'stage':         stage,
            'next_milestone': next_milestone,
            'balances':      balances_info,
        }
