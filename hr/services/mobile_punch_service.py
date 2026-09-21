"""
خدمة بصمة الهاتف الذكية وسيلفي الحضور والمزامنة (Mobile Punch & Offline Sync Service)
MWHEBA ERP - Mobile Punch Engine
"""
import base64
import logging
from datetime import datetime, date, time
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from ..models import (
    Employee,
    Shift,
    Attendance,
    BiometricLog,
    WorkLocation,
    AttendanceAuditLog,
)
from .geofencing_service import GeofencingService
from .attendance_service import AttendanceService

logger = logging.getLogger(__name__)


class MobilePunchService:
    """خدمة معالجة بصمة الهاتف الذكية وسيلفي الحضور والمزامنة الأوفلاين"""

    @staticmethod
    def get_punch_context(employee: Employee, user: Any) -> Dict[str, Any]:
        """
        جلب سياق البصمة الشامل للموظف:
        - وقت السيرفر الحالي.
        - الوردية الفعالة ومواعيدها.
        - المقرات الجغرافية المعتمدة وحدودها.
        - حالة بصمة اليوم (حضور / انصراف / ساعات العمل).
        - توكن البصمة الأمني المشفر (Anti-Replay Token).
        - صلاحيات الموظف (موبايل / متنقل / زيارات ميدانية).
        """
        now = timezone.now()
        today = now.date()

        # استرجاع أو التعرف على الوردية
        effective_shift = employee.shift or AttendanceService.resolve_effective_shift(employee)
        ref_start, ref_end = AttendanceService._get_reference_times(effective_shift, today) if effective_shift else (time(9, 0), time(17, 0))

        # المقرات الجغرافية النشطة
        active_locations = GeofencingService.get_active_locations()
        locations_data = []
        for loc in active_locations:
            locations_data.append({
                'id': loc.id,
                'name': loc.name_ar,
                'latitude': float(loc.latitude),
                'longitude': float(loc.longitude),
                'radius_meters': loc.radius_meters,
                'is_default': loc.is_default,
            })

        # سجل حضور اليوم
        today_att = Attendance.objects.filter(employee=employee, date=today).first()
        attendance_info = {
            'has_checked_in': bool(today_att and today_att.check_in),
            'check_in_time': timezone.localtime(today_att.check_in).strftime('%H:%M') if (today_att and today_att.check_in) else None,
            'has_checked_out': bool(today_att and today_att.check_out),
            'check_out_time': timezone.localtime(today_att.check_out).strftime('%H:%M') if (today_att and today_att.check_out) else None,
            'status': today_att.status if today_att else 'absent',
            'work_hours': float(today_att.work_hours) if today_att else 0.0,
            'late_minutes': today_att.late_minutes if today_att else 0,
            'overtime_hours': float(today_att.overtime_hours) if today_att else 0.0,
        }

        # توليد التوكن الأمني
        punch_token = GeofencingService.generate_secure_punch_token(
            employee_id=employee.id,
            user_id=user.id if user and hasattr(user, 'id') else 0
        )

        return {
            'server_time': now.isoformat(),
            'server_date': today.isoformat(),
            'employee': {
                'id': employee.id,
                'name': employee.get_full_name_ar(),
                'employee_number': employee.employee_number,
                'allow_mobile_attendance': getattr(employee, 'allow_mobile_attendance', True),
                'allowed_all_locations': getattr(employee, 'allowed_all_locations', False),
                'allow_field_visits': getattr(employee, 'allow_field_visits', False),
                'has_bound_device': bool(employee.registered_device_uuid),
                'registered_device_uuid': employee.registered_device_uuid,
            },
            'shift': {
                'id': effective_shift.id if effective_shift else None,
                'name': effective_shift.name if effective_shift else 'وردية عامة',
                'start_time': ref_start.strftime('%H:%M'),
                'end_time': ref_end.strftime('%H:%M'),
            },
            'locations': locations_data,
            'attendance_today': attendance_info,
            'punch_token': punch_token,
        }

    @staticmethod
    def _save_selfie_image(selfie_b64: str, employee_id: int) -> Optional[ContentFile]:
        """معالجة وحفظ صورة السيلفي من Base64"""
        if not selfie_b64:
            return None
        try:
            # استخراج بيانات الصورة إذا كانت data URL
            if ',' in selfie_b64:
                selfie_b64 = selfie_b64.split(',', 1)[1]
            img_data = base64.b64decode(selfie_b64)
            filename = f"selfie_emp_{employee_id}_{timezone.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"
            return ContentFile(img_data, name=filename)
        except Exception as e:
            logger.warning(f"Failed to decode selfie image for emp {employee_id}: {str(e)}")
            return None

    @staticmethod
    @transaction.atomic
    def process_mobile_punch(
        employee: Employee,
        user: Any,
        punch_type: str,
        latitude: float,
        longitude: float,
        location_accuracy: Optional[float] = None,
        device_uuid: Optional[str] = None,
        is_mock_flag: bool = False,
        speed_kmh: Optional[float] = None,
        punch_token: Optional[str] = None,
        selfie_base64: Optional[str] = None,
        is_field_visit: bool = False,
        field_visit_reason: str = '',
        customer_id: Optional[int] = None,
        work_order_id: Optional[int] = None,
        is_offline_synced: bool = False,
        client_timestamp: Optional[datetime] = None,
        is_emergency: bool = False,
    ) -> Dict[str, Any]:
        """
        معالجة بصمة الهاتف المركزية الموثقة:
        1. فحص تصريح بصمة الموبايل للموظف.
        2. التحقق من التوكن الأمني المشفر (Anti-Replay).
        3. فحص ومكافحة برامج التزييف (Mock Location / Fake GPS).
        4. فحص وحوكمة ربط الجهاز (Device Binding).
        5. التحقق من النطاق الجغرافي (Geofencing Validation).
        6. حفظ صورة السيلفي وسجل الـ BiometricLog.
        7. تحديث / إنشاء سجل الـ Attendance وتشغيل المحرك الحسابي.
        8. توثيق سجل التدقيق (Audit Trail).
        """
        # 1. فحص تصريح بصمة الموبايل
        if not getattr(employee, 'allow_mobile_attendance', True):
            return {
                'success': False,
                'message': 'غير مصرح لك باستخدام بصمة الهاتف. يرجى استخدام ماكينة البصمة المعتمدة أو مراجعة إدارة الموارد البشرية.',
            }

        # 2. التحقق من التوكن الأمني (في حالة البصم المباشر أونلاين)
        if not is_offline_synced and punch_token:
            is_token_valid, token_err = GeofencingService.verify_secure_punch_token(
                token=punch_token,
                employee_id=employee.id,
                max_age_seconds=180,
            )
            if not is_token_valid:
                return {'success': False, 'message': f'فشل التحقق الأمني من جلسة البصمة: {token_err}'}

        # 3. كشف برامج التزييف Fake GPS
        is_mock, mock_msg = GeofencingService.detect_mock_location(
            is_mock_flag=is_mock_flag,
            accuracy_meters=location_accuracy,
            speed_kmh=speed_kmh,
        )
        if is_mock:
            return {'success': False, 'message': mock_msg}

        # 4. فحص ربط الجهاز Hardware Binding
        is_dev_valid, is_newly_bound, dev_msg = GeofencingService.validate_device_binding(
            employee=employee,
            device_uuid=device_uuid or 'UNKNOWN_BROWSER',
            is_emergency=is_emergency,
        )
        if not is_dev_valid:
            return {'success': False, 'message': dev_msg}

        # 5. التحقق من الموقع الجغرافي Geofencing
        is_loc_valid, matched_loc, dist_meters, loc_msg = GeofencingService.validate_location(
            employee=employee,
            latitude=latitude,
            longitude=longitude,
            is_field_visit=is_field_visit,
            accuracy_meters=location_accuracy,
        )
        if not is_loc_valid:
            return {'success': False, 'message': loc_msg}

        # تحديد وقت وتاريخ البصمة
        punch_time = client_timestamp if (is_offline_synced and client_timestamp) else timezone.now()
        punch_date = punch_time.date() if timezone.is_aware(punch_time) else timezone.localtime(punch_time).date()

        # 6. فحص تسلسل ومنطق البصمة (Attendance Flow & Anti-Spam Validation)
        effective_shift = employee.shift or AttendanceService.resolve_effective_shift(employee, check_in_dt=punch_time)
        attendance, created = Attendance.objects.get_or_create(
            employee=employee,
            date=punch_date,
            defaults={
                'shift': effective_shift,
                'status': 'present',
            }
        )

        if not attendance.shift:
            attendance.shift = effective_shift

        action_label = ''
        if punch_type == 'check_in':
            if attendance.check_in and not created:
                check_in_fmt = timezone.localtime(attendance.check_in).strftime('%I:%M %p').replace('AM', 'ص').replace('PM', 'م')
                return {
                    'success': False,
                    'message': f'لقد تم تسجيل حضورك مسبقاً اليوم في تمام الساعة {check_in_fmt}. لا يمكن إعادة تسجيل الحضور مرة أخرى.',
                }
            attendance.check_in = punch_time
            action_label = 'تسجيل الحضور'
        elif punch_type == 'check_out':
            if not attendance.check_in:
                return {
                    'success': False,
                    'message': 'لا يمكن تسجيل الانصراف قبل تسجيل الحضور أولاً.',
                }
            if not attendance.check_out:
                attendance.check_out = punch_time
                action_label = 'تسجيل الانصراف'
            else:
                diff_checkout_sec = abs((punch_time - attendance.check_out).total_seconds())
                if diff_checkout_sec < 60:
                    check_out_fmt = timezone.localtime(attendance.check_out).strftime('%I:%M %p').replace('AM', 'ص').replace('PM', 'م')
                    return {
                        'success': False,
                        'message': f'تم تسجيل انصرافك بالفعل عند الساعة {check_out_fmt}.',
                    }
                action_label = 'تحديث بصمة الانصراف'
                attendance.check_out = max(attendance.check_out, punch_time)

        # 7. حفظ صورة السيلفي وسجل الـ BiometricLog
        selfie_file = MobilePunchService._save_selfie_image(selfie_base64, employee.id)

        bio_log = BiometricLog.objects.create(
            employee=employee,
            user_id=employee.employee_number or str(employee.id),
            timestamp=punch_time,
            log_type=punch_type,
            source='mobile_gps',
            latitude=Decimal(str(round(latitude, 7))),
            longitude=Decimal(str(round(longitude, 7))),
            location_accuracy=float(location_accuracy) if location_accuracy else None,
            matched_location=matched_loc,
            selfie_image=selfie_file,
            device_uuid=device_uuid,
            is_device_unverified=is_emergency,
            is_offline_synced=is_offline_synced,
            sync_received_at=timezone.now() if is_offline_synced else None,
            customer_id=customer_id,
            work_order_id=work_order_id,
            is_processed=True,
            attendance=attendance,
        )

        # تشغيل المحرك الحسابي الموحد لحساب ساعات العمل والغياب والتأخير والإضافي
        AttendanceService.calculate_daily_attendance(attendance)
        attendance.save()

        # 8. توثيق سجل التدقيق التاريخي Audit Log
        if user and hasattr(user, 'id') and user.is_authenticated:
            loc_name = matched_loc.name_ar if matched_loc else ('مأمورية ميدانية' if is_field_visit else 'موقع خارجي')
            AttendanceAuditLog.objects.create(
                attendance=attendance,
                field_name=punch_type,
                old_value='',
                new_value=punch_time.strftime('%Y-%m-%d %H:%M:%S'),
                changed_by=user,
                reason=f'بصمة موبايل ذكية ({action_label}) - {loc_name}' + (f' - سبب المأمورية: {field_visit_reason}' if field_visit_reason else ''),
            )

        success_msg = f'تم {action_label} بنجاح عند الساعة {timezone.localtime(punch_time).strftime("%H:%M")}'
        if is_field_visit:
            success_msg += f' (مأمورية ميدانية: {field_visit_reason or "معتمدة"})'
        elif matched_loc:
            success_msg += f' في مقر ({matched_loc.name_ar})'

        return {
            'success': True,
            'message': success_msg,
            'punch_type': punch_type,
            'punch_time': timezone.localtime(punch_time).strftime('%H:%M:%S'),
            'date': punch_date.isoformat(),
            'attendance_id': attendance.id,
            'matched_location': matched_loc.name_ar if matched_loc else None,
            'distance_meters': dist_meters,
            'work_hours': float(attendance.work_hours),
            'late_minutes': attendance.late_minutes,
            'early_leave_minutes': attendance.early_leave_minutes,
            'overtime_hours': float(attendance.overtime_hours),
            'status': attendance.status,
            'is_newly_bound_device': is_newly_bound,
        }

    @staticmethod
    def process_offline_sync(employee: Employee, user: Any, punches: List[Dict[str, Any]]) -> Dict[str, Any]:
        """معالجة دفعة بصمات أوفلاين تم تجميعها أثناء انقطاع الإنترنت"""
        if not punches:
            return {'success': True, 'synced_count': 0, 'results': []}

        # ترتيب البصمات زمنياً
        sorted_punches = sorted(punches, key=lambda p: p.get('client_timestamp', ''))
        results = []
        synced_count = 0

        for p in sorted_punches:
            client_ts_raw = p.get('client_timestamp')
            client_dt = None
            if client_ts_raw:
                try:
                    client_dt = datetime.fromisoformat(client_ts_raw)
                    if timezone.is_naive(client_dt):
                        client_dt = timezone.make_aware(client_dt)
                except Exception:
                    client_dt = timezone.now()

            res = MobilePunchService.process_mobile_punch(
                employee=employee,
                user=user,
                punch_type=p.get('punch_type', 'check_in'),
                latitude=float(p.get('latitude', 0.0)),
                longitude=float(p.get('longitude', 0.0)),
                location_accuracy=float(p.get('location_accuracy', 10.0)),
                device_uuid=p.get('device_uuid'),
                is_mock_flag=bool(p.get('is_mock_flag', False)),
                speed_kmh=float(p.get('speed_kmh', 0.0)) if p.get('speed_kmh') else None,
                punch_token=None,  # لا يتطلب فحص التوكن المباشر للأوفلاين
                selfie_base64=p.get('selfie_base64'),
                is_field_visit=bool(p.get('is_field_visit', False)),
                field_visit_reason=p.get('field_visit_reason', 'مزامنة أوفلاين'),
                customer_id=p.get('customer_id'),
                work_order_id=p.get('work_order_id'),
                is_offline_synced=True,
                client_timestamp=client_dt,
                is_emergency=bool(p.get('is_emergency', False)),
            )
            results.append(res)
            if res.get('success'):
                synced_count += 1

        return {
            'success': True,
            'synced_count': synced_count,
            'total_received': len(punches),
            'results': results,
            'message': f'تمت مزامنة {synced_count} من أصل {len(punches)} بصمة أوفلاين بنجاح.',
        }

    @staticmethod
    def process_supervisor_crew_punch(
        supervisor_user: Any,
        crew_employee_ids: List[int],
        punch_type: str,
        latitude: float,
        longitude: float,
        location_accuracy: Optional[float] = None,
        selfie_base64: Optional[str] = None,
        notes: str = '',
    ) -> Dict[str, Any]:
        """
        بصمة طاقم العمل للمشرف / رئيس العمال (Supervisor Crew Punch):
        - تسجيل بصمة جماعية لطاقم العمل في الموقع الميداني أو الإنشائي.
        - توثيق إحداثيات وصورة المشرف كشاهد معتمد.
        """
        if not crew_employee_ids:
            return {'success': False, 'message': 'يرجى اختيار موظف واحد على الأقل من طاقم العمل.'}

        employees = Employee.objects.filter(id__in=crew_employee_ids, status='active')
        if not employees.exists():
            return {'success': False, 'message': 'لم يتم العثور على موظفين نشطين في القائمة المحددة.'}

        successful_employees = []
        failed_employees = []

        now = timezone.now()

        for emp in employees:
            is_field = getattr(emp, 'allow_field_visits', False)
            res = MobilePunchService.process_mobile_punch(
                employee=emp,
                user=supervisor_user,
                punch_type=punch_type,
                latitude=latitude,
                longitude=longitude,
                location_accuracy=location_accuracy,
                device_uuid=f"SUPERVISOR_{supervisor_user.id}",
                is_mock_flag=False,
                punch_token=None,
                selfie_base64=selfie_base64,
                is_field_visit=is_field,
                field_visit_reason=f'بصمة طاقم عمل بإشراف المشرف ({supervisor_user.get_full_name() or supervisor_user.username})' + (f' - {notes}' if notes else ''),
                is_emergency=True,
            )
            if res.get('success'):
                successful_employees.append(emp.get_full_name_ar())
            else:
                failed_employees.append({'name': emp.get_full_name_ar(), 'reason': res.get('message')})

        return {
            'success': len(successful_employees) > 0,
            'total_selected': len(crew_employee_ids),
            'success_count': len(successful_employees),
            'failed_count': len(failed_employees),
            'successful_names': successful_employees,
            'failed_details': failed_employees,
            'message': f'تم تسجيل بصمة {len(successful_employees)} موظف بنجاح بواسطة المشرف.',
        }
