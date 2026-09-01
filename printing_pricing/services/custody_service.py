from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

from printing_pricing.models.order import DieMouldCustody, PrintingOrder
from supplier.models import Supplier
from customer.models import Customer


class DieMouldCustodyService:
    """
    خدمة تتبع وأرشفة عهدة فورمات التكسير، كليشيهات البصمة، وزنكات الأوفست
    (Die, Mould, and Tooling Custody Archive Service)
    """

    @classmethod
    def register_mould(
        cls,
        code: str,
        name: str,
        mould_type: str = DieMouldCustody.MouldType.DIE_CUT,
        customer: Customer = None,
        workshop: Supplier = None,
        storage_location: str = None,
        dimensions: str = None,
        notes: str = None
    ) -> DieMouldCustody:
        """تسجيل فورمة / كليشيه جديد في الأرشيف"""
        if DieMouldCustody.objects.filter(code=code).exists():
            raise ValidationError(str(_("كود الفورمة مسجل بالفعل مسبقاً.")))

        mould = DieMouldCustody.objects.create(
            code=code,
            name=name,
            mould_type=mould_type,
            customer=customer,
            current_workshop=workshop,
            storage_location=storage_location,
            dimensions=dimensions,
            notes=notes,
            status=DieMouldCustody.MouldStatus.ACTIVE
        )
        return mould

    @classmethod
    def record_usage(cls, mould: DieMouldCustody, order: PrintingOrder, hits: int) -> DieMouldCustody:
        """
        تسجيل استخدام وسحب على الفورمة / الكليشيه وفحص حد الصيانة (20,000 ضربة)
        """
        mould.hit_count += hits
        mould.last_used_order = order

        # إذا تجاوزت الضربات 20,000، نغير الحالة تلقائياً إلى صيانة
        if mould.hit_count >= 20000 and mould.status == DieMouldCustody.MouldStatus.ACTIVE:
            mould.status = DieMouldCustody.MouldStatus.MAINTENANCE
            mould.notes = (mould.notes or "") + "\n[تحذير آلي: تجاوزت الفورمة 20,000 ضربة وتتطلب تغيير حشايا ومجاري الريجة]."

        mould.save()
        return mould

    @classmethod
    def transfer_location(
        cls,
        mould: DieMouldCustody,
        to_workshop: Supplier,
        new_storage_location: str = None
    ) -> DieMouldCustody:
        """نقل عهدة الفورمة إلى ورشة أخرى"""
        mould.current_workshop = to_workshop
        if new_storage_location:
            mould.storage_location = new_storage_location
        mould.save()
        return mould
