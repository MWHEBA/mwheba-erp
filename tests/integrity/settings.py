"""
Settings for System Integrity Testing

Optimized settings for fast and reliable integrity testing with proper database configurations.
"""

from tests.settings import *
import os

# Test identification
TESTING_INTEGRITY = True

# Database configuration for integrity tests
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',  # In-memory for speed
        'OPTIONS': {
            'timeout': 20,
        },
        'TEST': {
            'NAME': ':memory:',
        }
    }
}

# PostgreSQL configuration for concurrency tests (when needed)
CONCURRENCY_DATABASE = {
    'ENGINE': 'django.db.backends.postgresql',
    'NAME': 'test_integrity_concurrency',
    'USER': os.getenv('POSTGRES_USER', 'postgres'),
    'PASSWORD': os.getenv('POSTGRES_PASSWORD', 'postgres'),
    'HOST': os.getenv('POSTGRES_HOST', 'localhost'),
    'PORT': os.getenv('POSTGRES_PORT', '5432'),
    'OPTIONS': {
        'isolation_level': 2,  # READ_COMMITTED for proper concurrency testing
    },
    'TEST': {
        'NAME': 'test_integrity_concurrency',
    }
}

# Logging configuration for integrity tests
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'integrity': {
            'format': '[INTEGRITY] {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'integrity',
        },
    },
    'loggers': {
        'governance': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'tests.integrity': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

# Performance settings for integrity tests
INTEGRITY_TEST_SETTINGS = {
    'SMOKE_TEST_TIMEOUT': 60,  # seconds
    'INTEGRITY_TEST_TIMEOUT': 300,  # 5 minutes
    'CONCURRENCY_TEST_TIMEOUT': 600,  # 10 minutes
    'MAX_CONCURRENT_THREADS': 10,
    'CLEANUP_AFTER_TESTS': True,
}

# Disable unnecessary features for testing
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Cache configuration
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

# Email configuration
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

# Security settings for testing
SECRET_KEY = 'integrity-test-secret-key-not-for-production'
ALLOWED_HOSTS = ['*']
DEBUG = False

# Governance system settings for testing
GOVERNANCE_SETTINGS = {
    'ENABLE_AUDIT_TRAIL': True,
    'ENABLE_IDEMPOTENCY': True,
    'ENABLE_QUARANTINE': True,
    'STRICT_AUTHORITY_CHECKING': True,
    'EMERGENCY_MODE': False,
}

# Test-specific middleware (minimal for performance)
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'governance.middleware.GovernanceMiddleware',  # Keep governance middleware
]

# Hypothesis settings for property-based testing
HYPOTHESIS_SETTINGS = {
    'max_examples': 50,
    'deadline': 30000,  # 30 seconds
    'suppress_health_check': ['too_slow'],
}

# Test markers configuration
PYTEST_MARKERS = {
    'smoke': 'Quick tests for immediate feedback (≤60s)',
    'integrity': 'Comprehensive governance tests (≤5m)',
    'concurrency': 'Thread-safety tests (≤10m, PostgreSQL required)',
    'property': 'Property-based tests using Hypothesis',
    'database_constraints': 'Tests for database-level constraints',
    'admin_bypass': 'Tests for admin interface restrictions',
    'idempotency': 'Tests for signal idempotency protection',
    'governance': 'Tests for governance system integrity',
    'gateway_authority': 'Tests for gateway authority enforcement',
}