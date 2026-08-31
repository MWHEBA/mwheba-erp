"""
Unified Backup Management Views for MWHEBA ERP
Hardened with Superuser Security, Audit Logging, and Dual-Engine Disaster Recovery.
"""

import os
import re
import json
import logging
import zipfile
import tempfile
import unicodedata
from pathlib import Path
from datetime import datetime
from typing import Optional

from django.shortcuts import render
from django.http import JsonResponse, FileResponse, Http404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.urls import reverse
from django.conf import settings
from django.utils import timezone
from django.utils.encoding import escape_uri_path

from core.services.backup_service import BackupService
from core.models import SystemSetting

logger = logging.getLogger(__name__)

BACKUP_ID_REGEX = re.compile(r'^backup_\d{8}_\d{6}$')


def superuser_required(view_func):
    """Decorator ensuring only active superusers can access backup views"""
    actual_decorator = user_passes_test(
        lambda u: u.is_authenticated and u.is_active and u.is_superuser,
        login_url='core:dashboard'
    )
    return actual_decorator(view_func)


def _log_audit_event(request, action: str, details: dict):
    """Helper to log backup actions in AuditTrail safely"""
    try:
        from governance.models import AuditTrail
        AuditTrail.objects.create(
            user=request.user if request.user.is_authenticated else None,
            action=action,
            resource_type='SYSTEM_ADMINISTRATION',
            changes=details,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:255]
        )
    except Exception as e:
        logger.warning(f"Failed to record audit log for {action}: {e}")



class TempFileCleanupWrapper:
    """Wrapper that closes and deletes a temporary file after streaming response finishes"""
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.file_obj = open(file_path, 'rb')

    def read(self, *args):
        return self.file_obj.read(*args)

    def __iter__(self):
        return iter(self.file_obj)

    def close(self):
        try:
            self.file_obj.close()
        finally:
            try:
                if os.path.exists(self.file_path):
                    os.unlink(self.file_path)
                    logger.info(f"Cleaned up temporary download archive: {self.file_path}")
            except Exception as e:
                logger.warning(f"Failed to delete temp archive {self.file_path}: {e}")


@superuser_required
def backup_management(request):
    """
    Main backup management page with 3 tabs
    """
    context = {
        'active_menu': 'settings',
        'title': 'إدارة النسخ الاحتياطية',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الإعدادات', 'url': reverse('core:system_settings'), 'icon': 'fas fa-cog'},
            {'title': 'إدارة النسخ الاحتياطية', 'active': True}
        ],
        'python_executable': os.sys.executable,
        'base_dir': str(settings.BASE_DIR)
    }
    return render(request, 'core/backup/backup_management.html', context)


@superuser_required
@transaction.non_atomic_requests
@require_http_methods(["POST"])
def create_backup(request):
    """
    Create a new backup (API endpoint)
    """
    try:
        backup_type = request.POST.get('backup_type', 'full')
        download_mode = request.POST.get('download_mode', 'false').lower() == 'true'
        
        if backup_type not in ['full', 'database', 'media']:
            return JsonResponse({
                'success': False,
                'message': 'نوع النسخة الاحتياطية غير صحيح'
            }, status=400)
        
        backup_service = BackupService()
        backup_info = backup_service.create_backup(
            backup_type=backup_type,
            download_mode=download_mode
        )
        
        # Verify real success
        if backup_info.get('status') != 'completed' or not backup_info.get('files'):
            error_msg = backup_info.get('errors', ['فشل إنشاء ملفات النسخة الاحتياطية'])[0] if backup_info.get('errors') else 'فشل إنشاء النسخة'
            return JsonResponse({
                'success': False,
                'message': f'فشل إنشاء النسخة الاحتياطية: {error_msg}',
                'errors': backup_info.get('errors', [])
            }, status=500)
        
        # Build suggested filename synchronized with backup_id
        company_name = SystemSetting.get_setting('site_name', 'MWHEBA_ERP')
        clean_company = re.sub(r'[\\/*?:"<>| ]', '_', company_name)
        date_str = backup_info['backup_id'].replace('backup_', '')
        
        backup_type_en = {'full': 'Full', 'database': 'Database', 'media': 'Media'}
        type_name = backup_type_en.get(backup_type, backup_type.capitalize())
        
        if len(backup_info['files']) == 1:
            first_file = Path(backup_info['files'][0]['path'])
            ext = ''.join(first_file.suffixes)
        else:
            ext = '.zip'
        
        suggested_filename = f'{clean_company}_Backup_{type_name}_{date_str}{ext}'
        
        _log_audit_event(request, 'CREATE_BACKUP', {
            'backup_id': backup_info['backup_id'],
            'backup_type': backup_type,
            'size_bytes': backup_info.get('size_bytes', 0),
            'download_mode': download_mode
        })
        
        response_data = {
            'success': True,
            'message': 'تم إنشاء النسخة الاحتياطية بنجاح',
            'backup_id': backup_info['backup_id'],
            'size_bytes': backup_info['size_bytes'],
            'suggested_filename': suggested_filename,
            'warnings': backup_info.get('warnings', []),
            'errors': backup_info.get('errors', [])
        }
        
        if download_mode:
            response_data['download_url'] = reverse('core:backup_download', args=[backup_info['backup_id']])
            response_data['download_filename'] = suggested_filename
        
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"Backup creation view failed: {e}", exc_info=True)
        resp = {
            'success': False,
            'message': f'فشل إنشاء النسخة الاحتياطية: {str(e)}'
        }
        if settings.DEBUG:
            import traceback
            resp['traceback'] = traceback.format_exc()
        return JsonResponse(resp, status=500)


@superuser_required
def download_backup(request, backup_id: str):
    """
    Download a backup file with RFC 6266 compliance and temp file cleanup
    """
    try:
        if not BACKUP_ID_REGEX.match(backup_id):
            raise Http404("معرف النسخة الاحتياطية غير صالح")
        
        backup_service = BackupService()
        backup_files = backup_service._find_backup_files(backup_id)
        
        if not backup_files:
            raise Http404("النسخة الاحتياطية غير موجودة")
        
        company_name = SystemSetting.get_setting('site_name', 'MWHEBA_ERP')
        clean_company = re.sub(r'[\\/*?:"<>| ]', '_', company_name)
        date_str = backup_id.replace('backup_', '')
        
        has_db = any('db_' in f.name for f in backup_files)
        has_media = any('media_' in f.name for f in backup_files)
        
        if len(backup_files) == 1 and backup_files[0].name.endswith('.zip') and 'full_' in backup_files[0].name:
            backup_type = 'Full'
        elif has_db and has_media:
            backup_type = 'Full'
        elif has_db:
            backup_type = 'Database'
        elif has_media:
            backup_type = 'Media'
        else:
            backup_type = 'Archive'
        
        _log_audit_event(request, 'DOWNLOAD_BACKUP', {
            'backup_id': backup_id,
            'files_count': len(backup_files)
        })
        
        # If multiple files, create temporary zip archive
        if len(backup_files) > 1:
            display_filename = f'{clean_company}_Backup_{backup_type}_{date_str}.zip'
            temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
            temp_zip.close()
            
            with zipfile.ZipFile(temp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for b_file in backup_files:
                    zipf.write(b_file, b_file.name)
            
            wrapper = TempFileCleanupWrapper(temp_zip.name)
            response = FileResponse(wrapper, as_attachment=True, filename=display_filename)
        else:
            single_file = backup_files[0]
            ext = ''.join(single_file.suffixes)
            display_filename = f'{clean_company}_Backup_{backup_type}_{date_str}{ext}'
            response = FileResponse(open(single_file, 'rb'), as_attachment=True, filename=display_filename)
        
        # RFC 6266 / RFC 5987 Unicode Header Protection
        ascii_filename = unicodedata.normalize('NFKD', display_filename).encode('ascii', 'ignore').decode('ascii') or f"backup_{date_str}.zip"
        encoded_filename = escape_uri_path(display_filename)
        response['Content-Disposition'] = f'attachment; filename="{ascii_filename}"; filename*=UTF-8\'\'{encoded_filename}'
        return response
        
    except Http404:
        raise
    except Exception as e:
        logger.error(f"Backup download failed: {e}", exc_info=True)
        raise Http404("فشل تحميل النسخة الاحتياطية")


@superuser_required
@transaction.non_atomic_requests
@require_http_methods(["POST"])
def restore_backup_from_upload(request):
    """
    Restore from an uploaded backup file (API endpoint)
    """
    temp_path = None
    try:
        if 'backup_file' not in request.FILES:
            return JsonResponse({
                'success': False,
                'message': 'لم يتم رفع ملف النسخة الاحتياطية'
            }, status=400)
        
        backup_file = request.FILES['backup_file']
        restore_type = request.POST.get('restore_type', 'auto')
        
        # Max upload size 500MB
        max_size = getattr(settings, 'DATA_UPLOAD_MAX_MEMORY_SIZE', 500 * 1024 * 1024)
        if backup_file.size > max_size:
            return JsonResponse({
                'success': False,
                'message': f'حجم الملف كبير جداً. الحد الأقصى {max_size // (1024*1024)} ميجابايت'
            }, status=400)
        
        # Validate Compound Extensions
        valid_compound_suffixes = (
            '.sql.gz', '.sql', '.tar.gz', '.tgz', '.zip',
            '.db.gz', '.db', '.sqlite3.gz', '.sqlite3',
            '.json.gz', '.json'
        )
        original_name_lower = backup_file.name.lower()
        if not any(original_name_lower.endswith(suf) for suf in valid_compound_suffixes):
            return JsonResponse({
                'success': False,
                'message': f'نوع الملف غير مدعوم. الصيغ المدعومة: {", ".join(valid_compound_suffixes)}'
            }, status=400)
        
        # Magic bytes and header inspection for uploaded files
        first_chunk = backup_file.read(4096)
        backup_file.seek(0)
        
        clean_chunk = first_chunk[3:].lstrip() if first_chunk.startswith(b'\xef\xbb\xbf') else first_chunk.lstrip()
        
        is_gzip = first_chunk.startswith(b'\x1f\x8b')
        is_zip = first_chunk.startswith(b'PK\x03\x04') or first_chunk.startswith(b'PK\x05\x06')
        is_sqlite = first_chunk.startswith(b'SQLite format 3\x00')
        is_tar = (len(first_chunk) >= 262 and first_chunk[257:262] == b'ustar') or any(clean_chunk.startswith(m) for m in [b'./', b'media/'])
        is_text = any(clean_chunk.lower().startswith(m) for m in [
            b'--', b'/*', b'#', b'set', b'create', b'insert', b'drop', b'use', b'lock', b'alter', b'[', b'{'
        ])
        
        if not (is_gzip or is_zip or is_sqlite or is_tar or is_text):
            logger.warning(f"Non-standard file header for {backup_file.name}, allowing decompression engine to inspect: {first_chunk[:40]!r}")

        
        # Determine appropriate temp suffix
        matched_ext = next((suf for suf in valid_compound_suffixes if original_name_lower.endswith(suf)), '.tmp')
        
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=matched_ext)
        for chunk in backup_file.chunks():
            temp_file.write(chunk)
        temp_file.close()
        temp_path = Path(temp_file.name)
        
        backup_service = BackupService()
        restore_info = backup_service.restore_from_uploaded_file(
            str(temp_path),
            restore_type=restore_type
        )
        
        if restore_info.get('status') != 'completed':
            error_msg = restore_info.get('error', 'فشلت عملية الاستعادة')
            return JsonResponse({
                'success': False,
                'message': f'فشلت استعادة البيانات: {error_msg}',
                'error_details': error_msg
            }, status=400)
        
        _log_audit_event(request, 'RESTORE_BACKUP_UPLOAD', {
            'filename': backup_file.name,
            'size_bytes': backup_file.size,
            'restored_components': restore_info.get('restored_components', [])
        })
        
        # Persist session into freshly restored database to prevent SessionInterrupted on overwritten django_session table
        try:
            try:
                request.session.save(must_create=True)
            except Exception:
                request.session.save(must_create=False)
            request.session.modified = False
        except Exception as sess_err:
            logger.warning(f"Could not persist session in restored database: {sess_err}")
            request.session.modified = False
        
        return JsonResponse({

            'success': True,
            'message': 'تم استعادة النسخة الاحتياطية بنجاح 100%',
            'restored_components': restore_info.get('restored_components', []),
            'details': restore_info.get('details', {})
        })

        
    except Exception as e:
        logger.error(f"Restore from upload failed: {e}", exc_info=True)
        resp = {
            'success': False,
            'message': f'فشل استعادة النسخة الاحتياطية: {str(e)}'
        }
        if settings.DEBUG:
            import traceback
            resp['error_details'] = traceback.format_exc()
        return JsonResponse(resp, status=500)
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception as e:
                logger.warning(f"Failed to clean up temp restore file: {e}")


@superuser_required
@transaction.non_atomic_requests
@require_http_methods(["POST"])
def restore_backup(request):
    """
    Restore from a saved server backup file (API endpoint)
    Restores all available components (DB + Media) or Media-only safely.
    """
    try:
        backup_id = request.POST.get('backup_id', '').strip()
        
        if not backup_id or not BACKUP_ID_REGEX.match(backup_id):
            return JsonResponse({
                'success': False,
                'message': 'معرف النسخة الاحتياطية غير صالح'
            }, status=400)
        
        backup_service = BackupService()
        backup_files = backup_service._find_backup_files(backup_id)
        
        if not backup_files:
            return JsonResponse({
                'success': False,
                'message': 'النسخة الاحتياطية غير موجودة على السيرفر'
            }, status=404)
        
        restore_info = backup_service.restore_from_backup(backup_id)
        
        if restore_info.get('status') != 'completed':
            error_msg = restore_info.get('error', 'فشلت استعادة البيانات')
            return JsonResponse({
                'success': False,
                'message': f'فشلت استعادة النسخة: {error_msg}',
                'error_details': error_msg
            }, status=500)
        
        _log_audit_event(request, 'RESTORE_BACKUP_SERVER', {
            'backup_id': backup_id,
            'restored_components': restore_info.get('restored_components', [])
        })
        
        # Persist session into freshly restored database to prevent SessionInterrupted on overwritten django_session table
        try:
            try:
                request.session.save(must_create=True)
            except Exception:
                request.session.save(must_create=False)
            request.session.modified = False
        except Exception as sess_err:
            logger.warning(f"Could not persist session in restored database: {sess_err}")
            request.session.modified = False
        
        return JsonResponse({

            'success': True,
            'message': 'تم استعادة النسخة الاحتياطية بنجاح 100%',
            'restored_components': restore_info.get('restored_components', []),
            'details': restore_info.get('details', {})
        })

        
    except Exception as e:
        logger.error(f"Server backup restore failed: {e}", exc_info=True)
        resp = {
            'success': False,
            'message': f'فشل استعادة النسخة الاحتياطية: {str(e)}'
        }
        if settings.DEBUG:
            import traceback
            resp['error_details'] = traceback.format_exc()
        return JsonResponse(resp, status=500)


@superuser_required
def list_backups(request):
    """
    List all available backups with metadata (API endpoint)
    """
    try:
        backup_service = BackupService()
        backups = backup_service.list_backups()
        
        company_name = SystemSetting.get_setting('site_name', 'MWHEBA_ERP')
        clean_company = re.sub(r'[\\/*?:"<>| ]', '_', company_name)
        
        for backup in backups:
            if isinstance(backup.get('created_at'), (datetime, timezone.datetime)):
                backup['created_at'] = backup['created_at'].isoformat()
            
            backup_type = backup.get('backup_type', 'database').capitalize()
            date_str = backup['backup_id'].replace('backup_', '')
            backup['display_name'] = f'{clean_company}_Backup_{backup_type}_{date_str}'
        
        return JsonResponse({
            'success': True,
            'backups': backups
        })
        
    except Exception as e:
        logger.error(f"Failed to list backups: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'message': 'فشل تحميل قائمة النسخ الاحتياطية'
        }, status=500)


@superuser_required
@require_http_methods(["POST"])
def delete_backup(request, backup_id: str):
    """
    Delete a backup safely (API endpoint)
    """
    try:
        if not BACKUP_ID_REGEX.match(backup_id):
            return JsonResponse({
                'success': False,
                'message': 'معرف النسخة الاحتياطية غير صالح'
            }, status=400)
        
        backup_service = BackupService()
        success = backup_service.delete_backup(backup_id)
        
        if not success:
            return JsonResponse({
                'success': False,
                'message': 'النسخة الاحتياطية غير موجودة أو تعذر حذفها'
            }, status=404)
        
        _log_audit_event(request, 'DELETE_BACKUP', {'backup_id': backup_id})
        
        return JsonResponse({
            'success': True,
            'message': 'تم حذف النسخة الاحتياطية بنجاح'
        })
        
    except Exception as e:
        logger.error(f"Backup deletion view failed: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'message': f'فشل حذف النسخة الاحتياطية: {str(e)}'
        }, status=500)


@superuser_required
def get_backup_settings(request):
    """
    Get backup settings from SystemSetting with proper boolean types (API endpoint)
    """
    try:
        def _get_bool(key: str, default: bool = False) -> bool:
            val = SystemSetting.get_setting(key, default)
            return val in [True, 'True', 'true', 1, '1']
        
        def _get_int(key: str, default: int = 5) -> int:
            try:
                return int(SystemSetting.get_setting(key, default))
            except (ValueError, TypeError):
                return default
        
        backup_settings = {
            'db_retention_type': SystemSetting.get_setting('backup_db_retention_type', 'count'),
            'db_retention_count': _get_int('backup_db_retention_count', 10),
            'db_retention_days': _get_int('backup_db_retention_days', 30),
            'db_auto_cleanup': _get_bool('backup_db_auto_cleanup', True),
            
            'full_retention_type': SystemSetting.get_setting('backup_full_retention_type', 'count'),
            'full_retention_count': _get_int('backup_full_retention_count', 5),
            'full_retention_days': _get_int('backup_full_retention_days', 60),
            'full_auto_cleanup': _get_bool('backup_full_auto_cleanup', True),
            
            'media_retention_type': SystemSetting.get_setting('backup_media_retention_type', 'count'),
            'media_retention_count': _get_int('backup_media_retention_count', 3),
            'media_retention_days': _get_int('backup_media_retention_days', 90),
            'media_auto_cleanup': _get_bool('backup_media_auto_cleanup', True),
            
            'enable_daily_db_backup': _get_bool('backup_enable_daily_db', False),
            'daily_db_backup_time': SystemSetting.get_setting('backup_daily_db_time', '02:00'),
            
            'enable_weekly_full_backup': _get_bool('backup_enable_weekly_full', False),
            'weekly_full_backup_day': str(SystemSetting.get_setting('backup_weekly_full_day', '5')),
            'weekly_full_backup_time': SystemSetting.get_setting('backup_weekly_full_time', '03:00'),
            
            'enable_monthly_media_backup': _get_bool('backup_enable_monthly_media', False),
            'monthly_media_backup_day': str(SystemSetting.get_setting('backup_monthly_media_day', '1')),
            'monthly_media_backup_time': SystemSetting.get_setting('backup_monthly_media_time', '04:00'),
        }
        
        return JsonResponse({
            'success': True,
            'settings': backup_settings
        })
        
    except Exception as e:
        logger.error(f"Failed to get backup settings: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'message': 'فشل تحميل الإعدادات'
        }, status=500)


@superuser_required
@require_http_methods(["POST"])
def update_backup_settings(request):
    """
    Atomic update of backup settings with strict boundary validations and cache invalidation
    """
    try:
        def _parse_bounded_int(val, default, min_v=1, max_v=365):
            try:
                num = int(val)
                return max(min_v, min(num, max_v))
            except (ValueError, TypeError):
                return default

        valid_types = ['count', 'days', 'none']
        
        db_retention_type = request.POST.get('db_retention_type', 'count')
        db_retention_count = _parse_bounded_int(request.POST.get('db_retention_count'), 10, 1, 100)
        db_retention_days = _parse_bounded_int(request.POST.get('db_retention_days'), 30, 1, 365)
        db_auto_cleanup = request.POST.get('db_auto_cleanup', 'false').lower() == 'true'
        
        full_retention_type = request.POST.get('full_retention_type', 'count')
        full_retention_count = _parse_bounded_int(request.POST.get('full_retention_count'), 5, 1, 50)
        full_retention_days = _parse_bounded_int(request.POST.get('full_retention_days'), 60, 1, 365)
        full_auto_cleanup = request.POST.get('full_auto_cleanup', 'false').lower() == 'true'
        
        media_retention_type = request.POST.get('media_retention_type', 'count')
        media_retention_count = _parse_bounded_int(request.POST.get('media_retention_count'), 3, 1, 30)
        media_retention_days = _parse_bounded_int(request.POST.get('media_retention_days'), 90, 1, 365)
        media_auto_cleanup = request.POST.get('media_auto_cleanup', 'false').lower() == 'true'
        
        if db_retention_type not in valid_types or full_retention_type not in valid_types or media_retention_type not in valid_types:
            return JsonResponse({
                'success': False,
                'message': 'نوع سياسة الاحتفاظ غير صحيح'
            }, status=400)
        
        enable_daily_db = request.POST.get('enable_daily_db_backup', 'false').lower() == 'true'
        daily_db_time = request.POST.get('daily_db_backup_time', '02:00')
        
        enable_weekly_full = request.POST.get('enable_weekly_full_backup', 'false').lower() == 'true'
        weekly_full_day = request.POST.get('weekly_full_backup_day', '5')
        weekly_full_time = request.POST.get('weekly_full_backup_time', '03:00')
        
        enable_monthly_media = request.POST.get('enable_monthly_media_backup', 'false').lower() == 'true'
        monthly_media_day = request.POST.get('monthly_media_backup_day', '1')
        monthly_media_time = request.POST.get('monthly_media_backup_time', '04:00')
        
        settings_to_save = [
            ('backup_db_retention_type', db_retention_type, 'string'),
            ('backup_db_retention_count', str(db_retention_count), 'integer'),
            ('backup_db_retention_days', str(db_retention_days), 'integer'),
            ('backup_db_auto_cleanup', str(db_auto_cleanup), 'boolean'),
            
            ('backup_full_retention_type', full_retention_type, 'string'),
            ('backup_full_retention_count', str(full_retention_count), 'integer'),
            ('backup_full_retention_days', str(full_retention_days), 'integer'),
            ('backup_full_auto_cleanup', str(full_auto_cleanup), 'boolean'),
            
            ('backup_media_retention_type', media_retention_type, 'string'),
            ('backup_media_retention_count', str(media_retention_count), 'integer'),
            ('backup_media_retention_days', str(media_retention_days), 'integer'),
            ('backup_media_auto_cleanup', str(media_auto_cleanup), 'boolean'),
            
            ('backup_enable_daily_db', str(enable_daily_db), 'boolean'),
            ('backup_daily_db_time', daily_db_time, 'string'),
            ('backup_enable_weekly_full', str(enable_weekly_full), 'boolean'),
            ('backup_weekly_full_day', str(weekly_full_day), 'string'),
            ('backup_weekly_full_time', weekly_full_time, 'string'),
            ('backup_enable_monthly_media', str(enable_monthly_media), 'boolean'),
            ('backup_monthly_media_day', str(monthly_media_day), 'string'),
            ('backup_monthly_media_time', monthly_media_time, 'string'),
        ]
        
        with transaction.atomic():
            for key, val, dtype in settings_to_save:
                SystemSetting.objects.update_or_create(
                    key=key,
                    defaults={
                        'value': val,
                        'group': 'backup',
                        'data_type': dtype,
                        'is_active': True
                    }
                )
        
        SystemSetting.invalidate_all_system_caches()
        
        _log_audit_event(request, 'UPDATE_BACKUP_SETTINGS', {
            'db_retention': f"{db_retention_type}/{db_retention_count}",
            'full_retention': f"{full_retention_type}/{full_retention_count}",
            'media_retention': f"{media_retention_type}/{media_retention_count}"
        })
        
        return JsonResponse({
            'success': True,
            'message': 'تم حفظ جميع الإعدادات بنجاح'
        })
        
    except Exception as e:
        logger.error(f"Failed to update backup settings: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'message': f'فشل حفظ الإعدادات: {str(e)}'
        }, status=500)


@superuser_required
@require_http_methods(["POST"])
def cleanup_old_backups(request):
    """
    Manually trigger cleanup of old backups and return freed space statistics (API endpoint)
    """
    try:
        backup_service = BackupService()
        cleanup_stats = backup_service.cleanup_old_backups()
        
        _log_audit_event(request, 'MANUAL_BACKUP_CLEANUP', cleanup_stats)
        
        return JsonResponse({
            'success': True,
            'message': f'تم تنظيف النسخ القديمة بنجاح (تم حذف {cleanup_stats.get("deleted_count", 0)} ملف وتحرير {cleanup_stats.get("freed_mb", 0):.2f} ميجابايت)',
            'stats': cleanup_stats
        })
        
    except Exception as e:
        logger.error(f"Manual backup cleanup failed: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'message': f'فشل تنظيف النسخ القديمة: {str(e)}'
        }, status=500)
