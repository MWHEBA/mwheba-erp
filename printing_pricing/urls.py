from django.urls import path, include

# استيراد العروض من المجلدات المنظمة
from .views.order_views import (
    OrderListView, OrderDetailView, OrderCreateView, 
    OrderUpdateView, OrderDeleteView, dashboard_redirect,
    calculate_order_cost, approve_order, duplicate_order
)
from .views.api_views import (
    LivePricingCalculateAPIView,
    OrderSummaryAPIView, GetCustomersAPIView,
    GetProductTypesAPIView, GetProductSizesAPIView,
    GetPressesAPIView, GetPaperTypesAPIView,
    GetPaperSuppliersAPIView, GetPaperWeightsAPIView, GetPaperSheetTypesAPIView,
    GetPaperOriginsAPIView, GetPaperPriceAPIView, GetPieceSizesAPIView,
    GetServiceTypesAPIView, GetSuppliersByServiceAPIView,
    GetSupplierServicesAPIView, GetServicePriceByIdAPIView,
    CustomerInfoAPIView,
    SaveOrderServiceSupplierAPIView,
    BulkPriceUpdateAPIView,
    GenerateVendorPOsAPIView,
    ApprovedOrdersAPIView,
)

# استيراد عروض الإعدادات
from .views.settings_views import (
    settings_home, PaperTypeListView, PaperTypeCreateView, 
    PaperTypeUpdateView, PaperTypeDeleteView,
    PaperSizeListView, PaperSizeCreateView, PaperSizeUpdateView, PaperSizeDeleteView,
    PaperWeightListView, PaperWeightCreateView, PaperWeightUpdateView, PaperWeightDeleteView,
    PaperOriginListView, PaperOriginCreateView, PaperOriginUpdateView, PaperOriginDeleteView,
    CoatingTypeListView, CoatingTypeCreateView, CoatingTypeUpdateView, CoatingTypeDeleteView,
    FinishingTypeListView, FinishingTypeCreateView, FinishingTypeUpdateView, FinishingTypeDeleteView,
    PackagingTypeListView, PackagingTypeCreateView, PackagingTypeUpdateView, PackagingTypeDeleteView,
    PieceSizeListView, PieceSizeCreateView, PieceSizeUpdateView, PieceSizeDeleteView,
    PlateSizeListView, PlateSizeCreateView, PlateSizeUpdateView, PlateSizeDeleteView,
    ProductTypeListView, ProductTypeCreateView, ProductTypeUpdateView, ProductTypeDeleteView,
    ProductTypeReorderView, ProductTypeToggleActiveView,
    ProductSizeListView, ProductSizeCreateView, ProductSizeUpdateView, ProductSizeDeleteView,
    ProductSizeReorderView, ProductSizeToggleActiveView,
    OffsetMachineTypeListView, OffsetMachineTypeCreateView, OffsetMachineTypeUpdateView, OffsetMachineTypeDeleteView,
    OffsetSheetSizeListView, OffsetSheetSizeCreateView, OffsetSheetSizeUpdateView, OffsetSheetSizeDeleteView,
    DigitalMachineTypeListView, DigitalMachineTypeCreateView, DigitalMachineTypeUpdateView, DigitalMachineTypeDeleteView,
    DigitalSheetSizeListView, DigitalSheetSizeCreateView, DigitalSheetSizeUpdateView, DigitalSheetSizeDeleteView
)

from supplier.views_settings.service_type_views import (
    service_type_list, service_type_create, service_type_edit,
    service_type_delete, service_type_schema
)

app_name = 'printing_pricing'

# URLs للطلبات
order_patterns = [
    path('', OrderListView.as_view(), name='order_list'),
    path('create/', OrderCreateView.as_view(), name='order_create'),
    path('<int:pk>/', OrderDetailView.as_view(), name='order_detail'),
    path('<int:pk>/edit/', OrderUpdateView.as_view(), name='order_update'),
    path('<int:pk>/delete/', OrderDeleteView.as_view(), name='order_delete'),
    path('<int:pk>/calculate/', calculate_order_cost, name='calculate_cost'),
    path('<int:pk>/calculate-cost/', calculate_order_cost, name='calculate_order_cost'),
    path('<int:pk>/approve/', approve_order, name='approve_order'),
    path('<int:pk>/duplicate/', duplicate_order, name='duplicate_order'),
]

# URLs للAPI
api_patterns = [
    path('live-calculate/', LivePricingCalculateAPIView.as_view(), name='api_live_calculate'),
    path('order-summary/<int:order_id>/', OrderSummaryAPIView.as_view(), name='api_order_summary'),
    
    # APIs للحقول الديناميكية ومعلومات العميل
    path('get-customers/', GetCustomersAPIView.as_view(), name='api_get_customers'),
    path('customer-info/<int:customer_id>/', CustomerInfoAPIView.as_view(), name='api_customer_info'),
    path('approved-orders/', ApprovedOrdersAPIView.as_view(), name='api_approved_orders'),
    path('get-product-types/', GetProductTypesAPIView.as_view(), name='api_get_product_types'),
    path('get-product-sizes/', GetProductSizesAPIView.as_view(), name='api_get_product_sizes'),
    
    # APIs للمطابع والماكينات
    path('presses/', GetPressesAPIView.as_view(), name='api_presses'),
    
    # APIs للورق
    path('paper-types/', GetPaperTypesAPIView.as_view(), name='api_paper_types'),
    path('paper-suppliers/', GetPaperSuppliersAPIView.as_view(), name='api_paper_suppliers'),
    path('paper-weights/', GetPaperWeightsAPIView.as_view(), name='api_paper_weights'),
    path('paper-sheet-types/', GetPaperSheetTypesAPIView.as_view(), name='api_paper_sheet_types'),
    path('paper-origins/', GetPaperOriginsAPIView.as_view(), name='api_paper_origins'),
    path('paper-price/', GetPaperPriceAPIView.as_view(), name='api_paper_price'),
    
    # APIs لمقاسات القطع
    path('piece-sizes/', GetPieceSizesAPIView.as_view(), name='api_piece_sizes'),

    # APIs خدمات الموردين
    path('service-types/',        GetServiceTypesAPIView.as_view(),      name='api_service_types'),
    path('suppliers-by-service/', GetSuppliersByServiceAPIView.as_view(), name='api_suppliers_by_service'),
    path('supplier-services/',    GetSupplierServicesAPIView.as_view(),   name='api_supplier_services'),
    path('service-price/',        GetServicePriceByIdAPIView.as_view(),   name='api_service_price_by_id'),

    # ربط الموردين والتسعير الجماعي
    path('save-order-service-supplier/', SaveOrderServiceSupplierAPIView.as_view(), name='api_save_order_service_supplier'),
    path('bulk-price-update/', BulkPriceUpdateAPIView.as_view(), name='api_bulk_price_update'),

    # جسر المشتريات وتوليد أوامر الشغل للموردين
    path('generate-vendor-pos/<int:order_id>/', GenerateVendorPOsAPIView.as_view(), name='api_generate_vendor_pos'),
]

# URLs للإعدادات
settings_patterns = [
    # الصفحة الرئيسية للإعدادات
    path('', settings_home, name='settings_home'),
    
    # خدمات وقدرات التسعير
    path('service-types/', service_type_list, name='service_type_list'),
    path('service-types/create/', service_type_create, name='service_type_create'),
    path('service-types/<int:pk>/edit/', service_type_edit, name='service_type_edit'),
    path('service-types/<int:pk>/delete/', service_type_delete, name='service_type_delete'),
    path('service-types/<int:pk>/schema/', service_type_schema, name='service_type_schema'),
    
    # أنواع الورق
    path('paper-types/', PaperTypeListView.as_view(), name='paper_type_list'),
    path('paper-types/create/', PaperTypeCreateView.as_view(), name='paper_type_create'),
    path('paper-types/<int:pk>/edit/', PaperTypeUpdateView.as_view(), name='paper_type_edit'),
    path('paper-types/<int:pk>/delete/', PaperTypeDeleteView.as_view(), name='paper_type_delete'),
    
    # مقاسات الورق
    path('paper-sizes/', PaperSizeListView.as_view(), name='paper_size_list'),
    path('paper-sizes/create/', PaperSizeCreateView.as_view(), name='paper_size_create'),
    path('paper-sizes/<int:pk>/edit/', PaperSizeUpdateView.as_view(), name='paper_size_edit'),
    path('paper-sizes/<int:pk>/delete/', PaperSizeDeleteView.as_view(), name='paper_size_delete'),
    
    # أوزان الورق
    path('paper-weights/', PaperWeightListView.as_view(), name='paper_weight_list'),
    path('paper-weights/create/', PaperWeightCreateView.as_view(), name='paper_weight_create'),
    path('paper-weights/<int:pk>/edit/', PaperWeightUpdateView.as_view(), name='paper_weight_edit'),
    path('paper-weights/<int:pk>/delete/', PaperWeightDeleteView.as_view(), name='paper_weight_delete'),
    
    # مناشئ الورق
    path('paper-origins/', PaperOriginListView.as_view(), name='paper_origin_list'),
    path('paper-origins/create/', PaperOriginCreateView.as_view(), name='paper_origin_create'),
    path('paper-origins/<int:pk>/edit/', PaperOriginUpdateView.as_view(), name='paper_origin_edit'),
    path('paper-origins/<int:pk>/delete/', PaperOriginDeleteView.as_view(), name='paper_origin_delete'),
    
    # أنواع التغطية
    path('coating-types/', CoatingTypeListView.as_view(), name='coating_type_list'),
    path('coating-types/create/', CoatingTypeCreateView.as_view(), name='coating_type_create'),
    path('coating-types/<int:pk>/edit/', CoatingTypeUpdateView.as_view(), name='coating_type_edit'),
    path('coating-types/<int:pk>/delete/', CoatingTypeDeleteView.as_view(), name='coating_type_delete'),
    
    # أنواع خدمات الطباعة
    path('finishing-types/', FinishingTypeListView.as_view(), name='finishing_type_list'),
    path('finishing-types/create/', FinishingTypeCreateView.as_view(), name='finishing_type_create'),
    path('finishing-types/<int:pk>/edit/', FinishingTypeUpdateView.as_view(), name='finishing_type_edit'),
    path('finishing-types/<int:pk>/delete/', FinishingTypeDeleteView.as_view(), name='finishing_type_delete'),
    
    # أنواع التقفيل
    path('packaging-types/', PackagingTypeListView.as_view(), name='packaging_type_list'),
    path('packaging-types/create/', PackagingTypeCreateView.as_view(), name='packaging_type_create'),
    path('packaging-types/<int:pk>/edit/', PackagingTypeUpdateView.as_view(), name='packaging_type_edit'),
    path('packaging-types/<int:pk>/delete/', PackagingTypeDeleteView.as_view(), name='packaging_type_delete'),
    
    # مقاسات القطع
    path('piece-sizes/', PieceSizeListView.as_view(), name='piece_size_list'),
    path('piece-sizes/create/', PieceSizeCreateView.as_view(), name='piece_size_create'),
    path('piece-sizes/<int:pk>/edit/', PieceSizeUpdateView.as_view(), name='piece_size_edit'),
    path('piece-sizes/<int:pk>/delete/', PieceSizeDeleteView.as_view(), name='piece_size_delete'),
    
    # مقاسات الزنكات
    path('plate-sizes/', PlateSizeListView.as_view(), name='plate_size_list'),
    path('plate-sizes/create/', PlateSizeCreateView.as_view(), name='plate_size_create'),
    path('plate-sizes/<int:pk>/edit/', PlateSizeUpdateView.as_view(), name='plate_size_edit'),
    path('plate-sizes/<int:pk>/delete/', PlateSizeDeleteView.as_view(), name='plate_size_delete'),
    
    # أنواع المطبوعات
    path('product-types/', ProductTypeListView.as_view(), name='product_type_list'),
    path('product-types/create/', ProductTypeCreateView.as_view(), name='product_type_create'),
    path('product-types/<int:pk>/edit/', ProductTypeUpdateView.as_view(), name='product_type_edit'),
    path('product-types/<int:pk>/delete/', ProductTypeDeleteView.as_view(), name='product_type_delete'),
    path('product-types/reorder/', ProductTypeReorderView.as_view(), name='product_type_reorder'),
    path('product-types/<int:pk>/toggle-active/', ProductTypeToggleActiveView.as_view(), name='product_type_toggle_active'),
    
    # مقاسات المطبوعات
    path('product-sizes/', ProductSizeListView.as_view(), name='product_size_list'),
    path('product-sizes/create/', ProductSizeCreateView.as_view(), name='product_size_create'),
    path('product-sizes/<int:pk>/edit/', ProductSizeUpdateView.as_view(), name='product_size_edit'),
    path('product-sizes/<int:pk>/delete/', ProductSizeDeleteView.as_view(), name='product_size_delete'),
    path('product-sizes/reorder/', ProductSizeReorderView.as_view(), name='product_size_reorder'),
    path('product-sizes/<int:pk>/toggle-active/', ProductSizeToggleActiveView.as_view(), name='product_size_toggle_active'),
    
    
    # أنواع ماكينات الأوفست
    path('offset-machine-types/', OffsetMachineTypeListView.as_view(), name='offset_machine_type_list'),
    path('offset-machine-types/create/', OffsetMachineTypeCreateView.as_view(), name='offset_machine_type_create'),
    path('offset-machine-types/<int:pk>/edit/', OffsetMachineTypeUpdateView.as_view(), name='offset_machine_type_edit'),
    path('offset-machine-types/<int:pk>/delete/', OffsetMachineTypeDeleteView.as_view(), name='offset_machine_type_delete'),
    
    # مقاسات ماكينات الأوفست
    path('offset-sheet-sizes/', OffsetSheetSizeListView.as_view(), name='offset_sheet_size_list'),
    path('offset-sheet-sizes/create/', OffsetSheetSizeCreateView.as_view(), name='offset_sheet_size_create'),
    path('offset-sheet-sizes/<int:pk>/edit/', OffsetSheetSizeUpdateView.as_view(), name='offset_sheet_size_edit'),
    path('offset-sheet-sizes/<int:pk>/delete/', OffsetSheetSizeDeleteView.as_view(), name='offset_sheet_size_delete'),
    
    # أنواع ماكينات الديجيتال
    path('digital-machine-types/', DigitalMachineTypeListView.as_view(), name='digital_machine_type_list'),
    path('digital-machine-types/create/', DigitalMachineTypeCreateView.as_view(), name='digital_machine_type_create'),
    path('digital-machine-types/<int:pk>/edit/', DigitalMachineTypeUpdateView.as_view(), name='digital_machine_type_edit'),
    path('digital-machine-types/<int:pk>/delete/', DigitalMachineTypeDeleteView.as_view(), name='digital_machine_type_delete'),
    
    # مقاسات ماكينات الديجيتال
    path('digital-sheet-sizes/', DigitalSheetSizeListView.as_view(), name='digital_sheet_size_list'),
    path('digital-sheet-sizes/create/', DigitalSheetSizeCreateView.as_view(), name='digital_sheet_size_create'),
    path('digital-sheet-sizes/<int:pk>/edit/', DigitalSheetSizeUpdateView.as_view(), name='digital_sheet_size_edit'),
    path('digital-sheet-sizes/<int:pk>/delete/', DigitalSheetSizeDeleteView.as_view(), name='digital_sheet_size_delete'),
]

urlpatterns = [
    # الصفحة الرئيسية — redirect لقائمة الطلبات
    path('', dashboard_redirect, name='dashboard'),
    
    # طلبات التسعير
    path('orders/', include(order_patterns)),
    
    # APIs
    path('api/', include(api_patterns)),
    
    # الإعدادات
    path('settings/', include(settings_patterns)),
]
