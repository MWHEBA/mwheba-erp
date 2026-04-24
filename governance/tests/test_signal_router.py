"""
Comprehensive tests for SignalRouter with governance controls.
Tests thread-safety, kill switches, depth limiting, and monitoring.
"""

import pytest
import threading
import time
from unittest.mock import Mock, patch
from django.test import TestCase
from django.contrib.auth import get_user_model

from governance.services.signal_router import SignalRouter, signal_router
from governance.exceptions import SignalError
from governance.models import GovernanceContext

User = get_user_model()


class TestSignalRouter(TestCase):
    """Test SignalRouter functionality"""
    
    def setUp(self):
        """Set up test environment"""
        self.router = SignalRouter(depth_limit=3, enable_audit=False)  # Disable audit for cleaner tests
        self.test_user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Set governance context
        GovernanceContext.set_context(user=self.test_user, service='TestService')
    
    def tearDown(self):
        """Clean up after tests"""
        GovernanceContext.clear_context()
    
    def test_initialization(self):
        """Test SignalRouter initialization"""
        router = SignalRouter(depth_limit=5, enable_audit=True)
        
        self.assertEqual(router.depth_limit, 5)
        self.assertTrue(router.enable_audit)
        self.assertTrue(router.global_enabled)
        self.assertFalse(router.maintenance_mode)
        self.assertEqual(len(router.call_stack), 0)
    
    def test_global_kill_switch(self):
        """Test global kill switch functionality"""
        # Initially enabled
        self.assertTrue(self.router.global_enabled)
        
        # Disable globally
        self.router.disable_global_signals("Test disable")
        self.assertFalse(self.router.global_enabled)
        
        # Re-enable
        self.router.enable_global_signals()
        self.assertTrue(self.router.global_enabled)
    
    def test_per_signal_kill_switch(self):
        """Test per-signal kill switches"""
        signal_name = "test_signal"
        
        # Initially enabled (default)
        self.assertTrue(self.router.is_signal_enabled(signal_name))
        
        # Disable specific signal
        self.router.disable_signal(signal_name, "Test disable")
        self.assertFalse(self.router.is_signal_enabled(signal_name))
        
        # Re-enable
        self.router.enable_signal(signal_name)
        self.assertTrue(self.router.is_signal_enabled(signal_name))
    
    def test_maintenance_mode(self):
        """Test maintenance mode functionality"""
        # Initially not in maintenance mode
        self.assertFalse(self.router.maintenance_mode)
        
        # Enter maintenance mode
        self.router.enter_maintenance_mode("Test maintenance")
        self.assertTrue(self.router.maintenance_mode)
        
        # Exit maintenance mode
        self.router.exit_maintenance_mode()
        self.assertFalse(self.router.maintenance_mode)
    
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
        self.assertEqual(stats['registered_handlers'][signal_name], 1)
        
        # Unregister handler
        removed = self.router.unregister_handler(signal_name, test_handler)
        self.assertTrue(removed)
        
        stats = self.router.get_signal_statistics()
        self.assertEqual(stats['registered_handlers'].get(signal_name, 0), 0)
    
    def test_depth_limiting(self):
        """Test signal chain depth limiting"""
        signal_name = "recursive_signal"
        
        def recursive_handler(sender, instance=None, **kwargs):
            # Try to route the same signal again (would cause infinite recursion)
            return self.router.route_signal(signal_name, sender, instance)
        
        self.router.register_handler(signal_name, recursive_handler, description="Recursive handler")
        
        # First call should work
        result = self.router.route_signal(signal_name, Mock())
        self.assertTrue(result['success'])
        self.assertEqual(result['handlers_executed'], 1)
        
        # The recursive call should be blocked due to depth limit
        # Check that the handler result contains a blocked signal
        handler_result = result['handler_results'][0]['result']
        self.assertTrue(handler_result['blocked'])
        self.assertIn('depth_limit_exceeded', handler_result['block_reason'])
    
    def test_circular_signal_detection(self):
        """Test detection of circular signal chains"""
        # Fill call stack to simulate circular chain
        self.router.call_stack.extend(['signal_a', 'signal_b', 'signal_c'])
        
        # Try to route signal_b again (circular)
        result = self.router.route_signal('signal_b', Mock())
        
        self.assertTrue(result['blocked'])
        self.assertIn('circular_signal_chain_detected', result['block_reason'])
    
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
        
        self.assertTrue(result['blocked'])
        self.assertEqual(result['block_reason'], 'global_kill_switch_active')
        self.assertEqual(result['handlers_executed'], 0)
        self.assertTrue(result['success'])  # Non-critical signals succeed when blocked
    
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
        
        self.assertTrue(result['blocked'])
        self.assertEqual(result['block_reason'], 'signal_disabled')
        self.assertEqual(result['handlers_executed'], 0)
    
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
        self.assertTrue(result['blocked'])
        self.assertEqual(result['block_reason'], 'maintenance_mode_active')
        
        # Route critical signal - should execute
        result = self.router.route_signal(signal_name, Mock(), critical=True)
        self.assertFalse(result['blocked'])
        self.assertTrue(result['success'])
        # Only critical handler should execute
        self.assertEqual(result['handlers_executed'], 1)
    
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
        
        self.assertTrue(result['success'])
        self.assertFalse(result['blocked'])
        self.assertEqual(result['handlers_executed'], 2)
        self.assertEqual(result['handlers_failed'], 0)
        
        # Check handler results
        self.assertEqual(len(result['handler_results']), 2)
        self.assertTrue(all(hr['success'] for hr in result['handler_results']))
    
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
        
        self.assertTrue(result['success'])  # Overall success despite handler failure
        self.assertEqual(result['handlers_executed'], 1)
        self.assertEqual(result['handlers_failed'], 1)
        
        # Check that one succeeded and one failed
        success_count = sum(1 for hr in result['handler_results'] if hr['success'])
        failure_count = sum(1 for hr in result['handler_results'] if not hr['success'])
        self.assertEqual(success_count, 1)
        self.assertEqual(failure_count, 1)
    
    def test_critical_signal_failure_propagation(self):
        """Test that critical signal failures are handled appropriately"""
        signal_name = "critical_signal"
        
        def failing_handler(sender, instance=None, **kwargs):
            raise ValueError("Critical failure")
        
        self.router.register_handler(signal_name, failing_handler, critical=True, description="Critical handler")
        
        # Critical signal with handler failure should still succeed at routing level
        # (The handler failure is recorded but doesn't break the signal routing)
        result = self.router.route_signal(signal_name, Mock(), critical=True)
        
        self.assertTrue(result['success'])  # Routing succeeded
        self.assertEqual(result['handlers_failed'], 1)
        self.assertFalse(result['handler_results'][0]['success'])
    
    def test_signal_context_manager(self):
        """Test signal context manager"""
        signal_name = "test_signal"
        
        # Test successful context
        with self.router.signal_context(signal_name) as can_proceed:
            self.assertTrue(can_proceed)
            self.assertIn(signal_name, self.router.call_stack)
        
        # Call stack should be cleaned up
        self.assertNotIn(signal_name, self.router.call_stack)
        
        # Test blocked context
        self.router.disable_signal(signal_name, "Test")
        
        with self.router.signal_context(signal_name) as can_proceed:
            self.assertFalse(can_proceed)
    
    def test_signal_context_manager_critical_blocked(self):
        """Test signal context manager with critical signal blocked"""
        signal_name = "critical_signal"
        
        # Disable signal
        self.router.disable_signal(signal_name, "Test")
        
        # Critical signal should raise exception when blocked
        with self.assertRaises(SignalError):
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
            self.assertIn(expected_signal, results[thread_id])
    
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
        
        self.assertEqual(
            final_stats['counters']['signals_processed'], 
            initial_processed + 3
        )
        self.assertGreaterEqual(final_stats['counters']['signals_blocked'], 1)
    
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
        self.assertGreater(stats['counters']['signals_processed'], 0)
        
        # Reset stats
        self.router.reset_statistics()
        
        # Verify stats are reset
        stats = self.router.get_signal_statistics()
        self.assertEqual(stats['counters']['signals_processed'], 0)
        self.assertEqual(stats['counters']['signals_blocked'], 0)
        self.assertEqual(stats['counters']['signal_errors'], 0)
    
    def test_configuration_validation(self):
        """Test configuration validation"""
        # Valid configuration
        valid_router = SignalRouter(depth_limit=5)
        errors = valid_router.validate_configuration()
        self.assertEqual(len(errors), 0)
        
        # Invalid depth limit
        invalid_router = SignalRouter(depth_limit=0)
        errors = invalid_router.validate_configuration()
        self.assertGreater(len(errors), 0)
        self.assertTrue(any("depth_limit" in error for error in errors))
        
        # Excessive depth limit
        excessive_router = SignalRouter(depth_limit=25)
        errors = excessive_router.validate_configuration()
        self.assertGreater(len(errors), 0)
        self.assertTrue(any("Excessive depth_limit" in error for error in errors))
    
    def test_global_signal_router_instance(self):
        """Test that global signal_router instance works correctly"""
        # The global instance should be available
        self.assertIsInstance(signal_router, SignalRouter)
        
        # Should have default configuration
        self.assertEqual(signal_router.depth_limit, SignalRouter.DEFAULT_DEPTH_LIMIT)
        self.assertTrue(signal_router.global_enabled)
    
    def test_convenience_functions(self):
        """Test convenience functions"""
        from governance.services.signal_router import (
            route_signal, disable_all_signals, enable_all_signals,
            signals_disabled, maintenance_mode, register_signal_handler,
            get_signal_statistics
        )
        
        # Test route_signal function
        result = route_signal("test_signal", Mock())
        self.assertIn('success', result)
        
        # Test disable/enable all signals
        disable_all_signals("Test disable")
        self.assertFalse(signal_router.global_enabled)
        
        enable_all_signals()
        self.assertTrue(signal_router.global_enabled)
        
        # Test signals_disabled context manager
        with signals_disabled("Test context"):
            self.assertFalse(signal_router.global_enabled)
        self.assertTrue(signal_router.global_enabled)
        
        # Test maintenance_mode context manager
        with maintenance_mode("Test maintenance"):
            self.assertTrue(signal_router.maintenance_mode)
        self.assertFalse(signal_router.maintenance_mode)
        
        # Test register_signal_handler
        def test_handler(sender, instance=None, **kwargs):
            return "test"
        
        register_signal_handler("test_signal", test_handler, description="Test")
        stats = get_signal_statistics()
        self.assertIn("test_signal", stats['registered_handlers'])


class TestSignalRouterIntegration(TestCase):
    """Integration tests for SignalRouter with Django signals"""
    
    def setUp(self):
        """Set up test environment"""
        self.test_user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        GovernanceContext.set_context(user=self.test_user, service='TestService')
    
    def tearDown(self):
        """Clean up after tests"""
        GovernanceContext.clear_context()
    
    def test_signal_independence_principle(self):
        """
        Test that signal failures don't break main operations.
        This validates Requirement 9.7: Signal failure MUST NOT break writes.
        """
        signal_name = "side_effect_signal"
        
        def failing_side_effect(sender, instance=None, **kwargs):
            raise Exception("Side effect failed")
        
        # Register a failing side-effect handler
        signal_router.register_handler(
            signal_name, 
            failing_side_effect, 
            critical=False,  # Non-critical side effect
            description="Failing side effect"
        )
        
        # Simulate main operation with side effect
        main_operation_success = True
        
        try:
            # Main operation (e.g., saving a model)
            # ... main operation code ...
            
            # Trigger side effect signal
            result = signal_router.route_signal(signal_name, Mock())
            
            # Signal routing should succeed even though handler failed
            self.assertTrue(result['success'])
            self.assertEqual(result['handlers_failed'], 1)
            
        except Exception:
            main_operation_success = False
        
        # Main operation should not be affected by signal failure
        self.assertTrue(main_operation_success)
    
    def test_critical_vs_non_critical_signals(self):
        """Test difference between critical and non-critical signal handling"""
        critical_signal = "critical_signal"
        non_critical_signal = "non_critical_signal"
        
        def handler(sender, instance=None, **kwargs):
            return "executed"
        
        signal_router.register_handler(critical_signal, handler, critical=True, description="Critical")
        signal_router.register_handler(non_critical_signal, handler, critical=False, description="Non-critical")
        
        # Enter maintenance mode
        signal_router.enter_maintenance_mode("Test")
        
        # Critical signal should execute
        critical_result = signal_router.route_signal(critical_signal, Mock(), critical=True)
        self.assertFalse(critical_result['blocked'])
        self.assertEqual(critical_result['handlers_executed'], 1)
        
        # Non-critical signal should be blocked
        non_critical_result = signal_router.route_signal(non_critical_signal, Mock(), critical=False)
        self.assertTrue(non_critical_result['blocked'])
        self.assertEqual(non_critical_result['handlers_executed'], 0)
        
        # Exit maintenance mode
        signal_router.exit_maintenance_mode()
    
    @patch('governance.services.signal_router.logger')
    def test_comprehensive_logging(self, mock_logger):
        """Test that all signal operations are properly logged"""
        signal_name = "logged_signal"
        
        def test_handler(sender, instance=None, **kwargs):
            return "logged_result"
        
        # Create router with audit enabled
        router = SignalRouter(enable_audit=True)
        router.register_handler(signal_name, test_handler, description="Logged handler")
        
        # Route signal
        result = router.route_signal(signal_name, Mock())
        
        # Verify logging occurred
        self.assertTrue(result['success'])
        # Logger should have been called for various operations
        self.assertTrue(mock_logger.info.called or mock_logger.debug.called)


@pytest.mark.django_db
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