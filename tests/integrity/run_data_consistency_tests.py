#!/usr/bin/env python
"""
Data Relationship Consistency Test Runner

This script provides a comprehensive test runner for data relationship consistency
tests that validates Purchase → StockMovement and Sale → StockMovement relationships.

Usage:
    python tests/integrity/run_data_consistency_tests.py [--smoke] [--full] [--verbose]

Options:
    --smoke     Run only smoke tests (quick validation)
    --full      Run full comprehensive tests
    --verbose   Enable verbose output
    --help      Show this help message

Requirements Validated:
    - Requirement 5.1: Purchase → StockMovement net effect consistency
    - Requirement 5.2: Sale → StockMovement net effect consistency
    - Explicit reversal operations handling
"""

import os
import sys
import argparse
import time
from datetime import datetime

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

# Configure Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'corporate_erp.settings')

import django
django.setup()

# Import test classes
from tests.integrity.tests.test_data_relationship_consistency import (
    DataRelationshipConsistencyTester,
    DataRelationshipSmokeTester,
    run_data_relationship_consistency_tests
)


class DataConsistencyTestRunner:
    """
    Comprehensive test runner for data relationship consistency tests.
    """
    
    def __init__(self, verbose=False):
        self.verbose = verbose
        self.start_time = None
        self.results = {
            'smoke_tests': None,
            'full_tests': None,
            'consistency_analysis': None,
            'execution_time': 0,
            'success': False
        }
    
    def log(self, message, level='INFO'):
        """Log message with timestamp"""
        if self.verbose or level in ['ERROR', 'WARNING']:
            timestamp = datetime.now().strftime('%H:%M:%S')
            print(f"[{timestamp}] {level}: {message}")
    
    def run_smoke_tests(self):
        """Run smoke tests for quick validation"""
        self.log("Starting data relationship consistency smoke tests...")
        
        try:
            smoke_results = DataRelationshipSmokeTester.run_data_relationship_smoke_tests()
            self.results['smoke_tests'] = smoke_results
            
            self.log(f"Smoke tests completed: {smoke_results['passed']}/{len(smoke_results['tests_run'])} passed")
            self.log(f"Execution time: {smoke_results['execution_time']:.2f}s")
            
            if smoke_results['errors']:
                self.log("Smoke test errors detected:", 'WARNING')
                for error in smoke_results['errors']:
                    self.log(f"  - {error}", 'WARNING')
            
            return smoke_results['failed'] == 0
            
        except Exception as e:
            self.log(f"Error during smoke tests: {str(e)}", 'ERROR')
            return False
    
    def run_consistency_analysis(self):
        """Run detailed consistency analysis"""
        self.log("Running detailed data relationship consistency analysis...")
        
        analysis_results = {
            'purchase_consistency': None,
            'sale_consistency': None,
            'reversal_operations': None,
            'summary': {
                'total_violations': 0,
                'total_missing': 0,
                'total_errors': 0,
                'critical_issues': []
            }
        }
        
        try:
            # Test Purchase consistency
            self.log("Analyzing Purchase → StockMovement consistency...")
            purchase_results = DataRelationshipConsistencyTester.test_purchase_stock_movement_net_effect_consistency()
            analysis_results['purchase_consistency'] = purchase_results
            
            self.log(f"  Purchases tested: {purchase_results['purchases_tested']}")
            self.log(f"  Stock movements found: {purchase_results['stock_movements_created']}")
            self.log(f"  Consistency violations: {len(purchase_results['consistency_violations'])}")
            self.log(f"  Missing movements: {len(purchase_results['missing_movements'])}")
            self.log(f"  Net effect errors: {len(purchase_results['net_effect_errors'])}")
            
            # Test Sale consistency
            self.log("Analyzing Sale → StockMovement consistency...")
            sale_results = DataRelationshipConsistencyTester.test_sale_stock_movement_net_effect_consistency()
            analysis_results['sale_consistency'] = sale_results
            
            self.log(f"  Sales tested: {sale_results['sales_tested']}")
            self.log(f"  Stock movements found: {sale_results['stock_movements_created']}")
            self.log(f"  Consistency violations: {len(sale_results['consistency_violations'])}")
            self.log(f"  Missing movements: {len(sale_results['missing_movements'])}")
            self.log(f"  Net effect errors: {len(sale_results['net_effect_errors'])}")
            
            # Test Reversal operations
            self.log("Analyzing explicit reversal operations...")
            reversal_results = DataRelationshipConsistencyTester.test_explicit_reversal_operations()
            analysis_results['reversal_operations'] = reversal_results
            
            self.log(f"  Reversals tested: {reversal_results['reversals_tested']}")
            self.log(f"  Explicit reversals found: {reversal_results['explicit_reversals_found']}")
            self.log(f"  Deletion reversals found: {reversal_results['deletion_reversals_found']}")
            self.log(f"  Reversal violations: {len(reversal_results['reversal_violations'])}")
            self.log(f"  Audit trail issues: {len(reversal_results['audit_trail_issues'])}")
            
            # Calculate summary
            summary = analysis_results['summary']
            summary['total_violations'] = (
                len(purchase_results['consistency_violations']) +
                len(sale_results['consistency_violations']) +
                len(reversal_results['reversal_violations'])
            )
            summary['total_missing'] = (
                len(purchase_results['missing_movements']) +
                len(sale_results['missing_movements'])
            )
            summary['total_errors'] = (
                len(purchase_results['net_effect_errors']) +
                len(sale_results['net_effect_errors'])
            )
            
            # Identify critical issues
            if summary['total_violations'] > 0:
                summary['critical_issues'].append(f"{summary['total_violations']} consistency violations detected")
            if summary['total_missing'] > 0:
                summary['critical_issues'].append(f"{summary['total_missing']} missing stock movements detected")
            if summary['total_errors'] > 0:
                summary['critical_issues'].append(f"{summary['total_errors']} net effect errors detected")
            
            self.results['consistency_analysis'] = analysis_results
            
            # Log critical issues
            if summary['critical_issues']:
                self.log("Critical issues detected:", 'WARNING')
                for issue in summary['critical_issues']:
                    self.log(f"  - {issue}", 'WARNING')
            else:
                self.log("No critical consistency issues detected")
            
            return len(summary['critical_issues']) == 0
            
        except Exception as e:
            self.log(f"Error during consistency analysis: {str(e)}", 'ERROR')
            return False
    
    def run_full_tests(self):
        """Run full comprehensive tests using Django test framework"""
        self.log("Running full data relationship consistency tests...")
        
        try:
            full_results = run_data_relationship_consistency_tests()
            self.results['full_tests'] = full_results
            
            self.log(f"Full tests completed: {full_results['tests_run']} tests run")
            self.log(f"Failures: {full_results['failures']}")
            self.log(f"Errors: {full_results['errors']}")
            self.log(f"Success: {full_results['success']}")
            
            return full_results['success']
            
        except Exception as e:
            self.log(f"Error during full tests: {str(e)}", 'ERROR')
            return False
    
    def generate_report(self):
        """Generate comprehensive test report"""
        report = []
        report.append("=" * 80)
        report.append("DATA RELATIONSHIP CONSISTENCY TEST REPORT")
        report.append("=" * 80)
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"Total execution time: {self.results['execution_time']:.2f}s")
        report.append("")
        
        # Smoke tests section
        if self.results['smoke_tests']:
            smoke = self.results['smoke_tests']
            report.append("SMOKE TESTS RESULTS:")
            report.append("-" * 40)
            report.append(f"Tests run: {len(smoke['tests_run'])}")
            report.append(f"Passed: {smoke['passed']}")
            report.append(f"Failed: {smoke['failed']}")
            report.append(f"Execution time: {smoke['execution_time']:.2f}s")
            
            if smoke['errors']:
                report.append("\nSmoke test errors:")
                for error in smoke['errors']:
                    report.append(f"  - {error}")
            report.append("")
        
        # Consistency analysis section
        if self.results['consistency_analysis']:
            analysis = self.results['consistency_analysis']
            summary = analysis['summary']
            
            report.append("CONSISTENCY ANALYSIS RESULTS:")
            report.append("-" * 40)
            report.append(f"Total consistency violations: {summary['total_violations']}")
            report.append(f"Total missing movements: {summary['total_missing']}")
            report.append(f"Total net effect errors: {summary['total_errors']}")
            
            if summary['critical_issues']:
                report.append("\nCritical issues:")
                for issue in summary['critical_issues']:
                    report.append(f"  - {issue}")
            else:
                report.append("\n✅ No critical consistency issues detected")
            
            # Purchase details
            if analysis['purchase_consistency']:
                purchase = analysis['purchase_consistency']
                report.append(f"\nPurchase Analysis:")
                report.append(f"  Purchases tested: {purchase['purchases_tested']}")
                report.append(f"  Stock movements: {purchase['stock_movements_created']}")
                report.append(f"  Violations: {len(purchase['consistency_violations'])}")
                report.append(f"  Missing: {len(purchase['missing_movements'])}")
                report.append(f"  Errors: {len(purchase['net_effect_errors'])}")
            
            # Sale details
            if analysis['sale_consistency']:
                sale = analysis['sale_consistency']
                report.append(f"\nSale Analysis:")
                report.append(f"  Sales tested: {sale['sales_tested']}")
                report.append(f"  Stock movements: {sale['stock_movements_created']}")
                report.append(f"  Violations: {len(sale['consistency_violations'])}")
                report.append(f"  Missing: {len(sale['missing_movements'])}")
                report.append(f"  Errors: {len(sale['net_effect_errors'])}")
            
            # Reversal details
            if analysis['reversal_operations']:
                reversal = analysis['reversal_operations']
                report.append(f"\nReversal Operations Analysis:")
                report.append(f"  Reversals tested: {reversal['reversals_tested']}")
                report.append(f"  Explicit reversals: {reversal['explicit_reversals_found']}")
                report.append(f"  Deletion reversals: {reversal['deletion_reversals_found']}")
                report.append(f"  Violations: {len(reversal['reversal_violations'])}")
                report.append(f"  Audit issues: {len(reversal['audit_trail_issues'])}")
            
            report.append("")
        
        # Full tests section
        if self.results['full_tests']:
            full = self.results['full_tests']
            report.append("FULL TESTS RESULTS:")
            report.append("-" * 40)
            report.append(f"Tests run: {full['tests_run']}")
            report.append(f"Failures: {full['failures']}")
            report.append(f"Errors: {full['errors']}")
            report.append(f"Success: {full['success']}")
            report.append("")
        
        # Overall result
        report.append("OVERALL RESULT:")
        report.append("-" * 40)
        if self.results['success']:
            report.append("✅ ALL DATA RELATIONSHIP CONSISTENCY TESTS PASSED")
        else:
            report.append("❌ SOME DATA RELATIONSHIP CONSISTENCY TESTS FAILED")
        
        report.append("=" * 80)
        
        return "\n".join(report)
    
    def run(self, smoke_only=False, full_only=False):
        """Run the complete test suite"""
        self.start_time = time.time()
        self.log("Starting Data Relationship Consistency Test Suite...")
        
        success = True
        
        # Run smoke tests (unless full_only is specified)
        if not full_only:
            if not self.run_smoke_tests():
                success = False
                if smoke_only:
                    self.log("Smoke tests failed - stopping execution", 'ERROR')
                    self.results['success'] = False
                    self.results['execution_time'] = time.time() - self.start_time
                    return False
        
        # Run consistency analysis (unless smoke_only is specified)
        if not smoke_only:
            if not self.run_consistency_analysis():
                success = False
        
        # Run full tests if requested
        if full_only or (not smoke_only and success):
            if not self.run_full_tests():
                success = False
        
        self.results['success'] = success
        self.results['execution_time'] = time.time() - self.start_time
        
        self.log(f"Test suite completed in {self.results['execution_time']:.2f}s")
        self.log(f"Overall result: {'PASSED' if success else 'FAILED'}")
        
        return success


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Data Relationship Consistency Test Runner',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python tests/integrity/run_data_consistency_tests.py --smoke
    python tests/integrity/run_data_consistency_tests.py --full --verbose
    python tests/integrity/run_data_consistency_tests.py
        """
    )
    
    parser.add_argument('--smoke', action='store_true',
                       help='Run only smoke tests (quick validation)')
    parser.add_argument('--full', action='store_true',
                       help='Run full comprehensive tests')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose output')
    parser.add_argument('--report', '-r', action='store_true',
                       help='Generate detailed report')
    
    args = parser.parse_args()
    
    # Create test runner
    runner = DataConsistencyTestRunner(verbose=args.verbose)
    
    # Run tests
    success = runner.run(smoke_only=args.smoke, full_only=args.full)
    
    # Generate report if requested
    if args.report or args.verbose:
        print("\n" + runner.generate_report())
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()