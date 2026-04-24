"""
Management Command لفحص وإصلاح مشاكل الـ migrations
"""
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db import connection
from django.apps import apps
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'فحص وإصلاح مشاكل الـ migrations والـ database schema'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='إصلاح المشاكل المكتشفة تلقائياً'
        )
        
        parser.add_argument(
            '--check-indexes',
            action='store_true',
            help='فحص الـ database indexes'
        )
        
        parser.add_argument(
            '--optimize',
            action='store_true',
            help='تحسين قاعدة البيانات'
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🔍 بدء فحص الـ migrations والـ database schema')
        )
        
        # 1. فحص الـ migrations المعلقة
        self.check_pending_migrations(options.get('fix', False))
        
        # 2. فحص الـ database indexes
        if options.get('check_indexes', False):
            self.check_database_indexes()
        
        # 3. فحص تكامل البيانات
        self.check_data_integrity()
        
        # 4. تحسين قاعدة البيانات
        if options.get('optimize', False):
            self.optimize_database()
        
        self.stdout.write(
            self.style.SUCCESS('✅ انتهى فحص الـ migrations والـ database')
        )

    def check_pending_migrations(self, fix=False):
        """
        فحص الـ migrations المعلقة
        """
        self.stdout.write('📋 فحص الـ migrations المعلقة...')
        
        try:
            # فحص الـ migrations المعلقة
            from django.db.migrations.executor import MigrationExecutor
            executor = MigrationExecutor(connection)
            plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
            
            if plan:
                self.stdout.write(
                    self.style.WARNING(f'⚠️ تم العثور على {len(plan)} migrations معلقة')
                )
                
                for migration, backwards in plan:
                    self.stdout.write(f'  - {migration.app_label}.{migration.name}')
                
                if fix:
                    self.stdout.write('🔧 تطبيق الـ migrations المعلقة...')
                    call_command('migrate', verbosity=1)
                    self.stdout.write(self.style.SUCCESS('✅ تم تطبيق جميع الـ migrations'))
                else:
                    self.stdout.write(
                        self.style.WARNING('💡 استخدم --fix لتطبيق الـ migrations تلقائياً')
                    )
            else:
                self.stdout.write(self.style.SUCCESS('✅ جميع الـ migrations محدثة'))
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ خطأ في فحص الـ migrations: {str(e)}')
            )

    def check_database_indexes(self):
        """
        فحص الـ database indexes
        """
        self.stdout.write('🔍 فحص الـ database indexes...')
        
        try:
            with connection.cursor() as cursor:
                # فحص الـ indexes الموجودة
                cursor.execute("""
                    SELECT name, sql FROM sqlite_master 
                    WHERE type = 'index' AND name NOT LIKE 'sqlite_%'
                    ORDER BY name
                """)
                
                indexes = cursor.fetchall()
                self.stdout.write(f'📊 تم العثور على {len(indexes)} index')
                
                # عرض الـ indexes المهمة للأمان
                security_indexes = [
                    'idx_user_email',
                    'idx_user_is_active',
                    'idx_systemlog_action',
                    'idx_systemlog_timestamp',
                    'idx_systemlog_ip_address'
                ]
                
                existing_indexes = [idx[0] for idx in indexes]
                missing_indexes = [idx for idx in security_indexes if idx not in existing_indexes]
                
                if missing_indexes:
                    self.stdout.write(
                        self.style.WARNING(f'⚠️ indexes مفقودة للأمان: {", ".join(missing_indexes)}')
                    )
                else:
                    self.stdout.write(self.style.SUCCESS('✅ جميع الـ security indexes موجودة'))
                    
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ خطأ في فحص الـ indexes: {str(e)}')
            )

    def check_data_integrity(self):
        """
        فحص تكامل البيانات
        """
        self.stdout.write('🔍 فحص تكامل البيانات...')
        
        try:
            issues = []
            
            # فحص الـ foreign keys
            with connection.cursor() as cursor:
                cursor.execute("PRAGMA foreign_key_check")
                fk_violations = cursor.fetchall()
                
                if fk_violations:
                    issues.append(f'Foreign key violations: {len(fk_violations)}')
                
                # فحص الـ constraints
                cursor.execute("PRAGMA integrity_check")
                integrity_result = cursor.fetchone()
                
                if integrity_result[0] != 'ok':
                    issues.append(f'Integrity check failed: {integrity_result[0]}')
            
            if issues:
                self.stdout.write(
                    self.style.WARNING(f'⚠️ مشاكل في تكامل البيانات:')
                )
                for issue in issues:
                    self.stdout.write(f'  - {issue}')
            else:
                self.stdout.write(self.style.SUCCESS('✅ تكامل البيانات سليم'))
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ خطأ في فحص تكامل البيانات: {str(e)}')
            )

    def optimize_database(self):
        """
        تحسين قاعدة البيانات
        """
        self.stdout.write('⚡ تحسين قاعدة البيانات...')
        
        try:
            with connection.cursor() as cursor:
                # تحليل الجداول لتحسين الـ query planner
                cursor.execute("ANALYZE")
                
                # تنظيف قاعدة البيانات
                cursor.execute("VACUUM")
                
                # إعادة بناء الـ indexes
                cursor.execute("REINDEX")
                
                self.stdout.write(self.style.SUCCESS('✅ تم تحسين قاعدة البيانات'))
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ خطأ في تحسين قاعدة البيانات: {str(e)}')
            )

    def get_database_stats(self):
        """
        الحصول على إحصائيات قاعدة البيانات
        """
        try:
            with connection.cursor() as cursor:
                # حجم قاعدة البيانات
                cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
                db_size = cursor.fetchone()[0]
                
                # عدد الجداول
                cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
                table_count = cursor.fetchone()[0]
                
                # عدد الـ indexes
                cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'")
                index_count = cursor.fetchone()[0]
                
                self.stdout.write('📊 إحصائيات قاعدة البيانات:')
                self.stdout.write(f'  - الحجم: {db_size / 1024 / 1024:.2f} MB')
                self.stdout.write(f'  - عدد الجداول: {table_count}')
                self.stdout.write(f'  - عدد الـ Indexes: {index_count}')
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ خطأ في الحصول على الإحصائيات: {str(e)}')
            )