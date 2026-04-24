"""
Management command for controlling payroll signal governance.

This command provides administrative control over the gradual rollout
of payroll signal governance controls.

Usage:
    python manage.py manage_payroll_signals --enable --reason "Initial rollout"
    python manage.py manage_payroll_signals --disable --reason "Emergency rollback"
    python manage.py manage_payroll_signals --status
    python manage.py manage_payroll_signals --kill-switch payroll_creation_notifications --reason "High error rate"
    python manage.py manage_payroll_signals --promote payroll_cache_invalidation --percentage 50
"""

import json
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.utils import timezone

from governance.services.payroll_signal_governance import payroll_signal_governance
from governance.signals.payroll_signals import PayrollSignalFeatureFlags

User = get_user_model()


class Command(BaseCommand):
    help = 'Manage payroll signal governance controls with gradual rollout'
    
    def add_arguments(self, parser):
        # Main actions
        parser.add_argument(
            '--enable',
            action='store_true',
            help='Enable payroll signal governance'
        )
        
        parser.add_argument(
            '--disable',
            action='store_true',
            help='Disable payroll signal governance (safe rollback)'
        )
        
        parser.add_argument(
            '--status',
            action='store_true',
            help='Show current rollout status'
        )
        
        parser.add_argument(
            '--health',
            action='store_true',
            help='Show health status'
        )
        
        # Kill switch controls
        parser.add_argument(
            '--kill-switch',
            type=str,
            help='Activate kill switch for specific signal'
        )
        
        parser.add_argument(
            '--restore-switch',
            type=str,
            help='Deactivate kill switch for specific signal'
        )
        
        # Rollout controls
        parser.add_argument(
            '--promote',
            type=str,
            help='Promote specific signal to higher rollout percentage'
        )
        
        parser.add_argument(
            '--percentage',
            type=int,
            help='Target percentage for promotion (default: auto-increment)'
        )
        
        # Common parameters
        parser.add_argument(
            '--reason',
            type=str,
            default='Management command',
            help='Reason for the action'
        )
        
        parser.add_argument(
            '--user',
            type=str,
            help='Username performing the action (default: system)'
        )
        
        parser.add_argument(
            '--json',
            action='store_true',
            help='Output in JSON format'
        )
    
    def handle(self, *args, **options):
        try:
            # Get user
            user = self.get_user(options.get('user'))
            
            # Handle different actions
            if options['enable']:
                self.handle_enable(user, options['reason'])
            elif options['disable']:
                self.handle_disable(user, options['reason'])
            elif options['status']:
                self.handle_status(options['json'])
            elif options['health']:
                self.handle_health(options['json'])
            elif options['kill_switch']:
                self.handle_kill_switch(options['kill_switch'], user, options['reason'])
            elif options['restore_switch']:
                self.handle_restore_switch(options['restore_switch'], user, options['reason'])
            elif options['promote']:
                self.handle_promote(options['promote'], user, options.get('percentage'))
            else:
                self.print_help('manage.py', 'manage_payroll_signals')
                
        except Exception as e:
            raise CommandError(f'Command failed: {str(e)}')
    
    def get_user(self, username):
        """Get user for the operation"""
        if username:
            try:
                return User.objects.get(username=username)
            except User.DoesNotExist:
                raise CommandError(f'User not found: {username}')
        else:
            # Get or create system user
            user, created = User.objects.get_or_create(
                username='system',
                defaults={
                    'email': 'system@example.com',
                    'first_name': 'System',
                    'last_name': 'User',
                    'is_staff': True,
                    'is_superuser': True
                }
            )
            return user
    
    def handle_enable(self, user, reason):
        """Enable payroll signal governance"""
        self.stdout.write(
            self.style.WARNING(f'Enabling payroll signal governance...')
        )
        
        success = payroll_signal_governance.enable_payroll_signal_governance(user, reason)
        
        if success:
            self.stdout.write(
                self.style.SUCCESS(
                    f'✅ Payroll signal governance enabled successfully\n'
                    f'   Reason: {reason}\n'
                    f'   User: {user.username}\n'
                    f'   Time: {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}'
                )
            )
            
            # Show initial status
            self.stdout.write('\n📊 Initial Rollout Status:')
            self.show_rollout_summary()
        else:
            self.stdout.write(
                self.style.ERROR('❌ Failed to enable payroll signal governance')
            )
    
    def handle_disable(self, user, reason):
        """Disable payroll signal governance"""
        self.stdout.write(
            self.style.WARNING(f'Disabling payroll signal governance...')
        )
        
        success = payroll_signal_governance.disable_payroll_signal_governance(user, reason)
        
        if success:
            self.stdout.write(
                self.style.SUCCESS(
                    f'✅ Payroll signal governance disabled successfully\n'
                    f'   Reason: {reason}\n'
                    f'   User: {user.username}\n'
                    f'   Time: {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}'
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR('❌ Failed to disable payroll signal governance')
            )
    
    def handle_status(self, json_output):
        """Show rollout status"""
        status = payroll_signal_governance.get_rollout_status()
        
        if json_output:
            self.stdout.write(json.dumps(status, indent=2, default=str))
        else:
            self.show_detailed_status(status)
    
    def handle_health(self, json_output):
        """Show health status"""
        health = payroll_signal_governance.get_health_status()
        
        if json_output:
            self.stdout.write(json.dumps(health, indent=2, default=str))
        else:
            self.show_health_status(health)
    
    def handle_kill_switch(self, signal_name, user, reason):
        """Activate kill switch for signal"""
        self.stdout.write(
            self.style.WARNING(f'Activating kill switch for {signal_name}...')
        )
        
        success = payroll_signal_governance.activate_kill_switch(signal_name, user, reason)
        
        if success:
            self.stdout.write(
                self.style.SUCCESS(
                    f'🔴 Kill switch activated for {signal_name}\n'
                    f'   Reason: {reason}\n'
                    f'   User: {user.username}'
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(f'❌ Failed to activate kill switch for {signal_name}')
            )
    
    def handle_restore_switch(self, signal_name, user, reason):
        """Deactivate kill switch for signal"""
        self.stdout.write(
            self.style.WARNING(f'Deactivating kill switch for {signal_name}...')
        )
        
        success = payroll_signal_governance.deactivate_kill_switch(signal_name, user, reason)
        
        if success:
            self.stdout.write(
                self.style.SUCCESS(
                    f'🟢 Kill switch deactivated for {signal_name}\n'
                    f'   Reason: {reason}\n'
                    f'   User: {user.username}'
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(f'❌ Failed to deactivate kill switch for {signal_name}')
            )
    
    def handle_promote(self, signal_name, user, target_percentage):
        """Promote signal rollout"""
        self.stdout.write(
            self.style.WARNING(f'Promoting rollout for {signal_name}...')
        )
        
        success = payroll_signal_governance.promote_signal_rollout(
            signal_name, user, target_percentage
        )
        
        if success:
            # Get updated status
            status = payroll_signal_governance.get_rollout_status()
            signal_status = status['signals'].get(signal_name, {})
            new_percentage = signal_status.get('rollout_percentage', 0)
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'📈 Rollout promoted for {signal_name}\n'
                    f'   New percentage: {new_percentage}%\n'
                    f'   User: {user.username}'
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(f'❌ Failed to promote rollout for {signal_name}')
            )
    
    def show_rollout_summary(self):
        """Show summary of rollout status"""
        status = payroll_signal_governance.get_rollout_status()
        
        # Overall status
        governance_enabled = status['governance_enabled']
        monitoring_active = status['monitoring_active']
        
        self.stdout.write(f'🎛️  Governance: {"✅ Enabled" if governance_enabled else "❌ Disabled"}')
        self.stdout.write(f'📡 Monitoring: {"✅ Active" if monitoring_active else "❌ Inactive"}')
        
        # Summary stats
        summary = status['summary']
        self.stdout.write(f'📊 Signals: {summary["enabled_signals"]}/{summary["total_signals"]} enabled')
        self.stdout.write(f'🎯 Fully rolled out: {summary["fully_rolled_out"]}')
        self.stdout.write(f'🔴 Kill switches: {summary["kill_switches_active"]}')
        self.stdout.write(f'📉 Avg error rate: {summary["average_error_rate"]:.1f}%')
        
        # Signal status
        self.stdout.write('\n📋 Signal Status:')
        for signal_name, signal_data in status['signals'].items():
            rollout = signal_data['rollout_percentage']
            enabled = signal_data['is_enabled']
            kill_switch = signal_data['kill_switch_active']
            error_rate = signal_data['metrics']['error_rate']
            
            status_icon = '🔴' if kill_switch else ('✅' if enabled else '❌')
            
            self.stdout.write(
                f'  {status_icon} {signal_name}: {rollout}% '
                f'(errors: {error_rate:.1f}%)'
            )
    
    def show_detailed_status(self, status):
        """Show detailed rollout status"""
        self.stdout.write(self.style.SUCCESS('🎛️  Payroll Signal Governance Status'))
        self.stdout.write('=' * 50)
        
        # Overall status
        governance_enabled = status['governance_enabled']
        monitoring_active = status['monitoring_active']
        master_kill_switch = status['master_kill_switch']
        
        self.stdout.write(f'Governance Enabled: {"✅ Yes" if governance_enabled else "❌ No"}')
        self.stdout.write(f'Monitoring Active: {"✅ Yes" if monitoring_active else "❌ No"}')
        self.stdout.write(f'Master Kill Switch: {"🔴 Active" if master_kill_switch else "✅ Inactive"}')
        
        # Summary statistics
        summary = status['summary']
        self.stdout.write(f'\n📊 Summary Statistics:')
        self.stdout.write(f'  Total Signals: {summary["total_signals"]}')
        self.stdout.write(f'  Enabled Signals: {summary["enabled_signals"]}')
        self.stdout.write(f'  Fully Rolled Out: {summary["fully_rolled_out"]}')
        self.stdout.write(f'  Kill Switches Active: {summary["kill_switches_active"]}')
        self.stdout.write(f'  Average Error Rate: {summary["average_error_rate"]:.1f}%')
        
        # Counters
        counters = status['counters']
        self.stdout.write(f'\n📈 Operation Counters:')
        self.stdout.write(f'  Rollout Promotions: {counters["rollout_promotions"]}')
        self.stdout.write(f'  Rollout Rollbacks: {counters["rollout_rollbacks"]}')
        self.stdout.write(f'  Kill Switch Activations: {counters["kill_switch_activations"]}')
        
        # Individual signal status
        self.stdout.write(f'\n📋 Individual Signal Status:')
        for signal_name, signal_data in status['signals'].items():
            self.stdout.write(f'\n  🔧 {signal_name}:')
            self.stdout.write(f'    Description: {signal_data["description"]}')
            self.stdout.write(f'    Rollout: {signal_data["rollout_percentage"]}%')
            self.stdout.write(f'    Enabled: {"✅ Yes" if signal_data["is_enabled"] else "❌ No"}')
            self.stdout.write(f'    Kill Switch: {"🔴 Active" if signal_data["kill_switch_active"] else "✅ Inactive"}')
            
            metrics = signal_data['metrics']
            self.stdout.write(f'    Executions: {metrics["total_executions"]} (success: {metrics["successful_executions"]}, failed: {metrics["failed_executions"]})')
            self.stdout.write(f'    Error Rate: {metrics["error_rate"]:.1f}%')
            self.stdout.write(f'    Avg Time: {metrics["average_execution_time"]:.3f}s')
            self.stdout.write(f'    Consecutive Failures: {metrics["consecutive_failures"]}')
            
            if metrics['last_execution_time']:
                self.stdout.write(f'    Last Execution: {metrics["last_execution_time"]}')
            
            if metrics['last_error']:
                self.stdout.write(f'    Last Error: {metrics["last_error"]}')
        
        # Recommendations
        if status.get('recommendations'):
            self.stdout.write(f'\n💡 Recommendations:')
            for rec in status['recommendations']:
                self.stdout.write(f'  • {rec}')
    
    def show_health_status(self, health):
        """Show health status"""
        status_color = {
            'healthy': self.style.SUCCESS,
            'warning': self.style.WARNING,
            'critical': self.style.ERROR
        }
        
        color_func = status_color.get(health['status'], self.style.SUCCESS)
        
        self.stdout.write(color_func(f'🏥 Health Status: {health["status"].upper()}'))
        self.stdout.write('=' * 40)
        
        # Metrics
        metrics = health['metrics']
        self.stdout.write(f'Governance Enabled: {"✅" if metrics["governance_enabled"] else "❌"}')
        self.stdout.write(f'Monitoring Active: {"✅" if metrics["monitoring_active"] else "❌"}')
        self.stdout.write(f'Enabled Signals: {metrics["enabled_signals"]}')
        self.stdout.write(f'Average Error Rate: {metrics["average_error_rate"]:.1f}%')
        self.stdout.write(f'Kill Switches Active: {metrics["kill_switches_active"]}')
        
        # Issues
        if health['issues']:
            self.stdout.write(f'\n⚠️  Issues:')
            for issue in health['issues']:
                self.stdout.write(f'  • {issue}')
        
        # Recommendations
        if health['recommendations']:
            self.stdout.write(f'\n💡 Recommendations:')
            for rec in health['recommendations']:
                self.stdout.write(f'  • {rec}')
        
        if not health['issues']:
            self.stdout.write(self.style.SUCCESS('\n✅ No issues detected'))