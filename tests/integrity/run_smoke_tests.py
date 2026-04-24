#!/usr/bin/env python
"""
Smoke Test Execution Script

Runs core invariant validation tests within 60 seconds for immediate feedback.
Enhanced with CI integration and better error handling.
"""

import os
import sys
import time
import subprocess
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Set Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.integrity.settings')

import django
django.setup()

from tests.integrity.ci_config import CITestConfigurator, TestCategory, setup_ci_environment


def run_smoke_tests():
    """Run smoke tests with CI integration"""
    # Setup CI environment
    ci_info = setup_ci_environment()
    
    # Initialize configurator
    configurator = CITestConfigurator(project_root)
    
    print("=" * 60)
    print("SYSTEM INTEGRITY SMOKE TESTS")
    print("=" * 60)
    
    if ci_info['is_ci']:
        print(f"CI Environment: {ci_info['provider']}")
        print(f"Branch: {ci_info['branch']}")
        print(f"Commit: {ci_info['commit']}")
        print()
    
    print("Target: Complete within 60 seconds")
    print("Focus: Core invariant validation for immediate feedback")
    print("Database: SQLite (in-memory for speed)")
    print()
    
    # Execute smoke tests
    result = configurator.execute_test_category(TestCategory.SMOKE)
    
    # Print detailed results
    print("\nDETAILED RESULTS:")
    print("=" * 40)
    
    if result.get('stdout'):
        print("STDOUT:")
        print(result['stdout'])
        print()
    
    if result.get('stderr'):
        print("STDERR:")
        print(result['stderr'])
        print()
    
    # Return appropriate exit code
    if result['status'] == 'passed':
        print("🎉 SMOKE TESTS COMPLETED SUCCESSFULLY")
        print("System integrity core invariants validated")
        return 0
    else:
        print("💥 SMOKE TESTS FAILED")
        print("Critical integrity issues detected - investigate immediately")
        
        # Print failure details
        if result.get('timeout_violated'):
            print(f"⏰ Timeout violation: {result['execution_time']:.2f}s > {result['timeout_limit']}s")
        
        if result.get('return_code'):
            print(f"Exit code: {result['return_code']}")
        
        return 1


def main():
    """Main execution function"""
    try:
        exit_code = run_smoke_tests()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️  Smoke tests interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n💥 Unexpected error during smoke tests: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()