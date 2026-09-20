from django.urls import path
from . import views
from . import views_settings

app_name = "customer"

urlpatterns = [
    path("", views.customer_list, name="customer_list"),
    path("add/", views.customer_add, name="customer_add"),
    path("add-ajax/", views.customer_add_ajax, name="customer_add_ajax"),
    path("<int:pk>/edit/", views.customer_edit, name="customer_edit"),
    path("<int:pk>/delete/", views.customer_delete, name="customer_delete"),
    path("<int:pk>/reactivate/", views.customer_reactivate, name="customer_reactivate"),
    path("<int:pk>/detail/", views.customer_detail, name="customer_detail"),
    path(
        "<int:pk>/change-account/",
        views.customer_change_account,
        name="customer_change_account",
    ),
    path(
        "<int:pk>/create-account/",
        views.customer_create_account,
        name="customer_create_account",
    ),
    path(
        "<int:pk>/aging-api/",
        views.customer_aging_api,
        name="customer_aging_api",
    ),
    path(
        "<int:pk>/allocate-prepaid/",
        views.allocate_customer_prepaid,
        name="allocate_customer_prepaid",
    ),
    path(
        "<int:pk>/add-advance/",
        views.add_customer_advance_action,
        name="add_customer_advance",
    ),

    # ==================== إعدادات العملاء (Customer Settings) ====================
    path("settings/", views_settings.customer_settings_index, name="settings_index"),
    path("settings/general/", views_settings.customer_general_settings_view, name="general_settings"),
    
    # الشرائح والتصنيفات التجارية (Customer Tiers)
    path("settings/tiers/", views_settings.customer_tier_list, name="tier_list"),
    path("settings/tiers/create/", views_settings.customer_tier_create, name="tier_create"),
    path("settings/tiers/<int:pk>/edit/", views_settings.customer_tier_edit, name="tier_edit"),
    path("settings/tiers/<int:pk>/delete/", views_settings.customer_tier_delete, name="tier_delete"),
    path("settings/tiers/<int:pk>/toggle-status/", views_settings.customer_tier_toggle_status, name="tier_toggle_status"),
    path("settings/tiers/reorder/", views_settings.customer_tier_reorder, name="tier_reorder"),
    path("settings/tiers/<int:pk>/api-info/", views_settings.api_customer_tier_info, name="api_tier_info"),

    # شروط السداد والائتمان (Payment Terms)
    path("settings/payment-terms/", views_settings.payment_term_list, name="payment_term_list"),
    path("settings/payment-terms/create/", views_settings.payment_term_create, name="payment_term_create"),
    path("settings/payment-terms/<int:pk>/edit/", views_settings.payment_term_edit, name="payment_term_edit"),
    path("settings/payment-terms/<int:pk>/delete/", views_settings.payment_term_delete, name="payment_term_delete"),
    path("settings/payment-terms/<int:pk>/toggle-status/", views_settings.payment_term_toggle_status, name="payment_term_toggle_status"),
    path("settings/payment-terms/quick-add/", views_settings.payment_term_quick_add, name="payment_term_quick_add"),
]

