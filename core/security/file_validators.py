"""
🔒 متحققات أمان الملفات المتقدمة
حماية شاملة من File Upload attacks
"""

import os
import hashlib
from PIL import Image
from django.core.exceptions import ValidationError
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.core.validators import FileExtensionValidator

# محاولة استيراد python-magic مع fallback
try:
    import magic
    MAGIC_AVAILABLE = True
except ImportError:
    MAGIC_AVAILABLE = False
    # لا نطبع رسائل أثناء الاستيراد لتجنب مشاكل WSGI
    import logging
    logger = logging.getLogger(__name__)
    logger.warning("python-magic not available. File type validation will be limited.")


class SecureFileValidator:
    """
    ✅ متحقق أمان الملفات المتقدم
    """
    
    # الامتدادات المسموحة لكل نوع
    ALLOWED_EXTENSIONS = {
        'image': ['jpg', 'jpeg', 'png', 'gif', 'webp'],
        'document': ['pdf', 'doc', 'docx', 'txt'],
        'spreadsheet': ['xls', 'xlsx', 'csv'],
        'archive': ['zip', 'rar'],
    }
    
    # أنواع MIME المسموحة
    ALLOWED_MIME_TYPES = {
        'image/jpeg': ['jpg', 'jpeg'],
        'image/png': ['png'],
        'image/gif': ['gif'],
        'image/webp': ['webp'],
        'application/pdf': ['pdf'],
        'application/msword': ['doc'],
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['docx'],
        'text/plain': ['txt'],
        'application/vnd.ms-excel': ['xls'],
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['xlsx'],
        'text/csv': ['csv'],
        'application/zip': ['zip'],
    }
    
    # الحد الأقصى لحجم الملف (بالبايت)
    MAX_FILE_SIZES = {
        'image': 5 * 1024 * 1024,      # 5MB
        'document': 10 * 1024 * 1024,  # 10MB
        'spreadsheet': 15 * 1024 * 1024, # 15MB
        'archive': 50 * 1024 * 1024,   # 50MB
    }
    
    def __init__(self, file_type='image', max_size=None):
        self.file_type = file_type
        self.max_size = max_size or self.MAX_FILE_SIZES.get(file_type, 5 * 1024 * 1024)
        self.allowed_extensions = self.ALLOWED_EXTENSIONS.get(file_type, ['jpg', 'png'])
    
    def __call__(self, file):
        """
        التحقق الشامل من أمان الملف
        """
        # 1. التحقق من حجم الملف
        self._validate_file_size(file)
        
        # 2. التحقق من امتداد الملف
        self._validate_file_extension(file)
        
        # 3. التحقق من نوع MIME الحقيقي
        self._validate_mime_type(file)
        
        # 4. التحقق من محتوى الملف
        self._validate_file_content(file)
        
        # 5. فحص الملف للبحث عن محتوى خبيث
        self._scan_malicious_content(file)
        
        return file
    
    def _validate_file_size(self, file):
        """التحقق من حجم الملف"""
        if file.size > self.max_size:
            raise ValidationError(
                _('حجم الملف كبير جداً. الحد الأقصى المسموح: %(max_size)s MB') % {
                    'max_size': self.max_size / (1024 * 1024)
                }
            )
    
    def _validate_file_extension(self, file):
        """التحقق من امتداد الملف"""
        ext = os.path.splitext(file.name)[1][1:].lower()
        
        if ext not in self.allowed_extensions:
            raise ValidationError(
                _('نوع الملف غير مسموح. الأنواع المسموحة: %(extensions)s') % {
                    'extensions': ', '.join(self.allowed_extensions)
                }
            )
    
    def _validate_mime_type(self, file):
        """التحقق من نوع MIME الحقيقي"""
        if not MAGIC_AVAILABLE:
            # إذا لم تكن مكتبة magic متاحة، استخدم فحص بسيط بناءً على الامتداد
            ext = os.path.splitext(file.name)[1][1:].lower()
            if ext not in self.allowed_extensions:
                raise ValidationError(
                    _('نوع الملف غير مسموح. الأنواع المسموحة: %(extensions)s') % {
                        'extensions': ', '.join(self.allowed_extensions)
                    }
                )
            return
        
        try:
            # قراءة أول 2048 بايت لتحديد نوع الملف
            file.seek(0)
            file_header = file.read(2048)
            file.seek(0)
            
            # استخدام python-magic لتحديد نوع MIME الحقيقي
            mime_type = magic.from_buffer(file_header, mime=True)
            
            # التحقق من أن نوع MIME مسموح
            if mime_type not in self.ALLOWED_MIME_TYPES:
                raise ValidationError(
                    _('نوع الملف غير مسموح: %(mime_type)s') % {
                        'mime_type': mime_type
                    }
                )
            
            # التحقق من تطابق الامتداد مع نوع MIME
            ext = os.path.splitext(file.name)[1][1:].lower()
            expected_extensions = self.ALLOWED_MIME_TYPES[mime_type]
            
            if ext not in expected_extensions:
                raise ValidationError(
                    _('امتداد الملف لا يتطابق مع محتواه الحقيقي')
                )
                
        except Exception as e:
            if MAGIC_AVAILABLE:
                raise ValidationError(
                    _('فشل في التحقق من نوع الملف: %(error)s') % {
                        'error': str(e)
                    }
                )
            else:
                # fallback للفحص البسيط
                ext = os.path.splitext(file.name)[1][1:].lower()
                if ext not in self.allowed_extensions:
                    raise ValidationError(
                        _('نوع الملف غير مسموح. الأنواع المسموحة: %(extensions)s') % {
                            'extensions': ', '.join(self.allowed_extensions)
                        }
                    )
    
    def _validate_file_content(self, file):
        """التحقق من محتوى الملف للصور"""
        if self.file_type == 'image':
            try:
                file.seek(0)
                # محاولة فتح الصورة للتأكد من صحتها
                image = Image.open(file)
                image.verify()
                file.seek(0)
                
                # التحقق من أبعاد الصورة
                if image.size[0] > 10000 or image.size[1] > 10000:
                    raise ValidationError(
                        _('أبعاد الصورة كبيرة جداً. الحد الأقصى: 10000x10000 بكسل')
                    )
                    
            except Exception as e:
                raise ValidationError(
                    _('الملف ليس صورة صحيحة: %(error)s') % {
                        'error': str(e)
                    }
                )
    
    def _scan_malicious_content(self, file):
        """فحص الملف للبحث عن محتوى خبيث"""
        file.seek(0)
        content = file.read(8192)  # قراءة أول 8KB
        file.seek(0)
        
        # البحث عن أنماط خبيثة شائعة
        malicious_patterns = [
            b'<?php',
            b'<script',
            b'javascript:',
            b'vbscript:',
            b'onload=',
            b'onerror=',
            b'eval(',
            b'exec(',
            b'system(',
            b'shell_exec(',
            b'passthru(',
            b'base64_decode(',
        ]
        
        content_lower = content.lower()
        for pattern in malicious_patterns:
            if pattern in content_lower:
                raise ValidationError(
                    _('تم اكتشاف محتوى خبيث في الملف')
                )


def validate_secure_image(file):
    """متحقق آمن للصور"""
    validator = SecureFileValidator('image')
    return validator(file)


def validate_secure_document(file):
    """متحقق آمن للمستندات"""
    validator = SecureFileValidator('document')
    return validator(file)


def validate_secure_spreadsheet(file):
    """متحقق آمن لجداول البيانات"""
    validator = SecureFileValidator('spreadsheet')
    return validator(file)


def generate_secure_filename(original_filename):
    """
    ✅ إنشاء اسم ملف آمن
    """
    # الحصول على الامتداد
    name, ext = os.path.splitext(original_filename)
    
    # تنظيف اسم الملف
    safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).rstrip()
    safe_name = safe_name.replace(' ', '_')
    
    # إضافة hash للتفرد
    hash_suffix = hashlib.md5(original_filename.encode()).hexdigest()[:8]
    
    return f"{safe_name}_{hash_suffix}{ext.lower()}"


def secure_upload_path(instance, filename):
    """
    ✅ مسار رفع آمن للملفات
    """
    # إنشاء اسم ملف آمن
    safe_filename = generate_secure_filename(filename)
    
    # تنظيم الملفات حسب التاريخ والنوع
    from datetime import datetime
    date_path = datetime.now().strftime('%Y/%m/%d')
    
    # تحديد نوع الملف
    model_name = instance.__class__.__name__.lower()
    
    return f'secure_uploads/{model_name}/{date_path}/{safe_filename}'