# -*- coding: utf-8 -*-
"""
Admin Audit Trail System for Code Governance

This module provides comprehensive audit trail functionality specifically
for Django admin panel operations with thread-safe implementation.

Key Features:
- Thread-safe audit record creation
- Comprehensive admin operation logging
- Special permission tracking
- Bypass attempt detection
- Real-time security monitoring
- Performance optimized for high-volume admin usage
"""

from django.contrib import admin
from django.contrib.admin.models import LogEntry, ADDITION, CHANGE, DELETION
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.http import HttpRequest
from django.core.exceptions import PermissionDenied
from typing import Optional, Dict, Any, List
import logging
import threading
import json
from datetime import datetime, timedelta

from .models import AuditTrail
from .services.audit_service import AuditService
from .thread_safety import ThreadSafeOperationMixin
from .exceptions import GovernanceError

User = get_user_model()
logger = logging.getLogger('governance.admin_audit')


class AdminAuditTrail(ThreadSafeOperationMixin):
    """
    Thread-safe admin audit trail system for comprehensive operation tracking.
    
    This class provides specialized audit functionality for Django admin
    operations with focus on security and governance compliance.
    """
    
    # Thread-local storage for request context
    _local = threading.local()
    
    # Admin operation types
    ADMIN_OPERATIONS = {
        'view_list': 'Admin list view access',
        'view_detail': 'Admin detail view access',
        'add_attempt': 'Admin add attempt',
        'change_attempt': 'Admin change attempt',
        'delete_attempt': 'Admin delete attempt',
        'bulk_action': 'Admin bulk action',
        'inline_edit': 'Admin inline edit',
        'save_model_bypass': 'Admin save model bypass attempt',
        'delete_model_bypass': 'Admin delete model bypass attempt',
        'permission_check': 'Admin permission check',
        'special_permission_required': 'Special permission required',
        'security_violation': 'Admin security violation'
    }
    
    # Security levels
    SECURITY_LEVELS = {
        'INFO': 'Informational',
        'WARNING': 'Warning',
        'ERROR': 'Error',
        'CRITICAL': 'Critical Security Event'
    }
    
    @classmethod
    def set_request_context(cls, request: HttpRequest):
        """Set the current request context for thread-local storage."""
        cls._local.request = request
        cls._local.user = getattr(request, 'user', None)
        cls._local.session_key = getattr(request.session, 'session_key', None)
        cls._local.ip_address = cls._get_client_ip(request)
        cls._local.user_agent = request.META.get('HTTP_USER_AGENT', '')
        cls._local.path = request.path
        cls._local.method = request.method
    
    @classmethod
    def clear_request_context(cls):
        """Clear the request context from thread-local storage."""
        for attr in ['request', 'user', 'session_key', 'ip_address', 'user_agent', 'path', 'method']:
            if hasattr(cls._local, attr):
                delattr(cls._local, attr)
    
    @classmethod
    @transaction.atomic
    def log_admin_operation(
        cls,
        operation_type: str,
        model_name: str,
        object_id: Optional[str] = None,
        object_repr: Optional[str] = None,
        result: str = 'success',
        security_level: str = 'INFO',
        additional_context: Optional[Dict] = None,
        user: Optional[User] = None
    ) -> Optional[AuditTrail]:
        """
        Log an admin operation with comprehensive context.
        
        Args:
            operation_type: Type of admin operation
            model_name: Name of the model being operated on
            object_id: ID of the specific object
            object_repr: String representation of the object
            result: Result of the operation (success, blocked, error)
            security_level: Security level of the event
            additional_context: Additional context information
            user: User performing the operation (if not in thread-local)
            
        Returns:
            AuditTrail: The created audit record or None if failed
        """
        try:
            with cls._get_thread_lock():
                # Get user from parameter or thread-local storage
                audit_user = user or getattr(cls._local, 'user', None)
                if not audit_user or not audit_user.is_authenticated:
                    logger.warning("Admin operation logged without authenticated user")
                    return None
                
                # Prepare audit context
                audit_context = {
                    'operation_type': operation_type,
                    'operation_description': cls.ADMIN_OPERATIONS.get(operation_type, operation_type),
                    'result': result,
                    'security_level': security_level,
                    'security_description': cls.SECURITY_LEVELS.get(security_level, security_level),
                    'admin_panel': True,
                    'timestamp': timezone.now().isoformat()
                }
                
                # Add request context if available
                if hasattr(cls._local, 'request'):
                    audit_context.update({
                        'ip_address': getattr(cls._local, 'ip_address', None),
                        'user_agent': getattr(cls._local, 'user_agent', None),
                        'session_key': getattr(cls._local, 'session_key', None),
                        'path': getattr(cls._local, 'path', None),
                        'method': getattr(cls._local, 'method', None)
                    })
                
                # Add object information
                if object_id:
                    audit_context['object_id'] = str(object_id)
                if object_repr:
                    audit_context['object_repr'] = object_repr
                
                # Merge additional context
                if additional_context:
                    audit_context.update(additional_context)
                
                # Create audit record using AuditService
                audit_record = AuditService.create_audit_record(
                    model_name=model_name,
                    object_id=object_id,
                    operation=f"admin_{operation_type}",
                    user=audit_user,
                    source_service="AdminPanel",
                    additional_context=audit_context
                )
                
                # Log to application logger based on security level
                log_level = {
                    'INFO': logging.INFO,
                    'WARNING': logging.WARNING,
                    'ERROR': logging.ERROR,
                    'CRITICAL': logging.CRITICAL
                }.get(security_level, logging.INFO)
                
                logger.log(
                    log_level,
                    f"Admin operation: {operation_type} on {model_name} "
                    f"by {audit_user.username} - Result: {result}",
                    extra=audit_context
                )
                
                return audit_record
                
        except Exception as e:
            logger.error(f"Failed to log admin operation: {e}")
            return None
    
    @classmethod
    def log_permission_check(
        cls,
        model_name: str,
        permission_type: str,
        granted: bool,
        required_permission: Optional[str] = None,
        user: Optional[User] = None
    ) -> Optional[AuditTrail]:
        """
        Log admin permission checks for security monitoring.
        
        Args:
            model_name: Name of the model being accessed
            permission_type: Type of permission (add, change, delete, view)
            granted: Whether permission was granted
            required_permission: Specific permission that was required
            user: User being checked
            
        Returns:
            AuditTrail: The created audit record or None if failed
        """
        result = 'granted' if granted else 'denied'
        security_level = 'INFO' if granted else 'WARNING'
        
        context = {
            'permission_type': permission_type,
            'granted': granted,
            'required_permission': required_permission
        }
        
        return cls.log_admin_operation(
            operation_type='permission_check',
            model_name=model_name,
            result=result,
            security_level=security_level,
            additional_context=context,
            user=user
        )
    
    @classmethod
    def log_security_violation(
        cls,
        model_name: str,
        violation_type: str,
        violation_details: Dict,
        object_id: Optional[str] = None,
        user: Optional[User] = None
    ) -> Optional[AuditTrail]:
        """
        Log security violations for immediate attention.
        
        Args:
            model_name: Name of the model involved
            violation_type: Type of security violation
            violation_details: Detailed information about the violation
            object_id: ID of the object involved
            user: User who caused the violation
            
        Returns:
            AuditTrail: The created audit record or None if failed
        """
        context = {
            'violation_type': violation_type,
            'violation_details': violation_details,
            'requires_investigation': True,
            'security_event': True
        }
        
        return cls.log_admin_operation(
            operation_type='security_violation',
            model_name=model_name,
            object_id=object_id,
            result='blocked',
            security_level='CRITICAL',
            additional_context=context,
            user=user
        )
    
    @classmethod
    def log_bypass_attempt(
        cls,
        model_name: str,
        bypass_type: str,
        method_name: str,
        object_id: Optional[str] = None,
        form_data: Optional[Dict] = None,
        user: Optional[User] = None
    ) -> Optional[AuditTrail]:
        """
        Log attempts to bypass admin security controls.
        
        Args:
            model_name: Name of the model being bypassed
            bypass_type: Type of bypass attempt
            method_name: Admin method being bypassed
            object_id: ID of the object involved
            form_data: Form data from the bypass attempt
            user: User attempting the bypass
            
        Returns:
            AuditTrail: The created audit record or None if failed
        """
        context = {
            'bypass_type': bypass_type,
            'method_name': method_name,
            'form_data': cls._sanitize_form_data(form_data),
            'security_event': True,
            'requires_investigation': True
        }
        
        return cls.log_admin_operation(
            operation_type='save_model_bypass' if 'save' in bypass_type else 'delete_model_bypass',
            model_name=model_name,
            object_id=object_id,
            result='blocked',
            security_level='CRITICAL',
            additional_context=context,
            user=user
        )
    
    @classmethod
    def log_bulk_action_attempt(
        cls,
        model_name: str,
        action_name: str,
        queryset_count: int,
        queryset_ids: List[str],
        blocked: bool = False,
        user: Optional[User] = None
    ) -> Optional[AuditTrail]:
        """
        Log bulk action attempts on high-risk models.
        
        Args:
            model_name: Name of the model being acted upon
            action_name: Name of the bulk action
            queryset_count: Number of objects in the queryset
            queryset_ids: List of object IDs
            blocked: Whether the action was blocked
            user: User attempting the action
            
        Returns:
            AuditTrail: The created audit record or None if failed
        """
        context = {
            'action_name': action_name,
            'queryset_count': queryset_count,
            'queryset_ids': queryset_ids[:100],  # Limit to first 100 IDs
            'blocked': blocked
        }
        
        result = 'blocked' if blocked else 'allowed'
        security_level = 'WARNING' if blocked else 'INFO'
        
        return cls.log_admin_operation(
            operation_type='bulk_action',
            model_name=model_name,
            result=result,
            security_level=security_level,
            additional_context=context,
            user=user
        )
    
    @classmethod
    def get_admin_audit_summary(
        cls,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        model_name: Optional[str] = None,
        user: Optional[User] = None
    ) -> Dict[str, Any]:
        """
        Get a summary of admin audit activities.
        
        Args:
            start_date: Start date for the summary
            end_date: End date for the summary
            model_name: Filter by specific model
            user: Filter by specific user
            
        Returns:
            Dict containing audit summary statistics
        """
        try:
            # Default to last 24 hours if no dates provided
            if not start_date:
                start_date = timezone.now() - timedelta(hours=24)
            if not end_date:
                end_date = timezone.now()
            
            # Build query filters
            filters = {
                'timestamp__gte': start_date,
                'timestamp__lte': end_date,
                'source_service': 'AdminPanel'
            }
            
            if model_name:
                filters['model_name'] = model_name
            if user:
                filters['user'] = user
            
            # Get audit records
            audit_records = AuditTrail.objects.filter(**filters)
            
            # Calculate summary statistics
            summary = {
                'total_operations': audit_records.count(),
                'unique_users': audit_records.values('user').distinct().count(),
                'unique_models': audit_records.values('model_name').distinct().count(),
                'operations_by_type': {},
                'operations_by_result': {},
                'security_events': 0,
                'blocked_operations': 0,
                'time_range': {
                    'start': start_date.isoformat(),
                    'end': end_date.isoformat()
                }
            }
            
            # Analyze operations
            for record in audit_records:
                # Count by operation type
                operation = record.operation
                summary['operations_by_type'][operation] = summary['operations_by_type'].get(operation, 0) + 1
                
                # Count by result
                if record.additional_context:
                    result = record.additional_context.get('result', 'unknown')
                    summary['operations_by_result'][result] = summary['operations_by_result'].get(result, 0) + 1
                    
                    # Count security events
                    if record.additional_context.get('security_event'):
                        summary['security_events'] += 1
                    
                    # Count blocked operations
                    if result == 'blocked':
                        summary['blocked_operations'] += 1
            
            return summary
            
        except Exception as e:
            logger.error(f"Failed to generate admin audit summary: {e}")
            return {
                'error': str(e),
                'total_operations': 0
            }
    
    @classmethod
    def get_security_alerts(
        cls,
        hours: int = 24,
        min_severity: str = 'WARNING'
    ) -> List[Dict[str, Any]]:
        """
        Get recent security alerts from admin operations.
        
        Args:
            hours: Number of hours to look back
            min_severity: Minimum security level to include
            
        Returns:
            List of security alert dictionaries
        """
        try:
            start_time = timezone.now() - timedelta(hours=hours)
            
            # Security level hierarchy
            severity_levels = {
                'INFO': 0,
                'WARNING': 1,
                'ERROR': 2,
                'CRITICAL': 3
            }
            min_level = severity_levels.get(min_severity, 1)
            
            # Get audit records with security events
            audit_records = AuditTrail.objects.filter(
                timestamp__gte=start_time,
                source_service='AdminPanel',
                additional_context__security_event=True
            ).order_by('-timestamp')
            
            alerts = []
            for record in audit_records:
                context = record.additional_context or {}
                security_level = context.get('security_level', 'INFO')
                
                if severity_levels.get(security_level, 0) >= min_level:
                    alert = {
                        'id': record.id,
                        'timestamp': record.timestamp.isoformat(),
                        'user': record.user.username if record.user else 'Unknown',
                        'model_name': record.model_name,
                        'operation': record.operation,
                        'security_level': security_level,
                        'result': context.get('result', 'unknown'),
                        'violation_type': context.get('violation_type'),
                        'ip_address': context.get('ip_address'),
                        'requires_investigation': context.get('requires_investigation', False)
                    }
                    alerts.append(alert)
            
            return alerts
            
        except Exception as e:
            logger.error(f"Failed to get security alerts: {e}")
            return []
    
    @classmethod
    def _get_client_ip(cls, request: HttpRequest) -> Optional[str]:
        """Extract client IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    @classmethod
    def _sanitize_form_data(cls, form_data: Optional[Dict]) -> Optional[Dict]:
        """Sanitize form data for safe storage."""
        if not form_data:
            return None
        
        sanitized = {}
        for key, value in form_data.items():
            # Skip sensitive fields
            if key.lower() in ['password', 'token', 'secret', 'key', 'credential']:
                sanitized[key] = '[REDACTED]'
            else:
                sanitized[key] = str(value)[:500]  # Limit length
        
        return sanitized


class AdminAuditMiddleware:
    """
    Middleware to automatically set request context for admin audit trail.
    
    This middleware ensures that all admin requests have proper context
    set for audit logging without requiring manual setup in each view.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Set request context for admin paths
        if request.path.startswith('/admin/'):
            AdminAuditTrail.set_request_context(request)
        
        try:
            response = self.get_response(request)
        finally:
            # Clear request context after processing
            if request.path.startswith('/admin/'):
                AdminAuditTrail.clear_request_context()
        
        return response


# Admin audit decorators for easy integration
def audit_admin_operation(operation_type: str, security_level: str = 'INFO'):
    """
    Decorator to automatically audit admin operations.
    
    Usage:
        @audit_admin_operation('custom_action', 'WARNING')
        def custom_admin_action(self, request, queryset):
            # Action implementation
            pass
    """
    def decorator(func):
        def wrapper(self, request, *args, **kwargs):
            # Set request context
            AdminAuditTrail.set_request_context(request)
            
            try:
                result = func(self, request, *args, **kwargs)
                
                # Log successful operation
                AdminAuditTrail.log_admin_operation(
                    operation_type=operation_type,
                    model_name=f"{self.model._meta.app_label}.{self.model._meta.model_name}",
                    result='success',
                    security_level=security_level,
                    additional_context={
                        'function_name': func.__name__,
                        'admin_class': self.__class__.__name__
                    }
                )
                
                return result
                
            except Exception as e:
                # Log failed operation
                AdminAuditTrail.log_admin_operation(
                    operation_type=f"{operation_type}_failed",
                    model_name=f"{self.model._meta.app_label}.{self.model._meta.model_name}",
                    result='error',
                    security_level='ERROR',
                    additional_context={
                        'function_name': func.__name__,
                        'admin_class': self.__class__.__name__,
                        'error': str(e)
                    }
                )
                
                raise
            finally:
                AdminAuditTrail.clear_request_context()
        
        return wrapper
    return decorator


# Export main classes and functions
__all__ = [
    'AdminAuditTrail',
    'AdminAuditMiddleware',
    'audit_admin_operation'
]