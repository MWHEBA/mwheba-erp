"""
System Integrity Testing Configuration

Pytest fixtures and configuration for integrity testing suite.
"""

import pytest
import os
from django.conf import settings
from django.test import override_settings
from django.db import transaction
from hypothesis import settings as hypothesis_settings, HealthCheck
from governance.models import GovernanceContext
from governance.services import IdempotencyService


# Configure Hypothesis for integrity testing
hypothesis_settings.register_profile(
    "integrity_smoke", 
    max_examples=10, 
    deadline=5000,  # 5 seconds per test
    suppress_health_check=[HealthCheck.too_slow]
)

hypothesis_settings.register_profile(
    "integrity_full", 
    max_examples=50, 
    deadline=30000,  # 30 seconds per test
    suppress_health_check=[HealthCheck.too_slow]
)

hypothesis_settings.register_profile(
    "integrity_concurrency", 
    max_examples=100, 
    deadline=60000,  # 60 seconds per test
    suppress_health_check=[HealthCheck.too_slow]
)

# Load appropriate profile based on test markers
def pytest_configure(config):
    """Configure Hypothesis based on test execution context"""
    # Register custom markers
    config.addinivalue_line("markers", "smoke: Quick tests for immediate feedback (≤60s)")
    config.addinivalue_line("markers", "integrity: Comprehensive governance tests (≤5m)")
    config.addinivalue_line("markers", "concurrency: Thread-safety tests requiring PostgreSQL (≤10m)")
    config.addinivalue_line("markers", "performance: Test performance validation")
    config.addinivalue_line("markers", "slow: Tests that may take longer than usual")
    
    if config.getoption("--markers") and "smoke" in str(config.getoption("--markers")):
        hypothesis_settings.load_profile("integrity_smoke")
    elif config.getoption("--markers") and "concurrency" in str(config.getoption("--markers")):
        hypothesis_settings.load_profile("integrity_concurrency")
    else:
        hypothesis_settings.load_profile("integrity_full")


@pytest.fixture
def integrity_user(db):
    """Create a test user for integrity testing"""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    return User.objects.create_user(
        username='integrity_test_user',
        email='integrity@test.com',
        password='integrity_test_pass'
    )


@pytest.fixture
def admin_user(db):
    """Create an admin user for admin bypass testing"""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    return User.objects.create_superuser(
        username='admin_test_user',
        email='admin@test.com',
        password='admin_test_pass'
    )


@pytest.fixture
def governance_context(integrity_user):
    """Set up governance context for testing"""
    GovernanceContext.set_context(
        user=integrity_user,
        service='IntegrityTestSuite',
        operation='test_operation'
    )
    yield
    GovernanceContext.clear_context()


@pytest.fixture
def clean_idempotency():
    """Clean up idempotency records before and after tests"""
    # Clean before test
    from governance.models import IdempotencyRecord
    IdempotencyRecord.objects.all().delete()
    
    yield
    
    # Clean after test
    IdempotencyRecord.objects.all().delete()


@pytest.fixture
def test_warehouse(db):
    """Create a test warehouse for stock operations"""
    from product.models import Warehouse
    
    return Warehouse.objects.create(
        name='Test Warehouse',
        code='TEST_WH',
        location='Test Location'
    )


@pytest.fixture
def test_product(db):
    """Create a test product for operations"""
    from product.models import Product, Category, Unit
    
    # Create category and unit if they don't exist
    category, _ = Category.objects.get_or_create(
        name='Test Category',
        defaults={'code': 'TEST_CAT'}
    )
    
    unit, _ = Unit.objects.get_or_create(
        name='Test Unit',
        defaults={'symbol': 'TU'}
    )
    
    return Product.objects.create(
        name='Test Product',
        code='TEST_PROD',
        category=category,
        unit=unit,
        cost_price=100.00,
        selling_price=150.00
    )


@pytest.fixture
def test_supplier(db):
    """Create a test supplier for purchase operations"""
    from supplier.models import Supplier
    
    return Supplier.objects.create(
        name='Test Supplier',
        code='TEST_SUP',
        phone='123456789',
        email='supplier@test.com'
    )


@pytest.fixture
def test_customer(db):
    """Create a test customer for sale operations"""
    from client.models import Customer
    
    return Customer.objects.create(
        name='Test Customer',
        code='TEST_CUST',
        phone='123456789',
        email='customer@test.com'
    )


@pytest.fixture
def sqlite_database():
    """Ensure we're using SQLite for fast tests"""
    if settings.DATABASES['default']['ENGINE'] != 'django.db.backends.sqlite3':
        pytest.skip("This test requires SQLite database")


@pytest.fixture
def postgresql_database():
    """Ensure we're using PostgreSQL for concurrency tests"""
    if 'postgresql' not in settings.DATABASES['default']['ENGINE']:
        pytest.skip("This test requires PostgreSQL database for proper concurrency testing")


@pytest.fixture
def atomic_transaction():
    """Provide atomic transaction context for testing"""
    with transaction.atomic():
        yield


@pytest.fixture
def mock_request():
    """Create a mock request object for testing"""
    from django.test import RequestFactory
    from django.contrib.auth.models import AnonymousUser
    
    factory = RequestFactory()
    request = factory.get('/')
    request.user = AnonymousUser()
    return request


# Test data cleanup fixture
@pytest.fixture(autouse=True)
def cleanup_test_data():
    """Automatically clean up test data after each test"""
    yield
    
    # Clean up governance records
    from governance.models import IdempotencyRecord, AuditTrail, QuarantineRecord
    
    try:
        IdempotencyRecord.objects.filter(
            operation_type__startswith='TEST_'
        ).delete()
        
        AuditTrail.objects.filter(
            source_service='IntegrityTestSuite'
        ).delete()
        
        QuarantineRecord.objects.filter(
            quarantine_reason__contains='integrity test'
        ).delete()
    except Exception:
        # Ignore cleanup errors to avoid masking test failures
        pass


# Performance monitoring fixture
@pytest.fixture
def performance_monitor():
    """Monitor test performance for timeout validation"""
    import time
    
    start_time = time.time()
    yield
    end_time = time.time()
    
    execution_time = end_time - start_time
    
    # Store execution time for later validation
    if not hasattr(performance_monitor, 'execution_times'):
        performance_monitor.execution_times = []
    performance_monitor.execution_times.append(execution_time)


# Database constraint testing fixtures
@pytest.fixture
def constraint_violation_data():
    """Provide data designed to violate database constraints"""
    return {
        'negative_stock': {
            'quantity': -10,
            'reserved_quantity': 0
        },
        'invalid_reserved': {
            'quantity': 100,
            'reserved_quantity': 150  # Greater than available
        },
        'zero_quantity_with_reserved': {
            'quantity': 0,
            'reserved_quantity': 5  # Reserved > available
        }
    }


# Concurrency testing fixtures
@pytest.fixture
def concurrent_operations_data():
    """Provide data for concurrent operations testing"""
    return {
        'thread_count': 5,
        'operations_per_thread': 10,
        'test_timeout': 30  # seconds
    }