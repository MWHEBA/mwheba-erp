import pytest
from django.urls import reverse
from django.test import override_settings
from django.contrib.auth import get_user_model
from users.models import Role, ActivityLog
from sale.models import Sale
from customer.models import Customer
from purchase.models import Purchase
from supplier.models import Supplier
from decimal import Decimal

User = get_user_model()


@pytest.fixture
def clean_roles(db):
    """إعداد الأدوار القياسية النظيفة"""
    from django.core.management import call_command
    call_command('seed_clean_roles')


@pytest.fixture
def superuser(db, clean_roles):
    admin_role = Role.objects.get(name='admin')
    user = User.objects.create_superuser(
        username='p9_superuser',
        email='p9_super@example.com',
        password='TestPassword123!',
        role=admin_role
    )
    return user


@pytest.fixture
def secondary_superuser(db, clean_roles):
    admin_role = Role.objects.get(name='admin')
    user = User.objects.create_superuser(
        username='p9_super2',
        email='p9_super2@example.com',
        password='TestPassword123!',
        role=admin_role
    )
    return user


@pytest.fixture
def viewer_user(db, clean_roles):
    role = Role.objects.get(name='viewer')
    user = User.objects.create_user(
        username='p9_viewer',
        email='p9_viewer@example.com',
        password='TestPassword123!',
        role=role
    )
    return user


@pytest.fixture
def sales_rep_user(db, clean_roles):
    role = Role.objects.get(name='sales_rep')
    user = User.objects.create_user(
        username='p9_salesrep',
        email='p9_salesrep@example.com',
        password='TestPassword123!',
        role=role
    )
    return user


@pytest.fixture
def accountant_user(db, clean_roles):
    role = Role.objects.get(name='accountant')
    user = User.objects.create_user(
        username='p9_accountant',
        email='p9_accountant@example.com',
        password='TestPassword123!',
        role=role
    )
    return user


@pytest.fixture
def inventory_manager_user(db, clean_roles):
    role = Role.objects.get(name='inventory_manager')
    user = User.objects.create_user(
        username='p9_invmanager',
        email='p9_invmanager@example.com',
        password='TestPassword123!',
        role=role
    )
    return user


@pytest.fixture
def sample_customer(db):
    return Customer.objects.create(name='عميل تجريبي مرحلة 9', phone='01012345678')


@pytest.fixture
def sample_supplier(db):
    return Supplier.objects.create(name='مورد تجريبي مرحلة 9', phone='01112345678')


from product.models import Warehouse
from django.utils import timezone


@pytest.fixture
def sample_warehouse(db):
    return Warehouse.objects.create(name='مخزن رئيسي تجريبي', is_active=True)


@pytest.fixture
def sample_sale(db, sample_customer, superuser, sample_warehouse):
    return Sale.objects.create(
        number='INV-P9-001',
        customer=sample_customer,
        warehouse=sample_warehouse,
        date=timezone.now().date(),
        subtotal=Decimal('1000.00'),
        total=Decimal('1000.00'),
        payment_status='unpaid',
        payment_method='cash',
        status='draft',
        created_by=superuser
    )


@pytest.fixture
def sample_purchase(db, sample_supplier, superuser, sample_warehouse):
    return Purchase.objects.create(
        number='PUR-P9-001',
        supplier=sample_supplier,
        warehouse=sample_warehouse,
        date=timezone.now().date(),
        subtotal=Decimal('2000.00'),
        total=Decimal('2000.00'),
        payment_status='unpaid',
        payment_method='cash',
        status='draft',
        created_by=superuser
    )


# =========================================================================
# 1. اختبارات دورة حياة انتحال الهوية (Impersonation Lifecycle & Audit)
# =========================================================================

@pytest.mark.django_db
class TestImpersonationSecurity:

    def test_superuser_can_impersonate_regular_user(self, client, superuser, viewer_user):
        """المدير العام يمكنه انتحال هوية مستخدم عادي مع تسجيل سجل الرقابة ومسح الكاش"""
        client.force_login(superuser)
        url = reverse('users:login_as_user', args=[viewer_user.id])
        
        response = client.post(url)
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

        # التحقق من تسجيل النشاط في سجل الرقابة
        log = ActivityLog.objects.filter(action='IMPERSONATION_START', user=superuser).first()
        assert log is not None
        assert log.extra_data.get('target_username') == viewer_user.username

        # التحقق من أن الجلسة تحولت لليوزر الهدف
        session = client.session
        assert session.get('is_impersonating') is True
        assert session.get('impersonated_by') == superuser.id

    def test_impersonation_attaches_security_header(self, client, superuser, viewer_user):
        """الـ Middleware يضيف ترويسة X-Impersonated-By أثناء الانتحال"""
        client.force_login(superuser)
        client.post(reverse('users:login_as_user', args=[viewer_user.id]))

        # طلب أي صفحة
        response = client.get(reverse('core:dashboard'))
        assert response.status_code == 200
        assert response.get('X-Impersonated-By') == superuser.username

    def test_stop_impersonation_restores_admin_and_logs(self, client, superuser, viewer_user):
        """إنهاء الانتحال يسترجع حساب المشرف ويسجل في AuditLog ويزيل الترويسة"""
        client.force_login(superuser)
        client.post(reverse('users:login_as_user', args=[viewer_user.id]))

        # إيقاف الانتحال
        stop_url = reverse('users:stop_impersonation')
        response = client.get(stop_url, follow=True)
        assert response.status_code == 200

        # الجلسة تم تنظيفها
        session = client.session
        assert 'is_impersonating' not in session
        assert 'impersonated_by' not in session

        # توثيق في ActivityLog
        stop_log = ActivityLog.objects.filter(action='IMPERSONATION_STOP', user=superuser).first()
        assert stop_log is not None

        # الصفحة التالية لا تحوي الترويسة
        dash_response = client.get(reverse('core:dashboard'))
        assert dash_response.get('X-Impersonated-By') is None

    def test_cannot_impersonate_another_superuser(self, client, superuser, secondary_superuser):
        """حظر أمني: لا يمكن انتحال حساب مدير عام آخر"""
        client.force_login(superuser)
        url = reverse('users:login_as_user', args=[secondary_superuser.id])
        response = client.post(url)
        assert response.status_code == 403
        data = response.json()
        assert data['success'] is False

    def test_regular_user_cannot_impersonate(self, client, viewer_user, sales_rep_user):
        """مستخدم غير مصرح لا يمكنه استدعاء login_as_user"""
        client.force_login(viewer_user)
        url = reverse('users:login_as_user', args=[sales_rep_user.id])
        response = client.post(url)
        assert response.status_code == 403

    def test_nested_impersonation_is_blocked(self, client, superuser, viewer_user, sales_rep_user):
        """حظر الانتحال المتداخل"""
        client.force_login(superuser)
        client.post(reverse('users:login_as_user', args=[viewer_user.id]))

        # محاولة انتحال مستخدم ثانٍ أثناء وضع الانتحال
        url = reverse('users:login_as_user', args=[sales_rep_user.id])
        response = client.post(url)
        assert response.status_code in [400, 403]


# =========================================================================
# 2. اختبارات خلو الـ DOM من تسرب الصلاحيات والأزرار في شاشات التفاصيل
# =========================================================================

@pytest.mark.django_db
class TestDetailViewsDomGating:

    def test_viewer_cannot_see_sale_edit_or_delete_actions(self, client, viewer_user, sample_sale):
        """مستخدم الاستعلام لا يرى أزرار التعديل أو الحذف في تفاصيل الفاتورة"""
        client.force_login(viewer_user)
        url = reverse('sale:sale_detail', args=[sample_sale.pk])
        response = client.get(url)
        assert response.status_code == 200

        content = response.content.decode('utf-8')
        edit_url = reverse('sale:sale_edit', args=[sample_sale.pk])
        delete_url = reverse('sale:sale_delete', args=[sample_sale.pk])

        assert edit_url not in content
        assert delete_url not in content

    def test_superuser_sees_sale_edit_and_delete_actions(self, client, superuser, sample_sale):
        """المدير العام يرى خيارات التعديل والحذف للفاتورة المسودة"""
        client.force_login(superuser)
        url = reverse('sale:sale_detail', args=[sample_sale.pk])
        response = client.get(url)
        assert response.status_code == 200

        content = response.content.decode('utf-8')
        edit_url = reverse('sale:sale_edit', args=[sample_sale.pk])
        delete_url = reverse('sale:sale_delete', args=[sample_sale.pk])

        assert edit_url in content
        assert delete_url in content

    def test_paid_sale_does_not_show_delete_even_for_admin(self, client, superuser, sample_sale):
        """الفاتورة المدفوعة لا تعرض زر الحذف حتى للأدمن التزاماً بدورة حياة المستند"""
        from sale.models import SalePayment
        SalePayment.objects.create(
            sale=sample_sale,
            amount=sample_sale.total,
            status='posted',
            payment_method='cash',
            payment_date=timezone.now().date(),
            created_by=superuser
        )
        sample_sale.refresh_from_db()
        sample_sale.save()

        client.force_login(superuser)
        url = reverse('sale:sale_detail', args=[sample_sale.pk])
        response = client.get(url)
        assert response.status_code == 200

        content = response.content.decode('utf-8')
        delete_url = reverse('sale:sale_delete', args=[sample_sale.pk])
        assert delete_url not in content

    def test_viewer_cannot_see_purchase_edit_or_delete(self, client, viewer_user, sample_purchase):
        """مستخدم الاستعلام لا يرى أزرار التعديل أو الحذف في فواتير المشتريات"""
        client.force_login(viewer_user)
        url = reverse('purchase:purchase_detail', args=[sample_purchase.pk])
        response = client.get(url)
        assert response.status_code == 200

        content = response.content.decode('utf-8')
        edit_url = reverse('purchase:purchase_edit', args=[sample_purchase.pk])
        delete_url = reverse('purchase:purchase_delete', args=[sample_purchase.pk])

        assert edit_url not in content
        assert delete_url not in content

    def test_viewer_cannot_see_customer_delete_or_edit(self, client, viewer_user, sample_customer):
        """مستخدم الاستعلام لا يرى خيارات تعديل أو حذف العميل في customer_detail"""
        client.force_login(viewer_user)
        url = reverse('customer:customer_detail', args=[sample_customer.pk])
        response = client.get(url)
        assert response.status_code == 200

        content = response.content.decode('utf-8')
        edit_url = reverse('customer:customer_edit', args=[sample_customer.pk])
        assert edit_url not in content
        assert 'حذف / أرشفة العميل' not in content

    def test_viewer_cannot_see_supplier_delete_or_edit(self, client, viewer_user, sample_supplier):
        """مستخدم الاستعلام لا يرى خيارات تعديل أو حذف المورد في supplier_detail"""
        client.force_login(viewer_user)
        url = reverse('supplier:supplier_detail', args=[sample_supplier.pk])
        response = client.get(url)
        assert response.status_code == 200

        content = response.content.decode('utf-8')
        edit_url = reverse('supplier:supplier_edit', args=[sample_supplier.pk])
        delete_url = reverse('supplier:supplier_delete', args=[sample_supplier.pk])

        assert edit_url not in content
        assert delete_url not in content


# =========================================================================
# 3. اختبارات القائمة الجانبية (Sidebar Orphan Headers Prevention)
# =========================================================================

@pytest.mark.django_db
class TestSidebarGating:

    def test_sales_rep_sidebar_does_not_leak_pricing_policies(self, client, sales_rep_user):
        """مندوب المبيعات لا تظهر له قوائم أسعار أو قواعد الخصم في القائمة الجانبية"""
        client.force_login(sales_rep_user)
        response = client.get(reverse('core:dashboard'))
        assert response.status_code == 200

        content = response.content.decode('utf-8')
        assert 'سياسات وقوائم الأسعار' not in content
        assert reverse('sale:price_list_list') not in content

    def test_viewer_sidebar_does_not_leak_hr_settings(self, client, viewer_user):
        """مستخدم الاستعلام لا تظهر له إعدادات الموارد البشرية أو البصمة"""
        client.force_login(viewer_user)
        response = client.get(reverse('core:dashboard'))
        assert response.status_code == 200

        content = response.content.decode('utf-8')
        assert 'نظام البصمة والإعدادات' not in content
        assert reverse('hr:hr_settings') not in content


# =========================================================================
# 4. مصفوفة التحقق من الأدوار القياسية (Roles Integrity Matrix)
# =========================================================================

@pytest.mark.django_db
class TestRolesIntegrity:

    def test_all_ten_canonical_roles_exist_and_system_protected(self, clean_roles):
        """التأكد من وجود الأدوار العشرة وكونها محمية كنظام (is_system_role=True)"""
        expected_roles = [
            'admin', 'financial_manager', 'accountant', 'sales_manager',
            'sales_rep', 'procurement_officer', 'inventory_manager',
            'production_supervisor', 'hr_officer', 'viewer'
        ]
        for role_name in expected_roles:
            role = Role.objects.filter(name=role_name).first()
            assert role is not None, f"Role {role_name} does not exist"
            assert role.is_system_role is True, f"Role {role_name} is not marked as system role"

# =========================================================================
# 5. اختبارات شاشات عروض الأسعار وأوامر الشغل الإضافية (Rule #1 Consistency)
# =========================================================================

@pytest.mark.django_db
class TestAdditionalDetailViewsGating:

    @pytest.fixture(autouse=True)
    def enable_work_orders(self, db):
        from core.models import SystemModule
        SystemModule.objects.update_or_create(
            code='work_orders',
            defaults={'name': 'أوامر الشغل', 'is_enabled': True}
        )

    def test_viewer_cannot_see_quotation_conversion_or_edit(self, client, viewer_user, sample_customer, superuser):
        """مستخدم الاستعلام لا يرى أزرار التحويل أو التعديل في تفاصيل عرض السعر"""
        from sale.models import Quotation
        quotation = Quotation.objects.create(
            number='QUO-P9-001',
            customer=sample_customer,
            date=timezone.now().date(),
            valid_until=timezone.now().date(),
            total=Decimal('500.00'),
            status='draft',
            created_by=superuser
        )

        client.force_login(viewer_user)
        url = reverse('sale:quotation_detail', args=[quotation.pk])
        response = client.get(url)
        assert response.status_code == 200

        content = response.content.decode('utf-8')
        edit_url = reverse('sale:quotation_edit', args=[quotation.pk])
        delete_url = reverse('sale:quotation_delete', args=[quotation.pk])
        convert_so_url = reverse('sale:sales_order_create_for_quotation', args=[quotation.pk])

        assert edit_url not in content
        assert delete_url not in content
        assert convert_so_url not in content

    def test_viewer_cannot_see_work_order_edit_or_delete(self, client, viewer_user, sample_customer, superuser):
        """مستخدم الاستعلام لا يرى أزرار تعديل أو حذف أمر الشغل"""
        from work_order.models import WorkOrder
        wo = WorkOrder.objects.create(
            number='WO-P9-001',
            customer=sample_customer,
            status='draft',
            created_by=superuser
        )

        client.force_login(viewer_user)
        url = reverse('work_order:work_order_detail', args=[wo.pk])
        response = client.get(url)
        assert response.status_code == 200

        content = response.content.decode('utf-8')
        edit_url = reverse('work_order:work_order_edit', args=[wo.pk])
        delete_url = reverse('work_order:work_order_delete', args=[wo.pk])

        assert edit_url not in content
        assert delete_url not in content

    def test_completed_work_order_does_not_show_edit_even_for_admin(self, client, sample_customer, superuser):
        """أمر الشغل المنتهي لا يعرض زر التعديل حتى للمشرف التزاماً بدورة حياة المستند"""
        from work_order.models import WorkOrder
        wo = WorkOrder.objects.create(
            number='WO-P9-002',
            customer=sample_customer,
            status='completed',
            created_by=superuser
        )

        client.force_login(superuser)
        url = reverse('work_order:work_order_detail', args=[wo.pk])
        response = client.get(url)
        assert response.status_code == 200

        content = response.content.decode('utf-8')
        edit_url = reverse('work_order:work_order_edit', args=[wo.pk])
        assert edit_url not in content


# =========================================================================
# 6. اختبارات لوحة إدارة الصلاحيات ومصفوفة الشخصيات (Personas Matrix)
# =========================================================================

@pytest.mark.django_db
class TestPermissionsDashboardAndPersonas:

    def test_non_superuser_cannot_access_permissions_dashboard(self, client, accountant_user):
        """المحاسب لا يمكنه الوصول إلى لوحة تحكم صلاحيات المستخدمين والأدوار"""
        client.force_login(accountant_user)
        url = reverse('users:permissions_dashboard')
        response = client.get(url)
        assert response.status_code == 403

    def test_superuser_sees_impersonate_button_in_users_tab(self, client, superuser, viewer_user):
        """المدير العام يرى زر الانتحال في جدول المستخدمين"""
        client.force_login(superuser)
        url = reverse('users:permissions_dashboard') + '?tab=users'
        response = client.get(url)
        assert response.status_code == 200

        content = response.content.decode('utf-8')
        assert 'login-as-user-btn' in content
        assert 'fa-user-secret' in content

    def test_accountant_can_view_journal_entries_but_not_hr(self, client, accountant_user):
        """المحاسب يمكنه رؤية القيود اليومية ولكن لا يملك صلاحية الموظفين أو الرواتب"""
        client.force_login(accountant_user)
        assert accountant_user.has_perm('financial.view_journalentry') is True
        assert accountant_user.has_perm('hr.view_employee') is False
        assert accountant_user.has_perm('hr.view_payroll') is False

    def test_sales_rep_has_no_financial_or_purchase_access(self, client, sales_rep_user):
        """مندوب المبيعات لا يملك صلاحيات محاسبية ولا مشتريات"""
        assert sales_rep_user.has_perm('sale.view_sale') is True
        assert sales_rep_user.has_perm('financial.view_journalentry') is False
        assert sales_rep_user.has_perm('purchase.view_purchase') is False

    def test_inventory_manager_has_warehouse_and_grn_perms(self, client, inventory_manager_user):
        """أمين المخزن يملك صلاحيات إذون الاستلام والمخازن ولا يملك فواتير بيع أو قيود"""
        assert inventory_manager_user.has_perm('product.view_warehouse') is True
        assert inventory_manager_user.has_perm('purchase.view_goodsreceivednote') is True
        assert inventory_manager_user.has_perm('sale.change_sale') is False
        assert inventory_manager_user.has_perm('financial.add_journalentry') is False

    @override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
    def test_permission_cache_invalidation_lifecycle(self, viewer_user):
        """التحقق من عمل PermissionCacheService وإبطاله بنظافة دون أخطاء"""
        from users.services.permission_cache import PermissionCacheService
        test_perms = {'sale.view_sale', 'purchase.view_purchase'}
        PermissionCacheService.set_user_permissions(viewer_user.id, test_perms)
        cached = PermissionCacheService.get_user_permissions(viewer_user.id)
        assert cached == test_perms

        PermissionCacheService.invalidate_user_cache(viewer_user.id)
        assert PermissionCacheService.get_user_permissions(viewer_user.id) is None

    def test_financial_manager_has_revaluation_perms(self, clean_roles):
        """المدير المالي يملك صلاحيات تقييم العملات وإغلاق الفترات"""
        fm_role = Role.objects.get(name='financial_manager')
        codenames = set(fm_role.permissions.values_list('codename', flat=True))
        assert 'view_currency' in codenames
        assert 'view_journalentry' in codenames
        assert 'view_accountingperiod' in codenames

    def test_production_supervisor_has_work_order_perms(self, clean_roles):
        """مسؤول الإنتاج يملك صلاحيات أوامر الشغل ومراحل الطباعة"""
        ps_role = Role.objects.get(name='production_supervisor')
        codenames = set(ps_role.permissions.values_list('codename', flat=True))
        assert 'view_workorder' in codenames
        assert 'view_printingorder' in codenames

    def test_hr_officer_has_exclusive_hr_perms(self, clean_roles):
        """مسؤول الموارد البشرية يملك صلاحيات الرواتب والموظفين فقط"""
        hr_role = Role.objects.get(name='hr_officer')
        app_labels = set(hr_role.permissions.values_list('content_type__app_label', flat=True))
        assert app_labels == {'hr'}

    def test_stop_impersonation_redirects_unauthenticated_or_missing_session(self, client):
        """إيقاف الانتحال يعيد التوجيه بأمان إذا لم تكن هناك جلسة انتحال نشطة"""
        url = reverse('users:stop_impersonation')
        response = client.get(url)
        assert response.status_code == 302
        assert response.url == '/login/?next=/users/stop-impersonation/'

