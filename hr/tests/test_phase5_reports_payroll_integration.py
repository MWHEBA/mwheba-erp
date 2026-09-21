"""
Automated unit & integration test suite for Phase 5:
- Overtime review & override (approved_overtime_hours & overtime_override_reason)
- Automatic draft payroll invalidation (is_stale flag) and recalculation
- Enhanced attendance Excel export with source, location, offline sync, and overtime
- Monthly attendance summary Excel export
- Guard on approved/paid payroll modifications
"""
import pytest
from datetime import date, time, datetime, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.urls import reverse
from hr.models import (
    Employee, Department, JobTitle, Shift, Contract,
    Attendance, AttendanceSummary, Payroll, BiometricLog, WorkLocation
)
from hr.reports import export_attendance_excel, export_attendance_summary_excel
from hr.views.attendance_views import override_attendance_summary_overtime, attendance_summary_list

User = get_user_model()


@pytest.fixture
def hr_setup(db):
    user = User.objects.create_superuser(
        username='hr_admin_p5',
        password='password123',
        email='hr_p5@test.com'
    )
    dept = Department.objects.create(name_ar='تقنية المعلومات', is_active=True)
    job = JobTitle.objects.create(title_ar='مهندس برمجيات', department=dept)
    loc = WorkLocation.objects.create(
        name_ar='المقر الرئيسي',
        latitude=Decimal('30.044420'),
        longitude=Decimal('31.235712'),
        radius_meters=150,
        is_active=True
    )
    shift = Shift.objects.create(
        name='وردية الصباح 9-5',
        start_time=time(9, 0),
        end_time=time(17, 0),
        grace_period_in=15,
        grace_period_out=15
    )
    emp = Employee.objects.create(
        user=user,
        name='أحمد ممدوح عبد الرحمن',
        employee_number='EMP-P5-001',
        national_id='29501011234567',
        birth_date=date(1995, 1, 1),
        gender='male',
        marital_status='single',
        created_by=user,
        department=dept,
        job_title=job,
        shift=shift,
        work_location=loc,
        status='active',
        hire_date=date(2026, 1, 1)
    )
    contract = Contract.objects.create(
        employee=emp,
        basic_salary=Decimal('6000.00'),
        start_date=date(2026, 1, 1),
        created_by=user,
        status='active'
    )
    return {
        'user': user,
        'department': dept,
        'job': job,
        'location': loc,
        'shift': shift,
        'employee': emp,
        'contract': contract
    }


@pytest.mark.django_db
class TestPhase5ReportsAndPayrollIntegration:

    def test_approved_overtime_hours_override(self, hr_setup):
        """اختبار تعديل واعتماد ساعات الإضافي يدوياً وتأثيرها على الحساب المالي للملخص"""
        emp = hr_setup['employee']
        month_date = date(2026, 9, 1)

        summary = AttendanceSummary.objects.create(
            employee=emp,
            month=month_date,
            total_working_days=22,
            present_days=22,
            total_overtime_hours=Decimal('10.00'),
            is_calculated=True
        )
        summary._calculate_financial_amounts()
        summary.save()

        # المبلغ المحسوب بناءً على 10 ساعات
        initial_ot_amount = summary.overtime_amount
        assert initial_ot_amount > Decimal('0')

        # تعديل الساعات المعتمدة يدوياً إلى 15 ساعة مع سبب التعديل
        summary.approved_overtime_hours = Decimal('15.00')
        summary.overtime_override_reason = 'اعتماد ساعات إضافية لإنهاء تسليم المشروع'
        summary._calculate_financial_amounts()
        summary.save()

        # المبلغ الجديد يجب أن يكون أكبر
        assert summary.overtime_amount > initial_ot_amount
        assert summary.approved_overtime_hours == Decimal('15.00')
        assert summary.overtime_override_reason == 'اعتماد ساعات إضافية لإنهاء تسليم المشروع'

        # إعادة التعيين (حذف التعديل اليدوي)
        summary.approved_overtime_hours = None
        summary._calculate_financial_amounts()
        summary.save()
        assert summary.overtime_amount == initial_ot_amount

    def test_override_overtime_view_and_payroll_stale_invalidation(self, hr_setup):
        """اختبار endpoint تعديل ساعات الإضافي ووسم مسودة الراتب كـ is_stale"""
        emp = hr_setup['employee']
        user = hr_setup['user']
        month_date = date(2026, 9, 1)

        summary = AttendanceSummary.objects.create(
            employee=emp,
            month=month_date,
            total_working_days=22,
            present_days=22,
            total_overtime_hours=Decimal('5.00'),
            is_calculated=True
        )

        # مسودة راتب مفتوحة
        payroll = Payroll.objects.create(
            employee=emp,
            month=month_date,
            contract=hr_setup['contract'],
            basic_salary=Decimal('6000.00'),
            gross_salary=Decimal('6000.00'),
            net_salary=Decimal('6000.00'),
            processed_by=user,
            status='calculated',
            is_stale=False
        )

        from django.contrib.messages.storage.cookie import CookieStorage
        factory = RequestFactory()
        request = factory.post(
            f'/hr/attendance/summaries/{summary.id}/override-overtime/',
            data={
                'approved_overtime_hours': '8.5',
                'overtime_override_reason': 'عمل إضافي معتمد من مدير الإدارة'
            }
        )
        request.user = user
        setattr(request, '_messages', CookieStorage(request))

        response = override_attendance_summary_overtime(request, pk=summary.id)
        assert response.status_code == 302

        summary.refresh_from_db()
        assert summary.approved_overtime_hours == Decimal('8.5')
        assert summary.overtime_override_reason == 'عمل إضافي معتمد من مدير الإدارة'

        # التحقق من وسم مسودة الراتب كـ is_stale
        payroll.refresh_from_db()
        assert payroll.is_stale is True

    def test_override_overtime_blocked_on_paid_payroll(self, hr_setup):
        """حظر تعديل ساعات الإضافي بعد دفع أو اعتماد الراتب نهائياً"""
        emp = hr_setup['employee']
        user = hr_setup['user']
        month_date = date(2026, 9, 1)

        summary = AttendanceSummary.objects.create(
            employee=emp,
            month=month_date,
            total_working_days=22,
            present_days=22,
            total_overtime_hours=Decimal('5.00'),
            is_calculated=True
        )

        # راتب مدفوع نهائياً
        Payroll.objects.create(
            employee=emp,
            month=month_date,
            contract=hr_setup['contract'],
            basic_salary=Decimal('6000.00'),
            gross_salary=Decimal('6000.00'),
            net_salary=Decimal('6000.00'),
            processed_by=user,
            status='paid',
            is_stale=False
        )

        factory = RequestFactory()
        request = factory.post(
            f'/hr/attendance/summaries/{summary.id}/override-overtime/',
            data={'approved_overtime_hours': '12.0'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        request.user = user

        response = override_attendance_summary_overtime(request, pk=summary.id)
        assert response.status_code == 400

        summary.refresh_from_db()
        assert summary.approved_overtime_hours is None

    def test_export_attendance_excel_comprehensive(self, hr_setup):
        """اختبار تصدير سجلات الحضور اليومية الشاملة إلى ملف Excel"""
        emp = hr_setup['employee']
        loc = hr_setup['location']
        shift = hr_setup['shift']

        att1 = Attendance.objects.create(
            employee=emp,
            date=date(2026, 9, 1),
            shift=shift,
            check_in=datetime(2026, 9, 1, 9, 0),
            check_out=datetime(2026, 9, 1, 18, 30),
            work_hours=Decimal('9.50'),
            overtime_hours=Decimal('1.50'),
            late_minutes=0,
            status='present'
        )
        # حركة بصمة هاتف مرتبطة
        BiometricLog.objects.create(
            attendance=att1,
            employee=emp,
            user_id=emp.employee_number,
            timestamp=datetime(2026, 9, 1, 9, 0),
            log_type='check_in',
            source='mobile',
            matched_location=loc,
            is_offline_synced=True
        )

        attendances = Attendance.objects.filter(employee=emp, date=date(2026, 9, 1))
        response = export_attendance_excel(attendances, date(2026, 9, 1))

        assert response.status_code == 200
        assert response['Content-Type'] == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        assert 'attendance_report_2026-09.xlsx' in response['Content-Disposition']
        assert len(response.content) > 1000

    def test_export_attendance_summary_excel_and_view(self, hr_setup):
        """اختبار تصدير ملخص الحضور الشهري الشامل عبر الدالة وعبر الـ View"""
        emp = hr_setup['employee']
        user = hr_setup['user']
        month_date = date(2026, 9, 1)

        summary = AttendanceSummary.objects.create(
            employee=emp,
            month=month_date,
            total_working_days=22,
            present_days=21,
            absent_days=1,
            half_days=0,
            total_work_hours=Decimal('168.00'),
            total_overtime_hours=Decimal('8.00'),
            approved_overtime_hours=Decimal('10.00'),
            overtime_amount=Decimal('450.00'),
            net_penalizable_minutes=30,
            late_deduction_amount=Decimal('100.00'),
            absence_deduction_amount=Decimal('200.00'),
            is_calculated=True,
            is_approved=True,
            overtime_override_reason='إضافي تسليم مشاريع'
        )

        # 1. اختبار الدالة المباشرة
        summaries = AttendanceSummary.objects.filter(id=summary.id)
        response_direct = export_attendance_summary_excel(summaries, month_date)
        assert response_direct.status_code == 200
        assert 'attendance_summary_2026-09.xlsx' in response_direct['Content-Disposition']

        # 2. اختبار عبر View مع ?export=excel
        factory = RequestFactory()
        request = factory.get(f'/hr/attendance/summaries/?month=2026-09&export=excel')
        request.user = user

        response_view = attendance_summary_list(request)
        assert response_view.status_code == 200
        assert response_view['Content-Type'] == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        assert len(response_view.content) > 1000
