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

urlpatterns = [
    # الصفحة الرئيسية
    path('', DashboardView.as_view(), name='dashboard'),
    
    # طلبات التسعير (مع حسابات ديناميكية مدمجة)
    path('orders/', include(order_patterns)),
    
    # APIs
    path('api/', include(api_patterns)),
    
    # تقارير (سيتم إضافتها لاحقاً)
    # path('reports/', views.ReportsView.as_view(), name='reports'),
    # path('reports/export/<str:format>/', views.export_report, name='export_report'),
    
    # إعدادات (سيتم إضافتها لاحقاً)
    # path('settings/', views.SettingsView.as_view(), name='settings'),
]
