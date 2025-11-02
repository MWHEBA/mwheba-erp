from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)

from .viewsets import (
    UserViewSet,
    CategoryViewSet, ProductViewSet, StockViewSet, StockMovementViewSet, WarehouseViewSet,
    SupplierTypeViewSet, SupplierViewSet,
    CustomerViewSet,
    SaleViewSet, PurchaseViewSet,
    ChartOfAccountsViewSet, JournalEntryViewSet
)

app_name = "api"

# إنشاء راوتر لواجهة API
router = DefaultRouter()

# تسجيل ViewSets

# Users
router.register(r'users', UserViewSet, basename='user')

# Products
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'products', ProductViewSet, basename='product')
router.register(r'stocks', StockViewSet, basename='stock')
router.register(r'stock-movements', StockMovementViewSet, basename='stock-movement')
router.register(r'warehouses', WarehouseViewSet, basename='warehouse')

# Suppliers
router.register(r'supplier-types', SupplierTypeViewSet, basename='supplier-type')
router.register(r'suppliers', SupplierViewSet, basename='supplier')

# Customers
router.register(r'customers', CustomerViewSet, basename='customer')

# Sales & Purchases
router.register(r'sales', SaleViewSet, basename='sale')
router.register(r'purchases', PurchaseViewSet, basename='purchase')

# Financial
router.register(r'accounts', ChartOfAccountsViewSet, basename='account')
router.register(r'journal-entries', JournalEntryViewSet, basename='journal-entry')

urlpatterns = [
    # تسجيل الدخول والمصادقة
    path("token/", obtain_auth_token, name="token_obtain"),
    path("token/jwt/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/jwt/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("token/jwt/verify/", TokenVerifyView.as_view(), name="token_verify"),
    # توجيه المسارات إلى الراوتر
    path("", include(router.urls)),
    # توجيه المسارات إلى واجهة API للمصادقة
    path("auth/", include("rest_framework.urls")),
]
