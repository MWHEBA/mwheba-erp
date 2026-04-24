"""
Django management command for SignalRouter governance controls.
Provides CLI interface for managing signal routing and monitoring.
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from governance.services.signal_router import signal_router
import json


class Command(BaseCommand):
    help = 'Manage SignalRouter governance controls'
    
    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(dest='action', help='Available actions')
        
        # Status command
        status_parser = subparsers.add_parser('status', help='Show signal router status')
        status_parser.add_argument(
            '--json', 
            action='store_true', 
            help='Output in JSON format'
        )
        
        # Enable/disable global signals
        enable_parser = subparsers.add_parser('enable-global', help='Enable global signal processing')
        
        disable_parser = subparsers.add_parser('disable-global', help='Disable global signal processing')
        disable_parser.add_argument(
            '--reason', 
            default='Manual disable via management command',
            help='Reason for disabling signals'
        )
        
        # Enable/disable specific signals
        enable_signal_parser = subparsers.add_parser('enable-signal', help='Enable specific signal')
        enable_signal_parser.add_argument('signal_name', help='Name of signal to enable')
        
        disable_signal_parser = subparsers.add_parser('disable-signal', help='Disable specific signal')
        disable_signal_parser.add_argument('signal_name', help='Name of signal to disable')
        disable_signal_parser.add_argument(
            '--reason', 
            default='Manual disable via management command',
            help='Reason for disabling signal'
        )
        
        # Maintenance mode
        maintenance_enter_parser = subparsers.add_parser('enter-maintenance', help='Enter maintenance mode')
        maintenance_enter_parser.add_argument(
            '--reason', 
            default='Maintenance mode via management command',
            help='Reason for entering maintenance mode'
        )
        
        maintenance_exit_parser = subparsers.add_parser('exit-maintenance', help='Exit maintenance mode')
        
        # Statistics
        stats_parser = subparsers.add_parser('stats', help='Show signal statistics')
        stats_parser.add_argument(
            '--reset', 
            action='store_true', 
            help='Reset statistics after showing them'
        )
        
        # Validation
        validate_parser = subparsers.add_parser('validate', help='Validate signal router configuration')
        
        # List handlers
        list_parser = subparsers.add_parser('list-handlers', help='List registered signal handlers')
        list_parser.add_argument(
            '--signal', 
            help='Show handlers for specific signal only'
        )
    
    def handle(self, *args, **options):
        action = options.get('action')
        
        if not action:
            self.print_help('manage.py', 'manage_signals')
            return
        
        try:
            if action == 'status':
                self.handle_status(options)
            elif action == 'enable-global':
                self.handle_enable_global(options)
            elif action == 'disable-global':
                self.handle_disable_global(options)
            elif action == 'enable-signal':
                self.handle_enable_signal(options)
            elif action == 'disable-signal':
                self.handle_disable_signal(options)
            elif action == 'enter-maintenance':
                self.handle_enter_maintenance(options)
            elif action == 'exit-maintenance':
                self.handle_exit_maintenance(options)
            elif action == 'stats':
                self.handle_stats(options)
            elif action == 'validate':
                self.handle_validate(options)
            elif action == 'list-handlers':
                self.handle_list_handlers(options)
            else:
                raise CommandError(f"Unknown action: {action}")
                
        except Exception as e:
            raise CommandError(f"Command failed: {e}")
    
    def handle_status(self, options):
        """Show signal router status"""
        stats = signal_router.get_signal_statistics()
        
        if options.get('json'):
            self.stdout.write(json.dumps(stats, indent=2, default=str))
        else:
            self.stdout.write(self.style.SUCCESS("=== SignalRouter Status ==="))
            self.stdout.write(f"Global Enabled: {self._format_bool(stats['global_enabled'])}")
            self.stdout.write(f"Maintenance Mode: {self._format_bool(stats['maintenance_mode'])}")
            self.stdout.write(f"Depth Limit: {stats['depth_limit']}")
            self.stdout.write(f"Current Call Stack Depth: {stats['current_call_stack_depth']}")
            
            if stats['current_call_stack']:
                self.stdout.write(f"Current Call Stack: {' -> '.join(stats['current_call_stack'])}")
            
            if stats['disabled_signals']:
                self.stdout.write(self.style.WARNING(f"Disabled Signals: {', '.join(stats['disabled_signals'])}"))
            
            self.stdout.write(f"\nRegistered Handlers: {len(stats['registered_handlers'])} signals")
            for signal, count in stats['registered_handlers'].items():
                self.stdout.write(f"  {signal}: {count} handlers")
            
            counters = stats['counters']
            self.stdout.write(f"\nCounters:")
            self.stdout.write(f"  Signals Processed: {counters['signals_processed']}")
            self.stdout.write(f"  Signals Blocked: {counters['signals_blocked']}")
            self.stdout.write(f"  Signal Errors: {counters['signal_errors']}")
    
    def handle_enable_global(self, options):
        """Enable global signal processing"""
        signal_router.enable_global_signals()
        self.stdout.write(self.style.SUCCESS("Global signal processing enabled"))
    
    def handle_disable_global(self, options):
        """Disable global signal processing"""
        reason = options['reason']
        signal_router.disable_global_signals(reason)
        self.stdout.write(self.style.WARNING(f"Global signal processing disabled: {reason}"))
    
    def handle_enable_signal(self, options):
        """Enable specific signal"""
        signal_name = options['signal_name']
        signal_router.enable_signal(signal_name)
        self.stdout.write(self.style.SUCCESS(f"Signal '{signal_name}' enabled"))
    
    def handle_disable_signal(self, options):
        """Disable specific signal"""
        signal_name = options['signal_name']
        reason = options['reason']
        signal_router.disable_signal(signal_name, reason)
        self.stdout.write(self.style.WARNING(f"Signal '{signal_name}' disabled: {reason}"))
    
    def handle_enter_maintenance(self, options):
        """Enter maintenance mode"""
        reason = options['reason']
        signal_router.enter_maintenance_mode(reason)
        self.stdout.write(self.style.WARNING(f"Entered maintenance mode: {reason}"))
    
    def handle_exit_maintenance(self, options):
        """Exit maintenance mode"""
        signal_router.exit_maintenance_mode()
        self.stdout.write(self.style.SUCCESS("Exited maintenance mode"))
    
    def handle_stats(self, options):
        """Show signal statistics"""
        stats = signal_router.get_signal_statistics()
        counters = stats['counters']
        
        self.stdout.write(self.style.SUCCESS("=== Signal Statistics ==="))
        self.stdout.write(f"Signals Processed: {counters['signals_processed']}")
        self.stdout.write(f"Signals Blocked: {counters['signals_blocked']}")
        self.stdout.write(f"Signal Errors: {counters['signal_errors']}")
        
        if counters['signals_processed'] > 0:
            block_rate = (counters['signals_blocked'] / counters['signals_processed']) * 100
            error_rate = (counters['signal_errors'] / counters['signals_processed']) * 100
            self.stdout.write(f"Block Rate: {block_rate:.2f}%")
            self.stdout.write(f"Error Rate: {error_rate:.2f}%")
        
        if options.get('reset'):
            signal_router.reset_statistics()
            self.stdout.write(self.style.SUCCESS("Statistics reset"))
    
    def handle_validate(self, options):
        """Validate signal router configuration"""
        errors = signal_router.validate_configuration()
        
        if not errors:
            self.stdout.write(self.style.SUCCESS("✅ SignalRouter configuration is valid"))
        else:
            self.stdout.write(self.style.ERROR("❌ SignalRouter configuration errors:"))
            for error in errors:
                self.stdout.write(f"  - {error}")
    
    def handle_list_handlers(self, options):
        """List registered signal handlers"""
        stats = signal_router.get_signal_statistics()
        specific_signal = options.get('signal')
        
        if specific_signal:
            if specific_signal in stats['registered_handlers']:
                count = stats['registered_handlers'][specific_signal]
                self.stdout.write(f"Signal '{specific_signal}': {count} handlers")
            else:
                self.stdout.write(f"No handlers registered for signal '{specific_signal}'")
        else:
            self.stdout.write(self.style.SUCCESS("=== Registered Signal Handlers ==="))
            if not stats['registered_handlers']:
                self.stdout.write("No signal handlers registered")
            else:
                for signal, count in sorted(stats['registered_handlers'].items()):
                    self.stdout.write(f"{signal}: {count} handlers")
    
    def _format_bool(self, value):
        """Format boolean value with color"""
        if value:
            return self.style.SUCCESS("✅ Yes")
        else:
            return self.style.ERROR("❌ No")