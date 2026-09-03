"""
Views Package - حزمة عروض وواجهات تسعير المطبوعات
تجميع منظم للعروض من order_views و api_views و settings_views
"""
from .order_views import (
    OrderListView, OrderDetailView, OrderCreateView,
    OrderUpdateView, OrderDeleteView, DashboardView, dashboard_redirect,
    calculate_order_cost, approve_order, duplicate_order
)
from .api_views import (
    LivePricingCalculateAPIView, OrderSummaryAPIView,
    GetCustomersAPIView, GetProductTypesAPIView, GetProductSizesAPIView,
    GetPressesAPIView, GetPaperTypesAPIView, GetPaperSuppliersAPIView,
    GetPaperWeightsAPIView, GetPaperSheetTypesAPIView, GetPaperOriginsAPIView,
    GetPaperPriceAPIView, GetPieceSizesAPIView, GetServiceTypesAPIView,
    GetSuppliersByServiceAPIView, GetSupplierServicesAPIView,
    GetServicePriceByIdAPIView, SaveOrderServiceSupplierAPIView,
    CustomerInfoAPIView, BulkPriceUpdateAPIView, GenerateVendorPOsAPIView
)
from .settings_views import settings_home

__all__ = [
    'OrderListView', 'OrderDetailView', 'OrderCreateView',
    'OrderUpdateView', 'OrderDeleteView', 'DashboardView', 'dashboard_redirect',
    'calculate_order_cost', 'approve_order', 'duplicate_order',
    'LivePricingCalculateAPIView', 'OrderSummaryAPIView',
    'GetCustomersAPIView', 'GetProductTypesAPIView', 'GetProductSizesAPIView',
    'GetPressesAPIView', 'GetPaperTypesAPIView', 'GetPaperSuppliersAPIView',
    'GetPaperWeightsAPIView', 'GetPaperSheetTypesAPIView', 'GetPaperOriginsAPIView',
    'GetPaperPriceAPIView', 'GetPieceSizesAPIView', 'GetServiceTypesAPIView',
    'GetSuppliersByServiceAPIView', 'GetSupplierServicesAPIView',
    'GetServicePriceByIdAPIView', 'SaveOrderServiceSupplierAPIView',
    'CustomerInfoAPIView', 'BulkPriceUpdateAPIView', 'GenerateVendorPOsAPIView',
    'settings_home',
]
