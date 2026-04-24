# -*- coding: utf-8 -*-
"""
Service Integration Utilities

Utilities for integrating optimized services into existing views and operations.
"""

from typing import Dict, Any, Optional, List
import logging

from core.services import ServiceFactory
from core.services.system_cache_service import SystemCacheService

logger = logging.getLogger('core.service_integration')


class ServiceIntegrationHelper:
    """
    Helper class for integrating optimized services into existing code.
    
    Features:
    - Service factory integration
    - Cache-aware operations
    - Fallback to existing code patterns
    """
    
    @staticmethod
    def get_user_management_service():
        """
        Get user management service instance.
        
        Returns:
            UserManagementService: Service instance
        """
        try:
            return ServiceFactory.create_service('user_management')
        except Exception as e:
            logger.error(f"Failed to create user management service: {e}")
            # Fallback to direct import
            from users.services.user_management_service import UserManagementService
            return UserManagementService()
    
    @staticmethod
    def get_users_with_stats(use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        Get users with permission statistics using optimized service.
        
        Args:
            use_cache: Whether to use cached data
            
        Returns:
            list: Users with statistics
        """
        try:
            service = ServiceIntegrationHelper.get_user_management_service()
            return service.execute('get_users_with_stats')
        except Exception as e:
            logger.error(f"Failed to get users with stats from service: {e}")
            # Fallback to direct query
            from users.models import User
            return list(User.objects.filter(is_active=True).select_related('role'))
    
    @staticmethod
    def get_system_statistics(use_cache: bool = True) -> Dict[str, Any]:
        """
        Get system statistics using optimized service and caching.
        
        Args:
            use_cache: Whether to use cached data
            
        Returns:
            dict: System statistics
        """
        try:
            if use_cache:
                cache_service = SystemCacheService()
                cached_stats = cache_service.get_system_overview()
                if cached_stats:
                    return cached_stats
            
            service = ServiceIntegrationHelper.get_user_management_service()
            stats = service.execute('get_system_stats')
            
            # Cache the results
            if use_cache and stats:
                cache_service = SystemCacheService()
                cache_service.execute('set', 'system_overview', stats, timeout=1800)
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get system statistics from service: {e}")
            # Fallback to basic counts
            from users.models import User, Role
            return {
                'overview': {
                    'total_active_users': User.objects.filter(is_active=True).count(),
                    'total_active_roles': Role.objects.filter(is_active=True).count(),
                    'users_with_roles': User.objects.filter(role__isnull=False, is_active=True).count()
                }
            }
    
    @staticmethod
    def get_user_permission_summary(user, use_cache: bool = True) -> Dict[str, Any]:
        """
        Get user permission summary using optimized service.
        
        Args:
            user: User instance
            use_cache: Whether to use cached data
            
        Returns:
            dict: User permission summary
        """
        try:
            service = ServiceIntegrationHelper.get_user_management_service()
            return service.execute('get_user_summary', user=user)
        except Exception as e:
            logger.error(f"Failed to get user permission summary from service: {e}")
            # Fallback to basic user info
            return {
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'full_name': user.get_full_name(),
                    'email': user.email
                },
                'role': {
                    'name': user.role.display_name if user.role else 'بدون دور'
                }
            }
    
    @staticmethod
    def warm_user_caches(user_ids: List[int]) -> Dict[str, Any]:
        """
        Warm caches for multiple users.
        
        Args:
            user_ids: List of user IDs
            
        Returns:
            dict: Cache warming results
        """
        try:
            cache_service = SystemCacheService()
            return cache_service.execute('warm_user_caches', user_ids=user_ids)
        except Exception as e:
            logger.error(f"Failed to warm user caches: {e}")
            return {'success': [], 'failed': user_ids, 'total': len(user_ids)}
    
    @staticmethod
    def invalidate_user_caches(user_id: int) -> Dict[str, Any]:
        """
        Invalidate all caches for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            dict: Invalidation results
        """
        try:
            cache_service = SystemCacheService()
            return cache_service.execute('invalidate_user_related', user_id=user_id)
        except Exception as e:
            logger.error(f"Failed to invalidate user caches: {e}")
            return {'success': False, 'error': str(e)}
    

# Convenience functions for common operations
def get_optimized_users_list(use_cache: bool = True) -> List[Dict[str, Any]]:
    """
    Get optimized users list with statistics.
    
    Args:
        use_cache: Whether to use cached data
        
    Returns:
        list: Users with statistics
    """
    return ServiceIntegrationHelper.get_users_with_stats(use_cache)


def get_optimized_system_stats(use_cache: bool = True) -> Dict[str, Any]:
    """
    Get optimized system statistics.
    
    Args:
        use_cache: Whether to use cached data
        
    Returns:
        dict: System statistics
    """
    return ServiceIntegrationHelper.get_system_statistics(use_cache)


def invalidate_user_related_caches(user_id: int) -> None:
    """
    Invalidate all caches related to a user.
    
    Args:
        user_id: User ID
    """
    ServiceIntegrationHelper.invalidate_user_caches(user_id)


# Export main classes and functions
__all__ = [
    'ServiceIntegrationHelper',
    'get_optimized_users_list',
    'get_optimized_system_stats',
    'invalidate_user_related_caches'
]