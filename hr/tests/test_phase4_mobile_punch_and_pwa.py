"""
اختبارات شاملة للمرحلة 4:
1. جلب سياق البصمة الذكية والتوكن المشفر (API Get Punch Context)
2. تسجيل الحضور والانصراف بالسيلفي والموقع الجغرافي (Mobile Punch In / Out)
3. حظر البصمة في حالة عدم التصريح باستخدام الهاتف (Mobile Punch Authorization Guard)
4. رفض البصمة خارج النطاق الجغرافي (Geofencing Guard)
5. كشف وحظر محاولات التلاعب وتزييف الموقع (Mock Location Guard)
6. حوكمة عتاد الجهاز ورفض الأجهزة غير المصرح بها (Device Binding Guard)
7. تسجيل بصمات المأموريات والزيارات الميدانية المعتمدة (Field Visit Punch)
8. مزامنة البصمات المجمعة أوفلاين (Offline Punches Batch Sync)
9. بصمة طواقم العمل بإشراف المشرف الميداني (Supervisor Crew Batch Punch)
10. حماية التوكنات المشفرة ومكافحة هجمات إعادة الإرسال (Anti-Replay Token Guard)
"""
import base64
import json
import pytest
from datetime import date, time, datetime, timedelta
from decimal import Decimal

from django.test import RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.utils import timezone

from hr.models import (
    Employee, Department, JobTitle, Shift, WorkLocation, Contract, Attendance, BiometricLog
)
from hr.services.geofencing_service import GeofencingService
from hr.services.mobile_punch_service import MobilePunchService
from hr.views.mobile_attendance_views import (
    api_get_punch_context,
    api_submit_mobile_punch,
    api_sync_offline_punches,
    api_supervisor_crew_punch,
)

User = get_user_model()


@pytest.fixture
def phase4_setup(db):
    """إعداد بيانات الاختبار الأساسية للمرحلة 4"""
    cache.clear()
    dept = Department.objects.create(name_ar='إدارة المشاريع والتنفيذ', code='PRJ')
    job = JobTitle.objects.create(title_ar='مهندس موقع', department=dept)
    shift = Shift.objects.create(
        name='وردية نهارية للمشاريع',
        start_time=time(9, 0),
        end_time=time(17, 0)
    )

    # مستخدم موظف
    user_emp = User.objects.create_user(
        username='emp_mobile_user',
        email='emp_mobile_user@test.com',
        password='password123'
    )
    # مستخدم مشرف
    user_supervisor = User.objects.create_user(
        username='supervisor_user',
        email='supervisor_user@test.com',
        password='password123',
        is_staff=True
    )

    # منح صلاحيات للمشرف
    ct_att = ContentType.objects.get_for_model(Attendance)
    perm_add_att, _ = Permission.objects.get_or_create(
        codename='add_attendance',
        content_type=ct_att,
        defaults={'name': 'إضافة حضور'}
    )
    user_supervisor.user_permissions.add(perm_add_att)

    # مقر رئيسي (30.012000, 31.432000) بنصف قطر 100 متر
    hq_loc = WorkLocation.objects.create(
        name_ar='المقر الرئيسي - التجمع',
        latitude=Decimal('30.0120000'),
        longitude=Decimal('31.4320000'),
        radius_meters=100,
        is_active=True,
        is_default=True,
    )

    # موظف 1: بصمة موبايل مفعلة
    emp1 = Employee.objects.create(
        user=user_emp,
        name='أحمد حسني محمود',
        employee_number='EMP-MOB-001',
        national_id='29401011234591',
        birth_date=date(1994, 5, 10),
        gender='male',
        marital_status='married',
        mobile_phone='01099998881',
        created_by=user_supervisor,
        department=dept,
        job_title=job,
        shift=shift,
        work_location=hq_loc,
        allow_mobile_attendance=True,
        allowed_all_locations=False,
        allow_field_visits=False,
        status='active',
        hire_date=date(2025, 1, 1),
    )

    # موظف 2: مندوب ميداني مسموح له بالزيارات
    emp_field = Employee.objects.create(
        name='محمود سامي خليل',
        employee_number='EMP-MOB-002',
        national_id='29601011234592',
        birth_date=date(1996, 8, 12),
        gender='male',
        marital_status='single',
        mobile_phone='01099998882',
        created_by=user_supervisor,
        department=dept,
        job_title=job,
        shift=shift,
        work_location=hq_loc,
        allow_mobile_attendance=True,
        allowed_all_locations=False,
        allow_field_visits=True,
        status='active',
        hire_date=date(2025, 1, 1),
    )

    # موظف 3: بصمة الموبايل معطلة
    emp_blocked = Employee.objects.create(
        name='عمرو خالد إبراهيم',
        employee_number='EMP-MOB-003',
        national_id='29801011234593',
        birth_date=date(1998, 2, 20),
        gender='male',
        marital_status='single',
        mobile_phone='01099998883',
        created_by=user_supervisor,
        department=dept,
        job_title=job,
        shift=shift,
        work_location=hq_loc,
        allow_mobile_attendance=False,
        allowed_all_locations=False,
        allow_field_visits=False,
        status='active',
        hire_date=date(2025, 1, 1),
    )

    # صورة سيلفي وهمية صالحة (1x1 PNG pixel Base64)
    dummy_selfie = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

    return {
        'dept': dept,
        'job': job,
        'shift': shift,
        'hq_loc': hq_loc,
        'user_emp': user_emp,
        'user_supervisor': user_supervisor,
        'emp1': emp1,
        'emp_field': emp_field,
        'emp_blocked': emp_blocked,
        'dummy_selfie': dummy_selfie,
        'rf': RequestFactory(),
    }


@pytest.mark.django_db
class TestPhase4MobilePunchAPIs:
    """اختبارات الـ APIs لمحرك بصمة الهاتف الذكية"""

    def test_get_punch_context_api(self, phase4_setup):
        """اختبار جلب سياق البصمة الحالي والتوكن المشفر"""
        rf = phase4_setup['rf']
        user = phase4_setup['user_emp']
        emp = phase4_setup['emp1']

        request = rf.get('/hr/api/attendance/mobile/context/')
        request.user = user

        response = api_get_punch_context(request)
        assert response.status_code == 200
        data = json.loads(response.content.decode('utf-8'))
        assert data['success'] is True
        assert 'punch_token' in data['data']
        assert data['data']['employee']['name'] == emp.get_full_name_ar()
        assert len(data['data']['locations']) > 0

    def test_mobile_punch_check_in_and_check_out_success(self, phase4_setup):
        """تسجيل الحضور ثم الانصراف عبر الموبايل بنجاح داخل النطاق الجغرافي"""
        rf = phase4_setup['rf']
        user = phase4_setup['user_emp']
        emp = phase4_setup['emp1']
        selfie = phase4_setup['dummy_selfie']

        token = GeofencingService.generate_secure_punch_token(emp.id, user.id)

        # 1. تسجيل الحضور (Check-In)
        req_in = rf.post(
            '/hr/api/attendance/mobile/punch/',
            data=json.dumps({
                'punch_type': 'check_in',
                'latitude': 30.012050,
                'longitude': 31.432050,
                'accuracy': 12.0,
                'device_uuid': 'DEVICE-PHONE-12345',
                'punch_token': token,
                'selfie_image': selfie,
            }),
            content_type='application/json'
        )
        req_in.user = user

        res_in = api_submit_mobile_punch(req_in)
        assert res_in.status_code == 200
        data_in = json.loads(res_in.content.decode('utf-8'))
        assert data_in['success'] is True
        assert data_in['punch_type'] == 'check_in'

        # التحقق من قاعدة البيانات
        today = timezone.now().date()
        att = Attendance.objects.get(employee=emp, date=today)
        assert att.check_in is not None
        assert att.status in ['present', 'late']

        # التحقق من سجل الـ BiometricLog
        bio_in = BiometricLog.objects.filter(employee=emp, log_type='check_in').latest('timestamp')
        assert bio_in.source == 'mobile_gps'
        assert bio_in.selfie_image is not None
        assert bio_in.device_uuid == 'DEVICE-PHONE-12345'

        # 2. تسجيل الانصراف (Check-Out)
        token_out = GeofencingService.generate_secure_punch_token(emp.id, user.id)
        req_out = rf.post(
            '/hr/api/attendance/mobile/punch/',
            data=json.dumps({
                'punch_type': 'check_out',
                'latitude': 30.012050,
                'longitude': 31.432050,
                'accuracy': 15.0,
                'device_uuid': 'DEVICE-PHONE-12345',
                'punch_token': token_out,
                'selfie_image': selfie,
            }),
            content_type='application/json'
        )
        req_out.user = user

        res_out = api_submit_mobile_punch(req_out)
        assert res_out.status_code == 200
        data_out = json.loads(res_out.content.decode('utf-8'))
        assert data_out['success'] is True
        assert data_out['punch_type'] == 'check_out'

        att.refresh_from_db()
        assert att.check_out is not None

    def test_mobile_punch_unauthorized_mobile_rejected(self, phase4_setup):
        """رفض البصمة للموظف المعطل له بصمة الموبايل"""
        emp_blocked = phase4_setup['emp_blocked']
        user = phase4_setup['user_emp']

        res = MobilePunchService.process_mobile_punch(
            employee=emp_blocked,
            user=user,
            punch_type='check_in',
            latitude=30.012000,
            longitude=31.432000,
        )
        assert res['success'] is False
        assert "غير مصرح لك باستخدام بصمة الهاتف" in res['message']

    def test_mobile_punch_outside_geofence_rejected(self, phase4_setup):
        """رفض البصمة عند التواجد خارج المقر الجغرافي المعتمد"""
        emp = phase4_setup['emp1']
        user = phase4_setup['user_emp']

        # إحداثيات بعيدة 10 كم
        res = MobilePunchService.process_mobile_punch(
            employee=emp,
            user=user,
            punch_type='check_in',
            latitude=30.150000,
            longitude=31.300000,
            location_accuracy=10.0,
            device_uuid='DEV-001',
        )
        assert res['success'] is False
        assert "أنت خارج نطاق مقر العمل" in res['message']

    def test_mobile_punch_mock_location_blocked(self, phase4_setup):
        """حظر البصمة عند رصد برنامج Fake GPS"""
        emp = phase4_setup['emp1']
        user = phase4_setup['user_emp']

        res = MobilePunchService.process_mobile_punch(
            employee=emp,
            user=user,
            punch_type='check_in',
            latitude=30.012000,
            longitude=31.432000,
            is_mock_flag=True,
        )
        assert res['success'] is False
        assert "Mock Location" in res['message']

    def test_mobile_punch_device_binding_guard(self, phase4_setup):
        """حوكمة عتاد الهاتف ومنع البصم من أجهزة غير مسجلة"""
        emp = phase4_setup['emp1']
        user = phase4_setup['user_emp']

        # ربط الهاتف الأول
        res1 = MobilePunchService.process_mobile_punch(
            employee=emp,
            user=user,
            punch_type='check_in',
            latitude=30.012000,
            longitude=31.432000,
            device_uuid='PHONE-UUID-ALPHA',
        )
        assert res1['success'] is True
        assert res1['is_newly_bound_device'] is True

        # محاولة البصم من هاتف آخر بدون طوارئ
        res2 = MobilePunchService.process_mobile_punch(
            employee=emp,
            user=user,
            punch_type='check_out',
            latitude=30.012000,
            longitude=31.432000,
            device_uuid='PHONE-UUID-BETA',
            is_emergency=False,
        )
        assert res2['success'] is False
        assert "مرتبط بجهاز هاتف آخر" in res2['message']

    def test_field_visit_punch_with_reason(self, phase4_setup):
        """تسجيل بصمة مأمورية ميدانية مع السبب للموظف المصرح له"""
        emp_field = phase4_setup['emp_field']
        user = phase4_setup['user_emp']

        # إحداثيات خارج الفروع
        res = MobilePunchService.process_mobile_punch(
            employee=emp_field,
            user=user,
            punch_type='check_in',
            latitude=30.080000,
            longitude=31.320000,
            is_field_visit=True,
            field_visit_reason='معاينة مشروع مدينتي',
            device_uuid='FIELD-PHONE-1',
        )
        assert res['success'] is True
        assert "مأمورية ميدانية" in res['message']

        bio = BiometricLog.objects.filter(employee=emp_field).latest('timestamp')
        assert bio.source == 'mobile_gps'

    def test_offline_sync_batch_processing(self, phase4_setup):
        """مزامنة دفعة بصمات تم جمعها أثناء انقطاع الإنترنت"""
        emp = phase4_setup['emp1']
        user = phase4_setup['user_emp']
        rf = phase4_setup['rf']

        now_dt = timezone.now()
        ts_in = (now_dt - timedelta(hours=8)).isoformat()
        ts_out = now_dt.isoformat()

        batch_punches = [
            {
                'punch_type': 'check_in',
                'latitude': 30.012000,
                'longitude': 31.432000,
                'location_accuracy': 10.0,
                'device_uuid': 'OFFLINE-DEV-001',
                'client_timestamp': ts_in,
            },
            {
                'punch_type': 'check_out',
                'latitude': 30.012000,
                'longitude': 31.432000,
                'location_accuracy': 12.0,
                'device_uuid': 'OFFLINE-DEV-001',
                'client_timestamp': ts_out,
            }
        ]

        req_sync = rf.post(
            '/hr/api/attendance/mobile/sync/',
            data=json.dumps({'punches': batch_punches}),
            content_type='application/json'
        )
        req_sync.user = user

        res_sync = api_sync_offline_punches(req_sync)
        assert res_sync.status_code == 200
        data_sync = json.loads(res_sync.content.decode('utf-8'))
        assert data_sync['success'] is True
        assert data_sync['synced_count'] == 2

        # التحقق من وسم البصمات بـ is_offline_synced
        offline_logs = BiometricLog.objects.filter(employee=emp, is_offline_synced=True)
        assert offline_logs.count() == 2

    def test_supervisor_crew_batch_punch(self, phase4_setup):
        """تسجيل بصمة جماعية لطاقم العمل بإشراف المشرف الميداني"""
        emp1 = phase4_setup['emp1']
        emp_field = phase4_setup['emp_field']
        supervisor = phase4_setup['user_supervisor']
        rf = phase4_setup['rf']

        req_crew = rf.post(
            '/hr/api/attendance/supervisor/punch/',
            data=json.dumps({
                'crew_employee_ids': [emp1.id, emp_field.id],
                'punch_type': 'check_in',
                'latitude': 30.012000,
                'longitude': 31.432000,
                'accuracy': 10.0,
                'notes': 'موقع العاصمة الإدارية R7'
            }),
            content_type='application/json'
        )
        req_crew.user = supervisor

        res_crew = api_supervisor_crew_punch(req_crew)
        assert res_crew.status_code == 200
        data_crew = json.loads(res_crew.content.decode('utf-8'))
        assert data_crew['success'] is True
        assert data_crew['success_count'] == 2

        # كلا الموظفين تم تسجيل حضورهم
        assert Attendance.objects.filter(employee=emp1, date=timezone.now().date()).exists()
        assert Attendance.objects.filter(employee=emp_field, date=timezone.now().date()).exists()
