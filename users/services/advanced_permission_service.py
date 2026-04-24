# -*- coding: utf-8 -*-
"""
Advanced Permission Service (Simplified)

This service focuses on practical features that are actually needed:
- Simple role assignment with audit
- Basic security monitoring without over-engineering
- Only essential governance features
"""

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from typing import Dict, Any, Optional, List
import logging

from governance.services.audit_service import AuditService
from .permission_service import PermissionService

logger = logging.getLogger('users.advanced_permission_service')


class AdvancedPermissionService:
    """
    Simplified advanced permission service.
    
    Features only what's actually useful:
    - Safe role assignment with audit
    - Basic security monitoring
    - Simple metrics without complexity
    """
    
    @classmethod
    @transaction.atomic
    def safe_role_assignment(
        cls, 
        user, 
        role, 
        assigned_by, 
        reason: str = None
    ) -> Dict[str, Any]:
        """
        Simple role assignment with audit logging.
        Removed complex idempotency - Django transactions are enough.
        """
        try:
            # Check if user already has this role
            if user.role == role:
                return {
                    'success': True,
                    'already_assigned': True,
                    'message': f'المستخدم لديه الدور {role.display_name} بالفعل'
                }
            
            # Use the existing PermissionService method
            result = PermissionService.assign_role_to_user(user, role, assigned_by)
            
            # Add reason to audit if provided
            if reason:
                AuditService.create_audit_record(
                    model_name='Role',
                    object_id=role.id,
                    operation='ROLE_ASSIGNMENT_REASON',
                    user=assigned_by,
                    source_service='AdvancedPermissionService',
                    additional_context={
                        'target_user_id': user.id,
                        'reason': reason
                    }
                )
            
            return result
            
        except Exception as e:
            logger.error(f"Failed role assignment: {e}")
            raise
    
    @classmethod
    def log_security_event(
        cls,
        user,
        event_type: str,
        details: Dict[str, Any],
        severity: str = 'MEDIUM'
    ):
        """
        Simple security event logging without complex quarantine.
        Just log to audit trail - simpler and more practical.
        """
        AuditService.create_audit_record(
            model_name='SecurityEvent',
            object_id=user.id if user else None,
            operation='SECURITY_EVENT',
            user=user,
            source_service='AdvancedPermissionService',
            additional_context={
                'event_type': event_type,
                'severity': severity,
                'details': details,
                'requires_review': severity in ['HIGH', 'CRITICAL']
            }
        )
        
        if severity in ['HIGH', 'CRITICAL']:
            logger.warning(
                f"Security event: {event_type} by {user.username if user else 'Anonymous'}"
            )
    
    @classmethod
    def get_basic_security_metrics(cls) -> Dict[str, Any]:
        """
        Simple security metrics without complex quarantine/delegation stats.
        Focus on what's actually useful.
        """
        try:
            from django.contrib.auth import get_user_model
            from users.models import Role
            from governance.models import AuditTrail
            
            User = get_user_model()
            
            # Basic user statistics
            total_users = User.objects.filter(is_active=True).count()
            users_with_roles = User.objects.filter(role__isnull=False, is_active=True).count()
            
            # Recent activity (last 7 days)
            week_ago = timezone.now() - timezone.timedelta(days=7)
            recent_logins = User.objects.filter(last_login__gte=week_ago).count()
            
            # Recent security events (last 24 hours)
            day_ago = timezone.now() - timezone.timedelta(days=1)
            recent_security_events = AuditTrail.objects.filter(
                timestamp__gte=day_ago,
                operation='SECURITY_EVENT'
            ).count()
            
            # Failed permission checks
            failed_permission_checks = AuditTrail.objects.filter(
                timestamp__gte=day_ago,
                operation='PERMISSION_CHECK',
                additional_context__result=False
            ).count()
            
            return {
                'users': {
                    'total': total_users,
                    'with_roles': users_with_roles,
                    'recent_logins': recent_logins,
                    'role_coverage': round((users_with_roles / total_users * 100) if total_users > 0 else 0, 1)
                },
                'security': {
                    'recent_events': recent_security_events,
                    'failed_permission_checks': failed_permission_checks,
                    'security_score': cls._calculate_simple_security_score(
                        total_users, users_with_roles, failed_permission_checks
                    )
                },
                'timestamp': timezone.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting security metrics: {e}")
            return {}
    
    @staticmethod
    def _calculate_simple_security_score(total_users, users_with_roles, failed_checks):
        """Calculate simple security score (0-100)."""
        score = 100
        
        # Deduct for users without roles
        if total_users > 0:
            role_coverage = users_with_roles / total_users
            if role_coverage < 0.8:
                score -= 20
        
        # Deduct for failed permission checks
        if failed_checks > 10:
            score -= 15
        elif failed_checks > 5:
            score -= 10
        
        return max(0, score)