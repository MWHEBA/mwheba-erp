# -*- coding: utf-8 -*-
"""
MWHEBA ERP - Legacy Sequence Analyzer Service
Extracts year and max sequence numbers from legacy historical records using Regex.
"""
import re
from typing import Tuple
from django.db import models
from django.utils import timezone


class LegacySequenceAnalyzer:
    """
    محلل البيانات والأرقام التسلسلية القديمة بـ Regex لتغذية الـ Seed تلقائياً
    """

    @classmethod
    def parse_legacy_number(cls, raw_number: str) -> Tuple[int, int]:
        """
        تحليل النص القديم واستخراج (السنة، الرقم التسلسلي)
        أمثلة:
        - "INV-20260803-0098" -> year=2026, sequence=98
        - "PO-2026-0015"     -> year=2026, sequence=15
        - "JE-0042"          -> year=current_year, sequence=42
        """
        current_year = timezone.now().year
        if not raw_number:
            return current_year, 0

        text = str(raw_number).strip()

        # 1. Search for YYYYMMDD or YYYY date string inside text
        date_match = re.search(r"(20\d{2})(?:(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01]))?", text)
        year = int(date_match.group(1)) if date_match else current_year

        # 2. Extract trailing numbers or numbers after hyphens
        digits_list = re.findall(r"\d+", text)
        if not digits_list:
            return year, 0

        # The actual sequence is usually the last group of digits
        last_digits = int(digits_list[-1])

        # If last digits is the 8-digit date itself (e.g. 20260803), fallback to 0
        if len(digits_list[-1]) == 8 and date_match and digits_list[-1] == date_match.group(0):
            last_digits = 0

        return year, last_digits

    @classmethod
    def get_max_legacy_seed(cls, model_class, field_name: str, year: int) -> int:
        """
        فحص السجلات الكائنة في قواعد البيانات واستخراج أعلى رقم لسنة محددة
        """
        if not model_class or not hasattr(model_class, 'objects'):
            return 0

        max_seq = 0
        try:
            # Query all non-empty number values
            filter_kwargs = {f"{field_name}__isnull": False}
            queryset = model_class.objects.filter(**filter_kwargs).values_list(field_name, flat=True)

            for raw_val in queryset:
                parsed_year, parsed_num = cls.parse_legacy_number(raw_val)
                if parsed_year == year and parsed_num > max_seq:
                    max_seq = parsed_num
        except Exception:
            max_seq = 0

        return max_seq
