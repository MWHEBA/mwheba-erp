"""
CI Integration Configuration for System Integrity Testing

This module provides configuration and utilities for running integrity tests
in CI/CD environments with proper timeout handling and database setup.
"""

import os
import sys
import time
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class TestCategory(Enum):
    """Test categories with their execution requirements"""
    SMOKE = "smoke"
    INTEGRITY = "integrity"
    CONCURRENCY = "concurrency"


class DatabaseType(Enum):
    """Database types for test execution"""
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"


@dataclass
class TestConfiguration:
    """Configuration for test execution"""
    category: TestCategory
    timeout_seconds: int
    database_type: DatabaseType
    max_failures: int
    pytest_markers: List[str]
    required_env_vars: List[str] = None
    optional: bool = False
    description: str = ""


class CITestConfigurator:
    """Manages CI test configuration and execution"""
    
    # Test configurations
    CONFIGURATIONS = {
        TestCategory.SMOKE: TestConfiguration(
            category=TestCategory.SMOKE,
            timeout_seconds=60,
            database_type=DatabaseType.SQLITE,
            max_failures=5,
            pytest_markers=["smoke", "ci_smoke", "timeout_60s"],
            description="Quick integrity tests for immediate feedback"
        ),
        
        TestCategory.INTEGRITY: TestConfiguration(
            category=TestCategory.INTEGRITY,
            timeout_seconds=300,  # 5 minutes
            database_type=DatabaseType.SQLITE,
            max_failures=10,
            pytest_markers=["integrity", "ci_integrity", "timeout_300s"],
            description="Comprehensive governance and constraint tests"
        ),
        
        TestCategory.CONCURRENCY: TestConfiguration(
            category=TestCategory.CONCURRENCY,
            timeout_seconds=600,  # 10 minutes
            database_type=DatabaseType.POSTGRESQL,
            max_failures=5,
            pytest_markers=["concurrency", "ci_optional", "timeout_600s", "postgresql_required"],
            required_env_vars=["POSTGRES_HOST", "POSTGRES_USER", "POSTGRES_PASSWORD"],
            optional=True,
            description="Thread-safety and race condition tests (PostgreSQL required)"
        )
    }
    
    def __init__(self, project_root: Optional[Path] = None):
        """Initialize CI test configurator"""
        self.project_root = project_root or Path(__file__).parent.parent.parent
        self.results = {}
    
    def get_configuration(self, category: TestCategory) -> TestConfiguration:
        """Get configuration for test category"""
        return self.CONFIGURATIONS[category]
    
    def check_requirements(self, config: TestConfiguration) -> Tuple[bool, List[str]]:
        """Check if requirements are met for test execution"""
        issues = []
        
        # Check required environment variables
        if config.required_env_vars:
            for env_var in config.required_env_vars:
                if not os.getenv(env_var):
                    issues.append(f"Missing required environment variable: {env_var}")
        
        # Check database availability
        if config.database_type == DatabaseType.POSTGRESQL:
            if not self._check_postgresql_available():
                issues.append("PostgreSQL database not available")
        
        return len(issues) == 0, issues
    
    def _check_postgresql_available(self) -> bool:
        """Check if PostgreSQL is available"""
        try:
            import psycopg2
            
            conn = psycopg2.connect(
                host=os.getenv('POSTGRES_HOST', 'localhost'),
                port=os.getenv('POSTGRES_PORT', '5432'),
                user=os.getenv('POSTGRES_USER', 'postgres'),
                password=os.getenv('POSTGRES_PASSWORD', 'postgres'),
                database='postgres'
            )
            conn.close()
            return True
        except Exception:
            return False
    
    def build_pytest_command(self, config: TestConfiguration) -> List[str]:
        """Build pytest command for test category"""
        cmd = [
            'pytest',
            'tests/integrity/',
            '--tb=short',
            f'--maxfail={config.max_failures}',
            '-v',
            f'--rootdir={self.project_root}'
        ]
        
        # Add markers
        if config.pytest_markers:
            marker_expr = " or ".join(config.pytest_markers)
            cmd.extend(['-m', marker_expr])
        
        # Add database-specific options
        if config.database_type == DatabaseType.SQLITE:
            cmd.append('--reuse-db')
        elif config.database_type == DatabaseType.POSTGRESQL:
            cmd.extend(['--create-db', '--reuse-db'])
        
        return cmd
    
    def execute_test_category(self, category: TestCategory, force: bool = False) -> Dict:
        """Execute tests for a specific category"""
        config = self.get_configuration(category)
        
        print(f"\n{'='*60}")
        print(f"EXECUTING {category.value.upper()} TESTS")
        print(f"{'='*60}")
        print(f"Description: {config.description}")
        print(f"Timeout: {config.timeout_seconds} seconds")
        print(f"Database: {config.database_type.value}")
        print(f"Optional: {config.optional}")
        print()
        
        # Check requirements
        requirements_met, issues = self.check_requirements(config)
        
        if not requirements_met:
            if config.optional and not force:
                print(f"⏭️  Skipping {category.value} tests (optional, requirements not met):")
                for issue in issues:
                    print(f"   - {issue}")
                return {
                    'category': category.value,
                    'status': 'skipped',
                    'reason': 'requirements_not_met',
                    'issues': issues,
                    'execution_time': 0
                }
            else:
                print(f"❌ Requirements not met for {category.value} tests:")
                for issue in issues:
                    print(f"   - {issue}")
                return {
                    'category': category.value,
                    'status': 'failed',
                    'reason': 'requirements_not_met',
                    'issues': issues,
                    'execution_time': 0
                }
        
        # Execute tests
        start_time = time.time()
        
        try:
            cmd = self.build_pytest_command(config)
            print(f"Executing: {' '.join(cmd)}")
            print()
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=config.timeout_seconds + 30  # Buffer for cleanup
            )
            
            execution_time = time.time() - start_time
            
            # Process results
            test_result = {
                'category': category.value,
                'execution_time': execution_time,
                'return_code': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'timeout_limit': config.timeout_seconds,
                'timeout_violated': execution_time > config.timeout_seconds
            }
            
            if result.returncode == 0 and not test_result['timeout_violated']:
                test_result['status'] = 'passed'
                print(f"✅ {category.value.upper()} TESTS PASSED in {execution_time:.2f}s")
            else:
                test_result['status'] = 'failed'
                if test_result['timeout_violated']:
                    print(f"❌ {category.value.upper()} TESTS TIMEOUT VIOLATION: {execution_time:.2f}s > {config.timeout_seconds}s")
                else:
                    print(f"❌ {category.value.upper()} TESTS FAILED in {execution_time:.2f}s")
            
            return test_result
            
        except subprocess.TimeoutExpired:
            execution_time = time.time() - start_time
            print(f"❌ {category.value.upper()} TESTS TIMED OUT after {execution_time:.2f}s")
            return {
                'category': category.value,
                'status': 'timeout',
                'execution_time': execution_time,
                'timeout_limit': config.timeout_seconds,
                'timeout_violated': True
            }
        
        except Exception as e:
            execution_time = time.time() - start_time
            print(f"❌ {category.value.upper()} TESTS ERROR after {execution_time:.2f}s: {e}")
            return {
                'category': category.value,
                'status': 'error',
                'execution_time': execution_time,
                'error': str(e)
            }
    
    def execute_ci_pipeline(self, include_optional: bool = False, force_optional: bool = False) -> Dict:
        """Execute complete CI test pipeline"""
        print("🚀 STARTING CI INTEGRITY TEST PIPELINE")
        print("=" * 60)
        
        pipeline_start = time.time()
        results = {}
        
        # Execute mandatory tests
        mandatory_categories = [TestCategory.SMOKE, TestCategory.INTEGRITY]
        
        for category in mandatory_categories:
            result = self.execute_test_category(category)
            results[category.value] = result
            
            # Stop on mandatory test failure
            if result['status'] not in ['passed', 'skipped']:
                print(f"\n💥 MANDATORY TEST FAILURE - STOPPING PIPELINE")
                break
        
        # Execute optional tests if requested
        if include_optional:
            optional_categories = [TestCategory.CONCURRENCY]
            
            for category in optional_categories:
                result = self.execute_test_category(category, force=force_optional)
                results[category.value] = result
        
        # Generate pipeline summary
        pipeline_time = time.time() - pipeline_start
        
        summary = {
            'pipeline_execution_time': pipeline_time,
            'results': results,
            'overall_status': self._determine_overall_status(results),
            'mandatory_passed': all(
                results.get(cat.value, {}).get('status') in ['passed', 'skipped']
                for cat in mandatory_categories
            )
        }
        
        self._print_pipeline_summary(summary)
        
        return summary
    
    def _determine_overall_status(self, results: Dict) -> str:
        """Determine overall pipeline status"""
        mandatory_categories = ['smoke', 'integrity']
        
        # Check mandatory tests
        for category in mandatory_categories:
            if category in results:
                status = results[category]['status']
                if status not in ['passed', 'skipped']:
                    return 'failed'
        
        return 'passed'
    
    def _print_pipeline_summary(self, summary: Dict):
        """Print pipeline execution summary"""
        print(f"\n{'='*60}")
        print("CI PIPELINE SUMMARY")
        print(f"{'='*60}")
        print(f"Total execution time: {summary['pipeline_execution_time']:.2f} seconds")
        print(f"Overall status: {summary['overall_status'].upper()}")
        print()
        
        for category, result in summary['results'].items():
            status_icon = {
                'passed': '✅',
                'failed': '❌',
                'timeout': '⏰',
                'error': '💥',
                'skipped': '⏭️'
            }.get(result['status'], '❓')
            
            print(f"{status_icon} {category.upper()}: {result['status']} ({result['execution_time']:.2f}s)")
        
        print()
        
        if summary['overall_status'] == 'passed':
            print("🎉 CI PIPELINE COMPLETED SUCCESSFULLY")
        else:
            print("💥 CI PIPELINE FAILED")


# Environment detection utilities
def detect_ci_environment() -> Dict[str, str]:
    """Detect CI environment and return configuration"""
    ci_info = {
        'is_ci': False,
        'provider': 'unknown',
        'branch': os.getenv('GITHUB_REF_NAME', 'unknown'),
        'commit': os.getenv('GITHUB_SHA', 'unknown')[:8] if os.getenv('GITHUB_SHA') else 'unknown'
    }
    
    # GitHub Actions
    if os.getenv('GITHUB_ACTIONS'):
        ci_info.update({
            'is_ci': True,
            'provider': 'github_actions',
            'workflow': os.getenv('GITHUB_WORKFLOW', 'unknown'),
            'run_id': os.getenv('GITHUB_RUN_ID', 'unknown')
        })
    
    # GitLab CI
    elif os.getenv('GITLAB_CI'):
        ci_info.update({
            'is_ci': True,
            'provider': 'gitlab_ci',
            'pipeline_id': os.getenv('CI_PIPELINE_ID', 'unknown'),
            'job_id': os.getenv('CI_JOB_ID', 'unknown')
        })
    
    # Jenkins
    elif os.getenv('JENKINS_URL'):
        ci_info.update({
            'is_ci': True,
            'provider': 'jenkins',
            'build_number': os.getenv('BUILD_NUMBER', 'unknown'),
            'job_name': os.getenv('JOB_NAME', 'unknown')
        })
    
    return ci_info


def setup_ci_environment():
    """Setup environment for CI execution"""
    ci_info = detect_ci_environment()
    
    if ci_info['is_ci']:
        print(f"🔧 Detected CI environment: {ci_info['provider']}")
        
        # Set CI-specific environment variables
        os.environ['CI'] = 'true'
        os.environ['DJANGO_SETTINGS_MODULE'] = 'tests.integrity.settings'
        os.environ['HYPOTHESIS_PROFILE'] = 'ci'
        
        # Disable interactive prompts
        os.environ['PYTHONUNBUFFERED'] = '1'
        os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
    
    return ci_info