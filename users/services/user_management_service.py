# -*- coding: utf-8 -*-
"""
User Management Service

Enhanced user management service following unified service patterns with
optimized queries and bulk operations support.
"""

from django.db import transaction, DatabaseError
from django.db.models import Count, Q, Prefetch
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth.models import Permission
from typing import List, Dict, Any, Optional
import logging

from core.services.base_service import TransactionalService, BulkOperationService
from governance.thread_safety import monitor_operation
from governance.services.audit_service import AuditService
from ..models import User, Role
from .permission_service import PermissionService
from .permission_cache import PermissionCacheService

logger = logging.getLogger('users.user_management_service')


class UserManagementService(TransactionalService):
    """
    Enhanced User Management Service following unified patterns.
    
    Features:
    - Optimized database queries with select_related/prefetch_related
    - Bulk operations support
    - Caching integration
    - User statistics with custom permissions only
    - Permission summaries for users
    - Integration with PermissionService for filtering
    """
    
    def perform_operation(self, action: str, *args, **kwargs) -> Any:
        """
        Perform user management operations.
        
        Args:
            action: Operation to perform
            *args: Operation arguments
            **kwargs: Operation keyword arguments
            
        Returns:
            Any: Operation result
        """
        if action == 'get_users_with_stats':
            return self._get_users_with_permission_stats()
        elif action == 'get_user_summary':
            return self._get_permission_summary_for_user(kwargs['user'])
        elif action == 'get_system_stats':
            return self._get_system_permission_statistics()
        elif action == 'update_user_permissions':
            return self._update_user_custom_permissions(
                kwargs['user'], kwargs['permission_ids'], kwargs['updated_by']
            )
        elif action == 'search_users':
            return self._search_users(
                kwargs.get('query', ''),
                kwargs.get('role_id'),
                kwargs.get('has_permissions')
            )
        else:
            raise ValueError(f"عملية غير مدعومة: {action}")
    
    def _get_users_with_permission_stats(self) -> List[Dict[str, Any]]:
        """
        Get all users with their custom permission statistics using optimized queries.
        Only counts the custom business-relevant permissions.
        
        Returns:
            list: Users with permission statistics
        """
        with monitor_operation("get_users_with_permission_stats"):
            try:
                # Get custom permission IDs once to avoid repeated queries
                custom_perm_ids = list(PermissionService.get_custom_permissions_only().values_list('id', flat=True))
                
                # Optimized query with all necessary relations (including inactive users)
                users = User.objects.all().select_related('role').prefetch_related(
                    Prefetch(
                        'user_permissions',
                        queryset=Permission.objects.filter(id__in=custom_perm_ids),
                        to_attr='cached_custom_permissions'
                    ),
                    Prefetch(
                        'role__permissions',
                        queryset=Permission.objects.filter(id__in=custom_perm_ids),
                        to_attr='cached_role_custom_permissions'
                    )
                )
                
                result = []
                for user in users:
                    # Count custom permissions efficiently using cached attributes
                    direct_custom_count = len(getattr(user, 'cached_custom_permissions', []))
                    role_custom_count = 0
                    
                    if user.role and hasattr(user.role, 'cached_role_custom_permissions'):
                        role_custom_count = len(user.role.cached_role_custom_permissions)
                    
                    # Total unique custom permissions (avoid double counting)
                    direct_perm_ids = {p.id for p in getattr(user, 'cached_custom_permissions', [])}
                    role_perm_ids = set()
                    if user.role and hasattr(user.role, 'cached_role_custom_permissions'):
                        role_perm_ids = {p.id for p in user.role.cached_role_custom_permissions}
                    
                    total_custom_count = len(direct_perm_ids | role_perm_ids)
                    
                    user_data = {
                        'user': user,
                        'user_id': user.id,
                        'username': user.username,
                        'full_name': user.get_full_name(),
                        'email': user.email,
                        'is_active': user.is_active,
                        'is_superuser': user.is_superuser,
                        'last_login': user.last_login,
                        'date_joined': user.date_joined,
                        'custom_permissions_count': total_custom_count,
                        'role_name': user.role.display_name if user.role else 'بدون دور',
                        'role_id': user.role.id if user.role else None,
                        'role_permissions_count': role_custom_count,
                        'direct_permissions_count': direct_custom_count,
                        'total_custom_permissions': len(custom_perm_ids)
                    }
                    
                    result.append(user_data)
                
                # Sort by custom permissions count (descending)
                result.sort(key=lambda x: x['custom_permissions_count'], reverse=True)
                
                logger.info(f"Retrieved permission statistics for {len(result)} users")
                return result
                
            except ValidationError as e:
                logger.error(f"Validation error getting users with permission stats: {e}")
                return []
            except DatabaseError as e:
                logger.error(f"Database error getting users with permission stats: {e}")
                return []
            except Exception as e:
                logger.error(f"Unexpected error getting users with permission stats: {e}")
                return []
    
    def _get_permission_summary_for_user(self, user: User) -> Dict[str, Any]:
        """
        Get detailed permission summary for a specific user with optimized queries.
        Shows breakdown by categories and includes only custom permissions.
        
        Args:
            user: User to get summary for
            
        Returns:
            dict: Detailed permission summary
        """
        with monitor_operation("get_permission_summary_for_user"):
            try:
                # Try cache first
                cached_summary = PermissionCacheService.get_user_summary(user.id)
                if cached_summary:
                    return cached_summary
                
                # Get custom permission IDs
                custom_perm_ids = list(PermissionService.get_custom_permissions_only().values_list('id', flat=True))
                
                # Optimized query for user with custom permissions only
                user = User.objects.select_related('role').prefetch_related(
                    Prefetch(
                        'user_permissions',
                        queryset=Permission.objects.filter(id__in=custom_perm_ids).select_related('content_type'),
                        to_attr='cached_custom_permissions'
                    ),
                    Prefetch(
                        'role__permissions',
                        queryset=Permission.objects.filter(id__in=custom_perm_ids).select_related('content_type'),
                        to_attr='cached_role_custom_permissions'
                    )
                ).get(id=user.id)
                
                # Get user's custom permissions efficiently
                direct_perms = getattr(user, 'cached_custom_permissions', [])
                role_perms = []
                if user.role and hasattr(user.role, 'cached_role_custom_permissions'):
                    role_perms = user.role.cached_role_custom_permissions
                
                # Combine permissions (avoid duplicates)
                all_user_perms = {}
                for perm in direct_perms:
                    all_user_perms[perm.id] = perm
                for perm in role_perms:
                    all_user_perms[perm.id] = perm
                
                user_custom_perms = list(all_user_perms.values())
                
                # Get categorized custom permissions
                categorized_permissions = PermissionService.get_categorized_custom_permissions()
                
                # Build summary by category
                category_summary = {}
                total_assigned = 0
                total_available = 0
                
                for category_key, category_data in categorized_permissions.items():
                    category_perms = category_data['permissions']
                    total_available += len(category_perms)
                    
                    # Find which permissions in this category the user has
                    user_perm_ids = {p.id for p in user_custom_perms}
                    user_has_perms = [
                        perm for perm in category_perms 
                        if perm.id in user_perm_ids
                    ]
                    
                    assigned_count = len(user_has_perms)
                    total_assigned += assigned_count
                    
                    category_summary[category_key] = {
                        'name': category_data['name'],
                        'name_en': category_data['name_en'],
                        'icon': category_data['icon'],
                        'description': category_data['description'],
                        'total_permissions': len(category_perms),
                        'assigned_permissions': assigned_count,
                        'percentage': round((assigned_count / len(category_perms)) * 100, 1) if category_perms else 0,
                        'permissions': [
                            {
                                'id': perm.id,
                                'codename': perm.codename,
                                'name': perm.name,
                                'assigned': perm in user_has_perms
                            }
                            for perm in category_perms
                        ]
                    }
                
                # Overall summary
                overall_percentage = round((total_assigned / total_available) * 100, 1) if total_available > 0 else 0
                
                summary = {
                    'user': {
                        'id': user.id,
                        'username': user.username,
                        'full_name': user.get_full_name(),
                        'email': user.email,
                        'is_active': user.is_active,
                        'is_superuser': user.is_superuser
                    },
                    'role': {
                        'id': user.role.id if user.role else None,
                        'name': user.role.display_name if user.role else 'بدون دور',
                        'description': user.role.description if user.role else None
                    },
                    'permissions_overview': {
                        'total_available_custom': total_available,
                        'total_assigned_custom': total_assigned,
                        'overall_percentage': overall_percentage,
                        'categories_count': len(categorized_permissions)
                    },
                    'categories': category_summary,
                    'generated_at': timezone.now().isoformat()
                }
                
                # Cache the summary
                PermissionCacheService.set_user_summary(user.id, summary)
                
                return summary
                
            except ValidationError as e:
                logger.error(f"Validation error getting permission summary for user {user.id}: {e}")
                return {}
            except DatabaseError as e:
                logger.error(f"Database error getting permission summary for user {user.id}: {e}")
                return {}
            except Exception as e:
                logger.error(f"Unexpected error getting permission summary for user {user.id}: {e}")
                return {}
    
    def _get_system_permission_statistics(self) -> Dict[str, Any]:
        """
        Get system-wide permission statistics with optimized queries.
        
        Returns:
            dict: System permission statistics
        """
        with monitor_operation("get_system_permission_statistics"):
            try:
                # Basic counts with optimized queries
                total_users = User.objects.filter(is_active=True).count()
                total_roles = Role.objects.filter(is_active=True).count()
                total_custom_permissions = PermissionService.get_custom_permissions_only().count()
                
                # Users with roles
                users_with_roles = User.objects.filter(role__isnull=False, is_active=True).count()
                
                # Users with direct custom permissions - optimized query
                custom_perm_ids = PermissionService.get_custom_permissions_only().values_list('id', flat=True)
                users_with_direct_custom_perms = User.objects.filter(
                    user_permissions__in=custom_perm_ids,
                    is_active=True
                ).distinct().count()
                
                # Role usage statistics with optimized queries
                roles_with_counts = Role.objects.filter(is_active=True).annotate(
                    active_users_count=Count('users', filter=Q(users__is_active=True))
                ).prefetch_related(
                    Prefetch(
                        'permissions',
                        queryset=Permission.objects.filter(id__in=custom_perm_ids)
                    )
                )
                
                role_usage = {}
                for role in roles_with_counts:
                    custom_perms_count = len(role.permissions.all())
                    
                    role_usage[role.display_name] = {
                        'users_count': role.active_users_count,
                        'custom_permissions_count': custom_perms_count,
                        'percentage_of_custom': round((custom_perms_count / total_custom_permissions) * 100, 1) if total_custom_permissions > 0 else 0
                    }
                
                # Category statistics
                categorized_permissions = PermissionService.get_categorized_custom_permissions()
                category_stats = {}
                for category_key, category_data in categorized_permissions.items():
                    category_stats[category_key] = {
                        'name': category_data['name'],
                        'permissions_count': len(category_data['permissions']),
                        'percentage_of_total': round((len(category_data['permissions']) / total_custom_permissions) * 100, 1) if total_custom_permissions > 0 else 0
                    }
                
                return {
                    'overview': {
                        'total_active_users': total_users,
                        'total_active_roles': total_roles,
                        'total_custom_permissions': total_custom_permissions,
                        'users_with_roles': users_with_roles,
                        'users_without_roles': total_users - users_with_roles,
                        'users_with_direct_custom_permissions': users_with_direct_custom_perms,
                        'role_assignment_rate': round((users_with_roles / total_users) * 100, 1) if total_users > 0 else 0
                    },
                    'role_usage': role_usage,
                    'category_distribution': category_stats,
                    'generated_at': timezone.now().isoformat()
                }
                
            except Exception as e:
                logger.error(f"Error getting system permission statistics: {e}")
                return {}
    
    @transaction.atomic
    def _update_user_custom_permissions(self, user: User, permission_ids: List[int], updated_by: User) -> bool:
        """
        Update user's direct custom permissions with optimized operations.
        Only allows assignment of custom business-relevant permissions.
        
        Args:
            user: User to update permissions for
            permission_ids: List of permission IDs to assign
            updated_by: User performing the update
            
        Returns:
            bool: True if successful
        """
        with monitor_operation("update_user_custom_permissions"):
            try:
                # Validate permissions
                if not updated_by.has_perm('users.change_user') and not updated_by.is_superuser:
                    raise ValidationError("Insufficient permissions to update user permissions")
                
                # Get custom permissions only with optimized query
                custom_permissions = PermissionService.get_custom_permissions_only()
                valid_permission_ids = set(custom_permissions.values_list('id', flat=True))
                
                # Filter to only allow custom permissions
                filtered_permission_ids = [
                    pid for pid in permission_ids 
                    if pid in valid_permission_ids
                ]
                
                # Store old permissions for audit
                old_custom_perms = list(user.user_permissions.filter(
                    id__in=valid_permission_ids
                ).values_list('codename', flat=True))
                
                # Update user's direct permissions (only custom ones)
                user.user_permissions.clear()
                if filtered_permission_ids:
                    new_permissions = custom_permissions.filter(id__in=filtered_permission_ids)
                    user.user_permissions.set(new_permissions)
                
                # Invalidate cache
                PermissionCacheService.invalidate_user_cache(user.id)
                
                # New permissions for audit
                new_custom_perms = list(user.user_permissions.filter(
                    id__in=valid_permission_ids
                ).values_list('codename', flat=True))
                
                # Log the update
                AuditService.log_operation(
                    model_name='User',
                    object_id=user.id,
                    operation='UPDATE_CUSTOM_PERMISSIONS',
                    source_service='UserManagementService',
                    user=updated_by,
                    before_data={'custom_permissions': old_custom_perms},
                    after_data={'custom_permissions': new_custom_perms},
                    target_user_id=user.id
                )
                
                logger.info(f"Custom permissions updated for user '{user.username}' by '{updated_by.username}'")
                return True
                
            except Exception as e:
                logger.error(f"Error updating user custom permissions: {e}")
                raise
    
    def _search_users(self, query: str = '', role_id: int = None, has_permissions: bool = None) -> List[Dict[str, Any]]:
        """
        Search users with filtering options using optimized queries.
        
        Args:
            query: Search query for username, email, or full name
            role_id: Filter by specific role ID
            has_permissions: Filter by whether user has custom permissions
            
        Returns:
            list: Filtered users with stats
        """
        with monitor_operation("search_users"):
            try:
                # Start with all users (including inactive)
                users_query = User.objects.all()
                
                # Apply search query
                if query:
                    users_query = users_query.filter(
                        Q(username__icontains=query) |
                        Q(first_name__icontains=query) |
                        Q(last_name__icontains=query) |
                        Q(email__icontains=query)
                    )
                
                # Filter by role
                if role_id:
                    users_query = users_query.filter(role_id=role_id)
                
                # Filter by permissions
                if has_permissions is not None:
                    custom_perm_ids = PermissionService.get_custom_permissions_only().values_list('id', flat=True)
                    if has_permissions:
                        users_query = users_query.filter(
                            Q(user_permissions__in=custom_perm_ids) |
                            Q(role__permissions__in=custom_perm_ids)
                        ).distinct()
                    else:
                        users_query = users_query.exclude(
                            Q(user_permissions__in=custom_perm_ids) |
                            Q(role__permissions__in=custom_perm_ids)
                        ).distinct()
                
                # Optimize query with necessary relations
                users = users_query.select_related('role').prefetch_related(
                    Prefetch(
                        'user_permissions',
                        queryset=Permission.objects.filter(id__in=PermissionService.get_custom_permissions_only().values_list('id', flat=True))
                    ),
                    Prefetch(
                        'role__permissions',
                        queryset=Permission.objects.filter(id__in=PermissionService.get_custom_permissions_only().values_list('id', flat=True))
                    )
                )
                
                result = []
                for user in users:
                    # Count custom permissions efficiently
                    direct_perms = set(user.user_permissions.all())
                    role_perms = set(user.role.permissions.all() if user.role else [])
                    total_custom_perms = len(direct_perms | role_perms)
                    
                    result.append({
                        'user': user,
                        'user_id': user.id,
                        'username': user.username,
                        'full_name': user.get_full_name(),
                        'email': user.email,
                        'role_name': user.role.display_name if user.role else 'بدون دور',
                        'custom_permissions_count': total_custom_perms,
                        'last_login': user.last_login
                    })
                
                logger.info(f"User search returned {len(result)} results")
                return result
                
            except Exception as e:
                logger.error(f"Error searching users: {e}")
                return []


class BulkUserManagementService(BulkOperationService):
    """
    Bulk operations service for user management with optimized queries.
    
    Features:
    - Bulk permission updates
    - Bulk role assignments
    - Bulk cache warming
    """
    
    def process_batch(self, batch: list, operation: str, **kwargs) -> list:
        """
        Process batch of users for bulk operations.
        
        Args:
            batch: Batch of users or user data
            operation: Operation to perform
            **kwargs: Operation parameters
            
        Returns:
            list: Successfully processed items
        """
        processed = []
        
        if operation == 'warm_cache':
            # Bulk cache warming
            user_ids = [user.id if hasattr(user, 'id') else user for user in batch]
            result = PermissionCacheService.bulk_cache_user_permissions(user_ids)
            processed.extend(result['success'])
            
        elif operation == 'assign_roles':
            # Bulk role assignment
            role = kwargs.get('role')
            assigned_by = kwargs.get('assigned_by')
            
            if not role or not assigned_by:
                raise ValueError("Role and assigned_by are required for bulk role assignment")
            
            with transaction.atomic():
                for user in batch:
                    try:
                        user.role = role
                        user.save(update_fields=['role'])
                        
                        # Invalidate cache
                        PermissionCacheService.invalidate_user_cache(user.id)
                        
                        processed.append(user)
                        
                    except Exception as e:
                        logger.error(f"Failed to assign role to user {user.id}: {e}")
                        continue
        
        return processed


# Export main classes
__all__ = ['UserManagementService', 'BulkUserManagementService']