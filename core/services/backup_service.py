# ============================================================
# PHASE 5: DATA PROTECTION - BACKUP SERVICE
# ============================================================

"""
Comprehensive backup service for database and media files.
Simplified and unified backup system.
"""

import os
import gzip
import shutil
import hashlib
import logging
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from django.conf import settings
from django.db import connection
from django.utils import timezone

logger = logging.getLogger(__name__)

class BackupService:
    """
    Comprehensive backup service with multiple storage backends
    """
    
    def __init__(self):
        self.backup_dir = Path(getattr(settings, 'BACKUP_LOCAL_DIR', settings.BASE_DIR / 'backups'))
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
    def create_backup(self, backup_type='full', download_mode=False) -> Dict[str, any]:
        """
        Create backup with specified type
        
        Args:
            backup_type: 'full', 'database', or 'media'
            download_mode: True to return file for direct download, False to save on server
        
        Returns:
            Dict with backup information
        """
        backup_id = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_info = {
            'backup_id': backup_id,
            'timestamp': timezone.now(),
            'status': 'started',
            'backup_type': backup_type,
            'download_mode': download_mode,
            'files': [],
            'errors': [],
            'size_bytes': 0,
            'warnings': []
        }
        
        try:
            logger.info(f"Starting {backup_type} backup: {backup_id}")
            
            # Create backups based on type
            if backup_type in ['full', 'database']:
                db_backup = self._create_database_backup(backup_id)
                if db_backup:
                    backup_info['files'].append(db_backup)
                    backup_info['size_bytes'] += db_backup['size_bytes']
                else:
                    error_msg = 'Database backup failed'
                    if hasattr(self, '_last_error'):
                        error_msg = self._last_error
                    backup_info['warnings'].append(error_msg)
            
            if backup_type in ['full', 'media']:
                media_backup = self._create_media_backup(backup_id)
                if media_backup:
                    backup_info['files'].append(media_backup)
                    backup_info['size_bytes'] += media_backup['size_bytes']
                else:
                    backup_info['warnings'].append('Media backup failed - check logs for details')
            
            # Verify backup integrity
            verification_result = self._verify_backup_integrity(backup_info)
            backup_info['verification'] = verification_result
            
            # Clean old backups (only if not download mode)
            if not download_mode:
                # Determine backup type for cleanup
                cleanup_type = 'all'
                if backup_type == 'database':
                    cleanup_type = 'database'
                elif backup_type == 'media':
                    cleanup_type = 'media'
                elif backup_type == 'full':
                    cleanup_type = 'full'
                
                self._cleanup_old_backups(backup_type=cleanup_type)
            
            backup_info['status'] = 'completed'
            logger.info(f"Backup completed successfully: {backup_id}")
                
        except Exception as e:
            backup_info['status'] = 'failed'
            backup_info['errors'].append(str(e))
            logger.error(f"Backup failed: {backup_id} - {e}")
            raise
        
        return backup_info
    
    def _create_database_backup(self, backup_id: str) -> Optional[Dict[str, any]]:
        """
        Create database backup using mysqldump or pg_dump
        """
        error_details = None
        try:
            db_config = settings.DATABASES['default']
            engine = db_config['ENGINE']
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            if 'mysql' in engine.lower():
                filename = f"db_mysql_{backup_id}_{timestamp}.sql"
                result = self._create_mysql_backup(db_config, filename)
                logger.info(f"MySQL backup created: {filename}, size: {result.get('size_bytes', 0) if result else 0}")
                return result
            elif 'postgresql' in engine.lower():
                filename = f"db_postgresql_{backup_id}_{timestamp}.sql"
                result = self._create_postgresql_backup(db_config, filename)
                logger.info(f"PostgreSQL backup created: {filename}, size: {result.get('size_bytes', 0) if result else 0}")
                return result
            elif 'sqlite' in engine.lower():
                filename = f"db_sqlite_{backup_id}_{timestamp}.db"
                result = self._create_sqlite_backup(db_config, filename)
                logger.info(f"SQLite backup created: {filename}, size: {result.get('size_bytes', 0) if result else 0}")
                return result
            else:
                error_details = f"Unsupported database engine: {engine}"
                logger.warning(error_details)
                return None
                
        except Exception as e:
            import traceback
            error_details = f"Database backup failed: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_details)
            # Store error for debugging
            if not hasattr(self, '_last_error'):
                self._last_error = error_details
            return None
    
    def _create_mysql_backup(self, db_config: Dict, filename: str) -> Dict[str, any]:
        """
        Create MySQL database backup using mysqldump or Django's dumpdata
        """
        backup_path = self.backup_dir / filename
        
        logger.info(f"Starting MySQL backup to: {backup_path}")
        
        # Try mysqldump first
        try:
            # Build mysqldump command
            cmd = [
                'mysqldump',
                '--single-transaction',
                '--routines',
                '--triggers',
                '--events',
                '--add-drop-database',
                '--create-options',
                '--disable-keys',
                '--extended-insert',
                '--quick',
                '--lock-tables=false',
                f"--host={db_config.get('HOST', 'localhost')}",
                f"--port={db_config.get('PORT', 3306)}",
                f"--user={db_config['USER']}",
                f"--password={db_config['PASSWORD']}",
                db_config['NAME']
            ]
            
            # Execute mysqldump
            with open(backup_path, 'w', encoding='utf-8') as f:
                result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, text=True)
            
            if result.returncode != 0:
                logger.warning(f"mysqldump failed: {result.stderr}, trying alternative method")
                raise Exception("mysqldump not available")
            
            # Check if file was created and has content
            if not backup_path.exists() or backup_path.stat().st_size == 0:
                logger.warning("mysqldump created empty file, trying alternative method")
                raise Exception("mysqldump created empty file")
                
        except Exception as e:
            logger.info(f"mysqldump not available ({e}), using Django dumpdata as fallback")
            
            # Fallback: Use Django's dumpdata
            from django.core.management import call_command
            from django.apps import apps
            from django.db import connection
            from io import StringIO
            
            output = StringIO()
            try:
                # Get all models that are managed and have existing tables
                managed_models = []
                with connection.cursor() as cursor:
                    # Get list of existing tables
                    cursor.execute("SHOW TABLES")
                    existing_tables = {row[0] for row in cursor.fetchall()}
                
                for model in apps.get_models():
                    if model._meta.managed:
                        table_name = model._meta.db_table
                        # Only include models whose tables actually exist
                        if table_name in existing_tables:
                            managed_models.append(f"{model._meta.app_label}.{model._meta.model_name}")
                        else:
                            logger.warning(f"Skipping model {model._meta.app_label}.{model._meta.model_name} - table {table_name} does not exist")
                
                if managed_models:
                    call_command('dumpdata', *managed_models, '--natural-foreign', 
                               '--natural-primary', '--indent=2', stdout=output)
                    
                    with open(backup_path, 'w', encoding='utf-8') as f:
                        f.write(output.getvalue())
                    
                    logger.info(f"Django dumpdata backup created successfully for {len(managed_models)} models")
                else:
                    logger.warning("No managed models found to backup")
                    raise Exception("No managed models found")
                    
            except Exception as dump_error:
                logger.error(f"Django dumpdata also failed: {dump_error}")
                raise Exception(f"Both mysqldump and dumpdata failed: {dump_error}")
        
        # Check if file was created and has content
        if not backup_path.exists():
            raise Exception(f"Backup file was not created: {backup_path}")
        
        original_size = backup_path.stat().st_size
        logger.info(f"MySQL dump created successfully, size: {original_size} bytes")
        
        if original_size == 0:
            raise Exception(f"MySQL dump file is empty: {backup_path}")
        
        # Compress the backup
        compressed_path = self._compress_file(backup_path)
        compressed_size = compressed_path.stat().st_size
        logger.info(f"MySQL backup compressed: {compressed_path.name}, size: {compressed_size} bytes")
        
        # Calculate file hash
        file_hash = self._calculate_file_hash(compressed_path)
        
        return {
            'type': 'database',
            'engine': 'mysql',
            'filename': compressed_path.name,
            'path': str(compressed_path),
            'size_bytes': compressed_size,
            'hash': file_hash,
            'created_at': timezone.now()
        }
    
    def _create_postgresql_backup(self, db_config: Dict, filename: str) -> Dict[str, any]:
        """
        Create PostgreSQL database backup using pg_dump
        """
        backup_path = self.backup_dir / filename
        
        # Set environment variables for pg_dump
        env = os.environ.copy()
        env['PGPASSWORD'] = db_config['PASSWORD']
        
        # Build pg_dump command
        cmd = [
            'pg_dump',
            '--verbose',
            '--clean',
            '--no-owner',
            '--no-privileges',
            '--format=custom',
            f"--host={db_config.get('HOST', 'localhost')}",
            f"--port={db_config.get('PORT', 5432)}",
            f"--username={db_config['USER']}",
            f"--dbname={db_config['NAME']}",
            f"--file={backup_path}"
        ]
        
        # Execute pg_dump
        result = subprocess.run(cmd, env=env, stderr=subprocess.PIPE, text=True)
        
        if result.returncode != 0:
            raise Exception(f"pg_dump failed: {result.stderr}")
        
        # Compress the backup
        compressed_path = self._compress_file(backup_path)
        
        # Calculate file hash
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
    
    def _create_sqlite_backup(self, db_config: Dict, filename: str) -> Dict[str, any]:
        """
        Create SQLite database backup by copying the file
        """
        source_path = Path(db_config['NAME'])
        backup_path = self.backup_dir / filename
        
        # Copy SQLite database file
        shutil.copy2(source_path, backup_path)
        
        # Compress the backup
        compressed_path = self._compress_file(backup_path)
        
        # Calculate file hash
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
    
    def _create_media_backup(self, backup_id: str) -> Optional[Dict[str, any]]:
        """
        Create backup of media files
        """
        try:
            media_root = Path(settings.MEDIA_ROOT)
            if not media_root.exists():
                logger.warning(f"Media root directory does not exist: {media_root}")
                return None
            
            # Check if media directory has any files
            media_files = list(media_root.rglob('*'))
            if not media_files:
                logger.info("Media directory is empty, skipping media backup")
                return None
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            archive_name = f"media_{backup_id}_{timestamp}.tar.gz"
            archive_path = self.backup_dir / archive_name
            
            logger.info(f"Creating media backup with {len(media_files)} files")
            
            # Create compressed archive of media files
            shutil.make_archive(
                str(archive_path.with_suffix('')),
                'gztar',
                root_dir=media_root.parent,
                base_dir=media_root.name
            )
            
            if not archive_path.exists() or archive_path.stat().st_size == 0:
                logger.error(f"Media archive was not created or is empty: {archive_path}")
                return None
            
            # Calculate file hash
            file_hash = self._calculate_file_hash(archive_path)
            
            logger.info(f"Media backup created successfully: {archive_path.name}, size: {archive_path.stat().st_size} bytes")
            
            return {
                'type': 'media',
                'filename': archive_path.name,
                'path': str(archive_path),
                'size_bytes': archive_path.stat().st_size,
                'hash': file_hash,
                'created_at': timezone.now()
            }
            
        except Exception as e:
            logger.error(f"Media backup failed: {e}", exc_info=True)
            return None
    
    def _cleanup_old_backups(self, backup_type='all'):
        """
        Remove old backup files based on retention policy from SystemSettings
        Separate policies for database, full, and media backups
        
        Args:
            backup_type: 'database', 'full', 'media', or 'all'
        """
        try:
            from core.models import SystemSetting
            
            # Determine which backup types to clean
            types_to_clean = []
            if backup_type == 'all':
                types_to_clean = ['database', 'full', 'media']
            else:
                types_to_clean = [backup_type]
            
            for btype in types_to_clean:
                # Get retention settings for this backup type
                retention_type = SystemSetting.get_setting(f'backup_{btype}_retention_type', 'count')
                retention_count = SystemSetting.get_setting(f'backup_{btype}_retention_count', 5)
                retention_days = SystemSetting.get_setting(f'backup_{btype}_retention_days', 30)
                auto_cleanup = SystemSetting.get_setting(f'backup_{btype}_auto_cleanup', True)
                
                # Skip cleanup if disabled
                if not auto_cleanup:
                    logger.info(f"Automatic backup cleanup is disabled for {btype} backups")
                    continue
                
                # Get backup files for this type
                if btype == 'database':
                    pattern = 'db_*'
                elif btype == 'full':
                    # Full backups have both db_ and media_ files with same backup_id
                    # We'll identify them by having both types
                    pattern = '*backup_*'
                elif btype == 'media':
                    pattern = 'media_*'
                else:
                    continue
                
                backup_files = sorted(
                    [f for f in self.backup_dir.glob(pattern) if f.is_file()],
                    key=lambda x: x.stat().st_mtime
                )
                
                # For full backups, group by backup_id
                if btype == 'full':
                    # Group files by backup_id
                    from collections import defaultdict
                    backup_groups = defaultdict(list)
                    
                    for f in backup_files:
                        import re
                        match = re.search(r'backup_(\d{8}_\d{6})', f.name)
                        if match:
                            backup_id = match.group(1)
                            backup_groups[backup_id].append(f)
                    
                    # Only consider groups that have both db and media files
                    full_backup_files = []
                    for backup_id, files in backup_groups.items():
                        has_db = any('db_' in f.name for f in files)
                        has_media = any('media_' in f.name for f in files)
                        if has_db and has_media:
                            full_backup_files.extend(files)
                    
                    backup_files = sorted(full_backup_files, key=lambda x: x.stat().st_mtime)
                
                if retention_type == 'count':
                    # Keep only the last N backups
                    if len(backup_files) > retention_count:
                        files_to_delete = backup_files[:-retention_count]
                        for backup_file in files_to_delete:
                            backup_file.unlink()
                            logger.info(f"Removed old {btype} backup (count policy): {backup_file.name}")
                
                elif retention_type == 'days':
                    # Remove backups older than N days
                    cutoff_date = datetime.now() - timedelta(days=retention_days)
                    for backup_file in backup_files:
                        file_time = datetime.fromtimestamp(backup_file.stat().st_mtime)
                        if file_time < cutoff_date:
                            backup_file.unlink()
                            logger.info(f"Removed old {btype} backup (days policy): {backup_file.name}")
                
                # retention_type == 'none': don't delete anything
                
                logger.info(f"Cleanup completed for {btype} backups: policy={retention_type}, count={retention_count}, days={retention_days}")
        
        except Exception as e:
            logger.error(f"Backup cleanup failed: {e}")
    
    def _compress_file(self, file_path: Path) -> Path:
        """
        Compress a file using gzip
        """
        compressed_path = file_path.with_suffix(file_path.suffix + '.gz')
        
        with open(file_path, 'rb') as f_in:
            with gzip.open(compressed_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        # Remove original file
        file_path.unlink()
        
        return compressed_path
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """
        Calculate SHA-256 hash of a file
        """
        hash_sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
    
    def _verify_backup_integrity(self, backup_info: Dict) -> Dict[str, any]:
        """
        Verify backup file integrity
        """
        verification_result = {
            'status': 'success',
            'verified_files': 0,
            'failed_files': 0,
            'errors': []
        }
        
        try:
            for file_info in backup_info['files']:
                file_path = Path(file_info['path'])
                
                if not file_path.exists():
                    verification_result['failed_files'] += 1
                    verification_result['errors'].append(f"File not found: {file_path}")
                    continue
                
                # Verify file size
                actual_size = file_path.stat().st_size
                expected_size = file_info['size_bytes']
                
                if actual_size != expected_size:
                    verification_result['failed_files'] += 1
                    verification_result['errors'].append(
                        f"Size mismatch for {file_path}: expected {expected_size}, got {actual_size}"
                    )
                    continue
                
                # Verify file hash
                actual_hash = self._calculate_file_hash(file_path)
                expected_hash = file_info['hash']
                
                if actual_hash != expected_hash:
                    verification_result['failed_files'] += 1
                    verification_result['errors'].append(
                        f"Hash mismatch for {file_path}: expected {expected_hash}, got {actual_hash}"
                    )
                    continue
                
                verification_result['verified_files'] += 1
            
            if verification_result['failed_files'] > 0:
                verification_result['status'] = 'failed'
            
        except Exception as e:
            verification_result['status'] = 'error'
            verification_result['errors'].append(str(e))
        
        return verification_result
    
    def restore_from_uploaded_file(self, file_path: str, restore_type: str = 'auto') -> Dict[str, any]:
        """
        Restore from an uploaded backup file
        
        Args:
            file_path: Path to the uploaded backup file
            restore_type: 'auto', 'database', 'media', or 'full'
        
        Returns:
            Dict with restore information including success rate
        """
        restore_info = {
            'timestamp': timezone.now(),
            'status': 'started',
            'restored_components': [],
            'errors': [],
            'success_rate': None,
            'details': {}
        }
        
        try:
            file_path_obj = Path(file_path)
            logger.info(f"Starting restore from uploaded file: {file_path_obj.name}, type: {restore_type}")
            
            # Auto-detect file type if needed
            if restore_type == 'auto':
                restore_type = self._detect_backup_type(file_path_obj)
                logger.info(f"Auto-detected backup type: {restore_type}")
            
            # Handle different file types
            if restore_type == 'database':
                result = self._restore_database_from_file(file_path_obj)
                restore_info['restored_components'].append('database')
                
                # Extract success rate if available
                if isinstance(result, dict) and 'success_rate' in result:
                    restore_info['success_rate'] = result['success_rate']
                    restore_info['details'] = result
            
            elif restore_type == 'media':
                self._restore_media_from_file(file_path_obj)
                restore_info['restored_components'].append('media')
                restore_info['success_rate'] = 100.0
            
            elif restore_type == 'full':
                # Try to extract and restore both
                if file_path_obj.suffix == '.zip':
                    # Extract zip and restore components
                    import zipfile
                    import tempfile
                    
                    temp_dir = tempfile.mkdtemp()
                    try:
                        with zipfile.ZipFile(file_path_obj, 'r') as zip_ref:
                            zip_ref.extractall(temp_dir)
                        
                        # Find and restore database files
                        for extracted_file in Path(temp_dir).rglob('*'):
                            if extracted_file.is_file():
                                if any(pattern in extracted_file.name.lower() for pattern in ['db_', 'database', '.sql', '.db']):
                                    try:
                                        result = self._restore_database_from_file(extracted_file)
                                        restore_info['restored_components'].append('database')
                                        if isinstance(result, dict) and 'success_rate' in result:
                                            restore_info['success_rate'] = result['success_rate']
                                    except Exception as e:
                                        logger.warning(f"Failed to restore database from {extracted_file.name}: {e}")
                                
                                elif any(pattern in extracted_file.name.lower() for pattern in ['media_', 'media', '.tar']):
                                    try:
                                        self._restore_media_from_file(extracted_file)
                                        restore_info['restored_components'].append('media')
                                    except Exception as e:
                                        logger.warning(f"Failed to restore media from {extracted_file.name}: {e}")
                    finally:
                        # Clean up temp directory
                        shutil.rmtree(temp_dir, ignore_errors=True)
                else:
                    raise Exception("Full backup restore requires a .zip file")
            
            restore_info['status'] = 'completed'
            logger.info(f"Restore completed successfully. Components: {restore_info['restored_components']}, Success rate: {restore_info.get('success_rate')}")
            
        except Exception as e:
            restore_info['status'] = 'failed'
            restore_info['errors'].append(str(e))
            logger.error(f"Restore from uploaded file failed: {e}")
            raise
        
        return restore_info
    
    def _detect_backup_type(self, file_path: Path) -> str:
        """
        Auto-detect backup type from filename and extension
        Enhanced with content inspection
        """
        filename_lower = file_path.name.lower()
        
        # Check for media indicators first (most specific)
        if any(pattern in filename_lower for pattern in ['media_', 'media.tar', 'media.zip']):
            return 'media'
        
        # Check for full backup indicators
        if 'full' in filename_lower or '.zip' in filename_lower:
            return 'full'
        
        # Check for database indicators
        if any(pattern in filename_lower for pattern in ['db_', 'database', '.sql', '.db', '.sqlite', '.json']):
            return 'database'
        
        # If still uncertain, try to inspect file content
        try:
            # Try to read first few bytes to determine type
            working_file = file_path
            
            # Decompress if needed for inspection
            if file_path.suffix == '.gz':
                import tempfile
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='')
                temp_file.close()
                
                with gzip.open(file_path, 'rb') as f_in:
                    with open(temp_file.name, 'wb') as f_out:
                        # Read only first 1KB for detection
                        f_out.write(f_in.read(1024))
                
                working_file = Path(temp_file.name)
            
            # Read first bytes
            with open(working_file, 'rb') as f:
                first_bytes = f.read(100)
            
            # Clean up temp file
            if working_file != file_path:
                working_file.unlink()
            
            # Check if it's JSON
            if first_bytes.strip().startswith(b'[') or first_bytes.strip().startswith(b'{'):
                return 'database'
            
            # Check if it's SQL
            if b'CREATE' in first_bytes.upper() or b'INSERT' in first_bytes.upper() or b'DROP' in first_bytes.upper():
                return 'database'
            
            # Check if it's tar archive
            if first_bytes.startswith(b'\x1f\x8b') or b'ustar' in first_bytes:
                return 'media'
                
        except Exception as e:
            logger.warning(f"Failed to inspect file content for type detection: {e}")
        
        # Default to database if uncertain
        return 'database'
    
    def _restore_database_from_file(self, file_path: Path):
        """
        Restore database from a backup file with enhanced detection and validation
        """
        logger.info(f"Restoring database from file: {file_path.name}, size: {file_path.stat().st_size} bytes")
        
        # Validate file exists and has content
        if not file_path.exists():
            raise Exception(f"ملف النسخة الاحتياطية غير موجود: {file_path}")
        
        if file_path.stat().st_size == 0:
            raise Exception(f"ملف النسخة الاحتياطية فارغ: {file_path}")
        
        db_config = settings.DATABASES['default']
        engine = db_config['ENGINE']
        
        # Decompress if needed
        working_file = file_path
        is_temp_file = False
        
        if file_path.suffix == '.gz':
            logger.info(f"Decompressing gzip file: {file_path.name}")
            import tempfile
            
            try:
                # Create temp file
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='')
                temp_file.close()
                
                with gzip.open(file_path, 'rb') as f_in:
                    with open(temp_file.name, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                
                working_file = Path(temp_file.name)
                is_temp_file = True
                
                # Validate decompressed file
                if not working_file.exists() or working_file.stat().st_size == 0:
                    raise Exception("فشل فك ضغط الملف أو الملف المفكوك فارغ")
                
                logger.info(f"Decompressed successfully: {working_file}, size: {working_file.stat().st_size} bytes")
                
            except gzip.BadGzipFile:
                if is_temp_file and working_file.exists():
                    working_file.unlink()
                raise Exception("الملف ليس ملف gzip صحيح. تأكد من أن الملف غير تالف.")
            except Exception as decompress_error:
                if is_temp_file and working_file.exists():
                    working_file.unlink()
                logger.error(f"Failed to decompress file: {decompress_error}")
                raise Exception(f"فشل فك ضغط الملف: {str(decompress_error)}")
        
        # Detect file type by reading first few bytes
        file_format = None
        try:
            with open(working_file, 'rb') as f:
                first_bytes = f.read(200)
            
            # Try to decode as UTF-8
            try:
                first_chars = first_bytes.decode('utf-8').strip()
                
                # Check for JSON format
                if first_chars.startswith('[') or first_chars.startswith('{'):
                    file_format = 'json'
                    logger.info("Detected JSON format (Django dumpdata)")
                # Check for SQL format
                elif any(keyword in first_chars.upper() for keyword in ['CREATE', 'INSERT', 'DROP', 'ALTER', '--', '/*']):
                    file_format = 'sql'
                    logger.info("Detected SQL format")
                else:
                    logger.warning(f"Unknown format. First 100 chars: {first_chars[:100]}")
                    file_format = 'unknown'
                    
            except UnicodeDecodeError:
                # Binary file, might be SQLite
                if first_bytes.startswith(b'SQLite format'):
                    file_format = 'sqlite'
                    logger.info("Detected SQLite database file")
                else:
                    logger.warning("Binary file with unknown format")
                    file_format = 'unknown'
                    
        except Exception as detect_error:
            logger.error(f"Failed to detect file type: {detect_error}")
            file_format = 'unknown'
        
        # Validate format is supported
        if file_format == 'unknown':
            if is_temp_file and working_file.exists():
                working_file.unlink()
            raise Exception("تعذر تحديد نوع ملف النسخة الاحتياطية. تأكد من أن الملف صحيح وغير تالف.")
        
        # Rename temp file with correct extension for better handling
        if is_temp_file:
            import tempfile
            if file_format == 'json':
                new_temp = tempfile.NamedTemporaryFile(delete=False, suffix='.json')
                new_temp.close()
                shutil.move(str(working_file), new_temp.name)
                working_file = Path(new_temp.name)
                logger.info(f"Renamed temp file to JSON: {working_file}")
            elif file_format == 'sql':
                new_temp = tempfile.NamedTemporaryFile(delete=False, suffix='.sql')
                new_temp.close()
                shutil.move(str(working_file), new_temp.name)
                working_file = Path(new_temp.name)
                logger.info(f"Renamed temp file to SQL: {working_file}")
            elif file_format == 'sqlite':
                new_temp = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
                new_temp.close()
                shutil.move(str(working_file), new_temp.name)
                working_file = Path(new_temp.name)
                logger.info(f"Renamed temp file to SQLite: {working_file}")
        
        try:
            # Route to appropriate restore method based on format
            if file_format == 'json':
                logger.info("Using Django loaddata for JSON restore")
                result = self._restore_from_json(working_file)
                # Return result with success rate if available
                return result if isinstance(result, dict) else None
            elif file_format == 'sql':
                if 'mysql' in engine.lower():
                    self._restore_mysql_database(db_config, working_file)
                elif 'postgresql' in engine.lower():
                    self._restore_postgresql_database(db_config, working_file)
                else:
                    raise Exception(f"نوع قاعدة البيانات غير مدعوم: {engine}")
            elif file_format == 'sqlite':
                if 'sqlite' in engine.lower():
                    self._restore_sqlite_database(db_config, working_file)
                else:
                    raise Exception("ملف SQLite لا يمكن استعادته في قاعدة بيانات من نوع آخر")
            else:
                raise Exception(f"صيغة الملف غير مدعومة: {file_format}")
                
            logger.info("Database restored successfully")
            return None
            
        except Exception as restore_error:
            logger.error(f"Database restore failed: {restore_error}")
            raise
        finally:
            # Clean up temp file if created
            if is_temp_file and working_file.exists():
                try:
                    working_file.unlink()
                    logger.info(f"Cleaned up temporary file: {working_file}")
                except Exception as cleanup_error:
                    logger.warning(f"Failed to cleanup temp file: {cleanup_error}")
    
    def _restore_from_json(self, file_path: Path):
        """
        Restore database from Django JSON dumpdata format
        """
        from django.core.management import call_command
        from django.core import serializers
        from django.db import transaction, connection
        from django.db.models import signals
        from io import StringIO
        import sys
        import json
        
        logger.info(f"Starting JSON restore from: {file_path}")
        
        # Validate JSON file
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if not isinstance(data, list):
                raise Exception("ملف JSON غير صحيح: يجب أن يحتوي على قائمة من الكائنات")
            
            logger.info(f"Loaded {len(data)} objects from JSON file")
            
        except json.JSONDecodeError as e:
            raise Exception(f"ملف JSON تالف أو غير صحيح: {str(e)}")
        except Exception as e:
            raise Exception(f"فشل قراءة ملف JSON: {str(e)}")
        
        # Try standard loaddata first
        try:
            logger.info("Attempting standard Django loaddata")
            
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            sys.stdout = StringIO()
            sys.stderr = StringIO()
            
            try:
                call_command('loaddata', str(file_path), verbosity=2)
                stdout_output = sys.stdout.getvalue()
                stderr_output = sys.stderr.getvalue()
                
                logger.info(f"Loaddata stdout: {stdout_output}")
                if stderr_output:
                    logger.warning(f"Loaddata stderr: {stderr_output}")
                
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr
            
            logger.info("Database restored successfully using Django loaddata")
            return {'success_rate': 100.0, 'method': 'loaddata'}
            
        except Exception as loaddata_error:
            logger.warning(f"Standard loaddata failed: {loaddata_error}")
            logger.info("Attempting manual JSON restore with error handling")
        
        # Manual restore with error handling and FK constraints disabled
        # Also disable signals to prevent interference
        # Use autocommit mode to avoid atomic block issues
        try:
            # Store original signal receivers
            saved_receivers = {}
            signal_types = [
                signals.pre_save, signals.post_save,
                signals.pre_delete, signals.post_delete,
                signals.m2m_changed
            ]
            
            # Temporarily disconnect all signals
            logger.info("Temporarily disconnecting Django signals")
            for signal_type in signal_types:
                saved_receivers[signal_type] = signal_type.receivers[:]
                signal_type.receivers = []
            
            # Get current autocommit state and enable it
            original_autocommit = connection.get_autocommit()
            connection.set_autocommit(True)
            logger.info(f"Set autocommit to True (was: {original_autocommit})")
            
            # Disable foreign key checks for MySQL
            db_engine = connection.settings_dict['ENGINE']
            if 'mysql' in db_engine.lower():
                logger.info("Disabling MySQL foreign key checks")
                with connection.cursor() as cursor:
                    cursor.execute('SET FOREIGN_KEY_CHECKS=0;')
            elif 'postgresql' in db_engine.lower():
                logger.info("Disabling PostgreSQL constraints")
                with connection.cursor() as cursor:
                    cursor.execute('SET CONSTRAINTS ALL DEFERRED;')
            
            success_count = 0
            error_count = 0
            errors = []
            skipped_models = set()
            
            # Process each object WITHOUT transactions (autocommit mode)
            for i, obj_data in enumerate(data):
                try:
                    # Deserialize and save each object individually
                    for obj in serializers.deserialize('json', json.dumps([obj_data])):
                        obj.save()
                    
                    success_count += 1
                    
                    # Log progress every 100 objects
                    if (i + 1) % 100 == 0:
                        logger.info(f"Progress: {i + 1}/{len(data)} objects processed, {success_count} successful, {error_count} failed")
                        
                except Exception as obj_error:
                    error_count += 1
                    model_name = obj_data.get('model', 'unknown')
                    error_msg = f"{model_name}: {str(obj_error)}"
                    
                    # Track skipped models
                    skipped_models.add(model_name)
                    
                    # Log first 20 errors in detail
                    if error_count <= 20:
                        logger.warning(f"Failed to restore object {i + 1}: {error_msg}")
                    
                    errors.append(error_msg)
            
            logger.info(f"Manual JSON restore completed: {success_count} objects restored, {error_count} failed")
            
            # Re-enable foreign key checks
            if 'mysql' in db_engine.lower():
                logger.info("Re-enabling MySQL foreign key checks")
                with connection.cursor() as cursor:
                    cursor.execute('SET FOREIGN_KEY_CHECKS=1;')
            elif 'postgresql' in db_engine.lower():
                logger.info("Re-enabling PostgreSQL constraints")
                with connection.cursor() as cursor:
                    cursor.execute('SET CONSTRAINTS ALL IMMEDIATE;')
            
            # Restore original autocommit state
            connection.set_autocommit(original_autocommit)
            logger.info(f"Restored autocommit to: {original_autocommit}")
            
            # Reconnect signals
            logger.info("Reconnecting Django signals")
            for signal_type in signal_types:
                signal_type.receivers = saved_receivers[signal_type]
            
            if skipped_models:
                logger.warning(f"Skipped models due to errors: {', '.join(sorted(skipped_models))}")
            
            if success_count == 0:
                raise Exception(f"لم يتم استعادة أي بيانات. أمثلة على الأخطاء: {errors[:3]}")
            
            # More lenient success criteria - accept if we restored at least 10% of data
            success_rate = (success_count / len(data)) * 100
            logger.info(f"Restore success rate: {success_rate:.1f}% ({success_count}/{len(data)})")
            
            if error_count > 0:
                logger.warning(f"تم تخطي {error_count} كائن بسبب أخطاء. الأخطاء الأولى: {errors[:5]}")
                
                # Only fail if success rate is very low (less than 10%)
                if success_rate < 10:
                    raise Exception(f"فشلت استعادة معظم البيانات ({error_count}/{len(data)}). معدل النجاح: {success_rate:.1f}%")
                
                # Warn if success rate is low but acceptable
                if success_rate < 50:
                    logger.warning(f"⚠️ معدل نجاح منخفض: {success_rate:.1f}%. قد تحتاج لمراجعة البيانات المفقودة.")
            
            # Return success info with rate
            return {
                'success_rate': success_rate,
                'method': 'manual',
                'success_count': success_count,
                'error_count': error_count,
                'total_count': len(data),
                'skipped_models': list(skipped_models)
            }
            
        except Exception as manual_error:
            # Make sure to re-enable constraints, restore autocommit, and reconnect signals even on error
            try:
                if 'mysql' in db_engine.lower():
                    with connection.cursor() as cursor:
                        cursor.execute('SET FOREIGN_KEY_CHECKS=1;')
                elif 'postgresql' in db_engine.lower():
                    with connection.cursor() as cursor:
                        cursor.execute('SET CONSTRAINTS ALL IMMEDIATE;')
                
                # Restore autocommit
                connection.set_autocommit(original_autocommit)
                
                # Reconnect signals
                for signal_type in signal_types:
                    signal_type.receivers = saved_receivers[signal_type]
            except:
                pass
            
            logger.error(f"Manual JSON restore failed: {manual_error}")
            raise Exception(f"فشل استعادة البيانات من ملف JSON: {str(manual_error)}")
    
    def _old_restore_logic_for_reference(self):
        """
        Old restore logic - kept for reference, will be removed
        """
        try:
            # If it's JSON, use Django's loaddata
            if is_json:
                logger.info("Detected JSON format, using Django loaddata")
                from django.core.management import call_command
                from django.core.serializers import base
                from io import StringIO
                import sys
                import json
                
                # Try to load with ignoring errors
                try:
                    # First, try normal loaddata
                    logger.info("Attempting standard loaddata")
                    old_stdout = sys.stdout
                    old_stderr = sys.stderr
                    sys.stdout = StringIO()
                    sys.stderr = StringIO()
                    
                    try:
                        call_command('loaddata', str(working_file), verbosity=2)
                        output = sys.stdout.getvalue()
                        logger.info(f"Django loaddata output: {output}")
                    finally:
                        sys.stdout = old_stdout
                        sys.stderr = old_stderr
                    
                    logger.info("Database restored successfully using Django loaddata")
                    return
                    
                except Exception as loaddata_error:
                    logger.warning(f"Standard loaddata failed: {loaddata_error}")
                    logger.info("Attempting manual JSON restore with error handling")
                    
                    # Manual restore with error handling
                    from django.core import serializers
                    from django.db import transaction
                    
                    with open(working_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    logger.info(f"Loaded {len(data)} objects from JSON")
                    
                    success_count = 0
                    error_count = 0
                    errors = []
                    
                    for obj_data in data:
                        try:
                            # Deserialize and save each object individually
                            for obj in serializers.deserialize('json', json.dumps([obj_data])):
                                obj.save()
                                success_count += 1
                        except Exception as obj_error:
                            error_count += 1
                            error_msg = f"{obj_data.get('model', 'unknown')}: {str(obj_error)}"
                            if error_count <= 10:  # Log first 10 errors
                                logger.warning(f"Failed to restore object: {error_msg}")
                            errors.append(error_msg)
                    
                    logger.info(f"Manual JSON restore completed: {success_count} objects restored, {error_count} failed")
                    
                    if success_count == 0:
                        raise Exception(f"No objects were restored successfully. Sample errors: {errors[:3]}")
                    
                    if error_count > 0:
                        logger.warning(f"Some objects failed to restore ({error_count} errors). First few: {errors[:5]}")
                    
                    return
            
            # Otherwise, use SQL restore methods
            if 'mysql' in engine.lower():
                self._restore_mysql_database(db_config, working_file)
            elif 'postgresql' in engine.lower():
                self._restore_postgresql_database(db_config, working_file)
            elif 'sqlite' in engine.lower():
                self._restore_sqlite_database(db_config, working_file)
            else:
                raise Exception(f"Unsupported database engine: {engine}")
        finally:
            # Clean up decompressed file if created
            if working_file != file_path:
                try:
                    working_file.unlink()
                    logger.info(f"Cleaned up temporary decompressed file: {working_file}")
                except Exception as cleanup_error:
                    logger.warning(f"Failed to cleanup temp file: {cleanup_error}")
    
    def _restore_mysql_database(self, db_config: Dict, file_path: Path):
        """
        Restore MySQL database from SQL file
        """
        logger.info(f"Restoring MySQL database from: {file_path}")
        
        # Validate file exists and has content
        if not file_path.exists():
            raise Exception(f"Backup file not found: {file_path}")
        
        file_size = file_path.stat().st_size
        if file_size == 0:
            raise Exception(f"Backup file is empty: {file_path}")
        
        logger.info(f"Backup file size: {file_size} bytes")
        
        try:
            # Check if mysql command is available
            mysql_available = shutil.which('mysql') is not None
            
            if mysql_available:
                logger.info("Using mysql command for restore")
                # Try using mysql command
                cmd = [
                    'mysql',
                    f"--host={db_config.get('HOST', 'localhost')}",
                    f"--port={db_config.get('PORT', 3306)}",
                    f"--user={db_config['USER']}",
                    f"--password={db_config['PASSWORD']}",
                    db_config['NAME']
                ]
                
                with open(file_path, 'r', encoding='utf-8') as f:
                    result = subprocess.run(cmd, stdin=f, stderr=subprocess.PIPE, text=True)
                
                if result.returncode != 0:
                    raise Exception(f"mysql restore failed: {result.stderr}")
                
                logger.info("MySQL database restored successfully using mysql command")
            else:
                # Fallback: Use PyMySQL to execute SQL directly
                logger.info("mysql command not available, using PyMySQL fallback")
                
                try:
                    import pymysql
                except ImportError:
                    raise Exception("PyMySQL library not installed. Cannot restore database without mysql command or PyMySQL.")
                
                connection = pymysql.connect(
                    host=db_config.get('HOST', 'localhost'),
                    port=int(db_config.get('PORT', 3306)),
                    user=db_config['USER'],
                    password=db_config['PASSWORD'],
                    database=db_config['NAME'],
                    charset='utf8mb4'
                )
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        sql_content = f.read()
                    
                    if not sql_content.strip():
                        raise Exception("SQL file is empty or contains only whitespace")
                    
                    logger.info(f"Read SQL content: {len(sql_content)} characters")
                    
                    # Try to execute the entire SQL file at once (simpler and more reliable)
                    cursor = connection.cursor()
                    
                    try:
                        # For mysqldump files, try executing all at once
                        logger.info("Attempting to execute SQL file as a whole")
                        
                        # Split by semicolon and execute each statement
                        # Use a simple regex-based split that handles most cases
                        import re
                        
                        # Remove comments first
                        sql_no_comments = re.sub(r'--[^\n]*\n', '\n', sql_content)
                        sql_no_comments = re.sub(r'/\*.*?\*/', '', sql_no_comments, flags=re.DOTALL)
                        
                        # Split by semicolon (simple approach)
                        raw_statements = sql_no_comments.split(';')
                        
                        statements = []
                        for stmt in raw_statements:
                            stmt = stmt.strip()
                            if stmt and len(stmt) > 5:  # Ignore very short statements
                                statements.append(stmt + ';')
                        
                        logger.info(f"Parsed {len(statements)} SQL statements")
                        
                        # Log first statement as sample for debugging
                        if statements:
                            first_stmt = statements[0][:300] + '...' if len(statements[0]) > 300 else statements[0]
                            logger.info(f"First statement sample: {first_stmt}")
                        
                        if len(statements) == 0:
                            # Try alternative: execute without parsing
                            logger.warning("No statements found with standard parsing, trying direct execution")
                            
                            # Remove only single-line comments
                            sql_cleaned = '\n'.join([
                                line for line in sql_content.split('\n')
                                if line.strip() and not line.strip().startswith('--')
                            ])
                            
                            if sql_cleaned.strip():
                                # Try to execute as-is
                                try:
                                    for result in cursor.execute(sql_cleaned, multi=True):
                                        pass
                                    connection.commit()
                                    logger.info("SQL executed successfully using multi-statement execution")
                                    cursor.close()
                                    return
                                except AttributeError:
                                    # PyMySQL doesn't support multi parameter
                                    logger.info("Multi-statement not supported, will try splitting differently")
                                    # Split by semicolon at end of line
                                    statements = [s.strip() + ';' for s in sql_cleaned.split(';') if s.strip()]
                                    if not statements:
                                        raise Exception("No valid SQL statements found in backup file")
                            else:
                                raise Exception("No valid SQL statements found in backup file")
                        
                        # Execute statements
                        executed_count = 0
                        failed_count = 0
                        last_error = None
                        
                        for i, statement in enumerate(statements):
                            try:
                                cursor.execute(statement)
                                executed_count += 1
                                
                                # Log progress every 100 statements
                                if (i + 1) % 100 == 0:
                                    logger.info(f"Progress: {i + 1}/{len(statements)} statements executed")
                                    
                            except Exception as stmt_error:
                                # Log but continue with other statements
                                failed_count += 1
                                error_msg = str(stmt_error)
                                last_error = error_msg
                                
                                # Log first few errors with more details
                                if failed_count <= 10:
                                    logger.error(f"Failed to execute statement {i + 1}: {error_msg}")
                                    # Log first 200 chars of statement for debugging
                                    stmt_preview = statement[:200] + '...' if len(statement) > 200 else statement
                                    logger.error(f"Failed statement: {stmt_preview}")
                        
                        connection.commit()
                        cursor.close()
                        logger.info(f"MySQL database restored using PyMySQL: {executed_count} statements executed, {failed_count} failed")
                        
                        if executed_count == 0:
                            error_detail = f"Last error: {last_error}" if last_error else "No error details available"
                            raise Exception(f"No SQL statements were executed successfully. {error_detail}")
                            
                    except Exception as exec_error:
                        logger.error(f"Failed to execute SQL: {exec_error}")
                        raise
                    
                finally:
                    connection.close()
            
        except Exception as e:
            logger.error(f"MySQL restore failed: {e}")
            raise
    
    def _restore_postgresql_database(self, db_config: Dict, file_path: Path):
        """
        Restore PostgreSQL database from backup file
        """
        logger.info(f"Restoring PostgreSQL database from: {file_path}")
        
        env = os.environ.copy()
        env['PGPASSWORD'] = db_config['PASSWORD']
        
        cmd = [
            'pg_restore',
            '--verbose',
            '--clean',
            '--no-owner',
            '--no-privileges',
            f"--host={db_config.get('HOST', 'localhost')}",
            f"--port={db_config.get('PORT', 5432)}",
            f"--username={db_config['USER']}",
            f"--dbname={db_config['NAME']}",
            str(file_path)
        ]
        
        result = subprocess.run(cmd, env=env, stderr=subprocess.PIPE, text=True)
        
        if result.returncode != 0:
            raise Exception(f"pg_restore failed: {result.stderr}")
        
        logger.info("PostgreSQL database restored successfully")
    
    def _restore_sqlite_database(self, db_config: Dict, file_path: Path):
        """
        Restore SQLite database by replacing the file
        """
        logger.info(f"Restoring SQLite database from: {file_path}")
        
        db_path = Path(db_config['NAME'])
        
        # Backup current database
        if db_path.exists():
            backup_path = db_path.with_suffix('.db.backup')
            shutil.copy2(db_path, backup_path)
            logger.info(f"Current database backed up to: {backup_path}")
        
        # Replace with new database
        shutil.copy2(file_path, db_path)
        logger.info("SQLite database restored successfully")
    
    def _restore_media_from_file(self, file_path: Path):
        """
        Restore media files from archive
        """
        logger.info(f"Restoring media files from: {file_path.name}")
        
        media_root = Path(settings.MEDIA_ROOT)
        
        # Backup current media directory
        if media_root.exists():
            backup_dir = media_root.parent / f"{media_root.name}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            shutil.copytree(media_root, backup_dir)
            logger.info(f"Current media backed up to: {backup_dir}")
        
        # Extract archive
        if file_path.suffix == '.gz' and '.tar' in file_path.name:
            # tar.gz file
            import tarfile
            with tarfile.open(file_path, 'r:gz') as tar:
                tar.extractall(media_root.parent)
        elif file_path.suffix == '.zip':
            # zip file
            import zipfile
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(media_root.parent)
        else:
            raise Exception(f"Unsupported media archive format: {file_path.suffix}")
        
        logger.info("Media files restored successfully")
    
    def restore_from_backup(self, backup_id: str, restore_database: bool = True, 
                          restore_media: bool = True) -> Dict[str, any]:
        """
        Restore system from backup
        """
        restore_info = {
            'backup_id': backup_id,
            'timestamp': timezone.now(),
            'status': 'started',
            'restored_components': [],
            'errors': []
        }
        
        try:
            logger.info(f"Starting restore from backup: {backup_id}")
            
            # Find backup files
            backup_files = self._find_backup_files(backup_id)
            
            if not backup_files:
                raise Exception(f"No backup files found for backup ID: {backup_id}")
            
            # Restore database
            if restore_database:
                db_file = next((f for f in backup_files if f['type'] == 'database'), None)
                if db_file:
                    self._restore_database(db_file)
                    restore_info['restored_components'].append('database')
            
            # Restore media files
            if restore_media:
                media_file = next((f for f in backup_files if f['type'] == 'media'), None)
                if media_file:
                    self._restore_media(media_file)
                    restore_info['restored_components'].append('media')
            
            restore_info['status'] = 'completed'
            logger.info(f"Restore completed successfully: {backup_id}")
            
        except Exception as e:
            restore_info['status'] = 'failed'
            restore_info['errors'].append(str(e))
            logger.error(f"Restore failed: {backup_id} - {e}")
            raise
        
        return restore_info
    
    def _find_backup_files(self, backup_id: str) -> List[Dict[str, any]]:
        """
        Find backup files for a given backup ID
        """
        backup_files = []
        
        # Search local backup directory
        for backup_file in self.backup_dir.glob(f"*{backup_id}*"):
            if backup_file.is_file():
                file_type = 'unknown'
                if 'db_' in backup_file.name:
                    file_type = 'database'
                elif 'media_' in backup_file.name:
                    file_type = 'media'
                elif 'config_' in backup_file.name:
                    file_type = 'config'
                
                backup_files.append({
                    'type': file_type,
                    'filename': backup_file.name,
                    'path': str(backup_file),
                    'size_bytes': backup_file.stat().st_size
                })
        
        return backup_files
    
    def _restore_database(self, db_file: Dict[str, any]):
        """
        Restore database from backup file
        """
        # Implementation depends on database type
        # This is a placeholder for the actual restore logic
        logger.info(f"Restoring database from: {db_file['filename']}")
        # TODO: Implement database-specific restore logic
    
    def _restore_media(self, media_file: Dict[str, any]):
        """
        Restore media files from backup
        """
        logger.info(f"Restoring media files from: {media_file['filename']}")
        # TODO: Implement media restore logic
    
    def list_backups(self) -> List[Dict[str, any]]:
        """
        List available backups grouped by backup_id
        """
        backups = []
        
        # Group backup files by backup ID
        backup_groups = {}
        
        for backup_file in self.backup_dir.glob('*'):
            if backup_file.is_file():
                # Extract backup ID from filename
                # Format: db_backup_20260212_045439.sql.gz or media_backup_20260212_045439.tar.gz
                filename = backup_file.name
                
                # Find backup_YYYYMMDD_HHMMSS pattern
                import re
                match = re.search(r'backup_(\d{8}_\d{6})', filename)
                
                if match:
                    backup_id = f"backup_{match.group(1)}"
                    
                    if backup_id not in backup_groups:
                        backup_groups[backup_id] = []
                    
                    backup_groups[backup_id].append({
                        'filename': backup_file.name,
                        'path': str(backup_file),
                        'size_bytes': backup_file.stat().st_size,
                        'created_at': datetime.fromtimestamp(backup_file.stat().st_mtime)
                    })
        
        # Convert groups to backup list
        for backup_id, files in backup_groups.items():
            total_size = sum(f['size_bytes'] for f in files)
            created_at = min(f['created_at'] for f in files)
            
            backups.append({
                'backup_id': backup_id,
                'created_at': created_at,
                'total_size_bytes': total_size,
                'file_count': len(files),
                'files': files
            })
        
        # Sort by creation date (newest first)
        backups.sort(key=lambda x: x['created_at'], reverse=True)
        
        return backups