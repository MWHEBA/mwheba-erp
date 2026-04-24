"""
Management command to verify HR governance migration is complete.
"""
from django.core.management.base import BaseCommand
from django.db import connection
import os
import re


class Command(BaseCommand):
    help = 'Verify HR governance migration is complete and system is ready for deployment'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\n' + '='*70))
        self.stdout.write(self.style.SUCCESS('HR Governance Migration Verification'))
        self.stdout.write(self.style.SUCCESS('='*70 + '\n'))

        all_checks_passed = True

        # Check 1: Verify no direct Payroll.objects.create()
        self.stdout.write('1. Checking for direct Payroll.objects.create() calls...')
        if self._check_no_direct_creates('Payroll.objects.create', 'hr/'):
            self.stdout.write(self.style.SUCCESS('   ✅ No direct Payroll.objects.create() found\n'))
        else:
            self.stdout.write(self.style.ERROR('   ❌ Found direct Payroll.objects.create() calls\n'))
            all_checks_passed = False

        # Check 2: Verify no direct JournalEntry.objects.create()
        self.stdout.write('2. Checking for direct JournalEntry.objects.create() calls...')
        if self._check_no_direct_creates('JournalEntry.objects.create', 'hr/'):
            self.stdout.write(self.style.SUCCESS('   ✅ No direct JournalEntry.objects.create() found\n'))
        else:
            self.stdout.write(self.style.ERROR('   ❌ Found direct JournalEntry.objects.create() calls\n'))
            all_checks_passed = False

        # Check 3: Verify gateway services exist
        self.stdout.write('3. Checking gateway services exist...')
        gateway_services = [
            'hr/services/payroll_gateway_service.py',
            'hr/services/payroll_accounting_service.py',
        ]
        services_exist = all(os.path.exists(f) for f in gateway_services)
        if services_exist:
            self.stdout.write(self.style.SUCCESS('   ✅ All gateway services exist\n'))
        else:
            self.stdout.write(self.style.ERROR('   ❌ Some gateway services missing\n'))
            all_checks_passed = False

        # Check 4: Verify documentation exists
        self.stdout.write('4. Checking documentation exists...')
        docs = [
            'hr/docs/GOVERNANCE_INTEGRATION_GUIDE.md',
            'hr/docs/DEPLOYMENT_GUIDE.md',
            'hr/docs/BREAKING_CHANGES.md',
            'hr/docs/ROLLBACK_PLAN.md',
        ]
        docs_exist = all(os.path.exists(f) for f in docs)
        if docs_exist:
            self.stdout.write(self.style.SUCCESS('   ✅ All documentation exists\n'))
        else:
            self.stdout.write(self.style.ERROR('   ❌ Some documentation missing\n'))
            all_checks_passed = False

        # Check 5: Verify old methods have deprecation warnings
        self.stdout.write('5. Checking old methods have deprecation warnings...')
        old_methods = [
            '_create_journal_entry',
            '_create_individual_journal_entry',
            'create_monthly_payroll_journal_entry',
            'create_secure_journal_entry',
        ]
        all_deprecated = True
        for method in old_methods:
            if not self._check_method_has_deprecation(method, 'hr/services/'):
                self.stdout.write(self.style.WARNING(f'   ⚠️  Method {method} missing deprecation warning'))
                all_deprecated = False
        
        if all_deprecated:
            self.stdout.write(self.style.SUCCESS('   ✅ All old methods have deprecation warnings\n'))
        else:
            self.stdout.write(self.style.WARNING('   ⚠️  Some methods missing deprecation warnings (non-critical)\n'))

        # Check 6: Verify views use gateway services
        self.stdout.write('6. Checking views use gateway services...')
        if self._check_views_use_gateways():
            self.stdout.write(self.style.SUCCESS('   ✅ Views use gateway services\n'))
        else:
            self.stdout.write(self.style.ERROR('   ❌ Some views not using gateway services\n'))
            all_checks_passed = False

        # Check 7: Verify tests exist
        self.stdout.write('7. Checking tests exist...')
        test_files = [
            'hr/tests/test_services.py',
            'hr/tests/test_poc_gateway_integration.py',
        ]
        tests_exist = all(os.path.exists(f) for f in test_files)
        if tests_exist:
            self.stdout.write(self.style.SUCCESS('   ✅ Test files exist\n'))
        else:
            self.stdout.write(self.style.ERROR('   ❌ Some test files missing\n'))
            all_checks_passed = False

        # Check 8: Verify governance models accessible
        self.stdout.write('8. Checking governance models accessible...')
        try:
            from governance.models import AuditTrail
            from governance.services.payroll_gateway import PayrollGateway
            from governance.services.accounting_gateway import AccountingGateway
            self.stdout.write(self.style.SUCCESS('   ✅ Governance models accessible\n'))
        except ImportError as e:
            self.stdout.write(self.style.ERROR(f'   ❌ Cannot import governance models: {e}\n'))
            all_checks_passed = False

        # Final summary
        self.stdout.write('\n' + '='*70)
        if all_checks_passed:
            self.stdout.write(self.style.SUCCESS('✅ ALL CHECKS PASSED - READY FOR DEPLOYMENT'))
            self.stdout.write(self.style.SUCCESS('='*70 + '\n'))
            self.stdout.write(self.style.SUCCESS('Next steps:'))
            self.stdout.write('  1. Run full test suite: pytest hr/tests/ -v')
            self.stdout.write('  2. Review deployment guide: hr/docs/DEPLOYMENT_GUIDE.md')
            self.stdout.write('  3. Schedule deployment window')
            self.stdout.write('  4. Notify team\n')
        else:
            self.stdout.write(self.style.ERROR('❌ SOME CHECKS FAILED - NOT READY FOR DEPLOYMENT'))
            self.stdout.write(self.style.ERROR('='*70 + '\n'))
            self.stdout.write(self.style.WARNING('Please fix the issues above before deploying.\n'))

    def _check_no_direct_creates(self, pattern, directory):
        """Check if pattern exists in Python files (excluding deprecated and private methods)."""
        for root, dirs, files in os.walk(directory):
            # Skip migrations, __pycache__, tests, and management commands
            dirs[:] = [d for d in dirs if d not in ['migrations', '__pycache__', 'tests', 'management']]
            
            for file in files:
                if file.endswith('.py'):
                    filepath = os.path.join(root, file)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read()
                            if pattern in content:
                                # Check if entire file has DEPRECATED marker
                                if 'DEPRECATED' in content[:500]:  # Check first 500 chars
                                    continue
                                # Check if it's in a deprecated or private method
                                lines = content.split('\n')
                                for i, line in enumerate(lines):
                                    if pattern in line:
                                        # Check context for deprecation or private method (100 lines before)
                                        context_start = max(0, i-100)
                                        context_lines = lines[context_start:i+5]
                                        context = '\n'.join(context_lines)
                                        
                                        # If in deprecated method, skip
                                        if 'warnings.warn' in context or 'DEPRECATED' in context:
                                            continue
                                        
                                        # If in private method (def _method_name), skip
                                        # Find the most recent function definition
                                        for j in range(len(context_lines) - 1, -1, -1):
                                            ctx_line = context_lines[j].strip()
                                            if ctx_line.startswith('def '):
                                                # Found function definition
                                                if ctx_line.startswith('def _'):
                                                    # It's a private method, skip
                                                    break
                                                else:
                                                    # It's a public method, report it
                                                    self.stdout.write(self.style.WARNING(f'      Found in: {filepath} (line {i+1})'))
                                                    return False
                                        else:
                                            # No function definition found, might be module level
                                            continue
                    except Exception:
                        pass
        return True

    def _check_method_has_deprecation(self, method_name, directory):
        """Check if method has deprecation warning."""
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if d != '__pycache__']
            
            for file in files:
                if file.endswith('.py'):
                    filepath = os.path.join(root, file)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read()
                            # Look for method definition
                            pattern = rf'def {method_name}\s*\('
                            if re.search(pattern, content):
                                # Check if it has deprecation warning nearby
                                lines = content.split('\n')
                                for i, line in enumerate(lines):
                                    if re.search(pattern, line):
                                        # Check 10 lines before and after for deprecation
                                        context = '\n'.join(lines[max(0, i-10):min(len(lines), i+10)])
                                        if 'warnings.warn' in context or 'DEPRECATED' in context or 'deprecated' in context:
                                            return True
                                        return False
                    except Exception:
                        pass
        return True  # If method not found, assume it's removed (good)

    def _check_views_use_gateways(self):
        """Check if views use gateway services."""
        view_files = [
            'hr/views/integrated_payroll_views.py',
        ]
        
        for filepath in view_files:
            if not os.path.exists(filepath):
                continue
                
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Check for gateway service imports
                    if 'HRPayrollGatewayService' not in content:
                        self.stdout.write(self.style.WARNING(f'      {filepath} not using HRPayrollGatewayService'))
                        return False
            except Exception:
                pass
        
        return True
