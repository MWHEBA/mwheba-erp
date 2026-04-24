#!/bin/bash
# Setup Test Environment Script
# Prepares the environment for running system integrity tests

set -e

echo "🔧 Setting up System Integrity Test Environment"
echo "================================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if we're in the right directory
if [ ! -f "manage.py" ]; then
    print_error "This script must be run from the project root directory"
    exit 1
fi

# Check Python version
print_status "Checking Python version..."
python_version=$(python3 --version 2>&1 | cut -d' ' -f2)
required_version="3.9"

if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 9) else 1)"; then
    print_error "Python 3.9+ is required. Current version: $python_version"
    exit 1
fi
print_success "Python version: $python_version"

# Install Python dependencies
print_status "Installing Python dependencies..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    print_success "Main dependencies installed"
else
    print_warning "requirements.txt not found"
fi

if [ -f "requirements-test.txt" ]; then
    pip install -r requirements-test.txt
    print_success "Test dependencies installed"
else
    print_warning "requirements-test.txt not found"
fi

# Install additional test dependencies
print_status "Installing additional test dependencies..."
pip install pytest-timeout pytest-xdist pytest-cov hypothesis

# Check PostgreSQL availability (optional)
print_status "Checking PostgreSQL availability..."
if command -v psql >/dev/null 2>&1; then
    if pg_isready -h localhost -p 5432 >/dev/null 2>&1; then
        print_success "PostgreSQL is available for concurrency tests"
        export POSTGRES_AVAILABLE=true
    else
        print_warning "PostgreSQL is not running - concurrency tests will be skipped"
        print_warning "To enable concurrency tests, run: docker run -d --name postgres-test -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:13"
        export POSTGRES_AVAILABLE=false
    fi
else
    print_warning "PostgreSQL client not installed - concurrency tests will be skipped"
    export POSTGRES_AVAILABLE=false
fi

# Create test directories
print_status "Creating test directories..."
mkdir -p tests/integrity/results
mkdir -p tests/integrity/.hypothesis
print_success "Test directories created"

# Set environment variables
print_status "Setting environment variables..."
export DJANGO_SETTINGS_MODULE=tests.integrity.settings
export PYTHONUNBUFFERED=1
export HYPOTHESIS_PROFILE=dev

# Create environment file for tests
cat > tests/integrity/.env << EOF
DJANGO_SETTINGS_MODULE=tests.integrity.settings
PYTHONUNBUFFERED=1
HYPOTHESIS_PROFILE=dev
POSTGRES_AVAILABLE=${POSTGRES_AVAILABLE:-false}
EOF

print_success "Environment variables configured"

# Run Django checks
print_status "Running Django system checks..."
if python manage.py check --settings=tests.integrity.settings; then
    print_success "Django system checks passed"
else
    print_error "Django system checks failed"
    exit 1
fi

# Create test database
print_status "Setting up test database..."
if python manage.py migrate --settings=tests.integrity.settings --run-syncdb; then
    print_success "Test database setup completed"
else
    print_error "Test database setup failed"
    exit 1
fi

# Run a quick smoke test to verify setup
print_status "Running setup verification..."
if python -c "
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.integrity.settings')
django.setup()
from django.conf import settings
print('✅ Django setup successful')
print(f'Database: {settings.DATABASES[\"default\"][\"ENGINE\"]}')
print(f'Test settings loaded: {hasattr(settings, \"TESTING_INTEGRITY\")}')
"; then
    print_success "Setup verification passed"
else
    print_error "Setup verification failed"
    exit 1
fi

echo ""
echo "🎉 Test Environment Setup Complete!"
echo "=================================="
echo ""
echo "Available test commands:"
echo "  python tests/integrity/run_smoke_tests.py      # Quick tests (≤60s)"
echo "  python tests/integrity/run_integrity_tests.py  # Comprehensive tests (≤5m)"
echo "  python tests/integrity/run_all_tests.py        # All mandatory tests"
echo ""
if [ "$POSTGRES_AVAILABLE" = "true" ]; then
    echo "  python tests/integrity/run_concurrency_tests.py --force  # Concurrency tests (≤10m)"
    echo "  python tests/integrity/run_all_tests.py --concurrency    # All tests including concurrency"
else
    echo "  # Concurrency tests not available (PostgreSQL not running)"
fi
echo ""
echo "Docker commands:"
echo "  docker-compose -f tests/integrity/docker-compose.test.yml up smoke-tests"
echo "  docker-compose -f tests/integrity/docker-compose.test.yml up integrity-tests-only"
echo "  docker-compose -f tests/integrity/docker-compose.test.yml up integrity-tests"
echo ""
echo "Make commands:"
echo "  make -C tests/integrity smoke"
echo "  make -C tests/integrity integrity"
echo "  make -C tests/integrity all"
echo ""