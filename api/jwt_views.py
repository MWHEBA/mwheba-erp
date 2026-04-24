"""
Custom JWT Views مع Throttling للحماية من Brute Force
"""
from rest_framework_simplejwt.views import (
    TokenObtainPairView as BaseTokenObtainPairView,
    TokenRefreshView as BaseTokenRefreshView,
    TokenVerifyView as BaseTokenVerifyView,
    TokenBlacklistView as BaseTokenBlacklistView,
)
from utils.throttling import TokenObtainThrottle, TokenRefreshThrottle, TokenVerifyThrottle


class TokenObtainPairView(BaseTokenObtainPairView):
    """
    ✅ Custom Token Obtain View مع Rate Limiting
    الحماية من Brute Force: 5 محاولات/دقيقة فقط
    """
    throttle_classes = [TokenObtainThrottle]


class TokenRefreshView(BaseTokenRefreshView):
    """
    ✅ Custom Token Refresh View مع Rate Limiting
    10 محاولات/دقيقة فقط
    """
    throttle_classes = [TokenRefreshThrottle]


class TokenVerifyView(BaseTokenVerifyView):
    """
    ✅ Custom Token Verify View مع Rate Limiting
    20 محاولات/دقيقة فقط
    """
    throttle_classes = [TokenVerifyThrottle]


class TokenBlacklistView(BaseTokenBlacklistView):
    """
    ✅ Token Blacklist View للـ Logout الآمن
    """
    pass
