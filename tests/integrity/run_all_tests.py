#!/usr/bin/env python
"""
All Tests Execution Script

Runs all integrity tests with proper sequencing and error handling.
This is the main entry point for comprehensive integrity testing.
"""

import os
import sys
import argparse
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Set Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.integrity.settings')

import django
django.setup()

from tests.integrity.ci_config import CITestConfigurator, TestCategory, setup_ci_environment


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Run System Integrity Tests',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Test Categories:
  smoke       - Quick tests (≤60s) for immediate feedback
  integrity   - Comprehensive tests (≤5m) for governance validation
  concurrency - Thread-safety tests (≤10m, PostgreSQL required)

Examples:
  python run_all_tests.py                    # Run smoke + integrity (mandatory)
  python run_all_tests.py --concurrency      # Include concurrency tests
  python run_all_tests.py --smoke-only       # Smoke tests only
  python run_all_tests.py --force            # Force all tests including optional
        """
    )
    
    parser.add_argument(
        '--smoke-only',
        action='store_true',
        help='Run smoke tests only (fastest validation)'
    )
    
    parser.add_argument(
        '--concurrency',
        action='store_true',
        help='Include concurrency tests (requires PostgreSQL)'
    )
    
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force execution of all tests including optional ones'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    
    return parser.parse_args()


def main():
    """Main execution function"""
    args = parse_arguments()
    
    # Setup CI environment
    ci_info = setup_ci_environment()
    
    print("🔍 SYSTEM INTEGRITY TEST SUITE")
    print("=" * 60)
    
    if ci_info['is_ci']:
        print(f"CI Environment: {ci_info['provider']}")
        print(f"Branch: {ci_info['branch']}")
        print(f"Commit: {ci_info['commit']}")
        print()
    
    try:
        # Initialize configurator
        configurator = CITestConfigurator(project_root)
        
        # Determine test execution strategy
        if args.smoke_only:
            print("Strategy: Smoke tests only (quick validation)")
            result = configurator.execute_test_category(TestCategory.SMOKE)
            
            if result['status'] == 'passed':
                print("\n🎉 SMOKE TESTS PASSED - Quick validation successful")
                sys.exit(0)
            else:
                print("\n💥 SMOKE TESTS FAILED - Critical issues detected")
                sys.exit(1)
        
        else:
            # Run full pipeline
            include_optional = args.concurrency or args.force
            force_optional = args.force
            
            print(f"Strategy: {'Full pipeline' if include_optional else 'Mandatory tests only'}")
            
            summary = configurator.execute_ci_pipeline(
                include_optional=include_optional,
                force_optional=force_optional
            )
            
            # Determine exit code
            if summary['overall_status'] == 'passed':
                print("\n🎉 ALL TESTS COMPLETED SUCCESSFULLY")
                sys.exit(0)
            else:
                # Check if only optional tests failed
                mandatory_passed = summary.get('mandatory_passed', False)
                
                if mandatory_passed:
                    print("\n⚠️  OPTIONAL TESTS FAILED - Mandatory tests passed")
                    print("System may still be production-ready")
                    sys.exit(2)  # Warning exit code
                else:
                    print("\n💥 MANDATORY TESTS FAILED - Critical issues detected")
                    sys.exit(1)
    
    except KeyboardInterrupt:
        print("\n⚠️  Test execution interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n💥 Unexpected error during test execution: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()