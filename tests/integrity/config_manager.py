"""
Test Configuration Manager

Manages test configurations, environment setup, and database switching
for different test scenarios.
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class TestConfigurationManager:
    """Manages test configurations for different scenarios"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent.parent
        self.test_configs = {
            'smoke': {
                'database': 'sqlite_memory',
                'timeout': 60,
                'max_examples': 10,
                'parallel': False,
                'markers': ['smoke'],
                'settings_module': 'tests.integrity.settings'
            },
            'integrity': {
                'database': 'sqlite_file',
                'timeout': 300,
                'max_examples': 50,
                'parallel': False,
                'markers': ['integrity'],
                'settings_module': 'tests.integrity.settings'
            },
            'concurrency': {
                'database': 'postgresql',
                'timeout': 600,
                'max_examples': 100,
                'parallel': True,
                'markers': ['concurrency'],
                'settings_module': 'tests.integrity.settings_postgresql'
            }
        }
        
        self.database_configs = {
            'sqlite_memory': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': ':memory:',
                'OPTIONS': {
                    'timeout': 20,
                }
            },
            'sqlite_file': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': str(self.project_root / 'tests' / 'integrity' / 'test_db.sqlite3'),
                'OPTIONS': {
                    'timeout': 20,
                }
            },
            'postgresql': {
                'ENGINE': 'django.db.backends.postgresql',
                'NAME': os.getenv('POSTGRES_DB', 'test_integrity'),
                'USER': os.getenv('POSTGRES_USER', 'postgres'),
                'PASSWORD': os.getenv('POSTGRES_PASSWORD', 'postgres'),
                'HOST': os.getenv('POSTGRES_HOST', 'localhost'),
                'PORT': os.getenv('POSTGRES_PORT', '5433'),
                'OPTIONS': {
                    'isolation_level': 2,  # READ_COMMITTED
                }
            }
        }
    
    def get_test_config(self, test_category: str) -> Dict[str, Any]:
        """Get configuration for a test category"""
        if test_category not in self.test_configs:
            raise ValueError(f"Unknown test category: {test_category}")
        
        return self.test_configs[test_category].copy()
    
    def get_database_config(self, database_type: str) -> Dict[str, Any]:
        """Get database configuration"""
        if database_type not in self.database_configs:
            raise ValueError(f"Unknown database type: {database_type}")
        
        return self.database_configs[database_type].copy()
    
    def setup_test_environment(self, test_category: str) -> Dict[str, Any]:
        """Set up test environment for a category"""
        config = self.get_test_config(test_category)
        
        # Set Django settings module
        os.environ['DJANGO_SETTINGS_MODULE'] = config['settings_module']
        
        # Set Hypothesis profile
        hypothesis_profile = f"integrity_{test_category}"
        os.environ['HYPOTHESIS_PROFILE'] = hypothesis_profile
        
        # Set database configuration
        db_config = self.get_database_config(config['database'])
        
        # Create settings dynamically if needed
        if test_category == 'concurrency':
            self._create_postgresql_settings()
        
        return {
            'config': config,
            'database': db_config,
            'environment_vars': {
                'DJANGO_SETTINGS_MODULE': config['settings_module'],
                'HYPOTHESIS_PROFILE': hypothesis_profile
            }
        }
    
    def _create_postgresql_settings(self):
        """Create PostgreSQL settings file if it doesn't exist"""
        settings_file = self.project_root / 'tests' / 'integrity' / 'settings_postgresql.py'
        
        if not settings_file.exists():
            settings_content = '''"""
PostgreSQL settings for concurrency tests
"""
from .settings import *

# Override database configuration for PostgreSQL
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('POSTGRES_DB', 'test_integrity'),
        'USER': os.getenv('POSTGRES_USER', 'postgres'),
        'PASSWORD': os.getenv('POSTGRES_PASSWORD', 'postgres'),
        'HOST': os.getenv('POSTGRES_HOST', 'localhost'),
        'PORT': os.getenv('POSTGRES_PORT', '5433'),
        'OPTIONS': {
            'isolation_level': 2,  # READ_COMMITTED for proper concurrency testing
        },
        'TEST': {
            'NAME': 'test_integrity_concurrency',
        }
    }
}

# Enable connection pooling for better concurrency performance
DATABASES['default']['CONN_MAX_AGE'] = 60

# Logging configuration for concurrency tests
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'INFO',
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': 'tests/integrity/concurrency_tests.log',
            'level': 'DEBUG',
        },
    },
    'loggers': {
        'tests.integrity': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'governance': {
            'handlers': ['file'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}
'''
            
            with open(settings_file, 'w') as f:
                f.write(settings_content)
            
            logger.info(f"Created PostgreSQL settings file: {settings_file}")
    
    def validate_environment(self, test_category: str) -> Dict[str, Any]:
        """Validate test environment for a category"""
        validation = {
            'valid': True,
            'issues': [],
            'warnings': [],
            'requirements_met': True
        }
        
        config = self.get_test_config(test_category)
        
        # Check database requirements
        if config['database'] == 'postgresql':
            # Check if PostgreSQL is available
            try:
                import psycopg2
                
                db_config = self.get_database_config('postgresql')
                conn = psycopg2.connect(
                    host=db_config['HOST'],
                    port=db_config['PORT'],
                    user=db_config['USER'],
                    password=db_config['PASSWORD'],
                    database='postgres',  # Connect to default database
                    connect_timeout=5
                )
                conn.close()
                
            except ImportError:
                validation['issues'].append("psycopg2 not installed - required for PostgreSQL tests")
                validation['valid'] = False
                validation['requirements_met'] = False
                
            except Exception as e:
                validation['issues'].append(f"PostgreSQL connection failed: {e}")
                validation['valid'] = False
        
        # Check Python packages
        required_packages = {
            'smoke': ['hypothesis', 'pytest'],
            'integrity': ['hypothesis', 'pytest', 'factory_boy'],
            'concurrency': ['hypothesis', 'pytest', 'factory_boy', 'psycopg2']
        }
        
        for package in required_packages.get(test_category, []):
            try:
                __import__(package)
            except ImportError:
                validation['issues'].append(f"Required package '{package}' not installed")
                validation['requirements_met'] = False
        
        # Check file permissions
        test_db_path = self.project_root / 'tests' / 'integrity' / 'test_db.sqlite3'
        if config['database'] == 'sqlite_file':
            try:
                # Try to create/write to test database file
                test_db_path.parent.mkdir(parents=True, exist_ok=True)
                test_db_path.touch()
                
                if not os.access(test_db_path, os.W_OK):
                    validation['warnings'].append(f"Test database file may not be writable: {test_db_path}")
                    
            except Exception as e:
                validation['issues'].append(f"Cannot create test database file: {e}")
        
        # Check disk space
        try:
            import shutil
            free_space = shutil.disk_usage(self.project_root).free
            required_space = 100 * 1024 * 1024  # 100MB
            
            if free_space < required_space:
                validation['warnings'].append(
                    f"Low disk space: {free_space / 1024 / 1024:.1f}MB available, "
                    f"{required_space / 1024 / 1024:.1f}MB recommended"
                )
        except Exception:
            validation['warnings'].append("Could not check disk space")
        
        return validation
    
    def create_pytest_config(self, test_category: str) -> str:
        """Create pytest configuration for a test category"""
        config = self.get_test_config(test_category)
        
        pytest_config = f"""[tool:pytest]
DJANGO_SETTINGS_MODULE = {config['settings_module']}
testpaths = tests/integrity/tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*

addopts = 
    --strict-markers
    --verbose
    --tb=short
    --maxfail=5
    --timeout={config['timeout']}
    -m {' or '.join(config['markers'])}

markers =
    smoke: Quick tests for immediate feedback (≤60s)
    integrity: Comprehensive governance tests (≤5m)
    concurrency: Thread-safety tests (≤10m, PostgreSQL required)
    database_constraints: Tests for database-level constraints
    admin_bypass: Tests for admin interface restrictions
    idempotency: Tests for signal idempotency protection
    governance: Tests for governance system integrity
    gateway_authority: Tests for gateway authority enforcement
    access_control: Tests for access control validation
"""
        
        if config.get('parallel', False):
            pytest_config += "\n    -n auto  # Run tests in parallel\n"
        
        return pytest_config
    
    def export_environment_info(self, filename: Optional[str] = None) -> str:
        """Export current environment information"""
        import json
        import platform
        import django
        from datetime import datetime
        
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"test_environment_info_{timestamp}.json"
        
        env_info = {
            'timestamp': datetime.now().isoformat(),
            'system': {
                'platform': platform.platform(),
                'python_version': platform.python_version(),
                'architecture': platform.architecture(),
            },
            'django': {
                'version': django.get_version(),
                'settings_module': os.environ.get('DJANGO_SETTINGS_MODULE', 'not set'),
            },
            'environment_variables': {
                key: value for key, value in os.environ.items()
                if key.startswith(('DJANGO_', 'POSTGRES_', 'HYPOTHESIS_'))
            },
            'test_configurations': self.test_configs,
            'database_configurations': {
                name: {k: v for k, v in config.items() if k != 'PASSWORD'}
                for name, config in self.database_configs.items()
            },
            'project_root': str(self.project_root),
        }
        
        # Add package versions
        packages = ['django', 'pytest', 'hypothesis', 'factory_boy']
        env_info['packages'] = {}
        
        for package in packages:
            try:
                module = __import__(package)
                version = getattr(module, '__version__', 'unknown')
                env_info['packages'][package] = version
            except ImportError:
                env_info['packages'][package] = 'not installed'
        
        with open(filename, 'w') as f:
            json.dump(env_info, f, indent=2, default=str)
        
        logger.info(f"Environment info exported to: {filename}")
        return filename
    
    def setup_logging(self, test_category: str, log_level: str = 'INFO'):
        """Set up logging for test category"""
        import logging.config
        
        log_file = self.project_root / 'tests' / 'integrity' / f'{test_category}_tests.log'
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        logging_config = {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'detailed': {
                    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                },
                'simple': {
                    'format': '%(levelname)s - %(message)s'
                }
            },
            'handlers': {
                'console': {
                    'class': 'logging.StreamHandler',
                    'level': log_level,
                    'formatter': 'simple',
                    'stream': sys.stdout
                },
                'file': {
                    'class': 'logging.FileHandler',
                    'level': 'DEBUG',
                    'formatter': 'detailed',
                    'filename': str(log_file),
                    'mode': 'a'
                }
            },
            'loggers': {
                'tests.integrity': {
                    'handlers': ['console', 'file'],
                    'level': 'DEBUG',
                    'propagate': False
                },
                'governance': {
                    'handlers': ['file'],
                    'level': 'DEBUG',
                    'propagate': False
                },
                'purchase': {
                    'handlers': ['file'],
                    'level': 'INFO',
                    'propagate': False
                },
                'sale': {
                    'handlers': ['file'],
                    'level': 'INFO',
                    'propagate': False
                }
            },
            'root': {
                'level': log_level,
                'handlers': ['console']
            }
        }
        
        logging.config.dictConfig(logging_config)
        logger.info(f"Logging configured for {test_category} tests - log file: {log_file}")


def main():
    """Command line interface for configuration manager"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test Configuration Manager')
    parser.add_argument(
        'action',
        choices=['validate', 'setup', 'export-env', 'create-config'],
        help='Action to perform'
    )
    parser.add_argument(
        '--category',
        choices=['smoke', 'integrity', 'concurrency'],
        default='integrity',
        help='Test category (default: integrity)'
    )
    parser.add_argument(
        '--output',
        help='Output filename for export actions'
    )
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create configuration manager
    config_manager = TestConfigurationManager()
    
    try:
        if args.action == 'validate':
            validation = config_manager.validate_environment(args.category)
            
            print(f"\nENVIRONMENT VALIDATION - {args.category.upper()}")
            print("=" * 50)
            print(f"Valid: {validation['valid']}")
            print(f"Requirements met: {validation['requirements_met']}")
            
            if validation['issues']:
                print("\nISSUES:")
                for issue in validation['issues']:
                    print(f"  - {issue}")
            
            if validation['warnings']:
                print("\nWARNINGS:")
                for warning in validation['warnings']:
                    print(f"  - {warning}")
        
        elif args.action == 'setup':
            setup_info = config_manager.setup_test_environment(args.category)
            
            print(f"\nTEST ENVIRONMENT SETUP - {args.category.upper()}")
            print("=" * 50)
            print(f"Settings module: {setup_info['environment_vars']['DJANGO_SETTINGS_MODULE']}")
            print(f"Hypothesis profile: {setup_info['environment_vars']['HYPOTHESIS_PROFILE']}")
            print(f"Database: {setup_info['config']['database']}")
            print(f"Timeout: {setup_info['config']['timeout']}s")
            print(f"Markers: {', '.join(setup_info['config']['markers'])}")
        
        elif args.action == 'export-env':
            filename = config_manager.export_environment_info(args.output)
            print(f"\nEnvironment info exported to: {filename}")
        
        elif args.action == 'create-config':
            pytest_config = config_manager.create_pytest_config(args.category)
            
            if args.output:
                with open(args.output, 'w') as f:
                    f.write(pytest_config)
                print(f"\nPytest config written to: {args.output}")
            else:
                print(f"\nPYTEST CONFIG - {args.category.upper()}")
                print("=" * 50)
                print(pytest_config)
    
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())