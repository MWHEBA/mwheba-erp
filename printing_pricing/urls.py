from django.urls import path, include

# استيراد العروض من المجلدات المنظمة
from .views.order_views import (
    OrderListView, OrderDetailView, OrderCreateView, 
    OrderUpdateView, OrderDeleteView, DashboardView,
    calculate_order_cost, approve_order, duplicate_order
)
# تم حذف calculation_views - الحسابات تتم داخل نموذج الطلب ديناميكياً
from .views.api_views import (
    CalculateCostAPIView, GetMaterialPriceAPIView, GetServicePriceAPIView,
    ValidateOrderAPIView, OrderSummaryAPIView, GetClientsAPIView,
    GetProductTypesAPIView, GetProductSizesAPIView, GetPrintingSuppliersAPIView,
    GetPressesAPIView, GetPressPriceAPIView, GetCTPSuppliersAPIView,
    GetCTPPlatesAPIView, GetCTPPriceAPIView, GetPaperTypesAPIView,
    GetPaperSuppliersAPIView, GetPaperWeightsAPIView, GetPaperSheetTypesAPIView,
    GetPaperOriginsAPIView, GetPaperPriceAPIView, GetPieceSizesAPIView
)

# استيراد عروض الإعدادات
from .views.settings_views import (
    settings_home, PaperTypeListView, PaperTypeCreateView, 
    PaperTypeUpdateView, PaperTypeDeleteView,
    PaperSizeListView, PaperSizeCreateView, PaperSizeUpdateView, PaperSizeDeleteView,
    PaperWeightListView, PaperWeightCreateView, PaperWeightUpdateView, PaperWeightDeleteView,
    PaperOriginListView, PaperOriginCreateView, PaperOriginUpdateView, PaperOriginDeleteView,
    PrintDirectionListView, PrintDirectionCreateView, PrintDirectionUpdateView, PrintDirectionDeleteView,
    PrintSideListView, PrintSideCreateView, PrintSideUpdateView, PrintSideDeleteView,
    # العروض المتقدمة - تم دمجها في settings_views.py
    CoatingTypeListView, CoatingTypeCreateView, CoatingTypeUpdateView, CoatingTypeDeleteView,
    FinishingTypeListView, FinishingTypeCreateView, FinishingTypeUpdateView, FinishingTypeDeleteView,
    PackagingTypeListView, PackagingTypeCreateView, PackagingTypeUpdateView, PackagingTypeDeleteView,
    PieceSizeListView, PieceSizeCreateView, PieceSizeUpdateView, PieceSizeDeleteView,
    PlateSizeListView, PlateSizeCreateView, PlateSizeUpdateView, PlateSizeDeleteView,
    ProductTypeListView, ProductTypeCreateView, ProductTypeUpdateView, ProductTypeDeleteView,
    ProductSizeListView, ProductSizeCreateView, ProductSizeUpdateView, ProductSizeDeleteView,
    VATSettingListView, VATSettingCreateView, VATSettingUpdateView, VATSettingDeleteView,
    OffsetMachineTypeListView, OffsetMachineTypeCreateView, OffsetMachineTypeUpdateView, OffsetMachineTypeDeleteView,
    OffsetSheetSizeListView, OffsetSheetSizeCreateView, OffsetSheetSizeUpdateView, OffsetSheetSizeDeleteView,
    DigitalMachineTypeListView, DigitalMachineTypeCreateView, DigitalMachineTypeUpdateView, DigitalMachineTypeDeleteView,
    DigitalSheetSizeListView, DigitalSheetSizeCreateView, DigitalSheetSizeUpdateView, DigitalSheetSizeDeleteView,
    SystemSettingListView, SystemSettingCreateView, SystemSettingUpdateView, SystemSettingDeleteView
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
    path('<int:pk>/approve/', approve_order, name='approve_order'),
    path('<int:pk>/duplicate/', duplicate_order, name='duplicate_order'),
]

# تم حذف calculation_patterns - الحسابات تتم داخل نموذج الطلب ديناميكياً

# URLs للAPI
api_patterns = [
    path('calculate-cost/', CalculateCostAPIView.as_view(), name='api_calculate_cost'),
    path('get-material-price/', GetMaterialPriceAPIView.as_view(), name='api_material_price'),
    path('get-service-price/', GetServicePriceAPIView.as_view(), name='api_service_price'),
    path('validate-order/', ValidateOrderAPIView.as_view(), name='api_validate_order'),
    path('order-summary/<int:order_id>/', OrderSummaryAPIView.as_view(), name='api_order_summary'),
    
    # APIs للحقول الديناميكية
    path('get-clients/', GetClientsAPIView.as_view(), name='api_get_clients'),
    path('get-product-types/', GetProductTypesAPIView.as_view(), name='api_get_product_types'),
    path('get-product-sizes/', GetProductSizesAPIView.as_view(), name='api_get_product_sizes'),
    
    # APIs للمطابع والماكينات
    path('printing-suppliers/', GetPrintingSuppliersAPIView.as_view(), name='api_printing_suppliers'),
    path('presses/', GetPressesAPIView.as_view(), name='api_presses'),
    path('press-price/', GetPressPriceAPIView.as_view(), name='api_press_price'),
    
    # APIs للزنكات
    path('ctp-suppliers/', GetCTPSuppliersAPIView.as_view(), name='api_ctp_suppliers'),
    path('ctp-plates/', GetCTPPlatesAPIView.as_view(), name='api_ctp_plates'),
    path('ctp-price/', GetCTPPriceAPIView.as_view(), name='api_ctp_price'),
    
    # APIs للورق
    path('paper-types/', GetPaperTypesAPIView.as_view(), name='api_paper_types'),
    path('paper-suppliers/', GetPaperSuppliersAPIView.as_view(), name='api_paper_suppliers'),
    path('paper-weights/', GetPaperWeightsAPIView.as_view(), name='api_paper_weights'),
    path('paper-sheet-types/', GetPaperSheetTypesAPIView.as_view(), name='api_paper_sheet_types'),
    path('paper-origins/', GetPaperOriginsAPIView.as_view(), name='api_paper_origins'),
    path('paper-price/', GetPaperPriceAPIView.as_view(), name='api_paper_price'),
    
    # APIs لمقاسات القطع
    path('piece-sizes/', GetPieceSizesAPIView.as_view(), name='api_piece_sizes'),
]

# URLs للإعدادات
settings_patterns = [
    # الصفحة الرئيسية للإعدادات
    path('', settings_home, name='settings_home'),
    
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
    
    # اتجاهات الطباعة
    path('print-directions/', PrintDirectionListView.as_view(), name='print_direction_list'),
    path('print-directions/create/', PrintDirectionCreateView.as_view(), name='print_direction_create'),
    path('print-directions/<int:pk>/edit/', PrintDirectionUpdateView.as_view(), name='print_direction_edit'),
    path('print-directions/<int:pk>/delete/', PrintDirectionDeleteView.as_view(), name='print_direction_delete'),
    
    # جوانب الطباعة
    path('print-sides/', PrintSideListView.as_view(), name='print_side_list'),
    path('print-sides/create/', PrintSideCreateView.as_view(), name='print_side_create'),
    path('print-sides/<int:pk>/edit/', PrintSideUpdateView.as_view(), name='print_side_edit'),
    path('print-sides/<int:pk>/delete/', PrintSideDeleteView.as_view(), name='print_side_delete'),
    
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
    
    # أنواع المنتجات
    path('product-types/', ProductTypeListView.as_view(), name='product_type_list'),
    path('product-types/create/', ProductTypeCreateView.as_view(), name='product_type_create'),
    path('product-types/<int:pk>/edit/', ProductTypeUpdateView.as_view(), name='product_type_edit'),
    path('product-types/<int:pk>/delete/', ProductTypeDeleteView.as_view(), name='product_type_delete'),
    
    # مقاسات المنتجات
    path('product-sizes/', ProductSizeListView.as_view(), name='product_size_list'),
    path('product-sizes/create/', ProductSizeCreateView.as_view(), name='product_size_create'),
    path('product-sizes/<int:pk>/edit/', ProductSizeUpdateView.as_view(), name='product_size_edit'),
    path('product-sizes/<int:pk>/delete/', ProductSizeDeleteView.as_view(), name='product_size_delete'),
    
    # إعدادات ضريبة القيمة المضافة
    path('vat-settings/', VATSettingListView.as_view(), name='vat_setting_list'),
    path('vat-settings/create/', VATSettingCreateView.as_view(), name='vat_setting_create'),
    path('vat-settings/<int:pk>/edit/', VATSettingUpdateView.as_view(), name='vat_setting_edit'),
    path('vat-settings/<int:pk>/delete/', VATSettingDeleteView.as_view(), name='vat_setting_delete'),
    
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
    
    # إعدادات النظام
    path('system-settings/', SystemSettingListView.as_view(), name='system_setting_list'),
    path('system-settings/create/', SystemSettingCreateView.as_view(), name='system_setting_create'),
    path('system-settings/<int:pk>/edit/', SystemSettingUpdateView.as_view(), name='system_setting_edit'),
    path('system-settings/<int:pk>/delete/', SystemSettingDeleteView.as_view(), name='system_setting_delete'),
]

urlpatterns = [
    # الصفحة الرئيسية
    path('', DashboardView.as_view(), name='dashboard'),
    
    # طلبات التسعير (مع حسابات ديناميكية مدمجة)
    path('orders/', include(order_patterns)),
    
    # APIs
    path('api/', include(api_patterns)),
    
    # الإعدادات
    path('settings/', include(settings_patterns)),
    
    # تقارير (سيتم إضافتها لاحقاً)
    # path('reports/', views.ReportsView.as_view(), name='reports'),
    # path('reports/export/<str:format>/', views.export_report, name='export_report'),
]
