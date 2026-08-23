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
    path("<int:pk>/pdf/", views.sale_pdf_download, name="sale_pdf_download"),
    path("<int:pk>/email-pdf/", views.sale_email_pdf, name="sale_email_pdf"),
    path("<int:pk>/print/thermal/", views.sale_print_thermal, name="sale_print_thermal"),
    path("<int:pk>/duplicate/", views.sale_duplicate, name="sale_duplicate"),
    path("<int:pk>/payment/", views.add_payment, name="sale_add_payment"),
    path("<int:pk>/allocate-prepaid/", views.allocate_prepaid_balance, name="sale_allocate_prepaid"),
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
    path(
        "payments/<int:payment_id>/delete/",
        views.delete_payment,
        name="delete_payment",
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
    
    # عروض الأسعار (Quotations)
    path("quotations/", views.quotation_list, name="quotation_list"),
    path("quotations/create/", views.quotation_create, name="quotation_create"),
    path("quotations/create/customer/<int:customer_id>/", views.quotation_create, name="quotation_create_for_customer"),
    path("quotations/<int:pk>/", views.quotation_detail, name="quotation_detail"),
    path("quotations/<int:pk>/edit/", views.quotation_edit, name="quotation_edit"),
    path("quotations/<int:pk>/delete/", views.quotation_delete, name="quotation_delete"),
    path("quotations/<int:pk>/print/", views.quotation_print, name="quotation_print"),
    path("quotations/<int:pk>/pdf/", views.quotation_pdf_download, name="quotation_pdf_download"),
    path("quotations/<int:pk>/email-pdf/", views.quotation_email_pdf, name="quotation_email_pdf"),
    path("quotations/<int:pk>/convert/", views.quotation_convert_to_sale, name="quotation_convert_to_sale"),
    path("quotations/<int:pk>/convert-order/", views.sales_order_create, name="quotation_convert_to_sales_order"),
    path("quotations/api/check-stock/", views.check_product_stock, name="check_product_stock"),

    # إدارة الحقول الإضافية المخصصة
    path("custom-fields/", views.custom_field_list, name="custom_field_list"),
    path("custom-fields/create/", views.custom_field_create, name="custom_field_create"),
    path("custom-fields/<int:pk>/edit/", views.custom_field_edit, name="custom_field_edit"),
    path("custom-fields/<int:pk>/toggle/", views.custom_field_toggle, name="custom_field_toggle"),
    path("custom-fields/<int:pk>/delete/", views.custom_field_delete, name="custom_field_delete"),
    path("custom-fields/api/create/", views.api_create_custom_field, name="api_create_custom_field"),

    # الإشعارات الدائنة والخصومات المالية
    path("credit-notes/", views.credit_note_list, name="credit_note_list"),
    path("credit-notes/create/", views.credit_note_create, name="credit_note_create"),
    path("credit-notes/<int:pk>/", views.credit_note_detail, name="credit_note_detail"),
    path("credit-notes/<int:pk>/post/", views.credit_note_post, name="credit_note_post"),
    path("credit-notes/<int:pk>/reverse/", views.credit_note_reverse, name="credit_note_reverse"),

    # أوامر البيع (Sales Orders)
    path("orders/", views.sales_order_list, name="sales_order_list"),
    path("orders/create/", views.sales_order_create, name="sales_order_create"),
    path("orders/create/quotation/<int:quotation_id>/", views.sales_order_create, name="sales_order_create_for_quotation"),
    path("orders/<int:pk>/", views.sales_order_detail, name="sales_order_detail"),
    path("orders/<int:pk>/edit/", views.sales_order_edit, name="sales_order_edit"),
    path("orders/<int:pk>/print/", views.sales_order_print, name="sales_order_print"),
    path("orders/<int:pk>/confirm/", views.sales_order_confirm, name="sales_order_confirm"),
    path("orders/<int:pk>/cancel/", views.sales_order_cancel, name="sales_order_cancel"),
    path("orders/<int:pk>/convert-sale/", views.sales_order_convert_to_sale, name="sales_order_convert_to_sale"),

    # إذون تسليم البضاعة (Delivery Notes)
    path("delivery-notes/", views.delivery_note_list, name="delivery_note_list"),
    path("delivery-notes/create/", views.delivery_note_create, name="delivery_note_create"),
    path("delivery-notes/<int:pk>/", views.delivery_note_detail, name="delivery_note_detail"),
    path("delivery-notes/<int:pk>/print/", views.delivery_note_print, name="delivery_note_print"),
    path("delivery-notes/<int:pk>/cancel/", views.delivery_note_cancel, name="delivery_note_cancel"),
    path("delivery-notes/<int:pk>/convert-sale/", views.delivery_note_convert_to_sale, name="delivery_note_convert_to_sale"),

    # قوائم الأسعار وقواعد الخصم (Pricing & Policies)
    path("api/pricing/evaluate-cart/", views.evaluate_cart_api, name="api_evaluate_cart"),
    path("pricing/price-lists/", views.price_list_list, name="price_list_list"),
    path("pricing/price-lists/create/", views.price_list_create, name="price_list_create"),
    path("pricing/price-lists/<int:pk>/", views.price_list_detail, name="price_list_detail"),
    path("pricing/discount-rules/", views.discount_rule_list, name="discount_rule_list"),
    path("pricing/discount-rules/create/", views.discount_rule_create, name="discount_rule_create"),
    path("pricing/discount-rules/<int:pk>/edit/", views.discount_rule_edit, name="discount_rule_edit"),
    path("pricing/discount-rules/<int:pk>/toggle/", views.discount_rule_toggle_status, name="discount_rule_toggle"),
    path("pricing/discount-rules/<int:pk>/delete/", views.discount_rule_delete, name="discount_rule_delete"),
]
