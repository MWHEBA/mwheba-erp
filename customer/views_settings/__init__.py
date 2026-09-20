"""تصدير عروض إعدادات العملاء"""
from .customer_tier_views import (
    customer_tier_list,
    customer_tier_create,
    customer_tier_edit,
    customer_tier_delete,
    customer_tier_reorder,
    customer_tier_toggle_status,
    api_customer_tier_info,
)
from .payment_term_views import (
    payment_term_list,
    payment_term_create,
    payment_term_edit,
    payment_term_delete,
    payment_term_toggle_status,
    payment_term_quick_add,
)
from .general_settings_views import (
    customer_general_settings_view,
)
from .settings_index_views import (
    customer_settings_index,
)

__all__ = [
    "customer_tier_list",
    "customer_tier_create",
    "customer_tier_edit",
    "customer_tier_delete",
    "customer_tier_reorder",
    "customer_tier_toggle_status",
    "api_customer_tier_info",
    "payment_term_list",
    "payment_term_create",
    "payment_term_edit",
    "payment_term_delete",
    "payment_term_toggle_status",
    "payment_term_quick_add",
    "customer_general_settings_view",
    "customer_settings_index",
]
