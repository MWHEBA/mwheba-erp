"""
Management command to clean up expired idempotency records.
This should be run periodically as a maintenance task.
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from governance.services import IdempotencyService
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Clean up expired idempotency records'

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=1000,
            help='Number of records to process in each batch (default: 1000)'
        )
        parser.add_argument(
            '--max-age-days',
            type=int,
            default=30,
            help='Maximum age in days for records to keep (default: 30)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed progress information'
        )

    def handle(self, *args, **options):
        batch_size = options['batch_size']
        max_age_days = options['max_age_days']
        dry_run = options['dry_run']
        verbose = options['verbose']

        self.stdout.write(
            self.style.SUCCESS(
                f'Starting idempotency cleanup (batch_size={batch_size}, '
                f'max_age_days={max_age_days}, dry_run={dry_run})'
            )
        )

        try:
            # Get initial statistics
            if verbose:
                initial_stats = IdempotencyService.get_operation_statistics()
                self.stdout.write(f"Initial record count: {initial_stats.get('total_records', 0)}")
                self.stdout.write(f"Expired records: {initial_stats.get('expired_count', 0)}")

            if dry_run:
                # Show what would be deleted
                from datetime import timedelta
                now = timezone.now()
                expired_cutoff = now
                old_cutoff = now - timedelta(days=max_age_days)
                
                from governance.models import IdempotencyRecord
                
                expired_count = IdempotencyRecord.objects.filter(
                    expires_at__lt=expired_cutoff
                ).count()
                
                old_count = IdempotencyRecord.objects.filter(
                    created_at__lt=old_cutoff
                ).count()
                
                total_to_delete = expired_count + old_count
                
                self.stdout.write(
                    self.style.WARNING(
                        f'DRY RUN: Would delete {total_to_delete} records '
                        f'({expired_count} expired + {old_count} old)'
                    )
                )
                return

            # Perform actual cleanup
            cleanup_stats = IdempotencyService.cleanup_expired_records(
                batch_size=batch_size,
                max_age_days=max_age_days
            )

            # Report results
            total_deleted = cleanup_stats['total_deleted']
            duration = cleanup_stats.get('duration', 0)
            errors = cleanup_stats.get('errors', [])

            if errors:
                for error in errors:
                    self.stdout.write(self.style.ERROR(f'Error: {error}'))

            self.stdout.write(
                self.style.SUCCESS(
                    f'Cleanup completed: {total_deleted} records deleted '
                    f'in {duration:.2f} seconds'
                )
            )

            if verbose:
                final_stats = IdempotencyService.get_operation_statistics()
                self.stdout.write(f"Final record count: {final_stats.get('total_records', 0)}")
                self.stdout.write(f"Remaining expired records: {final_stats.get('expired_count', 0)}")

        except Exception as e:
            logger.error(f"Idempotency cleanup failed: {e}")
            raise CommandError(f'Cleanup failed: {e}')