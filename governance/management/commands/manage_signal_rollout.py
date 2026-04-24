"""
Management command for managing signal governance rollout.

This command provides safe, gradual rollout management with monitoring and rollback capabilities.

Usage:
    python manage.py manage_signal_rollout --action=start --workflow=customer_payment_to_journal_entry
    python manage.py manage_signal_rollout --action=advance --workflow=customer_payment_to_journal_entry
    python manage.py manage_signal_rollout --action=status
    python manage.py manage_signal_rollout --action=monitor --workflow=customer_payment_to_journal_entry
    python manage.py manage_signal_rollout --action=rollback --workflow=customer_payment_to_journal_entry --reason="Performance issues"
"""

import logging
import time
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from governance.services.signal_rollout_service import signal_rollout_service
from governance.services import governance_switchboard, signal_router
from governance.models import GovernanceContext

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Manage signal governance rollout with gradual activation and monitoring'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--action',
            type=str,
            choices=['start', 'advance', 'status', 'monitor', 'rollback', 'health-check'],
            required=True,
            help='Rollout action to perform'
        )
        
        parser.add_argument(
            '--workflow',
            type=str,
            choices=[
                'customer_payment_to_journal_entry',
                'purchase_payment_to_journal_entry',
                'stock_movement_to_journal_entry',
                'transportation_fee_to_journal_entry',
                'all'
            ],
            help='Workflow to manage (required for most actions)'
        )
        
        parser.add_argument(
            '--target-phase',
            type=str,
            choices=['MONITORING', 'PILOT', 'GRADUAL', 'FULL'],
            default='FULL',
            help='Target rollout phase (default: FULL)'
        )
        
        parser.add_argument(
            '--reason',
            type=str,
            help='Reason for rollback (required for rollback action)'
        )
        
        parser.add_argument(
            '--auto-advance',
            action='store_true',
            help='Automatically advance through phases with monitoring'
        )
        
        parser.add_argument(
            '--monitoring-interval',
            type=int,
            default=300,  # 5 minutes
            help='Monitoring interval in seconds for auto-advance (default: 300)'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes'
        )
    
    def handle(self, *args, **options):
        action = options['action']
        workflow = options['workflow']
        target_phase = options['target_phase']
        reason = options['reason']
        auto_advance = options['auto_advance']
        monitoring_interval = options['monitoring_interval']
        dry_run = options['dry_run']
        
        self.stdout.write(
            self.style.SUCCESS(f'🚀 Signal Rollout Management - Action: {action}')
        )
        
        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No changes will be made'))
        
        try:
            # Set governance context
            GovernanceContext.set_context(
                user=None,  # System operation
                service='SignalRolloutCommand',
                operation=f'rollout_{action}'
            )
            
            if action == 'start':
                self._handle_start_rollout(workflow, target_phase, auto_advance, monitoring_interval, dry_run)
            elif action == 'advance':
                self._handle_advance_rollout(workflow, dry_run)
            elif action == 'status':
                self._handle_status_check(workflow)
            elif action == 'monitor':
                self._handle_monitoring(workflow)
            elif action == 'rollback':
                self._handle_rollback(workflow, reason, dry_run)
            elif action == 'health-check':
                self._handle_health_check(workflow)
            
            self.stdout.write(
                self.style.SUCCESS(f'✅ Rollout {action} completed successfully')
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Rollout {action} failed: {e}')
            )
            raise CommandError(f'Rollout operation failed: {e}')
            
        finally:
            GovernanceContext.clear_context()
    
    def _handle_start_rollout(self, workflow: str, target_phase: str, auto_advance: bool, 
                            monitoring_interval: int, dry_run: bool):
        """Handle rollout start action"""
        if not workflow or workflow == 'all':
            workflows = [
                'customer_payment_to_journal_entry',
                'purchase_payment_to_journal_entry',
                'stock_movement_to_journal_entry',
                'transportation_fee_to_journal_entry'
            ]
        else:
            workflows = [workflow]
        
        for wf in workflows:
            self.stdout.write(f'🚀 Starting rollout for workflow: {wf}')
            
            if not dry_run:
                try:
                    result = signal_rollout_service.start_gradual_rollout(
                        workflow=wf,
                        target_phase=target_phase,
                        user=None
                    )
                    
                    if result['success']:
                        self.stdout.write(f'  ✅ Rollout started: {result["rollout_id"]}')
                        self.stdout.write(f'  📊 Current phase: {result["current_phase"]}')
                        
                        if auto_advance:
                            self._auto_advance_rollout(wf, target_phase, monitoring_interval)
                    else:
                        self.stdout.write(f'  ❌ Failed to start rollout for {wf}')
                        
                except Exception as e:
                    self.stdout.write(f'  ❌ Error starting rollout for {wf}: {e}')
            else:
                self.stdout.write(f'  🔍 [DRY RUN] Would start rollout for {wf} targeting {target_phase}')
    
    def _handle_advance_rollout(self, workflow: str, dry_run: bool):
        """Handle rollout advance action"""
        if not workflow:
            raise CommandError('Workflow is required for advance action')
        
        self.stdout.write(f'⏭️  Advancing rollout for workflow: {workflow}')
        
        if not dry_run:
            try:
                result = signal_rollout_service.advance_rollout_phase(
                    workflow=workflow,
                    user=None
                )
                
                if result['success']:
                    self.stdout.write(f'  ✅ Phase advanced: {result["previous_phase"]} → {result["new_phase"]}')
                    self.stdout.write(f'  🔒 Safety checks: {"✅ PASSED" if result["safety_checks_passed"] else "❌ FAILED"}')
                    
                    if result['metrics']:
                        self._display_metrics(result['metrics'])
                        
                    if result.get('automatic_rollback'):
                        self.stdout.write('  🔄 Automatic rollback was triggered due to safety issues')
                else:
                    self.stdout.write(f'  ❌ Failed to advance rollout for {workflow}')
                    
            except Exception as e:
                self.stdout.write(f'  ❌ Error advancing rollout for {workflow}: {e}')
        else:
            self.stdout.write(f'  🔍 [DRY RUN] Would advance rollout phase for {workflow}')
    
    def _handle_status_check(self, workflow: str):
        """Handle status check action"""
        self.stdout.write('📊 Rollout Status Report')
        self.stdout.write('=' * 50)
        
        try:
            status = signal_rollout_service.get_rollout_status(workflow)
            
            if workflow:
                # Single workflow status
                if status:
                    self._display_workflow_status(workflow, status)
                else:
                    self.stdout.write(f'❌ No active rollout found for {workflow}')
            else:
                # All workflows status
                for wf, wf_status in status.items():
                    self._display_workflow_status(wf, wf_status)
                    self.stdout.write('')  # Empty line between workflows
                    
        except Exception as e:
            self.stdout.write(f'❌ Error getting rollout status: {e}')
    
    def _handle_monitoring(self, workflow: str):
        """Handle monitoring action"""
        if not workflow:
            raise CommandError('Workflow is required for monitoring action')
        
        self.stdout.write(f'📈 Monitoring rollout health for: {workflow}')
        
        try:
            health = signal_rollout_service.monitor_rollout_health(workflow)
            
            # Display health status
            status_icon = {
                'healthy': '✅',
                'warning': '⚠️',
                'critical': '🚨',
                'unknown': '❓',
                'no_rollout': '⭕',
                'error': '❌'
            }.get(health['health_status'], '❓')
            
            self.stdout.write(f'  {status_icon} Health Status: {health["health_status"].upper()}')
            
            # Display metrics
            if health.get('metrics'):
                self._display_metrics(health['metrics'])
            
            # Display alerts
            if health.get('alerts'):
                self.stdout.write('  🚨 Alerts:')
                for alert in health['alerts']:
                    self.stdout.write(f'    • {alert}')
            
            # Display recommendations
            if health.get('recommendations'):
                self.stdout.write('  💡 Recommendations:')
                for rec in health['recommendations']:
                    self.stdout.write(f'    • {rec}')
            
            # Check for automatic rollback recommendation
            if health.get('automatic_rollback_recommended'):
                self.stdout.write('  🔄 AUTOMATIC ROLLBACK RECOMMENDED')
                
        except Exception as e:
            self.stdout.write(f'❌ Error monitoring rollout health: {e}')
    
    def _handle_rollback(self, workflow: str, reason: str, dry_run: bool):
        """Handle rollback action"""
        if not workflow:
            raise CommandError('Workflow is required for rollback action')
        
        if not reason:
            raise CommandError('Reason is required for rollback action')
        
        self.stdout.write(f'🔄 Rolling back workflow: {workflow}')
        self.stdout.write(f'   Reason: {reason}')
        
        if not dry_run:
            try:
                result = signal_rollout_service.emergency_rollback(
                    workflow=workflow,
                    reason=reason,
                    user=None
                )
                
                if result['success']:
                    self.stdout.write(f'  ✅ Rollback completed')
                    self.stdout.write(f'  📋 Actions taken: {", ".join(result["rollback_actions"])}')
                else:
                    self.stdout.write(f'  ❌ Rollback failed for {workflow}')
                    
            except Exception as e:
                self.stdout.write(f'  ❌ Error during rollback for {workflow}: {e}')
        else:
            self.stdout.write(f'  🔍 [DRY RUN] Would rollback {workflow} with reason: {reason}')
    
    def _handle_health_check(self, workflow: str):
        """Handle comprehensive health check"""
        self.stdout.write('🏥 Comprehensive Health Check')
        self.stdout.write('=' * 50)
        
        try:
            # Check governance infrastructure
            self._check_governance_infrastructure()
            
            # Check signal router
            self._check_signal_router()
            
            # Check workflow-specific health
            if workflow:
                workflows = [workflow]
            else:
                workflows = [
                    'customer_payment_to_journal_entry',
                    'purchase_payment_to_journal_entry',
                    'stock_movement_to_journal_entry',
                    'transportation_fee_to_journal_entry'
                ]
            
            for wf in workflows:
                self._check_workflow_health(wf)
                
        except Exception as e:
            self.stdout.write(f'❌ Health check failed: {e}')
    
    def _auto_advance_rollout(self, workflow: str, target_phase: str, monitoring_interval: int):
        """Automatically advance rollout with monitoring"""
        self.stdout.write(f'🤖 Starting auto-advance for {workflow} (interval: {monitoring_interval}s)')
        
        current_phase = 'MONITORING'
        phase_order = ['MONITORING', 'PILOT', 'GRADUAL', 'FULL']
        target_index = phase_order.index(target_phase)
        
        while current_phase != target_phase:
            self.stdout.write(f'⏳ Waiting {monitoring_interval}s before advancing from {current_phase}...')
            time.sleep(monitoring_interval)
            
            # Check health before advancing
            health = signal_rollout_service.monitor_rollout_health(workflow)
            
            if health['health_status'] in ['critical', 'error']:
                self.stdout.write(f'🚨 Critical health status detected - stopping auto-advance')
                break
            
            if health['health_status'] == 'warning':
                self.stdout.write(f'⚠️  Warning status detected - proceeding with caution')
            
            # Advance to next phase
            try:
                result = signal_rollout_service.advance_rollout_phase(workflow, user=None)
                
                if result['success']:
                    current_phase = result['new_phase']
                    self.stdout.write(f'✅ Auto-advanced to phase: {current_phase}')
                    
                    if current_phase == target_phase:
                        self.stdout.write(f'🎯 Target phase {target_phase} reached!')
                        break
                else:
                    self.stdout.write(f'❌ Auto-advance failed - stopping')
                    break
                    
            except Exception as e:
                self.stdout.write(f'❌ Auto-advance error: {e} - stopping')
                break
    
    def _display_workflow_status(self, workflow: str, status: dict):
        """Display status for a single workflow"""
        if not status:
            self.stdout.write(f'🔴 {workflow}: No active rollout')
            return
        
        phase_icons = {
            'DISABLED': '🔴',
            'MONITORING': '🟡',
            'PILOT': '🟠',
            'GRADUAL': '🔵',
            'FULL': '🟢'
        }
        
        current_phase = status.get('phase', 'UNKNOWN')
        target_phase = status.get('target_phase', 'UNKNOWN')
        
        icon = phase_icons.get(current_phase, '❓')
        
        self.stdout.write(f'{icon} {workflow}:')
        self.stdout.write(f'   Current Phase: {current_phase}')
        self.stdout.write(f'   Target Phase: {target_phase}')
        self.stdout.write(f'   Started: {status.get("started_at", "Unknown")}')
        self.stdout.write(f'   Status: {status.get("status", "Unknown")}')
    
    def _display_metrics(self, metrics: dict):
        """Display rollout metrics"""
        self.stdout.write('  📊 Metrics:')
        
        if 'total_signals' in metrics:
            self.stdout.write(f'    Total Signals: {metrics["total_signals"]}')
        
        if 'error_rate' in metrics:
            error_rate = metrics['error_rate']
            error_icon = '🚨' if error_rate > 0.05 else '⚠️' if error_rate > 0.01 else '✅'
            self.stdout.write(f'    {error_icon} Error Rate: {error_rate:.2%}')
        
        if 'blocked_rate' in metrics:
            blocked_rate = metrics['blocked_rate']
            blocked_icon = '🚨' if blocked_rate > 0.10 else '⚠️' if blocked_rate > 0.05 else '✅'
            self.stdout.write(f'    {blocked_icon} Blocked Rate: {blocked_rate:.2%}')
        
        if 'success_rate' in metrics:
            success_rate = metrics['success_rate']
            success_icon = '✅' if success_rate > 0.95 else '⚠️' if success_rate > 0.90 else '🚨'
            self.stdout.write(f'    {success_icon} Success Rate: {success_rate:.2%}')
    
    def _check_governance_infrastructure(self):
        """Check governance infrastructure health"""
        self.stdout.write('🎛️  Governance Infrastructure:')
        
        try:
            stats = governance_switchboard.get_governance_statistics()
            health = stats.get('health', {}).get('governance_active', False)
            
            self.stdout.write(f'   {"✅" if health else "❌"} Switchboard: {"Active" if health else "Inactive"}')
            self.stdout.write(f'   📊 Components: {stats.get("components", {}).get("enabled", 0)}/{stats.get("components", {}).get("total", 0)} enabled')
            self.stdout.write(f'   🚩 Workflows: {stats.get("workflows", {}).get("enabled", 0)}/{stats.get("workflows", {}).get("total", 0)} enabled')
            
        except Exception as e:
            self.stdout.write(f'   ❌ Error checking governance infrastructure: {e}')
    
    def _check_signal_router(self):
        """Check signal router health"""
        self.stdout.write('📡 Signal Router:')
        
        try:
            stats = signal_router.get_signal_statistics()
            
            self.stdout.write(f'   {"✅" if stats["global_enabled"] else "❌"} Global Enabled: {stats["global_enabled"]}')
            self.stdout.write(f'   {"⚠️" if stats["maintenance_mode"] else "✅"} Maintenance Mode: {stats["maintenance_mode"]}')
            self.stdout.write(f'   📊 Signals Processed: {stats["counters"]["signals_processed"]}')
            self.stdout.write(f'   🚨 Signal Errors: {stats["counters"]["signal_errors"]}')
            self.stdout.write(f'   🚫 Signals Blocked: {stats["counters"]["signals_blocked"]}')
            
        except Exception as e:
            self.stdout.write(f'   ❌ Error checking signal router: {e}')
    
    def _check_workflow_health(self, workflow: str):
        """Check health of specific workflow"""
        self.stdout.write(f'🔍 Workflow Health: {workflow}')
        
        try:
            # Check if workflow is enabled
            enabled = governance_switchboard.is_workflow_enabled(workflow)
            self.stdout.write(f'   {"✅" if enabled else "❌"} Enabled: {enabled}')
            
            # Get rollout status
            status = signal_rollout_service.get_rollout_status(workflow)
            if status:
                self.stdout.write(f'   📊 Rollout Phase: {status.get("phase", "Unknown")}')
            else:
                self.stdout.write(f'   📊 Rollout Phase: No active rollout')
            
            # Monitor health
            health = signal_rollout_service.monitor_rollout_health(workflow)
            health_icon = {
                'healthy': '✅',
                'warning': '⚠️',
                'critical': '🚨',
                'unknown': '❓',
                'no_rollout': '⭕'
            }.get(health['health_status'], '❓')
            
            self.stdout.write(f'   {health_icon} Health: {health["health_status"].upper()}')
            
        except Exception as e:
            self.stdout.write(f'   ❌ Error checking workflow health: {e}')