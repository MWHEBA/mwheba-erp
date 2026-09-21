"""
Comprehensive Test Suite for Phase 1 Attendance & Overtime Engine
================================================================
Covers:
1. 3-Tier Biometric Matching, Timezone Compensation & Sliding Debounce
2. Shift Start Boundary Protection (Early arrival guard)
3. Rotational Shift Proximity Auto-Detection
4. Overtime & Late Offset Policies (independent, offset_full, offset_ratio)
5. Half-Day Double-Deduction Guard
6. Holiday Signal Absence Cleanup & Actual Present Overtime Preservation
7. Permission Waiver Auto-Reconciliation
8. Mid-Month Joiner Pro-Rata Phantom Guard
9. Dynamic Overtime Base Wage Calculation with Contract Components
10. Draft Payroll Invalidation (is_stale)
"""
import pytest
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import date, time, datetime, timedelta
from decimal import Decimal
import json

from core.models import SystemSetting
from hr.models import (
    Department, JobTitle, Employee, Shift, Attendance,
    BiometricDevice, BiometricLog, BiometricUserMapping,
    OfficialHoliday, PermissionRequest, PermissionType,
    AttendanceSummary, Payroll, Contract, ContractSalaryComponent
)
from hr.services.attendance_service import AttendanceService
from hr.views.biometric_api import _match_employee_3tier, biometric_bridge_sync
from django.test import RequestFactory
from django.test import override_settings

User = get_user_model()


@pytest.mark.django_db
class TestPhase1AttendanceEngine(TestCase):
    """اختبارات المحرك المركزي للحضور والانصراف - المرحلة الأولى"""

    def setUp(self):
        """إعداد البيانات الأساسية للاختبار"""
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='hr_admin',
            password='password123',
            email='admin@mwheba.com'
        )

        self.dept = Department.objects.create(code='ENG', name_ar='الهندسة', is_active=True)
        self.job = JobTitle.objects.create(code='SE', title_ar='مهندس برمجيات', department=self.dept, is_active=True)

        # الوردية الصباحية 8:00 - 16:00 (8 ساعات، الجمعة والسبت عطلة)
        self.morning_shift = Shift.objects.create(
            name='الوردية الصباحية',
            shift_type='regular',
            start_time=time(8, 0),
            end_time=time(16, 0),
            grace_period_in=15,
            grace_period_out=15,
            weekly_off_days=[4, 5],  # Friday=4, Saturday=5
            is_active=True
        )

        # الوردية المسائية 16:00 - 00:00 (8 ساعات)
        self.evening_shift = Shift.objects.create(
            name='الوردية المسائية',
            shift_type='regular',
            start_time=time(16, 0),
            end_time=time(0, 0),
            grace_period_in=15,
            grace_period_out=15,
            weekly_off_days=[4, 5],
            is_active=True
        )

        # موظف 1
        self.employee1 = Employee.objects.create(
            employee_number='EMP001',
            name='أحمد محمود علي',
            national_id='29001011234567',
            birth_date=date(1990, 1, 1),
            gender='male',
            marital_status='single',
            hire_date=date(2026, 1, 1),
            department=self.dept,
            job_title=self.job,
            shift=self.morning_shift,
            biometric_user_id='BIO101',
            status='active',
            created_by=self.user
        )

        # جهاز البصمة
        self.device = BiometricDevice.objects.create(
            device_name='بصمة المقر الرئيسي',
            device_code='BIO-HQ-01',
            device_type='fingerprint',
            serial_number='SN12345678',
            ip_address='192.168.1.200',
            location='HQ',
            is_active=True,
            timezone_offset_hours=0,
            created_by=self.user
        )

    @override_settings(BRIDGE_AGENTS={'TEST_AGENT': 'secret_key_123'})
    def test_biometric_3_tier_matching_and_debounce(self):
        """1. اختبار المطابقة ثلاثية المستويات وسد الثغرة الزمنية (Debounce)"""
        # Tier 1: Match by Employee.biometric_user_id ('BIO101')
        emp_matched_tier1 = _match_employee_3tier('BIO101', self.device)
        assert emp_matched_tier1 == self.employee1

        # Tier 2: Match by BiometricUserMapping
        BiometricUserMapping.objects.create(
            device=self.device,
            biometric_user_id='MAPPED_99',
            employee=self.employee1,
            is_active=True
        )
        emp_matched_tier2 = _match_employee_3tier('MAPPED_99', self.device)
        assert emp_matched_tier2 == self.employee1

        # Tier 3: Match by employee_number
        emp_matched_tier3 = _match_employee_3tier('EMP001', self.device)
        assert emp_matched_tier3 == self.employee1

        # Test sync endpoint and Sliding Debounce (30s window)
        log_time = '2026-03-01T08:00:00'
        log_time_dup = '2026-03-01T08:00:10'  # 10s later -> duplicate
        payload = {
            'agent_code': 'TEST_AGENT',
            'agent_secret': 'secret_key_123',
            'device_code': 'BIO-HQ-01',
            'records': [
                {'user_id': 'BIO101', 'timestamp': log_time, 'punch': 0},
                {'user_id': 'BIO101', 'timestamp': log_time_dup, 'punch': 0},
            ]
        }

        request = self.factory.post(
            '/hr/api/biometric/bridge-sync/',
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_AUTHORIZATION='Bearer secret_key_123'
        )
        response = biometric_bridge_sync(request)
        res_data = response.data

        assert response.status_code == 200
        assert res_data['processed'] == 1
        assert res_data['skipped'] == 1
        assert BiometricLog.objects.filter(device=self.device, user_id='BIO101').count() == 1

    def test_shift_start_boundary_protection(self):
        """2. اختبار حماية حدود بداية الوردية (الحضور المبكر لا يولد إضافي صباحي)"""
        # الحضور 07:15 صباحاً (قبل الموعد بـ 45 دقيقة)، الانصراف 16:00 (في الموعد تماماً)
        check_in = timezone.make_aware(datetime(2026, 3, 2, 7, 15, 0))  # Monday
        check_out = timezone.make_aware(datetime(2026, 3, 2, 16, 0, 0))

        attendance = Attendance(
            employee=self.employee1,
            date=check_in.date(),
            shift=self.morning_shift,
            check_in=check_in,
            check_out=check_out
        )
        AttendanceService.calculate_daily_attendance(attendance)

        # ساعات العمل تحسب من 8:00 إلى 16:00 = 8.00 ساعات
        assert attendance.work_hours == Decimal('8.00')
        assert attendance.overtime_hours == Decimal('0.00')
        assert attendance.late_minutes == 0

    def test_rotational_shift_proximity_auto_detection(self):
        """3. اختبار التعرف الذكي على الوردية المتغيرة بالقرب الزمني"""
        # الموظف مسجل على الصباحية (8:00)، لكنه حضر الساعة 15:50 (قريب من المسائية 16:00)
        check_in = timezone.make_aware(datetime(2026, 3, 2, 15, 50, 0))
        resolved_shift = AttendanceService.resolve_effective_shift(self.employee1, check_in)

        assert resolved_shift.id == self.evening_shift.id

    def test_overtime_late_offset_policies(self):
        """4. اختبار سياسات تسوية التأخير الصباحي مقابل الإضافي المسائي"""
        # الموظف حضر 08:30 (تأخير 30 دقيقة)، وانصرف 17:30 (عمل 9 ساعات بدلاً من 8، إضافي خام 60 دقيقة)
        check_in = timezone.make_aware(datetime(2026, 3, 2, 8, 30, 0))
        check_out = timezone.make_aware(datetime(2026, 3, 2, 17, 30, 0))

        # Test Case A: independent (فصل تام)
        SystemSetting.set_setting('hr_overtime_late_offset_policy', 'independent')
        attendance_a = Attendance(
            employee=self.employee1,
            date=check_in.date(),
            shift=self.morning_shift,
            check_in=check_in,
            check_out=check_out
        )
        AttendanceService.calculate_daily_attendance(attendance_a)
        assert attendance_a.late_minutes == 30
        assert attendance_a.overtime_hours == Decimal('1.00')  # 9.0h - 8.0h = 1.0h overtime

        # Test Case B: offset_full (1:1) -> 60 min ot - 30 min late = 30 min = 0.5h
        SystemSetting.set_setting('hr_overtime_late_offset_policy', 'offset_full')
        attendance_b = Attendance(
            employee=self.employee1,
            date=check_in.date(),
            shift=self.morning_shift,
            check_in=check_in,
            check_out=check_out
        )
        AttendanceService.calculate_daily_attendance(attendance_b)
        assert attendance_b.late_minutes == 30
        assert attendance_b.overtime_hours == Decimal('0.50')

        # Test Case C: offset_ratio (0.50) -> 60 min ot - (30 * 0.5 = 15) = 45 min = 0.75h
        SystemSetting.set_setting('hr_overtime_late_offset_policy', 'offset_ratio')
        SystemSetting.set_setting('hr_overtime_late_offset_ratio', '0.50')
        attendance_c = Attendance(
            employee=self.employee1,
            date=check_in.date(),
            shift=self.morning_shift,
            check_in=check_in,
            check_out=check_out
        )
        AttendanceService.calculate_daily_attendance(attendance_c)
        assert attendance_c.late_minutes == 30
        assert attendance_c.overtime_hours == Decimal('0.75')

    def test_half_day_double_deduction_guard(self):
        """5. اختبار حظر الخصم المزدوج لنصف اليوم"""
        # الموظف حضر 8:00 وانصرف 11:00 (عمل 3 ساعات < 4 ساعات عتبة نصف اليوم)
        check_in = timezone.make_aware(datetime(2026, 3, 2, 8, 0, 0))
        check_out = timezone.make_aware(datetime(2026, 3, 2, 11, 0, 0))

        att = Attendance(
            employee=self.employee1,
            date=check_in.date(),
            shift=self.morning_shift,
            check_in=check_in,
            check_out=check_out
        )
        AttendanceService.calculate_daily_attendance(att)

        assert att.status == 'half_day'
        # الانصراف المبكر يصفر لمنع الخصم المزدوج
        assert att.early_leave_minutes == 0

    def test_holiday_signal_preservation_of_present_attendance(self):
        """6. اختبار إشارة العطلة الرسمية: حذف الغيابات وحفظ الحضور الفعلي كإضافي 2.0x"""
        holiday_date = date(2026, 3, 10)

        # غياب مسجل مسبقاً
        absent_att = Attendance.objects.create(
            employee=self.employee1,
            date=holiday_date,
            shift=self.morning_shift,
            status='absent',
            work_hours=Decimal('0.00')
        )

        # موظف آخر حضر فعلياً في ذلك اليوم
        emp2 = Employee.objects.create(
            employee_number='EMP003',
            name='كريم سامي أحمد',
            national_id='29101011234569',
            birth_date=date(1991, 3, 3),
            gender='male',
            marital_status='single',
            hire_date=date(2026, 1, 1),
            department=self.dept,
            job_title=self.job,
            shift=self.morning_shift,
            status='active',
            created_by=self.user
        )
        cin = timezone.make_aware(datetime(2026, 3, 10, 8, 0, 0))
        cout = timezone.make_aware(datetime(2026, 3, 10, 16, 0, 0))
        present_att = Attendance.objects.create(
            employee=emp2,
            date=holiday_date,
            shift=self.morning_shift,
            check_in=cin,
            check_out=cout,
            work_hours=Decimal('8.00'),
            status='present'
        )

        # إنشاء العطلة الرسمية
        OfficialHoliday.objects.create(
            name='يوم التأسيس',
            start_date=holiday_date,
            end_date=holiday_date,
            is_active=True
        )

        # التحقق: سجل الغياب تم حذفه
        assert not Attendance.objects.filter(id=absent_att.id).exists()

        # التحقق: سجل الحضور الفعلي تم الإبقاء عليه وتحديث إضافيه
        present_att.refresh_from_db()
        assert present_att.overtime_hours == Decimal('8.00')

    def test_permission_waiver_auto_reconciliation(self):
        """7. اختبار التسوية التلقائية مع أذونات العمل الصباحية والمسائية"""
        perm_type = PermissionType.objects.create(
            name_ar='إذن شخصي',
            code='PERSONAL',
            is_active=True
        )
        perm_date = date(2026, 3, 4)

        # إذن صباحي لمدة ساعتين معتمد
        PermissionRequest.objects.create(
            employee=self.employee1,
            permission_type=perm_type,
            date=perm_date,
            duration_hours=Decimal('2.00'),
            start_time=time(8, 0),
            end_time=time(10, 0),
            reason='مراجعة طبية',
            status='approved'
        )

        # حضور الموظف الساعة 09:30 (تأخير 90 دقيقة يغطيه الإذن 120 دقيقة)
        check_in = timezone.make_aware(datetime(2026, 3, 4, 9, 30, 0))
        check_out = timezone.make_aware(datetime(2026, 3, 4, 16, 0, 0))

        att = Attendance(
            employee=self.employee1,
            date=perm_date,
            shift=self.morning_shift,
            check_in=check_in,
            check_out=check_out
        )
        AttendanceService.calculate_daily_attendance(att)

        assert att.late_minutes == 0

    def test_pro_rata_mid_month_joiner_guard(self):
        """8. اختبار حماية التعيين في منتصف الشهر من توليد غيابات وهمية"""
        new_emp = Employee.objects.create(
            employee_number='EMP004',
            name='هاني شاكر علي',
            national_id='29301011234560',
            birth_date=date(1993, 4, 4),
            gender='male',
            marital_status='single',
            hire_date=date(2026, 3, 15),  # تعيين 15 مارس
            department=self.dept,
            job_title=self.job,
            shift=self.morning_shift,
            status='active',
            created_by=self.user
        )

        # توليد الحضور والغياب من 1 مارس إلى 20 مارس
        AttendanceService.generate_missing_attendances(date(2026, 3, 1), date(2026, 3, 20))

        # التأكد من عدم وجود أي سجل حضور أو غياب قبل 15 مارس
        before_hire_count = Attendance.objects.filter(employee=new_emp, date__lt=date(2026, 3, 15)).count()
        assert before_hire_count == 0

    def test_single_source_of_truth_and_draft_payroll_invalidation(self):
        """9. اختبار Single Source of Truth ووسم مسودات الرواتب بأنها Stale"""
        contract = Contract.objects.create(
            contract_number='CONT-PAYROLL-001',
            employee=self.employee1,
            contract_type='permanent',
            start_date=date(2026, 1, 1),
            basic_salary=Decimal('6000.00'),
            status='active',
            created_by=self.user
        )

        att_date = date(2026, 3, 3)
        payroll = Payroll.objects.create(
            employee=self.employee1,
            contract=contract,
            month=att_date,
            basic_salary=Decimal('6000.00'),
            gross_salary=Decimal('6000.00'),
            net_salary=Decimal('6000.00'),
            processed_by=self.user,
            status='draft',
            is_stale=False
        )

        cin = timezone.make_aware(datetime(2026, 3, 3, 8, 0, 0))
        attendance = AttendanceService.record_check_in(self.employee1, timestamp=cin)

        payroll.refresh_from_db()
        assert payroll.is_stale is True
        assert attendance.work_hours == Decimal('0.00')  # Missing checkout initially

        # تسجيل الانصراف
        cout = timezone.make_aware(datetime(2026, 3, 3, 16, 0, 0))
        attendance_out = AttendanceService.record_check_out(self.employee1, timestamp=cout)
        assert attendance_out.work_hours == Decimal('8.00')
        assert attendance_out.is_missing_checkout is False

    def test_dynamic_overtime_base_wage_with_contract_components(self):
        """10. اختبار احتساب أجر ساعة الإضافي بناءً على الراتب الأساسي والبدلات المحددة في العقد"""
        # إنشاء عقد للموظف مع بند يؤثر على الأوفر تايم وبند آخر لا يؤثر
        contract = Contract.objects.create(
            contract_number='CONT-2026-001',
            employee=self.employee1,
            contract_type='permanent',
            start_date=date(2026, 1, 1),
            basic_salary=Decimal('6000.00'),
            status='active',
            created_by=self.user
        )

        # بدل طبيعة عمل (يؤثر على الإضافي = True)
        ContractSalaryComponent.objects.create(
            contract=contract,
            name='بدل طبيعة عمل',
            code='NATURE_ALLOWANCE',
            component_type='earning',
            amount=Decimal('1200.00'),
            affects_overtime=True
        )

        # بدل هاتف (لا يؤثر على الإضافي = False)
        ContractSalaryComponent.objects.create(
            contract=contract,
            name='بدل هاتف',
            code='PHONE_ALLOWANCE',
            component_type='earning',
            amount=Decimal('500.00'),
            affects_overtime=False
        )

        summary = AttendanceSummary.objects.create(
            employee=self.employee1,
            month=date(2026, 3, 1),
            approved_overtime_hours=Decimal('10.00')
        )

        # الحساب:
        # الراتب الخاضع للإضافي = 6000 + 1200 = 7200
        # أجر اليوم = 7200 / 30 = 240
        # أجر الساعة = 240 / 8 = 30
        # قيمة الإضافي العادي (10 ساعات * 30 * 1.5) = 450.00
        hourly_rate = summary.calculate_hourly_rate()
        assert hourly_rate == Decimal('30.00')

        overtime_amount = summary.calculate_overtime_amount()
        assert overtime_amount == Decimal('450.00')
