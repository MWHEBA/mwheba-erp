from django.urls import path
from .views_modules import inventory_views
from . import views

app_name = "product"

urlpatterns = [
    # المنتجات
    path("", views.product_list, name="product_list"),
    path("create/", views.product_create, name="product_create"),
    path("<int:pk>/", views.product_detail, name="product_detail"),
    path("<int:pk>/edit/", views.product_edit, name="product_edit"),
    path("<int:pk>/delete/", views.product_delete, name="product_delete"),
    path("<int:pk>/upload-image/", views.product_image_upload, name="product_image_upload"),
    path("api/add-image/", views.add_product_image, name="add_product_image"),
    path(
        "api/delete-image/<int:pk>/",
        views.delete_product_image,
        name="delete_product_image",
    ),
    path(
        "images/<int:pk>/delete/",
        views.delete_product_image,
        name="delete_product_image_alt",
    ),
    # التصنيفات
    path("categories/", views.category_list, name="category_list"),
    path("categories/create/", views.category_create, name="category_create"),
    path("categories/<int:pk>/", views.category_detail, name="category_detail"),
    path("categories/<int:pk>/edit/", views.category_edit, name="category_edit"),
    path("categories/<int:pk>/delete/", views.category_delete, name="category_delete"),
    # الأنواع
    path("brands/", views.brand_list, name="brand_list"),
    path("brands/create/", views.brand_create, name="brand_create"),
    path("brands/<int:pk>/", views.brand_detail, name="brand_detail"),
    path("brands/<int:pk>/edit/", views.brand_edit, name="brand_edit"),
    path("brands/<int:pk>/delete/", views.brand_delete, name="brand_delete"),
    # وحدات القياس
    path("units/", views.unit_list, name="unit_list"),
    path("units/create/", views.unit_create, name="unit_create"),
    path("units/<int:pk>/", views.unit_detail, name="unit_detail"),
    path("units/<int:pk>/edit/", views.unit_edit, name="unit_edit"),
    path("units/<int:pk>/delete/", views.unit_delete, name="unit_delete"),
    # المخازن
    path("warehouses/", views.warehouse_list, name="warehouse_list"),
    path("warehouses/create/", views.warehouse_create, name="warehouse_create"),
    path("warehouses/<int:pk>/", views.warehouse_detail, name="warehouse_detail"),
    path("warehouses/<int:pk>/edit/", views.warehouse_edit, name="warehouse_edit"),
    path(
        "warehouses/<int:pk>/delete/", views.warehouse_delete, name="warehouse_delete"
    ),
    # المخزون
    path("stock/", views.stock_list, name="stock_list"),
    path("stock/<int:pk>/", views.stock_detail, name="stock_detail"),
    path("stock/<int:pk>/adjust/", views.stock_adjust, name="stock_adjust"),
    path(
        "products/stock/<int:pk>/", views.product_stock_view, name="product_stock_view"
    ),
    path("api/stock/", views.get_stock_by_warehouse, name="get_stock_by_warehouse"),
    # مسارات حركات المخزون
    path("stock-movements/", views.stock_movement_list, name="stock_movement_list"),
    path(
        "stock-movements/create/",
        views.stock_movement_create,
        name="stock_movement_create",
    ),
    path(
        "stock-movements/<int:pk>/",
        views.stock_movement_detail,
        name="stock_movement_detail",
    ),
    path(
        "stock-movements/<int:pk>/delete/",
        views.stock_movement_delete,
        name="stock_movement_delete",
    ),
    path(
        "api/stock-movements/add/", views.add_stock_movement, name="add_stock_movement"
    ),
    path(
        "api/stock-movements/export/",
        views.export_stock_movements,
        name="export_stock_movements",
    ),
    path(
        "api/warehouses/<int:warehouse_id>/export/",
        views.export_warehouse_inventory,
        name="export_warehouse_inventory",
    ),
    path(
        "api/warehouses/export/",
        views.export_warehouse_inventory_all,
        name="export_warehouse_inventory_all",
    ),
    # APIs أسعار الموردين
    path(
        "api/supplier-prices/add/",
        views.add_supplier_price_api,
        name="add_supplier_price_api",
    ),
    path(
        "api/supplier-prices/<int:pk>/edit/",
        views.edit_supplier_price_api,
        name="edit_supplier_price_api",
    ),
    path(
        "api/supplier-prices/<int:pk>/set-default/",
        views.set_default_supplier_api,
        name="set_default_supplier_api",
    ),
    path(
        "api/supplier-prices/<int:pk>/history/",
        views.supplier_price_history_api,
        name="supplier_price_history_api",
    ),
    path(
        "api/products/<int:product_id>/price-comparison/",
        views.product_price_comparison_api,
        name="product_price_comparison_api",
    ),
    # التقارير المتقدمة
    path(
        "reports/abc-analysis/",
        inventory_views.abc_analysis_report,
        name="abc_analysis_report",
    ),
    path(
        "reports/inventory-turnover/",
        inventory_views.inventory_turnover_report,
        name="inventory_turnover_report",
    ),
    path(
        "reports/reorder-point/",
        inventory_views.reorder_point_report,
        name="reorder_point_report",
    ),
]
