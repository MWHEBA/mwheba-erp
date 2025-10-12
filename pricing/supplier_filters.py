"""
دوال مساعدة لتصفية الموردين في نظام التسعير
"""

from supplier.models import Supplier


def get_printing_suppliers(order_type=None):
    """جلب موردي الطباعة المفلترين حسب نوع الطلب"""
    try:
        from supplier.models import OffsetPrintingDetails, DigitalPrintingDetails

        if order_type == "offset":
            # موردين لديهم خدمات أوفست فقط
            supplier_ids = (
                OffsetPrintingDetails.objects.filter(service__is_active=True)
                .values_list("service__supplier_id", flat=True)
                .distinct()
            )

        elif order_type == "digital":
            # موردين لديهم خدمات ديجيتال فقط
            supplier_ids = (
                DigitalPrintingDetails.objects.filter(service__is_active=True)
                .values_list("service__supplier_id", flat=True)
                .distinct()
            )

        else:
            # موردين لديهم أي نوع من خدمات الطباعة
            offset_ids = OffsetPrintingDetails.objects.filter(
                service__is_active=True
            ).values_list("service__supplier_id", flat=True)

            digital_ids = DigitalPrintingDetails.objects.filter(
                service__is_active=True
            ).values_list("service__supplier_id", flat=True)

            supplier_ids = list(set(list(offset_ids) + list(digital_ids)))

        return Supplier.objects.filter(id__in=supplier_ids, is_active=True).order_by(
            "name"
        )

    except Exception as e:
        # في حالة الخطأ، إرجاع جميع الموردين النشطين
        return Supplier.objects.filter(is_active=True).order_by("name")


def get_ctp_suppliers():
    """جلب موردي الزنكات CTP"""
    try:
        from supplier.models import PlateServiceDetails

        # موردين لديهم خدمات زنكات نشطة
        supplier_ids = (
            PlateServiceDetails.objects.filter(service__is_active=True)
            .values_list("service__supplier_id", flat=True)
            .distinct()
        )

        return Supplier.objects.filter(id__in=supplier_ids, is_active=True).order_by(
            "name"
        )

    except Exception as e:
        # في حالة الخطأ، إرجاع جميع الموردين النشطين
        return Supplier.objects.filter(is_active=True).order_by("name")
