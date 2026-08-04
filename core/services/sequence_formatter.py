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
        تنظيف البادئة ومنع التكرار والرموز الزائدة
        مثال: "inv-" -> "INV", "AP-INV-" -> "AP-INV"
        """
        if not prefix:
            return "DOC"
        cleaned = str(prefix).strip().upper()
        # Remove trailing hyphens or underscores
        cleaned = re.sub(r"[-_\s]+$", "", cleaned)
        cleaned = re.sub(r"^[-_\s]+", "", cleaned)
        return cleaned if cleaned else "DOC"

    @classmethod
    def format_number(cls, prefix: str, year: int, number: int, padding: int = 5) -> str:
        """
        تنسيق الرقم القياسي الموحد: PREFIX-YYYY-00001
        """
        cleaned_prefix = cls.clean_prefix(prefix)
        number_str = str(number).zfill(padding)
        return f"{cleaned_prefix}-{year}-{number_str}"
