from typing import Dict, Any, List
from django.utils.translation import gettext_lazy as _
from ..models import PrintingOrder, PriceAuditLog


class PriceAuditService:
    """
    خدمة تسجيل واسترجاع سجل التدقيق المالي لتغيرات أسعار وتكاليف المقايسات
    """

    @classmethod
    def log_price_change(
        cls,
        order: PrintingOrder,
        field_name: str,
        old_value: Any,
        new_value: Any,
        reason: str = "",
        user=None
    ) -> Dict[str, Any]:
        """
        تسجيل قيد في سجل تدقيق الأسعار
        """
        try:
            log_entry = PriceAuditLog.objects.create(
                order=order,
                field_name=field_name,
                old_value=str(old_value),
                new_value=str(new_value),
                change_reason=reason,
                changed_by=user,
                created_by=user
            )

            return {
                'success': True,
                'log_id': log_entry.id,
                'field_name': field_name,
                'old_value': str(old_value),
                'new_value': str(new_value),
                'reason': reason
            }
        except Exception as e:
            return {'success': False, 'error': str(e), 'details': _('خطأ في تسجيل تدقيق السعر')}

    @classmethod
    def get_order_audit_trail(cls, order: PrintingOrder) -> Dict[str, Any]:
        """
        استرجاع سجل التدقيق المالي الكامل لأمر التسعير
        """
        logs = order.price_audit_logs.filter(is_active=True).select_related('changed_by')
        trail = []

        for item in logs:
            trail.append({
                'id': item.id,
                'field_name': item.field_name,
                'old_value': item.old_value,
                'new_value': item.new_value,
                'change_reason': item.change_reason,
                'changed_by': item.changed_by.get_full_name() or item.changed_by.username if item.changed_by else _('النظام'),
                'created_at': item.created_at.strftime('%Y-%m-%d %H:%M') if item.created_at else None
            })

        return {
            'success': True,
            'order_id': order.id,
            'order_number': order.order_number,
            'logs_count': len(trail),
            'audit_trail': trail
        }
