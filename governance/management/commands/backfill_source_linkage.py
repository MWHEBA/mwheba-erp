"""
Management command to backfill source linkage for orphaned journal entries.
This command is part of the SourceLinkage contract system implementation.
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from governance.services import SourceLinkageService
from governance.models import GovernanceContext
import json
import logging

User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Backfill source linkage for orphaned journal entries'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--entry-id',
            type=int,
            help='Specific journal entry ID to backfill'
        )
        
        parser.add_argument(
            '--source-module',
            type=str,
            help='Source module name (e.g., client)'
        )
        
        parser.add_argument(
            '--source-model',
            type=str,
            help='Source model name (e.g., CustomerPayment)'
        )
        
        parser.add_argument(
            '--source-id',
            type=int,
            help='Source record ID'
        )
        
        parser.add_argument(
            '--user-id',
            type=int,
            help='User ID to attribute the backfill operation to'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Validate the backfill without actually updating the database'
        )
        
        parser.add_argument(
            '--batch-file',
            type=str,
            help='JSON file containing batch backfill operations'
        )
        
        parser.add_argument(
            '--quarantine-unfixable',
            action='store_true',
            help='Quarantine entries that cannot be backfilled'
        )
    
    def handle(self, *args, **options):
        """Execute the source linkage backfill command"""
        
        try:
            # Get user for operations
            user = None
            if options['user_id']:
                try:
                    user = User.objects.get(id=options['user_id'])
                    self.stdout.write(f"Using user: {user.username}")
                except User.DoesNotExist:
                    raise CommandError(f"User with ID {options['user_id']} not found")
            else:
                # Try to get a superuser
                user = User.objects.filter(is_superuser=True).first()
                if user:
                    self.stdout.write(f"Using superuser: {user.username}")
                else:
                    raise CommandError("No user specified and no superuser found")
            
            # Set governance context
            GovernanceContext.set_context(user=user, service='SourceLinkageService')
            
            # Handle single entry backfill
            if options['entry_id']:
                if not all([options['source_module'], options['source_model'], options['source_id']]):
                    raise CommandError(
                        "For single entry backfill, you must provide: "
                        "--source-module, --source-model, and --source-id"
                    )
                
                success, message, details = SourceLinkageService.backfill_source_linkage(
                    entry_id=options['entry_id'],
                    source_module=options['source_module'],
                    source_model=options['source_model'],
                    source_id=options['source_id'],
                    user=user,
                    dry_run=options['dry_run']
                )
                
                if success:
                    if options['dry_run']:
                        self.stdout.write(
                            self.style.SUCCESS(f"✓ Dry run successful: {message}")
                        )
                    else:
                        self.stdout.write(
                            self.style.SUCCESS(f"✓ Backfill successful: {message}")
                        )
                    
                    if details:
                        self.stdout.write(f"Entry: {details.get('entry_number', 'Unknown')}")
                        if 'original_linkage' in details:
                            orig = details['original_linkage']
                            self.stdout.write(f"Original: {orig.get('source_module', 'None')}.{orig.get('source_model', 'None')}#{orig.get('source_id', 'None')}")
                        if 'new_linkage' in details:
                            new = details['new_linkage']
                            self.stdout.write(f"New: {new['source_module']}.{new['source_model']}#{new['source_id']}")
                else:
                    self.stdout.write(
                        self.style.ERROR(f"✗ Backfill failed: {message}")
                    )
                    if details and 'error' in details:
                        self.stdout.write(f"Error details: {details['error']}")
                
                return
            
            # Handle batch backfill from file
            if options['batch_file']:
                try:
                    with open(options['batch_file'], 'r', encoding='utf-8') as f:
                        batch_data = json.load(f)
                    
                    if 'backfill_operations' not in batch_data:
                        raise CommandError("Batch file must contain 'backfill_operations' array")
                    
                    operations = batch_data['backfill_operations']
                    self.stdout.write(f"Processing {len(operations)} backfill operations...")
                    
                    successful = 0
                    failed = 0
                    
                    for i, operation in enumerate(operations, 1):
                        try:
                            required_fields = ['entry_id', 'source_module', 'source_model', 'source_id']
                            if not all(field in operation for field in required_fields):
                                self.stdout.write(
                                    self.style.ERROR(f"Operation {i}: Missing required fields")
                                )
                                failed += 1
                                continue
                            
                            success, message, details = SourceLinkageService.backfill_source_linkage(
                                entry_id=operation['entry_id'],
                                source_module=operation['source_module'],
                                source_model=operation['source_model'],
                                source_id=operation['source_id'],
                                user=user,
                                dry_run=options['dry_run']
                            )
                            
                            if success:
                                successful += 1
                                if not options.get('quiet', False):
                                    entry_num = details.get('entry_number', operation['entry_id'])
                                    self.stdout.write(f"✓ Operation {i}: Entry {entry_num}")
                            else:
                                failed += 1
                                self.stdout.write(
                                    self.style.ERROR(f"✗ Operation {i}: {message}")
                                )
                                
                        except Exception as e:
                            failed += 1
                            self.stdout.write(
                                self.style.ERROR(f"✗ Operation {i}: Unexpected error - {e}")
                            )
                    
                    # Summary
                    self.stdout.write("\n" + "="*50)
                    self.stdout.write("BATCH BACKFILL SUMMARY")
                    self.stdout.write("="*50)
                    self.stdout.write(f"Total operations: {len(operations)}")
                    self.stdout.write(f"Successful: {successful}")
                    self.stdout.write(f"Failed: {failed}")
                    if options['dry_run']:
                        self.stdout.write("Mode: DRY RUN (no changes made)")
                    self.stdout.write("="*50)
                    
                except FileNotFoundError:
                    raise CommandError(f"Batch file not found: {options['batch_file']}")
                except json.JSONDecodeError as e:
                    raise CommandError(f"Invalid JSON in batch file: {e}")
                
                return
            
            # If no specific operation requested, show usage
            self.stdout.write("Source Linkage Backfill Command")
            self.stdout.write("="*40)
            self.stdout.write("Usage examples:")
            self.stdout.write("")
            self.stdout.write("1. Backfill single entry:")
            self.stdout.write("   python manage.py backfill_source_linkage \\")
            self.stdout.write("     --entry-id 123 \\")
            self.stdout.write("     --source-module client \\")
            self.stdout.write("     --source-model CustomerPayment \\")
            self.stdout.write("     --source-id 456")
            self.stdout.write("")
            self.stdout.write("2. Dry run validation:")
            self.stdout.write("   python manage.py backfill_source_linkage \\")
            self.stdout.write("     --entry-id 123 --source-module client \\")
            self.stdout.write("     --source-model CustomerPayment --source-id 456 --dry-run")
            self.stdout.write("")
            self.stdout.write("3. Batch backfill from file:")
            self.stdout.write("   python manage.py backfill_source_linkage \\")
            self.stdout.write("     --batch-file backfill_operations.json")
            self.stdout.write("")
            self.stdout.write("Batch file format:")
            self.stdout.write("{")
            self.stdout.write('  "backfill_operations": [')
            self.stdout.write("    {")
            self.stdout.write('      "entry_id": 123,')
            self.stdout.write('      "source_module": "client",')
            self.stdout.write('      "source_model": "CustomerPayment",')
            self.stdout.write('      "source_id": 456')
            self.stdout.write("    }")
            self.stdout.write("  ]")
            self.stdout.write("}")
            
        except Exception as e:
            logger.error(f"Error in source linkage backfill: {e}", exc_info=True)
            raise CommandError(f"Backfill failed: {e}")
        
        finally:
            # Clear governance context
            GovernanceContext.clear_context()