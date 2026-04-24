@echo off
REM Setup Test Environment Script for Windows
REM Prepares the environment for running system integrity tests

echo 🔧 Setting up System Integrity Test Environment
echo ================================================

REM Check if we're in the right directory
if not exist "manage.py" (
    echo [ERROR] This script must be run from the project root directory
    exit /b 1
)

REM Check Python version
echo [INFO] Checking Python version...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set python_version=%%i
echo [SUCCESS] Python version: %python_version%

REM Install Python dependencies
echo [INFO] Installing Python dependencies...
if exist "requirements.txt" (
    pip install -r requirements.txt
    echo [SUCCESS] Main dependencies installed
) else (
    echo [WARNING] requirements.txt not found
)

if exist "requirements-test.txt" (
    pip install -r requirements-test.txt
    echo [SUCCESS] Test dependencies installed
) else (
    echo [WARNING] requirements-test.txt not found
)

REM Install additional test dependencies
echo [INFO] Installing additional test dependencies...
pip install pytest-timeout pytest-xdist pytest-cov hypothesis

REM Create test directories
echo [INFO] Creating test directories...
if not exist "tests\integrity\results" mkdir tests\integrity\results
if not exist "tests\integrity\.hypothesis" mkdir tests\integrity\.hypothesis
echo [SUCCESS] Test directories created

REM Set environment variables
echo [INFO] Setting environment variables...
set DJANGO_SETTINGS_MODULE=tests.integrity.settings
set PYTHONUNBUFFERED=1
set HYPOTHESIS_PROFILE=dev

REM Create environment file for tests
echo DJANGO_SETTINGS_MODULE=tests.integrity.settings > tests\integrity\.env
echo PYTHONUNBUFFERED=1 >> tests\integrity\.env
echo HYPOTHESIS_PROFILE=dev >> tests\integrity\.env
echo POSTGRES_AVAILABLE=false >> tests\integrity\.env

echo [SUCCESS] Environment variables configured

REM Run Django checks
echo [INFO] Running Django system checks...
python manage.py check --settings=tests.integrity.settings
if errorlevel 1 (
    echo [ERROR] Django system checks failed
    exit /b 1
)
echo [SUCCESS] Django system checks passed

REM Create test database
echo [INFO] Setting up test database...
python manage.py migrate --settings=tests.integrity.settings --run-syncdb
if errorlevel 1 (
    echo [ERROR] Test database setup failed
    exit /b 1
)
echo [SUCCESS] Test database setup completed

REM Run setup verification
echo [INFO] Running setup verification...
python -c "import os; import django; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.integrity.settings'); django.setup(); from django.conf import settings; print('✅ Django setup successful'); print(f'Database: {settings.DATABASES[\"default\"][\"ENGINE\"]}'); print(f'Test settings loaded: {hasattr(settings, \"TESTING_INTEGRITY\")}')"
if errorlevel 1 (
    echo [ERROR] Setup verification failed
    exit /b 1
)
echo [SUCCESS] Setup verification passed

echo.
echo 🎉 Test Environment Setup Complete!
echo ==================================
echo.
echo Available test commands:
echo   python tests/integrity/run_smoke_tests.py      # Quick tests (≤60s)
echo   python tests/integrity/run_integrity_tests.py  # Comprehensive tests (≤5m)
echo   python tests/integrity/run_all_tests.py        # All mandatory tests
echo.
echo   # Concurrency tests require PostgreSQL Docker container
echo   # docker run -d --name postgres-test -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:13
echo   # python tests/integrity/run_concurrency_tests.py --force
echo.
echo Docker commands:
echo   docker-compose -f tests/integrity/docker-compose.test.yml up smoke-tests
echo   docker-compose -f tests/integrity/docker-compose.test.yml up integrity-tests-only
echo   docker-compose -f tests/integrity/docker-compose.test.yml up integrity-tests
echo.