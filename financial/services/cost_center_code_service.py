# -*- coding: utf-8 -*-
"""
MWHEBA ERP - Cost Center Code Service
خدمة الترقيم التلقائي المتسلسل لمراكز التكلفة المحاسبية (شجري وهرمي ذكي وآمن).
"""
import re
from typing import Optional
from django.db import transaction


class CostCenterCodeService:
    """
    خدمة موحدة لحساب وتوليد وتأمين الترقيم التلقائي المتسلسل لمراكز التكلفة.
    """

    ROOT_STEP = 10
    ROOT_DEFAULT_START = 10

    @classmethod
    def sanitize_code(cls, code: Optional[str]) -> str:
        """تنظيف وتوحيد الكود"""
        if not code:
            return ""
        return str(code).strip().upper()

    @classmethod
    def get_next_root_code(cls) -> str:
        """
        حساب كود المركز الرئيسي التالي (المستوى 1 - بدون أب).
        يبدأ من 10، 20، 30... ويبحث عن أعلى رقم رئيسي لزيادته بـ 10.
        """
        from financial.models.cost_center import CostCenter

        # جلب أكواد المراكز الرئيسية فقط (التي ليس لها أب)
        root_codes = CostCenter.objects.filter(parent__isnull=True).values_list('code', flat=True)

        numeric_values = []
        for code in root_codes:
            cleaned = cls.sanitize_code(code)
            # استخراج الأرقام إذا كان الكود رقمياً خالصاً
            if cleaned.isdigit():
                numeric_values.append(int(cleaned))
            else:
                # محاولة استخراج الرقم لو كان مثل CC-01 أو CC-10
                match = re.search(r'\d+', cleaned)
                if match:
                    numeric_values.append(int(match.group(0)))

        if not numeric_values:
            next_num = cls.ROOT_DEFAULT_START
        else:
            max_val = max(numeric_values)
            # لو كانت الأكواد الحالية متسلسلة بالعشرات (10, 20) أو بالمئات (100, 200)
            if max_val >= cls.ROOT_DEFAULT_START:
                # نزيد بمقدار 10
                next_num = ((max_val // cls.ROOT_STEP) + 1) * cls.ROOT_STEP
            else:
                # لو كانت فردية 1, 2, 3.. نزيد 1 أو ننتقل للعشرات
                next_num = max_val + 1

        # التأكد التام من أن الكود المقترح غير موجود في أي مكان بقاعدة البيانات
        while CostCenter.objects.filter(code=str(next_num)).exists():
            next_num += cls.ROOT_STEP

        return str(next_num)

    @classmethod
    def get_next_child_code(cls, parent) -> str:
        """
        حساب كود المركز الفرعي التالي (تحت مركز أب).
        المعادلة: كود الأب + لاحقة تسلسلية من خانتين (01..99).
        مثال:
          - الأب 10 -> 1001, 1002, 1003...
          - الأب 1001 -> 100101, 100102...
          - الأب CC-HQ -> CC-HQ-01, CC-HQ-02...
        """
        from financial.models.cost_center import CostCenter

        if not parent:
            return cls.get_next_root_code()

        parent_code = cls.sanitize_code(parent.code)
        sibling_codes = CostCenter.objects.filter(parent=parent).values_list('code', flat=True)

        # استخراج اللواحق الرقمية للأبناء الحاليين
        suffix_numbers = []
        is_parent_numeric = parent_code.isdigit()

        for code in sibling_codes:
            cleaned = cls.sanitize_code(code)
            if is_parent_numeric:
                # كود الأب رقمي: نبحث عن تطابق البداية
                if cleaned.startswith(parent_code) and len(cleaned) > len(parent_code):
                    suffix = cleaned[len(parent_code):]
                    if suffix.isdigit():
                        suffix_numbers.append(int(suffix))
            else:
                # كود الأب نصي أو يحتوي فواصل مثل CC-HQ أو CC-01
                if cleaned.startswith(parent_code):
                    suffix = cleaned[len(parent_code):].lstrip('-_')
                    if suffix.isdigit():
                        suffix_numbers.append(int(suffix))

        if not suffix_numbers:
            next_seq = 1
        else:
            next_seq = max(suffix_numbers) + 1

        # بناء الكود والتأكد الحلقي من عدم وجوده مسبقاً
        while True:
            if is_parent_numeric:
                candidate = f"{parent_code}{next_seq:02d}"
            else:
                # بادئة نصية
                candidate = f"{parent_code}-{next_seq:02d}"

            if not CostCenter.objects.filter(code=candidate).exists():
                return candidate
            next_seq += 1

    @classmethod
    def get_next_code(cls, parent_id: Optional[int] = None) -> str:
        """
        واجهة برمجية موحدة لحساب الكود التالي بناءً على معرف الأب (أو None للمركز الرئيسي).
        """
        from financial.models.cost_center import CostCenter

        if parent_id:
            parent = CostCenter.objects.filter(id=parent_id).first()
            if parent:
                return cls.get_next_child_code(parent)

        return cls.get_next_root_code()

    @classmethod
    def generate_next_code(cls, parent=None) -> str:
        """
        توليد الكود التالي المحمي داخل Transaction لضمان الذرية ومنع التصادم.
        """
        with transaction.atomic():
            if parent:
                return cls.get_next_child_code(parent)
            return cls.get_next_root_code()
