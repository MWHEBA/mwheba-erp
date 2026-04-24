"""
Management command to check the health of the idempotency system.
Provides statistics and recommendations for maintenance.
"""

from django.core.management.base import BaseCommand
from governance.services import IdempotencyService
import json


class Command(BaseCommand):
    help = 'Check idempotency system health and get statistics'

    def add_arguments(self, parser):
        parser.add_argument(
            '--format',
            choices=['table', 'json'],
            default='table',
            help='Output format (default: table)'
        )
        parser.add_argument(
            '--detailed',
            action='store_true',
            help='Show detailed statistics'
        )

    def handle(self, *args, **options):
        output_format = options['format']
        detailed = options['detailed']

        # Get health status and statistics
        health = IdempotencyService.get_health_status()
        
        if detailed:
            stats = IdempotencyService.get_operation_statistics()
        else:
            stats = None

        if output_format == 'json':
            # JSON output
            output = {'health': health}
            if stats:
                output['statistics'] = stats
            self.stdout.write(json.dumps(output, indent=2, default=str))
        else:
            # Table output
            self._print_health_table(health)
            if detailed and stats:
                self._print_statistics_table(stats)

    def _print_health_table(self, health):
        """Print health status in table format"""
        status = health['status']
        status_color = {
            'healthy': self.style.SUCCESS,
            'warning': self.style.WARNING,
            'error': self.style.ERROR
        }.get(status, self.style.NOTICE)

        self.stdout.write(self.style.SUCCESS('=== Idempotency System Health ==='))
        self.stdout.write(f"Status: {status_color(status.upper())}")
        
        metrics = health.get('metrics', {})
        self.stdout.write(f"Total Records: {metrics.get('total_records', 0)}")
        self.stdout.write(f"Expired Ratio: {metrics.get('expired_ratio', 0):.2%}")
        self.stdout.write(f"Recent Activity: {metrics.get('recent_activity', 0)} operations")

        issues = health.get('issues', [])
        if issues:
            self.stdout.write(self.style.WARNING('\nIssues:'))
            for issue in issues:
                self.stdout.write(f"  - {issue}")

        recommendations = health.get('recommendations', [])
        if recommendations:
            self.stdout.write(self.style.NOTICE('\nRecommendations:'))
            for rec in recommendations:
                self.stdout.write(f"  - {rec}")

    def _print_statistics_table(self, stats):
        """Print detailed statistics in table format"""
        self.stdout.write(self.style.SUCCESS('\n=== Detailed Statistics ==='))
        
        # Basic counts
        self.stdout.write(f"Total Records: {stats.get('total_records', 0)}")
        self.stdout.write(f"Active Records: {stats.get('active_count', 0)}")
        self.stdout.write(f"Expired Records: {stats.get('expired_count', 0)}")
        self.stdout.write(f"Recent Operations (24h): {stats.get('recent_operations', 0)}")
        self.stdout.write(f"Weekly Operations: {stats.get('weekly_operations', 0)}")
        
        avg_age = stats.get('average_age_hours')
        if avg_age:
            self.stdout.write(f"Average Record Age: {avg_age:.1f} hours")

        # Operations by type
        by_type = stats.get('by_operation_type', {})
        if by_type:
            self.stdout.write(self.style.SUCCESS('\nOperations by Type:'))
            for op_type, count in by_type.items():
                self.stdout.write(f"  {op_type}: {count}")

        # Top users
        top_users = stats.get('top_users', {})
        if top_users:
            self.stdout.write(self.style.SUCCESS('\nTop Users:'))
            for user, count in list(top_users.items())[:5]:
                self.stdout.write(f"  {user}: {count}")

        # Cleanup recommendations
        cleanup = stats.get('cleanup_recommendations', {})
        if cleanup:
            self.stdout.write(self.style.SUCCESS('\nCleanup Recommendations:'))
            self.stdout.write(f"  Old Records: {cleanup.get('old_records_count', 0)}")
            self.stdout.write(f"  Should Cleanup: {cleanup.get('should_cleanup', False)}")
            if cleanup.get('should_cleanup'):
                self.stdout.write(f"  Estimated Time: {cleanup.get('estimated_cleanup_time', 'Unknown')}")