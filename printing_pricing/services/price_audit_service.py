import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


class PriceAuditService:
    """
    خدمة التدقيق المالي ومراجعة تعديلات الأسعار وهوامش الأرباح
    تسجل تاريخ التعديل والمستخدم والقيمة القديمة والجديدة والسبب لمنع التلاعب
    """
    @classmethod
    def log_price_change(cls, order, field_name: str, old_value, new_value, reason: str = '', user=None):
        """تسجيل تعديلات الأسعار وهوامش الأرباح في سجل المراجعة المالية"""
        order_identifier = getattr(order, 'order_number', None) or getattr(order, 'pk', 'New')
        user_name = getattr(user, 'username', 'System') if user else 'System'
        logger.info(
            f"Price audit for Order {order_identifier}: "
            f"Field '{field_name}' changed from {old_value} to {new_value} by {user_name}. "
            f"Reason: {reason or 'Manual override'}"
        )
