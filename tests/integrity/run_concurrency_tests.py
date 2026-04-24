#!/usr/bin/env python
"""
Concurrency Test Execution Script

Runs thread-safety and race condition tests within 10 minutes.
Requires PostgreSQL container for proper concurrency testing.
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

# Set Django settings for concurrency testing
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.integrity.settings')

import django
django.setup()

from tests.integrity.ci_config import CITestConfigurator, TestCategory, setup_ci_environment


def run_concurrency_tests():
    """Run concurrency tests with CI integration"""
    # Setup CI environment
    ci_info = setup_ci_environment()
    
    # Initialize configurator
    configurator = CITestConfigurator(project_root)
    
    print("=" * 60)
    print("SYSTEM INTEGRITY CONCURRENCY TESTS")
    print("=" * 60)
    
    if ci_info['is_ci']:
        print(f"CI Environment: {ci_info['provider']}")
        print(f"Branch: {ci_info['branch']}")
        print(f"Commit: {ci_info['commit']}")
        print()
    
    print("Target: Complete within 10 minutes (600 seconds)")
    print("Focus: Thread-safety and race condition testing")
    print("Database: PostgreSQL (required for proper concurrency testing)")
    print("Status: OPTIONAL - separate gate from daily MVP")
    print()
    
    # Check if user wants to proceed (unless forced)
    force = len(sys.argv) > 1 and sys.argv[1] == '--force'
    
    if not force and not ci_info['is_ci']:
        response = input("Do you want to run concurrency tests? (y/N): ").strip().lower()
        if response not in ['y', 'yes']:
            print("⏭️  Skipping concurrency tests (optional for daily MVP)")
            return 0
    
    # Execute concurrency tests
    result = configurator.execute_test_category(TestCategory.CONCURRENCY, force=force)
    
    # Handle skipped tests
    if result['status'] == 'skipped':
        print("⏭️  Concurrency tests skipped (requirements not met)")
        print("This is acceptable for daily MVP - system may still be production-ready")
        return 0
    
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
        print("🎉 CONCURRENCY TESTS COMPLETED SUCCESSFULLY")
        print("System thread-safety and race condition protection validated")
        return 0
    else:
        print("💥 CONCURRENCY TESTS FAILED")
        print("Thread-safety or race condition issues detected")
        print("Note: These are optional tests - system may still be production-ready")
        
        # Print failure details
        if result.get('timeout_violated'):
            print(f"⏰ Timeout violation: {result['execution_time']:.2f}s > {result['timeout_limit']}s")
        
        if result.get('return_code'):
            print(f"Exit code: {result['return_code']}")
        
        # For optional tests, return warning exit code instead of failure
        return 2  # Warning exit code for optional test failures


def main():
    """Main execution function"""
    try:
        exit_code = run_concurrency_tests()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️  Concurrency tests interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n💥 Unexpected error during concurrency tests: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()