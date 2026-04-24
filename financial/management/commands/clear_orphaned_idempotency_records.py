"""
Management command to clear orphaned idempotency records
(records that exist but their corresponding journal entries don't)
"""
from django.core.management.base import BaseCommand
from governance.models import IdempotencyRecord
from financial.models import JournalEntry


class Command(BaseCommand):
    help = 'Clear orphaned idempotency records for journal entries'

    def handle(self, *args, **options):
        # Find all customer payment idempotency records
        all_records = IdempotencyRecord.objects.filter(
            operation_type='journal_entry',
            idempotency_key__contains='CustomerPayment'
        )

        self.stdout.write(f'Checking {all_records.count()} idempotency records...')

        orphaned = []
        for record in all_records:
            # Extract payment ID from key like 'JE:client:CustomerPayment:6:payment'
            parts = record.idempotency_key.split(':')
            if len(parts) >= 4:
                payment_id = parts[3]
                # Check if journal entry exists
                entry_exists = JournalEntry.objects.filter(
                    source_module='client',
                    source_model='CustomerPayment',
                    source_id=payment_id
                ).exists()

                if not entry_exists:
                    orphaned.append(record)
                    self.stdout.write(f'  Orphaned: {record.idempotency_key}')

        if orphaned:
            self.stdout.write(f'\nFound {len(orphaned)} orphaned records')
            confirm = input('Delete them? (yes/no): ')
            if confirm.lower() == 'yes':
                for record in orphaned:
                    record.delete()
                self.stdout.write(self.style.SUCCESS(f'Deleted {len(orphaned)} orphaned records'))
            else:
                self.stdout.write('Cancelled')
        else:
            self.stdout.write(self.style.SUCCESS('No orphaned records found'))
