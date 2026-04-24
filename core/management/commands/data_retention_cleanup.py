# ============================================================
# PHASE 5: DATA PROTECTION - DATA RETENTION CLEANUP COMMAND
# ============================================================

"""
Management command for data retention cleanup.
Implements automated data lifecycle management with compliance.
"""

import logging
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from core.services.data_retention_service import DataRetentionService

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Run data retention cleanup according to configured policies'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting'
        )
        
        parser.add_argument(
            '--policy',
            type=str,
            help='Run cleanup for specific policy only (model name)'
        )
        
        parser.add_argument(
            '--status',
            action='store_true',
            help='Show retention status for all policies'
        )
        
        parser.add_argument(
            '--notifications',
            action='store_true',
            help='Send notifications for upcoming deletions'
        )
        
        parser.add_argument(
            '--export',
            type=str,
            help='Export data for specified model before cleanup'
        )
        
        parser.add_argument(
            '--quiet',
            action='store_true',
            help='Suppress output except errors'
        )
    
    def handle(self, *args, **options):
        """Execute data retention command"""
        
        retention_service = DataRetentionService()
        
        try:
            # Show retention status
            if options['status']:
                self._show_retention_status(retention_service, options['quiet'])
                return
            
            # Send notifications
            if options['notifications']:
                self._send_notifications(retention_service, options['quiet'])
                return
            
            # Export data
            if options['export']:
                self._export_data(retention_service, options['export'], options['quiet'])
                return
            
            # Run cleanup
            if not options['quiet']:
                mode = "DRY RUN" if options['dry_run'] else "LIVE"
                self.stdout.write(
                    self.style.SUCCESS(f"Starting data retention cleanup ({mode}) at {timezone.now()}")
                )
            
            # Filter by specific policy if requested
            if options['policy']:
                original_policies = retention_service.retention_policies
                retention_service.retention_policies = [
                    p for p in original_policies 
                    if p.model_name == options['policy']
                ]
                
                if not retention_service.retention_policies:
                    raise CommandError(f"Policy not found: {options['policy']}")
            
            # Run cleanup
            cleanup_result = retention_service.run_retention_cleanup(
                dry_run=options['dry_run']
            )
            
            # Display results
            if not options['quiet']:
                self._display_cleanup_results(cleanup_result)
                
        except Exception as e:
            logger.error(f"Data retention command failed: {e}")
            raise CommandError(f"Data retention cleanup failed: {e}")
    
    def _show_retention_status(self, retention_service, quiet):
        """Show current retention status"""
        
        if not quiet:
            self.stdout.write(self.style.SUCCESS("📊 Data Retention Status"))
            self.stdout.write("=" * 60)
        
        try:
            status = retention_service.get_retention_status()
            
            for policy_status in status['policies']:
                if not quiet:
                    self.stdout.write(f"\n📋 {policy_status['model_name']}")
                    self.stdout.write(f"   Retention: {policy_status['retention_days']} days")
                    self.stdout.write(f"   Total Records: {policy_status['total_records']:,}")
                    self.stdout.write(f"   Expired Records: {policy_status['expired_records']:,}")
                    self.stdout.write(f"   Retention Rate: {policy_status['retention_percentage']:.1f}%")
                    
                    if policy_status['expired_records'] > 0:
                        self.stdout.write(
                            self.style.WARNING(f"   ⚠️ {policy_status['expired_records']} records ready for cleanup")
                        )
                    else:
                        self.stdout.write(
                            self.style.SUCCESS("   ✅ No expired records")
                        )
            
            if not quiet:
                self.stdout.write(f"\n📅 Status generated at: {status['timestamp']}")
                
        except Exception as e:
            raise CommandError(f"Failed to get retention status: {e}")
    
    def _send_notifications(self, retention_service, quiet):
        """Send retention notifications"""
        
        if not quiet:
            self.stdout.write(self.style.SUCCESS("📧 Sending retention notifications"))
        
        try:
            notification_result = retention_service.schedule_retention_notifications()
            
            if not quiet:
                self.stdout.write(f"✅ Notifications sent: {notification_result['notifications_sent']}")
                
                if notification_result['errors']:
                    self.stdout.write(self.style.ERROR("❌ Errors occurred:"))
                    for error in notification_result['errors']:
                        self.stdout.write(f"   - {error}")
                        
        except Exception as e:
            raise CommandError(f"Failed to send notifications: {e}")
    
    def _export_data(self, retention_service, model_name, quiet):
        """Export data for specified model"""
        
        if not quiet:
            self.stdout.write(self.style.SUCCESS(f"📤 Exporting data for {model_name}"))
        
        try:
            export_path = retention_service.create_data_export(model_name)
            
            if not quiet:
                self.stdout.write(f"✅ Data exported to: {export_path}")
                
        except Exception as e:
            raise CommandError(f"Failed to export data: {e}")
    
    def _display_cleanup_results(self, cleanup_result):
        """Display cleanup results"""
        
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("📊 Data Retention Cleanup Results"))
        self.stdout.write("=" * 60)
        
        # Overall summary
        self.stdout.write(f"🕐 Completed at: {cleanup_result['timestamp']}")
        self.stdout.write(f"📋 Policies processed: {cleanup_result['policies_processed']}")
        self.stdout.write(f"🗑️ Records deleted: {cleanup_result['records_deleted']:,}")
        self.stdout.write(f"📦 Records archived: {cleanup_result['records_archived']:,}")
        self.stdout.write(f"🔒 Records anonymized: {cleanup_result['records_anonymized']:,}")
        
        if cleanup_result['dry_run']:
            self.stdout.write(self.style.WARNING("⚠️ This was a DRY RUN - no actual changes made"))
        
        # Policy details
        if cleanup_result['policy_results']:
            self.stdout.write("\n📋 Policy Details:")
            self.stdout.write("-" * 40)
            
            for policy_result in cleanup_result['policy_results']:
                self.stdout.write(f"\n📄 {policy_result['policy_name']}")
                self.stdout.write(f"   Retention: {policy_result['retention_days']} days")
                self.stdout.write(f"   Cutoff: {policy_result['cutoff_date'].strftime('%Y-%m-%d %H:%M')}")
                self.stdout.write(f"   Deleted: {policy_result['deleted_count']:,}")
                self.stdout.write(f"   Archived: {policy_result['archived_count']:,}")
                self.stdout.write(f"   Anonymized: {policy_result['anonymized_count']:,}")
                
                if policy_result['errors']:
                    self.stdout.write(self.style.ERROR("   ❌ Errors:"))
                    for error in policy_result['errors']:
                        self.stdout.write(f"      - {error}")
                elif policy_result['deleted_count'] > 0:
                    self.stdout.write(self.style.SUCCESS("   ✅ Completed successfully"))
                else:
                    self.stdout.write("   ℹ️ No records to process")
        
        # Global errors
        if cleanup_result['errors']:
            self.stdout.write(self.style.ERROR("\n❌ Global Errors:"))
            for error in cleanup_result['errors']:
                self.stdout.write(f"   - {error}")
        
        # Summary message
        if cleanup_result['records_deleted'] > 0:
            if cleanup_result['dry_run']:
                self.stdout.write(
                    self.style.WARNING(f"\n⚠️ Would delete {cleanup_result['records_deleted']:,} records in live run")
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(f"\n✅ Successfully processed {cleanup_result['records_deleted']:,} records")
                )
        else:
            self.stdout.write(self.style.SUCCESS("\n✅ No records required cleanup"))