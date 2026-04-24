"""
Management command for monitoring and managing circuit breakers
✅ PHASE 2: System Stability - Circuit breaker management
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from core.utils.circuit_breaker import get_circuit_breaker_stats, financial_api_breaker, email_service_breaker, bridge_agent_breaker
from core.utils.signal_error_handler import get_signal_failure_stats
import json

class Command(BaseCommand):
    help = 'Monitor and manage circuit breakers and signal failures'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--action',
            type=str,
            choices=['status', 'reset', 'open', 'close'],
            default='status',
            help='Action to perform on circuit breakers'
        )
        parser.add_argument(
            '--breaker',
            type=str,
            choices=['financial_api', 'email_service', 'bridge_agent', 'all'],
            default='all',
            help='Specific circuit breaker to manage'
        )
        parser.add_argument(
            '--json',
            action='store_true',
            help='Output in JSON format'
        )
    
    def handle(self, *args, **options):
        action = options['action']
        breaker_name = options['breaker']
        json_output = options['json']
        
        if action == 'status':
            self.show_status(json_output)
        elif action == 'reset':
            self.reset_breakers(breaker_name)
        elif action == 'open':
            self.open_breakers(breaker_name)
        elif action == 'close':
            self.close_breakers(breaker_name)
    
    def show_status(self, json_output=False):
        """Show status of all circuit breakers and signal failures"""
        # Get circuit breaker stats
        circuit_stats = get_circuit_breaker_stats()
        
        # Get signal failure stats
        signal_stats = get_signal_failure_stats()
        
        status_data = {
            'timestamp': timezone.now().isoformat(),
            'circuit_breakers': circuit_stats,
            'signal_failures': signal_stats
        }
        
        if json_output:
            self.stdout.write(json.dumps(status_data, indent=2))
            return
        
        # Human-readable output
        self.stdout.write(
            self.style.SUCCESS('=== Circuit Breaker Status ===')
        )
        
        for cb_stat in circuit_stats:
            status_color = self.style.SUCCESS
            if cb_stat['state'] == 'open':
                status_color = self.style.ERROR
            elif cb_stat['state'] == 'half_open':
                status_color = self.style.WARNING
            
            self.stdout.write(
                f"🔌 {cb_stat['name']}: {status_color(cb_stat['state'].upper())} "
                f"(failures: {cb_stat['failure_count']}/{cb_stat['failure_threshold']})"
            )
        
        self.stdout.write('\n' + self.style.SUCCESS('=== Signal Failure Status ==='))
        
        if 'error' in signal_stats:
            self.stdout.write(
                self.style.ERROR(f"❌ Error getting signal stats: {signal_stats['error']}")
            )
        else:
            total_failures = sum(signal_stats.get('failure_counts', {}).values())
            self.stdout.write(f"📊 Total signal failures (last hour): {total_failures}")
            
            if signal_stats.get('failure_counts'):
                self.stdout.write("📋 Failures by signal:")
                for signal_name, count in signal_stats['failure_counts'].items():
                    color = self.style.ERROR if count > 5 else self.style.WARNING
                    self.stdout.write(f"   • {signal_name}: {color(str(count))}")
            else:
                self.stdout.write(self.style.SUCCESS("✅ No signal failures recorded"))
    
    def reset_breakers(self, breaker_name):
        """Reset circuit breakers to closed state"""
        breakers = self._get_breakers(breaker_name)
        
        for name, breaker in breakers.items():
            breaker.force_close()
            self.stdout.write(
                self.style.SUCCESS(f"✅ Reset circuit breaker: {name}")
            )
    
    def open_breakers(self, breaker_name):
        """Manually open circuit breakers"""
        breakers = self._get_breakers(breaker_name)
        
        for name, breaker in breakers.items():
            breaker.force_open()
            self.stdout.write(
                self.style.WARNING(f"⚠️  Opened circuit breaker: {name}")
            )
    
    def close_breakers(self, breaker_name):
        """Manually close circuit breakers"""
        breakers = self._get_breakers(breaker_name)
        
        for name, breaker in breakers.items():
            breaker.force_close()
            self.stdout.write(
                self.style.SUCCESS(f"✅ Closed circuit breaker: {name}")
            )
    
    def _get_breakers(self, breaker_name):
        """Get circuit breaker instances based on name"""
        all_breakers = {
            'financial_api': financial_api_breaker,
            'email_service': email_service_breaker,
            'bridge_agent': bridge_agent_breaker
        }
        
        if breaker_name == 'all':
            return all_breakers
        elif breaker_name in all_breakers:
            return {breaker_name: all_breakers[breaker_name]}
        else:
            self.stdout.write(
                self.style.ERROR(f"❌ Unknown circuit breaker: {breaker_name}")
            )
            return {}