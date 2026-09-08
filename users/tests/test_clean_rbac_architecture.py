"""
Comprehensive Test Suite for MWHEBA ERP Clean RBAC Architecture
Validates:
1. Single Source of Truth (Role-based properties).
2. ModelBackend request-level caching and permission resolution.
3. Fast-path authorization for Superuser & Admin.
4. Segregation of Duties across the Enterprise Roles.
5. New custom Meta permissions in Sale, Purchase, Financial, Pricing, WorkOrder.
6. Absolute zero non-ascii / ghost permissions in auth_permission.
"""
import pytest
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from users.models import Role
from users.backends import RolePermissionBackend

User = get_user_model()


class CleanRBACArchitectureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Ensure clean roles exist
        cls.admin_role, _ = Role.objects.get_or_create(
            name='admin',
            defaults={'display_name': 'مدير النظام', 'is_system_role': True}
        )
        cls.fin_mgr_role, _ = Role.objects.get_or_create(
            name='financial_manager',
            defaults={'display_name': 'مدير مالي', 'is_system_role': True}
        )
        cls.accountant_role, _ = Role.objects.get_or_create(
            name='accountant',
            defaults={'display_name': 'محاسب', 'is_system_role': True}
        )
        cls.sales_mgr_role, _ = Role.objects.get_or_create(
            name='sales_manager',
            defaults={'display_name': 'مشرف مبيعات', 'is_system_role': True}
        )
        cls.sales_rep_role, _ = Role.objects.get_or_create(
            name='sales_rep',
            defaults={'display_name': 'مندوب مبيعات', 'is_system_role': True}
        )
        cls.inventory_mgr_role, _ = Role.objects.get_or_create(
            name='inventory_manager',
            defaults={'display_name': 'أمين مخزن ومواد', 'is_system_role': True}
        )

        # Assign specific permissions to roles for test
        sale_ct = ContentType.objects.get(app_label='sale', model='sale')
        cls.view_sale_perm = Permission.objects.get(content_type=sale_ct, codename='view_sale')
        cls.change_price_perm = Permission.objects.get(content_type=sale_ct, codename='change_unit_price')

        fin_period_ct = ContentType.objects.get(app_label='financial', model='accountingperiod')
        cls.close_period_perm = Permission.objects.get(content_type=fin_period_ct, codename='close_accounting_period')

        cls.sales_rep_role.permissions.set([cls.view_sale_perm])
        cls.sales_mgr_role.permissions.set([cls.view_sale_perm, cls.change_price_perm])
        cls.fin_mgr_role.permissions.set([cls.close_period_perm, cls.view_sale_perm])

    def setUp(self):
        self.backend = RolePermissionBackend()

    def test_no_arabic_ghost_permissions_exist(self):
        """Verify that zero non-ascii/Arabic codenames exist in auth_permission."""
        arabic_perms = Permission.objects.filter(codename__regex=r'[^\x00-\x7F]')
        self.assertEqual(arabic_perms.count(), 0, "Arabic permissions must be completely purged from DB.")

    def test_role_properties_single_source_of_truth(self):
        """Role-derived boolean properties match user.role."""
        rep = User.objects.create_user(username="rep_user", email="rep_user@corp.com", password="pwd", role=self.sales_rep_role)
        self.assertTrue(rep.is_sales_rep)
        self.assertFalse(rep.is_admin)
        self.assertFalse(rep.is_accountant)
        self.assertFalse(rep.is_financial_manager)

        mgr = User.objects.create_user(username="mgr_user", email="mgr_user@corp.com", password="pwd", role=self.fin_mgr_role)
        self.assertTrue(mgr.is_financial_manager)
        self.assertFalse(mgr.is_sales_rep)
        self.assertFalse(mgr.is_admin)

        sales_mgr = User.objects.create_user(username="smgr_user", email="smgr_user@corp.com", password="pwd", role=self.sales_mgr_role)
        self.assertTrue(sales_mgr.is_sales_manager)
        self.assertFalse(sales_mgr.is_sales_rep)

        role_perms = sales_mgr.get_role_permissions_list()
        self.assertIn('sale.view_sale', role_perms)
        self.assertIn('sale.change_unit_price', role_perms)

    def test_superuser_has_all_permissions_fast_path(self):
        """Superusers must always have all permissions immediately."""
        superuser = User.objects.create_superuser(username="root_admin", email="root@corp.com", password="pwd")
        self.assertTrue(superuser.has_perm('sale.view_sale'))
        self.assertTrue(superuser.has_perm('sale.change_unit_price'))
        self.assertTrue(superuser.has_perm('financial.close_accounting_period'))
        self.assertTrue(superuser.has_perm('any_app.non_existing_perm'))

    def test_admin_role_has_all_permissions(self):
        """Users with role='admin' must have full access."""
        admin_user = User.objects.create_user(username="owner_admin", email="owner_admin@corp.com", password="pwd", role=self.admin_role)
        self.assertTrue(admin_user.is_admin)
        self.assertTrue(admin_user.has_perm('sale.view_sale'))
        self.assertTrue(admin_user.has_perm('sale.change_unit_price'))
        self.assertTrue(admin_user.has_perm('financial.close_accounting_period'))

    def test_sales_rep_price_protection_segregation(self):
        """Sales Rep can view sales, but CANNOT change unit price."""
        sales_rep = User.objects.create_user(username="rep1", email="rep1@corp.com", password="pwd", role=self.sales_rep_role)
        self.assertTrue(sales_rep.has_perm('sale.view_sale'))
        self.assertFalse(sales_rep.has_perm('sale.change_unit_price'))
        self.assertFalse(sales_rep.has_perm('financial.close_accounting_period'))

    def test_sales_manager_can_change_price(self):
        """Sales Manager has explicit permission to change unit price."""
        sales_mgr = User.objects.create_user(username="sales_boss", email="sales_boss@corp.com", password="pwd", role=self.sales_mgr_role)
        self.assertTrue(sales_mgr.has_perm('sale.view_sale'))
        self.assertTrue(sales_mgr.has_perm('sale.change_unit_price'))
        self.assertFalse(sales_mgr.has_perm('financial.close_accounting_period'))

    def test_financial_manager_can_close_period(self):
        """Financial Manager can close accounting period, while others cannot."""
        fin_mgr = User.objects.create_user(username="cfo", email="cfo@corp.com", password="pwd", role=self.fin_mgr_role)
        self.assertTrue(fin_mgr.has_perm('financial.close_accounting_period'))

        accountant = User.objects.create_user(username="junior_acc", email="junior_acc@corp.com", password="pwd", role=self.accountant_role)
        self.assertFalse(accountant.has_perm('financial.close_accounting_period'))

    def test_request_level_permission_caching(self):
        """Verify that _cached_permissions on user_obj is populated and used."""
        rep = User.objects.create_user(username="cached_rep", email="cached_rep@corp.com", password="pwd", role=self.sales_rep_role)
        self.assertFalse(hasattr(rep, '_cached_permissions'))

        # First call populates cache
        perms = self.backend.get_all_permissions(rep)
        self.assertIn('sale.view_sale', perms)
        self.assertTrue(hasattr(rep, '_cached_permissions'))
        self.assertIn('sale.view_sale', rep._cached_permissions)

        # Subsequent call uses cache directly
        rep._cached_permissions = {'custom.dummy_perm'}
        self.assertTrue(self.backend.has_perm(rep, 'custom.dummy_perm'))

    def test_inactive_user_has_no_permissions(self):
        """Inactive users must have no permissions."""
        rep = User.objects.create_user(
            username="inactive_rep",
            email="inactive_rep@corp.com",
            password="pwd",
            role=self.sales_rep_role,
            is_active=False
        )
        self.assertFalse(rep.has_perm('sale.view_sale'))
        self.assertEqual(len(rep.get_all_permissions()), 0)

    def test_user_permissions_detail_endpoint(self):
        """Verify user_permissions_detail returns structured standard permission data."""
        from django.test import RequestFactory
        from users.permissions_views import user_permissions_detail
        
        admin_user = User.objects.create_superuser(username="admin_detail", email="admin_detail@corp.com", password="pwd")
        rep = User.objects.create_user(username="target_rep", email="target_rep@corp.com", password="pwd", role=self.sales_rep_role)
        
        factory = RequestFactory()
        request = factory.get(f"/users/permissions/users/{rep.id}/permissions/")
        request.user = admin_user
        
        response = user_permissions_detail(request, rep.id)
        self.assertEqual(response.status_code, 200)
        
        import json
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertIn('categories', data)
        self.assertIn('permissions_overview', data)
        self.assertIn('role_permissions', data)
        self.assertEqual(data['user']['id'], rep.id)
        self.assertEqual(data['user']['role_name'], self.sales_rep_role.display_name)

    def test_user_update_custom_permissions_endpoint(self):
        """Verify user_update_custom_permissions updates user.custom_permissions cleanly."""
        from django.test import RequestFactory
        from users.permissions_views import user_update_custom_permissions
        import json
        
        admin_user = User.objects.create_superuser(username="admin_update", email="admin_update@corp.com", password="pwd")
        rep = User.objects.create_user(username="perm_rep", email="perm_rep@corp.com", password="pwd", role=self.sales_rep_role)
        
        factory = RequestFactory()
        request = factory.post(
            f"/users/permissions/users/{rep.id}/update-custom-permissions/",
            data=json.dumps({'permission_ids': [self.view_sale_perm.id]}),
            content_type="application/json"
        )
        request.user = admin_user
        
        response = user_update_custom_permissions(request, rep.id)
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertIn(self.view_sale_perm, rep.custom_permissions.all())
