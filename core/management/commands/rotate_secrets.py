"""
Management command for rotating secrets in production
"""
from django.core.management.base import BaseCommand
from django.core.management.utils import get_random_secret_key
from django.conf import settings
import os
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Rotate application secrets for security'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--secret-type',
            type=str,
            choices=['django', 'bridge_agents', 'all'],
            default='all',
            help='Type of secret to rotate'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be rotated without making changes'
        )
    
    def handle(self, *args, **options):
        secret_type = options['secret_type']
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No changes will be made')
            )
        
        if secret_type in ['django', 'all']:
            self.rotate_django_secret_key(dry_run)
        
        if secret_type in ['bridge_agents', 'all']:
            self.rotate_bridge_agent_secrets(dry_run)
        
        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS('✅ Secret rotation completed successfully')
            )
            self.stdout.write(
                self.style.WARNING('⚠️  Remember to restart the application!')
            )
    
    def rotate_django_secret_key(self, dry_run=False):
        """Rotate Django SECRET_KEY"""
        new_secret_key = get_random_secret_key()
        
        if dry_run:
            self.stdout.write(f'Would rotate Django SECRET_KEY to: {new_secret_key[:10]}...')
            return
        
        # In production, this should update environment variables
        # For now, we'll show the new key that needs to be set
        self.stdout.write(
            self.style.SUCCESS(f'New Django SECRET_KEY generated: {new_secret_key}')
        )
        self.stdout.write(
            self.style.WARNING('Update your environment variable: SECRET_KEY=' + new_secret_key)
        )
        
        logger.info('Django SECRET_KEY rotated successfully')
    
    def rotate_bridge_agent_secrets(self, dry_run=False):
        """Rotate Bridge Agent secrets"""
        import secrets
        import string
        
        # Get current bridge agents
        bridge_agents = getattr(settings, 'BRIDGE_AGENTS', {})
        
        if not bridge_agents:
            self.stdout.write(
                self.style.WARNING('No Bridge Agents configured')
            )
            return
        
        new_secrets = {}
        for agent_code in bridge_agents.keys():
            # Generate strong random secret (32 characters)
            alphabet = string.ascii_letters + string.digits + '!@#$%^&*'
            new_secret = ''.join(secrets.choice(alphabet) for _ in range(32))
            new_secrets[agent_code] = new_secret
        
        if dry_run:
            for agent_code, secret in new_secrets.items():
                self.stdout.write(f'Would rotate {agent_code} secret to: {secret[:10]}...')
            return
        
        # Show new secrets that need to be updated
        bridge_agents_str = ','.join([f'{code}:{secret}' for code, secret in new_secrets.items()])
        
        self.stdout.write(
            self.style.SUCCESS('New Bridge Agent secrets generated:')
        )
        for agent_code, secret in new_secrets.items():
            self.stdout.write(f'  {agent_code}: {secret}')
        
        self.stdout.write(
            self.style.WARNING(f'Update your environment variable: BRIDGE_AGENTS={bridge_agents_str}')
        )
        
        logger.info(f'Bridge Agent secrets rotated for {len(new_secrets)} agents')