from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import transaction
import threading
import json
import logging

User = get_user_model()
logger = logging.getLogger(__name__)


class IdempotencyRecord(models.Model):
    """
    Ensures operations are not duplicated by tracking unique operation keys.
    Thread-safe implementation with proper database constraints.
    """
    operation_type = models.CharField(
        max_length=100,
        help_text="Type of operation (e.g., 'journal_entry', 'stock_movement')"
    )
    idempotency_key = models.CharField(
        max_length=255,
        help_text="Unique key for this operation"
    )
    result_data = models.JSONField(
        help_text="Serialized result of the operation"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        help_text="When this idempotency record expires"
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_idempotency_records',
        help_text="User who initiated the operation"
    )
    
    class Meta:
        unique_together = ['operation_type', 'idempotency_key']
        indexes = [
            models.Index(fields=['operation_type', 'idempotency_key']),
            models.Index(fields=['expires_at']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = "Idempotency Record"
        verbose_name_plural = "Idempotency Records"
    
    def __str__(self):
        return f"{self.operation_type}:{self.idempotency_key}"
    
    def clean(self):
        """Validate the idempotency record"""
        if self.expires_at and self.expires_at <= timezone.now():
            raise ValidationError("Expiration time must be in the future")
    
    def is_expired(self):
        """Check if this idempotency record has expired"""
        return self.expires_at <= timezone.now()
    
    @classmethod
    def check_and_record(cls, operation_type, idempotency_key, result_data, user, expires_in_hours=24):
        """
        Thread-safe method to check for existing operation or record new one.
        Returns (is_duplicate, record)
        """
        with transaction.atomic():
            try:
                # Try to get existing record
                existing = cls.objects.select_for_update().get(
                    operation_type=operation_type,
                    idempotency_key=idempotency_key
                )
                
                if existing.is_expired():
                    # Record expired, delete it and create new one
                    existing.delete()
                    record = cls.objects.create(
                        operation_type=operation_type,
                        idempotency_key=idempotency_key,
                        result_data=result_data,
                        expires_at=timezone.now() + timezone.timedelta(hours=expires_in_hours),
                        created_by=user
                    )
                    return False, record
                else:
                    # Return existing result
                    return True, existing
                    
            except cls.DoesNotExist:
                # No existing record, create new one
                record = cls.objects.create(
                    operation_type=operation_type,
                    idempotency_key=idempotency_key,
                    result_data=result_data,
                    expires_at=timezone.now() + timezone.timedelta(hours=expires_in_hours),
                    created_by=user
                )
                return False, record


class AuditTrail(models.Model):
    """
    Comprehensive audit trail for all sensitive operations.
    Thread-safe implementation with proper data capture.
    """
    model_name = models.CharField(
        max_length=100,
        help_text="Name of the model being audited"
    )
    object_id = models.PositiveIntegerField(
        help_text="ID of the object being audited"
    )
    operation = models.CharField(
        max_length=50,
        choices=[
            ('CREATE', 'Create'),
            ('UPDATE', 'Update'),
            ('DELETE', 'Delete'),
            ('VIEW', 'View'),
            ('ADMIN_ACCESS', 'Admin Access'),
            ('AUTHORITY_VIOLATION', 'Authority Violation'),
            ('EXCEPTION', 'Exception'),
            ('ENFORCE_IMMUTABILITY', 'Enforce Immutability'),
        ],
        help_text="Type of operation performed"
    )
    user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='governance_audit_trails',
        help_text="User who performed the operation (null for system operations)"
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    before_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Data before the operation"
    )
    after_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Data after the operation"
    )
    source_service = models.CharField(
        max_length=100,
        help_text="Service that initiated the operation"
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the user"
    )
    user_agent = models.TextField(
        null=True,
        blank=True,
        help_text="User agent string"
    )
    additional_context = models.JSONField(
        null=True,
        blank=True,
        help_text="Additional context information"
    )
    resolution_status = models.CharField(
        max_length=20,
        choices=[
            ('ACTIVE', 'Active'),
            ('RESOLVED', 'Resolved'),
            ('IGNORED', 'Ignored'),
            ('AUTO_RESOLVED', 'Auto Resolved'),
        ],
        default='ACTIVE',
        help_text="Resolution status for exceptions and violations"
    )
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the issue was resolved"
    )
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_audit_trails',
        help_text="User who marked this as resolved"
    )
    resolution_notes = models.TextField(
        null=True,
        blank=True,
        help_text="Notes about the resolution"
    )
    
    class Meta:
        indexes = [
            models.Index(fields=['model_name', 'object_id']),
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['operation', 'timestamp']),
            models.Index(fields=['source_service', 'timestamp']),
            models.Index(fields=['timestamp']),
            models.Index(fields=['resolution_status', 'operation']),
        ]
        verbose_name = "Audit Trail"
        verbose_name_plural = "Audit Trails"
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.operation} on {self.model_name}#{self.object_id} by {self.user.username}"
    
    @classmethod
    def log_operation(cls, model_name, object_id, operation, user, source_service, 
                     before_data=None, after_data=None, request=None, **kwargs):
        """
        Thread-safe method to log an operation.
        """
        try:
            # Extract request information if available
            ip_address = None
            user_agent = None
            if request:
                ip_address = cls._get_client_ip(request)
                user_agent = request.META.get('HTTP_USER_AGENT', '')
            
            # Create audit record atomically
            with transaction.atomic():
                audit_record = cls.objects.create(
                    model_name=model_name,
                    object_id=object_id,
                    operation=operation,
                    user=user,
                    source_service=source_service,
                    before_data=before_data,
                    after_data=after_data,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    additional_context=kwargs
                )
                
            logger.info(f"Audit trail created: {audit_record}")
            return audit_record
            
        except Exception as e:
            logger.error(f"Failed to create audit trail: {e}")
            # Don't raise exception to avoid breaking the main operation
            return None
    
    @staticmethod
    def _get_client_ip(request):
        """Extract client IP from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def mark_as_resolved(self, user, notes=""):
        """Mark this audit trail as resolved"""
        self.resolution_status = 'RESOLVED'
        self.resolved_at = timezone.now()
        self.resolved_by = user
        self.resolution_notes = notes
        self.save(update_fields=['resolution_status', 'resolved_at', 'resolved_by', 'resolution_notes'])
    
    def mark_as_ignored(self, user, notes=""):
        """Mark this audit trail as ignored"""
        self.resolution_status = 'IGNORED'
        self.resolved_at = timezone.now()
        self.resolved_by = user
        self.resolution_notes = notes
        self.save(update_fields=['resolution_status', 'resolved_at', 'resolved_by', 'resolution_notes'])
    
    def is_active(self):
        """Check if this issue is still active"""
        return self.resolution_status == 'ACTIVE'


class QuarantineRecord(models.Model):
    """
    Isolates suspicious or corrupted data for investigation.
    """
    model_name = models.CharField(
        max_length=100,
        help_text="Name of the model containing corrupted data"
    )
    object_id = models.PositiveIntegerField(
        help_text="ID of the corrupted object"
    )
    corruption_type = models.CharField(
        max_length=100,
        choices=[
            ('ORPHANED_ENTRY', 'Orphaned Journal Entry'),
            ('NEGATIVE_STOCK', 'Negative Stock'),
            ('UNBALANCED_ENTRY', 'Unbalanced Journal Entry'),
            ('MULTIPLE_ACTIVE_YEAR', 'Multiple Active Academic Years'),
            ('INVALID_SOURCE_LINK', 'Invalid Source Linkage'),
            ('AUTHORITY_VIOLATION', 'Authority Boundary Violation'),
            ('SUSPICIOUS_PATTERN', 'Suspicious Data Pattern'),
        ],
        help_text="Type of corruption detected"
    )
    original_data = models.JSONField(
        help_text="Original data before quarantine"
    )
    quarantine_reason = models.TextField(
        help_text="Detailed reason for quarantine"
    )
    quarantined_at = models.DateTimeField(auto_now_add=True)
    quarantined_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='quarantined_records',
        help_text="User or system that quarantined the data"
    )
    status = models.CharField(
        max_length=50,
        choices=[
            ('QUARANTINED', 'Quarantined'),
            ('UNDER_REVIEW', 'Under Review'),
            ('RESOLVED', 'Resolved'),
            ('PERMANENT', 'Permanent Quarantine'),
        ],
        default='QUARANTINED'
    )
    resolution_notes = models.TextField(
        null=True,
        blank=True,
        help_text="Notes about resolution"
    )
    resolved_at = models.DateTimeField(
        null=True,
        blank=True
    )
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='resolved_quarantine_records'
    )
    
    class Meta:
        indexes = [
            models.Index(fields=['model_name', 'object_id']),
            models.Index(fields=['corruption_type', 'status']),
            models.Index(fields=['quarantined_at']),
            models.Index(fields=['status']),
        ]
        verbose_name = "Quarantine Record"
        verbose_name_plural = "Quarantine Records"
        ordering = ['-quarantined_at']
    
    def __str__(self):
        return f"{self.corruption_type} - {self.model_name}#{self.object_id}"
    
    def resolve(self, user, notes=""):
        """Mark quarantine record as resolved"""
        with transaction.atomic():
            self.status = 'RESOLVED'
            self.resolved_at = timezone.now()
            self.resolved_by = user
            self.resolution_notes = notes
            self.save()
            
            # Log the resolution
            AuditTrail.log_operation(
                model_name='QuarantineRecord',
                object_id=self.id,
                operation='UPDATE',
                user=user,
                source_service='QuarantineSystem',
                before_data={'status': 'QUARANTINED'},
                after_data={'status': 'RESOLVED'},
                resolution_notes=notes
            )


class AuthorityDelegation(models.Model):
    """
    Manages temporary authority delegation between services.
    """
    from_service = models.CharField(
        max_length=100,
        help_text="Service delegating authority"
    )
    to_service = models.CharField(
        max_length=100,
        help_text="Service receiving authority"
    )
    model_name = models.CharField(
        max_length=100,
        help_text="Model for which authority is delegated"
    )
    granted_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        help_text="When this delegation expires"
    )
    granted_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='granted_authority_delegations',
        help_text="User who granted the delegation"
    )
    reason = models.TextField(
        help_text="Reason for delegation"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this delegation is currently active"
    )
    revoked_at = models.DateTimeField(
        null=True,
        blank=True
    )
    revoked_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='revoked_authority_delegations'
    )
    
    class Meta:
        indexes = [
            models.Index(fields=['from_service', 'to_service', 'model_name']),
            models.Index(fields=['expires_at', 'is_active']),
            models.Index(fields=['granted_at']),
        ]
        verbose_name = "Authority Delegation"
        verbose_name_plural = "Authority Delegations"
        ordering = ['-granted_at']
    
    def __str__(self):
        return f"{self.from_service} → {self.to_service} for {self.model_name}"
    
    def clean(self):
        """Validate the delegation"""
        if self.expires_at <= self.granted_at:
            raise ValidationError("Expiration time must be after grant time")
        
        # Check for maximum delegation duration (24 hours)
        max_duration = timezone.timedelta(hours=24)
        if self.expires_at - self.granted_at > max_duration:
            raise ValidationError(f"Delegation duration cannot exceed {max_duration}")
    
    def is_expired(self):
        """Check if this delegation has expired"""
        return timezone.now() > self.expires_at
    
    def is_valid(self):
        """Check if this delegation is currently valid"""
        return self.is_active and not self.is_expired() and not self.revoked_at
    
    def revoke(self, user, reason=""):
        """Revoke this delegation"""
        with transaction.atomic():
            self.is_active = False
            self.revoked_at = timezone.now()
            self.revoked_by = user
            self.save()
            
            # Log the revocation
            AuditTrail.log_operation(
                model_name='AuthorityDelegation',
                object_id=self.id,
                operation='UPDATE',
                user=user,
                source_service='AuthorityService',
                before_data={'is_active': True},
                after_data={'is_active': False},
                revocation_reason=reason
            )
    
    @classmethod
    def check_delegation(cls, from_service, to_service, model_name):
        """
        Check if there's a valid delegation for the given parameters.
        Thread-safe implementation.
        """
        with transaction.atomic():
            try:
                delegation = cls.objects.select_for_update().get(
                    from_service=from_service,
                    to_service=to_service,
                    model_name=model_name,
                    is_active=True,
                    expires_at__gt=timezone.now(),
                    revoked_at__isnull=True
                )
                return delegation.is_valid()
            except cls.DoesNotExist:
                return False
            except cls.MultipleObjectsReturned:
                # Multiple active delegations - this shouldn't happen
                logger.error(f"Multiple active delegations found: {from_service} → {to_service} for {model_name}")
                return False


# Thread-local storage for governance context
_governance_context = threading.local()


class GovernanceContext:
    """
    Thread-safe context manager for governance operations.
    Provides current user, service, and operation context.
    """
    
    @classmethod
    def set_context(cls, user=None, service=None, operation=None, request=None):
        """Set governance context for current thread"""
        _governance_context.user = user
        _governance_context.service = service
        _governance_context.operation = operation
        _governance_context.request = request
    
    @classmethod
    def get_context(cls):
        """Get governance context for current thread"""
        return {
            'user': getattr(_governance_context, 'user', None),
            'service': getattr(_governance_context, 'service', None),
            'operation': getattr(_governance_context, 'operation', None),
            'request': getattr(_governance_context, 'request', None),
        }
    
    @classmethod
    def clear_context(cls):
        """Clear governance context for current thread"""
        for attr in ['user', 'service', 'operation', 'request']:
            if hasattr(_governance_context, attr):
                delattr(_governance_context, attr)
    
    @classmethod
    def get_current_user(cls):
        """Get current user from context"""
        return getattr(_governance_context, 'user', None)
    
    @classmethod
    def get_current_service(cls):
        """Get current service from context"""
        return getattr(_governance_context, 'service', None)



# ==================== Security Models ====================

class SecurityIncident(models.Model):
    """Security incidents tracking"""
    
    INCIDENT_TYPES = [
        ('FAILED_LOGIN', 'محاولة دخول فاشلة'),
        ('UNAUTHORIZED_ACCESS', 'وصول غير مصرح'),
        ('SUSPICIOUS_ACTIVITY', 'نشاط مشبوه'),
        ('BRUTE_FORCE', 'هجوم بروت فورس'),
        ('SQL_INJECTION', 'محاولة SQL Injection'),
        ('XSS_ATTEMPT', 'محاولة XSS'),
        ('CSRF_VIOLATION', 'انتهاك CSRF'),
        ('RATE_LIMIT_EXCEEDED', 'تجاوز حد الطلبات'),
        ('PERMISSION_VIOLATION', 'انتهاك صلاحيات'),
        ('DATA_BREACH_ATTEMPT', 'محاولة اختراق بيانات'),
    ]
    
    SEVERITY_LEVELS = [
        ('LOW', 'منخفض'),
        ('MEDIUM', 'متوسط'),
        ('HIGH', 'عالي'),
        ('CRITICAL', 'حرج'),
    ]
    
    STATUS_CHOICES = [
        ('ACTIVE', 'نشط'),
        ('UNDER_REVIEW', 'قيد المراجعة'),
        ('RESOLVED', 'تم الحل'),
        ('FALSE_POSITIVE', 'إنذار خاطئ'),
        ('IGNORED', 'تم التجاهل'),
    ]
    
    incident_type = models.CharField(max_length=50, choices=INCIDENT_TYPES, verbose_name='نوع الحادث')
    severity = models.CharField(max_length=20, choices=SEVERITY_LEVELS, default='MEDIUM', verbose_name='الخطورة')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE', verbose_name='الحالة')
    
    ip_address = models.GenericIPAddressField(verbose_name='عنوان IP')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, 
                            related_name='security_incidents', verbose_name='المستخدم')
    username_attempted = models.CharField(max_length=150, blank=True, verbose_name='اسم المستخدم المحاول')
    
    description = models.TextField(verbose_name='الوصف')
    user_agent = models.TextField(blank=True, verbose_name='User Agent')
    request_path = models.CharField(max_length=500, blank=True, verbose_name='مسار الطلب')
    request_method = models.CharField(max_length=10, blank=True, verbose_name='نوع الطلب')
    
    detected_at = models.DateTimeField(auto_now_add=True, verbose_name='وقت الاكتشاف')
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name='وقت الحل')
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='resolved_incidents', verbose_name='تم الحل بواسطة')
    resolution_notes = models.TextField(blank=True, verbose_name='ملاحظات الحل')
    
    additional_data = models.JSONField(default=dict, blank=True, verbose_name='بيانات إضافية')
    
    class Meta:
        verbose_name = 'حادث أمني'
        verbose_name_plural = 'الحوادث الأمنية'
        ordering = ['-detected_at']
        indexes = [
            models.Index(fields=['-detected_at']),
            models.Index(fields=['status', '-detected_at']),
            models.Index(fields=['severity', '-detected_at']),
            models.Index(fields=['ip_address', '-detected_at']),
            models.Index(fields=['incident_type', '-detected_at']),
        ]
    
    def __str__(self):
        return f"{self.get_incident_type_display()} - {self.ip_address} - {self.detected_at}"
    
    @classmethod
    def log_incident(cls, incident_type, ip_address, severity='MEDIUM', user=None, 
                    username_attempted='', description='', request=None, **kwargs):
        """Log a security incident"""
        try:
            incident_data = {
                'incident_type': incident_type,
                'ip_address': ip_address,
                'severity': severity,
                'user': user,
                'username_attempted': username_attempted,
                'description': description,
            }
            
            if request:
                incident_data.update({
                    'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                    'request_path': request.path,
                    'request_method': request.method,
                })
            
            incident_data['additional_data'] = kwargs
            
            incident = cls.objects.create(**incident_data)
            logger.warning(f"Security incident logged: {incident}")
            
            # Auto-block IP if critical
            if severity == 'CRITICAL':
                BlockedIP.block_ip(ip_address, f"Auto-blocked due to critical incident: {incident_type}")
            
            return incident
        except Exception as e:
            logger.error(f"Failed to log security incident: {e}")
            return None
    
    def resolve(self, user, notes=''):
        """Mark incident as resolved"""
        self.status = 'RESOLVED'
        self.resolved_at = timezone.now()
        self.resolved_by = user
        self.resolution_notes = notes
        self.save(update_fields=['status', 'resolved_at', 'resolved_by', 'resolution_notes'])


class BlockedIP(models.Model):
    """Blocked IP addresses"""
    
    BLOCK_REASONS = [
        ('BRUTE_FORCE', 'هجوم بروت فورس'),
        ('SUSPICIOUS_ACTIVITY', 'نشاط مشبوه'),
        ('MANUAL_BLOCK', 'حجب يدوي'),
        ('AUTO_BLOCK', 'حجب تلقائي'),
        ('REPEATED_VIOLATIONS', 'انتهاكات متكررة'),
    ]
    
    ip_address = models.GenericIPAddressField(unique=True, verbose_name='عنوان IP')
    reason = models.CharField(max_length=50, choices=BLOCK_REASONS, verbose_name='السبب')
    description = models.TextField(blank=True, verbose_name='الوصف')
    
    blocked_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الحجب')
    blocked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='blocked_ips', verbose_name='تم الحجب بواسطة')
    
    is_active = models.BooleanField(default=True, verbose_name='نشط')
    unblocked_at = models.DateTimeField(null=True, blank=True, verbose_name='تاريخ إلغاء الحجب')
    unblocked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='unblocked_ips', verbose_name='تم إلغاء الحجب بواسطة')
    
    attempts_count = models.PositiveIntegerField(default=0, verbose_name='عدد المحاولات')
    last_attempt_at = models.DateTimeField(null=True, blank=True, verbose_name='آخر محاولة')
    
    class Meta:
        verbose_name = 'عنوان IP محجوب'
        verbose_name_plural = 'عناوين IP المحجوبة'
        ordering = ['-blocked_at']
        indexes = [
            models.Index(fields=['ip_address', 'is_active']),
            models.Index(fields=['-blocked_at']),
        ]
    
    def __str__(self):
        return f"{self.ip_address} - {self.get_reason_display()}"
    
    @classmethod
    def is_blocked(cls, ip_address):
        """Check if an IP is blocked"""
        return cls.objects.filter(ip_address=ip_address, is_active=True).exists()
    
    @classmethod
    def block_ip(cls, ip_address, description='', reason='AUTO_BLOCK', user=None):
        """Block an IP address"""
        try:
            blocked, created = cls.objects.get_or_create(
                ip_address=ip_address,
                defaults={
                    'reason': reason,
                    'description': description,
                    'blocked_by': user,
                    'is_active': True,
                }
            )
            
            if not created and not blocked.is_active:
                blocked.is_active = True
                blocked.blocked_at = timezone.now()
                blocked.blocked_by = user
                blocked.description = description
                blocked.save()
            
            logger.warning(f"IP blocked: {ip_address}")
            return blocked
        except Exception as e:
            logger.error(f"Failed to block IP {ip_address}: {e}")
            return None
    
    def unblock(self, user):
        """Unblock this IP"""
        self.is_active = False
        self.unblocked_at = timezone.now()
        self.unblocked_by = user
        self.save(update_fields=['is_active', 'unblocked_at', 'unblocked_by'])
        logger.info(f"IP unblocked: {self.ip_address} by {user}")
    
    def increment_attempts(self):
        """Increment failed attempts counter"""
        self.attempts_count += 1
        self.last_attempt_at = timezone.now()
        self.save(update_fields=['attempts_count', 'last_attempt_at'])


class ActiveSession(models.Model):
    """Track active user sessions"""
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='active_sessions', 
                            verbose_name='المستخدم')
    session_key = models.CharField(max_length=40, unique=True, verbose_name='مفتاح الجلسة')
    
    ip_address = models.GenericIPAddressField(verbose_name='عنوان IP')
    user_agent = models.TextField(blank=True, verbose_name='User Agent')
    
    login_at = models.DateTimeField(auto_now_add=True, verbose_name='وقت الدخول')
    last_activity = models.DateTimeField(auto_now=True, verbose_name='آخر نشاط')
    
    is_active = models.BooleanField(default=True, verbose_name='نشط')
    terminated_at = models.DateTimeField(null=True, blank=True, verbose_name='وقت الإنهاء')
    terminated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='terminated_sessions', verbose_name='تم الإنهاء بواسطة')
    
    class Meta:
        verbose_name = 'جلسة نشطة'
        verbose_name_plural = 'الجلسات النشطة'
        ordering = ['-login_at']
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['session_key']),
            models.Index(fields=['-last_activity']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.ip_address} - {self.login_at}"
    
    @classmethod
    def create_session(cls, user, session_key, ip_address, user_agent=''):
        """Create or update active session"""
        session, created = cls.objects.update_or_create(
            session_key=session_key,
            defaults={
                'user': user,
                'ip_address': ip_address,
                'user_agent': user_agent,
                'is_active': True,
            }
        )
        return session
    
    def terminate(self, terminated_by=None):
        """Terminate this session"""
        self.is_active = False
        self.terminated_at = timezone.now()
        self.terminated_by = terminated_by
        self.save(update_fields=['is_active', 'terminated_at', 'terminated_by'])
        logger.info(f"Session terminated: {self.user.username} by {terminated_by}")
    
    @classmethod
    def cleanup_expired_sessions(cls, hours=24):
        """Clean up old inactive sessions"""
        cutoff = timezone.now() - timezone.timedelta(hours=hours)
        expired = cls.objects.filter(last_activity__lt=cutoff, is_active=True)
        count = expired.count()
        expired.update(is_active=False, terminated_at=timezone.now())
        logger.info(f"Cleaned up {count} expired sessions")
        return count


class SecurityPolicy(models.Model):
    """Security policies configuration"""
    
    POLICY_TYPES = [
        ('PASSWORD_ENCRYPTION', 'تشفير كلمات المرور'),
        ('SESSION_TIMEOUT', 'انتهاء الجلسة'),
        ('BRUTE_FORCE_PROTECTION', 'حماية من البروت فورس'),
        ('RATE_LIMITING', 'تحديد معدل الطلبات'),
        ('IP_WHITELIST', 'قائمة IP البيضاء'),
        ('TWO_FACTOR_AUTH', 'المصادقة الثنائية'),
        ('PASSWORD_POLICY', 'سياسة كلمات المرور'),
    ]
    
    policy_type = models.CharField(max_length=50, choices=POLICY_TYPES, unique=True, 
                                  verbose_name='نوع السياسة')
    is_enabled = models.BooleanField(default=True, verbose_name='مفعل')
    
    configuration = models.JSONField(default=dict, verbose_name='الإعدادات')
    description = models.TextField(blank=True, verbose_name='الوصف')
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='updated_policies', verbose_name='تم التحديث بواسطة')
    
    class Meta:
        verbose_name = 'سياسة أمنية'
        verbose_name_plural = 'السياسات الأمنية'
        ordering = ['policy_type']
    
    def __str__(self):
        return f"{self.get_policy_type_display()} - {'مفعل' if self.is_enabled else 'معطل'}"
    
    @classmethod
    def get_policy(cls, policy_type):
        """Get a specific policy"""
        try:
            return cls.objects.get(policy_type=policy_type)
        except cls.DoesNotExist:
            return None
    
    @classmethod
    def is_policy_enabled(cls, policy_type):
        """Check if a policy is enabled"""
        policy = cls.get_policy(policy_type)
        return policy.is_enabled if policy else False


class EncryptionKey(models.Model):
    """Encryption keys management"""
    
    KEY_TYPES = [
        ('AES-128', 'AES-128'),
        ('AES-256', 'AES-256'),
        ('RSA-2048', 'RSA-2048'),
        ('RSA-4096', 'RSA-4096'),
    ]
    
    STATUS_CHOICES = [
        ('ACTIVE', 'نشط'),
        ('EXPIRING_SOON', 'قريب الانتهاء'),
        ('EXPIRED', 'منتهي'),
        ('ROTATED', 'تم التدوير'),
    ]
    
    key_name = models.CharField(max_length=100, unique=True, verbose_name='اسم المفتاح')
    key_type = models.CharField(max_length=20, choices=KEY_TYPES, verbose_name='نوع التشفير')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE', verbose_name='الحالة')
    
    key_hash = models.CharField(max_length=255, verbose_name='Hash المفتاح', 
                               help_text='Hash للمفتاح - ليس المفتاح نفسه')
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')
    expires_at = models.DateTimeField(verbose_name='تاريخ الانتهاء')
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, 
                                  related_name='created_encryption_keys', verbose_name='تم الإنشاء بواسطة')
    
    rotated_at = models.DateTimeField(null=True, blank=True, verbose_name='تاريخ التدوير')
    rotated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='rotated_encryption_keys', verbose_name='تم التدوير بواسطة')
    
    usage_count = models.PositiveIntegerField(default=0, verbose_name='عدد مرات الاستخدام')
    last_used_at = models.DateTimeField(null=True, blank=True, verbose_name='آخر استخدام')
    
    notes = models.TextField(blank=True, verbose_name='ملاحظات')
    
    class Meta:
        verbose_name = 'مفتاح تشفير'
        verbose_name_plural = 'مفاتيح التشفير'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['key_name', 'status']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['expires_at']),
        ]
    
    def __str__(self):
        return f"{self.key_name} ({self.key_type}) - {self.get_status_display()}"
    
    def clean(self):
        """Validate the encryption key"""
        if self.expires_at and self.expires_at <= timezone.now():
            raise ValidationError("تاريخ الانتهاء يجب أن يكون في المستقبل")
    
    def is_expired(self):
        """Check if key is expired"""
        return timezone.now() > self.expires_at
    
    def is_expiring_soon(self, days=30):
        """Check if key is expiring soon"""
        return timezone.now() + timezone.timedelta(days=days) > self.expires_at
    
    def update_status(self):
        """Update key status based on expiration"""
        if self.is_expired():
            self.status = 'EXPIRED'
        elif self.is_expiring_soon():
            self.status = 'EXPIRING_SOON'
        else:
            self.status = 'ACTIVE'
        self.save(update_fields=['status'])
    
    def rotate(self, user, new_key_hash):
        """Rotate this encryption key"""
        with transaction.atomic():
            # Mark current key as rotated
            self.status = 'ROTATED'
            self.rotated_at = timezone.now()
            self.rotated_by = user
            self.save()
            
            # Create new key
            new_key = EncryptionKey.objects.create(
                key_name=self.key_name,
                key_type=self.key_type,
                key_hash=new_key_hash,
                created_by=user,
                expires_at=timezone.now() + timezone.timedelta(days=365),
                notes=f"تدوير من المفتاح #{self.id}"
            )
            
            # Log the rotation
            AuditTrail.log_operation(
                model_name='EncryptionKey',
                object_id=self.id,
                operation='UPDATE',
                user=user,
                source_service='EncryptionService',
                before_data={'status': 'ACTIVE'},
                after_data={'status': 'ROTATED'},
                new_key_id=new_key.id
            )
            
            logger.info(f"Encryption key rotated: {self.key_name} by {user}")
            return new_key
    
    def increment_usage(self):
        """Increment usage counter"""
        self.usage_count += 1
        self.last_used_at = timezone.now()
        self.save(update_fields=['usage_count', 'last_used_at'])
    
    @classmethod
    def get_active_key(cls, key_name):
        """Get active key by name"""
        try:
            key = cls.objects.get(key_name=key_name, status='ACTIVE')
            key.increment_usage()
            return key
        except cls.DoesNotExist:
            logger.error(f"Active encryption key not found: {key_name}")
            return None
    
    @classmethod
    def cleanup_old_keys(cls, days=90):
        """Archive old rotated keys"""
        cutoff = timezone.now() - timezone.timedelta(days=days)
        old_keys = cls.objects.filter(status='ROTATED', rotated_at__lt=cutoff)
        count = old_keys.count()
        # In production, you might want to archive instead of delete
        logger.info(f"Found {count} old rotated keys (older than {days} days)")
        return count


class SecurityMetric(models.Model):
    """Security metrics and statistics"""
    
    METRIC_TYPES = [
        ('LOGIN_SUCCESS', 'تسجيل دخول ناجح'),
        ('LOGIN_FAILED', 'محاولة دخول فاشلة'),
        ('ACCOUNT_LOCKED', 'حساب مقفل'),
        ('SESSION_CREATED', 'جلسة جديدة'),
        ('SESSION_TERMINATED', 'جلسة منتهية'),
        ('SECURITY_SCAN', 'فحص أمني'),
        ('KEY_ROTATION', 'تدوير مفتاح'),
        ('POLICY_UPDATE', 'تحديث سياسة'),
        ('INCIDENT_DETECTED', 'حادث أمني'),
        ('INCIDENT_RESOLVED', 'حل حادث'),
    ]
    
    metric_type = models.CharField(max_length=50, choices=METRIC_TYPES, verbose_name='نوع المقياس')
    value = models.IntegerField(default=1, verbose_name='القيمة')
    
    recorded_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ التسجيل', db_index=True)
    date = models.DateField(auto_now_add=True, verbose_name='التاريخ', db_index=True)
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                            related_name='security_metrics', verbose_name='المستخدم')
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name='عنوان IP')
    
    metadata = models.JSONField(default=dict, blank=True, verbose_name='بيانات إضافية')
    
    class Meta:
        verbose_name = 'مقياس أمني'
        verbose_name_plural = 'المقاييس الأمنية'
        ordering = ['-recorded_at']
        indexes = [
            models.Index(fields=['metric_type', '-recorded_at']),
            models.Index(fields=['date', 'metric_type']),
            models.Index(fields=['-recorded_at']),
        ]
    
    def __str__(self):
        return f"{self.get_metric_type_display()} - {self.recorded_at}"
    
    @classmethod
    def record(cls, metric_type, value=1, user=None, ip_address=None, **metadata):
        """Record a security metric"""
        try:
            metric = cls.objects.create(
                metric_type=metric_type,
                value=value,
                user=user,
                ip_address=ip_address,
                metadata=metadata
            )
            return metric
        except Exception as e:
            logger.error(f"Failed to record security metric: {e}")
            return None
    
    @classmethod
    def get_today_count(cls, metric_type):
        """Get count for today"""
        today = timezone.now().date()
        return cls.objects.filter(
            metric_type=metric_type,
            date=today
        ).aggregate(total=models.Sum('value'))['total'] or 0
    
    @classmethod
    def get_period_count(cls, metric_type, days=7):
        """Get count for a period"""
        start_date = timezone.now().date() - timezone.timedelta(days=days)
        return cls.objects.filter(
            metric_type=metric_type,
            date__gte=start_date
        ).aggregate(total=models.Sum('value'))['total'] or 0
    
    @classmethod
    def get_daily_stats(cls, metric_type, days=30):
        """Get daily statistics for a metric"""
        start_date = timezone.now().date() - timezone.timedelta(days=days)
        return cls.objects.filter(
            metric_type=metric_type,
            date__gte=start_date
        ).values('date').annotate(
            total=models.Sum('value')
        ).order_by('date')
    
    @classmethod
    def cleanup_old_metrics(cls, days=90):
        """Clean up old metrics"""
        cutoff = timezone.now().date() - timezone.timedelta(days=days)
        old_metrics = cls.objects.filter(date__lt=cutoff)
        count = old_metrics.count()
        old_metrics.delete()
        logger.info(f"Cleaned up {count} old security metrics")
        return count


# ==================== Signal Monitoring Models ====================

class SignalRegistry(models.Model):
    """
    سجل جميع الإشارات المسجلة في النظام
    Registry of all signals in the system
    """
    
    SIGNAL_TYPES = [
        ('post_save', 'Post Save'),
        ('pre_save', 'Pre Save'),
        ('post_delete', 'Post Delete'),
        ('pre_delete', 'Pre Delete'),
        ('m2m_changed', 'M2M Changed'),
        ('custom', 'Custom Signal'),
    ]
    
    PRIORITY_LEVELS = [
        ('LOW', 'منخفض'),
        ('MEDIUM', 'متوسط'),
        ('HIGH', 'عالي'),
        ('CRITICAL', 'حرج'),
    ]
    
    STATUS_CHOICES = [
        ('ACTIVE', 'نشط'),
        ('DISABLED', 'معطل'),
        ('PAUSED', 'متوقف مؤقتاً'),
        ('ERROR', 'خطأ'),
    ]
    
    signal_name = models.CharField(max_length=200, unique=True, verbose_name='اسم الإشارة')
    signal_type = models.CharField(max_length=20, choices=SIGNAL_TYPES, verbose_name='نوع الإشارة')
    module_name = models.CharField(max_length=100, verbose_name='اسم الموديول')
    model_name = models.CharField(max_length=100, verbose_name='اسم الموديل')
    priority = models.CharField(max_length=20, choices=PRIORITY_LEVELS, default='MEDIUM', verbose_name='الأولوية')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE', verbose_name='الحالة')
    is_critical = models.BooleanField(default=False, verbose_name='حرج')
    description = models.TextField(blank=True, verbose_name='الوصف')
    handler_function = models.CharField(max_length=200, verbose_name='دالة المعالج')
    registered_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ التسجيل')
    last_updated = models.DateTimeField(auto_now=True, verbose_name='آخر تحديث')
    max_execution_time_ms = models.IntegerField(default=1000, verbose_name='الحد الأقصى لوقت التنفيذ (ms)')
    
    class Meta:
        verbose_name = 'سجل إشارة'
        verbose_name_plural = 'سجل الإشارات'
        ordering = ['module_name', 'signal_name']
        indexes = [
            models.Index(fields=['signal_name']),
            models.Index(fields=['module_name', 'status']),
            models.Index(fields=['status', 'is_critical']),
        ]
    
    def __str__(self):
        return f"{self.signal_name} ({self.module_name})"
    
    def get_success_rate(self, days=1):
        """حساب معدل النجاح"""
        from datetime import timedelta
        start_time = timezone.now() - timedelta(days=days)
        executions = self.executions.filter(executed_at__gte=start_time)
        total = executions.count()
        if total == 0:
            return 100.0
        successful = executions.filter(status='SUCCESS').count()
        return round((successful / total) * 100, 1)
    
    def get_avg_execution_time(self, days=1):
        """حساب متوسط وقت التنفيذ"""
        from datetime import timedelta
        from django.db.models import Avg
        start_time = timezone.now() - timedelta(days=days)
        avg = self.executions.filter(
            executed_at__gte=start_time,
            status='SUCCESS'
        ).aggregate(avg_time=Avg('execution_time_ms'))
        return round(avg['avg_time'] or 0, 2)
    
    def get_execution_count(self, days=1):
        """عدد مرات التنفيذ"""
        from datetime import timedelta
        start_time = timezone.now() - timedelta(days=days)
        return self.executions.filter(executed_at__gte=start_time).count()
    
    def get_last_execution(self):
        """آخر تنفيذ"""
        return self.executions.order_by('-executed_at').first()
    
    def get_performance_status(self):
        """حالة الأداء"""
        avg_time = self.get_avg_execution_time()
        success_rate = self.get_success_rate()
        if success_rate < 90:
            return 'danger'
        elif avg_time > self.max_execution_time_ms:
            return 'warning'
        elif success_rate >= 98 and avg_time < self.max_execution_time_ms * 0.5:
            return 'excellent'
        else:
            return 'good'


class SignalExecution(models.Model):
    """سجل تنفيذ الإشارات"""
    
    STATUS_CHOICES = [
        ('SUCCESS', 'نجح'),
        ('FAILED', 'فشل'),
        ('TIMEOUT', 'انتهت المهلة'),
        ('SKIPPED', 'تم التخطي'),
    ]
    
    signal = models.ForeignKey(SignalRegistry, on_delete=models.CASCADE, related_name='executions', verbose_name='الإشارة')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, verbose_name='الحالة')
    executed_at = models.DateTimeField(auto_now_add=True, verbose_name='وقت التنفيذ', db_index=True)
    execution_time_ms = models.IntegerField(verbose_name='وقت التنفيذ (ms)')
    instance_id = models.IntegerField(null=True, blank=True, verbose_name='معرف الكائن')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='signal_executions', verbose_name='المستخدم')
    error_message = models.TextField(blank=True, verbose_name='رسالة الخطأ')
    error_traceback = models.TextField(blank=True, verbose_name='تتبع الخطأ')
    metadata = models.JSONField(default=dict, blank=True, verbose_name='بيانات إضافية')
    
    class Meta:
        verbose_name = 'تنفيذ إشارة'
        verbose_name_plural = 'تنفيذات الإشارات'
        ordering = ['-executed_at']
        indexes = [
            models.Index(fields=['signal', '-executed_at']),
            models.Index(fields=['status', '-executed_at']),
            models.Index(fields=['-executed_at']),
            models.Index(fields=['signal', 'status']),
        ]
    
    def __str__(self):
        return f"{self.signal.signal_name} - {self.status} - {self.executed_at}"
    
    @classmethod
    def log_execution(cls, signal_name, status, execution_time_ms, instance_id=None, user=None, error_message='', error_traceback='', **metadata):
        """تسجيل تنفيذ إشارة"""
        from datetime import timedelta
        try:
            signal_registry, _ = SignalRegistry.objects.get_or_create(
                signal_name=signal_name,
                defaults={'signal_type': 'custom', 'module_name': 'unknown', 'model_name': 'unknown', 'handler_function': signal_name}
            )
            execution = cls.objects.create(
                signal=signal_registry, status=status, execution_time_ms=execution_time_ms,
                instance_id=instance_id, user=user, error_message=error_message,
                error_traceback=error_traceback, metadata=metadata
            )
            if status == 'FAILED' and signal_registry.status == 'ACTIVE':
                recent_failures = cls.objects.filter(
                    signal=signal_registry, status='FAILED',
                    executed_at__gte=timezone.now() - timedelta(minutes=5)
                ).count()
                if recent_failures >= 3:
                    signal_registry.status = 'ERROR'
                    signal_registry.save(update_fields=['status'])
                    logger.error(f"Signal {signal_name} marked as ERROR due to multiple failures")
            return execution
        except Exception as e:
            logger.error(f"Failed to log signal execution: {e}")
            return None
    
    @classmethod
    def get_statistics(cls, days=1):
        """إحصائيات التنفيذ"""
        from datetime import timedelta
        from django.db.models import Avg
        start_time = timezone.now() - timedelta(days=days)
        executions = cls.objects.filter(executed_at__gte=start_time)
        total = executions.count()
        successful = executions.filter(status='SUCCESS').count()
        failed = executions.filter(status='FAILED').count()
        return {
            'total': total, 'successful': successful, 'failed': failed,
            'success_rate': round((successful / total * 100) if total > 0 else 100, 1),
            'avg_time': executions.aggregate(avg=Avg('execution_time_ms'))['avg'] or 0,
        }


class SignalPerformanceAlert(models.Model):
    """تنبيهات أداء الإشارات"""
    
    ALERT_TYPES = [
        ('SLOW_EXECUTION', 'تنفيذ بطيء'),
        ('HIGH_FAILURE_RATE', 'معدل فشل عالي'),
        ('TIMEOUT', 'انتهاء المهلة'),
        ('REPEATED_ERRORS', 'أخطاء متكررة'),
        ('CRITICAL_FAILURE', 'فشل حرج'),
    ]
    
    SEVERITY_LEVELS = [
        ('INFO', 'معلومة'),
        ('WARNING', 'تحذير'),
        ('ERROR', 'خطأ'),
        ('CRITICAL', 'حرج'),
    ]
    
    signal = models.ForeignKey(SignalRegistry, on_delete=models.CASCADE, related_name='alerts', verbose_name='الإشارة')
    alert_type = models.CharField(max_length=50, choices=ALERT_TYPES, verbose_name='نوع التنبيه')
    severity = models.CharField(max_length=20, choices=SEVERITY_LEVELS, verbose_name='الخطورة')
    message = models.TextField(verbose_name='الرسالة')
    details = models.JSONField(default=dict, blank=True, verbose_name='التفاصيل')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')
    is_resolved = models.BooleanField(default=False, verbose_name='تم الحل')
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name='تاريخ الحل')
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_signal_alerts', verbose_name='تم الحل بواسطة')
    
    class Meta:
        verbose_name = 'تنبيه أداء إشارة'
        verbose_name_plural = 'تنبيهات أداء الإشارات'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['signal', '-created_at']),
            models.Index(fields=['is_resolved', '-created_at']),
            models.Index(fields=['severity', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.signal.signal_name} - {self.get_alert_type_display()}"
    
    def resolve(self, user):
        """حل التنبيه"""
        self.is_resolved = True
        self.resolved_at = timezone.now()
        self.resolved_by = user
        self.save(update_fields=['is_resolved', 'resolved_at', 'resolved_by'])
    
    @classmethod
    def create_alert(cls, signal, alert_type, severity, message, **details):
        """إنشاء تنبيه جديد"""
        from datetime import timedelta
        try:
            recent_alert = cls.objects.filter(
                signal=signal, alert_type=alert_type, is_resolved=False,
                created_at__gte=timezone.now() - timedelta(hours=1)
            ).first()
            if recent_alert:
                recent_alert.details = details
                recent_alert.save(update_fields=['details'])
                return recent_alert
            alert = cls.objects.create(signal=signal, alert_type=alert_type, severity=severity, message=message, details=details)
            logger.warning(f"Signal alert created: {alert}")
            return alert
        except Exception as e:
            logger.error(f"Failed to create signal alert: {e}")
            return None


# ==================== Reports Builder Models ====================

class SavedReport(models.Model):
    """
    التقارير المحفوظة
    Saved custom reports
    """
    
    REPORT_TYPES = [
        ('table', 'جدول'),
        ('bar', 'رسم بياني عمودي'),
        ('pie', 'رسم دائري'),
        ('line', 'رسم خطي'),
        ('summary', 'ملخص إحصائي'),
    ]
    
    DATA_SOURCES = [
        ('customers', 'العملاء'),
        ('sales', 'فواتير المبيعات'),
        ('purchases', 'فواتير المشتريات'),
        ('payments', 'المدفوعات'),
        ('employees', 'الموظفين'),
        ('journal_entries', 'القيود اليومية'),
        ('products', 'المنتجات'),
        ('suppliers', 'الموردين'),
    ]
    
    STATUS_CHOICES = [
        ('ACTIVE', 'نشط'),
        ('INACTIVE', 'غير نشط'),
        ('ARCHIVED', 'مؤرشف'),
    ]
    
    name = models.CharField(max_length=200, verbose_name='اسم التقرير')
    description = models.TextField(blank=True, verbose_name='الوصف')
    report_type = models.CharField(max_length=20, choices=REPORT_TYPES, verbose_name='نوع التقرير')
    data_source = models.CharField(max_length=50, choices=DATA_SOURCES, verbose_name='مصدر البيانات')
    
    # Report configuration
    selected_fields = models.JSONField(default=list, verbose_name='الحقول المختارة')
    filters = models.JSONField(default=dict, verbose_name='المرشحات')
    group_by = models.CharField(max_length=50, blank=True, verbose_name='التجميع حسب')
    sort_by = models.CharField(max_length=50, blank=True, verbose_name='الترتيب حسب')
    sort_order = models.CharField(max_length=10, default='asc', choices=[('asc', 'تصاعدي'), ('desc', 'تنازلي')], verbose_name='اتجاه الترتيب')
    
    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_reports', verbose_name='تم الإنشاء بواسطة')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')
    last_run_at = models.DateTimeField(null=True, blank=True, verbose_name='آخر تشغيل')
    run_count = models.PositiveIntegerField(default=0, verbose_name='عدد مرات التشغيل')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE', verbose_name='الحالة')
    is_public = models.BooleanField(default=False, verbose_name='عام')
    
    class Meta:
        verbose_name = 'تقرير محفوظ'
        verbose_name_plural = 'التقارير المحفوظة'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_by', '-created_at']),
            models.Index(fields=['data_source', 'status']),
            models.Index(fields=['status', '-last_run_at']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.get_report_type_display()})"
    
    def increment_run_count(self):
        """زيادة عداد التشغيل"""
        self.run_count += 1
        self.last_run_at = timezone.now()
        self.save(update_fields=['run_count', 'last_run_at'])
    
    def can_user_access(self, user):
        """التحقق من صلاحية الوصول"""
        return self.is_public or self.created_by == user or user.is_superuser


class ReportSchedule(models.Model):
    """
    جدولة التقارير
    Report scheduling
    """
    
    FREQUENCY_CHOICES = [
        ('daily', 'يومياً'),
        ('weekly', 'أسبوعياً'),
        ('monthly', 'شهرياً'),
        ('quarterly', 'ربع سنوي'),
    ]
    
    STATUS_CHOICES = [
        ('ACTIVE', 'نشط'),
        ('PAUSED', 'متوقف مؤقتاً'),
        ('DISABLED', 'معطل'),
    ]
    
    report = models.ForeignKey(SavedReport, on_delete=models.CASCADE, related_name='schedules', verbose_name='التقرير')
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, verbose_name='التكرار')
    schedule_time = models.TimeField(verbose_name='وقت التشغيل')
    
    # For weekly: 0=Monday, 6=Sunday
    day_of_week = models.IntegerField(null=True, blank=True, verbose_name='يوم الأسبوع', 
                                     help_text='0=الاثنين, 6=الأحد')
    # For monthly: 1-31
    day_of_month = models.IntegerField(null=True, blank=True, verbose_name='يوم الشهر',
                                      help_text='1-31')
    
    # Email recipients
    email_recipients = models.TextField(verbose_name='المستلمون', 
                                       help_text='عناوين البريد الإلكتروني مفصولة بفواصل')
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE', verbose_name='الحالة')
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_schedules', verbose_name='تم الإنشاء بواسطة')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')
    
    last_run_at = models.DateTimeField(null=True, blank=True, verbose_name='آخر تشغيل')
    next_run_at = models.DateTimeField(null=True, blank=True, verbose_name='التشغيل التالي')
    
    class Meta:
        verbose_name = 'جدولة تقرير'
        verbose_name_plural = 'جدولة التقارير'
        ordering = ['next_run_at']
        indexes = [
            models.Index(fields=['status', 'next_run_at']),
            models.Index(fields=['report', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.report.name} - {self.get_frequency_display()}"
    
    def calculate_next_run(self):
        """حساب موعد التشغيل التالي"""
        from datetime import datetime, timedelta
        
        now = timezone.now()
        today = now.date()
        schedule_datetime = datetime.combine(today, self.schedule_time)
        schedule_datetime = timezone.make_aware(schedule_datetime)
        
        if self.frequency == 'daily':
            if schedule_datetime <= now:
                schedule_datetime += timedelta(days=1)
        
        elif self.frequency == 'weekly':
            days_ahead = self.day_of_week - today.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            schedule_datetime += timedelta(days=days_ahead)
            if schedule_datetime <= now:
                schedule_datetime += timedelta(weeks=1)
        
        elif self.frequency == 'monthly':
            if self.day_of_month:
                schedule_datetime = schedule_datetime.replace(day=min(self.day_of_month, 28))
                if schedule_datetime <= now:
                    # Move to next month
                    if schedule_datetime.month == 12:
                        schedule_datetime = schedule_datetime.replace(year=schedule_datetime.year + 1, month=1)
                    else:
                        schedule_datetime = schedule_datetime.replace(month=schedule_datetime.month + 1)
        
        elif self.frequency == 'quarterly':
            # Every 3 months
            if schedule_datetime <= now:
                months_to_add = 3
                new_month = schedule_datetime.month + months_to_add
                new_year = schedule_datetime.year
                while new_month > 12:
                    new_month -= 12
                    new_year += 1
                schedule_datetime = schedule_datetime.replace(year=new_year, month=new_month)
        
        self.next_run_at = schedule_datetime
        self.save(update_fields=['next_run_at'])
        return schedule_datetime
    
    def mark_as_run(self):
        """تسجيل التشغيل"""
        self.last_run_at = timezone.now()
        self.calculate_next_run()
    
    def pause(self):
        """إيقاف مؤقت"""
        self.status = 'PAUSED'
        self.save(update_fields=['status'])
    
    def resume(self):
        """استئناف"""
        self.status = 'ACTIVE'
        self.calculate_next_run()


class ReportExecution(models.Model):
    """
    سجل تنفيذ التقارير
    Report execution log
    """
    
    STATUS_CHOICES = [
        ('PENDING', 'قيد الانتظار'),
        ('RUNNING', 'قيد التشغيل'),
        ('SUCCESS', 'نجح'),
        ('FAILED', 'فشل'),
    ]
    
    report = models.ForeignKey(SavedReport, on_delete=models.CASCADE, related_name='executions', verbose_name='التقرير')
    schedule = models.ForeignKey(ReportSchedule, on_delete=models.SET_NULL, null=True, blank=True, 
                                related_name='executions', verbose_name='الجدولة')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', verbose_name='الحالة')
    started_at = models.DateTimeField(auto_now_add=True, verbose_name='وقت البدء')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='وقت الانتهاء')
    execution_time_ms = models.IntegerField(null=True, blank=True, verbose_name='وقت التنفيذ (ms)')
    
    triggered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='triggered_executions', verbose_name='تم التشغيل بواسطة')
    
    # Results
    rows_count = models.IntegerField(null=True, blank=True, verbose_name='عدد الصفوف')
    result_data = models.JSONField(null=True, blank=True, verbose_name='بيانات النتيجة')
    
    # Error handling
    error_message = models.TextField(blank=True, verbose_name='رسالة الخطأ')
    error_traceback = models.TextField(blank=True, verbose_name='تتبع الخطأ')
    
    class Meta:
        verbose_name = 'تنفيذ تقرير'
        verbose_name_plural = 'تنفيذات التقارير'
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['report', '-started_at']),
            models.Index(fields=['status', '-started_at']),
            models.Index(fields=['-started_at']),
        ]
    
    def __str__(self):
        return f"{self.report.name} - {self.status} - {self.started_at}"
    
    def mark_as_success(self, rows_count, result_data=None):
        """تسجيل النجاح"""
        self.status = 'SUCCESS'
        self.completed_at = timezone.now()
        self.execution_time_ms = int((self.completed_at - self.started_at).total_seconds() * 1000)
        self.rows_count = rows_count
        self.result_data = result_data
        self.save()
    
    def mark_as_failed(self, error_message, error_traceback=''):
        """تسجيل الفشل"""
        self.status = 'FAILED'
        self.completed_at = timezone.now()
        self.execution_time_ms = int((self.completed_at - self.started_at).total_seconds() * 1000)
        self.error_message = error_message
        self.error_traceback = error_traceback
        self.save()
    
    @classmethod
    def get_statistics(cls, days=7):
        """إحصائيات التنفيذ"""
        from datetime import timedelta
        from django.db.models import Avg, Count
        
        start_date = timezone.now() - timedelta(days=days)
        executions = cls.objects.filter(started_at__gte=start_date)
        
        total = executions.count()
        successful = executions.filter(status='SUCCESS').count()
        failed = executions.filter(status='FAILED').count()
        
        return {
            'total': total,
            'successful': successful,
            'failed': failed,
            'success_rate': round((successful / total * 100) if total > 0 else 100, 1),
            'avg_time': executions.filter(status='SUCCESS').aggregate(
                avg=Avg('execution_time_ms'))['avg'] or 0,
        }
