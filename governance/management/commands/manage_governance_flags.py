"""
Management command for governance feature flags.
Provides CLI interface for managing component and workflow flags.
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.utils import timezone
from governance.services import governance_switchboard
import json

User = get_user_model()


class Command(BaseCommand):
    help = 'Manage governance feature flags (components, workflows, emergency)'
    
    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(dest='action', help='Available actions')
        
        # Status command
        status_parser = subparsers.add_parser('status', help='Show current flag status')
        status_parser.add_argument('--json', action='store_true', help='Output as JSON')
        
        # Enable component
        enable_comp_parser = subparsers.add_parser('enable-component', help='Enable a component')
        enable_comp_parser.add_argument('component', help='Component name')
        enable_comp_parser.add_argument('--reason', default='CLI enable', help='Reason for enabling')
        enable_comp_parser.add_argument('--user', help='Username performing action')
        
        # Disable component
        disable_comp_parser = subparsers.add_parser('disable-component', help='Disable a component')
        disable_comp_parser.add_argument('component', help='Component name')
        disable_comp_parser.add_argument('--reason', default='CLI disable', help='Reason for disabling')
        disable_comp_parser.add_argument('--user', help='Username performing action')
        
        # Enable workflow
        enable_wf_parser = subparsers.add_parser('enable-workflow', help='Enable a workflow')
        enable_wf_parser.add_argument('workflow', help='Workflow name')
        enable_wf_parser.add_argument('--reason', default='CLI enable', help='Reason for enabling')
        enable_wf_parser.add_argument('--user', help='Username performing action')
        
        # Disable workflow
        disable_wf_parser = subparsers.add_parser('disable-workflow', help='Disable a workflow')
        disable_wf_parser.add_argument('workflow', help='Workflow name')
        disable_wf_parser.add_argument('--reason', default='CLI disable', help='Reason for disabling')
        disable_wf_parser.add_argument('--user', help='Username performing action')
        
        # Emergency commands
        emergency_parser = subparsers.add_parser('emergency', help='Emergency flag management')
        emergency_parser.add_argument('emergency_action', choices=['activate', 'deactivate'], help='Emergency action')
        emergency_parser.add_argument('emergency_name', help='Emergency flag name')
        emergency_parser.add_argument('--reason', required=True, help='Reason for emergency action')
        emergency_parser.add_argument('--user', help='Username performing action')
        
        # List available flags
        list_parser = subparsers.add_parser('list', help='List available flags')
        list_parser.add_argument('--type', choices=['components', 'workflows', 'emergency'], help='Filter by type')
        
        # Validate configuration
        subparsers.add_parser('validate', help='Validate switchboard configuration')
        
        # Health check
        subparsers.add_parser('health', help='Show governance health status')
    
    def handle(self, *args, **options):
        action = options.get('action')
        
        if not action:
            self.print_help('manage.py', 'manage_governance_flags')
            return
        
        try:
            if action == 'status':
                self.handle_status(options)
            elif action == 'enable-component':
                self.handle_enable_component(options)
            elif action == 'disable-component':
                self.handle_disable_component(options)
            elif action == 'enable-workflow':
                self.handle_enable_workflow(options)
            elif action == 'disable-workflow':
                self.handle_disable_workflow(options)
            elif action == 'emergency':
                self.handle_emergency(options)
            elif action == 'list':
                self.handle_list(options)
            elif action == 'validate':
                self.handle_validate()
            elif action == 'health':
                self.handle_health()
            else:
                raise CommandError(f"Unknown action: {action}")
                
        except Exception as e:
            raise CommandError(f"Command failed: {str(e)}")
    
    def handle_status(self, options):
        """Show current flag status"""
        stats = governance_switchboard.get_governance_statistics()
        
        if options.get('json'):
            self.stdout.write(json.dumps(stats, indent=2, default=str))
            return
        
        self.stdout.write(self.style.SUCCESS("=== Governance Switchboard Status ==="))
        
        # Components
        self.stdout.write(f"\n{self.style.WARNING('Components:')} ({stats['components']['enabled']}/{stats['components']['total']} enabled)")
        for comp in stats['components']['enabled_list']:
            self.stdout.write(f"  ✓ {comp}")
        for comp in stats['components']['disabled_list']:
            self.stdout.write(f"  ✗ {comp}")
        
        # Workflows
        self.stdout.write(f"\n{self.style.WARNING('Workflows:')} ({stats['workflows']['enabled']}/{stats['workflows']['total']} enabled)")
        for wf in stats['workflows']['enabled_list']:
            risk = governance_switchboard.WORKFLOW_FLAGS.get(wf, {}).get('risk_level', 'UNKNOWN')
            self.stdout.write(f"  ✓ {wf} (Risk: {risk})")
        for wf in stats['workflows']['disabled_list']:
            risk = governance_switchboard.WORKFLOW_FLAGS.get(wf, {}).get('risk_level', 'UNKNOWN')
            self.stdout.write(f"  ✗ {wf} (Risk: {risk})")
        
        # Emergency flags
        if stats['emergency']['active']:
            self.stdout.write(f"\n{self.style.ERROR('ACTIVE EMERGENCIES:')} ({stats['emergency']['active']})")
            for emerg in stats['emergency']['active_list']:
                self.stdout.write(f"  🚨 {emerg}")
        else:
            self.stdout.write(f"\n{self.style.SUCCESS('Emergency Flags:')} None active")
        
        # Health
        health = stats['health']
        if health['emergency_override']:
            self.stdout.write(f"\n{self.style.ERROR('HEALTH: EMERGENCY OVERRIDE ACTIVE')}")
        elif health['governance_active']:
            self.stdout.write(f"\n{self.style.SUCCESS('HEALTH: Governance Active')}")
        else:
            self.stdout.write(f"\n{self.style.WARNING('HEALTH: No governance active')}")
        
        # Counters
        counters = stats['counters']
        self.stdout.write(f"\nCounters: Changes={counters['flag_changes']}, Emergencies={counters['emergency_activations']}, Violations={counters['governance_violations']}")
    
    def handle_enable_component(self, options):
        """Enable a component"""
        component = options['component']
        reason = options['reason']
        user = self._get_user(options.get('user'))
        
        if component not in governance_switchboard.COMPONENT_FLAGS:
            available = list(governance_switchboard.COMPONENT_FLAGS.keys())
            raise CommandError(f"Unknown component '{component}'. Available: {available}")
        
        success = governance_switchboard.enable_component(component, reason, user)
        if success:
            self.stdout.write(self.style.SUCCESS(f"Component '{component}' enabled"))
        else:
            self.stdout.write(self.style.ERROR(f"Failed to enable component '{component}'"))
    
    def handle_disable_component(self, options):
        """Disable a component"""
        component = options['component']
        reason = options['reason']
        user = self._get_user(options.get('user'))
        
        if component not in governance_switchboard.COMPONENT_FLAGS:
            available = list(governance_switchboard.COMPONENT_FLAGS.keys())
            raise CommandError(f"Unknown component '{component}'. Available: {available}")
        
        success = governance_switchboard.disable_component(component, reason, user)
        if success:
            self.stdout.write(self.style.SUCCESS(f"Component '{component}' disabled"))
        else:
            self.stdout.write(self.style.ERROR(f"Failed to disable component '{component}'"))
    
    def handle_enable_workflow(self, options):
        """Enable a workflow"""
        workflow = options['workflow']
        reason = options['reason']
        user = self._get_user(options.get('user'))
        
        if workflow not in governance_switchboard.WORKFLOW_FLAGS:
            available = list(governance_switchboard.WORKFLOW_FLAGS.keys())
            raise CommandError(f"Unknown workflow '{workflow}'. Available: {available}")
        
        success = governance_switchboard.enable_workflow(workflow, reason, user)
        if success:
            self.stdout.write(self.style.SUCCESS(f"Workflow '{workflow}' enabled"))
        else:
            self.stdout.write(self.style.ERROR(f"Failed to enable workflow '{workflow}'"))
    
    def handle_disable_workflow(self, options):
        """Disable a workflow"""
        workflow = options['workflow']
        reason = options['reason']
        user = self._get_user(options.get('user'))
        
        if workflow not in governance_switchboard.WORKFLOW_FLAGS:
            available = list(governance_switchboard.WORKFLOW_FLAGS.keys())
            raise CommandError(f"Unknown workflow '{workflow}'. Available: {available}")
        
        success = governance_switchboard.disable_workflow(workflow, reason, user)
        if success:
            self.stdout.write(self.style.SUCCESS(f"Workflow '{workflow}' disabled"))
        else:
            self.stdout.write(self.style.ERROR(f"Failed to disable workflow '{workflow}'"))
    
    def handle_emergency(self, options):
        """Handle emergency flag operations"""
        action = options['emergency_action']
        emergency_name = options['emergency_name']
        reason = options['reason']
        user = self._get_user(options.get('user'))
        
        if emergency_name not in governance_switchboard.EMERGENCY_FLAGS:
            available = list(governance_switchboard.EMERGENCY_FLAGS.keys())
            raise CommandError(f"Unknown emergency flag '{emergency_name}'. Available: {available}")
        
        if action == 'activate':
            success = governance_switchboard.activate_emergency_flag(emergency_name, reason, user)
            if success:
                self.stdout.write(self.style.ERROR(f"🚨 EMERGENCY FLAG ACTIVATED: {emergency_name}"))
            else:
                self.stdout.write(self.style.ERROR(f"Failed to activate emergency flag '{emergency_name}'"))
        
        elif action == 'deactivate':
            success = governance_switchboard.deactivate_emergency_flag(emergency_name, reason, user)
            if success:
                self.stdout.write(self.style.SUCCESS(f"Emergency flag deactivated: {emergency_name}"))
            else:
                self.stdout.write(self.style.ERROR(f"Failed to deactivate emergency flag '{emergency_name}'"))
    
    def handle_list(self, options):
        """List available flags"""
        flag_type = options.get('type')
        
        if not flag_type or flag_type == 'components':
            self.stdout.write(self.style.SUCCESS("=== Component Flags ==="))
            for name, config in governance_switchboard.COMPONENT_FLAGS.items():
                critical = "CRITICAL" if config['critical'] else "normal"
                self.stdout.write(f"  {name} ({critical})")
                self.stdout.write(f"    {config['description']}")
                if config.get('affects_workflows'):
                    self.stdout.write(f"    Affects workflows: {config['affects_workflows']}")
                self.stdout.write("")
        
        if not flag_type or flag_type == 'workflows':
            self.stdout.write(self.style.SUCCESS("=== Workflow Flags ==="))
            for name, config in governance_switchboard.WORKFLOW_FLAGS.items():
                risk = config.get('risk_level', 'UNKNOWN')
                critical = "CRITICAL" if config['critical'] else "normal"
                self.stdout.write(f"  {name} (Risk: {risk}, {critical})")
                self.stdout.write(f"    {config['description']}")
                if config.get('component_dependencies'):
                    self.stdout.write(f"    Requires components: {config['component_dependencies']}")
                if config.get('corruption_prevention'):
                    self.stdout.write(f"    Prevents: {config['corruption_prevention']}")
                self.stdout.write("")
        
        if not flag_type or flag_type == 'emergency':
            self.stdout.write(self.style.SUCCESS("=== Emergency Flags ==="))
            for name, config in governance_switchboard.EMERGENCY_FLAGS.items():
                self.stdout.write(f"  {name}")
                self.stdout.write(f"    {config['description']}")
                affects = config.get('affects', [])
                if affects == 'ALL_COMPONENTS_AND_WORKFLOWS':
                    self.stdout.write(f"    Affects: ALL GOVERNANCE")
                else:
                    self.stdout.write(f"    Affects: {affects}")
                self.stdout.write("")
    
    def handle_validate(self):
        """Validate switchboard configuration"""
        errors = governance_switchboard.validate_configuration()
        
        if not errors:
            self.stdout.write(self.style.SUCCESS("✓ Switchboard configuration is valid"))
        else:
            self.stdout.write(self.style.ERROR("✗ Configuration errors found:"))
            for error in errors:
                self.stdout.write(f"  - {error}")
    
    def handle_health(self):
        """Show governance health status"""
        health = governance_switchboard.get_governance_statistics()['health']
        
        self.stdout.write(self.style.SUCCESS("=== Governance Health Status ==="))
        
        if health['emergency_override']:
            self.stdout.write(self.style.ERROR("🚨 EMERGENCY OVERRIDE ACTIVE - All governance disabled"))
        elif health['governance_active']:
            self.stdout.write(self.style.SUCCESS("✓ Governance is active"))
        else:
            self.stdout.write(self.style.WARNING("⚠ No governance components active"))
        
        if health['critical_workflows_protected']:
            self.stdout.write(self.style.SUCCESS("✓ Critical workflows are protected"))
        else:
            self.stdout.write(self.style.WARNING("⚠ No critical workflows protected"))
    
    def _get_user(self, username):
        """Get user object from username"""
        if not username:
            return None
        
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f"User '{username}' not found")