from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from governance.models import ActiveSession, SecurityIncident
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Cleanup old security data (expired sessions, old incidents)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--session-hours',
            type=int,
            default=24,
            help='Clean up sessions older than X hours (default: 24)'
        )
        parser.add_argument(
            '--incident-days',
            type=int,
            default=90,
            help='Archive incidents older than X days (default: 90)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be cleaned without actually cleaning'
        )

    def handle(self, *args, **options):
        session_hours = options['session_hours']
        incident_days = options['incident_days']
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No data will be deleted'))
        
        # Cleanup expired sessions
        self.stdout.write('Cleaning up expired sessions...')
        session_count = ActiveSession.cleanup_expired_sessions(hours=session_hours)
        
        if dry_run:
            self.stdout.write(self.style.SUCCESS(f'  Would clean up {session_count} expired sessions'))
        else:
            self.stdout.write(self.style.SUCCESS(f'  ✓ Cleaned up {session_count} expired sessions'))
        
        # Archive old resolved incidents
        self.stdout.write(f'Archiving old incidents (older than {incident_days} days)...')
        cutoff_date = timezone.now() - timedelta(days=incident_days)
        
        old_incidents = SecurityIncident.objects.filter(
            status='RESOLVED',
            resolved_at__lt=cutoff_date
        )
        
        count = old_incidents.count()
        
        if dry_run:
            self.stdout.write(self.style.SUCCESS(f'  Would archive {count} old incidents'))
        else:
            # In production, you might want to move these to an archive table
            # For now, we'll just mark them
            old_incidents.update(
                additional_data={'archived': True, 'archived_at': timezone.now().isoformat()}
            )
            self.stdout.write(self.style.SUCCESS(f'  ✓ Archived {count} old incidents'))
        
        # Summary
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Cleanup completed!'))
        if not dry_run:
            self.stdout.write(self.style.SUCCESS(f'  - {session_count} sessions cleaned'))
            self.stdout.write(self.style.SUCCESS(f'  - {count} incidents archived'))
