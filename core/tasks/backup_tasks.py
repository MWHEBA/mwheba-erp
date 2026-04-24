# ============================================================
# PHASE 5: DATA PROTECTION - BACKUP CELERY TASKS
# ============================================================

"""
Celery tasks for automated backup operations.
Handles scheduled backups, verification, and cleanup.
"""

import logging
from datetime import datetime, timedelta
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from django.core.mail import send_mail
from core.services.backup_service import BackupService
from core.services.data_retention_service import DataRetentionService

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def create_daily_backup(self):
    """
    Create daily automated backup
    """
    try:
        logger.info("Starting daily backup task")
        
        backup_service = BackupService()
        backup_info = backup_service.create_backup(backup_type='full', download_mode=False)
        
        if backup_info['status'] == 'completed':
            logger.info(f"Daily backup completed successfully: {backup_info['backup_id']}")
            
            # Send success notification
            _send_backup_task_notification(
                task_name="Daily Backup",
                status="success",
                details=backup_info
            )
            
            return {
                'status': 'success',
                'backup_id': backup_info['backup_id'],
                'files_created': len(backup_info['files']),
                'total_size_mb': backup_info['size_bytes'] / (1024 * 1024)
            }
        else:
            raise Exception(f"Backup failed with status: {backup_info['status']}")
            
    except Exception as e:
        logger.error(f"Daily backup task failed: {e}")
        
        # Send failure notification
        _send_backup_task_notification(
            task_name="Daily Backup",
            status="failed",
            error=str(e)
        )
        
        # Retry the task
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying daily backup task (attempt {self.request.retries + 1})")
            raise self.retry(countdown=300, exc=e)  # Retry after 5 minutes
        
        raise

@shared_task(bind=True, max_retries=2)
def create_weekly_backup(self):
    """
    Create weekly comprehensive backup
    """
    try:
        logger.info("Starting weekly backup task")
        
        backup_service = BackupService()
        
        # Create full backup with extended verification
        backup_info = backup_service.create_backup(backup_type='full', download_mode=False)
        
        if backup_info['status'] == 'completed':
            # Additional weekly backup tasks
            weekly_tasks = []
            
            # Verify backup integrity more thoroughly
            if 'verification' in backup_info:
                verification = backup_info['verification']
                if verification['status'] != 'success':
                    weekly_tasks.append(f"Verification issues: {verification['failed_files']} files failed")
            
            # Check backup storage space
            storage_info = _check_backup_storage_space()
            if storage_info['usage_percentage'] > 80:
                weekly_tasks.append(f"Storage usage high: {storage_info['usage_percentage']:.1f}%")
            
            # Generate backup report
            report = _generate_weekly_backup_report(backup_info, storage_info)
            
            logger.info(f"Weekly backup completed successfully: {backup_info['backup_id']}")
            
            # Send detailed notification
            _send_backup_task_notification(
                task_name="Weekly Backup",
                status="success",
                details=backup_info,
                additional_info={
                    'weekly_tasks': weekly_tasks,
                    'storage_info': storage_info,
                    'report': report
                }
            )
            
            return {
                'status': 'success',
                'backup_id': backup_info['backup_id'],
                'files_created': len(backup_info['files']),
                'total_size_mb': backup_info['size_bytes'] / (1024 * 1024),
                'weekly_tasks': weekly_tasks,
                'storage_usage': storage_info['usage_percentage']
            }
        else:
            raise Exception(f"Weekly backup failed with status: {backup_info['status']}")
            
    except Exception as e:
        logger.error(f"Weekly backup task failed: {e}")
        
        # Send failure notification
        _send_backup_task_notification(
            task_name="Weekly Backup",
            status="failed",
            error=str(e)
        )
        
        # Retry the task
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying weekly backup task (attempt {self.request.retries + 1})")
            raise self.retry(countdown=600, exc=e)  # Retry after 10 minutes
        
        raise

@shared_task(bind=True)
def verify_backup_integrity(backup_id):
    """
    Verify integrity of a specific backup
    """
    try:
        logger.info(f"Starting backup verification for: {backup_id}")
        
        backup_service = BackupService()
        
        # Find backup files
        backup_files = backup_service._find_backup_files(backup_id)
        
        if not backup_files:
            raise Exception(f"No backup files found for backup ID: {backup_id}")
        
        # Create mock backup info for verification
        backup_info = {
            'backup_id': backup_id,
            'files': backup_files
        }
        
        # Verify integrity
        verification_result = backup_service._verify_backup_integrity(backup_info)
        
        if verification_result['status'] == 'success':
            logger.info(f"Backup verification successful: {backup_id}")
            return {
                'status': 'success',
                'backup_id': backup_id,
                'verified_files': verification_result['verified_files'],
                'failed_files': verification_result['failed_files']
            }
        else:
            logger.error(f"Backup verification failed: {backup_id}")
            
            # Send notification about verification failure
            _send_backup_task_notification(
                task_name="Backup Verification",
                status="failed",
                error=f"Verification failed for backup {backup_id}",
                details=verification_result
            )
            
            return {
                'status': 'failed',
                'backup_id': backup_id,
                'errors': verification_result['errors']
            }
            
    except Exception as e:
        logger.error(f"Backup verification task failed: {e}")
        raise

@shared_task(bind=True)
def cleanup_old_backups(self):
    """
    Clean up old backup files according to retention policy from SystemSettings
    """
    try:
        logger.info("Starting backup cleanup task")
        
        backup_service = BackupService()
        
        # Perform cleanup (reads settings from SystemSettings internally)
        backup_service._cleanup_old_backups()
        
        logger.info("Backup cleanup completed successfully")
        
        return {
            'status': 'success',
            'cleanup_date': timezone.now()
        }
        
    except Exception as e:
        logger.error(f"Backup cleanup task failed: {e}")
        raise

@shared_task(bind=True)
def run_data_retention_cleanup(self, dry_run=False):
    """
    Run data retention cleanup
    """
    try:
        logger.info(f"Starting data retention cleanup task (dry_run={dry_run})")
        
        retention_service = DataRetentionService()
        cleanup_result = retention_service.run_retention_cleanup(dry_run=dry_run)
        
        if cleanup_result['errors']:
            logger.warning(f"Data retention cleanup completed with errors: {cleanup_result['errors']}")
        else:
            logger.info("Data retention cleanup completed successfully")
        
        # Send notification
        _send_retention_task_notification(cleanup_result)
        
        return {
            'status': 'success' if not cleanup_result['errors'] else 'partial',
            'policies_processed': cleanup_result['policies_processed'],
            'records_deleted': cleanup_result['records_deleted'],
            'records_archived': cleanup_result['records_archived'],
            'errors': cleanup_result['errors']
        }
        
    except Exception as e:
        logger.error(f"Data retention cleanup task failed: {e}")
        
        # Send failure notification
        _send_retention_task_notification({
            'status': 'failed',
            'error': str(e),
            'timestamp': timezone.now()
        })
        
        raise

@shared_task(bind=True)
def send_retention_notifications(self):
    """
    Send notifications for upcoming data deletions
    """
    try:
        logger.info("Starting retention notifications task")
        
        retention_service = DataRetentionService()
        notification_result = retention_service.schedule_retention_notifications()
        
        logger.info(f"Retention notifications sent: {notification_result['notifications_sent']}")
        
        return {
            'status': 'success',
            'notifications_sent': notification_result['notifications_sent'],
            'errors': notification_result['errors']
        }
        
    except Exception as e:
        logger.error(f"Retention notifications task failed: {e}")
        raise

@shared_task(bind=True)
def validate_data_protection_systems(self):
    """
    Validate all data protection systems
    """
    try:
        logger.info("Starting data protection systems validation")
        
        validation_results = {}
        
        # Validate backup system
        backup_service = BackupService()
        backup_validation = _validate_backup_system(backup_service)
        validation_results['backup_system'] = backup_validation
        
        # Validate encryption system
        from core.services.data_encryption_service import DataEncryptionService
        encryption_service = DataEncryptionService()
        encryption_validation = encryption_service.validate_encryption_integrity()
        validation_results['encryption_system'] = encryption_validation
        
        # Validate retention system
        retention_service = DataRetentionService()
        retention_status = retention_service.get_retention_status()
        validation_results['retention_system'] = {
            'status': 'success',
            'total_policies': retention_status['total_policies'],
            'timestamp': retention_status['timestamp']
        }
        
        # Overall status
        overall_status = 'success'
        for system, result in validation_results.items():
            if result.get('status') != 'success':
                overall_status = 'failed'
                break
        
        validation_results['overall_status'] = overall_status
        
        # Send validation report
        _send_validation_report(validation_results)
        
        logger.info(f"Data protection validation completed with status: {overall_status}")
        
        return validation_results
        
    except Exception as e:
        logger.error(f"Data protection validation task failed: {e}")
        raise

def _send_backup_task_notification(task_name, status, details=None, error=None, additional_info=None):
    """
    Send notification about backup task results
    """
    try:
        notification_emails = getattr(settings, 'BACKUP_NOTIFICATION_EMAILS', [])
        if not notification_emails:
            return
        
        subject = f"{task_name} {'Completed' if status == 'success' else 'Failed'}"
        
        if status == 'success':
            message = f"""
{task_name} completed successfully!

Timestamp: {timezone.now()}
"""
            if details:
                message += f"""
Backup ID: {details.get('backup_id', 'N/A')}
Files Created: {len(details.get('files', []))}
Total Size: {details.get('size_bytes', 0) / (1024*1024):.2f} MB
Status: {details.get('status', 'Unknown')}
"""
                
                if 'verification' in details:
                    verification = details['verification']
                    message += f"""
Verification Status: {verification['status']}
Verified Files: {verification['verified_files']}
Failed Files: {verification['failed_files']}
"""
            
            if additional_info:
                if 'weekly_tasks' in additional_info and additional_info['weekly_tasks']:
                    message += f"\nWeekly Tasks:\n"
                    for task in additional_info['weekly_tasks']:
                        message += f"- {task}\n"
                
                if 'storage_info' in additional_info:
                    storage = additional_info['storage_info']
                    message += f"\nStorage Usage: {storage['usage_percentage']:.1f}%\n"
        else:
            message = f"""
{task_name} failed!

Timestamp: {timezone.now()}
Error: {error or 'Unknown error'}
"""
            if details and 'errors' in details:
                message += f"\nDetails:\n"
                for err in details['errors']:
                    message += f"- {err}\n"
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=notification_emails,
            fail_silently=True
        )
        
    except Exception as e:
        logger.error(f"Failed to send backup task notification: {e}")

def _send_retention_task_notification(cleanup_result):
    """
    Send notification about retention cleanup results
    """
    try:
        notification_emails = getattr(settings, 'DATA_RETENTION_NOTIFICATION_EMAILS', [])
        if not notification_emails:
            return
        
        status = cleanup_result.get('status', 'unknown')
        subject = f"Data Retention Cleanup {'Completed' if status == 'success' else 'Failed'}"
        
        if status in ['success', 'partial']:
            message = f"""
Data Retention Cleanup Report

Timestamp: {cleanup_result.get('timestamp', timezone.now())}
Status: {status}
Policies Processed: {cleanup_result.get('policies_processed', 0)}
Records Deleted: {cleanup_result.get('records_deleted', 0)}
Records Archived: {cleanup_result.get('records_archived', 0)}
Records Anonymized: {cleanup_result.get('records_anonymized', 0)}
"""
            
            if cleanup_result.get('errors'):
                message += f"\nErrors:\n"
                for error in cleanup_result['errors']:
                    message += f"- {error}\n"
        else:
            message = f"""
Data Retention Cleanup Failed

Timestamp: {cleanup_result.get('timestamp', timezone.now())}
Error: {cleanup_result.get('error', 'Unknown error')}
"""
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=notification_emails,
            fail_silently=True
        )
        
    except Exception as e:
        logger.error(f"Failed to send retention task notification: {e}")

def _check_backup_storage_space():
    """
    Check backup storage space usage
    """
    try:
        import shutil
        
        backup_dir = getattr(settings, 'BACKUP_LOCAL_DIR', '/tmp/backups')
        
        # Get disk usage
        total, used, free = shutil.disk_usage(backup_dir)
        
        usage_percentage = (used / total) * 100
        
        return {
            'total_gb': total / (1024**3),
            'used_gb': used / (1024**3),
            'free_gb': free / (1024**3),
            'usage_percentage': usage_percentage
        }
        
    except Exception as e:
        logger.error(f"Failed to check storage space: {e}")
        return {
            'total_gb': 0,
            'used_gb': 0,
            'free_gb': 0,
            'usage_percentage': 0
        }

def _generate_weekly_backup_report(backup_info, storage_info):
    """
    Generate weekly backup report
    """
    try:
        report = {
            'backup_summary': {
                'backup_id': backup_info.get('backup_id'),
                'files_created': len(backup_info.get('files', [])),
                'total_size_mb': backup_info.get('size_bytes', 0) / (1024 * 1024),
                'status': backup_info.get('status')
            },
            'storage_summary': storage_info,
            'verification_summary': backup_info.get('verification', {}),
            'upload_summary': backup_info.get('remote_upload', {}),
            'generated_at': timezone.now()
        }
        
        return report
        
    except Exception as e:
        logger.error(f"Failed to generate weekly backup report: {e}")
        return {}

def _validate_backup_system(backup_service):
    """
    Validate backup system functionality
    """
    try:
        validation_result = {
            'status': 'success',
            'tests_passed': 0,
            'tests_failed': 0,
            'errors': []
        }
        
        # Test 1: Check backup directory
        if backup_service.backup_dir.exists():
            validation_result['tests_passed'] += 1
        else:
            validation_result['tests_failed'] += 1
            validation_result['errors'].append("Backup directory does not exist")
        
        # Test 2: Check storage configuration
        if backup_service.storage_type in ['local', 's3', 'ftp', 'sftp']:
            validation_result['tests_passed'] += 1
        else:
            validation_result['tests_failed'] += 1
            validation_result['errors'].append(f"Invalid storage type: {backup_service.storage_type}")
        
        # Test 3: Check recent backups
        recent_backups = backup_service.list_backups()
        if recent_backups:
            # Check if we have backups from the last 7 days
            recent_backup = recent_backups[0]
            days_old = (timezone.now().date() - recent_backup['created_at'].date()).days
            
            if days_old <= 7:
                validation_result['tests_passed'] += 1
            else:
                validation_result['tests_failed'] += 1
                validation_result['errors'].append(f"No recent backups (last backup: {days_old} days ago)")
        else:
            validation_result['tests_failed'] += 1
            validation_result['errors'].append("No backups found")
        
        # Set overall status
        if validation_result['tests_failed'] > 0:
            validation_result['status'] = 'failed'
        
        return validation_result
        
    except Exception as e:
        return {
            'status': 'error',
            'tests_passed': 0,
            'tests_failed': 1,
            'errors': [str(e)]
        }

def _send_validation_report(validation_results):
    """
    Send data protection validation report
    """
    try:
        notification_emails = getattr(settings, 'BACKUP_NOTIFICATION_EMAILS', [])
        if not notification_emails:
            return
        
        overall_status = validation_results['overall_status']
        subject = f"Data Protection Validation {'Passed' if overall_status == 'success' else 'Failed'}"
        
        message = f"""
Data Protection Systems Validation Report

Overall Status: {overall_status.upper()}
Timestamp: {timezone.now()}

System Details:
"""
        
        for system_name, result in validation_results.items():
            if system_name == 'overall_status':
                continue
                
            message += f"""
{system_name.replace('_', ' ').title()}:
  Status: {result.get('status', 'unknown')}
  Tests Passed: {result.get('tests_passed', 'N/A')}
  Tests Failed: {result.get('tests_failed', 'N/A')}
"""
            
            if result.get('errors'):
                message += f"  Errors:\n"
                for error in result['errors']:
                    message += f"    - {error}\n"
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=notification_emails,
            fail_silently=True
        )
        
    except Exception as e:
        logger.error(f"Failed to send validation report: {e}")