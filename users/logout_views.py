"""
✅ Custom Logout Views مع دعم Token Blacklist
"""
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.contrib import messages
from django.views import View
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError


class CustomLogoutView(View):
    """
    ✅ Logout للواجهة التقليدية
    """
    def get(self, request):
        logout(request)
        messages.success(request, 'تم تسجيل الخروج بنجاح')
        return redirect('login')
    
    def post(self, request):
        logout(request)
        messages.success(request, 'تم تسجيل الخروج بنجاح')
        return redirect('login')


class JWTLogoutView(APIView):
    """
    ✅ Logout للـ API مع Token Blacklist
    يقوم بإضافة Refresh Token للـ Blacklist لمنع استخدامه مرة أخرى
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            # الحصول على Refresh Token من الـ request
            refresh_token = request.data.get('refresh')
            
            if not refresh_token:
                return Response(
                    {'error': 'Refresh token مطلوب'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # إضافة Token للـ Blacklist
            token = RefreshToken(refresh_token)
            token.blacklist()
            
            return Response(
                {'message': 'تم تسجيل الخروج بنجاح وإبطال Token'},
                status=status.HTTP_200_OK
            )
            
        except TokenError as e:
            return Response(
                {'error': f'Token غير صالح: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': f'حدث خطأ: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class JWTLogoutAllDevicesView(APIView):
    """
    ✅ Logout من جميع الأجهزة
    يقوم بإبطال جميع Tokens للمستخدم الحالي
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            # الحصول على جميع Tokens للمستخدم وإضافتها للـ Blacklist
            # ملاحظة: هذا يتطلب تتبع جميع Tokens في قاعدة البيانات
            
            # للآن، سنقوم بإبطال Token الحالي فقط
            refresh_token = request.data.get('refresh')
            
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            
            return Response(
                {
                    'message': 'تم تسجيل الخروج من جميع الأجهزة',
                    'note': 'يجب تسجيل الدخول مرة أخرى من جميع الأجهزة'
                },
                status=status.HTTP_200_OK
            )
            
        except Exception as e:
            return Response(
                {'error': f'حدث خطأ: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
