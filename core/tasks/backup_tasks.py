"""
Enterprise Automated Celery Tasks for Backup & Disaster Recovery
Handles scheduled backups, group retention, integrity validation, and reporting.
"""

import os
import shutil
import logging
from datetime import datetime, timedelta
from typing import List

from celery import shared_task
from django.conf import settings
from django.utils import timezone
from django.core.mail import send_mail

from core.services.backup_service import BackupService
from core.services.data_retention_service import DataRetentionService
from core.models import SystemSetting

logger = logging.getLogger(__name__)


def _get_notification_emails() -> List[str]:
    """Helper to parse notification email addresses from SystemSetting or settings.py"""
    raw_emails = SystemSetting.get_setting('backup_notification_emails', None)
    if not raw_emails:
        raw_emails = getattr(settings, 'BACKUP_NOTIFICATION_EMAILS', [])
    
    if isinstance(raw_emails, list):
        return [str(e).strip() for e in raw_emails if str(e).strip()]
    elif isinstance(raw_emails, str):
        return [e.strip() for e in raw_emails.replace(';', ',').split(',') if e.strip()]
    return []


@shared_task(bind=True, max_retries=3)
def create_daily_backup(self):
    """
    Create daily automated database backup
    """
    try:
        logger.info("Starting daily automated database backup task")
        
        backup_service = BackupService()
        backup_info = backup_service.create_backup(backup_type='database', download_mode=False)
        
        if backup_info.get('status') == 'completed':
            logger.info(f"Daily backup completed successfully: {backup_info['backup_id']}")
            _send_backup_task_notification(
                task_name="Daily Database Backup",
                status="success",
                details=backup_info
            )
            return {
                'status': 'success',
                'backup_id': backup_info['backup_id'],
                'files_created': len(backup_info.get('files', [])),
                'total_size_mb': backup_info.get('size_bytes', 0) / (1024 * 1024)
            }
        else:
            raise Exception(f"Backup failed with errors: {backup_info.get('errors')}")
            
    except Exception as e:
        logger.error(f"Daily backup task failed: {e}", exc_info=True)
        _send_backup_task_notification(
            task_name="Daily Database Backup",
            status="failed",
            error=str(e)
        )
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=300, exc=e)
        raise


@shared_task(bind=True, max_retries=2)
def create_weekly_backup(self):
    """
    Create weekly full comprehensive backup (DB + Media + Keys)
    """
    try:
        logger.info("Starting weekly full backup task")
        
        backup_service = BackupService()
        backup_info = backup_service.create_backup(backup_type='full', download_mode=False)
        
        if backup_info.get('status') == 'completed':
            storage_info = _check_backup_storage_space()
            _send_backup_task_notification(
                task_name="Weekly Full Backup",
                status="success",
                details=backup_info,
                additional_info={'storage_info': storage_info}
            )
            return {
                'status': 'success',
                'backup_id': backup_info['backup_id'],
                'total_size_mb': backup_info.get('size_bytes', 0) / (1024 * 1024),
                'storage_usage': storage_info.get('usage_percentage')
            }
        else:
            raise Exception(f"Weekly backup failed: {backup_info.get('errors')}")
            
    except Exception as e:
        logger.error(f"Weekly backup task failed: {e}", exc_info=True)
        _send_backup_task_notification(
            task_name="Weekly Full Backup",
            status="failed",
            error=str(e)
        )
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=600, exc=e)
        raise


@shared_task(bind=True, max_retries=2)
def create_monthly_backup(self):
    """
    Create monthly media archive backup
    """
    try:
        logger.info("Starting monthly media backup task")
        backup_service = BackupService()
        backup_info = backup_service.create_backup(backup_type='media', download_mode=False)
        
        if backup_info.get('status') == 'completed':
            return {
                'status': 'success',
                'backup_id': backup_info['backup_id'],
                'total_size_mb': backup_info.get('size_bytes', 0) / (1024 * 1024)
            }
        else:
            raise Exception(f"Monthly media backup failed: {backup_info.get('errors')}")
    except Exception as e:
        logger.error(f"Monthly media backup task failed: {e}", exc_info=True)
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=600, exc=e)
        raise


@shared_task(bind=True)
def verify_backup_integrity(self, backup_id: str):
    """
    Verify integrity of a specific backup (Fixed signature with self)
    """
    try:
        logger.info(f"Starting backup verification task for: {backup_id}")
        backup_service = BackupService()
        backup_files = backup_service._find_backup_files(backup_id)
        
        if not backup_files:
            raise Exception(f"No backup files found for ID: {backup_id}")
        
        mock_info = {
            'backup_id': backup_id,
            'files': [{'path': str(f), 'hash': backup_service._calculate_file_hash(f)} for f in backup_files]
        }
        res = backup_service._verify_backup_integrity(mock_info)
        return {'status': res.get('status'), 'backup_id': backup_id}
    except Exception as e:
        logger.error(f"Backup verification task failed: {e}", exc_info=True)
        raise


@shared_task(bind=True)
def cleanup_old_backups(self):
    """
    Clean up old backup files according to SystemSetting retention policies
    """
    try:
        logger.info("Starting automated backup retention cleanup task")
        backup_service = BackupService()
        stats = backup_service.cleanup_old_backups()
        return stats
    except Exception as e:
        logger.error(f"Backup cleanup task failed: {e}", exc_info=True)
        raise


@shared_task(bind=True)
def run_data_retention_cleanup(self, dry_run: bool = False):
    """
    Run data retention policy cleanup
    """
    try:
        logger.info(f"Starting data retention cleanup task (dry_run={dry_run})")
        retention_service = DataRetentionService()
        cleanup_result = retention_service.run_retention_cleanup(dry_run=dry_run)
        _send_retention_task_notification(cleanup_result)
        return cleanup_result
    except Exception as e:
        logger.error(f"Data retention cleanup task failed: {e}", exc_info=True)
        raise


@shared_task(bind=True)
def send_retention_notifications(self):
    """
    Send notifications for upcoming data deletions
    """
    try:
        retention_service = DataRetentionService()
        return retention_service.schedule_retention_notifications()
    except Exception as e:
        logger.error(f"Retention notifications task failed: {e}", exc_info=True)
        raise


@shared_task(bind=True)
def validate_data_protection_systems(self):
    """
    Validate data protection systems health and recent backup existence
    """
    try:
        backup_service = BackupService()
        validation_results = {
            'backup_system': _validate_backup_system(backup_service),
            'timestamp': timezone.now().isoformat()
        }
        
        overall = 'success' if validation_results['backup_system']['status'] == 'success' else 'failed'
        validation_results['overall_status'] = overall
        _send_validation_report(validation_results)
        return validation_results
    except Exception as e:
        logger.error(f"Data protection validation task failed: {e}", exc_info=True)
        raise


def _send_backup_task_notification(task_name: str, status: str, details: dict = None, error: str = None, additional_info: dict = None):
    """Send email notifications for backup tasks safely"""
    try:
        recipients = _get_notification_emails()
        if not recipients:
            return
        
        subject = f"[MWHEBA ERP] {task_name} - {'ناجح' if status == 'success' else 'فاشل'}"
        body = f"تقرير تنفيذ مهمة النسخ الاحتياطي: {task_name}\nالحالة: {status}\nالتوقيت: {timezone.now()}\n"
        if details:
            body += f"معرف النسخة: {details.get('backup_id', 'N/A')}\nالحجم: {details.get('size_bytes', 0) / (1024*1024):.2f} MB\n"
        if error:
            body += f"\nالخطأ المسجل:\n{error}\n"
            
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=True
        )
    except Exception as e:
        logger.warning(f"Failed to send backup task email: {e}")


def _send_retention_task_notification(cleanup_result: dict):
    """Send email notification for data retention cleanup"""
    try:
        recipients = _get_notification_emails()
        if not recipients:
            return
        subject = "[MWHEBA ERP] تقرير دورة الاحتفاظ بالبيانات"
        body = f"نتائج دورة تنظيف البيانات:\n{cleanup_result}"
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=True
        )
    except Exception as e:
        logger.warning(f"Failed to send retention email: {e}")


def _check_backup_storage_space() -> dict:
    """Check storage disk space usage percentage"""
    try:
        backup_dir = Path(getattr(settings, 'BACKUP_LOCAL_DIR', settings.BASE_DIR / 'backups'))
        total, used, free = shutil.disk_usage(backup_dir)
        return {
            'total_gb': total / (1024**3),
            'used_gb': used / (1024**3),
            'free_gb': free / (1024**3),
            'usage_percentage': (used / total) * 100
        }
    except Exception as e:
        logger.warning(f"Storage check error: {e}")
        return {'usage_percentage': 0, 'free_gb': 0}


def _validate_backup_system(backup_service: BackupService) -> dict:
    """Validate recent backups and storage accessibility"""
    result = {'status': 'success', 'errors': []}
    if not backup_service.backup_dir.exists():
        result['status'] = 'failed'
        result['errors'].append("Backup directory does not exist")
        return result
    
    backups = backup_service.list_backups()
    if backups:
        recent = backups[0]
        created_at = recent.get('created_at')
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at)
            except Exception:
                created_at = timezone.now()
        
        if timezone.is_naive(created_at):
            created_at = timezone.make_aware(created_at)
            
        days_old = (timezone.now() - created_at).days
        if days_old > 7:
            result['status'] = 'warning'
            result['errors'].append(f"Last backup is {days_old} days old")
    else:
        result['status'] = 'warning'
        result['errors'].append("No backups found on server")
        
    return result


def _send_validation_report(validation_results: dict):
    """Send data protection validation report"""
    try:
        recipients = _get_notification_emails()
        if not recipients:
            return
        subject = f"[MWHEBA ERP] تقرير فحص سلامة نظام الحماية ({validation_results.get('overall_status')})"
        send_mail(
            subject=subject,
            message=str(validation_results),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=True
        )
    except Exception as e:
        logger.warning(f"Failed to send validation report email: {e}")