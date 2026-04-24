# -*- coding: utf-8 -*-
"""
Unified Permission Service

This service provides comprehensive permission management functionality
integrated with the governance system for audit logging and security.
"""

from django.db import transaction, DatabaseError, IntegrityError
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.utils import timezone
from django.core.cache import cache
from django.db.models import Prefetch
from typing import List, Dict, Any, Optional, Union, Tuple
import logging
from functools import lru_cache

from governance.thread_safety import monitor_operation
from governance.services.audit_service import AuditService
from governance.models import GovernanceContext
from ..models import User, Role
from .permission_cache import PermissionCacheService

logger = logging.getLogger('users.permission_service')


class PermissionService:
    """
    Unified service for permission management with governance integration.
    
    Features:
    - Role-based permission management
    - Individual user permissions
    - Custom permissions filtering (42 business-relevant permissions)
    - Frontend categorization without database models
    - Comprehensive audit logging
    - Security validation
    - Governance integration
    - Performance-optimized caching
    - Bulk operations support
    """
    
    # Cache configuration
    CACHE_TIMEOUT = 300  # 5 minutes
    CACHE_PREFIX = 'perm_service'
    
    @classmethod
    def get_custom_permissions_only(cls) -> 'QuerySet[Permission]':
        """
        Get simplified business-relevant permissions grouped by functionality.
        Shows high-level permissions instead of detailed CRUD operations.
        
        Returns:
            QuerySet: Simplified business permissions
        """
        from django.db.models import Q
        
        # Focus on high-level business permissions only
        high_level_patterns = [
            # Management permissions (إدارة شاملة)
            'can_manage_', 'ادارة_', 'manage_',
            # Processing permissions (معالجة العمليات)
            'can_process_', 'معالجة_', 'process_',
            # Export and reporting (التقارير والتصدير)
            'can_export_', 'تصدير_', 'export_', 'view_report',
            # Dashboard and monitoring (المراقبة واللوحات)
            'dashboard', 'monitor',
            # Administrative permissions (الصلاحيات الإدارية)
            'admin', 'supervisor', 'مشرف'
        ]
        
        # Build query for high-level patterns
        pattern_query = Q()
        for pattern in high_level_patterns:
            pattern_query |= Q(codename__icontains=pattern) | Q(name__icontains=pattern)
        
        # Include specific important permissions for key business areas
        specific_permissions = [
            # Financial
            'add_transaction', 'change_transaction', 'view_transaction',
            'add_invoice', 'change_invoice', 'view_invoice',
            
            # HR
            'add_employee', 'change_employee', 'view_employee',
            'add_qrapplication', 'change_qrapplication', 'view_qrapplication',
            'can_convert_application', 'view_qrcode',
            
            # Products and Purchases
            'add_product', 'change_product', 'view_product',
            'add_purchase', 'change_purchase', 'view_purchase',
            
            # Customers
            'add_customer', 'change_customer', 'view_customer',
            'add_customerpayment', 'change_customerpayment', 'view_customerpayment',
            
            # HR and Users
            'add_employee', 'change_employee', 'view_employee',
            'add_user', 'change_user', 'view_user',
        ]
        
        specific_query = Q()
        for perm in specific_permissions:
            specific_query |= Q(codename=perm)
        
        # Get permissions from business apps only
        business_apps = [
            'financial', 'hr', 'product', 'purchase', 'supplier',
            'core', 'users', 'governance'
        ]
        
        # Combine all queries
        simplified_permissions = Permission.objects.filter(
            (Q(content_type__app_label__in=business_apps) & (pattern_query | specific_query))
        ).exclude(
            # Exclude Django system apps
            Q(content_type__app_label__in=['admin', 'auth', 'contenttypes', 'sessions', 'token_blacklist'])
        ).exclude(
            # Exclude very detailed permissions we don't need
            Q(codename__icontains='logentry') |
            Q(codename__icontains='permission') |
            Q(codename__icontains='group') |
            Q(codename__icontains='contenttype') |
            # Exclude audit log permissions - these should be automatic for all users
            Q(codename__icontains='audit') |
            Q(codename__icontains='log') |
            Q(name__icontains='audit') |
            Q(name__icontains='سجل')
        ).distinct()
        
        return simplified_permissions
    
    @classmethod
    def get_categorized_custom_permissions(cls) -> Dict[str, Dict[str, Any]]:
        """
        Get custom permissions organized in logical categories using frontend categorization.
        No database models - categories are hardcoded for simplicity.
        
        Returns:
            dict: Categorized permissions
        """
        custom_permissions = cls.get_custom_permissions_only()
        
        # Define categories with icons and descriptions
        categories = {
            'financial': {
                'name': 'الإدارة المالية',
                'name_en': 'Financial Management',
                'icon': 'fas fa-calculator',
                'description': 'إدارة الحسابات والمدفوعات والمعاملات المالية',
                'permissions': []
            },
            'inventory': {
                'name': 'المبيعات والمخزون',
                'name_en': 'Sales & Inventory',
                'icon': 'fas fa-boxes',
                'description': 'إدارة المنتجات والمبيعات والمشتريات والمخزون',
                'permissions': []
            },
            'hr': {
                'name': 'الموارد البشرية',
                'name_en': 'Human Resources',
                'icon': 'fas fa-user-tie',
                'description': 'إدارة الموظفين والرواتب والشؤون الإدارية',
                'permissions': []
            },
            'suppliers': {
                'name': 'الموردين والعملاء',
                'name_en': 'Suppliers & Customers',
                'icon': 'fas fa-handshake',
                'description': 'إدارة الموردين والعملاء والعلاقات التجارية',
                'permissions': []
            },
            'reports': {
                'name': 'التقارير والمراقبة',
                'name_en': 'Reports & Monitoring',
                'icon': 'fas fa-chart-bar',
                'description': 'عرض التقارير وتصدير البيانات ومراقبة النظام',
                'permissions': []
            },
            'system': {
                'name': 'إدارة النظام والمستخدمين',
                'name_en': 'System & User Management',
                'icon': 'fas fa-cogs',
                'description': 'إدارة المستخدمين والأدوار وإعدادات النظام',
                'permissions': []
            }
        }
        
        # Categorize permissions based on codename and model
        for permission in custom_permissions:
            codename = permission.codename.lower()
            model = permission.content_type.model.lower()
            app_label = permission.content_type.app_label.lower()
            
            # Financial Management
            if (any(keyword in codename for keyword in ['financial', 'payment', 'account', 'transaction', 'invoice', 'مالية', 'مدفوعات', 'حساب']) or 
                  app_label == 'financial' or
                  any(keyword in model for keyword in ['payment', 'account', 'financial', 'transaction', 'invoice'])):
                categories['financial']['permissions'].append(permission)
            
            # Sales, Purchases & Inventory
            elif (any(keyword in codename for keyword in ['purchase', 'product', 'inventory', 'stock', 'supplier', 'مشتريات', 'منتجات', 'مخزون', 'موردين']) or
                  app_label in ['product', 'purchase', 'supplier'] or
                  any(keyword in model for keyword in ['product', 'purchase', 'supplier', 'inventory'])):
                categories['inventory']['permissions'].append(permission)
            
            # HR Management (إدارة الموارد البشرية)
            elif (any(keyword in codename for keyword in ['employee', 'salary', 'hr', 'staff', 'موظف', 'راتب', 'موارد_بشرية']) or 
                  app_label == 'hr' or
                  any(keyword in model for keyword in ['employee', 'salary', 'staff'])):
                categories['hr']['permissions'].append(permission)
            
            # Activities & Transportation — removed (modules deleted)
            # Reports & Analytics (التقارير والتحليلات)
            elif (any(keyword in codename for keyword in ['report', 'export', 'audit', 'monitor', 'dashboard', 'تقارير', 'تصدير', 'مراقبة']) or
                  'view_report' in codename or 'can_export' in codename):
                categories['reports']['permissions'].append(permission)
            
            # System Administration (إدارة النظام)
            elif (any(keyword in codename for keyword in ['user', 'role', 'permission', 'admin', 'manage', 'مستخدم', 'دور', 'صلاحية', 'ادارة']) or
                  app_label in ['users', 'core'] or
                  'can_manage' in codename):
                categories['system']['permissions'].append(permission)
            
            # Default to System for any uncategorized permissions
            else:
                categories['system']['permissions'].append(permission)
        
        # Add permission counts to each category
        for category_key, category_data in categories.items():
            category_data['count'] = len(category_data['permissions'])
        
        return categories
    
    @classmethod
    def get_user_custom_permissions(cls, user: User) -> 'QuerySet[Permission]':
        """
        Get only custom permissions for a specific user.
        
        Args:
            user: User to get permissions for
            
        Returns:
            QuerySet: User's custom permissions only
        """
        custom_permissions = cls.get_custom_permissions_only()
        
        # Get user's direct permissions
        user_permission_ids = set(user.user_permissions.filter(
            id__in=custom_permissions.values_list('id', flat=True)
        ).values_list('id', flat=True))
        
        # Add role permissions if user has a role
        if hasattr(user, 'role') and user.role:
            role_permission_ids = set(user.role.permissions.filter(
                id__in=custom_permissions.values_list('id', flat=True)
            ).values_list('id', flat=True))
            user_permission_ids.update(role_permission_ids)
        
        # Return combined permissions as a single queryset
        return custom_permissions.filter(id__in=user_permission_ids)
    
    @classmethod
    def _get_cache_key(cls, key_type: str, identifier: Union[int, str]) -> str:
        """Generate cache key for permission data."""
        return f"{cls.CACHE_PREFIX}:{key_type}:{identifier}"
    
    @classmethod
    def _invalidate_user_cache(cls, user_id: int) -> None:
        """Invalidate all cached data for a user."""
        PermissionCacheService.invalidate_user_cache(user_id)
        # Also clear LRU cache
        cls._get_cached_user_permissions.cache_clear()
    
    @classmethod
    def _invalidate_role_cache(cls, role_id: int) -> None:
        """Invalidate cached data for a role."""
        PermissionCacheService.invalidate_role_cache(role_id)
        PermissionCacheService.invalidate_users_with_role(role_id)
        # Also clear LRU cache
        cls._get_cached_user_permissions.cache_clear()
    
    @classmethod
    @lru_cache(maxsize=1000)
    def _get_cached_user_permissions(cls, user_id: int) -> frozenset:
        """Get cached user permissions as frozenset for hashability."""
        try:
            user = User.objects.select_related('role').prefetch_related(
                'role__permissions',
                'custom_permissions',
                'groups__permissions'
            ).get(id=user_id)
            
            permissions = user.get_all_permissions()
            return frozenset((perm.codename, perm.name) for perm in permissions)
        except User.DoesNotExist:
            return frozenset()
    
    @classmethod
    def check_user_permission(cls, user: User, permission_name: str, obj: Any = None) -> bool:
        """
        Check if user has a specific permission with caching.
        
        Args:
            user: User to check
            permission_name: Permission codename or display name
            obj: Object to check permission against (for object-level permissions)
            
        Returns:
            bool: True if user has permission
        """
        with monitor_operation("check_user_permission"):
            try:
                # Superuser always has all permissions
                if user.is_superuser:
                    return True
                
                # Check if user is active
                if not user.is_active:
                    return False
                
                # Get cached permissions
                user_permissions = cls._get_cached_user_permissions(user.id)
                
                # Check by codename or name
                has_permission = any(
                    permission_name in (codename, name)
                    for codename, name in user_permissions
                )
                
                # Log permission check for audit (only for critical operations)
                if not has_permission or permission_name in ['ادارة_المستخدمين', 'ادارة_الادوار_والصلاحيات']:
                    AuditService.log_operation(
                        model_name='Permission',
                        object_id=0,
                        operation='CHECK_PERMISSION',
                        source_service='PermissionService',
                        user=user,
                        permission_name=permission_name,
                        result=has_permission,
                        target_user_id=user.id
                    )
                
                return has_permission
                
            except ValidationError as e:
                logger.error(f"Validation error checking permission for user {user.id}: {e}")
                return False
            except DatabaseError as e:
                logger.error(f"Database error checking permission for user {user.id}: {e}")
                return False
            except Exception as e:
                logger.error(f"Unexpected error checking permission for user {user.id}: {e}")
                return False
    
    @classmethod
    @transaction.atomic
    def assign_role_to_user(cls, user: User, role: Role, assigned_by: User) -> bool:
        """
        Assign a role to a user with full audit logging.
        
        Args:
            user: User to assign role to
            role: Role to assign
            assigned_by: User performing the assignment
            
        Returns:
            bool: True if successful
        """
        with monitor_operation("assign_role_to_user"):
            try:
                # Validate inputs
                if not user or not role:
                    raise ValidationError("User and role are required")
                
                if not assigned_by.can_manage_roles():
                    raise ValidationError("Insufficient permissions to assign roles")
                
                # Store old role for audit
                old_role = user.role
                old_role_name = old_role.display_name if old_role else "بدون دور"
                
                # Assign new role
                user.role = role
                user.save()
                
                # Invalidate user cache
                cls._invalidate_user_cache(user.id)
                
                # Log the assignment
                AuditService.log_operation(
                    model_name='User',
                    object_id=user.id,
                    operation='ASSIGN_ROLE',
                    source_service='PermissionService',
                    user=assigned_by,
                    before_data={'role': old_role_name},
                    after_data={'role': role.display_name},
                    target_user_id=user.id,
                    assigned_role_id=role.id
                )
                
                logger.info(f"Role '{role.display_name}' assigned to user '{user.username}' by '{assigned_by.username}'")
                return True
                
            except Exception as e:
                logger.error(f"Error assigning role to user {user.id}: {e}")
                raise
    
    @classmethod
    def get_user_permissions_summary(cls, user: User) -> Dict[str, Any]:
        """
        Get comprehensive summary of user permissions with caching.
        
        Args:
            user: User to get summary for
            
        Returns:
            dict: Permission summary
        """
        with monitor_operation("get_user_permissions_summary"):
            try:
                # Try to get from cache first
                cached_summary = PermissionCacheService.get_user_summary(user.id)
                if cached_summary:
                    return cached_summary
                
                # Get all permissions with optimized queries
                user = User.objects.select_related('role').prefetch_related(
                    'role__permissions__content_type',
                    'custom_permissions__content_type',
                    'groups__permissions__content_type'
                ).get(id=user.id)
                
                all_permissions = user.get_all_permissions()
                role_permissions = set(user.role.permissions.all()) if user.role else set()
                custom_permissions = set(user.custom_permissions.all())
                
                # Group permissions by app
                permissions_by_app = {}
                for perm in all_permissions:
                    app_label = perm.content_type.app_label
                    if app_label not in permissions_by_app:
                        permissions_by_app[app_label] = {
                            'role_permissions': [],
                            'custom_permissions': [],
                            'total': 0
                        }
                    
                    if perm in role_permissions:
                        permissions_by_app[app_label]['role_permissions'].append({
                            'id': perm.id,
                            'name': perm.name,
                            'codename': perm.codename,
                            'model': perm.content_type.model
                        })
                    if perm in custom_permissions:
                        permissions_by_app[app_label]['custom_permissions'].append({
                            'id': perm.id,
                            'name': perm.name,
                            'codename': perm.codename,
                            'model': perm.content_type.model
                        })
                    
                    permissions_by_app[app_label]['total'] += 1
                
                summary = {
                    'user': {
                        'id': user.id,
                        'username': user.username,
                        'full_name': user.get_full_name()
                    },
                    'role': {
                        'id': user.role.id if user.role else None,
                        'name': user.role.display_name if user.role else None
                    },
                    'total_permissions': len(all_permissions),
                    'role_permissions_count': len(role_permissions),
                    'custom_permissions_count': len(custom_permissions),
                    'permissions_by_app': permissions_by_app,
                    'is_superuser': user.is_superuser,
                    'is_active': user.is_active,
                    'generated_at': timezone.now().isoformat()
                }
                
                # Cache the summary
                PermissionCacheService.set_user_summary(user.id, summary)
                
                return summary
                
            except Exception as e:
                logger.error(f"Error getting permissions summary for user {user.id}: {e}")
                return {}
    
    @classmethod
    @transaction.atomic
    def create_role(cls, name: str, display_name: str, description: str, 
                   permissions: List[Permission], created_by: User, is_active: bool = True) -> Role:
        """
        Create a new role with permissions.
        
        Args:
            name: Role internal name
            display_name: Role display name
            description: Role description
            permissions: List of permissions to assign
            created_by: User creating the role
            is_active: Whether role is active
            
        Returns:
            Role: Created role
        """
        with monitor_operation("create_role"):
            try:
                # Validate inputs
                if not created_by.can_manage_roles():
                    raise ValidationError("Insufficient permissions to create roles")
                
                if Role.objects.filter(name=name).exists():
                    raise ValidationError(f"Role with name '{name}' already exists")
                
                # Create role
                role = Role.objects.create(
                    name=name,
                    display_name=display_name,
                    description=description,
                    is_active=is_active
                )
                
                # Assign permissions
                if permissions:
                    role.permissions.set(permissions)
                
                # Log the creation
                AuditService.log_operation(
                    model_name='Role',
                    object_id=role.id,
                    operation='CREATE',
                    source_service='PermissionService',
                    user=created_by,
                    after_data={
                        'name': name,
                        'display_name': display_name,
                        'permissions_count': len(permissions)
                    }
                )
                
                logger.info(f"Role '{display_name}' created by '{created_by.username}'")
                return role
                
            except Exception as e:
                logger.error(f"Error creating role: {e}")
                raise
    
    @classmethod
    @transaction.atomic
    def update_role_permissions(cls, role: Role, permissions: List[Permission], updated_by: User) -> bool:
        """
        Update role permissions.
        
        Args:
            role: Role to update
            permissions: New list of permissions
            updated_by: User performing the update
            
        Returns:
            bool: True if successful
        """
        with monitor_operation("update_role_permissions"):
            try:
                # Validate inputs
                if not updated_by.can_manage_roles():
                    raise ValidationError("Insufficient permissions to update roles")
                
                # Store old permissions for audit
                old_permissions = list(role.permissions.all())
                old_permission_names = [p.codename for p in old_permissions]
                
                # Update permissions
                role.permissions.set(permissions)
                
                # Invalidate role cache
                cls._invalidate_role_cache(role.id)
                
                # New permissions for audit
                new_permission_names = [p.codename for p in permissions]
                
                # Log the update
                AuditService.log_operation(
                    model_name='Role',
                    object_id=role.id,
                    operation='UPDATE_PERMISSIONS',
                    source_service='PermissionService',
                    user=updated_by,
                    before_data={'permissions': old_permission_names},
                    after_data={'permissions': new_permission_names}
                )
                
                logger.info(f"Permissions updated for role '{role.display_name}' by '{updated_by.username}'")
                return True
                
            except Exception as e:
                logger.error(f"Error updating role permissions: {e}")
                raise
    
    @classmethod
    def get_permission_statistics(cls) -> Dict[str, Any]:
        """
        Get system-wide permission statistics.
        
        Returns:
            dict: Permission statistics
        """
        with monitor_operation("get_permission_statistics"):
            try:
                # Basic counts
                total_users = User.objects.filter(is_active=True).count()
                total_roles = Role.objects.filter(is_active=True).count()
                total_permissions = Permission.objects.count()
                
                # Users with roles
                users_with_roles = User.objects.filter(role__isnull=False, is_active=True).count()
                
                # Users with custom permissions
                users_with_custom_perms = User.objects.filter(
                    custom_permissions__isnull=False, is_active=True
                ).distinct().count()
                
                # Role usage statistics - optimized to avoid N+1 queries
                roles_with_counts = Role.objects.filter(is_active=True).annotate(
                    active_users_count=Count('users', filter=Q(users__is_active=True))
                ).select_related().prefetch_related('permissions')
                
                role_usage = {}
                for role in roles_with_counts:
                    role_usage[role.display_name] = role.active_users_count
                
                return {
                    'total_users': total_users,
                    'total_roles': total_roles,
                    'total_permissions': total_permissions,
                    'users_with_roles': users_with_roles,
                    'users_without_roles': total_users - users_with_roles,
                    'users_with_custom_permissions': users_with_custom_perms,
                    'role_usage': role_usage
                }
                
            except Exception as e:
                logger.error(f"Error getting permission statistics: {e}")
                return {}
    
    @classmethod
    def get_recent_permission_changes(cls, days: int = 7) -> List[Dict[str, Any]]:
        """
        Get recent permission changes from audit log.
        
        Args:
            days: Number of days to look back
            
        Returns:
            list: Recent permission changes
        """
        with monitor_operation("get_recent_permission_changes"):
            try:
                from datetime import timedelta
                from governance.models import AuditTrail
                
                since_date = timezone.now() - timedelta(days=days)
                
                # Get permission-related audit entries
                permission_operations = [
                    'ASSIGN_ROLE', 'ADD_CUSTOM_PERMISSION', 'REMOVE_CUSTOM_PERMISSION',
                    'CREATE', 'UPDATE_PERMISSIONS'
                ]
                
                audit_entries = AuditTrail.objects.filter(
                    timestamp__gte=since_date,
                    operation__in=permission_operations,
                    source_service='PermissionService'
                ).order_by('-timestamp')[:50]
                
                changes = []
                for entry in audit_entries:
                    changes.append({
                        'timestamp': entry.timestamp,
                        'operation': entry.operation,
                        'user': entry.user.get_full_name() if entry.user else 'System',
                        'model': entry.model_name,
                        'object_id': entry.object_id,
                        'details': entry.additional_context
                    })
                
                return changes
                
            except Exception as e:
                logger.error(f"Error getting recent permission changes: {e}")
                return []
    
    @classmethod
    @transaction.atomic
    def bulk_assign_roles(cls, user_role_pairs: List[Tuple[User, Role]], assigned_by: User) -> Dict[str, Any]:
        """
        Assign roles to multiple users in a single transaction.
        
        Args:
            user_role_pairs: List of (user, role) tuples
            assigned_by: User performing the assignments
            
        Returns:
            dict: Results with success and failed assignments
        """
        with monitor_operation("bulk_assign_roles"):
            results = {'success': [], 'failed': [], 'total': len(user_role_pairs)}
            
            try:
                # Validate permissions
                if not assigned_by.can_manage_roles():
                    raise ValidationError("Insufficient permissions for bulk role assignment")
                
                for user, role in user_role_pairs:
                    try:
                        # Store old role for audit
                        old_role = user.role
                        old_role_name = old_role.display_name if old_role else "بدون دور"
                        
                        # Assign new role
                        user.role = role
                        user.save()
                        
                        # Invalidate cache
                        cls._invalidate_user_cache(user.id)
                        
                        # Log successful assignment
                        AuditService.log_operation(
                            model_name='User',
                            object_id=user.id,
                            operation='BULK_ASSIGN_ROLE',
                            source_service='PermissionService',
                            user=assigned_by,
                            before_data={'role': old_role_name},
                            after_data={'role': role.display_name},
                            target_user_id=user.id,
                            assigned_role_id=role.id
                        )
                        
                        results['success'].append({
                            'user': user.username,
                            'user_name': user.get_full_name(),
                            'role': role.display_name,
                            'old_role': old_role_name
                        })
                        
                    except Exception as e:
                        logger.error(f"Failed to assign role to user {user.id}: {e}")
                        results['failed'].append({
                            'user': user.username,
                            'user_name': user.get_full_name(),
                            'role': role.display_name,
                            'error': str(e)
                        })
                
                logger.info(f"Bulk role assignment completed: {len(results['success'])} success, {len(results['failed'])} failed")
                return results
                
            except Exception as e:
                logger.error(f"Bulk role assignment failed: {e}")
                raise
    
    @classmethod
    def compare_roles(cls, role1: Role, role2: Role) -> Dict[str, Any]:
        """
        Compare permissions between two roles.
        
        Args:
            role1: First role to compare
            role2: Second role to compare
            
        Returns:
            dict: Comparison results
        """
        with monitor_operation("compare_roles"):
            try:
                # Get permissions for both roles
                role1_perms = set(role1.permissions.all())
                role2_perms = set(role2.permissions.all())
                
                # Calculate differences
                common_permissions = role1_perms & role2_perms
                role1_only = role1_perms - role2_perms
                role2_only = role2_perms - role1_perms
                
                # Group permissions by app for better display
                def group_by_app(permissions):
                    grouped = {}
                    for perm in permissions:
                        app_label = perm.content_type.app_label
                        if app_label not in grouped:
                            grouped[app_label] = []
                        grouped[app_label].append({
                            'id': perm.id,
                            'name': perm.name,
                            'codename': perm.codename,
                            'model': perm.content_type.model
                        })
                    return grouped
                
                return {
                    'role1': {
                        'id': role1.id,
                        'name': role1.display_name,
                        'permissions_count': len(role1_perms)
                    },
                    'role2': {
                        'id': role2.id,
                        'name': role2.display_name,
                        'permissions_count': len(role2_perms)
                    },
                    'comparison': {
                        'common_count': len(common_permissions),
                        'role1_only_count': len(role1_only),
                        'role2_only_count': len(role2_only),
                        'total_unique_count': len(role1_perms | role2_perms),
                        'similarity_percentage': round((len(common_permissions) / len(role1_perms | role2_perms)) * 100, 2) if role1_perms | role2_perms else 0
                    },
                    'permissions': {
                        'common': group_by_app(common_permissions),
                        'role1_only': group_by_app(role1_only),
                        'role2_only': group_by_app(role2_only)
                    }
                }
                
            except Exception as e:
                logger.error(f"Error comparing roles {role1.id} and {role2.id}: {e}")
                return {}
    
    @classmethod
    def export_role_configuration(cls, role_ids: List[int] = None) -> Dict[str, Any]:
        """
        Export role configuration for backup or transfer.
        
        Args:
            role_ids: List of role IDs to export (None for all active roles)
            
        Returns:
            dict: Exportable role configuration
        """
        with monitor_operation("export_role_configuration"):
            try:
                # Get roles to export
                if role_ids:
                    roles = Role.objects.filter(id__in=role_ids, is_active=True)
                else:
                    roles = Role.objects.filter(is_active=True)
                
                roles = roles.prefetch_related('permissions__content_type')
                
                export_data = {
                    'export_timestamp': timezone.now().isoformat(),
                    'total_roles': roles.count(),
                    'roles': []
                }
                
                for role in roles:
                    role_data = {
                        'name': role.name,
                        'display_name': role.display_name,
                        'description': role.description,
                        'is_system_role': role.is_system_role,
                        'permissions': []
                    }
                    
                    # Export permissions with full context
                    for perm in role.permissions.all():
                        role_data['permissions'].append({
                            'codename': perm.codename,
                            'name': perm.name,
                            'app_label': perm.content_type.app_label,
                            'model': perm.content_type.model
                        })
                    
                    export_data['roles'].append(role_data)
                
                logger.info(f"Exported configuration for {len(export_data['roles'])} roles")
                return export_data
                
            except Exception as e:
                logger.error(f"Error exporting role configuration: {e}")
                return {}
    
    @classmethod
    def get_performance_metrics(cls) -> Dict[str, Any]:
        """
        Get performance metrics for the permission system.
        
        Returns:
            dict: Performance metrics
        """
        with monitor_operation("get_performance_metrics"):
            try:
                # Get cache statistics
                cache_stats = PermissionCacheService.get_cache_stats()
                
                # Get LRU cache info
                lru_info = cls._get_cached_user_permissions.cache_info()
                
                # Get basic counts
                total_users = User.objects.filter(is_active=True).count()
                total_roles = Role.objects.filter(is_active=True).count()
                users_with_roles = User.objects.filter(role__isnull=False, is_active=True).count()
                
                return {
                    'cache_performance': {
                        'lru_hits': lru_info.hits,
                        'lru_misses': lru_info.misses,
                        'lru_hit_rate': round(lru_info.hits / (lru_info.hits + lru_info.misses) * 100, 2) if (lru_info.hits + lru_info.misses) > 0 else 0,
                        'lru_current_size': lru_info.currsize,
                        'lru_max_size': lru_info.maxsize,
                        'cache_backend': cache_stats.get('cache_backend', 'Unknown')
                    },
                    'system_stats': {
                        'total_active_users': total_users,
                        'total_active_roles': total_roles,
                        'users_with_roles': users_with_roles,
                        'users_without_roles': total_users - users_with_roles,
                        'role_assignment_rate': round((users_with_roles / total_users) * 100, 2) if total_users > 0 else 0
                    },
                    'generated_at': timezone.now().isoformat()
                }
                
            except Exception as e:
                logger.error(f"Error getting performance metrics: {e}")
                return {'error': str(e)}


# Export main class
__all__ = ['PermissionService']