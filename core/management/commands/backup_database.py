"""
Management command لإنشاء نسخة احتياطية من قاعدة البيانات
يدعم PostgreSQL و SQLite مع إمكانية الرفع على S3
"""

import os
import subprocess
import gzip
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import connection


class Command(BaseCommand):
    help = 'إنشاء نسخة احتياطية من قاعدة البيانات'

    def add_arguments(self, parser):
        parser.add_argument(
            '--compress',
            action='store_true',
            help='ضغط النسخة الاحتياطية باستخدام gzip',
        )
        parser.add_argument(
            '--upload-s3',
            action='store_true',
            help='رفع النسخة الاحتياطية على S3',
        )
        parser.add_argument(
            '--cleanup',
            action='store_true',
            help='حذف النسخ الاحتياطية القديمة',
        )
        parser.add_argument(
            '--retention-days',
            type=int,
            default=30,
            help='عدد الأيام للاحتفاظ بالنسخ الاحتياطية (افتراضي: 30)',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🔄 بدء عملية النسخ الاحتياطي...'))
        
        # إنشاء مجلد النسخ الاحتياطية
        backup_dir = self._get_backup_dir()
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        # إنشاء النسخة الاحتياطية
        backup_file = self._create_backup(backup_dir, options['compress'])
        
        if backup_file:
            self.stdout.write(
                self.style.SUCCESS(f'✅ تم إنشاء النسخة الاحتياطية: {backup_file}')
            )
            
            # رفع على S3 إذا طُلب
            if options['upload_s3']:
                self._upload_to_s3(backup_file)
            
            # تنظيف النسخ القديمة إذا طُلب
            if options['cleanup']:
                self._cleanup_old_backups(backup_dir, options['retention_days'])
        else:
            raise CommandError('❌ فشل إنشاء النسخة الاحتياطية')

    def _get_backup_dir(self):
        """الحصول على مجلد النسخ الاحتياطية"""
        backup_dir = os.environ.get('BACKUP_DIR', 'backups')
        return Path(settings.BASE_DIR) / backup_dir

    def _create_backup(self, backup_dir, compress=False):
        """إنشاء النسخة الاحتياطية"""
        db_config = settings.DATABASES['default']
        db_engine = db_config['ENGINE']
        
        # اسم الملف مع التاريخ والوقت
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'backup_{timestamp}'
        
        if 'postgresql' in db_engine:
            return self._backup_postgresql(db_config, backup_dir, filename, compress)
        elif 'sqlite' in db_engine:
            return self._backup_sqlite(db_config, backup_dir, filename, compress)
        else:
            self.stdout.write(
                self.style.WARNING(f'⚠️ نوع قاعدة البيانات غير مدعوم: {db_engine}')
            )
            return None

    def _backup_postgresql(self, db_config, backup_dir, filename, compress):
        """نسخ احتياطي لـ PostgreSQL"""
        self.stdout.write('📦 إنشاء نسخة احتياطية من PostgreSQL...')
        
        backup_file = backup_dir / f'{filename}.sql'
        
        # إعداد متغيرات البيئة لـ pg_dump
        env = os.environ.copy()
        if db_config.get('PASSWORD'):
            env['PGPASSWORD'] = db_config['PASSWORD']
        
        # بناء أمر pg_dump
        cmd = [
            'pg_dump',
            '-h', db_config.get('HOST', 'localhost'),
            '-p', str(db_config.get('PORT', 5432)),
            '-U', db_config.get('USER', 'postgres'),
            '-F', 'p',  # Plain text format
            '-f', str(backup_file),
            db_config['NAME']
        ]
        
        try:
            subprocess.run(cmd, env=env, check=True, capture_output=True)
            
            # ضغط الملف إذا طُلب
            if compress:
                backup_file = self._compress_file(backup_file)
            
            return backup_file
        except subprocess.CalledProcessError as e:
            self.stdout.write(
                self.style.ERROR(f'❌ خطأ في pg_dump: {e.stderr.decode()}')
            )
            return None
        except FileNotFoundError:
            self.stdout.write(
                self.style.ERROR('❌ pg_dump غير موجود. تأكد من تثبيت PostgreSQL client')
            )
            return None

    def _backup_sqlite(self, db_config, backup_dir, filename, compress):
        """نسخ احتياطي لـ SQLite"""
        self.stdout.write('📦 إنشاء نسخة احتياطية من SQLite...')
        
        db_path = Path(db_config['NAME'])
        backup_file = backup_dir / f'{filename}.db'
        
        try:
            # نسخ ملف قاعدة البيانات
            shutil.copy2(db_path, backup_file)
            
            # ضغط الملف إذا طُلب
            if compress:
                backup_file = self._compress_file(backup_file)
            
            return backup_file
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ خطأ في نسخ SQLite: {str(e)}')
            )
            return None

    def _compress_file(self, file_path):
        """ضغط الملف باستخدام gzip"""
        self.stdout.write('🗜️ ضغط النسخة الاحتياطية...')
        
        compressed_file = Path(str(file_path) + '.gz')
        
        try:
            with open(file_path, 'rb') as f_in:
                with gzip.open(compressed_file, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            # حذف الملف الأصلي
            file_path.unlink()
            
            return compressed_file
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ خطأ في الضغط: {str(e)}')
            )
            return file_path

    def _upload_to_s3(self, backup_file):
        """رفع النسخة الاحتياطية على S3"""
        try:
            import boto3
            from botocore.exceptions import ClientError
        except ImportError:
            self.stdout.write(
                self.style.WARNING('⚠️ boto3 غير مثبت. تخطي الرفع على S3')
            )
            return
        
        bucket_name = os.environ.get('BACKUP_S3_BUCKET')
        if not bucket_name:
            self.stdout.write(
                self.style.WARNING('⚠️ BACKUP_S3_BUCKET غير محدد. تخطي الرفع على S3')
            )
            return
        
        self.stdout.write('☁️ رفع النسخة الاحتياطية على S3...')
        
        try:
            s3_client = boto3.client(
                's3',
                aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
                region_name=os.environ.get('AWS_REGION', 'us-east-1')
            )
            
            s3_key = f'backups/{backup_file.name}'
            s3_client.upload_file(str(backup_file), bucket_name, s3_key)
            
            self.stdout.write(
                self.style.SUCCESS(f'✅ تم الرفع على S3: s3://{bucket_name}/{s3_key}')
            )
        except ClientError as e:
            self.stdout.write(
                self.style.ERROR(f'❌ خطأ في الرفع على S3: {str(e)}')
            )

    def _cleanup_old_backups(self, backup_dir, retention_days):
        """حذف النسخ الاحتياطية القديمة"""
        self.stdout.write(f'🧹 تنظيف النسخ الاحتياطية الأقدم من {retention_days} يوم...')
        
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        deleted_count = 0
        
        for backup_file in backup_dir.glob('backup_*'):
            if backup_file.stat().st_mtime < cutoff_date.timestamp():
                try:
                    backup_file.unlink()
                    deleted_count += 1
                    self.stdout.write(f'  🗑️ حذف: {backup_file.name}')
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(f'  ⚠️ فشل حذف {backup_file.name}: {str(e)}')
                    )
        
        if deleted_count > 0:
            self.stdout.write(
                self.style.SUCCESS(f'✅ تم حذف {deleted_count} نسخة احتياطية قديمة')
            )
        else:
            self.stdout.write('ℹ️ لا توجد نسخ احتياطية قديمة للحذف')
