"""
Management command for QuarantineSystem operations.

Provides command-line interface for:
- Quarantine system health checks
- Generating quarantine reports
- Batch operations on quarantine records
- System maintenance tasks
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
import json

from governance.services.quarantine_system import quarantine_system
from governance.models import QuarantineRecord

User = get_user_model()


class Command(BaseCommand):
    help = 'Manage QuarantineSystem operations'
    
    def add_arguments(self, parser):
        """Add command arguments"""
        subparsers = parser.add_subparsers(dest='action', help='Available actions')
        
        # Health check command
        health_parser = subparsers.add_parser('health', help='Run quarantine system health check')
        health_parser.add_argument(
            '--format',
            choices=['json', 'text'],
            default='text',
            help='Output format'
        )
        
        # Report generation command
        report_parser = subparsers.add_parser('report', help='Generate quarantine reports')
        report_parser.add_argument(
            '--type',
            choices=['full', 'summary', 'trends'],
            default='summary',
            help='Report type'
        )
        report_parser.add_argument(
            '--output',
            help='Output file path (optional)'
        )
        report_parser.add_argument(
            '--format',
            choices=['json', 'text'],
            default='text',
            help='Output format'
        )
        
        # Statistics command
        stats_parser = subparsers.add_parser('stats', help='Show quarantine statistics')
        stats_parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Number of days for statistics (default: 30)'
        )
        stats_parser.add_argument(
            '--format',
            choices=['json', 'text'],
            default='text',
            help='Output format'
        )
        
        # Search command
        search_parser = subparsers.add_parser('search', help='Search quarantine records')
        search_parser.add_argument(
            '--model',
            help='Filter by model name'
        )
        search_parser.add_argument(
            '--corruption-type',
            help='Filter by corruption type'
        )
        search_parser.add_argument(
            '--status',
            choices=['QUARANTINED', 'UNDER_REVIEW', 'RESOLVED', 'PERMANENT'],
            help='Filter by status'
        )
        search_parser.add_argument(
            '--limit',
            type=int,
            default=10,
            help='Maximum number of results (default: 10)'
        )
        
        # Batch resolve command
        resolve_parser = subparsers.add_parser('batch-resolve', help='Batch resolve quarantine records')
        resolve_parser.add_argument(
            '--ids',
            required=True,
            help='Comma-separated list of quarantine record IDs'
        )
        resolve_parser.add_argument(
            '--notes',
            required=True,
            help='Resolution notes'
        )
        resolve_parser.add_argument(
            '--user',
            required=True,
            help='Username of user performing resolution'
        )
        
        # Cleanup command
        cleanup_parser = subparsers.add_parser('cleanup', help='Clean up old resolved quarantine records')
        cleanup_parser.add_argument(
            '--days',
            type=int,
            default=90,
            help='Delete resolved records older than N days (default: 90)'
        )
        cleanup_parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting'
        )
        
        # Trends command
        trends_parser = subparsers.add_parser('trends', help='Show quarantine trends')
        trends_parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Number of days for trend analysis (default: 30)'
        )
        trends_parser.add_argument(
            '--format',
            choices=['json', 'text'],
            default='text',
            help='Output format'
        )
    
    def handle(self, *args, **options):
        """Handle command execution"""
        action = options.get('action')
        
        if not action:
            self.print_help('manage.py', 'quarantine_management')
            return
        
        try:
            if action == 'health':
                self.handle_health_check(options)
            elif action == 'report':
                self.handle_report_generation(options)
            elif action == 'stats':
                self.handle_statistics(options)
            elif action == 'search':
                self.handle_search(options)
            elif action == 'batch-resolve':
                self.handle_batch_resolve(options)
            elif action == 'cleanup':
                self.handle_cleanup(options)
            elif action == 'trends':
                self.handle_trends(options)
            else:
                raise CommandError(f"Unknown action: {action}")
                
        except Exception as e:
            raise CommandError(f"Command failed: {str(e)}")
    
    def handle_health_check(self, options):
        """Handle health check command"""
        self.stdout.write("Running QuarantineSystem health check...")
        
        health_status = quarantine_system.health_check()
        
        if options['format'] == 'json':
            self.stdout.write(json.dumps(health_status, indent=2))
        else:
            self.print_health_status_text(health_status)
    
    def print_health_status_text(self, health_status):
        """Print health status in text format"""
        status = health_status['status']
        if status == 'healthy':
            self.stdout.write(self.style.SUCCESS(f"Overall Status: {status.upper()}"))
        else:
            self.stdout.write(self.style.ERROR(f"Overall Status: {status.upper()}"))
        
        self.stdout.write(f"Timestamp: {health_status['timestamp']}")
        self.stdout.write("")
        
        for check_name, check_result in health_status['checks'].items():
            check_status = check_result['status']
            
            if check_status == 'ok':
                status_style = self.style.SUCCESS
            elif check_status == 'warning':
                status_style = self.style.WARNING
            else:
                status_style = self.style.ERROR
            
            self.stdout.write(f"{check_name}: {status_style(check_status.upper())}")
            
            # Print additional details
            for key, value in check_result.items():
                if key != 'status':
                    self.stdout.write(f"  {key}: {value}")
            self.stdout.write("")
    
    def handle_report_generation(self, options):
        """Handle report generation command"""
        report_type = options['type']
        output_file = options.get('output')
        output_format = options['format']
        
        self.stdout.write(f"Generating {report_type} quarantine report...")
        
        report = quarantine_system.generate_quarantine_report(
            report_type=report_type
        )
        
        if output_format == 'json':
            report_content = json.dumps(report, indent=2, default=str)
        else:
            report_content = self.format_report_text(report)
        
        if output_file:
            with open(output_file, 'w') as f:
                f.write(report_content)
            self.stdout.write(self.style.SUCCESS(f"Report saved to: {output_file}"))
        else:
            self.stdout.write(report_content)
    
    def format_report_text(self, report):
        """Format report in text format"""
        lines = []
        lines.append(f"Quarantine Report - {report['report_type'].upper()}")
        lines.append(f"Generated: {report['generated_at']}")
        lines.append("=" * 50)
        lines.append("")
        
        data = report['data']
        
        if 'statistics' in data:
            stats = data['statistics']
            lines.append("STATISTICS SUMMARY")
            lines.append("-" * 20)
            summary = stats['summary']
            lines.append(f"Total Quarantined: {summary['total_quarantined']}")
            lines.append(f"Recent (24h): {summary['recent_24h']}")
            lines.append(f"Recent (7d): {summary['recent_7d']}")
            lines.append(f"Resolved: {summary['resolved_count']}")
            lines.append(f"Resolution Rate: {summary['resolution_rate']}%")
            lines.append("")
            
            lines.append("BY STATUS:")
            for status, count in stats['by_status'].items():
                lines.append(f"  {status}: {count}")
            lines.append("")
            
            lines.append("BY CORRUPTION TYPE:")
            for corruption_type, count in stats['by_corruption_type'].items():
                lines.append(f"  {corruption_type}: {count}")
            lines.append("")
        
        if 'recent_quarantines' in data:
            recent = data['recent_quarantines']
            lines.append(f"RECENT QUARANTINES ({recent['count']})")
            lines.append("-" * 20)
            for record in recent['records']:
                lines.append(f"ID: {record['id']} | {record['model_name']}#{record['object_id']}")
                lines.append(f"  Type: {record['corruption_type']}")
                lines.append(f"  Status: {record['status']}")
                lines.append(f"  Date: {record['quarantined_at']}")
                lines.append("")
        
        return "\n".join(lines)
    
    def handle_statistics(self, options):
        """Handle statistics command"""
        days = options['days']
        output_format = options['format']
        
        date_from = timezone.now() - timedelta(days=days)
        stats = quarantine_system.get_quarantine_statistics(date_from=date_from)
        
        if output_format == 'json':
            self.stdout.write(json.dumps(stats, indent=2, default=str))
        else:
            self.print_statistics_text(stats, days)
    
    def print_statistics_text(self, stats, days):
        """Print statistics in text format"""
        self.stdout.write(f"Quarantine Statistics (Last {days} days)")
        self.stdout.write("=" * 40)
        
        summary = stats['summary']
        self.stdout.write(f"Total Quarantined: {summary['total_quarantined']}")
        self.stdout.write(f"Recent (24h): {summary['recent_24h']}")
        self.stdout.write(f"Recent (7d): {summary['recent_7d']}")
        self.stdout.write(f"Resolved: {summary['resolved_count']}")
        self.stdout.write(f"Resolution Rate: {summary['resolution_rate']}%")
        
        if summary['avg_resolution_time_seconds']:
            avg_hours = summary['avg_resolution_time_seconds'] / 3600
            self.stdout.write(f"Avg Resolution Time: {avg_hours:.1f} hours")
        
        self.stdout.write("")
        self.stdout.write("By Status:")
        for status, count in stats['by_status'].items():
            self.stdout.write(f"  {status}: {count}")
        
        self.stdout.write("")
        self.stdout.write("By Corruption Type:")
        for corruption_type, count in stats['by_corruption_type'].items():
            self.stdout.write(f"  {corruption_type}: {count}")
    
    def handle_search(self, options):
        """Handle search command"""
        filters = {}
        
        if options.get('model'):
            filters['model_name'] = options['model']
        if options.get('corruption_type'):
            filters['corruption_type'] = options['corruption_type']
        if options.get('status'):
            filters['status'] = options['status']
        
        limit = options['limit']
        
        result = quarantine_system.search_quarantine_records(
            filters=filters,
            page_size=limit
        )
        
        records = result['records']
        total = result['pagination']['total_records']
        
        self.stdout.write(f"Found {total} quarantine records (showing first {len(records)}):")
        self.stdout.write("=" * 60)
        
        for record in records:
            self.stdout.write(f"ID: {record.id}")
            self.stdout.write(f"  Model: {record.model_name}#{record.object_id}")
            self.stdout.write(f"  Type: {record.corruption_type}")
            self.stdout.write(f"  Status: {record.status}")
            self.stdout.write(f"  Quarantined: {record.quarantined_at}")
            self.stdout.write(f"  By: {record.quarantined_by.username if record.quarantined_by else 'System'}")
            if record.resolved_at:
                self.stdout.write(f"  Resolved: {record.resolved_at}")
            self.stdout.write(f"  Reason: {record.quarantine_reason[:100]}...")
            self.stdout.write("")
    
    def handle_batch_resolve(self, options):
        """Handle batch resolve command"""
        ids_str = options['ids']
        notes = options['notes']
        username = options['user']
        
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f"User '{username}' not found")
        
        try:
            quarantine_ids = [int(id_str.strip()) for id_str in ids_str.split(',')]
        except ValueError:
            raise CommandError("Invalid quarantine IDs format. Use comma-separated integers.")
        
        self.stdout.write(f"Resolving {len(quarantine_ids)} quarantine records...")
        
        result = quarantine_system.batch_resolve_quarantine(
            quarantine_ids=quarantine_ids,
            resolution_notes=notes,
            user=user
        )
        
        updated_count = len(result['updated'])
        failed_count = len(result['failed'])
        
        self.stdout.write(self.style.SUCCESS(f"Successfully resolved: {updated_count}"))
        
        if failed_count > 0:
            self.stdout.write(self.style.ERROR(f"Failed to resolve: {failed_count}"))
            for failure in result['failed']:
                self.stdout.write(f"  ID {failure['id']}: {failure['error']}")
    
    def handle_cleanup(self, options):
        """Handle cleanup command"""
        days = options['days']
        dry_run = options['dry_run']
        
        cutoff_date = timezone.now() - timedelta(days=days)
        
        old_records = QuarantineRecord.objects.filter(
            status='RESOLVED',
            resolved_at__lt=cutoff_date
        )
        
        count = old_records.count()
        
        if dry_run:
            self.stdout.write(f"DRY RUN: Would delete {count} resolved quarantine records older than {days} days")
            
            if count > 0:
                self.stdout.write("Records that would be deleted:")
                for record in old_records[:10]:  # Show first 10
                    self.stdout.write(f"  ID: {record.id} | {record.model_name}#{record.object_id} | Resolved: {record.resolved_at}")
                
                if count > 10:
                    self.stdout.write(f"  ... and {count - 10} more")
        else:
            if count > 0:
                old_records.delete()
                self.stdout.write(self.style.SUCCESS(f"Deleted {count} old resolved quarantine records"))
            else:
                self.stdout.write("No old resolved records to delete")
    
    def handle_trends(self, options):
        """Handle trends command"""
        days = options['days']
        output_format = options['format']
        
        trends = quarantine_system.manager.get_quarantine_trends(days=days)
        
        if output_format == 'json':
            self.stdout.write(json.dumps(trends, indent=2, default=str))
        else:
            self.print_trends_text(trends)
    
    def print_trends_text(self, trends):
        """Print trends in text format"""
        period = trends['period']
        self.stdout.write(f"Quarantine Trends ({period['days']} days)")
        self.stdout.write(f"Period: {period['start_date']} to {period['end_date']}")
        self.stdout.write("=" * 50)
        
        daily_counts = trends['daily_counts']
        if daily_counts:
            self.stdout.write("Daily Quarantine Counts:")
            for day_data in daily_counts[-10:]:  # Show last 10 days
                date_str = day_data['date'].strftime('%Y-%m-%d') if hasattr(day_data['date'], 'strftime') else str(day_data['date'])
                self.stdout.write(f"  {date_str}: {day_data['count']}")
        else:
            self.stdout.write("No daily data available")
        
        self.stdout.write("")
        corruption_trends = trends['corruption_type_trends']
        if corruption_trends:
            self.stdout.write("Trends by Corruption Type:")
            for corruption_type, trend_data in corruption_trends.items():
                total = sum(item['count'] for item in trend_data)
                self.stdout.write(f"  {corruption_type}: {total} total")
        else:
            self.stdout.write("No corruption type trends available")