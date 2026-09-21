import pytest
import json
from decimal import Decimal
from datetime import date
from django.test import TestCase, RequestFactory, override_settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from users.models import Role
from sale.models import Sale, SaleItem
from purchase.models import Purchase, PurchaseItem
from customer.models import Customer
from supplier.models import Supplier
from product.models import Product, Category, Warehouse
from product.models.product_core import Unit
from financial.models.fiscal_year import FiscalYear
from financial.models.journal_entry import AccountingPeriod, JournalEntry
from financial.exceptions import PeriodClosedError
from sale.services.sale_service import SaleService
from financial.services.period_control_service import PeriodControlService
from customer.views import customer_add_ajax
from purchase.views.purchase_views import purchase_delete

User = get_user_model()


class RBACPhase3EnforcementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Clean cache before tests
        cache.clear()

        # Roles
        cls.admin_role, _ = Role.objects.get_or_create(
            name='admin', defaults={'display_name': 'مدير النظام', 'is_system_role': True}
        )
        cls.sales_rep_role, _ = Role.objects.get_or_create(
            name='sales_rep', defaults={'display_name': 'مندوب مبيعات', 'is_system_role': True}
        )
        cls.purchasing_role, _ = Role.objects.get_or_create(
            name='procurement_officer', defaults={'display_name': 'مسؤول المشتريات', 'is_system_role': True}
        )
        cls.accountant_role, _ = Role.objects.get_or_create(
            name='accountant', defaults={'display_name': 'محاسب', 'is_system_role': True}
        )
        cls.fin_mgr_role, _ = Role.objects.get_or_create(
            name='financial_manager', defaults={'display_name': 'مدير مالي', 'is_system_role': True}
        )

        # Users
        cls.admin_user = User.objects.create_user(
            username='admin_p3', email='admin@test.com', password='pass', role=cls.admin_role, is_superuser=True
        )
        cls.sales_rep = User.objects.create_user(
            username='rep_p3', email='rep@test.com', password='pass', role=cls.sales_rep_role
        )
        cls.procurement_user = User.objects.create_user(
            username='proc_p3', email='proc@test.com', password='pass', role=cls.purchasing_role
        )
        cls.accountant_user = User.objects.create_user(
            username='acc_p3', email='acc@test.com', password='pass', role=cls.accountant_role
        )
        cls.fin_mgr_user = User.objects.create_user(
            username='fin_mgr_p3', email='fin_mgr@test.com', password='pass', role=cls.fin_mgr_role
        )
        cls.regular_user = User.objects.create_user(
            username='regular_p3', email='reg@test.com', password='pass'
        )

        # Master Data
        cls.unit, _ = Unit.objects.get_or_create(name="قطعة", defaults={'symbol': 'قطعة'})
        cls.customer = Customer.objects.create(name="عميل اختبار المرحلة 3", code="CUST-P3-01", created_by=cls.admin_user)
        cls.supplier = Supplier.objects.create(name="مورد اختبار المرحلة 3", code="SUP-P3-01")
        cls.category = Category.objects.create(name="تصنيف اختبار 3", code="CAT-P3")
        cls.warehouse = Warehouse.objects.create(name="مخزن اختبار 3", code="WH-P3-01")
        cls.product = Product.objects.create(
            name="منتج تجريبي 3",
            sku="PRD-P3-01",
            unit=cls.unit,
            selling_price=Decimal("150.00"),
            cost_price=Decimal("90.00"),
            category=cls.category,
            created_by=cls.admin_user
        )

        # Factory
        cls.factory = RequestFactory()

    def setUp(self):
        cache.clear()

    # -------------------------------------------------------------------------
    # Test 1 & 2: Ghost Roles Purge & Standard 10 Roles
    # -------------------------------------------------------------------------
    def test_ghost_roles_purged_from_db(self):
        """التأكد من خلو قاعدة البيانات من الأدوار الشبحية الخمسة واستقرار الأدوار"""
        ghost_names = [
            'activities_coordinator',
            'transportation_coordinator',
            'receptionist',
            'manager',
            'hr_manager'
        ]
        found_ghosts = Role.objects.filter(name__in=ghost_names)
        assert not found_ghosts.exists(), f"وجدت أدوار شبحية في الداتابيز: {list(found_ghosts.values_list('name', flat=True))}"

    def test_standard_10_roles_seeded_with_permissions(self):
        """التأكد من وجود الأدوار المؤسسية القياسية وتخصيص صلاحيات لها"""
        standard_slugs = [
            'admin',
            'general_manager',
            'financial_manager',
            'chief_accountant',
            'accountant',
            'cashier',
            'warehouse_manager',
            'production_manager',
            'sales_manager',
            'sales_rep',
        ]
        for slug in standard_slugs:
            role = Role.objects.filter(name=slug).first()
            if role:
                assert role.is_system_role is True

    # -------------------------------------------------------------------------
    # Test 3 & 4: Permissions Delegation & Caching
    # -------------------------------------------------------------------------
    def test_user_get_all_permissions_delegates_to_backend(self):
        """التحقق من أن user.get_all_permissions() ترجع set[str] بصيغة app_label.codename"""
        # Assign a permission to sales_rep role
        perm = Permission.objects.filter(codename='view_sale').first()
        if perm:
            self.sales_rep_role.permissions.add(perm)

        perms = self.sales_rep.get_all_permissions()
        assert isinstance(perms, set)
        if perm:
            expected_perm = f"{perm.content_type.app_label}.{perm.codename}"
            assert expected_perm in perms

    @override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
    def test_superuser_cached_all_permissions(self):
        """التحقق من أن الـ Superuser يحصل على مجموعة الصلاحيات المخزنة مركزياً دون كويريز مكررة"""
        perms = self.admin_user.get_all_permissions()
        assert isinstance(perms, set)
        assert len(perms) > 0
        cached_global = cache.get("all_system_permissions_set")
        assert cached_global is not None

    # -------------------------------------------------------------------------
    # Test 5 & 6: Auto-Injected Implicit Dependencies
    # -------------------------------------------------------------------------
    def test_sales_rep_currency_warehouse_permissions(self):
        """مندوب المبيعات يحصل تلقائياً على العملات والمخازن والوحدات والضرائب"""
        # Ensure role has view_sale
        view_sale_perm = Permission.objects.filter(content_type__app_label='sale', codename='view_sale').first()
        if view_sale_perm:
            self.sales_rep_role.permissions.add(view_sale_perm)

        perms = self.sales_rep.get_all_permissions()
        assert "financial.view_currency" in perms
        assert "product.view_warehouse" in perms
        assert "product.view_unit" in perms
        assert "financial.view_taxrate" in perms

    def test_procurement_officer_currency_warehouse_permissions(self):
        """مسؤول المشتريات يحصل تلقائياً على صلاحيات العملات والمخازن والضرائب"""
        view_pur_perm = Permission.objects.filter(content_type__app_label='purchase', codename='view_purchase').first()
        if view_pur_perm:
            self.purchasing_role.permissions.add(view_pur_perm)

        perms = self.procurement_user.get_all_permissions()
        assert "financial.view_currency" in perms
        assert "product.view_warehouse" in perms

    # -------------------------------------------------------------------------
    # Test 7 & 8: Purchase Unit Cost Security
    # -------------------------------------------------------------------------
    def test_sales_rep_cannot_change_unit_cost_in_purchase(self):
        """مستخدم لا يملك purchase.change_unit_cost لا يستطيع تعديل تكلفة الشراء الأصلية"""
        # User without change_unit_cost
        assert not self.sales_rep.has_perm("purchase.change_unit_cost")

    def test_procurement_officer_with_perm_can_change_unit_cost(self):
        """مسؤول المشتريات الذي يملك purchase.change_unit_cost يتمتع بصلاحية تعديل تكلفة الشراء"""
        perm = Permission.objects.filter(content_type__app_label='purchase', codename='change_unit_cost').first()
        if perm:
            self.purchasing_role.permissions.add(perm)
            cache.clear()
            assert self.procurement_user.has_perm("purchase.change_unit_cost")

    # -------------------------------------------------------------------------
    # Test 9, 10, 11: Purchase Deletion & Accounting Immutability
    # -------------------------------------------------------------------------
    def test_purchase_delete_posted_prohibited(self):
        """حظر حذف فاتورة مشتريات مستلمة/مرحلة لمنع تمزيق الدفاتر والقيود المحاسبية"""
        # Give permission to procurement user
        del_perm = Permission.objects.filter(content_type__app_label='purchase', codename='delete_purchase').first()
        if del_perm:
            self.procurement_user.user_permissions.add(del_perm)

        purchase = Purchase.objects.create(
            number="PUR-TEST-POSTED-01",
            date=date(2026, 1, 1),
            supplier=self.supplier,
            warehouse=self.warehouse,
            payment_method="cash",
            subtotal=Decimal("1000.00"),
            total=Decimal("1000.00"),
            status="confirmed",
            created_by=self.procurement_user,
        )

        self.client.force_login(self.procurement_user)
        response = self.client.post(reverse("purchase:purchase_delete", kwargs={"pk": purchase.pk}))
        assert response.status_code == 302
        # Verify purchase still exists in DB!
        assert Purchase.objects.filter(pk=purchase.pk).exists()

    def test_purchase_delete_draft_safely_removes_lines_without_deleting_journal(self):
        """حذف فاتورة شراء مسودة يحذف سطورها بأمان دون مساس بأي قيود يومية"""
        del_perm = Permission.objects.filter(content_type__app_label='purchase', codename='delete_purchase').first()
        if del_perm:
            self.procurement_user.user_permissions.add(del_perm)

        purchase = Purchase.objects.create(
            number="PUR-TEST-DRAFT-01",
            date=date(2026, 1, 1),
            supplier=self.supplier,
            warehouse=self.warehouse,
            payment_method="cash",
            subtotal=Decimal("500.00"),
            total=Decimal("500.00"),
            status="draft",
            created_by=self.procurement_user,
        )
        PurchaseItem.objects.create(
            purchase=purchase,
            product=self.product,
            quantity=5,
            unit_price=Decimal("100.00"),
            total=Decimal("500.00")
        )

        self.client.force_login(self.procurement_user)
        response = self.client.post(reverse("purchase:purchase_delete", kwargs={"pk": purchase.pk}))
        assert response.status_code == 302
        assert not Purchase.objects.filter(pk=purchase.pk).exists()

    def test_purchase_delete_requires_delete_permission(self):
        """محاولة حذف فاتورة شراء بدون صلاحية delete_purchase ترفع PermissionDenied"""
        purchase = Purchase.objects.create(
            number="PUR-TEST-NO-PERM-01",
            date=date(2026, 1, 1),
            supplier=self.supplier,
            warehouse=self.warehouse,
            payment_method="cash",
            subtotal=Decimal("300.00"),
            total=Decimal("300.00"),
            status="draft",
            created_by=self.sales_rep,
        )

        self.client.force_login(self.sales_rep)
        response = self.client.post(reverse("purchase:purchase_delete", kwargs={"pk": purchase.pk}))
        assert response.status_code == 403

    # -------------------------------------------------------------------------
    # Test 12, 13, 14: Sale Deletion & Accounting Immutability
    # -------------------------------------------------------------------------
    def test_sale_delete_posted_prohibited(self):
        """محاولة حذف فاتورة مبيعات مرحلة أو مكتملة عبر SaleService ترفع ValidationError"""
        sale = Sale.objects.create(
            number="INV-TEST-POSTED-01",
            date=date(2026, 1, 1),
            customer=self.customer,
            warehouse=self.warehouse,
            payment_method="cash",
            subtotal=Decimal("1500.00"),
            total=Decimal("1500.00"),
            status="confirmed",
            created_by=self.admin_user,
        )

        with pytest.raises(ValidationError):
            SaleService.delete_sale(sale, user=self.admin_user)
        assert Sale.objects.filter(pk=sale.pk).exists()

    def test_sale_delete_draft_allowed_with_permission(self):
        """حذف فاتورة مبيعات مسودة ينجح للمستخدم المخول بصلاحية sale.delete_sale"""
        sale = Sale.objects.create(
            number="INV-TEST-DRAFT-01",
            date=date(2026, 1, 1),
            customer=self.customer,
            warehouse=self.warehouse,
            payment_method="cash",
            subtotal=Decimal("200.00"),
            total=Decimal("200.00"),
            status="draft",
            created_by=self.admin_user,
        )
        SaleItem.objects.create(
            sale=sale,
            product=self.product,
            quantity=Decimal("1"),
            unit_price=Decimal("200.00"),
            total=Decimal("200.00")
        )

        success = SaleService.delete_sale(sale, user=self.admin_user)
        assert success is True
        assert not Sale.objects.filter(pk=sale.pk).exists()

    def test_sale_delete_without_permission_denied(self):
        """حذف فاتورة المبيعات يرفع PermissionDenied إذا كان المستخدم يفتقر للصلاحية"""
        sale = Sale.objects.create(
            number="INV-TEST-DRAFT-02",
            date=date(2026, 1, 1),
            customer=self.customer,
            warehouse=self.warehouse,
            payment_method="cash",
            subtotal=Decimal("200.00"),
            total=Decimal("200.00"),
            status="draft",
            created_by=self.sales_rep,
        )

        with pytest.raises(PermissionDenied):
            SaleService.delete_sale(sale, user=self.sales_rep)

    # -------------------------------------------------------------------------
    # Test 15 & 16: Customer Quick Add Zero-Credit & RBAC
    # -------------------------------------------------------------------------
    def test_customer_quick_add_zero_credit_enforced(self):
        """إضافة عميل عبر customer_add_ajax من مندوب مبيعات تضبط سقف الائتمان تلقائياً بـ 0.00"""
        # Grant add_customer to sales_rep
        add_perm = Permission.objects.filter(content_type__app_label='customer', codename='add_customer').first()
        if add_perm:
            self.sales_rep.user_permissions.add(add_perm)

        request = self.factory.post(
            reverse("customer:customer_add_ajax"),
            data={
                "code": "CUST-P3-999",
                "name": "عميل سريع تجريبي",
                "phone": "+201012345678",
                "credit_limit": "50000.00",  # Representative attempts to grant 50k credit!
            }
        )
        request.user = self.sales_rep

        response = customer_add_ajax(request)
        assert response.status_code == 200
        data = json.loads(response.content.decode('utf-8'))
        assert data.get("success") is True
        created_cust = Customer.objects.get(pk=data["customer"]["id"])
        # Verified: Credit limit MUST be 0.00!
        assert created_cust.credit_limit == Decimal("0.00")

    def test_customer_quick_add_denied_without_add_perm(self):
        """رفض استدعاء customer_add_ajax لمستخدم يفتقر لصلاحية customer.add_customer بـ 403"""
        request = self.factory.post(
            reverse("customer:customer_add_ajax"),
            data={"name": "عميل غير مصرح"}
        )
        request.user = self.regular_user

        response = customer_add_ajax(request)
        assert response.status_code == 403
        data = json.loads(response.content.decode('utf-8'))
        assert data.get("success") is False

    # -------------------------------------------------------------------------
    # Test 17: Period Close Draft Guard & RBAC
    # -------------------------------------------------------------------------
    def test_period_close_draft_guard_and_permission(self):
        """التحقق من أن إغلاق الفترة يشترط صلاحية financial.close_accounting_period ويحظر المسودات"""
        fy, _ = FiscalYear.objects.get_or_create(
            year_code="FY2045-P3",
            defaults={
                "name": "سنة 2045 تجريبية",
                "start_date": date(2045, 1, 1),
                "end_date": date(2045, 12, 31),
                "status": "open"
            }
        )
        AccountingPeriod.objects.filter(start_date=date(2045, 1, 1), end_date=date(2045, 1, 31)).delete()
        period = AccountingPeriod.objects.create(
            fiscal_year=fy,
            name="فترة يناير 2045",
            period_number=1,
            start_date=date(2045, 1, 1),
            end_date=date(2045, 1, 31),
            status="open"
        )

        # 1. Permission Denied test
        with pytest.raises(PermissionDenied):
            PeriodControlService.close_period(period.id, user=self.sales_rep)

        # 2. Draft Guard test (with authorized user)
        JournalEntry.objects.create(
            number="JE-DRAFT-01",
            accounting_period=period,
            date=date(2045, 1, 15),
            status="draft",
            description="قيد مسودة تجريبي"
        )
        with pytest.raises(PeriodClosedError) as exc_info:
            PeriodControlService.close_period(period.id, user=self.admin_user)
        assert "يوجد 1 قيد مسودة" in str(exc_info.value)

    # -------------------------------------------------------------------------
    # Test 18: Cache Invalidation on Role Permission Change
    # -------------------------------------------------------------------------
    @override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
    def test_cache_invalidation_on_role_permission_change(self):
        """التحقق من مسح الكاش Tier-2 عند تعديل صلاحيات الدور عبر الإشارات"""
        # Clear cache first
        cache.clear()
        # Seed cache for user
        self.sales_rep.get_all_permissions()
        cache_key = f"user_perms_{self.sales_rep.id}"
        assert cache.get(cache_key) is not None

        # Add a permission to the role -> triggers m2m_changed signal
        some_perm = Permission.objects.exclude(codename__in=self.sales_rep_role.permissions.values_list('codename', flat=True)).first()
        if some_perm:
            self.sales_rep_role.permissions.add(some_perm)
            # The signal should have invalidated the cache!
            assert cache.get(cache_key) is None
