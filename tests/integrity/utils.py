"""
Utility functions and helpers for System Integrity Testing
"""

import time
import threading
from contextlib import contextmanager
from decimal import Decimal
from django.db import transaction, connection
from django.test import override_settings
import logging

logger = logging.getLogger(__name__)


class IntegrityTestUtils:
    """Utility class for integrity testing operations"""
    
    @staticmethod
    def measure_execution_time(func, *args, **kwargs):
        """Measure execution time of a function"""
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            success = True
            error = None
        except Exception as e:
            result = None
            success = False
            error = str(e)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        return {
            'result': result,
            'success': success,
            'error': error,
            'execution_time': execution_time,
            'start_time': start_time,
            'end_time': end_time
        }
    
    @staticmethod
    def validate_smoke_test_timeout(execution_time, max_timeout=60):
        """Validate that smoke test completed within timeout"""
        if execution_time > max_timeout:
            raise AssertionError(
                f"Smoke test exceeded timeout: {execution_time:.2f}s > {max_timeout}s"
            )
        return True
    
    @staticmethod
    def validate_integrity_test_timeout(execution_time, max_timeout=300):
        """Validate that integrity test completed within timeout"""
        if execution_time > max_timeout:
            raise AssertionError(
                f"Integrity test exceeded timeout: {execution_time:.2f}s > {max_timeout}s"
            )
        return True
    
    @staticmethod
    def validate_concurrency_test_timeout(execution_time, max_timeout=600):
        """Validate that concurrency test completed within timeout"""
        if execution_time > max_timeout:
            raise AssertionError(
                f"Concurrency test exceeded timeout: {execution_time:.2f}s > {max_timeout}s"
            )
        return True
    
    @staticmethod
    def check_database_constraint_exists(table_name, constraint_name):
        """Check if a database constraint exists"""
        with connection.cursor() as cursor:
            if connection.vendor == 'sqlite':
                # SQLite constraint checking
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = cursor.fetchall()
                
                # Check for CHECK constraints in table schema
                cursor.execute(f"SELECT sql FROM sqlite_master WHERE name='{table_name}'")
                schema = cursor.fetchone()
                
                if schema and constraint_name.lower() in schema[0].lower():
                    return True
                    
            elif connection.vendor == 'postgresql':
                # PostgreSQL constraint checking
                cursor.execute("""
                    SELECT constraint_name 
                    FROM information_schema.table_constraints 
                    WHERE table_name = %s AND constraint_name = %s
                """, [table_name, constraint_name])
                
                return cursor.fetchone() is not None
        
        return False
    
    @staticmethod
    def force_constraint_violation(model_class, violation_data):
        """Attempt to force a constraint violation for testing"""
        try:
            # Try to create object that violates constraints
            obj = model_class(**violation_data)
            obj.save()
            return False, obj  # No violation occurred
        except Exception as e:
            return True, str(e)  # Violation occurred
    
    @staticmethod
    def run_concurrent_operations(operation_func, thread_count=5, operations_per_thread=10, timeout=30):
        """Run operations concurrently and collect results"""
        results = []
        errors = []
        threads = []
        
        def thread_worker(thread_id):
            thread_results = []
            thread_errors = []
            
            for op_id in range(operations_per_thread):
                try:
                    result = operation_func(thread_id, op_id)
                    thread_results.append(result)
                except Exception as e:
                    thread_errors.append({
                        'thread_id': thread_id,
                        'operation_id': op_id,
                        'error': str(e)
                    })
            
            results.extend(thread_results)
            errors.extend(thread_errors)
        
        # Start threads
        for thread_id in range(thread_count):
            thread = threading.Thread(target=thread_worker, args=(thread_id,))
            threads.append(thread)
            thread.start()
        
        # Wait for completion with timeout
        for thread in threads:
            thread.join(timeout=timeout)
            if thread.is_alive():
                logger.warning(f"Thread {thread.name} did not complete within timeout")
        
        return {
            'results': results,
            'errors': errors,
            'total_operations': thread_count * operations_per_thread,
            'successful_operations': len(results),
            'failed_operations': len(errors)
        }
    
    @staticmethod
    def validate_idempotency_protection(operation_func, idempotency_key, expected_result):
        """Validate that an operation is properly protected by idempotency"""
        # First execution
        result1 = operation_func(idempotency_key)
        
        # Second execution (should return same result)
        result2 = operation_func(idempotency_key)
        
        # Validate results are identical
        if result1 != result2:
            raise AssertionError(
                f"Idempotency violation: first result {result1} != second result {result2}"
            )
        
        # Validate expected result
        if result1 != expected_result:
            raise AssertionError(
                f"Unexpected result: {result1} != expected {expected_result}"
            )
        
        return True
    
    @staticmethod
    def check_admin_permissions(admin_class, user, model_class):
        """Check admin permissions for a user"""
        from django.contrib.admin.sites import site
        from django.test import RequestFactory
        
        factory = RequestFactory()
        request = factory.get('/')
        request.user = user
        
        admin_instance = admin_class(model_class, site)
        
        return {
            'has_add_permission': admin_instance.has_add_permission(request),
            'has_change_permission': admin_instance.has_change_permission(request),
            'has_delete_permission': admin_instance.has_delete_permission(request),
            'has_view_permission': admin_instance.has_view_permission(request)
        }
    
    @staticmethod
    def validate_audit_trail_completeness(operation_type, object_id, expected_operations):
        """Validate that audit trail is complete for an operation"""
        from governance.models import AuditTrail
        
        audit_records = AuditTrail.objects.filter(
            model_name=operation_type,
            object_id=object_id
        ).order_by('timestamp')
        
        if len(audit_records) != len(expected_operations):
            raise AssertionError(
                f"Incomplete audit trail: {len(audit_records)} records != {len(expected_operations)} expected"
            )
        
        for i, (record, expected_op) in enumerate(zip(audit_records, expected_operations)):
            if record.operation != expected_op:
                raise AssertionError(
                    f"Audit trail mismatch at position {i}: {record.operation} != {expected_op}"
                )
        
        return True
    
    @staticmethod
    def validate_data_consistency(purchase_or_sale, expected_stock_movements):
        """Validate data consistency for Purchase/Sale operations"""
        from product.models import StockMovement
        
        # Check stock movements
        if hasattr(purchase_or_sale, 'items'):
            items = purchase_or_sale.items.all()
        else:
            items = []
        
        for item in items:
            movements = StockMovement.objects.filter(
                product=item.product,
                reference_type=purchase_or_sale.__class__.__name__.lower(),
                reference_id=purchase_or_sale.id
            )
            
            if movements.count() != 1:
                raise AssertionError(
                    f"Expected 1 stock movement for {item.product}, found {movements.count()}"
                )
            
            movement = movements.first()
            if abs(movement.quantity) != item.quantity:
                raise AssertionError(
                    f"Stock movement quantity mismatch: {movement.quantity} != {item.quantity}"
                )
        
        return True
    
    @staticmethod
    def create_database_deadlock_scenario():
        """Create a scenario that could cause database deadlocks"""
        # This is a placeholder for deadlock testing
        # Implementation would depend on specific database and models
        pass
    
    @staticmethod
    def validate_governance_invariants():
        """Validate core governance invariants"""
        from product.models import Stock
        from financial.models import JournalEntry, JournalEntryLine
        from django.db.models import Sum
        
        invariant_violations = []
        
        # Invariant 1: Stock.quantity >= 0
        negative_stock = Stock.objects.filter(quantity__lt=0)
        if negative_stock.exists():
            invariant_violations.append(
                f"Negative stock quantities found: {negative_stock.count()} records"
            )
        
        # Invariant 2: Stock.reserved_quantity <= Stock.quantity
        invalid_reserved = Stock.objects.filter(reserved_quantity__gt=models.F('quantity'))
        if invalid_reserved.exists():
            invariant_violations.append(
                f"Invalid reserved quantities found: {invalid_reserved.count()} records"
            )
        
        # Invariant 3: JournalEntry balanced (sum(debit) = sum(credit))
        unbalanced_entries = []
        for entry in JournalEntry.objects.all():
            lines = entry.lines.all()
            total_debit = lines.aggregate(Sum('debit_amount'))['debit_amount__sum'] or Decimal('0')
            total_credit = lines.aggregate(Sum('credit_amount'))['credit_amount__sum'] or Decimal('0')
            
            if total_debit != total_credit:
                unbalanced_entries.append(entry.id)
        
        if unbalanced_entries:
            invariant_violations.append(
                f"Unbalanced journal entries found: {len(unbalanced_entries)} entries"
            )
        
        return invariant_violations


@contextmanager
def performance_monitor(test_name, max_duration=None):
    """Context manager for monitoring test performance"""
    start_time = time.time()
    logger.info(f"Starting performance monitoring for {test_name}")
    
    try:
        yield
    finally:
        end_time = time.time()
        duration = end_time - start_time
        
        logger.info(f"Test {test_name} completed in {duration:.2f} seconds")
        
        if max_duration and duration > max_duration:
            logger.warning(
                f"Test {test_name} exceeded maximum duration: {duration:.2f}s > {max_duration}s"
            )


@contextmanager
def database_isolation():
    """Context manager for database isolation during testing"""
    with transaction.atomic():
        savepoint = transaction.savepoint()
        try:
            yield
        finally:
            transaction.savepoint_rollback(savepoint)


@contextmanager
def governance_context(user, service="IntegrityTestSuite", operation="test"):
    """Context manager for setting governance context"""
    from governance.models import GovernanceContext
    
    GovernanceContext.set_context(
        user=user,
        service=service,
        operation=operation
    )
    
    try:
        yield
    finally:
        GovernanceContext.clear_context()


class AssertionHelpers:
    """Helper methods for common integrity test assertions"""
    
    @staticmethod
    def assert_constraint_violation(func, *args, **kwargs):
        """Assert that a function raises a constraint violation"""
        from django.db import IntegrityError
        from django.core.exceptions import ValidationError
        
        try:
            func(*args, **kwargs)
            raise AssertionError("Expected constraint violation but none occurred")
        except (IntegrityError, ValidationError):
            # Expected behavior
            pass
    
    @staticmethod
    def assert_admin_readonly(admin_class, model_class, user):
        """Assert that admin interface is read-only for a user"""
        permissions = IntegrityTestUtils.check_admin_permissions(
            admin_class, user, model_class
        )
        
        assert not permissions['has_add_permission'], "Admin should not have add permission"
        assert not permissions['has_change_permission'], "Admin should not have change permission"
        assert permissions['has_view_permission'], "Admin should have view permission"
    
    @staticmethod
    def assert_idempotency_protected(operation_func, key, expected_result):
        """Assert that an operation is protected by idempotency"""
        return IntegrityTestUtils.validate_idempotency_protection(
            operation_func, key, expected_result
        )
    
    @staticmethod
    def assert_audit_trail_complete(model_name, object_id, expected_operations):
        """Assert that audit trail is complete"""
        return IntegrityTestUtils.validate_audit_trail_completeness(
            model_name, object_id, expected_operations
        )
    
    @staticmethod
    def assert_data_consistency(purchase_or_sale, expected_movements):
        """Assert data consistency for business operations"""
        return IntegrityTestUtils.validate_data_consistency(
            purchase_or_sale, expected_movements
        )
    
    @staticmethod
    def assert_governance_invariants():
        """Assert that all governance invariants are maintained"""
        violations = IntegrityTestUtils.validate_governance_invariants()
        
        if violations:
            raise AssertionError(
                f"Governance invariant violations found: {'; '.join(violations)}"
            )
        
        return True
    
    @staticmethod
    def assert_stock_movement_consistency(operation, expected_count):
        """Assert that stock movements are consistent with operation"""
        from product.models import StockMovement
        
        movements = StockMovement.objects.filter(
            reference_type=operation.__class__.__name__.lower(),
            reference_id=operation.id
        )
        
        actual_count = movements.count()
        if actual_count != expected_count:
            raise AssertionError(
                f"Expected {expected_count} stock movements, found {actual_count}"
            )
        
        # Validate movement quantities match operation items
        if hasattr(operation, 'items'):
            items = operation.items.all()
            for item in items:
                item_movements = movements.filter(product=item.product)
                if item_movements.count() != 1:
                    raise AssertionError(
                        f"Expected 1 movement for product {item.product}, found {item_movements.count()}"
                    )
                
                movement = item_movements.first()
                if abs(movement.quantity) != item.quantity:
                    raise AssertionError(
                        f"Movement quantity {movement.quantity} doesn't match item quantity {item.quantity}"
                    )
        
        return True
    
    @staticmethod
    def assert_idempotency_record_lifecycle(operation_type, key, expected_status):
        """Assert idempotency record follows proper lifecycle"""
        from governance.models import IdempotencyRecord
        
        try:
            record = IdempotencyRecord.objects.get(
                operation_type=operation_type,
                idempotency_key=key
            )
        except IdempotencyRecord.DoesNotExist:
            raise AssertionError(f"Idempotency record not found for {operation_type}:{key}")
        
        if record.status != expected_status:
            raise AssertionError(
                f"Expected status {expected_status}, found {record.status}"
            )
        
        # Validate lifecycle progression
        if expected_status == 'completed':
            assert record.completed_at is not None, "Completed record should have completed_at timestamp"
            assert record.result_data is not None, "Completed record should have result_data"
        elif expected_status == 'failed':
            assert record.failed_at is not None, "Failed record should have failed_at timestamp"
            assert record.error_message is not None, "Failed record should have error_message"
        
        return True
    
    @staticmethod
    def assert_concurrent_operation_safety(operation_results, expected_success_count):
        """Assert that concurrent operations maintain safety"""
        successful_results = [r for r in operation_results if r.get('success', False)]
        failed_results = [r for r in operation_results if not r.get('success', False)]
        
        if len(successful_results) != expected_success_count:
            raise AssertionError(
                f"Expected {expected_success_count} successful operations, "
                f"found {len(successful_results)}"
            )
        
        # Check for race condition indicators
        duplicate_results = {}
        for result in successful_results:
            result_key = result.get('result_key', 'unknown')
            if result_key in duplicate_results:
                raise AssertionError(
                    f"Duplicate result detected: {result_key} - possible race condition"
                )
            duplicate_results[result_key] = result
        
        return True
    
    @staticmethod
    def assert_performance_within_limits(execution_time, max_time, operation_name):
        """Assert that operation performance is within limits"""
        if execution_time > max_time:
            raise AssertionError(
                f"{operation_name} exceeded time limit: {execution_time:.2f}s > {max_time}s"
            )
        
        return True
    
    @staticmethod
    def assert_database_constraints_enforced(model_class, constraint_violations):
        """Assert that database constraints are properly enforced"""
        from django.db import IntegrityError
        
        for violation_data in constraint_violations:
            try:
                obj = model_class(**violation_data)
                obj.save()
                # If we get here, constraint was not enforced
                raise AssertionError(
                    f"Database constraint not enforced for data: {violation_data}"
                )
            except IntegrityError:
                # Expected behavior - constraint was enforced
                pass
        
        return True
    
    @staticmethod
    def assert_gateway_authority_enforced(gateway_class, unauthorized_operations):
        """Assert that gateway authority is properly enforced"""
        for operation_data in unauthorized_operations:
            try:
                result = gateway_class.execute_operation(**operation_data)
                if result.get('success', False):
                    raise AssertionError(
                        f"Unauthorized operation succeeded: {operation_data}"
                    )
            except PermissionError:
                # Expected behavior - authority enforced
                pass
        
        return True
    
    @staticmethod
    def assert_signal_idempotency_maintained(signal_triggers, expected_side_effects):
        """Assert that signal idempotency is maintained"""
        # Track side effects before and after multiple signal triggers
        initial_count = expected_side_effects['initial_count']
        
        # Trigger signals multiple times
        for _ in range(3):  # Trigger 3 times
            for trigger in signal_triggers:
                trigger()
        
        # Check that side effects only occurred once
        final_count = expected_side_effects['count_function']()
        expected_final = initial_count + expected_side_effects['expected_increment']
        
        if final_count != expected_final:
            raise AssertionError(
                f"Signal idempotency violated: expected {expected_final} side effects, "
                f"found {final_count}"
            )
        
        return True


class MockServices:
    """Mock services for testing without external dependencies"""
    
    @staticmethod
    def mock_gateway_service():
        """Mock gateway service for testing"""
        class MockGateway:
            def __init__(self):
                self.operations = []
            
            def create_with_governance(self, data, user):
                operation = {
                    'data': data,
                    'user': user,
                    'timestamp': time.time()
                }
                self.operations.append(operation)
                return operation
        
        return MockGateway()
    
    @staticmethod
    def mock_idempotency_service():
        """Mock idempotency service for testing"""
        class MockIdempotencyService:
            def __init__(self):
                self.records = {}
            
            def check_and_record_operation(self, operation_type, key, result_data, user):
                full_key = f"{operation_type}:{key}"
                
                if full_key in self.records:
                    return True, self.records[full_key], self.records[full_key]['result_data']
                
                record = {
                    'operation_type': operation_type,
                    'key': key,
                    'result_data': result_data,
                    'user': user,
                    'timestamp': time.time()
                }
                
                self.records[full_key] = record
                return False, record, result_data
        
        return MockIdempotencyService()


# Test result collection utilities
class PostgreSQLContainerManager:
    """PostgreSQL container management utilities for concurrency tests"""
    
    def __init__(self):
        self.container_name = "integrity_test_postgres"
        self.container_port = "5433"
        self.postgres_user = "postgres"
        self.postgres_password = "postgres"
        self.postgres_db = "test_integrity"
        
    def is_docker_available(self):
        """Check if Docker is available"""
        try:
            import subprocess
            result = subprocess.run(['docker', '--version'], 
                                  capture_output=True, text=True, timeout=10)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            return False
    
    def is_container_running(self):
        """Check if PostgreSQL container is running"""
        try:
            import subprocess
            result = subprocess.run(['docker', 'ps', '--filter', f'name={self.container_name}', 
                                   '--format', '{{.Names}}'], 
                                  capture_output=True, text=True, timeout=10)
            return self.container_name in result.stdout
        except (subprocess.TimeoutExpired, Exception):
            return False
    
    def start_container(self):
        """Start PostgreSQL container for testing"""
        if not self.is_docker_available():
            raise RuntimeError("Docker is not available. Cannot start PostgreSQL container.")
        
        if self.is_container_running():
            logger.info(f"PostgreSQL container {self.container_name} is already running")
            return True
        
        try:
            import subprocess
            
            # Stop and remove existing container if it exists
            subprocess.run(['docker', 'stop', self.container_name], 
                         capture_output=True, timeout=10)
            subprocess.run(['docker', 'rm', self.container_name], 
                         capture_output=True, timeout=10)
            
            # Start new container
            cmd = [
                'docker', 'run', '-d',
                '--name', self.container_name,
                '-p', f'{self.container_port}:5432',
                '-e', f'POSTGRES_USER={self.postgres_user}',
                '-e', f'POSTGRES_PASSWORD={self.postgres_password}',
                '-e', f'POSTGRES_DB={self.postgres_db}',
                'postgres:13-alpine'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode != 0:
                raise RuntimeError(f"Failed to start PostgreSQL container: {result.stderr}")
            
            # Wait for container to be ready
            self.wait_for_container_ready()
            
            logger.info(f"PostgreSQL container {self.container_name} started successfully")
            return True
            
        except subprocess.TimeoutExpired:
            raise RuntimeError("Timeout starting PostgreSQL container")
        except Exception as e:
            raise RuntimeError(f"Error starting PostgreSQL container: {e}")
    
    def stop_container(self):
        """Stop PostgreSQL container"""
        if not self.is_container_running():
            logger.info(f"PostgreSQL container {self.container_name} is not running")
            return True
        
        try:
            import subprocess
            
            result = subprocess.run(['docker', 'stop', self.container_name], 
                                  capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                logger.info(f"PostgreSQL container {self.container_name} stopped successfully")
                return True
            else:
                logger.warning(f"Failed to stop container: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("Timeout stopping PostgreSQL container")
            return False
        except Exception as e:
            logger.error(f"Error stopping PostgreSQL container: {e}")
            return False
    
    def wait_for_container_ready(self, timeout=30):
        """Wait for PostgreSQL container to be ready"""
        import time
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if self.test_connection():
                return True
            time.sleep(1)
        
        raise RuntimeError(f"PostgreSQL container not ready after {timeout} seconds")
    
    def test_connection(self):
        """Test connection to PostgreSQL container"""
        try:
            import psycopg2
            
            conn = psycopg2.connect(
                host='localhost',
                port=self.container_port,
                user=self.postgres_user,
                password=self.postgres_password,
                database=self.postgres_db,
                connect_timeout=5
            )
            conn.close()
            return True
            
        except Exception:
            return False
    
    def get_connection_params(self):
        """Get connection parameters for Django settings"""
        return {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': self.postgres_db,
            'USER': self.postgres_user,
            'PASSWORD': self.postgres_password,
            'HOST': 'localhost',
            'PORT': self.container_port,
            'OPTIONS': {
                'isolation_level': 2,  # READ_COMMITTED for proper concurrency testing
            }
        }
    
    def cleanup_test_data(self):
        """Clean up test data from PostgreSQL container"""
        if not self.test_connection():
            return False
        
        try:
            import psycopg2
            
            conn = psycopg2.connect(
                host='localhost',
                port=self.container_port,
                user=self.postgres_user,
                password=self.postgres_password,
                database=self.postgres_db
            )
            
            cursor = conn.cursor()
            
            # Clean up test tables (be careful with this in production!)
            cleanup_queries = [
                "TRUNCATE TABLE governance_idempotencyrecord CASCADE;",
                "TRUNCATE TABLE governance_audittrail CASCADE;",
                "TRUNCATE TABLE product_stockmovement CASCADE;",
                "TRUNCATE TABLE purchase_purchaseitem CASCADE;",
                "TRUNCATE TABLE purchase_purchase CASCADE;",
                "TRUNCATE TABLE sale_saleitem CASCADE;",
                "TRUNCATE TABLE sale_sale CASCADE;",
                "TRUNCATE TABLE product_stock CASCADE;",
            ]
            
            for query in cleanup_queries:
                try:
                    cursor.execute(query)
                except Exception as e:
                    logger.warning(f"Failed to execute cleanup query {query}: {e}")
            
            conn.commit()
            cursor.close()
            conn.close()
            
            logger.info("PostgreSQL test data cleaned up successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error cleaning up PostgreSQL test data: {e}")
            return False


class DatabaseStateManager:
    """Database state management utilities for testing"""
    
    def __init__(self):
        self.snapshots = {}
        
    def create_snapshot(self, snapshot_name="default"):
        """Create a snapshot of current database state"""
        from django.db import connection
        
        snapshot = {
            'name': snapshot_name,
            'timestamp': time.time(),
            'tables': {}
        }
        
        # Get all table names
        with connection.cursor() as cursor:
            if connection.vendor == 'sqlite':
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            elif connection.vendor == 'postgresql':
                cursor.execute("""
                    SELECT tablename FROM pg_tables 
                    WHERE schemaname = 'public' AND tablename NOT LIKE 'django_%';
                """)
            
            tables = [row[0] for row in cursor.fetchall()]
            
            # Count records in each table
            for table in tables:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table};")
                    count = cursor.fetchone()[0]
                    snapshot['tables'][table] = count
                except Exception as e:
                    logger.warning(f"Could not snapshot table {table}: {e}")
                    snapshot['tables'][table] = -1
        
        self.snapshots[snapshot_name] = snapshot
        logger.info(f"Database snapshot '{snapshot_name}' created with {len(snapshot['tables'])} tables")
        return snapshot
    
    def compare_with_snapshot(self, snapshot_name="default"):
        """Compare current state with a snapshot"""
        if snapshot_name not in self.snapshots:
            raise ValueError(f"Snapshot '{snapshot_name}' not found")
        
        original_snapshot = self.snapshots[snapshot_name]
        current_snapshot = self.create_snapshot(f"{snapshot_name}_current")
        
        differences = {
            'added_tables': [],
            'removed_tables': [],
            'changed_tables': {}
        }
        
        original_tables = set(original_snapshot['tables'].keys())
        current_tables = set(current_snapshot['tables'].keys())
        
        differences['added_tables'] = list(current_tables - original_tables)
        differences['removed_tables'] = list(original_tables - current_tables)
        
        # Check for changed record counts
        for table in original_tables & current_tables:
            original_count = original_snapshot['tables'][table]
            current_count = current_snapshot['tables'][table]
            
            if original_count != current_count:
                differences['changed_tables'][table] = {
                    'original': original_count,
                    'current': current_count,
                    'difference': current_count - original_count
                }
        
        return differences
    
    def restore_to_snapshot(self, snapshot_name="default"):
        """Restore database to snapshot state (WARNING: Destructive operation)"""
        # This is a placeholder - actual implementation would be complex
        # and potentially dangerous. For testing, we typically use transactions
        # or test database isolation instead.
        logger.warning("restore_to_snapshot is not implemented - use transaction rollback instead")
        return False
    
    def get_table_statistics(self):
        """Get current database table statistics"""
        from django.db import connection
        
        stats = {
            'total_tables': 0,
            'total_records': 0,
            'tables': {}
        }
        
        with connection.cursor() as cursor:
            if connection.vendor == 'sqlite':
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            elif connection.vendor == 'postgresql':
                cursor.execute("""
                    SELECT tablename FROM pg_tables 
                    WHERE schemaname = 'public';
                """)
            
            tables = [row[0] for row in cursor.fetchall()]
            stats['total_tables'] = len(tables)
            
            for table in tables:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table};")
                    count = cursor.fetchone()[0]
                    stats['tables'][table] = count
                    stats['total_records'] += count
                except Exception as e:
                    logger.warning(f"Could not get stats for table {table}: {e}")
                    stats['tables'][table] = -1
        
        return stats


# Enhanced context managers
@contextmanager
def postgresql_container():
    """Context manager for PostgreSQL container lifecycle"""
    container_manager = PostgreSQLContainerManager()
    
    try:
        # Start container
        container_manager.start_container()
        yield container_manager
    finally:
        # Stop container
        container_manager.stop_container()


@contextmanager
def database_snapshot(snapshot_name="test_snapshot"):
    """Context manager for database state snapshots"""
    state_manager = DatabaseStateManager()
    
    # Create initial snapshot
    initial_snapshot = state_manager.create_snapshot(snapshot_name)
    
    try:
        yield state_manager
    finally:
        # Compare final state
        differences = state_manager.compare_with_snapshot(snapshot_name)
        if any([differences['added_tables'], differences['removed_tables'], differences['changed_tables']]):
            logger.info(f"Database changes detected: {differences}")


@contextmanager
def concurrency_test_environment():
    """Context manager for setting up concurrency test environment"""
    # Check if PostgreSQL is required and available
    from django.conf import settings
    
    if 'postgresql' not in settings.DATABASES['default']['ENGINE']:
        # Try to use PostgreSQL container for concurrency tests
        with postgresql_container() as container:
            # Temporarily override database settings
            original_db_config = settings.DATABASES['default'].copy()
            settings.DATABASES['default'] = container.get_connection_params()
            
            try:
                yield container
            finally:
                # Restore original database settings
                settings.DATABASES['default'] = original_db_config
    else:
        # PostgreSQL already configured
        yield None


# Test result collection utilities
class TestResultCollector:
    """Collect and analyze test results"""
    
    def __init__(self):
        self.results = {
            'smoke': [],
            'integrity': [],
            'concurrency': []
        }
        self.start_time = time.time()
        self.performance_metrics = {}
        self.error_patterns = {}
    
    def add_result(self, category, test_name, success, execution_time, error=None, metadata=None):
        """Add a test result"""
        result = {
            'test_name': test_name,
            'success': success,
            'execution_time': execution_time,
            'error': error,
            'metadata': metadata or {},
            'timestamp': time.time()
        }
        
        self.results[category].append(result)
        
        # Track performance metrics
        if category not in self.performance_metrics:
            self.performance_metrics[category] = {
                'total_time': 0,
                'min_time': float('inf'),
                'max_time': 0,
                'avg_time': 0,
                'test_count': 0
            }
        
        metrics = self.performance_metrics[category]
        metrics['total_time'] += execution_time
        metrics['min_time'] = min(metrics['min_time'], execution_time)
        metrics['max_time'] = max(metrics['max_time'], execution_time)
        metrics['test_count'] += 1
        metrics['avg_time'] = metrics['total_time'] / metrics['test_count']
        
        # Track error patterns
        if error and not success:
            error_type = type(error).__name__ if isinstance(error, Exception) else str(error)
            if error_type not in self.error_patterns:
                self.error_patterns[error_type] = []
            self.error_patterns[error_type].append({
                'test_name': test_name,
                'category': category,
                'error': str(error)
            })
    
    def get_summary(self):
        """Get summary of all test results"""
        total_time = time.time() - self.start_time
        
        summary = {
            'total_execution_time': total_time,
            'categories': {},
            'performance_metrics': self.performance_metrics,
            'error_patterns': self.error_patterns,
            'overall_stats': {
                'total_tests': 0,
                'total_passed': 0,
                'total_failed': 0,
                'success_rate': 0
            }
        }
        
        total_tests = 0
        total_passed = 0
        
        for category, results in self.results.items():
            if results:
                successful = sum(1 for r in results if r['success'])
                failed = len(results) - successful
                avg_time = sum(r['execution_time'] for r in results) / len(results)
                max_time = max(r['execution_time'] for r in results)
                
                summary['categories'][category] = {
                    'total_tests': len(results),
                    'successful': successful,
                    'failed': failed,
                    'success_rate': successful / len(results) * 100,
                    'average_time': avg_time,
                    'max_time': max_time,
                    'total_time': sum(r['execution_time'] for r in results),
                    'performance_status': self._get_performance_status(category, avg_time, max_time)
                }
                
                total_tests += len(results)
                total_passed += successful
        
        summary['overall_stats'] = {
            'total_tests': total_tests,
            'total_passed': total_passed,
            'total_failed': total_tests - total_passed,
            'success_rate': (total_passed / total_tests * 100) if total_tests > 0 else 0
        }
        
        return summary
    
    def _get_performance_status(self, category, avg_time, max_time):
        """Get performance status for a category"""
        thresholds = {
            'smoke': {'avg': 5, 'max': 60},
            'integrity': {'avg': 30, 'max': 300},
            'concurrency': {'avg': 60, 'max': 600}
        }
        
        if category not in thresholds:
            return 'unknown'
        
        threshold = thresholds[category]
        
        if avg_time <= threshold['avg'] and max_time <= threshold['max']:
            return 'excellent'
        elif avg_time <= threshold['avg'] * 1.5 and max_time <= threshold['max'] * 1.2:
            return 'good'
        elif avg_time <= threshold['avg'] * 2 and max_time <= threshold['max'] * 1.5:
            return 'acceptable'
        else:
            return 'poor'
    
    def get_failed_tests(self):
        """Get list of failed tests with details"""
        failed_tests = []
        
        for category, results in self.results.items():
            for result in results:
                if not result['success']:
                    failed_tests.append({
                        'category': category,
                        'test_name': result['test_name'],
                        'error': result['error'],
                        'execution_time': result['execution_time'],
                        'metadata': result.get('metadata', {})
                    })
        
        return failed_tests
    
    def get_performance_report(self):
        """Get detailed performance report"""
        return {
            'performance_metrics': self.performance_metrics,
            'category_performance': {
                category: self._get_performance_status(
                    category, 
                    metrics['avg_time'], 
                    metrics['max_time']
                )
                for category, metrics in self.performance_metrics.items()
            },
            'recommendations': self._get_performance_recommendations()
        }
    
    def _get_performance_recommendations(self):
        """Get performance improvement recommendations"""
        recommendations = []
        
        for category, metrics in self.performance_metrics.items():
            status = self._get_performance_status(category, metrics['avg_time'], metrics['max_time'])
            
            if status == 'poor':
                recommendations.append(
                    f"{category.title()} tests are performing poorly. "
                    f"Average time: {metrics['avg_time']:.2f}s, Max time: {metrics['max_time']:.2f}s. "
                    f"Consider optimizing test data setup or using faster database operations."
                )
            elif status == 'acceptable':
                recommendations.append(
                    f"{category.title()} tests are within acceptable limits but could be optimized. "
                    f"Consider reviewing slow tests and optimizing where possible."
                )
        
        return recommendations
    
    def export_results(self, format='json', filename=None):
        """Export test results to file"""
        import json
        from pathlib import Path
        
        if filename is None:
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            filename = f"integrity_test_results_{timestamp}.{format}"
        
        summary = self.get_summary()
        
        if format == 'json':
            with open(filename, 'w') as f:
                json.dump(summary, f, indent=2, default=str)
        elif format == 'csv':
            import csv
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Category', 'Test Name', 'Success', 'Execution Time', 'Error'])
                
                for category, results in self.results.items():
                    for result in results:
                        writer.writerow([
                            category,
                            result['test_name'],
                            result['success'],
                            result['execution_time'],
                            result.get('error', '')
                        ])
        
        return filename
    """Collect and analyze test results"""
    
    def __init__(self):
        self.results = {
            'smoke': [],
            'integrity': [],
            'concurrency': []
        }
        self.start_time = time.time()
    
    def add_result(self, category, test_name, success, execution_time, error=None):
        """Add a test result"""
        result = {
            'test_name': test_name,
            'success': success,
            'execution_time': execution_time,
            'error': error,
            'timestamp': time.time()
        }
        
        self.results[category].append(result)
    
    def get_summary(self):
        """Get summary of all test results"""
        total_time = time.time() - self.start_time
        
        summary = {
            'total_execution_time': total_time,
            'categories': {}
        }
        
        for category, results in self.results.items():
            if results:
                successful = sum(1 for r in results if r['success'])
                failed = len(results) - successful
                avg_time = sum(r['execution_time'] for r in results) / len(results)
                max_time = max(r['execution_time'] for r in results)
                
                summary['categories'][category] = {
                    'total_tests': len(results),
                    'successful': successful,
                    'failed': failed,
                    'success_rate': successful / len(results) * 100,
                    'average_time': avg_time,
                    'max_time': max_time,
                    'total_time': sum(r['execution_time'] for r in results)
                }
        
        return summary