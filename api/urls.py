from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)

app_name = 'api'

# إنشاء راوتر لواجهة API
router = DefaultRouter()

# هنا سيتم إضافة عناصر المسارات الخاصة بالوحدات المختلفة

urlpatterns = [
    # تسجيل الدخول والمصادقة
    path('token/', obtain_auth_token, name='token_obtain'),
    path('token/jwt/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/jwt/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/jwt/verify/', TokenVerifyView.as_view(), name='token_verify'),
    
    # توجيه المسارات إلى الراوتر
    path('', include(router.urls)),
    
    # توجيه المسارات إلى واجهة API للمصادقة
    path('auth/', include('rest_framework.urls')),
] 