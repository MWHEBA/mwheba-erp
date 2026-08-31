"""
Comprehensive Unit & Integration Test Suite for MWHEBA ERP Backup & Disaster Recovery System
"""

import os
import json
import gzip
import shutil
import pytest
from pathlib import Path
from datetime import timedelta

from django.test import TestCase, Client
from django.urls import reverse
from django.conf import settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.management import call_command

from core.services.backup_service import BackupService
from core.models import SystemSetting, BackupRecord

User = get_user_model()


@pytest.mark.django_db
class BackupSystemTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.superuser = User.objects.create_superuser(
            username='admin_test',
            email='admin@mwheba.com',
            password='password123'
        )
        self.regular_user = User.objects.create_user(
            username='user_test',
            email='user@mwheba.com',
            password='password123'
        )
        self.backup_service = BackupService()

    def test_backup_service_initialization(self):
        """Verify backup service initializes paths and permissions properly"""
        assert self.backup_service.backup_dir.exists()
        assert self.backup_service.safety_dir.exists()
        assert self.backup_service.storage_type == 'local'
        assert not self.backup_service.is_maintenance_locked()

    def test_maintenance_lock_workflow(self):
        """Test global maintenance lock creation and release"""
        self.backup_service.set_maintenance_lock(True, "Testing lock")
        assert self.backup_service.is_maintenance_locked()
        
        self.backup_service.set_maintenance_lock(False)
        assert not self.backup_service.is_maintenance_locked()

    def test_create_database_backup(self):
        """Test database backup creation and verify non-empty file with correct hash"""
        res = self.backup_service.create_backup(backup_type='database')
        assert res['status'] == 'completed'
        assert len(res['files']) == 1
        assert res['size_bytes'] > 0
        
        file_path = Path(res['files'][0]['path'])
        assert file_path.exists()
        assert file_path.name.endswith('.gz')
        
        # Verify SHA-256
        calc_hash = self.backup_service._calculate_file_hash(file_path)
        assert calc_hash == res['files'][0]['hash']
        
        # Cleanup
        self.backup_service.delete_backup(res['backup_id'])

    def test_create_media_backup_extension(self):
        """Test media archive creation and ensure NO double extension (.tar.tar.gz)"""
        # Create a sample media file
        sample_file = Path(settings.MEDIA_ROOT) / 'test_sample.txt'
        sample_file.parent.mkdir(parents=True, exist_ok=True)
        sample_file.write_text("Test media content", encoding='utf-8')
        
        res = self.backup_service.create_backup(backup_type='media')
        assert res['status'] == 'completed'
        assert len(res['files']) == 1
        
        file_name = res['files'][0]['filename']
        assert file_name.endswith('.tar.gz')
        assert not file_name.endswith('.tar.tar.gz')
        
        # Cleanup
        sample_file.unlink(missing_ok=True)
        self.backup_service.delete_backup(res['backup_id'])

    def test_create_full_backup(self):
        """Test full backup packaging database and media into a zip archive"""
        res = self.backup_service.create_backup(backup_type='full')
        assert res['status'] == 'completed'
        assert len(res['files']) == 1
        
        zip_file = Path(res['files'][0]['path'])
        assert zip_file.exists()
        assert zip_file.name.endswith('.zip')
        
        # Verify listing
        backups = self.backup_service.list_backups()
        found = any(b['backup_id'] == res['backup_id'] for b in backups)
        assert found
        
        # Cleanup
        self.backup_service.delete_backup(res['backup_id'])

    def test_group_aware_retention_cleanup(self):
        """Test group retention cleanup deletes entire backup groups atomically"""
        SystemSetting.objects.update_or_create(
            key='backup_db_retention_count',
            defaults={'value': '2', 'group': 'backup', 'data_type': 'integer'}
        )
        
        b1 = self.backup_service.create_backup(backup_type='database')
        b2 = self.backup_service.create_backup(backup_type='database')
        b3 = self.backup_service.create_backup(backup_type='database')
        
        stats = self.backup_service.cleanup_old_backups()
        assert stats['status'] == 'completed'
        
        remaining_backups = self.backup_service.list_backups()
        db_backups = [b for b in remaining_backups if b.get('backup_type') == 'database']
        assert len(db_backups) <= 2
        
        # Cleanup all
        for b in remaining_backups:
            self.backup_service.delete_backup(b['backup_id'])

    def test_superuser_security_guard(self):
        """Test regular users and unauthenticated users cannot access backup APIs"""
        url = reverse('core:backup_create')
        
        # Unauthenticated -> redirect to dashboard/login
        resp = self.client.post(url, {'backup_type': 'database'})
        assert resp.status_code == 302
        
        # Regular user -> redirect to dashboard
        self.client.force_login(self.regular_user)
        resp = self.client.post(url, {'backup_type': 'database'})
        assert resp.status_code == 302
        
        # Superuser -> allowed
        self.client.force_login(self.superuser)
        resp = self.client.post(url, {'backup_type': 'database'})
        assert resp.status_code == 200
        data = resp.json()
        assert data['success'] is True
        
        self.backup_service.delete_backup(data['backup_id'])

    def test_backup_settings_boolean_and_atomic_save(self):
        """Test boolean serialization and atomic update in backup settings"""
        self.client.force_login(self.superuser)
        
        # Update settings
        update_url = reverse('core:backup_settings_update')
        resp = self.client.post(update_url, {
            'db_retention_type': 'count',
            'db_retention_count': '15',
            'db_retention_days': '45',
            'db_auto_cleanup': 'true',
            'enable_daily_db_backup': 'true',
            'daily_db_backup_time': '01:30'
        })
        assert resp.status_code == 200
        assert resp.json()['success'] is True
        
        # Retrieve settings
        get_url = reverse('core:backup_settings')
        resp = self.client.get(get_url)
        assert resp.status_code == 200
        settings_data = resp.json()['settings']
        
        assert settings_data['db_retention_count'] == 15
        assert settings_data['db_auto_cleanup'] is True
        assert isinstance(settings_data['db_auto_cleanup'], bool)
        assert settings_data['enable_daily_db_backup'] is True
        assert isinstance(settings_data['enable_daily_db_backup'], bool)
        assert settings_data['daily_db_backup_time'] == '01:30'

    def test_management_command_create_backup(self):
        """Test running python manage.py create_backup via CLI"""
        call_command('create_backup', backup_type='database', cleanup=False)
        backups = self.backup_service.list_backups()
        assert len(backups) > 0
        for b in backups:
            self.backup_service.delete_backup(b['backup_id'])
