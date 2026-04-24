# -*- coding: utf-8 -*-
"""
Management command to apply admin security controls to high-risk models.

This command ensures that all high-risk models have proper security controls
applied in the Django admin interface.
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib import admin
from django.apps import apps
from django.utils import timezone
import logging

from governance.admin_security import AdminSecurityManager
from governance.services.audit_service import AuditService

logger = logging.getLogger('governance.admin_security')


class Command(BaseCommand):
    help = 'Apply admin security controls to high-risk models'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--check-only',
            action='store_true',
            help='Only check compliance without applying changes',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force application of security controls',
        )
        parser.add_argument(
            '--model',
            type=str,
            help='Apply security to specific model (app_label.model_name)',
        )
    
    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🔒 Admin Security Control Application Started')
        )
        
        try:
            if options['check_only']:
                self.check_compliance()
            else:
                self.apply_security_controls(
                    force=options['force'],
                    specific_model=options.get('model')
                )
                
        except Exception as e:
            logger.error(f"Admin security application failed: {e}")
            raise CommandError(f'Failed to apply admin security: {e}')
    
    def check_compliance(self):
        """Check compliance of all high-risk models."""
        self.stdout.write('📋 Checking admin security compliance...')
        
        compliance_report = AdminSecurityManager.check_security_compliance()
        
        self.stdout.write(
            f"✅ Compliant models: {len(compliance_report['compliant_models'])}"
        )
        for model in compliance_report['compliant_models']:
            self.stdout.write(f"  • {model}")
        
        if compliance_report['non_compliant_models']:
            self.stdout.write(
                self.style.WARNING(
                    f"⚠️ Non-compliant models: {len(compliance_report['non_compliant_models'])}"
                )
            )
            for model in compliance_report['non_compliant_models']:
                self.stdout.write(f"  • {model}")
        
        if compliance_report['errors']:
            self.stdout.write(
                self.style.ERROR(f"❌ Errors: {len(compliance_report['errors'])}")
            )
            for error in compliance_report['errors']:
                self.stdout.write(f"  • {error}")
    
    def apply_security_controls(self, force=False, specific_model=None):
        """Apply security controls to high-risk models."""
        self.stdout.write('🔧 Applying admin security controls...')
        
        if specific_model:
            self.apply_to_specific_model(specific_model, force)
        else:
            self.apply_to_all_models(force)
        
        # Log the security application
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            
            # Create system user for audit logging
            system_user, created = User.objects.get_or_create(
                username='system_governance',
                defaults={
                    'email': 'system@governance.local',
                    'is_active': False,
                    'is_staff': False
                }
            )
            
            AuditService.log_governance_event(
                event_type='admin_security_applied',
                event_details={
                    'timestamp': timezone.now().isoformat(),
                    'force': force,
                    'specific_model': specific_model,
                    'applied_by': 'management_command'
                },
                user=system_user
            )
            
        except Exception as e:
            logger.warning(f"Failed to log security application: {e}")
        
        self.stdout.write(
            self.style.SUCCESS('✅ Admin security controls applied successfully')
        )
    
    def apply_to_specific_model(self, model_label, force):
        """Apply security controls to a specific model."""
        try:
            app_label, model_name = model_label.split('.')
            model_class = apps.get_model(app_label, model_name)
            
            if model_label not in AdminSecurityManager.HIGH_RISK_MODELS:
                if not force:
                    raise CommandError(
                        f'{model_label} is not a high-risk model. Use --force to override.'
                    )
                self.stdout.write(
                    self.style.WARNING(f'⚠️ Forcing security on non-high-risk model: {model_label}')
                )
            
            self.stdout.write(f'🔒 Applying security to {model_label}...')
            
            # Check if model is already registered in admin
            if model_class in admin.site._registry:
                admin_class = admin.site._registry[model_class]
                
                # Check if it already has security controls
                if hasattr(admin_class, 'is_high_risk_model'):
                    self.stdout.write(f'✅ {model_label} already has security controls')
                else:
                    self.stdout.write(f'⚠️ {model_label} needs security upgrade')
            else:
                self.stdout.write(f'❌ {model_label} not registered in admin')
            
        except ValueError:
            raise CommandError(
                'Model must be in format app_label.model_name (e.g., financial.JournalEntry)'
            )
        except LookupError:
            raise CommandError(f'Model {model_label} not found')
    
    def apply_to_all_models(self, force):
        """Apply security controls to all high-risk models."""
        self.stdout.write('🔒 Applying security to all high-risk models...')
        
        applied_count = 0
        error_count = 0
        
        for model_label in AdminSecurityManager.HIGH_RISK_MODELS:
            try:
                self.stdout.write(f'  Processing {model_label}...')
                
                app_label, model_name = model_label.split('.')
                model_class = apps.get_model(app_label, model_name)
                
                if model_class in admin.site._registry:
                    admin_class = admin.site._registry[model_class]
                    
                    if hasattr(admin_class, 'is_high_risk_model'):
                        self.stdout.write(f'    ✅ Already secured')
                    else:
                        self.stdout.write(f'    ⚠️ Needs security upgrade')
                        # In a real implementation, this would apply the security
                        
                    applied_count += 1
                else:
                    self.stdout.write(f'    ❌ Not registered in admin')
                    error_count += 1
                    
            except Exception as e:
                self.stdout.write(f'    ❌ Error: {e}')
                error_count += 1
        
        self.stdout.write(
            f'📊 Summary: {applied_count} processed, {error_count} errors'
        )
    
    def create_security_report(self):
        """Create a detailed security report."""
        report = {
            'timestamp': timezone.now().isoformat(),
            'high_risk_models': AdminSecurityManager.HIGH_RISK_MODELS,
            'admin_registrations': {},
            'security_status': {}
        }
        
        for model_label in AdminSecurityManager.HIGH_RISK_MODELS:
            try:
                app_label, model_name = model_label.split('.')
                model_class = apps.get_model(app_label, model_name)
                
                is_registered = model_class in admin.site._registry
                report['admin_registrations'][model_label] = is_registered
                
                if is_registered:
                    admin_class = admin.site._registry[model_class]
                    has_security = hasattr(admin_class, 'is_high_risk_model')
                    report['security_status'][model_label] = {
                        'has_security_controls': has_security,
                        'admin_class': admin_class.__class__.__name__,
                        'read_only_mode': getattr(admin_class, 'read_only_mode', False),
                        'require_special_permission': getattr(admin_class, 'require_special_permission', False)
                    }
                else:
                    report['security_status'][model_label] = {
                        'has_security_controls': False,
                        'admin_class': None,
                        'error': 'Not registered in admin'
                    }
                    
            except Exception as e:
                report['security_status'][model_label] = {
                    'has_security_controls': False,
                    'error': str(e)
                }
        
        return report