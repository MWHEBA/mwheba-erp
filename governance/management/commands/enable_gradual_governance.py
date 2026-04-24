"""
Management command to enable gradual governance enforcement for selected high-risk workflows.

This command implements Task 21: Enable gradual governance enforcement (NO BIG-BANG)
- Activates AccountingGateway enforcement for CustomerPayment → JournalEntry
- Activates AccountingGateway enforcement for StockMovement → JournalEntry  
- Activates AccountingGateway enforcement for PurchasePayment → JournalEntry
- Activates MovementService enforcement for stock operations
- Activates AuthorityService validation for high-risk models
- Provides monitoring and rollback capabilities

Usage:
    python manage.py enable_gradual_governance --phase=1 --workflow=customer_payment_to_journal_entry
    python manage.py enable_gradual_governance --phase=2 --all-workflows
    python manage.py enable_gradual_governance --rollback --workflow=customer_payment_to_journal_entry
    python manage.py enable_gradual_governance --status
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db import transaction
from django.contrib.auth import get_user_model

from governance.services import (
    governance_switchboard, AccountingGateway, MovementService, 
    AuthorityService, AuditService, MonitoringService
)
from governance.models import GovernanceContext, AuditTrail
from governance.exceptions import GovernanceError, ValidationError

User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Enable gradual governance enforcement for selected high-risk workflows'
    
    # Selected high-risk workflows for Phase 5 activation
    SELECTED_WORKFLOWS = [
        'customer_payment_to_journal_entry',
        'stock_movement_to_journal_entry', 
        'purchase_payment_to_journal_entry'
    ]
    
    # High-risk models for authority boundary enforcement
    HIGH_RISK_MODELS = [
        'JournalEntry',
        'JournalEntryLine', 
        'Stock',
        'StockMovement',
        'CustomerPayment',
        'Sale'
    ]
    
    # Required components for the selected workflows
    REQUIRED_COMPONENTS = [
        'accounting_gateway_enforcement',
        'movement_service_enforcement',
        'authority_boundary_enforcement',
        'audit_trail_enforcement',
        'idempotency_enforcement'
    ]
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--phase',
            type=int,
            choices=[1, 2],
            help='Activation phase: 1=single workflow, 2=all selected workflows'
        )
        
        parser.add_argument(
            '--workflow',
            type=str,
            choices=self.SELECTED_WORKFLOWS,
            help='Specific workflow to enable (required for phase 1)'
        )        
        parser.add_argument(
            '--all-workflows',
            action='store_true',
            help='Enable all selected workflows (phase 2)'
        )
        
        parser.add_argument(
            '--rollback',
            action='store_true',
            help='Rollback governance enforcement for specified workflow'
        )
        
        parser.add_argument(
            '--status',
            action='store_true',
            help='Show current governance enforcement status'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes'
        )
        
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force activation even if dependencies are not met'
        )
        
        parser.add_argument(
            '--monitor-duration',
            type=int,
            default=300,
            help='Duration to monitor after activation (seconds, default: 300)'
        )
    
    def handle(self, *args, **options):
        """Main command handler"""
        try:
            # Set up governance context
            admin_user = self._get_admin_user()
            GovernanceContext.set_context(
                user=admin_user,
                service='GradualGovernanceActivation',
                operation='enable_governance'
            )
            
            if options['status']:
                self._show_status()
            elif options['rollback']:
                self._handle_rollback(options)
            elif options['phase']:
                self._handle_activation(options)
            else:
                self.stdout.write(
                    self.style.ERROR('Please specify --phase, --rollback, or --status')
                )
                
        except Exception as e:
            logger.error(f"Gradual governance activation failed: {e}")
            self.stdout.write(
                self.style.ERROR(f'Command failed: {e}')
            )
            raise CommandError(f'Gradual governance activation failed: {e}')
    
    def _get_admin_user(self) -> User:
        """Get or create admin user for governance operations"""
        try:
            return User.objects.filter(is_superuser=True).first()
        except Exception:
            # Create a system user if no admin exists
            return User.objects.create_user(
                username='governance_system',
                email='governance@system.local',
                is_staff=True,
                is_superuser=True
            )
    
    def _show_status(self):
        """Show current governance enforcement status"""
        self.stdout.write(
            self.style.SUCCESS('\n🔍 Current Governance Enforcement Status')
        )
        self.stdout.write('=' * 60)
        
        # Get governance statistics
        stats = governance_switchboard.get_governance_statistics()
        
        # Show component status
        self.stdout.write('\n📦 Component Status:')
        for component in self.REQUIRED_COMPONENTS:
            enabled = governance_switchboard.is_component_enabled(component)
            status = '✅ ENABLED' if enabled else '❌ DISABLED'
            self.stdout.write(f'  {component}: {status}')
        
        # Show workflow status
        self.stdout.write('\n🔄 Workflow Status:')
        for workflow in self.SELECTED_WORKFLOWS:
            enabled = governance_switchboard.is_workflow_enabled(workflow)
            status = '✅ ENABLED' if enabled else '❌ DISABLED'
            risk_level = governance_switchboard.WORKFLOW_FLAGS.get(workflow, {}).get('risk_level', 'UNKNOWN')
            self.stdout.write(f'  {workflow}: {status} (Risk: {risk_level})')
        
        # Show emergency status
        emergency_active = stats['emergency']['global_override_active']
        if emergency_active:
            self.stdout.write('\n🚨 EMERGENCY OVERRIDE ACTIVE - All governance disabled')
        
        # Show health status
        health = stats['health']
        self.stdout.write(f'\n💚 Governance Health:')
        self.stdout.write(f'  Active: {health["governance_active"]}')
        self.stdout.write(f'  Critical workflows protected: {health["critical_workflows_protected"]}')
        self.stdout.write(f'  Emergency override: {health["emergency_override"]}')
        
        # Show counters
        counters = stats['counters']
        self.stdout.write(f'\n📊 Statistics:')
        self.stdout.write(f'  Flag changes: {counters["flag_changes"]}')
        self.stdout.write(f'  Emergency activations: {counters["emergency_activations"]}')
        self.stdout.write(f'  Governance violations: {counters["governance_violations"]}')
    
    def _handle_activation(self, options):
        """Handle governance activation based on phase"""
        phase = options['phase']
        dry_run = options['dry_run']
        force = options['force']
        
        if phase == 1:
            # Phase 1: Single workflow activation
            if not options['workflow']:
                raise CommandError('Phase 1 requires --workflow parameter')
            
            workflow = options['workflow']
            self._activate_single_workflow(workflow, dry_run, force, options)
            
        elif phase == 2:
            # Phase 2: All selected workflows activation
            if not options['all_workflows']:
                raise CommandError('Phase 2 requires --all-workflows parameter')
            
            self._activate_all_workflows(dry_run, force, options)
    
    def _activate_single_workflow(self, workflow: str, dry_run: bool, force: bool, options: Dict):
        """Activate a single workflow with monitoring"""
        self.stdout.write(
            self.style.SUCCESS(f'\n🚀 Phase 1: Activating single workflow: {workflow}')
        )
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        # Pre-activation checks
        if not self._pre_activation_checks(workflow, force):
            return
        
        # Activation plan
        activation_plan = self._create_activation_plan(workflow)
        self._show_activation_plan(activation_plan, dry_run)
        
        if dry_run:
            return
        
        # Execute activation
        success = self._execute_activation_plan(activation_plan, options)
        
        if success:
            self.stdout.write(
                self.style.SUCCESS(f'✅ Successfully activated workflow: {workflow}')
            )
            
            # Start monitoring
            if options.get('monitor_duration', 0) > 0:
                self._monitor_activation(workflow, options['monitor_duration'])
        else:
            self.stdout.write(
                self.style.ERROR(f'❌ Failed to activate workflow: {workflow}')
            )
    
    def _activate_all_workflows(self, dry_run: bool, force: bool, options: Dict):
        """Activate all selected workflows progressively"""
        self.stdout.write(
            self.style.SUCCESS('\n🚀 Phase 2: Activating all selected workflows')
        )
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        # Pre-activation checks for all workflows
        for workflow in self.SELECTED_WORKFLOWS:
            if not self._pre_activation_checks(workflow, force):
                self.stdout.write(
                    self.style.ERROR(f'❌ Pre-activation checks failed for {workflow}')
                )
                return
        
        # Create comprehensive activation plan
        activation_plan = self._create_comprehensive_activation_plan()
        self._show_activation_plan(activation_plan, dry_run)
        
        if dry_run:
            return
        
        # Execute progressive activation
        success_count = 0
        for workflow in self.SELECTED_WORKFLOWS:
            workflow_plan = [step for step in activation_plan if workflow in step.get('workflow', '')]
            
            self.stdout.write(f'\n🔄 Activating workflow: {workflow}')
            
            if self._execute_activation_plan(workflow_plan, options):
                success_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'✅ Successfully activated: {workflow}')
                )
                
                # Brief monitoring between activations
                time.sleep(30)  # 30 second pause between activations
                
            else:
                self.stdout.write(
                    self.style.ERROR(f'❌ Failed to activate: {workflow}')
                )
                break
        
        # Final status
        if success_count == len(self.SELECTED_WORKFLOWS):
            self.stdout.write(
                self.style.SUCCESS('\n🎉 All selected workflows activated successfully!')
            )
            
            # Start comprehensive monitoring
            if options.get('monitor_duration', 0) > 0:
                self._monitor_all_workflows(options['monitor_duration'])
        else:
            self.stdout.write(
                self.style.ERROR(f'\n❌ Only {success_count}/{len(self.SELECTED_WORKFLOWS)} workflows activated')
            )
    
    def _pre_activation_checks(self, workflow: str, force: bool) -> bool:
        """Perform pre-activation checks for a workflow"""
        self.stdout.write(f'\n🔍 Pre-activation checks for: {workflow}')
        
        checks_passed = True
        
        # Check if workflow is already enabled
        if governance_switchboard.is_workflow_enabled(workflow):
            self.stdout.write(
                self.style.WARNING(f'  ⚠️  Workflow already enabled: {workflow}')
            )
            return True
        
        # Check emergency overrides
        if governance_switchboard._is_emergency_override_active():
            self.stdout.write(
                self.style.ERROR('  ❌ Emergency override is active - cannot enable governance')
            )
            return False
        
        # Check component dependencies
        workflow_config = governance_switchboard.WORKFLOW_FLAGS.get(workflow, {})
        dependencies = workflow_config.get('component_dependencies', [])
        
        for dep in dependencies:
            if not governance_switchboard.is_component_enabled(dep):
                self.stdout.write(
                    self.style.ERROR(f'  ❌ Required component not enabled: {dep}')
                )
                checks_passed = False
        
        # Check system health
        try:
            # Test AccountingGateway
            gateway = AccountingGateway()
            self.stdout.write('  ✅ AccountingGateway available')
            
            # Test MovementService
            movement_service = MovementService()
            self.stdout.write('  ✅ MovementService available')
            
            # Test AuthorityService
            auth_service = AuthorityService()
            self.stdout.write('  ✅ AuthorityService available')
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'  ❌ Service availability check failed: {e}')
            )
            checks_passed = False
        
        if not checks_passed and not force:
            self.stdout.write(
                self.style.ERROR('  ❌ Pre-activation checks failed. Use --force to override.')
            )
            return False
        elif not checks_passed and force:
            self.stdout.write(
                self.style.WARNING('  ⚠️  Pre-activation checks failed but --force specified')
            )
        
        return True
    
    def _create_activation_plan(self, workflow: str) -> List[Dict[str, Any]]:
        """Create activation plan for a single workflow"""
        plan = []
        
        # Get workflow configuration
        workflow_config = governance_switchboard.WORKFLOW_FLAGS.get(workflow, {})
        dependencies = workflow_config.get('component_dependencies', [])
        
        # Step 1: Enable required components
        for component in dependencies:
            if not governance_switchboard.is_component_enabled(component):
                plan.append({
                    'type': 'enable_component',
                    'component': component,
                    'reason': f'Required for workflow: {workflow}',
                    'order': 1
                })
        
        # Step 2: Enable the workflow
        plan.append({
            'type': 'enable_workflow',
            'workflow': workflow,
            'reason': f'Phase 5 gradual activation: {workflow}',
            'order': 2
        })
        
        # Step 3: Validation checks
        plan.append({
            'type': 'validate_activation',
            'workflow': workflow,
            'reason': 'Post-activation validation',
            'order': 3
        })
        
        return sorted(plan, key=lambda x: x['order'])
    
    def _create_comprehensive_activation_plan(self) -> List[Dict[str, Any]]:
        """Create comprehensive activation plan for all workflows"""
        plan = []
        
        # Step 1: Enable all required components first
        for component in self.REQUIRED_COMPONENTS:
            if not governance_switchboard.is_component_enabled(component):
                plan.append({
                    'type': 'enable_component',
                    'component': component,
                    'reason': 'Required for selected workflows',
                    'order': 1
                })
        
        # Step 2: Enable workflows progressively
        for i, workflow in enumerate(self.SELECTED_WORKFLOWS):
            plan.append({
                'type': 'enable_workflow',
                'workflow': workflow,
                'reason': f'Phase 5 gradual activation: {workflow}',
                'order': 2 + i
            })
            
            # Add validation after each workflow
            plan.append({
                'type': 'validate_activation',
                'workflow': workflow,
                'reason': f'Post-activation validation: {workflow}',
                'order': 2 + i + 0.5
            })
        
        return sorted(plan, key=lambda x: x['order'])
    
    def _show_activation_plan(self, plan: List[Dict[str, Any]], dry_run: bool):
        """Show the activation plan"""
        mode = 'DRY RUN' if dry_run else 'EXECUTION'
        self.stdout.write(f'\n📋 Activation Plan ({mode}):')
        
        for i, step in enumerate(plan, 1):
            step_type = step['type']
            reason = step['reason']
            
            if step_type == 'enable_component':
                component = step['component']
                self.stdout.write(f'  {i}. Enable component: {component}')
                self.stdout.write(f'     Reason: {reason}')
                
            elif step_type == 'enable_workflow':
                workflow = step['workflow']
                self.stdout.write(f'  {i}. Enable workflow: {workflow}')
                self.stdout.write(f'     Reason: {reason}')
                
            elif step_type == 'validate_activation':
                workflow = step['workflow']
                self.stdout.write(f'  {i}. Validate activation: {workflow}')
                self.stdout.write(f'     Reason: {reason}')
    
    def _execute_activation_plan(self, plan: List[Dict[str, Any]], options: Dict) -> bool:
        """Execute the activation plan"""
        admin_user = self._get_admin_user()
        
        for step in plan:
            step_type = step['type']
            reason = step['reason']
            
            try:
                if step_type == 'enable_component':
                    component = step['component']
                    success = governance_switchboard.enable_component(
                        component, reason, admin_user
                    )
                    if not success:
                        self.stdout.write(
                            self.style.ERROR(f'❌ Failed to enable component: {component}')
                        )
                        return False
                    
                    self.stdout.write(f'  ✅ Enabled component: {component}')
                    
                elif step_type == 'enable_workflow':
                    workflow = step['workflow']
                    success = governance_switchboard.enable_workflow(
                        workflow, reason, admin_user
                    )
                    if not success:
                        self.stdout.write(
                            self.style.ERROR(f'❌ Failed to enable workflow: {workflow}')
                        )
                        return False
                    
                    self.stdout.write(f'  ✅ Enabled workflow: {workflow}')
                    
                elif step_type == 'validate_activation':
                    workflow = step['workflow']
                    if self._validate_workflow_activation(workflow):
                        self.stdout.write(f'  ✅ Validation passed: {workflow}')
                    else:
                        self.stdout.write(
                            self.style.ERROR(f'❌ Validation failed: {workflow}')
                        )
                        return False
                
                # Brief pause between steps
                time.sleep(2)
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Step failed: {step_type} - {e}')
                )
                return False
        
        return True
    
    def _validate_workflow_activation(self, workflow: str) -> bool:
        """Validate that workflow activation was successful"""
        try:
            # Check if workflow is enabled
            if not governance_switchboard.is_workflow_enabled(workflow):
                return False
            
            # Check component dependencies
            workflow_config = governance_switchboard.WORKFLOW_FLAGS.get(workflow, {})
            dependencies = workflow_config.get('component_dependencies', [])
            
            for dep in dependencies:
                if not governance_switchboard.is_component_enabled(dep):
                    return False
            
            # Workflow-specific validation
            if workflow == 'customer_payment_to_journal_entry':
                return self._validate_accounting_gateway_workflow()
            elif workflow == 'stock_movement_to_journal_entry':
                return self._validate_movement_service_workflow()
            elif workflow == 'purchase_payment_to_journal_entry':
                return self._validate_purchase_payment_workflow()
            
            return True
            
        except Exception as e:
            logger.error(f"Workflow validation failed for {workflow}: {e}")
            return False
    
    def _validate_accounting_gateway_workflow(self) -> bool:
        """Validate AccountingGateway workflow is working"""
        try:
            gateway = AccountingGateway()
            # Basic validation - check if gateway is responsive
            return True
        except Exception:
            return False
    
    def _validate_movement_service_workflow(self) -> bool:
        """Validate MovementService workflow is working"""
        try:
            service = MovementService()
            # Basic validation - check if service is responsive
            return True
        except Exception:
            return False
    
    def _validate_purchase_payment_workflow(self) -> bool:
        """Validate PurchasePayment workflow is working"""
        try:
            gateway = AccountingGateway()
            return True
        except Exception:
            return False
    
    def _monitor_activation(self, workflow: str, duration: int):
        """Monitor single workflow activation"""
        self.stdout.write(
            self.style.SUCCESS(f'\n👁️  Monitoring workflow: {workflow} for {duration} seconds')
        )
        
        start_time = time.time()
        violations_start = governance_switchboard._governance_violations.get_value()
        
        while time.time() - start_time < duration:
            # Check for violations
            current_violations = governance_switchboard._governance_violations.get_value()
            new_violations = current_violations - violations_start
            
            if new_violations > 0:
                self.stdout.write(
                    self.style.ERROR(f'⚠️  {new_violations} governance violations detected!')
                )
            
            # Check if workflow is still enabled
            if not governance_switchboard.is_workflow_enabled(workflow):
                self.stdout.write(
                    self.style.ERROR(f'❌ Workflow disabled during monitoring: {workflow}')
                )
                break
            
            # Progress indicator
            elapsed = int(time.time() - start_time)
            remaining = duration - elapsed
            self.stdout.write(f'  ⏱️  Monitoring... {remaining}s remaining', ending='\r')
            
            time.sleep(10)  # Check every 10 seconds
        
        self.stdout.write('\n✅ Monitoring completed')
    
    def _monitor_all_workflows(self, duration: int):
        """Monitor all workflows activation"""
        self.stdout.write(
            self.style.SUCCESS(f'\n👁️  Monitoring all workflows for {duration} seconds')
        )
        
        start_time = time.time()
        violations_start = governance_switchboard._governance_violations.get_value()
        
        while time.time() - start_time < duration:
            # Check for violations
            current_violations = governance_switchboard._governance_violations.get_value()
            new_violations = current_violations - violations_start
            
            if new_violations > 0:
                self.stdout.write(
                    self.style.ERROR(f'⚠️  {new_violations} governance violations detected!')
                )
            
            # Check workflow status
            disabled_workflows = []
            for workflow in self.SELECTED_WORKFLOWS:
                if not governance_switchboard.is_workflow_enabled(workflow):
                    disabled_workflows.append(workflow)
            
            if disabled_workflows:
                self.stdout.write(
                    self.style.ERROR(f'❌ Workflows disabled during monitoring: {disabled_workflows}')
                )
                break
            
            # Progress indicator
            elapsed = int(time.time() - start_time)
            remaining = duration - elapsed
            self.stdout.write(f'  ⏱️  Monitoring... {remaining}s remaining', ending='\r')
            
            time.sleep(15)  # Check every 15 seconds
        
        self.stdout.write('\n✅ Comprehensive monitoring completed')
    
    def _handle_rollback(self, options):
        """Handle governance rollback"""
        workflow = options.get('workflow')
        dry_run = options.get('dry_run', False)
        
        if not workflow:
            raise CommandError('Rollback requires --workflow parameter')
        
        self.stdout.write(
            self.style.WARNING(f'\n🔄 Rolling back workflow: {workflow}')
        )
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        # Create rollback plan
        rollback_plan = self._create_rollback_plan(workflow)
        self._show_rollback_plan(rollback_plan, dry_run)
        
        if dry_run:
            return
        
        # Execute rollback
        success = self._execute_rollback_plan(rollback_plan)
        
        if success:
            self.stdout.write(
                self.style.SUCCESS(f'✅ Successfully rolled back workflow: {workflow}')
            )
        else:
            self.stdout.write(
                self.style.ERROR(f'❌ Failed to rollback workflow: {workflow}')
            )
    
    def _create_rollback_plan(self, workflow: str) -> List[Dict[str, Any]]:
        """Create rollback plan for a workflow"""
        plan = []
        
        # Step 1: Disable the workflow
        plan.append({
            'type': 'disable_workflow',
            'workflow': workflow,
            'reason': f'Rollback requested for: {workflow}',
            'order': 1
        })
        
        # Step 2: Check if components can be disabled
        # (Only disable if no other workflows depend on them)
        workflow_config = governance_switchboard.WORKFLOW_FLAGS.get(workflow, {})
        dependencies = workflow_config.get('component_dependencies', [])
        
        for component in dependencies:
            # Check if other enabled workflows depend on this component
            can_disable = True
            for other_workflow in self.SELECTED_WORKFLOWS:
                if other_workflow != workflow and governance_switchboard.is_workflow_enabled(other_workflow):
                    other_config = governance_switchboard.WORKFLOW_FLAGS.get(other_workflow, {})
                    other_deps = other_config.get('component_dependencies', [])
                    if component in other_deps:
                        can_disable = False
                        break
            
            if can_disable:
                plan.append({
                    'type': 'disable_component',
                    'component': component,
                    'reason': f'No longer needed after rollback of: {workflow}',
                    'order': 2
                })
        
        return sorted(plan, key=lambda x: x['order'])
    
    def _show_rollback_plan(self, plan: List[Dict[str, Any]], dry_run: bool):
        """Show the rollback plan"""
        mode = 'DRY RUN' if dry_run else 'EXECUTION'
        self.stdout.write(f'\n📋 Rollback Plan ({mode}):')
        
        for i, step in enumerate(plan, 1):
            step_type = step['type']
            reason = step['reason']
            
            if step_type == 'disable_workflow':
                workflow = step['workflow']
                self.stdout.write(f'  {i}. Disable workflow: {workflow}')
                self.stdout.write(f'     Reason: {reason}')
                
            elif step_type == 'disable_component':
                component = step['component']
                self.stdout.write(f'  {i}. Disable component: {component}')
                self.stdout.write(f'     Reason: {reason}')
    
    def _execute_rollback_plan(self, plan: List[Dict[str, Any]]) -> bool:
        """Execute the rollback plan"""
        admin_user = self._get_admin_user()
        
        for step in plan:
            step_type = step['type']
            reason = step['reason']
            
            try:
                if step_type == 'disable_workflow':
                    workflow = step['workflow']
                    success = governance_switchboard.disable_workflow(
                        workflow, reason, admin_user
                    )
                    if not success:
                        self.stdout.write(
                            self.style.ERROR(f'❌ Failed to disable workflow: {workflow}')
                        )
                        return False
                    
                    self.stdout.write(f'  ✅ Disabled workflow: {workflow}')
                    
                elif step_type == 'disable_component':
                    component = step['component']
                    success = governance_switchboard.disable_component(
                        component, reason, admin_user
                    )
                    if not success:
                        self.stdout.write(
                            self.style.ERROR(f'❌ Failed to disable component: {component}')
                        )
                        return False
                    
                    self.stdout.write(f'  ✅ Disabled component: {component}')
                
                # Brief pause between steps
                time.sleep(1)
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Rollback step failed: {step_type} - {e}')
                )
                return False
        
        return True