from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
import re
import os


def validate_phone_number(value):
    """
    التحقق من صحة رقم الهاتف
    يقبل الأرقام المصرية بصيغ مختلفة
    """
    if not value:
        raise ValidationError(_('رقم الهاتف مطلوب'))
    
    # التأكد من أن رقم الهاتف يحتوي على أرقام فقط مع السماح بعلامة + في البداية
    pattern = r'^(\+|00)?[0-9]+$'
    if not re.match(pattern, value):
        raise ValidationError(_('رقم هاتف غير صالح. يجب أن يحتوي على أرقام فقط'))
    
    # التحقق من الطول المناسب لرقم الهاتف المصري
    clean_number = re.sub(r'^(\+20|0020)', '', value)  # إزالة رمز الدولة
    clean_number = re.sub(r'^0', '', clean_number)  # إزالة الصفر البادئ
    
    if not (10 <= len(clean_number) <= 11) or not clean_number.startswith(('10', '11', '12', '15')):
        raise ValidationError(_('رقم هاتف غير صالح'))


def validate_national_id(value):
    """
    التحقق من صحة رقم الهوية الوطنية المصرية
    """
    if not value:
        raise ValidationError(_('رقم الهوية الوطنية مطلوب'))
    
    # التأكد من أن رقم الهوية يحتوي على أرقام فقط
    if not value.isdigit():
        raise ValidationError(_('رقم هوية وطنية غير صالح. يجب أن يحتوي على أرقام فقط'))
    
    # التحقق من الطول المناسب (13 أو 14 رقم)
    if len(value) not in (13, 14):
        raise ValidationError(_('رقم هوية وطنية غير صالح. يجب أن يتكون من 13 أو 14 رقم'))


def validate_positive_number(value):
    """
    التحقق من أن القيمة هي رقم موجب
    """
    try:
        # التحويل إلى رقم إذا كان نصًا
        if isinstance(value, str):
            value = float(value)
        
        if value <= 0:
            raise ValidationError(_('يجب أن تكون القيمة رقم موجب'))
    except (ValueError, TypeError):
        raise ValidationError(_('الرجاء إدخال رقم صالح'))


def validate_file_extension(value):
    """
    التحقق من امتداد الملف
    """
    ext = os.path.splitext(value)[1]  # الحصول على امتداد الملف
    valid_extensions = ['.pdf', '.doc', '.docx', '.xlsx', '.xls', '.txt', '.csv', '.zip', '.rar', '.png', '.jpg', '.jpeg', '.gif']
    
    if not ext.lower() in valid_extensions:
        raise ValidationError(_('امتداد الملف غير مسموح به. الامتدادات المسموحة هي: {0}'.format(', '.join(valid_extensions))))


def validate_image_extension(value):
    """
    التحقق من امتداد الصورة
    """
    ext = os.path.splitext(value)[1]  # الحصول على امتداد الملف
    valid_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.svg']
    
    if not ext.lower() in valid_extensions:
        raise ValidationError(_('امتداد الصورة غير مسموح به. الامتدادات المسموحة هي: {0}'.format(', '.join(valid_extensions))))


def validate_arabic_text(value):
    """
    التحقق من أن النص عربي
    """
    # نطاق الحروف العربية في يونيكود
    arabic_pattern = re.compile(r'^[\u0600-\u06FF\s.,!?()-_]*$')
    
    if not arabic_pattern.match(value):
        raise ValidationError(_('الرجاء إدخال نص باللغة العربية فقط'))


def validate_english_text(value):
    """
    التحقق من أن النص إنجليزي
    """
    # نطاق الحروف الإنجليزية والأرقام والرموز الشائعة
    english_pattern = re.compile(r'^[a-zA-Z0-9\s.,!?()-_]*$')
    
    if not english_pattern.match(value):
        raise ValidationError(_('الرجاء إدخال نص باللغة الإنجليزية فقط'))


def validate_alphanumeric(value):
    """
    التحقق من أن النص يحتوي على أحرف وأرقام فقط
    """
    pattern = re.compile(r'^[a-zA-Z0-9_]*$')
    
    if not pattern.match(value):
        raise ValidationError(_('الرجاء إدخال أحرف وأرقام فقط (بدون مسافات أو رموز خاصة)'))


def validate_percentage(value):
    """
    التحقق من أن القيمة هي نسبة مئوية صالحة (0-100)
    """
    try:
        # التحويل إلى رقم إذا كان نصًا
        if isinstance(value, str):
            value = float(value)
        
        if value < 0 or value > 100:
            raise ValidationError(_('الرجاء إدخال نسبة مئوية صالحة (0-100)'))
    except (ValueError, TypeError):
        raise ValidationError(_('الرجاء إدخال رقم صالح')) 