# -*- coding: utf-8 -*-
"""
Delivery Block Service - خدمة حظر الصرف المخزني للتعثر وقفل مقاصة الشيكات
مسؤول عن:
1. فحص الأقساط المتأخرة للعميل وحظر اعتماد إذن التسليم (Warehouse Delivery Block) عند التعثر.
2. حظر صرف البضاعة أثناء فترة مقاصة الشيك بالبنك (Cheque Clearing Float Dispatch Lock) لحين تمام التحصيل.
3. إدارة استثناءات المدير المالي المعتمدة (CFO Delivery Override).
"""
import logging
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from sale.models.installments import InstallmentItem
from sale.models.sales_models import DeliveryNote

logger = logging.getLogger(__name__)


class DeliveryBlockService:
    """
    خدمة الرقابة على صرف وتسليم البضاعة من المخزن المرتبطة بعقود وأقساط المبيعات
    """

    @classmethod
    def check_delivery_allowed(cls, delivery_note: DeliveryNote, user, cfo_override: bool = False) -> tuple[bool, str]:
        """
        التحقق من إمكانية اعتماد إذن التسليم المخزني
        يرجع (is_allowed, reason)
        """
        # إذا كانت التشغيلة عينات تجريبية (Pilot Run) يتم تمريرها دون حظر
        if getattr(delivery_note, 'is_pilot_run', False):
            return True, _("تشغيلة عينات تجريبية معفاة من حظر التسليم.")

        customer = delivery_note.customer
        if not customer:
            return True, ""

        # فحص استثناء المدير المالي
        if cfo_override:
            if not (user.is_superuser or user.has_perm('sale.override_delivery_block')):
                raise ValidationError(_("غير مصرح لك بتجاوز حظر التسليم المخزني."))
            logger.warning(f"⚠️ تم تجاوز حظر التسليم لإذن الصرف {delivery_note.delivery_number} باستثناء معتمد من {user.username}")
            return True, _("تم التجاوز بموجب استثناء رسمي معتمد من الإدارة المالية.")

        # 1. فحص وجود أقساط متأخرة تجاوزت فترة السماح للعميل (Overdue Check)
        overdue_items = InstallmentItem.objects.filter(
            plan__customer=customer,
            cash_status=InstallmentItem.CashStatus.OVERDUE,
        ).select_related('plan__sale')

        if overdue_items.exists():
            first_overdue = overdue_items.first()
            sale_num = first_overdue.plan.sale.number
            reason = _(f"العميل محظور من استلام بضاعة جديدة لوجود قسط متأخر غير مسدد (قسط #{first_overdue.installment_number} بفاتورة {sale_num}).")
            # تحديث حقل الحظر بالفاتورة
            delivery_note.sales_order.delivery_notes.filter(pk=delivery_note.pk).update(status='DRAFT')
            first_overdue.plan.sale.delivery_blocked_on_overdue = True
            first_overdue.plan.sale.save(update_fields=['delivery_blocked_on_overdue'])
            return False, reason

        # 2. فحص قفل مقاصة الشيك بالبنك (Clearing Float Dispatch Lock)
        # إذا كان إذن الصرف مرتبطاً بقسط مغطى بشيك ما زال تحت التحصيل ولم يحصل فعلياً
        if getattr(delivery_note, 'pk', None):
            linked_installments = getattr(delivery_note, 'linked_installments', None)
            if linked_installments and linked_installments.exists():
                for inst in linked_installments.all():
                    if inst.paper_coverage == InstallmentItem.PaperCoverage.BANK_DEPOSITED and inst.cash_status != InstallmentItem.CashStatus.COLLECTED:
                        reason = _(f"محظور صرف البضاعة: القسط #{inst.installment_number} مغطى بشيك تحت المقاصة البنكية ولم يتم تأكيد تحصيله بعد.")
                        return False, reason

        return True, ""

    @classmethod
    def enforce_delivery_dispatch_guard(cls, delivery_note: DeliveryNote, user, cfo_override: bool = False):
        """
        تطبيق الحظر الصارم بإطلاق ValidationError إذا كان التسليم محظوراً
        """
        allowed, reason = cls.check_delivery_allowed(delivery_note, user, cfo_override=cfo_override)
        if not allowed:
            raise ValidationError(reason)
