"""
Unified Backup Management Views
"""

import os
import json
from pathlib import Path
from django.shortcuts import render
from django.http import JsonResponse, FileResponse, Http404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.urls import reverse
from django.conf import settings
from core.services.backup_service import BackupService
from core.models import SystemSetting
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


@login_required
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
        ]
    }
    return render(request, 'core/backup/backup_management.html', context)


@login_required
@require_http_methods(["POST"])
def create_backup(request):
    """
    Create a new backup (API endpoint)
    """
    try:
        backup_type = request.POST.get('backup_type', 'full')
        download_mode = request.POST.get('download_mode', 'false').lower() == 'true'
        
        # Validate backup type
        if backup_type not in ['full', 'database', 'media']:
            return JsonResponse({
                'success': False,
                'message': 'نوع النسخة الاحتياطية غير صحيح'
            })
        
        # Create backup
        backup_service = BackupService()
        backup_info = backup_service.create_backup(
            backup_type=backup_type,
            download_mode=False  # Always save to server first
        )
        
        # Debug info
        debug_info = {
            'files_count': len(backup_info.get('files', [])),
            'files_details': []
        }
        
        for file_info in backup_info.get('files', []):
            debug_info['files_details'].append({
                'filename': file_info.get('filename', 'unknown'),
                'size': file_info.get('size_bytes', 0),
                'type': file_info.get('type', 'unknown')
            })
        
        # Build suggested filename
        from datetime import datetime
        from core.models import SystemSetting
        
        company_name = SystemSetting.get_setting('site_name', 'Company')
        company_name = company_name.replace(' ', '_').replace('/', '_')
        date_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        backup_type_en = {
            'full': 'Full',
            'database': 'Database',
            'media': 'Media'
        }
        type_name = backup_type_en.get(backup_type, backup_type)
        
        # Get extension from first file
        if backup_info['files']:
            from pathlib import Path
            first_file = Path(backup_info['files'][0]['path'])
            ext = ''.join(first_file.suffixes) if len(backup_info['files']) == 1 else '.zip'
        else:
            ext = '.zip'
        
        suggested_filename = f'{company_name}_Backup_{type_name}_{date_str}{ext}'
        
        response_data = {
            'success': True,
            'message': 'تم إنشاء النسخة الاحتياطية بنجاح',
            'backup_id': backup_info['backup_id'],
            'size_bytes': backup_info['size_bytes'],
            'suggested_filename': suggested_filename,
            'debug': debug_info,  # Add debug info
            'warnings': backup_info.get('warnings', []),
            'errors': backup_info.get('errors', [])
        }
        
        # If download mode, provide download URL
        if download_mode:
            response_data['download_url'] = reverse('core:backup_download', 
                                                   args=[backup_info['backup_id']])
            response_data['download_filename'] = suggested_filename
        
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"Backup creation failed: {e}")
        import traceback
        return JsonResponse({
            'success': False,
            'message': f'فشل إنشاء النسخة الاحتياطية: {str(e)}',
            'traceback': traceback.format_exc()
        }, status=500)


@login_required
def download_backup(request, backup_id):
    """
    Download a backup file
    """
    try:
        backup_service = BackupService()
        backup_dir = backup_service.backup_dir
        
        # Find backup files
        backup_files = list(backup_dir.glob(f"*{backup_id}*"))
        
        if not backup_files:
            raise Http404("النسخة الاحتياطية غير موجودة")
        
        # Get company name for filename
        company_name = SystemSetting.get_setting('site_name', 'Company')
        company_name = company_name.replace(' ', '_').replace('/', '_')
        
        # Determine backup type
        has_db = any('db_' in f.name for f in backup_files)
        has_media = any('media_' in f.name for f in backup_files)
        
        if has_db and has_media:
            backup_type = 'Full'
        elif has_db:
            backup_type = 'Database'
        elif has_media:
            backup_type = 'Media'
        else:
            backup_type = 'Unknown'
        
        # Create display filename
        date_str = backup_id.replace('backup_', '')
        
        # If multiple files, create a zip
        if len(backup_files) > 1:
            import zipfile
            import tempfile
            
            display_filename = f'{company_name}_Backup_{backup_type}_{date_str}.zip'
            
            # Create temporary zip file
            temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
            with zipfile.ZipFile(temp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for backup_file in backup_files:
                    zipf.write(backup_file, backup_file.name)
            
            response = FileResponse(
                open(temp_zip.name, 'rb'),
                as_attachment=True,
                filename=display_filename
            )
            return response
        else:
            # Single file download
            backup_file = backup_files[0]
            
            # Get extension from original file
            ext = ''.join(backup_file.suffixes)
            display_filename = f'{company_name}_Backup_{backup_type}_{date_str}{ext}'
            
            response = FileResponse(
                open(backup_file, 'rb'),
                as_attachment=True,
                filename=display_filename
            )
            return response
            
    except Exception as e:
        logger.error(f"Backup download failed: {e}")
        raise Http404("فشل تحميل النسخة الاحتياطية")


@login_required
@require_http_methods(["POST"])
def restore_backup_from_upload(request):
    """
    Restore from an uploaded backup file (API endpoint)
    Enhanced with better validation and error handling
    """
    try:
        if not request.FILES.get('backup_file'):
            return JsonResponse({
                'success': False,
                'message': 'لم يتم رفع ملف النسخة الاحتياطية'
            }, status=400)
        
        backup_file = request.FILES['backup_file']
        restore_type = request.POST.get('restore_type', 'auto')
        
        # Validate file size (max 500MB)
        max_size = 500 * 1024 * 1024  # 500MB
        if backup_file.size > max_size:
            return JsonResponse({
                'success': False,
                'message': f'حجم الملف كبير جداً. الحد الأقصى {max_size // (1024*1024)} ميجابايت'
            }, status=400)
        
        # Validate file extension
        allowed_extensions = ['.sql', '.gz', '.tar', '.zip', '.db', '.sqlite3', '.json']
        file_ext = ''.join(Path(backup_file.name).suffixes)
        
        if not any(file_ext.lower().endswith(ext) for ext in allowed_extensions):
            return JsonResponse({
                'success': False,
                'message': f'نوع الملف غير مدعوم. الصيغ المدعومة: {", ".join(allowed_extensions)}'
            }, status=400)
        
        logger.info(f"Starting restore from uploaded file: {backup_file.name}, size: {backup_file.size} bytes, type: {restore_type}")
        
        # Save uploaded file temporarily
        import tempfile
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_ext)
        
        try:
            # Write file in chunks
            for chunk in backup_file.chunks():
                temp_file.write(chunk)
            temp_file.close()
            
            temp_path = Path(temp_file.name)
            logger.info(f"Uploaded file saved to: {temp_path}, size: {temp_path.stat().st_size} bytes")
            
            # Validate file was written correctly
            if not temp_path.exists() or temp_path.stat().st_size == 0:
                raise Exception("فشل حفظ الملف المرفوع")
            
            if temp_path.stat().st_size != backup_file.size:
                logger.warning(f"File size mismatch: uploaded={backup_file.size}, saved={temp_path.stat().st_size}")
            
            # Use BackupService to restore
            backup_service = BackupService()
            restore_info = backup_service.restore_from_uploaded_file(
                str(temp_path),
                restore_type=restore_type
            )
            
            logger.info(f"Restore completed successfully: {restore_info}")
            
            # Add success rate info if available
            success_message = 'تم استعادة النسخة الاحتياطية بنجاح'
            if 'success_rate' in restore_info:
                success_rate = restore_info['success_rate']
                if success_rate < 100:
                    success_message += f' (معدل النجاح: {success_rate:.1f}%)'
            
            return JsonResponse({
                'success': True,
                'message': success_message,
                'restored_components': restore_info.get('restored_components', []),
                'success_rate': restore_info.get('success_rate'),
                'details': restore_info.get('details')
            })
            
        except Exception as restore_error:
            logger.error(f"Restore operation failed: {restore_error}")
            import traceback
            error_traceback = traceback.format_exc()
            logger.error(error_traceback)
            
            # Provide user-friendly error message
            error_message = str(restore_error)
            
            # Translate common errors to Arabic
            if 'gzip' in error_message.lower() or 'badgzipfile' in error_message.lower():
                error_message = 'الملف ليس ملف gzip صحيح. تأكد من أن الملف غير تالف.'
            elif 'json' in error_message.lower() and 'decode' in error_message.lower():
                error_message = 'ملف JSON تالف أو غير صحيح. تأكد من صحة النسخة الاحتياطية.'
            elif 'mysql' in error_message.lower() or 'pymysql' in error_message.lower():
                error_message = 'فشل الاتصال بقاعدة البيانات أو خطأ في تنفيذ SQL. تأكد من صحة ملف النسخة الاحتياطية.'
            elif 'file' in error_message.lower() and 'not found' in error_message.lower():
                error_message = 'لم يتم العثور على الملف المطلوب. حاول مرة أخرى.'
            elif 'permission' in error_message.lower():
                error_message = 'خطأ في الصلاحيات. تأكد من صلاحيات الملفات والمجلدات.'
            elif 'unsupported' in error_message.lower() or 'غير مدعوم' in error_message:
                pass  # Keep original message
            elif 'empty' in error_message.lower() or 'فارغ' in error_message:
                pass  # Keep original message
            
            return JsonResponse({
                'success': False,
                'message': error_message,
                'error_details': str(restore_error) if settings.DEBUG else None
            }, status=500)
            
        finally:
            # Clean up temporary file
            try:
                if os.path.exists(temp_file.name):
                    os.unlink(temp_file.name)
                    logger.info(f"Temporary file cleaned up: {temp_file.name}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup temp file: {cleanup_error}")
        
    except Exception as e:
        logger.error(f"Backup restore from upload failed: {e}")
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(error_traceback)
        
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ غير متوقع: {str(e)}',
            'error_details': str(e) if settings.DEBUG else None
        }, status=500)


@login_required
@require_http_methods(["POST"])
def restore_backup(request):
    """
    Restore from a saved backup file (API endpoint)
    Simply finds the database file and restores it
    """
    try:
        backup_id = request.POST.get('backup_id')
        
        if not backup_id:
            return JsonResponse({
                'success': False,
                'message': 'معرف النسخة الاحتياطية مطلوب'
            }, status=400)
        
        logger.info(f"Starting restore from saved backup: {backup_id}")
        
        # Find backup files
        backup_service = BackupService()
        backup_dir = backup_service.backup_dir
        backup_files = list(backup_dir.glob(f"*{backup_id}*"))
        
        if not backup_files:
            return JsonResponse({
                'success': False,
                'message': 'النسخة الاحتياطية غير موجودة'
            }, status=404)
        
        # Find the database file
        db_file = next((f for f in backup_files if 'db_' in f.name), None)
        
        if not db_file:
            return JsonResponse({
                'success': False,
                'message': 'لم يتم العثور على ملف قاعدة البيانات'
            }, status=404)
        
        logger.info(f"Found database file: {db_file.name}")
        
        # Restore using the uploaded file method (it handles everything)
        restore_info = backup_service.restore_from_uploaded_file(
            str(db_file),
            restore_type='database'  # Always database for individual files
        )
        
        logger.info(f"Restore completed successfully: {restore_info}")
        
        # Build success message
        success_message = 'تم استعادة النسخة الاحتياطية بنجاح'
        if 'success_rate' in restore_info and restore_info['success_rate']:
            success_rate = restore_info['success_rate']
            if success_rate < 100:
                success_message += f' (معدل النجاح: {success_rate:.1f}%)'
        
        return JsonResponse({
            'success': True,
            'message': success_message,
            'restored_components': restore_info.get('restored_components', []),
            'success_rate': restore_info.get('success_rate'),
            'details': restore_info.get('details')
        })
        
    except Exception as e:
        logger.error(f"Backup restore failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        return JsonResponse({
            'success': False,
            'message': f'فشل استعادة النسخة الاحتياطية: {str(e)}',
            'error_details': str(e) if settings.DEBUG else None
        }, status=500)


@login_required
def list_backups(request):
    """
    List all available backups (API endpoint)
    """
    try:
        backup_service = BackupService()
        backups = backup_service.list_backups()
        
        # Get company name for display
        company_name = SystemSetting.get_setting('site_name', 'Company')
        company_name = company_name.replace(' ', '_').replace('/', '_')
        
        # Convert datetime objects to strings and add display name
        for backup in backups:
            backup['created_at'] = backup['created_at'].isoformat()
            
            # Determine backup type from files
            backup_type = 'Full'
            has_db = any('db_' in f['filename'] for f in backup['files'])
            has_media = any('media_' in f['filename'] for f in backup['files'])
            
            if has_db and has_media:
                backup_type = 'Full'
            elif has_db:
                backup_type = 'Database'
            elif has_media:
                backup_type = 'Media'
            
            # Create display name
            date_str = backup['backup_id'].replace('backup_', '')
            backup['display_name'] = f'{company_name}_Backup_{backup_type}_{date_str}'
        
        return JsonResponse({
            'success': True,
            'backups': backups
        })
        
    except Exception as e:
        logger.error(f"Failed to list backups: {e}")
        return JsonResponse({
            'success': False,
            'message': 'فشل تحميل قائمة النسخ الاحتياطية'
        }, status=500)


@login_required
@require_http_methods(["POST"])
def delete_backup(request, backup_id):
    """
    Delete a backup (API endpoint)
    """
    try:
        backup_service = BackupService()
        backup_dir = backup_service.backup_dir
        
        # Find and delete backup files
        backup_files = list(backup_dir.glob(f"*{backup_id}*"))
        
        if not backup_files:
            return JsonResponse({
                'success': False,
                'message': 'النسخة الاحتياطية غير موجودة'
            })
        
        for backup_file in backup_files:
            backup_file.unlink()
        
        return JsonResponse({
            'success': True,
            'message': 'تم حذف النسخة الاحتياطية بنجاح'
        })
        
    except Exception as e:
        logger.error(f"Backup deletion failed: {e}")
        return JsonResponse({
            'success': False,
            'message': f'فشل حذف النسخة الاحتياطية: {str(e)}'
        }, status=500)


@login_required
def get_backup_settings(request):
    """
    Get backup settings from SystemSettings (API endpoint)
    Separate settings for each backup type + automatic schedule
    """
    try:
        # Database backup settings
        backup_settings = {
            'db_retention_type': SystemSetting.get_setting('backup_db_retention_type', 'count'),
            'db_retention_count': SystemSetting.get_setting('backup_db_retention_count', 10),
            'db_retention_days': SystemSetting.get_setting('backup_db_retention_days', 30),
            'db_auto_cleanup': SystemSetting.get_setting('backup_db_auto_cleanup', True),
            
            # Full backup settings
            'full_retention_type': SystemSetting.get_setting('backup_full_retention_type', 'count'),
            'full_retention_count': SystemSetting.get_setting('backup_full_retention_count', 5),
            'full_retention_days': SystemSetting.get_setting('backup_full_retention_days', 60),
            'full_auto_cleanup': SystemSetting.get_setting('backup_full_auto_cleanup', True),
            
            # Media backup settings
            'media_retention_type': SystemSetting.get_setting('backup_media_retention_type', 'count'),
            'media_retention_count': SystemSetting.get_setting('backup_media_retention_count', 3),
            'media_retention_days': SystemSetting.get_setting('backup_media_retention_days', 90),
            'media_auto_cleanup': SystemSetting.get_setting('backup_media_auto_cleanup', True),
            
            # Automatic backup schedule settings
            'enable_daily_db_backup': SystemSetting.get_setting('backup_enable_daily_db', False),
            'daily_db_backup_time': SystemSetting.get_setting('backup_daily_db_time', '02:00'),
            
            'enable_weekly_full_backup': SystemSetting.get_setting('backup_enable_weekly_full', False),
            'weekly_full_backup_day': SystemSetting.get_setting('backup_weekly_full_day', '5'),
            'weekly_full_backup_time': SystemSetting.get_setting('backup_weekly_full_time', '03:00'),
            
            'enable_monthly_media_backup': SystemSetting.get_setting('backup_enable_monthly_media', False),
            'monthly_media_backup_day': SystemSetting.get_setting('backup_monthly_media_day', '1'),
            'monthly_media_backup_time': SystemSetting.get_setting('backup_monthly_media_time', '04:00'),
        }
        
        return JsonResponse({
            'success': True,
            'settings': backup_settings
        })
        
    except Exception as e:
        logger.error(f"Failed to get backup settings: {e}")
        return JsonResponse({
            'success': False,
            'message': 'فشل تحميل الإعدادات'
        }, status=500)


@login_required
@require_http_methods(["POST"])
def update_backup_settings(request):
    """
    Update backup settings in SystemSetting (API endpoint)
    Separate settings for each backup type
    """
    try:
        # Database backup settings
        db_retention_type = request.POST.get('db_retention_type', 'count')
        db_retention_count = int(request.POST.get('db_retention_count', 10))
        db_retention_days = int(request.POST.get('db_retention_days', 30))
        db_auto_cleanup = request.POST.get('db_auto_cleanup', 'false').lower() == 'true'
        
        # Full backup settings
        full_retention_type = request.POST.get('full_retention_type', 'count')
        full_retention_count = int(request.POST.get('full_retention_count', 5))
        full_retention_days = int(request.POST.get('full_retention_days', 60))
        full_auto_cleanup = request.POST.get('full_auto_cleanup', 'false').lower() == 'true'
        
        # Media backup settings
        media_retention_type = request.POST.get('media_retention_type', 'count')
        media_retention_count = int(request.POST.get('media_retention_count', 3))
        media_retention_days = int(request.POST.get('media_retention_days', 90))
        media_auto_cleanup = request.POST.get('media_auto_cleanup', 'false').lower() == 'true'
        
        # Validate retention types
        valid_types = ['count', 'days', 'none']
        if db_retention_type not in valid_types or full_retention_type not in valid_types or media_retention_type not in valid_types:
            return JsonResponse({
                'success': False,
                'message': 'نوع سياسة الاحتفاظ غير صحيح'
            })
        
        # Save database backup settings
        SystemSetting.objects.update_or_create(
            key='backup_db_retention_type',
            defaults={'value': db_retention_type, 'group': 'backup', 'data_type': 'string'}
        )
        SystemSetting.objects.update_or_create(
            key='backup_db_retention_count',
            defaults={'value': str(db_retention_count), 'group': 'backup', 'data_type': 'integer'}
        )
        SystemSetting.objects.update_or_create(
            key='backup_db_retention_days',
            defaults={'value': str(db_retention_days), 'group': 'backup', 'data_type': 'integer'}
        )
        SystemSetting.objects.update_or_create(
            key='backup_db_auto_cleanup',
            defaults={'value': str(db_auto_cleanup), 'group': 'backup', 'data_type': 'boolean'}
        )
        
        # Save full backup settings
        SystemSetting.objects.update_or_create(
            key='backup_full_retention_type',
            defaults={'value': full_retention_type, 'group': 'backup', 'data_type': 'string'}
        )
        SystemSetting.objects.update_or_create(
            key='backup_full_retention_count',
            defaults={'value': str(full_retention_count), 'group': 'backup', 'data_type': 'integer'}
        )
        SystemSetting.objects.update_or_create(
            key='backup_full_retention_days',
            defaults={'value': str(full_retention_days), 'group': 'backup', 'data_type': 'integer'}
        )
        SystemSetting.objects.update_or_create(
            key='backup_full_auto_cleanup',
            defaults={'value': str(full_auto_cleanup), 'group': 'backup', 'data_type': 'boolean'}
        )
        
        # Save media backup settings
        SystemSetting.objects.update_or_create(
            key='backup_media_retention_type',
            defaults={'value': media_retention_type, 'group': 'backup', 'data_type': 'string'}
        )
        SystemSetting.objects.update_or_create(
            key='backup_media_retention_count',
            defaults={'value': str(media_retention_count), 'group': 'backup', 'data_type': 'integer'}
        )
        SystemSetting.objects.update_or_create(
            key='backup_media_retention_days',
            defaults={'value': str(media_retention_days), 'group': 'backup', 'data_type': 'integer'}
        )
        SystemSetting.objects.update_or_create(
            key='backup_media_auto_cleanup',
            defaults={'value': str(media_auto_cleanup), 'group': 'backup', 'data_type': 'boolean'}
        )
        
        # Save automatic backup schedule settings
        enable_daily_db = request.POST.get('enable_daily_db_backup', 'false').lower() == 'true'
        daily_db_time = request.POST.get('daily_db_backup_time', '02:00')
        
        enable_weekly_full = request.POST.get('enable_weekly_full_backup', 'false').lower() == 'true'
        weekly_full_day = request.POST.get('weekly_full_backup_day', '5')
        weekly_full_time = request.POST.get('weekly_full_backup_time', '03:00')
        
        enable_monthly_media = request.POST.get('enable_monthly_media_backup', 'false').lower() == 'true'
        monthly_media_day = request.POST.get('monthly_media_backup_day', '1')
        monthly_media_time = request.POST.get('monthly_media_backup_time', '04:00')
        
        SystemSetting.objects.update_or_create(
            key='backup_enable_daily_db',
            defaults={'value': str(enable_daily_db), 'group': 'backup', 'data_type': 'boolean'}
        )
        SystemSetting.objects.update_or_create(
            key='backup_daily_db_time',
            defaults={'value': daily_db_time, 'group': 'backup', 'data_type': 'string'}
        )
        
        SystemSetting.objects.update_or_create(
            key='backup_enable_weekly_full',
            defaults={'value': str(enable_weekly_full), 'group': 'backup', 'data_type': 'boolean'}
        )
        SystemSetting.objects.update_or_create(
            key='backup_weekly_full_day',
            defaults={'value': str(weekly_full_day), 'group': 'backup', 'data_type': 'string'}
        )
        SystemSetting.objects.update_or_create(
            key='backup_weekly_full_time',
            defaults={'value': weekly_full_time, 'group': 'backup', 'data_type': 'string'}
        )
        
        SystemSetting.objects.update_or_create(
            key='backup_enable_monthly_media',
            defaults={'value': str(enable_monthly_media), 'group': 'backup', 'data_type': 'boolean'}
        )
        SystemSetting.objects.update_or_create(
            key='backup_monthly_media_day',
            defaults={'value': str(monthly_media_day), 'group': 'backup', 'data_type': 'string'}
        )
        SystemSetting.objects.update_or_create(
            key='backup_monthly_media_time',
            defaults={'value': monthly_media_time, 'group': 'backup', 'data_type': 'string'}
        )
        
        logger.info(f"Backup settings updated - DB: {db_retention_type}/{db_retention_count}, Full: {full_retention_type}/{full_retention_count}, Media: {media_retention_type}/{media_retention_count}")
        logger.info(f"Schedule settings - Daily DB: {enable_daily_db}, Weekly Full: {enable_weekly_full}, Monthly Media: {enable_monthly_media}")
        
        return JsonResponse({
            'success': True,
            'message': 'تم حفظ جميع الإعدادات بنجاح'
        })
        
    except Exception as e:
        logger.error(f"Failed to update backup settings: {e}")
        return JsonResponse({
            'success': False,
            'message': f'فشل حفظ الإعدادات: {str(e)}'
        }, status=500)


@login_required
@require_http_methods(["POST"])
def cleanup_old_backups(request):
    """
    Manually trigger cleanup of old backups (API endpoint)
    """
    try:
        backup_service = BackupService()
        backup_service._cleanup_old_backups()
        
        return JsonResponse({
            'success': True,
            'message': 'تم تنظيف النسخ القديمة بنجاح'
        })
        
    except Exception as e:
        logger.error(f"Backup cleanup failed: {e}")
        return JsonResponse({
            'success': False,
            'message': f'فشل تنظيف النسخ القديمة: {str(e)}'
        }, status=500)
