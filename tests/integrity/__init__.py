"""
System Integrity Testing Suite

Minimum Viable Integrity Suite - focused on critical data integrity and security testing
with categorized test execution (smoke tests ≤60s, integrity tests ≤5m, concurrency tests ≤10m).

Test Categories:
- Smoke Tests: Core invariant validation for immediate feedback
- Integrity Tests: Comprehensive governance and constraint testing  
- Concurrency Tests: Thread-safety and race condition testing (PostgreSQL required)
"""