from django.urls import path
from . import views

app_name = "sale"

urlpatterns = [
    # فواتير المبيعات
    path("", views.sale_list, name="sale_list"),
    path("create/", views.sale_create, name="sale_create"),
    path("create/customer/<int:customer_id>/", views.sale_create, name="sale_create_for_customer"),
    path("<int:pk>/", views.sale_detail, name="sale_detail"),
    path("<int:pk>/edit/", views.sale_edit, name="sale_edit"),
    path("<int:pk>/delete/", views.sale_delete, name="sale_delete"),
    path("<int:pk>/print/", views.sale_print, name="sale_print"),
    path("<int:pk>/payment/", views.add_payment, name="sale_add_payment"),
    # مدفوعات المبيعات - إعادة توجيه للنظام الموحد
    path("payments/", views.redirect_to_unified_payments, name="sale_payment_list"),
    path("payments/<int:pk>/", views.payment_detail, name="payment_detail"),
    path("payments/<int:payment_id>/post/", views.post_payment, name="post_payment"),
    path(
        "payments/<int:payment_id>/unpost/", views.unpost_payment, name="unpost_payment"
    ),
    path("payments/<int:payment_id>/edit/", views.edit_payment, name="edit_payment"),
    path(
        "payments/<int:payment_id>/unpost-only/",
        views.unpost_payment_only,
        name="unpost_payment_only",
    ),
    # مرتجعات المبيعات
    path("returns/", views.sale_return_list, name="sale_return_list"),
    path("<int:pk>/return/", views.sale_return, name="sale_return"),
    path("returns/<int:pk>/", views.sale_return_detail, name="sale_return_detail"),
    path(
        "returns/<int:pk>/confirm/",
        views.sale_return_confirm,
        name="sale_return_confirm",
    ),
    path(
        "returns/<int:pk>/cancel/", views.sale_return_cancel, name="sale_return_cancel"
    ),
]
