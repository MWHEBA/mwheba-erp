#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
setup_production.py - Production Environment Setup Script
Initializes the Mwheba ERP system for production deployment on cPanel with MySQL

This script:
- Validates production environment configuration
- Tests MySQL database connectivity
- Applies all database migrations
- Loads required fixtures and initial data
- Creates custom permissions and roles
- Creates superuser accounts
- Verifies the complete setup

Usage:
    python setup_production.py              # Interactive mode
    python setup_production.py --auto       # Automatic mode (no prompts)
    python setup_production.py --dry-run    # Validation only, no changes
"""

import os
import sys
import argparse
import warnings
import logging
from pathlib import Path
from datetime import datetime

# Suppress deprecation warnings from third-party packages
warnings.filterwarnings('ignore', category=UserWarning, module='coreapi')
warnings.filterwarnings('ignore', category=DeprecationWarning)

# Setup encoding for Windows/Linux compatibility
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


class Colors:
    """ANSI color codes for terminal output"""
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    GRAY = "\033[90m"
    WHITE = "\033[97m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def parse_arguments():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description='Production setup script for Mwheba ERP system',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python setup_production.py              # Interactive mode with prompts
  python setup_production.py --auto       # Automatic mode (use env vars)
  python setup_production.py --dry-run    # Validate configuration only
  python setup_production.py --auto --dry-run  # Validate in auto mode
        """
    )
    
    parser.add_argument(
        '--auto',
        action='store_true',
        help='Run in automatic mode without user prompts (uses environment variables)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Validate configuration without making any changes to the database'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output for debugging'
    )
    
    return parser.parse_args()


def print_colored(text, color="", auto_mode=False):
    """
    Print colored text to console
    
    Args:
        text: Text to print
        color: ANSI color code
        auto_mode: If True, strip emoji and use plain text
    """
    try:
        if auto_mode:
            # Remove emoji and special characters for automated environments
            text_clean = text.replace("✅", "[OK]").replace("❌", "[ERROR]")
            text_clean = text_clean.replace("⚠️", "[WARN]").replace("ℹ️", "[INFO]")
            text_clean = text_clean.replace("📦", "[*]").replace("🔄", "[~]")
            print(text_clean)
        else:
            print(f"{color}{text}{Colors.RESET}")
    except UnicodeEncodeError:
        # Fallback to ASCII if Unicode fails
        text_safe = text.encode('ascii', 'ignore').decode('ascii')
        print(f"{color}{text_safe}{Colors.RESET}")


def print_header(text, auto_mode=False):
    """Print a formatted header"""
    print_colored(f"\n{'='*60}", Colors.CYAN, auto_mode)
    print_colored(f"  {text}", Colors.CYAN + Colors.BOLD, auto_mode)
    print_colored(f"{'='*60}\n", Colors.CYAN, auto_mode)


def print_step(step_num, total, text, auto_mode=False):
    """Print a step indicator"""
    print_colored(f"\n📦 Step {step_num}/{total}: {text}...", Colors.YELLOW, auto_mode)


def print_success(text, auto_mode=False):
    """Print a success message"""
    print_colored(f"   ✅ {text}", Colors.GREEN, auto_mode)


def print_error(text, auto_mode=False):
    """Print an error message"""
    print_colored(f"   ❌ {text}", Colors.RED, auto_mode)


def print_warning(text, auto_mode=False):
    """Print a warning message"""
    print_colored(f"   ⚠️  {text}", Colors.YELLOW, auto_mode)


def print_info(text, auto_mode=False):
    """Print an informational message"""
    print_colored(f"   ℹ️  {text}", Colors.GRAY, auto_mode)


def detect_cpanel_environment():
    """
    Detect if running in a cPanel environment
    
    Returns:
        bool: True if cPanel environment detected
    """
    # Check for common cPanel environment variables
    cpanel_indicators = [
        'CPANEL',
        'cPanel',
        os.path.exists('/usr/local/cpanel'),
        os.path.exists(os.path.expanduser('~/public_html')),
        'REMOTE_USER' in os.environ,
    ]
    
    return any(cpanel_indicators)


def setup_logging(verbose=False):
    """Configure logging for the setup script"""
    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Log file with timestamp
    log_file = log_dir / f"setup_production_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    # Configure logging
    log_level = logging.DEBUG if verbose else logging.INFO
    
    # Create formatters
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # File handler (detailed logging)
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)
    
    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(log_level)
    logger.addHandler(file_handler)
    
    # Create custom filter to exclude passwords from logs
    class PasswordFilter(logging.Filter):
        def filter(self, record):
            # Mask any potential passwords in log messages
            if hasattr(record, 'msg'):
                msg = str(record.msg)
                # Replace common password patterns
                for pattern in ['password=', 'PASSWORD=', 'pwd=', 'PWD=']:
                    if pattern in msg.lower():
                        record.msg = msg.split(pattern)[0] + pattern + '***REDACTED***'
            return True
    
    logger.addFilter(PasswordFilter())
    
    return log_file


def initialize_django():
    """Initialize Django environment"""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mwheba_erp.settings")
    
    # Verify settings file exists
    settings_path = Path("mwheba_erp/settings.py")
    if not settings_path.exists():
        print_error(f"Settings file not found: {settings_path}")
        print_info("Make sure you're running this script from the project root directory")
        logging.error(f"Settings file not found: {settings_path}")
        sys.exit(1)
    
    try:
        import django
        django.setup()
        logging.info("Django initialized successfully")
        return True
    except Exception as e:
        print_error(f"Failed to initialize Django: {e}")
        logging.error(f"Failed to initialize Django: {e}", exc_info=True)
        return False


# ============================================================================
# Exception Classes
# ============================================================================

class SetupError(Exception):
    """Base exception for setup errors"""
    def __init__(self, step, message, details=None):
        self.step = step
        self.message = message
        self.details = details or {}
        super().__init__(f"[{step}] {message}")


class EnvironmentError(SetupError):
    """Environment configuration errors"""
    pass


class DatabaseError(SetupError):
    """Database connection and operation errors"""
    pass


class FixtureError(SetupError):
    """Fixture loading errors"""
    pass


class ValidationError(SetupError):
    """Data validation errors"""
    pass


# ============================================================================
# Environment Validator
# ============================================================================

class EnvironmentValidator:
    """Validates production environment configuration"""
    
    REQUIRED_VARS = [
        'DB_ENGINE', 'DB_NAME', 'DB_USER', 'DB_PASSWORD',
        'DB_HOST', 'DB_PORT', 'SECRET_KEY', 'DEBUG', 'ALLOWED_HOSTS'
    ]
    
    def __init__(self):
        from dotenv import load_dotenv
        load_dotenv()
    
    def validate_all(self):
        """Validate all environment settings and return all errors"""
        logging.info("Starting environment validation")
        errors = []
        
        # Check required variables
        for var in self.REQUIRED_VARS:
            if not os.getenv(var):
                error_msg = f"Missing required environment variable: {var}"
                errors.append(error_msg)
                logging.error(error_msg)
        
        # Validate database configuration
        db_engine = os.getenv('DB_ENGINE', '')
        if db_engine and db_engine != 'mysql':
            error_msg = f"DB_ENGINE must be 'mysql' for production, got: {db_engine}"
            errors.append(error_msg)
            logging.error(error_msg)
        
        # Validate SECRET_KEY complexity
        secret_key = os.getenv('SECRET_KEY', '')
        if secret_key:
            if len(secret_key) < 50:
                error_msg = f"SECRET_KEY must be at least 50 characters, got {len(secret_key)}"
                errors.append(error_msg)
                logging.error(error_msg)
            
            # Check for character variety
            has_upper = any(c.isupper() for c in secret_key)
            has_lower = any(c.islower() for c in secret_key)
            has_digit = any(c.isdigit() for c in secret_key)
            has_special = any(not c.isalnum() for c in secret_key)
            
            if not (has_upper and has_lower and has_digit and has_special):
                error_msg = "SECRET_KEY must contain uppercase, lowercase, digits, and special characters"
                errors.append(error_msg)
                logging.error(error_msg)
        
        # Validate DEBUG mode
        debug = os.getenv('DEBUG', '').lower()
        if debug not in ['false', '0', 'no', '']:
            error_msg = f"DEBUG must be False in production, got: {debug}"
            errors.append(error_msg)
            logging.error(error_msg)
        
        # Validate ALLOWED_HOSTS
        allowed_hosts = os.getenv('ALLOWED_HOSTS', '')
        if not allowed_hosts or allowed_hosts.strip() == '':
            error_msg = "ALLOWED_HOSTS must be configured in production"
            errors.append(error_msg)
            logging.error(error_msg)
        
        if len(errors) == 0:
            logging.info("Environment validation passed")
        else:
            logging.error(f"Environment validation failed with {len(errors)} errors")
        
        return (len(errors) == 0, errors)
    
    def get_database_config(self):
        """Get database configuration from environment"""
        return {
            'ENGINE': os.getenv('DB_ENGINE'),
            'NAME': os.getenv('DB_NAME'),
            'USER': os.getenv('DB_USER'),
            'PASSWORD': os.getenv('DB_PASSWORD'),
            'HOST': os.getenv('DB_HOST', 'localhost'),
            'PORT': os.getenv('DB_PORT', '3306'),
        }


# ============================================================================
# Database Connector
# ============================================================================

class DatabaseConnector:
    """Handles MySQL database connection testing"""
    
    def test_connection(self):
        """Test database connection and return status"""
        logging.info("Testing database connection")
        try:
            import MySQLdb
            from django.conf import settings
            
            db_config = settings.DATABASES['default']
            logging.info(f"Connecting to database: {db_config['NAME']} on {db_config['HOST']}")
            
            # Test connection
            conn = MySQLdb.connect(
                host=db_config['HOST'],
                user=db_config['USER'],
                passwd=db_config['PASSWORD'],
                db=db_config['NAME'],
                port=int(db_config['PORT']),
                charset='utf8mb4',
                connect_timeout=10
            )
            
            # Verify charset
            cursor = conn.cursor()
            cursor.execute("SHOW VARIABLES LIKE 'character_set_database'")
            result = cursor.fetchone()
            charset = result[1] if result else 'unknown'
            
            cursor.close()
            conn.close()
            
            if charset != 'utf8mb4':
                error_msg = f"Database charset is {charset}, should be utf8mb4"
                logging.error(error_msg)
                return (False, error_msg)
            
            success_msg = f"Connected to {db_config['NAME']} on {db_config['HOST']}"
            logging.info(success_msg)
            return (True, success_msg)
            
        except ImportError as e:
            error_msg = "MySQLdb (mysqlclient) not installed. Run: pip install mysqlclient"
            logging.error(error_msg)
            return (False, error_msg)
        except Exception as e:
            logging.error(f"Database connection failed: {e}", exc_info=True)
            return (False, str(e))


# ============================================================================
# Migration Manager
# ============================================================================

class MigrationManager:
    """Manages database migrations"""
    
    def apply_migrations(self):
        """Apply all pending migrations"""
        logging.info("Applying database migrations")
        try:
            from django.core.management import call_command
            from io import StringIO
            
            output = StringIO()
            call_command('migrate', '--noinput', stdout=output, stderr=output)
            
            logging.info("Migrations applied successfully")
            logging.debug(f"Migration output: {output.getvalue()}")
            return (True, "All migrations applied")
            
        except Exception as e:
            logging.error(f"Migration failed: {e}", exc_info=True)
            return (False, str(e))
    
    def verify_migrations(self):
        """Verify migration status"""
        try:
            from django.core.management import call_command
            from io import StringIO
            
            output = StringIO()
            call_command('showmigrations', '--list', stdout=output)
            
            # Check for unapplied migrations
            output_str = output.getvalue()
            unapplied = [line for line in output_str.split('\n') if '[ ]' in line]
            
            return (len(unapplied) == 0, unapplied)
            
        except Exception as e:
            return (False, [str(e)])


# ============================================================================
# Fixture Loader
# ============================================================================

class FixtureLoader:
    """Loads fixtures in correct order"""
    
    FIXTURE_ORDER = [
        'core/fixtures/system_settings_final.json',
        'core/fixtures/hr_leave_settings.json',
        'financial/fixtures/payment_sync_rules.json',
        'hr/fixtures/departments.json',
        'hr/fixtures/job_titles.json',
        'hr/fixtures/initial_data.json',
        'supplier/fixtures/supplier_types.json',
        'printing_pricing/fixtures/paper_types.json',
        'printing_pricing/fixtures/paper_sizes.json',
        'printing_pricing/fixtures/paper_weights.json',
        'printing_pricing/fixtures/paper_colors.json',
        'printing_pricing/fixtures/finishing_types.json',
        'printing_pricing/fixtures/binding_types.json',
        'printing_pricing/fixtures/lamination_types.json',
        'printing_pricing/fixtures/cutting_types.json',
        'printing_pricing/fixtures/machines.json',
        'printing_pricing/fixtures/machine_paper_compatibility.json',
        'printing_pricing/fixtures/machine_speed_settings.json',
        'printing_pricing/fixtures/cost_factors.json',
    ]
    
    def verify_fixture_exists(self, fixture_path):
        """Check if fixture file exists"""
        return Path(fixture_path).exists()
    
    def load_fixture(self, fixture_path):
        """Load a single fixture"""
        try:
            if not self.verify_fixture_exists(fixture_path):
                return (False, f"Fixture file not found: {fixture_path}")
            
            from django.core.management import call_command
            from io import StringIO
            
            output = StringIO()
            call_command('loaddata', fixture_path, stdout=output, stderr=output)
            
            return (True, f"Loaded {fixture_path}")
            
        except Exception as e:
            return (False, f"Failed to load {fixture_path}: {str(e)}")
    
    def load_all_fixtures(self):
        """Load all fixtures in order"""
        logging.info("Starting fixture loading")
        results = {
            'success': True,
            'loaded': 0,
            'skipped': 0,
            'errors': []
        }
        
        for fixture_path in self.FIXTURE_ORDER:
            if not self.verify_fixture_exists(fixture_path):
                logging.warning(f"Fixture not found, skipping: {fixture_path}")
                results['skipped'] += 1
                continue
            
            success, message = self.load_fixture(fixture_path)
            if success:
                results['loaded'] += 1
                logging.info(message)
            else:
                results['success'] = False
                results['errors'].append(message)
                logging.error(message)
        
        logging.info(f"Fixture loading complete: {results['loaded']} loaded, {results['skipped']} skipped")
        return results


# ============================================================================
# Permission and Role Manager
# ============================================================================

class PermissionRoleManager:
    """Manages custom permissions and roles"""
    
    def create_custom_permissions(self):
        """Create custom permissions using management command"""
        try:
            from django.core.management import call_command
            from io import StringIO
            
            output = StringIO()
            call_command('create_custom_permissions', stdout=output, stderr=output)
            
            return (True, "Custom permissions created")
            
        except Exception as e:
            return (False, str(e))
    
    def create_roles(self):
        """Create roles using management command"""
        try:
            from django.core.management import call_command
            from io import StringIO
            
            output = StringIO()
            call_command('update_roles_with_custom_permissions', stdout=output, stderr=output)
            
            return (True, "Roles created and updated")
            
        except Exception as e:
            return (False, str(e))
    
    def verify_permissions(self):
        """Verify permissions exist"""
        try:
            from django.contrib.auth.models import Permission
            count = Permission.objects.count()
            return (count > 0, count)
        except Exception as e:
            return (False, 0)
    
    def verify_roles(self):
        """Verify roles exist"""
        try:
            from django.contrib.auth.models import Group
            count = Group.objects.count()
            return (count > 0, count)
        except Exception as e:
            return (False, 0)


# ============================================================================
# User Manager
# ============================================================================

class UserManager:
    """Manages superuser creation"""
    
    def __init__(self, auto_mode=False):
        self.auto_mode = auto_mode
    
    def get_credentials_from_env(self):
        """Read credentials from environment variables"""
        return {
            'username': os.getenv('SUPERUSER_USERNAME'),
            'email': os.getenv('SUPERUSER_EMAIL'),
            'password': os.getenv('SUPERUSER_PASSWORD'),
            'first_name': os.getenv('SUPERUSER_FIRST_NAME', ''),
            'last_name': os.getenv('SUPERUSER_LAST_NAME', ''),
        }
    
    def prompt_for_credentials(self):
        """Prompt user for credentials interactively"""
        import getpass
        
        print_info("Enter superuser credentials:")
        username = input("  Username: ").strip()
        email = input("  Email: ").strip()
        first_name = input("  First name: ").strip()
        last_name = input("  Last name: ").strip()
        
        while True:
            password = getpass.getpass("  Password: ")
            password_confirm = getpass.getpass("  Confirm password: ")
            
            if password != password_confirm:
                print_error("Passwords don't match. Try again.")
                continue
            
            is_valid, message = self.validate_password_strength(password)
            if not is_valid:
                print_error(f"Password validation failed: {message}")
                continue
            
            break
        
        return {
            'username': username,
            'email': email,
            'password': password,
            'first_name': first_name,
            'last_name': last_name,
        }
    
    def validate_password_strength(self, password):
        """Validate password using Django validators"""
        try:
            from django.contrib.auth.password_validation import validate_password
            validate_password(password)
            return (True, "Password is strong")
        except Exception as e:
            return (False, str(e))
    
    def create_or_update_superusers(self):
        """Create or update superuser accounts"""
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            
            # Get credentials
            if self.auto_mode:
                creds = self.get_credentials_from_env()
                if not all([creds['username'], creds['email'], creds['password']]):
                    return (False, "Missing superuser credentials in environment variables")
            else:
                creds = self.prompt_for_credentials()
            
            # Validate password
            is_valid, message = self.validate_password_strength(creds['password'])
            if not is_valid:
                return (False, f"Password validation failed: {message}")
            
            # Create or update user
            user, created = User.objects.get_or_create(
                username=creds['username'],
                defaults={
                    'email': creds['email'],
                    'first_name': creds['first_name'],
                    'last_name': creds['last_name'],
                    'is_staff': True,
                    'is_superuser': True,
                }
            )
            
            if not created:
                # Update existing user
                user.email = creds['email']
                user.first_name = creds['first_name']
                user.last_name = creds['last_name']
                user.is_staff = True
                user.is_superuser = True
            
            # Set password (always update)
            user.set_password(creds['password'])
            user.save()
            
            action = "created" if created else "updated"
            return (True, f"Superuser '{creds['username']}' {action} successfully")
            
        except Exception as e:
            return (False, str(e))


# ============================================================================
# Accounting Period Manager
# ============================================================================

class AccountingPeriodManager:
    """Manages accounting periods"""
    
    def create_current_year_period(self):
        """Create accounting period for current year"""
        try:
            from financial.models import AccountingPeriod
            from datetime import datetime
            
            current_year = datetime.now().year
            
            # Check if period already exists
            period, created = AccountingPeriod.objects.get_or_create(
                year=current_year,
                defaults={
                    'status': 'open',
                    'start_date': datetime(current_year, 1, 1),
                    'end_date': datetime(current_year, 12, 31),
                }
            )
            
            if created:
                return (True, f"Accounting period for {current_year} created")
            else:
                return (True, f"Accounting period for {current_year} already exists")
                
        except Exception as e:
            return (False, str(e))


# ============================================================================
# Verification and Summary
# ============================================================================

def verify_setup():
    """Verify all setup components"""
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Permission, Group
    
    User = get_user_model()
    
    summary = {
        'users': User.objects.filter(is_superuser=True).count(),
        'permissions': Permission.objects.count(),
        'roles': Group.objects.count(),
    }
    
    try:
        from financial.models import AccountingPeriod
        summary['accounting_periods'] = AccountingPeriod.objects.count()
    except:
        summary['accounting_periods'] = 0
    
    return summary


def display_summary(summary, auto_mode=False):
    """Display setup summary"""
    print_info(f"Superusers: {summary['users']}", auto_mode)
    print_info(f"Permissions: {summary['permissions']}", auto_mode)
    print_info(f"Roles: {summary['roles']}", auto_mode)
    print_info(f"Accounting periods: {summary['accounting_periods']}", auto_mode)


def main():
    """Main setup orchestration function"""
    # Parse command-line arguments
    args = parse_arguments()
    
    # Setup logging
    log_file = setup_logging(args.verbose)
    logging.info("="*60)
    logging.info("Production Setup Started")
    logging.info(f"Mode: {'Auto' if args.auto else 'Interactive'}")
    logging.info(f"Dry Run: {args.dry_run}")
    logging.info("="*60)
    
    # Print header
    print_header("Mwheba ERP - Production Setup", args.auto)
    print_info(f"Logging to: {log_file}", args.auto)
    
    # Detect cPanel environment
    is_cpanel = detect_cpanel_environment()
    if is_cpanel:
        print_info("cPanel environment detected", args.auto)
        print_info("Adapting setup for cPanel hosting", args.auto)
    
    # Show mode information
    if args.dry_run:
        print_colored("\n🔍 DRY RUN MODE: No changes will be made", Colors.CYAN, args.auto)
        print_info("This will validate your configuration without modifying the database", args.auto)
    
    if args.auto:
        print_colored("\n🤖 AUTOMATIC MODE: Using environment variables", Colors.CYAN, args.auto)
        print_info("No user prompts will be shown", args.auto)
    
    # Confirm before proceeding (unless in auto mode)
    if not args.auto and not args.dry_run:
        print_colored("\n⚠️  WARNING: This will initialize the production database", Colors.YELLOW)
        print_info("Make sure you have:")
        print_info("  1. Created MySQL database in cPanel")
        print_info("  2. Configured .env file with database credentials")
        print_info("  3. Backed up any existing data")
        
        response = input("\nDo you want to continue? (yes/no): ").strip().lower()
        if response != 'yes':
            print_colored("\n❌ Setup cancelled by user", Colors.YELLOW)
            sys.exit(0)
    
    # Initialize Django
    print_step(1, 10, "Initializing Django environment", args.auto)
    if not initialize_django():
        print_error("Failed to initialize Django")
        sys.exit(1)
    print_success("Django initialized successfully", args.auto)
    
    # Step 2: Validate environment configuration
    print_step(2, 10, "Validating environment configuration", args.auto)
    validator = EnvironmentValidator()
    is_valid, errors = validator.validate_all()
    if not is_valid:
        print_error("Environment validation failed:")
        for error in errors:
            print_error(f"  - {error}", args.auto)
        sys.exit(1)
    print_success("Environment configuration is valid", args.auto)
    
    # Step 3: Test database connection
    print_step(3, 10, "Testing database connection", args.auto)
    db_connector = DatabaseConnector()
    success, message = db_connector.test_connection()
    if not success:
        print_error(f"Database connection failed: {message}", args.auto)
        sys.exit(1)
    print_success(f"Database connection successful: {message}", args.auto)
    
    if args.dry_run:
        print_header("Dry Run Complete!", args.auto)
        print_success("Configuration is valid and database is accessible", args.auto)
        print_info("Run without --dry-run to apply changes", args.auto)
        return
    
    # Step 4: Apply migrations
    print_step(4, 10, "Applying database migrations", args.auto)
    migration_manager = MigrationManager()
    success, message = migration_manager.apply_migrations()
    if not success:
        print_error(f"Migration failed: {message}", args.auto)
        sys.exit(1)
    print_success("Migrations applied successfully", args.auto)
    
    # Step 5: Load fixtures
    print_step(5, 10, "Loading fixtures", args.auto)
    fixture_loader = FixtureLoader()
    results = fixture_loader.load_all_fixtures()
    if not results['success']:
        print_error("Fixture loading failed", args.auto)
        for error in results.get('errors', []):
            print_error(f"  - {error}", args.auto)
        sys.exit(1)
    print_success(f"Loaded {results['loaded']} fixtures successfully", args.auto)
    if results.get('skipped', 0) > 0:
        print_info(f"Skipped {results['skipped']} fixtures (already loaded)", args.auto)
    
    # Step 6: Create custom permissions
    print_step(6, 10, "Creating custom permissions", args.auto)
    perm_manager = PermissionRoleManager()
    success, message = perm_manager.create_custom_permissions()
    if not success:
        print_error(f"Permission creation failed: {message}", args.auto)
        sys.exit(1)
    print_success(message, args.auto)
    
    # Step 7: Create roles
    print_step(7, 10, "Creating roles", args.auto)
    success, message = perm_manager.create_roles()
    if not success:
        print_error(f"Role creation failed: {message}", args.auto)
        sys.exit(1)
    print_success(message, args.auto)
    
    # Step 8: Create superusers
    print_step(8, 10, "Creating superuser accounts", args.auto)
    user_manager = UserManager(auto_mode=args.auto)
    success, message = user_manager.create_or_update_superusers()
    if not success:
        print_error(f"Superuser creation failed: {message}", args.auto)
        sys.exit(1)
    print_success(message, args.auto)
    
    # Step 9: Create accounting period
    print_step(9, 10, "Creating accounting period", args.auto)
    period_manager = AccountingPeriodManager()
    success, message = period_manager.create_current_year_period()
    if not success:
        print_error(f"Accounting period creation failed: {message}", args.auto)
        sys.exit(1)
    print_success(message, args.auto)
    
    # Step 10: Verify and display summary
    print_step(10, 10, "Verifying setup", args.auto)
    summary = verify_setup()
    display_summary(summary, args.auto)
    
    print_header("Setup Complete!", args.auto)
    print_success("Production environment is ready", args.auto)
    
    if is_cpanel:
        print_info("\nNext steps for cPanel deployment:", args.auto)
        print_info("  1. Configure Passenger WSGI (passenger_wsgi.py)", args.auto)
        print_info("  2. Run: python manage.py collectstatic", args.auto)
        print_info("  3. Set up SSL certificate in cPanel", args.auto)
        print_info("  4. Configure application URL in cPanel", args.auto)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_colored("\n\n❌ Setup cancelled by user (Ctrl+C)", Colors.YELLOW)
        sys.exit(130)
    except Exception as e:
        print_colored(f"\n❌ Unexpected error: {e}", Colors.RED)
        if '--verbose' in sys.argv:
            import traceback
            traceback.print_exc()
        sys.exit(1)
