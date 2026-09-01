from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

from printing_pricing.models.order import PrintingOrder, SupplementalRemake
from supplier.models import Supplier


class SupplementalRemakeService:
    """
    خدمة إدارة أوامر إعادة التشغيل التكميلية للمرتجعات الجزئية وتحميل خسائر COPQ
    (Supplemental Remake & Defect Fault Allocation Service)
    """

    @classmethod
    @transaction.atomic
    def create_remake_order(
        cls,
        order: PrintingOrder,
        defective_quantity: int,
        fault_party: str,
        reason: str,
        responsible_supplier: Supplier = None,
        estimated_copq: Decimal = Decimal('0.00')
    ) -> SupplementalRemake:
        """
        إصدار أمر إعادة تشغيل تكميلي
        """
        if defective_quantity <= 0:
            raise ValidationError(str(_("الكمية المعيبة يجب أن تكون أكبر من الصفر.")))

        # توليد رقم تسلسلي لأمر التعويض
        today_str = timezone.now().strftime('%y%m%d')
        remake_count = SupplementalRemake.objects.filter(order=order).count() + 1
        remake_num = f"RMK-{today_str}-{order.id}-{remake_count}"

        remake = SupplementalRemake.objects.create(
            order=order,
            remake_number=remake_num,
            defective_quantity=defective_quantity,
            fault_allocation=fault_party,
            responsible_supplier=responsible_supplier,
            estimated_copq=estimated_copq,
            reason=reason,
            status=SupplementalRemake.RemakeStatus.PENDING
        )
        return remake

    @classmethod
    def get_order_remakes(cls, order: PrintingOrder):
        """جلب أوامر إعادة التشغيل المرتبطة بالأوردر"""
        return SupplementalRemake.objects.filter(order=order).order_by('-created_at')

    @classmethod
    def get_order_total_copq(cls, order: PrintingOrder) -> Decimal:
        """احتساب إجمالي تكلفة الهادر الغارق (COPQ) الناتجة عن المرتجعات والتوالف"""
        remakes = cls.get_order_remakes(order)
        return sum((r.estimated_copq for r in remakes), Decimal('0.00'))
