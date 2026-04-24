"""
خدمة التخزين المؤقت المحسنة للنظام الموحد
Enhanced Caching Service for the Unified System
"""

import hashlib
import json
import time
from typing import Any, Dict, List, Optional, Union, Callable
from django.core.cache import cache
from django.core.cache.utils import make_template_fragment_key
from django.conf import settings
from django.utils import timezone
from django.db import models
from django.core.serializers.json import DjangoJSONEncoder
import logging

logger = logging.getLogger(__name__)


class CachingService:
    """
    خدمة التخزين المؤقت الموحدة والمحسنة
    Unified and Enhanced Caching Service
    """
    
    # Cache timeout configurations (in seconds)
    TIMEOUT_SHORT = 300      # 5 minutes
    TIMEOUT_MEDIUM = 1800    # 30 minutes  
    TIMEOUT_LONG = 3600      # 1 hour
    TIMEOUT_EXTENDED = 86400 # 24 hours
    
    # Cache key prefixes for different data types
    PREFIX_USER = "user"
    PREFIX_CUSTOMER = "customer"
    PREFIX_FINANCIAL = "financial"
    PREFIX_ACADEMIC = "academic"
    PREFIX_REPORT = "report"
    PREFIX_QUERY = "query"
    PREFIX_SESSION = "session"
    
    def __init__(self):
        """Initialize the caching service"""
        self.default_timeout = getattr(settings, 'CACHE_DEFAULT_TIMEOUT', self.TIMEOUT_MEDIUM)
        self.cache_stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'deletes': 0
        }
    
    def generate_cache_key(self, prefix: str, *args, **kwargs) -> str:
        """
        Generate a unique cache key based on prefix and parameters
        
        Args:
            prefix: Cache key prefix
            *args: Positional arguments to include in key
            **kwargs: Keyword arguments to include in key
            
        Returns:
            str: Generated cache key
        """
        try:
            # Create a string representation of all parameters
            key_parts = [str(prefix)]
            
            # Add positional arguments
            for arg in args:
                if isinstance(arg, models.Model):
                    key_parts.append(f"{arg.__class__.__name__}_{arg.pk}")
                else:
                    key_parts.append(str(arg))
            
            # Add keyword arguments (sorted for consistency)
            for key, value in sorted(kwargs.items()):
                if isinstance(value, models.Model):
                    key_parts.append(f"{key}_{value.__class__.__name__}_{value.pk}")
                else:
                    key_parts.append(f"{key}_{value}")
            
            # Create base key
            base_key = "_".join(key_parts)
            
            # Hash if key is too long (Redis has 512MB key limit, but we keep it reasonable)
            if len(base_key) > 200:
                hash_obj = hashlib.md5(base_key.encode('utf-8'))
                return f"{prefix}_{hash_obj.hexdigest()}"
            
            return base_key.replace(' ', '_').replace(':', '_')
            
        except Exception as e:
            logger.error(f"Error generating cache key: {str(e)}")
            # Fallback to simple hash-based key
            fallback_data = f"{prefix}_{args}_{kwargs}"
            hash_obj = hashlib.md5(fallback_data.encode('utf-8'))
            return f"{prefix}_{hash_obj.hexdigest()}"
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get value from cache
        
        Args:
            key: Cache key
            default: Default value if key not found
            
        Returns:
            Cached value or default
        """
        try:
            # Use a unique sentinel to distinguish between None values and cache misses
            sentinel = object()
            value = cache.get(key, sentinel)
            
            if value is not sentinel:
                self.cache_stats['hits'] += 1
                logger.debug(f"Cache hit for key: {key}")
                return value
            else:
                self.cache_stats['misses'] += 1
                logger.debug(f"Cache miss for key: {key}")
                return default
        except Exception as e:
            logger.error(f"Error getting cache key {key}: {str(e)}")
            self.cache_stats['misses'] += 1
            return default
    
    def set(self, key: str, value: Any, timeout: Optional[int] = None) -> bool:
        """
        Set value in cache
        
        Args:
            key: Cache key
            value: Value to cache
            timeout: Cache timeout in seconds
            
        Returns:
            bool: True if successful
        """
        try:
            if timeout is None:
                timeout = self.default_timeout
            
            # Handle serialization for complex objects
            cache_value = value
            if isinstance(value, (dict, list)):
                try:
                    cache_value = json.dumps(value, cls=DjangoJSONEncoder, ensure_ascii=False)
                except (TypeError, ValueError) as e:
                    logger.warning(f"Failed to serialize value for key {key}: {str(e)}")
                    # Keep original value if serialization fails
                    cache_value = value
            elif isinstance(value, models.Model):
                try:
                    cache_value = json.dumps({
                        'model': value.__class__.__name__,
                        'pk': value.pk,
                        'fields': {field.name: getattr(value, field.name) for field in value._meta.fields}
                    }, cls=DjangoJSONEncoder, ensure_ascii=False)
                except (TypeError, ValueError) as e:
                    logger.warning(f"Failed to serialize model for key {key}: {str(e)}")
                    cache_value = value
            
            # Attempt to set in cache
            try:
                result = cache.set(key, cache_value, timeout)
                # Django cache.set() returns None on success, not True/False
                # We consider None as success
                success = result is not False  # None or True = success, False = failure
                if success:
                    self.cache_stats['sets'] += 1
                    logger.debug(f"Cache set for key: {key}, timeout: {timeout}")
                return success
            except Exception as cache_error:
                logger.error(f"Cache backend error for key {key}: {str(cache_error)}")
                return False
                
        except Exception as e:
            logger.error(f"Error setting cache key {key}: {str(e)}")
            return False
    
    def delete(self, key: str) -> bool:
        """
        Delete value from cache
        
        Args:
            key: Cache key to delete
            
        Returns:
            bool: True if successful
        """
        try:
            success = cache.delete(key)
            if success:
                self.cache_stats['deletes'] += 1
                logger.debug(f"Cache deleted for key: {key}")
            return success
        except Exception as e:
            logger.error(f"Error deleting cache key {key}: {str(e)}")
            return False
    
    def delete_pattern(self, pattern: str) -> int:
        """
        Delete all cache keys matching a pattern
        
        Args:
            pattern: Pattern to match (supports wildcards)
            
        Returns:
            int: Number of keys deleted
        """
        try:
            if hasattr(cache, 'delete_pattern'):
                # Redis backend supports pattern deletion
                return cache.delete_pattern(pattern)
            else:
                # Fallback for other backends
                logger.warning(f"Pattern deletion not supported for current cache backend")
                return 0
        except Exception as e:
            logger.error(f"Error deleting cache pattern {pattern}: {str(e)}")
            return 0
    
    def get_or_set(self, key: str, callable_func: Callable, timeout: Optional[int] = None, *args, **kwargs) -> Any:
        """
        Get value from cache or set it using a callable function
        
        Args:
            key: Cache key
            callable_func: Function to call if cache miss
            timeout: Cache timeout in seconds
            *args: Arguments for callable function
            **kwargs: Keyword arguments for callable function
            
        Returns:
            Cached or computed value
        """
        try:
            # Try to get from cache first using sentinel to detect None values
            sentinel = object()
            value = cache.get(key, sentinel)
            
            if value is not sentinel:
                # Cache hit
                self.cache_stats['hits'] += 1
                logger.debug(f"Cache hit for get_or_set key: {key}")
                return value
            
            # Cache miss - compute value
            self.cache_stats['misses'] += 1
            logger.debug(f"Cache miss for get_or_set key: {key}, computing value")
            
            start_time = time.time()
            computed_value = callable_func(*args, **kwargs)
            computation_time = time.time() - start_time
            
            # Set in cache
            set_success = self.set(key, computed_value, timeout)
            if not set_success:
                logger.warning(f"Failed to cache computed value for key: {key}")
            
            logger.debug(f"Cache computed for key: {key}, time: {computation_time:.3f}s")
            return computed_value
            
        except Exception as e:
            logger.error(f"Error in get_or_set for key {key}: {str(e)}")
            # Fallback to direct computation
            try:
                return callable_func(*args, **kwargs)
            except Exception as inner_e:
                logger.error(f"Error in fallback computation: {str(inner_e)}")
                return None
    
    def cache_model_instance(self, instance: models.Model, timeout: Optional[int] = None) -> str:
        """
        Cache a model instance
        
        Args:
            instance: Django model instance
            timeout: Cache timeout in seconds
            
        Returns:
            str: Cache key used
        """
        try:
            key = self.generate_cache_key(
                f"model_{instance.__class__.__name__.lower()}", 
                instance.pk
            )
            
            # Serialize model instance
            instance_data = {
                'model': instance.__class__.__name__,
                'pk': instance.pk,
                'fields': {}
            }
            
            for field in instance._meta.fields:
                field_value = getattr(instance, field.name)
                if isinstance(field_value, models.Model):
                    instance_data['fields'][field.name] = {
                        'model': field_value.__class__.__name__,
                        'pk': field_value.pk
                    }
                else:
                    instance_data['fields'][field.name] = field_value
            
            self.set(key, instance_data, timeout)
            return key
            
        except Exception as e:
            logger.error(f"Error caching model instance: {str(e)}")
            return ""
    
    def invalidate_model_cache(self, model_class: type, instance_id: Optional[int] = None) -> int:
        """
        Invalidate cache for a model class or specific instance
        
        Args:
            model_class: Django model class
            instance_id: Specific instance ID (optional)
            
        Returns:
            int: Number of cache keys invalidated
        """
        try:
            model_name = model_class.__name__.lower()
            
            if instance_id:
                # Invalidate specific instance
                key = self.generate_cache_key(f"model_{model_name}", instance_id)
                return 1 if self.delete(key) else 0
            else:
                # Invalidate all instances of this model
                pattern = f"model_{model_name}_*"
                return self.delete_pattern(pattern)
                
        except Exception as e:
            logger.error(f"Error invalidating model cache: {str(e)}")
            return 0
    
    def cache_query_result(self, query_key: str, queryset, timeout: Optional[int] = None) -> str:
        """
        Cache a queryset result
        
        Args:
            query_key: Unique identifier for the query
            queryset: Django queryset to cache
            timeout: Cache timeout in seconds
            
        Returns:
            str: Cache key used
        """
        try:
            key = self.generate_cache_key(self.PREFIX_QUERY, query_key)
            
            # Convert queryset to list of dictionaries
            query_data = []
            for obj in queryset:
                if isinstance(obj, models.Model):
                    obj_data = {
                        'model': obj.__class__.__name__,
                        'pk': obj.pk,
                        'fields': {}
                    }
                    for field in obj._meta.fields:
                        field_value = getattr(obj, field.name)
                        if isinstance(field_value, models.Model):
                            obj_data['fields'][field.name] = {
                                'model': field_value.__class__.__name__,
                                'pk': field_value.pk
                            }
                        else:
                            obj_data['fields'][field.name] = field_value
                    query_data.append(obj_data)
                else:
                    query_data.append(obj)
            
            self.set(key, query_data, timeout)
            return key
            
        except Exception as e:
            logger.error(f"Error caching query result: {str(e)}")
            return ""
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics
        
        Returns:
            dict: Cache statistics
        """
        try:
            # Calculate hit rate
            total_requests = self.cache_stats['hits'] + self.cache_stats['misses']
            hit_rate = (self.cache_stats['hits'] / total_requests * 100) if total_requests > 0 else 0
            
            stats = {
                'hits': self.cache_stats['hits'],
                'misses': self.cache_stats['misses'],
                'sets': self.cache_stats['sets'],
                'deletes': self.cache_stats['deletes'],
                'hit_rate': round(hit_rate, 2),
                'total_requests': total_requests
            }
            
            # Add backend-specific stats if available
            if hasattr(cache, 'get_stats'):
                backend_stats = cache.get_stats()
                stats.update(backend_stats)
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {str(e)}")
            return self.cache_stats.copy()
    
    def clear_all_cache(self) -> bool:
        """
        Clear all cache entries
        
        Returns:
            bool: True if successful
        """
        try:
            cache.clear()
            logger.info("All cache cleared")
            return True
        except Exception as e:
            logger.error(f"Error clearing all cache: {str(e)}")
            return False
    
    def warm_up_cache(self, warm_up_functions: List[Callable]) -> Dict[str, bool]:
        """
        Warm up cache by pre-loading frequently accessed data
        
        Args:
            warm_up_functions: List of functions to call for cache warm-up
            
        Returns:
            dict: Results of warm-up operations
        """
        results = {}
        
        for func in warm_up_functions:
            try:
                func_name = func.__name__ if hasattr(func, '__name__') else str(func)
                start_time = time.time()
                
                func()
                
                execution_time = time.time() - start_time
                results[func_name] = {
                    'success': True,
                    'execution_time': round(execution_time, 3)
                }
                
                logger.info(f"Cache warm-up completed for {func_name} in {execution_time:.3f}s")
                
            except Exception as e:
                func_name = func.__name__ if hasattr(func, '__name__') else str(func)
                results[func_name] = {
                    'success': False,
                    'error': str(e)
                }
                logger.error(f"Cache warm-up failed for {func_name}: {str(e)}")
        
        return results


# Global instance
caching_service = CachingService()


# Utility functions for common caching patterns
def cache_user_data(user_id: int, timeout: Optional[int] = None) -> str:
    """Cache user data"""
    return caching_service.generate_cache_key(caching_service.PREFIX_USER, user_id)


def cache_customer_data(customer_id: int, timeout: Optional[int] = None) -> str:
    """Cache customer data"""
    return caching_service.generate_cache_key(caching_service.PREFIX_CUSTOMER, customer_id)


def cache_financial_data(account_id: int, timeout: Optional[int] = None) -> str:
    """Cache financial account data"""
    return caching_service.generate_cache_key(caching_service.PREFIX_FINANCIAL, account_id)


def invalidate_user_cache(user_id: int) -> bool:
    """Invalidate user-related cache"""
    key = cache_user_data(user_id)
    return caching_service.delete(key)


def invalidate_customer_cache(customer_id: int) -> bool:
    """Invalidate customer-related cache"""
    key = cache_customer_data(customer_id)
    return caching_service.delete(key)