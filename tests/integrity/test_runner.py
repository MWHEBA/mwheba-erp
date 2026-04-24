"""
System Integrity Test Runner

Comprehensive test runner for executing integrity tests with proper categorization,
performance monitoring, and result reporting.
"""

import os
import sys
import time
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Configure Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.integrity.settings')

import django
django.setup()

from tests.integrity.utils import (
    TestResultCollector, 
    PostgreSQLContainerManager,
    performance_monitor,
    IntegrityTestUtils
)

logger = logging.getLogger(__name__)


class SystemIntegrityTestRunner:
    """Main test runner with categorized execution"""
    
    def __init__(self):
        self.result_collector = TestResultCollector()
        self.postgres_manager = PostgreSQLContainerManager()
        self.test_categories = {
            'smoke': {
                'description': 'Quick tests for immediate feedback (≤60s)',
                'timeout': 60,
                'markers': ['smoke'],
                'required_db': 'sqlite'
            },
            'integrity': {
                'description': 'Comprehensive governance tests (≤5m)',
                'timeout': 300,
                'markers': ['integrity'],
                'required_db': 'sqlite'
            },
            'concurrency': {
                'description': 'Thread-safety tests (≤10m, PostgreSQL required)',
                'timeout': 600,
                'markers': ['concurrency'],
                'required_db': 'postgresql'
            }
        }
    
    def run_smoke_tests(self) -> Dict:
        """Execute core invariant tests within 60s"""
        logger.info("Starting smoke tests execution...")
        
        with performance_monitor("smoke_tests_suite", max_duration=65):
            return self._run_test_category('smoke')
    
    def run_integrity_tests(self) -> Dict:
        """Execute comprehensive tests within 5m"""
        logger.info("Starting integrity tests execution...")
        
        with performance_monitor("integrity_tests_suite", max_duration=320):
            return self._run_test_category('integrity')
    
    def run_concurrency_tests(self) -> Dict:
        """Execute thread-safety tests within 10m"""
        logger.info("Starting concurrency tests execution...")
        
        # Check PostgreSQL availability
        if not self._ensure_postgresql_available():
            return {
                'success': False,
                'error': 'PostgreSQL not available for concurrency tests',
                'skipped': True
            }
        
        with performance_monitor("concurrency_tests_suite", max_duration=620):
            return self._run_test_category('concurrency')
    
    def run_selective_tests(self, category: str) -> Dict:
        """Execute specific test category"""
        if category not in self.test_categories:
            raise ValueError(f"Unknown test category: {category}")
        
        logger.info(f"Starting {category} tests execution...")
        return self._run_test_category(category)
    
    def run_all_tests(self) -> Dict:
        """Execute all test categories in sequence"""
        logger.info("Starting complete test suite execution...")
        
        all_results = {
            'smoke': None,
            'integrity': None,
            'concurrency': None,
            'overall_success': True,
            'total_execution_time': 0,
            'summary': {}
        }
        
        start_time = time.time()
        
        # Run smoke tests first (mandatory)
        smoke_result = self.run_smoke_tests()
        all_results['smoke'] = smoke_result
        
        if not smoke_result.get('success', False):
            logger.error("Smoke tests failed - stopping execution")
            all_results['overall_success'] = False
            return all_results
        
        # Run integrity tests (mandatory)
        integrity_result = self.run_integrity_tests()
        all_results['integrity'] = integrity_result
        
        if not integrity_result.get('success', False):
            logger.error("Integrity tests failed - continuing with concurrency tests")
            all_results['overall_success'] = False
        
        # Run concurrency tests (optional)
        concurrency_result = self.run_concurrency_tests()
        all_results['concurrency'] = concurrency_result
        
        if not concurrency_result.get('success', False) and not concurrency_result.get('skipped', False):
            logger.warning("Concurrency tests failed - this is optional")
        
        all_results['total_execution_time'] = time.time() - start_time
        all_results['summary'] = self.result_collector.get_summary()
        
        return all_results
    
    def _run_test_category(self, category: str) -> Dict:
        """Run a specific test category"""
        category_config = self.test_categories[category]
        start_time = time.time()
        
        try:
            # Prepare test environment
            if category_config['required_db'] == 'postgresql':
                if not self._ensure_postgresql_available():
                    return {
                        'success': False,
                        'error': 'PostgreSQL not available',
                        'skipped': True,
                        'execution_time': 0
                    }
            
            # Build pytest command
            cmd = self._build_pytest_command(category, category_config)
            
            # Execute tests
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=category_config['timeout'],
                cwd=project_root
            )
            
            execution_time = time.time() - start_time
            
            # Parse results
            success = result.returncode == 0
            
            # Add to result collector
            self.result_collector.add_result(
                category=category,
                test_name=f"{category}_suite",
                success=success,
                execution_time=execution_time,
                error=result.stderr if not success else None,
                metadata={
                    'command': ' '.join(cmd),
                    'stdout': result.stdout,
                    'stderr': result.stderr
                }
            )
            
            return {
                'success': success,
                'execution_time': execution_time,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'command': ' '.join(cmd),
                'test_count': self._parse_test_count(result.stdout),
                'passed_count': self._parse_passed_count(result.stdout),
                'failed_count': self._parse_failed_count(result.stdout)
            }
            
        except subprocess.TimeoutExpired:
            execution_time = time.time() - start_time
            error_msg = f"{category} tests exceeded timeout of {category_config['timeout']}s"
            
            self.result_collector.add_result(
                category=category,
                test_name=f"{category}_suite",
                success=False,
                execution_time=execution_time,
                error=error_msg
            )
            
            return {
                'success': False,
                'execution_time': execution_time,
                'error': error_msg,
                'timeout': True
            }
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Error running {category} tests: {e}"
            
            self.result_collector.add_result(
                category=category,
                test_name=f"{category}_suite",
                success=False,
                execution_time=execution_time,
                error=error_msg
            )
            
            return {
                'success': False,
                'execution_time': execution_time,
                'error': error_msg
            }
    
    def _build_pytest_command(self, category: str, config: Dict) -> List[str]:
        """Build pytest command for category"""
        cmd = [
            sys.executable, '-m', 'pytest',
            'tests/integrity/tests/',
            '-v',
            '--tb=short',
            '--maxfail=5',
            f'--timeout={config["timeout"]}'
        ]
        
        # Add markers
        for marker in config['markers']:
            cmd.extend(['-m', marker])
        
        # Add category-specific options
        if category == 'smoke':
            cmd.extend(['--durations=10'])  # Show slowest tests
        elif category == 'integrity':
            cmd.extend(['--durations=20'])
        elif category == 'concurrency':
            cmd.extend(['--durations=30', '--capture=no'])  # Show output for debugging
        
        return cmd
    
    def _ensure_postgresql_available(self) -> bool:
        """Ensure PostgreSQL is available for concurrency tests"""
        try:
            if self.postgres_manager.is_container_running():
                return True
            
            if self.postgres_manager.is_docker_available():
                logger.info("Starting PostgreSQL container for concurrency tests...")
                return self.postgres_manager.start_container()
            else:
                logger.warning("Docker not available - cannot start PostgreSQL container")
                return False
                
        except Exception as e:
            logger.error(f"Error ensuring PostgreSQL availability: {e}")
            return False
    
    def _parse_test_count(self, stdout: str) -> int:
        """Parse total test count from pytest output"""
        import re
        match = re.search(r'(\d+) passed', stdout)
        if match:
            return int(match.group(1))
        
        match = re.search(r'(\d+) failed', stdout)
        if match:
            return int(match.group(1))
        
        return 0
    
    def _parse_passed_count(self, stdout: str) -> int:
        """Parse passed test count from pytest output"""
        import re
        match = re.search(r'(\d+) passed', stdout)
        return int(match.group(1)) if match else 0
    
    def _parse_failed_count(self, stdout: str) -> int:
        """Parse failed test count from pytest output"""
        import re
        match = re.search(r'(\d+) failed', stdout)
        return int(match.group(1)) if match else 0
    
    def get_test_summary(self) -> Dict:
        """Get comprehensive test summary"""
        return self.result_collector.get_summary()
    
    def export_results(self, format='json', filename=None) -> str:
        """Export test results to file"""
        return self.result_collector.export_results(format, filename)
    
    def cleanup(self):
        """Clean up test environment"""
        try:
            if self.postgres_manager.is_container_running():
                logger.info("Stopping PostgreSQL container...")
                self.postgres_manager.stop_container()
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")


class IntegrityTestValidator:
    """Validator for integrity test requirements"""
    
    @staticmethod
    def validate_smoke_test_performance(execution_time: float) -> bool:
        """Validate smoke test performance requirements"""
        return IntegrityTestUtils.validate_smoke_test_timeout(execution_time, 60)
    
    @staticmethod
    def validate_integrity_test_performance(execution_time: float) -> bool:
        """Validate integrity test performance requirements"""
        return IntegrityTestUtils.validate_integrity_test_timeout(execution_time, 300)
    
    @staticmethod
    def validate_concurrency_test_performance(execution_time: float) -> bool:
        """Validate concurrency test performance requirements"""
        return IntegrityTestUtils.validate_concurrency_test_timeout(execution_time, 600)
    
    @staticmethod
    def validate_test_coverage(results: Dict) -> Dict:
        """Validate test coverage requirements"""
        coverage_report = {
            'database_constraints': False,
            'admin_bypass': False,
            'signal_idempotency': False,
            'governance_integrity': False,
            'gateway_authority': False,
            'access_control': False,
            'concurrency_safety': False,
            'audit_trail': False,
            'overall_coverage': 0
        }
        
        # Check if each test category has been executed
        for category, category_results in results.get('categories', {}).items():
            if category_results['successful'] > 0:
                if category == 'smoke':
                    coverage_report['database_constraints'] = True
                    coverage_report['admin_bypass'] = True
                elif category == 'integrity':
                    coverage_report['signal_idempotency'] = True
                    coverage_report['governance_integrity'] = True
                    coverage_report['gateway_authority'] = True
                    coverage_report['access_control'] = True
                    coverage_report['audit_trail'] = True
                elif category == 'concurrency':
                    coverage_report['concurrency_safety'] = True
        
        # Calculate overall coverage
        covered_areas = sum(1 for covered in coverage_report.values() if isinstance(covered, bool) and covered)
        total_areas = len([k for k, v in coverage_report.items() if isinstance(v, bool)])
        coverage_report['overall_coverage'] = (covered_areas / total_areas) * 100
        
        return coverage_report


def main():
    """Main entry point for test runner"""
    import argparse
    
    parser = argparse.ArgumentParser(description='System Integrity Test Runner')
    parser.add_argument(
        'category',
        nargs='?',
        choices=['smoke', 'integrity', 'concurrency', 'all'],
        default='all',
        help='Test category to run'
    )
    parser.add_argument(
        '--export',
        choices=['json', 'csv'],
        help='Export results to file'
    )
    parser.add_argument(
        '--output',
        help='Output filename for exported results'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Verbose output'
    )
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create test runner
    runner = SystemIntegrityTestRunner()
    
    try:
        # Run tests
        if args.category == 'all':
            results = runner.run_all_tests()
        else:
            results = runner.run_selective_tests(args.category)
        
        # Print summary
        print("\n" + "="*80)
        print("SYSTEM INTEGRITY TEST RESULTS")
        print("="*80)
        
        if args.category == 'all':
            for category, result in results.items():
                if category in ['smoke', 'integrity', 'concurrency'] and result:
                    print(f"\n{category.upper()} TESTS:")
                    print(f"  Success: {result.get('success', False)}")
                    print(f"  Execution Time: {result.get('execution_time', 0):.2f}s")
                    if result.get('test_count'):
                        print(f"  Tests: {result['test_count']} total, {result.get('passed_count', 0)} passed, {result.get('failed_count', 0)} failed")
            
            print(f"\nOVERALL SUCCESS: {results.get('overall_success', False)}")
            print(f"TOTAL EXECUTION TIME: {results.get('total_execution_time', 0):.2f}s")
        else:
            print(f"\n{args.category.upper()} TESTS:")
            print(f"  Success: {results.get('success', False)}")
            print(f"  Execution Time: {results.get('execution_time', 0):.2f}s")
            if results.get('test_count'):
                print(f"  Tests: {results['test_count']} total, {results.get('passed_count', 0)} passed, {results.get('failed_count', 0)} failed")
        
        # Export results if requested
        if args.export:
            filename = runner.export_results(args.export, args.output)
            print(f"\nResults exported to: {filename}")
        
        # Validate coverage
        summary = runner.get_test_summary()
        coverage = IntegrityTestValidator.validate_test_coverage(summary)
        print(f"\nTest Coverage: {coverage['overall_coverage']:.1f}%")
        
        # Exit with appropriate code
        if args.category == 'all':
            exit_code = 0 if results.get('overall_success', False) else 1
        else:
            exit_code = 0 if results.get('success', False) else 1
        
        sys.exit(exit_code)
        
    except KeyboardInterrupt:
        print("\nTest execution interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\nError running tests: {e}")
        sys.exit(1)
    finally:
        # Cleanup
        runner.cleanup()


if __name__ == '__main__':
    main()