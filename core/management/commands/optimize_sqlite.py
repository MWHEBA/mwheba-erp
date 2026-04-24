# -*- coding: utf-8 -*-
"""
أمر Django لتطبيق تحسينات SQLite وحل مشكلة Database Lock
"""

from django.core.management.base import BaseCommand
from django.db import connection
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """أمر تطبيق تحسينات SQLite"""
    
    help = 'تطبيق تحسينات SQLite لحل مشكلة Database Lock'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--check-only',
            action='store_true',
            help='فحص الإعدادات الحالية فقط بدون تطبيق تغييرات',
        )
        
        parser.add_argument(
            '--force-wal',
            action='store_true',
            help='إجبار تفعيل WAL mode حتى لو كان مفعلاً',
        )
    
    def handle(self, *args, **options):
        """تنفيذ الأمر"""
        
        # التحقق من أن قاعدة البيانات هي SQLite
        if not self.is_sqlite_database():
            self.stdout.write(
                self.style.WARNING('قاعدة البيانات ليست SQLite - لا حاجة للتحسينات')
            )
            return
        
        self.stdout.write('🔧 بدء تطبيق تحسينات SQLite...')
        
        if options['check_only']:
            self.check_current_settings()
        else:
            self.apply_optimizations(options['force_wal'])
    
    def is_sqlite_database(self):
        """التحقق من أن قاعدة البيانات هي SQLite"""
        try:
            db_engine = settings.DATABASES['default']['ENGINE']
            return 'sqlite' in db_engine.lower()
        except (KeyError, AttributeError):
            return False
    
    def check_current_settings(self):
        """فحص الإعدادات الحالية"""
        self.stdout.write('📊 فحص الإعدادات الحالية...')
        
        try:
            with connection.cursor() as cursor:
                # فحص journal mode
                cursor.execute("PRAGMA journal_mode;")
                journal_mode = cursor.fetchone()[0]
                self.stdout.write(f'Journal Mode: {journal_mode}')
                
                # فحص synchronous
                cursor.execute("PRAGMA synchronous;")
                synchronous = cursor.fetchone()[0]
                self.stdout.write(f'Synchronous: {synchronous}')
                
                # فحص cache size
                cursor.execute("PRAGMA cache_size;")
                cache_size = cursor.fetchone()[0]
                self.stdout.write(f'Cache Size: {cache_size}')
                
                # فحص temp store
                cursor.execute("PRAGMA temp_store;")
                temp_store = cursor.fetchone()[0]
                self.stdout.write(f'Temp Store: {temp_store}')
                
                # فحص busy timeout
                cursor.execute("PRAGMA busy_timeout;")
                busy_timeout = cursor.fetchone()[0]
                self.stdout.write(f'Busy Timeout: {busy_timeout} ms')
                
                # فحص integrity
                cursor.execute("PRAGMA integrity_check;")
                integrity = cursor.fetchone()[0]
                
                if integrity == 'ok':
                    self.stdout.write(
                        self.style.SUCCESS('✅ قاعدة البيانات في حالة جيدة')
                    )
                else:
                    self.stdout.write(
                        self.style.ERROR(f'❌ مشكلة في قاعدة البيانات: {integrity}')
                    )
                    
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ فشل في فحص الإعدادات: {str(e)}')
            )
    
    def apply_optimizations(self, force_wal=False):
        """تطبيق التحسينات"""
        
        try:
            with connection.cursor() as cursor:
                # 1. تفعيل WAL mode
                cursor.execute("PRAGMA journal_mode;")
                current_mode = cursor.fetchone()[0]
                
                if current_mode.upper() != 'WAL' or force_wal:
                    self.stdout.write('🔄 تفعيل WAL mode...')
                    cursor.execute("PRAGMA journal_mode=WAL;")
                    self.stdout.write(
                        self.style.SUCCESS('✅ تم تفعيل WAL mode')
                    )
                else:
                    self.stdout.write('ℹ️ WAL mode مفعل بالفعل')
                
                # 2. تحسين synchronous
                self.stdout.write('🔄 تحسين synchronous mode...')
                cursor.execute("PRAGMA synchronous=NORMAL;")
                self.stdout.write(
                    self.style.SUCCESS('✅ تم تحسين synchronous mode')
                )
                
                # 3. زيادة cache size
                self.stdout.write('🔄 زيادة cache size...')
                cursor.execute("PRAGMA cache_size=10000;")
                self.stdout.write(
                    self.style.SUCCESS('✅ تم زيادة cache size إلى 10000')
                )
                
                # 4. تحسين temp store
                self.stdout.write('🔄 تحسين temp store...')
                cursor.execute("PRAGMA temp_store=MEMORY;")
                self.stdout.write(
                    self.style.SUCCESS('✅ تم تحسين temp store')
                )
                
                # 5. زيادة busy timeout
                self.stdout.write('🔄 زيادة busy timeout...')
                cursor.execute("PRAGMA busy_timeout=60000;")  # 60 ثانية
                self.stdout.write(
                    self.style.SUCCESS('✅ تم زيادة busy timeout إلى 60 ثانية')
                )
                
                # 6. تحسين الفهارس
                self.stdout.write('🔄 تحسين الفهارس...')
                cursor.execute("PRAGMA optimize;")
                self.stdout.write(
                    self.style.SUCCESS('✅ تم تحسين الفهارس')
                )
                
                # 7. تنظيف WAL file
                self.stdout.write('🔄 تنظيف WAL file...')
                cursor.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                self.stdout.write(
                    self.style.SUCCESS('✅ تم تنظيف WAL file')
                )
                
                self.stdout.write(
                    self.style.SUCCESS('🎉 تم تطبيق جميع التحسينات بنجاح!')
                )
                
                # فحص نهائي
                self.stdout.write('\n📊 الإعدادات النهائية:')
                self.check_current_settings()
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ فشل في تطبيق التحسينات: {str(e)}')
            )
            raise