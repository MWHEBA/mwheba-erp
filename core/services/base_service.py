# -*- coding: utf-8 -*-
"""
Base Service Classes

This module provides the foundation for all services in the unified system,
following the patterns defined in the unified services guide.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Union, List
from django.db import transaction
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)


class BaseService(ABC):
    """
    Base class for all services following unified patterns.
    
    Features:
    - Standardized error handling
    - Logging integration
    - Input validation framework
    - Post-processing hooks
    """
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__module__)
    
    def execute(self, *args, **kwargs) -> Any:
        """
        Execute the service operation with standardized flow.
        
        Returns:
            Any: Operation result
        """
        try:
            self.validate_input(*args, **kwargs)
            result = self.perform_operation(*args, **kwargs)
            self.post_process(result, *args, **kwargs)
            return result
        except Exception as e:
            self.handle_error(e, *args, **kwargs)
            raise
    
    @abstractmethod
    def perform_operation(self, *args, **kwargs) -> Any:
        """
        Main operation implementation - must be implemented by subclasses.
        
        Returns:
            Any: Operation result
        """
        pass
    
    def validate_input(self, *args, **kwargs) -> None:
        """
        Validate input parameters.
        Override in subclasses for specific validation.
        """
        pass
    
    def post_process(self, result: Any, *args, **kwargs) -> None:
        """
        Post-processing after successful operation.
        Override in subclasses for specific post-processing.
        """
        pass
    
    def handle_error(self, error: Exception, *args, **kwargs) -> None:
        """
        Handle errors with standardized logging.
        
        Args:
            error: Exception that occurred
            *args: Original arguments
            **kwargs: Original keyword arguments
        """
        self.logger.error(f"خطأ في {self.__class__.__name__}: {error}")
        
        # Log additional context for debugging
        error_context = {
            'service': self.__class__.__name__,
            'args': str(args)[:200],  # Limit length to avoid long messages
            'kwargs': str(kwargs)[:200],
            'error_type': type(error).__name__
        }
        self.logger.error("تفاصيل الخطأ", extra=error_context)


class TransactionalService(BaseService):
    """
    Service with database transaction support.
    
    All operations are wrapped in atomic transactions.
    """
    
    @transaction.atomic
    def execute(self, *args, **kwargs) -> Any:
        """
        Execute operation within database transaction.
        
        Returns:
            Any: Operation result
        """
        return super().execute(*args, **kwargs)


class BulkOperationService(BaseService):
    """
    Service for bulk operations with batch processing.
    
    Features:
    - Configurable batch size
    - Error handling per batch
    - Progress tracking
    """
    
    def __init__(self, batch_size: int = 100):
        super().__init__()
        self.batch_size = batch_size
    
    def execute_bulk(self, items: list, *args, **kwargs) -> Dict[str, Any]:
        """
        Execute bulk operations in batches.
        
        Args:
            items: List of items to process
            *args: Additional arguments
            **kwargs: Additional keyword arguments
            
        Returns:
            dict: Results with success/failed counts
        """
        results = {'success': [], 'failed': [], 'total': len(items)}
        
        for i in range(0, len(items), self.batch_size):
            batch = items[i:i + self.batch_size]
            try:
                batch_result = self.process_batch(batch, *args, **kwargs)
                results['success'].extend(batch_result)
            except Exception as e:
                self.logger.error(f"فشل في معالجة الدفعة {i//self.batch_size + 1}: {e}")
                results['failed'].extend(batch)
        
        return results
    
    @abstractmethod
    def process_batch(self, batch: list, *args, **kwargs) -> list:
        """
        Process a batch of items.
        
        Args:
            batch: Batch of items to process
            *args: Additional arguments
            **kwargs: Additional keyword arguments
            
        Returns:
            list: Successfully processed items
        """
        pass


class CacheService(BaseService):
    """
    Service with caching capabilities following unified patterns.
    
    Features:
    - Configurable cache timeout
    - Cache key management
    - Cache invalidation patterns
    """
    
    def __init__(self, prefix: str = '', default_timeout: int = 3600):
        super().__init__()
        self.prefix = prefix
        self.default_timeout = default_timeout
    
    def perform_operation(self, action: str, key: str, value: Any = None, **kwargs) -> Any:
        """
        Perform cache operations.
        
        Args:
            action: Cache action ('get', 'set', 'delete', 'get_or_set')
            key: Cache key
            value: Value to cache (for set operations)
            **kwargs: Additional parameters
            
        Returns:
            Any: Cache operation result
        """
        cache_key = self._build_cache_key(key)
        
        if action == 'get':
            return cache.get(cache_key, kwargs.get('default'))
        elif action == 'set':
            timeout = kwargs.get('timeout', self.default_timeout)
            cache.set(cache_key, value, timeout)
            return True
        elif action == 'delete':
            cache.delete(cache_key)
            return True
        elif action == 'get_or_set':
            return self._get_or_set(cache_key, value, kwargs.get('timeout', self.default_timeout))
        else:
            raise ValueError(f"عملية غير مدعومة: {action}")
    
    def _build_cache_key(self, key: str) -> str:
        """
        Build cache key with prefix.
        
        Args:
            key: Base cache key
            
        Returns:
            str: Full cache key
        """
        if self.prefix:
            return f"{self.prefix}:{key}"
        return key
    
    def _get_or_set(self, cache_key: str, callable_or_value: Any, timeout: int) -> Any:
        """
        Get from cache or set new value.
        
        Args:
            cache_key: Cache key
            callable_or_value: Value or callable to get value
            timeout: Cache timeout
            
        Returns:
            Any: Cached or computed value
        """
        cached_value = cache.get(cache_key)
        if cached_value is not None:
            return cached_value
        
        # If value is callable, call it
        if callable(callable_or_value):
            value = callable_or_value()
        else:
            value = callable_or_value
        
        cache.set(cache_key, value, timeout)
        return value
    
    def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate cache keys matching pattern.
        
        Args:
            pattern: Pattern to match
            
        Returns:
            int: Number of keys invalidated
        """
        try:
            from django.core.cache.backends.redis import RedisCache
            if isinstance(cache, RedisCache):
                keys = cache._cache.keys(f"{self.prefix}:{pattern}")
                if keys:
                    return cache._cache.delete(*keys)
        except ImportError:
            pass
        
        return 0


class IntegrationService(BaseService):
    """
    Service for external system integration.
    
    Features:
    - HTTP request handling
    - Timeout management
    - Error handling for external services
    """
    
    def __init__(self, service_name: str, base_url: str, timeout: int = 30):
        super().__init__()
        self.service_name = service_name
        self.base_url = base_url
        self.timeout = timeout
    
    def perform_operation(self, method: str, endpoint: str, data: Optional[Dict] = None, **kwargs) -> Any:
        """
        Perform HTTP request to external service.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            data: Request data
            **kwargs: Additional request parameters
            
        Returns:
            Any: Response data
        """
        import requests
        
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        
        try:
            response = requests.request(
                method=method.upper(),
                url=url,
                json=data,
                timeout=self.timeout,
                **kwargs
            )
            
            response.raise_for_status()
            return response.json() if response.content else None
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"فشل في الاتصال بـ {self.service_name}: {e}")
            raise
    
    def validate_input(self, method: str, endpoint: str, data: Optional[Dict] = None, **kwargs) -> None:
        """
        Validate HTTP request parameters.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            data: Request data
            **kwargs: Additional parameters
        """
        if not method or method.upper() not in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']:
            raise ValueError("طريقة HTTP غير صحيحة")
        
        if not endpoint:
            raise ValueError("endpoint مطلوب")