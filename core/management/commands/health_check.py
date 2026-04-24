"""
✅ PHASE 7: Simple Health Check Management Command
Basic health check command for system monitoring
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from core.monitoring import check_system_health, trigger_alert_check


class Command(BaseCommand):
    help = 'Perform system health check and trigger alerts if needed'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--check-alerts',
            action='store_true',
            help='Also check alert rules and trigger alerts if needed',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output',
        )
    
    def handle(self, *args, **options):
        """Execute health check"""
        self.stdout.write(
            self.style.SUCCESS(f'Starting health check at {timezone.now()}')
        )
        
        # Perform health check
        health_status = check_system_health()
        
        # Display results
        if health_status['status'] == 'healthy':
            self.stdout.write(
                self.style.SUCCESS('✅ System is healthy')
            )
        else:
            self.stdout.write(
                self.style.ERROR('❌ System has issues')
            )
        
        if options['verbose']:
            for check_name, check_result in health_status['checks'].items():
                status = check_result['status']
                if status == 'healthy':
                    self.stdout.write(f'  ✅ {check_name}: {status}')
                elif status == 'degraded':
                    self.stdout.write(f'  ⚠️ {check_name}: {status}')
                else:
                    self.stdout.write(f'  ❌ {check_name}: {status}')
                    if 'error' in check_result:
                        self.stdout.write(f'     Error: {check_result["error"]}')
        
        # Check alerts if requested
        if options['check_alerts']:
            self.stdout.write('\nChecking alert rules...')
            triggered_alerts = trigger_alert_check()
            
            if triggered_alerts:
                self.stdout.write(
                    self.style.WARNING(f'⚠️ {len(triggered_alerts)} alerts triggered')
                )
                if options['verbose']:
                    for alert in triggered_alerts:
                        self.stdout.write(f'  - {alert["rule"]}: {alert["severity"]}')
            else:
                self.stdout.write(
                    self.style.SUCCESS('✅ No alerts triggered')
                )
        
        self.stdout.write(
            self.style.SUCCESS(f'Health check completed at {timezone.now()}')
        )