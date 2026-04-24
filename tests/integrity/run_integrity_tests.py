#!/usr/bin/env python
"""
Integrity Test Execution Script

Runs comprehensive governance and constraint tests within 5 minutes.
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


def run_integrity_tests():
    """Run integrity tests with CI integration"""
    # Setup CI environment
    ci_info = setup_ci_environment()
    
    # Initialize configurator
    configurator = CITestConfigurator(project_root)
    
    print("=" * 60)
    print("SYSTEM INTEGRITY COMPREHENSIVE TESTS")
    print("=" * 60)
    
    if ci_info['is_ci']:
        print(f"CI Environment: {ci_info['provider']}")
        print(f"Branch: {ci_info['branch']}")
        print(f"Commit: {ci_info['commit']}")
        print()
    
    print("Target: Complete within 5 minutes (300 seconds)")
    print("Focus: Comprehensive governance and constraint testing")
    print("Database: SQLite (optimized for CI)")
    print()
    
    # Execute integrity tests
    result = configurator.execute_test_category(TestCategory.INTEGRITY)
    
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
        print("🎉 INTEGRITY TESTS COMPLETED SUCCESSFULLY")
        print("System governance and constraints validated")
        return 0
    else:
        print("💥 INTEGRITY TESTS FAILED")
        print("Governance or constraint violations detected - investigate immediately")
        
        # Print failure details
        if result.get('timeout_violated'):
            print(f"⏰ Timeout violation: {result['execution_time']:.2f}s > {result['timeout_limit']}s")
        
        if result.get('return_code'):
            print(f"Exit code: {result['return_code']}")
        
        return 1


def main():
    """Main execution function"""
    try:
        exit_code = run_integrity_tests()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️  Integrity tests interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n💥 Unexpected error during integrity tests: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()