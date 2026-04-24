#!/usr/bin/env python
"""
Task 8 Test Runner: Gateway Authority and Access Control Tests

This script runs all tests for Task 8, including:
- Task 8.1: GatewayAuthorityTester test class (unit tests)
- Task 8.2: Property test for gateway authority enforcement (Property 5)
- Task 8.3: Access control validation tests (unit tests)
- Task 8.4: Property test for access control enforcement (Property 10)

**Feature: system-integrity-testing**
**Validates: Requirements 8.1, 8.2, 8.5, 6.1, 6.2, 6.4**
"""

import os
import sys
import subprocess
import time
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

def run_test_file(test_file, description):
    """Run a test file and return results"""
    print(f"\n{'='*80}")
    print(f"🧪 Running {description}")
    print(f"📁 File: {test_file}")
    print(f"{'='*80}")
    
    start_time = time.time()
    
    try:
        result = subprocess.run([
            sys.executable, test_file
        ], capture_output=True, text=True, cwd=Path(__file__).parent)
        
        execution_time = time.time() - start_time
        
        if result.returncode == 0:
            print(f"✅ {description} - PASSED ({execution_time:.2f}s)")
            if result.stdout:
                print(result.stdout)
            return True
        else:
            print(f"❌ {description} - FAILED ({execution_time:.2f}s)")
            if result.stdout:
                print("STDOUT:", result.stdout)
            if result.stderr:
                print("STDERR:", result.stderr)
            return False
            
    except Exception as e:
        execution_time = time.time() - start_time
        print(f"💥 {description} - ERROR ({execution_time:.2f}s)")
        print(f"Exception: {e}")
        return False

def main():
    """Run all Task 8 tests"""
    print("🚀 Task 8 Test Suite: Gateway Authority and Access Control Tests")
    print("Feature: system-integrity-testing")
    print("Validates: Requirements 8.1, 8.2, 8.5, 6.1, 6.2, 6.4")
    print(f"Started at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Test files to run
    tests = [
        {
            'file': 'test_gateway_authority_standalone.py',
            'description': 'Task 8.1 - Gateway Authority Unit Tests',
            'requirements': 'Requirements 8.1, 8.2, 8.5'
        },
        {
            'file': 'test_gateway_authority_property.py',
            'description': 'Task 8.2 - Gateway Authority Property Tests (Property 5)',
            'requirements': 'Requirements 8.1, 8.2, 8.5'
        },
        {
            'file': 'test_access_control_validation_standalone.py',
            'description': 'Task 8.3 - Access Control Validation Unit Tests',
            'requirements': 'Requirements 6.1, 6.2, 6.4'
        },
        {
            'file': 'test_access_control_property.py',
            'description': 'Task 8.4 - Access Control Property Tests (Property 10)',
            'requirements': 'Requirements 6.2'
        }
    ]
    
    # Run all tests
    results = []
    total_start_time = time.time()
    
    for test in tests:
        print(f"\n📋 {test['description']}")
        print(f"🎯 Validates: {test['requirements']}")
        
        success = run_test_file(test['file'], test['description'])
        results.append({
            'test': test['description'],
            'file': test['file'],
            'requirements': test['requirements'],
            'success': success
        })
    
    # Summary
    total_execution_time = time.time() - total_start_time
    passed = sum(1 for r in results if r['success'])
    total = len(results)
    
    print(f"\n{'='*80}")
    print("📊 TASK 8 TEST SUITE SUMMARY")
    print(f"{'='*80}")
    print(f"⏱️  Total Execution Time: {total_execution_time:.2f} seconds")
    print(f"📈 Tests Passed: {passed}/{total}")
    print(f"🎯 Success Rate: {(passed/total)*100:.1f}%")
    
    print(f"\n📋 Detailed Results:")
    for result in results:
        status = "✅ PASSED" if result['success'] else "❌ FAILED"
        print(f"  {status} - {result['test']}")
        print(f"    📁 {result['file']}")
        print(f"    🎯 {result['requirements']}")
    
    # Requirements coverage summary
    print(f"\n🎯 Requirements Coverage:")
    requirements_covered = set()
    for result in results:
        if result['success']:
            # Extract requirement numbers from the requirements string
            req_text = result['requirements']
            if '8.1' in req_text:
                requirements_covered.add('8.1 - PurchaseGateway single entry point')
            if '8.2' in req_text:
                requirements_covered.add('8.2 - SaleGateway single entry point')
            if '8.5' in req_text:
                requirements_covered.add('8.5 - Direct model access prevention')
            if '6.1' in req_text:
                requirements_covered.add('6.1 - Non-superuser governance switch access denial')
            if '6.2' in req_text:
                requirements_covered.add('6.2 - Governance bypass prevention')
            if '6.4' in req_text:
                requirements_covered.add('6.4 - Audit trail completeness')
    
    for req in sorted(requirements_covered):
        print(f"  ✅ {req}")
    
    # Property tests summary
    print(f"\n🔬 Property Tests Summary:")
    property_tests = [r for r in results if 'Property' in r['test']]
    if property_tests:
        property_passed = sum(1 for r in property_tests if r['success'])
        print(f"  📊 Property Tests: {property_passed}/{len(property_tests)} passed")
        for result in property_tests:
            status = "✅" if result['success'] else "❌"
            if 'Property 5' in result['test']:
                print(f"    {status} Property 5: Gateway Authority Enforcement")
            elif 'Property 10' in result['test']:
                print(f"    {status} Property 10: Access Control Enforcement")
    
    # Final status
    if passed == total:
        print(f"\n🎉 TASK 8 COMPLETED SUCCESSFULLY!")
        print("   All gateway authority and access control tests passed.")
        print("   System integrity protection is validated.")
        return 0
    else:
        print(f"\n⚠️  TASK 8 PARTIALLY COMPLETED")
        print(f"   {total - passed} test(s) failed - review and fix issues.")
        return 1

if __name__ == "__main__":
    sys.exit(main())