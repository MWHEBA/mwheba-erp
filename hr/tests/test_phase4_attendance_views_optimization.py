"""
Automated unit & integration test suite for Phase 4:
- Hybrid weekend / holiday punches inclusion in Attendance list
- Archived/Exempt employee filtering when specific employee_id is requested
- Source filtering (mobile, device, manual, field_visit, etc.)
- Database-level status filtering for 'permission' keeping SSR pagination intact
- Panoramic KPIs calculated across the full queryset
- Rich movements serialization (movements_rich & movements_json)
- Attendance Excel export with source, location, customer, and device columns
- Timezone awareness in manual attendance save and excel import
"""
import io
import json
import openpyxl
import pytest
from datetime import date, time, datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from hr.models import (
    Employee, Department, JobTitle, Shift, Contract,
    Attendance, AttendanceSummary, BiometricLog, WorkLocation, BiometricDevice,
    PermissionRequest, PermissionType, AttendanceAuditLog
)

User = get_user_model()


@pytest.fixture
def p4_setup(db):
    user = User.objects.create_superuser(
        username='hr_admin_phase4',
        password='password123',
        email='hr_phase4@test.com'
    )
    content_type = ContentType.objects.get_for_model(Attendance)
    perm_view, _ = Permission.objects.get_or_create(
        codename='view_attendance',
        content_type=content_type,
        defaults={'name': 'عرض الحضور'}
    )
    perm_manual, _ = Permission.objects.get_or_create(
        codename='can_manual_attendance',
        content_type=content_type,
        defaults={'name': 'إضافة حضور يدوي'}
    )
    perm_import, _ = Permission.objects.get_or_create(
        codename='can_import_attendance',
        content_type=content_type,
        defaults={'name': 'استيراد حضور'}
    )
    user.user_permissions.add(perm_view, perm_manual, perm_import)

    client = Client()
    client.force_login(user)

    dept = Department.objects.create(name_ar='إدارة العمليات الميدانية', is_active=True)
    job = JobTitle.objects.create(title_ar='فني صيانة ميداني', department=dept)
    shift = Shift.objects.create(
        name='وردية التشغيل',
        start_time=time(9, 0),
        end_time=time(17, 0)
    )
    loc = WorkLocation.objects.create(
        name_ar='فرع الدقي',
        latitude=Decimal('30.038100'),
        longitude=Decimal('31.212000'),
        radius_meters=100,
        is_active=True
    )
    emp_active = Employee.objects.create(
        name='محمد أحمد عبد السميع',
        employee_number='EMP-P4-001',
        national_id='29501011234571',
        birth_date=date(1995, 1, 1),
        gender='male',
        marital_status='single',
        created_by=user,
        department=dept,
        job_title=job,
        shift=shift,
        status='active',
        attendance_exempt=False,
        hire_date=date(2025, 1, 1),
    )
    emp_archived = Employee.objects.create(
        name='سعيد إبراهيم الخولي',
        employee_number='EMP-P4-002',
        national_id='29501011234572',
        birth_date=date(1990, 1, 1),
        gender='male',
        marital_status='married',
        created_by=user,
        department=dept,
        job_title=job,
        shift=shift,
        status='terminated',
        attendance_exempt=False,
        hire_date=date(2024, 1, 1),
    )
    device = BiometricDevice.objects.create(
        device_name='ماكينة الدقي 1',
        device_code='DEV-P4-001',
        serial_number='SN-P4-001',
        ip_address='192.168.1.200',
        port=4370,
        device_type='face',
        created_by=user,
        is_active=True
    )

    return {
        'user': user,
        'client': client,
        'dept': dept,
        'shift': shift,
        'loc': loc,
        'emp_active': emp_active,
        'emp_archived': emp_archived,
        'device': device,
    }


@pytest.mark.django_db
class TestPhase4AttendanceViewsAndQueries:

    def test_attendance_list_hybrid_weekend_punch_visibility(self, p4_setup):
        """التحقق من ظهور بصمة الجمعة/العطلات في قائمة الحضور إذا وُجد تسجيل فعلي"""
        client = p4_setup['client']
        emp = p4_setup['emp_active']
        shift = p4_setup['shift']

        # 2026-05-15 is Friday (weekday = 4)
        friday_date = date(2026, 5, 15)
        assert friday_date.weekday() == 4

        check_in_dt = timezone.make_aware(datetime.combine(friday_date, time(9, 0)), timezone.get_current_timezone())
        check_out_dt = timezone.make_aware(datetime.combine(friday_date, time(17, 0)), timezone.get_current_timezone())

        att = Attendance.objects.create(
            employee=emp,
            date=friday_date,
            shift=shift,
            check_in=check_in_dt,
            check_out=check_out_dt,
            work_hours=Decimal('8.00'),
            status='present',
            source='mobile'
        )

        response = client.get('/hr/attendance/', {
            'date_from': '2026-05-10',
            'date_to': '2026-05-17',
        })
        assert response.status_code == 200

        data = response.context['attendance_data']
        dates_in_data = [item['date'] for item in data]
        assert friday_date in dates_in_data

    def test_attendance_list_employee_archive_filter(self, p4_setup):
        """التحقق من أن الموظف المنتهية خدمته يظهر فقط عند فلترته برقم الموظف"""
        client = p4_setup['client']
        emp_archived = p4_setup['emp_archived']
        shift = p4_setup['shift']

        target_date = date(2026, 5, 12)
        Attendance.objects.create(
            employee=emp_archived,
            date=target_date,
            shift=shift,
            status='present',
            check_in=timezone.now(),
            source='device'
        )

        # 1. الاستعلام العام بدون تحديد موظف: الموظف المستبعد لا يظهر
        res_general = client.get('/hr/attendance/', {
            'date_from': '2026-05-10',
            'date_to': '2026-05-15',
        })
        emp_ids_general = [item['employee'].id for item in res_general.context['attendance_data']]
        assert emp_archived.id not in emp_ids_general

        # 2. الاستعلام المخصص بـ employee_id: يظهر سجله بنجاح
        res_specific = client.get('/hr/attendance/', {
            'date_from': '2026-05-10',
            'date_to': '2026-05-15',
            'employee': emp_archived.id,
        })
        emp_ids_specific = [item['employee'].id for item in res_specific.context['attendance_data']]
        assert emp_archived.id in emp_ids_specific

    def test_attendance_list_source_filter(self, p4_setup):
        """التحقق من عمل فلتر المصدر (موبايل، ماكينة، يدوي)"""
        client = p4_setup['client']
        emp = p4_setup['emp_active']
        shift = p4_setup['shift']

        date1 = date(2026, 5, 11)
        date2 = date(2026, 5, 12)

        Attendance.objects.create(
            employee=emp, date=date1, shift=shift, status='present',
            check_in=timezone.now(), source='mobile'
        )
        Attendance.objects.create(
            employee=emp, date=date2, shift=shift, status='present',
            check_in=timezone.now(), source='device'
        )

        # استعلام فلتر موبايل فقط
        response = client.get('/hr/attendance/', {
            'date_from': '2026-05-10',
            'date_to': '2026-05-15',
            'source': 'mobile',
        })
        data = response.context['attendance_data']
        assert len(data) == 1
        assert data[0]['source'] == 'mobile'

    def test_attendance_list_permission_db_filter(self, p4_setup):
        """التحقق من تصفية الأذونات في الـ Queryset مباشرة لحفظ الـ Pagination"""
        client = p4_setup['client']
        user = p4_setup['user']
        emp = p4_setup['emp_active']
        shift = p4_setup['shift']

        target_date = date(2026, 5, 13)
        Attendance.objects.create(
            employee=emp, date=target_date, shift=shift, status='present',
            check_in=timezone.now(), source='device'
        )

        perm_type = PermissionType.objects.create(name_ar='إذن خاص', code='PERM-P4-001')
        PermissionRequest.objects.create(
            employee=emp,
            permission_type=perm_type,
            date=target_date,
            start_time=time(10, 0),
            end_time=time(12, 0),
            duration_hours=Decimal('2.00'),
            status='approved',
            reason='إذن متابعة ميدانية'
        )

        response = client.get('/hr/attendance/', {
            'date_from': '2026-05-10',
            'date_to': '2026-05-15',
            'status': 'permission',
        })
        data = response.context['attendance_data']
        assert len(data) == 1
        assert data[0]['status'] == 'permission'
        assert data[0]['permission_info'] is not None

    def test_attendance_list_panoramic_kpis_and_rich_movements(self, p4_setup):
        """التحقق من حساب المؤشرات الشاملة وتجهيز movements_rich و movements_json"""
        client = p4_setup['client']
        emp = p4_setup['emp_active']
        shift = p4_setup['shift']
        loc = p4_setup['loc']
        dev = p4_setup['device']

        target_date = date(2026, 5, 14)
        att = Attendance.objects.create(
            employee=emp, date=target_date, shift=shift, status='present',
            check_in=timezone.now(), source='mobile', location_name='مقر الدقي'
        )

        log1 = BiometricLog.objects.create(
            employee=emp,
            attendance=att,
            user_id=emp.employee_number,
            timestamp=timezone.now(),
            log_type='check_in',
            source='mobile',
            matched_location=loc,
            device=dev,
            latitude=Decimal('30.038100'),
            longitude=Decimal('31.212000'),
            location_accuracy=15.0,
            is_device_unverified=False
        )

        response = client.get('/hr/attendance/', {
            'date_from': '2026-05-10',
            'date_to': '2026-05-15',
        })

        ctx = response.context
        assert ctx['present_count'] >= 1
        assert 'source_filter' in ctx

        row = ctx['attendance_data'][0]
        assert len(row['movements_rich']) == 1
        rich = row['movements_rich'][0]
        assert rich['location'] == 'فرع الدقي'
        assert rich['type'] == 'حضور'
        assert rich['source'] == 'موبايل'
        assert rich['lat'] == 30.0381
        assert 'movements_json' in row
        parsed_json = json.loads(row['movements_json'])
        assert len(parsed_json) == 1

    def test_attendance_export_excel_columns(self, p4_setup):
        """التحقق من تصدير ملف الإكسيل بأعمدة المصدر والموقع والعميل والجهاز"""
        client = p4_setup['client']
        emp = p4_setup['emp_active']
        shift = p4_setup['shift']
        loc = p4_setup['loc']

        target_date = date(2026, 5, 11)
        att = Attendance.objects.create(
            employee=emp, date=target_date, shift=shift, status='present',
            check_in=timezone.now(), source='mobile', location_name='فرع الدقي'
        )
        BiometricLog.objects.create(
            employee=emp,
            attendance=att,
            user_id=emp.employee_number,
            timestamp=timezone.now(),
            log_type='check_in',
            source='mobile',
            matched_location=loc
        )

        response = client.get(reverse('hr:attendance_export_excel'), {
            'date_from': '2026-05-10',
            'date_to': '2026-05-15',
            'source': 'mobile',
        })
        assert response.status_code == 200
        assert 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' in response['Content-Type']

        wb = openpyxl.load_workbook(io.BytesIO(response.content))
        ws = wb.active
        headers = [cell.value for cell in ws[2]]
        assert 'المصدر' in headers
        assert 'المقر / الموقع' in headers
        assert 'العميل / أمر الشغل' in headers
        assert 'الجهاز' in headers

    def test_attendance_manual_save_and_localtime_response(self, p4_setup):
        """التحقق من حفظ الحضور اليدوي وتنسيق التوقيت المحلي بدقة"""
        client = p4_setup['client']
        emp = p4_setup['emp_active']

        target_date = date(2026, 5, 18)
        response = client.post('/hr/attendance/manual-save/', {
            'employee_id': emp.id,
            'date': target_date.strftime('%Y-%m-%d'),
            'status': 'present',
            'check_in': '08:30',
            'check_out': '16:30',
            'reason': 'توجيه مباشر من الإدارة',
        })
        assert response.status_code == 200
        res_data = response.json()
        assert res_data['success'] is True
        assert res_data['data']['check_in'] != '-'
        assert res_data['data']['check_out'] != '-'

        saved_att = Attendance.objects.get(employee=emp, date=target_date)
        assert timezone.is_aware(saved_att.check_in)
        assert timezone.is_aware(saved_att.check_out)
