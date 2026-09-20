# -*- coding: utf-8 -*-
"""
Test Suite for Phase 10 RBAC Architecture
MWHEBA ERP - Enterprise Multi-Role, Role Hierarchy, Revocations, API Hardening & Audit
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import Client, RequestFactory
from django.urls import reverse
from users.models import Role, ActivityLog
from users.backends import RolePermissionBackend
from users.services.permission_cache import PermissionCacheService
import json

User = get_user_model()


@pytest.fixture
def permissions_setup(db):
    """Create sample content types and permissions for testing."""
    ct = ContentType.objects.get_for_model(User)
    perm1 = Permission.objects.get_or_create(codename='view_user', content_type=ct, defaults={'name': 'Can view user'})[0]
    perm2 = Permission.objects.get_or_create(codename='change_user', content_type=ct, defaults={'name': 'Can change user'})[0]
    perm3 = Permission.objects.get_or_create(codename='delete_user', content_type=ct, defaults={'name': 'Can delete user'})[0]
    perm4 = Permission.objects.get_or_create(codename='add_user', content_type=ct, defaults={'name': 'Can add user'})[0]
    return {
        'view': perm1,
        'change': perm2,
        'delete': perm3,
        'add': perm4,
    }


@pytest.mark.django_db
class TestPhase10MultiRoleAndHierarchy:
    """Test multi-role support and recursive parent role hierarchy."""

    def test_secondary_roles_union(self, permissions_setup):
        """User inherits permissions from both primary and secondary roles."""
        role1 = Role.objects.create(name='primary_role', display_name='Primary Role')
        role1.permissions.add(permissions_setup['view'])

        role2 = Role.objects.create(name='secondary_role', display_name='Secondary Role')
        role2.permissions.add(permissions_setup['change'])

        user = User.objects.create_user(username='multirole_user', password='password123', role=role1)
        user.secondary_roles.add(role2)

        backend = RolePermissionBackend()
        user_perms = backend.get_all_permissions(user)

        assert 'users.view_user' in user_perms
        assert 'users.change_user' in user_perms
        assert 'users.delete_user' not in user_perms

    def test_role_hierarchy_inheritance(self, permissions_setup):
        """Child role inherits permissions from parent role recursively."""
        grandparent_role = Role.objects.create(name='executive_role', display_name='Executive')
        grandparent_role.permissions.add(permissions_setup['view'])

        parent_role = Role.objects.create(name='senior_manager', display_name='Senior Manager', parent_role=grandparent_role)
        parent_role.permissions.add(permissions_setup['change'])

        child_role = Role.objects.create(name='team_lead', display_name='Team Lead', parent_role=parent_role)
        child_role.permissions.add(permissions_setup['add'])

        user = User.objects.create_user(username='hierarchy_user', password='password123', role=child_role)

        backend = RolePermissionBackend()
        user_perms = backend.get_all_permissions(user)

        assert 'users.add_user' in user_perms
        assert 'users.change_user' in user_perms
        assert 'users.view_user' in user_perms
        assert 'users.delete_user' not in user_perms

    def test_circular_role_hierarchy_prevention(self, permissions_setup):
        """Role hierarchy prevents infinite recursion and validates against cycles."""
        from django.core.exceptions import ValidationError

        role_a = Role.objects.create(name='role_a', display_name='Role A')
        role_b = Role.objects.create(name='role_b', display_name='Role B', parent_role=role_a)
        role_a.parent_role = role_b

        # 1. Proactive validation: save() must reject the cycle
        with pytest.raises(ValidationError):
            role_a.save()

        # 2. Defensive backend guard: If loop exists in DB via direct update, backend must not crash
        Role.objects.filter(id=role_a.id).update(parent_role=role_b)
        role_a.refresh_from_db()

        role_a.permissions.add(permissions_setup['view'])
        role_b.permissions.add(permissions_setup['change'])

        user = User.objects.create_user(username='loop_user', password='password123', role=role_a)

        backend = RolePermissionBackend()
        # Must execute without recursion overflow
        user_perms = backend.get_all_permissions(user)
        assert 'users.view_user' in user_perms
        assert 'users.change_user' in user_perms


@pytest.mark.django_db
class TestPhase10RevokedPermissions:
    """Test negative permission revocation overrides."""

    def test_revoked_permission_denial(self, permissions_setup):
        """Revoked permission subtracts from role-inherited permissions."""
        role = Role.objects.create(name='auditor_role', display_name='Auditor')
        role.permissions.add(permissions_setup['view'], permissions_setup['change'], permissions_setup['delete'])

        user = User.objects.create_user(username='revoked_user', password='password123', role=role)
        user.revoked_permissions.add(permissions_setup['delete'])

        backend = RolePermissionBackend()
        user_perms = backend.get_all_permissions(user)

        assert 'users.view_user' in user_perms
        assert 'users.change_user' in user_perms
        # Crucial check: delete_user MUST NOT be present
        assert 'users.delete_user' not in user_perms
        assert not user.has_perm('users.delete_user')

    def test_cache_invalidation_on_revocation_change(self, permissions_setup):
        """Modifying revoked permissions clears cached permission sets."""
        role = Role.objects.create(name='officer_role', display_name='Officer')
        role.permissions.add(permissions_setup['view'], permissions_setup['change'])

        user = User.objects.create_user(username='cached_user', password='password123', role=role)

        backend = RolePermissionBackend()
        assert 'users.change_user' in backend.get_all_permissions(user)

        # Revoke change_user
        user.revoked_permissions.add(permissions_setup['change'])
        if hasattr(user, '_cached_permissions'):
            delattr(user, '_cached_permissions')

        assert 'users.change_user' not in backend.get_all_permissions(user)


@pytest.mark.django_db
class TestPhase10APIHardening:
    """Test REST API hardening for salesmen and IsOwnerOrReadOnly."""

    def test_is_owner_or_read_only_rejects_plain_staff(self):
        """IsOwnerOrReadOnly must not grant full edit rights to staff without superuser/admin."""
        from api.permissions import IsOwnerOrReadOnly
        perm = IsOwnerOrReadOnly()

        rf = RequestFactory()
        req = rf.put('/api/some-endpoint/')
        staff_user = User.objects.create_user(username='plain_staff', password='password123', email='staff@test.com', is_staff=True)
        req.user = staff_user

        class DummyObj:
            created_by = None

        # Staff user is not owner and not superuser/admin -> must return False
        assert not perm.has_object_permission(req, None, DummyObj())

    def test_salesmen_endpoint_filtering(self, client):
        """Salesmen endpoint must only return users with sales role or permissions."""
        sales_role = Role.objects.create(name='sales_rep', display_name='مندوب مبيعات')
        sales_user = User.objects.create_user(username='sales_person', password='pass', email='sales@test.com', role=sales_role)

        accountant_role = Role.objects.create(name='accountant', display_name='محاسب')
        accountant_user = User.objects.create_user(username='accountant_person', password='pass', email='accountant@test.com', role=accountant_role)

        admin_user = User.objects.create_superuser(username='admin_boss', password='password123', email='admin@test.com')
        client.force_login(admin_user)

        res = client.get('/api/users/salesmen/')
        assert res.status_code == 200
        data = res.json()
        returned_usernames = [u['username'] for u in data]
        assert 'sales_person' in returned_usernames
        assert 'accountant_person' not in returned_usernames


@pytest.mark.django_db
class TestPhase10AuditAndForensics:
    """Test user permission update forensic diff logging."""

    def test_forensic_diff_logging(self, client, permissions_setup):
        """Updating custom permissions logs added and removed diffs to ActivityLog."""
        admin_user = User.objects.create_superuser(username='super_admin', password='password123', email='adm@test.com')
        target_user = User.objects.create_user(username='target_worker', password='password123', email='target@test.com')
        target_user.user_permissions.add(permissions_setup['view'])

        client.force_login(admin_user)

        payload = {
            'permission_ids': [permissions_setup['change'].id],
            'revoked_permission_ids': [permissions_setup['delete'].id]
        }

        url = reverse('users:user_update_custom_permissions', args=[target_user.id])
        res = client.post(url, data=json.dumps(payload), content_type='application/json')
        assert res.status_code == 200

        target_user.refresh_from_db()
        assert permissions_setup['change'] in target_user.user_permissions.all()
        assert permissions_setup['view'] not in target_user.user_permissions.all()
        assert permissions_setup['delete'] in target_user.revoked_permissions.all()

        log_entry = ActivityLog.objects.filter(model_name='User', object_id=target_user.id).order_by('-id').first()
        assert log_entry is not None
        assert 'view_user' in log_entry.extra_data.get('removed_permissions', [])
        assert 'change_user' in log_entry.extra_data.get('added_permissions', [])


@pytest.mark.django_db
class TestPhase10RoleHierarchyAndSafetyGuards:
    """Test role hierarchy depth limits, self-parenting guard, and descendant discovery."""

    def test_self_parenting_rejected(self):
        """Role cannot be its own parent."""
        from django.core.exceptions import ValidationError
        role = Role.objects.create(name='self_role', display_name='Self Role')
        role.parent_role = role
        with pytest.raises(ValidationError):
            role.save()

    def test_role_hierarchy_depth_cap(self):
        """Role hierarchy cannot exceed 4 levels."""
        from django.core.exceptions import ValidationError
        r1 = Role.objects.create(name='lvl1', display_name='L1')
        r2 = Role.objects.create(name='lvl2', display_name='L2', parent_role=r1)
        r3 = Role.objects.create(name='lvl3', display_name='L3', parent_role=r2)
        r4 = Role.objects.create(name='lvl4', display_name='L4', parent_role=r3)

        # 5th level must be rejected
        r5 = Role(name='lvl5', display_name='L5', parent_role=r4)
        with pytest.raises(ValidationError):
            r5.save()

    def test_get_all_descendant_roles(self):
        """get_all_descendant_roles returns all recursive children and grandchildren."""
        r_root = Role.objects.create(name='root', display_name='Root')
        r_child1 = Role.objects.create(name='child1', display_name='Child 1', parent_role=r_root)
        r_child2 = Role.objects.create(name='child2', display_name='Child 2', parent_role=r_root)
        r_grandchild = Role.objects.create(name='grandchild', display_name='Grandchild', parent_role=r_child1)

        descendants = r_root.get_all_descendant_roles()
        assert r_child1 in descendants
        assert r_child2 in descendants
        assert r_grandchild in descendants
        assert len(descendants) == 3


@pytest.mark.django_db
class TestPhase10SuperuserGuardsAndDataScoping:
    """Test superuser editing guards and centralized data scoping."""

    def test_superuser_assignment_and_perm_guard(self, client):
        """Superuser role and custom permissions cannot be modified via user endpoints."""
        admin = User.objects.create_superuser(username='super_admin2', password='password123', email='adm2@test.com')
        target_super = User.objects.create_superuser(username='target_super', password='password123', email='tsuper@test.com')
        client.force_login(admin)

        # Attempt to assign role to superuser -> 400
        url_assign = reverse('users:user_assign_role', args=[target_super.id])
        res1 = client.post(url_assign, data=json.dumps({'role_id': None}), content_type='application/json')
        assert res1.status_code == 400

        # Attempt to edit custom perms on superuser -> 400
        url_perms = reverse('users:user_update_custom_permissions', args=[target_super.id])
        res2 = client.post(url_perms, data=json.dumps({'permission_ids': []}), content_type='application/json')
        assert res2.status_code == 400

    def test_data_scoping_service_salesmen(self):
        """DataScopingService.get_scoped_salesmen correctly filters salesmen and excludes non-sales."""
        from users.services.data_scoping_service import DataScopingService

        sales_role = Role.objects.create(name='sales_rep', display_name='مندوب')
        sales_user = User.objects.create_user(username='scoped_rep', password='123', email='rep@test.com', role=sales_role)

        sec_role_user = User.objects.create_user(username='sec_rep', password='123', email='secrep@test.com')
        sec_role_user.secondary_roles.add(sales_role)

        driver_role = Role.objects.create(name='driver', display_name='سائق')
        driver_user = User.objects.create_user(username='driver_worker', password='123', email='driver@test.com', role=driver_role)

        salesmen = list(DataScopingService.get_scoped_salesmen())
        salesmen_ids = [u.id for u in salesmen]

        assert sales_user.id in salesmen_ids
        assert sec_role_user.id in salesmen_ids
        assert driver_user.id not in salesmen_ids

    def test_production_cache_backend_check(self):
        """check_production_cache_backend warns when LocMemCache is used with DEBUG=False."""
        from users.apps import check_production_cache_backend
        from django.test import override_settings

        with override_settings(DEBUG=False, CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}):
            warnings = check_production_cache_backend(None)
            assert len(warnings) == 1
            assert warnings[0].id == "users.W001"

        with override_settings(DEBUG=True, CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}):
            warnings = check_production_cache_backend(None)
            assert len(warnings) == 0

