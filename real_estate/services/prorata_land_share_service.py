# -*- coding: utf-8 -*-
"""
ProrataLandShareService - خدمة الحسابات الهندسية للحصة الشائعة في الأرض والمنافع المشتركة
MWHEBA ERP — Engineering Pro-Rata Land & Common Areas Share Calculator (Law 9/2022)
"""
import math
from decimal import Decimal
from typing import Dict, Any, Optional
from django.db.models import Sum
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from real_estate.models.unit import PropertyUnit
from real_estate.models.project import RealEstateProject


class ProrataLandShareService:
    """
    محرك الحسابات الهندسية وتحديد الحصص الشائعة في الأرض والأجزاء المشتركة
    طبقاً لأحكام القانون رقم 9 لسنة 2022 بتعديل قانون تنظيم الشهر العقاري
    """

    @classmethod
    def calculate_pro_rata_shares(
        cls,
        unit: PropertyUnit,
        project: Optional[RealEstateProject] = None
    ) -> Dict[str, Any]:
        """
        حساب الحصة الشائعة في أرض وبناء المشروع والأجزاء المشتركة:
        - المساحة الشائعة بالأمتار المربعة بدقة 4 أرقام عشرية.
        - النسبة المئوية الدقيقة.
        - الكسر الاعتيادي المبسط (Simplified Fraction).
        - التعبير القانوني التقليدي بالقيراط والسهم (من أصل 24 قيراط).
        - النص القانوني المصاغ والجاهز للدمج في عقود البيع المشهرة.
        """
        target_project = project or unit.project
        if not target_project:
            raise ValidationError(_("يجب ربط الوحدة بمشروع عقاري صالح لحساب الحصة الشائعة."))

        total_land = target_project.total_land_area
        if total_land <= Decimal('0.00'):
            raise ValidationError(
                _("مساحة أرض المشروع %(project)s غير محددة أو تساوي صفراً.") % {'project': target_project.name}
            )

        # تحديد المسطح البنائي الإجمالي للمشروع (GBA) أو مجموع مساحات الوحدات
        total_gba = target_project.gross_built_area
        if total_gba <= Decimal('0.00'):
            agg = PropertyUnit.objects.filter(project=target_project).aggregate(total=Sum('gross_area'))
            total_gba = agg.get('total') or Decimal('0.00')

        if total_gba <= Decimal('0.00'):
            raise ValidationError(
                _("إجمالي المساحة البنائية لمشروع %(project)s غير محددة أو تساوي صفراً.") % {'project': target_project.name}
            )

        unit_gross_area = unit.gross_area
        if unit_gross_area <= Decimal('0.00'):
            raise ValidationError(_("المساحة الإجمالية للوحدة العقارية يجب أن تكون أكبر من الصفر."))

        # 1. نسبة المشاركة الدقيقة (Share Ratio)
        share_ratio = unit_gross_area / total_gba
        percentage = (share_ratio * Decimal('100.00')).quantize(Decimal('0.0001'))

        # 2. الحصة الشائعة في الأرض بالأمتار المربعة (Sqm Land Share)
        land_share_sqm = (total_land * share_ratio).quantize(Decimal('0.0001'))

        # 3. الكسر الاعتيادي المبسط
        num = int(unit_gross_area * 100)
        denom = int(total_gba * 100)
        common_divisor = math.gcd(num, denom)
        simp_num = num // common_divisor
        simp_denom = denom // common_divisor
        fraction_str = f"{simp_num}/{simp_denom}"

        # 4. التعبير الشرعي والقانوني بالقراريط والأسهم (out of 24 Qirats)
        total_qirats = share_ratio * Decimal('24.00')
        qirat_int = int(total_qirats)
        remaining_qirat_fraction = total_qirats - Decimal(str(qirat_int))
        sahm_float = remaining_qirat_fraction * Decimal('24.00')
        sahm_val = round(float(sahm_float), 2)

        qirat_expression = f"{qirat_int} ط و {sahm_val} سهم من 24 قيراط"

        # 5. النص القانوني المعتمد طبقاً للقانون 9 لسنة 2022
        legal_clause_ar = (
            f"تمتلك الوحدة موضوع هذا العقد حصة شائعة في أرض وبناء العقار والأجزاء المشتركة "
            f"بنسبة مساحتها الإجمالية البالغة ({unit_gross_area:,.2f} م²) إلى إجمالي المسطح البنائي الإجمالي "
            f"للمشروع البالغ ({total_gba:,.2f} م²)، وهو ما يعادل حصة قدرها ({land_share_sqm} م²) "
            f"من إجمالي مساحة أرض المشروع البالغة ({total_land:,.2f} م²)، أي ما يوازي تعاقدياً بنسبة "
            f"({percentage}%) ({fraction_str})، وكذا حصة مماثلة في كافة الأجزاء والمنافع المشتركة والمرافق "
            f"الخدمية للبرج/المشروع، وذلك طبقاً لأحكام القانون رقم 9 لسنة 2022 بتعديل قانون تنظيم الشهر العقاري "
            f"والقانون المدني المصري."
        )

        return {
            'unit_code': unit.unit_code,
            'project_name': target_project.name,
            'unit_gross_area': unit_gross_area,
            'total_project_gba': total_gba,
            'total_land_area': total_land,
            'share_ratio': share_ratio,
            'percentage': percentage,
            'land_share_sqm': land_share_sqm,
            'fraction_str': fraction_str,
            'simplified_numerator': simp_num,
            'simplified_denominator': simp_denom,
            'qirat_expression': qirat_expression,
            'legal_clause_ar': legal_clause_ar,
        }
