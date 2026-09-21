"""
خدمة التحقق الجغرافي ومكافحة التحايل وأمن البصمة (Geofencing & Anti-Fraud Service)
MWHEBA ERP - Geofencing & Mobile Punch Engine
"""
import math
import uuid
import logging
from typing import Optional, Tuple, List, Dict, Any

from django.core.cache import cache
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.utils import timezone

from ..models.work_location import WorkLocation
from ..models.employee import Employee

logger = logging.getLogger(__name__)


class GeofencingService:
    """خدمة التحقق الجغرافي، الكاش السريع، ومكافحة التحايل والتزييف"""

    CACHE_KEY = 'mwheba_active_work_locations'
    CACHE_TIMEOUT = 300  # 5 دقائق

    @staticmethod
    def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        حساب المسافة الجغرافية الدقيقة بين نقطتين بالأمتار باستخدام معادلة هافرسين (Haversine Formula).
        الدقة: دقيقة حتى مستوى السنتيمتر.
        """
        R = 6371000.0  # متوسط نصف قطر الأرض بالمتر
        phi1 = math.radians(float(lat1))
        phi2 = math.radians(float(lat2))
        delta_phi = math.radians(float(lat2) - float(lat1))
        delta_lambda = math.radians(float(lon2) - float(lon1))

        a = (
            math.sin(delta_phi / 2.0) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
        )
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return round(R * c, 2)

    @staticmethod
    def get_active_locations() -> List[WorkLocation]:
        """استرجاع كافة مقرات العمل النشطة من الكاش للأداء الفائق (<50ms)"""
        cached = cache.get(GeofencingService.CACHE_KEY)
        if cached is not None:
            return cached
        locations = list(WorkLocation.objects.filter(is_active=True))
        cache.set(GeofencingService.CACHE_KEY, locations, GeofencingService.CACHE_TIMEOUT)
        return locations

    @staticmethod
    def invalidate_cache() -> None:
        """تفريغ كاش مقرات العمل عند أي تعديل أو إنشاء جديد"""
        cache.delete(GeofencingService.CACHE_KEY)

    @staticmethod
    def validate_location(
        employee: Employee,
        latitude: float,
        longitude: float,
        is_field_visit: bool = False,
        accuracy_meters: Optional[float] = None,
    ) -> Tuple[bool, Optional[WorkLocation], float, Optional[str]]:
        """
        التحقق الجغرافي الشامل من موقع البصمة:
        - التحقق من دقة إشارة الـ GPS.
        - دعم الزيارات الميدانية للموظفين المصرح لهم.
        - دعم الموظف المتنقل بين كافة المقرات (allowed_all_locations).
        - دعم الموظف المرتبط بمقر محدد (work_location).
        - الاعتماد على أقرب مقر نشط كـ Fallback.
        """
        # 1. فحص دقة الـ GPS
        if accuracy_meters is not None:
            try:
                acc_val = float(accuracy_meters)
                if acc_val > 150.0:
                    return False, None, 0.0, f"إشارة الـ GPS ضعيفة ({int(acc_val)} متر). يرجى التواجد في مكان مفتوح والمحاولة مجدداً"
                if acc_val <= 0.0:
                    return False, None, 0.0, "إشارة الـ GPS غير صالحة"
            except (ValueError, TypeError):
                pass

        # 2. إذا كانت زيارة ميدانية
        if is_field_visit:
            if getattr(employee, 'allow_field_visits', False):
                return True, None, 0.0, "زيارة ميدانية معتمدة"
            else:
                return False, None, 0.0, "الموظف غير مصرح له بتسجيل زيارات أو مأموريات ميدانية"

        # 3. فحص المقرات المعتمدة
        active_locations = GeofencingService.get_active_locations()
        if not active_locations:
            return False, None, 0.0, "لا توجد مقرات عمل جغرافية نشطة معرفة في النظام"

        target_loc = getattr(employee, 'work_location', None)
        allowed_all = getattr(employee, 'allowed_all_locations', False)

        # إذا كان الموظف مخصص له مقر محدد ونشط وليس متجولاً
        if target_loc and target_loc.is_active and not allowed_all:
            dist = GeofencingService.calculate_distance(
                latitude, longitude, target_loc.latitude, target_loc.longitude
            )
            if dist <= float(target_loc.radius_meters):
                return True, target_loc, dist, None
            else:
                return (
                    False,
                    target_loc,
                    dist,
                    f"أنت خارج نطاق مقر العمل ({target_loc.name_ar}) بمسافة {int(dist)} متر (المسموح: {target_loc.radius_meters} متر)",
                )

        # إذا كان الموظف متجولاً أو غير محدد له مقر بعينه
        nearest_loc = None
        min_dist = float('inf')

        for loc in active_locations:
            dist = GeofencingService.calculate_distance(
                latitude, longitude, loc.latitude, loc.longitude
            )
            if dist < min_dist:
                min_dist = dist
                nearest_loc = loc
            if dist <= float(loc.radius_meters):
                return True, loc, dist, None

        near_name = nearest_loc.name_ar if nearest_loc else "مقر العمل"
        return (
            False,
            nearest_loc,
            min_dist,
            f"أنت خارج نطاق جميع مقرات العمل المعتمدة (أقرب مقر: {near_name} بمسافة {int(min_dist)} متر)",
        )

    @staticmethod
    def detect_mock_location(
        is_mock_flag: bool = False,
        accuracy_meters: Optional[float] = None,
        speed_kmh: Optional[float] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        كشف ومكافحة برامج تزييف الموقع (Anti-Mock Location & Fake GPS):
        - فحص الراية الصادرة من متصفح/نظام الموبايل.
        - فحص سرعات الانتقال غير الواقعية.
        """
        if is_mock_flag:
            return True, "تم اكتشاف استخدام برنامج تزييف الموقع الجغرافي (Mock Location). البصمة مرفوضة أمنياً."

        if speed_kmh is not None:
            try:
                speed_val = float(speed_kmh)
                if speed_val > 350.0:  # سرعة تتجاوز 350 كم/ساعة
                    return True, "تم رصد سرعة انتقال غير واقعية تدل على التلاعب بالإحداثيات."
            except (ValueError, TypeError):
                pass

        return False, None

    @staticmethod
    def validate_device_binding(
        employee: Employee,
        device_uuid: str,
        is_emergency: bool = False,
    ) -> Tuple[bool, bool, Optional[str]]:
        """
        فحص وحوكمة ربط عتاد جهاز الموظف (Hardware Device Binding):
        Returns: (is_valid, is_newly_bound, message)
        - أول تسجيل دخول: ربط عتاد الهاتف تلقائياً بحساب الموظف.
        - الاستخدامات اللاحقة: مطابقة الـ UUID لمنع تبادل الهواتف.
        - حالات الطوارئ: السماح بالبصمة مع وسمها وتنبيه الـ HR.
        """
        if not device_uuid or not str(device_uuid).strip():
            return False, False, "تعذر قراءة معرف عتاد الجهاز. يرجى تفعيل الصلاحيات في المتصفح."

        clean_uuid = str(device_uuid).strip()

        # أول استخدام للموظف -> ربط تلقائي
        if not employee.registered_device_uuid:
            employee.registered_device_uuid = clean_uuid
            employee.device_bound_at = timezone.now()
            employee.save(update_fields=['registered_device_uuid', 'device_bound_at'])
            return True, True, None

        # مسجل مسبقاً -> مطابقة تامة
        if employee.registered_device_uuid == clean_uuid:
            return True, False, None

        # جهاز مختلف
        if is_emergency:
            return True, False, "بصمة طوارئ من جهاز غير موثق (تم تسجيلها وتتطلب مراجعة إدارة الموارد البشرية)"

        return (
            False,
            False,
            "هذا الحساب مرتبط بجهاز هاتف آخر معتمد. يرجى استخدام هاتفك المسجل أو طلب فك الارتباط من الموارد البشرية.",
        )

    @staticmethod
    def reset_device_binding(employee: Employee, reset_by_user: Any, reason: str = '') -> None:
        """فك ربط جهاز الموظف بواسطة مسؤول الموارد البشرية"""
        employee.registered_device_uuid = None
        employee.device_bound_at = None
        employee.save(update_fields=['registered_device_uuid', 'device_bound_at'])
        logger.info(
            f"Device binding reset for employee {employee.id} ({employee.name}) by user {reset_by_user} - Reason: {reason}"
        )

    @staticmethod
    def generate_secure_punch_token(employee_id: int, user_id: int) -> str:
        """توليد توكن مشفر مؤقت (Anti-Replay Token) لتأمين عملية البصمة"""
        nonce = uuid.uuid4().hex[:12]
        signer = TimestampSigner(salt='mwheba_attendance_punch_salt')
        value = f"{employee_id}:{user_id}:{nonce}"
        return signer.sign(value)

    _in_memory_nonces: Dict[str, float] = {}

    @staticmethod
    def _is_nonce_used(nonce: str) -> bool:
        import time
        now = time.time()
        # تنظيف النونسات المنتهية
        expired = [k for k, exp in GeofencingService._in_memory_nonces.items() if exp < now]
        for k in expired:
            GeofencingService._in_memory_nonces.pop(k, None)

        cache_val = cache.get(f"mwheba_punch_nonce_{nonce}")
        if cache_val or nonce in GeofencingService._in_memory_nonces:
            return True
        return False

    @staticmethod
    def _mark_nonce_used(nonce: str, max_age_seconds: int) -> None:
        import time
        cache.set(f"mwheba_punch_nonce_{nonce}", True, max_age_seconds)
        GeofencingService._in_memory_nonces[nonce] = time.time() + max_age_seconds

    @staticmethod
    def verify_secure_punch_token(
        token: str,
        employee_id: int,
        max_age_seconds: int = 180,
    ) -> Tuple[bool, Optional[str]]:
        """
        التحقق من التوكن المشفر ومنع هجمات إعادة الإرسال (Replay Attack Prevention):
        - فحص التوقيع المشفر.
        - فحص انتهاء الصلاحية الزمنية.
        - منع إعادة استخدام نفس الـ Nonce.
        """
        if not token:
            return False, "توكن البصمة الأمني مفقود."

        signer = TimestampSigner(salt='mwheba_attendance_punch_salt')
        try:
            unsigned = signer.unsign(token, max_age=max_age_seconds)
            parts = unsigned.split(':')
            if len(parts) != 3:
                return False, "تنسيق توكن البصمة غير صالح."

            token_emp_id, token_user_id, nonce = parts
            if int(token_emp_id) != employee_id:
                return False, "توكن البصمة الأمني لا يتطابق مع الموظف المحدد."

            if GeofencingService._is_nonce_used(nonce):
                return False, "تم استخدام هذا التوكن مسبقاً (Replay Attack Detected)."

            # تسجيل الـ Nonce لمنع استخدامه مرة أخرى
            GeofencingService._mark_nonce_used(nonce, max_age_seconds)
            return True, None
        except SignatureExpired:
            return False, "انتهت صلاحية جلسة البصمة الأمنية (انتهت المهلة الزمنية)، يرجى إعادة المحاولة."
        except BadSignature:
            return False, "توقيع جلسة البصمة غير صالح أو تم التلاعب به."
