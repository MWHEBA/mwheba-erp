"""
Thread-safety mechanisms for concurrent governance operations.
Provides database-appropriate locking and concurrency control.
"""

import threading
import time
import logging
from contextlib import contextmanager
from django.db import transaction, connection
from django.core.exceptions import ObjectDoesNotExist
from .exceptions import ConcurrencyError

logger = logging.getLogger(__name__)


class DatabaseLockManager:
    """
    Database-appropriate locking mechanism.
    Adapts to different database backends (SQLite vs PostgreSQL).
    """
    
    @staticmethod
    def get_database_vendor():
        """Get the current database vendor"""
        return connection.vendor
    
    @staticmethod
    def supports_row_locking():
        """Check if database supports row-level locking"""
        return connection.vendor in ['postgresql', 'mysql']
    
    @classmethod
    @contextmanager
    def atomic_operation(cls, savepoint=True):
        """
        Context manager for atomic database operations.
        Uses savepoints for nested transactions when supported.
        """
        try:
            with transaction.atomic(savepoint=savepoint):
                yield
        except Exception as e:
            logger.error(f"Atomic operation failed: {e}")
            raise ConcurrencyError(
                message=f"Database operation failed: {str(e)}",
                resource="database_transaction"
            )
    
    @classmethod
    def select_for_update_if_supported(cls, queryset, nowait=False, skip_locked=False):
        """
        Apply select_for_update if database supports it, otherwise return queryset as-is.
        """
        if cls.supports_row_locking():
            try:
                return queryset.select_for_update(nowait=nowait, skip_locked=skip_locked)
            except Exception as e:
                logger.warning(f"select_for_update failed, falling back to regular query: {e}")
                return queryset
        else:
            # SQLite: No row locking, rely on atomic transactions
            return queryset
    
    @classmethod
    def get_with_lock(cls, model_class, **kwargs):
        """
        Get object with appropriate locking for database type.
        """
        with cls.atomic_operation():
            queryset = model_class.objects.filter(**kwargs)
            queryset = cls.select_for_update_if_supported(queryset)
            
            try:
                return queryset.get()
            except ObjectDoesNotExist:
                raise
            except Exception as e:
                raise ConcurrencyError(
                    message=f"Failed to get object with lock: {str(e)}",
                    resource=f"{model_class.__name__}({kwargs})"
                )


class IdempotencyLock:
    """
    Thread-safe idempotency checking with appropriate locking.
    """
    
    def __init__(self, operation_type: str, idempotency_key: str):
        self.operation_type = operation_type
        self.idempotency_key = idempotency_key
        self.lock_key = f"{operation_type}:{idempotency_key}"
    
    @contextmanager
    def acquire(self, timeout=30):
        """
        Acquire idempotency lock with timeout.
        Uses database-appropriate locking mechanism.
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                with DatabaseLockManager.atomic_operation():
                    # Try to create or get existing idempotency record
                    from .models import IdempotencyRecord
                    
                    # Use database-appropriate locking
                    queryset = IdempotencyRecord.objects.filter(
                        operation_type=self.operation_type,
                        idempotency_key=self.idempotency_key
                    )
                    
                    queryset = DatabaseLockManager.select_for_update_if_supported(
                        queryset, nowait=True
                    )
                    
                    try:
                        record = queryset.get()
                        # Record exists, check if expired
                        if record.is_expired():
                            record.delete()
                            yield None  # Allow operation to proceed
                        else:
                            yield record  # Return existing result
                        return
                    except IdempotencyRecord.DoesNotExist:
                        # No existing record, operation can proceed
                        yield None
                        return
                        
            except Exception as e:
                if "locked" in str(e).lower() or "timeout" in str(e).lower():
                    # Lock contention, wait and retry
                    time.sleep(0.1)
                    continue
                else:
                    # Other error, re-raise
                    raise ConcurrencyError(
                        message=f"Idempotency lock failed: {str(e)}",
                        resource=self.lock_key
                    )
        
        # Timeout reached
        raise ConcurrencyError(
            message=f"Idempotency lock timeout after {timeout}s",
            resource=self.lock_key
        )


class StockLockManager:
    """
    Specialized locking for stock operations to prevent negative stock.
    """
    
    @classmethod
    @contextmanager
    def lock_stock_for_update(cls, product_id, timeout=10):
        """
        Lock stock record for update with appropriate database locking.
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                with DatabaseLockManager.atomic_operation():
                    from product.models import Stock  # Import here to avoid circular imports
                    
                    # Get stock with appropriate locking
                    try:
                        stock = DatabaseLockManager.get_with_lock(
                            Stock, product_id=product_id
                        )
                        yield stock
                        return
                    except Stock.DoesNotExist:
                        # Create stock record if it doesn't exist
                        from product.models import Product
                        product = Product.objects.get(id=product_id)
                        stock = Stock.objects.create(
                            product=product,
                            quantity=0
                        )
                        yield stock
                        return
                        
            except Exception as e:
                if "locked" in str(e).lower() or "timeout" in str(e).lower():
                    # Lock contention, wait and retry
                    time.sleep(0.1)
                    continue
                else:
                    # Other error, re-raise
                    raise ConcurrencyError(
                        message=f"Stock lock failed: {str(e)}",
                        resource=f"stock_product_{product_id}"
                    )
        
        # Timeout reached
        raise ConcurrencyError(
            message=f"Stock lock timeout after {timeout}s",
            resource=f"stock_product_{product_id}"
        )


class ThreadSafeCounter:
    """
    Thread-safe counter for tracking concurrent operations.
    """
    
    def __init__(self, initial_value=0):
        self._value = initial_value
        self._lock = threading.Lock()
    
    def increment(self):
        """Atomically increment counter"""
        with self._lock:
            self._value += 1
            return self._value
    
    def decrement(self):
        """Atomically decrement counter"""
        with self._lock:
            self._value -= 1
            return self._value
    
    def get_value(self):
        """Get current counter value"""
        with self._lock:
            return self._value
    
    def reset(self):
        """Reset counter to zero"""
        with self._lock:
            self._value = 0


class ConcurrencyMonitor:
    """
    Monitor concurrent operations and detect potential issues.
    """
    
    def __init__(self):
        self.operation_counters = {}
        self.lock = threading.Lock()
    
    def start_operation(self, operation_type: str):
        """Register start of operation"""
        with self.lock:
            if operation_type not in self.operation_counters:
                self.operation_counters[operation_type] = ThreadSafeCounter()
            
            count = self.operation_counters[operation_type].increment()
            
            # Log high concurrency
            if count > 10:
                logger.warning(f"High concurrency detected for {operation_type}: {count} operations")
            
            return count
    
    def end_operation(self, operation_type: str):
        """Register end of operation"""
        with self.lock:
            if operation_type in self.operation_counters:
                return self.operation_counters[operation_type].decrement()
            return 0
    
    def get_operation_count(self, operation_type: str):
        """Get current operation count"""
        with self.lock:
            if operation_type in self.operation_counters:
                return self.operation_counters[operation_type].get_value()
            return 0
    
    def get_all_counts(self):
        """Get all operation counts"""
        with self.lock:
            return {
                op_type: counter.get_value() 
                for op_type, counter in self.operation_counters.items()
            }


class ThreadSafeOperationMixin:
    """
    Mixin class providing thread-safe operation utilities.
    """
    
    _thread_locks = {}
    _locks_lock = threading.Lock()
    
    @classmethod
    def _get_thread_lock(cls, lock_name: str = None):
        """Get or create a thread lock for this class"""
        if lock_name is None:
            lock_name = cls.__name__
        
        with cls._locks_lock:
            if lock_name not in cls._thread_locks:
                cls._thread_locks[lock_name] = threading.RLock()
            return cls._thread_locks[lock_name]
    
    @contextmanager
    def thread_safe_operation(self, operation_name: str = None):
        """Context manager for thread-safe operations"""
        if operation_name is None:
            operation_name = f"{self.__class__.__name__}_operation"
        
        with monitor_operation(operation_name):
            with self._get_thread_lock():
                yield


# Global concurrency monitor instance
concurrency_monitor = ConcurrencyMonitor()


@contextmanager
def monitor_operation(operation_type: str):
    """
    Context manager to monitor operation concurrency.
    """
    count = concurrency_monitor.start_operation(operation_type)
    try:
        yield count
    finally:
        concurrency_monitor.end_operation(operation_type)


def retry_on_concurrency_error(max_retries=3, delay=0.1, backoff=2.0):
    """
    Decorator to retry operations on concurrency errors.
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except ConcurrencyError as e:
                    last_exception = e
                    if attempt < max_retries:
                        wait_time = delay * (backoff ** attempt)
                        logger.info(f"Retrying {func.__name__} after concurrency error (attempt {attempt + 1}/{max_retries + 1}), waiting {wait_time}s")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"Max retries exceeded for {func.__name__}")
                        break
                except Exception as e:
                    # Don't retry non-concurrency errors
                    raise
            
            # Re-raise the last concurrency error
            raise last_exception
        
        return wrapper
    return decorator