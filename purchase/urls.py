from django.urls import path
from .views import (
    # Purchase Invoice Views
    purchase_list,
    purchase_create,
    purchase_detail,
    purchase_update,
    purchase_delete,
    purchase_print,
    purchase_duplicate,
    # Payment Views
    payment_detail,
    add_payment,
    post_payment,
    unpost_payment,
    edit_payment,
    unpost_payment_only,
    delete_payment,
    # Return Views
    purchase_return,
    purchase_return_list,
    purchase_return_detail,
    purchase_return_confirm,
    purchase_return_cancel,
    # API Views
    get_supplier_type_api,
    ajax_create_product,
    ajax_get_form_data,
)

app_name = "purchase"

urlpatterns = [
    # فواتير المشتريات
    path("", purchase_list, name="purchase_list"),
    path("create/", purchase_create, name="purchase_create"),
    path("create/supplier/<int:supplier_id>/", purchase_create, name="purchase_create_for_supplier"),
    # API - يجب أن يكون قبل patterns الـ <int:pk>
    path("api/supplier-type/<int:supplier_id>/", get_supplier_type_api, name="supplier_type_api"),
    path("api/create-product/", ajax_create_product, name="ajax_create_product"),
    path("api/form-data/", ajax_get_form_data, name="ajax_form_data"),
    path("<int:pk>/", purchase_detail, name="purchase_detail"),
    path("<int:pk>/edit/", purchase_update, name="purchase_edit"),
    path("<int:pk>/delete/", purchase_delete, name="purchase_delete"),
    path("<int:pk>/print/", purchase_print, name="purchase_print"),
    path("<int:pk>/duplicate/", purchase_duplicate, name="purchase_duplicate"),
    # المدفوعات
    path("<int:pk>/add-payment/", add_payment, name="purchase_add_payment"),
    path("payments/<int:pk>/", payment_detail, name="payment_detail"),
    path("payments/<int:payment_id>/post/", post_payment, name="post_payment"),
    path(
        "payments/<int:payment_id>/unpost/", unpost_payment, name="unpost_payment"
    ),
    path("payments/<int:payment_id>/edit/", edit_payment, name="edit_payment"),
    path("payments/<int:payment_id>/delete/", delete_payment, name="delete_payment"),
    path(
        "payments/<int:payment_id>/unpost-only/",
        unpost_payment_only,
        name="unpost_payment_only",
    ),
    # مرتجعات المشتريات
    path("<int:pk>/return/", purchase_return, name="purchase_return"),
    path("returns/", purchase_return_list, name="purchase_return_list"),
    path(
        "returns/<int:pk>/", purchase_return_detail, name="purchase_return_detail"
    ),
    path(
        "returns/<int:pk>/confirm/",
        purchase_return_confirm,
        name="purchase_return_confirm",
    ),
    path(
        "returns/<int:pk>/cancel/",
        purchase_return_cancel,
        name="purchase_return_cancel",
    ),
]
