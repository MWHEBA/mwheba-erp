"""
🔒 متحققات أمان متقدمة
حماية شاملة من كلمات المرور الضعيفة والمدخلات الخطيرة
"""

import re
import os
import requests
import hashlib
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.conf import settings


class CustomPasswordValidator:
    """
    ✅ متحقق كلمات المرور المتقدم
    """
    
    def __init__(self, min_length=12):
        self.min_length = min_length
        
        # قائمة كلمات المرور المحظورة
        self.forbidden_passwords = {
            'password', 'password123', '123456', '123456789', 'qwerty',
            'abc123', 'password1', 'admin', 'administrator', 'root',
            'user', 'guest', 'test', 'demo', 'welcome', 'login',
            'مرور', 'كلمة', 'سر', 'ادمن', 'مدير', 'مستخدم'
        }
        
        # أنماط ضعيفة
        self.weak_patterns = [
            r'^(.)\1+$',  # تكرار نفس الحرف
            r'^(012|123|234|345|456|567|678|789|890)+',  # أرقام متتالية
            r'^(abc|bcd|cde|def|efg|fgh|ghi|hij|ijk|jkl|klm|lmn|mno|nop|opq|pqr|qrs|rst|stu|tuv|uvw|vwx|wxy|xyz)+',  # أحرف متتالية
            r'^(qwe|wer|ert|rty|tyu|yui|uio|iop|asd|sdf|dfg|fgh|ghj|hjk|jkl|zxc|xcv|cvb|vbn|bnm)+',  # لوحة المفاتيح
        ]
    
    def validate(self, password, user=None):
        """التحقق الشامل من قوة كلمة المرور"""
        
        # 1. التحقق من الطول
        if len(password) < self.min_length:
            raise ValidationError(
                _('كلمة المرور قصيرة جداً. يجب أن تكون %(min_length)d حرف على الأقل.') % {
                    'min_length': self.min_length
                }
            )
        
        # 2. التحقق من التعقيد
        self._validate_complexity(password)
        
        # 3. التحقق من كلمات المرور المحظورة
        self._validate_forbidden_passwords(password)
        
        # 4. التحقق من الأنماط الضعيفة
        self._validate_weak_patterns(password)
        
        # 5. التحقق من معلومات المستخدم
        if user:
            self._validate_user_info(password, user)
        
        # 6. التحقق من قاعدة بيانات كلمات المرور المخترقة (اختياري)
        if getattr(settings, 'CHECK_BREACHED_PASSWORDS', False):
            self._check_breached_password(password)
    
    def _validate_complexity(self, password):
        """التحقق من تعقيد كلمة المرور"""
        checks = {
            'lowercase': bool(re.search(r'[a-z]', password)),
            'uppercase': bool(re.search(r'[A-Z]', password)),
            'digits': bool(re.search(r'\d', password)),
            'special': bool(re.search(r'[!@#$%^&*(),.?":{}|<>]', password)),
            'arabic': bool(re.search(r'[\u0600-\u06FF]', password)),
        }
        
        # يجب أن تحتوي على 3 أنواع على الأقل
        passed_checks = sum(checks.values())
        if passed_checks < 3:
            raise ValidationError(
                _('كلمة المرور ضعيفة. يجب أن تحتوي على 3 أنواع على الأقل من: '
                  'أحرف صغيرة، أحرف كبيرة، أرقام، رموز خاصة')
            )
    
    def _validate_forbidden_passwords(self, password):
        """التحقق من كلمات المرور المحظورة"""
        password_lower = password.lower()
        
        for forbidden in self.forbidden_passwords:
            if forbidden in password_lower:
                raise ValidationError(
                    _('كلمة المرور تحتوي على كلمات محظورة أو شائعة')
                )
    
    def _validate_weak_patterns(self, password):
        """التحقق من الأنماط الضعيفة"""
        password_lower = password.lower()
        
        for pattern in self.weak_patterns:
            if re.search(pattern, password_lower):
                raise ValidationError(
                    _('كلمة المرور تحتوي على نمط ضعيف أو متكرر')
                )
    
    def _validate_user_info(self, password, user):
        """التحقق من عدم احتواء كلمة المرور على معلومات المستخدم"""
        password_lower = password.lower()
        
        # معلومات المستخدم للتحقق منها
        user_info = [
            getattr(user, 'username', ''),
            getattr(user, 'first_name', ''),
            getattr(user, 'last_name', ''),
            getattr(user, 'email', '').split('@')[0] if getattr(user, 'email', '') else '',
        ]
        
        for info in user_info:
            if info and len(info) > 2 and info.lower() in password_lower:
                raise ValidationError(
                    _('كلمة المرور لا يجب أن تحتوي على معلومات شخصية')
                )
    
    def _check_breached_password(self, password):
        """التحقق من قاعدة بيانات كلمات المرور المخترقة (HaveIBeenPwned)"""
        try:
            # حساب SHA-1 hash لكلمة المرور
            sha1_hash = hashlib.sha1(password.encode('utf-8')).hexdigest().upper()
            prefix = sha1_hash[:5]
            suffix = sha1_hash[5:]
            
            # استعلام API
            response = requests.get(
                f'https://api.pwnedpasswords.com/range/{prefix}',
                timeout=3
            )
            
            if response.status_code == 200:
                # البحث عن كلمة المرور في النتائج
                for line in response.text.splitlines():
                    hash_suffix, count = line.split(':')
                    if hash_suffix == suffix:
                        raise ValidationError(
                            _('كلمة المرور هذه معروفة ومخترقة. يرجى اختيار كلمة مرور أخرى.')
                        )
        except requests.RequestException:
            # في حالة فشل الاتصال، نتجاهل هذا الفحص
            pass
    
    def get_help_text(self):
        """نص المساعدة لكلمة المرور"""
        return _(
            'كلمة المرور يجب أن تكون %(min_length)d حرف على الأقل وتحتوي على '
            '3 أنواع على الأقل من: أحرف صغيرة، أحرف كبيرة، أرقام، رموز خاصة'
        ) % {'min_length': self.min_length}


def validate_no_script_tags(value):
    """
    ✅ التحقق من عدم وجود script tags في المدخلات
    """
    if not value:
        return
    
    # البحث عن script tags وأنماط خطيرة أخرى
    dangerous_patterns = [
        r'<script[^>]*>.*?</script>',
        r'javascript:',
        r'vbscript:',
        r'on\w+\s*=',
        r'<iframe[^>]*>',
        r'<object[^>]*>',
        r'<embed[^>]*>',
        r'<link[^>]*>',
        r'<meta[^>]*>',
    ]
    
    value_lower = str(value).lower()
    for pattern in dangerous_patterns:
        if re.search(pattern, value_lower, re.IGNORECASE | re.DOTALL):
            raise ValidationError(
                _('المدخل يحتوي على محتوى غير آمن')
            )


def validate_sql_injection_safe(value):
    """
    ✅ التحقق من عدم وجود محاولات SQL injection
    """
    if not value:
        return
    
    # أنماط SQL injection شائعة
    sql_patterns = [
        r'\bunion\s+select\b',
        r'\bdrop\s+table\b',
        r'\binsert\s+into\b',
        r'\bdelete\s+from\b',
        r'\bupdate\s+.*\s+set\b',
        r'\bexec\s*\(',
        r'\bexecute\s*\(',
        r'\bsp_\w+',
        r'\bxp_\w+',
        r'--',
        r'/\*.*\*/',
        r'\bchar\s*\(',
        r'\bascii\s*\(',
        r'\bsubstring\s*\(',
        r'\bwaitfor\s+delay\b',
    ]
    
    value_lower = str(value).lower()
    for pattern in sql_patterns:
        if re.search(pattern, value_lower, re.IGNORECASE):
            raise ValidationError(
                _('المدخل يحتوي على محتوى غير آمن')
            )


def validate_safe_filename(value):
    """
    ✅ التحقق من أمان اسم الملف
    """
    if not value:
        return
    
    # أحرف محظورة في أسماء الملفات
    forbidden_chars = ['<', '>', ':', '"', '|', '?', '*', '\\', '/', '\0']
    
    for char in forbidden_chars:
        if char in value:
            raise ValidationError(
                _('اسم الملف يحتوي على أحرف غير مسموحة')
            )
    
    # أسماء ملفات محظورة (Windows)
    forbidden_names = [
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
    ]
    
    name_without_ext = os.path.splitext(value)[0].upper()
    if name_without_ext in forbidden_names:
        raise ValidationError(
            _('اسم الملف محظور')
        )


# إضافة المتحققات إلى قائمة المتحققات المتاحة
SECURE_VALIDATORS = {
    'no_script_tags': validate_no_script_tags,
    'sql_injection_safe': validate_sql_injection_safe,
    'safe_filename': validate_safe_filename,
}


def get_validator(validator_name):
    """
    ✅ الحصول على متحقق بالاسم
    """
    return SECURE_VALIDATORS.get(validator_name)