#!/usr/bin/env python3
"""
Task 10 Test Runner: Audit Trail and Error Reporting Tests

This script runs all tests for Task 10 of the System Integrity Testing suite:
- Task 10.1: AuditTrailTester test class (unit tests)
- Task 10.2: Property test for audit trail completeness (Property 9) - OPTIONAL
- Task 10.3: Error reporting quality tests (unit tests)
- Task 10.4: Property test for error reporting quality (Property 12) - OPTIONAL

**Feature: system-integrity-testing**

Requirements validated:
- Requirements 4.5, 6.4: Audit trail completeness
- Requirements 9.4, 9.5: Error reporting quality

Key test areas:
- Complete audit trail maintenance
- Governance switch change logging
- Security-sensitive operation logging
- Clear error messages with remediation steps
- Critical failure identification
- Test result reporting accuracy
"""

import os
import sys
import django
import pytest
import time
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.integrity.settings')
django.setup()

def run_task_10_tests():
    """
    Run all Task 10 tests with proper categorization and reporting.
    
    Test Categories:
    1. Unit Tests (AuditTrailTester, ErrorReportingTester)
    2. Property Tests (Optional - requires hypothesis)
    
    Returns:
        bool: True if all tests pass, False otherwise
    """
    print("=" * 80)
    print("TASK 10: AUDIT TRAIL AND ERROR REPORTING TESTS")
    print("=" * 80)
    print()
    
    # Test configuration
    test_files = [
        {
            'file': 'tests/integrity/tests/test_audit_trail_error_reporting.py',
            'description': 'Task 10.1 & 10.3 - Audit Trail and Error Reporting Tests',
            'category': 'integrity',
            'requirements': 'Requirements 4.5, 6.4, 9.4, 9.5'
        }
    ]
    
    total_passed = 0
    total_failed = 0
    start_time = time.time()
    
    print("Running Task 10 Tests:")
    print("-" * 40)
    
    for test_config in test_files:
        print(f"\n📋 {test_config['description']}")
        print(f"   📁 File: {test_config['file']}")
        print(f"   🎯 Category: {test_config['category']}")
        print(f"   📋 Validates: {test_config['requirements']}")
        print()
        
        # Run the test file
        result = pytest.main([
            test_config['file'],
            '-v',
            '--tb=short',
            '--maxfail=5',
            f'--junit-xml=tests/integrity/results/task_10_{test_config["category"]}_results.xml'
        ])
        
        if result == 0:
            print(f"   ✅ {test_config['description']} - PASSED")
            total_passed += 1
        else:
            print(f"   ❌ {test_config['description']} - FAILED")
            total_failed += 1
    
    # Optional Property Tests
    print("\n" + "=" * 60)
    print("OPTIONAL PROPERTY TESTS")
    print("=" * 60)
    
    optional_tests = [
        {
            'task': '10.2',
            'description': 'Property test for audit trail completeness (Property 9)',
            'status': 'OPTIONAL - Not implemented in MVP'
        },
        {
            'task': '10.4',
            'description': 'Property test for error reporting quality (Property 12)',
            'status': 'OPTIONAL - Not implemented in MVP'
        }
    ]
    
    for test in optional_tests:
        print(f"📋 Task {test['task']}: {test['description']}")
        print(f"   ⏭️  Status: {test['status']}")
        print()
    
    # Summary
    execution_time = time.time() - start_time
    print("=" * 80)
    print("TASK 10 TEST SUMMARY")
    print("=" * 80)
    print(f"✅ Tests Passed: {total_passed}")
    print(f"❌ Tests Failed: {total_failed}")
    print(f"⏱️  Execution Time: {execution_time:.2f} seconds")
    print(f"📊 Success Rate: {(total_passed / (total_passed + total_failed) * 100):.1f}%" if (total_passed + total_failed) > 0 else "📊 Success Rate: N/A")
    
    if total_failed == 0:
        print("\n🎉 ALL TASK 10 TESTS PASSED!")
        print("\n✅ Audit Trail Completeness Validated")
        print("✅ Error Reporting Quality Confirmed")
        print("✅ Security-Sensitive Operations Logged")
        print("✅ Clear Error Messages with Remediation")
        print("✅ Critical Failure Identification Working")
        print("✅ Test Result Reporting Accurate")
        
        print("\n📋 Requirements Validated:")
        print("   • Requirements 4.5: Complete audit trail maintenance")
        print("   • Requirements 6.4: Security-sensitive operation logging")
        print("   • Requirements 9.4: Clear error messages with remediation")
        print("   • Requirements 9.5: Test result reporting accuracy")
        
        return True
    else:
        print(f"\n⚠️  {total_failed} TEST(S) FAILED")
        print("\n🔧 Recommended Actions:")
        print("   1. Review failed test output above")
        print("   2. Check audit trail implementation")
        print("   3. Verify error message generation")
        print("   4. Validate reporting accuracy")
        print("   5. Run individual tests for detailed debugging")
        
        return False

def run_individual_test_categories():
    """Run individual test categories for debugging"""
    print("\n" + "=" * 60)
    print("INDIVIDUAL TEST CATEGORY EXECUTION")
    print("=" * 60)
    
    categories = [
        {
            'name': 'Audit Trail Tests',
            'command': [
                'tests/integrity/tests/test_audit_trail_error_reporting.py::AuditTrailErrorReportingTests::test_complete_audit_trail_maintenance',
                'tests/integrity/tests/test_audit_trail_error_reporting.py::AuditTrailErrorReportingTests::test_governance_switch_change_logging',
                'tests/integrity/tests/test_audit_trail_error_reporting.py::AuditTrailErrorReportingTests::test_security_sensitive_operation_logging',
                '-v'
            ]
        },
        {
            'name': 'Error Reporting Tests',
            'command': [
                'tests/integrity/tests/test_audit_trail_error_reporting.py::AuditTrailErrorReportingTests::test_clear_error_messages_with_remediation',
                'tests/integrity/tests/test_audit_trail_error_reporting.py::AuditTrailErrorReportingTests::test_critical_failure_identification',
                'tests/integrity/tests/test_audit_trail_error_reporting.py::AuditTrailErrorReportingTests::test_result_reporting_accuracy',
                '-v'
            ]
        }
    ]
    
    for category in categories:
        print(f"\n🧪 Running {category['name']}...")
        result = pytest.main(category['command'])
        if result == 0:
            print(f"✅ {category['name']} - PASSED")
        else:
            print(f"❌ {category['name']} - FAILED")

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Run Task 10 Audit Trail and Error Reporting Tests')
    parser.add_argument('--individual', action='store_true', 
                       help='Run individual test categories for debugging')
    parser.add_argument('--verbose', action='store_true',
                       help='Enable verbose output')
    
    args = parser.parse_args()
    
    if args.individual:
        run_individual_test_categories()
    else:
        success = run_task_10_tests()
        sys.exit(0 if success else 1)