"""
Text sanitization and normalization utilities for MWHEBA ERP.
Provides robust text sanitizing to ensure security, database integrity,
and clean Arabic/English typography across transactional document lines.
"""

import re
from typing import Any
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

# Regex to strip non-printable ASCII control characters except tab (\t) and newline (\n)
CONTROL_CHAR_REGEX = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def normalize_line_details(value: Any, max_length: int = 2000, row_index: int = None) -> str:
    """
    Normalizes and validates transactional line details/specifications.

    Rules:
    1. None or empty string returns empty string ("").
    2. Non-string types (except None) raise a ValidationError.
    3. Normalizes all newline variants (\\r\\n, \\r) to \\n.
    4. Strips dangerous ASCII control characters while strictly preserving
       Arabic Unicode text, diacritics (تشكيل), numbers, and standard punctuation.
    5. Strips outer leading/trailing whitespace.
    6. Enforces length <= max_length (default 2000 characters).

    :param value: Raw input value from forms, API, or data conversions.
    :param max_length: Maximum allowed character count (default 2000).
    :param row_index: Optional 1-indexed row number for clear validation feedback.
    :return: Clean, normalized string ready for storage.
    :raises ValidationError: If value is non-string or exceeds max_length.
    """
    if value is None:
        return ""

    if not isinstance(value, str):
        error_msg = _("صيغة تفاصيل البند غير صالحة، يجب أن تكون نصاً.")
        if row_index is not None:
            error_msg = _("صيغة تفاصيل البند في السطر %(row)s غير صالحة، يجب أن تكون نصاً.") % {"row": row_index}
        raise ValidationError(error_msg)

    # تنظيف المسافات الخارجية وتوحيد فواصل الأسطر
    text = value.strip()
    if not text:
        return ""

    # توحيد نهايات الأسطر
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # إزالة أحرف التحكم الضارة مع الحفاظ على الأسطر وعلامات التبويب واليونيكود العربي
    text = CONTROL_CHAR_REGEX.sub("", text)

    # التحقق من الحد الأقصى للأحرف
    if len(text) > max_length:
        error_msg = _("تفاصيل البند تتجاوز الحد الأقصى المسموح به (%(max)s حرف). الحجم الحالي: %(curr)s حرف.") % {
            "max": max_length,
            "curr": len(text),
        }
        if row_index is not None:
            error_msg = _("تفاصيل البند في السطر %(row)s تتجاوز الحد الأقصى المسموح به (%(max)s حرف). الحجم الحالي: %(curr)s حرف.") % {
                "row": row_index,
                "max": max_length,
                "curr": len(text),
            }
        raise ValidationError(error_msg)

    return text
