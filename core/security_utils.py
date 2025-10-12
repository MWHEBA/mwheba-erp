"""
أدوات الأمان المشتركة
"""
import logging
import hashlib
import re
from typing import Any, Dict
from django.http import JsonResponse
from django.conf import settings

logger = logging.getLogger(__name__)


def safe_error_response(
    error: Exception, user_message: str = "حدث خطأ غير متوقع"
) -> JsonResponse:
    """
    إرجاع استجابة خطأ آمنة بدون تسريب معلومات حساسة

    Args:
        error: الاستثناء الذي حدث
        user_message: رسالة آمنة للمستخدم

    Returns:
        JsonResponse: استجابة JSON آمنة
    """
    # تسجيل الخطأ الكامل في السجلات
    logger.error(f"Application error: {str(error)}", exc_info=True)

    # إرجاع رسالة عامة للمستخدم
    response_data = {"success": False, "message": user_message}

    # في وضع التطوير فقط، يمكن إضافة تفاصيل إضافية
    if settings.DEBUG:
        response_data["debug_info"] = str(error)

    return JsonResponse(response_data, status=500)


def secure_hash(data: str, algorithm: str = "sha256") -> str:
    """
    إنشاء hash آمن للبيانات

    Args:
        data: البيانات المراد تشفيرها
        algorithm: خوارزمية التشفير (sha256, sha512)

    Returns:
        str: Hash آمن
    """
    if algorithm == "sha256":
        return hashlib.sha256(data.encode()).hexdigest()
    elif algorithm == "sha512":
        return hashlib.sha512(data.encode()).hexdigest()
    else:
        raise ValueError(f"Unsupported hashing algorithm: {algorithm}")


def safe_html_clean(html_content: str) -> str:
    """
    تنظيف HTML بطريقة آمنة

    Args:
        html_content: محتوى HTML

    Returns:
        str: محتوى HTML نظيف
    """
    if not html_content:
        return ""

    # إزالة النصوص البرمجية بطريقة آمنة
    clean_content = re.sub(
        r"<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>",
        "",
        html_content,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # إزالة الأحداث المضمنة
    clean_content = re.sub(r' on\w+="[^"]*"', "", clean_content, flags=re.IGNORECASE)
    clean_content = re.sub(r" on\w+='[^']*'", "", clean_content, flags=re.IGNORECASE)

    # إزالة إطارات iframe
    clean_content = re.sub(
        r"<iframe\b[^<]*(?:(?!<\/iframe>)<[^<]*)*<\/iframe>",
        "",
        clean_content,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # إزالة object و embed
    clean_content = re.sub(
        r"<(object|embed)\b[^>]*>.*?</\1>",
        "",
        clean_content,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # إزالة javascript: URLs
    clean_content = re.sub(
        r'javascript:[^"\']*', "", clean_content, flags=re.IGNORECASE
    )

    return clean_content


def validate_input(data: Any, field_name: str, max_length: int = None) -> bool:
    """
    التحقق من صحة المدخلات

    Args:
        data: البيانات المراد التحقق منها
        field_name: اسم الحقل
        max_length: الحد الأقصى للطول

    Returns:
        bool: True إذا كانت البيانات صحيحة
    """
    if data is None:
        return False

    if isinstance(data, str):
        if max_length and len(data) > max_length:
            logger.warning(
                f"Input too long for field {field_name}: {len(data)} > {max_length}"
            )
            return False

        # فحص الأحرف الضارة
        dangerous_patterns = [
            r"<script",
            r"javascript:",
            r"vbscript:",
            r"onload=",
            r"onerror=",
            r"onclick=",
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, data, re.IGNORECASE):
                logger.warning(
                    f"Dangerous pattern found in field {field_name}: {pattern}"
                )
                return False

    return True


class SecureExceptionHandler:
    """
    معالج آمن للاستثناءات
    """

    @staticmethod
    def handle_view_exception(view_name: str, error: Exception) -> JsonResponse:
        """
        معالجة استثناءات Views بطريقة آمنة
        """
        error_messages = {
            "PermissionError": "ليس لديك صلاحية للوصول لهذا المورد",
            "ValidationError": "البيانات المدخلة غير صحيحة",
            "IntegrityError": "تعارض في البيانات",
            "DoesNotExist": "العنصر المطلوب غير موجود",
            "MultipleObjectsReturned": "تم العثور على عدة عناصر",
            "ValueError": "قيمة غير صحيحة",
            "TypeError": "نوع بيانات غير صحيح",
        }

        error_type = type(error).__name__
        user_message = error_messages.get(error_type, "حدث خطأ غير متوقع")

        logger.error(
            f"Error in view {view_name}: {error_type} - {str(error)}", exc_info=True
        )

        return JsonResponse(
            {
                "success": False,
                "message": user_message,
                "error_code": error_type.lower(),
            },
            status=500,
        )
