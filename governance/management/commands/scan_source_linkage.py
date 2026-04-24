"""
Management command to scan for orphaned journal entries and generate backfill reports.
This command is part of the SourceLinkage contract system implementation.
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from governance.services import SourceLinkageService
import json
import logging

User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Scan for orphaned journal entries and generate backfill reports'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=1000,
            help='Number of entries to process in each batch (default: 1000)'
        )
        
        parser.add_argument(
            '--output-file',
            type=str,
            help='Output file path for the orphaned entries report (JSON format)'
        )
        
        parser.add_argument(
            '--validate-allowlist',
            action='store_true',
            help='Validate that all allowlisted source models are accessible'
        )
        
        parser.add_argument(
            '--show-stats',
            action='store_true',
            help='Show source linkage statistics'
        )
        
        parser.add_argument(
            '--quiet',
            action='store_true',
            help='Suppress detailed output'
        )
    
    def handle(self, *args, **options):
        """Execute the source linkage scan command"""
        
        try:
            # Validate allowlist if requested
            if options['validate_allowlist']:
                self.stdout.write("Validating allowlisted source models...")
                errors = SourceLinkageService.validate_allowlist_models()
                
                if errors:
                    self.stdout.write(
                        self.style.ERROR(f"Allowlist validation failed with {len(errors)} errors:")
                    )
                    for error in errors:
                        self.stdout.write(self.style.ERROR(f"  - {error}"))
                    return
                else:
                    self.stdout.write(
                        self.style.SUCCESS("✓ All allowlisted source models are valid")
                    )
            
            # Show statistics if requested
            if options['show_stats']:
                self.stdout.write("Generating source linkage statistics...")
                stats = SourceLinkageService.get_backfill_statistics()
                
                if 'error' in stats:
                    self.stdout.write(
                        self.style.ERROR(f"Error generating statistics: {stats['error']}")
                    )
                    return
                
                self.stdout.write("\n" + "="*50)
                self.stdout.write("SOURCE LINKAGE STATISTICS")
                self.stdout.write("="*50)
                self.stdout.write(f"Total journal entries: {stats.get('total_entries', 0):,}")
                self.stdout.write(f"Complete linkage: {stats.get('complete_linkage_count', 0):,}")
                self.stdout.write(f"Missing linkage: {stats.get('missing_linkage_count', 0):,}")
                self.stdout.write(f"Completion percentage: {stats.get('linkage_completion_percentage', 0):.1f}%")
                self.stdout.write(f"Quarantined orphans: {stats.get('quarantined_orphans', 0):,}")
                
                if stats.get('entries_by_source'):
                    self.stdout.write("\nEntries by source model:")
                    for source, count in stats['entries_by_source'].items():
                        self.stdout.write(f"  {source}: {count:,}")
                
                self.stdout.write("="*50 + "\n")
            
            # Scan for orphaned entries
            self.stdout.write("Scanning for orphaned journal entries...")
            
            batch_size = options['batch_size']
            orphaned_entries = SourceLinkageService.scan_orphaned_entries(batch_size=batch_size)
            
            if not orphaned_entries:
                self.stdout.write(
                    self.style.SUCCESS("✓ No orphaned journal entries found!")
                )
                return
            
            # Report findings
            self.stdout.write(
                self.style.WARNING(f"Found {len(orphaned_entries)} orphaned journal entries")
            )
            
            # Group by issue type
            issues_by_type = {}
            for entry in orphaned_entries:
                issue_type = entry['issue']
                if issue_type not in issues_by_type:
                    issues_by_type[issue_type] = []
                issues_by_type[issue_type].append(entry)
            
            # Display summary
            if not options['quiet']:
                self.stdout.write("\nIssues by type:")
                for issue_type, entries in issues_by_type.items():
                    self.stdout.write(f"  {issue_type}: {len(entries)} entries")
                
                # Show sample entries
                self.stdout.write("\nSample orphaned entries:")
                for i, entry in enumerate(orphaned_entries[:5]):
                    self.stdout.write(
                        f"  {i+1}. Entry #{entry['entry_number']} ({entry['entry_date']}) - {entry['issue']}"
                    )
                
                if len(orphaned_entries) > 5:
                    self.stdout.write(f"  ... and {len(orphaned_entries) - 5} more entries")
            
            # Save to file if requested
            if options['output_file']:
                try:
                    with open(options['output_file'], 'w', encoding='utf-8') as f:
                        json.dump({
                            'scan_timestamp': str(logger.handlers[0].formatter.formatTime(logger.makeRecord(
                                'scan', logging.INFO, '', 0, '', (), None
                            )) if logger.handlers else 'unknown'),
                            'total_orphaned_entries': len(orphaned_entries),
                            'issues_by_type': {
                                issue_type: len(entries) 
                                for issue_type, entries in issues_by_type.items()
                            },
                            'orphaned_entries': orphaned_entries
                        }, f, indent=2, ensure_ascii=False)
                    
                    self.stdout.write(
                        self.style.SUCCESS(f"✓ Report saved to: {options['output_file']}")
                    )
                    
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"Error saving report: {e}")
                    )
            
            # Provide next steps guidance
            self.stdout.write("\n" + "="*50)
            self.stdout.write("NEXT STEPS")
            self.stdout.write("="*50)
            self.stdout.write("1. Review the orphaned entries report")
            self.stdout.write("2. Use 'backfill_source_linkage' command to fix entries")
            self.stdout.write("3. Quarantine entries that cannot be fixed")
            self.stdout.write("4. Re-run this scan to verify fixes")
            self.stdout.write("="*50)
            
        except Exception as e:
            logger.error(f"Error in source linkage scan: {e}", exc_info=True)
            raise CommandError(f"Scan failed: {e}")