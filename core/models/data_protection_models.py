# ============================================================
# PHASE 5: DATA PROTECTION - DATABASE MODELS
# ============================================================

"""
Database models for data protection, backup tracking, and retention policies.
"""

from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
import json

class BackupRecord(models.Model):
    """
    Track backup operations and their status
    """
    BACKUP_TYPES = [
        ('full', 'Full Backup'),
        ('database', 'Database Only'),
        ('media', 'Media Files Only'),
        ('config', 'Configuration Only'),
        ('incremental', 'Incremental Backup'),
    ]
    
    BACKUP_STATUS = [
        ('started', 'Started'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('verified', 'Verified'),
        ('corrupted', 'Corrupted'),
    ]
    
    STORAGE_TYPES = [
        ('local', 'Local Storage'),
        ('s3', 'Amazon S3'),
        ('ftp', 'FTP Server'),
        ('sftp', 'SFTP Server'),
    ]
    
    backup_id = models.CharField(max_length=100, unique=True, db_index=True)
    backup_type = models.CharField(max_length=20, choices=BACKUP_TYPES)
    status = models.CharField(max_length=20, choices=BACKUP_STATUS, default='started')
    storage_type = models.CharField(max_length=20, choices=STORAGE_TYPES)
    
    # Backup details
    total_size_bytes = models.BigIntegerField(default=0)
    file_count = models.IntegerField(default=0)
    compression_ratio = models.FloatField(null=True, blank=True)
    
    # Timing information
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.IntegerField(null=True, blank=True)
    
    # Verification information
    verification_status = models.CharField(max_length=20, null=True, blank=True)
    verified_files = models.IntegerField(default=0)
    failed_files = models.IntegerField(default=0)
    verification_errors = models.TextField(blank=True)
    
    # Remote storage information
    remote_path = models.CharField(max_length=500, blank=True)
    remote_upload_status = models.CharField(max_length=20, blank=True)
    
    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'core_backup_record'
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['backup_id']),
            models.Index(fields=['status']),
            models.Index(fields=['started_at']),
            models.Index(fields=['backup_type']),
        ]
    
    def __str__(self):
        return f"Backup {self.backup_id} ({self.backup_type}) - {self.status}"
    
    @property
    def size_mb(self):
        """Return size in megabytes"""
        return self.total_size_bytes / (1024 * 1024) if self.total_size_bytes else 0
    
    @property
    def is_successful(self):
        """Check if backup was successful"""
        return self.status in ['completed', 'verified']
    
    def mark_completed(self):
        """Mark backup as completed"""
        self.status = 'completed'
        self.completed_at = timezone.now()
        if self.started_at:
            self.duration_seconds = int((self.completed_at - self.started_at).total_seconds())
        self.save()
    
    def mark_failed(self, error_message=None):
        """Mark backup as failed"""
        self.status = 'failed'
        self.completed_at = timezone.now()
        if error_message:
            self.verification_errors = error_message
        self.save()


class BackupFile(models.Model):
    """
    Track individual files within a backup
    """
    FILE_TYPES = [
        ('database', 'Database Dump'),
        ('media', 'Media Archive'),
        ('config', 'Configuration Files'),
        ('logs', 'Log Files'),
        ('other', 'Other Files'),
    ]
    
    backup_record = models.ForeignKey(BackupRecord, on_delete=models.CASCADE, related_name='files')
    file_type = models.CharField(max_length=20, choices=FILE_TYPES)
    filename = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500)
    
    # File information
    size_bytes = models.BigIntegerField()
    checksum = models.CharField(max_length=64)  # SHA-256 hash
    is_encrypted = models.BooleanField(default=False)
    is_compressed = models.BooleanField(default=False)
    
    # Verification
    is_verified = models.BooleanField(default=False)
    verification_date = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        db_table = 'core_backup_file'
        ordering = ['file_type', 'filename']
        indexes = [
            models.Index(fields=['backup_record', 'file_type']),
            models.Index(fields=['checksum']),
        ]
    
    def __str__(self):
        return f"{self.filename} ({self.file_type})"
    
    @property
    def size_mb(self):
        """Return size in megabytes"""
        return self.size_bytes / (1024 * 1024)


class DataRetentionPolicy(models.Model):
    """
    Define data retention policies for different data types
    """
    POLICY_STATUS = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('draft', 'Draft'),
    ]
    
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    model_name = models.CharField(max_length=100)  # e.g., 'client.Customer'
    
    # Retention settings
    retention_days = models.IntegerField(validators=[MinValueValidator(1)])
    archive_before_delete = models.BooleanField(default=True)
    anonymize_before_delete = models.BooleanField(default=False)
    cascade_delete = models.BooleanField(default=False)
    
    # Notification settings
    notification_days = models.IntegerField(default=30, validators=[MinValueValidator(0)])
    
    # Policy conditions (stored as JSON)
    conditions = models.JSONField(default=dict, blank=True)
    exclude_conditions = models.JSONField(default=dict, blank=True)
    
    # Status and metadata
    status = models.CharField(max_length=20, choices=POLICY_STATUS, default='active')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        db_table = 'core_data_retention_policy'
        verbose_name_plural = 'Data Retention Policies'
        ordering = ['name']
        indexes = [
            models.Index(fields=['model_name']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.retention_days} days)"
    
    @property
    def is_active(self):
        """Check if policy is active"""
        return self.status == 'active'


class DataRetentionExecution(models.Model):
    """
    Track data retention cleanup executions
    """
    EXECUTION_STATUS = [
        ('started', 'Started'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('partial', 'Partially Completed'),
    ]
    
    execution_id = models.CharField(max_length=100, unique=True, db_index=True)
    policy = models.ForeignKey(DataRetentionPolicy, on_delete=models.CASCADE, related_name='executions')
    
    # Execution details
    status = models.CharField(max_length=20, choices=EXECUTION_STATUS, default='started')
    dry_run = models.BooleanField(default=False)
    
    # Results
    records_found = models.IntegerField(default=0)
    records_deleted = models.IntegerField(default=0)
    records_archived = models.IntegerField(default=0)
    records_anonymized = models.IntegerField(default=0)
    
    # Timing
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.IntegerField(null=True, blank=True)
    
    # Error tracking
    errors = models.TextField(blank=True)
    
    class Meta:
        db_table = 'core_data_retention_execution'
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['execution_id']),
            models.Index(fields=['policy', 'started_at']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"Retention execution {self.execution_id} - {self.policy.name}"
    
    def mark_completed(self):
        """Mark execution as completed"""
        self.status = 'completed'
        self.completed_at = timezone.now()
        if self.started_at:
            self.duration_seconds = int((self.completed_at - self.started_at).total_seconds())
        self.save()


class EncryptionKey(models.Model):
    """
    Track encryption keys and their rotation
    """
    KEY_STATUS = [
        ('active', 'Active'),
        ('rotated', 'Rotated'),
        ('revoked', 'Revoked'),
    ]
    
    key_id = models.CharField(max_length=100, unique=True, db_index=True)
    key_hash = models.CharField(max_length=64)  # SHA-256 hash of the key
    algorithm = models.CharField(max_length=50, default='fernet')
    
    # Key lifecycle
    status = models.CharField(max_length=20, choices=KEY_STATUS, default='active')
    created_at = models.DateTimeField(default=timezone.now)
    activated_at = models.DateTimeField(null=True, blank=True)
    rotated_at = models.DateTimeField(null=True, blank=True)
    
    # Usage tracking
    encryption_count = models.IntegerField(default=0)
    decryption_count = models.IntegerField(default=0)
    last_used_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    rotation_reason = models.CharField(max_length=200, blank=True)
    
    class Meta:
        db_table = 'core_encryption_key'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['key_id']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"Encryption Key {self.key_id} ({self.status})"
    
    @property
    def is_active(self):
        """Check if key is active"""
        return self.status == 'active'
    
    def rotate(self, reason=None):
        """Mark key as rotated"""
        self.status = 'rotated'
        self.rotated_at = timezone.now()
        if reason:
            self.rotation_reason = reason
        self.save()


class DataProtectionAudit(models.Model):
    """
    Audit trail for data protection operations
    """
    OPERATION_TYPES = [
        ('backup_created', 'Backup Created'),
        ('backup_verified', 'Backup Verified'),
        ('backup_restored', 'Backup Restored'),
        ('data_encrypted', 'Data Encrypted'),
        ('data_decrypted', 'Data Decrypted'),
        ('data_anonymized', 'Data Anonymized'),
        ('data_deleted', 'Data Deleted'),
        ('key_rotated', 'Key Rotated'),
        ('policy_applied', 'Policy Applied'),
    ]
    
    operation_type = models.CharField(max_length=30, choices=OPERATION_TYPES)
    object_type = models.CharField(max_length=100)  # Model name or object type
    object_id = models.CharField(max_length=100, blank=True)
    
    # Operation details
    description = models.TextField()
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)
    
    # Context information
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    
    class Meta:
        db_table = 'core_data_protection_audit'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['operation_type', 'timestamp']),
            models.Index(fields=['object_type', 'object_id']),
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['success', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.operation_type} - {self.object_type} ({self.timestamp})"
    
    @classmethod
    def log_operation(cls, operation_type, object_type, description, 
                     object_id=None, user=None, success=True, error_message=None, 
                     metadata=None, ip_address=None, user_agent=None):
        """
        Convenience method to log data protection operations
        """
        return cls.objects.create(
            operation_type=operation_type,
            object_type=object_type,
            object_id=object_id or '',
            description=description,
            success=success,
            error_message=error_message or '',
            user=user,
            ip_address=ip_address,
            user_agent=user_agent or '',
            metadata=metadata or {}
        )


class DataClassification(models.Model):
    """
    Classify data sensitivity levels
    """
    CLASSIFICATION_LEVELS = [
        ('public', 'Public'),
        ('internal', 'Internal'),
        ('confidential', 'Confidential'),
        ('restricted', 'Restricted'),
    ]
    
    model_name = models.CharField(max_length=100)
    field_name = models.CharField(max_length=100)
    classification_level = models.CharField(max_length=20, choices=CLASSIFICATION_LEVELS)
    
    # Classification rules
    requires_encryption = models.BooleanField(default=False)
    requires_anonymization = models.BooleanField(default=False)
    retention_days = models.IntegerField(null=True, blank=True)
    
    # Metadata
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'core_data_classification'
        unique_together = ['model_name', 'field_name']
        ordering = ['model_name', 'field_name']
        indexes = [
            models.Index(fields=['model_name']),
            models.Index(fields=['classification_level']),
        ]
    
    def __str__(self):
        return f"{self.model_name}.{self.field_name} ({self.classification_level})"
    
    @property
    def is_sensitive(self):
        """Check if data is sensitive (confidential or restricted)"""
        return self.classification_level in ['confidential', 'restricted']