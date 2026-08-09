"""
Purchase Views Package
تقسيم views المشتريات إلى ملفات منفصلة لسهولة الصيانة
"""

# Purchase Invoice Views
from .purchase_views import (
    purchase_list,
    purchase_create,
    purchase_detail,
    purchase_update,
    purchase_delete,
    purchase_print,
    purchase_pdf_download,
    purchase_email_pdf,
    purchase_duplicate,
    allocate_supplier_prepaid_balance,
)

# Payment Views
from .payment_views import (
    payment_detail,
    add_payment,
    post_payment,
    unpost_payment,
    edit_payment,
    unpost_payment_only,
    delete_payment,
)

# Return Views
from .return_views import (
    purchase_return,
    purchase_return_list,
    purchase_return_detail,
    purchase_return_confirm,
    purchase_return_cancel,
)

# GRN Views
from .grn_views import (
    grn_list,
    grn_create,
    grn_detail,
    grn_submit,
    grn_approve,
    grn_post,
    grn_reverse,
)

# Landed Cost Views
from .landed_cost_views import (
    landed_cost_list,
    landed_cost_create,
)

# API Views
from .api_views import (
    get_supplier_type_api,
    ajax_create_product,
    ajax_get_form_data,
)

__all__ = [
    # Purchase Invoice Views
    'purchase_list',
    'purchase_create',
    'purchase_detail',
    'purchase_update',
    'purchase_delete',
    'purchase_print',
    'purchase_pdf_download',
    'purchase_email_pdf',
    'purchase_duplicate',
    'allocate_supplier_prepaid_balance',
    # Payment Views
    'payment_detail',
    'add_payment',
    'post_payment',
    'unpost_payment',
    'edit_payment',
    'unpost_payment_only',
    'delete_payment',
    # Return Views
    'purchase_return',
    'purchase_return_list',
    'purchase_return_detail',
    'purchase_return_confirm',
    'purchase_return_cancel',
    # GRN Views
    'grn_list',
    'grn_create',
    'grn_detail',
    'grn_submit',
    'grn_approve',
    'grn_post',
    'grn_reverse',
    # Landed Cost Views
    'landed_cost_list',
    'landed_cost_create',
    # API Views
    'get_supplier_type_api',
    'ajax_create_product',
    'ajax_get_form_data',
]
