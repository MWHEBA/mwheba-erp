# -*- coding: utf-8 -*-
"""
Middleware لتحسين أداء SQLite وتجنب مشكلة Database Lock
"""

from django.db import connection
from django.conf import settings
import logging
import threading

logger = logging.getLogger(__name__)

# متغير لتتبع ما إذا تم تطبيق التحسينات
_optimizations_applied = threading.local()


class SQLiteOptimizationMiddleware:
    """
    Middleware لتطبيق تحسينات SQLite تلقائياً
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        
    def __call__(self, request):
        # تطبيق التحسينات إذا لم يتم تطبيقها من قبل
        self.ensure_sqlite_optimizations()
        
        response = self.get_response(request)
        return response
    
    def ensure_sqlite_optimizations(self):
        """التأكد من تطبيق تحسينات SQLite"""
        # التحقق من أن قاعدة البيانات هي SQLite
        if not self.is_sqlite_database():
            return
        
        # التحقق من أن التحسينات لم يتم تطبيقها من قبل في هذا الـ thread
        if getattr(_optimizations_applied, 'done', False):
            return
        
        try:
            self.apply_sqlite_optimizations()
            _optimizations_applied.done = True
            logger.info("تم تطبيق تحسينات SQLite تلقائياً")
            
        except Exception as e:
            logger.error(f"فشل في تطبيق تحسينات SQLite: {str(e)}")
    
    def is_sqlite_database(self):
        """التحقق من أن قاعدة البيانات هي SQLite"""
        try:
            db_engine = settings.DATABASES['default']['ENGINE']
            return 'sqlite' in db_engine.lower()
        except (KeyError, AttributeError):
            return False
    
    def apply_sqlite_optimizations(self):
        """تطبيق تحسينات SQLite"""
        with connection.cursor() as cursor:
            # تفعيل WAL mode إذا لم يكن مفعلاً
            cursor.execute("PRAGMA journal_mode;")
            current_mode = cursor.fetchone()[0]
            
            if current_mode.upper() != 'WAL':
                cursor.execute("PRAGMA journal_mode=WAL;")
                logger.debug("تم تفعيل WAL mode")
            
            # تطبيق الإعدادات الأخرى
            optimizations = [
                ("PRAGMA synchronous=NORMAL;", "Synchronous mode"),
                ("PRAGMA cache_size=10000;", "Cache size"),
                ("PRAGMA temp_store=MEMORY;", "Temp store"),
                ("PRAGMA busy_timeout=30000;", "Busy timeout"),
            ]
            
            for pragma, description in optimizations:
                try:
                    cursor.execute(pragma)
                    logger.debug(f"تم تطبيق {description}")
                except Exception as e:
                    logger.warning(f"فشل في تطبيق {description}: {str(e)}")


class DatabaseConnectionMiddleware:
    """
    Middleware لإدارة اتصالات قاعدة البيانات وتجنب الأقفال
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        try:
            response = self.get_response(request)
            return response
        finally:
            # إغلاق الاتصال بعد كل طلب لتجنب الأقفال الطويلة
            self.cleanup_database_connections()
    
    def cleanup_database_connections(self):
        """تنظيف اتصالات قاعدة البيانات"""
        try:
            # إغلاق الاتصال الحالي
            connection.close()
            logger.debug("تم إغلاق اتصال قاعدة البيانات")
            
        except Exception as e:
            logger.warning(f"فشل في إغلاق اتصال قاعدة البيانات: {str(e)}")


class TransactionTimeoutMiddleware:
    """
    Middleware لمراقبة المعاملات الطويلة
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.max_transaction_time = 30  # 30 ثانية
    
    def __call__(self, request):
        import time
        start_time = time.time()
        
        try:
            response = self.get_response(request)
            return response
        finally:
            # مراقبة وقت المعاملة
            transaction_time = time.time() - start_time
            
            if transaction_time > self.max_transaction_time:
                logger.warning(
                    f"معاملة طويلة: {transaction_time:.2f} ثانية "
                    f"للطلب {request.path}"
                )
            elif transaction_time > 10:  # تحذير للمعاملات أكثر من 10 ثوان
                logger.info(
                    f"معاملة بطيئة: {transaction_time:.2f} ثانية "
                    f"للطلب {request.path}"
                )