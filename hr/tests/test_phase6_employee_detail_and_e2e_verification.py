import json
from datetime import date, time, timedelta
from decimal import Decimal
from django.test import TestCase, Client
from django.utils import timezone
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from hr.models import (
    Employee, Department, JobTitle, Shift, WorkLocation,
    Attendance, BiometricLog, AttendanceSummary
)
from hr.services.geofencing_service import GeofencingService

User = get_user_model()


class TestPhase6EmployeeDetailAndE2E(TestCase):
    def setUp(self):
        self.client = Client()
        self.today = timezone.localdate()

        # إنشاء مستخدم أدمن ومستخدم HR
        self.admin_user = User.objects.create_superuser(
            username='admin_p6',
            email='admin_p6@example.com',
            password='password123'
        )

        self.hr_user = User.objects.create_user(
            username='hr_officer_p6',
            email='hr_p6@example.com',
            password='password123',
            is_staff=True
        )
        
        emp_ct = ContentType.objects.get_for_model(Employee)
        att_ct = ContentType.objects.get_for_model(Attendance)
        
        perm_change_emp = Permission.objects.get(codename='change_employee', content_type=emp_ct)
        perm_view_emp = Permission.objects.get(codename='view_employee', content_type=emp_ct)
        perm_change_att = Permission.objects.get(codename='change_attendance', content_type=att_ct)
        perm_view_att = Permission.objects.get(codename='view_attendance', content_type=att_ct)
        perm_export_att, _ = Permission.objects.get_or_create(
            codename='can_export_attendance',
            content_type=att_ct,
            defaults={'name': 'تصدير الحضور'}
        )
        self.hr_user.user_permissions.add(perm_change_emp, perm_view_emp, perm_change_att, perm_view_att, perm_export_att)

        self.regular_user = User.objects.create_user(
            username='regular_p6',
            email='reg_p6@example.com',
            password='password123'
        )

        # قسم ومسمى ووردية ومقر
        self.dept = Department.objects.create(name_ar='قسم تكنولوجيا المعلومات', is_active=True)
        self.job = JobTitle.objects.create(title_ar='مهندس برمجيات', department=self.dept)
        self.shift = Shift.objects.create(
            name='الوردية الصباحية',
            start_time=time(9, 0),
            end_time=time(17, 0)
        )

        self.loc = WorkLocation.objects.create(
            name_ar='المقر الرئيسي بالمعادي',
            latitude=Decimal('30.044400'),
            longitude=Decimal('31.235700'),
            radius_meters=150,
            is_active=True,
            is_default=True
        )

        # موظف مرتبط بجهاز
        self.employee = Employee.objects.create(
            name='علي محمود إبراهيم',
            employee_number='EMP-P6-001',
            national_id='29001011234567',
            gender='male',
            marital_status='single',
            hire_date=date(2023, 1, 1),
            birth_date=date(1990, 1, 1),
            created_by=self.admin_user,
            department=self.dept,
            job_title=self.job,
            shift=self.shift,
            work_location=self.loc,
            allow_mobile_attendance=True,
            registered_device_uuid='DEV-TEST-P6-UUID-12345678',
            device_bound_at=timezone.now(),
            status='active'
        )

        # 1x1 Transparent PNG Dummy
        self.dummy_png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="

    def test_employee_detail_renders_device_binding_card_and_badges(self):
        """التحقق من ظهور بطاقة ربط الهاتف المعتمد والشارة وزر فك الارتباط في بروفايل الموظف"""
        self.client.login(username='hr_officer_p6', password='password123')
        url = reverse('hr:employee_detail', args=[self.employee.pk])
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)

        # فحص الشارة وزر فك الربط وكود المعرف
        self.assertContains(res, 'حالة ربط الهاتف (Device Binding)')
        self.assertContains(res, 'معتمد')
        self.assertContains(res, 'DEV-TEST-P6-UUID')
        self.assertContains(res, 'فك الربط')
        self.assertContains(res, 'id="resetDeviceModal"')

    def test_employee_detail_awaiting_first_bind_status(self):
        """التحقق من ظهور حالة 'بانتظار أول ربط' إذا كان الموظف مفعل للموبايل بدون جهاز مقترن"""
        self.employee.registered_device_uuid = None
        self.employee.device_bound_at = None
        self.employee.save()

        self.client.login(username='hr_officer_p6', password='password123')
        url = reverse('hr:employee_detail', args=[self.employee.pk])
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)

        self.assertContains(res, 'بانتظار أول ربط')

    def test_employee_detail_recent_biometric_logs_presentation(self):
        """التحقق من عرض آخر 5 بصمات مع مصادر الموبايل والمأموريات ومصغرات السيلفي وعدم وجود بادج فارغ"""
        BiometricLog.objects.create(
            employee=self.employee,
            timestamp=timezone.now() - timedelta(hours=3),
            log_type='check_in',
            source='mobile',
            matched_location=self.loc,
            is_processed=True
        )
        BiometricLog.objects.create(
            employee=self.employee,
            timestamp=timezone.now() - timedelta(hours=1),
            log_type='field_visit',
            source='field_visit',
            device_info={'reason': 'مقر شركة الأمل - العبور'},
            is_processed=True
        )

        self.client.login(username='hr_officer_p6', password='password123')
        url = reverse('hr:employee_detail', args=[self.employee.pk])
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)

        self.assertContains(res, 'آخر 5 حركات بصمة مسجلة')
        self.assertContains(res, 'موبايل')
        self.assertContains(res, 'مأمورية')
        self.assertContains(res, 'المقر الرئيسي بالمعادي')
        self.assertContains(res, 'مقر شركة الأمل - العبور')

    def test_reset_device_binding_permission_security(self):
        """التحقق من حوكمة صلاحيات فك ربط الهاتف: قبول HR والمسؤولين ورفض المستخدمين العاديين"""
        reset_url = reverse('hr:reset_employee_device_binding', args=[self.employee.pk])

        # 1. مستخدم عادي بدون صلاحيات -> 403 Forbidden
        self.client.login(username='regular_p6', password='password123')
        res1 = self.client.post(reset_url, {'reason': 'تغيير هاتف'})
        self.assertEqual(res1.status_code, 403)

        # الموظف ما زال مرتبطاً
        self.employee.refresh_from_db()
        self.assertIsNotNone(self.employee.registered_device_uuid)

        # 2. مسؤول HR يحمل hr.change_employee و is_staff -> 200 OK
        self.client.login(username='hr_officer_p6', password='password123')
        res2 = self.client.post(reset_url, {'reason': 'قام الموظف بشراء هاتف جديد'})
        self.assertEqual(res2.status_code, 200)
        data = res2.json()
        self.assertTrue(data['success'])

        # فك الارتباط تم بنجاح
        self.employee.refresh_from_db()
        self.assertIsNone(self.employee.registered_device_uuid)
        self.assertIsNone(self.employee.device_bound_at)

    def test_post_delete_signal_cleans_selfie_file(self):
        """التحقق من أن حذف سجل البصمة يحذف ملف السيلفي المادي من وحدة التخزين دون ترك ملفات يتيمة"""
        dummy_file = ContentFile(b'fake_selfie_bytes_data', name='selfie_test_p6.jpg')
        log = BiometricLog.objects.create(
            employee=self.employee,
            timestamp=timezone.now(),
            log_type='check_in',
            source='mobile',
            selfie_image=dummy_file,
            is_processed=True
        )
        file_path = log.selfie_image.name
        self.assertTrue(default_storage.exists(file_path))

        # حذف السجل
        log.delete()

        # تم حذف الملف تلقائياً عبر الإشارة post_delete
        self.assertFalse(default_storage.exists(file_path))

    def test_e2e_full_mobile_punch_and_payroll_integration(self):
        """اختبار تكاملي شامل من بصمة الموبايل حتى احتساب ملخص الرواتب وتصدير الإكسيل"""
        self.client.login(username='hr_officer_p6', password='password123')

        # توليد توكن أمني مباشر
        punch_token = GeofencingService.generate_secure_punch_token(self.employee.id, self.hr_user.id)
        self.assertTrue(bool(punch_token))

        # 1. إرسال بصمة الحضور
        punch_url = reverse('hr:api_submit_mobile_punch')
        check_in_data = {
            'employee_id': self.employee.id,
            'punch_type': 'check_in',
            'latitude': 30.0444,
            'longitude': 31.2357,
            'accuracy': 15.0,
            'device_uuid': self.employee.registered_device_uuid,
            'punch_token': punch_token,
            'selfie_image': self.dummy_png,
            'client_timestamp': timezone.now().isoformat()
        }
        res_in = self.client.post(punch_url, data=json.dumps(check_in_data), content_type='application/json')
        self.assertEqual(res_in.status_code, 200)
        data_in = res_in.json()
        self.assertTrue(data_in['success'])
        new_token = data_in['new_punch_token']

        # التحقق من إنشاء سجل الحضور اليومي وتعيين المصدر mobile
        att = Attendance.objects.get(employee=self.employee, date=self.today)
        self.assertIsNotNone(att.check_in)
        self.assertEqual(att.source, 'mobile')

        # 2. إرسال بصمة الانصراف
        check_out_data = {
            'employee_id': self.employee.id,
            'punch_type': 'check_out',
            'latitude': 30.0444,
            'longitude': 31.2357,
            'accuracy': 18.0,
            'device_uuid': self.employee.registered_device_uuid,
            'punch_token': new_token,
            'selfie_image': self.dummy_png,
            'client_timestamp': (timezone.now() + timedelta(hours=8)).isoformat()
        }
        res_out = self.client.post(punch_url, data=json.dumps(check_out_data), content_type='application/json')
        self.assertEqual(res_out.status_code, 200)
        data_out = res_out.json()
        self.assertTrue(data_out['success'])

        att.refresh_from_db()
        self.assertIsNotNone(att.check_out)

        # 3. احتساب ملخص الحضور الشهري للرواتب
        summary = AttendanceSummary.objects.create(
            employee=self.employee,
            month=date(self.today.year, self.today.month, 1)
        )
        summary.calculate()
        summary.refresh_from_db()

        # تأكيد تسجيل الحضور وتحديث الساعات في ملخص الراتب
        self.assertGreaterEqual(summary.present_days, 1)

        # 4. تصدير إكسيل الحضور
        export_url = reverse('hr:attendance_export_excel') + f'?month={self.today.month}&year={self.today.year}'
        res_export = self.client.get(export_url)
        self.assertEqual(res_export.status_code, 200)
        self.assertIn('spreadsheet', res_export['Content-Type'])
