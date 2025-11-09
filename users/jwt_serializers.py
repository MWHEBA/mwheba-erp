"""
Custom JWT Serializers مع Claims إضافية
"""
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from datetime import datetime


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom serializer لإضافة claims إضافية للـ JWT token
    """
    
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        
        # إضافة custom claims أساسية فقط
        token['username'] = user.username
        token['email'] = user.email
        token['is_staff'] = user.is_staff
        token['is_superuser'] = user.is_superuser
        
        # ✅ تم إزالة permissions و groups من Token لأسباب أمنية
        # الصلاحيات يجب التحقق منها من قاعدة البيانات في كل request
        # لتجنب استخدام صلاحيات قديمة بعد تحديثها
        
        # إضافة timestamp للتتبع
        token['issued_at'] = datetime.now().isoformat()
        
        return token
    
    def validate(self, attrs):
        data = super().validate(attrs)
        
        # إضافة معلومات إضافية للـ response
        data['user'] = {
            'id': self.user.id,
            'username': self.user.username,
            'email': self.user.email,
            'full_name': self.user.get_full_name(),
            'is_staff': self.user.is_staff,
            'is_superuser': self.user.is_superuser,
        }
        
        return data


def get_tokens_for_user(user):
    """
    دالة مساعدة للحصول على tokens لمستخدم معين
    """
    refresh = RefreshToken.for_user(user)
    
    # إضافة custom claims أساسية فقط
    refresh['username'] = user.username
    refresh['email'] = user.email
    refresh['is_staff'] = user.is_staff
    refresh['is_superuser'] = user.is_superuser
    # ✅ تم إزالة permissions و groups لأسباب أمنية
    refresh['issued_at'] = datetime.now().isoformat()
    
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }
