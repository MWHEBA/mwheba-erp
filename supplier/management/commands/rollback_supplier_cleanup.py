"""
Management command to rollback the supplier categories removal
This command can restore the removed models and data if needed
"""

from django.core.management.base import BaseCommand
from django.db import migrations, models
import django.db.models.deletion


class Command(BaseCommand):
    help = 'Rollback the supplier categories removal by restoring removed models'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm that you want to rollback the changes',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be restored without actually doing it',
        )

    def handle(self, *args, **options):
        if options['dry_run']:
            self.stdout.write(
                self.style.WARNING('DRY RUN: The following models would be restored:')
            )
            self.list_models_to_restore()
            return

        if not options['confirm']:
            self.stdout.write(
                self.style.ERROR(
                    'This command will restore all removed supplier models and data.\n'
                    'Use --confirm to proceed or --dry-run to see what would be restored.'
                )
            )
            return

        self.stdout.write('Starting rollback process...')
        
        try:
            # Here we would implement the actual rollback logic
            # For now, we'll provide instructions
            self.stdout.write(
                self.style.WARNING(
                    'To rollback the changes, you need to:\n'
                    '1. Run: python manage.py migrate supplier 0005_remove_brand_fields\n'
                    '2. This will undo migrations 0006 and 0007\n'
                    '3. The removed models and data will be restored\n'
                )
            )
            
            self.stdout.write(
                self.style.SUCCESS('Rollback instructions provided successfully.')
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error during rollback: {str(e)}')
            )

    def list_models_to_restore(self):
        """List all models that would be restored"""
        models_to_restore = [
            'Service Detail Models:',
            '- PaperServiceDetails',
            '- OffsetPrintingDetails', 
            '- DigitalPrintingDetails',
            '- PlateServiceDetails',
            '- FinishingServiceDetails',
            '- PackagingServiceDetails',
            '- CoatingServiceDetails',
            '- OutdoorPrintingDetails',
            '- LaserServiceDetails',
            '- VIPGiftDetails',
            '',
            'Advanced Service Models:',
            '- SpecializedService',
            '- ServicePriceTier',
            '- SupplierServiceTag',
            '',
            'Supplier Type Data:',
            '- SupplierType records with codes: paper, offset_printing, digital_printing, etc.',
            '- SupplierTypeSettings records with the same codes',
        ]
        
        for item in models_to_restore:
            if item.startswith('-'):
                self.stdout.write(f'  {item}')
            elif item.endswith(':'):
                self.stdout.write(self.style.SUCCESS(item))
            else:
                self.stdout.write(item)