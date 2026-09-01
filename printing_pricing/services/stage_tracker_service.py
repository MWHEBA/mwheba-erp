from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.apps import apps

from printing_pricing.models.order import PrintingOrder
from supplier.models import Supplier


class StageTrackerService:
    """
    خدمة تتبع موقع الشغل ومرحلته الحالية بدون تعقيد (الشغل فين دلوقتي؟)
    مع إمكانية تسجيل أجرة النقل/المشوار للمندوب كمورد تلقائياً
    """

    @classmethod
    @transaction.atomic
    def update_order_stage(
        cls,
        order: PrintingOrder,
        stage: str,
        workshop: Supplier = None,
        driver: Supplier = None,
        driver_fee: Decimal = Decimal('0.00'),
        notes: str = None,
        user = None
    ) -> dict:
        """
        تحديث موقع الشغل ومرحلته الحالية فوراً
        """
        # حفظ الموقع السابق قبل التحديث
        prev_location = (order.current_workshop.name if order.current_workshop else order.get_current_stage_display())
        
        order.current_stage = stage
        if workshop is not None:
            order.current_workshop = workshop
        order.save(update_fields=['current_stage', 'current_workshop', 'updated_at'])

        next_location = (order.current_workshop.name if order.current_workshop else order.get_current_stage_display())

        # تسجيل حركة النقل (مين اللي نقل، من فين، إلى فين، والأجرة)
        from printing_pricing.models.order import OrderTransportLog
        transport_log = OrderTransportLog.objects.create(
            order=order,
            from_location=prev_location,
            to_location=next_location,
            transporter=driver,
            cost=driver_fee,
            transfer_date=timezone.now(),
            notes=notes
        )

        created_po = None
        # إذا كان هناك سائق/مشوارجي وأجرة نقل، ننشئ له قيد فاتورة خدمة تلقائي كمورد
        if driver and driver_fee > Decimal('0.00'):
            Purchase = apps.get_model('purchase', 'Purchase')
            user_obj = user or order.created_by
            if not user_obj:
                User = apps.get_model('auth', 'User')
                user_obj = User.objects.first()

            today_str = timezone.now().strftime('%y%m%d')
            po_num = f"TRN-{today_str}-{order.id}-{driver.id}"

            # التحقق من عدم التكرار
            existing = Purchase.objects.filter(number=po_num).first()
            if not existing:
                created_po = Purchase.objects.create(
                    number=po_num,
                    date=timezone.now().date(),
                    status="confirmed",
                    supplier=driver,
                    subtotal=driver_fee,
                    discount=Decimal('0.00'),
                    tax=Decimal('0.00'),
                    tax_active=False,
                    wht_active=False,
                    total=driver_fee,
                    payment_method="credit",
                    payment_status="unpaid",
                    is_service=True,
                    service_type="transportation",
                    work_order=order.work_order,
                    created_by=user_obj,
                    notes=(
                        f"أجرة نقل ومشوار بين الورش:\n"
                        f"- أمر التسعير: {order.order_number}\n"
                        f"- من: {prev_location} إلى: {next_location}\n"
                        f"- ملاحظات: {notes or 'نقل خامات وشغل'}"
                    )
                )

        return {
            'success': True,
            'order_id': order.id,
            'order_number': order.order_number,
            'current_stage': order.current_stage,
            'current_stage_display': order.get_current_stage_display(),
            'from_location': prev_location,
            'to_location': next_location,
            'transporter_name': driver.name if driver else None,
            'cost': driver_fee,
            'transport_log_id': transport_log.id,
            'workshop_name': order.current_workshop.name if order.current_workshop else None,
            'driver_po_number': created_po.number if created_po else None,
            'message': _('تم تحديث موقع الشغل وتوثيق حركة النقل بنجاح.')
        }

