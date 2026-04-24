"""
Test Execution Utility

Provides a unified interface for executing system integrity tests
with proper configuration, timeout handling, and result reporting.
"""

import os
import sys
import time
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Union
from dataclasses import dataclass, asdict
from enum import Enum
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class ExecutionMode(Enum):
    """Test execution modes"""
    SMOKE_ONLY = "smoke_only"
    MANDATORY = "mandatory"
    FULL = "full"
    CUSTOM = "custom"


class TestResult(Enum):
    """Test execution results"""
    PASSED = "passed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class TestExecution:
    """Test execution configuration and results"""
    category: str
    command: List[str]
    timeout_seconds: int
    description: str
    optional: bool = False
    result: Optional[TestResult] = None
    execution_time: Optional[float] = None
    return_code: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class IntegrityTestExecutor:
    """Manages execution of system integrity tests"""
    
    def __init__(self, project_root: Optional[Path] = None):
        """Initialize test executor"""
        self.project_root = project_root or Path(__file__).parent.parent.parent
        self.results_dir = Path(__file__).parent / "results"
        self.results_dir.mkdir(exist_ok=True)
        
        # Test configurations
        self.test_configurations = {
            "smoke": TestExecution(
                category="smoke",
                command=["python", "tests/integrity/run_smoke_tests.py"],
                timeout_seconds=60,
                description="Quick integrity tests for immediate feedback",
                optional=False
            ),
            "integrity": TestExecution(
                category="integrity",
                command=["python", "tests/integrity/run_integrity_tests.py"],
                timeout_seconds=300,
                description="Comprehensive governance and constraint tests",
                optional=False
            ),
            "concurrency": TestExecution(
                category="concurrency",
                command=["python", "tests/integrity/run_concurrency_tests.py", "--force"],
                timeout_seconds=600,
                description="Thread-safety and race condition tests (PostgreSQL required)",
                optional=True
            )
        }
    
    def execute_test(self, test_config: TestExecution) -> TestExecution:
        """Execute a single test configuration"""
        logger.info(f"Starting {test_config.category} tests...")
        logger.info(f"Description: {test_config.description}")
        logger.info(f"Timeout: {test_config.timeout_seconds} seconds")
        logger.info(f"Command: {' '.join(test_config.command)}")
        
        # Update execution info
        test_config.started_at = time.strftime('%Y-%m-%d %H:%M:%S')
        start_time = time.time()
        
        try:
            # Execute test command
            result = subprocess.run(
                test_config.command,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=test_config.timeout_seconds + 30  # Buffer for cleanup
            )
            
            execution_time = time.time() - start_time
            test_config.execution_time = execution_time
            test_config.return_code = result.returncode
            test_config.stdout = result.stdout
            test_config.stderr = result.stderr
            test_config.completed_at = time.strftime('%Y-%m-%d %H:%M:%S')
            
            # Determine result
            if result.returncode == 0:
                if execution_time <= test_config.timeout_seconds:
                    test_config.result = TestResult.PASSED
                    logger.info(f"✅ {test_config.category} tests PASSED in {execution_time:.2f}s")
                else:
                    test_config.result = TestResult.TIMEOUT
                    test_config.error_message = f"Timeout violation: {execution_time:.2f}s > {test_config.timeout_seconds}s"
                    logger.error(f"⏰ {test_config.category} tests TIMEOUT: {test_config.error_message}")
            else:
                test_config.result = TestResult.FAILED
                test_config.error_message = f"Test failed with exit code {result.returncode}"
                logger.error(f"❌ {test_config.category} tests FAILED: {test_config.error_message}")
        
        except subprocess.TimeoutExpired:
            execution_time = time.time() - start_time
            test_config.execution_time = execution_time
            test_config.result = TestResult.TIMEOUT
            test_config.error_message = f"Process timeout after {execution_time:.2f}s"
            test_config.completed_at = time.strftime('%Y-%m-%d %H:%M:%S')
            logger.error(f"⏰ {test_config.category} tests TIMED OUT: {test_config.error_message}")
        
        except Exception as e:
            execution_time = time.time() - start_time
            test_config.execution_time = execution_time
            test_config.result = TestResult.ERROR
            test_config.error_message = str(e)
            test_config.completed_at = time.strftime('%Y-%m-%d %H:%M:%S')
            logger.error(f"💥 {test_config.category} tests ERROR: {test_config.error_message}")
        
        return test_config
    
    def execute_mode(self, mode: ExecutionMode, custom_tests: Optional[List[str]] = None) -> Dict[str, TestExecution]:
        """Execute tests based on execution mode"""
        logger.info(f"Executing tests in {mode.value} mode")
        
        # Determine which tests to run
        if mode == ExecutionMode.SMOKE_ONLY:
            test_names = ["smoke"]
        elif mode == ExecutionMode.MANDATORY:
            test_names = ["smoke", "integrity"]
        elif mode == ExecutionMode.FULL:
            test_names = ["smoke", "integrity", "concurrency"]
        elif mode == ExecutionMode.CUSTOM:
            test_names = custom_tests or []
        else:
            raise ValueError(f"Unknown execution mode: {mode}")
        
        # Execute tests
        results = {}
        for test_name in test_names:
            if test_name not in self.test_configurations:
                logger.warning(f"Unknown test configuration: {test_name}")
                continue
            
            test_config = self.test_configurations[test_name]
            
            # Skip optional tests if they fail requirements check
            if test_config.optional and not self._check_optional_requirements(test_name):
                logger.info(f"⏭️  Skipping {test_name} tests (requirements not met)")
                test_config.result = TestResult.SKIPPED
                test_config.error_message = "Requirements not met"
                results[test_name] = test_config
                continue
            
            # Execute test
            executed_config = self.execute_test(test_config)
            results[test_name] = executed_config
            
            # Stop on mandatory test failure
            if not test_config.optional and executed_config.result not in [TestResult.PASSED, TestResult.SKIPPED]:
                logger.error(f"Mandatory test {test_name} failed - stopping execution")
                break
        
        return results
    
    def _check_optional_requirements(self, test_name: str) -> bool:
        """Check if requirements are met for optional tests"""
        if test_name == "concurrency":
            # Check PostgreSQL availability
            try:
                import psycopg2
                conn = psycopg2.connect(
                    host=os.getenv('POSTGRES_HOST', 'localhost'),
                    port=os.getenv('POSTGRES_PORT', '5432'),
                    user=os.getenv('POSTGRES_USER', 'postgres'),
                    password=os.getenv('POSTGRES_PASSWORD', 'postgres'),
                    database='postgres'
                )
                conn.close()
                return True
            except Exception:
                return False
        
        return True
    
    def generate_report(self, results: Dict[str, TestExecution], output_file: Optional[str] = None) -> Dict:
        """Generate execution report"""
        report = {
            "execution_summary": {
                "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
                "total_tests": len(results),
                "passed": sum(1 for r in results.values() if r.result == TestResult.PASSED),
                "failed": sum(1 for r in results.values() if r.result == TestResult.FAILED),
                "timeout": sum(1 for r in results.values() if r.result == TestResult.TIMEOUT),
                "error": sum(1 for r in results.values() if r.result == TestResult.ERROR),
                "skipped": sum(1 for r in results.values() if r.result == TestResult.SKIPPED),
                "total_execution_time": sum(r.execution_time or 0 for r in results.values())
            },
            "test_results": {name: asdict(config) for name, config in results.items()},
            "overall_status": self._determine_overall_status(results)
        }
        
        # Save report if output file specified
        if output_file:
            output_path = self.results_dir / output_file
            with open(output_path, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            logger.info(f"Report saved to: {output_path}")
        
        return report
    
    def _determine_overall_status(self, results: Dict[str, TestExecution]) -> str:
        """Determine overall execution status"""
        mandatory_tests = ["smoke", "integrity"]
        
        # Check mandatory tests
        for test_name in mandatory_tests:
            if test_name in results:
                result = results[test_name].result
                if result not in [TestResult.PASSED, TestResult.SKIPPED]:
                    return "failed"
        
        return "passed"
    
    def print_summary(self, results: Dict[str, TestExecution]):
        """Print execution summary"""
        print("\n" + "=" * 60)
        print("SYSTEM INTEGRITY TEST EXECUTION SUMMARY")
        print("=" * 60)
        
        total_time = sum(r.execution_time or 0 for r in results.values())
        print(f"Total execution time: {total_time:.2f} seconds")
        
        # Print individual results
        for test_name, config in results.items():
            status_icon = {
                TestResult.PASSED: "✅",
                TestResult.FAILED: "❌",
                TestResult.TIMEOUT: "⏰",
                TestResult.ERROR: "💥",
                TestResult.SKIPPED: "⏭️"
            }.get(config.result, "❓")
            
            time_str = f"({config.execution_time:.2f}s)" if config.execution_time else ""
            print(f"{status_icon} {test_name.upper()}: {config.result.value if config.result else 'unknown'} {time_str}")
            
            if config.error_message:
                print(f"   Error: {config.error_message}")
        
        # Overall status
        overall_status = self._determine_overall_status(results)
        status_icon = "🎉" if overall_status == "passed" else "💥"
        print(f"\n{status_icon} Overall Status: {overall_status.upper()}")


def main():
    """Main execution function for standalone usage"""
    import argparse
    
    parser = argparse.ArgumentParser(description='System Integrity Test Executor')
    parser.add_argument('--mode', choices=['smoke_only', 'mandatory', 'full'], 
                       default='mandatory', help='Execution mode')
    parser.add_argument('--output', help='Output file for results (JSON)')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Execute tests
    executor = IntegrityTestExecutor()
    mode = ExecutionMode(args.mode)
    results = executor.execute_mode(mode)
    
    # Generate report
    report = executor.generate_report(results, args.output)
    
    # Print summary
    executor.print_summary(results)
    
    # Exit with appropriate code
    exit_code = 0 if report['overall_status'] == 'passed' else 1
    sys.exit(exit_code)


if __name__ == '__main__':
    main()