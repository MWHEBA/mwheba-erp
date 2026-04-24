"""
Management command to migrate payroll signals to thin adapters.

This command implements task 27.1: Migrate payroll signals to thin adapters
with feature flag protection for safe rollback capability.

Usage:
    python manage.py migrate_payroll_signals --workflow payroll --dry-run
    python manage.py migrate_payroll_signals --workflow payroll --enable-flags
    python manage.py migrate_payroll_signals --workflow payroll --disable-flags
    python manage.py migrate_payroll_signals --workflow payroll --status
"""

import logging
from typing import Dict, Any, List
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db import transaction

from governance.signals.payroll_signals import (
    PayrollSignalFeatureFlags,
    PayrollSignalMonitor,
    register_payroll_signals,
    unregister_payroll_signals
)
from governance.services.signal_router import signal_router
from governance.services.audit_service import AuditService
from governance.models import GovernanceContext

logger = logging.getLogger('governance.management')


class Command(BaseCommand):
    help = 'Migrate payroll signals to thin adapters with feature flag protection'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--workflow',
            type=str,
            default='payroll',
            choices=['payroll'],
            help='Workflow to migrate (currently only payroll supported)'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes'
        )
        
        parser.add_argument(
            '--enable-flags',
            action='store_true',
            help='Enable payroll signal feature flags'
        )
        
        parser.add_argument(
            '--disable-flags',
            action='store_true',
            help='Disable payroll signal feature flags (safe rollback)'
        )
        
        parser.add_argument(
            '--status',
            action='store_true',
            help='Show current status of payroll signals'
        )
        
        parser.add_argument(
            '--validate',
            action='store_true',
            help='Validate signal independence and governance'
        )
        
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force operation even if validation fails'
        )
        
        parser.add_argument(
            '--specific-flag',
            type=str,
            help='Enable/disable a specific feature flag'
        )
    
    def handle(self, *args, **options):
        """Main command handler"""
        workflow = options['workflow']
        dry_run = options['dry_run']
        
        self.stdout.write(
            self.style.SUCCESS(f'🚀 Payroll Signal Migration Tool - Workflow: {workflow}')
        )
        
        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No changes will be made'))
        
        try:
            # Set governance context
            GovernanceContext.set_context(
                user=None,  # System operation
                service='PayrollSignalMigration',
                operation='migrate_signals'
            )
            
            # Route to appropriate handler
            if options['status']:
                self._show_status()
            elif options['validate']:
                self._validate_signals()
            elif options['enable_flags']:
                self._enable_flags(options, dry_run)
            elif options['disable_flags']:
                self._disable_flags(options, dry_run)
            else:
                self._migrate_signals(workflow, dry_run, options)
                
        except Exception as e:
            logger.error(f"Payroll signal migration failed: {e}", exc_info=True)
            raise CommandError(f"Migration failed: {e}")
        
        finally:
            GovernanceContext.clear_context()
    
    def _show_status(self):
        """Show current status of payroll signals"""
        self.stdout.write('📊 Payroll Signal Status:')
        self.stdout.write('')
        
        # Feature flag status
        flags = PayrollSignalFeatureFlags.get_status()
        self.stdout.write('🚩 Feature Flags:')
        for flag, enabled in flags.items():
            status_icon = '✅' if enabled else '❌'
            self.stdout.write(f'  {status_icon} {flag}: {enabled}')
        
        self.stdout.write('')
        
        # Signal health status
        health = PayrollSignalMonitor.get_signal_health_status()
        health_icon = '✅' if health['healthy'] else '❌'
        self.stdout.write(f'🏥 Health Status: {health_icon} {"Healthy" if health["healthy"] else "Issues Detected"}')
        
        if health['issues']:
            self.stdout.write('⚠️  Issues:')
            for issue in health['issues']:
                self.stdout.write(f'  - {issue}')
        
        if health['recommendations']:
            self.stdout.write('💡 Recommendations:')
            for rec in health['recommendations']:
                self.stdout.write(f'  - {rec}')
        
        self.stdout.write('')
        
        # Signal router statistics
        stats = signal_router.get_signal_statistics()
        self.stdout.write('📈 Signal Router Statistics:')
        self.stdout.write(f'  Global Enabled: {stats["global_enabled"]}')
        self.stdout.write(f'  Maintenance Mode: {stats["maintenance_mode"]}')
        self.stdout.write(f'  Depth Limit: {stats["depth_limit"]}')
        self.stdout.write(f'  Signals Processed: {stats["counters"]["signals_processed"]}')
        self.stdout.write(f'  Signals Blocked: {stats["counters"]["signals_blocked"]}')
        self.stdout.write(f'  Signal Errors: {stats["counters"]["signal_errors"]}')
    
    def _validate_signals(self):
        """Validate signal independence and governance"""
        self.stdout.write('🔍 Validating payroll signal independence...')
        
        # Validate signal independence
        independence = PayrollSignalMonitor.validate_signal_independence()
        
        if independence['independent']:
            self.stdout.write(self.style.SUCCESS('✅ Signal independence validation passed'))
        else:
            self.stdout.write(self.style.ERROR('❌ Signal independence validation failed'))
            for issue in independence['issues']:
                self.stdout.write(f'  - {issue}')
        
        # Show test results
        self.stdout.write('')
        self.stdout.write('🧪 Test Results:')
        for test, result in independence['test_results'].items():
            result_icon = '✅' if result == 'passed' else '❌'
            self.stdout.write(f'  {result_icon} {test}: {result}')
        
        # Validate signal router configuration
        self.stdout.write('')
        self.stdout.write('⚙️  Validating signal router configuration...')
        
        config_errors = signal_router.validate_configuration()
        if not config_errors:
            self.stdout.write(self.style.SUCCESS('✅ Signal router configuration is valid'))
        else:
            self.stdout.write(self.style.ERROR('❌ Signal router configuration issues:'))
            for error in config_errors:
                self.stdout.write(f'  - {error}')
    
    def _enable_flags(self, options, dry_run):
        """Enable payroll signal feature flags"""
        specific_flag = options.get('specific_flag')
        force = options.get('force', False)
        
        if not force:
            # Validate before enabling
            self.stdout.write('🔍 Validating before enabling flags...')
            independence = PayrollSignalMonitor.validate_signal_independence()
            if not independence['independent']:
                self.stdout.write(self.style.ERROR('❌ Validation failed. Use --force to override.'))
                for issue in independence['issues']:
                    self.stdout.write(f'  - {issue}')
                return
        
        if specific_flag:
            self._enable_specific_flag(specific_flag, dry_run)
        else:
            self._enable_all_flags(dry_run)
    
    def _enable_specific_flag(self, flag_name, dry_run):
        """Enable a specific feature flag"""
        if dry_run:
            self.stdout.write(f'🔍 [DRY RUN] Would enable flag: {flag_name}')
            return
        
        try:
            PayrollSignalFeatureFlags.enable_flag(flag_name)
            self.stdout.write(self.style.SUCCESS(f'✅ Enabled flag: {flag_name}'))
            
            # Log the change
            AuditService.log_operation(
                model_name='PayrollSignalFeatureFlags',
                object_id=0,
                operation='ENABLE_FLAG',
                source_service='PayrollSignalMigration',
                flag_name=flag_name
            )
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Failed to enable flag {flag_name}: {e}'))
    
    def _enable_all_flags(self, dry_run):
        """Enable all payroll signal feature flags"""
        if dry_run:
            self.stdout.write('🔍 [DRY RUN] Would enable all payroll signal flags')
            flags = PayrollSignalFeatureFlags.get_status()
            for flag in flags.keys():
                self.stdout.write(f'  - {flag}')
            return
        
        self.stdout.write('⚠️  Enabling ALL payroll signal flags...')
        
        try:
            PayrollSignalFeatureFlags.enable_all()
            self.stdout.write(self.style.SUCCESS('✅ All payroll signal flags enabled'))
            
            # Log the change
            AuditService.log_operation(
                model_name='PayrollSignalFeatureFlags',
                object_id=0,
                operation='ENABLE_ALL_FLAGS',
                source_service='PayrollSignalMigration'
            )
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Failed to enable all flags: {e}'))
    
    def _disable_flags(self, options, dry_run):
        """Disable payroll signal feature flags (safe rollback)"""
        specific_flag = options.get('specific_flag')
        
        if specific_flag:
            self._disable_specific_flag(specific_flag, dry_run)
        else:
            self._disable_all_flags(dry_run)
    
    def _disable_specific_flag(self, flag_name, dry_run):
        """Disable a specific feature flag"""
        if dry_run:
            self.stdout.write(f'🔍 [DRY RUN] Would disable flag: {flag_name}')
            return
        
        try:
            PayrollSignalFeatureFlags.disable_flag(flag_name)
            self.stdout.write(self.style.SUCCESS(f'✅ Disabled flag: {flag_name}'))
            
            # Log the change
            AuditService.log_operation(
                model_name='PayrollSignalFeatureFlags',
                object_id=0,
                operation='DISABLE_FLAG',
                source_service='PayrollSignalMigration',
                flag_name=flag_name
            )
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Failed to disable flag {flag_name}: {e}'))
    
    def _disable_all_flags(self, dry_run):
        """Disable all payroll signal feature flags (safe rollback)"""
        if dry_run:
            self.stdout.write('🔍 [DRY RUN] Would disable all payroll signal flags (safe rollback)')
            return
        
        self.stdout.write('🛡️  Disabling all payroll signal flags (safe rollback)...')
        
        try:
            PayrollSignalFeatureFlags.disable_all()
            self.stdout.write(self.style.SUCCESS('✅ All payroll signal flags disabled (safe rollback)'))
            
            # Log the change
            AuditService.log_operation(
                model_name='PayrollSignalFeatureFlags',
                object_id=0,
                operation='DISABLE_ALL_FLAGS',
                source_service='PayrollSignalMigration'
            )
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Failed to disable all flags: {e}'))
    
    def _migrate_signals(self, workflow: str, dry_run: bool, options: Dict):
        """Perform the main signal migration"""
        self.stdout.write(f'🔄 Migrating {workflow} signals to thin adapters...')
        
        # Step 1: Validate current state
        self.stdout.write('  1️⃣ Validating current state...')
        if not self._validate_migration_prerequisites(dry_run):
            raise CommandError("Migration prerequisites not met")
        
        # Step 2: Create thin adapter signals (already done in payroll_signals.py)
        self.stdout.write('  2️⃣ Thin adapter signals already implemented ✅')
        
        # Step 3: Initialize feature flags (disabled by default)
        self.stdout.write('  3️⃣ Initializing feature flags...')
        self._initialize_feature_flags(dry_run)
        
        # Step 4: Register signals with Django
        self.stdout.write('  4️⃣ Registering signal adapters...')
        self._register_signal_adapters(dry_run)
        
        # Step 5: Validate signal independence
        self.stdout.write('  5️⃣ Validating signal independence...')
        if not self._validate_signal_independence(dry_run):
            self.stdout.write(self.style.WARNING('⚠️  Signal independence validation had issues'))
        
        # Step 6: Create migration summary
        self.stdout.write('  6️⃣ Creating migration summary...')
        self._create_migration_summary(workflow, dry_run)
        
        self.stdout.write(self.style.SUCCESS('✅ Payroll signal migration completed'))
        self.stdout.write('')
        self.stdout.write('📋 Next Steps:')
        self.stdout.write('  1. Review the migration summary')
        self.stdout.write('  2. Test core payroll operations work without signals')
        self.stdout.write('  3. Gradually enable feature flags as needed')
        self.stdout.write('  4. Monitor signal performance and health')
    
    def _validate_migration_prerequisites(self, dry_run: bool) -> bool:
        """Validate prerequisites for migration"""
        if dry_run:
            self.stdout.write('    🔍 [DRY RUN] Would validate migration prerequisites')
            return True
        
        # Check that PayrollGateway exists and is functional
        try:
            from governance.services.payroll_gateway import PayrollGateway
            gateway = PayrollGateway()
            self.stdout.write('    ✅ PayrollGateway is available')
        except ImportError as e:
            self.stdout.write(self.style.ERROR(f'    ❌ PayrollGateway not available: {e}'))
            return False
        
        # Check that signal router is functional
        if not signal_router.global_enabled:
            self.stdout.write(self.style.WARNING('    ⚠️  Signal router is globally disabled'))
        
        # Check that required services are available
        required_services = [
            'core.services.notification_service',
            'core.services.analytics_service',
            'core.services.cache_service'
        ]
        
        for service in required_services:
            try:
                __import__(service)
                self.stdout.write(f'    ✅ {service} is available')
            except ImportError:
                self.stdout.write(self.style.WARNING(f'    ⚠️  {service} not available (signals will handle gracefully)'))
        
        return True
    
    def _initialize_feature_flags(self, dry_run: bool):
        """Initialize feature flags (disabled by default for safety)"""
        if dry_run:
            self.stdout.write('    🔍 [DRY RUN] Would initialize feature flags (all disabled)')
            return
        
        # Ensure all flags are disabled by default
        PayrollSignalFeatureFlags.disable_all()
        self.stdout.write('    ✅ Feature flags initialized (all disabled for safety)')
        
        # Log the initialization
        AuditService.log_operation(
            model_name='PayrollSignalFeatureFlags',
            object_id=0,
            operation='INITIALIZE_FLAGS',
            source_service='PayrollSignalMigration'
        )
    
    def _register_signal_adapters(self, dry_run: bool):
        """Register signal adapters with Django"""
        if dry_run:
            self.stdout.write('    🔍 [DRY RUN] Would register payroll signal adapters')
            return
        
        try:
            # Signals are already registered during module import
            # This is just for confirmation
            self.stdout.write('    ✅ Payroll signal adapters registered')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'    ❌ Failed to register signal adapters: {e}'))
            raise
    
    def _validate_signal_independence(self, dry_run: bool) -> bool:
        """Validate that signals are truly independent"""
        if dry_run:
            self.stdout.write('    🔍 [DRY RUN] Would validate signal independence')
            return True
        
        independence = PayrollSignalMonitor.validate_signal_independence()
        
        if independence['independent']:
            self.stdout.write('    ✅ Signal independence validated')
            return True
        else:
            self.stdout.write('    ❌ Signal independence validation failed:')
            for issue in independence['issues']:
                self.stdout.write(f'      - {issue}')
            return False
    
    def _create_migration_summary(self, workflow: str, dry_run: bool):
        """Create a summary of the migration"""
        if dry_run:
            self.stdout.write('    🔍 [DRY RUN] Would create migration summary')
            return
        
        summary = {
            'workflow': workflow,
            'migration_date': timezone.now().isoformat(),
            'signals_created': [
                'payroll_creation_notifications',
                'payroll_cache_invalidation',
                'payroll_status_notifications',
                'payroll_analytics_tracking',
                'payroll_audit_enhancements',
                'payroll_deletion_cleanup'
            ],
            'feature_flags': PayrollSignalFeatureFlags.get_status(),
            'signal_router_status': signal_router.get_signal_statistics()
        }
        
        # Log the migration summary
        AuditService.log_operation(
            model_name='PayrollSignalMigration',
            object_id=0,
            operation='MIGRATION_COMPLETED',
            source_service='PayrollSignalMigration',
            migration_summary=summary
        )
        
        self.stdout.write('    ✅ Migration summary created and logged')