# -*- coding: utf-8 -*-
"""
MWHEBA ERP - Sequence Formatter Service
Formats document number strings consistently ({prefix}-{year}-{number:05d}).
"""
import re


class SequenceFormatter:
    """
    مساعد تنسيق وصياغة أرقام المستندات الرسمية
    """

    @staticmethod
    def clean_prefix(prefix: str) -> str:
        """
        تنظيف البادئة وإزالة الفواصل والرموز الزائدة
        مثال: "inv-" -> "INV", "AP-INV" -> "AP", "GL-" -> "GL"
        """
        if not prefix:
            return "DOC"
        cleaned = str(prefix).strip().upper()
        # Remove hyphens, underscores and spaces
        cleaned = re.sub(r"[-_\s]+", "", cleaned)
        return cleaned if cleaned else "DOC"

    @classmethod
    def format_number(cls, prefix: str, year: int, number: int, padding: int = 4) -> str:
        """
        تنسيق الرقم القياسي الموحد بدون فواصل: PREFIX + YY + 0001
        مثال: GL260001, INV260001
        """
        cleaned_prefix = cls.clean_prefix(prefix)
        year_short = str(year)[-2:] if year else ""
        number_str = str(number).zfill(padding)
        return f"{cleaned_prefix}{year_short}{number_str}"

