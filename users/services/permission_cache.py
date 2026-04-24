# -*- coding: utf-8 -*-
"""
Permission Cache Service

Enhanced caching layer for permission operations following unified service patterns.
Optimized for performance with proper query optimization and bulk operations.
"""

from django.core.cache import cache
from django.contrib.auth.models import Permission
from django.db.models import Prefetch
from typing import Dict, Any, List, Optional, Set
import logging

from ..models import User, Role

logger = logging.getLogger('users.permission_cache')


class PermissionCacheService:
    """
    Enhanced caching service for permission-related data with query optimization.
    
    Features:
    - Optimized database queries with select_related/prefetch_related
    - Bulk cache operations
    - Smart cache invalidation
    - Performance monitoring
    """
    
    # Cache configuration
    CACHE_TIMEOUT = 300  # 5 minutes
    CACHE_PREFIX = 'perm_cache'
    
    @classmethod
    def _get_cache_key(cls, key_type: str, identifier: str) -> str:
        """Generate standardized cache key."""
        return f"{cls.CACHE_PREFIX}:{key_type}:{identifier}"
    
    @classmethod
    def get_user_permissions(cls, user_id: int) -> Optional[Set[str]]:
        """
        Get cached user permissions.
        
        Args:
            user_id: User ID
            
        Returns:
            set: Set of permission codenames or None if not cached
        """
        cache_key = cls._get_cache_key('user_perms', str(user_id))
        return cache.get(cache_key)
    
    @classmethod
    def set_user_permissions(cls, user_id: int, permissions: Set[str]) -> None:
        """
        Cache user permissions.
        
        Args:
            user_id: User ID
            permissions: Set of permission codenames
        """
        cache_key = cls._get_cache_key('user_perms', str(user_id))
        cache.set(cache_key, permissions, cls.CACHE_TIMEOUT)
        logger.debug(f"Cached permissions for user {user_id}: {len(permissions)} permissions")
    
    @classmethod
    def get_role_permissions(cls, role_id: int) -> Optional[Set[str]]:
        """
        Get cached role permissions.
        
        Args:
            role_id: Role ID
            
        Returns:
            set: Set of permission codenames or None if not cached
        """
        cache_key = cls._get_cache_key('role_perms', str(role_id))
        return cache.get(cache_key)
    
    @classmethod
    def set_role_permissions(cls, role_id: int, permissions: Set[str]) -> None:
        """
        Cache role permissions.
        
        Args:
            role_id: Role ID
            permissions: Set of permission codenames
        """
        cache_key = cls._get_cache_key('role_perms', str(role_id))
        cache.set(cache_key, permissions, cls.CACHE_TIMEOUT)
        logger.debug(f"Cached permissions for role {role_id}: {len(permissions)} permissions")
    
    @classmethod
    def get_user_summary(cls, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Get cached user permission summary.
        
        Args:
            user_id: User ID
            
        Returns:
            dict: Permission summary or None if not cached
        """
        cache_key = cls._get_cache_key('user_summary', str(user_id))
        return cache.get(cache_key)
    
    @classmethod
    def set_user_summary(cls, user_id: int, summary: Dict[str, Any]) -> None:
        """
        Cache user permission summary.
        
        Args:
            user_id: User ID
            summary: Permission summary data
        """
        cache_key = cls._get_cache_key('user_summary', str(user_id))
        cache.set(cache_key, summary, cls.CACHE_TIMEOUT)
        logger.debug(f"Cached summary for user {user_id}")
    
    @classmethod
    def bulk_cache_user_permissions(cls, user_ids: List[int]) -> Dict[str, Any]:
        """
        Bulk cache permissions for multiple users with optimized queries.
        
        Args:
            user_ids: List of user IDs to cache
            
        Returns:
            dict: Results with success/failed counts
        """
        results = {'success': [], 'failed': [], 'total': len(user_ids)}
        
        try:
            # Optimized query to get all users with their permissions in one go
            users = User.objects.filter(
                id__in=user_ids,
                is_active=True
            ).select_related('role').prefetch_related(
                Prefetch(
                    'role__permissions',
                    queryset=Permission.objects.select_related('content_type')
                ),
                Prefetch(
                    'user_permissions',
                    queryset=Permission.objects.select_related('content_type')
                ),
                Prefetch(
                    'groups__permissions',
                    queryset=Permission.objects.select_related('content_type')
                )
            )
            
            for user in users:
                try:
                    # Get all permissions for user
                    permissions = user.get_all_permissions()
                    permission_codenames = {perm.codename for perm in permissions}
                    
                    # Cache permissions
                    cls.set_user_permissions(user.id, permission_codenames)
                    results['success'].append(user.id)
                    
                except Exception as e:
                    logger.error(f"Failed to cache permissions for user {user.id}: {e}")
                    results['failed'].append(user.id)
            
            logger.info(f"Bulk cached permissions for {len(results['success'])} users")
            return results
            
        except Exception as e:
            logger.error(f"Bulk cache operation failed: {e}")
            return {'success': [], 'failed': user_ids, 'total': len(user_ids)}
    
    @classmethod
    def bulk_cache_role_permissions(cls, role_ids: List[int]) -> Dict[str, Any]:
        """
        Bulk cache permissions for multiple roles with optimized queries.
        
        Args:
            role_ids: List of role IDs to cache
            
        Returns:
            dict: Results with success/failed counts
        """
        results = {'success': [], 'failed': [], 'total': len(role_ids)}
        
        try:
            # Optimized query to get all roles with their permissions
            roles = Role.objects.filter(
                id__in=role_ids,
                is_active=True
            ).prefetch_related(
                Prefetch(
                    'permissions',
                    queryset=Permission.objects.select_related('content_type')
                )
            )
            
            for role in roles:
                try:
                    # Get role permissions
                    permission_codenames = {perm.codename for perm in role.permissions.all()}
                    
                    # Cache permissions
                    cls.set_role_permissions(role.id, permission_codenames)
                    results['success'].append(role.id)
                    
                except Exception as e:
                    logger.error(f"Failed to cache permissions for role {role.id}: {e}")
                    results['failed'].append(role.id)
            
            logger.info(f"Bulk cached permissions for {len(results['success'])} roles")
            return results
            
        except Exception as e:
            logger.error(f"Bulk role cache operation failed: {e}")
            return {'success': [], 'failed': role_ids, 'total': len(role_ids)}
    
    @classmethod
    def invalidate_user_cache(cls, user_id: int) -> None:
        """
        Invalidate all cached data for a user.
        
        Args:
            user_id: User ID
        """
        cache_keys = [
            cls._get_cache_key('user_perms', str(user_id)),
            cls._get_cache_key('user_summary', str(user_id))
        ]
        cache.delete_many(cache_keys)
        logger.debug(f"Invalidated cache for user {user_id}")
    
    @classmethod
    def invalidate_role_cache(cls, role_id: int) -> None:
        """
        Invalidate cached data for a role.
        
        Args:
            role_id: Role ID
        """
        cache_key = cls._get_cache_key('role_perms', str(role_id))
        cache.delete(cache_key)
        logger.debug(f"Invalidated cache for role {role_id}")
    
    @classmethod
    def invalidate_users_with_role(cls, role_id: int) -> None:
        """
        Invalidate cache for all users with a specific role using optimized query.
        
        Args:
            role_id: Role ID
        """
        # Optimized query to get only user IDs
        user_ids = User.objects.filter(role_id=role_id).values_list('id', flat=True)
        
        # Bulk invalidate user caches
        for user_id in user_ids:
            cls.invalidate_user_cache(user_id)
        
        logger.debug(f"Invalidated cache for {len(user_ids)} users with role {role_id}")
    
    @classmethod
    def warm_cache_for_user(cls, user_id: int) -> None:
        """
        Pre-warm cache for a user with optimized queries.
        
        Args:
            user_id: User ID
        """
        try:
            # Optimized query with all necessary relations
            user = User.objects.select_related('role').prefetch_related(
                Prefetch(
                    'role__permissions',
                    queryset=Permission.objects.select_related('content_type')
                ),
                Prefetch(
                    'user_permissions',
                    queryset=Permission.objects.select_related('content_type')
                ),
                Prefetch(
                    'groups__permissions',
                    queryset=Permission.objects.select_related('content_type')
                )
            ).get(id=user_id)
            
            # Cache user permissions
            permissions = user.get_all_permissions()
            permission_codenames = {perm.codename for perm in permissions}
            cls.set_user_permissions(user_id, permission_codenames)
            
            logger.debug(f"Warmed cache for user {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to warm cache for user {user_id}: {e}")
    
    @classmethod
    def warm_cache_for_active_users(cls, limit: int = 100) -> Dict[str, Any]:
        """
        Pre-warm cache for most active users with bulk operations.
        
        Args:
            limit: Maximum number of users to warm cache for
            
        Returns:
            dict: Results with success/failed counts
        """
        try:
            # Get most recently active users
            user_ids = User.objects.filter(
                is_active=True,
                last_login__isnull=False
            ).order_by('-last_login').values_list('id', flat=True)[:limit]
            
            return cls.bulk_cache_user_permissions(list(user_ids))
            
        except Exception as e:
            logger.error(f"Failed to warm cache for active users: {e}")
            return {'success': [], 'failed': [], 'total': 0}
    
    @classmethod
    def get_cache_stats(cls) -> Dict[str, Any]:
        """
        Get enhanced cache statistics for monitoring.
        
        Returns:
            dict: Cache statistics
        """
        try:
            # Get basic cache info
            stats = {
                'cache_backend': cache.__class__.__name__,
                'cache_timeout': cls.CACHE_TIMEOUT,
                'cache_prefix': cls.CACHE_PREFIX,
                'status': 'active'
            }
            
            # Try to get cache size info if available
            try:
                if hasattr(cache, '_cache'):
                    # Redis cache
                    info = cache._cache.info()
                    stats.update({
                        'used_memory': info.get('used_memory_human', 'N/A'),
                        'connected_clients': info.get('connected_clients', 'N/A'),
                        'keyspace_hits': info.get('keyspace_hits', 0),
                        'keyspace_misses': info.get('keyspace_misses', 0)
                    })
                    
                    # Calculate hit rate
                    hits = info.get('keyspace_hits', 0)
                    misses = info.get('keyspace_misses', 0)
                    if hits + misses > 0:
                        stats['hit_rate'] = round((hits / (hits + misses)) * 100, 2)
            except Exception:
                pass  # Ignore if cache backend doesn't support info
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {'status': 'error', 'error': str(e)}
    
    @classmethod
    def clear_all_permission_cache(cls) -> None:
        """
        Clear all permission-related cache entries.
        Warning: This will impact performance until cache is rebuilt.
        """
        try:
            logger.warning("Clearing all permission cache - performance may be impacted")
            
            # Try to clear by pattern if Redis is available
            try:
                if hasattr(cache, '_cache'):
                    pattern = f"{cls.CACHE_PREFIX}:*"
                    keys = cache._cache.keys(pattern)
                    if keys:
                        cache._cache.delete(*keys)
                        logger.info(f"Cleared {len(keys)} permission cache keys")
                        return
            except Exception:
                pass
            
            # Fallback: log warning that manual cache clear is needed
            logger.warning("Could not clear cache by pattern - consider manual cache flush")
            
        except Exception as e:
            logger.error(f"Failed to clear permission cache: {e}")


# Export main class
__all__ = ['PermissionCacheService']