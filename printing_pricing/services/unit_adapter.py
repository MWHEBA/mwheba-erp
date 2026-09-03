"""
Printing Unit Adapter
محول الوحدات الصناعي الصارم لتسعير المطبوعات ومطابقتها مع نماذج الموردين.
يحمي النظام من أخطاء ضرب كميات الأفرخ في أسعار الطن أو المتر المربع أو الرزمة.
"""
from decimal import Decimal, ROUND_UP
import math
from typing import Optional, Any
from supplier.models import SupplierService


class PrintingUnitAdapter:
    """
    محول فيزيائي يربط مواصفات ومقاسات الشغلانة بالوحدة المحددة في معادلة تسعير المورد (pricing_formula).
    """

    @staticmethod
    def normalize_quantity(
        service: Optional[SupplierService],
        raw_qty: Any,
        width_cm: Optional[Any] = None,
        height_cm: Optional[Any] = None,
        gsm: Optional[Any] = None,
        pages: Optional[Any] = None,
        pages_per_sig: Optional[Any] = 16,
        is_packaging_sheet: bool = False
    ) -> Decimal:
        """
        تحويل الكمية الخام من مقايسة المطبوعات إلى الكمية القياسية المكافئة لوحدة تسعير المورد.
        """
        if not service:
            return Decimal(str(raw_qty or 1))

        formula = getattr(service, 'pricing_formula', 'PER_PIECE')
        qty = Decimal(str(raw_qty or 1))

        if formula == 'PER_TON':
            # التحويل من عدد الأفرخ إلى أطنان
            # وزن الفرخ (كجم) = (الطول_سم * العرض_سم * الجراماج) / 10,000,000
            # إجمالي الوزن (طن) = (عدد الأفرخ * وزن الفرخ_كجم) / 1,000
            if width_cm and height_cm and gsm:
                w = Decimal(str(width_cm))
                h = Decimal(str(height_cm))
                g = Decimal(str(gsm))
                sheet_weight_kg = (w * h * g) / Decimal('10000000')
                total_tons = (qty * sheet_weight_kg) / Decimal('1000')
                return total_tons.quantize(Decimal('0.0001'), rounding=ROUND_UP)
            return qty

        elif formula == 'PER_SQM':
            # التحويل إلى متر مربع
            # المساحة (م2) = (الطول_سم * العرض_سم / 10,000) * عدد القطع أو الأفرخ
            if width_cm and height_cm:
                w = Decimal(str(width_cm))
                h = Decimal(str(height_cm))
                sqm_per_unit = (w * h) / Decimal('10000')
                total_sqm = qty * sqm_per_unit
                return total_sqm.quantize(Decimal('0.01'), rounding=ROUND_UP)
            return qty

        elif formula == 'PER_THOUSAND':
            # التحويل إلى آلاف السحبات (تراجات)
            # 1,000 سحبة = 1 تراج
            thousands = qty / Decimal('1000.00')
            return thousands.quantize(Decimal('0.001'), rounding=ROUND_UP)

        elif formula == 'PER_REAM':
            # التحويل إلى رزم مقفولة أو كسور رزم
            pack_size = Decimal(str(getattr(service, 'sheets_per_pack', 500) or 500))
            reams = qty / pack_size
            return reams.quantize(Decimal('0.01'), rounding=ROUND_UP)

        elif formula == 'PER_SIGNATURE':
            # التحويل إلى عدد الملازم
            sig_pages = Decimal(str(pages_per_sig or 16))
            total_p = Decimal(str(pages or 1))
            total_sigs = math.ceil(float(total_p / sig_pages))
            # إجمالي الملازم للكمية = عدد الملازم في النسخة * عدد النسخ
            return (Decimal(str(total_sigs)) * qty).quantize(Decimal('1'), rounding=ROUND_UP)

        elif formula == 'FIXED_TOOLING':
            # فورمة أو كليشيه مقطوعية ثابتة
            return Decimal('1.00')

        # PER_PIECE أو PER_SHEET أو افتراضي
        return qty.quantize(Decimal('0.01'), rounding=ROUND_UP)
