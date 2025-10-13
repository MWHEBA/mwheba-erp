from django.urls import path
from . import views
from . import views_pricing
from . import api_views

app_name = "supplier"

urlpatterns = [
    path("", views.supplier_list, name="supplier_list"),
    path("add/", views.supplier_add, name="supplier_add"),
    path("<int:pk>/edit/", views.supplier_edit, name="supplier_edit"),
    path("<int:pk>/delete/", views.supplier_delete, name="supplier_delete"),
    path("<int:pk>/detail/", views.supplier_detail, name="supplier_detail"),
    path(
        "<int:pk>/change-account/",
        views.supplier_change_account,
        name="supplier_change_account",
    ),
    # الخدمات المتخصصة الجديدة (النظام الديناميكي)
    path(
        "<int:supplier_id>/specialized-services/add/",
        views.add_specialized_service,
        name="add_specialized_service",
    ),
    path(
        "<int:supplier_id>/specialized-services/<int:service_id>/edit/",
        views.edit_specialized_service,
        name="edit_specialized_service",
    ),
    path(
        "<int:supplier_id>/specialized-services/<int:service_id>/delete/",
        views.delete_specialized_service,
        name="delete_specialized_service",
    ),
    # API لتحميل النماذج (مطلوب للنظام الجديد)
    path(
        "api/get-category-form/",
        api_views.get_category_form_api,
        name="get_category_form_api",
    ),
    # APIs النظام الجديد الموحد
    path(
        "api/universal/get-service-data/<int:service_id>/",
        api_views.get_service_data_universal,
        name="get_service_data_universal",
    ),
    path(
        "api/universal/save-service-data/",
        api_views.save_service_data_universal,
        name="save_service_data_universal",
    ),
    path(
        "api/universal/update-service-data/<int:service_id>/",
        api_views.update_service_data_universal,
        name="update_service_data_universal",
    ),
    path(
        "api/universal/get-field-mapping/<str:service_type>/",
        api_views.get_field_mapping_api,
        name="get_field_mapping_api",
    ),
    path("by-type/", views.suppliers_by_type, name="suppliers_by_type"),
    path("service-comparison/", views.service_comparison, name="service_comparison"),
    path(
        "<int:pk>/specialized-services/",
        views.supplier_services_detail,
        name="supplier_services_detail",
    ),
    # Price comparison and calculator
    path("price-comparison/", views_pricing.price_comparison, name="price_comparison"),
    path(
        "service-calculator/",
        views_pricing.service_calculator,
        name="service_calculator",
    ),
    path(
        "bulk-calculator/",
        views_pricing.bulk_price_calculator,
        name="bulk_price_calculator",
    ),
    path(
        "ajax/calculate-price/",
        views_pricing.ajax_calculate_price,
        name="ajax_calculate_price",
    ),
    path(
        "supplier/<int:supplier_id>/services-comparison/",
        views_pricing.supplier_services_comparison,
        name="supplier_services_comparison",
    ),
    path(
        "category/<str:category_code>/analysis/",
        views_pricing.category_analysis,
        name="category_analysis",
    ),
    # API endpoints
    path("api/list/", views.supplier_list_api, name="supplier_list_api"),
    path(
        "api/paper-sheet-sizes/",
        views.get_paper_sheet_sizes_api,
        name="get_paper_sheet_sizes_api",
    ),
    path(
        "api/paper-weights/", views.get_paper_weights_api, name="get_paper_weights_api"
    ),
    path(
        "api/paper-origins/", views.get_paper_origins_api, name="get_paper_origins_api"
    ),
    path("api/paper-price/", views.get_paper_price_api, name="get_paper_price_api"),
    path(
        "api/debug-paper-services/",
        views.debug_paper_services_api,
        name="debug_paper_services_api",
    ),
    path(
        "api/root-cause-analysis/",
        views.root_cause_analysis_api,
        name="root_cause_analysis_api",
    ),
]
