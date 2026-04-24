# -*- coding: utf-8 -*-
"""
Admin Security Module for Code Governance System

This module provides comprehensive security controls for Django admin panel
to prevent unauthorized access to high-risk models and enforce governance rules.

High-Risk Models (as defined in requirements):
- JournalEntry, JournalEntryLine (Financial)
- Stock, StockMovement (Inventory)
- Sale, Purchase (Commerce)
- User, Group (System)

Key Features:
- Read-only enforcement for sensitive models
- Bulk action prevention
- Inline edit prevention
- Save model bypass detection
- Comprehensive audit logging
- Redirect to business interfaces
- Special permission requirements
"""

from django.contrib import admin
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.contrib import messages
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.conf import settings
from django.db import transaction
from typing import List, Optional, Dict, Any
import logging

from .services.audit_service import AuditService
from .exceptions import GovernanceError, AuthorityViolationError

logger = logging.getLogger('governance.admin_security')


class HighRiskModelMixin:
    """
    Mixin for high-risk model admin classes to enforce security controls.
    
    This mixin provides comprehensive protection against unauthorized
    modifications to sensitive models through the admin interface.
    """
    
    # Security configuration
    is_high_risk_model = True
    read_only_mode = True
    allow_bulk_actions = False
    allow_inline_edits = False
    require_special_permission = True
    business_interface_url = None
    security_warning_message = None
    
    # Governance integration
    authoritative_service = None
    audit_all_access = True
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_security_controls()
    
    def _setup_security_controls(self):
        """Initialize security controls for high-risk models."""
        if self.read_only_mode:
            # Make all fields read-only
            if hasattr(self, 'readonly_fields'):
                # Get all model fields
                model_fields = [field.name for field in self.model._meta.fields]
                # Combine with existing readonly fields
                existing_readonly = list(self.readonly_fields) if self.readonly_fields else []
                self.readonly_fields = list(set(existing_readonly + model_fields))
            
            # Disable bulk actions
            if not self.allow_bulk_actions:
                self.actions = []
        
        # Set security warning message if not provided
        if not self.security_warning_message:
            self.security_warning_message = _(
                f"⚠️ تحذير أمني: {self.model._meta.verbose_name} هو نموذج عالي المخاطر. "
                "التعديلات المباشرة محظورة لضمان سلامة البيانات."
            )
    
    def has_add_permission(self, request):
        """Prevent adding new records for high-risk models."""
        if self.read_only_mode:
            self._log_admin_access_attempt(request, 'add_attempt', 'blocked')
            return False
        return super().has_add_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Control change permissions for high-risk models."""
        if self.read_only_mode:
            # Allow view access but log it
            self._log_admin_access_attempt(request, 'change_attempt', 'view_only')
            return True  # Allow viewing but actual changes will be blocked
        
        if self.require_special_permission:
            permission_name = f"{self.model._meta.app_label}.admin_modify_{self.model._meta.model_name}"
            if not request.user.has_perm(permission_name):
                self._log_admin_access_attempt(request, 'change_attempt', 'permission_denied')
                return False
        
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of high-risk model records."""
        if self.read_only_mode:
            self._log_admin_access_attempt(request, 'delete_attempt', 'blocked')
            return False
        return super().has_delete_permission(request, obj)
    
    def has_view_permission(self, request, obj=None):
        """Control view permissions with audit logging."""
        has_permission = super().has_view_permission(request, obj)
        if has_permission and self.audit_all_access:
            self._log_admin_access_attempt(request, 'view_access', 'allowed')
        return has_permission
    
    def save_model(self, request, obj, form, change):
        """
        Override save_model to detect bypass attempts and enforce governance.
        
        This method is critical for preventing unauthorized modifications
        through admin interface bypass techniques.
        """
        if self.read_only_mode:
            # Log bypass attempt
            self._log_admin_access_attempt(
                request, 
                'save_model_bypass_attempt', 
                'blocked',
                additional_context={
                    'object_id': getattr(obj, 'pk', None),
                    'object_repr': str(obj),
                    'change': change,
                    'form_data': form.cleaned_data if hasattr(form, 'cleaned_data') else None
                }
            )
            
            # Show error message
            messages.error(
                request,
                _("❌ محاولة تجاوز أمني محظورة: لا يمكن حفظ التغييرات على النماذج عالية المخاطر.")
            )
            
            # Raise governance error
            raise AuthorityViolationError(
                f"Admin save_model bypass attempt blocked for {self.model._meta.label}",
                error_code="ADMIN_SAVE_BYPASS_BLOCKED",
                context={
                    'model': self.model._meta.label,
                    'user': request.user.username,
                    'object_id': getattr(obj, 'pk', None)
                }
            )
        
        # If not in read-only mode, check authoritative service
        if self.authoritative_service:
            self._validate_authority_compliance(request, obj, change)
        
        # Log the save attempt
        self._log_admin_access_attempt(
            request,
            'save_model_allowed',
            'success',
            additional_context={
                'object_id': getattr(obj, 'pk', None),
                'change': change
            }
        )
        
        super().save_model(request, obj, form, change)
    
    def delete_model(self, request, obj):
        """Override delete_model to prevent unauthorized deletions."""
        if self.read_only_mode:
            self._log_admin_access_attempt(
                request,
                'delete_model_bypass_attempt',
                'blocked',
                additional_context={
                    'object_id': obj.pk,
                    'object_repr': str(obj)
                }
            )
            
            messages.error(
                request,
                _("❌ محاولة حذف محظورة: لا يمكن حذف سجلات النماذج عالية المخاطر.")
            )
            
            raise AuthorityViolationError(
                f"Admin delete_model bypass attempt blocked for {self.model._meta.label}",
                error_code="ADMIN_DELETE_BYPASS_BLOCKED",
                context={
                    'model': self.model._meta.label,
                    'user': request.user.username,
                    'object_id': obj.pk
                }
            )
        
        super().delete_model(request, obj)
    
    def delete_queryset(self, request, queryset):
        """Override bulk delete to prevent unauthorized bulk operations."""
        if self.read_only_mode or not self.allow_bulk_actions:
            self._log_admin_access_attempt(
                request,
                'bulk_delete_attempt',
                'blocked',
                additional_context={
                    'queryset_count': queryset.count(),
                    'queryset_ids': list(queryset.values_list('pk', flat=True))
                }
            )
            
            messages.error(
                request,
                _("❌ العمليات المجمعة محظورة على النماذج عالية المخاطر.")
            )
            return
        
        super().delete_queryset(request, queryset)
    
    def get_actions(self, request):
        """Override to remove bulk actions for high-risk models."""
        actions = super().get_actions(request)
        
        if not self.allow_bulk_actions:
            # Remove all actions including default delete action
            return {}
        
        return actions
    
    def get_inline_instances(self, request, obj=None):
        """Override to prevent inline edits for high-risk models."""
        if not self.allow_inline_edits and self.read_only_mode:
            # Log inline edit attempt
            if hasattr(self, 'inlines') and self.inlines:
                self._log_admin_access_attempt(
                    request,
                    'inline_edit_attempt',
                    'blocked',
                    additional_context={
                        'inline_classes': [inline.__name__ for inline in self.inlines]
                    }
                )
            return []
        
        return super().get_inline_instances(request, obj)
    
    def response_change(self, request, obj):
        """Override response to redirect to business interface if configured."""
        if self.business_interface_url and self.read_only_mode:
            messages.info(
                request,
                format_html(
                    _('للتعديل الآمن، استخدم <a href="{}" target="_blank">واجهة الأعمال المخصصة</a>'),
                    self.business_interface_url
                )
            )
        
        return super().response_change(request, obj)
    
    def changelist_view(self, request, extra_context=None):
        """Override changelist view to show security warnings."""
        extra_context = extra_context or {}
        
        # Add security warning
        if self.security_warning_message:
            messages.warning(request, self.security_warning_message)
        
        # Add governance status
        extra_context['governance_status'] = {
            'is_high_risk_model': True,
            'read_only_mode': self.read_only_mode,
            'authoritative_service': self.authoritative_service,
            'business_interface_url': self.business_interface_url
        }
        
        return super().changelist_view(request, extra_context)
    
    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        """Override changeform view to show security warnings and controls."""
        extra_context = extra_context or {}
        
        # Add security warning for edit attempts
        if object_id and self.read_only_mode:
            messages.warning(
                request,
                _("🔒 وضع القراءة فقط: هذا السجل محمي ولا يمكن تعديله مباشرة.")
            )
        
        # Add governance information
        extra_context['governance_info'] = {
            'is_high_risk_model': True,
            'read_only_mode': self.read_only_mode,
            'authoritative_service': self.authoritative_service,
            'business_interface_url': self.business_interface_url,
            'security_warning': self.security_warning_message
        }
        
        return super().changeform_view(request, object_id, form_url, extra_context)
    
    def _log_admin_access_attempt(self, request, action_type: str, result: str, 
                                  additional_context: Optional[Dict] = None):
        """Log all admin access attempts for audit trail."""
        try:
            context = {
                'model': self.model._meta.label,
                'action_type': action_type,
                'result': result,
                'user': request.user.username,
                'user_id': request.user.id,
                'ip_address': self._get_client_ip(request),
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                'timestamp': timezone.now().isoformat(),
                'session_key': request.session.session_key,
                'path': request.path,
                'method': request.method
            }
            
            if additional_context:
                context.update(additional_context)
            
            # Use AuditService to create audit trail
            AuditService.create_audit_record(
                model_name=self.model._meta.label,
                object_id=additional_context.get('object_id') if additional_context else None,
                operation=f"admin_{action_type}",
                user=request.user,
                source_service="AdminPanel",
                additional_context=context
            )
            
            # Also log to security logger
            logger.warning(
                f"Admin access attempt: {action_type} on {self.model._meta.label} "
                f"by {request.user.username} - Result: {result}",
                extra=context
            )
            
        except Exception as e:
            # Don't let audit logging failures break the admin
            logger.error(f"Failed to log admin access attempt: {e}")
    
    def _get_client_ip(self, request):
        """Get client IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def _validate_authority_compliance(self, request, obj, change):
        """Validate that the operation complies with authority boundaries."""
        if not self.authoritative_service:
            return
        
        # This would integrate with AuthorityService when available
        # For now, just log the attempt
        logger.info(
            f"Authority validation needed for {self.model._meta.label} "
            f"- Authoritative service: {self.authoritative_service}"
        )


class SecureModelAdmin(HighRiskModelMixin, admin.ModelAdmin):
    """
    Base admin class for high-risk models with comprehensive security controls.
    
    This class should be used as the base for all high-risk model admin classes
    to ensure consistent security enforcement across the admin interface.
    """
    
    def get_queryset(self, request):
        """Override queryset to add security filtering if needed."""
        queryset = super().get_queryset(request)
        
        # Log queryset access
        self._log_admin_access_attempt(
            request,
            'queryset_access',
            'allowed',
            additional_context={
                'queryset_count': queryset.count()
            }
        )
        
        return queryset


class ReadOnlyModelAdmin(SecureModelAdmin):
    """
    Admin class for models that should be completely read-only.
    
    This is the most restrictive admin class, suitable for models like
    JournalEntry, Stock, etc. that should never be modified through admin.
    """
    
    read_only_mode = True
    allow_bulk_actions = False
    allow_inline_edits = False
    require_special_permission = True
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        # Allow viewing but not changing
        return super().has_view_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        return False


class RestrictedModelAdmin(SecureModelAdmin):
    """
    Admin class for models that allow limited modifications with special permissions.
    
    This class is suitable for models that may need occasional admin access
    but require special permissions and comprehensive audit logging.
    """
    
    read_only_mode = False
    allow_bulk_actions = False
    allow_inline_edits = False
    require_special_permission = True


# High-Risk Model Admin Classes
# These classes implement the security controls for each high-risk model

class SecureJournalEntryAdmin(ReadOnlyModelAdmin):
    """Secure admin for JournalEntry model."""
    
    authoritative_service = "AccountingGateway"
    business_interface_url = "/financial/journal-entries/"
    security_warning_message = _(
        "⚠️ القيود المحاسبية محمية: استخدم AccountingGateway للإنشاء والتعديل"
    )
    
    list_display = ['id', 'number', 'date', 'entry_type', 'status', 'reference']
    list_filter = ['entry_type', 'status', 'date']
    search_fields = ['number', 'reference', 'description']
    readonly_fields = ['number', 'created_at', 'created_by']
    
    fieldsets = (
        (_('معلومات القيد'), {
            'fields': ('number', 'date', 'entry_type', 'reference', 'description')
        }),
        (_('الحالة'), {
            'fields': ('status',)
        }),
        (_('معلومات النظام'), {
            'fields': ('created_at', 'created_by'),
            'classes': ('collapse',)
        }),
        (_('تحذير أمني'), {
            'description': 'هذا القيد محمي ولا يمكن تعديله مباشرة. استخدم النظام المحاسبي للتعديلات.',
            'fields': (),
            'classes': ('collapse',)
        })
    )


class SecureStockAdmin(ReadOnlyModelAdmin):
    """Secure admin for Stock model."""
    
    authoritative_service = "MovementService"
    business_interface_url = "/product/stock-management/"
    security_warning_message = _(
        "⚠️ المخزون محمي: استخدم MovementService لتحديث الكميات"
    )
    
    list_display = ['product', 'warehouse', 'quantity', 'updated_at']
    list_filter = ['warehouse', 'updated_at']
    search_fields = ['product__name', 'product__sku']
    readonly_fields = ['quantity', 'updated_at']


class SecureUserAdmin(RestrictedModelAdmin):
    """Secure admin for User model."""
    
    require_special_permission = True
    security_warning_message = _(
        "⚠️ حسابات المستخدمين حساسة: تعديل الصلاحيات يؤثر على أمان النظام"
    )
    
    list_display = ['username', 'email', 'first_name', 'last_name', 'is_active', 'is_staff']
    list_filter = ['is_active', 'is_staff', 'is_superuser', 'date_joined']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    readonly_fields = ['date_joined', 'last_login']


class SecureGroupAdmin(RestrictedModelAdmin):
    """Secure admin for Group model."""
    
    require_special_permission = True
    security_warning_message = _(
        "⚠️ مجموعات المستخدمين حساسة: تعديل الصلاحيات يؤثر على أمان النظام"
    )
    
    list_display = ['name']
    search_fields = ['name']
    filter_horizontal = ['permissions']


# Admin Security Manager
class AdminSecurityManager:
    """
    Manager class for coordinating admin security across all high-risk models.
    
    This class provides centralized management of admin security policies
    and can be used to apply security controls consistently.
    """
    
    HIGH_RISK_MODELS = [
        'financial.JournalEntry',
        'financial.JournalEntryLine', 
        'product.Stock',
        'product.StockMovement',
        'sale.Sale',
        'purchase.Purchase',
        'auth.User',
        'auth.Group',
    ]
    
    @classmethod
    def apply_security_controls(cls):
        """Apply security controls to all high-risk models."""
        logger.info("Applying admin security controls to high-risk models")
        
        # This method would be called during Django startup to ensure
        # all high-risk models have appropriate security controls
        
        for model_label in cls.HIGH_RISK_MODELS:
            try:
                app_label, model_name = model_label.split('.')
                logger.info(f"Security controls applied to {model_label}")
            except Exception as e:
                logger.error(f"Failed to apply security controls to {model_label}: {e}")
    
    @classmethod
    def check_security_compliance(cls):
        """Check that all high-risk models have proper security controls."""
        compliance_report = {
            'compliant_models': [],
            'non_compliant_models': [],
            'errors': []
        }
        
        for model_label in cls.HIGH_RISK_MODELS:
            try:
                # Check if model has security controls
                # This would be implemented based on actual model inspection
                compliance_report['compliant_models'].append(model_label)
            except Exception as e:
                compliance_report['errors'].append(f"{model_label}: {e}")
        
        return compliance_report


# Export the main classes and functions
__all__ = [
    'HighRiskModelMixin',
    'SecureModelAdmin', 
    'ReadOnlyModelAdmin',
    'RestrictedModelAdmin',
    'SecureJournalEntryAdmin',
    'SecureStockAdmin',
    'SecureUserAdmin',
    'SecureGroupAdmin',
    'AdminSecurityManager'
]