#!/usr/bin/env python
"""
CI Pipeline Execution Script

Runs the complete integrity test pipeline with proper CI integration,
timeout handling, and failure reporting.
"""

import os
import sys
import json
import argparse
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Set Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.integrity.settings')

import django
django.setup()

from tests.integrity.ci_config import CITestConfigurator, setup_ci_environment


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Run System Integrity Test CI Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_ci_pipeline.py                    # Run mandatory tests only
  python run_ci_pipeline.py --include-optional # Run all tests including optional
  python run_ci_pipeline.py --force-optional   # Force optional tests even if requirements not met
  python run_ci_pipeline.py --smoke-only       # Run smoke tests only
  python run_ci_pipeline.py --output results.json # Save results to JSON file
        """
    )
    
    parser.add_argument(
        '--include-optional',
        action='store_true',
        help='Include optional tests (concurrency) in pipeline'
    )
    
    parser.add_argument(
        '--force-optional',
        action='store_true',
        help='Force execution of optional tests even if requirements not met'
    )
    
    parser.add_argument(
        '--smoke-only',
        action='store_true',
        help='Run smoke tests only (fastest validation)'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        help='Output file for test results (JSON format)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    
    return parser.parse_args()


def run_smoke_only_pipeline():
    """Run smoke tests only for quick validation"""
    configurator = CITestConfigurator(project_root)
    
    print("🚀 QUICK VALIDATION PIPELINE (SMOKE TESTS ONLY)")
    print("=" * 60)
    
    from tests.integrity.ci_config import TestCategory
    result = configurator.execute_test_category(TestCategory.SMOKE)
    
    summary = {
        'pipeline_type': 'smoke_only',
        'results': {'smoke': result},
        'overall_status': 'passed' if result['status'] == 'passed' else 'failed'
    }
    
    return summary


def run_full_pipeline(include_optional=False, force_optional=False):
    """Run full CI pipeline"""
    configurator = CITestConfigurator(project_root)
    
    return configurator.execute_ci_pipeline(
        include_optional=include_optional,
        force_optional=force_optional
    )


def save_results(results, output_file):
    """Save results to JSON file"""
    try:
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"📄 Results saved to: {output_file}")
    except Exception as e:
        print(f"⚠️  Failed to save results to {output_file}: {e}")


def print_ci_summary(results):
    """Print CI-friendly summary"""
    print("\n" + "=" * 60)
    print("CI PIPELINE EXECUTION SUMMARY")
    print("=" * 60)
    
    # Overall status
    status_icon = "✅" if results['overall_status'] == 'passed' else "❌"
    print(f"{status_icon} Overall Status: {results['overall_status'].upper()}")
    
    # Execution time
    if 'pipeline_execution_time' in results:
        print(f"⏱️  Total Time: {results['pipeline_execution_time']:.2f} seconds")
    
    # Individual test results
    print("\nTest Results:")
    for category, result in results.get('results', {}).items():
        status_icon = {
            'passed': '✅',
            'failed': '❌',
            'timeout': '⏰',
            'error': '💥',
            'skipped': '⏭️'
        }.get(result['status'], '❓')
        
        time_str = f"({result['execution_time']:.2f}s)" if 'execution_time' in result else ""
        print(f"  {status_icon} {category.upper()}: {result['status']} {time_str}")
        
        # Show timeout violations
        if result.get('timeout_violated'):
            print(f"    ⚠️  Timeout violation: {result['execution_time']:.2f}s > {result['timeout_limit']}s")
    
    # Exit code guidance
    print(f"\nExit Code: {get_exit_code(results)}")
    
    # CI-specific information
    ci_info = setup_ci_environment()
    if ci_info['is_ci']:
        print(f"\nCI Environment: {ci_info['provider']}")
        print(f"Branch: {ci_info['branch']}")
        print(f"Commit: {ci_info['commit']}")


def get_exit_code(results):
    """Determine appropriate exit code for CI"""
    if results['overall_status'] == 'passed':
        return 0
    
    # Check if only optional tests failed
    mandatory_failed = False
    for category in ['smoke', 'integrity']:
        if category in results.get('results', {}):
            if results['results'][category]['status'] not in ['passed', 'skipped']:
                mandatory_failed = True
                break
    
    if mandatory_failed:
        return 1  # Hard failure
    else:
        return 2  # Warning (optional tests failed)


def main():
    """Main execution function"""
    args = parse_arguments()
    
    # Setup CI environment
    ci_info = setup_ci_environment()
    
    try:
        # Execute appropriate pipeline
        if args.smoke_only:
            results = run_smoke_only_pipeline()
        else:
            results = run_full_pipeline(
                include_optional=args.include_optional or args.force_optional,
                force_optional=args.force_optional
            )
        
        # Save results if requested
        if args.output:
            save_results(results, args.output)
        
        # Print summary
        if args.verbose or ci_info['is_ci']:
            print_ci_summary(results)
        
        # Exit with appropriate code
        exit_code = get_exit_code(results)
        
        if exit_code == 0:
            print("\n🎉 CI PIPELINE COMPLETED SUCCESSFULLY")
        elif exit_code == 1:
            print("\n💥 CI PIPELINE FAILED - MANDATORY TESTS FAILED")
        else:
            print("\n⚠️  CI PIPELINE WARNING - OPTIONAL TESTS FAILED")
        
        sys.exit(exit_code)
        
    except KeyboardInterrupt:
        print("\n⚠️  CI pipeline interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n💥 Unexpected error during CI pipeline: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()