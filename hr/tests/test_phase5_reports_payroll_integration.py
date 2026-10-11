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
from django.utils import timezone
from hr.models import (
    Employee, Department, JobTitle, Shift, Contract,
    Attendance, AttendanceSummary, Payroll, BiometricLog, WorkLocation, BiometricDevice
)
from hr.reports import export_attendance_excel, export_attendance_summary_excel
from hr.views.attendance_views import override_attendance_summary_overtime, attendance_summary_list
from hr.services.attendance_service import AttendanceService
from hr.utils.biometric_utils import bulk_process_logs

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

    def test_early_field_mission_hours_not_truncated(self, hr_setup):
        """عدم اقتطاع ساعات العمل للمأموريات الميدانية الصباحية المبكرة قبل بداية الوردية"""
        emp = hr_setup['employee']
        shift = hr_setup['shift'] # وردية 9:00 إلى 17:00
        target_date = date(2026, 9, 2) # يوم عمل عادي (الأربعاء)

        # الموظف يبدأ مأمورية الساعة 07:00 ص وينصرف 17:00 (10 ساعات كاملة)
        check_in_ts = timezone.make_aware(datetime.combine(target_date, time(7, 0)))
        check_out_ts = timezone.make_aware(datetime.combine(target_date, time(17, 0)))

        att = Attendance.objects.create(
            employee=emp,
            date=target_date,
            shift=shift,
            check_in=check_in_ts,
            check_out=check_out_ts,
            is_field_visit=True,
            location_name='موقع محطة الكهرباء'
        )
        AttendanceService.calculate_daily_attendance(att)
        att.save()

        # التأكد من احتساب 10.00 ساعات كاملة دون بترها بحد الـ 9:00 ص
        assert float(att.work_hours) == 10.0

    def test_morning_field_mission_late_waiver(self, hr_setup):
        """إعفاء الموظف من التأخير الصباحي عند بدء يومه بمأمورية ميدانية معتمدة"""
        emp = hr_setup['employee']
        shift = hr_setup['shift'] # وردية 9:00
        target_date = date(2026, 9, 3)

        # وصول للموقع الميداني الساعة 10:30 ص
        check_in_ts = timezone.make_aware(datetime.combine(target_date, time(10, 30)))
        att = Attendance.objects.create(
            employee=emp,
            date=target_date,
            shift=shift,
            check_in=check_in_ts,
            is_field_visit=True,
            source='field_visit',
            location_name='زيارة ميدانية لشركة النور'
        )
        AttendanceService.calculate_daily_attendance(att)
        att.save()

        # التأكد من تصفير دقائق التأخير واعتبار الحالة حاضر
        assert att.late_minutes == 0
        assert att.status == 'present'

    def test_afternoon_field_mission_preserves_morning_office_lateness(self, hr_setup):
        """منع استغلال الزيارات الميدانية المسائية لمحو التأخير الصباحي في مقر الفرع"""
        emp = hr_setup['employee']
        shift = hr_setup['shift'] # وردية 9:00 سماح 15 دقيقة
        target_date = date(2026, 9, 4)

        # 1. حضور متأخر للفرع الساعة 10:15 ص (تأخير 75 دقيقة - 15 سماح = 60 دقيقة صافي)
        check_in_ts = timezone.make_aware(datetime.combine(target_date, time(10, 15)))
        att = Attendance.objects.create(
            employee=emp,
            date=target_date,
            shift=shift,
            check_in=check_in_ts,
            source='device',
            location_name='المقر الرئيسي'
        )
        # تسجيل حركة ماكينة الحضور الصباحي
        BiometricLog.objects.create(
            employee=emp,
            user_id=emp.employee_number,
            timestamp=check_in_ts,
            log_type='check_in',
            source='device',
            attendance=att
        )

        # 2. مأمورية بعد الظهر
        att.is_field_visit = True
        BiometricLog.objects.create(
            employee=emp,
            user_id=emp.employee_number,
            timestamp=timezone.make_aware(datetime.combine(target_date, time(14, 0))),
            log_type='check_in',
            source='field_visit',
            device_info={'is_field_visit': True, 'reason': 'اجتماع عميل'},
            attendance=att
        )

        AttendanceService.calculate_daily_attendance(att)
        att.save()

        # التأخير الصباحي في الفرع يظل ثابتاً ولا يُمحى
        assert att.late_minutes > 0
        assert att.status == 'late'

    def test_field_mission_not_converted_to_half_day(self, hr_setup):
        """منع تحويل المأموريات الميدانية المعتمدة قسرياً إلى جزاء نصف يوم"""
        emp = hr_setup['employee']
        shift = hr_setup['shift'] # وردية 8 ساعات (حد النصف يوم 4 ساعات)
        target_date = date(2026, 9, 7)

        # مأمورية ميدانية لمدة 3 ساعات (أقل من نصف الوردية)
        check_in_ts = timezone.make_aware(datetime.combine(target_date, time(9, 0)))
        check_out_ts = timezone.make_aware(datetime.combine(target_date, time(12, 0)))

        att = Attendance.objects.create(
            employee=emp,
            date=target_date,
            shift=shift,
            check_in=check_in_ts,
            check_out=check_out_ts,
            is_field_visit=True,
            source='field_visit',
            location_name='معاينة فنية سريعة'
        )
        AttendanceService.calculate_daily_attendance(att)
        att.save()

        assert float(att.work_hours) == 3.0
        assert att.status == 'present' # لم يتم تحويلها إلى half_day

    def test_bulk_process_logs_preserves_mobile_checkout_and_field_info(self, hr_setup):
        """تحصين bulk_process_logs من مسح انصراف الموبايل وبيانات المأموريات وتفادي AttributeError"""
        emp = hr_setup['employee']
        shift = hr_setup['shift']
        target_date = date(2026, 9, 8)

        # بصمة حضور بالماكينة صباحاً
        ts_in = timezone.make_aware(datetime.combine(target_date, time(9, 0)))
        device = BiometricDevice.objects.create(
            device_name='ماكينة الحائط الرئيسية',
            device_code='BIO-DEV-TEST-01',
            serial_number='SN-BIO-12345',
            device_type='fingerprint',
            ip_address='192.168.1.200',
            location='المقر الرئيسي',
            created_by=hr_setup['user'],
            is_active=True
        )
        log_in = BiometricLog.objects.create(
            employee=emp,
            user_id=emp.employee_number,
            device=device,
            timestamp=ts_in,
            log_type='check_in',
            source='device'
        )

        # سجل حضور تم فيه توثيق انصراف بالموبايل لاحقاً الساعة 17:00
        ts_out_mobile = timezone.make_aware(datetime.combine(target_date, time(17, 0)))
        att = Attendance.objects.create(
            employee=emp,
            date=target_date,
            shift=shift,
            check_in=ts_in,
            check_out=ts_out_mobile,
            source='mobile',
            is_field_visit=True,
            location_name='مأمورية معتمدة'
        )

        # تشغيل bulk_process_logs لمعالجة سجل الماكينة (الذي ليس به انصراف)
        stats = bulk_process_logs(date=target_date, employee_id=emp.id)
        assert stats['processed'] == 1

        att.refresh_from_db()
        # التأكد من عدم تصفير بصمة الانصراف
        assert att.check_out == ts_out_mobile
        # التأكد من الحفاظ على وسم المأمورية
        assert att.is_field_visit is True

    def test_attendance_summary_preserves_friday_work_and_overtime(self, hr_setup):
        """شمول عمل الجمع والعطلات في كشف المرتبات الشهري وعدم إهداره"""
        emp = hr_setup['employee']
        shift = hr_setup['shift']

        # يوم جمعة 2026-09-04
        friday_date = date(2026, 9, 4)
        assert friday_date.weekday() == 4 # Friday

        check_in_ts = timezone.make_aware(datetime.combine(friday_date, time(9, 0)))
        check_out_ts = timezone.make_aware(datetime.combine(friday_date, time(17, 0)))

        att_friday = Attendance.objects.create(
            employee=emp,
            date=friday_date,
            shift=shift,
            check_in=check_in_ts,
            check_out=check_out_ts,
        )
        AttendanceService.calculate_daily_attendance(att_friday)
        att_friday.save()
        assert float(att_friday.overtime_hours) == 8.0

        # حساب ملخص الحضور لشهر 9
        summary, _ = AttendanceSummary.objects.get_or_create(
            employee=emp,
            month=date(2026, 9, 1)
        )
        summary.calculate()
        summary.refresh_from_db()

        # التأكد من شمول عمل الجمعة في الإضافي وساعات العمل وأيام الحضور
        assert float(summary.total_overtime_hours) >= 8.0
        assert float(summary.total_work_hours) >= 8.0
        assert summary.present_days >= 1

    def test_attendance_summary_respects_field_visit_late_waiver(self, hr_setup):
        """احترام إعفاء المأموريات في كشف المرتبات وتصفير الدقائق القابلة للجزاء"""
        emp = hr_setup['employee']
        shift = hr_setup['shift']
        target_date = date(2026, 9, 9)

        # مأمورية ميدانية صباحية
        check_in_ts = timezone.make_aware(datetime.combine(target_date, time(10, 0)))
        check_out_ts = timezone.make_aware(datetime.combine(target_date, time(17, 0)))

        att = Attendance.objects.create(
            employee=emp,
            date=target_date,
            shift=shift,
            check_in=check_in_ts,
            check_out=check_out_ts,
            is_field_visit=True,
            source='field_visit'
        )
        AttendanceService.calculate_daily_attendance(att)
        att.save()

        summary, _ = AttendanceSummary.objects.get_or_create(
            employee=emp,
            month=date(2026, 9, 1)
        )
        summary.calculate()
        summary.refresh_from_db()

        # التأكد من عدم فرض أي دقائق جزاء على يوم المأمورية
        assert summary.net_penalizable_minutes == 0

