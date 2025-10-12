from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
import os
import re
from PIL import Image
import io

def validate_phone_number(value):
    """
    متحقق من صحة رقم الهاتف
    يقبل الأرقام والعلامة + في البداية فقط
    """
    if not value:
        raise ValidationError(_('رقم الهاتف مطلوب'))
    
    # التأكد من أن رقم الهاتف يحتوي على أرقام فقط مع السماح بعلامة + في البداية
    pattern = r'^\+?[0-9]+$'
    if not re.match(pattern, value):
        raise ValidationError(_('رقم هاتف غير صالح. يجب أن يحتوي على أرقام فقط'))
    
    # التحقق من الطول المناسب
    if len(value) < 7 or len(value) > 15:
        raise ValidationError(_('رقم هاتف غير صالح. الطول غير مناسب'))


def validate_positive_number(value):
    """
    متحقق من أن الرقم موجب
    """
    try:
        # التحويل إلى رقم إذا كان نصًا
        if isinstance(value, str):
            value = float(value)
        
        if value <= 0:
            raise ValidationError(_('يجب إدخال قيمة موجبة'))
    except (ValueError, TypeError):
        raise ValidationError(_('الرجاء إدخال رقم صالح'))


def validate_future_date(value, include_today=False):
    """
    متحقق من أن التاريخ في المستقبل
    """
    today = timezone.now().date()
    
    if include_today:
        if value < today:
            raise ValidationError(_('يجب أن يكون التاريخ اليوم أو في المستقبل'))
    else:
        if value <= today:
            raise ValidationError(_('يجب أن يكون التاريخ في المستقبل'))


def validate_file_extension(value, allowed_extensions=None):
    """
    متحقق من امتداد الملف
    """
    if not allowed_extensions:
        raise ValidationError(_('لم يتم تحديد الامتدادات المسموحة'))
    
    ext = os.path.splitext(value.name)[1][1:].lower()
    
    if ext not in allowed_extensions:
        raise ValidationError(_(f'نوع الملف غير مسموح. الأنواع المسموحة: {", ".join(allowed_extensions)}'))


def validate_file_size(value, max_size=None):
    """
    متحقق من حجم الملف (بالبايت)
    """
    if not max_size:
        max_size = 5 * 1024 * 1024  # 5 ميجابايت افتراضي
    
    if value.size > max_size:
        max_size_mb = max_size / (1024 * 1024)
        raise ValidationError(_(f'حجم الملف كبير جدًا. يجب أن يكون أقل من {max_size_mb} ميجابايت'))


def validate_image_dimensions(value, min_width=None, min_height=None, max_width=None, max_height=None, aspect_ratio=None):
    """
    متحقق من أبعاد الصورة
    """
    try:
        image = Image.open(value)
        width, height = image.size
        
        # التحقق من الحد الأدنى للعرض
        if min_width and width < min_width:
            raise ValidationError(_(f'عرض الصورة صغير جدًا. يجب أن يكون على الأقل {min_width} بكسل'))
        
        # التحقق من الحد الأدنى للارتفاع
        if min_height and height < min_height:
            raise ValidationError(_(f'ارتفاع الصورة صغير جدًا. يجب أن يكون على الأقل {min_height} بكسل'))
        
        # التحقق من الحد الأقصى للعرض
        if max_width and width > max_width:
            raise ValidationError(_(f'عرض الصورة كبير جدًا. يجب أن يكون أقل من {max_width} بكسل'))
        
        # التحقق من الحد الأقصى للارتفاع
        if max_height and height > max_height:
            raise ValidationError(_(f'ارتفاع الصورة كبير جدًا. يجب أن يكون أقل من {max_height} بكسل'))
        
        # التحقق من نسبة الأبعاد
        if aspect_ratio:
            current_ratio = width / height
            allowed_ratio_diff = 0.01  # السماح بفارق بسيط
            
            if abs(current_ratio - aspect_ratio) > allowed_ratio_diff:
                raise ValidationError(_(f'نسبة أبعاد الصورة غير مناسبة. النسبة المطلوبة هي {aspect_ratio}'))
    
    except (IOError, AttributeError):
        raise ValidationError(_('ملف الصورة تالف أو غير صالح'))


def validate_arabic_text(value):
    """
    متحقق من أن النص عربي
    """
    # نطاق الحروف العربية في يونيكود
    arabic_pattern = re.compile(r'[\u0600-\u06FF\s]+$')
    
    if not arabic_pattern.match(value):
        raise ValidationError(_('الرجاء إدخال نص باللغة العربية فقط'))


def validate_english_text(value):
    """
    متحقق من أن النص إنجليزي
    """
    # نطاق الحروف الإنجليزية والأرقام والرموز الشائعة
    english_pattern = re.compile(r'^[a-zA-Z0-9\s.,!?()-_]*$')
    
    if not english_pattern.match(value):
        raise ValidationError(_('الرجاء إدخال نص باللغة الإنجليزية فقط'))


def validate_alphanumeric(value):
    """
    متحقق من أن النص يحتوي على أحرف وأرقام فقط
    """
    pattern = re.compile(r'^[a-zA-Z0-9_]*$')
    
    if not pattern.match(value):
        raise ValidationError(_('الرجاء إدخال أحرف وأرقام فقط (بدون مسافات أو رموز خاصة)'))


def validate_percentage(value):
    """
    متحقق من أن القيمة هي نسبة مئوية صالحة (0-100)
    """
    try:
        # التحويل إلى رقم إذا كان نصًا
        if isinstance(value, str):
            value = float(value)
        
        if value < 0 or value > 100:
            raise ValidationError(_('الرجاء إدخال نسبة مئوية صالحة (0-100)'))
    except (ValueError, TypeError):
        raise ValidationError(_('الرجاء إدخال رقم صالح'))


def validate_isbn(value):
    """
    متحقق من صحة رقم ISBN
    دعم لكل من ISBN-10 و ISBN-13
    """
    # إزالة الشرطات والمسافات
    isbn = re.sub(r'[\s-]', '', value)
    
    # التحقق من ISBN-10
    if len(isbn) == 10:
        try:
            # التحقق من أن 9 أرقام الأولى هي أرقام
            if not isbn[:9].isdigit():
                raise ValidationError(_('رقم ISBN غير صالح'))
                
            # التحقق من الرقم الأخير (يمكن أن يكون X)
            if not (isbn[9].isdigit() or isbn[9].upper() == 'X'):
                raise ValidationError(_('رقم ISBN غير صالح'))
                
            # حساب التحقق من صحة ISBN-10
            sum = 0
            for i in range(9):
                sum += int(isbn[i]) * (10 - i)
                
            # التعامل مع الحالة الخاصة للرقم الأخير إذا كان X
            if isbn[9].upper() == 'X':
                sum += 10
            else:
                sum += int(isbn[9])
                
            if sum % 11 != 0:
                raise ValidationError(_('رقم ISBN غير صالح'))
                
        except (ValueError, TypeError, IndexError):
            raise ValidationError(_('رقم ISBN غير صالح'))
            
    # التحقق من ISBN-13
    elif len(isbn) == 13:
        try:
            # التحقق من أن كل 13 رقم هي أرقام
            if not isbn.isdigit():
                raise ValidationError(_('رقم ISBN غير صالح'))
                
            # حساب التحقق من صحة ISBN-13
            sum = 0
            for i in range(12):
                if i % 2 == 0:
                    sum += int(isbn[i])
                else:
                    sum += int(isbn[i]) * 3
                    
            check = (10 - (sum % 10)) % 10
            
            if check != int(isbn[12]):
                raise ValidationError(_('رقم ISBN غير صالح'))
                
        except (ValueError, TypeError, IndexError):
            raise ValidationError(_('رقم ISBN غير صالح'))
            
    else:
        raise ValidationError(_('رقم ISBN غير صالح. يجب أن يكون 10 أو 13 رقم')) 