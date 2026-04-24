# -*- coding: utf-8 -*-
"""
System Cache Service

Comprehensive caching service following unified patterns with optimized queries
and bulk operations support for system-wide caching needs.
"""

from django.core.cache import cache
from django.db.models import Prefetch
from typing import Dict, Any, List, Optional, Set, Union
import logging
from datetime import timedelta
from django.utils import timezone

from .base_service import CacheService, BulkOperationService

logger = logging.getLogger('core.system_cache_service')


class SystemCacheService(CacheService):
    """
    System-wide cache service with optimized queries and bulk operations.
    
    Features:
    - Multi-level caching (user, role, system)
    - Bulk cache operations
    - Smart invalidation patterns
    - Performance monitoring
    - Query optimization
    """
    
    def __init__(self):
        super().__init__(prefix='system', default_timeout=1800)  # 30 minutes
    
    def perform_operation(self, action: str, *args, **kwargs) -> Any:
        """
        Perform system cache operations.
        
        Args:
            action: Cache action to perform
            *args: Action arguments
            **kwargs: Action keyword arguments
            
        Returns:
            Any: Operation result
        """
        if action == 'warm_user_caches':
            return self._warm_user_caches(kwargs.get('user_ids', []))
        elif action == 'warm_system_stats':
            return self._warm_system_statistics()
        elif action == 'invalidate_user_related':
            return self._invalidate_user_related_caches(kwargs['user_id'])
        elif action == 'get_cache_health':
            return self._get_cache_health_stats()
        else:
            return super().perform_operation(action, *args, **kwargs)
    
    def _warm_user_caches(self, user_ids: List[int]) -> Dict[str, Any]:
        """
        Warm caches for multiple users with optimized queries.
        
        Args:
            user_ids: List of user IDs to warm cache for
            
        Returns:
            dict: Results with success/failed counts
        """
        results = {'success': [], 'failed': [], 'total': len(user_ids)}
        
        try:
            from users.models import User
            from django.contrib.auth.models import Permission
            
            # Optimized query to get all users with their permissions
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
                    # Cache user basic info
                    user_info = {
                        'id': user.id,
                        'username': user.username,
                        'full_name': user.get_full_name(),
                        'email': user.email,
                        'is_active': user.is_active,
                        'is_superuser': user.is_superuser,
                        'role_id': user.role.id if user.role else None,
                        'role_name': user.role.display_name if user.role else None,
                        'last_login': user.last_login.isoformat() if user.last_login else None,
                        'cached_at': timezone.now().isoformat()
                    }
                    
                    self.execute('set', f'user_info:{user.id}', user_info, timeout=3600)
                    
                    # Cache user permissions
                    all_permissions = user.get_all_permissions()
                    permission_codenames = {perm.codename for perm in all_permissions}
                    self.execute('set', f'user_permissions:{user.id}', permission_codenames, timeout=1800)
                    
                    # Cache user statistics
                    user_stats = {
                        'total_permissions': len(all_permissions),
                        'role_permissions': len(user.role.permissions.all()) if user.role else 0,
                        'direct_permissions': len(user.user_permissions.all()),
                        'group_permissions': sum(len(group.permissions.all()) for group in user.groups.all()),
                        'last_updated': timezone.now().isoformat()
                    }
                    
                    self.execute('set', f'user_stats:{user.id}', user_stats, timeout=1800)
                    
                    results['success'].append(user.id)
                    
                except Exception as e:
                    logger.error(f"Failed to warm cache for user {user.id}: {e}")
                    results['failed'].append(user.id)
            
            logger.info(f"Warmed cache for {len(results['success'])} users")
            return results
            
        except Exception as e:
            logger.error(f"Bulk cache warming failed: {e}")
            return {'success': [], 'failed': user_ids, 'total': len(user_ids)}
    
    def _warm_system_statistics(self) -> Dict[str, Any]:
        """
        Warm system-wide statistics cache with optimized queries.
        
        Returns:
            dict: Cache warming results
        """
        try:
            from users.models import User, Role
            from django.contrib.auth.models import Permission
            from django.db.models import Count, Q
            
            # System overview statistics
            system_stats = {
                'total_users': User.objects.filter(is_active=True).count(),
                'total_roles': Role.objects.filter(is_active=True).count(),
                'total_permissions': Permission.objects.count(),
                'users_with_roles': User.objects.filter(role__isnull=False, is_active=True).count(),
                'superusers_count': User.objects.filter(is_superuser=True, is_active=True).count(),
                'recent_logins': User.objects.filter(
                    last_login__gte=timezone.now() - timedelta(days=7),
                    is_active=True
                ).count(),
                'generated_at': timezone.now().isoformat()
            }
            
            self.execute('set', 'system_overview', system_stats, timeout=3600)
            
            # Role usage statistics with optimized query
            roles_with_counts = Role.objects.filter(is_active=True).annotate(
                active_users_count=Count('users', filter=Q(users__is_active=True)),
                total_permissions_count=Count('permissions')
            ).select_related().prefetch_related('permissions')
            
            role_stats = {}
            for role in roles_with_counts:
                role_stats[role.id] = {
                    'name': role.display_name,
                    'users_count': role.active_users_count,
                    'permissions_count': role.total_permissions_count,
                    'utilization': round((role.active_users_count / system_stats['total_users']) * 100, 2) if system_stats['total_users'] > 0 else 0
                }
            
            self.execute('set', 'role_statistics', role_stats, timeout=1800)
            
            # Permission distribution statistics
            try:
                from users.services.permission_service import PermissionService
                
                custom_permissions = PermissionService.get_custom_permissions_only()
                categorized_permissions = PermissionService.get_categorized_custom_permissions()
                
                permission_stats = {
                    'total_custom_permissions': custom_permissions.count(),
                    'categories_count': len(categorized_permissions),
                    'category_distribution': {
                        category_key: {
                            'name': category_data['name'],
                            'count': len(category_data['permissions']),
                            'percentage': round((len(category_data['permissions']) / custom_permissions.count()) * 100, 1) if custom_permissions.count() > 0 else 0
                        }
                        for category_key, category_data in categorized_permissions.items()
                    },
                    'generated_at': timezone.now().isoformat()
                }
                
                self.execute('set', 'permission_statistics', permission_stats, timeout=1800)
                
            except ImportError:
                logger.warning("PermissionService not available for permission statistics")
            
            logger.info("System statistics cache warmed successfully")
            return {'success': True, 'message': 'System statistics cached'}
            
        except Exception as e:
            logger.error(f"Failed to warm system statistics cache: {e}")
            return {'success': False, 'error': str(e)}
    
    def _invalidate_user_related_caches(self, user_id: int) -> Dict[str, Any]:
        """
        Invalidate all caches related to a specific user.
        
        Args:
            user_id: User ID to invalidate caches for
            
        Returns:
            dict: Invalidation results
        """
        try:
            # User-specific cache keys
            user_cache_keys = [
                self._build_cache_key(f'user_info:{user_id}'),
                self._build_cache_key(f'user_permissions:{user_id}'),
                self._build_cache_key(f'user_stats:{user_id}'),
                self._build_cache_key(f'user_summary:{user_id}')
            ]
            
            # Invalidate user caches
            cache.delete_many(user_cache_keys)
            
            # Also invalidate system-wide caches that might be affected
            system_cache_keys = [
                self._build_cache_key('system_overview'),
                self._build_cache_key('role_statistics'),
                self._build_cache_key('permission_statistics')
            ]
            
            cache.delete_many(system_cache_keys)
            
            # Invalidate permission service caches
            try:
                from users.services.permission_cache import PermissionCacheService
                PermissionCacheService.invalidate_user_cache(user_id)
            except ImportError:
                pass
            
            logger.debug(f"Invalidated caches for user {user_id}")
            return {
                'success': True,
                'invalidated_keys': len(user_cache_keys) + len(system_cache_keys),
                'user_id': user_id
            }
            
        except Exception as e:
            logger.error(f"Failed to invalidate caches for user {user_id}: {e}")
            return {'success': False, 'error': str(e)}
    
    def _get_cache_health_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive cache health statistics.
        
        Returns:
            dict: Cache health statistics
        """
        try:
            health_stats = {
                'cache_backend': cache.__class__.__name__,
                'default_timeout': self.default_timeout,
                'cache_prefix': self.prefix,
                'status': 'healthy'
            }
            
            # Test cache connectivity
            test_key = self._build_cache_key('health_check')
            test_value = {'timestamp': timezone.now().isoformat()}
            
            try:
                cache.set(test_key, test_value, 60)
                retrieved_value = cache.get(test_key)
                
                if retrieved_value == test_value:
                    health_stats['connectivity'] = 'ok'
                else:
                    health_stats['connectivity'] = 'degraded'
                    health_stats['status'] = 'warning'
                
                cache.delete(test_key)
                
            except Exception as e:
                health_stats['connectivity'] = 'failed'
                health_stats['status'] = 'error'
                health_stats['connectivity_error'] = str(e)
            
            # Try to get Redis-specific stats if available
            try:
                if hasattr(cache, '_cache') and hasattr(cache._cache, 'info'):
                    redis_info = cache._cache.info()
                    health_stats.update({
                        'used_memory': redis_info.get('used_memory_human', 'N/A'),
                        'connected_clients': redis_info.get('connected_clients', 'N/A'),
                        'keyspace_hits': redis_info.get('keyspace_hits', 0),
                        'keyspace_misses': redis_info.get('keyspace_misses', 0),
                        'uptime_in_seconds': redis_info.get('uptime_in_seconds', 'N/A')
                    })
                    
                    # Calculate hit rate
                    hits = redis_info.get('keyspace_hits', 0)
                    misses = redis_info.get('keyspace_misses', 0)
                    if hits + misses > 0:
                        health_stats['hit_rate'] = round((hits / (hits + misses)) * 100, 2)
                        
            except Exception:
                pass  # Redis info not available
            
            health_stats['checked_at'] = timezone.now().isoformat()
            
            return health_stats
            
        except Exception as e:
            logger.error(f"Failed to get cache health stats: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'checked_at': timezone.now().isoformat()
            }
    
    def get_user_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Get cached user information.
        
        Args:
            user_id: User ID
            
        Returns:
            dict: User information or None if not cached
        """
        return self.execute('get', f'user_info:{user_id}')
    
    def get_user_permissions(self, user_id: int) -> Optional[Set[str]]:
        """
        Get cached user permissions.
        
        Args:
            user_id: User ID
            
        Returns:
            set: User permissions or None if not cached
        """
        return self.execute('get', f'user_permissions:{user_id}')
    
    def get_system_overview(self) -> Optional[Dict[str, Any]]:
        """
        Get cached system overview statistics.
        
        Returns:
            dict: System overview or None if not cached
        """
        return self.execute('get', 'system_overview')
    
    def get_role_statistics(self) -> Optional[Dict[str, Any]]:
        """
        Get cached role statistics.
        
        Returns:
            dict: Role statistics or None if not cached
        """
        return self.execute('get', 'role_statistics')


class BulkSystemCacheService(BulkOperationService):
    """
    Bulk cache operations service for system-wide caching.
    
    Features:
    - Bulk cache warming
    - Bulk cache invalidation
    - Performance monitoring
    """
    
    def __init__(self, batch_size: int = 100):
        super().__init__(batch_size)
        self.cache_service = SystemCacheService()
    
    def process_batch(self, batch: list, operation: str, **kwargs) -> list:
        """
        Process batch of cache operations.
        
        Args:
            batch: Batch of items to process
            operation: Operation to perform
            **kwargs: Operation parameters
            
        Returns:
            list: Successfully processed items
        """
        processed = []
        
        if operation == 'warm_user_caches':
            # Bulk user cache warming
            user_ids = [user.id if hasattr(user, 'id') else user for user in batch]
            result = self.cache_service.execute('warm_user_caches', user_ids=user_ids)
            processed.extend(result['success'])
            
        elif operation == 'invalidate_user_caches':
            # Bulk user cache invalidation
            for user_id in batch:
                try:
                    result = self.cache_service.execute('invalidate_user_related', user_id=user_id)
                    if result['success']:
                        processed.append(user_id)
                except Exception as e:
                    logger.error(f"Failed to invalidate cache for user {user_id}: {e}")
                    continue
        
        return processed


# Export main classes
__all__ = ['SystemCacheService', 'BulkSystemCacheService']