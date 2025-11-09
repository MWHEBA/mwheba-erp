"""
# تخصيص قيود معدل الطلبات (Throttling) للنقاط النهائية المختلفة في النظام
"""
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle


class BurstRateThrottle(UserRateThrottle):
    """
    # تحديد معدل طلبات مرتفع للأوقات القصيرة للمستخدمين المسجلين
    """

    scope = "burst"
    rate = "60/min"


class SustainedRateThrottle(UserRateThrottle):
    """
    # تحديد معدل طلبات منخفض للأوقات الطويلة للمستخدمين المسجلين
    """

    scope = "sustained"
    rate = "1000/day"


class LoginRateThrottle(AnonRateThrottle):
    """
    # تحديد معدل طلبات تسجيل الدخول للمستخدمين غير المسجلين لمنع هجمات القوة الغاشمة
    """

    scope = "login"
    rate = "5/min"


class RegisterRateThrottle(AnonRateThrottle):
    """
    # تحديد معدل طلبات التسجيل للمستخدمين غير المسجلين
    """

    scope = "register"
    rate = "3/hour"


class ImportExportRateThrottle(UserRateThrottle):
    """
    # تحديد معدل طلبات الاستيراد والتصدير للمستخدمين المسجلين
    """

    scope = "import_export"
    rate = "10/hour"


class ReportRateThrottle(UserRateThrottle):
    """
    # تحديد معدل طلبات التقارير للمستخدمين المسجلين
    """

    scope = "report"
    rate = "30/hour"


# ✅ إضافة Throttling للـ JWT Token endpoints للحماية من Brute Force
class TokenObtainThrottle(AnonRateThrottle):
    """
    # تحديد معدل طلبات الحصول على Token - حماية من Brute Force
    """
    
    scope = "token_obtain"
    rate = "5/min"


class TokenRefreshThrottle(AnonRateThrottle):
    """
    # تحديد معدل طلبات تحديث Token
    """
    
    scope = "token_refresh"
    rate = "10/min"


class TokenVerifyThrottle(AnonRateThrottle):
    """
    # تحديد معدل طلبات التحقق من Token
    """
    
    scope = "token_verify"
    rate = "20/min"
