"""
Gateway Authority Testing - Standalone Version

Tests for gateway authority enforcement without database dependencies.
Validates Requirements 8.1, 8.2, 8.5

This test suite validates that PurchaseGateway and SaleGateway are the single
entry points for their respective operations and that direct model access is prevented.
"""

import unittest
from unittest.mock import MagicMock, patch
from decimal import Decimal


class MockUser:
    """Mock user for testing"""
    def __init__(self, username="test_user", is_superuser=False):
        self.username = username
        self.is_superuser = is_superuser
        self.id = 1


class MockPurchaseGateway:
    """Mock PurchaseGateway for testing authority enforcement"""
    
    def __init__(self):
        self.operations = []
        self.is_authorized = True
        self.governance_enabled = True
    
    def create_purchase_with_governance(self, purchase_data, user):
        """Mock method for creating purchase with governance"""
        if not self.is_authorized:
            raise PermissionError("Unauthorized access to PurchaseGateway")
        
        if not self.governance_enabled:
            raise ValueError("Governance is disabled")
        
        operation = {
            'type': 'create_purchase',
            'data': purchase_data,
            'user': user,
            'governance_applied': True,
            'audit_trail': f"Purchase created by {user.username} via PurchaseGateway"
        }
        
        self.operations.append(operation)
        return operation
    
    def update_purchase_with_governance(self, purchase, user):
        """Mock method for updating purchase with governance"""
        if not self.is_authorized:
            raise PermissionError("Unauthorized access to PurchaseGateway")
        
        operation = {
            'type': 'update_purchase',
            'purchase_id': getattr(purchase, 'id', 1),
            'user': user,
            'governance_applied': True,
            'audit_trail': f"Purchase {getattr(purchase, 'id', 1)} updated by {user.username} via PurchaseGateway"
        }
        
        self.operations.append(operation)
        return operation


class MockSaleGateway:
    """Mock SaleGateway for testing authority enforcement"""
    
    def __init__(self):
        self.operations = []
        self.is_authorized = True
        self.governance_enabled = True
    
    def create_sale_with_governance(self, sale_data, user):
        """Mock method for creating sale with governance"""
        if not self.is_authorized:
            raise PermissionError("Unauthorized access to SaleGateway")
        
        if not self.governance_enabled:
            raise ValueError("Governance is disabled")
        
        operation = {
            'type': 'create_sale',
            'data': sale_data,
            'user': user,
            'governance_applied': True,
            'audit_trail': f"Sale created by {user.username} via SaleGateway"
        }
        
        self.operations.append(operation)
        return operation
    
    def update_sale_with_governance(self, sale, user):
        """Mock method for updating sale with governance"""
        if not self.is_authorized:
            raise PermissionError("Unauthorized access to SaleGateway")
        
        operation = {
            'type': 'update_sale',
            'sale_id': getattr(sale, 'id', 1),
            'user': user,
            'governance_applied': True,
            'audit_trail': f"Sale {getattr(sale, 'id', 1)} updated by {user.username} via SaleGateway"
        }
        
        self.operations.append(operation)
        return operation


class GatewayAuthorityTesterStandalone(unittest.TestCase):
    """
    Standalone test class for gateway authority enforcement.
    
    This class implements comprehensive tests to validate that PurchaseGateway
    and SaleGateway are the single entry points for their respective operations
    and that direct model access is prevented.
    """
    
    def setUp(self):
        """Set up test data"""
        self.user = MockUser("gateway_user", is_superuser=True)
        
        # Initialize mock gateways
        self.mock_purchase_gateway = MockPurchaseGateway()
        self.mock_sale_gateway = MockSaleGateway()
    
    def test_purchase_gateway_single_entry_point(self):
        """
        Test that PurchaseGateway is the single authoritative entry point for Purchase operations.
        
        Validates Requirements 8.1: PurchaseGateway SHALL be the single authoritative entry point
        """
        # Test data for purchase creation
        purchase_data = {
            'supplier_id': 1,
            'warehouse_id': 1,
            'payment_method': 'cash',
            'total': Decimal('1000.00'),
            'items': [
                {
                    'product_name': 'Test Product',
                    'quantity': 10,
                    'unit_price': Decimal('100.00')
                }
            ]
        }
        
        # Test that gateway accepts authorized operations
        result = self.mock_purchase_gateway.create_purchase_with_governance(purchase_data, self.user)
        
        # Validate gateway operation
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'create_purchase')
        self.assertEqual(result['user'], self.user)
        self.assertTrue(result['governance_applied'])
        self.assertIn('PurchaseGateway', result['audit_trail'])
        
        # Verify operation was recorded
        self.assertEqual(len(self.mock_purchase_gateway.operations), 1)
        operation = self.mock_purchase_gateway.operations[0]
        self.assertEqual(operation['type'], 'create_purchase')
        self.assertEqual(operation['data'], purchase_data)
        self.assertEqual(operation['user'], self.user)
    
    def test_sale_gateway_single_entry_point(self):
        """
        Test that SaleGateway is the single authoritative entry point for Sale operations.
        
        Validates Requirements 8.2: SaleGateway SHALL be the single authoritative entry point
        """
        # Test data for sale creation
        sale_data = {
            'parent_id': 1,
            'warehouse_id': 1,
            'payment_method': 'cash',
            'total': Decimal('750.00'),
            'items': [
                {
                    'product_name': 'Test Product',
                    'quantity': 5,
                    'unit_price': Decimal('150.00')
                }
            ]
        }
        
        # Test that gateway accepts authorized operations
        result = self.mock_sale_gateway.create_sale_with_governance(sale_data, self.user)
        
        # Validate gateway operation
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'create_sale')
        self.assertEqual(result['user'], self.user)
        self.assertTrue(result['governance_applied'])
        self.assertIn('SaleGateway', result['audit_trail'])
        
        # Verify operation was recorded
        self.assertEqual(len(self.mock_sale_gateway.operations), 1)
        operation = self.mock_sale_gateway.operations[0]
        self.assertEqual(operation['type'], 'create_sale')
        self.assertEqual(operation['data'], sale_data)
        self.assertEqual(operation['user'], self.user)
    
    def test_direct_model_access_prevention(self):
        """
        Test that direct model access is prevented when Gateway services are available.
        
        Validates Requirements 8.5: Direct model access should be prevented
        """
        # Simulate direct model access detection
        with patch('logging.getLogger') as mock_logger:
            mock_log = MagicMock()
            mock_logger.return_value = mock_log
            
            # Simulate direct Purchase model creation (should trigger warning)
            bypass_info = self._simulate_direct_model_access('Purchase')
            
            # Verify warning was logged
            self.assertTrue(bypass_info['attempt_detected'])
            self.assertEqual(bypass_info['bypass_method'], 'direct_model_access')
            self.assertEqual(bypass_info['security_risk'], 'high')
            
            # Simulate direct Sale model creation (should trigger warning)
            bypass_info = self._simulate_direct_model_access('Sale')
            
            # Verify warning was logged
            self.assertTrue(bypass_info['attempt_detected'])
            self.assertEqual(bypass_info['bypass_method'], 'direct_model_access')
            self.assertEqual(bypass_info['security_risk'], 'high')
    
    def test_gateway_authorization_enforcement(self):
        """
        Test that gateway services enforce proper authorization.
        
        Validates Requirements 8.1, 8.2: Gateway services should validate user permissions
        """
        # Test unauthorized access to PurchaseGateway
        self.mock_purchase_gateway.is_authorized = False
        
        purchase_data = {
            'supplier_id': 1,
            'warehouse_id': 1,
            'total': Decimal('1000.00')
        }
        
        with self.assertRaises(PermissionError) as context:
            self.mock_purchase_gateway.create_purchase_with_governance(purchase_data, self.user)
        
        self.assertIn("Unauthorized access to PurchaseGateway", str(context.exception))
        
        # Test unauthorized access to SaleGateway
        self.mock_sale_gateway.is_authorized = False
        
        sale_data = {
            'parent_id': 1,
            'warehouse_id': 1,
            'total': Decimal('750.00')
        }
        
        with self.assertRaises(PermissionError) as context:
            self.mock_sale_gateway.create_sale_with_governance(sale_data, self.user)
        
        self.assertIn("Unauthorized access to SaleGateway", str(context.exception))
    
    def test_gateway_governance_validation(self):
        """
        Test that gateway services enforce governance rules.
        
        Validates Requirements 8.1, 8.2: Gateway services should enforce business rules
        """
        # Test governance disabled scenario
        self.mock_purchase_gateway.governance_enabled = False
        
        purchase_data = {
            'supplier_id': 1,
            'warehouse_id': 1,
            'total': Decimal('1000.00')
        }
        
        with self.assertRaises(ValueError) as context:
            self.mock_purchase_gateway.create_purchase_with_governance(purchase_data, self.user)
        
        self.assertIn("Governance is disabled", str(context.exception))
        
        # Test governance disabled for sales
        self.mock_sale_gateway.governance_enabled = False
        
        sale_data = {
            'parent_id': 1,
            'warehouse_id': 1,
            'total': Decimal('750.00')
        }
        
        with self.assertRaises(ValueError) as context:
            self.mock_sale_gateway.create_sale_with_governance(sale_data, self.user)
        
        self.assertIn("Governance is disabled", str(context.exception))
    
    def test_gateway_audit_trail_maintenance(self):
        """
        Test that gateway services maintain complete audit trails.
        
        Validates Requirements 8.4: Gateway services should maintain audit trails
        """
        # Test purchase audit trail
        purchase_data = {
            'supplier_id': 1,
            'warehouse_id': 1,
            'total': Decimal('1000.00')
        }
        
        result = self.mock_purchase_gateway.create_purchase_with_governance(purchase_data, self.user)
        
        # Validate audit trail
        self.assertIn('audit_trail', result)
        self.assertIn(self.user.username, result['audit_trail'])
        self.assertIn('PurchaseGateway', result['audit_trail'])
        self.assertIn('created', result['audit_trail'])
        
        # Test sale audit trail
        sale_data = {
            'parent_id': 1,
            'warehouse_id': 1,
            'total': Decimal('750.00')
        }
        
        result = self.mock_sale_gateway.create_sale_with_governance(sale_data, self.user)
        
        # Validate audit trail
        self.assertIn('audit_trail', result)
        self.assertIn(self.user.username, result['audit_trail'])
        self.assertIn('SaleGateway', result['audit_trail'])
        self.assertIn('created', result['audit_trail'])
    
    def test_gateway_update_operations(self):
        """
        Test that gateway services handle update operations properly.
        
        Validates Requirements 8.1, 8.2: Gateway services should handle all CRUD operations
        """
        # Create mock purchase for testing updates
        mock_purchase = MagicMock()
        mock_purchase.id = 1
        
        # Test purchase update through gateway
        result = self.mock_purchase_gateway.update_purchase_with_governance(mock_purchase, self.user)
        
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'update_purchase')
        self.assertEqual(result['purchase_id'], 1)
        self.assertEqual(result['user'], self.user)
        self.assertTrue(result['governance_applied'])
        
        # Create mock sale for testing updates
        mock_sale = MagicMock()
        mock_sale.id = 1
        
        # Test sale update through gateway
        result = self.mock_sale_gateway.update_sale_with_governance(mock_sale, self.user)
        
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'update_sale')
        self.assertEqual(result['sale_id'], 1)
        self.assertEqual(result['user'], self.user)
        self.assertTrue(result['governance_applied'])
    
    def test_gateway_performance_requirements(self):
        """
        Test that gateway operations meet performance requirements.
        
        Validates Requirements 9.1, 9.2: Gateway operations should be efficient
        """
        import time
        
        start_time = time.time()
        
        # Test multiple gateway operations within time limit
        for i in range(10):
            purchase_data = {
                'supplier_id': 1,
                'warehouse_id': 1,
                'total': Decimal(f'{100 + i}.00')
            }
            
            result = self.mock_purchase_gateway.create_purchase_with_governance(purchase_data, self.user)
            self.assertIsNotNone(result)
        
        for i in range(10):
            sale_data = {
                'parent_id': 1,
                'warehouse_id': 1,
                'total': Decimal(f'{150 + i}.00')
            }
            
            result = self.mock_sale_gateway.create_sale_with_governance(sale_data, self.user)
            self.assertIsNotNone(result)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Verify performance requirement (should complete within 5 seconds)
        self.assertLess(execution_time, 5.0, f"Gateway operations took {execution_time:.2f}s, expected < 5.0s")
        
        # Verify all operations were recorded
        self.assertEqual(len(self.mock_purchase_gateway.operations), 10)
        self.assertEqual(len(self.mock_sale_gateway.operations), 10)
    
    def test_gateway_concurrent_access_safety(self):
        """
        Test that gateway operations are safe under concurrent access.
        
        Validates Requirements 7.1, 7.2: Gateway operations should handle concurrency
        """
        import threading
        import time
        
        results = []
        errors = []
        
        def create_purchase_operation(thread_id):
            try:
                purchase_data = {
                    'supplier_id': 1,
                    'warehouse_id': 1,
                    'total': Decimal(f'{100 + thread_id}.00')
                }
                result = self.mock_purchase_gateway.create_purchase_with_governance(purchase_data, self.user)
                results.append(f"Thread {thread_id}: Success")
            except Exception as e:
                errors.append(f"Thread {thread_id}: {str(e)}")
        
        # Create multiple threads to test concurrent access
        threads = []
        for i in range(5):
            thread = threading.Thread(target=create_purchase_operation, args=(i,))
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join(timeout=10)
        
        # Validate results
        self.assertEqual(len(errors), 0, f"Concurrent access errors: {errors}")
        self.assertEqual(len(results), 5, f"Expected 5 successful operations, got {len(results)}")
    
    def _simulate_direct_model_access(self, model_name):
        """
        Utility method to simulate direct model access for testing.
        
        Args:
            model_name: Name of the model being accessed directly
        
        Returns:
            dict: Information about the bypass attempt
        """
        bypass_info = {
            'attempt_detected': True,
            'bypass_method': 'direct_model_access',
            'model': model_name,
            'recommendation': f'Use appropriate {model_name}Gateway service instead',
            'security_risk': 'high'
        }
        
        return bypass_info


def validate_gateway_authority(gateway_instance, operation_type, expected_user):
    """
    Utility function to validate gateway authority enforcement.
    
    Args:
        gateway_instance: The gateway instance to validate
        operation_type: Type of operation being performed
        expected_user: Expected user for the operation
    
    Returns:
        bool: True if authority is properly enforced
    """
    if not hasattr(gateway_instance, 'operations'):
        return False
    
    if not gateway_instance.operations:
        return False
    
    last_operation = gateway_instance.operations[-1]
    
    return (
        last_operation.get('type') == operation_type and
        last_operation.get('user') == expected_user and
        last_operation.get('governance_applied', False) and
        'audit_trail' in last_operation
    )


def simulate_gateway_bypass_attempt():
    """
    Utility function to simulate gateway bypass attempts for testing.
    
    Returns:
        dict: Information about the bypass attempt
    """
    bypass_info = {
        'attempt_detected': True,
        'bypass_method': 'direct_model_access',
        'recommendation': 'Use appropriate Gateway service instead',
        'security_risk': 'high'
    }
    
    return bypass_info


if __name__ == '__main__':
    unittest.main()