from django.urls import path
from .views_modules import inventory_views
from .views import voucher_views
from .views import transfer_views
from .views import batch_voucher_views
from . import views

app_name = "product"

urlpatterns = [
    # المنتجات
    path("", views.product_list, name="product_list"),
    path("services/", views.service_list, name="service_list"),  # ✨ صفحة الخدمات
    path("bundles/", views.bundle_list, name="bundle_list"),
    path("bundles/<int:pk>/", views.bundle_detail, name="bundle_detail"),
    path("bundles/create/", views.bundle_create, name="bundle_create"),
    path("bundles/<int:pk>/edit/", views.bundle_edit, name="bundle_edit"),
    
    # Bundle Analytics URLs
    path("bundles/analytics/", views.bundle_analytics_dashboard, name="bundle_analytics_dashboard"),
    path("api/bundles/analytics/", views.bundle_analytics_api, name="bundle_analytics_api"),
    path("api/bundles/charts/", views.bundle_chart_data_api, name="bundle_chart_data_api"),
    path("api/bundles/analytics/report/", views.bundle_analytics_report_api, name="bundle_analytics_report_api"),
    path("bulk-edit/", views.product_bulk_edit, name="product_bulk_edit"),
    path("create/", views.product_create, name="product_create"),
    path("create/modal/", views.product_create_modal, name="product_create_modal"),
    path("api/generate-sku/", views.generate_sku_ajax, name="generate_sku"),
    path("<int:pk>/", views.product_detail, name="product_detail"),
    path("<int:pk>/edit/", views.product_edit, name="product_edit"),
    path("<int:pk>/delete/", views.product_delete, name="product_delete"),
    path("<int:pk>/upload-image/", views.product_image_upload, name="product_image_upload"),
    
    # AJAX endpoints for bundle components
    path("api/available-products/", views.get_available_products_ajax, name="get_available_products_ajax"),
    path("api/product-info/<int:product_id>/", views.get_product_info_ajax, name="get_product_info_ajax"),
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
    path("warehouses/<int:pk>/toggle-active/", views.warehouse_toggle_active, name="warehouse_toggle_active"),
    # المخزون
    path("stock/", views.stock_list, name="stock_list"),
    path("stock/<int:pk>/", views.stock_detail, name="stock_detail"),
    path("stock/<int:pk>/adjust/", views.stock_adjust, name="stock_adjust"),
    path(
        "products/stock/<int:pk>/", views.product_stock_view, name="product_stock_view"
    ),
    path("api/stock/", views.get_stock_by_warehouse, name="get_stock_by_warehouse"),
    path("api/products-for-invoice/", views.get_products_for_invoice, name="get_products_for_invoice"),
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
    path(
        "reports/enhanced-inventory/",
        inventory_views.enhanced_inventory_report,
        name="enhanced_inventory_report",
    ),
    path(
        "api/bundle-stock-alerts/",
        inventory_views.bundle_stock_alerts_api,
        name="bundle_stock_alerts_api",
    ),
    
    # API للأذون
    path("api/product-warehouses/", voucher_views.GetProductWarehousesView.as_view(), name="get_product_warehouses"),
    path("api/available-products/", voucher_views.GetAvailableProductsView.as_view(), name="get_available_products"),
    
    # أذون الاستلام (Receipt Vouchers)
    path("vouchers/receipt/", voucher_views.ReceiptVoucherListView.as_view(), name="receipt_voucher_list"),
    path("vouchers/receipt/create/", voucher_views.ReceiptVoucherCreateView.as_view(), name="receipt_voucher_create"),
    path("vouchers/receipt/<int:pk>/", voucher_views.ReceiptVoucherDetailView.as_view(), name="receipt_voucher_detail"),
    path("vouchers/receipt/<int:pk>/approve/", voucher_views.ReceiptVoucherApproveView.as_view(), name="receipt_voucher_approve"),
    
    # أذون الصرف (Issue Vouchers)
    path("vouchers/issue/", voucher_views.IssueVoucherListView.as_view(), name="issue_voucher_list"),
    path("vouchers/issue/create/", voucher_views.IssueVoucherCreateView.as_view(), name="issue_voucher_create"),
    path("vouchers/issue/<int:pk>/", voucher_views.IssueVoucherDetailView.as_view(), name="issue_voucher_detail"),
    path("vouchers/issue/<int:pk>/approve/", voucher_views.IssueVoucherApproveView.as_view(), name="issue_voucher_approve"),

    # أذون التحويل (Transfer Vouchers)
    path("vouchers/transfer/", transfer_views.TransferVoucherListView.as_view(), name="transfer_voucher_list"),
    path("vouchers/transfer/create/", transfer_views.TransferVoucherCreateView.as_view(), name="transfer_voucher_create"),
    path("vouchers/transfer/<int:pk>/", transfer_views.TransferVoucherDetailView.as_view(), name="transfer_voucher_detail"),
    path("vouchers/transfer/<int:pk>/approve/", transfer_views.TransferVoucherApproveView.as_view(), name="transfer_voucher_approve"),

    # الأذون الجماعية (Batch Vouchers)
    path("vouchers/batch/", batch_voucher_views.BatchVoucherListView.as_view(), name="batch_voucher_list"),
    path("vouchers/batch/create/", batch_voucher_views.BatchVoucherCreateView.as_view(), name="batch_voucher_create"),
    path("vouchers/batch/<int:pk>/", batch_voucher_views.BatchVoucherDetailView.as_view(), name="batch_voucher_detail"),
    path("vouchers/batch/<int:pk>/update/", batch_voucher_views.BatchVoucherUpdateView.as_view(), name="batch_voucher_update"),
    path("vouchers/batch/<int:pk>/approve/", batch_voucher_views.BatchVoucherApproveView.as_view(), name="batch_voucher_approve"),
    path("vouchers/batch/<int:pk>/delete/", batch_voucher_views.BatchVoucherDeleteView.as_view(), name="batch_voucher_delete"),
    path("api/vouchers/batch/product-cost/", batch_voucher_views.GetProductCostView.as_view(), name="get_product_cost"),
]
