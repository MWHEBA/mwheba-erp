"""
Infrastructure Tests

Basic tests to validate the integrity testing infrastructure is working correctly.
"""

import pytest
import time
from django.test import TestCase
from django.contrib.auth import get_user_model
from tests.integrity.utils import performance_monitor, IntegrityTestUtils

User = get_user_model()


@pytest.mark.smoke
@pytest.mark.django_db
class TestInfrastructureSmoke:
    """Smoke tests for testing infrastructure"""
    
    def test_database_connection(self, sqlite_database):
        """Test database connection is working"""
        with performance_monitor("db_connection", max_duration=2):
            # Simple database operation
            user = User.objects.create_user(
                username="infra_test",
                email="infra@test.com",
                password="test_password"
            )
            assert user.username == "infra_test"
    
    def test_performance_monitoring(self):
        """Test performance monitoring utilities"""
        start_time = time.time()
        
        with performance_monitor("test_monitor", max_duration=1):
            time.sleep(0.1)  # Small delay
        
        # Should complete without timeout
        assert time.time() - start_time < 1


@pytest.mark.integrity
@pytest.mark.django_db
class TestInfrastructureIntegrity:
    """Integrity tests for testing infrastructure"""
    
    def test_governance_context(self, governance_context, integrity_user):
        """Test governance context setup"""
        from governance.models import GovernanceContext
        
        context = GovernanceContext.get_context()
        assert context['user'] == integrity_user
        assert context['service'] == 'IntegrityTestSuite'