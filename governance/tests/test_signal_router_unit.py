"""
Unit tests for SignalRouter that don't require Django database setup.
Tests core functionality without Django model dependencies.
"""

import pytest
import threading
import time
from unittest.mock import Mock, patch

# Import the SignalRouter directly without Django dependencies
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from governance.services.signal_router import SignalRouter
from governance.exceptions import SignalError


class TestSignalRouterUnit:
    """Unit tests for SignalRouter core functionality"""
    
    def setup_method(self):
        """Set up test environment"""
        self.router = SignalRouter(depth_limit=3, enable_audit=False)
    
    def test_initialization(self):
        """Test SignalRouter initialization"""
        router = SignalRouter(depth_limit=5, enable_audit=True)
        
        assert router.depth_limit == 5
        assert router.enable_audit == True
        assert router.global_enabled == True
        assert router.maintenance_mode == False
        assert len(router.call_stack) == 0
    
    def test_global_kill_switch(self):
        """Test global kill switch functionality"""
        # Initially enabled
        assert self.router.global_enabled == True
        
        # Disable globally
        self.router.disable_global_signals("Test disable")
        assert self.router.global_enabled == False
        
        # Re-enable
        self.router.enable_global_signals()
        assert self.router.global_enabled == True
    
    def test_per_signal_kill_switch(self):
        """Test per-signal kill switches"""
        signal_name = "test_signal"
        
        # Initially enabled (default)
        assert self.router.is_signal_enabled(signal_name) == True
        
        # Disable specific signal
        self.router.disable_signal(signal_name, "Test disable")
        assert self.router.is_signal_enabled(signal_name) == False
        
        # Re-enable
        self.router.enable_signal(signal_name)
        assert self.router.is_signal_enabled(signal_name) == True
    
    def test_maintenance_mode(self):
        """Test maintenance mode functionality"""
        # Initially not in maintenance mode
        assert self.router.maintenance_mode == False
        
        # Enter maintenance mode
        self.router.enter_maintenance_mode("Test maintenance")
        assert self.router.maintenance_mode == True
        
        # Exit maintenance mode
        self.router.exit_maintenance_mode()
        assert self.router.maintenance_mode == False
    
    def test_signal_handler_registration(self):
        """Test signal handler registration and unregistration"""
        signal_name = "test_signal"
        
        def test_handler(sender, instance=None, **kwargs):
            return "handler_result"
        
        # Register handler
        self.router.register_handler(
            signal_name, 
            test_handler, 
            critical=True, 
            description="Test handler"
        )
        
        stats = self.router.get_signal_statistics()
        assert stats['registered_handlers'][signal_name] == 1
        
        # Unregister handler
        removed = self.router.unregister_handler(signal_name, test_handler)
        assert removed == True
        
        stats = self.router.get_signal_statistics()
        assert stats['registered_handlers'].get(signal_name, 0) == 0
    
    def test_depth_limiting(self):
        """Test signal chain depth limiting"""
        signal_name = "recursive_signal"
        
        def recursive_handler(sender, instance=None, **kwargs):
            # Try to route the same signal again (would cause infinite recursion)
            return self.router.route_signal(signal_name, sender, instance)
        
        self.router.register_handler(signal_name, recursive_handler, description="Recursive handler")
        
        # First call should work
        result = self.router.route_signal(signal_name, Mock())
        assert result['success'] == True
        assert result['handlers_executed'] == 1
        
        # The recursive call should be blocked due to depth limit
        # Check that the handler result contains a blocked signal
        handler_result = result['handler_results'][0]['result']
        assert handler_result['blocked'] == True
        assert 'depth_limit_exceeded' in handler_result['block_reason']
    
    def test_circular_signal_detection(self):
        """Test detection of circular signal chains"""
        # Fill call stack to simulate circular chain
        self.router.call_stack.extend(['signal_a', 'signal_b', 'signal_c'])
        
        # Try to route signal_b again (circular)
        result = self.router.route_signal('signal_b', Mock())
        
        assert result['blocked'] == True
        assert 'circular_signal_chain_detected' in result['block_reason']
    
    def test_signal_routing_with_global_disable(self):
        """Test signal routing when globally disabled"""
        signal_name = "test_signal"
        
        def test_handler(sender, instance=None, **kwargs):
            return "should_not_execute"
        
        self.router.register_handler(signal_name, test_handler, description="Test handler")
        
        # Disable globally
        self.router.disable_global_signals("Test")
        
        # Route signal - should be blocked
        result = self.router.route_signal(signal_name, Mock())
        
        assert result['blocked'] == True
        assert result['block_reason'] == 'global_kill_switch_active'
        assert result['handlers_executed'] == 0
        assert result['success'] == True  # Non-critical signals succeed when blocked
    
    def test_signal_routing_with_signal_disable(self):
        """Test signal routing when specific signal is disabled"""
        signal_name = "test_signal"
        
        def test_handler(sender, instance=None, **kwargs):
            return "should_not_execute"
        
        self.router.register_handler(signal_name, test_handler, description="Test handler")
        
        # Disable specific signal
        self.router.disable_signal(signal_name, "Test")
        
        # Route signal - should be blocked
        result = self.router.route_signal(signal_name, Mock())
        
        assert result['blocked'] == True
        assert result['block_reason'] == 'signal_disabled'
        assert result['handlers_executed'] == 0
    
    def test_maintenance_mode_blocking(self):
        """Test that maintenance mode blocks non-critical signals"""
        signal_name = "test_signal"
        
        def non_critical_handler(sender, instance=None, **kwargs):
            return "should_not_execute"
        
        def critical_handler(sender, instance=None, **kwargs):
            return "should_execute"
        
        self.router.register_handler(signal_name, non_critical_handler, critical=False, description="Non-critical")
        self.router.register_handler(signal_name, critical_handler, critical=True, description="Critical")
        
        # Enter maintenance mode
        self.router.enter_maintenance_mode("Test")
        
        # Route non-critical signal - should be blocked
        result = self.router.route_signal(signal_name, Mock(), critical=False)
        assert result['blocked'] == True
        assert result['block_reason'] == 'maintenance_mode_active'
        
        # Route critical signal - should execute
        result = self.router.route_signal(signal_name, Mock(), critical=True)
        assert result['blocked'] == False
        assert result['success'] == True
        # Only critical handler should execute
        assert result['handlers_executed'] == 1
    
    def test_handler_execution_success(self):
        """Test successful handler execution"""
        signal_name = "test_signal"
        
        def handler1(sender, instance=None, **kwargs):
            return "result1"
        
        def handler2(sender, instance=None, **kwargs):
            return "result2"
        
        self.router.register_handler(signal_name, handler1, description="Handler 1")
        self.router.register_handler(signal_name, handler2, description="Handler 2")
        
        result = self.router.route_signal(signal_name, Mock())
        
        assert result['success'] == True
        assert result['blocked'] == False
        assert result['handlers_executed'] == 2
        assert result['handlers_failed'] == 0
        
        # Check handler results
        assert len(result['handler_results']) == 2
        assert all(hr['success'] for hr in result['handler_results'])
    
    def test_handler_execution_with_failure(self):
        """Test handler execution when some handlers fail"""
        signal_name = "test_signal"
        
        def good_handler(sender, instance=None, **kwargs):
            return "success"
        
        def bad_handler(sender, instance=None, **kwargs):
            raise ValueError("Handler error")
        
        self.router.register_handler(signal_name, good_handler, description="Good handler")
        self.router.register_handler(signal_name, bad_handler, description="Bad handler")
        
        result = self.router.route_signal(signal_name, Mock())
        
        assert result['success'] == True  # Overall success despite handler failure
        assert result['handlers_executed'] == 1
        assert result['handlers_failed'] == 1
        
        # Check that one succeeded and one failed
        success_count = sum(1 for hr in result['handler_results'] if hr['success'])
        failure_count = sum(1 for hr in result['handler_results'] if not hr['success'])
        assert success_count == 1
        assert failure_count == 1
    
    def test_signal_context_manager(self):
        """Test signal context manager"""
        signal_name = "test_signal"
        
        # Test successful context
        with self.router.signal_context(signal_name) as can_proceed:
            assert can_proceed == True
            assert signal_name in self.router.call_stack
        
        # Call stack should be cleaned up
        assert signal_name not in self.router.call_stack
        
        # Test blocked context
        self.router.disable_signal(signal_name, "Test")
        
        with self.router.signal_context(signal_name) as can_proceed:
            assert can_proceed == False
    
    def test_signal_context_manager_critical_blocked(self):
        """Test signal context manager with critical signal blocked"""
        signal_name = "critical_signal"
        
        # Disable signal
        self.router.disable_signal(signal_name, "Test")
        
        # Critical signal should raise exception when blocked
        with pytest.raises(SignalError):
            with self.router.signal_context(signal_name, critical=True):
                pass
    
    def test_thread_safety_call_stack(self):
        """Test thread-safe call stack management"""
        results = {}
        
        def thread_worker(thread_id):
            signal_name = f"thread_signal_{thread_id}"
            
            def handler(sender, instance=None, **kwargs):
                # Record the call stack from this thread's perspective
                results[thread_id] = self.router.call_stack.copy()
                return f"result_{thread_id}"
            
            router = SignalRouter(enable_audit=False)
            router.register_handler(signal_name, handler, description=f"Handler {thread_id}")
            router.route_signal(signal_name, Mock())
        
        # Start multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=thread_worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Each thread should have seen its own signal in the call stack
        for thread_id in range(5):
            expected_signal = f"thread_signal_{thread_id}"
            assert expected_signal in results[thread_id]
    
    def test_statistics_tracking(self):
        """Test statistics tracking"""
        signal_name = "test_signal"
        
        def test_handler(sender, instance=None, **kwargs):
            return "result"
        
        self.router.register_handler(signal_name, test_handler, description="Test handler")
        
        # Initial stats
        initial_stats = self.router.get_signal_statistics()
        initial_processed = initial_stats['counters']['signals_processed']
        
        # Route some signals
        self.router.route_signal(signal_name, Mock())
        self.router.route_signal(signal_name, Mock())
        
        # Block one signal
        self.router.disable_signal(signal_name, "Test")
        self.router.route_signal(signal_name, Mock())
        
        # Check updated stats
        final_stats = self.router.get_signal_statistics()
        
        assert final_stats['counters']['signals_processed'] == initial_processed + 3
        assert final_stats['counters']['signals_blocked'] >= 1
    
    def test_statistics_reset(self):
        """Test statistics reset functionality"""
        signal_name = "test_signal"
        
        def test_handler(sender, instance=None, **kwargs):
            return "result"
        
        self.router.register_handler(signal_name, test_handler, description="Test handler")
        
        # Generate some activity
        self.router.route_signal(signal_name, Mock())
        
        # Verify stats are non-zero
        stats = self.router.get_signal_statistics()
        assert stats['counters']['signals_processed'] > 0
        
        # Reset stats
        self.router.reset_statistics()
        
        # Verify stats are reset
        stats = self.router.get_signal_statistics()
        assert stats['counters']['signals_processed'] == 0
        assert stats['counters']['signals_blocked'] == 0
        assert stats['counters']['signal_errors'] == 0
    
    def test_configuration_validation(self):
        """Test configuration validation"""
        # Valid configuration
        valid_router = SignalRouter(depth_limit=5)
        errors = valid_router.validate_configuration()
        assert len(errors) == 0
        
        # Invalid depth limit
        invalid_router = SignalRouter(depth_limit=0)
        errors = invalid_router.validate_configuration()
        assert len(errors) > 0
        assert any("depth_limit" in error for error in errors)
        
        # Excessive depth limit
        excessive_router = SignalRouter(depth_limit=25)
        errors = excessive_router.validate_configuration()
        assert len(errors) > 0
        assert any("Excessive depth_limit" in error for error in errors)


class TestSignalRouterProperties:
    """Property-based tests for SignalRouter correctness"""
    
    def test_signal_depth_limiting_property(self):
        """
        Property: Signal chain depth should never exceed configured limit
        **Validates: Requirements 9.6**
        """
        router = SignalRouter(depth_limit=3, enable_audit=False)
        
        def recursive_handler(sender, instance=None, **kwargs):
            # Try to trigger the same signal recursively
            return router.route_signal("recursive_signal", sender)
        
        router.register_handler("recursive_signal", recursive_handler, description="Recursive")
        
        # Start the recursive chain
        result = router.route_signal("recursive_signal", Mock())
        
        # The chain should be limited and not cause infinite recursion
        assert result['success']
        assert result['call_stack_depth'] <= router.depth_limit
    
    def test_signal_independence_property(self):
        """
        Property: Signal failures should not affect main operation success
        **Validates: Requirements 9.7**
        """
        router = SignalRouter(enable_audit=False)
        
        def always_failing_handler(sender, instance=None, **kwargs):
            raise Exception("Always fails")
        
        router.register_handler("failing_signal", always_failing_handler, description="Always fails")
        
        # Route the failing signal
        result = router.route_signal("failing_signal", Mock(), critical=False)
        
        # Non-critical signal failure should not break the routing
        assert result['success']  # Routing succeeded
        assert result['handlers_failed'] > 0  # But handler failed
    
    def test_kill_switch_effectiveness_property(self):
        """
        Property: When kill switches are active, signals should be blocked
        **Validates: Requirements 9.2**
        """
        router = SignalRouter(enable_audit=False)
        
        def should_not_execute(sender, instance=None, **kwargs):
            return "should_not_be_called"
        
        router.register_handler("blocked_signal", should_not_execute, description="Should not execute")
        
        # Test global kill switch
        router.disable_global_signals("Test")
        result = router.route_signal("blocked_signal", Mock())
        
        assert result['blocked']
        assert result['handlers_executed'] == 0
        
        # Test per-signal kill switch
        router.enable_global_signals()
        router.disable_signal("blocked_signal", "Test")
        result = router.route_signal("blocked_signal", Mock())
        
        assert result['blocked']
        assert result['handlers_executed'] == 0
    
    def test_thread_safety_property(self):
        """
        Property: Concurrent signal routing should be thread-safe
        **Validates: Requirements 9.1**
        """
        router = SignalRouter(enable_audit=False)
        results = []
        
        def thread_safe_handler(sender, instance=None, **kwargs):
            # Simulate some work
            time.sleep(0.01)
            return f"thread_{threading.current_thread().ident}"
        
        router.register_handler("concurrent_signal", thread_safe_handler, description="Thread safe")
        
        def worker():
            result = router.route_signal("concurrent_signal", Mock())
            results.append(result)
        
        # Start multiple threads
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # All threads should have completed successfully
        assert len(results) == 10
        assert all(result['success'] for result in results)
        assert all(result['handlers_executed'] == 1 for result in results)


if __name__ == "__main__":
    # Run tests manually if executed directly
    import unittest
    
    # Convert pytest-style tests to unittest
    suite = unittest.TestSuite()
    
    # Add test methods
    test_class = TestSignalRouterUnit()
    test_methods = [method for method in dir(test_class) if method.startswith('test_')]
    
    for method_name in test_methods:
        suite.addTest(unittest.FunctionTestCase(getattr(test_class, method_name)))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print(f"\nTests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    if result.failures:
        print("\nFailures:")
        for test, traceback in result.failures:
            print(f"  {test}: {traceback}")
    
    if result.errors:
        print("\nErrors:")
        for test, traceback in result.errors:
            print(f"  {test}: {traceback}")