# -*- coding: utf-8 -*-
"""
أمر إدارة لإنشاء فهارس قاعدة البيانات المحسنة للمنتجات المجمعة
Create Bundle Database Indexes Management Command

Requirements: 9.2
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.conf import settings
import logging

from product.services.bundle_query_optimizer import BundleIndexOptimizer

logger = logging.getLogger('bundle_system')


class Command(BaseCommand):
    help = 'إنشاء فهارس قاعدة البيانات المحسنة للمنتجات المجمعة'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='عرض أوامر SQL فقط بدون تنفيذ'
        )
        
        parser.add_argument(
            '--force',
            action='store_true',
            help='إنشاء الفهارس حتى لو كانت موجودة'
        )
        
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='عرض تفاصيل إضافية'
        )
    
    def handle(self, *args, **options):
        self.verbosity = options.get('verbosity', 1)
        self.verbose = options.get('verbose', False)
        self.dry_run = options.get('dry_run', False)
        self.force = options.get('force', False)
        
        self.stdout.write(
            self.style.SUCCESS('بدء إنشاء فهارس المنتجات المجمعة...')
        )
        
        try:
            # الحصول على الفهارس المقترحة
            recommended_indexes = BundleIndexOptimizer.get_recommended_indexes()
            sql_commands = BundleIndexOptimizer.generate_index_sql()
            
            if self.dry_run:
                self.display_sql_commands(sql_commands, recommended_indexes)
                return
            
            # تنفيذ أوامر إنشاء الفهارس
            created_count = 0
            skipped_count = 0
            error_count = 0
            
            with connection.cursor() as cursor:
                for i, (sql_command, index_info) in enumerate(zip(sql_commands, recommended_indexes)):
                    try:
                        # التحقق من وجود الفهرس إذا لم يكن force
                        if not self.force and self.index_exists(cursor, index_info['name']):
                            skipped_count += 1
                            if self.verbose:
                                self.stdout.write(
                                    self.style.WARNING(f'  تم تخطي الفهرس الموجود: {index_info["name"]}')
                                )
                            continue
                        
                        # تنفيذ أمر إنشاء الفهرس
                        cursor.execute(sql_command)
                        created_count += 1
                        
                        if self.verbose:
                            self.stdout.write(
                                self.style.SUCCESS(f'  ✓ تم إنشاء الفهرس: {index_info["name"]}')
                            )
                        
                    except Exception as e:
                        error_count += 1
                        logger.error(f'خطأ في إنشاء الفهرس {index_info["name"]}: {str(e)}')
                        self.stdout.write(
                            self.style.ERROR(f'  ❌ فشل في إنشاء الفهرس {index_info["name"]}: {str(e)}')
                        )
            
            # عرض النتائج النهائية
            self.display_results(created_count, skipped_count, error_count, len(recommended_indexes))
            
        except Exception as e:
            logger.error(f'خطأ في إنشاء فهارس المنتجات المجمعة: {str(e)}')
            raise CommandError(f'خطأ في تشغيل الأمر: {str(e)}')
    
    def display_sql_commands(self, sql_commands, index_info):
        """عرض أوامر SQL بدون تنفيذ"""
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('أوامر SQL لإنشاء الفهارس:'))
        self.stdout.write('='*60)
        
        for i, (sql_command, index) in enumerate(zip(sql_commands, index_info), 1):
            self.stdout.write(f'\n{i}. {index["description"]}')
            self.stdout.write(f'   الجدول: {index["table"]}')
            self.stdout.write(f'   الأعمدة: {", ".join(index["columns"])}')
            self.stdout.write(f'   SQL: {sql_command}')
        
        self.stdout.write('\n' + '='*60)
        self.stdout.write(
            self.style.WARNING('تم عرض الأوامر فقط. استخدم --dry-run=false للتنفيذ الفعلي.')
        )
    
    def index_exists(self, cursor, index_name):
        """التحقق من وجود فهرس"""
        try:
            # استعلام للتحقق من وجود الفهرس (يعتمد على نوع قاعدة البيانات)
            db_engine = settings.DATABASES['default']['ENGINE']
            
            if 'sqlite' in db_engine:
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
                    [index_name]
                )
            elif 'postgresql' in db_engine:
                cursor.execute(
                    "SELECT indexname FROM pg_indexes WHERE indexname = %s",
                    [index_name]
                )
            elif 'mysql' in db_engine:
                cursor.execute(
                    "SELECT INDEX_NAME FROM INFORMATION_SCHEMA.STATISTICS WHERE INDEX_NAME = %s",
                    [index_name]
                )
            else:
                # افتراضي - محاولة SQLite
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
                    [index_name]
                )
            
            return cursor.fetchone() is not None
            
        except Exception as e:
            logger.warning(f'خطأ في التحقق من وجود الفهرس {index_name}: {str(e)}')
            return False
    
    def display_results(self, created_count, skipped_count, error_count, total_count):
        """عرض نتائج إنشاء الفهارس"""
        self.stdout.write('\n' + '='*50)
        self.stdout.write(self.style.SUCCESS('نتائج إنشاء الفهارس'))
        self.stdout.write('='*50)
        
        self.stdout.write(f'إجمالي الفهارس المقترحة: {total_count}')
        self.stdout.write(f'تم إنشاؤها: {created_count}')
        self.stdout.write(f'تم تخطيها (موجودة): {skipped_count}')
        self.stdout.write(f'الأخطاء: {error_count}')
        
        success_rate = ((created_count + skipped_count) / total_count * 100) if total_count > 0 else 0
        
        if error_count == 0:
            self.stdout.write(
                self.style.SUCCESS(f'\n✅ تمت العملية بنجاح! معدل النجاح: {success_rate:.1f}%')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'\n⚠️ تمت العملية مع أخطاء. معدل النجاح: {success_rate:.1f}%')
            )
        
        # نصائح للتحسين
        if created_count > 0:
            self.stdout.write('\n💡 نصائح:')
            self.stdout.write('  • قم بتشغيل ANALYZE أو VACUUM ANALYZE لتحديث إحصائيات قاعدة البيانات')
            self.stdout.write('  • راقب أداء الاستعلامات بعد إنشاء الفهارس')
            self.stdout.write('  • استخدم EXPLAIN QUERY PLAN للتحقق من استخدام الفهارس')
        
        self.stdout.write('='*50)