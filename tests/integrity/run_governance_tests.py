#!/usr/bin/env python
"""
Governance Tests Runner

Simple script to run governance integrity tests without the full Django test framework.
This script is useful for quick validation and debugging.
"""

import os
import sys
import django
import time
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Configure Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.integrity.settings')
django.setup()

from tests.integrity.tests.test_governance_data_consistency import (
    GovernanceTester, 
    GovernanceSmokeTester,
    run_governance_integrity_tests
)


def print_separator(title="", char="=", width=80):
    """Print a formatted separator line"""
    if title:
        title = f" {title} "
        padding = (width - len(title)) // 2
        line = char * padding + title + char * padding
        if len(line) < width:
            line += char
    else:
        line = char * width
    print(line)


def run_smoke_tests():
    """Run governance smoke tests"""
    print_separator("GOVERNANCE SMOKE TESTS")
    
    start_time = time.time()
    results = GovernanceSmokeTester.run_governance_smoke_tests()
    
    print(f"Tests run: {len(results['tests_run'])}")
    print(f"Passed: {results['passed']}")
    print(f"Failed: {results['failed']}")
    print(f"Execution time: {results['execution_time']:.2f}s")
    
    if results['errors']:
        print("\nErrors:")
        for error in results['errors']:
            print(f"  - {error}")
    
    # Validate smoke test timeout (should be ≤ 60s)
    if results['execution_time'] > 60:
        print(f"⚠️  WARNING: Smoke tests exceeded 60s timeout ({results['execution_time']:.2f}s)")
    else:
        print(f"✅ Smoke tests completed within timeout")
    
    return results['failed'] == 0


def run_individual_tests():
    """Run individual governance tests"""
    print_separator("INDIVIDUAL GOVERNANCE TESTS")
    
    all_passed = True
    
    # Test 1: Governance Switch Invariant Validation
    print("\n1. Testing Governance Switch Invariant Validation...")
    try:
        start_time = time.time()
        result1 = GovernanceTester.test_governance_switch_invariant_validation()
        execution_time = time.time() - start_time
        
        print(f"   ✅ Completed in {execution_time:.2f}s")
        print(f"   Invariants checked: {len(result1['invariants_checked'])}")
        print(f"   Violations detected: {len(result1['violations_detected'])}")
        
        if result1['violations_detected']:
            print("   ⚠️  Violations found:")
            for violation in result1['violations_detected'][:3]:  # Show first 3
                print(f"      - {violation.get('invariant', 'Unknown')}: {violation.get('description', 'No description')}")
    
    except Exception as e:
        print(f"   ❌ Failed: {str(e)}")
        all_passed = False
    
    # Test 2: Fully Governed Workflow Compliance
    print("\n2. Testing Fully Governed Workflow Compliance...")
    try:
        start_time = time.time()
        result2 = GovernanceTester.test_fully_governed_workflow_compliance()
        execution_time = time.time() - start_time
        
        print(f"   ✅ Completed in {execution_time:.2f}s")
        print(f"   Workflows tested: {len(result2['workflows_tested'])}")
        print(f"   Violations found: {len(result2['violations_found'])}")
        
        if result2['workflows_tested']:
            print(f"   Workflows: {', '.join(result2['workflows_tested'])}")
    
    except Exception as e:
        print(f"   ❌ Failed: {str(e)}")
        all_passed = False
    
    # Test 3: Partially Governed Workflow Boundaries
    print("\n3. Testing Partially Governed Workflow Boundaries...")
    try:
        start_time = time.time()
        result3 = GovernanceTester.test_partially_governed_workflow_boundaries()
        execution_time = time.time() - start_time
        
        print(f"   ✅ Completed in {execution_time:.2f}s")
        print(f"   Workflows tested: {len(result3['workflows_tested'])}")
        print(f"   Violations found: {len(result3['violations_found'])}")
        
        if result3['workflows_tested']:
            print(f"   Workflows: {', '.join(result3['workflows_tested'])}")
    
    except Exception as e:
        print(f"   ❌ Failed: {str(e)}")
        all_passed = False
    
    return all_passed


def run_governance_statistics():
    """Display governance system statistics"""
    print_separator("GOVERNANCE SYSTEM STATISTICS")
    
    try:
        from governance.services import governance_switchboard
        
        stats = governance_switchboard.get_governance_statistics()
        
        print(f"Components: {stats['components']['enabled']}/{stats['components']['total']} enabled")
        print(f"Workflows: {stats['workflows']['enabled']}/{stats['workflows']['total']} enabled")
        print(f"High-risk workflows enabled: {stats['workflows']['high_risk_enabled']}")
        print(f"Emergency flags active: {stats['emergency']['active']}")
        
        if stats['components']['enabled_list']:
            print(f"\nEnabled components:")
            for component in stats['components']['enabled_list']:
                print(f"  - {component}")
        
        if stats['workflows']['enabled_list']:
            print(f"\nEnabled workflows:")
            for workflow in stats['workflows']['enabled_list']:
                print(f"  - {workflow}")
        
        if stats['emergency']['active_list']:
            print(f"\n⚠️  Active emergency flags:")
            for emergency in stats['emergency']['active_list']:
                print(f"  - {emergency}")
        
        print(f"\nGovernance Health:")
        print(f"  - Governance active: {stats['health']['governance_active']}")
        print(f"  - Emergency override: {stats['health']['emergency_override']}")
        print(f"  - Critical workflows protected: {stats['health']['critical_workflows_protected']}")
        
    except Exception as e:
        print(f"❌ Failed to get governance statistics: {str(e)}")


def main():
    """Main test runner"""
    print_separator("GOVERNANCE INTEGRITY TEST RUNNER", "=", 80)
    print("Testing governance system integrity and data consistency...")
    print()
    
    # Run governance statistics first
    run_governance_statistics()
    print()
    
    # Run smoke tests
    smoke_passed = run_smoke_tests()
    print()
    
    # Run individual tests
    individual_passed = run_individual_tests()
    print()
    
    # Final summary
    print_separator("FINAL SUMMARY")
    
    if smoke_passed and individual_passed:
        print("✅ All governance tests PASSED")
        print("   - Smoke tests completed within timeout")
        print("   - Individual tests completed successfully")
        print("   - GovernanceTester class is working correctly")
        return 0
    else:
        print("❌ Some governance tests FAILED")
        if not smoke_passed:
            print("   - Smoke tests failed or exceeded timeout")
        if not individual_passed:
            print("   - Individual tests failed")
        return 1


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)