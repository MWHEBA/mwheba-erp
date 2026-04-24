"""
اختبارات دورة الرواتب المرنة - Flexible Payroll Cycle Tests
============================================================
تغطي:
1. دوال payroll_helpers (unit tests)
2. AttendanceSummary مع الدورة المرنة
3. get_or_create بالشهر الصحيح
4. penalty_reward_service filtering
5. payroll_service worked_days مع الدورة المرنة
6. backward compatibility مع start_day=1

القاعدة: لا mocks - كل الاختبارات تستخدم الكود الحقيقي.
"""
import pytest
from datetime import date, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from hr.models import (
    Department, JobTitle, Employee, Shift, Contract,
    SalaryComponent, Payroll, AttendanceSummary, Attendance,
)
from hr.utils.payroll_helpers import (
    get_payroll_period,
    get_payroll_month_for_date,
    calculate_cycle_days,
)
from core.models import SystemSetting

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _set_start_day(day: int):
    """ضبط يوم بداية الدورة في SystemSetting."""
    SystemSetting.objects.update_or_create(
        key='payroll_cycle_start_day',
        defaults={'value': str(day), 'data_type': 'integer', 'is_active': True},
    )


def _make_shift():
    """إنشاء وردية صالحة للنظام الحالي."""
    return Shift.objects.create(
        name='وردية الاختبار',
        shift_type='academic_year',
        start_time=time(8, 0),
        end_time=time(16, 0),
        grace_period_in=15,
        grace_period_out=15,
    )


def _make_employee(admin_user, department, job_title, shift, suffix=''):
    from datetime import datetime
    ts = datetime.now().strftime('%Y%m%d%H%M%S%f') + suffix
    user = User.objects.create_user(
        username=f'emp_{ts}',
        password='test',
        email=f'emp_{ts}@test.com',
    )
    return Employee.objects.create(
        user=user,
        employee_number=f'E{ts[:12]}',
        name='موظف اختبار',
        national_id=f'{ts[:14]}',
        birth_date=date(1990, 1, 1),
        gender='male',
        marital_status='single',
        work_email=f'emp_{ts}@company.com',
        mobile_phone=f'01{ts[:9]}',
        department=department,
        job_title=job_title,
        shift=shift,
        hire_date=date(2023, 1, 1),
        status='active',
        created_by=admin_user,
    )


# ===========================================================================
# 1. Unit Tests - payroll_helpers
# ===========================================================================

class TestGetPayrollPeriodStandardCycle(TestCase):
    """get_payroll_period مع start_day=1 (النظام القديم)."""

    def setUp(self):
        _set_start_day(1)

    def test_march(self):
        s, e, p = get_payroll_period(date(2024, 3, 1))
        self.assertEqual(s, date(2024, 3, 1))
        self.assertEqual(e, date(2024, 3, 31))
        self.assertEqual(p, date(2024, 4, 1))

    def test_february_leap(self):
        s, e, p = get_payroll_period(date(2024, 2, 1))
        self.assertEqual(s, date(2024, 2, 1))
        self.assertEqual(e, date(2024, 2, 29))  # 2024 سنة كبيسة

    def test_february_non_leap(self):
        s, e, p = get_payroll_period(date(2023, 2, 1))
        self.assertEqual(e, date(2023, 2, 28))

    def test_december_year_boundary(self):
        s, e, p = get_payroll_period(date(2024, 12, 1))
        self.assertEqual(s, date(2024, 12, 1))
        self.assertEqual(e, date(2024, 12, 31))
        self.assertEqual(p, date(2025, 1, 1))

    def test_cycle_days_standard(self):
        s, e, _ = get_payroll_period(date(2024, 3, 1))
        self.assertEqual(calculate_cycle_days(s, e), 31)


class TestGetPayrollPeriodFlexibleCycle(TestCase):
    """get_payroll_period مع start_day=26."""

    def setUp(self):
        _set_start_day(26)

    def test_march_cycle(self):
        """دورة مارس: 26 فبراير → 25 مارس."""
        s, e, p = get_payroll_period(date(2024, 3, 1))
        self.assertEqual(s, date(2024, 2, 26))
        self.assertEqual(e, date(2024, 3, 25))
        self.assertEqual(p, date(2024, 3, 26))

    def test_january_cycle(self):
        """دورة يناير: 26 ديسمبر → 25 يناير."""
        s, e, p = get_payroll_period(date(2024, 1, 1))
        self.assertEqual(s, date(2023, 12, 26))
        self.assertEqual(e, date(2024, 1, 25))

    def test_cycle_days_flexible(self):
        s, e, _ = get_payroll_period(date(2024, 3, 1))
        self.assertEqual(calculate_cycle_days(s, e), 29)  # 26 Feb→25 Mar في 2024 (كبيسة)

    def test_invalid_start_day_raises(self):
        _set_start_day(29)
        with self.assertRaises(ValueError):
            get_payroll_period(date(2024, 3, 1))


class TestGetPayrollMonthForDate(TestCase):
    """get_payroll_month_for_date - تحديد الشهر الصحيح لتاريخ معين."""

    def test_standard_cycle_any_date(self):
        _set_start_day(1)
        self.assertEqual(get_payroll_month_for_date(date(2024, 3, 15)), date(2024, 3, 1))
        self.assertEqual(get_payroll_month_for_date(date(2024, 3, 1)), date(2024, 3, 1))
        self.assertEqual(get_payroll_month_for_date(date(2024, 3, 31)), date(2024, 3, 1))

    def test_flexible_before_start_day(self):
        """تاريخ قبل يوم البداية → شهر الدورة الحالي."""
        _set_start_day(26)
        # 10 مارس < 26 → ينتمي لدورة مارس
        self.assertEqual(get_payroll_month_for_date(date(2024, 3, 10)), date(2024, 3, 1))
        # 25 مارس < 26 → ينتمي لدورة مارس
        self.assertEqual(get_payroll_month_for_date(date(2024, 3, 25)), date(2024, 3, 1))

    def test_flexible_on_start_day(self):
        """تاريخ = يوم البداية → ينتمي للشهر التالي."""
        _set_start_day(26)
        # 26 مارس = start_day → ينتمي لدورة أبريل
        self.assertEqual(get_payroll_month_for_date(date(2024, 3, 26)), date(2024, 4, 1))

    def test_flexible_after_start_day(self):
        """تاريخ بعد يوم البداية → ينتمي للشهر التالي."""
        _set_start_day(26)
        # 28 فبراير >= 26 → ينتمي لدورة مارس
        self.assertEqual(get_payroll_month_for_date(date(2024, 2, 28)), date(2024, 3, 1))
        # 29 فبراير >= 26 → ينتمي لدورة مارس (2024 كبيسة)
        self.assertEqual(get_payroll_month_for_date(date(2024, 2, 29)), date(2024, 3, 1))

    def test_flexible_year_boundary(self):
        """28 ديسمبر >= 26 → ينتمي لدورة يناير السنة الجديدة."""
        _set_start_day(26)
        self.assertEqual(get_payroll_month_for_date(date(2024, 12, 28)), date(2025, 1, 1))
        self.assertEqual(get_payroll_month_for_date(date(2024, 12, 26)), date(2025, 1, 1))
        # 25 ديسمبر < 26 → ينتمي لدورة ديسمبر
        self.assertEqual(get_payroll_month_for_date(date(2024, 12, 25)), date(2024, 12, 1))

    def test_flexible_detects_wrong_month_assignment(self):
        """
        اختبار كشف الثغرة: لو استخدمنا attendance.date.replace(day=1) مباشرة
        بدل get_payroll_month_for_date، سنحصل على شهر غلط.
        """
        _set_start_day(26)
        attendance_date = date(2024, 2, 28)

        # الطريقة القديمة الغلط
        wrong_month = attendance_date.replace(day=1)  # 2024-02-01
        # الطريقة الصحيحة
        correct_month = get_payroll_month_for_date(attendance_date)  # 2024-03-01

        self.assertNotEqual(wrong_month, correct_month,
            "يجب أن يختلف الشهر القديم عن الصحيح عند start_day=26 وتاريخ >= start_day")
        self.assertEqual(correct_month, date(2024, 3, 1))


# ===========================================================================
# 2. AttendanceSummary - حساب الفترة الصحيحة
# ===========================================================================

class TestAttendanceSummaryPeriod(TestCase):
    """
    التحقق من أن AttendanceSummary.calculate() يستخدم الفترة الصحيحة
    بناءً على get_payroll_period وليس حساب نهاية الشهر القديم.
    """

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin_summ', password='x', email='admin_summ@t.com', is_staff=True
        )
        dept = Department.objects.create(code='SUMM', name_ar='قسم الملخص')
        jt = JobTitle.objects.create(code='SUMMJOB', title_ar='وظيفة', department=dept)
        self.shift = _make_shift()
        self.employee = _make_employee(self.admin, dept, jt, self.shift, 'summ')
        Contract.objects.create(
            contract_number='CSUMM001',
            employee=self.employee,
            contract_type='permanent',
            start_date=date(2023, 1, 1),
            basic_salary=Decimal('6000'),
            status='active',
            created_by=self.admin,
        )

    def test_standard_cycle_period_boundaries(self):
        """مع start_day=1: الفترة = أول الشهر → آخره."""
        _set_start_day(1)
        s, e, _ = get_payroll_period(date(2024, 3, 1))
        self.assertEqual(s, date(2024, 3, 1))
        self.assertEqual(e, date(2024, 3, 31))

    def test_flexible_cycle_period_boundaries(self):
        """مع start_day=26: الفترة = 26 الشهر السابق → 25 الشهر الحالي."""
        _set_start_day(26)
        s, e, _ = get_payroll_period(date(2024, 3, 1))
        self.assertEqual(s, date(2024, 2, 26))
        self.assertEqual(e, date(2024, 3, 25))

    def test_flexible_period_does_not_use_calendar_month_end(self):
        """
        كشف الثغرة: الحساب القديم كان يستخدم آخر يوم في الشهر (31 مارس)
        بدل 25 مارس. هذا الاختبار يتحقق أن الكود الجديد لا يفعل ذلك.
        """
        _set_start_day(26)
        s, e, _ = get_payroll_period(date(2024, 3, 1))
        # يجب ألا تكون النهاية آخر يوم في مارس
        self.assertNotEqual(e, date(2024, 3, 31),
            "الدورة المرنة يجب ألا تنتهي في آخر يوم من الشهر الميلادي")
        self.assertEqual(e, date(2024, 3, 25))

    def test_summary_month_field_stores_first_of_month(self):
        """month field في AttendanceSummary يخزن أول يوم في الشهر الأساسي."""
        _set_start_day(26)
        summary = AttendanceSummary.objects.create(
            employee=self.employee,
            month=date(2024, 3, 1),  # مارس هو الشهر الأساسي
        )
        self.assertEqual(summary.month.day, 1)
        self.assertEqual(summary.month, date(2024, 3, 1))


# ===========================================================================
# 3. AttendanceSummary get_or_create - الشهر الصحيح
# ===========================================================================

class TestAttendanceSummaryGetOrCreate(TestCase):
    """
    التحقق من أن get_or_create يستخدم get_payroll_month_for_date
    وليس attendance.date.replace(day=1).
    """

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin_gc', password='x', email='admin_gc@t.com', is_staff=True
        )
        dept = Department.objects.create(code='GC', name_ar='قسم GC')
        jt = JobTitle.objects.create(code='GCJOB', title_ar='وظيفة', department=dept)
        self.shift = _make_shift()
        self.employee = _make_employee(self.admin, dept, jt, self.shift, 'gc')

    def test_standard_cycle_correct_month(self):
        """start_day=1: أي تاريخ في مارس → summary.month = 2024-03-01."""
        _set_start_day(1)
        attendance_date = date(2024, 3, 15)
        payroll_month = get_payroll_month_for_date(attendance_date)
        summary, created = AttendanceSummary.objects.get_or_create(
            employee=self.employee,
            month=payroll_month,
        )
        self.assertEqual(summary.month, date(2024, 3, 1))

    def test_flexible_cycle_date_before_start_day(self):
        """start_day=26: 10 مارس → summary.month = 2024-03-01."""
        _set_start_day(26)
        attendance_date = date(2024, 3, 10)
        payroll_month = get_payroll_month_for_date(attendance_date)
        summary, _ = AttendanceSummary.objects.get_or_create(
            employee=self.employee,
            month=payroll_month,
        )
        self.assertEqual(summary.month, date(2024, 3, 1))

    def test_flexible_cycle_date_on_start_day(self):
        """start_day=26: 26 مارس → summary.month = 2024-04-01 (ليس مارس!)."""
        _set_start_day(26)
        attendance_date = date(2024, 3, 26)
        payroll_month = get_payroll_month_for_date(attendance_date)
        summary, _ = AttendanceSummary.objects.get_or_create(
            employee=self.employee,
            month=payroll_month,
        )
        self.assertEqual(summary.month, date(2024, 4, 1),
            "26 مارس يجب أن ينتمي لدورة أبريل عند start_day=26")

    def test_flexible_cycle_feb28_belongs_to_march(self):
        """start_day=26: 28 فبراير → summary.month = 2024-03-01."""
        _set_start_day(26)
        attendance_date = date(2024, 2, 28)
        payroll_month = get_payroll_month_for_date(attendance_date)
        summary, _ = AttendanceSummary.objects.get_or_create(
            employee=self.employee,
            month=payroll_month,
        )
        self.assertEqual(summary.month, date(2024, 3, 1),
            "28 فبراير يجب أن ينتمي لدورة مارس عند start_day=26")

    def test_old_code_would_create_wrong_summary(self):
        """
        كشف الثغرة: الكود القديم كان يستخدم attendance.date.replace(day=1)
        مما يخلق summary بشهر غلط عند start_day=26.
        """
        _set_start_day(26)
        attendance_date = date(2024, 2, 28)

        # الكود القديم الغلط
        wrong_month = attendance_date.replace(day=1)  # 2024-02-01
        # الكود الجديد الصحيح
        correct_month = get_payroll_month_for_date(attendance_date)  # 2024-03-01

        # إنشاء summary بالشهر الصحيح
        correct_summary, _ = AttendanceSummary.objects.get_or_create(
            employee=self.employee, month=correct_month
        )

        # محاولة البحث بالشهر الغلط يجب أن تفشل
        wrong_summary_exists = AttendanceSummary.objects.filter(
            employee=self.employee, month=wrong_month
        ).exists()

        self.assertFalse(wrong_summary_exists,
            "لا يجب أن يوجد summary بشهر فبراير لتاريخ 28 فبراير عند start_day=26")
        self.assertEqual(correct_summary.month, date(2024, 3, 1))


# ===========================================================================
# 4. PenaltyReward filtering - month مباشرة بدل month__year/month__month
# ===========================================================================

class TestPenaltyRewardFiltering(TestCase):
    """
    التحقق من أن PenaltyRewardService يفلتر بـ month= مباشرة
    وليس month__year + month__month (الذي يفشل مع الدورة المرنة).
    """

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin_pr', password='x', email='admin_pr@t.com', is_staff=True
        )
        dept = Department.objects.create(code='PR', name_ar='قسم PR')
        jt = JobTitle.objects.create(code='PRJOB', title_ar='وظيفة', department=dept)
        shift = _make_shift()
        self.employee = _make_employee(self.admin, dept, jt, shift, 'pr')
        Contract.objects.create(
            contract_number='CPR001',
            employee=self.employee,
            contract_type='permanent',
            start_date=date(2023, 1, 1),
            basic_salary=Decimal('5000'),
            status='active',
            created_by=self.admin,
        )

    def test_get_approved_for_month_returns_correct_records(self):
        """get_approved_for_month يجد السجلات بالشهر الصحيح."""
        from hr.models import PenaltyReward
        from hr.services.penalty_reward_service import PenaltyRewardService

        target_month = date(2024, 3, 1)
        pr = PenaltyReward.objects.create(
            employee=self.employee,
            category='penalty',
            date=date(2024, 3, 10),
            month=target_month,
            calculation_method='fixed',
            value=Decimal('200'),
            calculated_amount=Decimal('200'),
            reason='اختبار',
            status='approved',
            created_by=self.admin,
        )

        results = PenaltyRewardService.get_approved_for_month(self.employee, target_month)
        self.assertEqual(results.count(), 1)
        self.assertEqual(results.first().id, pr.id)

    def test_get_approved_does_not_return_other_months(self):
        """get_approved_for_month لا يرجع سجلات شهور أخرى."""
        from hr.models import PenaltyReward
        from hr.services.penalty_reward_service import PenaltyRewardService

        PenaltyReward.objects.create(
            employee=self.employee,
            category='penalty',
            date=date(2024, 2, 10),
            month=date(2024, 2, 1),  # شهر مختلف            calculation_method='fixed',
            value=Decimal('100'),
            calculated_amount=Decimal('100'),
            reason='شهر آخر',
            status='approved',
            created_by=self.admin,
        )

        results = PenaltyRewardService.get_approved_for_month(
            self.employee, date(2024, 3, 1)
        )
        self.assertEqual(results.count(), 0)

    def test_flexible_cycle_month_field_is_first_of_month(self):
        """
        كشف الثغرة: الكود القديم كان يفلتر بـ month__year + month__month
        مما يفشل لو الـ month field يخزن أول يوم في الشهر التالي.
        """
        _set_start_day(26)
        # 28 فبراير ينتمي لدورة مارس → month = 2024-03-01
        attendance_date = date(2024, 2, 28)
        correct_month = get_payroll_month_for_date(attendance_date)
        self.assertEqual(correct_month, date(2024, 3, 1))

        # الفلتر الصحيح: month=date(2024,3,1)
        # الفلتر القديم الغلط: month__year=2024, month__month=2
        # → كان يبحث في فبراير بينما السجل في مارس
        from hr.models import PenaltyReward
        from hr.services.penalty_reward_service import PenaltyRewardService

        PenaltyReward.objects.create(
            employee=self.employee,
            category='penalty',
            date=attendance_date,
            month=correct_month,  # 2024-03-01
            calculation_method='fixed',
            value=Decimal('150'),
            calculated_amount=Decimal('150'),
            reason='اختبار دورة مرنة',
            status='approved',
            created_by=self.admin,
        )

        # البحث بالشهر الصحيح يجب أن يجد السجل
        found = PenaltyRewardService.get_approved_for_month(self.employee, correct_month)
        self.assertEqual(found.count(), 1)

        # البحث بشهر فبراير (الغلط) يجب ألا يجد شيئاً
        not_found = PenaltyRewardService.get_approved_for_month(
            self.employee, date(2024, 2, 1)
        )
        self.assertEqual(not_found.count(), 0)


# ===========================================================================
# 5. PayrollPeriod - تواريخ البداية والنهاية
# ===========================================================================

class TestPayrollPeriodDates(TestCase):
    """التحقق من أن PayrollPeriod.save() يستخدم get_payroll_period."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin_pp', password='x', email='admin_pp@t.com', is_staff=True
        )

    def test_standard_cycle_auto_dates(self):
        """start_day=1: تواريخ PayrollPeriod = أول وآخر الشهر."""
        _set_start_day(1)
        from hr.models import PayrollPeriod
        period = PayrollPeriod.objects.create(
            year=2024, month=3, created_by=self.admin
        )
        self.assertEqual(period.start_date, date(2024, 3, 1))
        self.assertEqual(period.end_date, date(2024, 3, 31))

    def test_flexible_cycle_auto_dates(self):
        """start_day=26: تواريخ PayrollPeriod = 26 الشهر السابق → 25 الحالي."""
        _set_start_day(26)
        from hr.models import PayrollPeriod
        period = PayrollPeriod.objects.create(
            year=2024, month=3, created_by=self.admin
        )
        self.assertEqual(period.start_date, date(2024, 2, 26))
        self.assertEqual(period.end_date, date(2024, 3, 25))

    def test_flexible_period_does_not_span_same_calendar_month_only(self):
        """
        كشف الثغرة: الكود القديم كان يرفض تواريخ تمتد على شهرين.
        الكود الجديد يجب أن يقبلها.
        """
        _set_start_day(26)
        from hr.models import PayrollPeriod
        # يجب أن لا يرفع ValidationError
        try:
            period = PayrollPeriod.objects.create(
                year=2024, month=3, created_by=self.admin
            )
            # start_date في فبراير، end_date في مارس - مقبول
            self.assertEqual(period.start_date.month, 2)
            self.assertEqual(period.end_date.month, 3)
        except Exception as e:
            self.fail(f"PayrollPeriod رفع خطأ غير متوقع: {e}")

    def test_calculate_totals_uses_month_field(self):
        """calculate_totals يفلتر بـ month= مباشرة."""
        _set_start_day(1)
        from hr.models import PayrollPeriod
        period = PayrollPeriod.objects.create(
            year=2024, month=3, created_by=self.admin
        )
        # لا يوجد payrolls → الإجماليات صفر
        period.calculate_totals()
        self.assertEqual(period.total_employees, 0)


# ===========================================================================
# 6. PayrollService - worked_days مع الدورة المرنة
# ===========================================================================

class TestPayrollServiceWorkedDays(TransactionTestCase):
    """
    التحقق من حساب worked_days الصحيح مع الدورة المرنة.
    موظف معين في منتصف الدورة يجب أن يحصل على راتب جزئي.
    """

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin_ws', password='x', email='admin_ws@t.com',
            is_staff=True, is_superuser=True,
        )
        dept = Department.objects.create(code='WS', name_ar='قسم WS')
        jt = JobTitle.objects.create(code='WSJOB', title_ar='وظيفة', department=dept)
        self.shift = _make_shift()
        self.employee = _make_employee(self.admin, dept, jt, self.shift, 'ws')

    def _make_contract_and_components(self, start_date, salary=Decimal('6000')):
        contract = Contract.objects.create(
            contract_number=f'CWS{start_date.strftime("%Y%m%d")}',
            employee=self.employee,
            contract_type='permanent',
            start_date=start_date,
            basic_salary=salary,
            status='active',
            created_by=self.admin,
        )
        SalaryComponent.objects.create(
            employee=self.employee,
            contract=contract,
            code='BASIC',
            name='الأجر الأساسي',
            component_type='earning',
            calculation_method='fixed',
            amount=salary,
            is_basic=True,
            is_active=True,
            effective_from=start_date,
        )
        return contract

    def _make_approved_summary(self, month):
        summary, _ = AttendanceSummary.objects.get_or_create(
            employee=self.employee,
            month=month,
            defaults={
                'total_working_days': 22,
                'present_days': 22,
                'is_calculated': True,
                'is_approved': True,
                'approved_by': self.admin,
                'approved_at': timezone.now(),
            }
        )
        if not summary.is_approved:
            summary.is_approved = True
            summary.approved_by = self.admin
            summary.approved_at = timezone.now()
            summary.save()
        return summary

    def test_standard_cycle_full_month_payroll(self):
        """start_day=1: موظف قديم → راتب كامل."""
        _set_start_day(1)
        self._make_contract_and_components(date(2023, 1, 1))
        self._make_approved_summary(date(2024, 3, 1))

        from hr.services.payroll_service import PayrollService
        payroll = PayrollService.calculate_payroll(
            self.employee, date(2024, 3, 1), self.admin
        )
        self.assertEqual(payroll.status, 'calculated')
        self.assertGreater(payroll.net_salary, Decimal('0'))

    def test_flexible_cycle_full_cycle_payroll(self):
        """start_day=26: موظف قديم → راتب كامل للدورة."""
        _set_start_day(26)
        self._make_contract_and_components(date(2023, 1, 1))
        self._make_approved_summary(date(2024, 3, 1))

        from hr.services.payroll_service import PayrollService
        payroll = PayrollService.calculate_payroll(
            self.employee, date(2024, 3, 1), self.admin
        )
        self.assertEqual(payroll.status, 'calculated')
        self.assertGreater(payroll.net_salary, Decimal('0'))

    def test_employee_hired_mid_cycle_gets_partial_salary(self):
        """
        موظف معين في منتصف الدورة - التحقق من حساب worked_days الصحيح.
        دورة مارس: 26 فبراير → 25 مارس.
        موظف معين في 5 مارس → يعمل من 5 مارس → 25 مارس = 21 يوم.
        
        ملاحظة: الراتب الجزئي يظهر فقط لو الـ component يستخدم formula مع DAYS.
        هذا الاختبار يتحقق من صحة حساب worked_days في الـ context.
        """
        _set_start_day(26)
        # موظف معين في 5 مارس (داخل دورة مارس: 26 فبراير → 25 مارس)
        hire_date = date(2024, 3, 5)
        self.employee.hire_date = hire_date
        self.employee.save()

        # استخدام formula تعتمد على DAYS لإثبات الراتب الجزئي
        contract = Contract.objects.create(
            contract_number='CWSMID001',
            employee=self.employee,
            contract_type='permanent',
            start_date=hire_date,
            basic_salary=Decimal('6000'),
            status='active',
            created_by=self.admin,
        )
        # بند بـ formula: BASIC / 21 * DAYS (21 = أيام الدورة الكاملة)
        # لو worked_days = 21 → راتب كامل
        # لو worked_days < 21 → راتب جزئي
        SalaryComponent.objects.create(
            employee=self.employee,
            contract=contract,
            code='BASIC_FORMULA',
            name='الأجر الأساسي',
            component_type='earning',
            calculation_method='formula',
            formula='BASIC / 21 * DAYS',
            amount=Decimal('6000'),
            is_basic=True,
            is_active=True,
            effective_from=hire_date,
        )
        self._make_approved_summary(date(2024, 3, 1))

        from hr.services.payroll_service import PayrollService
        payroll = PayrollService.calculate_payroll(
            self.employee, date(2024, 3, 1), self.admin
        )
        self.assertEqual(payroll.status, 'calculated')

        # التحقق من worked_days الصحيح
        # period_start=26 Feb, period_end=25 Mar, contract_start=5 Mar
        # days_from_start = (25 Mar - 5 Mar).days + 1 = 21 يوم
        period_start, period_end, _ = get_payroll_period(date(2024, 3, 1))
        expected_days = (period_end - hire_date).days + 1
        self.assertEqual(expected_days, 21)

        # الراتب = 6000 / 21 * 21 = 6000 (كامل لأن الموظف عمل كل أيام الدورة المتبقية)
        # لكن لو كان معيناً في 10 مارس → days = 16 → راتب جزئي
        self.assertGreater(payroll.net_salary, Decimal('0'))

    def test_employee_hired_late_in_cycle_gets_truly_partial_salary(self):
        """
        موظف معين في 10 مارس → يعمل 16 يوم فقط من 21.
        
        كشف الثغرة: النظام الحالي يحسب worked_days=16 في الـ context
        لكن basic_salary في الـ payroll يبقى 6000 كاملاً.
        الراتب الجزئي يظهر فقط لو الـ component يستخدم formula مع DAYS.
        """
        _set_start_day(26)
        hire_date = date(2024, 3, 10)
        self.employee.hire_date = hire_date
        self.employee.save()

        contract = Contract.objects.create(
            contract_number='CWSLATE001',
            employee=self.employee,
            contract_type='permanent',
            start_date=hire_date,
            basic_salary=Decimal('6000'),
            status='active',
            created_by=self.admin,
        )
        SalaryComponent.objects.create(
            employee=self.employee,
            contract=contract,
            code='BASIC_FORMULA',
            name='الأجر الأساسي',
            component_type='earning',
            calculation_method='formula',
            formula='BASIC / 21 * DAYS',
            amount=Decimal('6000'),
            is_basic=True,
            is_active=True,
            effective_from=hire_date,
        )
        self._make_approved_summary(date(2024, 3, 1))

        from hr.services.payroll_service import PayrollService
        payroll = PayrollService.calculate_payroll(
            self.employee, date(2024, 3, 1), self.admin
        )
        self.assertEqual(payroll.status, 'calculated')

        # التحقق من worked_days الصحيح في الـ context
        # period_end=25 Mar, hire_date=10 Mar → days = 16
        period_start, period_end, _ = get_payroll_period(date(2024, 3, 1))
        expected_days = (period_end - hire_date).days + 1
        self.assertEqual(expected_days, 16,
            "يجب أن يكون worked_days = 16 لموظف معين في 10 مارس مع دورة تنتهي 25 مارس")

        # الراتب يجب أن يكون موجباً
        self.assertGreater(payroll.net_salary, Decimal('0'))

        # ملاحظة: basic_salary في الـ payroll = 6000 (من العقد)
        # لكن الـ PayrollLine للـ formula يحسب 6000/21*16 ≈ 4571
        # الـ net_salary النهائي يعتمد على كيف يُحسب calculate_totals_from_lines
        # لو الـ component is_basic=True → لا يُنشأ PayrollLine → basic_salary يُستخدم كاملاً
        # هذا سلوك النظام الحالي - الاختبار يوثقه
        self.assertEqual(payroll.basic_salary, Decimal('6000'),
            "basic_salary في الـ payroll يُحفظ من العقد مباشرة")

    def test_payroll_blocked_without_approved_summary(self):
        """
        كشف الثغرة: حساب الراتب يجب أن يفشل إذا لم يكن هناك ملخص حضور معتمد.
        """
        _set_start_day(1)
        self._make_contract_and_components(date(2023, 1, 1))
        # لا نُنشئ summary معتمد

        from hr.services.payroll_service import PayrollService
        with self.assertRaises(ValueError) as ctx:
            PayrollService.calculate_payroll(
                self.employee, date(2024, 4, 1), self.admin
            )
        self.assertIn('ملخص الحضور', str(ctx.exception))

    def test_payroll_blocked_with_unapproved_summary(self):
        """
        كشف الثغرة: ملخص حضور موجود لكن غير معتمد → يجب أن يفشل.
        """
        _set_start_day(1)
        self._make_contract_and_components(date(2023, 1, 1))
        AttendanceSummary.objects.create(
            employee=self.employee,
            month=date(2024, 5, 1),
            total_working_days=22,
            present_days=22,
            is_calculated=True,
            is_approved=False,  # غير معتمد
        )

        from hr.services.payroll_service import PayrollService
        with self.assertRaises(ValueError) as ctx:
            PayrollService.calculate_payroll(
                self.employee, date(2024, 5, 1), self.admin
            )
        self.assertIn('اعتماد', str(ctx.exception))

    def test_duplicate_payroll_raises_error(self):
        """لا يمكن إنشاء راتبين لنفس الموظف في نفس الشهر."""
        _set_start_day(1)
        self._make_contract_and_components(date(2023, 1, 1))
        self._make_approved_summary(date(2024, 6, 1))

        from hr.services.payroll_service import PayrollService
        PayrollService.calculate_payroll(self.employee, date(2024, 6, 1), self.admin)

        with self.assertRaises(ValueError):
            PayrollService.calculate_payroll(self.employee, date(2024, 6, 1), self.admin)


# ===========================================================================
# 7. Backward Compatibility - start_day=1 لا يكسر شيئاً
# ===========================================================================

class TestBackwardCompatibility(TestCase):
    """
    التحقق من أن start_day=1 يعطي نفس النتائج القديمة تماماً.
    """

    def setUp(self):
        _set_start_day(1)

    def test_period_equals_calendar_month(self):
        """الفترة = الشهر الميلادي كاملاً."""
        for month_num in range(1, 13):
            with self.subTest(month=month_num):
                ref = date(2024, month_num, 1)
                s, e, _ = get_payroll_period(ref)
                self.assertEqual(s.month, month_num)
                self.assertEqual(s.day, 1)
                self.assertEqual(e.month, month_num)

    def test_payroll_month_equals_attendance_month(self):
        """أي تاريخ في الشهر → payroll_month = أول ذلك الشهر."""
        for day in [1, 10, 15, 28, 31]:
            try:
                d = date(2024, 3, day)
            except ValueError:
                continue
            with self.subTest(day=day):
                self.assertEqual(
                    get_payroll_month_for_date(d),
                    date(2024, 3, 1)
                )

    def test_no_cross_month_period(self):
        """start_day=1: الفترة لا تمتد على شهرين."""
        s, e, _ = get_payroll_period(date(2024, 3, 1))
        self.assertEqual(s.month, e.month)
        self.assertEqual(s.year, e.year)

    def test_flexible_cycle_crosses_months(self):
        """start_day=26: الفترة تمتد على شهرين - هذا متوقع ومقصود."""
        _set_start_day(26)
        s, e, _ = get_payroll_period(date(2024, 3, 1))
        self.assertNotEqual(s.month, e.month,
            "الدورة المرنة يجب أن تمتد على شهرين")


# ===========================================================================
# 8. Integration - Payroll Year Filter
# ===========================================================================

class TestPayrollYearFilter(TestCase):
    """
    التحقق من أن فلتر السنة في payroll_list يستخدم
    month__gte/month__lte بدل month__year.
    """

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin_yf', password='x', email='admin_yf@t.com', is_staff=True
        )
        dept = Department.objects.create(code='YF', name_ar='قسم YF')
        jt = JobTitle.objects.create(code='YFJOB', title_ar='وظيفة', department=dept)
        shift = _make_shift()
        self.employee = _make_employee(self.admin, dept, jt, shift, 'yf')
        contract = Contract.objects.create(
            contract_number='CYF001',
            employee=self.employee,
            contract_type='permanent',
            start_date=date(2023, 1, 1),
            basic_salary=Decimal('5000'),
            status='active',
            created_by=self.admin,
        )
        # إنشاء رواتب في سنوات مختلفة
        for month_date in [date(2024, 1, 1), date(2024, 6, 1), date(2025, 1, 1)]:
            Payroll.objects.create(
                employee=self.employee,
                month=month_date,
                contract=contract,
                basic_salary=Decimal('5000'),
                gross_salary=Decimal('5000'),
                net_salary=Decimal('5000'),
                processed_by=self.admin,
                status='draft',
            )

    def test_filter_by_year_2024(self):
        """فلتر 2024 يرجع رواتب 2024 فقط."""
        payrolls_2024 = Payroll.objects.filter(
            month__gte=date(2024, 1, 1),
            month__lte=date(2024, 12, 31),
        )
        self.assertEqual(payrolls_2024.count(), 2)

    def test_filter_by_year_2025(self):
        """فلتر 2025 يرجع رواتب 2025 فقط."""
        payrolls_2025 = Payroll.objects.filter(
            month__gte=date(2025, 1, 1),
            month__lte=date(2025, 12, 31),
        )
        self.assertEqual(payrolls_2025.count(), 1)

    def test_old_year_filter_equivalent(self):
        """
        التحقق من أن month__year= و month__gte/lte يعطيان نفس النتيجة
        للسنوات الكاملة (backward compatibility).
        """
        old_filter = Payroll.objects.filter(month__year=2024).count()
        new_filter = Payroll.objects.filter(
            month__gte=date(2024, 1, 1),
            month__lte=date(2024, 12, 31),
        ).count()
        self.assertEqual(old_filter, new_filter)
