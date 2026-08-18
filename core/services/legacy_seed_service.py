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
        - "INV260009"        -> year=2026, sequence=9  (الصيغة المدمجة الحديثة)
        - "INV-2026-0001"    -> year=2026, sequence=1
        - "INV-20260803-0098"-> year=2026, sequence=98
        - "PO20260819001"    -> year=2026, sequence=1
        - "PO-2026-0015"     -> year=2026, sequence=15
        - "JE-0042"          -> year=current_year, sequence=42
        """
        current_year = timezone.now().year
        if not raw_number:
            return current_year, 0

        text = str(raw_number).strip().upper()

        # 1. Match modern compact format: PREFIX + YY + (4 to 6 digits serial) e.g. INV260009, GL260001, AP260012
        compact_match = re.match(r"^[A-Z_-]+(\d{2})(\d{4,6})$", text)
        if compact_match:
            yy = int(compact_match.group(1))
            year = 2000 + yy
            seq = int(compact_match.group(2))
            return year, seq

        # 2. Match date-based compact format: PREFIX + YYYYMMDD + (3 to 5 digits) e.g. PO20260819001
        date_compact_match = re.match(r"^[A-Z_-]*(20\d{2})\d{4}(\d{3,5})$", text)
        if date_compact_match:
            year = int(date_compact_match.group(1))
            seq = int(date_compact_match.group(2))
            return year, seq

        # 3. Match dash/separator standard format: PREFIX-YYYY-NUMBER or PREFIX-YY-NUMBER
        dash_match = re.search(r"[-_](20\d{2}|\d{2})[-_](\d+)$", text)
        if dash_match:
            year_raw = dash_match.group(1)
            year = int(year_raw) if len(year_raw) == 4 else 2000 + int(year_raw)
            seq = int(dash_match.group(2))
            return year, seq

        # 4. Match full date format with dashes: PREFIX-YYYYMMDD-XXXX e.g. INV-20260803-0098
        date_match = re.search(r"(20\d{2})(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])[-_](\d+)", text)
        if date_match:
            year = int(date_match.group(1))
            seq = int(date_match.group(2))
            return year, seq

        # 5. Fallback: Search for 4-digit year and trailing digits
        year_match = re.search(r"(20\d{2})", text)
        year = int(year_match.group(1)) if year_match else current_year

        digits_list = re.findall(r"\d+", text)
        if not digits_list:
            return year, 0

        last_digits = int(digits_list[-1])
        # If last digits is a full date or timestamp (e.g. 20260803 or 20260809205840), fallback to 0
        if len(digits_list[-1]) >= 8 and digits_list[-1].startswith(str(year)):
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
