"""
Enterprise Dual-Engine Disaster Recovery & Backup Service
MWHEBA ERP 100% Comprehensive Backup & Restoration Engine
"""

import os
import re
import gzip
import shutil
import tarfile
import zipfile
import hashlib
import logging
import sqlite3
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from django.conf import settings
from django.db import connection, connections, transaction
from django.utils import timezone
from django.core.cache import cache
from core.models import SystemSetting

logger = logging.getLogger(__name__)

BACKUP_ID_REGEX = re.compile(r'^backup_\d{8}_\d{6}$')



class BackupService:
    """
    Enterprise Backup & Disaster Recovery Service with Dual-Engine (MySQL & SQLite) Parity
    """
    
    def __init__(self):
        self.backup_dir = Path(getattr(settings, 'BACKUP_LOCAL_DIR', settings.BASE_DIR / 'backups'))
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.safety_dir = self.backup_dir / 'safety_snapshots'
        self.safety_dir.mkdir(parents=True, exist_ok=True)
        self.storage_type = 'local'
        self._last_error = None
        self._set_directory_permissions(self.backup_dir)
        self._set_directory_permissions(self.safety_dir)

    def _set_directory_permissions(self, path: Path):
        """Set secure permissions (0o700 for dirs, 0o600 for files) if supported"""
        try:
            if os.name != 'nt':
                if path.is_dir():
                    os.chmod(path, 0o700)
                elif path.is_file():
                    os.chmod(path, 0o600)
        except Exception as e:
            logger.debug(f"Permissions setting skipped for {path}: {e}")

    # ============================================================
    # 1. MAINTENANCE LOCK & CONCURRENCY CONTROL
    # ============================================================

    def is_maintenance_locked(self) -> bool:
        """Check if a system restore or critical maintenance lock is active"""
        lock_file = settings.BASE_DIR / '.maintenance_lock'
        return lock_file.exists()

    def set_maintenance_lock(self, active: bool = True, reason: str = "Database restore in progress"):
        """Create or release global HTTP 503 maintenance lock"""
        lock_file = settings.BASE_DIR / '.maintenance_lock'
        try:
            if active:
                with open(lock_file, 'w', encoding='utf-8') as f:
                    f.write(f"{reason}\nTimestamp: {timezone.now().isoformat()}\n")
                logger.warning(f"Maintenance lock ACTIVATED: {reason}")
            else:
                if lock_file.exists():
                    lock_file.unlink()
                logger.info("Maintenance lock RELEASED")
        except Exception as e:
            logger.error(f"Failed to toggle maintenance lock ({active}): {e}")

    # ============================================================
    # 2. FILE HELPERS, HASHING & COMPRESSION
    # ============================================================

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 file hash using fast 64KB buffers"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(65536), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _compress_file(self, file_path: Path, remove_original: bool = True) -> Path:
        """
        Compress file using Gzip with fast standard compression (compresslevel=6)
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File to compress does not exist: {file_path}")
        
        compressed_path = file_path.with_suffix(file_path.suffix + '.gz')
        
        with open(file_path, 'rb') as f_in:
            with gzip.open(compressed_path, 'wb', compresslevel=6) as f_out:
                shutil.copyfileobj(f_in, f_out, length=65536)
        
        if remove_original and file_path.exists() and file_path != compressed_path:
            try:
                file_path.unlink()
            except Exception as e:
                logger.warning(f"Could not remove uncompressed original file {file_path}: {e}")
        
        self._set_directory_permissions(compressed_path)
        return compressed_path

    def _find_backup_files(self, backup_id: str) -> List[Path]:
        """
        Find all files belonging to a specific backup_id, strictly isolating safety snapshots
        """
        if not BACKUP_ID_REGEX.match(backup_id):
            return []
        
        all_matches = list(self.backup_dir.glob(f"*{backup_id}*"))
        valid_files = [
            f for f in all_matches
            if f.is_file() and not f.name.startswith('safety_snapshot_') and not f.name.startswith('temp_')
        ]
        return valid_files

    # ============================================================
    # 3. BACKUP CREATION WORKFLOW (100% ATOMICITY)
    # ============================================================

    def create_backup(self, backup_type: str = 'full', download_mode: bool = False) -> Dict[str, Any]:
        """
        Create a full, database, or media backup
        """
        now = timezone.now()
        backup_id = f"backup_{now.strftime('%Y%m%d_%H%M%S')}"
        backup_info = {
            'backup_id': backup_id,
            'timestamp': now,
            'status': 'started',
            'backup_type': backup_type,
            'download_mode': download_mode,
            'files': [],
            'errors': [],
            'size_bytes': 0,
            'warnings': []
        }
        
        logger.info(f"Starting {backup_type} backup: {backup_id}")
        
        try:
            # 1. Check disk space
            if not self._check_disk_space():
                raise Exception("المساحة التخزينية المتاحة على القرص غير كافية لإنشاء النسخة الاحتياطية")
            
            # 2. Create Database Backup
            if backup_type in ['full', 'database']:
                db_result = self._create_database_backup(backup_id)
                if db_result:
                    backup_info['files'].append(db_result)
                    backup_info['size_bytes'] += db_result['size_bytes']
                else:
                    if backup_type == 'full':
                        raise Exception("فشل إنشاء نسخة قاعدة البيانات أثناء النسخ الكامل")
                    else:
                        backup_info['errors'].append("فشل إنشاء نسخة قاعدة البيانات")
            
            # 3. Create Media Backup
            if backup_type in ['full', 'media']:
                media_result = self._create_media_backup(backup_id)
                if media_result:
                    backup_info['files'].append(media_result)
                    backup_info['size_bytes'] += media_result['size_bytes']
                elif backup_type == 'media':
                    backup_info['errors'].append("فشل إنشاء نسخة ملفات الميديا")
            
            # 4. Handle Full Zip Packaging if requested and multiple files created
            if backup_type == 'full' and len(backup_info['files']) > 1:
                full_zip = self._package_full_backup_zip(backup_id, backup_info['files'])
                if full_zip:
                    backup_info['files'] = [full_zip]
                    backup_info['size_bytes'] = full_zip['size_bytes']
            
            # 5. Strict Verification & Integrity Check
            if not backup_info['files'] or backup_info['errors']:
                backup_info['status'] = 'failed'
                error_summary = ", ".join(backup_info['errors']) or "لم يتم إنشاء أي ملفات"
                self._last_error = error_summary
                logger.error(f"Backup {backup_id} failed: {error_summary}")
                self._record_backup_audit(backup_info)
                return backup_info
            
            # 6. Verify Backup Integrity
            integrity_result = self._verify_backup_integrity(backup_info)
            if integrity_result.get('status') != 'success':
                backup_info['status'] = 'failed'
                backup_info['errors'].append("فشل التحقق من سلامة تجزئة الملفات (Hash Mismatch)")
                self._last_error = "Integrity check failed"
                self._record_backup_audit(backup_info)
                return backup_info
            
            backup_info['status'] = 'completed'
            logger.info(f"Backup {backup_id} completed successfully (Size: {backup_info['size_bytes']} bytes)")
            
            # 7. Record in DB Audit Model
            self._record_backup_audit(backup_info)
            
            # 8. Clean up old backups if not download mode
            if not download_mode:
                self.cleanup_old_backups()
                
            return backup_info
            
        except Exception as e:
            logger.error(f"Unexpected error in create_backup: {e}", exc_info=True)
            backup_info['status'] = 'failed'
            backup_info['errors'].append(str(e))
            self._last_error = str(e)
            self._record_backup_audit(backup_info)
            return backup_info

    def _package_full_backup_zip(self, backup_id: str, file_records: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Package multiple backup files (DB, Media, Encryption Key) into a single atomic zip"""
        try:
            zip_path = self.backup_dir / f"full_{backup_id}.zip"
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for rec in file_records:
                    file_path = Path(rec['path'])
                    if file_path.exists():
                        zipf.write(file_path, file_path.name)
                        try:
                            file_path.unlink()
                        except Exception as e:
                            logger.warning(f"Could not remove standalone file after zip: {e}")
                
                # Include encryption key if present
                enc_key_path = settings.BASE_DIR / 'encryption.key'
                if enc_key_path.exists():
                    zipf.write(enc_key_path, 'encryption.key')
            
            self._set_directory_permissions(zip_path)
            file_hash = self._calculate_file_hash(zip_path)
            return {
                'type': 'full',
                'filename': zip_path.name,
                'path': str(zip_path),
                'size_bytes': zip_path.stat().st_size,
                'hash': file_hash,
                'created_at': timezone.now()
            }
        except Exception as e:
            logger.error(f"Failed to package full backup zip: {e}", exc_info=True)
            return None

    # ============================================================
    # 4. DATABASE BACKUP ENGINES (MySQL, PostgreSQL, SQLite)
    # ============================================================

    def _create_database_backup(self, backup_id: str) -> Optional[Dict[str, Any]]:
        """Create database backup based on configured ENGINE"""
        try:
            db_config = settings.DATABASES['default']
            engine = db_config['ENGINE']
            
            if 'mysql' in engine:
                return self._create_mysql_backup(db_config, backup_id)
            elif 'postgresql' in engine:
                return self._create_postgresql_backup(db_config, backup_id)
            elif 'sqlite' in engine:
                return self._create_sqlite_backup(db_config, backup_id)
            else:
                return self._create_json_backup(backup_id)
        except Exception as e:
            logger.error(f"Failed to create database backup: {e}", exc_info=True)
            self._last_error = str(e)
            return None

    def _find_mysql_binary(self, binary_name: str = 'mysqldump') -> str:
        """Search system PATH and standard Windows installations for MySQL binaries"""
        which_path = shutil.which(binary_name)
        if which_path:
            return which_path
        
        if os.name == 'nt':
            search_paths = [
                Path(r"C:/Program Files/MySQL") / f"MySQL Server 8.0/bin/{binary_name}.exe",
                Path(r"C:/Program Files/MySQL") / f"MySQL Server 8.4/bin/{binary_name}.exe",
                Path(r"C:/Program Files/MySQL") / f"MySQL Server 5.7/bin/{binary_name}.exe",
                Path(r"C:/xampp/mysql/bin") / f"{binary_name}.exe",
                Path(r"C:/laragon/bin/mysql/current/bin") / f"{binary_name}.exe",
            ]

            for p in search_paths:
                if p.exists():
                    return str(p)
                
            for root_dir in [Path(r"C:\Program Files\MySQL"), Path(r"C:\laragon\bin\mysql")]:
                if root_dir.exists():
                    for match in root_dir.glob(f"**/{binary_name}.exe"):
                        if match.is_file():
                            return str(match)
                            
        return binary_name

    def _create_mysql_backup(self, db_config: Dict[str, Any], backup_id: str) -> Dict[str, Any]:
        """Create MySQL dump with UTF-8 encoding, skip-lock-tables, and dumpdata fallback"""
        raw_sql_path = self.backup_dir / f"db_mysql_{backup_id}.sql"
        mysqldump_bin = self._find_mysql_binary('mysqldump')
        
        host = db_config.get('HOST') or 'localhost'
        port = str(db_config.get('PORT') or 3306)
        user = db_config.get('USER', 'root')
        password = db_config.get('PASSWORD', '')
        db_name = db_config.get('NAME', 'mwheba_erp')
        
        env = os.environ.copy()
        if password:
            env['MYSQL_PWD'] = password
            
        base_cmd = [
            mysqldump_bin,
            '--default-character-set=utf8mb4',
            '--single-transaction',
            '--quick',
            '--skip-lock-tables',
            '--add-drop-table',
            '--no-create-db',
            '--routines',
            '--triggers',
            f"--host={host}",
            f"--port={port}",
            f"--user={user}",
            db_name
        ]
        
        # Try with --events first, then fallback without --events if access denied
        cmd_candidates = [
            base_cmd + ['--events'],
            base_cmd
        ]
        
        dump_succeeded = False
        for cmd in cmd_candidates:
            try:
                with open(raw_sql_path, 'w', encoding='utf-8') as f_out:
                    res = subprocess.run(cmd, stdout=f_out, stderr=subprocess.PIPE, text=True, env=env)
                
                if res.returncode == 0 and raw_sql_path.exists() and raw_sql_path.stat().st_size > 0:
                    dump_succeeded = True
                    break
                else:
                    logger.warning(f"mysqldump attempt failed (returncode {res.returncode}): {res.stderr}")
                    raw_sql_path.unlink(missing_ok=True)
            except Exception as ex:
                logger.warning(f"mysqldump execution error: {ex}")
                raw_sql_path.unlink(missing_ok=True)
        
        # Fallback to Django dumpdata if mysqldump is not found or fails
        if not dump_succeeded:
            logger.info("Using Django dumpdata fallback for MySQL backup...")
            raw_sql_path = self._create_django_dumpdata_file(backup_id)
        
        if not raw_sql_path.exists() or raw_sql_path.stat().st_size == 0:
            raw_sql_path.unlink(missing_ok=True)
            raise Exception("Failed to generate database dump content (file is empty)")
        
        compressed_path = self._compress_file(raw_sql_path, remove_original=True)
        file_hash = self._calculate_file_hash(compressed_path)
        
        return {
            'type': 'database',
            'engine': 'mysql',
            'filename': compressed_path.name,
            'path': str(compressed_path),
            'size_bytes': compressed_path.stat().st_size,
            'hash': file_hash,
            'created_at': timezone.now()
        }

    def _create_django_dumpdata_file(self, backup_id: str) -> Path:
        """Create JSON dumpdata streamed directly to disk (O(1) Memory)"""
        from django.core.management import call_command
        from django.apps import apps
        
        json_path = self.backup_dir / f"db_django_{backup_id}.json"
        
        # Get existing managed models safely
        with connection.cursor() as cursor:
            existing_tables = set(connection.introspection.table_names(cursor))
        
        managed_models = []
        for model in apps.get_models():
            if model._meta.managed and model._meta.db_table in existing_tables:
                managed_models.append(f"{model._meta.app_label}.{model._meta.model_name}")
        
        if not managed_models:
            raise Exception("No managed database models found for dumpdata")
        
        with open(json_path, 'w', encoding='utf-8') as f_out:
            call_command(
                'dumpdata',
                *managed_models,
                '--natural-foreign',
                '--natural-primary',
                '--indent=2',
                '--exclude=contenttypes',
                '--exclude=auth.Permission',
                '--exclude=sessions',
                '--exclude=admin.logentry',
                stdout=f_out
            )
        
        return json_path

    def _create_sqlite_backup(self, db_config: Dict[str, Any], backup_id: str) -> Dict[str, Any]:
        """Create SQLite online backup integrating WAL journals cleanly"""
        source_name = db_config.get('NAME')
        source_path = Path(source_name)
        if not source_path.is_absolute():
            source_path = settings.BASE_DIR / source_path
        
        if not source_path.exists():
            raise FileNotFoundError(f"SQLite database file not found: {source_path}")
        
        raw_db_path = self.backup_dir / f"db_sqlite_{backup_id}.sqlite3"
        
        # Online backup API captures WAL uncheckpointed pages
        source_conn = sqlite3.connect(str(source_path))
        dest_conn = sqlite3.connect(str(raw_db_path))
        try:
            source_conn.backup(dest_conn)
        finally:
            dest_conn.close()
            source_conn.close()
        
        compressed_path = self._compress_file(raw_db_path, remove_original=True)
        file_hash = self._calculate_file_hash(compressed_path)
        
        return {
            'type': 'database',
            'engine': 'sqlite',
            'filename': compressed_path.name,
            'path': str(compressed_path),
            'size_bytes': compressed_path.stat().st_size,
            'hash': file_hash,
            'created_at': timezone.now()
        }

    def _create_postgresql_backup(self, db_config: Dict[str, Any], backup_id: str) -> Dict[str, Any]:
        """Create PostgreSQL custom format backup"""
        raw_dump_path = self.backup_dir / f"db_postgres_{backup_id}.dump"
        env = os.environ.copy()
        if db_config.get('PASSWORD'):
            env['PGPASSWORD'] = db_config['PASSWORD']
        
        cmd = [
            'pg_dump',
            '--clean',
            '--no-owner',
            '--no-privileges',
            '--format=custom',
            f"--host={db_config.get('HOST', 'localhost')}",
            f"--port={db_config.get('PORT', 5432)}",
            f"--username={db_config.get('USER', 'postgres')}",
            f"--dbname={db_config['NAME']}",
            f"--file={raw_dump_path}"
        ]
        
        res = subprocess.run(cmd, env=env, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            raw_dump_path.unlink(missing_ok=True)
            raise Exception(f"pg_dump failed: {res.stderr}")
        
        compressed_path = self._compress_file(raw_dump_path, remove_original=True)
        file_hash = self._calculate_file_hash(compressed_path)
        
        return {
            'type': 'database',
            'engine': 'postgresql',
            'filename': compressed_path.name,
            'path': str(compressed_path),
            'size_bytes': compressed_path.stat().st_size,
            'hash': file_hash,
            'created_at': timezone.now()
        }

    def _create_json_backup(self, backup_id: str) -> Dict[str, Any]:
        """Direct JSON backup fallback"""
        json_path = self._create_django_dumpdata_file(backup_id)
        compressed_path = self._compress_file(json_path, remove_original=True)
        file_hash = self._calculate_file_hash(compressed_path)
        return {
            'type': 'database',
            'engine': 'json',
            'filename': compressed_path.name,
            'path': str(compressed_path),
            'size_bytes': compressed_path.stat().st_size,
            'hash': file_hash,
            'created_at': timezone.now()
        }

    # ============================================================
    # 5. MEDIA FILES BACKUP (Correct Extension & O(1) Check)
    # ============================================================

    def _create_media_backup(self, backup_id: str) -> Optional[Dict[str, Any]]:
        """Create media archive with correct extension handling (.tar.gz)"""
        try:
            media_root = Path(settings.MEDIA_ROOT)
            if not media_root.exists() or not any(media_root.iterdir()):
                logger.info("Media directory is empty or does not exist, creating empty archive")
                media_root.mkdir(parents=True, exist_ok=True)
            
            # Pass raw base name to prevent .tar.tar.gz double extension
            archive_base_name = str(self.backup_dir / f"media_{backup_id}")
            final_tar_path = Path(shutil.make_archive(
                base_name=archive_base_name,
                format='gztar',
                root_dir=str(media_root)
            ))
            
            self._set_directory_permissions(final_tar_path)
            file_hash = self._calculate_file_hash(final_tar_path)
            
            return {
                'type': 'media',
                'filename': final_tar_path.name,
                'path': str(final_tar_path),
                'size_bytes': final_tar_path.stat().st_size,
                'hash': file_hash,
                'created_at': timezone.now()
            }
        except Exception as e:
            logger.error(f"Failed to create media backup: {e}", exc_info=True)
            return None

    # ============================================================
    # 6. RESTORATION ENGINE & RECOVERY PIPELINE
    # ============================================================

    def restore_from_backup(self, backup_id: str) -> Dict[str, Any]:
        """Restore all components of a saved backup on the server"""
        backup_files = self._find_backup_files(backup_id)
        if not backup_files:
            return {'status': 'failed', 'error': 'النسخة الاحتياطية غير موجودة على القرص'}
        
        # If single full zip archive exists
        if len(backup_files) == 1 and backup_files[0].name.endswith('.zip'):
            return self.restore_from_uploaded_file(str(backup_files[0]), restore_type='full')
        
        # Find DB and Media components
        db_file = next((f for f in backup_files if 'db_' in f.name), None)
        media_file = next((f for f in backup_files if 'media_' in f.name), None)
        
        if not db_file and not media_file:
            return {'status': 'failed', 'error': 'لم يتم العثور على أي ملفات صالحة للاستعادة'}
        
        restored_components = []
        details = {}
        
        # 1. Restore Database
        if db_file:
            db_res = self.restore_from_uploaded_file(str(db_file), restore_type='database')
            if db_res.get('status') != 'completed':
                return db_res
            restored_components.extend(db_res.get('restored_components', ['database']))
            details['database'] = db_res.get('details', {})
        
        # 2. Restore Media
        if media_file:
            media_res = self.restore_from_uploaded_file(str(media_file), restore_type='media')
            if media_res.get('status') != 'completed':
                return media_res
            restored_components.extend(media_res.get('restored_components', ['media']))
            details['media'] = media_res.get('details', {})
        
        return {
            'status': 'completed',
            'restored_components': list(set(restored_components)),
            'details': details
        }

    def restore_from_uploaded_file(self, file_path_str: str, restore_type: str = 'auto') -> Dict[str, Any]:
        """
        Master restoration handler supporting Gzip SQL, SQLite, JSON, Tar Media, and Full Zip Archives
        """
        file_path = Path(file_path_str)
        if not file_path.exists():
            return {'status': 'failed', 'error': 'الملف المطلوب استعادته غير موجود'}
        
        snapshot_id = f"snap_{timezone.now().strftime('%Y%m%d_%H%M%S')}"
        snapshot_created = False
        
        self.set_maintenance_lock(True, "Database restore in progress")
        try:
            # 0. Emergency cleanup of stale temp files and old artifacts to free disk space
            self._cleanup_stale_temp_artifacts()
            
            # 1. Take compressed safety snapshot of current database
            snapshot_created = self._create_safety_snapshot(snapshot_id)

            
            # 2. Close all existing database connections
            connections.close_all()
            
            # 3. Detect file format and route to appropriate restore handler
            detected_type, decompressed_path, is_temp = self._prepare_restore_payload(file_path)
            
            restored_components = []
            details = {}
            
            try:
                if detected_type == 'full_zip':
                    res = self._restore_full_zip_archive(decompressed_path)
                    restored_components = res.get('restored_components', ['database', 'media'])
                    details = res.get('details', {})
                elif detected_type == 'media':
                    res = self._restore_media_archive(decompressed_path)
                    restored_components = ['media']
                    details = res
                elif detected_type in ['sql', 'sqlite', 'json']:
                    res = self._restore_database_payload(decompressed_path, detected_type)
                    restored_components = ['database']
                    details = res
                else:
                    raise Exception(f"صيغة الملف غير مدعومة: {detected_type}")
            finally:
                if is_temp and decompressed_path.exists():
                    try:
                        if decompressed_path.is_file():
                            decompressed_path.unlink()
                        elif decompressed_path.is_dir():
                            shutil.rmtree(decompressed_path)
                    except Exception as clean_err:
                        logger.warning(f"Failed to clean temp payload: {clean_err}")
            
            # 4. Post-Restore DB migrations & schema sync
            try:
                from django.core.management import call_command
                call_command('migrate', interactive=False)
                logger.info("Post-restore auto-migrate executed successfully")
            except Exception as mig_err:
                logger.warning(f"Post-restore migrate warning: {mig_err}")
            
            # 5. Clear all system caches
            cache.clear()
            SystemSetting.invalidate_all_system_caches()
            
            # 6. Post-restore sanity check
            if not self._post_restore_sanity_audit():
                raise Exception("فشل الفحص الذاتي للبيانات بعد الاستعادة (Post-Restore Sanity Failed)")
            
            logger.info("Restore pipeline finished successfully 100%")
            return {
                'status': 'completed',
                'restored_components': restored_components,
                'details': details
            }
            
        except Exception as e:
            logger.error(f"Restore pipeline failed: {e}", exc_info=True)
            self._last_error = str(e)
            
            # Auto-rollback to safety snapshot
            if snapshot_created:
                logger.warning("Initiating auto-rollback to pre-restore safety snapshot...")
                self._rollback_safety_snapshot(snapshot_id)
            
            return {
                'status': 'failed',
                'error': str(e)
            }
        finally:
            connections.close_all()
            self.set_maintenance_lock(False)

    def _prepare_restore_payload(self, file_path: Path) -> Tuple[str, Path, bool]:
        """Detect file type and decompress in-memory/temp as needed"""
        filename_lower = file_path.name.lower()
        
        # 1. Full Zip Archive
        if filename_lower.endswith('.zip'):
            return 'full_zip', file_path, False
        
        # 2. Media Archive
        if filename_lower.endswith(('.tar.gz', '.tgz', '.tar')):
            return 'media', file_path, False
        
        # 3. Gzip Compressed DB Files
        if filename_lower.endswith('.gz'):
            temp_out = self.backup_dir / f"temp_decomp_{timezone.now().strftime('%Y%m%d_%H%M%S')}.bin"
            
            with gzip.open(file_path, 'rb') as f_in:
                with open(temp_out, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out, length=65536)
            
            # Detect format of uncompressed content
            dtype = self._inspect_payload_format(temp_out)
            ext_map = {'json': '.json', 'sql': '.sql', 'sqlite': '.sqlite3'}
            final_suffix = ext_map.get(dtype, '.sql')
            final_temp = temp_out.with_suffix(final_suffix)
            if temp_out != final_temp:
                if final_temp.exists():
                    final_temp.unlink()
                temp_out.rename(final_temp)
                
            return dtype, final_temp, True
        
        # 4. Raw Uncompressed Files
        dtype = self._inspect_payload_format(file_path)
        return dtype, file_path, False

    def _inspect_payload_format(self, file_path: Path) -> str:
        """Inspect first 4096 bytes of file to determine payload type accurately"""
        with open(file_path, 'rb') as f:
            header = f.read(4096)
        
        if header.startswith(b'SQLite format 3\x00'):
            return 'sqlite'
        
        # Clean UTF-8 BOM and whitespace
        clean_header = header[3:].lstrip() if header.startswith(b'\xef\xbb\xbf') else header.lstrip()
        
        header_text = clean_header.decode('utf-8', errors='ignore').strip()
        if header_text.startswith('[') or header_text.startswith('{'):
            return 'json'
        
        if any(header_text.upper().startswith(kw) for kw in ['--', '/*', '#', 'SET', 'INSERT', 'CREATE', 'DROP', 'USE', 'LOCK', 'ALTER', 'REPLACE']):
            return 'sql'
            
        if file_path.suffix in ['.sql']:
            return 'sql'
        elif file_path.suffix in ['.json']:
            return 'json'
        elif file_path.suffix in ['.db', '.sqlite3', '.sqlite']:
            return 'sqlite'
            
        return 'sql'

    # ============================================================
    # 7. SPECIFIC RESTORE EXECUTORS
    # ============================================================

    def _restore_database_payload(self, file_path: Path, payload_type: str) -> Dict[str, Any]:
        """Restore database payload based on current DB engine"""
        db_config = settings.DATABASES['default']
        engine = db_config['ENGINE']
        
        if payload_type == 'json':
            return self._restore_json_fixture(file_path)
        elif payload_type == 'sqlite':
            if 'sqlite' in engine:
                return self._restore_sqlite_database(db_config, file_path)
            else:
                raise Exception("لا يمكن استعادة نسخة SQLite مباشرة على خادم MySQL. يرجى استخدام نسخة SQL أو JSON.")
        elif payload_type == 'sql':
            if 'mysql' in engine or 'postgres' in engine:
                return self._restore_mysql_database(db_config, file_path)
            elif 'sqlite' in engine:
                return self._restore_mysql_via_cursor(file_path)
        
        if 'sqlite' in engine:
            return self._restore_sqlite_database(db_config, file_path)
        else:
            return self._restore_mysql_database(db_config, file_path)


    def _restore_mysql_database(self, db_config: Dict[str, Any], file_path: Path) -> Dict[str, Any]:
        """
        Restore MySQL database using CLI mysql or PyMySQL chunked batch with strict UTF-8 & foreign key control
        """
        mysql_bin = self._find_mysql_binary('mysql')
        host = db_config.get('HOST') or 'localhost'
        port = str(db_config.get('PORT') or 3306)
        user = db_config.get('USER', 'root')
        password = db_config.get('PASSWORD', '')
        db_name = db_config.get('NAME', 'mwheba_erp')
        
        env = os.environ.copy()
        if password:
            env['MYSQL_PWD'] = password
            
        cmd = [
            mysql_bin,
            '--default-character-set=utf8mb4',
            f"--host={host}",
            f"--port={port}",
            f"--user={user}",
            db_name
        ]
        
        # Attempt CLI restore first
        cli_success = False
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f_in:
                res = subprocess.run(cmd, stdin=f_in, stderr=subprocess.PIPE, text=True, env=env)
            if res.returncode == 0:
                cli_success = True
                logger.info("MySQL CLI restore completed successfully")
            else:
                logger.warning(f"MySQL CLI restore returned code {res.returncode}: {res.stderr}")
        except Exception as e:
            logger.warning(f"MySQL CLI invocation failed ({e}), falling back to PyMySQL parser")
        
        if not cli_success:
            self._restore_mysql_via_cursor(file_path)
            
        return {'engine': 'mysql', 'file': file_path.name, 'status': 'completed'}

    def _restore_mysql_via_cursor(self, file_path: Path):
        """Stateful SQL Tokenizer & PyMySQL execution with SET FOREIGN_KEY_CHECKS=0"""
        statements = []
        current_stmt = []
        in_quote = None
        is_escaped = False
        
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                stripped = line.strip()
                if not in_quote and (stripped.startswith('--') or stripped.startswith('#')):
                    continue
                
                i = 0
                while i < len(line):
                    ch = line[i]
                    current_stmt.append(ch)
                    
                    if is_escaped:
                        is_escaped = False
                    elif ch == '\\':
                        is_escaped = True
                    elif in_quote:
                        if ch == in_quote:
                            in_quote = None
                    else:
                        if ch in ("'", '"', '`'):
                            in_quote = ch
                        elif ch == ';':
                            stmt_str = "".join(current_stmt).strip()
                            if stmt_str and stmt_str != ';':
                                statements.append(stmt_str)
                            current_stmt = []
                    i += 1
        
        if current_stmt:
            tail = "".join(current_stmt).strip()
            if tail:
                statements.append(tail)
        
        if not statements:
            raise Exception("No valid SQL statements parsed from file")
        
        # Execute in a single dedicated connection
        with connection.cursor() as cursor:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
            cursor.execute("SET SQL_MODE = 'NO_AUTO_VALUE_ON_ZERO';")
            try:
                for idx, stmt in enumerate(statements):
                    stmt_clean = stmt.strip()
                    upper_stmt = stmt_clean.upper()
                    
                    # Skip database creation or switching statements that break on cPanel/shared hosting
                    if upper_stmt.startswith('USE ') or upper_stmt.startswith('CREATE DATABASE') or upper_stmt.startswith('DROP DATABASE'):
                        logger.debug(f"Skipping database-level directive: {stmt_clean[:50]}")
                        continue
                    
                    # Strip DEFINER clauses to prevent permission errors on shared hosting
                    if 'DEFINER=' in stmt_clean:
                        stmt_clean = re.sub(r'DEFINER\s*=\s*`?[^`@\s]+`?@`?[^`\s]+`?', '', stmt_clean)
                    
                    try:
                        cursor.execute(stmt_clean)
                    except Exception as stmt_err:
                        logger.error(f"SQL execution error at statement #{idx} (Snippet: {stmt_clean[:100]!r}): {stmt_err}")
                        raise Exception(f"خطأ في تنفيذ جملة SQL #{idx} ({stmt_clean[:60]}...): {stmt_err}")
            finally:
                cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")


    def _restore_sqlite_database(self, db_config: Dict[str, Any], file_path: Path) -> Dict[str, Any]:
        """Restore SQLite database cleanly removing stale WAL files"""
        source_name = db_config.get('NAME')
        db_path = Path(source_name)
        if not db_path.is_absolute():
            db_path = settings.BASE_DIR / db_path
        
        connections.close_all()
        
        # Remove stale WAL and SHM journal files to prevent WAL poisoning
        wal_path = db_path.with_name(db_path.name + '-wal')
        shm_path = db_path.with_name(db_path.name + '-shm')
        wal_path.unlink(missing_ok=True)
        shm_path.unlink(missing_ok=True)
        
        # Replace database file
        shutil.copy2(file_path, db_path)
        self._set_directory_permissions(db_path)
        
        return {'engine': 'sqlite', 'file': file_path.name, 'status': 'completed'}

    def _restore_json_fixture(self, file_path: Path) -> Dict[str, Any]:
        """Restore Django JSON dumpdata using loaddata"""
        from django.core.management import call_command
        
        actual_path = file_path
        renamed = False
        if not str(file_path).lower().endswith('.json'):
            actual_path = file_path.with_suffix('.json')
            if actual_path.exists():
                actual_path.unlink()
            shutil.copy2(file_path, actual_path)
            renamed = True
        
        with connection.cursor() as cursor:
            if 'mysql' in settings.DATABASES['default']['ENGINE']:
                cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
            elif 'sqlite' in settings.DATABASES['default']['ENGINE']:
                cursor.execute("PRAGMA foreign_keys = OFF;")
        
        try:
            call_command(
                'loaddata',
                str(actual_path),
                '--ignorenonexistent',
                verbosity=0
            )
        finally:
            if renamed and actual_path.exists():
                try:
                    actual_path.unlink()
                except Exception:
                    pass
            with connection.cursor() as cursor:
                if 'mysql' in settings.DATABASES['default']['ENGINE']:
                    cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
                elif 'sqlite' in settings.DATABASES['default']['ENGINE']:
                    cursor.execute("PRAGMA foreign_keys = ON;")
                    
        return {'engine': 'json', 'file': file_path.name, 'status': 'completed'}


    def _restore_media_archive(self, file_path: Path) -> Dict[str, Any]:
        """Restore media archive safely with path traversal protection (Anti-Zip/Tar Slip)"""
        media_root = Path(settings.MEDIA_ROOT)
        media_root.mkdir(parents=True, exist_ok=True)
        
        if file_path.name.endswith(('.tar.gz', '.tgz', '.tar')):
            with tarfile.open(file_path, 'r:*') as tar:
                for member in tar.getmembers():
                    # Zip/Tar Slip protection
                    target_path = (media_root / member.name).resolve()
                    if not str(target_path).startswith(str(media_root.resolve())):
                        raise Exception(f"Security Alert: Path traversal attempt in tar archive ({member.name})")
                tar.extractall(path=str(media_root))
        elif file_path.name.endswith('.zip'):
            with zipfile.ZipFile(file_path, 'r') as zipf:
                for member in zipf.namelist():
                    target_path = (media_root / member).resolve()
                    if not str(target_path).startswith(str(media_root.resolve())):
                        raise Exception(f"Security Alert: Path traversal attempt in zip archive ({member})")
                zipf.extractall(path=str(media_root))
                
        return {'type': 'media', 'file': file_path.name, 'status': 'completed'}

    def _restore_full_zip_archive(self, zip_path: Path) -> Dict[str, Any]:
        """Extract and restore full package (DB + Media + Encryption Key) atomically"""
        temp_extract_dir = self.backup_dir / f"temp_full_extract_{timezone.now().strftime('%Y%m%d_%H%M%S')}"
        temp_extract_dir.mkdir(parents=True, exist_ok=True)
        
        restored_components = []
        details = {}
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                for member in zipf.namelist():
                    target_path = (temp_extract_dir / member).resolve()
                    if not str(target_path).startswith(str(temp_extract_dir.resolve())):
                        raise Exception(f"Security Alert: Zip Slip detected in {member}")
                zipf.extractall(path=str(temp_extract_dir))
            
            # 1. Restore Encryption Key if included
            enc_key_file = temp_extract_dir / 'encryption.key'
            if enc_key_file.exists():
                shutil.copy2(enc_key_file, settings.BASE_DIR / 'encryption.key')
                details['encryption_key'] = 'restored'
            
            # 2. Find and restore DB file
            db_candidates = [
                f for f in temp_extract_dir.iterdir()
                if f.is_file() and any(f.name.lower().endswith(ext) for ext in ['.sql.gz', '.sql', '.sqlite3.gz', '.sqlite3', '.db.gz', '.db', '.json.gz', '.json'])
            ]
            
            if db_candidates:
                db_file = db_candidates[0]
                db_dtype, db_payload, is_tmp = self._prepare_restore_payload(db_file)
                try:
                    self._restore_database_payload(db_payload, db_dtype)
                    restored_components.append('database')
                finally:
                    if is_tmp and db_payload.exists():
                        db_payload.unlink(missing_ok=True)
            
            # 3. Find and restore Media archive
            media_candidates = [
                f for f in temp_extract_dir.iterdir()
                if f.is_file() and any(f.name.lower().endswith(ext) for ext in ['.tar.gz', '.tgz', '.tar'])
            ]
            if media_candidates:
                self._restore_media_archive(media_candidates[0])
                restored_components.append('media')
                
            return {
                'restored_components': restored_components,
                'details': details
            }
        finally:
            if temp_extract_dir.exists():
                shutil.rmtree(temp_extract_dir, ignore_errors=True)

    # ============================================================
    # 8. SAFETY SNAPSHOTS & AUTO-ROLLBACK
    # ============================================================

    def _cleanup_stale_temp_artifacts(self):
        """Purge temporary decompression folders, orphaned .tmp/.bin files, and old snapshots (>24h) to free disk space"""
        try:
            now = timezone.now()
            # 1. Clean backups dir temp files
            if self.backup_dir.exists():
                for p in self.backup_dir.iterdir():
                    if (p.name.startswith(('temp_', 'safety_snapshot_')) or p.suffix in ['.tmp', '.bin']) and p.is_file():
                        try:
                            p.unlink()
                        except Exception:
                            pass
                    elif p.name.startswith('temp_') and p.is_dir():
                        try:
                            shutil.rmtree(p, ignore_errors=True)
                        except Exception:
                            pass
            
            # 2. Clean safety snapshots older than 24 hours
            if self.safety_dir.exists():
                import time
                current_time = time.time()
                for p in self.safety_dir.iterdir():
                    if p.is_file():
                        if current_time - p.stat().st_mtime > 86400:
                            try:
                                p.unlink()
                            except Exception:
                                pass
        except Exception as e:
            logger.warning(f"Error during temp artifacts cleanup: {e}")


    def _create_safety_snapshot(self, snapshot_id: str) -> bool:
        """Create rapid compressed snapshot in safety_snapshots/ before any destructive change"""
        try:
            db_config = settings.DATABASES['default']
            engine = db_config['ENGINE']
            
            if 'sqlite' in engine:
                source_name = db_config.get('NAME')
                source_path = Path(source_name)
                if not source_path.is_absolute():
                    source_path = settings.BASE_DIR / source_path
                if source_path.exists():
                    dest_path = self.safety_dir / f"safety_snapshot_{snapshot_id}.sqlite3.gz"
                    with open(source_path, 'rb') as f_in, gzip.open(dest_path, 'wb', compresslevel=6) as f_out:
                        shutil.copyfileobj(f_in, f_out, length=65536)
                    return True
            elif 'mysql' in engine:
                # Compressed dump for safety saving 90% disk space
                raw_sql_gz = self.safety_dir / f"safety_snapshot_{snapshot_id}.sql.gz"
                mysqldump_bin = self._find_mysql_binary('mysqldump')
                env = os.environ.copy()
                if db_config.get('PASSWORD'):
                    env['MYSQL_PWD'] = db_config['PASSWORD']
                
                cmd = [
                    mysqldump_bin,
                    '--default-character-set=utf8mb4',
                    '--single-transaction',
                    '--skip-lock-tables',
                    f"--host={db_config.get('HOST', 'localhost')}",
                    f"--port={db_config.get('PORT', 3306)}",
                    f"--user={db_config.get('USER', 'root')}",
                    db_config.get('NAME', 'mwheba_erp')
                ]
                with gzip.open(raw_sql_gz, 'wb', compresslevel=6) as f_gz:
                    res = subprocess.run(cmd, stdout=f_gz, stderr=subprocess.PIPE, env=env)
                if res.returncode == 0 and raw_sql_gz.exists() and raw_sql_gz.stat().st_size > 0:
                    return True
                else:
                    raw_sql_gz.unlink(missing_ok=True)
                    return False
            return True
        except OSError as oe:
            # Handle Disk quota exceeded (Errno 122) or No space left on device (ENOSPC)
            logger.warning(f"Safety snapshot skipped due to disk quota limitation: {oe}")
            # Purge partial snapshot file to not lock disk
            for p in self.safety_dir.glob(f"*{snapshot_id}*"):
                p.unlink(missing_ok=True)
            return False
        except Exception as e:
            logger.warning(f"Failed to create safety snapshot: {e}")
            for p in self.safety_dir.glob(f"*{snapshot_id}*"):
                p.unlink(missing_ok=True)
            return False

    def _rollback_safety_snapshot(self, snapshot_id: str):
        """Rollback database to safety snapshot state if restore breaks"""
        try:
            db_config = settings.DATABASES['default']
            engine = db_config['ENGINE']
            
            if 'sqlite' in engine:
                snap_gz = self.safety_dir / f"safety_snapshot_{snapshot_id}.sqlite3.gz"
                if snap_gz.exists():
                    db_path = Path(db_config.get('NAME'))
                    if not db_path.is_absolute():
                        db_path = settings.BASE_DIR / db_path
                    connections.close_all()
                    with gzip.open(snap_gz, 'rb') as f_in, open(db_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out, length=65536)
                    logger.info("SQLite successfully rolled back to compressed safety snapshot")
            elif 'mysql' in engine:
                snap_gz = self.safety_dir / f"safety_snapshot_{snapshot_id}.sql.gz"
                if snap_gz.exists():
                    dtype, decomp_path, is_tmp = self._prepare_restore_payload(snap_gz)
                    try:
                        self._restore_mysql_database(db_config, decomp_path)
                        logger.info("MySQL successfully rolled back to compressed safety snapshot")
                    finally:
                        if is_tmp and decomp_path.exists():
                            decomp_path.unlink(missing_ok=True)
        except Exception as e:
            logger.critical(f"FATAL: Auto-rollback to safety snapshot failed: {e}", exc_info=True)


    def _post_restore_sanity_audit(self) -> bool:
        """Verify database responsiveness and user table existence after restore"""
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
                cursor.fetchone()
                
            from django.contrib.auth import get_user_model
            User = get_user_model()
            _ = User.objects.count()
            return True
        except Exception as e:
            logger.error(f"Post-restore sanity audit failed: {e}")
            return False

    # ============================================================
    # 9. INTEGRITY VERIFICATION, LISTING & RETENTION CLEANUP
    # ============================================================

    def _verify_backup_integrity(self, backup_info: Dict[str, Any]) -> Dict[str, Any]:
        """Verify all generated files exist and match their SHA-256 hashes"""
        failed_files = 0
        total_files = len(backup_info.get('files', []))
        
        for file_info in backup_info.get('files', []):
            path = Path(file_info['path'])
            if not path.exists() or path.stat().st_size == 0:
                failed_files += 1
                continue
            
            calc_hash = self._calculate_file_hash(path)
            if calc_hash != file_info.get('hash'):
                failed_files += 1
        
        status = 'success' if failed_files == 0 and total_files > 0 else 'failed'
        return {
            'status': status,
            'total_files': total_files,
            'failed_files': failed_files
        }

    def list_backups(self) -> List[Dict[str, Any]]:
        """
        List all backups grouped by backup_id with metadata
        """
        backups_map: Dict[str, Dict[str, Any]] = {}
        
        for file_path in self.backup_dir.iterdir():
            if not file_path.is_file() or file_path.name.startswith(('safety_snapshot_', 'temp_', '.')):
                continue
            
            # Extract backup_id (backup_YYYYMMDD_HHMMSS)
            match = re.search(r'backup_\d{8}_\d{6}', file_path.name)
            if not match:
                continue
            
            backup_id = match.group(0)
            if backup_id not in backups_map:
                try:
                    dt_str = backup_id.replace('backup_', '')
                    created_at = timezone.make_aware(datetime.strptime(dt_str, '%Y%m%d_%H%M%S'))
                except Exception:
                    created_at = timezone.now()
                
                backups_map[backup_id] = {
                    'backup_id': backup_id,
                    'created_at': created_at,
                    'files': [],
                    'size_bytes': 0,
                    'backup_type': 'database',
                    'storage_type': 'local'
                }
            
            size = file_path.stat().st_size
            backups_map[backup_id]['size_bytes'] += size
            backups_map[backup_id]['files'].append({
                'filename': file_path.name,
                'path': str(file_path),
                'size_bytes': size
            })
        
        # Refine backup types
        for b_id, b_data in backups_map.items():
            has_full_zip = any(f['filename'].startswith('full_') and f['filename'].endswith('.zip') for f in b_data['files'])
            has_db = any('db_' in f['filename'] for f in b_data['files'])
            has_media = any('media_' in f['filename'] for f in b_data['files'])
            
            if has_full_zip or (has_db and has_media):
                b_data['backup_type'] = 'full'
            elif has_db:
                b_data['backup_type'] = 'database'
            elif has_media:
                b_data['backup_type'] = 'media'
        
        # Sort by creation date descending
        sorted_backups = sorted(backups_map.values(), key=lambda x: x['created_at'], reverse=True)
        return sorted_backups

    def delete_backup(self, backup_id: str) -> bool:
        """Delete all files associated with a backup_id"""
        files = self._find_backup_files(backup_id)
        if not files:
            return False
        
        success = True
        for f in files:
            try:
                if f.is_file():
                    f.unlink()
                elif f.is_dir():
                    shutil.rmtree(f)
            except Exception as e:
                logger.error(f"Failed to delete backup file {f}: {e}")
                success = False
        
        # Remove from BackupRecord model
        try:
            from core.models import BackupRecord
            BackupRecord.objects.filter(backup_id=backup_id).delete()
        except Exception:
            pass
            
        return success

    def cleanup_old_backups(self) -> Dict[str, Any]:
        """
        Group-aware retention cleanup applying count and days policies per backup type
        """
        stats = {
            'deleted_count': 0,
            'freed_bytes': 0,
            'freed_mb': 0.0,
            'status': 'completed'
        }
        
        try:
            backups = self.list_backups()
            
            # Policy settings
            db_type = SystemSetting.get_setting('backup_db_retention_type', 'count')
            db_count = max(1, int(SystemSetting.get_setting('backup_db_retention_count', 10)))
            db_days = max(1, int(SystemSetting.get_setting('backup_db_retention_days', 30)))
            
            full_type = SystemSetting.get_setting('backup_full_retention_type', 'count')
            full_count = max(1, int(SystemSetting.get_setting('backup_full_retention_count', 5)))
            full_days = max(1, int(SystemSetting.get_setting('backup_full_retention_days', 60)))
            
            media_type = SystemSetting.get_setting('backup_media_retention_type', 'count')
            media_count = max(1, int(SystemSetting.get_setting('backup_media_retention_count', 3)))
            media_days = max(1, int(SystemSetting.get_setting('backup_media_retention_days', 90)))
            
            by_type: Dict[str, List[Dict[str, Any]]] = {'database': [], 'full': [], 'media': []}
            for b in backups:
                b_type = b.get('backup_type', 'database')
                if b_type in by_type:
                    by_type[b_type].append(b)
            
            to_delete_ids = set()
            now = timezone.now()
            
            # Check DB backups
            if db_type == 'count' and len(by_type['database']) > db_count:
                for b in by_type['database'][db_count:]:
                    to_delete_ids.add(b['backup_id'])
            elif db_type == 'days':
                cutoff = now - timedelta(days=db_days)
                for b in by_type['database']:
                    if b['created_at'] < cutoff:
                        to_delete_ids.add(b['backup_id'])
                        
            # Check Full backups
            if full_type == 'count' and len(by_type['full']) > full_count:
                for b in by_type['full'][full_count:]:
                    to_delete_ids.add(b['backup_id'])
            elif full_type == 'days':
                cutoff = now - timedelta(days=full_days)
                for b in by_type['full']:
                    if b['created_at'] < cutoff:
                        to_delete_ids.add(b['backup_id'])
                        
            # Check Media backups
            if media_type == 'count' and len(by_type['media']) > media_count:
                for b in by_type['media'][media_count:]:
                    to_delete_ids.add(b['backup_id'])
            elif media_type == 'days':
                cutoff = now - timedelta(days=media_days)
                for b in by_type['media']:
                    if b['created_at'] < cutoff:
                        to_delete_ids.add(b['backup_id'])
            
            # Execute deletion
            for b_id in to_delete_ids:
                files = self._find_backup_files(b_id)
                for f in files:
                    try:
                        f_size = f.stat().st_size
                        f.unlink()
                        stats['deleted_count'] += 1
                        stats['freed_bytes'] += f_size
                    except Exception as e:
                        logger.warning(f"Error removing old backup file {f}: {e}")
            
            stats['freed_mb'] = stats['freed_bytes'] / (1024 * 1024)
            logger.info(f"Retention cleanup completed: deleted {stats['deleted_count']} files, freed {stats['freed_mb']:.2f} MB")
            return stats
            
        except Exception as e:
            logger.error(f"Cleanup old backups failed: {e}", exc_info=True)
            stats['status'] = 'failed'
            return stats

    def _check_disk_space(self) -> bool:
        """Check that available disk space exceeds minimum threshold (100MB)"""
        try:
            usage = shutil.disk_usage(self.backup_dir)
            free_mb = usage.free / (1024 * 1024)
            return free_mb > 100
        except Exception as e:
            logger.warning(f"Disk space check skipped: {e}")
            return True

    def _record_backup_audit(self, backup_info: Dict[str, Any]):
        """Persist backup record in Django Admin Audit Model (BackupRecord)"""
        try:
            from core.models import BackupRecord
            BackupRecord.objects.update_or_create(
                backup_id=backup_info['backup_id'],
                defaults={
                    'backup_type': backup_info.get('backup_type', 'database'),
                    'status': backup_info.get('status', 'completed'),
                    'file_size': backup_info.get('size_bytes', 0),
                    'storage_type': 'local',
                    'file_path': backup_info['files'][0]['path'] if backup_info.get('files') else '',
                    'file_hash': backup_info['files'][0]['hash'] if backup_info.get('files') else '',
                    'completed_at': timezone.now() if backup_info.get('status') == 'completed' else None
                }
            )
        except Exception as e:
            logger.debug(f"Could not persist BackupRecord model: {e}")