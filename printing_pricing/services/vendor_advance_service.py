from decimal import Decimal
from typing import Dict, Any, Optional
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.db import transaction
from ..models import PrintingOrder, OrderVendorAdvance
from supplier.models import Supplier


class VendorAdvanceService:
    """
    خدمة إدارة وتتبع دفعات وعرابين الموردين والورش
    """

    @classmethod
    def record_advance(
        cls,
        order: PrintingOrder,
        supplier: Supplier,
        amount: Decimal,
        payment_method: str = "CASH",
        reference_number: str = "",
        notes: str = "",
        user=None
    ) -> Dict[str, Any]:
        """
        تسجيل دفعة مقدمة / عربون لمورد أو ورشة وربطها بأمر الشغل
        """
        try:
            amt = Decimal(str(amount))
            if amt <= 0:
                return {
                    'success': False,
                    'error': _('مبلغ العربون يجب أن يكون أكبر من الصفر'),
                    'field': 'amount',
                    'code': 'INVALID_AMOUNT'
                }

            with transaction.atomic():
                advance = OrderVendorAdvance.objects.create(
                    order=order,
                    work_order=order.work_order,
                    supplier=supplier,
                    amount=amt,
                    payment_method=payment_method,
                    reference_number=reference_number,
                    notes=notes,
                    created_by=user,
                    updated_by=user
                )

            return {
                'success': True,
                'advance_id': advance.id,
                'amount': amt,
                'supplier_name': supplier.name,
                'order_number': order.order_number,
                'work_order_id': order.work_order_id if order.work_order else None,
                'message': _('تم تسجيل دفعة العربون بنجاح')
            }
        except Exception as e:
            return {'success': False, 'error': str(e), 'details': _('خطأ في تسجيل عربون المورد')}

    @classmethod
    def get_advances_summary(cls, order: PrintingOrder) -> Dict[str, Any]:
        """
        الحصول على ملخص العرابين والدفعات المسددة للموردين تحت أمر التسعير
        """
        advances = order.vendor_advances.filter(is_active=True).select_related('supplier')
        
        total_advances = Decimal('0.00')
        settled_advances = Decimal('0.00')
        unsettled_advances = Decimal('0.00')
        advances_list = []

        for adv in advances:
            total_advances += adv.amount
            if adv.is_settled:
                settled_advances += adv.amount
            else:
                unsettled_advances += adv.amount
            
            advances_list.append({
                'id': adv.id,
                'supplier_id': adv.supplier_id,
                'supplier_name': adv.supplier.name,
                'amount': float(adv.amount),
                'payment_method': adv.payment_method,
                'reference_number': adv.reference_number,
                'is_settled': adv.is_settled,
                'created_at': adv.created_at.strftime('%Y-%m-%d %H:%M') if adv.created_at else None
            })

        return {
            'success': True,
            'order_id': order.id,
            'order_number': order.order_number,
            'total_advances': total_advances,
            'settled_advances': settled_advances,
            'unsettled_advances': unsettled_advances,
            'advances_count': len(advances_list),
            'advances': advances_list
        }

    @classmethod
    def settle_advance(cls, advance: OrderVendorAdvance, notes: str = "", user=None) -> Dict[str, Any]:
        """
        تسوية دفعة العربون مع فاتورة المورد النهائية
        """
        if advance.is_settled:
            return {'success': False, 'error': _('تمت تسوية هذا العربون مسبقاً')}

        advance.is_settled = True
        advance.settled_at = timezone.now()
        if notes:
            advance.notes = f"{advance.notes or ''}\n[تسوية]: {notes}".strip()
        if user:
            advance.updated_by = user
        advance.save()

        return {
            'success': True,
            'advance_id': advance.id,
            'is_settled': True,
            'settled_at': advance.settled_at.strftime('%Y-%m-%d %H:%M'),
            'message': _('تمت تسوية العربون بنجاح')
        }
