from django.urls import path
from . import views
from . import views_pricing
from . import api_views
from .views_settings.supplier_type_settings_views import *
from .views_settings.service_type_views import (
    service_type_list, service_type_create, service_type_edit,
    service_type_delete, service_type_schema, service_type_schema_sources_api,
)

app_name = "supplier"

urlpatterns = [
    path("", views.supplier_list, name="supplier_list"),
    path("add/", views.supplier_add, name="supplier_add"),
    path("create/", views.supplier_add, name="supplier_create"),
    path("create/modal/", views.supplier_create_modal, name="supplier_create_modal"),
    path("<int:pk>/edit/", views.supplier_edit, name="supplier_edit"),
    path("<int:pk>/delete/", views.supplier_delete, name="supplier_delete"),
    path("<int:pk>/detail/", views.supplier_detail, name="supplier_detail"),
    path("<int:pk>/change-account/", views.supplier_change_account, name="supplier_change_account"),
    path("<int:pk>/create-account/", views.supplier_create_account, name="supplier_create_account"),

    # ── خدمات المورد — المرحلة الثانية ──────────────────────────────
    path("<int:pk>/services/add/",                          views.supplier_service_add,    name="supplier_service_add"),
    path("<int:pk>/services/<int:service_pk>/edit/",        views.supplier_service_edit,   name="supplier_service_edit"),
    path("<int:pk>/services/<int:service_pk>/delete/",      views.supplier_service_delete, name="supplier_service_delete"),
    path("<int:pk>/services/<int:service_pk>/toggle/",      views.supplier_service_toggle, name="supplier_service_toggle"),
    path("<int:pk>/api/services/",                          views.supplier_services_api,   name="supplier_services_api"),

    # ── الشرائح السعرية — المرحلة الخامسة ──────────────────────────
    path("<int:pk>/services/<int:service_pk>/",                                          views.supplier_service_detail, name="supplier_service_detail"),
    path("<int:pk>/services/<int:service_pk>/tiers/add/",                                views.price_tier_add,          name="price_tier_add"),
    path("<int:pk>/services/<int:service_pk>/tiers/<int:tier_pk>/edit/",                 views.price_tier_edit,         name="price_tier_edit"),
    path("<int:pk>/services/<int:service_pk>/tiers/<int:tier_pk>/delete/",               views.price_tier_delete,       name="price_tier_delete"),
    path("<int:pk>/services/<int:service_pk>/tiers/<int:tier_pk>/toggle/",               views.price_tier_toggle,       name="price_tier_toggle"),
    path("api/schema-options/",                                                          views.service_type_schema_options_api, name="service_type_schema_options_api"),
    path("api/services/<int:service_pk>/price/",                                         views.service_price_api,       name="service_price_api"),

    # ── أنواع خدمات التسعير — المرحلة الرابعة ───────────────────────
    path("settings/service-types/",                         service_type_list,               name="service_type_list"),
    path("settings/service-types/create/",                  service_type_create,             name="service_type_create"),
    path("settings/service-types/<int:pk>/edit/",           service_type_edit,               name="service_type_edit"),
    path("settings/service-types/<int:pk>/delete/",         service_type_delete,             name="service_type_delete"),
    path("settings/service-types/<int:pk>/schema/",         service_type_schema,             name="service_type_schema"),
    path("settings/service-types/api/sources/",             service_type_schema_sources_api, name="service_type_schema_sources_api"),

    # API endpoints
    path("api/list/", views.supplier_list_api, name="supplier_list_api"),
    path("api/supplier-types-styles/", api_views.supplier_types_styles_api, name="supplier_types_styles_api"),

    # إعدادات أنواع الموردين الديناميكية
    path("settings/types/",                          supplier_type_settings_list,          name="supplier_type_settings_list"),
    path("settings/types/create/",                   supplier_type_settings_create,        name="supplier_type_settings_create"),
    path("settings/types/<int:pk>/edit/",            supplier_type_settings_edit,          name="supplier_type_settings_edit"),
    path("settings/types/<int:pk>/delete/",          supplier_type_settings_delete,        name="supplier_type_settings_delete"),
    path("settings/types/<int:pk>/preview/",         supplier_type_settings_preview,       name="supplier_type_settings_preview"),
    path("settings/types/<int:pk>/toggle-status/",   supplier_type_settings_toggle_status, name="supplier_type_settings_toggle_status"),
    path("settings/types/reorder/",                  supplier_type_settings_reorder,       name="supplier_type_settings_reorder"),
    path("settings/types/bulk-action/",              supplier_type_settings_bulk_action,   name="supplier_type_settings_bulk_action"),
    path("settings/types/export/",                   supplier_type_settings_export,        name="supplier_type_settings_export"),
    path("settings/types/sync/",                     supplier_type_settings_sync,          name="supplier_type_settings_sync"),
]
