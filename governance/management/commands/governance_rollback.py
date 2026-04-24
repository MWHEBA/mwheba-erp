"""
Management command for governance rollback operations.
Provides CLI interface for creating snapshots and performing rollbacks.
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.utils import timezone
from governance.services import (
    rollback_manager,
    create_governance_snapshot,
    rollback_to_snapshot,
    get_rollback_statistics
)

User = get_user_model()


class Command(BaseCommand):
    help = 'Manage governance rollback operations'
    
    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(dest='action', help='Available actions')
        
        # Create snapshot
        create_parser = subparsers.add_parser('create-snapshot', help='Create a governance snapshot')
        create_parser.add_argument('reason', help='Reason for creating snapshot')
        create_parser.add_argument('--user', help='Username (defaults to system)')
        
        # List snapshots
        list_parser = subparsers.add_parser('list-snapshots', help='List available snapshots')
        list_parser.add_argument('--recent', type=int, default=10, help='Number of recent snapshots to show')
        
        # Rollback
        rollback_parser = subparsers.add_parser('rollback', help='Rollback to a snapshot')
        rollback_parser.add_argument('snapshot_id', help='Snapshot ID to rollback to')
        rollback_parser.add_argument('reason', help='Reason for rollback')
        rollback_parser.add_argument('--user', help='Username (defaults to system)')
        rollback_parser.add_argument('--confirm', action='store_true', help='Confirm rollback operation')
        
        # Statistics
        stats_parser = subparsers.add_parser('stats', help='Show rollback statistics')
        
        # Violations
        violations_parser = subparsers.add_parser('record-violation', help='Record a test violation')
        violations_parser.add_argument('violation_type', help='Type of violation')
        violations_parser.add_argument('component', help='Component name')
        violations_parser.add_argument('--details', help='Additional details (JSON format)')
        violations_parser.add_argument('--user', help='Username (defaults to system)')
    
    def handle(self, *args, **options):
        action = options['action']
        
        if not action:
            self.print_help('manage.py', 'governance_rollback')
            return
        
        try:
            if action == 'create-snapshot':
                self.create_snapshot(options)
            elif action == 'list-snapshots':
                self.list_snapshots(options)
            elif action == 'rollback':
                self.rollback(options)
            elif action == 'stats':
                self.show_statistics(options)
            elif action == 'record-violation':
                self.record_violation(options)
            else:
                raise CommandError(f"Unknown action: {action}")
                
        except Exception as e:
            raise CommandError(f"Command failed: {e}")
    
    def create_snapshot(self, options):
        """Create a governance snapshot"""
        reason = options['reason']
        user = self.get_user(options.get('user'))
        
        self.stdout.write("Creating governance snapshot...")
        
        snapshot = create_governance_snapshot(reason, user)
        
        self.stdout.write(
            self.style.SUCCESS(f"Snapshot created successfully:")
        )
        self.stdout.write(f"  ID: {snapshot.snapshot_id}")
        self.stdout.write(f"  Reason: {snapshot.reason}")
        self.stdout.write(f"  Created by: {snapshot.created_by}")
        self.stdout.write(f"  Timestamp: {snapshot.timestamp}")
        self.stdout.write(f"  Components: {len(snapshot.component_flags)}")
        self.stdout.write(f"  Workflows: {len(snapshot.workflow_flags)}")
        self.stdout.write(f"  Emergency flags: {len(snapshot.emergency_flags)}")
    
    def list_snapshots(self, options):
        """List available snapshots"""
        recent_count = options['recent']
        
        snapshots = rollback_manager.get_recent_snapshots(recent_count)
        
        if not snapshots:
            self.stdout.write(self.style.WARNING("No snapshots available"))
            return
        
        self.stdout.write(f"Recent {len(snapshots)} snapshots:")
        self.stdout.write("-" * 80)
        
        for snapshot in reversed(snapshots):  # Show newest first
            self.stdout.write(f"ID: {snapshot.snapshot_id}")
            self.stdout.write(f"  Reason: {snapshot.reason}")
            self.stdout.write(f"  Created by: {snapshot.created_by}")
            self.stdout.write(f"  Timestamp: {snapshot.timestamp}")
            
            # Show enabled flags summary
            enabled_components = [name for name, enabled in snapshot.component_flags.items() if enabled]
            enabled_workflows = [name for name, enabled in snapshot.workflow_flags.items() if enabled]
            active_emergencies = [name for name, active in snapshot.emergency_flags.items() if active]
            
            self.stdout.write(f"  Enabled components: {len(enabled_components)}")
            if enabled_components:
                self.stdout.write(f"    {', '.join(enabled_components)}")
            
            self.stdout.write(f"  Active workflows: {len(enabled_workflows)}")
            if enabled_workflows:
                self.stdout.write(f"    {', '.join(enabled_workflows)}")
            
            if active_emergencies:
                self.stdout.write(
                    self.style.ERROR(f"  Emergency flags: {', '.join(active_emergencies)}")
                )
            
            self.stdout.write("-" * 80)
    
    def rollback(self, options):
        """Perform rollback to snapshot"""
        snapshot_id = options['snapshot_id']
        reason = options['reason']
        user = self.get_user(options.get('user'))
        confirm = options['confirm']
        
        # Find the snapshot
        snapshots = rollback_manager.get_snapshots()
        target_snapshot = None
        for snapshot in snapshots:
            if snapshot.snapshot_id == snapshot_id:
                target_snapshot = snapshot
                break
        
        if not target_snapshot:
            raise CommandError(f"Snapshot not found: {snapshot_id}")
        
        # Show rollback details
        self.stdout.write(f"Rollback target:")
        self.stdout.write(f"  ID: {target_snapshot.snapshot_id}")
        self.stdout.write(f"  Reason: {target_snapshot.reason}")
        self.stdout.write(f"  Created by: {target_snapshot.created_by}")
        self.stdout.write(f"  Timestamp: {target_snapshot.timestamp}")
        
        # Show what will change
        self.stdout.write(f"\nRollback will restore:")
        self.stdout.write(f"  Component flags: {len(target_snapshot.component_flags)}")
        self.stdout.write(f"  Workflow flags: {len(target_snapshot.workflow_flags)}")
        self.stdout.write(f"  Emergency flags: {len(target_snapshot.emergency_flags)}")
        
        if not confirm:
            self.stdout.write(
                self.style.WARNING("\nThis is a DRY RUN. Use --confirm to perform actual rollback.")
            )
            return
        
        # Confirm rollback
        self.stdout.write(
            self.style.WARNING(f"\nPerforming rollback to {snapshot_id}...")
        )
        
        success = rollback_to_snapshot(snapshot_id, reason, user)
        
        if success:
            self.stdout.write(
                self.style.SUCCESS("Rollback completed successfully!")
            )
        else:
            raise CommandError("Rollback failed")
    
    def show_statistics(self, options):
        """Show rollback statistics"""
        stats = get_rollback_statistics()
        
        self.stdout.write("Governance Rollback Statistics:")
        self.stdout.write("-" * 40)
        self.stdout.write(f"Total violations: {stats['total_violations']}")
        self.stdout.write(f"Total rollbacks: {stats['total_rollbacks']}")
        self.stdout.write(f"Emergency rollbacks: {stats['emergency_rollbacks']}")
        self.stdout.write(f"Active thresholds: {stats['active_thresholds']}")
        
        if stats['violation_types']:
            self.stdout.write("\nViolation types:")
            for violation_type, count in stats['violation_types'].items():
                self.stdout.write(f"  {violation_type}: {count}")
        
        if stats['recent_violations']:
            self.stdout.write("\nRecent violations (last hour):")
            for violation_type, count in stats['recent_violations'].items():
                if count > 0:
                    self.stdout.write(f"  {violation_type}: {count}")
    
    def record_violation(self, options):
        """Record a test violation"""
        violation_type = options['violation_type']
        component = options['component']
        details_str = options.get('details', '{}')
        user = self.get_user(options.get('user'))
        
        try:
            import json
            details = json.loads(details_str)
        except json.JSONDecodeError:
            raise CommandError("Invalid JSON format for details")
        
        details['component'] = component
        
        self.stdout.write(f"Recording violation: {violation_type}")
        
        from governance.services.rollback_manager import record_governance_violation
        record_governance_violation(violation_type, details, user)
        
        self.stdout.write(
            self.style.SUCCESS("Violation recorded successfully")
        )
        
        # Show updated statistics
        stats = get_rollback_statistics()
        self.stdout.write(f"Total violations: {stats['total_violations']}")
    
    def get_user(self, username):
        """Get user object or None"""
        if not username:
            return None
        
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f"User not found: {username}")
    
    def print_help(self, prog_name, subcommand):
        """Print help message"""
        self.stdout.write("Governance Rollback Management")
        self.stdout.write("=" * 40)
        self.stdout.write("")
        self.stdout.write("Available actions:")
        self.stdout.write("  create-snapshot <reason> [--user <username>]")
        self.stdout.write("  list-snapshots [--recent <count>]")
        self.stdout.write("  rollback <snapshot_id> <reason> [--user <username>] [--confirm]")
        self.stdout.write("  stats")
        self.stdout.write("  record-violation <type> <component> [--details <json>] [--user <username>]")
        self.stdout.write("")
        self.stdout.write("Examples:")
        self.stdout.write("  python manage.py governance_rollback create-snapshot 'Before deployment'")
        self.stdout.write("  python manage.py governance_rollback list-snapshots --recent 5")
        self.stdout.write("  python manage.py governance_rollback rollback snapshot_20231201_143022_1 'Emergency rollback' --confirm")
        self.stdout.write("  python manage.py governance_rollback stats")
        self.stdout.write("  python manage.py governance_rollback record-violation authority_violation accounting_gateway")