# -*- coding: utf-8 -*-
"""
Driver Authorization Service - خدمة حوكمة تفويض سائق النقل الخارجي وسند البوابة
مسؤول عن:
1. التحقق من وجود صورة تفويض الاستلام الرسمي (driver_authorization_doc) وبيانات السائق ورقم اللوحة.
2. استثناء تشغيلات العينات التجريبية (is_pilot_run) من إلزامية التفويض الورقي.
3. حماية المصنع من الطعن بإنكار الاستلام أمام المحاكم التجارية.
"""
import logging
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from sale.models.sales_models import DeliveryNote

logger = logging.getLogger(__name__)


class DriverAuthorizationService:
    """
    خدمة التحقق والتدقيق من تفويضات استلام البضاعة من بوابات ومخازن المصنع
    """

    @classmethod
    def validate_driver_authorization(cls, delivery_note: DeliveryNote, is_strict: bool = True) -> bool:
        """
        التحقق من استيفاء بيانات وتفويض السائق الخارجي قبل خروج البضاعة
        """
        # استثناء العينات التجريبية
        if getattr(delivery_note, 'is_pilot_run', False):
            return True

        # في عقود التقسيط والتوريد بالاستدعاء، التفويض إلزامي
        is_installment = False
        if hasattr(delivery_note, 'sales_order') and delivery_note.sales_order:
            # فحص فواتير أمر البيع
            invoices = delivery_note.sales_order.invoices.all() if hasattr(delivery_note.sales_order, 'invoices') else []
            is_installment = any(getattr(inv, 'is_installment_sale', False) for inv in invoices)

        if not is_installment and not is_strict:
            return True

        errors = []
        if not delivery_note.driver_name or not delivery_note.driver_name.strip():
            errors.append(_("يجب تسجيل اسم السائق الرباعي المستلم للبضاعة."))

        if not delivery_note.truck_plate_number or not delivery_note.truck_plate_number.strip():
            errors.append(_("يجب تسجيل رقم لوحة شاحنة النقل."))

        if is_strict and not delivery_note.driver_authorization_doc:
            errors.append(_("يجب إرفاق صورة تفويض الاستلام الرسمي الصادر من العميل للسائق لمنع الإنكار القضائي."))

        if errors:
            raise ValidationError(" - ".join(str(e) for e in errors))

        return True
