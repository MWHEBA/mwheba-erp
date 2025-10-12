"""
# واجهة برمجة التطبيقات (API) لتطبيق المستخدمين
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
from django.utils import timezone

from utils.throttling import LoginRateThrottle, RegisterRateThrottle
from .models import User


class LoginAPIView(APIView):
    """
    # واجهة برمجة التطبيق لتسجيل الدخول
    """
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        
        if not username or not password:
            return Response(
                {'error': 'يرجى توفير اسم المستخدم وكلمة المرور'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user = authenticate(username=username, password=password)
        
        if not user:
            return Response(
                {'error': 'بيانات الاعتماد غير صالحة'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # إنشاء أو استرداد الرمز المميز للمستخدم
        token, created = Token.objects.get_or_create(user=user)
        
        return Response({
            'token': token.key,
            'user_id': user.id,
            'username': user.username,
            'email': user.email,
            'is_staff': user.is_staff,
        }, status=status.HTTP_200_OK)


class RegisterAPIView(APIView):
    """
    # واجهة برمجة التطبيق لتسجيل المستخدمين الجدد
    """
    permission_classes = [AllowAny]
    throttle_classes = [RegisterRateThrottle]

    def post(self, request):
        username = request.data.get('username')
        email = request.data.get('email')
        password = request.data.get('password')
        
        # التحقق من البيانات
        if not username or not email or not password:
            return Response(
                {'error': 'يرجى توفير جميع البيانات المطلوبة'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # التحقق من وجود المستخدم بالفعل
        if User.objects.filter(username=username).exists():
            return Response(
                {'error': 'اسم المستخدم موجود بالفعل'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if User.objects.filter(email=email).exists():
            return Response(
                {'error': 'البريد الإلكتروني مستخدم بالفعل'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # إنشاء المستخدم الجديد
        user = User.objects.create_user(username=username, email=email, password=password)
        
        # إنشاء الرمز المميز للمستخدم
        token, created = Token.objects.get_or_create(user=user)
        
        return Response({
            'token': token.key,
            'user_id': user.id,
            'username': user.username,
            'email': user.email,
        }, status=status.HTTP_201_CREATED)


class UserProfileAPIView(APIView):
    """
    # واجهة برمجة التطبيق للوصول إلى ملف تعريف المستخدم وتحديثه
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user = request.user
        
        return Response({
            'user_id': user.id,
            'username': user.username,
            'email': user.email,
            'full_name': user.get_full_name(),
            'is_staff': user.is_staff,
            'date_joined': user.date_joined,
            'last_login': user.last_login,
        }, status=status.HTTP_200_OK)
    
    def put(self, request):
        user = request.user
        
        # تحديث البيانات المقدمة فقط
        if 'email' in request.data:
            user.email = request.data.get('email')
        
        if 'first_name' in request.data:
            user.first_name = request.data.get('first_name')
        
        if 'last_name' in request.data:
            user.last_name = request.data.get('last_name')
        
        # حفظ التغييرات
        user.save()
        
        return Response({
            'user_id': user.id,
            'username': user.username,
            'email': user.email,
            'full_name': user.get_full_name(),
            'is_staff': user.is_staff,
        }, status=status.HTTP_200_OK) 