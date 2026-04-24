# ============================================================
# PHASE 5: DATA PROTECTION - DATA RETENTION SERVICE
# ============================================================

"""
Comprehensive data retention and cleanup service.
Implements data lifecycle management with compliance and audit trails.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from django.core.mail import send_mail
from django.apps import apps
from dataclasses import dataclass
import json

logger = logging.getLogger(__name__)

@dataclass
class RetentionPolicy:
    """Data retention policy configuration"""
    model_name: str
    retention_days: int
    archive_before_delete: bool = True
    anonymize_before_delete: bool = False
    cascade_delete: bool = False
    conditions: Dict[str, Any] = None
    exclude_conditions: Dict[str, Any] = None
    notification_days: int = 30  # Days before deletion to send notification

class DataRetentionService:
    """
    Comprehensive data retention and lifecycle management service
    """
    
    def __init__(self):
        self.retention_policies = self._load_retention_policies()
        self.archive_enabled = getattr(settings, 'DATA_RETENTION_ARCHIVE_ENABLED', True)
        self.notification_enabled = getattr(settings, 'DATA_RETENTION_NOTIFICATIONS_ENABLED', True)
        self.notification_emails = getattr(settings, 'DATA_RETENTION_NOTIFICATION_EMAILS', [])
        
        # Compliance settings
        self.gdpr_enabled = getattr(settings, 'GDPR_COMPLIANCE_ENABLED', False)
        self.audit_enabled = getattr(settings, 'DATA_RETENTION_AUDIT_ENABLED', True)
        
    def _load_retention_policies(self) -> List[RetentionPolicy]:
        """
        Load data retention policies from settings
        """
        default_policies = [
            # Customer data - 7 years
            RetentionPolicy(
                model_name='client.Customer',
                retention_days=2555,
                archive_before_delete=True,
                anonymize_before_delete=True,
                conditions={'is_active': False}
            ),
            
            # Financial records - 7 years for tax compliance
            RetentionPolicy(
                model_name='financial.Transaction',
                retention_days=2555,
                archive_before_delete=True,
                cascade_delete=False
            ),
            
            # Payment records - 7 years
            RetentionPolicy(
                model_name='client.CustomerPayment',
                retention_days=2555,
                archive_before_delete=True
            ),
            
            # Audit logs - 3 years
            RetentionPolicy(
                model_name='governance.AuditLog',
                retention_days=1095,
                archive_before_delete=True
            ),
            
            # Session data - 30 days
            RetentionPolicy(
                model_name='django.contrib.sessions.Session',
                retention_days=30,
                archive_before_delete=False
            ),
            
            # Temporary files - 7 days
            RetentionPolicy(
                model_name='core.TempFile',
                retention_days=7,
                archive_before_delete=False
            ),
            
            # Email logs - 90 days
            RetentionPolicy(
                model_name='core.EmailLog',
                retention_days=90,
                archive_before_delete=True
            ),
            
            # Security events - 1 year
            RetentionPolicy(
                model_name='core.SecurityEvent',
                retention_days=365,
                archive_before_delete=True
            ),
            
            # Backup metadata - 1 year
            RetentionPolicy(
                model_name='core.BackupRecord',
                retention_days=365,
                archive_before_delete=False
            ),
            
            # User activity logs - 6 months
            RetentionPolicy(
                model_name='users.UserActivity',
                retention_days=180,
                archive_before_delete=True
            )
        ]
        
        # Load custom policies from settings
        custom_policies = getattr(settings, 'DATA_RETENTION_POLICIES', [])
        
        # Convert custom policies to RetentionPolicy objects
        for policy_config in custom_policies:
            policy = RetentionPolicy(**policy_config)
            default_policies.append(policy)
        
        return default_policies
    
    def run_retention_cleanup(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Run data retention cleanup process
        """
        cleanup_result = {
            'timestamp': timezone.now(),
            'dry_run': dry_run,
            'policies_processed': 0,
            'records_deleted': 0,
            'records_archived': 0,
            'records_anonymized': 0,
            'errors': [],
            'policy_results': []
        }
        
        try:
            logger.info(f"Starting data retention cleanup (dry_run={dry_run})")
            
            for policy in self.retention_policies:
                try:
                    policy_result = self._process_retention_policy(policy, dry_run)
                    cleanup_result['policy_results'].append(policy_result)
                    cleanup_result['policies_processed'] += 1
                    cleanup_result['records_deleted'] += policy_result['deleted_count']
                    cleanup_result['records_archived'] += policy_result['archived_count']
                    cleanup_result['records_anonymized'] += policy_result['anonymized_count']
                    
                except Exception as e:
                    error_msg = f"Policy {policy.model_name} failed: {e}"
                    cleanup_result['errors'].append(error_msg)
                    logger.error(error_msg)
            
            # Send notification if enabled
            if self.notification_enabled and not dry_run:
                self._send_cleanup_notification(cleanup_result)
            
            logger.info(f"Data retention cleanup completed. Processed {cleanup_result['policies_processed']} policies")
            
        except Exception as e:
            cleanup_result['errors'].append(str(e))
            logger.error(f"Data retention cleanup failed: {e}")
        
        return cleanup_result
    
    def _process_retention_policy(self, policy: RetentionPolicy, dry_run: bool) -> Dict[str, Any]:
        """
        Process a single retention policy
        """
        policy_result = {
            'policy_name': policy.model_name,
            'retention_days': policy.retention_days,
            'cutoff_date': timezone.now() - timedelta(days=policy.retention_days),
            'deleted_count': 0,
            'archived_count': 0,
            'anonymized_count': 0,
            'errors': []
        }
        
        try:
            # Get model class
            model_class = self._get_model_class(policy.model_name)
            if not model_class:
                raise Exception(f"Model not found: {policy.model_name}")
            
            # Build query for expired records
            query_filters = self._build_query_filters(policy, policy_result['cutoff_date'])
            
            # Get expired records
            expired_records = model_class.objects.filter(**query_filters)
            
            # Apply exclude conditions if specified
            if policy.exclude_conditions:
                expired_records = expired_records.exclude(**policy.exclude_conditions)
            
            total_expired = expired_records.count()
            logger.info(f"Found {total_expired} expired records for {policy.model_name}")
            
            if total_expired == 0:
                return policy_result
            
            # Process records in batches
            batch_size = 100
            processed = 0
            
            while processed < total_expired:
                batch = list(expired_records[processed:processed + batch_size])
                
                if not batch:
                    break
                
                if not dry_run:
                    with transaction.atomic():
                        batch_result = self._process_record_batch(batch, policy)
                        policy_result['deleted_count'] += batch_result['deleted']
                        policy_result['archived_count'] += batch_result['archived']
                        policy_result['anonymized_count'] += batch_result['anonymized']
                else:
                    # Dry run - just count
                    policy_result['deleted_count'] += len(batch)
                
                processed += len(batch)
                
                # Log progress
                if processed % 1000 == 0:
                    logger.info(f"Processed {processed}/{total_expired} records for {policy.model_name}")
            
        except Exception as e:
            policy_result['errors'].append(str(e))
            logger.error(f"Policy processing failed for {policy.model_name}: {e}")
        
        return policy_result
    
    def _get_model_class(self, model_name: str):
        """
        Get model class from string name
        """
        try:
            app_label, model_name = model_name.split('.')
            return apps.get_model(app_label, model_name)
        except (ValueError, LookupError) as e:
            logger.error(f"Failed to get model class for {model_name}: {e}")
            return None
    
    def _build_query_filters(self, policy: RetentionPolicy, cutoff_date: datetime) -> Dict[str, Any]:
        """
        Build query filters for finding expired records
        """
        filters = {}
        
        # Add date filter - try common date field names
        date_fields = ['created_at', 'date_created', 'timestamp', 'date', 'updated_at']
        
        model_class = self._get_model_class(policy.model_name)
        if model_class:
            model_fields = [field.name for field in model_class._meta.fields]
            
            # Find the appropriate date field
            date_field = None
            for field_name in date_fields:
                if field_name in model_fields:
                    date_field = field_name
                    break
            
            if date_field:
                filters[f'{date_field}__lt'] = cutoff_date
            else:
                logger.warning(f"No date field found for {policy.model_name}")
        
        # Add custom conditions
        if policy.conditions:
            filters.update(policy.conditions)
        
        return filters
    
    def _process_record_batch(self, records: List[models.Model], policy: RetentionPolicy) -> Dict[str, int]:
        """
        Process a batch of records according to retention policy
        """
        batch_result = {
            'deleted': 0,
            'archived': 0,
            'anonymized': 0
        }
        
        for record in records:
            try:
                # Archive before deletion if enabled
                if policy.archive_before_delete and self.archive_enabled:
                    self._archive_record(record)
                    batch_result['archived'] += 1
                
                # Anonymize before deletion if enabled
                if policy.anonymize_before_delete:
                    self._anonymize_record(record)
                    batch_result['anonymized'] += 1
                
                # Log deletion if audit enabled
                if self.audit_enabled:
                    self._log_record_deletion(record, policy)
                
                # Delete record
                if policy.cascade_delete:
                    record.delete()  # This will cascade to related objects
                else:
                    # Check for related objects before deletion
                    related_objects = self._get_related_objects(record)
                    if related_objects:
                        logger.warning(f"Skipping deletion of {record} - has related objects")
                        continue
                    
                    record.delete()
                
                batch_result['deleted'] += 1
                
            except Exception as e:
                logger.error(f"Failed to process record {record}: {e}")
        
        return batch_result
    
    def _archive_record(self, record: models.Model):
        """
        Archive a record before deletion
        """
        try:
            # Create archive data
            archive_data = {
                'model': f"{record._meta.app_label}.{record._meta.model_name}",
                'pk': record.pk,
                'data': self._serialize_record(record),
                'archived_at': timezone.now().isoformat(),
                'archived_by': 'data_retention_service'
            }
            
            # Save to archive (could be file, database, or external service)
            self._save_to_archive(archive_data)
            
        except Exception as e:
            logger.error(f"Failed to archive record {record}: {e}")
    
    def _serialize_record(self, record: models.Model) -> Dict[str, Any]:
        """
        Serialize a record to dictionary
        """
        data = {}
        
        for field in record._meta.fields:
            try:
                value = getattr(record, field.name)
                
                # Handle special field types
                if isinstance(field, models.DateTimeField) and value:
                    data[field.name] = value.isoformat()
                elif isinstance(field, models.DateField) and value:
                    data[field.name] = value.isoformat()
                elif isinstance(field, models.DecimalField) and value:
                    data[field.name] = str(value)
                elif isinstance(field, models.ForeignKey) and value:
                    data[field.name] = value.pk
                else:
                    data[field.name] = value
                    
            except Exception as e:
                logger.warning(f"Failed to serialize field {field.name}: {e}")
                data[field.name] = None
        
        return data
    
    def _save_to_archive(self, archive_data: Dict[str, Any]):
        """
        Save archived data to storage
        """
        # This could be implemented to save to:
        # - Archive database table
        # - File system
        # - External archive service
        # - Cloud storage
        
        # For now, log the archive (implement actual storage as needed)
        logger.info(f"Archived record: {archive_data['model']} ID {archive_data['pk']}")
    
    def _anonymize_record(self, record: models.Model):
        """
        Anonymize sensitive fields in a record
        """
        try:
            from core.services.data_encryption_service import DataEncryptionService
            
            encryption_service = DataEncryptionService()
            
            # Get sensitive fields
            sensitive_fields = [
                field.name for field in record._meta.fields
                if encryption_service.is_field_sensitive(field.name)
            ]
            
            # Anonymize each sensitive field
            for field_name in sensitive_fields:
                try:
                    field = record._meta.get_field(field_name)
                    
                    if isinstance(field, models.CharField):
                        setattr(record, field_name, f"ANONYMIZED_{record.pk}")
                    elif isinstance(field, models.EmailField):
                        setattr(record, field_name, f"anonymized_{record.pk}@example.com")
                    elif isinstance(field, models.TextField):
                        setattr(record, field_name, "ANONYMIZED_TEXT")
                    
                except Exception as e:
                    logger.warning(f"Failed to anonymize field {field_name}: {e}")
            
            # Save anonymized record
            record.save(update_fields=sensitive_fields)
            
        except Exception as e:
            logger.error(f"Failed to anonymize record {record}: {e}")
    
    def _get_related_objects(self, record: models.Model) -> List[models.Model]:
        """
        Get related objects that would prevent deletion
        """
        related_objects = []
        
        try:
            # Check reverse foreign keys
            for rel in record._meta.related_objects:
                if rel.on_delete == models.PROTECT:
                    related_manager = getattr(record, rel.get_accessor_name())
                    if related_manager.exists():
                        related_objects.extend(list(related_manager.all()[:5]))  # Limit for performance
        
        except Exception as e:
            logger.warning(f"Failed to check related objects for {record}: {e}")
        
        return related_objects
    
    def _log_record_deletion(self, record: models.Model, policy: RetentionPolicy):
        """
        Log record deletion for audit trail
        """
        try:
            audit_data = {
                'action': 'data_retention_deletion',
                'model': f"{record._meta.app_label}.{record._meta.model_name}",
                'object_id': record.pk,
                'policy': policy.model_name,
                'retention_days': policy.retention_days,
                'timestamp': timezone.now().isoformat(),
                'user': 'system'
            }
            
            # Log to audit system (implement as needed)
            logger.info(f"Data retention deletion: {json.dumps(audit_data)}")
            
        except Exception as e:
            logger.error(f"Failed to log deletion for {record}: {e}")
    
    def _send_cleanup_notification(self, cleanup_result: Dict[str, Any]):
        """
        Send notification about cleanup results
        """
        try:
            if not self.notification_emails:
                return
            
            subject = f"Data Retention Cleanup Report - {cleanup_result['timestamp'].strftime('%Y-%m-%d')}"
            
            message = f"""
Data Retention Cleanup Report

Timestamp: {cleanup_result['timestamp']}
Policies Processed: {cleanup_result['policies_processed']}
Records Deleted: {cleanup_result['records_deleted']}
Records Archived: {cleanup_result['records_archived']}
Records Anonymized: {cleanup_result['records_anonymized']}

Policy Details:
"""
            
            for policy_result in cleanup_result['policy_results']:
                message += f"""
- {policy_result['policy_name']}:
  Retention: {policy_result['retention_days']} days
  Cutoff Date: {policy_result['cutoff_date']}
  Deleted: {policy_result['deleted_count']}
  Archived: {policy_result['archived_count']}
  Anonymized: {policy_result['anonymized_count']}
"""
                
                if policy_result['errors']:
                    message += f"  Errors: {', '.join(policy_result['errors'])}\n"
            
            if cleanup_result['errors']:
                message += f"\nGlobal Errors:\n"
                for error in cleanup_result['errors']:
                    message += f"- {error}\n"
            
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=self.notification_emails,
                fail_silently=False
            )
            
        except Exception as e:
            logger.error(f"Failed to send cleanup notification: {e}")
    
    def get_retention_status(self) -> Dict[str, Any]:
        """
        Get current retention status for all policies
        """
        status = {
            'timestamp': timezone.now(),
            'policies': [],
            'total_policies': len(self.retention_policies)
        }
        
        for policy in self.retention_policies:
            try:
                model_class = self._get_model_class(policy.model_name)
                if not model_class:
                    continue
                
                cutoff_date = timezone.now() - timedelta(days=policy.retention_days)
                query_filters = self._build_query_filters(policy, cutoff_date)
                
                expired_count = model_class.objects.filter(**query_filters).count()
                total_count = model_class.objects.count()
                
                policy_status = {
                    'model_name': policy.model_name,
                    'retention_days': policy.retention_days,
                    'cutoff_date': cutoff_date,
                    'total_records': total_count,
                    'expired_records': expired_count,
                    'retention_percentage': (total_count - expired_count) / total_count * 100 if total_count > 0 else 0
                }
                
                status['policies'].append(policy_status)
                
            except Exception as e:
                logger.error(f"Failed to get status for {policy.model_name}: {e}")
        
        return status
    
    def schedule_retention_notifications(self) -> Dict[str, Any]:
        """
        Schedule notifications for upcoming data deletions
        """
        notification_result = {
            'timestamp': timezone.now(),
            'notifications_sent': 0,
            'errors': []
        }
        
        try:
            for policy in self.retention_policies:
                if policy.notification_days <= 0:
                    continue
                
                try:
                    # Calculate notification date
                    notification_cutoff = timezone.now() - timedelta(
                        days=policy.retention_days - policy.notification_days
                    )
                    
                    model_class = self._get_model_class(policy.model_name)
                    if not model_class:
                        continue
                    
                    # Find records that will be deleted soon
                    query_filters = self._build_query_filters(policy, notification_cutoff)
                    upcoming_deletions = model_class.objects.filter(**query_filters).count()
                    
                    if upcoming_deletions > 0:
                        self._send_deletion_notification(policy, upcoming_deletions)
                        notification_result['notifications_sent'] += 1
                
                except Exception as e:
                    error_msg = f"Notification failed for {policy.model_name}: {e}"
                    notification_result['errors'].append(error_msg)
                    logger.error(error_msg)
        
        except Exception as e:
            notification_result['errors'].append(str(e))
            logger.error(f"Retention notification scheduling failed: {e}")
        
        return notification_result
    
    def _send_deletion_notification(self, policy: RetentionPolicy, record_count: int):
        """
        Send notification about upcoming deletions
        """
        try:
            if not self.notification_emails:
                return
            
            subject = f"Upcoming Data Deletion Notification - {policy.model_name}"
            
            message = f"""
Data Deletion Notification

Model: {policy.model_name}
Records to be deleted: {record_count}
Deletion date: {(timezone.now() + timedelta(days=policy.notification_days)).strftime('%Y-%m-%d')}
Retention policy: {policy.retention_days} days

Archive before deletion: {'Yes' if policy.archive_before_delete else 'No'}
Anonymize before deletion: {'Yes' if policy.anonymize_before_delete else 'No'}

This is an automated notification from the data retention system.
"""
            
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=self.notification_emails,
                fail_silently=False
            )
            
        except Exception as e:
            logger.error(f"Failed to send deletion notification: {e}")
    
    def create_data_export(self, model_name: str, filters: Dict[str, Any] = None) -> str:
        """
        Create data export for compliance or backup purposes
        """
        try:
            model_class = self._get_model_class(model_name)
            if not model_class:
                raise Exception(f"Model not found: {model_name}")
            
            # Build query
            queryset = model_class.objects.all()
            if filters:
                queryset = queryset.filter(**filters)
            
            # Export data
            export_data = []
            for record in queryset:
                export_data.append(self._serialize_record(record))
            
            # Save export file
            timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
            filename = f"data_export_{model_name.replace('.', '_')}_{timestamp}.json"
            
            export_path = f"/tmp/{filename}"
            with open(export_path, 'w') as f:
                json.dump(export_data, f, indent=2, default=str)
            
            logger.info(f"Data export created: {export_path} ({len(export_data)} records)")
            return export_path
            
        except Exception as e:
            logger.error(f"Data export failed for {model_name}: {e}")
            raise