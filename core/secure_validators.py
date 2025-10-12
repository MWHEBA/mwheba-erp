"""
متحققات آمنة محسنة مع regex patterns محمية
"""

import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

class SecureRegexValidator:
    """
    فئة لإنشاء regex validators آمنة
    """
    
    @staticmethod
    def create_safe_pattern(chars_list):
        """
        إنشاء regex pattern آمن من قائمة أحرف
        
        Args:
            chars_list: قائمة الأحرف المسموحة
            
        Returns:
            str: regex pattern آمن
        """
        # escape special regex characters
        escaped_chars = []
        for char in chars_list:
            if char in r'\.^$*+?{}[]|()\-':
                escaped_chars.append('\\' + char)
            else:
                escaped_chars.append(char)
        
        return '[' + ''.join(escaped_chars) + ']'

# Secure regex patterns
SECURE_PATTERNS = {
    'arabic_text': r'^[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF\s.,!?\(\)\-_]*$',
    'english_text': r'^[a-zA-Z0-9\s.,!?\(\)\-_]*$',
    'alphanumeric': r'^[a-zA-Z0-9_]*$',
    'numeric': r'^[0-9]*$',
    'phone_number': r'^[\+]?[0-9\-\(\)\s]*$',
    'email_safe': r'^[a-zA-Z0-9._%\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$',
    'url_safe': r'^https?://[a-zA-Z0-9.\-]+(?:/[a-zA-Z0-9.\-_/]*)?$',
    'filename_safe': r'^[a-zA-Z0-9.\-_\s]*$',
    'code_safe': r'^[a-zA-Z0-9_\-]*$'
}

def validate_arabic_text_secure(value):
    """
    متحقق آمن للنص العربي
    """
    if not value:
        return
    
    pattern = re.compile(SECURE_PATTERNS['arabic_text'])
    if not pattern.match(value):
        raise ValidationError(_('الرجاء إدخال نص باللغة العربية فقط'))

def validate_english_text_secure(value):
    """
    متحقق آمن للنص الإنجليزي
    """
    if not value:
        return
    
    pattern = re.compile(SECURE_PATTERNS['english_text'])
    if not pattern.match(value):
        raise ValidationError(_('الرجاء إدخال نص باللغة الإنجليزية فقط'))

def validate_alphanumeric_secure(value):
    """
    متحقق آمن للأحرف والأرقام
    """
    if not value:
        return
    
    pattern = re.compile(SECURE_PATTERNS['alphanumeric'])
    if not pattern.match(value):
        raise ValidationError(_('الرجاء إدخال أحرف وأرقام فقط'))

def validate_phone_number_secure(value):
    """
    متحقق آمن لرقم الهاتف
    """
    if not value:
        return
    
    # إزالة المسافات للفحص
    clean_value = value.replace(' ', '').replace('-', '')
    
    # التحقق من الطول
    if len(clean_value) < 10 or len(clean_value) > 15:
        raise ValidationError(_('رقم الهاتف يجب أن يكون بين 10 و 15 رقم'))
    
    pattern = re.compile(SECURE_PATTERNS['phone_number'])
    if not pattern.match(value):
        raise ValidationError(_('رقم الهاتف يحتوي على أحرف غير صحيحة'))

def validate_email_secure(value):
    """
    متحقق آمن للبريد الإلكتروني
    """
    if not value:
        return
    
    pattern = re.compile(SECURE_PATTERNS['email_safe'])
    if not pattern.match(value):
        raise ValidationError(_('عنوان البريد الإلكتروني غير صحيح'))

def validate_url_secure(value):
    """
    متحقق آمن للرابط
    """
    if not value:
        return
    
    pattern = re.compile(SECURE_PATTERNS['url_safe'])
    if not pattern.match(value):
        raise ValidationError(_('الرابط غير صحيح'))

def validate_filename_secure(value):
    """
    متحقق آمن لاسم الملف
    """
    if not value:
        return
    
    # فحص الأحرف الخطيرة
    dangerous_chars = ['<', '>', ':', '"', '|', '?', '*', '/', '\\']
    for char in dangerous_chars:
        if char in value:
            raise ValidationError(_('اسم الملف يحتوي على أحرف غير مسموحة'))
    
    pattern = re.compile(SECURE_PATTERNS['filename_safe'])
    if not pattern.match(value):
        raise ValidationError(_('اسم الملف يحتوي على أحرف غير صحيحة'))

def validate_code_secure(value):
    """
    متحقق آمن للأكواد
    """
    if not value:
        return
    
    pattern = re.compile(SECURE_PATTERNS['code_safe'])
    if not pattern.match(value):
        raise ValidationError(_('الكود يجب أن يحتوي على أحرف وأرقام وشرطات فقط'))

def validate_no_script_tags(value):
    """
    التحقق من عدم وجود script tags
    """
    if not value:
        return
    
    dangerous_patterns = [
        r'<script[^>]*>',
        r'</script>',
        r'javascript:',
        r'vbscript:',
        r'on\w+\s*=',
        r'<iframe[^>]*>',
        r'</iframe>'
    ]
    
    for pattern in dangerous_patterns:
        if re.search(pattern, value, re.IGNORECASE):
            raise ValidationError(_('المحتوى يحتوي على عناصر غير مسموحة'))

def validate_sql_injection_safe(value):
    """
    التحقق من عدم وجود محاولات SQL injection
    """
    if not value:
        return
    
    dangerous_sql_patterns = [
        r'\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|EXECUTE)\b',
        r'--',
        r'/\*',
        r'\*/',
        r'\bUNION\b',
        r'\bOR\s+1\s*=\s*1\b',
        r'\bAND\s+1\s*=\s*1\b'
    ]
    
    for pattern in dangerous_sql_patterns:
        if re.search(pattern, value, re.IGNORECASE):
            raise ValidationError(_('المحتوى يحتوي على أحرف غير مسموحة'))

# Dictionary للوصول السريع للمتحققات
SECURE_VALIDATORS = {
    'arabic_text': validate_arabic_text_secure,
    'english_text': validate_english_text_secure,
    'alphanumeric': validate_alphanumeric_secure,
    'phone_number': validate_phone_number_secure,
    'email': validate_email_secure,
    'url': validate_url_secure,
    'filename': validate_filename_secure,
    'code': validate_code_secure,
    'no_script': validate_no_script_tags,
    'sql_safe': validate_sql_injection_safe
}
