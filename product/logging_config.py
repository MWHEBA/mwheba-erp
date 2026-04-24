# -*- coding: utf-8 -*-
"""
إعدادات تسجيل نظام المنتجات المجمعة
Bundle System Logging Configuration

Requirements: 10.3, 10.4
"""

import logging
import os
from django.conf import settings


def setup_bundle_logging():
    """إعداد نظام التسجيل للمنتجات المجمعة"""
    
    # إنشاء مجلد السجلات إذا لم يكن موجوداً
    log_dir = os.path.join(settings.BASE_DIR, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # إعداد logger للنظام
    bundle_logger = logging.getLogger('bundle_system')
    bundle_logger.setLevel(logging.INFO)
    
    # تجنب إضافة handlers متعددة
    if not bundle_logger.handlers:
        # إعداد file handler للسجلات العامة
        bundle_file_handler = logging.FileHandler(
            os.path.join(log_dir, 'bundle_system.log'),
            encoding='utf-8'
        )
        bundle_file_handler.setLevel(logging.INFO)
        
        # إعداد file handler للأخطاء
        error_file_handler = logging.FileHandler(
            os.path.join(log_dir, 'bundle_errors.log'),
            encoding='utf-8'
        )
        error_file_handler.setLevel(logging.ERROR)
        
        # إعداد تنسيق السجلات
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        detailed_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s\n'
            'Context: %(pathname)s\n'
            'Extra: %(extra)s\n',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        bundle_file_handler.setFormatter(formatter)
        error_file_handler.setFormatter(detailed_formatter)
        
        # إضافة handlers
        bundle_logger.addHandler(bundle_file_handler)
        bundle_logger.addHandler(error_file_handler)
        
        # إعداد console handler للتطوير
        if settings.DEBUG:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.DEBUG)
            console_handler.setFormatter(formatter)
            bundle_logger.addHandler(console_handler)


class BundleLoggerAdapter(logging.LoggerAdapter):
    """محول logger مخصص للمنتجات المجمعة"""
    
    def process(self, msg, kwargs):
        """إضافة معلومات إضافية للسجلات"""
        extra = kwargs.get('extra', {})
        
        # إضافة معلومات السياق
        if 'bundle_id' in extra:
            msg = f"[Bundle:{extra['bundle_id']}] {msg}"
        
        if 'transaction_id' in extra:
            msg = f"[Transaction:{extra['transaction_id']}] {msg}"
        
        if 'user_id' in extra:
            msg = f"[User:{extra['user_id']}] {msg}"
        
        # تحويل extra إلى string للتسجيل
        kwargs['extra'] = {'extra': str(extra)}
        
        return msg, kwargs


def get_bundle_logger(name=None):
    """الحصول على logger مخصص للمنتجات المجمعة"""
    logger_name = f'bundle_system.{name}' if name else 'bundle_system'
    logger = logging.getLogger(logger_name)
    return BundleLoggerAdapter(logger, {})


# إعداد التسجيل عند استيراد الملف
setup_bundle_logging()