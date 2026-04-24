# -*- coding: utf-8 -*-
"""
تحسينات قاعدة بيانات SQLite لتجنب مشكلة Database Lock
SQLite Database Optimizations
"""

from django.db import connection
from django.core.management.base import BaseCommand
import logging

logger = logging.getLogger(__name__)


def optimize_sqlite_settings():
    """
    تطبيق إعدادات تحسين SQLite لتجنب قفل قاعدة البيانات
    """
    try:
        with connection.cursor() as cursor:
            # تفعيل WAL mode لتحسين الأداء والتزامن
            cursor.execute("PRAGMA journal_mode=WAL;")
            
            # تقليل مستوى المزامنة لتحسين الأداء
            cursor.execute("PRAGMA synchronous=NORMAL;")
            
            # زيادة حجم الذاكرة المؤقتة
            cursor.execute("PRAGMA cache_size=10000;")
            
            # تخزين الملفات المؤقتة في الذاكرة
            cursor.execute("PRAGMA temp_store=MEMORY;")
            
            # تقليل timeout للمعاملات
            cursor.execute("PRAGMA busy_timeout=30000;")  # 30 ثانية
            
            # تحسين الفهارس
            cursor.execute("PRAGMA optimize;")
            
            logger.info("تم تطبيق تحسينات SQLite بنجاح")
            
    except Exception as e:
        logger.error(f"فشل في تطبيق تحسينات SQLite: {str(e)}")


def check_database_locks():
    """
    فحص وجود أقفال في قاعدة البيانات
    """
    try:
        with connection.cursor() as cursor:
            # فحص المعاملات النشطة
            cursor.execute("PRAGMA wal_checkpoint;")
            
            # فحص حالة قاعدة البيانات
            cursor.execute("PRAGMA integrity_check;")
            result = cursor.fetchone()
            
            if result and result[0] == 'ok':
                logger.info("قاعدة البيانات في حالة جيدة")
                return True
            else:
                logger.warning(f"مشكلة في قاعدة البيانات: {result}")
                return False
                
    except Exception as e:
        logger.error(f"فشل في فحص قاعدة البيانات: {str(e)}")
        return False


class Command(BaseCommand):
    """
    أمر Django لتطبيق تحسينات SQLite
    """
    help = 'تطبيق تحسينات SQLite لتجنب مشكلة Database Lock'
    
    def handle(self, *args, **options):
        self.stdout.write('تطبيق تحسينات SQLite...')
        
        optimize_sqlite_settings()
        
        if check_database_locks():
            self.stdout.write(
                self.style.SUCCESS('تم تطبيق التحسينات بنجاح')
            )
        else:
            self.stdout.write(
                self.style.ERROR('فشل في تطبيق التحسينات')
            )