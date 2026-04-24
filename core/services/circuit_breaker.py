"""
Circuit Breaker Pattern Implementation for External Services
✅ PHASE 2: System Stability - Circuit breaker for external services
"""
import time
import logging
from enum import Enum
from typing import Callable, Any, Optional
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Circuit is open, failing fast
    HALF_OPEN = "half_open"  # Testing if service is back

class CircuitBreakerError(Exception):
    """Exception raised when circuit breaker is open"""
    pass

class CircuitBreaker:
    """
    Circuit Breaker implementation for external service calls
    
    Usage:
        breaker = CircuitBreaker("financial_api", failure_threshold=5, timeout=60)
        
        @breaker
        def call_financial_api():
            # Your external API call here
            pass
    """
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        timeout: int = 60,
        expected_exception: tuple = (Exception,)
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.expected_exception = expected_exception
        
        # Cache keys for storing circuit breaker state
        self.state_key = f"circuit_breaker:{name}:state"
        self.failure_count_key = f"circuit_breaker:{name}:failures"
        self.last_failure_key = f"circuit_breaker:{name}:last_failure"
    
    def __call__(self, func: Callable) -> Callable:
        """Decorator to wrap functions with circuit breaker"""
        def wrapper(*args, **kwargs):
            return self.call(func, *args, **kwargs)
        return wrapper
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection"""
        state = self.get_state()
        
        if state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self._set_state(CircuitState.HALF_OPEN)
                logger.info(f"Circuit breaker {self.name} moved to HALF_OPEN state")
            else:
                logger.warning(f"Circuit breaker {self.name} is OPEN - failing fast")
                raise CircuitBreakerError(f"Circuit breaker {self.name} is open")
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
            
        except self.expected_exception as e:
            self._on_failure()
            logger.error(f"Circuit breaker {self.name} recorded failure: {e}")
            raise
    
    def get_state(self) -> CircuitState:
        """Get current circuit breaker state"""
        state_str = cache.get(self.state_key, CircuitState.CLOSED.value)
        return CircuitState(state_str)
    
    def _set_state(self, state: CircuitState):
        """Set circuit breaker state"""
        cache.set(self.state_key, state.value, timeout=3600)  # 1 hour
    
    def get_failure_count(self) -> int:
        """Get current failure count"""
        return cache.get(self.failure_count_key, 0)
    
    def _increment_failure_count(self):
        """Increment failure count"""
        current_count = self.get_failure_count()
        cache.set(self.failure_count_key, current_count + 1, timeout=3600)
        cache.set(self.last_failure_key, time.time(), timeout=3600)
    
    def _reset_failure_count(self):
        """Reset failure count"""
        cache.delete(self.failure_count_key)
        cache.delete(self.last_failure_key)
    
    def _should_attempt_reset(self) -> bool:
        """Check if we should attempt to reset the circuit breaker"""
        last_failure_time = cache.get(self.last_failure_key, 0)
        return time.time() - last_failure_time >= self.timeout
    
    def _on_success(self):
        """Handle successful call"""
        state = self.get_state()
        
        if state == CircuitState.HALF_OPEN:
            self._set_state(CircuitState.CLOSED)
            self._reset_failure_count()
            logger.info(f"Circuit breaker {self.name} reset to CLOSED state")
        elif state == CircuitState.CLOSED:
            # Reset failure count on successful call
            self._reset_failure_count()
    
    def _on_failure(self):
        """Handle failed call"""
        self._increment_failure_count()
        failure_count = self.get_failure_count()
        
        if failure_count >= self.failure_threshold:
            self._set_state(CircuitState.OPEN)
            logger.error(
                f"Circuit breaker {self.name} opened after {failure_count} failures"
            )
    
    def force_open(self):
        """Manually open the circuit breaker"""
        self._set_state(CircuitState.OPEN)
        logger.warning(f"Circuit breaker {self.name} manually opened")
    
    def force_close(self):
        """Manually close the circuit breaker"""
        self._set_state(CircuitState.CLOSED)
        self._reset_failure_count()
        logger.info(f"Circuit breaker {self.name} manually closed")
    
    def get_stats(self) -> dict:
        """Get circuit breaker statistics"""
        return {
            'name': self.name,
            'state': self.get_state().value,
            'failure_count': self.get_failure_count(),
            'failure_threshold': self.failure_threshold,
            'timeout': self.timeout,
            'last_failure': cache.get(self.last_failure_key, 0)
        }

# Pre-configured circuit breakers for common external services
financial_api_breaker = CircuitBreaker(
    "financial_api",
    failure_threshold=5,
    timeout=60,
    expected_exception=(Exception,)
)

email_service_breaker = CircuitBreaker(
    "email_service", 
    failure_threshold=3,
    timeout=30,
    expected_exception=(Exception,)
)

bridge_agent_breaker = CircuitBreaker(
    "bridge_agent",
    failure_threshold=10,
    timeout=120,
    expected_exception=(Exception,)
)

def get_circuit_breaker_stats() -> list:
    """Get statistics for all circuit breakers"""
    breakers = [financial_api_breaker, email_service_breaker, bridge_agent_breaker]
    return [breaker.get_stats() for breaker in breakers]